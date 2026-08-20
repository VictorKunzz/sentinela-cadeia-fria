// Teste de ambiente — Sentinela de Cadeia Fria.
// Valida o toolchain do ESP32 e a compilacao das bibliotecas (DHT, MQTT).
// Nao e o firmware final: apenas inicializa os objetos e imprime no serial.

#include <Arduino.h>
#include <WiFi.h>
#include <DHT.h>
#include <PubSubClient.h>

#define PINO_DHT   4
#define TIPO_DHT   DHT11

DHT dht(PINO_DHT, TIPO_DHT);
WiFiClient rede;
PubSubClient mqtt(rede);

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("Sentinela de Cadeia Fria - ambiente OK");
}

void loop() {
  Serial.println("loop vivo");
  delay(2000);
}
