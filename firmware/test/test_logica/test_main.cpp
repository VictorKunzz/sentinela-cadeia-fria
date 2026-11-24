// Testes da logica pura (lib/logica/Logica.h). Rodam no PC: pio test -e native
#include <unity.h>

#include "Logica.h"

using namespace logica;

void setUp() {}
void tearDown() {}

// --- Faixas ---
void test_faixa_temperatura() {
  TEST_ASSERT_TRUE(temperaturaValida(0.0f));
  TEST_ASSERT_TRUE(temperaturaValida(50.0f));
  TEST_ASSERT_TRUE(temperaturaValida(31.2f));
  TEST_ASSERT_FALSE(temperaturaValida(-0.1f));
  TEST_ASSERT_FALSE(temperaturaValida(50.1f));
  TEST_ASSERT_FALSE(temperaturaValida(NAN));
}

void test_faixa_umidade() {
  TEST_ASSERT_TRUE(umidadeValida(20.0f));
  TEST_ASSERT_TRUE(umidadeValida(90.0f));
  TEST_ASSERT_FALSE(umidadeValida(19.9f));
  TEST_ASSERT_FALSE(umidadeValida(90.1f));
  TEST_ASSERT_FALSE(umidadeValida(NAN));
}

void test_faixa_config_orcamento() {
  TEST_ASSERT_TRUE(orcamentoConfigValido(30.0f));
  TEST_ASSERT_TRUE(orcamentoConfigValido(600.0f));
  TEST_ASSERT_FALSE(orcamentoConfigValido(29.9f));
  TEST_ASSERT_FALSE(orcamentoConfigValido(600.1f));
  TEST_ASSERT_FALSE(orcamentoConfigValido(NAN));
}

// --- Dedup de commandId ---
void test_dedup_repetido_e_rejeitado() {
  DedupIds d;
  TEST_ASSERT_FALSE(d.vistoERegistra("c-000001"));
  TEST_ASSERT_TRUE(d.vistoERegistra("c-000001"));
  TEST_ASSERT_FALSE(d.vistoERegistra("c-000002"));
}

void test_dedup_guarda_os_ultimos_10() {
  DedupIds d;
  char id[24];
  for (int i = 1; i <= 10; i++) {
    snprintf(id, sizeof(id), "c-%06d", i);
    TEST_ASSERT_FALSE(d.vistoERegistra(id));
  }
  // os 10 estao na memoria
  for (int i = 1; i <= 10; i++) {
    snprintf(id, sizeof(id), "c-%06d", i);
    TEST_ASSERT_TRUE(d.jaVisto(id));
  }
  // o 11o expulsa o mais antigo (c-000001)
  TEST_ASSERT_FALSE(d.vistoERegistra("c-000011"));
  TEST_ASSERT_FALSE(d.jaVisto("c-000001"));
  TEST_ASSERT_TRUE(d.jaVisto("c-000002"));
  TEST_ASSERT_TRUE(d.jaVisto("c-000011"));
}

// --- Filtro do sensor ---
void test_sensor_tres_invalidas_entram_em_seguro() {
  FiltroSensor f;
  TEST_ASSERT_EQUAL((int)Transicao::NENHUMA, (int)f.registra(false));
  TEST_ASSERT_EQUAL((int)Transicao::NENHUMA, (int)f.registra(false));
  TEST_ASSERT_EQUAL((int)Transicao::ENTROU, (int)f.registra(false));
  TEST_ASSERT_TRUE(f.seguro);
  // continuar invalido nao gera nova transicao
  TEST_ASSERT_EQUAL((int)Transicao::NENHUMA, (int)f.registra(false));
}

void test_sensor_invalidas_intercaladas_nao_entram() {
  FiltroSensor f;
  f.registra(false);
  f.registra(false);
  f.registra(true);   // zera a sequencia
  f.registra(false);
  TEST_ASSERT_EQUAL((int)Transicao::NENHUMA, (int)f.registra(false));
  TEST_ASSERT_FALSE(f.seguro);
}

