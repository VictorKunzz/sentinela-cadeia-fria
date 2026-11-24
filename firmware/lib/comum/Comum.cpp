#include "Comum.h"

#include <ArduinoOTA.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <time.h>

#include "secrets.h"

// ---------------------------------------------------------------------------
// Configuracao. DEVICE_ID vem do platformio.ini (um por env), nao do secrets.h:
// os dois firmwares compartilham o mesmo secrets.h do computador.
// Tudo que falta no secrets.h antigo tem um padrao seguro.
// ---------------------------------------------------------------------------
#ifndef DEVICE_ID
#error "DEVICE_ID deve ser definido em build_flags no platformio.ini"
#endif
#ifndef MQTT_TOPIC_PREFIX
#define MQTT_TOPIC_PREFIX "sentinela/cadeia-fria"
#endif
// O broker declara o cliente morto apos ~1,5x o keep-alive. 60 s estabiliza o
// caminho hotspot -> broker publico; com Mosquitto na LAN volte para 15
// (#define MQTT_KEEPALIVE_S 15 no secrets.h).
#ifndef MQTT_KEEPALIVE_S
#define MQTT_KEEPALIVE_S 60
#endif
#ifndef NTP_SERVER
#define NTP_SERVER "pool.ntp.org"
#endif
#ifndef FUSO_S
#define FUSO_S (-3 * 3600)   // America/Sao_Paulo
#endif

// Credenciais do broker: uma senha por dispositivo (o usuario e o proprio deviceId,
// como no ACL do Mosquitto). Sem nenhuma senha definida, conecta sem autenticacao
// (broker publico do modo Wokwi).
#if defined(DEVICE_CF01) && defined(MQTT_PASSWORD_CF01)
#define SENHA_MQTT MQTT_PASSWORD_CF01
#elif defined(DEVICE_VENT01) && defined(MQTT_PASSWORD_VENT01)
#define SENHA_MQTT MQTT_PASSWORD_VENT01
#elif defined(MQTT_PASSWORD)
#define SENHA_MQTT MQTT_PASSWORD
#else
#define SENHA_MQTT ""
#endif
#ifndef MQTT_USER
#define MQTT_USER DEVICE_ID
#endif

