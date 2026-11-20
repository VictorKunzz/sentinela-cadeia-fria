"""O simulador precisa falar exatamente o contrato: toda mensagem dele passa pelo validador do backend."""
import json

from app.contrato import validar

from simulador import CF01Sim, Vent01Sim

T = 1_800_000_000.0


def checar(device, msgs):
    """Valida cada mensagem produzida contra o contrato; devolve (tipo, objeto) para inspecao."""
    saida = []
    for tipo, payload, retain in msgs:
        obj = validar(tipo, device, payload.encode())
        saida.append((tipo, obj))
        if tipo in ("status", "estado"):
            assert retain, f"{tipo} deve ser retido"
        else:
            assert not retain, f"{tipo} nao deve ser retido"
    return saida


def cmd(cid, acao, origem="usuario", **extra):
    return json.dumps({"version": 1, "deviceId": "x", "commandId": cid, "origem": origem, "acao": acao, **extra}).encode()


def confs(msgs):
    return [(o.resultado, o.motivo) for t, o in msgs if t == "confirmacao"]


def abrir_ate_quebra(cf, t=T):
    cf.definir(t, temperatura=40, tampa="aberta")
    for i in range(1, 6):
        yield t + i, cf.tick(t + i)


def test_mensagens_do_simulador_seguem_o_contrato():
    cf, vent = CF01Sim(velocidade=50), Vent01Sim()
    checar("CF-01", cf.conectar(T))
    checar("VENT-01", vent.conectar(T))
    checar("CF-01", cf.definir(T, temperatura=35, tampa="aberta"))
    for agora, msgs in abrir_ate_quebra(cf):
        checar("CF-01", msgs)
    assert cf.estado == "QUEBRA"
    checar("CF-01", cf.on_command("reset", cmd("c-000001", "reset"), T + 10))
    checar("VENT-01", vent.on_command("exaustor", cmd("c-000002", "ligar"), T))


def test_telemetria_a_cada_5s_e_com_sensor_em_falha_manda_null_inteiro():
    cf = CF01Sim()
    cf.tick(T)
    tele = [m for m in cf.tick(T + 5) if m[0] == "telemetria"]
    assert len(tele) == 1
    cf.definir(T + 6, sensor="falha")
    corpo = json.loads(cf.telemetria_msg(T + 10)[1])
    assert corpo["temperatura"] is None and corpo["umidade"] is None   # objeto inteiro null
    checar("CF-01", [cf.telemetria_msg(T + 10)])


def test_abertura_fechamento_e_quebra_por_orcamento():
    cf = CF01Sim(velocidade=40)
    ev = [o.evento for t, o in checar("CF-01", cf.definir(T, temperatura=30, tampa="aberta")) if t == "evento"]
    assert ev == ["abertura"] and cf.estado == "EXPOSTO"
    cf.tick(T)
    ev = []
    for i in range(1, 5):
        ev += [o.evento for t, o in checar("CF-01", cf.tick(T + i)) if t == "evento"]
    assert "quebra" in ev and cf.estado == "QUEBRA" and cf.orcamento == 0 and cf.buzzer


def test_fechamento_publica_duracao_e_consumo():
    cf = CF01Sim()
    cf.definir(T, temperatura=30, tampa="aberta")
    cf.tick(T)
    for i in range(1, 11):
        cf.tick(T + i)
    msgs = checar("CF-01", cf.definir(T + 10, tampa="fechada"))
    fech = [o for t, o in msgs if t == "evento"][0]
    assert fech.evento == "fechamento" and fech.duracao.valor == 10 and fech.consumo.valor > 0


def test_intertravamentos_e_faixa():
    cf = CF01Sim(velocidade=100)
    # reset sem QUEBRA
    assert confs(checar("CF-01", cf.on_command("reset", cmd("c-000001", "reset"), T))) == [("rejeitado", "SEM_QUEBRA")]
    # config fora da faixa / sem valor
    assert confs(checar("CF-01", cf.on_command("config", cmd("c-000002", "orcamentoInicial", valor=10), T))) == [("rejeitado", "FORA_DA_FAIXA")]
    assert confs(checar("CF-01", cf.on_command("config", cmd("c-000003", "orcamentoInicial"), T))) == [("rejeitado", "ACAO_INVALIDA")]
    ok = checar("CF-01", cf.on_command("config", cmd("c-000004", "orcamentoInicial", valor=90), T))
    assert confs(ok) == [("aceito", None), ("executado", None)] and cf.orcamento_ini == 90
    # acao invalida / comando desconhecido
    assert confs(checar("CF-01", cf.on_command("rele", cmd("c-000005", "explodir"), T))) == [("rejeitado", "ACAO_INVALIDA")]
    assert confs(checar("CF-01", cf.on_command("exaustor", cmd("c-000006", "ligar"), T))) == [("rejeitado", "ACAO_INVALIDA")]
    # QUEBRA: nao desliga o sinalizador, reset libera
    list(abrir_ate_quebra(cf))
    assert cf.estado == "QUEBRA"
    assert confs(checar("CF-01", cf.on_command("rele", cmd("c-000007", "desligar"), T + 9))) == [("rejeitado", "QUEBRA_ATIVA")]
    r = checar("CF-01", cf.on_command("reset", cmd("c-000008", "reset"), T + 9))
    assert confs(r) == [("aceito", None), ("executado", None)] and cf.estado == "FECHADO"
    assert "reset" in [o.evento for t, o in r if t == "evento"]


