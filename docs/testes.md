# Registro de testes — Sentinela de Cadeia Fria

Este documento registra o que foi **efetivamente exercitado** no sistema, em que ambiente, com que resultado observado — e, com o mesmo destaque, **o que ainda não foi testado**.

Os trechos de saída abaixo são capturas reais, não exemplos ilustrativos.

# Parte A — N3 (sistema final)

## A.1 Como cada coisa foi verificada

| Nível | O que cobre | Onde está |
|---|---|---|
| **Testes automatizados do backend** | validação do contrato, histerese da regra R8, `commandId` duplicado, ciclo de comando, perfis, Telegram (com stub), simulador contra o backend | `backend/tests/` (pytest, Python 3.12; rodam no CI) |
| **Testes automatizados do firmware** | lógica pura: filtro de sensor, modos, dedup de `commandId`, validação de faixa, temporizador do modo manual | `firmware/test/test_logica` (`pio test -e native`, 33 casos; rodam no CI) |
| **Simulador de dispositivos** | as duas caixas pelo contrato, com falhas injetáveis | `simulador/simulador.py` |
| **Hardware real em bancada** | integração das duas placas com o Mosquitto, o backend e o painel | relatos da equipe com data, abaixo; **sem capturas anexadas** neste repositório |

## A.2 Os quatro cenários de falha (R10)

Cada cenário traz a provocação, o esperado, o observado e a evidência. Onde só há relato da equipe, está escrito.

### Cenário 1: queda do Wi-Fi

- **Provocação:** derrubar a rede da placa (desligar o ponto de acesso ou o hotspot) e religá-la.
- **Esperado:** a regra local (semáforo e alarme) segue funcionando; o painel marca o dispositivo `offline` pelo *Last Will*; ao voltar a rede, a conexão se restabelece sozinha.
- **Observado (hardware, 21/11 e 24/11, relato da equipe):** as duas placas aparecem `offline` e voltam `online` no painel; em 24/11 a CF-01 reconectou ao hotspot e ao broker após ajustes de rede (IP do computador e firewall). **Não foi feita uma medição cronometrada** do tempo até `offline`/reconexão.
- **Evidência:** relato da equipe; lógica de reconexão em `firmware/lib/comum/Comum.cpp`. Sem captura de Serial ou do painel anexada.
- **Atenção:** com o `keep-alive` padrão de 60 s, o `offline` leva ~90 s para aparecer; com 15 s (recomendado com o Mosquitto na LAN) leva ~22 s.

### Cenário 2: broker indisponível

- **Provocação:** parar o Mosquitto (`docker compose stop mosquitto`).
- **Esperado:** os dispositivos tentam reconectar com espera crescente até 30 s e voltam sozinhos; comandos enviados pelo backend nesse intervalo terminam como `nao_confirmado`, não como sucesso.
- **Observado:** no lado do backend, **teste automatizado** (`test_comandos.py::test_broker_fora_marca_nao_confirmado_na_hora`). No hardware, a CF-01 registrou falhas de conexão MQTT (`rc=-2`) e reconectou depois de corrigido o endereço do broker (24/11, relato). **A parada deliberada do Mosquitto com a placa em bancada não foi registrada.**
- **Evidência:** teste citado; backoff em `Comum.cpp` (espera de 1 s até o teto de 30 s).

### Cenário 3: falha de sensor

- **Provocação:** desconectar o DHT11 da CF-01 em funcionamento (e, separadamente, soprar bafo no sensor).
- **Esperado:** após 3 leituras de temperatura inválidas, a CF-01 entra em **SEGURO** (orçamento congelado, LED azul, evento `sensor_falha`, alerta no painel); volta ao automático com 2 leituras válidas. Umidade fora de 20–90 % invalida só a umidade e **não** leva ao SEGURO.
- **Observado (hardware, 22/11, relato da equipe):** com o DHT11 desconectado a CF-01 entrou em SEGURO e recuperou ao religá-lo. O bafo (umidade > 90 %) levou ao SEGURO antes da correção; depois da correção, a temperatura permanece válida e o SEGURO não dispara.
- **Evidência:** testes automatizados `test_simulador.py::test_cf01_seguro_apos_3_leituras_invalidas_e_sai_com_2_validas` e `test_seguro_congela_o_orcamento`; testes nativos do filtro de sensor (`firmware/test/test_logica`).

### Cenário 4: comando inválido ou duplicado

