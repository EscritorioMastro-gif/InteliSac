"""Integração com o whatsapp-gateway (WhatsApp por QR code).

- POST /gateway/events          eventos vindos do gateway (status/QR e mensagens), em tempo real
- POST /services/{id}/start     inicia a conexão (gera QR code se ainda não estiver pareado)
- POST /services/{id}/logout    desconecta o aparelho (será preciso ler o QR de novo)
- GET  /services/{id}/connection  estado atual direto do gateway
"""

import base64
import hmac
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import avatars, storage, ticketing
from .messages import aplicar_edicao as messages_aplicar_edicao
from .messages import refresh_preview as messages_refresh_preview
from .messages import resumo as messages_resumo
from .messages import tirar_assinatura as messages_tirar_assinatura
from ..channels.gateway_client import GatewayError, gateway_request
from ..config import settings
from ..db import get_db
from ..deps import admin_user, current_user
from ..models import Contact, Message, Service, User, iso, now
from ..realtime import emit, emit_service

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


ACK_RANK = {"error": 0, "pending": 1, "sent": 2, "delivered": 3, "read": 4, "played": 5}


def _contatos_do_vcard(lista) -> list[dict]:
    """Contatos que o cliente mandou (vCard): nome + números (só dígitos), no máximo 20."""
    out = []
    for c in (lista if isinstance(lista, list) else [])[:20]:
        if not isinstance(c, dict):
            continue
        numeros = []
        for n in (c.get("numbers") or [])[:5]:
            d = "".join(ch for ch in str(n) if ch.isdigit())
            if 8 <= len(d) <= 15 and d not in numeros:
                numeros.append(d)
        nome = str(c.get("name") or "").strip()[:200]
        if numeros or nome:
            out.append({"name": nome or None, "numbers": numeros})
    return out


