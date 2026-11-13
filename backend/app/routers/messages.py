from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import ticketing
from ..channels import get_adapter
from ..db import get_db
from ..deps import current_user
from ..models import Contact, Message, Service, User
from ..realtime import emit

router = APIRouter(prefix="/messages", tags=["messages"])

# Canais em que a assinatura com o nome do colaborador vai junto da mensagem
SIGNED_CHANNELS = {"whatsapp", "whatsapp-business"}


def signs_messages(service: Service) -> bool:
    """Assinatura ligada por padrão nas conexões de WhatsApp; desliga em Conexões → Editar."""
    return service.type in SIGNED_CHANNELS and (service.data or {}).get("signMessages", True) is not False


def sign(text: str, name: str) -> str:
    nome = (name or "").strip().replace("*", "")
    return f"*{nome}:*\n{text}" if nome else text


def _where(request: Request, name: str) -> str | None:
    return request.query_params.get(name) or request.query_params.get(f"where[{name}]")


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
    recentes, sempre devolvidas em ordem cronológica."""
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
        "data": [m.to_dict() for m in rows],
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
    contact = (
        db.query(Contact)
        .filter(Contact.account_id == user.account_id, Contact.id == body.get("contactId"))
        .first()
    )
    if not contact:
        raise HTTPException(404, detail={"message": "Contato não encontrado"})
    if contact.blocked:
        raise HTTPException(422, detail={"message": "Contato bloqueado"})
    service = db.get(Service, contact.service_id)

    # Assinatura: o cliente recebe "*Nome:*" + texto (como no Digisac). No InteliSac fica o
    # texto original; o nome do colaborador aparece em cima da mensagem.
    assinar = signs_messages(service)
    texto_enviado = sign(text, user.name) if assinar else text

    # Envia primeiro (fora de transação de escrita) e depois registra, já com o id do canal.
    result = await get_adapter(service.type).send_text(service, contact, texto_enviado)
    jid = result.extra.get("jid")
    if jid and not contact.jid and not (
        db.query(Contact.id).filter(Contact.service_id == contact.service_id, Contact.jid == jid).first()
    ):
        contact.jid = jid
    data = {"signed": True} if assinar else {}
    if not result.ok:
        data["error"] = result.error
    msg, events = ticketing.register_message(
        db,
        contact,
        text,
        is_from_me=True,
        user=user,
        external_id=result.external_id,
        data=data,
    )
    db.commit()
    final = msg.to_dict()
    for name, payload in events:
        if name == "message.created" and payload["id"] == msg.id:
            payload = final
        await emit(user.account_id, name, payload)
    return final
