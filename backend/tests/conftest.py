"""Fixtures dos testes. Rodam em SQLite em memoria, sem broker e sem rede.

O ambiente e fixado ANTES de importar o app (get_settings e cacheado).
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ.update(
    DATABASE_URL="sqlite+pysqlite:///:memory:",
    MQTT_ENABLED="false",
    MQTT_TOPIC_PREFIX="sentinela/cadeia-fria",
    JWT_SECRET="segredo-de-teste",
    BCRYPT_ROUNDS="4",
    SEED_COORDENACAO_USER="coord",
    SEED_COORDENACAO_PASSWORD="senha-coord",
    SEED_TECNICO_USER="tec",
    SEED_TECNICO_PASSWORD="senha-tec",
    COMANDO_PRAZO_RECEBIDO_S="5",
    COMANDO_PRAZO_TOTAL_S="15",
)

RAIZ = Path(__file__).resolve().parents[2]
for caminho in (RAIZ / "simulador", RAIZ / "backend"):
    if str(caminho) not in sys.path:
        sys.path.insert(0, str(caminho))

import pytest  # noqa: E402

from app import db  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.ingest import garantir_dispositivos, processar  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402
from app.notify import definir_notificador  # noqa: E402
from app.regras import obter_regra  # noqa: E402
from app.security import semear_usuarios  # noqa: E402

T0 = datetime(2026, 11, 20, 12, 0, 0, tzinfo=timezone.utc)
PREFIXO = "sentinela/cadeia-fria"


class FakePublisher:
    """Faz o papel do broker: guarda o que o backend publicaria."""

    conectado = True

    def __init__(self):
        self.msgs: list[tuple[str, dict]] = []

    def publicar(self, topico, payload, qos=1, retain=False):
        self.msgs.append((topico, json.loads(payload)))
        return True

    def comandos(self, device=None, comando=None):
        saida = []
        for topico, corpo in self.msgs:
            partes = topico.split("/")
            if partes[-2] == "comando" or (len(partes) >= 3 and "comando" in partes):
                if device and f"/{device}/" not in topico:
                    continue
                if comando and not topico.endswith(f"/comando/{comando}"):
                    continue
                saida.append((topico, corpo))
        return saida


@pytest.fixture(autouse=True)
def banco():
    db.init_db("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(db.engine)
    with db.session_scope() as s:
        garantir_dispositivos(s)
        obter_regra(s)
        semear_usuarios(s)
    yield
    definir_notificador(None)


@pytest.fixture
def pub():
    p = FakePublisher()
    app.state.publisher = p
    return p


@pytest.fixture
def avisos():
    lista: list[str] = []
    definir_notificador(lista.append)
    return lista


def ingerir(pub, device, tipo, corpo, agora=T0):
    """Entrega uma mensagem ao backend como se viesse do broker."""
    bruto = corpo if isinstance(corpo, (bytes, str)) else json.dumps(corpo)
    if isinstance(bruto, str):
        bruto = bruto.encode()
    with db.session_scope() as s:
        return processar(s, pub, f"{PREFIXO}/{device}/{tipo}", bruto, agora=agora, settings=get_settings())


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def base(device, agora=T0):
    return {"version": 1, "deviceId": device, "ts": iso(agora), "horaSincronizada": True}


def telemetria(estado="FECHADO", temp=25.0, agora=T0, modo="AUTOMATICO", orcamento=100.0, aberturas=0):
    c = base("CF-01", agora)
    c.update(
        estado=estado, modo=modo,
        temperatura={"valor": temp, "unidade": "°C"} if temp is not None else None,
        umidade={"valor": 55, "unidade": "%"} if temp is not None else None,
        orcamento={"valor": orcamento, "unidade": "u"},
        aberturas=aberturas, rssi={"valor": -60, "unidade": "dBm"},
    )
    return c


def estado_vent(exaustor="desligado", modo="AUTOMATICO", agora=T0):
    c = base("VENT-01", agora)
    c.update(modo=modo, exaustor=exaustor)
    return c


def estado_cf(rele="desligado", buzzer="desligado", modo="AUTOMATICO", agora=T0, sensor="ok"):
    c = base("CF-01", agora)
    c.update(modo=modo, rele=rele, buzzer=buzzer, sensor=sensor)
    return c


def evento(device, nome, agora=T0, **extra):
    c = base(device, agora)
    c.update(evento=nome, n=None, duracao=None, temperaturaMedia=None, consumo=None, orcamento=None, detalhe=None)
    c.update(extra)
    return c


def confirmacao(device, command_id, resultado, motivo=None, agora=T0):
    c = base(device, agora)
    c.update(commandId=command_id, resultado=resultado, motivo=motivo, detalhe=None)
    return c


def vent_online(pub, agora=T0, exaustor="desligado", modo="AUTOMATICO"):
    ingerir(pub, "VENT-01", "status", "online", agora)
    ingerir(pub, "VENT-01", "estado", estado_vent(exaustor, modo, agora), agora)


def seg(n: float) -> timedelta:
    return timedelta(seconds=n)
