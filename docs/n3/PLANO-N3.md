# Plano da N3 — Sentinela de Cadeia Fria

**Defesa: 01/12/2026.** Este arquivo é a fonte única do que falta. Marque `[x]` quando o critério "pronto quando" for verdade, e não antes. Cada item cita o requisito do piso R1–R18 que ele atende (detalhes em [`CP12.md`](CP12.md)).

Onde cada frente está agora, recados entre frentes e diário: [`ESTADO.md`](ESTADO.md). Pinos e ligações: [`PINAGEM.md`](PINAGEM.md).

**Ordem de trabalho:**
1. Comprar as peças.
2. Enquanto elas não chegam: software e interface prontos, testados com a CF-01 que já existe e com o Wokwi.
3. Quando chegarem: hardware.
4. Testes de falha e entrega.
5. Só se sobrar tempo: compactação e molde 3D.

## Calendário

| Data | Marco |
|---|---|
| **17/11** (aula) | Compras feitas, frentes divididas, contrato v1 iniciado |
| 18–21/11 | Contrato v1 congelado; firmware CF-01 v2; backend recebendo e gravando; interface com login |
| **24/11** (aula) | Ciclo de comando ponta a ponta; regras do R8; VENT-01 rodando (Wokwi ou peças reais) |
| 25–28/11 | Hardware real integrado; testes de falha com evidência; OTA; CI; painel analítico |
| 29–30/11 | README final, tag de release, ensaio da defesa. **Congelar:** nada novo depois do dia 30 |
| **01/12** | **N3** |

## Decisões técnicas (fixas, para não rediscutir)

| Camada | Escolha |
|---|---|
| Broker | Mosquitto (container), na LAN |
| Backend | Python 3.12 + FastAPI + SQLAlchemy + Alembic + paho-mqtt |
| Banco | PostgreSQL 16 (container) |
| Interface | Páginas estáticas servidas pelo próprio FastAPI (HTML + JS + Chart.js). Consulta a API a cada 2–3 s. Nunca fala com o broker |
| Autenticação | Login com usuário e senha, token JWT; perfis `tecnico` (só vê) e `coordenacao` (vê e comanda) |
| Orquestração | `compose.yaml` com `mosquitto`, `db`, `backend` |
| Notificação | Bot do Telegram chamado pelo backend |
| Testes / CI | pytest + GitHub Actions |
| Firmware | PlatformIO, o mesmo projeto da N1; a VENT-01 em um segundo `env` ou pasta própria |
| Hardware | **Fechado pela compra de 18/11:** só se usa o que está no README, seção 6, e na [`BOM.md`](BOM.md). Pinos e ligações em [`PINAGEM.md`](PINAGEM.md) |

**Termos do CP12 × peça real.** O CP12 v1.0 (`docs/n3/CP12_EQUIPE-6_PROJETO_v1.0.pdf`, seções 1–9) é o compromisso entregue e não se altera. Ele foi escrito em 27/10, antes da compra. Regra: **onde o PDF conflita com a compra ou com este plano, valem a compra e o plano**, e a diferença é declarada como limitação. **Onde o PDF detalha algo que o plano não tinha** (esquema 5.1, modos e tempos do fluxograma 5.3, contrato congelado da seção 6), o PDF completa o plano. Ao falar dele, use esta correspondência:

| No CP12 | Peça real |
|---|---|
| "exaustor 12 V" | ventoinha 80 mm 12 V 0,15 A (no MQTT continua `exaustor`) |
| "módulo de potência" | módulo relé 1 canal SRD-05VDC |
| "fonte própria" | fonte 12 V 1 A; o ESP32 da VENT-01 recebe 5 V pelo LM2596 |
| "sinalizador de retenção" / "LED vermelho 10 mm + 150 Ω" | LED vermelho 5 mm do kit + 150 Ω, pelo contato do relé de 2 canais |
| "2 ESP32 (VENT-01 + reserva)", "DHT11 reserva" | só o ESP32 da VENT-01 foi comprado; sem reservas (limitação a declarar) |
| "chave de tampa" | microchave fim de curso KW12 |
| "botão de reset" | botão de painel PBS-11B |
| "montada em caixa térmica" | caixa térmica a providenciar pelo grupo (não comprada) |

---

## Fase 0 — Compras (hoje) · lista completa em [`BOM.md`](BOM.md)

