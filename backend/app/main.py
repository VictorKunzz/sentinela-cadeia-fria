"""Backend do Sentinela de Cadeia Fria (FastAPI)."""
import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import db
from .api import router
from .comandos import NullPublisher, varrer_prazos
from .config import get_settings
from .ingest import garantir_dispositivos
from .models import Base
from .regras import executar_regras, obter_regra
from .security import semear_usuarios
from .sync import LOCK

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("sentinela")


def preparar_banco(settings) -> None:
    """Migracoes (Alembic) em PostgreSQL; create_all so em SQLite de desenvolvimento/testes."""
    db.init_db(settings.database_url)
    if settings.database_url.startswith("sqlite"):
        Base.metadata.create_all(db.engine)
    elif settings.rodar_migracoes:
        from alembic import command
        from alembic.config import Config

        raiz = Path(__file__).resolve().parent.parent
        cfg = Config(str(raiz / "alembic.ini"))
        cfg.set_main_option("script_location", str(raiz / "alembic"))
        command.upgrade(cfg, "head")
    with db.session_scope() as s:
        garantir_dispositivos(s)
        obter_regra(s, settings)
        semear_usuarios(s)


def _relogio(app: FastAPI, parar: threading.Event, settings) -> None:
    """Prazos do ciclo de comando e regras que dependem de tempo decorrido."""
    while not parar.wait(settings.tick_s):
        try:
            with LOCK, db.session_scope() as s:
                varrer_prazos(s, settings=settings)
                executar_regras(s, app.state.publisher, settings=settings)
        except Exception:
            log.exception("erro no relogio do backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    preparar_banco(settings)

    from .telegram import configurar_telegram

    telegram = configurar_telegram(settings)  # None se token/chat_id vazios

    app.state.publisher = NullPublisher()
    mqtt_service = None
    if settings.mqtt_enabled:
        from .mqtt_service import MqttService

        mqtt_service = MqttService(settings)
        app.state.publisher = mqtt_service
        mqtt_service.start()

    parar = threading.Event()
    thread = threading.Thread(target=_relogio, args=(app, parar, settings), daemon=True, name="relogio")
    thread.start()
    try:
        yield
    finally:
        parar.set()
        if mqtt_service:
            mqtt_service.stop()
        if telegram:
            telegram.parar()


app = FastAPI(title="Sentinela de Cadeia Fria", version="1.0.0", lifespan=lifespan)
app.include_router(router)


@app.get("/health", tags=["infra"])
def health() -> dict:
    pub = getattr(app.state, "publisher", None)
    return {"status": "ok", "mqtt": bool(getattr(pub, "conectado", False))}


# Interface web (paginas estaticas). Montada por ultimo para nao encobrir a API.
class _EstaticosSempreAtuais(StaticFiles):
    """Revalida a cada acesso (ETag): evita o navegador mostrar uma versao velha da interface."""

    async def get_response(self, path, scope):
        resposta = await super().get_response(path, scope)
        resposta.headers["Cache-Control"] = "no-cache"
        return resposta


app.mount("/", _EstaticosSempreAtuais(directory=Path(__file__).resolve().parent / "static", html=True), name="web")
