"""Ciclo de comando (R7): enviado -> recebido -> executado -> confirmado.

O backend e o unico que publica comandos. O dispositivo valida (faixa,
intertravamento, duplicado) e responde; aqui so se registra o que ele disse.
"""
import json
import logging
import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import contrato
from .config import Settings, get_settings
from .models import Comando, Dispositivo, Evento
from .tempo import agora as _agora
from .tempo import utc

log = logging.getLogger("sentinela.comandos")

COMANDOS_POR_DISPOSITIVO = {
    "CF-01": {"rele", "buzzer", "reset", "config"},
    "VENT-01": {"exaustor"},
}
ABERTOS = ("enviado", "recebido", "executado")  # ainda aguardando o proximo passo
FINAIS = ("confirmado", "nao_confirmado", "sem_efeito")

_ESPERADO = {"ligar": "ligado", "desligar": "desligado", "disparar": "ligado", "silenciar": "desligado"}


class NullPublisher:
    """Usado quando o MQTT esta desligado (testes, dev sem broker)."""

    conectado = False

    def publicar(self, topico: str, payload: str, qos: int = 1, retain: bool = False) -> bool:
        return False


def topico_comando(settings: Settings, dispositivo_id: str, comando: str) -> str:
    return f"{settings.mqtt_topic_prefix}/{dispositivo_id}/comando/{comando}"


def criar_comando(
    session: Session,
    publisher,
    dispositivo_id: str,
    comando: str,
    acao: str,
    valor: float | None = None,
    origem: str = "usuario",
    usuario: str | None = None,
    agora=None,
    settings: Settings | None = None,
) -> Comando:
    settings = settings or get_settings()
    agora = agora or _agora()

    cmd = Comando(
        command_id=f"tmp-{uuid.uuid4().hex}",
        dispositivo_id=dispositivo_id,
        comando=comando,
        acao=acao,
        valor=valor,
        origem=origem,
        usuario=usuario,
        status="enviado",
        enviado_em=agora,
    )
    cmd.ja_batia = _ja_batia(session.get(Dispositivo, dispositivo_id), cmd)
    session.add(cmd)
    session.flush()
    cmd.command_id = f"c-{cmd.id:06d}"

    payload = {
        "version": 1,
        "deviceId": dispositivo_id,
        "commandId": cmd.command_id,
        "origem": origem,
        "acao": acao,
    }
    if valor is not None:
        payload["valor"] = valor

    ok = publisher.publicar(topico_comando(settings, dispositivo_id, comando), json.dumps(payload), qos=1, retain=False)
    if not ok:
        cmd.status = "nao_confirmado"
        cmd.detalhe = "broker indisponivel: comando nao publicado"
        log.error("comando %s nao publicado (broker fora)", cmd.command_id)
    else:
        log.info("comando %s -> %s/%s %s (%s)", cmd.command_id, dispositivo_id, comando, acao, origem)
    session.flush()
    return cmd


def concluido(cmd: Comando) -> bool:
    return cmd.status in FINAIS or (cmd.status == "recebido" and cmd.resultado == "rejeitado")


def rotulo(cmd: Comando) -> str:
    """Texto pronto para a interface."""
    if cmd.status == "confirmado":
        return "confirmado"
    if cmd.status == "sem_efeito":
        return "sem efeito: já estava assim"
    if cmd.status == "nao_confirmado":
        return "não confirmado"
    if cmd.status == "recebido" and cmd.resultado == "rejeitado":
        return f"rejeitado: {cmd.motivo}"
    if cmd.status == "executado":
        return "executado, aguardando confirmação"
    return "aguardando"


def _esperado(cmd: Comando):
    """(campo, valor) esperado no `estado` retido, ou None."""
    if cmd.comando in ("rele", "buzzer", "exaustor"):
        if cmd.acao == "auto":
            return ("modo", "AUTOMATICO")
        v = _ESPERADO.get(cmd.acao)
        return (cmd.comando, v) if v else None
    return None


def _ja_batia(disp: Dispositivo | None, cmd: Comando) -> bool:
    """O estado atual do dispositivo ja e o que o comando pede? (comando sem efeito)

    `auto` so tem efeito em MANUAL: em AUTOMATICO ou SEGURO nao muda nada.
    Sem estado conhecido nao ha como afirmar: devolve False (ciclo normal)."""
    esp = _esperado(cmd)
    estado = getattr(disp, "estado", None)
    if esp is None or not estado:
        return False
    if cmd.acao == "auto":
        return estado.get("modo") not in (None, "MANUAL")
    return estado.get(esp[0]) == esp[1]


