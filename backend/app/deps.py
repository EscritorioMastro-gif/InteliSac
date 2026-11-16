from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from . import integracao
from .db import get_db
from .models import User
from .security import decode_token, versao_confere


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    auth = request.headers.get("Authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    if integracao.parece_chave(token):  # outro sistema com chave de API (só algumas rotas)
        return integracao.usuario_da_chave(request, db, token)
    data = decode_token(token)
    if not data:
        raise HTTPException(401, detail={"message": "Token inválido ou expirado"})
    user = db.get(User, data["sub"])
    if not user or user.archived_at is not None:
        raise HTTPException(401, detail={"message": "Usuário inativo"})
    if not versao_confere(data, user):
        raise HTTPException(401, detail={"message": "Sessão encerrada. Entre de novo."})
    return user


def admin_user(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, detail={"message": "Apenas administradores"})
    return user


def paginate(query, page: int, per_page: int) -> dict:
    per_page = max(1, min(per_page, 200))
    page = max(1, page)
    total = query.count()
    rows = query.offset((page - 1) * per_page).limit(per_page).all()
    last_page = max(1, -(-total // per_page))
    skip = (page - 1) * per_page
    return {
        "data": [r.to_dict() for r in rows],
        "total": total,
        "limit": per_page,
        "skip": skip,
        "currentPage": page,
        "lastPage": last_page,
        "from": skip + 1 if rows else 0,
        "to": skip + len(rows),
    }
