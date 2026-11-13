"""Entrada de mensagens dos canais.

- POST /channels/{serviceId}/webhook  — chamado pelo provedor do canal (header X-Channel-Token).
- POST /simulator/inbound            — usado pela tela Simulador (usuário logado) para fingir
                                       ser um cliente mandando mensagem.
"""

import hmac

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import ticketing
from ..db import get_db
from ..deps import current_user
from ..models import Service, User
from ..realtime import emit

router = APIRouter(tags=["channels"])


async def _receive(db: Session, service: Service, body: dict) -> dict:
    number = str(body.get("from") or "").strip()
    text = (body.get("text") or "").strip()
    if not number or not text:
        raise HTTPException(422, detail={"message": "Campos obrigatórios: from, text"})
    contact, events = ticketing.find_or_create_contact(db, service, number, body.get("name"))
    if contact.blocked:
        db.commit()
        return {"ignored": "contato bloqueado"}
    msg, evs = ticketing.register_message(
        db, contact, text, is_from_me=False, msg_type=body.get("type") or "chat", external_id=body.get("externalId")
    )
    db.commit()
    final = {**msg.to_dict(), **ticketing.notify_info(db, msg)}
    for name, payload in events + evs:
        if name == "message.created" and payload.get("id") == msg.id:
            payload = final
        await emit(service.account_id, name, payload)
    return msg.to_dict()


@router.post("/channels/{service_id}/webhook")
async def channel_webhook(service_id: str, request: Request, body: dict = Body(...), db: Session = Depends(get_db)):
    service = db.get(Service, service_id)
    token = request.headers.get("X-Channel-Token", "")
    if not service or service.archived_at is not None or not hmac.compare_digest(token, service.webhook_token):
        raise HTTPException(401, detail={"message": "Conexão ou token inválido"})
    return await _receive(db, service, body)


@router.post("/simulator/inbound")
async def simulator_inbound(body: dict = Body(...), db: Session = Depends(get_db), user: User = Depends(current_user)):
    service = (
        db.query(Service)
        .filter(Service.account_id == user.account_id, Service.id == body.get("serviceId"))
        .first()
    )
    if not service:
        raise HTTPException(404, detail={"message": "Conexão não encontrada"})
    return await _receive(db, service, body)
