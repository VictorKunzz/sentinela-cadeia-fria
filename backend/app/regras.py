"""Regras de decisao remota (R8). Todas geram comandos com origem `regra` e
percorrem o mesmo ciclo do R7."""
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .comandos import ABERTOS, criar_comando
from .config import Settings, get_settings
from .models import Comando, Dispositivo, Medicao, Regra
from .notify import notificar
from .tempo import agora as _agora
from .tempo import utc

log = logging.getLogger("sentinela.regras")

FRESCOR_S = 15      # leitura mais velha que isto nao serve para decidir
COBERTURA_S = 10    # tolerancia (2 telemetrias) para a janela de 2 min estar "coberta"


def obter_regra(session: Session, settings: Settings | None = None) -> Regra:
    settings = settings or get_settings()
    regra = session.get(Regra, 1)
    if regra is None:
        regra = Regra(
            id=1,
            temp_ligar=settings.regra_temp_ligar,
            temp_desligar=settings.regra_temp_desligar,
            janela_s=settings.regra_janela_s,
            ativa=True,
        )
        session.add(regra)
        session.flush()
    return regra


def avaliar_histerese(
    leituras: list[tuple[datetime, float]],
    agora: datetime,
    exaustor_ligado: bool,
    temp_ligar: float,
    temp_desligar: float,
    janela_s: int,
) -> str | None:
    """Funcao pura da regra R8. Devolve 'ligar', 'desligar' ou None.

    - desligado: liga se TODAS as leituras da ultima `janela_s` ficaram acima de
      `temp_ligar` (e a janela esta de fato coberta por leituras);
    - ligado: desliga assim que a leitura mais recente fica abaixo de `temp_desligar`;
    - entre os dois limites (histerese) nada muda.
    """
    if not leituras:
        return None
    leituras = sorted(leituras, key=lambda x: x[0])
    ultimo_ts, ultima_temp = leituras[-1]
    if (agora - ultimo_ts).total_seconds() > FRESCOR_S:
        return None  # sem dado fresco nao se decide

    if exaustor_ligado:
        return "desligar" if ultima_temp < temp_desligar else None

    inicio = agora - timedelta(seconds=janela_s)
    na_janela = [(t, v) for t, v in leituras if t >= inicio]
    if not na_janela:
        return None
    coberta = leituras[0][0] <= inicio + timedelta(seconds=COBERTURA_S) or (
        na_janela[0][0] <= inicio + timedelta(seconds=COBERTURA_S)
    )
    if coberta and all(v > temp_ligar for _, v in na_janela):
        return "ligar"
    return None


def executar_regras(session: Session, publisher, agora=None, settings: Settings | None = None) -> None:
    """Regra 1 (exaustor). Chamada a cada telemetria/estado e a cada tick do relogio."""
    settings = settings or get_settings()
    agora = agora or _agora()
    regra = obter_regra(session, settings)
    if not regra.ativa:
        return

    vent = session.get(Dispositivo, "VENT-01")
    if vent is None or not vent.online:
        return  # comando QoS 1 para cliente offline (sessao limpa) se perderia
    estado = vent.estado or {}
    if estado.get("modo") == "MANUAL":
        return  # coordenacao assumiu; a regra se cala ate o dispositivo voltar ao automatico
    exaustor_ligado = estado.get("exaustor") == "ligado"

    desde = agora - timedelta(seconds=regra.janela_s + 30)
    linhas = session.execute(
        select(Medicao.recebido_em, Medicao.valor).where(
            Medicao.dispositivo_id == "CF-01",
            Medicao.grandeza == "temperatura",
            Medicao.recebido_em >= desde,
        )
    ).all()
    leituras = [(utc(t), v) for t, v in linhas]

    acao = avaliar_histerese(
        leituras, agora, exaustor_ligado, regra.temp_ligar, regra.temp_desligar, regra.janela_s
    )
    if acao is None:
        return

    # Nao empilhar comandos: ha um da regra em andamento ou enviado ha pouco?
    ultimos = session.scalars(
        select(Comando)
        .where(Comando.dispositivo_id == "VENT-01", Comando.comando == "exaustor", Comando.origem == "regra")
        .order_by(Comando.id.desc())
        .limit(3)
    ).all()
    for c in ultimos:
        if c.status in ABERTOS and c.resultado != "rejeitado":
            return
        if (agora - utc(c.enviado_em)).total_seconds() < settings.comando_prazo_total_s and c.acao == acao:
            return

    log.info("regra R8: %s exaustor (temp ultima=%.1f)", acao, leituras[-1][1] if leituras else float("nan"))
    criar_comando(session, publisher, "VENT-01", "exaustor", acao, origem="regra", agora=agora, settings=settings)


def acionar_quebra(session: Session, publisher, agora=None, settings: Settings | None = None) -> None:
    """Regra 2: caixa entrou em QUEBRA -> sinalizador de retencao + notificacao.
    Chamada so na TRANSICAO para QUEBRA, entao nao repete enquanto o estado nao mudar."""
    notificar("QUEBRA na CF-01: o orçamento térmico acabou. Sinalizador de retenção acionado.")
    criar_comando(session, publisher, "CF-01", "rele", "ligar", origem="regra", agora=agora, settings=settings)
