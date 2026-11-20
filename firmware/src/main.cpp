// Sentinela de Cadeia Fria - firmware da CF-01 (caixa que mede). N3, v2.
// Contrato MQTT: CONTRATOS.md v1. Pinos: docs/n3/PINAGEM.md.
//
// Maquina de estados local (FECHADO -> EXPOSTO -> QUEBRA) que funciona sem rede,
// mais os modos do fluxograma do CP12 (5.3):
//   AUTOMATICO : regra local (semaforo e alarme); rele so por comando/regra do backend.
//   MANUAL     : comando de usuario aceito sobre rele/buzzer; volta em 10 min ou por "auto".
//   SEGURO     : 3 leituras invalidas do sensor; orcamento congelado, LED azul;
//                sai com 2 leituras validas.

#include <Arduino.h>
#include <DHT.h>
#include <Preferences.h>

#include "Comum.h"
#include "Logica.h"

using logica::Modo;

// Mapa de pinos (docs/n3/PINAGEM.md).
constexpr uint8_t PINO_DHT    = 4;
constexpr uint8_t PINO_TAMPA  = 18;
constexpr uint8_t PINO_RESET  = 19;
constexpr uint8_t PINO_BUZZER = 27;
constexpr uint8_t PINO_LED_R  = 25;
constexpr uint8_t PINO_LED_G  = 26;
constexpr uint8_t PINO_LED_B  = 33;
constexpr uint8_t PINO_RELE   = 23;

// LED RGB: true = catodo comum (HIGH acende).
constexpr bool LED_ATIVO_ALTO = true;
// Modulo rele de 2 canais, opto-isolado: active-low (contato fecha com nivel baixo).
constexpr bool RELE_ATIVO_ALTO = false;
// Buzzer: true se for passivo (precisa de tone()); false se for ativo.
constexpr bool     BUZZER_PASSIVO = false;
constexpr uint16_t BUZZER_FREQ_HZ = 2000;

#define TIPO_DHT DHT11
DHT dht(PINO_DHT, TIPO_DHT);

constexpr uint32_t INTERVALO_DHT_MS        = 2000;
constexpr uint32_t TICK_MS                 = 1000;
constexpr uint32_t DEBOUNCE_MS             = 30;
constexpr uint32_t PISCA_MS                = 300;
constexpr uint32_t INTERVALO_TELEMETRIA_MS = 5000;   // contrato: 5 s
constexpr float    ORCAMENTO_PADRAO        = 120.0f;

// --- Debounce reutilizavel para chaves em INPUT_PULLUP (solto = HIGH) ---
struct Chave {
  uint8_t  pino;
  bool     nivel;
  bool     bruto;
  uint32_t marcador;

  void iniciar(uint8_t p) {
    pino = p;
    pinMode(pino, INPUT_PULLUP);
    nivel = bruto = (digitalRead(pino) == HIGH);
    marcador = 0;
  }

  bool atualizar(uint32_t agora) {
    bool leitura = (digitalRead(pino) == HIGH);
    if (leitura != bruto) { bruto = leitura; marcador = agora; }
    if ((agora - marcador) >= DEBOUNCE_MS && leitura != nivel) {
      nivel = leitura;
      return true;
    }
    return false;
  }
};

Chave tampa;
Chave botaoReset;

enum class Estado { FECHADO, EXPOSTO, QUEBRA };
enum class Forcado : uint8_t { NENHUM, LIGADO, SILENCIADO };

Estado estado = Estado::FECHADO;
Modo   modo   = Modo::AUTOMATICO;
logica::TimerManual   manual;
logica::FiltroSensor  filtro;
Forcado buzzerForcado = Forcado::NENHUM;

Preferences prefs;
float orcamentoInicial = ORCAMENTO_PADRAO;   // persistido em NVS, alteravel por "config"
float orcamento        = ORCAMENTO_PADRAO;
float orcamentoNaAbertura = ORCAMENTO_PADRAO;

