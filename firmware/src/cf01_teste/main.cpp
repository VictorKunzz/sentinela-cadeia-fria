// CF-01 - programa de teste de bancada (NAO e o firmware definitivo).
// Valida a fiacao da caixa bloco a bloco, so pelo Serial (115200), sem Wi-Fi e
// sem MQTT. Pinos conforme docs/n3/PINAGEM.md:
//   DHT11 GPIO 4 · tampa (KW12) GPIO 18 · reset GPIO 19 · buzzer GPIO 27
//   LED RGB: R 25, G 26, B 33 (catodo comum, HIGH acende) · rele 2 canais GPIO 23
//
// O que faz sozinho:
//   1) DHT11: temperatura e umidade a cada 2 s (ou FALHA se nao ler)
//   2) tampa e reset (INPUT_PULLUP): imprime ao mudar
//   3) buzzer: 1 bip curto a cada 5 s
//   4) LED RGB: vermelho -> verde -> azul -> apagado, 1 s cada
//   5) rele: alterna a cada 3 s (modulo solta com HIGH, aciona com LOW)
//
// Teclas no monitor serial (opcionais):
//   b = bip agora   l = proxima cor do LED   r = alterna o rele agora
//   o = liga/desliga o modo open-drain do rele (ligar = OUTPUT+LOW, desligar =
//       INPUT), o mesmo da VENT-01, caso o modulo nao solte com HIGH
//   h = ajuda

#include <Arduino.h>
#include <DHT.h>

constexpr uint8_t PINO_DHT    = 4;
constexpr uint8_t PINO_TAMPA  = 18;
constexpr uint8_t PINO_RESET  = 19;
constexpr uint8_t PINO_BUZZER = 27;
constexpr uint8_t PINO_LED_R  = 25;
constexpr uint8_t PINO_LED_G  = 26;
constexpr uint8_t PINO_LED_B  = 33;
constexpr uint8_t PINO_RELE   = 23;

constexpr uint32_t DHT_MS    = 2000;
constexpr uint32_t BIP_MS    = 5000;
constexpr uint32_t BIP_DUR   = 120;
constexpr uint32_t LED_MS    = 1000;
constexpr uint32_t RELE_MS   = 3000;
constexpr uint32_t DEBOUNCE  = 30;

DHT dht(PINO_DHT, DHT11);

// Rele: por padrao active-low com digitalWrite normal (LOW = aciona).
bool releOpenDrain = false;
bool releLigado    = false;

void aplicaRele(bool ligado) {
  releLigado = ligado;
  if (releOpenDrain) {
    if (ligado) { digitalWrite(PINO_RELE, LOW); pinMode(PINO_RELE, OUTPUT); }
    else        { pinMode(PINO_RELE, INPUT); }
  } else {
    pinMode(PINO_RELE, OUTPUT);
    digitalWrite(PINO_RELE, ligado ? LOW : HIGH);
  }
  Serial.printf("[rele]  %s  (GPIO 23 = %s)\n", ligado ? "ACIONADO" : "SOLTO",
                releOpenDrain ? (ligado ? "OUTPUT LOW" : "INPUT flutuante")
                              : (ligado ? "LOW" : "HIGH"));
}

void cor(bool r, bool g, bool b) {
  digitalWrite(PINO_LED_R, r ? HIGH : LOW);
  digitalWrite(PINO_LED_G, g ? HIGH : LOW);
  digitalWrite(PINO_LED_B, b ? HIGH : LOW);
}

uint8_t passoLed = 3;   // 0 vermelho, 1 verde, 2 azul, 3 apagado
void proximoLed() {
  passoLed = (passoLed + 1) % 4;
  switch (passoLed) {
    case 0: cor(true, false, false);  Serial.println("[led]   VERMELHO"); break;
    case 1: cor(false, true, false);  Serial.println("[led]   VERDE");    break;
    case 2: cor(false, false, true);  Serial.println("[led]   AZUL");     break;
    default: cor(false, false, false); Serial.println("[led]   apagado");  break;
  }
}

