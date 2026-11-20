"""Regra R8 (histerese) e regra de QUEBRA."""
from sqlalchemy import select

from app import db
from app.models import Comando
from app.regras import avaliar_histerese

from conftest import (T0, confirmacao, estado_cf, estado_vent, evento, ingerir, seg, telemetria,
                      vent_online)

LIGAR, DESLIGAR, JANELA = 30.0, 26.0, 120


def serie(temp, duracao_s, fim, passo=5):
    """Leituras a cada `passo` s terminando em `fim`."""
    n = int(duracao_s // passo)
    return [(fim - seg(passo * i), temp) for i in range(n, -1, -1)]


# ---------- funcao pura ----------
def test_29_graus_nunca_liga():
    fim = T0 + seg(300)
    assert avaliar_histerese(serie(29, 300, fim), fim, False, LIGAR, DESLIGAR, JANELA) is None


def test_31_graus_por_2_min_liga():
    fim = T0 + seg(300)
    assert avaliar_histerese(serie(31, 130, fim), fim, False, LIGAR, DESLIGAR, JANELA) == "ligar"


def test_31_graus_por_menos_de_2_min_nao_liga():
    fim = T0 + seg(300)
    assert avaliar_histerese(serie(31, 60, fim), fim, False, LIGAR, DESLIGAR, JANELA) is None


def test_uma_leitura_abaixo_na_janela_impede_ligar():
    fim = T0 + seg(300)
    leituras = serie(31, 130, fim)
    leituras[len(leituras) // 2] = (leituras[len(leituras) // 2][0], 29.0)
    assert avaliar_histerese(leituras, fim, False, LIGAR, DESLIGAR, JANELA) is None


def test_27_graus_com_exaustor_ligado_mantem_histerese():
    fim = T0 + seg(300)
    assert avaliar_histerese(serie(27, 130, fim), fim, True, LIGAR, DESLIGAR, JANELA) is None


def test_25_graus_com_exaustor_ligado_desliga():
    fim = T0 + seg(300)
    assert avaliar_histerese(serie(25, 30, fim), fim, True, LIGAR, DESLIGAR, JANELA) == "desligar"


def test_limites_sao_estritos():
    fim = T0 + seg(300)
    assert avaliar_histerese(serie(30, 130, fim), fim, False, LIGAR, DESLIGAR, JANELA) is None   # >30
    assert avaliar_histerese(serie(26, 30, fim), fim, True, LIGAR, DESLIGAR, JANELA) is None     # <26


def test_dado_velho_nao_decide():
    fim = T0 + seg(300)
    assert avaliar_histerese(serie(31, 130, fim - seg(60)), fim, False, LIGAR, DESLIGAR, JANELA) is None
    assert avaliar_histerese([], fim, False, LIGAR, DESLIGAR, JANELA) is None


# ---------- integrada: telemetria -> banco -> comando ----------
def alimentar(pub, temp, de, ate, passo=5):
    t = de
    while t <= ate:
        ingerir(pub, "CF-01", "telemetria", telemetria(temp=temp, agora=t), t)
        t += seg(passo)


def comandos_exaustor():
    with db.session_scope() as s:
        return [(c.acao, c.origem, c.status) for c in s.scalars(
            select(Comando).where(Comando.comando == "exaustor").order_by(Comando.id))]


def test_ciclo_completo_29_31_27_25(pub):
    vent_online(pub)
    alimentar(pub, 29, T0, T0 + seg(200))
    assert pub.comandos("VENT-01") == []                       # 29 C: nada

    alimentar(pub, 31, T0 + seg(205), T0 + seg(205 + 110))     # 110 s acima: ainda nao
    assert pub.comandos("VENT-01") == []
    alimentar(pub, 31, T0 + seg(205 + 115), T0 + seg(205 + 130))
    cmds = pub.comandos("VENT-01", "exaustor")
    assert len(cmds) == 1
    topico, corpo = cmds[0]
    assert topico == "sentinela/cadeia-fria/VENT-01/comando/exaustor"
    assert corpo["acao"] == "ligar" and corpo["origem"] == "regra" and corpo["version"] == 1
    cid = corpo["commandId"]

    # o dispositivo executa; o estado passa a `ligado`
    t = T0 + seg(340)
    ingerir(pub, "VENT-01", "confirmacao", confirmacao("VENT-01", cid, "aceito", agora=t), t)
    ingerir(pub, "VENT-01", "confirmacao", confirmacao("VENT-01", cid, "executado", agora=t), t)
    ingerir(pub, "VENT-01", "estado", estado_vent("ligado", agora=t), t)
    assert comandos_exaustor() == [("ligar", "regra", "confirmado")]

    # 27 C com o exaustor ligado: histerese, nada novo
    alimentar(pub, 27, T0 + seg(345), T0 + seg(400))
    assert len(pub.comandos("VENT-01", "exaustor")) == 1

    # 25 C: desliga
    ingerir(pub, "CF-01", "telemetria", telemetria(temp=25, agora=T0 + seg(405)), T0 + seg(405))
    cmds = pub.comandos("VENT-01", "exaustor")
    assert len(cmds) == 2 and cmds[1][1]["acao"] == "desligar" and cmds[1][1]["origem"] == "regra"


def test_nao_empilha_comando_enquanto_ha_um_em_andamento(pub):
    vent_online(pub)
    alimentar(pub, 31, T0, T0 + seg(200))
    assert len(pub.comandos("VENT-01", "exaustor")) == 1


def test_regra_se_cala_com_vent01_em_manual(pub):
    vent_online(pub, modo="MANUAL")
    alimentar(pub, 31, T0, T0 + seg(200))
    assert pub.comandos("VENT-01") == []


def test_regra_nao_comanda_dispositivo_offline(pub):
    ingerir(pub, "VENT-01", "status", "offline")
    alimentar(pub, 31, T0, T0 + seg(200))
    assert pub.comandos("VENT-01") == []


def test_limites_editaveis_valem_na_hora(pub):
    from app.models import Regra
    vent_online(pub)
    with db.session_scope() as s:
        r = s.get(Regra, 1)
        r.temp_ligar, r.janela_s = 28.0, 30
    alimentar(pub, 29, T0, T0 + seg(40))     # 29 > 28 por 30 s
    assert len(pub.comandos("VENT-01", "exaustor")) == 1


# ---------- QUEBRA ----------
def test_quebra_liga_sinalizador_e_notifica_uma_vez(pub, avisos):
    ingerir(pub, "CF-01", "telemetria", telemetria("EXPOSTO", 31, T0), T0)
    assert avisos == [] and pub.comandos("CF-01") == []

    t = T0 + seg(5)
    ingerir(pub, "CF-01", "telemetria", telemetria("QUEBRA", 31, t, orcamento=0), t)
    cmds = pub.comandos("CF-01", "rele")
    assert len(cmds) == 1 and cmds[0][1]["acao"] == "ligar" and cmds[0][1]["origem"] == "regra"
    assert len(avisos) == 1 and "QUEBRA" in avisos[0]

    # o evento `quebra` e telemetrias seguintes nao repetem
    ingerir(pub, "CF-01", "evento", evento("CF-01", "quebra", t), t)
    ingerir(pub, "CF-01", "telemetria", telemetria("QUEBRA", 31, t + seg(5), orcamento=0), t + seg(5))
    assert len(pub.comandos("CF-01", "rele")) == 1 and len(avisos) == 1

    # reset e nova quebra: avisa de novo
    ingerir(pub, "CF-01", "evento", evento("CF-01", "reset", t + seg(10)), t + seg(10))
    ingerir(pub, "CF-01", "telemetria", telemetria("QUEBRA", 31, t + seg(20), orcamento=0), t + seg(20))
    assert len(pub.comandos("CF-01", "rele")) == 2 and len(avisos) == 2


def test_evento_quebra_sozinho_tambem_dispara(pub, avisos):
    ingerir(pub, "CF-01", "evento", evento("CF-01", "quebra"))
    assert len(pub.comandos("CF-01", "rele")) == 1 and len(avisos) == 1
