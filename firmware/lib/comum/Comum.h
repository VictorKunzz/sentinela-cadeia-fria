// Camada comum dos dois firmwares (CF-01 e VENT-01): Wi-Fi, NTP, MQTT com
// backoff e Last Will, ciclo de comando com confirmacao e ArduinoOTA.
// Tudo nao bloqueante. O dispositivo chama comum::atualizar() a cada volta do loop.
// Contrato: CONTRATOS.md v1.
#pragma once

#include <Arduino.h>
#include "Logica.h"

#define UNIDADE_C "\xC2\xB0" "C"   // "°C" em UTF-8 (literais separados: \xB0C seria hexa)

namespace comum {

// Valida um comando ja parseado e com commandId novo. nullptr = aceito;
// senao o motivo do catalogo (e `*detalhe` pode apontar um texto curto).
typedef const char* (*ValidarFn)(const logica::Comando&, const char** detalhe);
// Executa o comando aceito (depois da confirmacao "aceito").
typedef void (*ExecutarFn)(const logica::Comando&);
// Chamado logo apos cada (re)conexao ao broker, com status=online ja publicado.
typedef void (*ConectadoFn)();

void iniciar(ValidarFn validar, ExecutarFn executar, ConectadoFn aoConectar);
void atualizar(uint32_t agora);

const char* deviceId();
bool wifiConectado();
bool mqttConectado();
bool horaSincronizada();
int rssi();
// millis() em que o MQTT deixou de estar conectado (ou do boot, se nunca conectou).
// So tem significado enquanto mqttConectado() for falso.
uint32_t mqttDesconectadoDesde();

// Escreve {"version":1,"deviceId":"..","ts":..,"horaSincronizada":..  (sem fechar a chave).
void cabecalho(logica::JsonBuf& j);

// Publica em {prefixo}/{deviceId}/{sub}. Falso se desconectado ou JSON estourou o buffer.
bool publicar(const char* sub, const char* payload, bool retido);
bool publicar(const char* sub, const logica::JsonBuf& j, bool retido);

// Evento no formato do contrato. Campos nao aplicaveis: n<0, NAN ou nullptr viram null.
bool publicarEvento(const char* evento, int32_t n, float duracaoS, float tempMedia,
                    float consumo, float orcamento, const char* detalhe);

}  // namespace comum
