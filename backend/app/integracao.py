"""Integrações por chave de API: outros sistemas (rotinas que disparam mensagens e guias)
falam com o InteliSac com `Authorization: Bearer isk_...`.

- Mesmo formato da API do Digisac nas rotas usadas pelas rotinas: quem já usa o Digisac troca
  só o endereço, a chave e o id da conexão.
- Uma chave só alcança as rotas da lista ROTAS (contatos, chamados, mensagens, fechar chamado).
  Nada de usuários, conexões/QR, configurações ou o próprio módulo API.
- Quem age por uma chave é o "robô" da conta: um usuário arquivado (não entra pela tela e não
  aparece nas listas), só para os registros ("fechado por Integração (API)").
"""

import hashlib
import re
import secrets

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from .models import ApiKey, User, now
from .protecao import Limite

PREFIXO = "isk_"
NOME_ROBO = "Integração (API)"

# O que uma chave pode chamar (método, caminho)
ROTAS = [
    (m, re.compile(p))
    for m, p in (
        ("GET", r"^/api/v1/services$"),
        ("GET", r"^/api/v1/contacts$"),
        ("POST", r"^/api/v1/contacts$"),
        ("GET", r"^/api/v1/contacts/[^/]+$"),
        ("POST", r"^/api/v1/contacts/[^/]+/ticket/close$"),
        ("GET", r"^/api/v1/tickets$"),
        ("GET", r"^/api/v1/tickets/[^/]+$"),
        ("GET", r"^/api/v1/messages$"),
        ("POST", r"^/api/v1/messages$"),
        ("GET", r"^/api/v1/integracao/ping$"),
    )
]

# Proteção do número de WhatsApp: no máximo 40 envios por minuto por chave
envios = Limite(40, 60)


def gerar_chave() -> str:
    return PREFIXO + secrets.token_urlsafe(32)


def hash_chave(chave: str) -> str:
    return hashlib.sha256(chave.encode()).hexdigest()


def parece_chave(token: str) -> bool:
    return token.startswith(PREFIXO) and 20 <= len(token) <= 100


def rota_permitida(metodo: str, caminho: str) -> bool:
    return any(m == metodo and p.match(caminho) for m, p in ROTAS)


def robo_da_conta(db: Session, account_id: str) -> User:
    email = f"api-{account_id}@integracao.intelisac.local"
    robo = db.query(User).filter(User.email == email).first()
    if robo is None:
        robo = User(account_id=account_id, name=NOME_ROBO, email=email, password_hash="", is_admin=False,
                    status="offline", archived_at=now())
        db.add(robo)
        db.flush()
    return robo


def chave_valida(db: Session, token: str) -> ApiKey | None:
    if not parece_chave(token):
        return None
    return db.query(ApiKey).filter(ApiKey.key_hash == hash_chave(token), ApiKey.revoked_at.is_(None)).first()


def usuario_da_chave(request: Request, db: Session, token: str) -> User:
    """Confere a chave e a rota e devolve o robô da conta, marcado com a chave usada."""
    chave = chave_valida(db, token)
    if chave is None:
        raise HTTPException(401, detail={"message": "Chave de API inválida ou revogada"})
    if not rota_permitida(request.method, request.url.path):
        raise HTTPException(403, detail={"message": "Esta chave de API não tem acesso a esta parte do sistema"})
    agora = now()
    ultimo = chave.last_used_at
    if ultimo is not None and ultimo.tzinfo is None:
        ultimo = ultimo.replace(tzinfo=agora.tzinfo)
    if ultimo is None or (agora - ultimo).total_seconds() > 60:
        chave.last_used_at = agora
    robo = robo_da_conta(db, chave.account_id)
    db.commit()
    robo.api_key_id = chave.id  # quem mandou (fica registrado nas mensagens)
    robo.api_key_nome = chave.name
    return robo


def eh_integracao(user: User) -> bool:
    return getattr(user, "api_key_id", None) is not None
