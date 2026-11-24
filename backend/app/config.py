"""Configuracao do backend, toda vinda do ambiente (.env no compose)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    database_url: str = "sqlite+pysqlite:///./sentinela.db"

    mqtt_enabled: bool = True
    mqtt_host: str = "mosquitto"
    mqtt_port: int = 1883
    mqtt_user: str = "backend"
    mqtt_pass_backend: str = ""
    mqtt_topic_prefix: str = "sentinela/cadeia-fria"

    jwt_secret: str = "dev-inseguro-troque"
    jwt_expira_min: int = 480
    bcrypt_rounds: int = 12  # os testes usam 4 so para rodar rapido
    seed_coordenacao_user: str = ""
    seed_coordenacao_password: str = ""
    seed_tecnico_user: str = ""
    seed_tecnico_password: str = ""

    comando_prazo_recebido_s: int = 5
    comando_prazo_total_s: int = 15

    regra_temp_ligar: float = 30.0
    regra_temp_desligar: float = 26.0
    regra_janela_s: int = 120

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    tick_s: float = 1.0
    rodar_migracoes: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
