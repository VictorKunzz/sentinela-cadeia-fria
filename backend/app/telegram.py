"""Notificacao por Telegram (R15).

Liga-se ao gancho de `notify.py`: quem decide QUANDO avisar sao os pontos que ja
detectam a TRANSICAO (ingest.py: dispositivo ficou offline; regras.py: CF-01
entrou em QUEBRA), entao nao ha repeticao enquanto o estado nao muda. Aqui so
se cuida de ENVIAR: em thread propria (nunca bloqueia o processamento MQTT) e
sem deixar uma falha da Bot API derrubar o backend.

Token e chat_id vem de TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID. Se qualquer um
estiver vazio, o envio fica desligado (apenas um log). O token NUNCA e logado:
a URL da Bot API o contem, entao as excecoes do httpx (que citam a URL) sao
registradas so pelo tipo.
"""
from __future__ import annotations

import logging
import queue
import threading

import httpx

from .config import Settings
from .notify import definir_notificador

log = logging.getLogger("sentinela.telegram")

# O httpx registra "HTTP Request: POST <url completa>" em INFO, e a URL da Bot API
# contem o token. Sobe o nivel desses loggers para que ele nunca va ao log.
for _nome in ("httpx", "httpcore"):
    logging.getLogger(_nome).setLevel(logging.WARNING)

API = "https://api.telegram.org"
TIMEOUT_S = 10.0
FILA_MAX = 50  # se a API ficar fora do ar, descarta as mais novas em vez de crescer sem limite


class TelegramNotificador:
    def __init__(self, token: str, chat_id: str, client: httpx.Client | None = None):
        self._url = f"{API}/bot{token}/sendMessage"
        self._chat_id = chat_id
        self._client = client or httpx.Client(timeout=TIMEOUT_S)
        self._fila: queue.Queue[str | None] = queue.Queue(maxsize=FILA_MAX)
        self._thread = threading.Thread(target=self._trabalhar, daemon=True, name="telegram")
        self._thread.start()

    def enviar(self, mensagem: str) -> None:
        """Enfileira e retorna na hora."""
        try:
            self._fila.put_nowait(mensagem)
        except queue.Full:
            log.warning("fila do Telegram cheia; mensagem descartada")

    def aguardar(self) -> None:
        """Bloqueia ate a fila esvaziar (usado nos testes e no desligamento)."""
        self._fila.join()

    def parar(self) -> None:
        self._fila.put(None)
        self._thread.join(timeout=TIMEOUT_S + 2)
        self._client.close()

    def _trabalhar(self) -> None:
        while True:
            mensagem = self._fila.get()
            try:
                if mensagem is None:
                    return
                self._postar(mensagem)
            finally:
                self._fila.task_done()

    def _postar(self, mensagem: str) -> None:
        texto = f"🧊 Sentinela: {mensagem}"
        try:
            resp = self._client.post(self._url, json={"chat_id": self._chat_id, "text": texto})
            if resp.status_code != 200:
                # Sem resp.url nem corpo bruto: nada que possa conter o token.
                log.warning("Telegram recusou a mensagem (HTTP %s)", resp.status_code)
        except Exception as exc:  # rede, DNS, timeout: o backend segue de pe
            log.warning("falha ao falar com o Telegram (%s)", type(exc).__name__)


def configurar_telegram(settings: Settings, client: httpx.Client | None = None) -> TelegramNotificador | None:
    """Registra o Telegram como notificador, se houver token e chat_id."""
    token = (settings.telegram_bot_token or "").strip()
    chat_id = (settings.telegram_chat_id or "").strip()
    if not token or not chat_id:
        log.info("Telegram desligado (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID vazios)")
        return None
    notificador = TelegramNotificador(token, chat_id, client)
    definir_notificador(notificador.enviar)
    log.info("Telegram ligado")
    return notificador