float    ultimaTemperatura = NAN;
float    ultimaUmidade     = NAN;
bool     releLigado        = false;
bool     buzzerAtual       = false;   // nivel fisico atual (evita reescrever o tone())

uint32_t inicioExposicao = 0;
float    somaTemp        = 0;
uint32_t amostrasTemp    = 0;
uint16_t aberturas       = 0;

uint32_t ultimaLeituraDht = 0;
uint32_t ultimoTick       = 0;
uint32_t ultimoPisca      = 0;
uint32_t ultimaTelemetria = 0;
bool     piscaLigado      = false;
bool     bootPublicado    = false;

// Assinatura do que o topico "estado" mostra; mudou -> republica (retido).
uint8_t assinaturaPublicada = 0xFF;

// ---------------------------------------------------------------------------
// Saidas fisicas
// ---------------------------------------------------------------------------
void escreveLed(uint8_t pino, bool ligado) { digitalWrite(pino, (ligado == LED_ATIVO_ALTO) ? HIGH : LOW); }

void setCor(bool r, bool g, bool b) {
  escreveLed(PINO_LED_R, r);
  escreveLed(PINO_LED_G, g);
  escreveLed(PINO_LED_B, b);
}

void buzzerFisico(bool ligado) {
  if (ligado == buzzerAtual) return;
  buzzerAtual = ligado;
  if (BUZZER_PASSIVO) {
    ligado ? tone(PINO_BUZZER, BUZZER_FREQ_HZ) : noTone(PINO_BUZZER);
  } else {
    digitalWrite(PINO_BUZZER, ligado ? HIGH : LOW);
  }
}

void setRele(bool ligado) {
  releLigado = ligado;
  digitalWrite(PINO_RELE, (ligado == RELE_ATIVO_ALTO) ? HIGH : LOW);
}

// O que o buzzer "deve estar fazendo" (o que o topico estado informa).
bool buzzerLogico() {
  if (buzzerForcado == Forcado::LIGADO) return true;
  if (buzzerForcado == Forcado::SILENCIADO) return false;
  return estado == Estado::QUEBRA;
}

void aplicarBuzzer() {
  bool som;
  if (buzzerForcado == Forcado::LIGADO) som = true;
  else if (buzzerForcado == Forcado::SILENCIADO) som = false;
  else som = (estado == Estado::QUEBRA) && piscaLigado;   // intermitente na QUEBRA
  buzzerFisico(som);
}

// Cor do semaforo fora da QUEBRA (a QUEBRA pisca em vermelho no loop).
void atualizarLed() {
  if (estado == Estado::QUEBRA) return;
  if (modo == Modo::SEGURO) { setCor(false, false, true); return; }   // azul
  if (estado == Estado::EXPOSTO) setCor(true, true, false);           // amarelo
  else setCor(false, true, false);                                    // verde
}

float consumoPorSegundo(float t) {
  float c = 1.0f + (t - 20.0f) / 10.0f;
  return c < 0 ? 0 : c;
}

const char* nomeEstado(Estado e) {
  switch (e) {
    case Estado::FECHADO: return "FECHADO";
    case Estado::EXPOSTO: return "EXPOSTO";
    case Estado::QUEBRA:  return "QUEBRA";
  }
  return "?";
}

// ---------------------------------------------------------------------------
// Publicacao
// ---------------------------------------------------------------------------
float tempMediaExposicao() { return amostrasTemp ? somaTemp / amostrasTemp : ultimaTemperatura; }

void publicarTelemetria() {
  char buf[512];
  logica::JsonBuf j(buf, sizeof(buf));
  comum::cabecalho(j);
  j.add(",\"estado\":\"%s\",\"modo\":\"%s\"", nomeEstado(estado), logica::nomeModo(modo));
  j.grandeza("temperatura", ultimaTemperatura, UNIDADE_C, 1);   // null com sensor em falha
  j.grandeza("umidade", ultimaUmidade, "%", 0);
  j.grandeza("orcamento", orcamento, "u", 1);
  j.add(",\"aberturas\":%u", (unsigned)aberturas);
  j.grandeza("rssi", (float)comum::rssi(), "dBm", 0);
  j.add("}");
  comum::publicar("telemetria", j, false);
}

