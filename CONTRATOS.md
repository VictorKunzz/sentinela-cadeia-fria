# CONTRATOS — MQTT do Sentinela de Cadeia Fria

**`version: 1`** · congelado como v1 na seção 6 do CP12 v1.0 (entrega de 27/10/2026); este arquivo é a versão detalhada e vigente. Ele transcreve e detalha esse contrato: **tópicos, comandos e catálogo de erros não mudam**. Qualquer mudança incompatível exige `version: 2` e aviso às frentes de firmware e backend.

Dispositivos: `CF-01` (caixa, mede e publica) e `VENT-01` (estação de ventilação, só atua). Eles **nunca se falam**: tudo passa pelo backend, que é o **único** que publica comandos. A interface nunca fala com o broker.

O contrato anterior (N1, tópicos sem `deviceId`) está em [`docs/arquitetura-mqtt.md`](docs/arquitetura-mqtt.md) e foi superado por este.

## 1. Árvore de tópicos

Prefixo: `sentinela/cadeia-fria/{deviceId}/`, com `deviceId` ∈ {`CF-01`, `VENT-01`}.

| Tópico (após o prefixo) | Quem publica | CF-01 | VENT-01 | QoS | Retain | Quando |
|---|---|---|---|---|---|---|
| `status` | dispositivo (e o broker, via *Last Will*) | ✔ | ✔ | LWT 1 · publicação 0 ¹ | **sim** | ao conectar (`online`); o broker publica `offline` se o dispositivo sumir |
| `telemetria` | dispositivo | ✔ | — | 0 | não | a cada 5 s |
| `evento` | dispositivo | ✔ | ✔ | 0 | não | a cada mudança de estado ou de modo |
| `estado` | dispositivo | ✔ | ✔ | 0 ¹ | **sim** | ao conectar e a cada mudança de atuador ou de modo |
| `comando/<comando>` | **backend** | ✔ | ✔ | **1** (assinatura) | não | a pedido da coordenação ou de uma regra |
| `confirmacao` | dispositivo | ✔ | ✔ | 0 ¹ | não | por comando: 1ª resposta (aceito/rejeitado) e 2ª (executado) |

¹ **Limitação do PubSubClient:** o parâmetro de QoS só vale na assinatura e no *Last Will*; toda publicação do dispositivo sai em **QoS 0**. A perda de uma confirmação não deixa o painel inconsistente: o backend marca o comando como `nao_confirmado` no prazo (seção 5).

**Justificativas**
- `status` retido: quem assina depois já sabe se o dispositivo está vivo. *Last Will* em QoS 1 porque é a única mensagem que o broker publica sozinho.
- `estado` retido: um painel ou backend que reinicia lê o estado atual dos atuadores sem esperar a próxima mudança.
- `telemetria` e `evento` não retidos: são histórico, não estado; perder uma amostra de 5 s não compromete o monitoramento. A QUEBRA continua visível na telemetria seguinte (`estado: "QUEBRA"`).
- `comando` **não retido**: evita que um comando antigo seja reexecutado quando o dispositivo reconecta.

**Quem assina o quê**
- Dispositivo: só `…/{seuDeviceId}/comando/+`.
- Backend: `sentinela/cadeia-fria/+/status`, `/telemetria`, `/evento`, `/estado`, `/confirmacao`.

## 2. Regras gerais de payload

- JSON UTF-8, **exceto `status`**, que é texto simples (`online` | `offline`).
- Todo JSON traz `version` (inteiro, `1`), `deviceId` e `ts`.
- `ts`: ISO-8601 com fuso (`2026-10-27T21:40:05-03:00`) quando o relógio estiver sincronizado por NTP. Campo `horaSincronizada` (bool) acompanha o `ts`. Se for `false`, **`ts` vai `null`** e o backend usa a hora de recebimento.
- Grandezas medidas são objetos `{"valor": …, "unidade": "…"}`. Unidades: `°C`, `%`, `u` (unidade do orçamento térmico), `dBm`, `s`.
- Valor ausente vai como `null`, nunca `NaN`.
- Campos desconhecidos são ignorados; campo obrigatório ausente, tipo errado, `version` ≠ 1 ou valor fora da faixa → o backend **descarta a mensagem e registra** em `mensagens_rejeitadas`.
- `estado` (da máquina da CF-01) ∈ {`FECHADO`, `EXPOSTO`, `QUEBRA`} · `modo` ∈ {`AUTOMATICO`, `MANUAL`, `SEGURO`}.

### Faixas válidas (backend valida; firmware também valida a leitura do sensor)

| Grandeza | Faixa |
|---|---|
| temperatura | 0 a 50 °C (limite do DHT11) |
| umidade | 20 a 90 % |
| orçamento | 0 a 600 u |
| rssi | −120 a 0 dBm |

