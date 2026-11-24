// Modelo de credenciais. Copie este arquivo para "secrets.h" e preencha.
// O secrets.h e ignorado pelo git e nunca deve ser versionado.
// Os dois firmwares (CF-01 e VENT-01) usam o MESMO secrets.h.
// O DEVICE_ID nao fica aqui: vem do platformio.ini (build_flags de cada env).
#pragma once

// --- Wi-Fi ---
// O ESP32 opera apenas em 2,4 GHz; redes 5 GHz nao aparecem na varredura.
#define WIFI_SSID     "coloque_sua_rede"
#define WIFI_PASSWORD "coloque_sua_senha"

// --- Broker MQTT ---
// Use o IP do PC na LAN (ex.: 192.168.0.10). "localhost" aponta para o proprio
// ESP32 e nunca alcanca o broker. Para o Wokwi, use um broker publico
// (ex.: broker.hivemq.com) com prefixo exclusivo (MQTT_TOPIC_PREFIX abaixo).
#define MQTT_HOST      "192.168.0.10"
#define MQTT_PORT      1883

// Senha de cada dispositivo no Mosquitto da N3 (iguais as do .env:
// MQTT_PASS_CF01 e MQTT_PASS_VENT01). O usuario e o proprio deviceId (CF-01 / VENT-01).
// Sem nenhuma senha definida, o firmware conecta sem autenticacao (broker publico).
#define MQTT_PASSWORD_CF01   "troque-esta-senha"
#define MQTT_PASSWORD_VENT01 "troque-esta-senha"

// Prefixo da arvore de topicos (padrao: sentinela/cadeia-fria). No modo Wokwi use
// um prefixo unico e o mesmo valor em MQTT_TOPIC_PREFIX do .env do backend, ex.:
// #define MQTT_TOPIC_PREFIX "sentinela-teste-a1b2c3/cadeia-fria"

// Keep-alive (padrao 60 s, estavel via hotspot + broker publico). Com Mosquitto na
// LAN, volte para 15 s para a deteccao de offline ser mais rapida:
// #define MQTT_KEEPALIVE_S 15

// --- OTA (R17) ---
// Senha do ArduinoOTA. Sem ela a OTA fica desativada (nunca sobe sem senha).
#define OTA_PASSWORD "troque-esta-senha"

// --- Hora (NTP) ---
// Padrao: pool.ntp.org e fuso -03:00. Para mudar:
// #define NTP_SERVER "a.ntp.br"
// #define FUSO_S (-3 * 3600)
