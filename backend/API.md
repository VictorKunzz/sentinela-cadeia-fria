# API do backend — Sentinela de Cadeia Fria

Base: `http://<host>:8000`. JSON UTF-8. Documentação interativa gerada pelo FastAPI em `/docs` (OpenAPI em `/openapi.json`).
A interface web **só fala com esta API**; nunca com o broker. Consultar com polling de 2–3 s (`/dispositivos`, `/alertas`, e `/comandos/{id}` enquanto um comando estiver aberto).

Datas: ISO-8601 em **UTC** (`2026-11-20T18:29:12.043281Z`); a interface converte para o fuso local. Números têm unidade explícita (`{"valor": 31.2, "unidade": "°C"}`).

## Autenticação

`POST /login` → token JWT (HS256, validade `JWT_EXPIRA_MIN`, padrão 8 h). Enviar em todas as demais rotas: `Authorization: Bearer <token>`.

| Perfil | Pode |
|---|---|
| `tecnico` | só **ler** (GET) |
| `coordenacao` | ler, **enviar comandos**, **alterar regras** |

Erros: sem token / token inválido ou expirado → **401** (`WWW-Authenticate: Bearer`); perfil sem permissão → **403**; dispositivo/comando inexistente → **404**; corpo inválido → **422**. Todo erro vem como `{"detail": "texto"}` (422 traz a lista do Pydantic em `detail`).

```http
POST /login
{"username": "coordenacao", "password": "..."}

200 {"access_token": "eyJ...", "token_type": "bearer", "expira_em_s": 28800,
     "usuario": "coordenacao", "perfil": "coordenacao"}
401 {"detail": "usuario ou senha invalidos"}
```

## Dispositivos

### `GET /dispositivos` → lista de `Dispositivo` (ordem: `CF-01`, `VENT-01`)
### `GET /dispositivos/{id}/estado` → um `Dispositivo` (404 se `id` desconhecido)

```json
{
  "id": "CF-01", "tipo": "caixa", "nome": "Caixa CF-01",
  "online": true,
  "ultimo_contato": "2026-11-20T18:29:08Z",
  "estado": "EXPOSTO",
  "modo": "AUTOMATICO",
  "temperatura": {"valor": 31.2, "unidade": "°C"},
  "umidade": {"valor": 55.0, "unidade": "%"},
  "orcamento": {"valor": 44.8, "unidade": "u"},
  "aberturas": 2,
  "rssi": {"valor": -60.0, "unidade": "dBm"},
  "atuadores": {"rele": "desligado", "buzzer": "desligado"},
  "sensor": "ok",
  "telemetria_em": "2026-11-20T18:29:08Z",
  "estado_em": "2026-11-20T18:29:02Z"
}
```

| Campo | Valores / observações |
|---|---|
| `tipo` | `caixa` (CF-01) · `estacao` (VENT-01) |
| `online` | presença (status MQTT + Last Will). `false` = **offline**. Dispositivo que nunca deu sinal: `online=false` e `ultimo_contato=null` |
| `estado` | máquina da caixa: `FECHADO` · `EXPOSTO` · `QUEBRA`; `null` na VENT-01 e antes da 1ª telemetria |
| `modo` | `AUTOMATICO` · `MANUAL` · `SEGURO` (ou `null` se ainda desconhecido) |
| `temperatura`, `umidade`, `orcamento`, `rssi` | objeto `{valor, unidade}` ou **`null`** (VENT-01 não mede; CF-01 com sensor em falha manda `temperatura`/`umidade` nulas) |
| `aberturas` | contador da caixa (`null` na VENT-01) |
| `atuadores` | CF-01: `rele` (sinalizador) e `buzzer`; VENT-01: `exaustor`. Valores `ligado` · `desligado`. Vazio até o 1º `estado` |
| `sensor` | `ok` · `falha` (só a CF-01; `null` se desconhecido) |
| `telemetria_em` / `estado_em` | quando o backend recebeu a última telemetria / o último `estado` |

A interface deve tratar `modo = SEGURO` ou `sensor = falha` como alerta de falha de sensor (já vem também em `/alertas`).

### `GET /dispositivos/{id}/historico`
Query: `grandeza` (`temperatura` padrão · `umidade` · `orcamento` · `rssi`), `desde`, `ate` (ISO-8601; padrão: última hora), `limite` (1–5000, padrão 500; devolve os **mais recentes**), `janela` (pontos da média móvel, 1–100, padrão 5).

```json
{"dispositivo": "CF-01", "grandeza": "temperatura", "unidade": "°C", "janela_media": 5,
 "pontos": [{"ts": "2026-11-20T18:00:00Z", "valor": 24.0, "media_movel": 24.0}, ...]}
```
Pontos em ordem cronológica; `media_movel` calculada no servidor (média dos últimos `janela` pontos, arredondada a 2 casas); direto para o Chart.js. `unidade` é `null` se não houver pontos.

### `GET /dispositivos/{id}/eventos?limite=50` (1–500)
Eventos da máquina de estados, **do mais novo para o mais antigo**:
```json
[{"id": 7, "dispositivo": "CF-01", "evento": "quebra", "ts": "...", "recebido_em": "...",
  "n": 2, "duracao_s": null, "temperatura_media": 40.0, "consumo": 120.0, "orcamento": 0.0, "detalhe": null}]
```
`evento` ∈ `abertura` `fechamento` `quebra` `reset` `sensor_falha` `sensor_ok` `modo_alterado` `boot`.