**Temperatura e umidade são validadas separadamente no firmware.** Só a **temperatura** decide o modo `SEGURO` (3 leituras inválidas seguidas: `NaN` ou fora de 0–50 °C; sai com 2 válidas) e alimenta o orçamento e a regra R8. Umidade fora de 20–90 % (ou `NaN`) invalida **apenas a umidade**: ela vai `null` na telemetria, sem afetar a temperatura nem o `SEGURO`. *Limitação conhecida:* bafo ou vapor satura o DHT11 (UR > 90 %); a umidade volta sozinha assim que a leitura retorna à faixa.

## 3. Mensagens publicadas pelo dispositivo

### `status`
```
online          (retido; publicado ao conectar)
offline         (retido; publicado pelo broker como Last Will)
```

### `telemetria` (somente CF-01, a cada 5 s)
```json
{
  "version": 1, "deviceId": "CF-01",
  "ts": "2026-10-27T21:40:05-03:00", "horaSincronizada": true,
  "estado": "EXPOSTO", "modo": "AUTOMATICO",
  "temperatura": {"valor": 31.0, "unidade": "°C"},
  "umidade": {"valor": 58, "unidade": "%"},
  "orcamento": {"valor": 44.8, "unidade": "u"},
  "aberturas": 2,
  "rssi": {"valor": -67, "unidade": "dBm"}
}
```
Com o sensor em falha (modo `SEGURO`), `temperatura` e `umidade` vão `null` e o orçamento fica congelado. Com a temperatura válida e só a umidade fora da faixa, `umidade` vai `null` e o restante segue normal (ver seção 2).

### `evento` (mudança de estado ou de modo)
```json
{
  "version": 1, "deviceId": "CF-01",
  "ts": "2026-10-27T21:40:53-03:00", "horaSincronizada": true,
  "evento": "fechamento",
  "n": 2,
  "duracao": {"valor": 48, "unidade": "s"},
  "temperaturaMedia": {"valor": 31.2, "unidade": "°C"},
  "consumo": {"valor": 101.8, "unidade": "u"},
  "orcamento": {"valor": 18.2, "unidade": "u"},
  "detalhe": null
}
```
`evento` ∈ {`abertura`, `fechamento`, `quebra`, `reset`, `sensor_falha`, `sensor_ok`, `modo_alterado`, `boot`}. Campos que não se aplicam ao evento vão `null` (mesmo esquema para todos, o consumidor não trata variações). `detalhe` é texto livre curto (ex.: `"AUTOMATICO->MANUAL"`). A VENT-01 só publica `modo_alterado` e `boot`.

### `estado` (retido, atuadores e modo)
```json
{
  "version": 1, "deviceId": "VENT-01",
  "ts": "2026-10-27T21:41:10-03:00", "horaSincronizada": true,
  "modo": "AUTOMATICO",
  "exaustor": "ligado"
}
```
CF-01: `{…, "modo": "AUTOMATICO", "rele": "desligado", "buzzer": "desligado", "sensor": "ok"}`. Valores de atuador ∈ {`ligado`, `desligado`}; `sensor` ∈ {`ok`, `falha`}. O campo do atuador é o **nome do comando** (`rele`, `buzzer`, `exaustor`).

## 4. Comandos (backend → dispositivo)

Tópico `…/{deviceId}/comando/<comando>` (o último segmento é o **nome do comando**; `acao` é um campo do payload), QoS 1, não retido. Payload:
```json
{
  "version": 1, "deviceId": "VENT-01",
  "commandId": "c-000123",
  "origem": "regra",
  "acao": "ligar"
}
```
- `commandId`: `c-` + 6 dígitos, gerado pelo backend, único. O dispositivo guarda os **últimos 10**; repetido → rejeitado sem executar (`DUPLICADO`).
- `origem` ∈ {`usuario`, `regra`}. Comando `usuario` aceito de `rele`, `buzzer` ou `exaustor` leva o dispositivo ao modo `MANUAL` (`reset` e `config` não mudam o modo) (volta ao `AUTOMATICO` em **10 min** ou com `acao: "auto"`). Comando `regra` não muda o modo.

| Dispositivo | Comando (último segmento do tópico) | `acao` aceitas | Faixa / regra |
|---|---|---|---|
| CF-01 | `rele` (sinalizador de retenção) | `ligar`, `desligar`, `auto` | `desligar` com QUEBRA ativa → `QUEBRA_ATIVA` |
| CF-01 | `buzzer` | `disparar`, `silenciar`, `auto` | — |
| CF-01 | `reset` | `reset` | sem QUEBRA ativa → `SEM_QUEBRA` |
| CF-01 | `config` | `orcamentoInicial` + `"valor": <número>` | 30 a 600 u; fora → `FORA_DA_FAIXA`; persistido em NVS |
| VENT-01 | `exaustor` | `ligar`, `desligar`, `auto` | — |

