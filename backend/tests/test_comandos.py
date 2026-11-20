"""Ciclo de comando (R7), prazos e integracao com o simulador."""
from sqlalchemy import select

from app import db
from app.comandos import criar_comando, varrer_prazos
from app.config import get_settings
from app.models import Comando, MensagemRejeitada

from conftest import PREFIXO, T0, confirmacao, estado_cf, estado_vent, ingerir, seg, vent_online

from simulador import CF01Sim, Vent01Sim  # noqa: E402  (caminho ajustado no conftest)


def novo(pub, device="VENT-01", comando="exaustor", acao="ligar", valor=None, agora=T0, origem="usuario"):
    with db.session_scope() as s:
        c = criar_comando(s, pub, device, comando, acao, valor, origem=origem, usuario="coord",
                          agora=agora, settings=get_settings())
        return c.command_id


def cmd(command_id):
    with db.session_scope() as s:
        return s.scalar(select(Comando).where(Comando.command_id == command_id))


def test_comando_publicado_no_formato_do_contrato(pub):
    cid = novo(pub, acao="ligar")
    topico, corpo = pub.msgs[-1]
    assert topico == f"{PREFIXO}/VENT-01/comando/exaustor"
    assert corpo == {"version": 1, "deviceId": "VENT-01", "commandId": cid, "origem": "usuario", "acao": "ligar"}
    assert cid.startswith("c-") and len(cid) == 8
    assert cmd(cid).status == "enviado"


def test_command_ids_sao_unicos_e_crescentes(pub):
    a, b = novo(pub), novo(pub)
    assert a != b and a < b


def test_config_leva_valor(pub):
    novo(pub, "CF-01", "config", "orcamentoInicial", 90.0)
    assert pub.msgs[-1][1]["valor"] == 90.0


def test_quatro_estados_ate_confirmado(pub):
    vent_online(pub)
    cid = novo(pub)
    assert cmd(cid).status == "enviado"
    ingerir(pub, "VENT-01", "confirmacao", confirmacao("VENT-01", cid, "aceito"), T0 + seg(1))
    assert cmd(cid).status == "recebido" and cmd(cid).resultado == "aceito"
    ingerir(pub, "VENT-01", "confirmacao", confirmacao("VENT-01", cid, "executado"), T0 + seg(2))
    assert cmd(cid).status == "executado"
    ingerir(pub, "VENT-01", "estado", estado_vent("ligado", "MANUAL", T0 + seg(3)), T0 + seg(3))
    c = cmd(cid)
    assert c.status == "confirmado"
    assert c.recebido_em and c.executado_em and c.confirmado_em


def test_estado_antigo_ou_diferente_nao_confirma(pub):
    vent_online(pub, exaustor="desligado")
    cid = novo(pub, acao="ligar", agora=T0 + seg(10))
    ingerir(pub, "VENT-01", "confirmacao", confirmacao("VENT-01", cid, "executado"), T0 + seg(11))
    ingerir(pub, "VENT-01", "estado", estado_vent("desligado"), T0 + seg(12))   # ainda desligado
    assert cmd(cid).status == "executado"


def test_rejeicao_encerra_com_motivo_e_nao_vira_nao_confirmado(pub):
    cid = novo(pub, "CF-01", "rele", "desligar")
    ingerir(pub, "CF-01", "confirmacao", confirmacao("CF-01", cid, "rejeitado", "QUEBRA_ATIVA"), T0 + seg(1))
    c = cmd(cid)
    assert (c.status, c.resultado, c.motivo) == ("recebido", "rejeitado", "QUEBRA_ATIVA")
    with db.session_scope() as s:
        assert varrer_prazos(s, T0 + seg(60), get_settings()) == 0
    assert cmd(cid).status == "recebido"


def test_sem_resposta_em_5s_vira_nao_confirmado(pub):
    cid = novo(pub)
    with db.session_scope() as s:
        assert varrer_prazos(s, T0 + seg(4), get_settings()) == 0
    with db.session_scope() as s:
        assert varrer_prazos(s, T0 + seg(6), get_settings()) == 1
    assert cmd(cid).status == "nao_confirmado"