void test_sensor_duas_validas_saem_do_seguro() {
  FiltroSensor f;
  f.registra(false); f.registra(false); f.registra(false);
  TEST_ASSERT_TRUE(f.seguro);
  TEST_ASSERT_EQUAL((int)Transicao::NENHUMA, (int)f.registra(true));   // so 1 valida
  TEST_ASSERT_TRUE(f.seguro);
  f.registra(false);                                                    // quebra a sequencia
  TEST_ASSERT_EQUAL((int)Transicao::NENHUMA, (int)f.registra(true));
  TEST_ASSERT_EQUAL((int)Transicao::SAIU, (int)f.registra(true));
  TEST_ASSERT_FALSE(f.seguro);
}

// --- Avaliacao da leitura: temperatura e umidade validadas separadamente ---
// Caso real (21/11): bafo no DHT11 -> 27,1 C com 91 % UR. So a umidade e invalida.
void test_umidade_fora_da_faixa_nao_invalida_a_temperatura() {
  AvaliacaoLeitura a = avaliaLeitura(27.1f, 91.0f);
  TEST_ASSERT_TRUE(a.temperaturaOk);
  TEST_ASSERT_FALSE(a.umidadeOk);
  // e, alimentando o filtro com a temperatura, nunca entra em SEGURO
  FiltroSensor f;
  for (int i = 0; i < 20; i++) f.registra(avaliaLeitura(27.1f, 91.0f).temperaturaOk);
  TEST_ASSERT_FALSE(f.seguro);
}

void test_umidade_nan_com_temperatura_ok_nao_entra_em_seguro() {
  AvaliacaoLeitura a = avaliaLeitura(27.1f, NAN);
  TEST_ASSERT_TRUE(a.temperaturaOk);
  TEST_ASSERT_FALSE(a.umidadeOk);
}

void test_temperatura_fora_da_faixa_conta_para_o_seguro() {
  FiltroSensor f;
  Transicao ultima = Transicao::NENHUMA;
  for (int i = 0; i < 3; i++) ultima = f.registra(avaliaLeitura(51.0f, 50.0f).temperaturaOk);
  TEST_ASSERT_EQUAL((int)Transicao::ENTROU, (int)ultima);
  TEST_ASSERT_TRUE(f.seguro);
  // NaN de temperatura tambem
  FiltroSensor g;
  for (int i = 0; i < 3; i++) g.registra(avaliaLeitura(NAN, 50.0f).temperaturaOk);
  TEST_ASSERT_TRUE(g.seguro);
}

void test_recuperacao_do_seguro_em_duas_validas_mesmo_com_umidade_ruim() {
  FiltroSensor f;
  for (int i = 0; i < 3; i++) f.registra(avaliaLeitura(NAN, NAN).temperaturaOk);
  TEST_ASSERT_TRUE(f.seguro);
  // temperatura volta ao normal; a umidade ainda saturada (91 %) nao atrapalha a saida
  TEST_ASSERT_EQUAL((int)Transicao::NENHUMA, (int)f.registra(avaliaLeitura(26.0f, 91.0f).temperaturaOk));
  TEST_ASSERT_EQUAL((int)Transicao::SAIU, (int)f.registra(avaliaLeitura(26.2f, 91.0f).temperaturaOk));
  TEST_ASSERT_FALSE(f.seguro);
}

// --- Timer do modo MANUAL ---
void test_manual_expira_em_10_min() {
  TimerManual t;
  TEST_ASSERT_FALSE(t.expirou(999999));   // inativo nunca expira
  t.inicia(1000);
  TEST_ASSERT_FALSE(t.expirou(1000 + MANUAL_TIMEOUT_MS - 1));
  TEST_ASSERT_TRUE(t.expirou(1000 + MANUAL_TIMEOUT_MS));
  t.inicia(5000);   // novo comando renova
  TEST_ASSERT_FALSE(t.expirou(1000 + MANUAL_TIMEOUT_MS));
  t.cancela();
  TEST_ASSERT_FALSE(t.expirou(5000 + MANUAL_TIMEOUT_MS + 1));
}

