"""Contatos + ações do chamado atual do contato (mesmos caminhos do Digisac)."""

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import ticketing
from ..db import get_db
from ..deps import current_user, paginate
from ..models import Contact, Department, Service, Tag, Ticket, User
from ..realtime import emit

router = APIRouter(prefix="/contacts", tags=["contacts"])


def _where(request: Request, name: str) -> str | None:
    """Aceita `?campo=` e o formato do Digisac `?where[campo]=`."""
    return request.query_params.get(name) or request.query_params.get(f"where[{name}]")


def _visible_ticket_filter(query, user: User):
    if user.is_admin:
        return query
    dep_ids = [d.id for d in user.departments]
    return query.filter(or_(Ticket.user_id == user.id, Ticket.department_id.in_(dep_ids)))


def _get_contact(db: Session, user: User, contact_id: str) -> Contact:
    contact = db.query(Contact).filter(Contact.account_id == user.account_id, Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(404, detail={"message": "Contato não encontrado"})
    return contact


async def _emit_all(account_id: str, events):
    for name, payload in events:
        await emit(account_id, name, payload)


@router.get("")
def list_contacts(
    request: Request,
    page: int = 1,
    perPage: int = 40,
    q: str | None = None,
    filter: str = "all",  # all | open | mine | queue
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    query = db.query(Contact).filter(Contact.account_id == user.account_id)
    service_id = _where(request, "serviceId")
    if service_id:
        query = query.filter(Contact.service_id == service_id)
    number = _where(request, "data.number") or _where(request, "number")
    if number:
        query = query.filter(Contact.number == number)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Contact.name.ilike(like), Contact.internal_name.ilike(like), Contact.number.ilike(like)))
    if filter in ("open", "mine", "queue"):
        query = query.join(Ticket, Ticket.id == Contact.current_ticket_id).filter(Ticket.is_open.is_(True))
        if filter == "mine":
            query = query.filter(Ticket.user_id == user.id)
        elif filter == "queue":
            query = _visible_ticket_filter(query.filter(Ticket.user_id.is_(None)), user)
        else:
            query = _visible_ticket_filter(query, user)
    query = query.order_by(Contact.last_message_at.is_(None), Contact.last_message_at.desc(), Contact.name)
    return paginate(query, page, perPage)


@router.get("/{contact_id}")
def get_contact(contact_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    contact = _get_contact(db, user, contact_id)
    data = contact.to_dict()
    ticket = ticketing.current_ticket(db, contact)
    data["currentTicket"] = ticket.to_dict() if ticket else None
    return data


def _apply_contact(db: Session, contact: Contact, body: dict, user: User):
    for key, attr in {"name": "name", "internalName": "internal_name", "note": "note", "blocked": "blocked"}.items():
        if key in body:
            setattr(contact, attr, body[key])
    data = body.get("data") or {}
    if "number" in body or "number" in data:
        contact.number = (body.get("number") or data.get("number") or "").strip() or None
    if "email" in body or "email" in data:
        contact.email = body.get("email") or data.get("email")
    if "tagIds" in body:
        contact.tags = db.query(Tag).filter(Tag.account_id == user.account_id, Tag.id.in_(body["tagIds"] or [])).all()


@router.post("", status_code=201)
async def create_contact(body: dict = Body(...), db: Session = Depends(get_db), user: User = Depends(current_user)):
    service = db.query(Service).filter(Service.account_id == user.account_id, Service.id == body.get("serviceId")).first()
    if not service:
        raise HTTPException(422, detail={"message": "Informe a conexão (serviceId)"})
    contact = Contact(account_id=user.account_id, service_id=service.id)
    _apply_contact(db, contact, body, user)
    if not contact.number:
        raise HTTPException(422, detail={"message": "Informe o número"})
    if db.query(Contact).filter(Contact.service_id == service.id, Contact.number == contact.number).first():
        raise HTTPException(422, detail={"message": "Já existe um contato com esse número nessa conexão"})
    contact.name = contact.name or contact.number
    db.add(contact)
    db.commit()
    await emit(user.account_id, "contact.created", contact.to_dict())
    return contact.to_dict()


@router.put("/{contact_id}")
async def update_contact(contact_id: str, body: dict = Body(...), db: Session = Depends(get_db), user: User = Depends(current_user)):
    contact = _get_contact(db, user, contact_id)
    _apply_contact(db, contact, body, user)
    db.commit()
    await emit(user.account_id, "contact.updated", contact.to_dict())
    return contact.to_dict()


@router.delete("/{contact_id}")
async def delete_contact(contact_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not user.is_admin:
        raise HTTPException(403, detail={"message": "Apenas administradores"})
    contact = _get_contact(db, user, contact_id)
    data = contact.to_dict()
    db.delete(contact)
    db.commit()
    await emit(user.account_id, "contact.destroyed", data)
    return True


@router.post("/{contact_id}/mark-read")
async def mark_read(contact_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    contact = _get_contact(db, user, contact_id)
    contact.unread = 0
    db.commit()
    await emit(user.account_id, "contact.updated", contact.to_dict())
    return True


@router.post("/{contact_id}/ticket/open")
async def open_ticket(contact_id: str, body: dict = Body(default={}), db: Session = Depends(get_db), user: User = Depends(current_user)):
    contact = _get_contact(db, user, contact_id)
    ticket, events = ticketing.open_ticket(
        db, contact, origin="manual", user=user, department_id=body.get("departmentId")
    )
    db.commit()
    await _emit_all(user.account_id, events + [("contact.updated", contact.to_dict())])
    return ticket.to_dict()


@router.post("/{contact_id}/ticket/transfer")
async def transfer_ticket(contact_id: str, body: dict = Body(...), db: Session = Depends(get_db), user: User = Depends(current_user)):
    contact = _get_contact(db, user, contact_id)
    dep_id = body.get("departmentId")
    if dep_id and not db.query(Department).filter(Department.account_id == user.account_id, Department.id == dep_id).first():
        raise HTTPException(422, detail={"message": "Departamento inválido"})
    target_id = body.get("userId")
    if target_id and not db.query(User).filter(User.account_id == user.account_id, User.id == target_id).first():
        raise HTTPException(422, detail={"message": "Atendente inválido"})
    try:
        ticket, events = ticketing.transfer_ticket(db, contact, user, dep_id, target_id, body.get("comments"))
    except ValueError as e:
        raise HTTPException(422, detail={"message": str(e)})
    db.commit()
    await _emit_all(user.account_id, events)
    return ticket.to_dict()


@router.post("/{contact_id}/ticket/close")
async def close_ticket(contact_id: str, body: dict = Body(default={}), db: Session = Depends(get_db), user: User = Depends(current_user)):
    contact = _get_contact(db, user, contact_id)
    try:
        _ticket, events = ticketing.close_ticket(db, contact, user, body.get("ticketTopicIds"), body.get("comments"))
    except ValueError as e:
        raise HTTPException(422, detail={"message": str(e)})
    db.commit()
    await _emit_all(user.account_id, events)
    return True
