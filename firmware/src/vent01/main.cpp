// Sentinela de Cadeia Fria - firmware da VENT-01 (estacao de ventilacao, so atua).
// Contrato MQTT: CONTRATOS.md v1. Pinos: docs/n3/PINAGEM.md.
//
// Assina apenas {prefixo}/VENT-01/comando/+ e aciona a ventoinha de 12 V pelo
// rele de 1 canal (a fonte de 12 V alimenta a ventoinha; o ESP32 nunca).
// Modos do fluxograma do CP12 (5.3):
//   AUTOMATICO : segue o backend (comandos de origem "regra").
//   MANUAL     : comando de usuario aceito; volta em 10 min ou por "auto".
//   SEGURO     : exaustor ligado ha 15 min sem MQTT -> desliga sozinho; sai quando
//                a conexao com o broker volta.
// O exaustor fica DESLIGADO no boot.

#include <Arduino.h>

#include "Comum.h"
#include "Logica.h"

using logica::Modo;

constexpr uint8_t PINO_RELE  = 23;
constexpr uint8_t PINO_LED_R = 25;
constexpr uint8_t PINO_LED_G = 26;
constexpr uint8_t PINO_LED_B = 33;

// Rele de 1 canal (SRD-05VDC), medido na bancada em 20/11 (ver PINAGEM.md):
// active-low e NAO solta quando o GPIO escreve HIGH de 3,3 V (o modulo e
// alimentado com 5 V). Por isso o pino e "open-drain simulado":
//   ligar    = saida em LOW  (puxa IN para GND, rele aciona)
//   desligar = entrada flutuante (o modulo puxa IN para 5 V, rele solta)
// Nunca escrever HIGH neste pino.

// LED RGB de estado (opcional, nao esta no esquema do CP12). Catodo comum.
// Sem o LED montado nada acontece: os GPIOs ficam como saida sem carga.
constexpr bool LED_ATIVO_ALTO = true;

Modo modo = Modo::AUTOMATICO;
logica::TimerManual manual;
bool exaustorLigado = false;
bool bootPublicado = false;
bool estavaConectado = false;
uint8_t assinaturaPublicada = 0xFF;

// ---------------------------------------------------------------------------
void escreveLed(uint8_t pino, bool ligado) { digitalWrite(pino, (ligado == LED_ATIVO_ALTO) ? HIGH : LOW); }
void setCor(bool r, bool g, bool b) {
  escreveLed(PINO_LED_R, r);
  escreveLed(PINO_LED_G, g);
  escreveLed(PINO_LED_B, b);
}

void setExaustor(bool ligado) {
  exaustorLigado = ligado;
  if (ligado) {
    digitalWrite(PINO_RELE, LOW);   // latch em LOW antes de virar saida: sem pulso
    pinMode(PINO_RELE, OUTPUT);
  } else {
    pinMode(PINO_RELE, INPUT);      // flutuante: o modulo solta o rele
  }
}

// Verde: ocioso e online · azul: exaustor ligado · amarelo: sem MQTT · vermelho: SEGURO.
void atualizarLed() {
  if (modo == Modo::SEGURO) setCor(true, false, false);
  else if (!comum::mqttConectado()) setCor(true, true, false);
  else if (exaustorLigado) setCor(false, false, true);
  else setCor(false, true, false);
}

uint8_t assinaturaEstado() {
  return (uint8_t)(((uint8_t)modo) | (exaustorLigado ? 4 : 0));
}

bool publicarEstado() {
  char buf[256];
  logica::JsonBuf j(buf, sizeof(buf));
  comum::cabecalho(j);
  j.add(",\"modo\":\"%s\",\"exaustor\":\"%s\"}", logica::nomeModo(modo), exaustorLigado ? "ligado" : "desligado");
  return comum::publicar("estado", j, true);
}