void test_manual_aguenta_virada_do_millis() {
  TimerManual t;
  t.inicia(0xFFFFFF00u);
  TEST_ASSERT_FALSE(t.expirou(0xFFFFFF00u + 1000u));
  TEST_ASSERT_TRUE(t.expirou(0xFFFFFF00u + MANUAL_TIMEOUT_MS));
}

// Regressao (21/11, integracao com hardware): o `agora` do loop() e lido antes do
// millis() que grava `inicio` dentro do callback do comando, entao agora < inicio
// por alguns ms. Sem diferenca com sinal, isso virava ~4 bilhoes e o MANUAL
// expirava na hora (o rele soltava e o comando ficava "nao confirmado").
void test_manual_nao_expira_com_agora_um_pouco_antes_do_inicio() {
  TimerManual t;
  t.inicia(50000);
  TEST_ASSERT_FALSE(t.expirou(50000 - 5));      // agora < inicio, por poucos ms
  TEST_ASSERT_FALSE(t.expirou(50000 - 1000));
  TEST_ASSERT_FALSE(t.expirou(50000));
  // e a virada do millis() com o mesmo desencontro:
  t.inicia(3u);
  TEST_ASSERT_FALSE(t.expirou(0xFFFFFFFDu));    // agora = 3 - 6 (com wrap)
}

// --- Parse de comando ---
void test_parse_comando_completo() {
  Comando c;
  parseComando("sentinela/cadeia-fria/VENT-01/comando/exaustor",
               "{\"version\":1,\"deviceId\":\"VENT-01\",\"commandId\":\"c-000123\",\"origem\":\"regra\",\"acao\":\"ligar\"}", c);
  TEST_ASSERT_EQUAL_STRING("exaustor", c.nome);
  TEST_ASSERT_TRUE(c.temId);
  TEST_ASSERT_EQUAL_STRING("c-000123", c.commandId);
  TEST_ASSERT_EQUAL_STRING("regra", c.origem);
  TEST_ASSERT_EQUAL_STRING("ligar", c.acao);
  TEST_ASSERT_EQUAL_STRING("VENT-01", c.deviceId);
  TEST_ASSERT_FALSE(c.temValor);
}

void test_parse_aceita_espacos_e_valor_numerico() {
  Comando c;
  parseComando("x/y/CF-01/comando/config",
               "{ \"commandId\" : \"c-000007\" , \"acao\" : \"orcamentoInicial\", \"valor\" : 150.5 }", c);
  TEST_ASSERT_TRUE(c.temId);
  TEST_ASSERT_TRUE(c.temAcao);
  TEST_ASSERT_TRUE(c.temValor);
  TEST_ASSERT_EQUAL_FLOAT(150.5f, c.valor);
  TEST_ASSERT_EQUAL_STRING("usuario", c.origem);   // ausente = usuario
  TEST_ASSERT_FALSE(c.temOrigem);
}

void test_parse_chave_dentro_de_valor_nao_engana() {
  Comando c;
  // "acao" aparece como VALOR de commandId; a chave real vem depois
  parseComando("x/comando/rele", "{\"commandId\":\"acao\",\"acao\":\"ligar\"}", c);
  TEST_ASSERT_EQUAL_STRING("acao", c.commandId);
  TEST_ASSERT_EQUAL_STRING("ligar", c.acao);
}

void test_parse_payload_malformado() {
  Comando c;
  parseComando("x/comando/rele", "isto nao e json", c);
  TEST_ASSERT_FALSE(c.temId);
  TEST_ASSERT_FALSE(c.temAcao);
  parseComando("x/comando/rele", "{\"commandId\":\"c-1\",\"acao\":\"liga", c);   // string nao terminada
  TEST_ASSERT_FALSE(c.temAcao);
}

