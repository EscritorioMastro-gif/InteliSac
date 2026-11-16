"""Ferramentas de texto para quem está escrevendo (botão "Corrigir meu texto") e o controle
do crédito do Claude (só administradores)."""

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import corretor
from ..config import settings
from ..db import get_db
from ..deps import admin_user, current_user
from ..models import CorretorConta, User, iso, now
from ..realtime import emit_admins

router = APIRouter(prefix="/text", tags=["text"])


def _conta(db: Session, account_id: str) -> CorretorConta:
    c = db.get(CorretorConta, account_id)
    if c is None:
        c = CorretorConta(account_id=account_id, mes="", gasto_mes_usd=0.0, correcoes_mes=0,
                          gasto_desde_saldo_usd=0.0, aviso_abaixo_usd=3.0)
        db.add(c)
        db.flush()
    return c


def _alerta(c: CorretorConta) -> str | None:
    if not settings.anthropic_api_key:
        return None
    if c.sem_credito_em:
        return "sem_credito"
    if c.saldo_usd is not None and c.saldo_usd - (c.gasto_desde_saldo_usd or 0) <= (c.aviso_abaixo_usd or 0):
        return "saldo_baixo"
    return None


def situacao(c: CorretorConta) -> dict:
    mes_atual = f"{now():%Y-%m}"
    no_mes = c.mes == mes_atual
    estimado = None if c.saldo_usd is None else round(c.saldo_usd - (c.gasto_desde_saldo_usd or 0), 4)
    return {
        "provider": "claude" if settings.anthropic_api_key else "languagetool",
        "model": settings.corretor_modelo if settings.anthropic_api_key else None,
        "month": mes_atual,
        "monthCostUsd": round(c.gasto_mes_usd or 0, 4) if no_mes else 0.0,
        "monthCorrections": (c.correcoes_mes or 0) if no_mes else 0,
        "balanceUsd": c.saldo_usd,
        "balanceAt": iso(c.saldo_em),
        "costSinceBalanceUsd": round(c.gasto_desde_saldo_usd or 0, 4),
        "estimatedBalanceUsd": estimado,
        "alertBelowUsd": c.aviso_abaixo_usd,
        "noCreditSince": iso(c.sem_credito_em),
        "alert": _alerta(c),
    }


@router.post("/correct")
async def corrigir_texto(body: dict = Body(...), db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Corrige ortografia e pontuação (português do Brasil). Devolve o texto corrigido e o que mudou."""
    try:
        r = await corretor.corrigir(str(body.get("text") or ""))
    except corretor.CorretorError as e:
        raise HTTPException(503, detail={"message": str(e)})
    uso = r.pop("uso", None)
    problema = r.pop("problema", None)
    if uso or problema == "sem_credito":
        c = _conta(db, user.account_id)
        antes = _alerta(c)
        mes = f"{now():%Y-%m}"
        if c.mes != mes:  # virou o mês: começa a somar de novo
            c.mes, c.gasto_mes_usd, c.correcoes_mes = mes, 0.0, 0
            db.flush()
        if uso:
            custo = float(uso["costUsd"])
            # soma no próprio banco (duas correções ao mesmo tempo não se perdem)
            c.gasto_mes_usd = CorretorConta.gasto_mes_usd + custo
            c.correcoes_mes = CorretorConta.correcoes_mes + 1
            c.gasto_desde_saldo_usd = CorretorConta.gasto_desde_saldo_usd + custo
            c.sem_credito_em = None
        else:
            c.sem_credito_em = c.sem_credito_em or now()
        db.commit()
        db.refresh(c)
        if _alerta(c) != antes:
            await emit_admins(user.account_id, "corretor.updated", situacao(c))
    return r


@router.get("/correct/status")
def status_do_corretor(db: Session = Depends(get_db), user: User = Depends(admin_user)):
    """Qual corretor está ligado, quanto gastou no mês e o saldo estimado da Anthropic."""
    c = db.get(CorretorConta, user.account_id) or CorretorConta(
        account_id=user.account_id, mes="", gasto_mes_usd=0.0, correcoes_mes=0, gasto_desde_saldo_usd=0.0, aviso_abaixo_usd=3.0
    )
    return situacao(c)


def _valor(v, campo: str) -> float | None:
    if v is None or v == "":
        return None
    try:
        n = round(float(str(v).replace(",", ".")), 2)
    except ValueError:
        raise HTTPException(422, detail={"message": f"{campo}: informe um valor em dólares (ex.: 20 ou 4,50)"})
    if n < 0 or n > 100000:
        raise HTTPException(422, detail={"message": f"{campo}: valor fora do esperado"})
    return n


@router.put("/correct/status")
async def informar_saldo(body: dict = Body(...), db: Session = Depends(get_db), user: User = Depends(admin_user)):
    """O administrador informa o saldo que aparece em console.anthropic.com (depois de recarregar)
    e abaixo de quanto quer ser avisado. O gasto passa a ser descontado a partir daqui."""
    c = _conta(db, user.account_id)
    if "balanceUsd" in body:
        c.saldo_usd = _valor(body.get("balanceUsd"), "Saldo")
        c.saldo_em = now() if c.saldo_usd is not None else None
        c.gasto_desde_saldo_usd = 0.0
        c.sem_credito_em = None  # recarregou
    if "alertBelowUsd" in body:
        c.aviso_abaixo_usd = _valor(body.get("alertBelowUsd"), "Aviso") or 0.0
    db.commit()
    db.refresh(c)
    s = situacao(c)
    await emit_admins(user.account_id, "corretor.updated", s)
    return s