@router.post("/gateway/events")
async def gateway_events(
    request: Request, background: BackgroundTasks, ev: dict = Body(...), db: Session = Depends(get_db)
):
    _check_secret(request)
    service = db.get(Service, ev.get("serviceId") or "")
    if not service or service.type != "whatsapp":
        # 404 faz o gateway descartar o evento (conexão apagada ou de outro tipo)
        raise HTTPException(404, detail={"message": "Conexão não encontrada"})

    if ev.get("type") == "status":
        _apply_status(service, ev)
        db.commit()
        await emit_service(service)
        return {"ok": True}

    if ev.get("type") == "ack":
        # ✓ enviada, ✓✓ entregue, ✓✓ azul lida/ouvida. Só avança (nunca volta de "lida" para "entregue").
        msg = (
            db.query(Message)
            .filter(Message.service_id == service.id, Message.external_id == (ev.get("messageId") or ""))
            .first()
        )
        novo = ev.get("ack")
        if not msg or novo not in ACK_RANK:
            return {"ok": True, "ignored": "mensagem não encontrada"}
        atual = (msg.data or {}).get("ack")
        if novo == "error":
            avanca = ACK_RANK.get(atual, 0) < ACK_RANK["delivered"]
        else:
            avanca = ACK_RANK[novo] > ACK_RANK.get(atual, 0)
        if not avanca:
            return {"ok": True, "ignored": "status anterior"}
        msg.data = {**(msg.data or {}), "ack": novo}
        db.commit()
        await emit(service.account_id, "message.updated", storage.attach_urls([msg.to_dict()])[0])
        return {"ok": True}

    if ev.get("type") == "revoke":
        # Alguém apagou uma mensagem para todos (o cliente, ou o celular/outro aparelho)
        msg = (
            db.query(Message)
            .filter(Message.service_id == service.id, Message.external_id == (ev.get("messageId") or ""))
            .first()
        )
        if not msg or (msg.data or {}).get("deleted"):
            return {"ok": True, "ignored": "mensagem não encontrada ou já apagada"}
        msg.data = {
            **(msg.data or {}),
            "deleted": True,
            "deletedAt": iso(now()),
            "deletedBy": "device" if ev.get("fromMe") else "contact",
        }
        contact = db.get(Contact, msg.contact_id)
        contato_mudou = messages_refresh_preview(db, contact, msg)
        db.commit()
        await emit(service.account_id, "message.updated", storage.attach_urls([msg.to_dict()])[0])
        if contato_mudou:
            await emit(service.account_id, "contact.updated", contact.to_dict())
        return {"ok": True}

    if ev.get("type") == "edit":
        # Mensagem editada no WhatsApp (pelo cliente, ou pelo celular/outro aparelho)
        msg = (
            db.query(Message)
            .filter(Message.service_id == service.id, Message.external_id == (ev.get("messageId") or ""))
            .first()
        )
        texto = (ev.get("text") or "").strip()
        if not msg or not texto or msg.type == "ticket" or (msg.data or {}).get("deleted"):
            return {"ok": True, "ignored": "mensagem não encontrada"}
        if msg.is_from_me and (msg.data or {}).get("signed"):
            texto = messages_tirar_assinatura(texto)
        if texto == (msg.text or ""):
            return {"ok": True, "ignored": "sem mudança"}  # ex.: a edição feita pelo próprio InteliSac
        contact = db.get(Contact, msg.contact_id)
        contato_mudou = messages_aplicar_edicao(db, contact, msg, texto, por="device" if ev.get("fromMe") else "contact")
        db.commit()
        await emit(service.account_id, "message.updated", storage.attach_urls([msg.to_dict()])[0])
        if contato_mudou:
            await emit(service.account_id, "contact.updated", contact.to_dict())
        return {"ok": True}

    if ev.get("type") == "message":
        m = ev.get("message") or {}
        ext_id = m.get("id")
        if ext_id and db.query(Message.id).filter(Message.service_id == service.id, Message.external_id == ext_id).first():
            return {"ok": True, "duplicate": True}
        grupo = bool(m.get("isGroup"))
        try:
            contact, events = ticketing.find_or_create_contact(
                db,
                service,
                number=None if grupo else m.get("number"),
                name=m.get("groupName") if grupo else m.get("pushName"),
                jid=m.get("jid"),
                is_group=grupo,
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
        if grupo and m.get("sender"):
            s = m["sender"]
            data["sender"] = {"jid": s.get("jid"), "number": s.get("number"), "name": s.get("name")}
        contatos = _contatos_do_vcard(m.get("contacts"))
        if contatos:
            data["contacts"] = contatos  # contato enviado (vCard): a tela oferece "Conversar"

        texto = m.get("text") or ""
        media = m.get("media") or None
        if media and media.get("base64"):
            # Arquivo recebido: guarda no Supabase Storage; a mensagem fica só com a legenda.
            try:
                raw = base64.b64decode(media["base64"])
                mimetype = media.get("mimetype") or "application/octet-stream"
                nome = media.get("fileName") or storage.safe_name(None, mimetype)
                path = storage.object_path(service.account_id, contact.id, nome, mimetype)
                await storage.upload(path, raw, mimetype)
                data["file"] = {"path": path, "mimetype": mimetype, "name": nome, "size": len(raw)}
                texto = m.get("caption") or ""
            except (storage.StorageError, ValueError) as e:
                data["fileError"] = str(e)  # fica o rótulo "[Imagem]" etc. no lugar do arquivo
        elif media and media.get("error"):
            data["fileError"] = media["error"]

        # Resposta citando outra mensagem: liga à mensagem original, se ela estiver no InteliSac
        if m.get("quotedId"):
            orig = (
                db.query(Message)
                .filter(Message.service_id == service.id, Message.external_id == m["quotedId"])
                .first()
            )
            if orig:
                data["replyTo"] = {
                    "id": orig.id, "text": messages_resumo(orig), "fromMe": orig.is_from_me,
                    "userId": orig.user_id, "type": orig.type,
                }
            else:
                data["replyTo"] = {"id": None, "text": (m.get("quotedText") or "Mensagem")[:300], "fromMe": None}

        msg, evs = ticketing.register_message(
            db,
            contact,
            texto,
            is_from_me=bool(m.get("fromMe")),
            msg_type=m.get("type") or "chat",
            external_id=ext_id,
            data=data,
            # Enviada pelo celular/Digisac sem chamado aberto: só histórico, não abre chamado.
            open_if_needed=not m.get("fromMe"),
            preview=m.get("label"),
        )
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return {"ok": True, "duplicate": True}
        # Evento da mensagem nova: com link do arquivo e com os dados para o aviso (som/notificação)
        final = storage.attach_urls([msg.to_dict()])[0] if data.get("file") else msg.to_dict()
        final.update(ticketing.notify_info(db, msg))
        for name, payload in events + evs:
            if name == "message.created" and payload.get("id") == msg.id:
                payload = final
            await emit(service.account_id, name, payload)
        # Foto do perfil: busca em segundo plano para contato novo ou foto com mais de 7 dias
        if avatars.needs_refresh(contact):
            background.add_task(avatars.refresh, contact.id)
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
    await emit_service(service)
    return service.to_dict()


@router.get("/services/{service_id}/connection")
async def connection_state(service_id: str, db: Session = Depends(get_db), user: User = Depends(admin_user)):
    service = _get_whatsapp_service(db, user, service_id)
    try:
        return await gateway_request("GET", f"/sessions/{service.id}")
    except GatewayError as e:
        return {"serviceId": service.id, "status": "offline", "message": str(e)}
