#!/usr/bin/env python3
"""Simulador de dispositivos do Sentinela (CF-01 e VENT-01) pelo CONTRATOS.md v1.

Serve para testar o backend sem hardware e como teste de integracao no CI.
A logica fica em classes puras (`CF01Sim`, `Vent01Sim`): recebem o tempo `now`
(epoch, segundos) e devolvem listas de mensagens `(tipo, payload, retain)`;
o `Executor` so liga isso ao MQTT. Assim os testes rodam sem broker.

Uso (com o compose no ar):
    python simulador.py --host localhost --porta 1883
Senhas dos dispositivos: --senha-cf01/--senha-vent01 ou as variaveis
MQTT_PASS_CF01 / MQTT_PASS_VENT01 (as mesmas do .env). Sem senha, conecta anonimo.

Controle ao vivo (CF-01): edite o arquivo dado em --controle, por exemplo
    {"temperatura": 31.5, "umidade": 58, "tampa": "aberta", "sensor": "ok"}
"tampa": "aberta"|"fechada"; "sensor": "ok"|"falha".
"""
import argparse
import json
import os
import sys
import threading
import time
from collections import deque
from datetime import datetime

MOTIVOS = ("QUEBRA_ATIVA", "SEM_QUEBRA", "DUPLICADO", "ACAO_INVALIDA", "FORA_DA_FAIXA")
MANUAL_S = 600       # modo MANUAL volta ao automatico em 10 min
SEGURO_VENT_S = 900  # VENT-01: ligada 15 min sem MQTT -> desliga e entra em SEGURO
INTERVALO_TELEMETRIA_S = 5
INTERVALO_LEITURA_S = 2


class Sim:
    """Parte comum: identidade, carimbo de tempo, comandos duplicados e modo MANUAL."""

    device_id = ""
    comandos: dict[str, tuple] = {}

    def __init__(self, sincronizada: bool = True):
        self.sincronizada = sincronizada
        self.modo = "AUTOMATICO"
        self.manual_ate: float | None = None
        self.vistos: deque[str] = deque(maxlen=10)

    # ---- montagem de mensagens ----
    def _ts(self, now: float) -> str | None:
        if not self.sincronizada:
            return None
        return datetime.fromtimestamp(now).astimezone().isoformat(timespec="seconds")

    def _msg(self, tipo: str, corpo: dict, now: float, retain: bool = False):
        base = {"version": 1, "deviceId": self.device_id, "ts": self._ts(now), "horaSincronizada": self.sincronizada}
        base.update(corpo)
        return (tipo, json.dumps(base, ensure_ascii=False), retain)

    def _evento(self, now: float, evento: str, **extra):
        corpo = {"evento": evento, "n": None, "duracao": None, "temperaturaMedia": None,
                 "consumo": None, "orcamento": None, "detalhe": None}
        corpo.update(extra)
        return self._msg("evento", corpo, now)

    def _conf(self, now: float, command_id: str, resultado: str, motivo=None, detalhe=None):
        assert motivo is None or motivo in MOTIVOS
        return self._msg("confirmacao", {"commandId": command_id, "resultado": resultado,
                                         "motivo": motivo, "detalhe": detalhe}, now)

    # ---- a implementar ----
    def estado_msg(self, now: float):
        raise NotImplementedError

    def _aplicar(self, comando: str, acao: str, dados: dict, now: float) -> list:
        raise NotImplementedError

    def _intertravamento(self, comando: str, acao: str, dados: dict):
        """Devolve (motivo, detalhe) se a regra do dispositivo rejeita, senao None."""
        return None

    # ---- ciclo comum ----
    def _entrar_manual(self, now: float) -> list:
        if self.modo == "MANUAL":
            self.manual_ate = now + MANUAL_S
            return []
        self.modo = "MANUAL"
        self.manual_ate = now + MANUAL_S
        return [self._evento(now, "modo_alterado", detalhe="AUTOMATICO->MANUAL"), self.estado_msg(now)]

    def _voltar_automatico(self, now: float, de: str) -> list:
        self.modo = "AUTOMATICO"
        self.manual_ate = None
        return [self._evento(now, "modo_alterado", detalhe=f"{de}->AUTOMATICO"), self.estado_msg(now)]

    def _tick_manual(self, now: float) -> list:
        if self.modo == "MANUAL" and self.manual_ate is not None and now >= self.manual_ate:
            return self._voltar_automatico(now, "MANUAL")
        return []

    def on_command(self, comando: str, bruto: bytes, now: float) -> list:
        try:
            dados = json.loads(bruto.decode("utf-8"))
            cid = dados["commandId"]
            if not isinstance(dados, dict) or not isinstance(cid, str):
                raise ValueError
        except Exception:
            return []  # sem commandId nao ha a quem responder

        if cid in self.vistos:
            return [self._conf(now, cid, "rejeitado", "DUPLICADO", "commandId repetido")]
        self.vistos.append(cid)

        acao = dados.get("acao")
        validas = self.comandos.get(comando)
        if validas is None:
            return [self._conf(now, cid, "rejeitado", "ACAO_INVALIDA", f"comando desconhecido: {comando}")]
        if acao not in validas:
            return [self._conf(now, cid, "rejeitado", "ACAO_INVALIDA", f"acao invalida para {comando}")]

        origem = dados.get("origem", "usuario")
        if origem == "regra" and self.modo == "MANUAL":
            return [self._conf(now, cid, "rejeitado", "ACAO_INVALIDA", "modo manual")]

        rej = self._intertravamento(comando, acao, dados)
        if rej:
            return [self._conf(now, cid, "rejeitado", rej[0], rej[1])]

        saida = [self._conf(now, cid, "aceito")]
        saida += self._aplicar(comando, acao, dados, now)
        # So comandos de ATUADOR levam ao MANUAL; reset e config nao (ver nota no relatorio).
        if comando in ("rele", "buzzer", "exaustor"):
            if acao == "auto":
                if self.modo == "MANUAL":
                    saida += self._voltar_automatico(now, "MANUAL")
            elif origem == "usuario":
                saida += self._entrar_manual(now)
        saida.append(self._conf(now, cid, "executado"))
        saida.append(self.estado_msg(now))  # estado retido logo apos executar (CONTRATOS.md, secao 5)
        return saida


