// Sentinela de Cadeia Fria - firmware (ESP32).
// Parte 6: buzzer (alarme na QUEBRA) e rele (sinalizador de retencao).

#include <Arduino.h>
#include <DHT.h>

// Mapa de pinos (pinos testes, confirmar pinos reais no hardware fisico).
constexpr uint8_t PINO_DHT    = 4;
constexpr uint8_t PINO_TAMPA  = 18;
constexpr uint8_t PINO_RESET  = 19;
constexpr uint8_t PINO_BUZZER = 27;
constexpr uint8_t PINO_LED_R  = 25;
constexpr uint8_t PINO_LED_G  = 26;
constexpr uint8_t PINO_LED_B  = 33;
constexpr uint8_t PINO_RELE   = 23;

// LED RGB: true = catodo comum (HIGH acende). Ajustar conforme a bancada.
constexpr bool LED_ATIVO_ALTO = true;
// Modulo rele: muitos sao active-low. Ajustar conforme o modulo.
constexpr bool RELE_ATIVO_ALTO = true;
// Buzzer: true se for passivo (precisa de tone()); false se for ativo.
constexpr bool     BUZZER_PASSIVO  = false;
constexpr uint16_t BUZZER_FREQ_HZ  = 2000;

#define TIPO_DHT DHT11
DHT dht(PINO_DHT, TIPO_DHT);

constexpr uint32_t INTERVALO_DHT_MS = 2000;
constexpr uint32_t TICK_MS          = 1000;  // passo da drenagem do orcamento
constexpr uint32_t DEBOUNCE_MS      = 30;
constexpr uint32_t PISCA_MS         = 300;   // piscada/bip em QUEBRA
constexpr float    ORCAMENTO_INICIAL = 120.0f;

// --- Debounce reutilizavel para chaves em INPUT_PULLUP (solto = HIGH) ---
struct Chave {
  uint8_t  pino;
  bool     nivel;      // estado ja estabilizado
  bool     bruto;      // ultima leitura crua
  uint32_t marcador;

  void iniciar(uint8_t p) {
    pino = p;
    pinMode(pino, INPUT_PULLUP);
    nivel = bruto = (digitalRead(pino) == HIGH);
    marcador = 0;
  }

  bool atualizar(uint32_t agora) {
    bool leitura = (digitalRead(pino) == HIGH);
    if (leitura != bruto) { bruto = leitura; marcador = agora; }
    if ((agora - marcador) >= DEBOUNCE_MS && leitura != nivel) {
      nivel = leitura;
      return true;
    }
    return false;
  }
};

Chave tampa;   // aberta = solto = HIGH (confirmar montagem mecanica)
Chave botaoReset;

enum class Estado { FECHADO, EXPOSTO, QUEBRA };
Estado estado = Estado::FECHADO;

float    orcamento         = ORCAMENTO_INICIAL;
float    ultimaTemperatura = NAN;
bool     releLigado        = false;

// Acumuladores da exposicao corrente.
uint32_t inicioExposicao = 0;
float    somaTemp        = 0;
uint32_t amostrasTemp    = 0;
uint16_t aberturas       = 0;

uint32_t ultimaLeituraDht = 0;
uint32_t ultimoTick       = 0;
uint32_t ultimoPisca      = 0;
bool     piscaLigado      = false;

void escreveLed(uint8_t pino, bool ligado) {
  digitalWrite(pino, (ligado == LED_ATIVO_ALTO) ? HIGH : LOW);
}

void setCor(bool r, bool g, bool b) {
  escreveLed(PINO_LED_R, r);
  escreveLed(PINO_LED_G, g);
  escreveLed(PINO_LED_B, b);
}

void semaforoVerde()    { setCor(false, true,  false); }
void semaforoAmarelo()  { setCor(true,  true,  false); }
void semaforoVermelho() { setCor(true,  false, false); }

void buzzer(bool ligado) {
  if (BUZZER_PASSIVO) {
    ligado ? tone(PINO_BUZZER, BUZZER_FREQ_HZ) : noTone(PINO_BUZZER);
  } else {
    digitalWrite(PINO_BUZZER, ligado ? HIGH : LOW);
  }
}

