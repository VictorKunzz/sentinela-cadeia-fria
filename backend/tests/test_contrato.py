"""Validacao das mensagens contra o CONTRATOS.md v1 (R3, R4)."""
import json

import pytest

from app import contrato
from app.contrato import ContratoErro, validar

# Exemplos literais da secao 6 do CP12 v1.0.
TELEMETRIA_CP12 = {
    "version": 1, "deviceId": "CF-01", "ts": "2026-10-27T21:40:05-03:00", "horaSincronizada": True,
    "estado": "EXPOSTO",
    "temperatura": {"valor": 31.0, "unidade": "°C"},
    "umidade": {"valor": 58, "unidade": "%"},
    "orcamento": {"valor": 44.8, "unidade": "u"},
    "aberturas": 2,
    "rssi": {"valor": -67, "unidade": "dBm"},
}
CONFIRMACAO_CP12 = {
    "version": 1, "deviceId": "VENT-01", "commandId": "c-000123",
    "resultado": "executado", "motivo": None, "ts": "2026-10-27T21:41:10-03:00", "horaSincronizada": True,
}


def j(d):
    return json.dumps(d).encode()


def mudar(base, **kw):
    d = json.loads(json.dumps(base))
    for k, v in kw.items():
        if v == "__apagar__":
            d.pop(k, None)
        else:
            d[k] = v
    return d


def test_exemplos_do_cp12_sao_validos():
    t = validar("telemetria", "CF-01", j(TELEMETRIA_CP12))
    assert t.estado == "EXPOSTO" and t.temperatura.valor == 31.0
    c = validar("confirmacao", "VENT-01", j(CONFIRMACAO_CP12))
    assert c.commandId == "c-000123" and c.resultado == "executado"


def test_sensor_em_falha_temperatura_e_umidade_null_inteiros():
    """Como o firmware manda: o objeto inteiro e null (nao {"valor": null})."""
    t = validar("telemetria", "CF-01", j(mudar(TELEMETRIA_CP12, temperatura=None, umidade=None)))
    assert t.temperatura is None and t.umidade is None
    ausentes = mudar(TELEMETRIA_CP12, temperatura="__apagar__", umidade="__apagar__")
    assert validar("telemetria", "CF-01", j(ausentes)).temperatura is None
    with pytest.raises(ContratoErro):
        validar("telemetria", "CF-01", j(mudar(TELEMETRIA_CP12, temperatura={"valor": None, "unidade": "°C"})))


def test_status_texto_simples():
    assert validar("status", "CF-01", b"online") == "online"
    assert validar("status", "VENT-01", b"offline\n") == "offline"
    with pytest.raises(ContratoErro):
        validar("status", "CF-01", b"talvez")


def test_hora_nao_sincronizada_aceita_ts_nulo():
    t = validar("telemetria", "CF-01", j(mudar(TELEMETRIA_CP12, ts=None, horaSincronizada=False)))
    assert t.ts_dt() is None


@pytest.mark.parametrize(
    "corpo, trecho",
    [
        (mudar(TELEMETRIA_CP12, version=2), "version"),
        (mudar(TELEMETRIA_CP12, version="__apagar__"), "version"),
        (mudar(TELEMETRIA_CP12, temperatura={"valor": 80, "unidade": "°C"}), "faixa"),
        (mudar(TELEMETRIA_CP12, temperatura={"valor": 25, "unidade": "F"}), "unidade"),
        (mudar(TELEMETRIA_CP12, umidade={"valor": 10, "unidade": "%"}), "faixa"),
        (mudar(TELEMETRIA_CP12, aberturas="__apagar__"), "aberturas"),
        (mudar(TELEMETRIA_CP12, estado="ABERTO"), "estado"),
        (mudar(TELEMETRIA_CP12, ts=None), "ts nulo"),
        (mudar(TELEMETRIA_CP12, ts="ontem"), "ISO"),
        (mudar(TELEMETRIA_CP12, ts="2026-10-27T21:40:05"), "fuso"),
        (mudar(TELEMETRIA_CP12, deviceId="CF-02"), "deviceId"),
        (mudar(TELEMETRIA_CP12, deviceId="VENT-01"), "difere"),
    ],
)
def test_telemetria_invalida_e_rejeitada(corpo, trecho):
    with pytest.raises(ContratoErro) as exc:
        validar("telemetria", "CF-01", j(corpo))
    assert trecho in str(exc.value)


def test_json_quebrado_e_nao_objeto():
    with pytest.raises(ContratoErro, match="JSON"):
        validar("telemetria", "CF-01", b"{nao e json")
    with pytest.raises(ContratoErro, match="objeto"):
        validar("telemetria", "CF-01", b"[1,2]")
    with pytest.raises(ContratoErro, match="UTF-8"):
        validar("telemetria", "CF-01", b"\xff\xfe")


def test_nan_nao_passa():
    bruto = json.dumps(TELEMETRIA_CP12).replace('"valor": 31.0', '"valor": NaN').encode()
    with pytest.raises(ContratoErro):
        validar("telemetria", "CF-01", bruto)


def test_telemetria_so_existe_para_cf01():
    with pytest.raises(ContratoErro, match="so existe"):
        validar("telemetria", "VENT-01", j(mudar(TELEMETRIA_CP12, deviceId="VENT-01")))


def test_device_e_tipo_desconhecidos():
    with pytest.raises(ContratoErro):
        validar("telemetria", "X-9", j(TELEMETRIA_CP12))
    with pytest.raises(ContratoErro):
        validar("comando", "CF-01", b"{}")


def test_confirmacao_rejeitada_exige_motivo_do_catalogo():
    with pytest.raises(ContratoErro, match="motivo"):
        validar("confirmacao", "VENT-01", j(mudar(CONFIRMACAO_CP12, resultado="rejeitado")))
    with pytest.raises(ContratoErro):
        validar("confirmacao", "VENT-01", j(mudar(CONFIRMACAO_CP12, resultado="rejeitado", motivo="NAO_SEI")))
    for m in contrato.MOTIVOS:
        ok = validar("confirmacao", "VENT-01", j(mudar(CONFIRMACAO_CP12, resultado="rejeitado", motivo=m)))
        assert ok.motivo == m


def test_command_id_formato():
    with pytest.raises(ContratoErro):
        validar("confirmacao", "VENT-01", j(mudar(CONFIRMACAO_CP12, commandId="123")))


def test_estado_exige_atuador_do_dispositivo():
    ok = {"version": 1, "deviceId": "VENT-01", "ts": None, "horaSincronizada": False,
          "modo": "AUTOMATICO", "exaustor": "ligado"}
    assert validar("estado", "VENT-01", j(ok)).exaustor == "ligado"
    with pytest.raises(ContratoErro, match="exaustor"):
        validar("estado", "VENT-01", j(mudar(ok, exaustor="__apagar__")))
    with pytest.raises(ContratoErro):
        validar("estado", "CF-01", j(mudar(ok, deviceId="CF-01")))  # CF-01 sem rele/buzzer


def test_evento_nomes():
    ev = {"version": 1, "deviceId": "CF-01", "ts": None, "horaSincronizada": False, "evento": "sensor_falha"}
    assert validar("evento", "CF-01", j(ev)).evento == "sensor_falha"
    with pytest.raises(ContratoErro):
        validar("evento", "CF-01", j(mudar(ev, evento="SENSOR_FALHA")))
