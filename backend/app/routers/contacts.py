"""Contatos + ações do chamado atual do contato (mesmos caminhos do Digisac)."""

import re

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .. import avatars, integracao, ticketing
from ..db import get_db
from ..deps import current_user, paginate
from ..models import Contact, Department, Service, Tag, Ticket, User, iso
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
    background: BackgroundTasks,
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
    if filter == "queue":
        # Fila: quem entrou há mais tempo primeiro (mandar outra mensagem não tira o lugar)
        entrada = func.coalesce(Ticket.queued_at, Ticket.started_at)
        query = query.order_by(entrada.asc(), Contact.name)
    else:
        query = query.order_by(Contact.last_message_at.is_(None), Contact.last_message_at.desc(), Contact.name)
    page_data = paginate(query, page, perPage)
    if filter == "queue":
        _entrada_na_fila(db, page_data["data"])
    _fotos(db, page_data["data"], background)
    return page_data


def _entrada_na_fila(db: Session, contatos: list[dict]) -> None:
    """Põe em cada contato da Fila a hora em que ele entrou na fila (a tela mostra há quanto tempo espera)."""
    ids = [c["currentTicketId"] for c in contatos if c.get("currentTicketId")]
    if not ids:
        return
    linhas = db.query(Ticket.id, Ticket.queued_at, Ticket.started_at).filter(Ticket.id.in_(ids)).all()
    quando = {r.id: iso(r.queued_at or r.started_at) for r in linhas}
    for c in contatos:
        c["queuedAt"] = quando.get(c.get("currentTicketId"))


def _fotos(db: Session, contatos: list[dict], background: BackgroundTasks | None) -> None:
    """Põe o link da foto do perfil e agenda a busca das fotos que faltam (ou têm mais de 7 dias)."""
    ids = [c["id"] for c in contatos]
    if not ids:
        return
    linhas = (
        db.query(Contact.id, Contact.jid, Contact.avatar_path, Contact.avatar_checked_at, Service.type)
        .join(Service, Service.id == Contact.service_id)
        .filter(Contact.id.in_(ids))
        .all()
    )
    avatars.attach_avatars(contatos, {r.id: r.avatar_path for r in linhas})
    if background is not None:
        faltando = [r.id for r in linhas if r.type == "whatsapp" and avatars.needs_refresh(r)][:20]
        if faltando:
            background.add_task(avatars.refresh_many, faltando)


@router.get("/{contact_id}")
def get_contact(
    contact_id: str,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    contact = _get_contact(db, user, contact_id)
    data = contact.to_dict()
    ticket = ticketing.current_ticket(db, contact)
    data["currentTicket"] = ticket.to_dict() if ticket else None
    _fotos(db, [data], background)
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
    if integracao.eh_integracao(user):
        # Outro sistema (como no Digisac): número já cadastrado devolve o contato que existe
        contact.number = _so_digitos(contact.number)
        filtros = [Contact.number == contact.number]
        if service.type == "whatsapp":
            filtros.append(Contact.jid == f"{contact.number}@s.whatsapp.net")
        existente = db.query(Contact).filter(Contact.service_id == service.id, or_(*filtros)).first()
        if existente:
            return JSONResponse(status_code=200, content=existente.to_dict())
    if db.query(Contact).filter(Contact.service_id == service.id, Contact.number == contact.number).first():
        raise HTTPException(422, detail={"message": "Já existe um contato com esse número nessa conexão"})
    contact.name = contact.name or contact.number
    db.add(contact)
    db.commit()
    await emit(user.account_id, "contact.created", contact.to_dict())
    return contact.to_dict()


def _so_digitos(numero) -> str:
    d = re.sub(r"\D", "", str(numero or ""))
    # Número brasileiro sem o 55 (ex.: "(16) 99145-2133" num contato salvo sem código do país)
    if len(d) in (10, 11) and not d.startswith("55"):
        d = "55" + d
    return d


@router.post("/start")
async def start_conversation(body: dict = Body(...), db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Conversar com um número (ex.: um contato que o cliente mandou): acha o contato nessa
    conexão pelo número ou cria um novo. A mensagem só sai quando o atendente escrever."""
    service = (
        db.query(Service)
        .filter(Service.account_id == user.account_id, Service.id == body.get("serviceId"), Service.archived_at.is_(None))
        .first()
    )
    if not service:
        raise HTTPException(422, detail={"message": "Conexão não encontrada"})
    numero = _so_digitos(body.get("number"))
    if not 10 <= len(numero) <= 15:
        raise HTTPException(422, detail={"message": "Número inválido"})
    filtros = [Contact.number == numero]
    if service.type == "whatsapp":
        filtros.append(Contact.jid == f"{numero}@s.whatsapp.net")
    contact = db.query(Contact).filter(Contact.service_id == service.id, or_(*filtros)).first()
    criado = contact is None
    if criado:
        nome = str(body.get("name") or "").strip()[:200]
        contact = Contact(account_id=user.account_id, service_id=service.id, number=numero, name=nome or numero)
        db.add(contact)
        db.commit()
        await emit(user.account_id, "contact.created", contact.to_dict())
    return {**contact.to_dict(), "created": criado}


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
    contact.unread_since = None
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
