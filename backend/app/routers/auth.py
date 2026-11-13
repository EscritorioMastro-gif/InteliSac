"""POST /api/v1/oauth/token — mesmo contrato do Digisac (OAuth2 password / refresh_token).

Com o Supabase Auth configurado (SUPABASE_URL + SUPABASE_ANON_KEY), o e-mail e a senha são
conferidos no Supabase; o usuário também precisa existir (ativo) no InteliSac com o mesmo e-mail.
Usuários antigos com senha local (ex.: o admin criado pelo seed) continuam entrando pela senha local.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import supabase_auth
from ..config import settings
from ..db import get_db
from ..models import User
from ..security import create_tokens, decode_token, verify_password

router = APIRouter(tags=["auth"])

INVALID = {"error": "invalid_grant", "message": "E-mail ou senha inválidos"}


def _active_user(db: Session, email: str, auth_user_id: str | None = None) -> User | None:
    user = None
    if auth_user_id:
        user = db.query(User).filter(User.auth_user_id == auth_user_id).first()
    if user is None:
        user = db.query(User).filter(User.email == email).first()
    if user is None or user.archived_at is not None:
        return None
    return user


async def _password_login(db: Session, email: str, password: str) -> User:
    if settings.supabase_auth_enabled:
        try:
            auth_user = await supabase_auth.sign_in(email, password)
        except supabase_auth.AuthServiceError:
            auth_user = None
            supabase_down = True
        else:
            supabase_down = False
        if auth_user:
            user = _active_user(db, email, auth_user.get("id"))
            if user is None:
                raise HTTPException(
                    403,
                    detail={"error": "not_registered", "message": "Login válido, mas este e-mail não está cadastrado (ou está arquivado) no InteliSac. Peça ao administrador."},
                )
            if not user.auth_user_id and auth_user.get("id"):
                user.auth_user_id = auth_user["id"]
                db.commit()
            return user
        # Senha recusada pelo Supabase (ou Supabase fora): só usuários com senha local podem entrar.
        user = _active_user(db, email)
        if user and user.password_hash and verify_password(password, user.password_hash):
            return user
        if supabase_down:
            raise HTTPException(503, detail={"error": "auth_unavailable", "message": "Serviço de login indisponível. Tente de novo em instantes."})
        raise HTTPException(401, detail=INVALID)

    user = _active_user(db, email)
    if not user or not verify_password(password, user.password_hash or ""):
        raise HTTPException(401, detail=INVALID)
    return user


@router.post("/oauth/token")
async def token(request: Request, db: Session = Depends(get_db)):
    if request.headers.get("content-type", "").startswith("application/json"):
        form = await request.json()
    else:
        form = dict(await request.form())
    grant = form.get("grant_type", "password")

    if grant == "password":
        email = (form.get("username") or "").strip().lower()
        password = form.get("password") or ""
        if not email or not password:
            raise HTTPException(401, detail=INVALID)
        user = await _password_login(db, email, password)
        return create_tokens(user.id, user.account_id)

    if grant == "refresh_token":
        data = decode_token(form.get("refresh_token") or "", expected_type="refresh")
        user = db.get(User, data["sub"]) if data else None
        if not user or user.archived_at is not None:
            raise HTTPException(401, detail={"error": "invalid_grant", "message": "Sessão expirada"})
        return create_tokens(user.id, user.account_id)

    raise HTTPException(400, detail={"error": "unsupported_grant_type"})


@router.post("/oauth/revoke")
def revoke():
    # JWT sem estado: o cliente descarta os tokens. (Lista de revogação fica para depois.)
    return True