void manterEstadoPublicado() {
  if (!comum::mqttConectado()) return;
  uint8_t a = assinaturaEstado();
  if (a == assinaturaPublicada) return;
  if (publicarEstado()) assinaturaPublicada = a;
}

void setModo(Modo novo) {
  if (novo == modo) return;
  char det[32];
  snprintf(det, sizeof(det), "%s->%s", logica::nomeModo(modo), logica::nomeModo(novo));
  Serial.printf("MODO: %s\n", det);
  modo = novo;
  atualizarLed();
  comum::publicarEvento("modo_alterado", -1, NAN, NAN, NAN, NAN, det);
}

// ---------------------------------------------------------------------------
// Comandos
// ---------------------------------------------------------------------------
const char* validarComando(const logica::Comando& c, const char** detalhe) {
  return logica::validarVent01(c, modo, detalhe);
}

void executarComando(const logica::Comando& c) {
  const Modo antes = modo;
  const Modo depois = logica::proximoModo(modo, c);

  if (!logica::igual(c.acao, "auto")) {
    setExaustor(logica::igual(c.acao, "ligar"));
    Serial.printf("EXAUSTOR: %s (origem %s)\n", exaustorLigado ? "ligado" : "desligado", c.origem);
  }

  if (depois == Modo::AUTOMATICO && antes == Modo::MANUAL) {
    manual.cancela();
    setModo(Modo::AUTOMATICO);   // o estado do exaustor fica; o backend decide a partir dai
  } else if (depois == Modo::MANUAL) {
    manual.inicia(millis());
    setModo(Modo::MANUAL);
  }
  atualizarLed();
}

// Apos cada (re)conexao: sai do SEGURO, republica o estado e, uma vez por boot, o evento "boot".
void aoConectar() {
  if (modo == Modo::SEGURO) setModo(Modo::AUTOMATICO);
  assinaturaPublicada = 0xFF;
  manterEstadoPublicado();
  if (!bootPublicado) {
    if (comum::publicarEvento("boot", -1, NAN, NAN, NAN, NAN, nullptr)) bootPublicado = true;
  }
  atualizarLed();
}

// ---------------------------------------------------------------------------
void setup() {
  // Exaustor desligado no boot: o pino fica em INPUT (flutuante), que e o
  // estado de repouso do rele (open-drain simulado, ver acima).
  setExaustor(false);

  Serial.begin(115200);
  delay(500);
  Serial.println();
  Serial.println("=== Sentinela de Cadeia Fria - VENT-01 ===");

  pinMode(PINO_LED_R, OUTPUT);
  pinMode(PINO_LED_G, OUTPUT);
  pinMode(PINO_LED_B, OUTPUT);
  atualizarLed();

  comum::iniciar(validarComando, executarComando, aoConectar);
  Serial.println("Pronto. Exaustor desligado, modo AUTOMATICO.");
}

void loop() {
  const uint32_t agora = millis();

  comum::atualizar(agora);

  const bool conectado = comum::mqttConectado();
  if (conectado != estavaConectado) {   // so para atualizar a cor do LED
    estavaConectado = conectado;
    atualizarLed();
  }

  if (manual.expirou(agora) && modo == Modo::MANUAL) {
    Serial.println("MANUAL: 10 min sem comando, voltando ao AUTOMATICO");
    manual.cancela();
    setModo(Modo::AUTOMATICO);
  }

  // Estado seguro de rede: exaustor ligado e sem MQTT ha 15 min -> desliga e entra em SEGURO.
  if (!conectado && exaustorLigado && modo != Modo::SEGURO &&
      (uint32_t)(agora - comum::mqttDesconectadoDesde()) >= logica::VENT_SEM_MQTT_MS) {
    Serial.println("SEGURO: 15 min sem MQTT com o exaustor ligado, desligando");
    setExaustor(false);
    manual.cancela();
    setModo(Modo::SEGURO);   // o evento so sai quando a rede voltar
  }

  manterEstadoPublicado();
}