uint8_t assinaturaEstado() {
  return (uint8_t)(((uint8_t)modo) | (releLigado ? 4 : 0) | (buzzerLogico() ? 8 : 0) | (filtro.seguro ? 16 : 0));
}

// Estado dos atuadores e do modo, retido. Chamado quando algo muda ou ao reconectar.
bool publicarEstado() {
  char buf[320];
  logica::JsonBuf j(buf, sizeof(buf));
  comum::cabecalho(j);
  j.add(",\"modo\":\"%s\",\"rele\":\"%s\",\"buzzer\":\"%s\",\"sensor\":\"%s\"}",
        logica::nomeModo(modo), releLigado ? "ligado" : "desligado",
        buzzerLogico() ? "ligado" : "desligado", filtro.seguro ? "falha" : "ok");
  return comum::publicar("estado", j, true);
}

void manterEstadoPublicado() {
  if (!comum::mqttConectado()) return;
  uint8_t a = assinaturaEstado();
  if (a == assinaturaPublicada) return;
  if (publicarEstado()) assinaturaPublicada = a;
}

// ---------------------------------------------------------------------------
// Modos
// ---------------------------------------------------------------------------
void setModo(Modo novo) {
  if (novo == modo) return;
  char det[32];
  snprintf(det, sizeof(det), "%s->%s", logica::nomeModo(modo), logica::nomeModo(novo));
  Serial.printf("MODO: %s\n", det);
  modo = novo;
  atualizarLed();
  comum::publicarEvento("modo_alterado", -1, NAN, NAN, NAN, orcamento, det);
}

// Volta ao AUTOMATICO (timeout, comando "auto" ou saida do SEGURO): solta o
// que estava forcado; o rele volta ao padrao local (aceso so durante a QUEBRA).
void voltarAutomatico() {
  manual.cancela();
  buzzerForcado = Forcado::NENHUM;
  setRele(estado == Estado::QUEBRA);
  setModo(Modo::AUTOMATICO);
}

// ---------------------------------------------------------------------------
// Transicoes da maquina de estados
// ---------------------------------------------------------------------------
void irParaFechado() {
  estado = Estado::FECHADO;
  atualizarLed();
  aplicarBuzzer();
}

void irParaExposto(uint32_t agora) {
  estado = Estado::EXPOSTO;
  inicioExposicao = agora;
  somaTemp = 0;
  amostrasTemp = 0;
  aberturas++;
  orcamentoNaAbertura = orcamento;
  atualizarLed();
  aplicarBuzzer();
  Serial.printf("ABERTURA #%u\n", aberturas);
  comum::publicarEvento("abertura", aberturas, NAN, NAN, NAN, orcamento, nullptr);
}

void irParaQuebra() {
  estado = Estado::QUEBRA;
  orcamento = 0;
  Serial.printf("QUEBRA  aberturas=%u  Tmed=%.1fC\n", aberturas, tempMediaExposicao());
  comum::publicarEvento("quebra", aberturas, NAN, tempMediaExposicao(), orcamentoNaAbertura - orcamento, orcamento, nullptr);
  // Seguranca primeiro: a QUEBRA tira o dispositivo do MANUAL. Assim o buzzer
  // silenciado/forcado e o relé do operador nao impedem o alarme, e o comando
  // "rele ligar" da regra de QUEBRA (origem "regra") deixa de ser rejeitado.
  if (modo == Modo::MANUAL) voltarAutomatico();
}

// Reset (botao ou comando): libera a QUEBRA, restaura o orcamento e solta a
// retencao (sinalizador apagado, alarme sem silenciamento).
void fazerReset(const char* detalhe) {
  orcamento = orcamentoInicial;
  buzzerForcado = Forcado::NENHUM;
  setRele(false);
  irParaFechado();
  Serial.println("RESET");
  comum::publicarEvento("reset", aberturas, NAN, NAN, NAN, orcamento, detalhe);
}

