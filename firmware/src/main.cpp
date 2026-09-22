// Sentinela de Cadeia Fria - firmware (ESP32).
// Parte 8: cliente MQTT com Last Will, presenca retida e reconexao com backoff.

#include <Arduino.h>
#include <WiFi.h>
#include <DHT.h>
#include <PubSubClient.h>
#include "secrets.h"

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
// Buzzer: true se for passivo (precisa de tone()); false se for ativo.
constexpr bool     BUZZER_PASSIVO  = false;
constexpr uint16_t BUZZER_FREQ_HZ  = 2000;

#define TIPO_DHT DHT11
DHT dht(PINO_DHT, TIPO_DHT);

constexpr uint32_t INTERVALO_DHT_MS = 2000;
constexpr uint32_t TICK_MS          = 1000;
constexpr uint32_t DEBOUNCE_MS      = 30;
constexpr uint32_t PISCA_MS         = 300;
constexpr uint32_t WIFI_RETENTA_MS  = 5000;   // intervalo entre tentativas
constexpr float    ORCAMENTO_INICIAL = 120.0f;

// --- MQTT ---
// Prefixo e topicos conforme docs/arquitetura-mqtt.md.
constexpr char TOPICO_STATUS[] = "sentinela/cadeia-fria/status";
constexpr char TOPICO_TELEMETRIA[] = "sentinela/cadeia-fria/telemetria";
// Assinatura com curinga: um unico subscribe cobre alarme, reset e rele.
constexpr char TOPICO_COMANDOS[]    = "sentinela/cadeia-fria/comando/+";
constexpr char TOPICO_CONFIRMACAO[] = "sentinela/cadeia-fria/confirmacao";
constexpr char TOPICO_EVENTO[] = "sentinela/cadeia-fria/evento";

// Cadencia da telemetria definida no contrato (5 s).
constexpr uint32_t INTERVALO_TELEMETRIA_MS = 5000;

// Backoff exponencial entre tentativas: 1s, 2s, 4s... ate o teto.
constexpr uint32_t MQTT_ESPERA_MIN_MS = 1000;
constexpr uint32_t MQTT_ESPERA_MAX_MS = 30000;

// O broker declara o cliente morto apos ~1,5x o keep-alive, entao este valor
// define em quanto tempo a presenca "offline" chega ao painel (~22 s aqui).
// Medicao no HiveMQ via simulador: com 6 s o cliente caia a cada ~10 s, pois o
// PINGRESP nao voltava a tempo pela rede simulada. Os padroes da biblioteca
// sustentam a sessao. Com Mosquitto na LAN, onde a latencia e minima, da para
// baixar de novo e cumprir a meta de 10 s do contrato.
constexpr uint16_t MQTT_KEEPALIVE_S = 15;
// Teto do bloqueio de mqtt.connect() quando o broker nao responde.
constexpr uint16_t MQTT_TIMEOUT_S   = 15;

WiFiClient   redeMqtt;
PubSubClient mqtt(redeMqtt);

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
Estado estado = Estado::FECHADO;

float    orcamento         = ORCAMENTO_INICIAL;
float    ultimaTemperatura = NAN;
bool     releLigado        = false;

uint32_t inicioExposicao = 0;
float    somaTemp        = 0;
uint32_t amostrasTemp    = 0;
uint16_t aberturas       = 0;

uint32_t ultimaLeituraDht   = 0;
uint32_t ultimoTick         = 0;
uint32_t ultimoPisca        = 0;
uint32_t ultimaTentativaWifi = 0;
bool     piscaLigado        = false;
bool     wifiEstavaConectado = false;

uint32_t ultimaTentativaMqtt = 0;
uint32_t esperaMqtt          = MQTT_ESPERA_MIN_MS;
bool     mqttEstavaConectado = false;
uint32_t ultimaTelemetria = 0;
float    ultimaUmidade    = NAN;
// Silenciamento por comando remoto: cala o buzzer sem tirar o estado de QUEBRA.
bool alarmeSilenciado = false;

// Orcamento no instante da abertura, para calcular o consumo daquela exposicao.
float orcamentoNaAbertura = ORCAMENTO_INICIAL;

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

void setRele(bool ligado) {
  releLigado = ligado;
  digitalWrite(PINO_RELE, (ligado == RELE_ATIVO_ALTO) ? HIGH : LOW);
}

float consumoPorSegundo(float t) {
  float c = 1.0f + (t - 20.0f) / 10.0f;
  return c < 0 ? 0 : c;
}

