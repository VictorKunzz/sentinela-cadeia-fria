"""Indicadores agregados (R14), calculados a partir dos eventos reais da caixa."""
from datetime import datetime
from zoneinfo import ZoneInfo

from .tempo import utc

FUSO = ZoneInfo("America/Sao_Paulo")


def turno_de(dt: datetime) -> str:
    h = utc(dt).astimezone(FUSO).hour
    if 6 <= h < 14:
        return "manha"
    if 14 <= h < 22:
        return "tarde"
    return "noite"


def calcular(eventos: list, agora: datetime, estado_atual: str | None) -> dict:
    """`eventos`: objetos com .evento, .recebido_em, .duracao_s, em ordem cronologica.

    - exposicao: de `abertura` ate `fechamento` (usa a duracao medida pelo
      dispositivo) ou ate `quebra`; se ainda aberta, ate agora;
    - QUEBRA: de `quebra` ate `reset`; se ainda ativa, ate agora.
    """
    aberturas = 0
    por_turno = {"manha": 0, "tarde": 0, "noite": 0}
    quebras = 0
    exposicao_s = 0.0
    quebra_s = 0.0
    inicio_exp = None
    inicio_quebra = None

    for e in eventos:
        t = utc(e.recebido_em)
        if e.evento == "abertura":
            aberturas += 1
            por_turno[turno_de(t)] += 1
            inicio_exp = t
        elif e.evento == "fechamento":
            if e.duracao_s is not None:
                exposicao_s += e.duracao_s
            elif inicio_exp is not None:
                exposicao_s += (t - inicio_exp).total_seconds()
            inicio_exp = None
        elif e.evento == "quebra":
            quebras += 1
            if inicio_exp is not None:
                exposicao_s += (t - inicio_exp).total_seconds()
                inicio_exp = None
            inicio_quebra = t
        elif e.evento == "reset":
            if inicio_quebra is not None:
                quebra_s += (t - inicio_quebra).total_seconds()
                inicio_quebra = None

    if inicio_exp is not None and estado_atual == "EXPOSTO":
        exposicao_s += (agora - inicio_exp).total_seconds()
    if inicio_quebra is not None and estado_atual == "QUEBRA":
        quebra_s += (agora - inicio_quebra).total_seconds()

    return {
        "aberturas": aberturas,
        "aberturas_por_turno": por_turno,
        "quebras": quebras,
        "tempo_exposicao_s": round(exposicao_s, 1),
        "tempo_quebra_s": round(quebra_s, 1),
    }
