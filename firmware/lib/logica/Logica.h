// Logica pura do firmware (sem Arduino): compila no ESP32 e no PC (pio test -e native).
// Reune o que precisa ser testavel sem hardware: validacao de faixa, dedup de
// commandId, filtro de sensor (modo SEGURO), regras de modo e de comando.
// Contrato: CONTRATOS.md v1.
#pragma once

#include <math.h>
#include <stdarg.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

namespace logica {

// --- Faixas (CONTRATOS.md secao 2) ---
constexpr float TEMP_MIN = 0.0f;
constexpr float TEMP_MAX = 50.0f;
constexpr float UMID_MIN = 20.0f;
constexpr float UMID_MAX = 90.0f;
constexpr float ORC_CFG_MIN = 30.0f;
constexpr float ORC_CFG_MAX = 600.0f;

// --- Tempos e contagens do fluxograma (CP12 5.3) ---
constexpr uint32_t MANUAL_TIMEOUT_MS = 10UL * 60UL * 1000UL;   // MANUAL -> AUTOMATICO
constexpr uint32_t VENT_SEM_MQTT_MS = 15UL * 60UL * 1000UL;    // VENT-01: ligada sem MQTT -> SEGURO
constexpr uint8_t FALHAS_PARA_SEGURO = 3;                      // leituras invalidas seguidas
constexpr uint8_t VALIDAS_PARA_SAIR = 2;                       // leituras validas seguidas

inline bool temperaturaValida(float t) { return !isnan(t) && t >= TEMP_MIN && t <= TEMP_MAX; }
inline bool umidadeValida(float u) { return !isnan(u) && u >= UMID_MIN && u <= UMID_MAX; }
inline bool orcamentoConfigValido(float v) { return !isnan(v) && v >= ORC_CFG_MIN && v <= ORC_CFG_MAX; }

// --- Modos ---
enum class Modo : uint8_t { AUTOMATICO, MANUAL, SEGURO };

inline const char* nomeModo(Modo m) {
  switch (m) {
    case Modo::AUTOMATICO: return "AUTOMATICO";
    case Modo::MANUAL: return "MANUAL";
    case Modo::SEGURO: return "SEGURO";
  }
  return "?";
}

// --- Catalogo de motivos (CONTRATOS.md secao 5) ---
constexpr const char* MOTIVO_QUEBRA_ATIVA = "QUEBRA_ATIVA";
constexpr const char* MOTIVO_SEM_QUEBRA = "SEM_QUEBRA";
constexpr const char* MOTIVO_DUPLICADO = "DUPLICADO";
constexpr const char* MOTIVO_ACAO_INVALIDA = "ACAO_INVALIDA";
constexpr const char* MOTIVO_FORA_DA_FAIXA = "FORA_DA_FAIXA";

inline bool igual(const char* a, const char* b) { return strcmp(a, b) == 0; }

// --- Buffer JSON minimo (so snprintf; sem dependencia de biblioteca) ---
struct JsonBuf {
  char* b;
  size_t n;
  size_t p;
  bool estourou;

  JsonBuf(char* buf, size_t tam) : b(buf), n(tam), p(0), estourou(false) {
    if (n) b[0] = '\0';
  }

  void add(const char* fmt, ...) __attribute__((format(printf, 2, 3))) {
    if (estourou || p >= n) {
      estourou = true;
      return;
    }
    va_list a;
    va_start(a, fmt);
    int r = vsnprintf(b + p, n - p, fmt, a);
    va_end(a);
    if (r < 0 || (size_t)r >= n - p) {
      estourou = true;
    } else {
      p += (size_t)r;
    }
  }

  // ,"chave":{"valor":V,"unidade":"U"}  ou  ,"chave":null  se V for NaN.
  void grandeza(const char* chave, float v, const char* unidade, int casas) {
    if (isnan(v)) add(",\"%s\":null", chave);
    else add(",\"%s\":{\"valor\":%.*f,\"unidade\":\"%s\"}", chave, casas, (double)v, unidade);
  }
};

// --- Ultimos 10 commandId (rejeita repetido sem executar) ---
struct DedupIds {
  enum { CAP = 10, TAM = 24 };
  char ids[CAP][TAM];
  uint8_t usados;
  uint8_t proximo;

  DedupIds() : usados(0), proximo(0) { memset(ids, 0, sizeof(ids)); }

