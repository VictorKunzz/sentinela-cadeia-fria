"""Comando que nao muda nada vira `sem_efeito` (informacao neutra), nunca alerta.

Origem: teste integrado de 21/11 — `auto` com o dispositivo ja em AUTOMATICO ficava
`nao_confirmado` e acendia alerta, mas o dispositivo tinha respondido `executado`."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.comandos import rotulo, concluido

from conftest import T0, confirmacao, estado_cf, estado_vent, ingerir, seg, vent_online
from test_comandos import cmd, novo
from test_api import token  # noqa: F401


def executar(pub, device, cid, t=1):
    ingerir(pub, device, "confirmacao", confirmacao(device, cid, "aceito"), T0 + seg(t))
    ingerir(pub, device, "confirmacao", confirmacao(device, cid, "executado"), T0 + seg(t + 1))


@pytest.mark.parametrize("estado_inicial,acao", [
    (dict(exaustor="desligado", modo="AUTOMATICO"), "auto"),
    (dict(exaustor="ligado", modo="MANUAL"), "ligar"),
    (dict(exaustor="desligado", modo="MANUAL"), "desligar"),
])
def test_vent01_comando_sem_efeito(pub, estado_inicial, acao):
    vent_online(pub, **estado_inicial)
    cid = novo(pub, acao=acao)
    assert cmd(cid).ja_batia is True
    executar(pub, "VENT-01", cid)
    c = cmd(cid)
    assert c.status == "sem_efeito" and c.detalhe == "já estava assim" and c.resultado == "executado"
    assert concluido(c) and rotulo(c) == "sem efeito: já estava assim"


@pytest.mark.parametrize("comando,acao,estado", [
    ("rele", "ligar", dict(rele="ligado")),
    ("rele", "desligar", dict(rele="desligado")),
    ("buzzer", "silenciar", dict(buzzer="desligado")),
    ("buzzer", "disparar", dict(buzzer="ligado")),
    ("rele", "auto", dict(modo="AUTOMATICO")),
    ("buzzer", "auto", dict(modo="SEGURO")),     # auto fora do MANUAL nao muda nada
])
def test_cf01_comando_sem_efeito(pub, comando, acao, estado):
    ingerir(pub, "CF-01", "status", "online", T0)
    ingerir(pub, "CF-01", "estado", estado_cf(**estado), T0)
    cid = novo(pub, "CF-01", comando, acao)
    executar(pub, "CF-01", cid)
    assert cmd(cid).status == "sem_efeito"


def test_mudanca_real_continua_ate_confirmado(pub):
    vent_online(pub, exaustor="desligado", modo="AUTOMATICO")
    cid = novo(pub, acao="ligar")
    assert cmd(cid).ja_batia is False
    executar(pub, "VENT-01", cid)
    assert cmd(cid).status == "executado"            # espera o estado novo
    ingerir(pub, "VENT-01", "estado", estado_vent("ligado", "MANUAL", T0 + seg(3)), T0 + seg(3))
    assert cmd(cid).status == "confirmado"


def test_auto_em_manual_muda_e_confirma(pub):
    vent_online(pub, exaustor="ligado", modo="MANUAL")
    cid = novo(pub, acao="auto")
    assert cmd(cid).ja_batia is False
    executar(pub, "VENT-01", cid)
    ingerir(pub, "VENT-01", "estado", estado_vent("ligado", "AUTOMATICO", T0 + seg(3)), T0 + seg(3))
    assert cmd(cid).status == "confirmado"


def test_rejeicao_nao_vira_sem_efeito(pub):
    ingerir(pub, "CF-01", "status", "online", T0)
    ingerir(pub, "CF-01", "estado", estado_cf(rele="ligado"), T0)
    cid = novo(pub, "CF-01", "rele", "ligar")          # ja ligado, mas o dispositivo rejeita
    ingerir(pub, "CF-01", "confirmacao", confirmacao("CF-01", cid, "rejeitado", "ACAO_INVALIDA"), T0 + seg(1))
    c = cmd(cid)
    assert c.status == "recebido" and c.resultado == "rejeitado" and c.motivo == "ACAO_INVALIDA"


def test_sem_resposta_continua_nao_confirmado(pub):
    from app import db
    from app.comandos import varrer_prazos
    from app.config import get_settings

    vent_online(pub, exaustor="desligado", modo="AUTOMATICO")
    cid = novo(pub, acao="auto")                        # ja_batia, mas o dispositivo nao responde
    with db.session_scope() as s:
        varrer_prazos(s, agora=T0 + seg(60), settings=get_settings())
    assert cmd(cid).status == "nao_confirmado"


def test_sem_estado_conhecido_segue_ciclo_normal(pub):
    cid = novo(pub, acao="ligar")                       # nenhum estado ainda: nao da para afirmar
    assert cmd(cid).ja_batia is False
    executar(pub, "VENT-01", cid)
    assert cmd(cid).status == "executado"


def test_sem_efeito_nao_gera_alerta_e_aparece_na_lista(pub):
    vent_online(pub, exaustor="desligado", modo="AUTOMATICO")
    cid = novo(pub, acao="auto")
    executar(pub, "VENT-01", cid)
    client = TestClient(app)
    h = token(client, "coord", "senha-coord")
    alertas = client.get("/alertas", headers=h).json()
    assert not any(a["tipo"] == "comando_nao_confirmado" for a in alertas)
    lista = client.get("/comandos?dispositivo=VENT-01", headers=h).json()
    c = next(x for x in lista if x["command_id"] == cid)
    assert c["status"] == "sem_efeito" and c["concluido"] is True
    assert c["rotulo"] == "sem efeito: já estava assim" and c["detalhe"] == "já estava assim"


def test_confirmacao_tardia_nao_reabre_sem_efeito(pub):
    vent_online(pub, exaustor="desligado", modo="AUTOMATICO")
    cid = novo(pub, acao="auto")
    executar(pub, "VENT-01", cid)
    ingerir(pub, "VENT-01", "confirmacao", confirmacao("VENT-01", cid, "executado"), T0 + seg(9))
    assert cmd(cid).status == "sem_efeito"