// WiFi.begin nao bloqueia: dispara a tentativa e retorna na hora.
// A confirmacao da conexao e feita por polling em manterWifi().
void manterWifi(uint32_t agora) {
  bool conectado = (WiFi.status() == WL_CONNECTED);

  if (conectado && !wifiEstavaConectado) {
    Serial.printf("Wi-Fi: conectado. IP %s  RSSI %d dBm\n",
                  WiFi.localIP().toString().c_str(), WiFi.RSSI());
  } else if (!conectado && wifiEstavaConectado) {
    Serial.println("Wi-Fi: conexao caiu.");
  }
  wifiEstavaConectado = conectado;

  if (!conectado && (agora - ultimaTentativaWifi >= WIFI_RETENTA_MS)) {
    ultimaTentativaWifi = agora;
    Serial.printf("Wi-Fi: tentando conectar em %s...\n", WIFI_SSID);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  }
}

// Reconexao MQTT com backoff. Nao usa while: cada passagem pelo laco faz no
// maximo uma tentativa, entao a maquina de estados continua respondendo.
void manterMqtt(uint32_t agora) {
  // Sem rede nao ha o que tentar; manterWifi() cuida de restabelecer o enlace.
  if (WiFi.status() != WL_CONNECTED) return;

  if (mqtt.connected()) {
    mqtt.loop();   // processa keep-alive e mensagens recebidas
    return;
  }

  if (mqttEstavaConectado) {
    // rc do PubSubClient: -4 = timeout de keep-alive, -3 = conexao perdida.
    Serial.print("MQTT: conexao caiu (rc=");
    Serial.print(mqtt.state());
    Serial.println(")");
    mqttEstavaConectado = false;
  }

  if (agora - ultimaTentativaMqtt < esperaMqtt) return;
  ultimaTentativaMqtt = agora;

  Serial.printf("MQTT: conectando em %s:%u ...\n", MQTT_HOST, MQTT_PORT);

  // O Last Will e registrado no momento da conexao: se este cliente sumir sem
  // se despedir, o proprio broker publica "offline" neste topico.
  if (mqtt.connect(MQTT_CLIENT_ID, TOPICO_STATUS, 1, true, "offline")) {
    // Retida: um painel que assinar depois ja recebe o estado atual na hora.
    mqtt.publish(TOPICO_STATUS, "online", true);
    // Reassina a cada reconexao: sessao limpa nao preserva assinaturas.
    mqtt.subscribe(TOPICO_COMANDOS, 1);
    Serial.println("MQTT: conectado. status=online");
    mqttEstavaConectado = true;
    esperaMqtt = MQTT_ESPERA_MIN_MS;
  } else {
    Serial.printf("MQTT: falha (rc=%d). Nova tentativa em %lu ms\n",
                  mqtt.state(), (unsigned long)esperaMqtt);
    esperaMqtt = (esperaMqtt * 2 > MQTT_ESPERA_MAX_MS) ? MQTT_ESPERA_MAX_MS
                                                       : esperaMqtt * 2;
  }
}

const char* nomeEstado(Estado e) {
  switch (e) {
    case Estado::FECHADO: return "FECHADO";
    case Estado::EXPOSTO: return "EXPOSTO";
    case Estado::QUEBRA:  return "QUEBRA";
  }
  return "DESCONHECIDO";
}

// Telemetria periodica em QoS 0 e sem retencao, conforme o contrato: perder
// uma amostra de 5 s nao compromete o monitoramento, a proxima chega logo.
// Sem leitura valida do sensor o campo vai como null, nao como "nan", que
// quebraria o JSON no consumidor.
void publicarTelemetria(uint32_t agora) {
  if (!mqtt.connected()) return;
  if (agora - ultimaTelemetria < INTERVALO_TELEMETRIA_MS) return;
  ultimaTelemetria = agora;

  char temp[12];
  char umid[12];
  if (isnan(ultimaTemperatura)) snprintf(temp, sizeof(temp), "null");
  else                          snprintf(temp, sizeof(temp), "%.1f", ultimaTemperatura);
  if (isnan(ultimaUmidade))     snprintf(umid, sizeof(umid), "null");
  else                          snprintf(umid, sizeof(umid), "%.0f", ultimaUmidade);

  char payload[192];
  snprintf(payload, sizeof(payload),
           "{\"ts\":%lu,\"estado\":\"%s\",\"temp\":%s,\"umid\":%s,"
           "\"orcamento\":%.1f,\"aberturas\":%u,\"rssi\":%d}",
           (unsigned long)(agora / 1000), nomeEstado(estado), temp, umid,
           orcamento, aberturas, WiFi.RSSI());

  if (!mqtt.publish(TOPICO_TELEMETRIA, payload)) {
    Serial.println("MQTT: falha ao publicar telemetria");
  }
}

