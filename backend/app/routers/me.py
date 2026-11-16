from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import supabase_auth
from ..config import settings
from ..db import get_db
from ..deps import current_user
from ..models import Account, User
from ..realtime import emit
from ..security import create_tokens, hash_password, verify_password

router = APIRouter(prefix="/me", tags=["me"])


@router.get("")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    data = user.to_dict()
    data["departments"] = [d.to_dict() for d in user.departments]
    data["permissions"] = ["*"] if user.is_admin else (user.role.permissions if user.role else [])
    data["account"] = db.get(Account, user.account_id).to_dict()
    data["features"] = {"simulator": settings.enable_simulator}
    return data


@router.get("/account")
def my_account(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.get(Account, user.account_id).to_dict()


@router.put("")
async def update_me(body: dict = Body(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    if "name" in body and body["name"]:
        user.name = str(body["name"])[:200]
    trocou_senha = False
    if body.get("password"):
        if len(body["password"]) < 8:
            raise HTTPException(422, detail={"message": "A senha precisa ter pelo menos 8 caracteres"})
        if user.auth_user_id and settings.supabase_auth_enabled:
            try:
                ok = await supabase_auth.sign_in(user.email, body.get("currentPassword") or "")
                if not ok:
                    raise HTTPException(422, detail={"message": "Senha atual incorreta"})
                supabase_auth.update_user(user.auth_user_id, password=body["password"])
            except supabase_auth.AuthServiceError as e:
                raise HTTPException(502, detail={"message": str(e)})
        else:
            if not verify_password(body.get("currentPassword") or "", user.password_hash or ""):
                raise HTTPException(422, detail={"message": "Senha atual incorreta"})
            user.password_hash = hash_password(body["password"])
        trocou_senha = True
        user.token_version = int(user.token_version or 0) + 1  # os logins antigos deixam de valer
    db.commit()
    await emit(user.account_id, "user.updated", user.to_dict())
    data = user.to_dict()
    if trocou_senha:
        # quem trocou continua logado neste aparelho, com tokens novos
        data["tokens"] = create_tokens(user.id, user.account_id, user.token_version)
    return data


@router.put("/status")
async def update_status(body: dict = Body(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    status = body.get("status")
    if status not in ("online", "away", "offline"):
        raise HTTPException(422, detail={"message": "status deve ser online, away ou offline"})
    user.status = status
    db.commit()
    await emit(user.account_id, "user.updated", user.to_dict())
    return user.to_dict()
