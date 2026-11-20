"""Rotas REST. A interface web consome so isto; nunca fala com o broker."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import comandos as cmd_mod
from . import indicadores as ind_mod
from .config import get_settings
from .contrato import DISPOSITIVOS
from .db import get_db
from .models import Comando, Dispositivo, Evento, Medicao, Regra, Usuario
from .regras import obter_regra
from .schemas import (
    AlertaOut,
    ComandoIn,
    ComandoOut,
    DispositivoOut,
    EventoOut,
    HistoricoOut,
    IndicadoresOut,
    LoginIn,
    PontoHistorico,
    RegraIO,
    RegraOut,
    TokenOut,
)
from .security import confere_senha, criar_token, exige_coordenacao, usuario_atual
from .sync import LOCK
from .tempo import agora as _agora
from .tempo import utc

router = APIRouter()


# ---------- conversoes ----------
def _dispositivo_out(d: Dispositivo) -> DispositivoOut:
    t = d.telemetria or {}
    e = d.estado or {}
    atuadores = {k: e[k] for k in ("rele", "buzzer", "exaustor") if e.get(k)}
    return DispositivoOut(
        id=d.id,
        tipo=d.tipo,
        nome=d.nome,
        online=bool(d.online),
        ultimo_contato=utc(d.ultimo_contato),
        estado=d.estado_maquina,
        modo=d.modo,
        temperatura=t.get("temperatura"),
        umidade=t.get("umidade"),
        orcamento=t.get("orcamento"),
        aberturas=t.get("aberturas"),
        rssi=t.get("rssi"),
        atuadores=atuadores,
        sensor=e.get("sensor"),
        telemetria_em=utc(d.telemetria_em),
        estado_em=utc(d.estado_em),
    )


def _comando_out(c: Comando) -> ComandoOut:
    return ComandoOut(
        command_id=c.command_id,
        dispositivo=c.dispositivo_id,
        comando=c.comando,
        acao=c.acao,
        valor=c.valor,
        origem=c.origem,
        usuario=c.usuario,
        status=c.status,
        resultado=c.resultado,
        motivo=c.motivo,
        detalhe=c.detalhe,
        concluido=cmd_mod.concluido(c),
        rotulo=cmd_mod.rotulo(c),
        enviado_em=utc(c.enviado_em),
        recebido_em=utc(c.recebido_em),
        executado_em=utc(c.executado_em),
        confirmado_em=utc(c.confirmado_em),
    )


def _dispositivo_ou_404(db: Session, did: str) -> Dispositivo:
    d = db.get(Dispositivo, did)
    if d is None:
        raise HTTPException(404, f"dispositivo desconhecido: {did}")
    return d


# ---------- login ----------
@router.post("/login", response_model=TokenOut, tags=["auth"])
def login(dados: LoginIn, db: Session = Depends(get_db)):
    u = db.scalar(select(Usuario).where(Usuario.username == dados.username))
    # Mesma resposta para usuario inexistente e senha errada.
    if u is None or not confere_senha(dados.password, u.senha_hash):
        raise HTTPException(401, "usuario ou senha invalidos", headers={"WWW-Authenticate": "Bearer"})
    token, expira = criar_token(u)
    return TokenOut(access_token=token, expira_em_s=expira, usuario=u.username, perfil=u.perfil)


# ---------- dispositivos ----------
@router.get("/dispositivos", response_model=list[DispositivoOut], tags=["dispositivos"])
def listar_dispositivos(db: Session = Depends(get_db), _: Usuario = Depends(usuario_atual)):
    return [_dispositivo_out(d) for d in db.scalars(select(Dispositivo).order_by(Dispositivo.id))]


@router.get("/dispositivos/{did}/estado", response_model=DispositivoOut, tags=["dispositivos"])
def estado_dispositivo(did: str, db: Session = Depends(get_db), _: Usuario = Depends(usuario_atual)):
    return _dispositivo_out(_dispositivo_ou_404(db, did))


@router.get("/dispositivos/{did}/historico", response_model=HistoricoOut, tags=["dispositivos"])
def historico(
    did: str,
    grandeza: str = Query("temperatura", pattern="^(temperatura|umidade|orcamento|rssi)$"),
    desde: datetime | None = None,
    ate: datetime | None = None,
    limite: int = Query(500, ge=1, le=5000),
    janela: int = Query(5, ge=1, le=100, description="pontos da media movel"),
    db: Session = Depends(get_db),
    _: Usuario = Depends(usuario_atual),
):
    _dispositivo_ou_404(db, did)
    agora = _agora()
    ate = utc(ate) if ate else agora
    desde = utc(desde) if desde else ate - timedelta(hours=1)
    linhas = db.scalars(
        select(Medicao)
        .where(
            Medicao.dispositivo_id == did,
            Medicao.grandeza == grandeza,
            Medicao.recebido_em >= desde,
            Medicao.recebido_em <= ate,
        )
        .order_by(Medicao.recebido_em.desc())
        .limit(limite)
    ).all()
    linhas.reverse()  # cronologico
    pontos, fila = [], []
    for m in linhas:
        fila.append(m.valor)
        if len(fila) > janela:
            fila.pop(0)
        pontos.append(PontoHistorico(ts=utc(m.recebido_em), valor=m.valor, media_movel=round(sum(fila) / len(fila), 2)))
    return HistoricoOut(
        dispositivo=did,
        grandeza=grandeza,
        unidade=linhas[0].unidade if linhas else None,
        janela_media=janela,
        pontos=pontos,
    )


@router.get("/dispositivos/{did}/eventos", response_model=list[EventoOut], tags=["dispositivos"])
def eventos(
    did: str,
    limite: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    _: Usuario = Depends(usuario_atual),
):
    _dispositivo_ou_404(db, did)
    linhas = db.scalars(
        select(Evento).where(Evento.dispositivo_id == did).order_by(Evento.id.desc()).limit(limite)
    ).all()
    return [
        EventoOut(
            id=e.id, dispositivo=e.dispositivo_id, evento=e.evento, ts=utc(e.ts), recebido_em=utc(e.recebido_em),
            n=e.n, duracao_s=e.duracao_s, temperatura_media=e.temperatura_media, consumo=e.consumo,
            orcamento=e.orcamento, detalhe=e.detalhe,
        )
        for e in linhas
    ]


# ---------- comandos ----------
@router.post("/dispositivos/{did}/comandos", response_model=ComandoOut, status_code=202, tags=["comandos"])
def enviar_comando(
    did: str,
    dados: ComandoIn,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(exige_coordenacao),
):
    _dispositivo_ou_404(db, did)
    if dados.comando not in cmd_mod.COMANDOS_POR_DISPOSITIVO[did]:
        raise HTTPException(
            422, f"{did} nao tem o comando '{dados.comando}' (validos: {sorted(cmd_mod.COMANDOS_POR_DISPOSITIVO[did])})"
        )
    # `acao` segue direto ao dispositivo: acao invalida e rejeitada la, com motivo (R10).
    with LOCK:
        c = cmd_mod.criar_comando(
            db, request.app.state.publisher, did, dados.comando, dados.acao, dados.valor,
            origem="usuario", usuario=usuario.username,
        )
        db.commit()
    return _comando_out(c)


@router.get("/comandos", response_model=list[ComandoOut], tags=["comandos"])
def listar_comandos(
    dispositivo: str | None = None,
    limite: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    _: Usuario = Depends(usuario_atual),
):
    q = select(Comando).order_by(Comando.id.desc()).limit(limite)
    if dispositivo:
        q = q.where(Comando.dispositivo_id == dispositivo)
    return [_comando_out(c) for c in db.scalars(q)]


@router.get("/comandos/{command_id}", response_model=ComandoOut, tags=["comandos"])
def obter_comando(command_id: str, db: Session = Depends(get_db), _: Usuario = Depends(usuario_atual)):
    c = db.scalar(select(Comando).where(Comando.command_id == command_id))
    if c is None:
        raise HTTPException(404, f"comando desconhecido: {command_id}")
    return _comando_out(c)


# ---------- regras ----------
def _regra_out(r: Regra) -> RegraOut:
    return RegraOut(
        temp_ligar=r.temp_ligar, temp_desligar=r.temp_desligar, janela_s=r.janela_s, ativa=r.ativa,
        atualizado_em=utc(r.atualizado_em),
    )


@router.get("/regras", response_model=RegraOut, tags=["regras"])
def ler_regras(db: Session = Depends(get_db), _: Usuario = Depends(usuario_atual)):
    return _regra_out(obter_regra(db, get_settings()))


@router.put("/regras", response_model=RegraOut, tags=["regras"])
def alterar_regras(dados: RegraIO, db: Session = Depends(get_db), _: Usuario = Depends(exige_coordenacao)):
    if dados.temp_desligar >= dados.temp_ligar:
        raise HTTPException(422, "temp_desligar deve ser menor que temp_ligar (histerese)")
    r = obter_regra(db, get_settings())
    r.temp_ligar, r.temp_desligar, r.janela_s, r.ativa = dados.temp_ligar, dados.temp_desligar, dados.janela_s, dados.ativa
    r.atualizado_em = _agora()
    db.flush()
    return _regra_out(r)


# ---------- alertas ----------
@router.get("/alertas", response_model=list[AlertaOut], tags=["alertas"])
def alertas(db: Session = Depends(get_db), _: Usuario = Depends(usuario_atual)):
    saida: list[AlertaOut] = []
    agora = _agora()
    for d in db.scalars(select(Dispositivo).order_by(Dispositivo.id)):
        if d.estado_maquina == "QUEBRA":
            q = db.scalar(
                select(Evento).where(Evento.dispositivo_id == d.id, Evento.evento == "quebra").order_by(Evento.id.desc())
            )
            saida.append(AlertaOut(
                tipo="quebra", severidade="critico", dispositivo=d.id,
                mensagem=f"{d.id} em QUEBRA: orçamento térmico esgotado",
                desde=utc(q.recebido_em) if q else None,
            ))
        if not d.online:
            saida.append(AlertaOut(
                tipo="offline", severidade="critico" if d.ultimo_contato else "aviso", dispositivo=d.id,
                mensagem=f"{d.id} offline" if d.ultimo_contato else f"{d.id} ainda não deu sinal",
                desde=utc(d.ultimo_contato),
            ))
        if d.id == "CF-01" and ((d.estado or {}).get("sensor") == "falha" or d.modo == "SEGURO"):
            saida.append(AlertaOut(
                tipo="sensor_falha", severidade="aviso", dispositivo=d.id,
                mensagem="CF-01 em modo SEGURO: falha de sensor, orçamento congelado", desde=utc(d.estado_em),
            ))
    recentes = db.scalars(
        select(Comando).where(Comando.status == "nao_confirmado").order_by(Comando.id.desc()).limit(20)
    ).all()
    for c in recentes:
        if agora - utc(c.enviado_em) <= timedelta(minutes=10):
            saida.append(AlertaOut(
                tipo="comando_nao_confirmado", severidade="aviso", dispositivo=c.dispositivo_id,
                mensagem=f"comando {c.command_id} ({c.comando} {c.acao}) não foi confirmado", desde=utc(c.enviado_em),
            ))
    return saida


# ---------- indicadores ----------
@router.get("/indicadores", response_model=IndicadoresOut, tags=["indicadores"])
def indicadores(
    dispositivo: str = "CF-01",
    desde: datetime | None = None,
    db: Session = Depends(get_db),
    _: Usuario = Depends(usuario_atual),
):
    if dispositivo not in DISPOSITIVOS:
        raise HTTPException(404, f"dispositivo desconhecido: {dispositivo}")
    d = _dispositivo_ou_404(db, dispositivo)
    agora = _agora()
    desde = utc(desde) if desde else agora - timedelta(hours=24)
    evs = db.scalars(
        select(Evento).where(Evento.dispositivo_id == dispositivo, Evento.recebido_em >= desde).order_by(Evento.id)
    ).all()
    calc = ind_mod.calcular(evs, agora, d.estado_maquina)
    orc = ((d.telemetria or {}).get("orcamento") or {}).get("valor")
    return IndicadoresOut(
        dispositivo=dispositivo, desde=desde, ate=agora, estado_atual=d.estado_maquina, orcamento_atual=orc, **calc
    )