- [x] Pedido feito no Mercado Livre (13 itens, R$ 307,93): ESP32 DevKit V1 30 pinos, ventoinha 12 V, fonte 12 V, relé 1 canal, 120 jumpers (M-M, M-F, F-F), regulador LM2596, conectores P4 fêmea, microchaves KW12, botões de painel, LEDs RGB cátodo comum, placas perfuradas, barras de pinos macho e fêmea, bornes KF301
- [ ] Conseguir **BC337 + resistor 1 kΩ** (buzzer) e **diodo 1N4007** (ventoinha), que estão no esquema do CP12 v1.0 e não foram comprados. Pedir ao tio
- [ ] Separar: power bank + cabo (CF-01)
- [ ] Providenciar a **caixa térmica** da CF-01 (isopor de supermercado serve). Não foi comprada e o CP12 promete a CF-01 montada nela
- [x] Ferramentas de solda e montagem em mãos (lista em [ESTADO.md](ESTADO.md), frente Hardware)
- [ ] Reservar a impressora 3D do laboratório (mesmo que o molde fique para o fim)

**Pronto quando:** os itens chegaram (previsão 18–19/11). Compactação só se sobrar tempo (Fase 5).

---

## Fase 1 — Software (enquanto as peças não chegam)

### 1.1 Contrato MQTT v1 · R3 — *bloqueia todo o resto; fazer primeiro*

- [ ] `CONTRATOS.md` na raiz do repo, com `version: 1`. O contrato já foi **congelado como v1 na seção 6 do CP12 v1.0**: transcrever e detalhar, sem mudar tópicos, comandos nem payloads. Deve trazer:
  - árvore `sentinela/cadeia-fria/{deviceId}/{status|telemetria|evento|estado|comando/<acao>|confirmacao}`
  - um payload de exemplo por tópico, com `version`, `deviceId`, `ts` (ISO-8601 ou epoch, com flag `horaSincronizada`) e unidades
  - lista de comandos com faixas: CF-01 `rele`, `buzzer`, `reset`, `config`; VENT-01 `exaustor`
  - confirmação com `commandId` + `resultado` (`aceito` | `rejeitado` | `executado`) + `motivo`
  - catálogo de códigos de erro: `QUEBRA_ATIVA`, `SEM_QUEBRA`, `DUPLICADO`, `ACAO_INVALIDA`, `FORA_DA_FAIXA`
  - QoS e retain justificados por tópico, incluindo a limitação do PubSubClient (só publica em QoS 0)
- [ ] `docs/arquitetura-mqtt.md` passa a apontar para o `CONTRATOS.md` (sem duplicar)

**Pronto quando:** os responsáveis por firmware e backend leram e aprovaram; tag `contrato-v1` criada.

### 1.2 Firmware CF-01 v2 · R2, R7, R17 — *testável no ESP32 atual*

- [ ] `deviceId` (`CF-01`) no `secrets.h` e nos tópicos novos
- [ ] Hora real por NTP (`configTime`); `horaSincronizada: false` enquanto não sincronizar
- [ ] Payloads no formato do contrato v1 (`version`, `deviceId`, `ts`, unidades)
- [ ] Comandos com `commandId`: confirmação `aceito`/`rejeitado` e depois `executado`; `commandId` repetido é rejeitado sem executar (guardar os últimos ~10)
- [ ] Validação de faixa plausível do DHT11 (0–50 °C, 20–90 % UR)
- [ ] Estado seguro de sensor ausente: orçamento congelado, LED azul, evento `sensor_falha` publicado
- [ ] Orçamento inicial em NVS (`Preferences`), alterável pelo comando `config`
- [ ] Modos do fluxograma do CP12 (5.3): AUTOMÁTICO (FECHADO/EXPOSTO/QUEBRA); **MANUAL** ao aceitar comando, volta ao automático em **10 min** ou por comando; **SEGURO** após **3 leituras inválidas**, sai com **2 válidas**
- [ ] Intertravamento: "desligar sinalizador" rejeitado com QUEBRA ativa (`QUEBRA_ATIVA`); "reset" rejeitado sem QUEBRA (`SEM_QUEBRA`)
- [ ] Backoff MQTT até 30 s (já existe, só conferir); keep-alive de volta a 15 s no Mosquitto local
- [ ] ArduinoOTA com senha (vinda do `secrets.h`)

**Pronto quando:** `pio run` compila; no ESP32 atual, um cliente MQTT vê cada tópico no formato do contrato; comando duplicado é rejeitado; tirar o DHT11 leva ao LED azul.

### 1.3 Firmware VENT-01 · R2, R13 — *testável no Wokwi antes das peças*

- [ ] Projeto/`env` próprio, `deviceId` `VENT-01`; assina só `VENT-01/comando/exaustor`
- [ ] Exaustor **desligado no boot**; relé em repouso antes de configurar o pino (como no fix active-low da CF-01)
- [ ] Ciclo de confirmação igual ao da CF-01 (`commandId`, duplicado, `executado`)
- [ ] Modos do fluxograma do CP12 (5.3): AUTOMÁTICO segue o backend; MANUAL por comando da coordenação, volta em **10 min**; **SEGURO**: exaustor desliga sozinho se ficar **ligado 15 min sem MQTT**, e sai do SEGURO quando a conexão com o broker volta
- [ ] Publica `status` (LWT) e `estado` (`exaustor: ligado/desligado`)