## Comandos

### `POST /dispositivos/{id}/comandos` — só `coordenacao` — **202**
```json
{"comando": "exaustor", "acao": "ligar"}
{"comando": "config", "acao": "orcamentoInicial", "valor": 90}
```
Comandos por dispositivo: **CF-01** `rele` (`ligar` `desligar` `auto`), `buzzer` (`disparar` `silenciar` `auto`), `reset` (`reset`), `config` (`orcamentoInicial` + `valor` 30–600); **VENT-01** `exaustor` (`ligar` `desligar` `auto`).
O backend só valida o **nome do comando** para o dispositivo (422 se não existir, ex.: `reset` na VENT-01). A `acao`/faixa vai direto ao dispositivo, que rejeita com motivo — assim a rejeição aparece na interface (R10).
Comando de usuário em `rele`/`buzzer`/`exaustor` põe o dispositivo em `MANUAL` por 10 min (volta sozinho, ou com `acao: "auto"`).

Resposta (`Comando`):
```json
{
  "command_id": "c-000123", "dispositivo": "VENT-01", "comando": "exaustor", "acao": "ligar", "valor": null,
  "origem": "usuario", "usuario": "coordenacao",
  "status": "enviado", "resultado": null, "motivo": null, "detalhe": null,
  "concluido": false, "rotulo": "aguardando",
  "enviado_em": "...", "recebido_em": null, "executado_em": null, "confirmado_em": null
}
```

### `GET /comandos/{command_id}` → `Comando` · `GET /comandos?dispositivo=&limite=20` → lista (mais novos primeiro)

**Ciclo do comando** (consultar até `concluido = true`):

| `status` | `resultado` | `rotulo` (texto pronto) | `concluido` |
|---|---|---|---|
| `enviado` | `null` | `aguardando` | não |
| `recebido` | `aceito` | `aguardando` | não |
| `executado` | `executado` | `executado, aguardando confirmação` | não |
| `confirmado` | `executado` | `confirmado` | **sim** |
| `recebido` | `rejeitado` | `rejeitado: <motivo>` | **sim** (o dispositivo recusou; ciclo encerrado) |
| `nao_confirmado` | — | `não confirmado` | **sim** (sem resposta no prazo) |

`motivo` (quando rejeitado) ∈ `QUEBRA_ATIVA` `SEM_QUEBRA` `DUPLICADO` `ACAO_INVALIDA` `FORA_DA_FAIXA`. `detalhe` é texto livre (ex.: `modo manual`, ou `broker indisponivel: comando nao publicado`).
Prazos de `nao_confirmado`: **5 s** sem `recebido`, **15 s** no total (configuráveis no `.env`). Uma confirmação tardia ainda atualiza o registro.
Comandos gerados pela regra aparecem com `origem: "regra"` e `usuario: null`.

## Regras (R8)

`GET /regras` (qualquer perfil) · `PUT /regras` (só `coordenacao`):
```json
{"temp_ligar": 30.0, "temp_desligar": 26.0, "janela_s": 120, "ativa": true, "atualizado_em": null}
```
Em `PUT` não se envia `atualizado_em`. Validação (422): `temp_desligar < temp_ligar` (histerese), `janela_s` 10–3600, temperaturas 0–60. Vale imediatamente.
Comportamento: com o exaustor desligado, se **todas** as leituras da caixa nos últimos `janela_s` ficarem **acima** de `temp_ligar`, liga; com ele ligado, desliga quando a leitura mais recente fica **abaixo** de `temp_desligar`. Se a VENT-01 estiver em `MANUAL` ou offline, a regra não age. Quebra da CF-01 → comando `rele ligar` + notificação, uma vez por transição.

## Alertas

`GET /alertas` → lista (vazia quando tudo está normal), pronta para o painel:
```json
[{"tipo": "quebra", "severidade": "critico", "dispositivo": "CF-01",
  "mensagem": "CF-01 em QUEBRA: orçamento térmico esgotado", "desde": "2026-11-20T18:32:54Z"}]
```
`tipo`: `quebra` (crítico) · `offline` (crítico; "aviso" se o dispositivo nunca deu sinal) · `sensor_falha` (aviso) · `comando_nao_confirmado` (aviso, últimos 10 min). `desde` pode ser `null`.

## Indicadores (R14)

`GET /indicadores?dispositivo=CF-01&desde=<ISO>` (padrão: últimas 24 h; só faz sentido para a caixa):
```json
{"dispositivo": "CF-01", "desde": "...", "ate": "...", "estado_atual": "QUEBRA", "orcamento_atual": 0.0,
 "aberturas": 3, "aberturas_por_turno": {"manha": 1, "tarde": 2, "noite": 0}, "quebras": 1,
 "tempo_exposicao_s": 412.0, "tempo_quebra_s": 95.0}
```
Turnos no fuso America/Sao_Paulo: `manha` 06–14 h, `tarde` 14–22 h, `noite` 22–06 h. `tempo_exposicao_s`: soma de abertura→fechamento (ou →quebra); se a caixa está `EXPOSTO` agora, inclui o tempo corrente. `tempo_quebra_s`: de `quebra` até `reset` (ou até agora, se ainda em QUEBRA).

## Infra

`GET /health` (sem login) → `{"status": "ok", "mqtt": true}` (`mqtt` = backend conectado ao broker).