// Sinalizador de retencao. Acionado por comando remoto (Parte 8).
void setRele(bool ligado) {
  releLigado = ligado;
  digitalWrite(PINO_RELE, (ligado == RELE_ATIVO_ALTO) ? HIGH : LOW);
}

float consumoPorSegundo(float t) {
  float c = 1.0f + (t - 20.0f) / 10.0f;
  return c < 0 ? 0 : c;
}

void irParaFechado() {
  estado = Estado::FECHADO;
  semaforoVerde();
  buzzer(false);
}

void irParaExposto(uint32_t agora) {
  estado = Estado::EXPOSTO;
  inicioExposicao = agora;
  somaTemp = 0;
  amostrasTemp = 0;
  aberturas++;
  semaforoAmarelo();
  buzzer(false);
  Serial.printf("ABERTURA #%u\n", aberturas);
}

void irParaQuebra() {
  estado = Estado::QUEBRA;
  orcamento = 0;
  Serial.printf("QUEBRA  aberturas=%u  Tmed=%.1fC\n",
                aberturas, amostrasTemp ? somaTemp / amostrasTemp : ultimaTemperatura);
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println();
  Serial.println("=== Sentinela de Cadeia Fria ===");

  pinMode(PINO_LED_R, OUTPUT);
  pinMode(PINO_LED_G, OUTPUT);
  pinMode(PINO_LED_B, OUTPUT);
  pinMode(PINO_BUZZER, OUTPUT);
  pinMode(PINO_RELE, OUTPUT);

  tampa.iniciar(PINO_TAMPA);
  botaoReset.iniciar(PINO_RESET);
  dht.begin();

  buzzer(false);
  setRele(false);
  irParaFechado();
  Serial.println("Pronto. Estado inicial: FECHADO.");
}

void loop() {
  uint32_t agora = millis();

  // Transicoes por tampa (ignoradas em QUEBRA, que so sai por reset).
  if (tampa.atualizar(agora)) {
    bool aberta = tampa.nivel;
    if (aberta && estado == Estado::FECHADO) {
      irParaExposto(agora);
    } else if (!aberta && estado == Estado::EXPOSTO) {
      uint32_t dur = (agora - inicioExposicao) / 1000;
      float tmed = amostrasTemp ? somaTemp / amostrasTemp : ultimaTemperatura;
      Serial.printf("FECHAMENTO #%u  dur=%us  Tmed=%.1fC  restante=%.1f\n",
                    aberturas, dur, tmed, orcamento);
      irParaFechado();
    }
  }

  // Reset so tem efeito em QUEBRA (chave pressionada = LOW).
  if (botaoReset.atualizar(agora) && !botaoReset.nivel && estado == Estado::QUEBRA) {
    orcamento = ORCAMENTO_INICIAL;
    irParaFechado();
    Serial.println("RESET");
  }

  // Leitura do DHT11: alimenta a ultima temperatura valida.
  if (agora - ultimaLeituraDht >= INTERVALO_DHT_MS) {
    ultimaLeituraDht = agora;
    float t = dht.readTemperature();
    if (!isnan(t)) ultimaTemperatura = t;
  }

  // Drenagem do orcamento: 1 passo por segundo, so enquanto exposto.
  if (agora - ultimoTick >= TICK_MS) {
    ultimoTick = agora;
    if (estado == Estado::EXPOSTO && !isnan(ultimaTemperatura)) {
      orcamento -= consumoPorSegundo(ultimaTemperatura);
      somaTemp += ultimaTemperatura;
      amostrasTemp++;
      Serial.printf("EXPOSTO  T=%.1fC  restante=%.1f\n", ultimaTemperatura, orcamento);
      if (orcamento <= 0) irParaQuebra();
    }
  }

  // Sinalizacao de QUEBRA: vermelho e buzzer intermitentes.
  if (estado == Estado::QUEBRA && agora - ultimoPisca >= PISCA_MS) {
    ultimoPisca = agora;
    piscaLigado = !piscaLigado;
    if (piscaLigado) {
      semaforoVermelho();
      buzzer(true);
    } else {
      setCor(false, false, false);
      buzzer(false);
    }
  }
}