namespace {

constexpr uint32_t WIFI_RETENTA_MS = 5000;
constexpr uint32_t MQTT_ESPERA_MIN_MS = 1000;
constexpr uint32_t MQTT_ESPERA_MAX_MS = 30000;   // teto do backoff (R10)
constexpr uint16_t MQTT_TIMEOUT_S = 15;          // teto do bloqueio de connect()
constexpr time_t HORA_MINIMA_VALIDA = 1700000000;  // 2023-11: antes disso o NTP nao rodou

WiFiClient redeMqtt;
PubSubClient mqtt(redeMqtt);

comum::ValidarFn fnValidar = nullptr;
comum::ExecutarFn fnExecutar = nullptr;
comum::ConectadoFn fnConectado = nullptr;

logica::DedupIds dedup;

char topicoPrefixo[64];   // "{prefixo}/{deviceId}/"
char topicoStatus[96];    // precisa persistir: o PubSubClient guarda o ponteiro do Last Will
char topicoComandos[96];

bool wifiEstavaConectado = false;
bool otaIniciado = false;
bool mqttEstavaConectado = false;
uint32_t ultimaTentativaWifi = 0;
uint32_t ultimaTentativaMqtt = 0;
uint32_t esperaMqtt = MQTT_ESPERA_MIN_MS;
uint32_t desconectadoDesde = 0;

// Troca caracteres que quebrariam o JSON ao devolver um texto vindo da rede.
void sanitiza(char* s) {
  for (; *s; s++) {
    if (*s == '"' || *s == '\\' || (unsigned char)*s < 0x20) *s = '_';
  }
}

void iniciarOta() {
#ifdef OTA_PASSWORD
  if (otaIniciado) return;
  ArduinoOTA.setHostname(DEVICE_ID);
  ArduinoOTA.setPassword(OTA_PASSWORD);
  ArduinoOTA.onStart([]() { Serial.println("OTA: iniciando atualizacao..."); });
  ArduinoOTA.onEnd([]() { Serial.println("OTA: concluida, reiniciando."); });
  ArduinoOTA.onError([](ota_error_t e) { Serial.printf("OTA: erro %u\n", (unsigned)e); });
  ArduinoOTA.begin();
  otaIniciado = true;
  Serial.println("OTA: pronta (hostname = deviceId).");
#else
  if (!otaIniciado) {
    otaIniciado = true;   // so para avisar uma vez
    Serial.println("OTA: desativada (defina OTA_PASSWORD no secrets.h).");
  }
#endif
}

// WiFi.begin nao bloqueia: dispara e volta. A confirmacao vem por polling.
void manterWifi(uint32_t agora) {
  bool conectado = (WiFi.status() == WL_CONNECTED);

  if (conectado && !wifiEstavaConectado) {
    Serial.printf("Wi-Fi: conectado. IP %s  RSSI %d dBm\n", WiFi.localIP().toString().c_str(), WiFi.RSSI());
    configTime(FUSO_S, 0, NTP_SERVER);   // idempotente; refaz a sincronizacao
    iniciarOta();
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

void publicarConfirmacao(const char* commandId, const char* resultado, const char* motivo,
                         const char* detalhe) {
  char id[logica::DedupIds::TAM];
  char buf[384];
  logica::JsonBuf j(buf, sizeof(buf));
  comum::cabecalho(j);
  if (commandId) {
    strncpy(id, commandId, sizeof(id) - 1);
    id[sizeof(id) - 1] = '\0';
    sanitiza(id);
    j.add(",\"commandId\":\"%s\"", id);
  } else {
    j.add(",\"commandId\":null");
  }
  j.add(",\"resultado\":\"%s\"", resultado);
  if (motivo) j.add(",\"motivo\":\"%s\"", motivo);
  else j.add(",\"motivo\":null");
  if (detalhe) j.add(",\"detalhe\":\"%s\"", detalhe);
  else j.add(",\"detalhe\":null");
  j.add("}");
  comum::publicar("confirmacao", j, false);
  Serial.printf("MQTT: confirmacao %s %s%s%s\n", commandId ? commandId : "(sem id)", resultado,
                motivo ? " motivo=" : "", motivo ? motivo : "");
}

// Ciclo do comando: valida -> (rejeitado | aceito -> executa -> executado).
void aoReceberComando(char* topico, byte* dados, unsigned int tamanho) {
  char payload[384];
  size_t n = (tamanho < sizeof(payload) - 1) ? tamanho : sizeof(payload) - 1;
  memcpy(payload, dados, n);
  payload[n] = '\0';   // o payload do PubSubClient nao vem terminado em nulo

  Serial.printf("MQTT: recebido %s\n", topico);

  logica::Comando c;
  logica::parseComando(topico, payload, c);

  const char* detalhe = nullptr;
  const char* motivo = nullptr;

  if (!c.temId) {
    publicarConfirmacao(nullptr, "rejeitado", logica::MOTIVO_ACAO_INVALIDA, "sem commandId");
    return;
  }
  if (dedup.vistoERegistra(c.commandId)) {
    publicarConfirmacao(c.commandId, "rejeitado", logica::MOTIVO_DUPLICADO, nullptr);
    return;
  }
  motivo = logica::validarComum(c, DEVICE_ID, &detalhe);
  if (!motivo && fnValidar) motivo = fnValidar(c, &detalhe);
  if (motivo) {
    publicarConfirmacao(c.commandId, "rejeitado", motivo, detalhe);
    return;
  }

  publicarConfirmacao(c.commandId, "aceito", nullptr, nullptr);
  if (fnExecutar) fnExecutar(c);
  publicarConfirmacao(c.commandId, "executado", nullptr, nullptr);
}

// Reconexao MQTT com backoff. Sem while: cada volta faz no maximo uma tentativa.
void manterMqtt(uint32_t agora) {
  if (WiFi.status() != WL_CONNECTED) {
    if (mqttEstavaConectado) {
      mqttEstavaConectado = false;
      desconectadoDesde = agora;
    }
    return;
  }

  if (mqtt.connected()) {
    mqtt.loop();   // keep-alive e mensagens recebidas
    return;
  }

  if (mqttEstavaConectado) {
    Serial.printf("MQTT: conexao caiu (rc=%d)\n", mqtt.state());
    mqttEstavaConectado = false;
    desconectadoDesde = agora;
  }

  if (agora - ultimaTentativaMqtt < esperaMqtt) return;
  ultimaTentativaMqtt = agora;

  Serial.printf("MQTT: conectando em %s:%u ...\n", MQTT_HOST, (unsigned)MQTT_PORT);

  // Last Will em QoS 1 e retido: se o dispositivo sumir, o broker publica "offline".
  const char* senha = SENHA_MQTT;
  bool ok;
  if (senha[0] != '\0') {
    ok = mqtt.connect("sentinela-" DEVICE_ID, MQTT_USER, senha, topicoStatus, 1, true, "offline");
  } else {
    ok = mqtt.connect("sentinela-" DEVICE_ID, topicoStatus, 1, true, "offline");
  }

  if (ok) {
    mqtt.publish(topicoStatus, "online", true);   // retido (QoS 0: limite do PubSubClient)
    mqtt.subscribe(topicoComandos, 1);            // reassina a cada reconexao
    Serial.println("MQTT: conectado. status=online");
    mqttEstavaConectado = true;
    esperaMqtt = MQTT_ESPERA_MIN_MS;
    if (fnConectado) fnConectado();
  } else {
    Serial.printf("MQTT: falha (rc=%d). Nova tentativa em %lu ms\n", mqtt.state(), (unsigned long)esperaMqtt);
    esperaMqtt = (esperaMqtt * 2 > MQTT_ESPERA_MAX_MS) ? MQTT_ESPERA_MAX_MS : esperaMqtt * 2;
  }
}

}  // namespace

namespace comum {

void iniciar(ValidarFn validar, ExecutarFn executar, ConectadoFn aoConectar) {
  fnValidar = validar;
  fnExecutar = executar;
  fnConectado = aoConectar;

  snprintf(topicoPrefixo, sizeof(topicoPrefixo), "%s/%s/", MQTT_TOPIC_PREFIX, DEVICE_ID);
  snprintf(topicoStatus, sizeof(topicoStatus), "%sstatus", topicoPrefixo);
  snprintf(topicoComandos, sizeof(topicoComandos), "%scomando/+", topicoPrefixo);

  desconectadoDesde = millis();

  WiFi.mode(WIFI_STA);   // estacao; nao vira ponto de acesso
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setKeepAlive(MQTT_KEEPALIVE_S);
  mqtt.setSocketTimeout(MQTT_TIMEOUT_S);
  mqtt.setBufferSize(1024);   // JSON da telemetria com o contrato v1 passa de 300 bytes
  mqtt.setCallback(aoReceberComando);
}

void atualizar(uint32_t agora) {
  manterWifi(agora);
  manterMqtt(agora);
  if (otaIniciado && wifiEstavaConectado) {
#ifdef OTA_PASSWORD
    ArduinoOTA.handle();
#endif
  }
}

const char* deviceId() { return DEVICE_ID; }
bool wifiConectado() { return WiFi.status() == WL_CONNECTED; }
bool mqttConectado() { return mqtt.connected(); }
int rssi() { return WiFi.RSSI(); }
uint32_t mqttDesconectadoDesde() { return desconectadoDesde; }

bool horaSincronizada() { return time(nullptr) > HORA_MINIMA_VALIDA; }

void cabecalho(logica::JsonBuf& j) {
  j.add("{\"version\":1,\"deviceId\":\"%s\"", DEVICE_ID);
  bool sync = horaSincronizada();
  if (sync) {
    time_t agora = time(nullptr);
    struct tm t;
    localtime_r(&agora, &t);
    char ts[24];
    strftime(ts, sizeof(ts), "%Y-%m-%dT%H:%M:%S", &t);
    long off = FUSO_S;
    char sinal = off < 0 ? '-' : '+';
    if (off < 0) off = -off;
    j.add(",\"ts\":\"%s%c%02ld:%02ld\"", ts, sinal, off / 3600, (off % 3600) / 60);
  } else {
    j.add(",\"ts\":null");   // hora nao sincronizada: o backend usa a hora de recebimento
  }
  j.add(",\"horaSincronizada\":%s", sync ? "true" : "false");
}

bool publicar(const char* sub, const char* payload, bool retido) {
  if (!mqtt.connected()) return false;
  char topico[112];
  snprintf(topico, sizeof(topico), "%s%s", topicoPrefixo, sub);
  return mqtt.publish(topico, payload, retido);
}

bool publicar(const char* sub, const logica::JsonBuf& j, bool retido) {
  if (j.estourou) {
    Serial.printf("MQTT: JSON de '%s' estourou o buffer, nao publicado\n", sub);
    return false;
  }
  return publicar(sub, j.b, retido);
}

bool publicarEvento(const char* evento, int32_t n, float duracaoS, float tempMedia,
                    float consumo, float orcamento, const char* detalhe) {
  char buf[448];
  logica::JsonBuf j(buf, sizeof(buf));
  cabecalho(j);
  j.add(",\"evento\":\"%s\"", evento);
  if (n < 0) j.add(",\"n\":null");
  else j.add(",\"n\":%ld", (long)n);
  j.grandeza("duracao", duracaoS, "s", 0);
  j.grandeza("temperaturaMedia", tempMedia, UNIDADE_C, 1);
  j.grandeza("consumo", consumo, "u", 1);
  j.grandeza("orcamento", orcamento, "u", 1);
  if (detalhe) j.add(",\"detalhe\":\"%s\"", detalhe);
  else j.add(",\"detalhe\":null");
  j.add("}");
  return publicar("evento", j, false);
}

}  // namespace comum
