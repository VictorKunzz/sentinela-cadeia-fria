"""Processamento das mensagens recebidas do broker (R4).

`processar` e chamada para cada mensagem. Valida contra o contrato; valida vai
ao banco, invalida vai para `mensagens_rejeitadas`. Nao faz commit: quem chama
(assinante MQTT ou teste) controla a transacao.
"""
import logging

from sqlalchemy.orm import Session

from . import contrato
from .comandos import aplicar_confirmacao, tentar_confirmar
from .config import Settings, get_settings
from .models import Dispositivo, Evento, Medicao, MensagemRejeitada
from .notify import notificar
from .regras import acionar_quebra, executar_regras
from .tempo import agora as _agora

log = logging.getLogger("sentinela.ingest")

_ESTADO_POR_EVENTO = {
    "abertura": "EXPOSTO",
    "fechamento": "FECHADO",
    "quebra": "QUEBRA",
    "reset": "FECHADO",
}


def garantir_dispositivos(session: Session) -> None:
    nomes = {"CF-01": "Caixa CF-01", "VENT-01": "Estação de ventilação VENT-01"}
    for did, tipo in contrato.DISPOSITIVOS.items():
        if session.get(Dispositivo, did) is None:
            session.add(Dispositivo(id=did, tipo=tipo, nome=nomes[did], online=False))
    session.flush()


def _rejeitar(session: Session, topico: str, bruto: bytes, motivo: str, agora) -> str:
    texto = bruto.decode("utf-8", errors="replace")
    session.add(
        MensagemRejeitada(topico=topico[:200], payload=texto[:4000], motivo=motivo[:2000], recebido_em=agora)
    )
    log.warning("mensagem rejeitada em %s: %s", topico, motivo)
    return "rejeitada"


def _ts_efetivo(obj, agora):
    return obj.ts_dt() or agora


def processar(
    session: Session,
    publisher,
    topico: str,
    bruto: bytes,
    agora=None,
    settings: Settings | None = None,
) -> str:
    """Devolve 'ok' ou 'rejeitada'."""
    settings = settings or get_settings()
    agora = agora or _agora()

    prefixo = settings.mqtt_topic_prefix + "/"
    if not topico.startswith(prefixo):
        return _rejeitar(session, topico, bruto, "topico fora do prefixo do contrato", agora)
    partes = topico[len(prefixo):].split("/")
    if len(partes) != 2:
        return _rejeitar(session, topico, bruto, "topico fora do formato {deviceId}/{tipo}", agora)
    device, tipo = partes

    try:
        obj = contrato.validar(tipo, device, bruto)
    except contrato.ContratoErro as exc:
        return _rejeitar(session, topico, bruto, str(exc), agora)

    garantir_dispositivos(session)
    disp = session.get(Dispositivo, device)
    disp.ultimo_contato = agora

    if tipo == "status":
        antes = disp.online
        disp.online = obj == "online"
        if antes and not disp.online:
            notificar(f"{device} ficou OFFLINE (perda de contato com o broker).")
        executar_regras(session, publisher, agora, settings)

    elif tipo == "telemetria":
        _telemetria(session, publisher, disp, obj, agora, settings)

    elif tipo == "evento":
        _evento(session, publisher, disp, obj, agora, settings)

    elif tipo == "estado":
        disp.estado = obj.model_dump(mode="json")
        disp.estado_em = agora
        disp.modo = obj.modo
        tentar_confirmar(session, device, agora)
        executar_regras(session, publisher, agora, settings)

    elif tipo == "confirmacao":
        problema = aplicar_confirmacao(session, obj, agora)
        if problema:
            return _rejeitar(session, topico, bruto, problema, agora)

    return "ok"


def _telemetria(session, publisher, disp, t: contrato.Telemetria, agora, settings) -> None:
    ts = _ts_efetivo(t, agora)
    anterior = disp.estado_maquina

    for grandeza in ("temperatura", "umidade", "orcamento", "rssi"):
        medida = getattr(t, grandeza)
        if medida is not None:
            session.add(
                Medicao(
                    dispositivo_id=disp.id,
                    grandeza=grandeza,
                    valor=medida.valor,
                    unidade=medida.unidade,
                    ts=ts,
                    recebido_em=agora,
                )
            )
    disp.telemetria = t.model_dump(mode="json")
    disp.telemetria_em = agora
    disp.estado_maquina = t.estado
    if t.modo:
        disp.modo = t.modo

    if t.estado == "QUEBRA" and anterior != "QUEBRA":
        acionar_quebra(session, publisher, agora, settings)
    executar_regras(session, publisher, agora, settings)


def _evento(session, publisher, disp, e: contrato.Evento, agora, settings) -> None:
    session.add(
        Evento(
            dispositivo_id=disp.id,
            evento=e.evento,
            ts=_ts_efetivo(e, agora),
            recebido_em=agora,
            n=e.n,
            duracao_s=e.duracao.valor if e.duracao else None,
            temperatura_media=e.temperaturaMedia.valor if e.temperaturaMedia else None,
            consumo=e.consumo.valor if e.consumo else None,
            orcamento=e.orcamento.valor if e.orcamento else None,
            detalhe=(e.detalhe or None) and e.detalhe[:120],
        )
    )
    session.flush()

    anterior = disp.estado_maquina
    novo = _ESTADO_POR_EVENTO.get(e.evento)
    if novo and disp.id == "CF-01":
        disp.estado_maquina = novo

    if e.evento == "quebra" and anterior != "QUEBRA":
        acionar_quebra(session, publisher, agora, settings)
    elif e.evento == "sensor_falha":
        notificar(f"{disp.id}: falha de sensor (estado seguro, orçamento congelado).")

    tentar_confirmar(session, disp.id, agora)
