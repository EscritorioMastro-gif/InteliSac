import mimetypes
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from .. import audio, storage, ticketing
from ..channels import get_adapter
from ..channels.base import MediaOut, Quoted, SendResult
from ..db import get_db
from ..deps import current_user
from ..models import Contact, Message, Service, User, iso, now
from ..realtime import emit

router = APIRouter(prefix="/messages", tags=["messages"])

# Canais em que a assinatura com o nome do colaborador vai junto da mensagem
SIGNED_CHANNELS = {"whatsapp", "whatsapp-business"}
# O WhatsApp só aceita "apagar para todos" até ~2 dias e meio depois do envio
REVOKE_LIMIT = timedelta(hours=60)


def signs_messages(service: Service) -> bool:
    """Assinatura ligada por padrão nas conexões de WhatsApp; desliga em Conexões → Editar."""
    return service.type in SIGNED_CHANNELS and (service.data or {}).get("signMessages", True) is not False


def sign(text: str, name: str) -> str:
    nome = (name or "").strip().replace("*", "")
    return f"*{nome}:*\n{text}" if nome else text


def _where(request: Request, name: str) -> str | None:
    return request.query_params.get(name) or request.query_params.get(f"where[{name}]")


def resumo(m: Message) -> str:
    """Texto curto de uma mensagem para a citação (texto, legenda ou rótulo do arquivo)."""
    if m.text:
        return m.text[:300]
    f = (m.data or {}).get("file") or {}
    if m.type == "document":
        return f"[Documento] {f.get('name') or ''}".strip()
    return storage.LABELS.get(m.type, "[Mensagem]")