  bool jaVisto(const char* id) const {
    for (uint8_t i = 0; i < usados; i++) {
      if (strncmp(ids[i], id, TAM - 1) == 0) return true;
    }
    return false;
  }

  void registra(const char* id) {
    strncpy(ids[proximo], id, TAM - 1);
    ids[proximo][TAM - 1] = '\0';
    proximo = (uint8_t)((proximo + 1) % CAP);
    if (usados < CAP) usados++;
  }

  // true se ja tinha sido visto; senao registra e devolve false.
  bool vistoERegistra(const char* id) {
    if (jaVisto(id)) return true;
    registra(id);
    return false;
  }
};

// --- Filtro do sensor: 3 invalidas seguidas -> SEGURO; 2 validas seguidas -> sai ---
enum class Transicao : uint8_t { NENHUMA, ENTROU, SAIU };

struct FiltroSensor {
  uint8_t invalidasSeguidas;
  uint8_t validasSeguidas;
  bool seguro;

  FiltroSensor() : invalidasSeguidas(0), validasSeguidas(0), seguro(false) {}

  Transicao registra(bool valida) {
    if (valida) {
      invalidasSeguidas = 0;
      if (validasSeguidas < 255) validasSeguidas++;
      if (seguro && validasSeguidas >= VALIDAS_PARA_SAIR) {
        seguro = false;
        return Transicao::SAIU;
      }
    } else {
      validasSeguidas = 0;
      if (invalidasSeguidas < 255) invalidasSeguidas++;
      if (!seguro && invalidasSeguidas >= FALHAS_PARA_SEGURO) {
        seguro = true;
        return Transicao::ENTROU;
      }
    }
    return Transicao::NENHUMA;
  }
};

// --- Temporizador do modo MANUAL (10 min, renovado a cada comando de usuario) ---
struct TimerManual {
  bool ativo;
  uint32_t inicio;

