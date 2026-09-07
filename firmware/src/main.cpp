// Sentinela de Cadeia Fria - firmware (ESP32).
// Parte 6: buzzer (alarme na QUEBRA) e rele (sinalizador de retencao).
// Parte 7: Wi-Fi com reconexao automatica (tarefa 7 do backlog).

#include <Arduino.h>
#include <DHT.h>
#include <WiFi.h>

// Mapa de pinos (pinos testes, confirmar pinos reais no hardware fisico).
constexpr uint8_t PINO_DHT    = 4;
constexpr uint8_t PINO_TAMPA  = 18;
constexpr uint8_t PINO_RESET  = 19;
constexpr uint8_t PINO_BUZZER = 27;
constexpr uint8_t PINO_LED_R  = 25;
constexpr uint8_t PINO_LED_G  = 26;
constexpr uint8_t PINO_LED_B  = 33;
constexpr uint8_t PINO_RELE   = 23;

// LED RGB: true = catodo comum (HIGH acende). Ajustar conforme a bancada.
constexpr bool LED_ATIVO_ALTO = true;
// Modulo rele: muitos sao active-low. Ajustar conforme o modulo.
constexpr bool RELE_ATIVO_ALTO = true;
constexpr uint16_t BUZZER_FREQ_HZ = 2000;

// Duas diferencas conhecidas entre a bancada e a simulacao (ver docs/simulacao-wokwi.md):
// 1. o Wokwi nao tem peca DHT11 - a simulacao usa DHT22, mesmo protocolo de 1 fio;
// 2. a peca de buzzer do Wokwi e piezo (passiva) e precisa de tone().
#ifdef SIM_WOKWI
  #define TIPO_DHT DHT22
  constexpr bool BUZZER_PASSIVO = true;
#else
  #define TIPO_DHT DHT11
  // true se for passivo (precisa de tone()); false se for ativo. Confirmar na bancada.
  constexpr bool BUZZER_PASSIVO = false;
#endif
DHT dht(PINO_DHT, TIPO_DHT);

// --- Credenciais de Wi-Fi -------------------------------------------------
// Na simulacao usamos o AP virtual aberto do Wokwi (canal 6 explicito acelera
// muito a associacao). Na bancada, as credenciais vem de include/secrets.h,
// que esta no .gitignore - o repositorio versiona apenas secrets.h.example.
#ifdef SIM_WOKWI
  #define WIFI_SSID  "Wokwi-GUEST"
  #define WIFI_SENHA ""
  constexpr int WIFI_CANAL = 6;
#else
  #if __has_include("secrets.h")
    #include "secrets.h"
  #else
    #error "Falta include/secrets.h - copie include/secrets.h.example e preencha SSID/senha."
  #endif
  constexpr int WIFI_CANAL = 0;  // 0 = descobrir por varredura
#endif

constexpr uint32_t INTERVALO_DHT_MS = 2000;
constexpr uint32_t TICK_MS          = 1000;  // passo da drenagem do orcamento
constexpr uint32_t DEBOUNCE_MS      = 30;
constexpr uint32_t PISCA_MS         = 300;   // piscada/bip em QUEBRA
constexpr float    ORCAMENTO_INICIAL = 120.0f;

