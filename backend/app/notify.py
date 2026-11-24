"""Gancho de notificacao externa. O Telegram (item 1.8) registra aqui o seu
envio com `definir_notificador`; ate la, so loga."""
import logging
from collections.abc import Callable

log = logging.getLogger("sentinela.notificacao")

_notificador: Callable[[str], None] | None = None


def definir_notificador(fn: Callable[[str], None] | None) -> None:
    global _notificador
    _notificador = fn


def notificar(mensagem: str) -> None:
    log.warning("NOTIFICACAO: %s", mensagem)
    if _notificador is not None:
        try:
            _notificador(mensagem)
        except Exception:  # notificar nunca derruba o processamento
            log.exception("falha ao enviar notificacao")