  TimerManual() : ativo(false), inicio(0) {}
  void inicia(uint32_t agora) { ativo = true; inicio = agora; }
  void cancela() { ativo = false; }
  bool expirou(uint32_t agora) const { return ativo && (uint32_t)(agora - inicio) >= MANUAL_TIMEOUT_MS; }
};

// --- JSON: extracao simples de campos de comandos (objetos planos) ---
inline const char* acharChave(const char* json, const char* chave) {
  char padrao[40];
  snprintf(padrao, sizeof(padrao), "\"%s\"", chave);
  const char* p = json;
  while ((p = strstr(p, padrao)) != nullptr) {
    const char* q = p + strlen(padrao);
    while (*q == ' ' || *q == '\t' || *q == '\n' || *q == '\r') q++;
    if (*q == ':') {
      q++;
      while (*q == ' ' || *q == '\t' || *q == '\n' || *q == '\r') q++;
      return q;
    }
    p += 1;  // era um valor, nao uma chave: continua procurando
  }
  return nullptr;
}

inline bool jsonString(const char* json, const char* chave, char* dst, size_t n) {
  const char* q = acharChave(json, chave);
  if (!q || *q != '"') return false;
  q++;
  size_t i = 0;
  while (*q && *q != '"') {
    if (*q == '\\' && q[1]) q++;  // pula o escape, copia o caractere seguinte
    if (i + 1 < n) dst[i++] = *q;
    q++;
  }
  if (*q != '"') return false;  // string nao terminada
  dst[i] = '\0';
  return true;
}

inline bool jsonNumero(const char* json, const char* chave, float* out) {
  const char* q = acharChave(json, chave);
  if (!q) return false;
  char* fim = nullptr;
  double v = strtod(q, &fim);
  if (fim == q) return false;
  *out = (float)v;
  return true;
}

// --- Comando recebido ---
struct Comando {
  char nome[16];       // ultimo segmento do topico: rele, buzzer, reset, config, exaustor
  char commandId[24];
  char origem[12];     // usuario | regra (ausente = usuario)
  char acao[24];
  char deviceId[16];
  bool temId;
  bool temAcao;
  bool temOrigem;
  bool temDeviceId;
  bool temValor;
  float valor;
};

inline void parseComando(const char* topico, const char* payload, Comando& c) {
  memset(&c, 0, sizeof(c));
  const char* barra = strrchr(topico, '/');
  const char* nome = barra ? barra + 1 : topico;
  strncpy(c.nome, nome, sizeof(c.nome) - 1);

  c.temId = jsonString(payload, "commandId", c.commandId, sizeof(c.commandId));
  c.temAcao = jsonString(payload, "acao", c.acao, sizeof(c.acao));
  c.temOrigem = jsonString(payload, "origem", c.origem, sizeof(c.origem));
  c.temDeviceId = jsonString(payload, "deviceId", c.deviceId, sizeof(c.deviceId));
  c.temValor = jsonNumero(payload, "valor", &c.valor);
  if (!c.temOrigem) strcpy(c.origem, "usuario");
}

inline bool ehUsuario(const Comando& c) { return igual(c.origem, "usuario"); }
inline bool ehAtuador(const Comando& c) {
  return igual(c.nome, "rele") || igual(c.nome, "buzzer") || igual(c.nome, "exaustor");
}

// Checagens comuns aos dois dispositivos (apos o commandId). nullptr = ok.
inline const char* validarComum(const Comando& c, const char* meuDeviceId, const char** det) {
  *det = nullptr;
  if (!c.temAcao) { *det = "sem acao"; return MOTIVO_ACAO_INVALIDA; }
  if (c.temDeviceId && !igual(c.deviceId, meuDeviceId)) { *det = "deviceId diferente"; return MOTIVO_ACAO_INVALIDA; }
  if (c.temOrigem && !igual(c.origem, "usuario") && !igual(c.origem, "regra")) {
    *det = "origem invalida";
    return MOTIVO_ACAO_INVALIDA;
  }
  return nullptr;
}

// CF-01. nullptr = aceito; senao o motivo (e `det` pode trazer um detalhe).
inline const char* validarCf01(const Comando& c, bool emQuebra, Modo modo, const char** det) {
  *det = nullptr;
  if (igual(c.nome, "rele")) {
    if (!(igual(c.acao, "ligar") || igual(c.acao, "desligar") || igual(c.acao, "auto"))) return MOTIVO_ACAO_INVALIDA;
    if (!ehUsuario(c) && modo == Modo::MANUAL) { *det = "modo manual"; return MOTIVO_ACAO_INVALIDA; }
    if (igual(c.acao, "desligar") && emQuebra) return MOTIVO_QUEBRA_ATIVA;
    return nullptr;
  }
  if (igual(c.nome, "buzzer")) {
    if (!(igual(c.acao, "disparar") || igual(c.acao, "silenciar") || igual(c.acao, "auto"))) return MOTIVO_ACAO_INVALIDA;
    if (!ehUsuario(c) && modo == Modo::MANUAL) { *det = "modo manual"; return MOTIVO_ACAO_INVALIDA; }
    return nullptr;
  }
  if (igual(c.nome, "reset")) {
    if (!igual(c.acao, "reset")) return MOTIVO_ACAO_INVALIDA;
    if (!emQuebra) return MOTIVO_SEM_QUEBRA;
    return nullptr;
  }
  if (igual(c.nome, "config")) {
    if (!igual(c.acao, "orcamentoInicial") || !c.temValor) return MOTIVO_ACAO_INVALIDA;
    if (!orcamentoConfigValido(c.valor)) return MOTIVO_FORA_DA_FAIXA;
    return nullptr;
  }
  *det = "comando desconhecido";
  return MOTIVO_ACAO_INVALIDA;
}

// VENT-01.
inline const char* validarVent01(const Comando& c, Modo modo, const char** det) {
  *det = nullptr;
  if (igual(c.nome, "exaustor")) {
    if (!(igual(c.acao, "ligar") || igual(c.acao, "desligar") || igual(c.acao, "auto"))) return MOTIVO_ACAO_INVALIDA;
    if (!ehUsuario(c) && modo == Modo::MANUAL) { *det = "modo manual"; return MOTIVO_ACAO_INVALIDA; }
    return nullptr;
  }
  *det = "comando desconhecido";
  return MOTIVO_ACAO_INVALIDA;
}

// Modo apos um comando aceito. So comandos de atuador mexem no modo:
// usuario -> MANUAL; "auto" -> AUTOMATICO; regra nao muda; SEGURO nao muda.
inline Modo proximoModo(Modo atual, const Comando& c) {
  if (!ehAtuador(c)) return atual;
  if (atual == Modo::SEGURO) return Modo::SEGURO;
  if (igual(c.acao, "auto")) return Modo::AUTOMATICO;
  if (ehUsuario(c)) return Modo::MANUAL;
  return atual;
}

}  // namespace logica