- **Provocação:** enviar comando com `acao` inválida, valor fora da faixa, `commandId` repetido, `reset` sem QUEBRA e `desligar` do sinalizador durante a QUEBRA.
- **Esperado:** o dispositivo rejeita com motivo do catálogo (`ACAO_INVALIDA`, `FORA_DA_FAIXA`, `DUPLICADO`, `SEM_QUEBRA`, `QUEBRA_ATIVA`) e **nada é executado duas vezes**; a interface mostra "recusado: motivo".
- **Observado:** cobertos por testes automatizados e pelo simulador; em hardware, a equipe confirmou `reset` em QUEBRA, e os comandos que não mudam nada (`auto`, `ligar` e `desligar` repetidos, que terminam como "já estava assim"). O intertravamento do sinalizador e a rejeição por `commandId` duplicado foram exercitados só nos testes automatizados e no simulador.
- **Evidência:** `test_comandos.py::test_command_id_duplicado_e_rejeitado_pelo_dispositivo`, `test_intertravamento_quebra_ativa_com_simulador`, `test_api.py::test_comando_rejeitado_aparece_com_motivo`, `test_sem_efeito.py`.

## A.3 Outros resultados em hardware (relatos da equipe)

| Data | O que foi feito | Resultado |
|---|---|---|
| 21/11 | sinalizador, buzzer e ventoinha comandados pelo painel; QUEBRA com LED, buzzer, relé e alerta; reset; perfil técnico sem botões | OK |
| 21/11 | regra R8 com aquecimento real (acima de 30 °C por mais de 2 min; desliga abaixo de 26 °C) | OK (não repetido na montagem final em 24/11, por falta de fonte de calor; a regra segue coberta pelos testes automatizados) |
| 21/11 | estabilidade: mais de 1 h seguida, VENT-01 na fonte e CF-01 no power bank | sem reinício |
| 22/11 | VENT-01 soldada: 5,0 V no regulador; relé e ventoinha ligados e desligados pelo painel, com confirmação | OK |
| 24/11 | teste conjunto: VENT-01 só na fonte de 12 V e CF-01 no power bank, ambas online; tampa, LEDs e exaustor | OK |
| 25/11 | autonomia do power bank com a CF-01 por 30 minutos | OK |

Falhas encontradas e corrigidas durante a integração: o modo manual expirava na hora (diferença de `millis()` sem sinal), o relé de 1 canal da VENT-01 não soltava com HIGH de 3,3 V (passou a open-drain), contatos frouxos na protoboard e soldas frias derrubaram a leitura do DHT11 e do botão de reset, e a senha dos usuários do painel não acompanhava o `.env`.

## A.4 O que não foi testado

- **OTA:** implementado no firmware, mas **nunca demonstrado em hardware**.
- **Telegram:** testado só com stub; **nenhum bot real foi criado**.
- **DHT11:** sem comparação com termômetro de referência e sem medição do tempo de resposta ([`risco-01-dht11.md`](risco-01-dht11.md)).
- **Queda do Wi-Fi e parada do broker** com medição de tempo e captura (cenários 1 e 2).
- **Ventoinha só com a tampa aberta:** o sistema não faz essa distinção (ver limitações no README).
- Capturas (prints, logs de Serial, fotos) dos testes em hardware: não anexadas ao repositório.

## A.5 Como reproduzir (N3)

Com o `docker compose up -d --build` no ar e o `.env` preenchido. Escutar tudo que o broker recebe:

```bash
docker compose exec mosquitto sh -c 'mosquitto_sub -h localhost -u backend -P "$MQTT_PASS_BACKEND" -t "sentinela/cadeia-fria/#" -v'
```

Enviar um comando **pela API** (o backend é o único que publica comandos; o Mosquitto recusa publicação de comando por outros usuários):

```bash
curl -s -X POST http://localhost:8000/login -H "Content-Type: application/json" -d '{"username":"<usuario-coordenacao>","password":"<senha>"}'
curl -s -X POST http://localhost:8000/dispositivos/VENT-01/comandos -H "Authorization: Bearer <token>" -H "Content-Type: application/json" -d '{"comando":"exaustor","acao":"ligar"}'
```

Rodar os testes: ver [`backend/README.md`](../backend/README.md) e `pio test -e native` na pasta `firmware/`.

---

# Parte B — Registro da N1 (histórico)

> Os comandos e os tópicos desta parte são do protótipo da N1 (broker aberto, tópicos sem `deviceId`, sem `commandId`) e **não funcionam no Mosquitto autenticado da N3**. Veja a Parte A.

## Ambientes de teste

| Ambiente | O que permite verificar | O que **não** permite |
|---|---|---|
| **Simulador Wokwi** | Lógica, rede, contrato MQTT, ciclo de comandos | Comportamento elétrico, sensor real, queda de Wi-Fi provocada |
| **Bancada física** | Sensor real, atuadores, eletrônica, tempo real | — |
| **Escuta do broker** | O que efetivamente trafega na rede, de um terceiro ponto | O estado interno do dispositivo |