// --- Validacao comum ---
void test_validar_comum() {
  Comando c;
  const char* det = nullptr;
  parseComando("x/comando/rele", "{\"commandId\":\"c-1\"}", c);
  TEST_ASSERT_EQUAL_STRING(MOTIVO_ACAO_INVALIDA, validarComum(c, "CF-01", &det));   // sem acao
  parseComando("x/comando/rele", "{\"commandId\":\"c-1\",\"acao\":\"ligar\",\"deviceId\":\"VENT-01\"}", c);
  TEST_ASSERT_EQUAL_STRING(MOTIVO_ACAO_INVALIDA, validarComum(c, "CF-01", &det));   // deviceId alheio
  parseComando("x/comando/rele", "{\"commandId\":\"c-1\",\"acao\":\"ligar\",\"origem\":\"robo\"}", c);
  TEST_ASSERT_EQUAL_STRING(MOTIVO_ACAO_INVALIDA, validarComum(c, "CF-01", &det));   // origem invalida
  parseComando("x/comando/rele", "{\"commandId\":\"c-1\",\"acao\":\"ligar\",\"deviceId\":\"CF-01\"}", c);
  TEST_ASSERT_NULL(validarComum(c, "CF-01", &det));
}

// --- Validacao CF-01 ---
static const char* cf(const char* nome, const char* json, bool quebra, Modo modo, const char** det) {
  static Comando c;
  char topico[64];
  snprintf(topico, sizeof(topico), "p/CF-01/comando/%s", nome);
  parseComando(topico, json, c);
  return validarCf01(c, quebra, modo, det);
}

void test_cf01_rele() {
  const char* det;
  TEST_ASSERT_NULL(cf("rele", "{\"commandId\":\"c-1\",\"acao\":\"ligar\"}", false, Modo::AUTOMATICO, &det));
  TEST_ASSERT_NULL(cf("rele", "{\"commandId\":\"c-1\",\"acao\":\"desligar\"}", false, Modo::AUTOMATICO, &det));
  TEST_ASSERT_EQUAL_STRING(MOTIVO_QUEBRA_ATIVA,
      cf("rele", "{\"commandId\":\"c-1\",\"acao\":\"desligar\"}", true, Modo::AUTOMATICO, &det));
  TEST_ASSERT_NULL(cf("rele", "{\"commandId\":\"c-1\",\"acao\":\"ligar\"}", true, Modo::AUTOMATICO, &det));
  TEST_ASSERT_EQUAL_STRING(MOTIVO_ACAO_INVALIDA,
      cf("rele", "{\"commandId\":\"c-1\",\"acao\":\"piscar\"}", false, Modo::AUTOMATICO, &det));
}

void test_cf01_reset() {
  const char* det;
  TEST_ASSERT_EQUAL_STRING(MOTIVO_SEM_QUEBRA,
      cf("reset", "{\"commandId\":\"c-1\",\"acao\":\"reset\"}", false, Modo::AUTOMATICO, &det));
  TEST_ASSERT_NULL(cf("reset", "{\"commandId\":\"c-1\",\"acao\":\"reset\"}", true, Modo::AUTOMATICO, &det));
  TEST_ASSERT_EQUAL_STRING(MOTIVO_ACAO_INVALIDA,
      cf("reset", "{\"commandId\":\"c-1\",\"acao\":\"limpar\"}", true, Modo::AUTOMATICO, &det));
}

void test_cf01_config_faixa() {
  const char* det;
  TEST_ASSERT_NULL(cf("config", "{\"commandId\":\"c-1\",\"acao\":\"orcamentoInicial\",\"valor\":120}", false, Modo::AUTOMATICO, &det));
  TEST_ASSERT_EQUAL_STRING(MOTIVO_FORA_DA_FAIXA,
      cf("config", "{\"commandId\":\"c-1\",\"acao\":\"orcamentoInicial\",\"valor\":20}", false, Modo::AUTOMATICO, &det));
  TEST_ASSERT_EQUAL_STRING(MOTIVO_FORA_DA_FAIXA,
      cf("config", "{\"commandId\":\"c-1\",\"acao\":\"orcamentoInicial\",\"valor\":601}", false, Modo::AUTOMATICO, &det));
  TEST_ASSERT_EQUAL_STRING(MOTIVO_ACAO_INVALIDA,
      cf("config", "{\"commandId\":\"c-1\",\"acao\":\"orcamentoInicial\"}", false, Modo::AUTOMATICO, &det));   // sem valor
}

