"""Telegram (R15): uma mensagem por transicao, desligado sem token, falha da API nao derruba."""
import json
import logging

import httpx
import pytest

from app.config import Settings
from app.telegram import configurar_telegram

from conftest import T0, evento, ingerir, seg, telemetria

TOKEN = "123456:segredo-do-bot-NAO-VAZAR"


class FakeTelegram:
    """Transporte httpx que grava as chamadas, sem rede."""

    def __init__(self, status=200, erro=None):
        self.chamadas: list[tuple[str, dict]] = []
        self.status = status
        self.erro = erro

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if self.erro:
            raise self.erro
        self.chamadas.append((str(request.url), json.loads(request.content)))
        return httpx.Response(self.status, json={"ok": self.status == 200})


@pytest.fixture
def telegram():
    """Notificador ligado ao gancho, falando com um transporte falso."""
    fake = FakeTelegram()
    cfg = Settings(telegram_bot_token=TOKEN, telegram_chat_id="-10042", _env_file=None)
    notificador = configurar_telegram(cfg, client=httpx.Client(transport=httpx.MockTransport(fake)))
    assert notificador is not None
    fake.notificador = notificador
    yield fake
    notificador.parar()


def textos(fake):
    fake.notificador.aguardar()
    return [corpo["text"] for _, corpo in fake.chamadas]


def test_sem_token_ou_sem_chat_fica_desligado(caplog):
    with caplog.at_level(logging.INFO):
        assert configurar_telegram(Settings(telegram_bot_token="", telegram_chat_id="1", _env_file=None)) is None
        assert configurar_telegram(Settings(telegram_bot_token=TOKEN, telegram_chat_id="", _env_file=None)) is None
    assert TOKEN not in caplog.text


def test_envia_para_a_bot_api_com_chat_e_texto(telegram):
    from app.notify import notificar

    notificar("teste de envio")
    assert textos(telegram) == ["🧊 Sentinela: teste de envio"]
    url, corpo = telegram.chamadas[0]
    assert url == f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    assert corpo["chat_id"] == "-10042"


def test_quebra_gera_uma_unica_mensagem(pub, telegram):
    ingerir(pub, "CF-01", "telemetria", telemetria("EXPOSTO", 31, T0), T0)
    assert textos(telegram) == []

    t = T0 + seg(5)
    ingerir(pub, "CF-01", "telemetria", telemetria("QUEBRA", 31, t, orcamento=0), t)
    ingerir(pub, "CF-01", "evento", evento("CF-01", "quebra", t), t)
    ingerir(pub, "CF-01", "telemetria", telemetria("QUEBRA", 31, t + seg(5), orcamento=0), t + seg(5))
    msgs = textos(telegram)
    assert len(msgs) == 1 and "QUEBRA" in msgs[0]


def test_offline_gera_uma_mensagem_por_transicao(pub, telegram):
    ingerir(pub, "VENT-01", "status", "online", T0)
    assert textos(telegram) == []
    ingerir(pub, "VENT-01", "status", "offline", T0 + seg(60))
    ingerir(pub, "VENT-01", "status", "offline", T0 + seg(61))  # LWT repetido
    msgs = textos(telegram)
    assert len(msgs) == 1 and "VENT-01" in msgs[0] and "OFFLINE" in msgs[0]

    ingerir(pub, "VENT-01", "status", "online", T0 + seg(90))
    ingerir(pub, "VENT-01", "status", "offline", T0 + seg(120))  # nova queda, nova mensagem
    assert len(textos(telegram)) == 2


def test_resposta_de_erro_da_api_nao_levanta_nem_vaza_o_token(telegram, caplog):
    from app.notify import notificar

    telegram.status = 401
    with caplog.at_level(logging.DEBUG):
        notificar("vai falhar")
        telegram.notificador.aguardar()
    assert "401" in caplog.text
    assert TOKEN not in caplog.text


def test_falha_de_rede_nao_derruba_e_nao_vaza_o_token(telegram, caplog):
    from app.notify import notificar

    # A excecao do httpx carrega a URL (com o token) na mensagem: nao pode ir ao log.
    telegram.erro = httpx.ConnectError(f"falhou em https://api.telegram.org/bot{TOKEN}/sendMessage")
    with caplog.at_level(logging.DEBUG):
        notificar("sem rede")
        telegram.notificador.aguardar()
        notificar("de novo")  # a thread continua viva depois da falha
        telegram.notificador.aguardar()
    assert "ConnectError" in caplog.text
    assert TOKEN not in caplog.text


def test_envio_nao_bloqueia_quem_notifica(telegram):
    """`enviar` so enfileira: volta antes de a Bot API responder."""
    import threading
    import time

    liberar = threading.Event()
    original = telegram.__call__

    def lenta(request):
        liberar.wait(5)
        return original(request)

    telegram.notificador._client = httpx.Client(transport=httpx.MockTransport(lenta))
    t0 = time.monotonic()
    telegram.notificador.enviar("lenta")
    assert time.monotonic() - t0 < 0.5
    liberar.set()
    assert len(textos(telegram)) == 1
