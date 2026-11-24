"""Assinante: valida, grava ou rejeita; presenca."""
from sqlalchemy import func, select

from app import db
from app.models import Dispositivo, Evento, Medicao, MensagemRejeitada

from conftest import PREFIXO, T0, estado_vent, evento, ingerir, seg, telemetria


def rejeitadas():
    with db.session_scope() as s:
        return s.scalars(select(MensagemRejeitada).order_by(MensagemRejeitada.id)).all()


def test_telemetria_valida_vai_ao_banco(pub):
    assert ingerir(pub, "CF-01", "telemetria", telemetria("EXPOSTO", 31.2)) == "ok"
    with db.session_scope() as s:
        grandezas = {m.grandeza: (m.valor, m.unidade) for m in s.scalars(select(Medicao))}
        d = s.get(Dispositivo, "CF-01")
        assert grandezas["temperatura"] == (31.2, "°C")
        assert grandezas["umidade"] == (55.0, "%")
        assert set(grandezas) == {"temperatura", "umidade", "orcamento", "rssi"}
        assert d.estado_maquina == "EXPOSTO" and d.telemetria["temperatura"]["valor"] == 31.2
        assert d.ultimo_contato is not None
    assert rejeitadas() == []


def test_sensor_ausente_nao_grava_medicao_nula(pub):
    ingerir(pub, "CF-01", "telemetria", telemetria(temp=None))
    with db.session_scope() as s:
        gr = {m.grandeza for m in s.scalars(select(Medicao))}
    assert "temperatura" not in gr and "umidade" not in gr and "orcamento" in gr


def test_json_invalido_cai_em_mensagens_rejeitadas(pub):
    assert ingerir(pub, "CF-01", "telemetria", b"{isto nao e json") == "rejeitada"
    r = rejeitadas()
    assert len(r) == 1
    assert r[0].topico == f"{PREFIXO}/CF-01/telemetria"
    assert "{isto nao e json" in r[0].payload and "JSON" in r[0].motivo
    with db.session_scope() as s:
        assert s.scalar(select(func.count()).select_from(Medicao)) == 0


def test_fora_da_faixa_e_deviceid_trocado_sao_rejeitados(pub):
    ingerir(pub, "CF-01", "telemetria", telemetria(temp=99.0))
    outra = telemetria()
    outra["deviceId"] = "VENT-01"
    ingerir(pub, "CF-01", "telemetria", outra)
    motivos = [r.motivo for r in rejeitadas()]
    assert len(motivos) == 2 and "faixa" in motivos[0] and "difere" in motivos[1]


def test_topico_fora_do_contrato(pub):
    with db.session_scope() as s:
        from app.ingest import processar
        assert processar(s, pub, "outro/prefixo/CF-01/telemetria", b"{}", agora=T0) == "rejeitada"
        assert processar(s, pub, f"{PREFIXO}/CF-01/comando/rele", b"{}", agora=T0) == "rejeitada"
        assert processar(s, pub, f"{PREFIXO}/XX-99/status", b"online", agora=T0) == "rejeitada"
    assert len(rejeitadas()) == 3


def test_presenca_online_offline_e_aviso_so_na_transicao(pub, avisos):
    ingerir(pub, "CF-01", "status", "online", T0)
    with db.session_scope() as s:
        d = s.get(Dispositivo, "CF-01")
        assert d.online and d.ultimo_contato is not None
    assert avisos == []
    ingerir(pub, "CF-01", "status", "offline", T0 + seg(60))
    ingerir(pub, "CF-01", "status", "offline", T0 + seg(61))  # LWT repetido: sem novo aviso
    with db.session_scope() as s:
        assert not s.get(Dispositivo, "CF-01").online
    assert len(avisos) == 1 and "CF-01" in avisos[0]


def test_evento_e_estado_atualizam_o_dispositivo(pub):
    ingerir(pub, "CF-01", "evento", evento("CF-01", "abertura", n=1))
    ingerir(pub, "VENT-01", "estado", estado_vent("ligado", "MANUAL"))
    with db.session_scope() as s:
        assert s.get(Dispositivo, "CF-01").estado_maquina == "EXPOSTO"
        v = s.get(Dispositivo, "VENT-01")
        assert v.estado["exaustor"] == "ligado" and v.modo == "MANUAL"
        assert s.scalar(select(func.count()).select_from(Evento)) == 1


def test_hora_nao_sincronizada_usa_hora_de_recebimento(pub):
    t = telemetria()
    t["ts"], t["horaSincronizada"] = None, False
    assert ingerir(pub, "CF-01", "telemetria", t, T0) == "ok"
    with db.session_scope() as s:
        m = s.scalars(select(Medicao)).first()
        assert m.ts.replace(tzinfo=None) == T0.replace(tzinfo=None)
