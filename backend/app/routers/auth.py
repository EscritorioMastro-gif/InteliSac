"""POST /api/v1/oauth/token — mesmo contrato do Digisac (OAuth2 password / refresh_token).

Com o Supabase Auth configurado (SUPABASE_URL + SUPABASE_ANON_KEY), o e-mail e a senha são
conferidos no Supabase; o usuário do Supabase precisa estar VINCULADO (users.auth_user_id) a um
usuário ativo do InteliSac. Não vale só o e-mail igual: o cadastro público do Supabase deixaria
qualquer pessoa criar uma conta com o e-mail de um colaborador ainda não vinculado.
Usuários antigos com senha local (ex.: o admin criado pelo seed) continuam entrando pela senha local.

Senha errada demais (30 por IP em 5 min, ou 10 no mesmo e-mail em 15 min) → 429 por alguns minutos.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import supabase_auth
from ..config import settings
from ..protecao import ip_do_cliente, login_por_email, login_por_ip
from ..db import get_db
from ..models import User
from ..security import create_tokens, decode_token, verify_password

router = APIRouter(tags=["auth"])

INVALID = {"error": "invalid_grant", "message": "E-mail ou senha inválidos"}


def _active_user(db: Session, email: str) -> User | None:
    user = db.query(User).filter(User.email == email).first()
    if user is None or user.archived_at is not None:
        return None
    return user


def _linked_user(db: Session, auth_user_id: str | None) -> User | None:
    if not auth_user_id:
        return None
    user = db.query(User).filter(User.auth_user_id == auth_user_id).first()
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
            user = _linked_user(db, auth_user.get("id"))
            if user is None:
                raise HTTPException(
                    403,
                    detail={"error": "not_registered", "message": "Login válido, mas este acesso não está liberado (ou está arquivado) no InteliSac. Peça ao administrador."},
                )
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


def _bloqueado(segundos: int):
    minutos = max(1, round(segundos / 60))
    return HTTPException(
        429,
        detail={"error": "too_many_attempts", "message": f"Muitas tentativas de login. Tente de novo em {minutos} min."},
        headers={"Retry-After": str(segundos)},
    )


@router.post("/oauth/token")
async def token(request: Request, db: Session = Depends(get_db)):
    try:
        if request.headers.get("content-type", "").startswith("application/json"):
            form = await request.json()
        else:
            form = dict(await request.form())
    except ValueError:
        form = None
    if not isinstance(form, dict):
        raise HTTPException(400, detail={"error": "invalid_request"})
    grant = form.get("grant_type", "password")

    if grant == "password":
        email = str(form.get("username") or "").strip().lower()[:200]
        password = str(form.get("password") or "")[:200]
        ip = ip_do_cliente(request)
        espera = max(login_por_ip.espera(ip), login_por_email.espera(email))
        if espera:
            raise _bloqueado(espera)
        if not email or not password:
            raise HTTPException(401, detail=INVALID)
        try:
            user = await _password_login(db, email, password)
        except HTTPException as e:
            if e.status_code == 401:
                login_por_ip.falhou(ip)
                login_por_email.falhou(email)
            raise
        login_por_email.zera(email)
        return create_tokens(user.id, user.account_id)

    if grant == "refresh_token":
        data = decode_token(str(form.get("refresh_token") or ""), expected_type="refresh")
        user = db.get(User, data["sub"]) if data else None
        if not user or user.archived_at is not None:
            raise HTTPException(401, detail={"error": "invalid_grant", "message": "Sessão expirada"})
        return create_tokens(user.id, user.account_id)

    raise HTTPException(400, detail={"error": "unsupported_grant_type"})


@router.post("/oauth/revoke")
def revoke():
    # JWT sem estado: o cliente descarta os tokens. (Lista de revogação fica para depois.)
    return True
