# Backend

FastAPI + SQLAlchemy + Alembic + paho-mqtt. Formatos da API em [`API.md`](API.md); mensagens MQTT em [`../CONTRATOS.md`](../CONTRATOS.md).

## Subir
Na raiz do repositório (precisa do `.env`, copiado de `.env.example`):
```
docker compose up -d --build
```
A migração do Alembic roda sozinha na partida do container.

## Testes (Python 3.12 em container)
Rodam em SQLite em memória, sem broker. Na raiz do repositório, PowerShell:
```
docker run --rm -v "${PWD}:/repo" -w /repo/backend python:3.12-slim sh -c "pip install -q -r requirements-dev.txt && python -m pytest -q"
```

## Simulador de dispositivos
`../simulador/simulador.py` faz o papel da CF-01 e da VENT-01 (ver o cabeçalho do arquivo). Com o compose no ar, de dentro da rede dele:
```
docker compose run --rm --no-deps -v "${PWD}/simulador:/sim:ro" backend python /sim/simulador.py --host mosquitto --velocidade 20
```
As senhas dos dispositivos vêm do `.env` (`MQTT_PASS_CF01`, `MQTT_PASS_VENT01`). Para variar temperatura/tampa/sensor ao vivo, use `--controle arquivo.json` (montado no container).

## Migrações
Nova migração: `docker compose run --rm --no-deps -v "${PWD}/backend:/app" backend alembic revision --autogenerate -m "descricao"`.

## Telegram (R15)
O backend avisa no Telegram quando a **CF-01 entra em QUEBRA** e quando **um dispositivo fica offline**, uma mensagem por transição (um LWT repetido ou telemetria seguinte em QUEBRA não gera outra). Sem token ou sem `chat_id` o envio fica desligado e o backend segue normal. O envio roda em thread própria: se a API do Telegram cair, nada trava. O token nunca vai para o log.

**O que fazer uma vez** (nenhum dado vai para o repositório):
1. No Telegram, abra uma conversa com **@BotFather**, envie `/newbot`, escolha um nome e um usuário terminado em `bot`. O BotFather responde com o **token** (algo como `123456789:AA...`). Guarde: quem tem o token controla o bot.
2. Crie um **grupo** (ou use uma conversa direta) e **adicione o bot** a ele. Mande qualquer mensagem no grupo.
3. Descubra o **chat_id**: abra no navegador `https://api.telegram.org/bot<SEU_TOKEN>/getUpdates` (troque pelo token) e procure `"chat":{"id":...`. Em grupo o número é **negativo** (ex.: `-1001234567890`). Se vier `"result":[]`, mande outra mensagem no grupo e recarregue.
4. Coloque no `.env` (não versionado):
   ```
   TELEGRAM_BOT_TOKEN=123456789:AA...
   TELEGRAM_CHAT_ID=-1001234567890
   ```
5. Reinicie o backend: `docker compose up -d --build backend`. No log aparece `Telegram ligado`.

Para testar sem esperar uma QUEBRA de verdade, rode o simulador com a CF-01 aberta e velocidade alta, ou publique um `status` `offline` de um dispositivo que estava online.

## CI (GitHub Actions)
[`.github/workflows/ci.yml`](../.github/workflows/ci.yml) roda a cada push e pull request, sem segredos reais:
- **backend:** `pytest` em Python 3.12 (contrato, histerese, `commandId` duplicado, perfis, Telegram, simulador contra o backend);
- **compose:** `docker compose config` com o `.env.example`;
- **firmware:** `pio run -e esp32dev -e vent01` (com `secrets.h` copiado do modelo) e `pio test -e native` (lógica pura).

Os mesmos comandos localmente (na raiz, Git Bash/PowerShell com Docker):
```
docker run --rm -v "${PWD}:/repo" -w /repo/backend python:3.12-slim sh -c "pip install -q -r requirements-dev.txt && python -m pytest -q"
```
```
pio run -e esp32dev -e vent01   # na pasta firmware/
```