Qualquer `acao` fora da tabela → `ACAO_INVALIDA`. Um comando `regra` que chegue com o dispositivo em `MANUAL` é rejeitado como `ACAO_INVALIDA` com `detalhe: "modo manual"` (o backend deveria já ter suspendido a regra ao ler `estado.modo`). **Exceção de segurança:** quando a CF-01 entra em QUEBRA estando em `MANUAL`, ela volta sozinha ao `AUTOMATICO` (publica `modo_alterado`, `detalhe: "MANUAL->AUTOMATICO"`), para que o alarme e o comando `rele ligar` da regra de QUEBRA não sejam bloqueados.

## 5. Confirmação e ciclo do comando

Tópico `…/{deviceId}/confirmacao`. O dispositivo publica **duas** mensagens por comando, com o mesmo `commandId`:
```json
{ "version": 1, "deviceId": "VENT-01", "commandId": "c-000123",
  "resultado": "aceito", "motivo": null, "detalhe": null,
  "ts": "2026-10-27T21:41:09-03:00", "horaSincronizada": true }
```
`resultado` ∈ {`aceito`, `rejeitado`, `executado`}. Rejeição traz `motivo` do catálogo e **não é seguida de `executado`**.

**Catálogo de motivos**

| `motivo` | Quando |
|---|---|
| `QUEBRA_ATIVA` | CF-01: `rele` + `desligar` enquanto houver QUEBRA (a retenção só sai com o reset) |
| `SEM_QUEBRA` | CF-01: `reset` sem QUEBRA ativa |
| `DUPLICADO` | `commandId` já visto (últimos 10) |
| `ACAO_INVALIDA` | `acao` desconhecida para aquele comando, ou payload malformado, ou regra em modo manual |
| `FORA_DA_FAIXA` | `config` com valor fora de 30–600 |

**Estados do comando no backend** (tabela `comandos`):

| Estado | Como é atingido |
|---|---|
| `enviado` | backend registrou e publicou |
| `recebido` | chegou `aceito` ou `rejeitado` (rejeitado encerra aqui, com o motivo) |
| `executado` | chegou `executado` |
| `confirmado` | o `estado` retido publicado depois reflete o pedido (`rele`/`buzzer`/`exaustor` iguais ao esperado; `reset` confirma pelo `evento` `reset`; `config` confirma pelo próprio `executado`, porque o orçamento inicial não faz parte do `estado`) |
| `nao_confirmado` | sem avançar no prazo: **5 s** para `recebido`, **15 s** no total (configuráveis no `.env`) |

O firmware publica o `estado` em até 2 s quando algum atuador, o modo ou o sensor mudam. Comandos que não mudam nada (`sem_efeito`) e o `config` não geram novo `estado`.

## 6. Erros no backend

Mensagem que não passa na validação (JSON inválido, `version` ≠ 1, campo obrigatório ausente, fora da faixa, `deviceId` do payload diferente do tópico) vai para `mensagens_rejeitadas` com tópico, payload bruto e motivo, e é descartada.

## 7. Detalhes acrescentados à v1

O CP12 congela árvore, comandos, catálogo de erros e o formato dos exemplos. Este arquivo **detalhou** o que o CP12 deixou em aberto, sem alterar o que estava congelado:

1. `origem` (`usuario`/`regra`) no comando: necessário para o fluxograma do CP12 (MANUAL só por comando da coordenação).
2. `acao: "auto"` em `rele`, `buzzer` e `exaustor`: é o "comando `auto`" que o fluxograma da CF-01 cita para sair do MANUAL.
3. Nomes de `acao`: `ligar`/`desligar` (relé, exaustor) e `disparar`/`silenciar` (buzzer), herdados da N1.
4. `config`: parâmetro `orcamentoInicial`, faixa 30–600 u (o CP12 só diz que existe e é alterável).
5. Nomes dos eventos em minúsculas com `_` (`sensor_falha` como no CP12); `modo` no payload da telemetria; campo `detalhe`.
6. Prazos do `nao_confirmado` (5 s / 15 s) e `ts: null` quando a hora não está sincronizada.
7. Faixas de validação e `deviceId` do payload igual ao do tópico.
8. **Reset:** o `reset` (botão ou comando) devolve a CF-01 ao `FECHADO`, restaura o orçamento, **apaga o sinalizador** e solta o silenciamento do buzzer.
9. **VENT-01 em `SEGURO`:** se o exaustor ficar ligado por 15 minutos sem conexão com o broker, o dispositivo o desliga e entra em `SEGURO`; ao reconectar, volta ao `AUTOMATICO`.
10. **Confirmação do `config`:** pelo `executado` (ver seção 5), porque o firmware não republica o `estado` nesse caso.

> A tag `contrato-v1` marca o contrato no momento do congelamento. As correções posteriores (regra da umidade, QUEBRA tirando do modo manual, confirmação do `config`) estão neste arquivo e valem para a v1; a versão defendida é a da tag de release do repositório.
