from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DT = DateTime(timezone=True)


class Base(DeclarativeBase):
    pass


class Dispositivo(Base):
    __tablename__ = "dispositivos"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)  # deviceId
    tipo: Mapped[str] = mapped_column(String(20))  # caixa | estacao
    nome: Mapped[str] = mapped_column(String(60))
    online: Mapped[bool] = mapped_column(Boolean, default=False)
    ultimo_contato: Mapped[datetime | None] = mapped_column(DT, nullable=True)
    estado_maquina: Mapped[str | None] = mapped_column(String(10), nullable=True)  # FECHADO/EXPOSTO/QUEBRA
    modo: Mapped[str | None] = mapped_column(String(12), nullable=True)
    telemetria: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # ultima telemetria valida
    telemetria_em: Mapped[datetime | None] = mapped_column(DT, nullable=True)
    estado: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # ultimo `estado` retido
    estado_em: Mapped[datetime | None] = mapped_column(DT, nullable=True)


class Medicao(Base):
    __tablename__ = "medicoes"
    __table_args__ = (Index("ix_medicoes_busca", "dispositivo_id", "grandeza", "recebido_em"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dispositivo_id: Mapped[str] = mapped_column(ForeignKey("dispositivos.id"))
    grandeza: Mapped[str] = mapped_column(String(20))  # temperatura | umidade | orcamento | rssi
    valor: Mapped[float] = mapped_column(Float)
    unidade: Mapped[str] = mapped_column(String(10))
    ts: Mapped[datetime] = mapped_column(DT)  # do dispositivo (ou recebimento, se hora nao sincronizada)
    recebido_em: Mapped[datetime] = mapped_column(DT)


class Evento(Base):
    __tablename__ = "eventos"
    __table_args__ = (Index("ix_eventos_busca", "dispositivo_id", "recebido_em"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dispositivo_id: Mapped[str] = mapped_column(ForeignKey("dispositivos.id"))
    evento: Mapped[str] = mapped_column(String(20))
    ts: Mapped[datetime] = mapped_column(DT)
    recebido_em: Mapped[datetime] = mapped_column(DT)
    n: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duracao_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperatura_media: Mapped[float | None] = mapped_column(Float, nullable=True)
    consumo: Mapped[float | None] = mapped_column(Float, nullable=True)
    orcamento: Mapped[float | None] = mapped_column(Float, nullable=True)
    detalhe: Mapped[str | None] = mapped_column(String(120), nullable=True)


class Comando(Base):
    __tablename__ = "comandos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    command_id: Mapped[str] = mapped_column(String(40), unique=True)
    dispositivo_id: Mapped[str] = mapped_column(ForeignKey("dispositivos.id"))
    comando: Mapped[str] = mapped_column(String(20))  # rele | buzzer | reset | config | exaustor
    acao: Mapped[str] = mapped_column(String(40))
    valor: Mapped[float | None] = mapped_column(Float, nullable=True)
    origem: Mapped[str] = mapped_column(String(10))  # usuario | regra
    usuario: Mapped[str | None] = mapped_column(String(60), nullable=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    resultado: Mapped[str | None] = mapped_column(String(12), nullable=True)  # aceito | rejeitado | executado
    motivo: Mapped[str | None] = mapped_column(String(20), nullable=True)
    detalhe: Mapped[str | None] = mapped_column(String(120), nullable=True)
    enviado_em: Mapped[datetime] = mapped_column(DT)
    recebido_em: Mapped[datetime | None] = mapped_column(DT, nullable=True)
    executado_em: Mapped[datetime | None] = mapped_column(DT, nullable=True)
    confirmado_em: Mapped[datetime | None] = mapped_column(DT, nullable=True)


class MensagemRejeitada(Base):
    __tablename__ = "mensagens_rejeitadas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topico: Mapped[str] = mapped_column(String(200))
    payload: Mapped[str] = mapped_column(Text)
    motivo: Mapped[str] = mapped_column(Text)
    recebido_em: Mapped[datetime] = mapped_column(DT)


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True)
    senha_hash: Mapped[str] = mapped_column(String(100))
    perfil: Mapped[str] = mapped_column(String(20))  # tecnico | coordenacao


class Regra(Base):
    """Linha unica (id=1) com os limites editaveis do R8."""
    __tablename__ = "regras"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    temp_ligar: Mapped[float] = mapped_column(Float)
    temp_desligar: Mapped[float] = mapped_column(Float)
    janela_s: Mapped[int] = mapped_column(Integer)
    ativa: Mapped[bool] = mapped_column(Boolean, default=True)
    atualizado_em: Mapped[datetime | None] = mapped_column(DT, nullable=True)
