// VENT-01 - programa de teste de bancada (NAO e o firmware definitivo).
// Objetivo: validar a montagem do rele de 1 canal e descobrir o nivel de
// acionamento (alto ou baixo) antes do firmware da VENT-01 existir.
//
// O que faz: alterna o GPIO 23 a cada 2 s e imprime no Serial qual nivel esta
// em uso. Quem monta observa o LED/clique do modulo e anota em PINAGEM.md:
//   - "contato fecha com GPIO 23 = LOW"  -> modulo active-low  (RELE_ATIVO_ALTO = false)
//   - "contato fecha com GPIO 23 = HIGH" -> modulo active-high (RELE_ATIVO_ALTO = true)
//
// Sem Wi-Fi, sem MQTT: so o rele. Pode rodar com a ventoinha desligada do
// borne (so ouvindo o clique) e depois com ela ligada.

#include <Arduino.h>

constexpr uint8_t  PINO_RELE   = 23;
constexpr uint32_t PERIODO_MS  = 2000;

// Estado de repouso presumido: HIGH (a maioria dos modulos opto-isolados e
// active-low, entao HIGH = contato aberto). Escrito ANTES de virar saida.
void setup() {
  digitalWrite(PINO_RELE, HIGH);
  pinMode(PINO_RELE, OUTPUT);

  Serial.begin(115200);
  delay(500);
  Serial.println();
  Serial.println("=== VENT-01 teste do rele (GPIO 23) ===");
  Serial.println("A cada 2 s o pino troca de nivel. Observe o LED/clique do modulo.");
  Serial.println("Anote em qual nivel o contato FECHA (clique + LED do modulo aceso).");
}

void loop() {
  static uint32_t ultimo = 0;
  static bool alto = true;   // comeca em HIGH (repouso presumido)
  static uint32_t ciclo = 0;

  const uint32_t agora = millis();
  if (agora - ultimo >= PERIODO_MS) {
    ultimo = agora;
    alto = !alto;
    digitalWrite(PINO_RELE, alto ? HIGH : LOW);
    ciclo++;
    Serial.printf("[%lu] GPIO 23 = %s  <- o contato fechou agora? (clique/LED)\n",
                  (unsigned long)ciclo, alto ? "HIGH" : "LOW");
  }
}