def test_comando_duplicado_nao_executa_de_novo():
    v = Vent01Sim()
    assert confs(checar("VENT-01", v.on_command("exaustor", cmd("c-000010", "ligar"), T)))[-1] == ("executado", None)
    v.exaustor = False
    assert confs(checar("VENT-01", v.on_command("exaustor", cmd("c-000010", "ligar"), T + 1))) == [("rejeitado", "DUPLICADO")]
    assert v.exaustor is False


def test_so_os_ultimos_10_command_ids_sao_lembrados():
    v = Vent01Sim()
    for i in range(11):
        v.on_command("exaustor", cmd(f"c-{i:06d}", "desligar"), T)
    esquecido = checar("VENT-01", v.on_command("exaustor", cmd("c-000000", "desligar"), T))
    assert confs(esquecido)[-1] == ("executado", None)
    recente = checar("VENT-01", v.on_command("exaustor", cmd("c-000010", "desligar"), T))
    assert confs(recente) == [("rejeitado", "DUPLICADO")]


def test_manual_por_usuario_volta_em_10_min_ou_por_auto():
    v = Vent01Sim()
    checar("VENT-01", v.on_command("exaustor", cmd("c-000020", "ligar"), T))
    assert v.modo == "MANUAL"
    assert v.tick(T + 599) == [] and v.modo == "MANUAL"
    msgs = checar("VENT-01", v.tick(T + 601))
    assert v.modo == "AUTOMATICO" and v.exaustor is True and any(o.evento == "modo_alterado" for t, o in msgs if t == "evento")
    # por comando auto
    checar("VENT-01", v.on_command("exaustor", cmd("c-000021", "desligar"), T + 700))
    assert v.modo == "MANUAL"
    checar("VENT-01", v.on_command("exaustor", cmd("c-000022", "auto"), T + 710))
    assert v.modo == "AUTOMATICO"


def test_comando_de_regra_nao_muda_modo_e_e_rejeitado_em_manual():
    v = Vent01Sim()
    checar("VENT-01", v.on_command("exaustor", cmd("c-000030", "ligar", origem="regra"), T))
    assert v.modo == "AUTOMATICO" and v.exaustor
    checar("VENT-01", v.on_command("exaustor", cmd("c-000031", "desligar", origem="usuario"), T + 1))
    assert v.modo == "MANUAL"
    r = checar("VENT-01", v.on_command("exaustor", cmd("c-000032", "ligar", origem="regra"), T + 2))
    assert confs(r) == [("rejeitado", "ACAO_INVALIDA")] and v.exaustor is False


def test_comando_sem_origem_vale_como_usuario():
    v = Vent01Sim()
    bruto = json.dumps({"version": 1, "commandId": "c-000040", "acao": "ligar"}).encode()
    v.on_command("exaustor", bruto, T)
    assert v.modo == "MANUAL"


def test_cf01_seguro_apos_3_leituras_invalidas_e_sai_com_2_validas():
    cf = CF01Sim()
    cf.definir(T, sensor="falha")
    eventos, t = [], T
    for _ in range(8):
        t += 1
        eventos += [o.evento for tp, o in checar("CF-01", cf.tick(t)) if tp == "evento"]
    assert cf.seguro and cf.modo == "SEGURO" and eventos.count("sensor_falha") == 1
    cf.definir(t, sensor="ok")
    sai = []
    for _ in range(8):
        t += 1
        sai += [o.evento for tp, o in checar("CF-01", cf.tick(t)) if tp == "evento"]
    assert not cf.seguro and cf.modo == "AUTOMATICO" and "sensor_ok" in sai


def test_seguro_congela_o_orcamento():
    cf = CF01Sim()
    cf.definir(T, temperatura=35, tampa="aberta")
    cf.tick(T)
    cf.tick(T + 1)
    cf.definir(T + 1, sensor="falha")
    for i in range(2, 12):
        cf.tick(T + i)
    congelado = cf.orcamento
    for i in range(12, 20):
        cf.tick(T + i)
    assert cf.seguro and cf.orcamento == congelado


def test_vent01_desliga_apos_15_min_ligada_sem_mqtt():
    v = Vent01Sim()
    v.on_command("exaustor", cmd("c-000050", "ligar", origem="regra"), T)
    v.perdeu_conexao(T + 10)
    assert v.tick(T + 10 + 899) == [] and v.exaustor
    msgs = checar("VENT-01", v.tick(T + 10 + 901))
    assert v.modo == "SEGURO" and v.exaustor is False and msgs
    voltou = checar("VENT-01", v.conectar(T + 2000))
    assert v.modo == "AUTOMATICO" and voltou[0][0] == "status"


def test_vent01_desligada_no_boot_e_so_publica_o_proprio_estado():
    v = Vent01Sim()
    msgs = checar("VENT-01", v.conectar(T))
    assert v.exaustor is False
    assert [t for t, _ in msgs] == ["status", "evento", "estado"]   # sem telemetria
    estado = [o for t, o in msgs if t == "estado"][0]
    assert estado.exaustor == "desligado" and estado.modo == "AUTOMATICO"


def test_hora_nao_sincronizada_manda_ts_nulo():
    cf = CF01Sim(sincronizada=False)
    obj = checar("CF-01", [cf.telemetria_msg(T)])[0][1]
    assert obj.ts is None and obj.horaSincronizada is False
