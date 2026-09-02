// Modelo de credenciais. Copie este arquivo para "secrets.h" e preencha.
// O secrets.h e ignorado pelo git e nunca deve ser versionado.
#pragma once

// --- Wi-Fi ---
// O ESP32 opera apenas em 2,4 GHz; redes 5 GHz nao aparecem na varredura.
#define WIFI_SSID     "coloque_sua_rede"
#define WIFI_PASSWORD "coloque_sua_senha"

// --- Broker MQTT ---
// Use o IP do PC na LAN (ex.: 192.168.0.10). "localhost" aponta para o proprio
// ESP32 e nunca alcanca o broker. Para desenvolvimento no simulador, um broker
// publico resolve (ex.: test.mosquitto.org).
#define MQTT_HOST      "192.168.0.10"
#define MQTT_PORT      1883

// Identificador no broker: dois clientes com o mesmo ID derrubam um ao outro.
// Em broker publico, use um sufixo proprio durante o desenvolvimento.
#define MQTT_CLIENT_ID "sentinela-cf01"
