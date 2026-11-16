"""Ferramentas de texto para quem está escrevendo (botão "Corrigir meu texto")."""

from fastapi import APIRouter, Body, Depends, HTTPException

from .. import corretor
from ..deps import current_user
from ..models import User

router = APIRouter(prefix="/text", tags=["text"])


@router.post("/correct")
async def corrigir_texto(body: dict = Body(...), user: User = Depends(current_user)):
    """Corrige ortografia e pontuação (português do Brasil). Devolve o texto corrigido e o que mudou."""
    try:
        return await corretor.corrigir(str(body.get("text") or ""))
    except corretor.CorretorError as e:
        raise HTTPException(503, detail={"message": str(e)})