A escuta do broker foi feita com `mosquitto_sub` a partir de uma máquina **distinta** do dispositivo, garantindo que o observado atravessou a rede de verdade.

---

## 1. Conexão Wi-Fi e obtenção de IP

**Ambiente:** simulador · **Data:** 08/09/2026

```
=== Sentinela de Cadeia Fria ===
Pronto. Estado inicial: FECHADO.
Wi-Fi: tentando conectar em Wokwi-GUEST...
Wi-Fi: conectado. IP 10.13.37.2  RSSI -86 dBm
```

**Resultado:** aprovado. O endereço é atribuído por DHCP; o firmware registra a transição de estado da conexão, o que serve de evidência para o requisito de rede.

## 2. Presença e *Last Will*

**Ambiente:** simulador · **Data:** 08/09/2026

Assinando `sentinela/cadeia-fria/#` de outra máquina, com a simulação em execução e depois interrompida:

```
sentinela/cadeia-fria/status | online
sentinela/cadeia-fria/status | offline
```

**Resultado:** aprovado. A mensagem `offline` foi publicada **pelo broker**, não pelo dispositivo — que já estava parado. Confirma que o *Last Will* registrado no CONNECT cumpre seu papel mesmo em desligamento abrupto.

Verificou-se também a **retenção**: ao assinar o tópico com o dispositivo já em execução, o estado corrente chegou imediatamente, sem aguardar a publicação seguinte.

## 3. Telemetria periódica

**Ambiente:** simulador · **Data:** 08/09/2026

```
20:05:45 | telemetria | {"ts":15,"estado":"FECHADO","temp":null,"umid":null,"orcamento":120.0,"aberturas":0,"rssi":-81}
20:05:53 | telemetria | {"ts":20,"estado":"FECHADO","temp":null,"umid":null,"orcamento":120.0,"aberturas":0,"rssi":-81}
20:06:02 | telemetria | {"ts":25,"estado":"FECHADO","temp":null,"umid":null,"orcamento":120.0,"aberturas":0,"rssi":-97}
```

**Resultado:** aprovado, com dois pontos registrados:

- Os sete campos do contrato estão presentes e o JSON é válido.
- Sem sensor no diagrama, `temp` e `umid` saem como **`null`** — não como `0` nem `"nan"`. O tratamento de dado inválido preserva a validade do JSON e comunica a ausência de leitura, em vez de emitir um número falso.

## 4. Ciclo de comando e confirmação

**Ambiente:** simulador · **Data:** 08/09/2026

Cinco comandos publicados de uma máquina externa, com as respostas capturadas em `confirmacao`:

| Comando publicado | `executado` | `estado_resultante` |
|---|---|---|
| `comando/rele` `{"acao":"ligar"}` | `true` | `sinalizador=ligado` |
| `comando/reset` `{"acao":"reset"}` *(sem quebra ativa)* | **`false`** | `reset ignorado: sem quebra ativa` |
| `comando/alarme` `{"acao":"disparar"}` | `true` | `buzzer=ligado` |
| `comando/rele` `{"acao":"desligar"}` | `true` | `sinalizador=desligado` |
| `comando/rele` `{"acao":"explodir"}` *(ação inexistente)* | **`false`** | `acao invalida para rele` |

Tempo entre a publicação do comando e a chegada da confirmação: **≈ 370 ms**, dos quais ≈ 210 ms de processamento no dispositivo.

**Resultado:** aprovado. Os dois casos de recusa são tão relevantes quanto os de sucesso: o dispositivo **recusa e informa o motivo**, em vez de ignorar em silêncio. A confirmação distingue *recebido* de *executado*.

## 5. Sensor real e máquina de estados em bancada

**Ambiente:** bancada física · **Data:** 14/09/2026

```
EXPOSTO  T=31.8C  restante=26.3
EXPOSTO  T=31.8C  restante=24.1
EXPOSTO  T=32.3C  restante=10.9
EXPOSTO  T=32.3C  restante=2.0
EXPOSTO  T=32.3C  restante=-0.2
QUEBRA  aberturas=1  Tmed=27.4C
RESET
ABERTURA #2
EXPOSTO  T=25.3C  restante=118.5
```

**Resultado:** aprovado. O ciclo completo `ABERTURA → EXPOSTO → QUEBRA → RESET → ABERTURA` foi percorrido com leitura real do DHT11.

**Conferência da fórmula.** O consumo previsto é `1 + (T − 20) / 10`:

| Temperatura observada | Consumo previsto | Queda observada no orçamento |
|---|---|---|
| 31,8 °C | 2,18 /s | 2,2 /s |
| 32,3 °C | 2,23 /s | 2,2 /s |
| 25,3 °C | 1,53 /s | 1,5 /s |