// ---------------------------------------------------------------------------
// Comandos (ciclo aceito -> executado em lib/comum)
// ---------------------------------------------------------------------------
const char* validarComando(const logica::Comando& c, const char** detalhe) {
  return logica::validarCf01(c, estado == Estado::QUEBRA, modo, detalhe);
}

void executarComando(const logica::Comando& c) {
  const uint32_t agora = millis();
  const Modo antes = modo;
  const Modo depois = logica::proximoModo(modo, c);
  const bool pedeAuto = logica::igual(c.acao, "auto");

  if (logica::igual(c.nome, "rele") && !pedeAuto) {
    setRele(logica::igual(c.acao, "ligar"));
  } else if (logica::igual(c.nome, "buzzer") && !pedeAuto) {
    buzzerForcado = logica::igual(c.acao, "disparar") ? Forcado::LIGADO : Forcado::SILENCIADO;
    aplicarBuzzer();
  } else if (logica::igual(c.nome, "reset")) {
    fazerReset("comando");
  } else if (logica::igual(c.nome, "config")) {
    orcamentoInicial = c.valor;
    prefs.putFloat("orcIni", orcamentoInicial);
    if (estado == Estado::FECHADO) orcamento = orcamentoInicial;   // vale ja se nao ha exposicao em curso
    Serial.printf("CONFIG: orcamentoInicial=%.1f (salvo em NVS)\n", orcamentoInicial);
  }

  // Modo: "auto" so tem efeito se estava em MANUAL; usuario leva a MANUAL (renova os 10 min).
  if (depois == Modo::AUTOMATICO && antes == Modo::MANUAL) {
    voltarAutomatico();
  } else if (depois == Modo::MANUAL) {
    manual.inicia(agora);
    setModo(Modo::MANUAL);
  }
}

// Apos cada (re)conexao: publica o estado atual e, uma vez por boot, o evento "boot".
void aoConectar() {
  assinaturaPublicada = 0xFF;   // forca republicar o estado retido
  manterEstadoPublicado();
  if (!bootPublicado) {
    if (comum::publicarEvento("boot", -1, NAN, NAN, NAN, orcamento, nullptr)) bootPublicado = true;
  }
}

// ---------------------------------------------------------------------------
// Sensor
// ---------------------------------------------------------------------------
void lerSensor() {
  float t = dht.readTemperature();
  float u = dht.readHumidity();
  bool valida = logica::temperaturaValida(t) && logica::umidadeValida(u);

  // Leitura invalida nao substitui a ultima valida (ate entrar em SEGURO).
  if (valida) { ultimaTemperatura = t; ultimaUmidade = u; }

  switch (filtro.registra(valida)) {
    case logica::Transicao::ENTROU:
      Serial.println("SENSOR: 3 leituras invalidas, entrando em SEGURO");
      manual.cancela();
      ultimaTemperatura = NAN;   // a telemetria passa a mostrar null
      ultimaUmidade = NAN;
      comum::publicarEvento("sensor_falha", -1, NAN, NAN, NAN, orcamento, nullptr);
      setModo(Modo::SEGURO);
      break;
    case logica::Transicao::SAIU:
      Serial.println("SENSOR: 2 leituras validas, saindo do SEGURO");
      comum::publicarEvento("sensor_ok", -1, NAN, NAN, NAN, orcamento, nullptr);
      voltarAutomatico();
      break;
    case logica::Transicao::NENHUMA:
      break;
  }
}