**Pronto quando:** no Wokwi, um comando publicado à mão liga e desliga o "relé" com as duas confirmações.

### 1.4 Infra · R12, R9

- [ ] `compose.yaml` com `mosquitto`, `db`, `backend`; volumes para os dados do banco e do Mosquitto
- [ ] `mosquitto.conf` com usuário e senha (sai o broker público e aberto da N1)
- [ ] `.env.example` com todas as variáveis; `.env` no `.gitignore`

**Pronto quando:** em uma máquina limpa, `docker compose up` sobe os três serviços sem erro.

### 1.5 Backend + banco · R4, R5, R7, R8

- [ ] Modelos e migração Alembic inicial:
  - `dispositivos`
  - `medicoes` (dispositivo, grandeza, valor, unidade, ts)
  - `eventos`
  - `comandos` (`commandId`, origem usuário/regra, ação, enviado_em, recebido_em, executado_em, confirmado_em, resultado, motivo, status)
  - `mensagens_rejeitadas`
  - `usuarios`
- [ ] Assinante MQTT: valida contra o contrato (Pydantic); válida → banco; inválida → `mensagens_rejeitadas` + log
- [ ] Presença: `online`/`offline` e `ultimo_contato` por dispositivo
- [ ] API:
  - `GET /dispositivos`
  - `GET /dispositivos/{id}/estado`
  - `GET /dispositivos/{id}/historico`
  - `POST /dispositivos/{id}/comandos`
  - `GET /comandos/{commandId}`
  - `GET/PUT /regras`
- [ ] Ciclo de comando: gera `commandId`, publica (é o **único** que publica comandos), avança `enviado → recebido → executado → confirmado`; sem resposta em X s vira `nao_confirmado`
- [ ] Regra 1: CF-01 acima de 30 °C por 2 min → `VENT-01` liga; abaixo de 26 °C → desliga. Limites editáveis em `/regras`
- [ ] Regra 2: CF-01 em `QUEBRA` → comando `rele` ligado na CF-01 + notificação

**Pronto quando:** com a CF-01 real ligada, a telemetria aparece no banco; um JSON inválido publicado à mão cai em `mensagens_rejeitadas`; um POST de comando percorre os 4 estados.

### 1.6 Autenticação e perfis · R9, R16

- [ ] `POST /login` → JWT; senhas com hash (bcrypt); usuários-semente pelo `.env`
- [ ] Rotas de comando e `/regras` exigem o perfil `coordenacao`; `tecnico` só lê

**Pronto quando:** com o perfil `tecnico`, o POST de comando devolve 403; sem token, devolve 401.

### 1.7 Interface web · R6, R14 — *pensar como produto: nome, cores, ícone do Sentinela*

- [ ] Tela de login
- [ ] Painel com um cartão por dispositivo: online/offline, último contato, temperatura e UR com unidade, estado (FECHADO/EXPOSTO/QUEBRA), orçamento, exaustor ligado/desligado
- [ ] Alertas ativos em destaque (QUEBRA, offline, falha de sensor)
- [ ] Botões de comando (só para `coordenacao`), com status ao vivo: `aguardando` → `executado`/`confirmado` ou `não confirmado`/`rejeitado: motivo`
- [ ] Histórico: gráfico de temperatura com média móvel (Chart.js)
- [ ] Indicadores (R14): tempo acumulado em exposição, aberturas por turno, tempo em QUEBRA
- [ ] Tela de regras: editar 30 °C / 26 °C / 2 min
- [ ] Funciona no celular (a coordenação usa o celular)

**Pronto quando:** alguém de fora da equipe faz login, entende o estado das duas caixas e manda um comando sem explicação.

### 1.8 Telegram · R15

- [ ] Bot criado (BotFather); token e chat_id no `.env`
- [ ] Mensagem quando a CF-01 entra em QUEBRA e quando qualquer dispositivo fica offline (sem repetir enquanto o estado não mudar)

**Pronto quando:** derrubar a CF-01 gera uma única mensagem no grupo.

### 1.9 Testes e CI · R18

- [ ] pytest: validação do contrato (válido/inválido), regra de histerese (29/31/27/25 °C), `commandId` duplicado, permissão por perfil
- [ ] `.github/workflows/ci.yml` rodando os testes a cada push e PR

**Pronto quando:** o selo do Actions aparece verde no README.