uint32_t fimBip = 0;
void bip(uint32_t agora) {
  digitalWrite(PINO_BUZZER, HIGH);
  fimBip = agora + BIP_DUR;
  Serial.println("[buzzer] bip");
}

struct Chave {
  uint8_t pino; bool nivel; bool bruto; uint32_t marca;
  void iniciar(uint8_t p) { pino = p; pinMode(p, INPUT_PULLUP); nivel = bruto = digitalRead(p); marca = 0; }
  bool mudou(uint32_t agora) {
    bool l = digitalRead(pino);
    if (l != bruto) { bruto = l; marca = agora; }
    if ((agora - marca) >= DEBOUNCE && l != nivel) { nivel = l; return true; }
    return false;
  }
};
Chave tampa, botao;

void ajuda() {
  Serial.println("Teclas: b=bip  l=proxima cor  r=alterna rele  o=open-drain do rele  h=ajuda");
}

void setup() {
  // Rele em repouso (solto) antes de qualquer coisa, para nao dar pulso.
  digitalWrite(PINO_RELE, HIGH);
  pinMode(PINO_RELE, OUTPUT);
  pinMode(PINO_BUZZER, OUTPUT);
  digitalWrite(PINO_BUZZER, LOW);
  pinMode(PINO_LED_R, OUTPUT);
  pinMode(PINO_LED_G, OUTPUT);
  pinMode(PINO_LED_B, OUTPUT);
  cor(false, false, false);

  Serial.begin(115200);
  delay(500);
  Serial.println();
  Serial.println("=== CF-01 teste de bancada (so Serial, sem Wi-Fi) ===");
  ajuda();

  tampa.iniciar(PINO_TAMPA);
  botao.iniciar(PINO_RESET);
  dht.begin();
  Serial.printf("[tampa] estado inicial: %s\n", tampa.nivel ? "ABERTA (solta)" : "FECHADA (haste apertada)");
  Serial.printf("[reset] estado inicial: %s\n", botao.nivel ? "solto" : "APERTADO");
}

void loop() {
  const uint32_t agora = millis();
  static uint32_t tDht = 0, tBip = 0, tLed = 0, tRele = 0;

  if (agora - tDht >= DHT_MS) {
    tDht = agora;
    float t = dht.readTemperature();
    float u = dht.readHumidity();
    if (isnan(t) || isnan(u)) Serial.println("[dht11] FALHA na leitura (confira DATA no GPIO 4, VCC no 3V3, GND, pull-up de 10k)");
    else Serial.printf("[dht11] %.1f C  %.0f %%UR\n", t, u);
  }

  if (tampa.mudou(agora)) Serial.printf("[tampa] %s\n", tampa.nivel ? "ABERTA" : "FECHADA");
  if (botao.mudou(agora)) Serial.printf("[reset] %s\n", botao.nivel ? "solto" : "APERTADO");

  if (agora - tBip >= BIP_MS) { tBip = agora; bip(agora); }
  if (fimBip && (int32_t)(agora - fimBip) >= 0) { digitalWrite(PINO_BUZZER, LOW); fimBip = 0; }

  if (agora - tLed >= LED_MS) { tLed = agora; proximoLed(); }
  if (agora - tRele >= RELE_MS) { tRele = agora; aplicaRele(!releLigado); }

  while (Serial.available()) {
    char c = Serial.read();
    if (c == 'b') bip(agora);
    else if (c == 'l') proximoLed();
    else if (c == 'r') aplicaRele(!releLigado);
    else if (c == 'o') {
      releOpenDrain = !releOpenDrain;
      Serial.printf("[rele]  modo open-drain %s\n", releOpenDrain ? "LIGADO" : "DESLIGADO");
      aplicaRele(false);
    } else if (c == 'h') ajuda();
  }
}