class CF01Sim(Sim):
    device_id = "CF-01"
    comandos = {
        "rele": ("ligar", "desligar", "auto"),
        "buzzer": ("disparar", "silenciar", "auto"),
        "reset": ("reset",),
        "config": ("orcamentoInicial",),
    }

    def __init__(self, sincronizada: bool = True, velocidade: float = 1.0, temperatura: float = 24.0):
        super().__init__(sincronizada)
        self.velocidade = velocidade
        self.temp = temperatura
        self.umid = 55.0
        self.estado = "FECHADO"
        self.orcamento_ini = 120.0
        self.orcamento = 120.0
        self.aberturas = 0
        self.tampa_aberta = False
        self.sensor_ok = True
        self.rele = False
        self.buzzer = False
        self.seguro = False
        self.invalidas = 0
        self.validas = 0
        self._ultima_leitura = 0.0
        self._ultima_tele = 0.0
        self._ultimo_tick: float | None = None
        self._abertura_ts = 0.0
        self._soma_t = 0.0
        self._amostras = 0
        self._orc_abertura = 120.0

    # ---- mensagens ----
    def estado_msg(self, now: float):
        return self._msg("estado", {"modo": self.modo, "rele": "ligado" if self.rele else "desligado",
                                    "buzzer": "ligado" if self.buzzer else "desligado",
                                    "sensor": "ok" if self.sensor_ok else "falha"}, now, retain=True)

    def telemetria_msg(self, now: float):
        leitura = self.sensor_ok
        return self._msg("telemetria", {
            "estado": self.estado, "modo": self.modo,
            "temperatura": {"valor": round(self.temp, 1), "unidade": "°C"} if leitura else None,
            "umidade": {"valor": round(self.umid), "unidade": "%"} if leitura else None,
            "orcamento": {"valor": round(self.orcamento, 1), "unidade": "u"},
            "aberturas": self.aberturas,
            "rssi": {"valor": -60, "unidade": "dBm"},
        }, now)

    def conectar(self, now: float) -> list:
        return [("status", "online", True), self._evento(now, "boot"), self.estado_msg(now), self.telemetria_msg(now)]

    # ---- entradas fisicas simuladas ----
    def definir(self, now: float, temperatura=None, umidade=None, tampa=None, sensor=None) -> list:
        saida: list = []
        if temperatura is not None:
            self.temp = float(temperatura)
        if umidade is not None:
            self.umid = float(umidade)
        if sensor is not None:
            self.sensor_ok = sensor == "ok"
        if tampa is not None:
            aberta = tampa == "aberta"
            if aberta != self.tampa_aberta:
                self.tampa_aberta = aberta
                saida += self._tampa(now, aberta)
        return saida

    def _tampa(self, now: float, aberta: bool) -> list:
        if aberta and self.estado == "FECHADO":
            self.estado = "EXPOSTO"
            self.aberturas += 1
            self._abertura_ts = now
            self._soma_t, self._amostras = 0.0, 0
            self._orc_abertura = self.orcamento
            return [self._evento(now, "abertura", n=self.aberturas, orcamento={"valor": round(self.orcamento, 1), "unidade": "u"})]
        if not aberta and self.estado == "EXPOSTO":
            dur = now - self._abertura_ts
            tmed = self._soma_t / self._amostras if self._amostras else self.temp
            self.estado = "FECHADO"
            return [self._evento(
                now, "fechamento", n=self.aberturas,
                duracao={"valor": round(dur), "unidade": "s"},
                temperaturaMedia={"valor": round(tmed, 1), "unidade": "°C"},
                consumo={"valor": round(self._orc_abertura - self.orcamento, 1), "unidade": "u"},
                orcamento={"valor": round(self.orcamento, 1), "unidade": "u"})]
        return []  # em QUEBRA a tampa e ignorada ate o reset

    # ---- relogio ----
    def tick(self, now: float) -> list:
        saida: list = self._tick_manual(now)
        dt = 0.0 if self._ultimo_tick is None else min(now - self._ultimo_tick, 5.0)
        self._ultimo_tick = now

        if now - self._ultima_leitura >= INTERVALO_LEITURA_S:
            self._ultima_leitura = now
            saida += self._leitura(now)

        if self.estado == "EXPOSTO" and not self.seguro and self.sensor_ok and dt > 0:
            consumo = max(0.0, 1.0 + (self.temp - 20.0) / 10.0) * self.velocidade * dt
            self.orcamento -= consumo
            self._soma_t += self.temp * dt
            self._amostras += dt
            if self.orcamento <= 0:
                self.orcamento = 0.0
                self.estado = "QUEBRA"
                tmed = self._soma_t / self._amostras if self._amostras else self.temp
                if self.modo == "AUTOMATICO":
                    self.buzzer = True
                saida.append(self._evento(
                    now, "quebra", n=self.aberturas,
                    temperaturaMedia={"valor": round(tmed, 1), "unidade": "°C"},
                    consumo={"valor": round(self._orc_abertura, 1), "unidade": "u"},
                    orcamento={"valor": 0.0, "unidade": "u"}))
                # Seguranca primeiro (CONTRATOS.md secao 4): QUEBRA tira do MANUAL.
                if self.modo == "MANUAL":
                    self.buzzer = True
                    self.rele = True
                    saida += self._voltar_automatico(now, "MANUAL")
                saida += [self.estado_msg(now), self.telemetria_msg(now)]
                self._ultima_tele = now

        if now - self._ultima_tele >= INTERVALO_TELEMETRIA_S:
            self._ultima_tele = now
            saida.append(self.telemetria_msg(now))
        return saida

    def _leitura(self, now: float) -> list:
        """Estado seguro (fluxograma 5.3): 3 leituras invalidas entram; 2 validas saem."""
        saida: list = []
        if not self.sensor_ok:
            self.invalidas += 1
            self.validas = 0
            if self.invalidas >= 3 and not self.seguro:
                self.seguro = True
                self.modo = "SEGURO"
                self.manual_ate = None
                saida += [self._evento(now, "sensor_falha"), self.estado_msg(now)]
        else:
            self.invalidas = 0
            if self.seguro:
                self.validas += 1
                if self.validas >= 2:
                    self.seguro = False
                    self.validas = 0
                    self.modo = "AUTOMATICO"
                    saida += [self._evento(now, "sensor_ok"), self.estado_msg(now)]
        return saida

    # ---- comandos ----
    def _intertravamento(self, comando, acao, dados):
        if comando == "rele" and acao == "desligar" and self.estado == "QUEBRA":
            return ("QUEBRA_ATIVA", "a retencao so sai com o reset")
        if comando == "reset" and self.estado != "QUEBRA":
            return ("SEM_QUEBRA", "nao ha QUEBRA ativa")
        if comando == "config":
            valor = dados.get("valor")
            if isinstance(valor, bool) or not isinstance(valor, (int, float)):
                return ("ACAO_INVALIDA", "config exige 'valor' numerico")
            if not 30 <= valor <= 600:
                return ("FORA_DA_FAIXA", "orcamentoInicial deve ficar entre 30 e 600")
        return None

    def _aplicar(self, comando, acao, dados, now) -> list:
        if comando == "rele" and acao != "auto":
            self.rele = acao == "ligar"
        elif comando == "buzzer" and acao != "auto":
            self.buzzer = acao == "disparar"
        elif comando == "reset":
            self.orcamento = self.orcamento_ini
            self.estado = "FECHADO"
            self.buzzer = False
            self.rele = False
            return [self._evento(now, "reset", orcamento={"valor": round(self.orcamento, 1), "unidade": "u"})]
        elif comando == "config":
            self.orcamento_ini = float(dados["valor"])
            if self.estado != "QUEBRA":
                self.orcamento = self.orcamento_ini
        return []