void test_cf01_regra_em_modo_manual_e_rejeitada() {
  const char* det = nullptr;
  TEST_ASSERT_EQUAL_STRING(MOTIVO_ACAO_INVALIDA,
      cf("buzzer", "{\"commandId\":\"c-1\",\"origem\":\"regra\",\"acao\":\"disparar\"}", false, Modo::MANUAL, &det));
  TEST_ASSERT_EQUAL_STRING("modo manual", det);
  // usuario em MANUAL e regra em AUTOMATICO passam
  TEST_ASSERT_NULL(cf("buzzer", "{\"commandId\":\"c-1\",\"origem\":\"usuario\",\"acao\":\"disparar\"}", false, Modo::MANUAL, &det));
  TEST_ASSERT_NULL(cf("buzzer", "{\"commandId\":\"c-1\",\"origem\":\"regra\",\"acao\":\"disparar\"}", false, Modo::AUTOMATICO, &det));
}

void test_cf01_comando_desconhecido() {
  const char* det;
  TEST_ASSERT_EQUAL_STRING(MOTIVO_ACAO_INVALIDA,
      cf("exaustor", "{\"commandId\":\"c-1\",\"acao\":\"ligar\"}", false, Modo::AUTOMATICO, &det));
}

// --- Validacao VENT-01 ---
void test_vent01() {
  Comando c;
  const char* det = nullptr;
  parseComando("p/VENT-01/comando/exaustor", "{\"commandId\":\"c-1\",\"origem\":\"regra\",\"acao\":\"ligar\"}", c);
  TEST_ASSERT_NULL(validarVent01(c, Modo::AUTOMATICO, &det));
  TEST_ASSERT_EQUAL_STRING(MOTIVO_ACAO_INVALIDA, validarVent01(c, Modo::MANUAL, &det));
  parseComando("p/VENT-01/comando/exaustor", "{\"commandId\":\"c-1\",\"acao\":\"girar\"}", c);
  TEST_ASSERT_EQUAL_STRING(MOTIVO_ACAO_INVALIDA, validarVent01(c, Modo::AUTOMATICO, &det));
  parseComando("p/VENT-01/comando/rele", "{\"commandId\":\"c-1\",\"acao\":\"ligar\"}", c);
  TEST_ASSERT_EQUAL_STRING(MOTIVO_ACAO_INVALIDA, validarVent01(c, Modo::AUTOMATICO, &det));
}

// --- Maquina de modos ---
static Modo prox(const char* nome, const char* json, Modo atual) {
  static Comando c;
  char topico[64];
  snprintf(topico, sizeof(topico), "p/X/comando/%s", nome);
  parseComando(topico, json, c);
  return proximoModo(atual, c);
}

void test_modo_usuario_leva_a_manual() {
  TEST_ASSERT_EQUAL((int)Modo::MANUAL, (int)prox("rele", "{\"commandId\":\"c-1\",\"origem\":\"usuario\",\"acao\":\"ligar\"}", Modo::AUTOMATICO));
  TEST_ASSERT_EQUAL((int)Modo::MANUAL, (int)prox("exaustor", "{\"commandId\":\"c-1\",\"acao\":\"desligar\"}", Modo::MANUAL));
}

void test_modo_regra_nao_muda() {
  TEST_ASSERT_EQUAL((int)Modo::AUTOMATICO, (int)prox("exaustor", "{\"commandId\":\"c-1\",\"origem\":\"regra\",\"acao\":\"ligar\"}", Modo::AUTOMATICO));
}

void test_modo_auto_volta_ao_automatico() {
  TEST_ASSERT_EQUAL((int)Modo::AUTOMATICO, (int)prox("rele", "{\"commandId\":\"c-1\",\"acao\":\"auto\"}", Modo::MANUAL));
}