// Eventos discretos da maquina de estados. Campos que nao se aplicam ao evento
// vao como null, preservando o mesmo formato para os quatro tipos e poupando o
// consumidor de tratar variacoes de esquema.
void publicarEvento(const char* evento, uint32_t agora,
                    int32_t durS, float tMed, float consumo) {
  if (!mqtt.connected()) return;

  char sDur[12];
  char sTmed[12];
  char sCons[12];
  if (durS < 0)       snprintf(sDur,  sizeof(sDur),  "null");
  else                snprintf(sDur,  sizeof(sDur),  "%ld", (long)durS);
  if (isnan(tMed))    snprintf(sTmed, sizeof(sTmed), "null");
  else                snprintf(sTmed, sizeof(sTmed), "%.1f", tMed);
  if (isnan(consumo)) snprintf(sCons, sizeof(sCons), "null");
  else                snprintf(sCons, sizeof(sCons), "%.1f", consumo);

  char payload[224];
  snprintf(payload, sizeof(payload),
           "{\"ts\":%lu,\"evento\":\"%s\",\"n\":%u,\"dur_s\":%s,"
           "\"t_med\":%s,\"consumo\":%s,\"restante\":%.1f}",
           (unsigned long)(agora / 1000), evento, aberturas,
           sDur, sTmed, sCons, orcamento);

  mqtt.publish(TOPICO_EVENTO, payload);
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
  orcamentoNaAbertura = orcamento;
  publicarEvento("ABERTURA", agora, -1, NAN, NAN);
}

void irParaQuebra() {
  estado = Estado::QUEBRA;
  orcamento = 0;
  Serial.printf("QUEBRA  aberturas=%u  Tmed=%.1fC\n",
                aberturas, amostrasTemp ? somaTemp / amostrasTemp : ultimaTemperatura);
  publicarEvento("QUEBRA", millis(), -1,
                 amostrasTemp ? somaTemp / amostrasTemp : ultimaTemperatura,
                 orcamentoNaAbertura - orcamento);
}

// Extrai o valor de "acao" do payload. Os comandos do contrato sao objetos de
// um campo so, entao uma varredura simples evita trazer uma dependencia de
// JSON para o firmware.
bool extrairAcao(const char* json, char* destino, size_t n) {
  const char* p = strstr(json, "\"acao\"");
  if (!p) return false;
  p = strchr(p + 6, ':');
  if (!p) return false;
  p = strchr(p, '"');
  if (!p) return false;
  p++;
  const char* fim = strchr(p, '"');
  if (!fim) return false;
  size_t tam = (size_t)(fim - p);
  if (tam >= n) tam = n - 1;
  memcpy(destino, p, tam);
  destino[tam] = '\0';
  return true;
}

// Fecha o ciclo do comando. O painel nao assume que a acao ocorreu por ter
// publicado: ele espera esta confirmacao. "executado": false cobre comando
// invalido ou nao aplicavel, com o motivo em "estado_resultante".
// Observacao: o PubSubClient so publica em QoS 0, enquanto o contrato preve
// QoS 1 para confirmacoes. Limitacao da biblioteca, registrada de proposito.
void publicarConfirmacao(const char* comando, const char* acao,
                         uint32_t recebidoTs, bool executado,
                         const char* resultado) {
  if (!mqtt.connected()) return;

  char payload[224];
  snprintf(payload, sizeof(payload),
           "{\"comando\":\"%s\",\"acao\":\"%s\",\"recebido_ts\":%lu,"
           "\"executado\":%s,\"estado_resultante\":\"%s\"}",
           comando, acao, (unsigned long)(recebidoTs / 1000),
           executado ? "true" : "false", resultado);

  mqtt.publish(TOPICO_CONFIRMACAO, payload);
  Serial.printf("MQTT: confirmacao %s/%s executado=%s\n",
                comando, acao, executado ? "true" : "false");
}

