"""Cliente MQTT do backend (paho-mqtt 2.x). Loop em thread propria, com
reconexao automatica. E o unico lugar que publica comandos."""
import logging

import paho.mqtt.client as mqtt

from . import db
from .config import Settings
from .ingest import processar
from .sync import LOCK

log = logging.getLogger("sentinela.mqtt")

TIPOS_ASSINADOS = ("status", "telemetria", "evento", "estado", "confirmacao")


class MqttService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="sentinela-backend")
        if settings.mqtt_pass_backend:
            self.client.username_pw_set(settings.mqtt_user, settings.mqtt_pass_backend)
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self._conectado = False

    @property
    def conectado(self) -> bool:
        return self._conectado

    def start(self) -> None:
        # connect_async + loop_start: se o broker ainda nao subiu, o paho tenta de novo sozinho.
        self.client.connect_async(self.settings.mqtt_host, self.settings.mqtt_port, keepalive=30)
        self.client.loop_start()
        log.info("MQTT: conectando em %s:%s", self.settings.mqtt_host, self.settings.mqtt_port)

    def stop(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()

    def publicar(self, topico: str, payload: str, qos: int = 1, retain: bool = False) -> bool:
        if not self._conectado:
            return False
        info = self.client.publish(topico, payload, qos=qos, retain=retain)
        return info.rc == mqtt.MQTT_ERR_SUCCESS

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code != 0:
            log.error("MQTT: conexao recusada (%s)", reason_code)
            return
        self._conectado = True
        prefixo = self.settings.mqtt_topic_prefix
        # Reassina a cada (re)conexao: sessao limpa nao guarda assinaturas.
        for tipo in TIPOS_ASSINADOS:
            client.subscribe(f"{prefixo}/+/{tipo}", qos=1)
        log.info("MQTT: conectado; assinando %s/+/{%s}", prefixo, ",".join(TIPOS_ASSINADOS))

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        self._conectado = False
        log.warning("MQTT: desconectado (%s); o paho reconecta sozinho", reason_code)

    def _on_message(self, client, userdata, msg):
        try:
            with LOCK, db.session_scope() as session:
                processar(session, self, msg.topic, msg.payload, settings=self.settings)
        except Exception:  # uma mensagem ruim nunca derruba o assinante
            log.exception("erro ao processar %s", msg.topic)