void test_modo_seguro_nao_muda_por_comando() {
  TEST_ASSERT_EQUAL((int)Modo::SEGURO, (int)prox("rele", "{\"commandId\":\"c-1\",\"acao\":\"ligar\"}", Modo::SEGURO));
  TEST_ASSERT_EQUAL((int)Modo::SEGURO, (int)prox("buzzer", "{\"commandId\":\"c-1\",\"acao\":\"auto\"}", Modo::SEGURO));
}

void test_modo_reset_e_config_nao_mexem_no_modo() {
  TEST_ASSERT_EQUAL((int)Modo::AUTOMATICO, (int)prox("reset", "{\"commandId\":\"c-1\",\"acao\":\"reset\"}", Modo::AUTOMATICO));
  TEST_ASSERT_EQUAL((int)Modo::AUTOMATICO, (int)prox("config", "{\"commandId\":\"c-1\",\"acao\":\"orcamentoInicial\",\"valor\":100}", Modo::AUTOMATICO));
}

// --- JSON ---
void test_json_grandeza_e_null() {
  char buf[128];
  JsonBuf j(buf, sizeof(buf));
  j.add("{\"a\":1");
  j.grandeza("temperatura", 31.0f, "C", 1);
  j.grandeza("umidade", NAN, "%", 0);
  j.add("}");
  TEST_ASSERT_FALSE(j.estourou);
  TEST_ASSERT_EQUAL_STRING("{\"a\":1,\"temperatura\":{\"valor\":31.0,\"unidade\":\"C\"},\"umidade\":null}", buf);
}

void test_json_estouro_e_detectado() {
  char buf[16];
  JsonBuf j(buf, sizeof(buf));
  j.add("%s", "um texto bem maior que o buffer");
  TEST_ASSERT_TRUE(j.estourou);
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_faixa_temperatura);
  RUN_TEST(test_faixa_umidade);
  RUN_TEST(test_umidade_fora_da_faixa_nao_invalida_a_temperatura);
  RUN_TEST(test_umidade_nan_com_temperatura_ok_nao_entra_em_seguro);
  RUN_TEST(test_temperatura_fora_da_faixa_conta_para_o_seguro);
  RUN_TEST(test_recuperacao_do_seguro_em_duas_validas_mesmo_com_umidade_ruim);
  RUN_TEST(test_faixa_config_orcamento);
  RUN_TEST(test_dedup_repetido_e_rejeitado);
  RUN_TEST(test_dedup_guarda_os_ultimos_10);
  RUN_TEST(test_sensor_tres_invalidas_entram_em_seguro);
  RUN_TEST(test_sensor_invalidas_intercaladas_nao_entram);
  RUN_TEST(test_sensor_duas_validas_saem_do_seguro);
  RUN_TEST(test_manual_expira_em_10_min);
  RUN_TEST(test_manual_aguenta_virada_do_millis);
  RUN_TEST(test_manual_nao_expira_com_agora_um_pouco_antes_do_inicio);
  RUN_TEST(test_parse_comando_completo);
  RUN_TEST(test_parse_aceita_espacos_e_valor_numerico);
  RUN_TEST(test_parse_chave_dentro_de_valor_nao_engana);
  RUN_TEST(test_parse_payload_malformado);
  RUN_TEST(test_validar_comum);
  RUN_TEST(test_cf01_rele);
  RUN_TEST(test_cf01_reset);
  RUN_TEST(test_cf01_config_faixa);
  RUN_TEST(test_cf01_regra_em_modo_manual_e_rejeitada);
  RUN_TEST(test_cf01_comando_desconhecido);
  RUN_TEST(test_vent01);
  RUN_TEST(test_modo_usuario_leva_a_manual);
  RUN_TEST(test_modo_regra_nao_muda);
  RUN_TEST(test_modo_auto_volta_ao_automatico);
  RUN_TEST(test_modo_seguro_nao_muda_por_comando);
  RUN_TEST(test_modo_reset_e_config_nao_mexem_no_modo);
  RUN_TEST(test_json_grandeza_e_null);
  RUN_TEST(test_json_estouro_e_detectado);
  return UNITY_END();
}