def _contato_para_envio(db: Session, user: User, contact_id: str | None) -> tuple[Contact, Service]:
    contact = db.query(Contact).filter(Contact.account_id == user.account_id, Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(404, detail={"message": "Contato não encontrado"})
    if contact.blocked:
        raise HTTPException(422, detail={"message": "Contato bloqueado"})
    return contact, db.get(Service, contact.service_id)


def _citacao(db: Session, contact: Contact, reply_to_id: str | None) -> tuple[Quoted | None, dict | None]:
    """Mensagem que está sendo respondida: o que vai para o canal e o que fica salvo."""
    if not reply_to_id:
        return None, None
    q = db.query(Message).filter(Message.id == reply_to_id, Message.contact_id == contact.id).first()
    if not q or q.type == "ticket":
        raise HTTPException(422, detail={"message": "Mensagem citada não encontrada nesta conversa"})
    if (q.data or {}).get("deleted"):
        raise HTTPException(422, detail={"message": "Não dá para responder uma mensagem apagada"})
    texto = resumo(q)
    remetente = (q.data or {}).get("sender") or {}
    salvo = {"id": q.id, "text": texto, "fromMe": q.is_from_me, "userId": q.user_id, "type": q.type}
    if remetente.get("name") or remetente.get("number"):
        salvo["senderName"] = remetente.get("name") or remetente.get("number")
    canal = (
        Quoted(id=q.external_id, from_me=q.is_from_me, text=texto, participant=None if q.is_from_me else remetente.get("jid"))
        if q.external_id
        else None
    )
    return canal, salvo


def _guardar_jid(db: Session, contact: Contact, result: SendResult) -> None:
    jid = result.extra.get("jid")
    if jid and not contact.jid and not (
        db.query(Contact.id).filter(Contact.service_id == contact.service_id, Contact.jid == jid).first()
    ):
        contact.jid = jid


async def _emitir(user: User, events, msg: Message) -> dict:
    final = storage.attach_urls([msg.to_dict()])[0]
    for name, payload in events:
        if name == "message.created" and payload["id"] == msg.id:
            payload = final
        await emit(user.account_id, name, payload)
    return final


@router.get("")
def list_messages(
    request: Request,
    page: int = 1,
    perPage: int = 50,
    latest: bool = True,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Mensagens de um contato/chamado. Com latest=true (padrão) a página 1 traz as mais
    recentes, sempre devolvidas em ordem cronológica. Arquivos vêm com fileUrl/downloadUrl
    (links assinados que expiram em 1 h)."""
    query = db.query(Message).filter(Message.account_id == user.account_id)
    contact_id = _where(request, "contactId")
    ticket_id = _where(request, "ticketId")
    if not contact_id and not ticket_id:
        raise HTTPException(422, detail={"message": "Informe contactId ou ticketId"})
    if contact_id:
        query = query.filter(Message.contact_id == contact_id)
    if ticket_id:
        query = query.filter(Message.ticket_id == ticket_id)
    per_page = max(1, min(perPage, 200))
    total = query.count()
    order = Message.created_at.desc() if latest else Message.created_at.asc()
    rows = query.order_by(order).offset((max(page, 1) - 1) * per_page).limit(per_page).all()
    if latest:
        rows.reverse()
    return {
        "data": storage.attach_urls([m.to_dict() for m in rows]),
        "total": total,
        "limit": per_page,
        "currentPage": page,
        "lastPage": max(1, -(-total // per_page)),
    }


@router.post("", status_code=201)
async def send_message(body: dict = Body(...), db: Session = Depends(get_db), user: User = Depends(current_user)):
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(422, detail={"message": "Mensagem vazia"})
    contact, service = _contato_para_envio(db, user, body.get("contactId"))
    quoted, reply = _citacao(db, contact, body.get("replyToId"))

    # Assinatura: o cliente recebe "*Nome:*" + texto (como no Digisac). No InteliSac fica o
    # texto original; o nome do colaborador aparece em cima da mensagem.
    assinar = signs_messages(service)
    texto_enviado = sign(text, user.name) if assinar else text

    # Envia primeiro (fora de transação de escrita) e depois registra, já com o id do canal.
    result = await get_adapter(service.type).send_text(service, contact, texto_enviado, quoted=quoted)
    _guardar_jid(db, contact, result)
    data = {"signed": True} if assinar else {}
    if reply:
        data["replyTo"] = reply
    if result.ok:
        data["ack"] = "sent"  # ✓ (depois o WhatsApp avisa entregue ✓✓ e lida ✓✓ azul)
    else:
        data["error"] = result.error
    msg, events = ticketing.register_message(
        db, contact, text, is_from_me=True, user=user, external_id=result.external_id, data=data
    )
    db.commit()
    return await _emitir(user, events, msg)


@router.post("/media", status_code=201)
async def send_media(
    contactId: str = Form(...),
    caption: str = Form(""),
    replyToId: str = Form(""),
    voice: bool = Form(False),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Envia um arquivo (foto, vídeo, áudio ou documento) com legenda opcional.
    voice=true: áudio gravado no navegador vira mensagem de voz do WhatsApp (OGG/Opus)."""
    contact, service = _contato_para_envio(db, user, contactId)
    quoted, reply = _citacao(db, contact, replyToId or None)
    raw = await file.read()
    if not raw:
        raise HTTPException(422, detail={"message": "Arquivo vazio"})
    if len(raw) > storage.MAX_BYTES:
        raise HTTPException(413, detail={"message": f"Arquivo maior que {storage.MAX_BYTES // (1024 * 1024)} MB"})
    nome = (file.filename or "").strip() or "arquivo"
    mimetype = (
        file.content_type
        if file.content_type and file.content_type != "application/octet-stream"
        else mimetypes.guess_type(nome)[0] or "application/octet-stream"
    )
    caption = (caption or "").strip()
    duracao = None
    onda = None
    if voice:
        try:
            raw = await audio.to_voice_note(raw)
        except audio.AudioError as e:
            raise HTTPException(422, detail={"message": str(e)})
        mimetype = audio.VOICE_MIMETYPE
        nome = f"audio-{now():%Y%m%d-%H%M%S}.ogg"
        duracao = audio.duration_seconds(raw)
        onda = await audio.waveform(raw)
        caption = ""
    kind = storage.media_kind(mimetype)

    path = storage.object_path(user.account_id, contact.id, nome, mimetype)
    try:
        await storage.upload(path, raw, mimetype)
        link = storage.sign_one(path, expires=900)  # o WhatsApp baixa daqui
    except storage.StorageError as e:
        raise HTTPException(502, detail={"message": str(e)})

    # Assinatura: arquivos levam o nome na legenda. Áudio não tem legenda no WhatsApp: o nome
    # vai como texto logo ANTES do áudio ("*Gabriel:*" e em seguida a mensagem de voz).
    assinar = signs_messages(service)
    nome_assin = (user.name or "").strip().replace("*", "")
    if assinar and voice:
        legenda = f"*{nome_assin}:*" if nome_assin else None
    elif assinar:
        legenda = sign(caption, user.name) if caption else (f"*{nome_assin}*" if nome_assin else None)
    else:
        legenda = caption or None

    result = await get_adapter(service.type).send_media(
        service,
        contact,
        MediaOut(
            url=link, mimetype=mimetype, file_name=nome, kind=kind, caption=legenda, ptt=voice,
            seconds=max(1, round(duracao)) if duracao else None, waveform=onda,
        ),
        quoted=quoted,
    )
    _guardar_jid(db, contact, result)
    data = {"file": {"path": path, "mimetype": mimetype, "name": nome, "size": len(raw)}}
    if duracao:
        data["file"]["duration"] = duracao
    if assinar:
        data["signed"] = True
    if reply:
        data["replyTo"] = reply
    if result.ok:
        data["ack"] = "sent"
    else:
        data["error"] = result.error
    msg_type = "ptt" if voice else kind
    msg, events = ticketing.register_message(
        db,
        contact,
        caption,
        is_from_me=True,
        user=user,
        msg_type=msg_type,
        external_id=result.external_id,
        data=data,
        preview=storage.LABELS.get(msg_type, "[Arquivo]") + (f" {nome}" if kind == "document" else ""),
    )
    db.commit()
    return await _emitir(user, events, msg)


@router.delete("/{message_id}")
async def delete_message(message_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Apaga para todos uma mensagem enviada por nós. Quem enviou ou um administrador pode apagar.
    No InteliSac a mensagem continua registrada, marcada como apagada (histórico)."""
    msg = db.query(Message).filter(Message.account_id == user.account_id, Message.id == message_id).first()
    if not msg or msg.type == "ticket":
        raise HTTPException(404, detail={"message": "Mensagem não encontrada"})
    if not msg.is_from_me:
        raise HTTPException(422, detail={"message": "Só dá para apagar mensagens enviadas por nós"})
    if (msg.data or {}).get("deleted"):
        raise HTTPException(422, detail={"message": "Mensagem já apagada"})
    if msg.user_id != user.id and not user.is_admin:
        raise HTTPException(403, detail={"message": "Só quem enviou (ou um administrador) pode apagar"})
    enviada = msg.created_at if msg.created_at.tzinfo else msg.created_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - enviada > REVOKE_LIMIT:
        raise HTTPException(422, detail={"message": "O WhatsApp só permite apagar para todos até cerca de 2 dias e meio depois do envio"})

    contact = db.get(Contact, msg.contact_id)
    service = db.get(Service, msg.service_id)
    if msg.external_id and not (msg.data or {}).get("error"):
        result = await get_adapter(service.type).revoke(service, contact, msg.external_id)
        if not result.ok:
            raise HTTPException(502, detail={"message": result.error or "Não consegui apagar no WhatsApp"})
    msg.data = {**(msg.data or {}), "deleted": True, "deletedAt": iso(now()), "deletedBy": user.id}
    contato_mudou = refresh_preview(db, contact, msg)
    db.commit()
    final = storage.attach_urls([msg.to_dict()])[0]
    await emit(user.account_id, "message.updated", final)
    if contato_mudou:
        await emit(user.account_id, "contact.updated", contact.to_dict())
    return final


def refresh_preview(db: Session, contact: Contact, msg: Message) -> bool:
    """Se a mensagem apagada era a última da conversa, a prévia da lista vira "[Mensagem apagada]"."""
    ultima = (
        db.query(Message)
        .filter(Message.contact_id == contact.id, Message.type != "ticket")
        .order_by(Message.created_at.desc())
        .first()
    )
    if ultima and ultima.id == msg.id:
        contact.last_message = "[Mensagem apagada]"
        return True
    return False
