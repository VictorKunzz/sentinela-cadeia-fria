"""API REST: login, perfis (R9/R16), comandos, historico, regras, alertas, indicadores."""
import pytest
from fastapi.testclient import TestClient

from app.main import app

from conftest import T0, confirmacao, estado_vent, evento, ingerir, seg, telemetria, vent_online


@pytest.fixture
def client(pub):
    return TestClient(app)


def token(client, user, senha):
    r = client.post("/login", json={"username": user, "password": senha})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def coord(client):
    return token(client, "coord", "senha-coord")


@pytest.fixture
def tec(client):
    return token(client, "tec", "senha-tec")


def test_login_ok_e_perfil(client):
    r = client.post("/login", json={"username": "coord", "password": "senha-coord"})
    corpo = r.json()
    assert r.status_code == 200 and corpo["perfil"] == "coordenacao" and corpo["token_type"] == "bearer"
    assert client.post("/login", json={"username": "tec", "password": "senha-tec"}).json()["perfil"] == "tecnico"


def test_semente_acompanha_mudanca_de_senha_do_env(client, monkeypatch):
    """Regressao (21/11): trocar a senha no .env deixava o hash antigo no banco
    (o semear so criava), e o login novo falhava ate editar o banco na mao."""
    from app import config, db, security

    monkeypatch.setenv("SEED_COORDENACAO_PASSWORD", "senha-nova")
    config.get_settings.cache_clear()
    with db.session_scope() as s:
        security.semear_usuarios(s)
    try:
        ok = client.post("/login", json={"username": "coord", "password": "senha-nova"})
        antiga = client.post("/login", json={"username": "coord", "password": "senha-coord"})
        assert ok.status_code == 200 and antiga.status_code == 401
    finally:
        monkeypatch.undo()
        config.get_settings.cache_clear()


@pytest.mark.parametrize("u,s", [("coord", "errada"), ("naoexiste", "x"), ("", "")])
def test_login_invalido_401(client, u, s):
    assert client.post("/login", json={"username": u, "password": s}).status_code == 401


@pytest.mark.parametrize("metodo,rota", [
    ("get", "/dispositivos"), ("get", "/dispositivos/CF-01/estado"), ("get", "/dispositivos/CF-01/historico"),
    ("get", "/comandos/c-000001"), ("get", "/regras"), ("get", "/alertas"), ("get", "/indicadores"),
    ("post", "/dispositivos/VENT-01/comandos"), ("put", "/regras"),
])
def test_sem_token_401(client, metodo, rota):
    assert getattr(client, metodo)(rota).status_code == 401


def test_token_invalido_401(client):
    assert client.get("/dispositivos", headers={"Authorization": "Bearer lixo"}).status_code == 401


def test_tecnico_so_le_comando_403(client, tec, pub):
    corpo = {"comando": "exaustor", "acao": "ligar"}
    assert client.post("/dispositivos/VENT-01/comandos", json=corpo, headers=tec).status_code == 403
    assert pub.msgs == []                                   # nada foi publicado
    assert client.get("/dispositivos", headers=tec).status_code == 200


def test_tecnico_nao_altera_regras(client, tec, coord):
    corpo = {"temp_ligar": 32, "temp_desligar": 27, "janela_s": 60, "ativa": True}
    assert client.put("/regras", json=corpo, headers=tec).status_code == 403
    assert client.get("/regras", headers=tec).json()["temp_ligar"] == 30.0
    r = client.put("/regras", json=corpo, headers=coord)
    assert r.status_code == 200 and r.json()["temp_ligar"] == 32 and r.json()["atualizado_em"]
    assert client.get("/regras", headers=tec).json()["janela_s"] == 60


def test_regras_exigem_histerese(client, coord):
    r = client.put("/regras", json={"temp_ligar": 25, "temp_desligar": 26, "janela_s": 60, "ativa": True}, headers=coord)
    assert r.status_code == 422


def test_coordenacao_comanda_e_acompanha_o_ciclo(client, coord, pub):
    vent_online(pub)
    r = client.post("/dispositivos/VENT-01/comandos", json={"comando": "exaustor", "acao": "ligar"}, headers=coord)
    assert r.status_code == 202
    c = r.json()
    assert c["status"] == "enviado" and c["origem"] == "usuario" and c["usuario"] == "coord"
    assert c["rotulo"] == "aguardando" and c["concluido"] is False
    assert pub.comandos("VENT-01", "exaustor")[0][1]["commandId"] == c["command_id"]

    cid = c["command_id"]
    ingerir(pub, "VENT-01", "confirmacao", confirmacao("VENT-01", cid, "aceito", agora=T0 + seg(1)), T0 + seg(1))
    assert client.get(f"/comandos/{cid}", headers=coord).json()["status"] == "recebido"
    ingerir(pub, "VENT-01", "confirmacao", confirmacao("VENT-01", cid, "executado"), T0 + seg(2))
    ingerir(pub, "VENT-01", "estado", estado_vent("ligado", "MANUAL"), T0 + seg(3))
    final = client.get(f"/comandos/{cid}", headers=coord).json()
    # o relogio do teste e T0; o do servidor e "agora": usa-se o proprio retorno para o rotulo
    assert final["status"] in ("confirmado", "executado")
    lista = client.get("/comandos", headers=coord).json()
    assert lista[0]["command_id"] == cid