class Vent01Sim(Sim):
    device_id = "VENT-01"
    comandos = {"exaustor": ("ligar", "desligar", "auto")}

    def __init__(self, sincronizada: bool = True):
        super().__init__(sincronizada)
        self.exaustor = False  # desligado no boot (estado seguro)
        self.desconectado_desde: float | None = None

    def estado_msg(self, now: float):
        return self._msg("estado", {"modo": self.modo, "exaustor": "ligado" if self.exaustor else "desligado"},
                         now, retain=True)

    def conectar(self, now: float) -> list:
        self.desconectado_desde = None
        saida = [("status", "online", True)]
        if self.modo == "SEGURO":  # a conexao com o broker voltou
            self.modo = "AUTOMATICO"
            saida.append(self._evento(now, "modo_alterado", detalhe="SEGURO->AUTOMATICO"))
        else:
            saida.append(self._evento(now, "boot"))
        saida.append(self.estado_msg(now))
        return saida

    def perdeu_conexao(self, now: float) -> None:
        if self.desconectado_desde is None:
            self.desconectado_desde = now

    def tick(self, now: float) -> list:
        saida = self._tick_manual(now)
        if (self.exaustor and self.desconectado_desde is not None
                and now - self.desconectado_desde >= SEGURO_VENT_S and self.modo != "SEGURO"):
            self.exaustor = False
            self.modo = "SEGURO"
            self.manual_ate = None
            saida += [self._evento(now, "modo_alterado", detalhe="->SEGURO"), self.estado_msg(now)]
        return saida

    def _aplicar(self, comando, acao, dados, now) -> list:
        if acao == "ligar":
            self.exaustor = True
        elif acao == "desligar":
            self.exaustor = False
        return []