// ---------------------------------------------------------------------------
void setup() {
  // Rele antes de tudo: o modulo e active-low, entao o nivel de repouso vai
  // para o latch do pino ANTES de ele virar saida (sem pisco no boot).
  setRele(false);
  pinMode(PINO_RELE, OUTPUT);

  Serial.begin(115200);
  delay(500);
  Serial.println();
  Serial.println("=== Sentinela de Cadeia Fria - CF-01 v2 ===");

  pinMode(PINO_LED_R, OUTPUT);
  pinMode(PINO_LED_G, OUTPUT);
  pinMode(PINO_LED_B, OUTPUT);
  pinMode(PINO_BUZZER, OUTPUT);

  // Orcamento inicial persistido; valor fora da faixa na NVS volta ao padrao.
  prefs.begin("sentinela", false);
  orcamentoInicial = prefs.getFloat("orcIni", ORCAMENTO_PADRAO);
  if (!logica::orcamentoConfigValido(orcamentoInicial)) orcamentoInicial = ORCAMENTO_PADRAO;
  orcamento = orcamentoInicial;
  Serial.printf("NVS: orcamentoInicial=%.1f\n", orcamentoInicial);

  tampa.iniciar(PINO_TAMPA);
  botaoReset.iniciar(PINO_RESET);
  dht.begin();

  buzzerFisico(false);
  irParaFechado();

  comum::iniciar(validarComando, executarComando, aoConectar);
  Serial.println("Pronto. Estado inicial: FECHADO, modo AUTOMATICO.");
}

void loop() {
  const uint32_t agora = millis();

  // Rede: independente da logica local; se cair, o resto segue funcionando.
  comum::atualizar(agora);

  if (manual.expirou(agora) && modo == Modo::MANUAL) {
    Serial.println("MANUAL: 10 min sem comando, voltando ao AUTOMATICO");
    voltarAutomatico();
  }

  // Transicoes por tampa (ignoradas em QUEBRA, que so sai por reset).
  if (tampa.atualizar(agora)) {
    bool aberta = tampa.nivel;
    if (aberta && estado == Estado::FECHADO) {
      irParaExposto(agora);
    } else if (!aberta && estado == Estado::EXPOSTO) {
      uint32_t dur = (agora - inicioExposicao) / 1000;
      float tmed = tempMediaExposicao();
      Serial.printf("FECHAMENTO #%u  dur=%us  Tmed=%.1fC  restante=%.1f\n", aberturas, (unsigned)dur, tmed, orcamento);
      comum::publicarEvento("fechamento", aberturas, (float)dur, tmed, orcamentoNaAbertura - orcamento, orcamento, nullptr);
      irParaFechado();
    }
  }

  // Botao fisico de reset: so tem efeito em QUEBRA (apertado = LOW).
  if (botaoReset.atualizar(agora) && !botaoReset.nivel && estado == Estado::QUEBRA) {
    fazerReset("botao");
  }

  if (agora - ultimaLeituraDht >= INTERVALO_DHT_MS) {
    ultimaLeituraDht = agora;
    lerSensor();
  }

  // Drenagem do orcamento: 1 passo por segundo, so EXPOSTO, e congelada em SEGURO.
  if (agora - ultimoTick >= TICK_MS) {
    ultimoTick = agora;
    if (estado == Estado::EXPOSTO && modo != Modo::SEGURO && !isnan(ultimaTemperatura)) {
      orcamento -= consumoPorSegundo(ultimaTemperatura);
      somaTemp += ultimaTemperatura;
      amostrasTemp++;
      Serial.printf("EXPOSTO  T=%.1fC  restante=%.1f\n", ultimaTemperatura, orcamento);
      if (orcamento <= 0) irParaQuebra();
    }
  }

  // QUEBRA: vermelho intermitente; o buzzer acompanha o pisca (salvo forcado por comando).
  if (estado == Estado::QUEBRA && agora - ultimoPisca >= PISCA_MS) {
    ultimoPisca = agora;
    piscaLigado = !piscaLigado;
    if (piscaLigado) setCor(true, false, false);
    else setCor(false, false, false);
  }
  aplicarBuzzer();

  if (comum::mqttConectado() && agora - ultimaTelemetria >= INTERVALO_TELEMETRIA_MS) {
    ultimaTelemetria = agora;
    publicarTelemetria();
  }
  manterEstadoPublicado();
}
