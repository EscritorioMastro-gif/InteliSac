"""Módulo API: administrador + senha do módulo → cria e revoga chaves de API.

Senha do módulo: definida pelo próprio administrador no primeiro acesso (fica só o hash no banco,
nunca no código). Entrar dá um passe de 30 minutos (cabeçalho X-Modulo-Token).
Senha errada ou passe vencido respondem 403 (401 derrubaria o login do InteliSac na tela).
"""

from datetime import timedelta

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import integracao
from ..db import get_db
from ..deps import admin_user, current_user
from ..models import ApiKey, ModuloApi, Service, User, now
from ..protecao import Limite
from ..security import _encode, decode_token, hash_password, verify_password

router = APIRouter(prefix="/integracao", tags=["integracao"])

PASSE_MINUTOS = 30
tentativas = Limite(5, 900)  # 5 senhas erradas por administrador a cada 15 min


def _passe(user: User) -> dict:
    token = _encode({"sub": user.id, "acc": user.account_id, "typ": "modulo_api"}, timedelta(minutes=PASSE_MINUTOS))
    return {"token": token, "expiresIn": PASSE_MINUTOS * 60}


def modulo_liberado(request: Request, user: User = Depends(admin_user)) -> User:
    data = decode_token(request.headers.get("X-Modulo-Token", ""), expected_type="modulo_api")
    if not data or data.get("sub") != user.id or data.get("acc") != user.account_id:
        raise HTTPException(403, detail={"message": "Digite a senha do módulo API de novo", "error": "modulo_bloqueado"})
    return user


def _senha_ok(senha: str) -> str:
    senha = str(senha or "")
    if len(senha) < 8:
        raise HTTPException(422, detail={"message": "A senha do módulo precisa ter pelo menos 8 caracteres"})
    if len(senha) > 200:
        raise HTTPException(422, detail={"message": "Senha longa demais"})
    return senha


@router.get("/modulo")
def situacao_do_modulo(db: Session = Depends(get_db), user: User = Depends(admin_user)):
    return {"configured": db.get(ModuloApi, user.account_id) is not None}


@router.post("/modulo/definir")
def definir_senha(body: dict = Body(...), db: Session = Depends(get_db), user: User = Depends(admin_user)):
    """Primeiro acesso: o administrador cria a senha do módulo (só quando ainda não existe)."""
    if db.get(ModuloApi, user.account_id) is not None:
        raise HTTPException(409, detail={"message": "A senha do módulo já foi definida"})
    db.add(ModuloApi(account_id=user.account_id, senha_hash=hash_password(_senha_ok(body.get("password"))),
                     atualizado_em=now(), atualizado_por=user.id))
    db.commit()
    return _passe(user)


@router.post("/modulo/entrar")
def entrar(body: dict = Body(...), db: Session = Depends(get_db), user: User = Depends(admin_user)):
    espera = tentativas.espera(user.id)
    if espera:
        raise HTTPException(429, detail={"message": f"Muitas senhas erradas. Tente de novo em {max(1, round(espera / 60))} min."},
                            headers={"Retry-After": str(espera)})
    modulo = db.get(ModuloApi, user.account_id)
    if modulo is None:
        raise HTTPException(409, detail={"message": "Defina a senha do módulo primeiro", "error": "sem_senha"})
    if not verify_password(str(body.get("password") or ""), modulo.senha_hash):
        tentativas.falhou(user.id)
        raise HTTPException(403, detail={"message": "Senha do módulo incorreta"})
    tentativas.zera(user.id)
    return _passe(user)


@router.post("/modulo/senha")
def trocar_senha(body: dict = Body(...), db: Session = Depends(get_db), user: User = Depends(modulo_liberado)):
    modulo = db.get(ModuloApi, user.account_id)
    if modulo is None or not verify_password(str(body.get("currentPassword") or ""), modulo.senha_hash):
        raise HTTPException(403, detail={"message": "Senha atual do módulo incorreta"})
    modulo.senha_hash = hash_password(_senha_ok(body.get("password")))
    modulo.atualizado_em, modulo.atualizado_por = now(), user.id
    db.commit()
    return {"ok": True}


@router.get("/chaves")
def listar_chaves(db: Session = Depends(get_db), user: User = Depends(modulo_liberado)):
    chaves = db.query(ApiKey).filter(ApiKey.account_id == user.account_id).order_by(ApiKey.created_at.desc()).all()
    nomes = {u.id: u.name for u in db.query(User).filter(User.account_id == user.account_id).all()}
    return {"data": [{**c.to_dict(), "createdByName": nomes.get(c.created_by)} for c in chaves]}


@router.post("/chaves", status_code=201)
def criar_chave(body: dict = Body(...), db: Session = Depends(get_db), user: User = Depends(modulo_liberado)):
    """A chave inteira só aparece nesta resposta: guarde em lugar seguro (o InteliSac guarda só o hash)."""
    nome = str(body.get("name") or "").strip()[:120]
    if not nome:
        raise HTTPException(422, detail={"message": "Dê um nome para a chave (ex.: Rotina de guias)"})
    chave = integracao.gerar_chave()
    obj = ApiKey(account_id=user.account_id, name=nome, prefix=chave[:12], key_hash=integracao.hash_chave(chave),
                 created_by=user.id, created_at=now())
    db.add(obj)
    integracao.robo_da_conta(db, user.account_id)
    db.commit()
    return {**obj.to_dict(), "createdByName": user.name, "key": chave}


@router.delete("/chaves/{chave_id}")
def revogar_chave(chave_id: str, db: Session = Depends(get_db), user: User = Depends(modulo_liberado)):
    obj = db.query(ApiKey).filter(ApiKey.account_id == user.account_id, ApiKey.id == chave_id).first()
    if obj is None:
        raise HTTPException(404, detail={"message": "Chave não encontrada"})
    if obj.revoked_at is None:
        obj.revoked_at = now()
        db.commit()
    return obj.to_dict()


@router.get("/ping")
def ping(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Teste de conexão para quem integra: diz qual chave chegou e lista as conexões (ids para serviceId)."""
    conexoes = db.query(Service).filter(Service.account_id == user.account_id, Service.archived_at.is_(None)).all()
    return {
        "ok": True,
        "key": getattr(user, "api_key_nome", None),
        "services": [{"id": s.id, "name": s.name, "type": s.type, "isConnected": s.is_connected} for s in conexoes],
    }