def test_comando_rejeitado_aparece_com_motivo(client, coord, pub):
    r = client.post("/dispositivos/CF-01/comandos", json={"comando": "reset", "acao": "reset"}, headers=coord)
    cid = r.json()["command_id"]
    ingerir(pub, "CF-01", "confirmacao", confirmacao("CF-01", cid, "rejeitado", "SEM_QUEBRA"))
    c = client.get(f"/comandos/{cid}", headers=coord).json()
    assert c["rotulo"] == "rejeitado: SEM_QUEBRA" and c["concluido"] is True and c["motivo"] == "SEM_QUEBRA"


def test_comando_invalido_para_o_dispositivo_422(client, coord):
    assert client.post("/dispositivos/VENT-01/comandos", json={"comando": "reset", "acao": "reset"}, headers=coord).status_code == 422
    assert client.post("/dispositivos/NADA/comandos", json={"comando": "x", "acao": "y"}, headers=coord).status_code == 404
    assert client.post("/dispositivos/VENT-01/comandos", json={"comando": "exaustor"}, headers=coord).status_code == 422


def test_acao_invalida_segue_para_o_dispositivo_decidir(client, coord, pub):
    r = client.post("/dispositivos/VENT-01/comandos", json={"comando": "exaustor", "acao": "explodir"}, headers=coord)
    assert r.status_code == 202 and pub.comandos("VENT-01")[-1][1]["acao"] == "explodir"


def test_dispositivos_e_estado(client, tec, pub):
    ingerir(pub, "CF-01", "status", "online")
    ingerir(pub, "CF-01", "telemetria", telemetria("EXPOSTO", 31.2, orcamento=44.8, aberturas=2))
    ingerir(pub, "VENT-01", "status", "online")
    ingerir(pub, "VENT-01", "estado", estado_vent("ligado", "MANUAL"))
    lista = client.get("/dispositivos", headers=tec).json()
    assert [d["id"] for d in lista] == ["CF-01", "VENT-01"]
    cf, vent = lista
    assert cf["online"] and cf["estado"] == "EXPOSTO" and cf["modo"] == "AUTOMATICO"
    assert cf["temperatura"] == {"valor": 31.2, "unidade": "°C"} and cf["orcamento"]["valor"] == 44.8
    assert cf["aberturas"] == 2 and cf["ultimo_contato"]
    assert vent["atuadores"] == {"exaustor": "ligado"} and vent["modo"] == "MANUAL" and vent["temperatura"] is None
    assert client.get("/dispositivos/CF-01/estado", headers=tec).json()["id"] == "CF-01"
    assert client.get("/dispositivos/NADA/estado", headers=tec).status_code == 404


def test_historico_com_media_movel(client, tec, pub):
    from datetime import datetime, timezone
    agora = datetime.now(timezone.utc)
    for i, v in enumerate([20, 22, 24, 26]):
        t = agora - seg(60 - i * 10)
        ingerir(pub, "CF-01", "telemetria", telemetria(temp=v, agora=t), t)
    r = client.get("/dispositivos/CF-01/historico?grandeza=temperatura&janela=2", headers=tec).json()
    assert r["unidade"] == "°C" and r["janela_media"] == 2
    assert [p["valor"] for p in r["pontos"]] == [20, 22, 24, 26]
    assert [p["media_movel"] for p in r["pontos"]] == [20, 21, 23, 25]
    assert client.get("/dispositivos/CF-01/historico?grandeza=pressao", headers=tec).status_code == 422


def test_alertas(client, tec, pub):
    assert {a["tipo"] for a in client.get("/alertas", headers=tec).json()} == {"offline"}   # nunca deram sinal
    ingerir(pub, "CF-01", "status", "online")
    ingerir(pub, "VENT-01", "status", "online")
    assert client.get("/alertas", headers=tec).json() == []
    ingerir(pub, "CF-01", "evento", evento("CF-01", "quebra"))
    ingerir(pub, "CF-01", "telemetria", telemetria("QUEBRA", 31, orcamento=0))
    ingerir(pub, "VENT-01", "status", "offline")
    tipos = {(a["tipo"], a["dispositivo"], a["severidade"]) for a in client.get("/alertas", headers=tec).json()}
    assert ("quebra", "CF-01", "critico") in tipos and ("offline", "VENT-01", "critico") in tipos


def test_indicadores(client, tec, pub):
    from datetime import datetime, timezone
    t = datetime.now(timezone.utc) - seg(600)
    ingerir(pub, "CF-01", "evento", evento("CF-01", "abertura", t, n=1), t)
    ingerir(pub, "CF-01", "evento", evento("CF-01", "fechamento", t + seg(40), n=1,
                                           duracao={"valor": 40, "unidade": "s"}), t + seg(40))
    ingerir(pub, "CF-01", "evento", evento("CF-01", "abertura", t + seg(100), n=2), t + seg(100))
    ingerir(pub, "CF-01", "evento", evento("CF-01", "quebra", t + seg(160), n=2), t + seg(160))
    ingerir(pub, "CF-01", "evento", evento("CF-01", "reset", t + seg(220)), t + seg(220))
    r = client.get("/indicadores?dispositivo=CF-01", headers=tec).json()
    assert r["aberturas"] == 2 and r["quebras"] == 1
    assert r["tempo_exposicao_s"] == pytest.approx(40 + 60, abs=1)      # 40 s medidos + 60 s ate a quebra
    assert r["tempo_quebra_s"] == pytest.approx(60, abs=1)
    assert sum(r["aberturas_por_turno"].values()) == 2
    assert client.get("/indicadores?dispositivo=XX", headers=tec).status_code == 404
