"""Trava unica: assinante MQTT, relogio de prazos/regras e API de comando mexem
nas mesmas linhas de comandos; serializar evita corrida entre eles."""
import threading

LOCK = threading.RLock()