---

## Fase 2 — Hardware (quando as peças chegarem) · R1, R13

- [ ] **Teste do power bank:** CF-01 ligada 30 min sem o power bank desligar sozinho
- [ ] CF-01: relé alimentado pelo `VIN` (5 V) com GND comum; o brownout some ao acionar
- [ ] CF-01: LED vermelho de 5 mm do kit (com resistor de 150 Ω) como sinalizador, ligado ao 5 V pela saída do relé; microchave KW12 como sensor de tampa; botão de painel como reset; buzzer pelo BC337 + 1 kΩ (esquema do CP12)
- [ ] VENT-01: uma fonte só. Fonte 12 V → conector P4 fêmea com borne → divide em dois ramos: (a) LM2596 **ajustado para 5,0 V no multímetro antes de ligar o ESP32** → `VIN`/`GND` do ESP32; (b) +12 V pelo COM/NA do relé até a ventoinha. O ESP32 nunca alimenta a ventoinha
- [ ] VENT-01: relé ligado com jumpers F-F (`VIN` 5 V, `GND`, `IN`); GND comum entre o LM2596, o ESP32 e o relé; diodo 1N4007 em antiparalelo na ventoinha (faixa no +)
- [ ] Mapa de pinos dos dois dispositivos em [`PINAGEM.md`](PINAGEM.md) (v1 escrita; confirmar na bancada) e esquema elétrico (Fritzing/KiCad/Wokwi) versionado como imagem
- [ ] Montagem mínima prometida no CP12: CF-01 **fixada dentro de uma caixa térmica real**, sem fios soltos (protoboard presa e fios organizados já cumprem; a placa soldada é a Fase 5)

**Pronto quando:** aquecer o DHT11 (mão ou secador) acima de 30 °C por 2 min faz o cooler da VENT-01 girar sozinho, e o painel mostra o comando confirmado.

---

## Fase 3 — Falhas testadas · R10 — *cada uma com provocação, esperado, observado e evidência (print ou vídeo) em `docs/testes.md`*

- [ ] Queda do Wi-Fi: o semáforo e o alarme locais seguem; o painel mostra offline; a reconexão é automática
- [ ] Broker parado (`docker compose stop mosquitto`): o backoff cresce até 30 s; a sessão volta sozinha
- [ ] Falha de sensor (desconectar o DHT11): estado seguro, LED azul, alerta no painel
- [ ] Comando inválido e `commandId` duplicado: rejeição com motivo; nada é executado duas vezes
- [ ] OTA (R17): gravar uma versão nova sem cabo; gravar em vídeo

---

## Fase 4 — Entrega · R11

- [ ] README "Como executar" da N3: pré-requisitos, `.env`, `docker compose up`, gravar os dois firmwares, usuários de teste
- [ ] README com o selo de CI, diagrama de arquitetura e link para `CONTRATOS.md`, `PLANO-N3.md` e `testes.md`
- [ ] Limitações da N3 declaradas abertamente
- [ ] **Commit de cada um dos 6 integrantes** no histórico
- [ ] Tag de release `v3.0.0` no commit defendido
- [ ] Roteiro da defesa (5–10 min): problema → demonstração ao vivo (abrir a tampa, aquecer, exaustor liga, QUEBRA → sinalizador + Telegram, comando pelo painel) → falha provocada → OTA
- [ ] Ensaio completo pelo menos uma vez, com cronômetro, no equipamento e na rede da defesa
- [ ] Plano B da demonstração: vídeo gravado de cada parte, caso a rede da sala falhe

---

## Fase 5 — Se sobrar tempo

- [ ] Eletrônica soldada em placa perfurada (CF-01 e VENT-01), ESP32 encaixado em barra fêmea (nunca soldado direto, para poder trocar); bornes KF301 nas entradas de alimentação e da ventoinha; barras macho para ligar módulos com jumper F-F
- [ ] Molde 3D (PETG de preferência), medido a partir da placa soldada: furos para LED, botão, sinalizador, cabo USB, entrada de ar do DHT11
- [ ] Fotos do produto final no README

---

## Divisão sugerida (preencher os nomes)

| Frente | Itens | Responsável |
|---|---|---|
| Contrato + firmware CF-01 | 1.1, 1.2 | |
| Firmware VENT-01 + hardware | 1.3, Fase 2 | |
| Infra + backend + banco | 1.4, 1.5 | |
| Autenticação + testes/CI | 1.6, 1.9 | |
| Interface + painel analítico | 1.7 | |
| Telegram + falhas + docs/defesa | 1.8, Fases 3 e 4 | |

Cada pessoa faz os próprios commits, em branch própria e com PR, porque o commit de cada integrante conta ponto.