# --------------------------------------------------------------------------
# Ligacao com o MQTT
# --------------------------------------------------------------------------
class Executor:
    def __init__(self, sim: Sim, host, porta, usuario, senha, prefixo, controle=None):
        import paho.mqtt.client as mqtt

        self.mqtt = mqtt
        self.sim = sim
        self.prefixo = prefixo
        self.controle = controle
        self.trava = threading.Lock()
        self._mtime = 0.0
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"sim-{sim.device_id}")
        if senha:
            self.client.username_pw_set(usuario, senha)
        # Last Will: o broker publica offline se o simulador sumir.
        self.client.will_set(self._topico("status"), "offline", qos=1, retain=True)
        self.client.reconnect_delay_set(1, 30)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.host, self.porta = host, porta

    def _topico(self, tipo: str) -> str:
        return f"{self.prefixo}/{self.sim.device_id}/{tipo}"

    def _publicar(self, msgs: list) -> None:
        for tipo, payload, retain in msgs:
            self.client.publish(self._topico(tipo), payload, qos=0, retain=retain)

    def _on_connect(self, client, userdata, flags, rc, props=None):
        if rc != 0:
            print(f"[{self.sim.device_id}] conexao recusada: {rc}", file=sys.stderr)
            return
        client.subscribe(self._topico("comando/+"), qos=1)
        with self.trava:
            self._publicar(self.sim.conectar(time.time()))
        print(f"[{self.sim.device_id}] conectado")

    def _on_disconnect(self, client, userdata, flags, rc, props=None):
        if hasattr(self.sim, "perdeu_conexao"):
            self.sim.perdeu_conexao(time.time())
        print(f"[{self.sim.device_id}] desconectado")

    def _on_message(self, client, userdata, msg):
        comando = msg.topic.rsplit("/", 1)[-1]
        with self.trava:
            saida = self.sim.on_command(comando, msg.payload, time.time())
            self._publicar(saida)
        print(f"[{self.sim.device_id}] comando {comando}: {msg.payload.decode(errors='replace')[:80]}")

    def _ler_controle(self, now: float) -> list:
        if not (self.controle and isinstance(self.sim, CF01Sim) and os.path.exists(self.controle)):
            return []
        m = os.path.getmtime(self.controle)
        if m == self._mtime:
            return []
        self._mtime = m
        try:
            with open(self.controle, encoding="utf-8") as f:
                c = json.load(f)
            return self.sim.definir(now, c.get("temperatura"), c.get("umidade"), c.get("tampa"), c.get("sensor"))
        except Exception as exc:
            print(f"controle invalido: {exc}", file=sys.stderr)
            return []

    def rodar(self, parar: threading.Event) -> None:
        self.client.connect_async(self.host, self.porta, keepalive=30)
        self.client.loop_start()
        while not parar.wait(1.0):
            now = time.time()
            with self.trava:
                saida = self._ler_controle(now) + self.sim.tick(now)
                if self.client.is_connected():
                    self._publicar(saida)
        self.client.loop_stop()
        self.client.disconnect()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", default="localhost")
    p.add_argument("--porta", type=int, default=1883)
    p.add_argument("--prefixo", default="sentinela/cadeia-fria")
    p.add_argument("--dispositivos", default="cf01,vent01", help="cf01, vent01 ou cf01,vent01")
    p.add_argument("--senha-cf01", default=os.environ.get("MQTT_PASS_CF01", ""))
    p.add_argument("--senha-vent01", default=os.environ.get("MQTT_PASS_VENT01", ""))
    p.add_argument("--temperatura", type=float, default=24.0, help="temperatura inicial da CF-01")
    p.add_argument("--tampa-aberta", action="store_true", help="comeca com a tampa aberta")
    p.add_argument("--velocidade", type=float, default=1.0, help="multiplica a drenagem do orcamento")
    p.add_argument("--sem-hora", action="store_true", help="horaSincronizada=false (ts nulo)")
    p.add_argument("--controle", help="arquivo JSON lido a cada segundo (temperatura, umidade, tampa, sensor)")
    a = p.parse_args()

    quais = {s.strip() for s in a.dispositivos.split(",")}
    execs = []
    if "cf01" in quais:
        cf = CF01Sim(sincronizada=not a.sem_hora, velocidade=a.velocidade, temperatura=a.temperatura)
        if a.tampa_aberta:
            cf.definir(time.time(), tampa="aberta")
        execs.append(Executor(cf, a.host, a.porta, "CF-01", a.senha_cf01, a.prefixo, a.controle))
    if "vent01" in quais:
        execs.append(Executor(Vent01Sim(sincronizada=not a.sem_hora), a.host, a.porta, "VENT-01",
                              a.senha_vent01, a.prefixo))

    parar = threading.Event()
    threads = [threading.Thread(target=e.rodar, args=(parar,), daemon=True) for e in execs]
    for t in threads:
        t.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        parar.set()
        for t in threads:
            t.join(timeout=3)


if __name__ == "__main__":
    main()
