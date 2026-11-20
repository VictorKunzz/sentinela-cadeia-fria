"""Validacao das mensagens dos dispositivos contra o CONTRATOS.md v1.

`validar(tipo, device_do_topico, bruto)` devolve o objeto Pydantic ou levanta
ContratoErro com o motivo (que vai para `mensagens_rejeitadas`).
"""
import json
import math
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

DISPOSITIVOS = {"CF-01": "caixa", "VENT-01": "estacao"}
MOTIVOS = ("QUEBRA_ATIVA", "SEM_QUEBRA", "DUPLICADO", "ACAO_INVALIDA", "FORA_DA_FAIXA")

# Faixas validas (CONTRATOS.md, secao 2)
FAIXAS = {
    "temperatura": ("°C", 0.0, 50.0),
    "umidade": ("%", 20.0, 90.0),
    "orcamento": ("u", 0.0, 600.0),
    "rssi": ("dBm", -120.0, 0.0),
}


class ContratoErro(Exception):
    pass


class Medida(BaseModel):
    model_config = ConfigDict(extra="ignore")
    valor: float = Field(allow_inf_nan=False)
    unidade: str


def _checar(medida: Medida | None, grandeza: str) -> None:
    if medida is None:
        return
    unidade, lo, hi = FAIXAS[grandeza]
    if medida.unidade != unidade:
        raise ValueError(f"{grandeza}: unidade deve ser '{unidade}', veio '{medida.unidade}'")
    if not (lo <= medida.valor <= hi):
        raise ValueError(f"{grandeza}: {medida.valor} fora da faixa {lo} a {hi} {unidade}")


def _parse_ts(texto: str) -> datetime:
    return datetime.fromisoformat(texto.replace("Z", "+00:00"))


class Base(BaseModel):
    model_config = ConfigDict(extra="ignore")

    version: Literal[1]
    deviceId: Literal["CF-01", "VENT-01"]
    ts: str | None
    horaSincronizada: bool

    @model_validator(mode="after")
    def _ts(self):
        if self.horaSincronizada and self.ts is None:
            raise ValueError("ts nulo com horaSincronizada=true")
        if self.ts is not None:
            try:
                dt = _parse_ts(self.ts)
            except ValueError as exc:
                raise ValueError(f"ts nao e ISO-8601: {exc}")
            if dt.tzinfo is None:
                raise ValueError("ts sem fuso horario")
        return self

    def ts_dt(self) -> datetime | None:
        if self.ts is None or not self.horaSincronizada:
            return None
        return _parse_ts(self.ts)


class Telemetria(Base):
    estado: Literal["FECHADO", "EXPOSTO", "QUEBRA"]
    modo: Literal["AUTOMATICO", "MANUAL", "SEGURO"] | None = None
    # Sensor em falha: o firmware manda os dois campos inteiros como null
    # (nao {"valor": null}); ausentes tambem sao aceitos.
    temperatura: Medida | None = None
    umidade: Medida | None = None
    orcamento: Medida
    aberturas: int = Field(ge=0)
    rssi: Medida | None = None

    @model_validator(mode="after")
    def _faixas(self):
        for g in ("temperatura", "umidade", "orcamento", "rssi"):
            _checar(getattr(self, g), g)
        return self


EVENTOS = ("abertura", "fechamento", "quebra", "reset", "sensor_falha", "sensor_ok", "modo_alterado", "boot")


class Evento(Base):
    evento: Literal[EVENTOS]
    n: int | None = Field(default=None, ge=0)
    duracao: Medida | None = None
    temperaturaMedia: Medida | None = None
    consumo: Medida | None = None
    orcamento: Medida | None = None
    detalhe: str | None = None

    @model_validator(mode="after")
    def _faixas(self):
        _checar(self.temperaturaMedia, "temperatura")
        _checar(self.orcamento, "orcamento")
        if self.duracao is not None and self.duracao.unidade != "s":
            raise ValueError("duracao: unidade deve ser 's'")
        return self


class Estado(Base):
    modo: Literal["AUTOMATICO", "MANUAL", "SEGURO"]
    rele: Literal["ligado", "desligado"] | None = None
    buzzer: Literal["ligado", "desligado"] | None = None
    exaustor: Literal["ligado", "desligado"] | None = None
    sensor: Literal["ok", "falha"] | None = None

    @model_validator(mode="after")
    def _atuadores(self):
        if self.deviceId == "VENT-01" and self.exaustor is None:
            raise ValueError("estado da VENT-01 exige 'exaustor'")
        if self.deviceId == "CF-01" and (self.rele is None or self.buzzer is None):
            raise ValueError("estado da CF-01 exige 'rele' e 'buzzer'")
        return self


class Confirmacao(Base):
    commandId: str = Field(pattern=r"^c-\d{6,}$")
    resultado: Literal["aceito", "rejeitado", "executado"]
    motivo: Literal[MOTIVOS] | None = None
    detalhe: str | None = None

    @model_validator(mode="after")
    def _motivo(self):
        if self.resultado == "rejeitado" and self.motivo is None:
            raise ValueError("rejeitado exige 'motivo' do catalogo")
        return self


_MODELOS = {"telemetria": Telemetria, "evento": Evento, "estado": Estado, "confirmacao": Confirmacao}
TIPOS = ("status", "telemetria", "evento", "estado", "confirmacao")


def _resumo(exc: ValidationError) -> str:
    partes = []
    for e in exc.errors():
        loc = ".".join(str(x) for x in e["loc"]) or "(raiz)"
        partes.append(f"{loc}: {e['msg']}")
    return "; ".join(partes)


def validar(tipo: str, device_do_topico: str, bruto: bytes):
    """Valida uma mensagem. `status` devolve 'online'/'offline'; os demais, o modelo."""
    if device_do_topico not in DISPOSITIVOS:
        raise ContratoErro(f"deviceId desconhecido no topico: {device_do_topico!r}")
    if tipo not in TIPOS:
        raise ContratoErro(f"tipo de topico fora do contrato: {tipo!r}")

    try:
        texto = bruto.decode("utf-8")
    except UnicodeDecodeError:
        raise ContratoErro("payload nao e UTF-8")

    if tipo == "status":
        valor = texto.strip()
        if valor not in ("online", "offline"):
            raise ContratoErro(f"status deve ser 'online' ou 'offline', veio {valor[:30]!r}")
        return valor

    try:
        dados = json.loads(texto, parse_constant=lambda c: math.nan)
    except json.JSONDecodeError as exc:
        raise ContratoErro(f"JSON invalido: {exc}")
    if not isinstance(dados, dict):
        raise ContratoErro("payload JSON deve ser um objeto")

    if tipo == "telemetria" and device_do_topico != "CF-01":
        raise ContratoErro("telemetria so existe para a CF-01")

    try:
        obj = _MODELOS[tipo].model_validate(dados)
    except ValidationError as exc:
        raise ContratoErro(_resumo(exc))

    if obj.deviceId != device_do_topico:
        raise ContratoErro(f"deviceId do payload ({obj.deviceId}) difere do topico ({device_do_topico})")
    return obj