def test_aceito_mas_sem_executar_vence_em_15s(pub):
    cid = novo(pub)
    ingerir(pub, "VENT-01", "confirmacao", confirmacao("VENT-01", cid, "aceito"), T0 + seg(1))
    with db.session_scope() as s:
        assert varrer_prazos(s, T0 + seg(10), get_settings()) == 0
    with db.session_scope() as s:
        assert varrer_prazos(s, T0 + seg(16), get_settings()) == 1
    assert cmd(cid).status == "nao_confirmado"


def test_broker_fora_marca_nao_confirmado_na_hora(pub):
    pub.conectado = False
    pub.publicar = lambda *a, **k: False
    cid = novo(pub)
    c = cmd(cid)
    assert c.status == "nao_confirmado" and "broker" in c.detalhe


def test_confirmacao_de_comando_desconhecido_e_registrada(pub):
    ingerir(pub, "VENT-01", "confirmacao", confirmacao("VENT-01", "c-999999", "aceito"))
    with db.session_scope() as s:
        r = s.scalars(select(MensagemRejeitada)).all()
    assert len(r) == 1 and "desconhecido" in r[0].motivo


def test_confirmacao_de_outro_dispositivo_e_rejeitada(pub):
    cid = novo(pub, "VENT-01")
    ingerir(pub, "CF-01", "confirmacao", confirmacao("CF-01", cid, "aceito"))
    assert cmd(cid).status == "enviado"


# ---------- com o simulador fechando o laco ----------
def laco(pub, sim, device, ate_n=1, agora=T0):
    """Entrega ao simulador os comandos que o backend publicou e devolve as respostas ao backend."""
    for topico, corpo in pub.comandos(device)[-ate_n:]:
        comando = topico.rsplit("/", 1)[-1]
        for tipo, payload, _ in sim.on_command(comando, __import__("json").dumps(corpo).encode(), agora.timestamp()):
            ingerir(pub, device, tipo, payload, agora + seg(1))


def test_ciclo_com_simulador_vent01(pub):
    sim = Vent01Sim()
    for tipo, payload, _ in sim.conectar(T0.timestamp()):
        ingerir(pub, "VENT-01", tipo, payload)
    cid = novo(pub, acao="ligar", agora=T0 + seg(1))
    laco(pub, sim, "VENT-01", agora=T0 + seg(1))
    assert cmd(cid).status == "confirmado" and sim.exaustor is True


def test_command_id_duplicado_e_rejeitado_pelo_dispositivo(pub):
    sim = Vent01Sim()
    for tipo, payload, _ in sim.conectar(T0.timestamp()):
        ingerir(pub, "VENT-01", tipo, payload)
    cid = novo(pub, acao="ligar", agora=T0 + seg(1))
    laco(pub, sim, "VENT-01", agora=T0 + seg(1))
    assert cmd(cid).status == "confirmado"

    # o mesmo commandId reenviado (retransmissao): o dispositivo recusa e nao executa de novo
    topico, corpo = pub.comandos("VENT-01")[-1]
    saida = sim.on_command("exaustor", __import__("json").dumps(corpo).encode(), (T0 + seg(5)).timestamp())
    assert len(saida) == 1
    conf = __import__("json").loads(saida[0][1])
    assert conf["resultado"] == "rejeitado" and conf["motivo"] == "DUPLICADO"
    ingerir(pub, "VENT-01", "confirmacao", saida[0][1], T0 + seg(6))
    assert cmd(cid).status == "confirmado"  # o registro nao regride


def test_intertravamento_quebra_ativa_com_simulador(pub):
    sim = CF01Sim(velocidade=1000)
    t = T0.timestamp()
    for tipo, payload, _ in sim.conectar(t):
        ingerir(pub, "CF-01", tipo, payload)
    sim.definir(t, temperatura=40, tampa="aberta")
    for i in range(1, 4):
        for tipo, payload, _ in sim.tick(t + i):
            ingerir(pub, "CF-01", tipo, payload, T0 + seg(i))
    assert sim.estado == "QUEBRA"
    cid = novo(pub, "CF-01", "rele", "desligar", agora=T0 + seg(5))
    laco(pub, sim, "CF-01", agora=T0 + seg(5))
    c = cmd(cid)
    assert (c.status, c.motivo) == ("recebido", "QUEBRA_ATIVA")
