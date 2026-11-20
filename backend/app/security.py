"""Autenticacao (R9) e perfis (R16): JWT + bcrypt.
`tecnico` so le; `coordenacao` le e comanda."""
from datetime import timedelta

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import Usuario
from .tempo import agora

PERFIS = ("tecnico", "coordenacao")
_bearer = HTTPBearer(auto_error=False)


def hash_senha(senha: str) -> str:
    return bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt(get_settings().bcrypt_rounds)).decode("ascii")


def confere_senha(senha: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(senha.encode("utf-8"), hashed.encode("ascii"))
    except ValueError:
        return False


def criar_token(usuario: Usuario) -> tuple[str, int]:
    s = get_settings()
    exp = agora() + timedelta(minutes=s.jwt_expira_min)
    token = jwt.encode(
        {"sub": usuario.username, "perfil": usuario.perfil, "exp": exp}, s.jwt_secret, algorithm="HS256"
    )
    return token, s.jwt_expira_min * 60


def semear_usuarios(session: Session) -> None:
    """Cria os usuarios-semente do .env (so se ainda nao existirem)."""
    s = get_settings()
    for user, senha, perfil in (
        (s.seed_coordenacao_user, s.seed_coordenacao_password, "coordenacao"),
        (s.seed_tecnico_user, s.seed_tecnico_password, "tecnico"),
    ):
        if not user or not senha:
            continue
        if session.scalar(select(Usuario).where(Usuario.username == user)) is None:
            session.add(Usuario(username=user, senha_hash=hash_senha(senha), perfil=perfil))
    session.flush()


def _nao_autenticado(detalhe: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detalhe, headers={"WWW-Authenticate": "Bearer"})


def usuario_atual(
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)
) -> Usuario:
    if cred is None:
        raise _nao_autenticado("token ausente")
    try:
        dados = jwt.decode(cred.credentials, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise _nao_autenticado("token expirado")
    except jwt.PyJWTError:
        raise _nao_autenticado("token invalido")
    usuario = db.scalar(select(Usuario).where(Usuario.username == dados.get("sub")))
    if usuario is None:
        raise _nao_autenticado("usuario inexistente")
    return usuario


def exige_coordenacao(usuario: Usuario = Depends(usuario_atual)) -> Usuario:
    if usuario.perfil != "coordenacao":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "perfil sem permissao: exige 'coordenacao'")
    return usuario