// --- Debounce reutilizavel para chaves em INPUT_PULLUP (solto = HIGH) ---
struct Chave {
  uint8_t  pino;
  bool     nivel;      // estado ja estabilizado
  bool     bruto;      // ultima leitura crua
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

Chave tampa;   // aberta = solto = HIGH (confirmar montagem mecanica)
Chave botaoReset;

enum class Estado { FECHADO, EXPOSTO, QUEBRA };
Estado estado = Estado::FECHADO;

float    orcamento         = ORCAMENTO_INICIAL;
float    ultimaTemperatura = NAN;
bool     releLigado        = false;

// Acumuladores da exposicao corrente.
uint32_t inicioExposicao = 0;
float    somaTemp        = 0;
uint32_t amostrasTemp    = 0;
uint16_t aberturas       = 0;

uint32_t ultimaLeituraDht = 0;
uint32_t ultimoTick       = 0;
uint32_t ultimoPisca      = 0;
bool     piscaLigado      = false;

// ==========================================================================
// Rede - Wi-Fi nao bloqueante com reconexao automatica (tarefa 7 do backlog)
// ==========================================================================
// Premissa do RISCO-02: a rede VAI cair. Nada aqui pode travar o laco - a
// maquina de estados, o semaforo e o buzzer continuam operando sem rede.
// Por isso nenhum "while (WiFi.status() != WL_CONNECTED) delay(500)": o
// progresso da associacao e verificado por amostragem, a cada volta do loop().

constexpr uint32_t WIFI_CHECAGEM_MS   = 500;    // com que frequencia olhamos o status
constexpr uint32_t WIFI_BACKOFF_MIN_MS = 1000;  // 1a espera entre tentativas
constexpr uint32_t WIFI_BACKOFF_MAX_MS = 16000; // teto do backoff exponencial
constexpr uint32_t WIFI_TIMEOUT_MS    = 10000;  // desiste da tentativa e recomeca
constexpr uint32_t WIFI_HEARTBEAT_MS  = 10000;  // log periodico de RSSI

enum class EstadoRede { OFFLINE, ASSOCIANDO, ONLINE };
EstadoRede estadoRede = EstadoRede::OFFLINE;

uint32_t wifiUltimaChecagem = 0;
uint32_t wifiInicioTentativa = 0;
uint32_t wifiProximaTentativa = 0;
uint32_t wifiBackoff        = WIFI_BACKOFF_MIN_MS;
uint32_t wifiQuedaEm        = 0;   // millis do instante em que a queda foi detectada
uint32_t wifiUltimoHeartbeat = 0;
uint16_t wifiTentativas     = 0;   // tentativas da rodada corrente
uint16_t wifiQuedas         = 0;   // quantas vezes a rede caiu desde o boot
bool     wifiJaConectouUmaVez = false;

// Traducao do RSSI para linguagem de campo. Referencia usada no projeto:
//   >= -60 dBm otimo | -60..-70 bom | -70..-80 fraco | < -80 instavel
const char* qualidadeRssi(int32_t rssi) {
  if (rssi >= -60) return "otimo";
  if (rssi >= -70) return "bom";
  if (rssi >= -80) return "fraco";
  return "instavel";
}

void logIpDoDhcp() {
  // Nenhum IP e fixado no codigo: quem entrega endereco, mascara, gateway e DNS
  // e o servidor DHCP do roteador. Imprimimos o que foi RECEBIDO.
  Serial.printf("[WiFi] IP (DHCP): %s   mascara: %s   gateway: %s   DNS: %s\n",
                WiFi.localIP().toString().c_str(),
                WiFi.subnetMask().toString().c_str(),
                WiFi.gatewayIP().toString().c_str(),
                WiFi.dnsIP().toString().c_str());
  Serial.printf("[WiFi] MAC: %s   canal: %d   RSSI: %ld dBm (%s)\n",
                WiFi.macAddress().c_str(), WiFi.channel(),
                (long)WiFi.RSSI(), qualidadeRssi(WiFi.RSSI()));
}

void iniciarTentativaWifi(uint32_t agora) {
  wifiTentativas++;
  wifiInicioTentativa = agora;
  estadoRede = EstadoRede::ASSOCIANDO;
  Serial.printf("[WiFi] tentativa %u de associacao a \"%s\"...\n",
                wifiTentativas, WIFI_SSID);
  WiFi.disconnect();       // limpa a associacao anterior sem desligar o radio
  WiFi.begin(WIFI_SSID, WIFI_SENHA, WIFI_CANAL);
}

void iniciarRede() {
  WiFi.mode(WIFI_STA);
  // Desligamos a reconexao automatica da pilha para que a reconexao seja
  // NOSSA e apareca no log - a evidencia pedida e ver o firmware reagindo.
  WiFi.setAutoReconnect(false);
  WiFi.persistent(false);
  Serial.println("[WiFi] modo estacao (STA). Sem IP fixo: o endereco vem por DHCP.");
  iniciarTentativaWifi(millis());
}

void atualizarRede(uint32_t agora) {
  if (agora - wifiUltimaChecagem < WIFI_CHECAGEM_MS) return;
  wifiUltimaChecagem = agora;

  bool conectado = (WiFi.status() == WL_CONNECTED);

  switch (estadoRede) {
    case EstadoRede::ASSOCIANDO:
      if (conectado) {
        uint32_t levou = agora - wifiInicioTentativa;
        if (wifiJaConectouUmaVez) {
          Serial.printf("[WiFi] === RECONECTADO === queda #%u durou %.1f s "
                        "(%u tentativa(s), ultima levou %u ms)\n",
                        wifiQuedas, (agora - wifiQuedaEm) / 1000.0f,
                        wifiTentativas, levou);
        } else {
          Serial.printf("[WiFi] === CONECTADO === em %u ms (%u tentativa(s))\n",
                        levou, wifiTentativas);
          wifiJaConectouUmaVez = true;
        }
        logIpDoDhcp();
        estadoRede = EstadoRede::ONLINE;
        wifiBackoff = WIFI_BACKOFF_MIN_MS;
        wifiTentativas = 0;
        wifiUltimoHeartbeat = agora;
      } else if (agora - wifiInicioTentativa >= WIFI_TIMEOUT_MS) {
        Serial.printf("[WiFi] tentativa expirou (status=%d). Nova tentativa em %u ms.\n",
                      (int)WiFi.status(), wifiBackoff);
        estadoRede = EstadoRede::OFFLINE;
        wifiProximaTentativa = agora + wifiBackoff;
        // Backoff exponencial: nao adianta martelar o AP que ainda nao voltou.
        wifiBackoff = min(wifiBackoff * 2, WIFI_BACKOFF_MAX_MS);
      }
      break;

    case EstadoRede::ONLINE:
      if (!conectado) {
        wifiQuedas++;
        wifiQuedaEm = agora;
        wifiBackoff = WIFI_BACKOFF_MIN_MS;
        wifiTentativas = 0;
        Serial.printf("\n[WiFi] !!! QUEDA DETECTADA !!! (queda #%u, status=%d) "
                      "- reconexao automatica iniciada, sem upload nem reset\n",
                      wifiQuedas, (int)WiFi.status());
        Serial.printf("[WiFi] a logica local segue rodando: estado=%s\n",
                      estado == Estado::FECHADO ? "FECHADO"
                      : estado == Estado::EXPOSTO ? "EXPOSTO" : "QUEBRA");
        iniciarTentativaWifi(agora);
      } else if (agora - wifiUltimoHeartbeat >= WIFI_HEARTBEAT_MS) {
        wifiUltimoHeartbeat = agora;
        int32_t rssi = WiFi.RSSI();
        Serial.printf("[WiFi] online  ip=%s  rssi=%ld dBm (%s)  uptime=%lus\n",
                      WiFi.localIP().toString().c_str(),
                      (long)rssi, qualidadeRssi(rssi), (unsigned long)(agora / 1000));
      }
      break;

    case EstadoRede::OFFLINE:
      // Comparacao por subtracao: sobrevive ao rollover de millis().
      if ((int32_t)(agora - wifiProximaTentativa) >= 0) iniciarTentativaWifi(agora);
      break;
  }
}

// Comandos de teste pelo monitor serial. Servem para PROVOCAR a queda quando
// nao da para desligar o AP de verdade (no Wokwi o "Wokwi-GUEST" nunca cai).
// Na bancada, a queda de verdade e desligar o roteador/hotspot - e o teste que
// vale, porque exercita tambem o tempo de volta do AP.
void lerComandoSerial() {
  if (!Serial.available()) return;
  char c = Serial.read();
  if (c == 'd' || c == 'D') {
    Serial.println("\n[TESTE] derrubando o Wi-Fi por software (simula queda do AP)...");
    WiFi.disconnect();
  } else if (c == 's' || c == 'S') {
    Serial.printf("[WiFi] status=%d  ip=%s  rssi=%ld dBm  quedas=%u\n",
                  (int)WiFi.status(), WiFi.localIP().toString().c_str(),
                  (long)WiFi.RSSI(), wifiQuedas);
  }
}

void escreveLed(uint8_t pino, bool ligado) {
  digitalWrite(pino, (ligado == LED_ATIVO_ALTO) ? HIGH : LOW);
}

void setCor(bool r, bool g, bool b) {
  escreveLed(PINO_LED_R, r);
  escreveLed(PINO_LED_G, g);
  escreveLed(PINO_LED_B, b);
}

void semaforoVerde()    { setCor(false, true,  false); }
void semaforoAmarelo()  { setCor(true,  true,  false); }
void semaforoVermelho() { setCor(true,  false, false); }

void buzzer(bool ligado) {
  if (BUZZER_PASSIVO) {
    ligado ? tone(PINO_BUZZER, BUZZER_FREQ_HZ) : noTone(PINO_BUZZER);
  } else {
    digitalWrite(PINO_BUZZER, ligado ? HIGH : LOW);
  }
}

// Sinalizador de retencao. Acionado por comando remoto (Parte 8).
void setRele(bool ligado) {
  releLigado = ligado;
  digitalWrite(PINO_RELE, (ligado == RELE_ATIVO_ALTO) ? HIGH : LOW);
}

float consumoPorSegundo(float t) {
  float c = 1.0f + (t - 20.0f) / 10.0f;
  return c < 0 ? 0 : c;
}

void irParaFechado() {
  estado = Estado::FECHADO;
  semaforoVerde();
  buzzer(false);
}

void irParaExposto(uint32_t agora) {
  estado = Estado::EXPOSTO;
  inicioExposicao = agora;
  somaTemp = 0;
  amostrasTemp = 0;
  aberturas++;
  semaforoAmarelo();
  buzzer(false);
  Serial.printf("ABERTURA #%u\n", aberturas);
}

void irParaQuebra() {
  estado = Estado::QUEBRA;
  orcamento = 0;
  Serial.printf("QUEBRA  aberturas=%u  Tmed=%.1fC\n",
                aberturas, amostrasTemp ? somaTemp / amostrasTemp : ultimaTemperatura);
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println();
  Serial.println("=== Sentinela de Cadeia Fria ===");

  pinMode(PINO_LED_R, OUTPUT);
  pinMode(PINO_LED_G, OUTPUT);
  pinMode(PINO_LED_B, OUTPUT);
  pinMode(PINO_BUZZER, OUTPUT);
  pinMode(PINO_RELE, OUTPUT);

  tampa.iniciar(PINO_TAMPA);
  botaoReset.iniciar(PINO_RESET);
  dht.begin();

  buzzer(false);
  setRele(false);
  irParaFechado();
  Serial.println("Pronto. Estado inicial: FECHADO.");

  iniciarRede();
  Serial.println("Comandos de teste no serial: 'd' derruba o Wi-Fi | 's' mostra status.");
}

void loop() {
  uint32_t agora = millis();

  // Rede primeiro, mas sem prioridade sobre nada: nao bloqueia o resto do laco.
  atualizarRede(agora);
  lerComandoSerial();

  // Transicoes por tampa (ignoradas em QUEBRA, que so sai por reset).
  if (tampa.atualizar(agora)) {
    bool aberta = tampa.nivel;
    if (aberta && estado == Estado::FECHADO) {
      irParaExposto(agora);
    } else if (!aberta && estado == Estado::EXPOSTO) {
      uint32_t dur = (agora - inicioExposicao) / 1000;
      float tmed = amostrasTemp ? somaTemp / amostrasTemp : ultimaTemperatura;
      Serial.printf("FECHAMENTO #%u  dur=%us  Tmed=%.1fC  restante=%.1f\n",
                    aberturas, dur, tmed, orcamento);
      irParaFechado();
    }
  }

  // Reset so tem efeito em QUEBRA (chave pressionada = LOW).
  if (botaoReset.atualizar(agora) && !botaoReset.nivel && estado == Estado::QUEBRA) {
    orcamento = ORCAMENTO_INICIAL;
    irParaFechado();
    Serial.println("RESET");
  }

  // Leitura do DHT11: alimenta a ultima temperatura valida.
  if (agora - ultimaLeituraDht >= INTERVALO_DHT_MS) {
    ultimaLeituraDht = agora;
    float t = dht.readTemperature();
    if (!isnan(t)) ultimaTemperatura = t;
  }

  // Drenagem do orcamento: 1 passo por segundo, so enquanto exposto.
  if (agora - ultimoTick >= TICK_MS) {
    ultimoTick = agora;
    if (estado == Estado::EXPOSTO && !isnan(ultimaTemperatura)) {
      orcamento -= consumoPorSegundo(ultimaTemperatura);
      somaTemp += ultimaTemperatura;
      amostrasTemp++;
      Serial.printf("EXPOSTO  T=%.1fC  restante=%.1f\n", ultimaTemperatura, orcamento);
      if (orcamento <= 0) irParaQuebra();
    }
  }

  // Sinalizacao de QUEBRA: vermelho e buzzer intermitentes.
  if (estado == Estado::QUEBRA && agora - ultimoPisca >= PISCA_MS) {
    ultimoPisca = agora;
    piscaLigado = !piscaLigado;
    if (piscaLigado) {
      semaforoVermelho();
      buzzer(true);
    } else {
      setCor(false, false, false);
      buzzer(false);
    }
  }
}