def tentar_confirmar(session: Session, dispositivo_id: str, agora=None) -> None:
    """Promove executado -> confirmado quando o estado/evento do dispositivo prova o resultado."""
    agora = agora or _agora()
    disp = session.get(Dispositivo, dispositivo_id)
    pendentes = session.scalars(
        select(Comando).where(Comando.dispositivo_id == dispositivo_id, Comando.status == "executado")
    ).all()
    for cmd in pendentes:
        enviado = utc(cmd.enviado_em)
        estado_ok = disp is not None and disp.estado is not None and utc(disp.estado_em) >= enviado
        confirmou = False
        if cmd.comando == "reset":
            recentes = session.scalars(
                select(Evento)
                .where(Evento.dispositivo_id == dispositivo_id, Evento.evento == "reset")
                .order_by(Evento.id.desc())
                .limit(5)
            ).all()
            confirmou = any(utc(e.recebido_em) >= enviado for e in recentes)
        elif cmd.comando == "config":
            confirmou = estado_ok
        else:
            esp = _esperado(cmd)
            confirmou = bool(esp) and estado_ok and disp.estado.get(esp[0]) == esp[1]
        if confirmou:
            cmd.status = "confirmado"
            cmd.confirmado_em = agora


def aplicar_confirmacao(session: Session, conf: "contrato.Confirmacao", agora=None) -> str | None:
    """Registra uma confirmacao do dispositivo. Devolve um motivo se ela nao casa com nenhum comando."""
    agora = agora or _agora()
    cmd = session.scalar(select(Comando).where(Comando.command_id == conf.commandId))
    if cmd is None:
        return f"commandId desconhecido: {conf.commandId}"
    if cmd.dispositivo_id != conf.deviceId:
        return f"commandId {conf.commandId} pertence a {cmd.dispositivo_id}, veio de {conf.deviceId}"

    if conf.resultado == "rejeitado":
        # Rejeicao encerra o ciclo (o dispositivo nao envia `executado` depois).
        if cmd.status in ("enviado", "nao_confirmado", "recebido"):
            cmd.status = "recebido"
            cmd.resultado = "rejeitado"
            cmd.motivo = conf.motivo
            cmd.detalhe = conf.detalhe
            cmd.recebido_em = cmd.recebido_em or agora
    elif conf.resultado == "aceito":
        if cmd.status in ("enviado", "nao_confirmado"):
            cmd.status = "recebido"
            cmd.resultado = "aceito"
            cmd.recebido_em = cmd.recebido_em or agora
    else:  # executado
        if cmd.resultado != "rejeitado" and cmd.status not in ("confirmado", "sem_efeito"):
            cmd.status = "executado"
            cmd.resultado = "executado"
            cmd.executado_em = agora
            cmd.recebido_em = cmd.recebido_em or agora  # o `aceito` pode ter se perdido (QoS 0)
            if cmd.ja_batia:
                # O dispositivo executou, mas o estado ja era o pedido: nada mudou, entao nao ha
                # novo `estado` a esperar. Fecha como informacao neutra (nao e falha, nao alerta).
                cmd.status = "sem_efeito"
                cmd.detalhe = cmd.detalhe or "já estava assim"
    session.flush()
    tentar_confirmar(session, cmd.dispositivo_id, agora)
    return None


def varrer_prazos(session: Session, agora=None, settings: Settings | None = None) -> int:
    """Marca como nao_confirmado o que estourou o prazo. Devolve quantos."""
    settings = settings or get_settings()
    agora = agora or _agora()
    n = 0
    abertos = session.scalars(select(Comando).where(Comando.status.in_(ABERTOS))).all()
    for cmd in abertos:
        if concluido(cmd):  # rejeitado pelo dispositivo: ciclo encerrado
            continue
        idade = agora - utc(cmd.enviado_em)
        estourou = idade > timedelta(seconds=settings.comando_prazo_total_s) or (
            cmd.status == "enviado" and idade > timedelta(seconds=settings.comando_prazo_recebido_s)
        )
        if estourou:
            cmd.status = "nao_confirmado"
            n += 1
            log.warning("comando %s nao confirmado (parou em %s)", cmd.command_id, cmd.resultado or "enviado")
    return n
