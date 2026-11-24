"""Formatos de entrada e saida da API REST (ver backend/API.md)."""
from datetime import datetime

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expira_em_s: int
    usuario: str
    perfil: str


class Medida(BaseModel):
    valor: float
    unidade: str


class DispositivoOut(BaseModel):
    id: str
    tipo: str
    nome: str
    online: bool
    ultimo_contato: datetime | None
    estado: str | None  # FECHADO | EXPOSTO | QUEBRA (so a caixa)
    modo: str | None  # AUTOMATICO | MANUAL | SEGURO
    temperatura: Medida | None
    umidade: Medida | None
    orcamento: Medida | None
    aberturas: int | None
    rssi: Medida | None
    atuadores: dict[str, str]  # rele/buzzer (CF-01) ou exaustor (VENT-01): ligado | desligado
    sensor: str | None  # ok | falha
    telemetria_em: datetime | None
    estado_em: datetime | None


class ComandoIn(BaseModel):
    comando: str = Field(min_length=1, max_length=20)
    acao: str = Field(min_length=1, max_length=40)
    valor: float | None = None


class ComandoOut(BaseModel):
    command_id: str
    dispositivo: str
    comando: str
    acao: str
    valor: float | None
    origem: str
    usuario: str | None
    status: str  # enviado | recebido | executado | confirmado | nao_confirmado | sem_efeito
    resultado: str | None  # aceito | rejeitado | executado
    motivo: str | None
    detalhe: str | None
    concluido: bool
    rotulo: str
    enviado_em: datetime
    recebido_em: datetime | None
    executado_em: datetime | None
    confirmado_em: datetime | None


class PontoHistorico(BaseModel):
    ts: datetime
    valor: float
    media_movel: float


class HistoricoOut(BaseModel):
    dispositivo: str
    grandeza: str
    unidade: str | None
    janela_media: int
    pontos: list[PontoHistorico]


class EventoOut(BaseModel):
    id: int
    dispositivo: str
    evento: str
    ts: datetime
    recebido_em: datetime
    n: int | None
    duracao_s: float | None
    temperatura_media: float | None
    consumo: float | None
    orcamento: float | None
    detalhe: str | None


class RegraIO(BaseModel):
    temp_ligar: float = Field(ge=0, le=60)
    temp_desligar: float = Field(ge=0, le=60)
    janela_s: int = Field(ge=10, le=3600)
    ativa: bool = True


class RegraOut(RegraIO):
    atualizado_em: datetime | None


class AlertaOut(BaseModel):
    tipo: str  # quebra | offline | sensor_falha | comando_nao_confirmado
    severidade: str  # critico | aviso
    dispositivo: str | None
    mensagem: str
    desde: datetime | None


class IndicadoresOut(BaseModel):
    dispositivo: str
    desde: datetime
    ate: datetime
    estado_atual: str | None
    orcamento_atual: float | None
    aberturas: int
    aberturas_por_turno: dict[str, int]
    quebras: int
    tempo_exposicao_s: float
    tempo_quebra_s: float