// Callback dos comandos remotos. O payload do PubSubClient nao vem terminado
// em nulo, entao precisa ser copiado antes de tratar como string.
void aoReceberComando(char* topico, byte* dados, unsigned int tamanho) {
  const uint32_t agora = millis();

  char payload[128];
  size_t n = (tamanho < sizeof(payload) - 1) ? tamanho : sizeof(payload) - 1;
  memcpy(payload, dados, n);
  payload[n] = '\0';

  // O ultimo segmento do topico identifica o comando (.../comando/rele).
  const char* barra = strrchr(topico, '/');
  const char* comando = barra ? barra + 1 : topico;

  Serial.printf("MQTT: recebido %s -> %s\n", topico, payload);

  char acao[24];
  if (!extrairAcao(payload, acao, sizeof(acao))) {
    publicarConfirmacao(comando, "?", agora, false, "payload sem campo acao");
    return;
  }

  if (strcmp(comando, "rele") == 0) {
    if (strcmp(acao, "ligar") == 0) {
      setRele(true);
      publicarConfirmacao(comando, acao, agora, true, "sinalizador=ligado");
    } else if (strcmp(acao, "desligar") == 0) {
      setRele(false);
      publicarConfirmacao(comando, acao, agora, true, "sinalizador=desligado");
    } else {
      publicarConfirmacao(comando, acao, agora, false, "acao invalida para rele");
    }

  } else if (strcmp(comando, "alarme") == 0) {
    if (strcmp(acao, "disparar") == 0) {
      alarmeSilenciado = false;
      buzzer(true);
      publicarConfirmacao(comando, acao, agora, true, "buzzer=ligado");
    } else if (strcmp(acao, "silenciar") == 0) {
      alarmeSilenciado = true;
      buzzer(false);
      publicarConfirmacao(comando, acao, agora, true, "buzzer=silenciado");
    } else {
      publicarConfirmacao(comando, acao, agora, false, "acao invalida para alarme");
    }

  } else if (strcmp(comando, "reset") == 0) {
    if (strcmp(acao, "reset") != 0) {
      publicarConfirmacao(comando, acao, agora, false, "acao invalida para reset");
    } else if (estado != Estado::QUEBRA) {
      // Recusa deliberada: reset so faz sentido para sair de uma quebra.
      publicarConfirmacao(comando, acao, agora, false, "reset ignorado: sem quebra ativa");
    } else {
      orcamento = ORCAMENTO_INICIAL;
      alarmeSilenciado = false;
      irParaFechado();
      publicarEvento("RESET", agora, -1, NAN, NAN);
      publicarConfirmacao(comando, acao, agora, true, "estado=FECHADO");
    }

  } else {
    publicarConfirmacao(comando, acao, agora, false, "comando desconhecido");
  }
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

  WiFi.mode(WIFI_STA);   // estacao (cliente); nao vira ponto de acesso

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setKeepAlive(MQTT_KEEPALIVE_S);
  mqtt.setSocketTimeout(MQTT_TIMEOUT_S);
  mqtt.setBufferSize(512);   // padrao 256 aperta com o JSON da telemetria
  mqtt.setCallback(aoReceberComando);

  Serial.println("Pronto. Estado inicial: FECHADO.");
}

void loop() {
  uint32_t agora = millis();

  // Rede: independente da logica local; se cair, o resto segue funcionando.
  manterWifi(agora);
  manterMqtt(agora);
  publicarTelemetria(agora);

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
      publicarEvento("FECHAMENTO", agora, (int32_t)dur, tmed,
                     orcamentoNaAbertura - orcamento);
      irParaFechado();
    }
  }

  // Reset so tem efeito em QUEBRA (chave pressionada = LOW).
  if (botaoReset.atualizar(agora) && !botaoReset.nivel && estado == Estado::QUEBRA) {
    orcamento = ORCAMENTO_INICIAL;
    irParaFechado();
    Serial.println("RESET");
    publicarEvento("RESET", agora, -1, NAN, NAN);
  }

  // Leitura do DHT11: alimenta a ultima temperatura valida.
  if (agora - ultimaLeituraDht >= INTERVALO_DHT_MS) {
    ultimaLeituraDht = agora;
    float t = dht.readTemperature();
    if (!isnan(t)) ultimaTemperatura = t;
    float u = dht.readHumidity();
    if (!isnan(u)) ultimaUmidade = u;
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
      buzzer(!alarmeSilenciado);   // silenciavel por comando, sem sair da QUEBRA
    } else {
      setCor(false, false, false);
      buzzer(false);
    }
  }
}
