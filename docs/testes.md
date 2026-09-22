# Registro de testes — Sentinela de Cadeia Fria

Este documento registra o que foi **efetivamente exercitado** no sistema, em que ambiente, com que resultado observado — e, com o mesmo destaque, **o que ainda não foi testado**.

Os trechos de saída abaixo são capturas reais, não exemplos ilustrativos.

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