A drenagem corresponde ao modelo nos três patamares de temperatura.

## 6. Telemetria com sensor real, pela rede

**Ambiente:** bancada física + escuta do broker · **Data:** 15/09/2026

```
20:29:06 | status      | online
20:29:10 | telemetria  | {"ts":180,"estado":"EXPOSTO","temp":24.8,"umid":55,"orcamento":54.9,"aberturas":3,"rssi":-51}
20:29:15 | telemetria  | {"ts":185,"estado":"EXPOSTO","temp":24.8,"umid":54,"orcamento":47.5,"aberturas":3,"rssi":-42}
20:29:20 | telemetria  | {"ts":190,"estado":"EXPOSTO","temp":24.8,"umid":54,"orcamento":40.1,"aberturas":3,"rssi":-51}
20:29:22 | evento      | {"ts":192,"evento":"FECHAMENTO","n":3,"dur_s":46,"t_med":24.8,"consumo":69.6,"restante":35.6}
20:29:25 | telemetria  | {"ts":195,"estado":"FECHADO","temp":24.8,"umid":54,"orcamento":35.6,"aberturas":3,"rssi":-42}
```

**Resultado:** aprovado. Temperatura e umidade reais atravessando Wi-Fi e MQTT até um observador externo, com o evento de fechamento trazendo duração, temperatura média e consumo daquela exposição.

Nova conferência: a 24,8 °C o consumo previsto é 1,48 /s; em intervalos de 5 s, o orçamento caiu 54,9 → 47,5 → 40,1, isto é **7,4 por intervalo**, equivalente a 1,48 /s.

## 7. Investigação: queda periódica da sessão MQTT

**Ambiente:** simulador + escuta do broker · **Data:** 08/09/2026

Durante os testes iniciais, a presença alternava entre `online` e `offline` em intervalos regulares. A causa foi isolada **medindo o período** sob dois valores de *keep-alive*:

| Keep-alive configurado | Intervalo observado entre quedas | 1,5 × keep-alive |
|---|---|---|
| 6 s | ~10 s | 9 s |
| 15 s | ~22 s | 22,5 s |

**Diagnóstico:** o período acompanhava exatamente `1,5 × keep-alive`, que é a regra pela qual o **broker** declara um cliente morto. Ou seja, a desconexão partia do broker por ausência de tráfego, e não de falha no firmware — os pacotes de *ping* não estavam chegando através da rede simulada.

**Resolução:** a introdução da telemetria periódica (a cada 5 s) eliminou o problema por construção, ao manter a sessão com tráfego constante. Verificado em seguida: nenhuma desconexão em 35 s de observação contínua, contra uma a cada 22 s antes da mudança.

Esse episódio motivou a escolha do valor de *keep-alive* documentada em [`arquitetura-mqtt.md`](arquitetura-mqtt.md).

---

## O que ainda não foi testado

| Item | Situação | Próximo passo |
|---|---|---|
| **Reconexão de Wi-Fi** | Lógica implementada (`manterWifi()`) e em execução, mas o ciclo completo — queda provocada e retorno automático — **não foi capturado**. A rede virtual do simulador não permite provocar a queda | Capturar em bancada, desligando o ponto de acesso |
| **Relé sob carga** | O comando e a confirmação foram validados; o acionamento físico **não**. Alimentar o módulo pelo pino de 3,3 V derruba a tensão e dispara o detector de *brownout* do ESP32 | Alimentar o módulo pelo `VIN` (5 V), com GND comum |
| **Operação com broker local** | Todos os testes de rede usaram broker público. O Mosquitto local nunca foi exercitado com o dispositivo físico | Apontar `MQTT_HOST` para o IP do computador na LAN |
| **Sensor analógico do plano B** | Não implementado. Pinos do ADC1 reservados | Depende do resultado do RISCO-01 |

---

## Como reproduzir

Com o firmware gravado e a placa conectada (ver [Como executar](../README.md#14-como-executar)), observe o tráfego de outra máquina:

```bash
mosquitto_sub -h <broker> -p 1883 -t "sentinela/#" -F '%I | %t | %p'
```

E envie comandos:

```bash
mosquitto_pub -h <broker> -p 1883 -t "sentinela/cadeia-fria/comando/rele" -m '{"acao":"ligar"}'
mosquitto_pub -h <broker> -p 1883 -t "sentinela/cadeia-fria/comando/reset" -m '{"acao":"reset"}'
```

O segundo comando, enviado com a caixa fora do estado `QUEBRA`, deve retornar `executado: false` com o motivo — é o caminho de recusa descrito no item 4.
