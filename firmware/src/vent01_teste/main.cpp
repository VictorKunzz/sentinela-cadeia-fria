// VENT-01 - programa de teste de bancada (NAO e o firmware definitivo).
// Valida a montagem do rele de 1 canal usando a saida CORRETA para este modulo
// (medido na bancada em 20/11, ver PINAGEM.md): o modulo e active-low e NAO
// solta quando o GPIO escreve HIGH de 3,3 V. Por isso o pino e "open-drain
// simulado":
//   ligar    = pinMode(23, OUTPUT) + digitalWrite(23, LOW)   (IN -> GND, aciona)
//   desligar = pinMode(23, INPUT)                            (flutuante, solta)
// Nunca se escreve HIGH no pino.
//
// O que faz: alterna ligado/desligado a cada 2 s e imprime no Serial. Esperado:
// o LED do modulo (e o clique) acompanha a linha "LIGADO"; sem Wi-Fi, sem MQTT.
// Pode rodar com a ventoinha desligada do borne (so ouvindo o clique).

#include <Arduino.h>

constexpr uint8_t  PINO_RELE  = 23;
constexpr uint32_t PERIODO_MS = 2000;

void releLigar() {
  digitalWrite(PINO_RELE, LOW);   // latch em LOW antes de virar saida: sem pulso
  pinMode(PINO_RELE, OUTPUT);
}

void releDesligar() { pinMode(PINO_RELE, INPUT); }

void setup() {
  releDesligar();   // repouso: pino flutuante

  Serial.begin(115200);
  delay(500);
  Serial.println();
  Serial.println("=== VENT-01 teste do rele (GPIO 23, open-drain simulado) ===");
  Serial.println("A cada 2 s alterna LIGADO (OUTPUT+LOW) / DESLIGADO (INPUT).");
  Serial.println("O LED do modulo e o clique devem acompanhar o LIGADO.");
}

void loop() {
  static uint32_t ultimo = 0;
  static bool ligado = false;
  static uint32_t ciclo = 0;

  const uint32_t agora = millis();
  if (agora - ultimo >= PERIODO_MS) {
    ultimo = agora;
    ligado = !ligado;
    if (ligado) releLigar(); else releDesligar();
    ciclo++;
    Serial.printf("[%lu] rele %s (GPIO 23 = %s)\n", (unsigned long)ciclo,
                  ligado ? "LIGADO" : "DESLIGADO",
                  ligado ? "OUTPUT LOW" : "INPUT flutuante");
  }
}
