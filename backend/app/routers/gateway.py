"""Integração com o whatsapp-gateway (WhatsApp por QR code).

- POST /gateway/events          eventos vindos do gateway (status/QR e mensagens), em tempo real
- POST /services/{id}/start     inicia a conexão (gera QR code se ainda não estiver pareado)
- POST /services/{id}/logout    desconecta o aparelho (será preciso ler o QR de novo)
- GET  /services/{id}/connection  estado atual direto do gateway
"""

import hmac
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import ticketing
from ..channels.gateway_client import GatewayError, gateway_request
from ..config import settings
from ..db import get_db
from ..deps import admin_user, current_user
from ..models import Message, Service, User, iso, now
from ..realtime import emit

router = APIRouter(tags=["whatsapp"])


def _check_secret(request: Request) -> None:
    given = request.headers.get("X-Gateway-Secret", "")
    if not settings.gateway_secret or not hmac.compare_digest(given, settings.gateway_secret):
        raise HTTPException(401, detail={"message": "Gateway não autorizado"})


def _apply_status(service: Service, ev: dict) -> None:
    status = ev.get("status") or "disconnected"
    service.data = {
        **(service.data or {}),
        "status": status,
        "qrCode": ev.get("qr") if status == "qr" else None,
        "reason": ev.get("reason"),
        "me": ev.get("me"),
        "statusAt": iso(now()),
    }
    service.is_connected = status == "connected"


@router.post("/gateway/events")
async def gateway_events(request: Request, ev: dict = Body(...), db: Session = Depends(get_db)):
    _check_secret(request)
    service = db.get(Service, ev.get("serviceId") or "")
    if not service or service.type != "whatsapp":
        # 404 faz o gateway descartar o evento (conexão apagada ou de outro tipo)
        raise HTTPException(404, detail={"message": "Conexão não encontrada"})

    if ev.get("type") == "status":
        _apply_status(service, ev)
        db.commit()
        await emit(service.account_id, "service.updated", service.to_dict())
        return {"ok": True}

    if ev.get("type") == "message":
        m = ev.get("message") or {}
        ext_id = m.get("id")
        if ext_id and db.query(Message.id).filter(Message.service_id == service.id, Message.external_id == ext_id).first():
            return {"ok": True, "duplicate": True}
        try:
            contact, events = ticketing.find_or_create_contact(
                db, service, number=m.get("number"), name=m.get("pushName"), jid=m.get("jid")
            )
        except ValueError:
            return {"ok": False, "ignored": "sem identificador"}
        if contact.blocked and not m.get("fromMe"):
            db.commit()
            return {"ok": True, "ignored": "contato bloqueado"}
        data = {}
        if m.get("timestamp"):
            data["sentAt"] = datetime.fromtimestamp(int(m["timestamp"]), tz=timezone.utc).isoformat()
        if m.get("fromMe"):
            data["origin"] = "device"  # enviada pelo celular ou outro aparelho conectado (ex.: Digisac)
        msg, evs = ticketing.register_message(
            db,
            contact,
            m.get("text") or "",
            is_from_me=bool(m.get("fromMe")),
            msg_type=m.get("type") or "chat",
            external_id=ext_id,
            data=data,
            # Enviada pelo celular/Digisac sem chamado aberto: só histórico, não abre chamado.
            open_if_needed=not m.get("fromMe"),
        )
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return {"ok": True, "duplicate": True}
        for name, payload in events + evs:
            await emit(service.account_id, name, payload)
        return {"ok": True, "messageId": msg.id}

    raise HTTPException(422, detail={"message": "Tipo de evento desconhecido"})


def _get_whatsapp_service(db: Session, user: User, service_id: str) -> Service:
    service = db.query(Service).filter(Service.account_id == user.account_id, Service.id == service_id).first()
    if not service:
        raise HTTPException(404, detail={"message": "Conexão não encontrada"})
    if service.type != "whatsapp":
        raise HTTPException(422, detail={"message": "Só conexões WhatsApp (QR code) usam essa ação"})
    return service


@router.post("/services/{service_id}/start")
async def start_service(service_id: str, db: Session = Depends(get_db), user: User = Depends(admin_user)):
    service = _get_whatsapp_service(db, user, service_id)
    try:
        state = await gateway_request("POST", f"/sessions/{service.id}/start", {})
    except GatewayError as e:
        raise HTTPException(e.status if e.status < 500 else 503, detail={"message": str(e)})
    return state


@router.post("/services/{service_id}/logout")
async def logout_service(service_id: str, db: Session = Depends(get_db), user: User = Depends(admin_user)):
    service = _get_whatsapp_service(db, user, service_id)
    try:
        await gateway_request("POST", f"/sessions/{service.id}/logout", {})
    except GatewayError as e:
        raise HTTPException(e.status if e.status < 500 else 503, detail={"message": str(e)})
    _apply_status(service, {"status": "disconnected", "reason": "logged_out"})
    db.commit()
    await emit(service.account_id, "service.updated", service.to_dict())
    return service.to_dict()


@router.get("/services/{service_id}/connection")
async def connection_state(service_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    service = _get_whatsapp_service(db, user, service_id)
    try:
        return await gateway_request("GET", f"/sessions/{service.id}")
    except GatewayError as e:
        return {"serviceId": service.id, "status": "offline", "message": str(e)}
