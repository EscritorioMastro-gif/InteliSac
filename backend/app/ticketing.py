"""Regras de atendimento: abrir, transferir e fechar chamados; registrar mensagens.

Cada função devolve a lista de eventos socket a emitir depois do commit
(`[(evento, payload), ...]`), para que a rota faça `await emit(...)`.
"""

from sqlalchemy import update
from sqlalchemy.orm import Session

from .models import (
    Account,
    Contact,
    Department,
    Message,
    Service,
    Ticket,
    TicketTopic,
    TicketTransfer,
    User,
    now,
)

Events = list[tuple[str, dict]]


def _next_protocol(db: Session, account: Account) -> str:
    # Incremento atômico no banco: dois chamados abertos ao mesmo tempo não repetem protocolo.
    seq = db.execute(
        update(Account)
        .where(Account.id == account.id)
        .values(ticket_seq=Account.ticket_seq + 1)
        .returning(Account.ticket_seq)
    ).scalar_one()
    return f"{now():%Y%m%d}{seq:05d}"


def _default_department(db: Session, account: Account) -> str | None:
    if account.default_department_id:
        return account.default_department_id
    dep = (
        db.query(Department)
        .filter(Department.account_id == account.id, Department.archived_at.is_(None))
        .order_by(Department.created_at)
        .first()
    )
    return dep.id if dep else None


def _ticket_event_message(db: Session, contact: Contact, ticket: Ticket, text: str, user: User | None) -> Message:
    msg = Message(
        account_id=contact.account_id,
        contact_id=contact.id,
        ticket_id=ticket.id,
        service_id=contact.service_id,
        user_id=user.id if user else None,
        type="ticket",
        text=text,
        is_from_me=True,
    )
    db.add(msg)
    return msg


def current_ticket(db: Session, contact: Contact) -> Ticket | None:
    if not contact.current_ticket_id:
        return None
    ticket = db.get(Ticket, contact.current_ticket_id)
    return ticket if ticket and ticket.is_open else None


def open_ticket(
    db: Session,
    contact: Contact,
    origin: str,
    user: User | None = None,
    department_id: str | None = None,
) -> tuple[Ticket, Events]:
    """Abre um chamado se o contato não tiver um aberto. Devolve (chamado, eventos)."""
    existing = current_ticket(db, contact)
    if existing:
        return existing, []
    account = db.get(Account, contact.account_id)
    inicio = now()
    ticket = Ticket(
        account_id=contact.account_id,
        contact_id=contact.id,
        department_id=department_id or _default_department(db, account),
        user_id=user.id if user else None,
        protocol=_next_protocol(db, account),
        origin=origin,
        is_open=True,
        started_at=inicio,
        queued_at=inicio,
    )
    db.add(ticket)
    db.flush()
    contact.current_ticket_id = ticket.id
    if user:
        texto = f"Chamado {ticket.protocol} aberto por {user.name}"
    elif origin == "contact":
        texto = f"Chamado {ticket.protocol} aberto pelo cliente"
    else:
        texto = f"Chamado {ticket.protocol} aberto"
    msg = _ticket_event_message(db, contact, ticket, texto, user)
    db.flush()
    return ticket, [("ticket.created", ticket.to_dict()), ("message.created", msg.to_dict())]


def register_message(
    db: Session,
    contact: Contact,
    text: str,
    is_from_me: bool,
    user: User | None = None,
    msg_type: str = "chat",
    external_id: str | None = None,
    data: dict | None = None,
    count_unread: bool = True,
    open_if_needed: bool = True,
    preview: str | None = None,
) -> tuple[Message, Events]:
    """Grava uma mensagem, abrindo chamado quando necessário (regra do Digisac).

    Mensagem do cliente sem chamado abre chamado na fila. Mensagem enviada por um
    atendente sem chamado abre chamado automático com ele. Com open_if_needed=False
    (mensagens enviadas pelo celular/outro aparelho, ex.: disparos do Digisac) a
    mensagem só entra no histórico, sem abrir chamado."""
    events: Events = []
    ticket = current_ticket(db, contact)
    if ticket is None and open_if_needed:
        origin = "automatic" if is_from_me else "contact"
        ticket, evs = open_ticket(db, contact, origin=origin, user=user if is_from_me else None)
        events += evs
    elif ticket is not None and is_from_me and user and ticket.user_id is None:
        # Atendente respondeu um chamado que estava na fila: assume o chamado.
        ticket.user_id = user.id
        events.append(("ticket.updated", ticket.to_dict()))

    msg = Message(
        account_id=contact.account_id,
        contact_id=contact.id,
        ticket_id=ticket.id if ticket else None,
        service_id=contact.service_id,
        user_id=user.id if (is_from_me and user) else None,
        type=msg_type,
        text=text,
        is_from_me=is_from_me,
        external_id=external_id,
        data=data or {},
    )
    db.add(msg)
    stamp = now()
    if ticket:
        ticket.last_message_at = stamp
    contact.last_message_at = stamp
    # prévia na lista de conversas: o texto/legenda, ou "[Imagem]", "[Documento] x.pdf"...
    contact.last_message = text or preview or ""
    if not is_from_me and count_unread:
        if not contact.unread or contact.unread_since is None:
            contact.unread_since = stamp
        contact.unread = (contact.unread or 0) + 1
    db.flush()
    events.append(("message.created", msg.to_dict()))
    if ticket:
        events.append(("ticket.updated", ticket.to_dict()))
    events.append(("contact.updated", contact.to_dict()))
    return msg, events


def transfer_ticket(
    db: Session,
    contact: Contact,
    by_user: User,
    department_id: str | None,
    user_id: str | None,
    comments: str | None,
) -> tuple[Ticket, Events]:
    ticket = current_ticket(db, contact)
    if ticket is None:
        raise ValueError("Contato não tem chamado aberto")
    transfer = TicketTransfer(
        ticket_id=ticket.id,
        from_department_id=ticket.department_id,
        to_department_id=department_id or ticket.department_id,
        from_user_id=ticket.user_id,
        to_user_id=user_id,
        by_user_id=by_user.id,
        comments=comments,
    )
    db.add(transfer)
    mesmo_departamento = (department_id or ticket.department_id) == ticket.department_id
    if user_id is None and (ticket.user_id is not None or not mesmo_departamento):
        ticket.queued_at = now()  # entrou (de novo) numa fila: conta a espera a partir de agora
    ticket.department_id = department_id or ticket.department_id
    ticket.user_id = user_id
    dep = db.get(Department, ticket.department_id) if ticket.department_id else None
    target = db.get(User, user_id) if user_id else None
    if target and target.id == by_user.id and mesmo_departamento:
        texto = f"Chamado assumido por {by_user.name}"
    else:
        destino = (dep.name if dep else "sem departamento") + (f" / {target.name}" if target else " (fila)")
        texto = f"Chamado transferido por {by_user.name} para {destino}"
    if comments and comments.strip():
        texto += f" · “{comments.strip()}”"
    msg = _ticket_event_message(db, contact, ticket, texto, by_user)
    db.flush()
    return ticket, [
        ("ticket.updated", ticket.to_dict()),
        ("message.created", msg.to_dict()),
        ("contact.updated", contact.to_dict()),
    ]


def close_ticket(
    db: Session,
    contact: Contact,
    by_user: User,
    topic_ids: list[str] | None = None,
    comments: str | None = None,
) -> tuple[Ticket, Events]:
    ticket = current_ticket(db, contact)
    if ticket is None:
        raise ValueError("Contato não tem chamado aberto")
    if topic_ids:
        ticket.topics = (
            db.query(TicketTopic)
            .filter(TicketTopic.account_id == contact.account_id, TicketTopic.id.in_(topic_ids))
            .all()
        )
    ticket.is_open = False
    ticket.ended_at = now()
    ticket.comments = comments
    if ticket.user_id is None:
        ticket.user_id = by_user.id
    contact.current_ticket_id = None
    contact.unread = 0
    contact.unread_since = None
    texto = f"Chamado {ticket.protocol} fechado por {by_user.name}"
    if ticket.topics:
        texto += " · Assunto: " + ", ".join(t.name for t in ticket.topics)
    msg = _ticket_event_message(db, contact, ticket, texto, by_user)
    db.flush()
    return ticket, [
        ("ticket.updated", ticket.to_dict()),
        ("message.created", msg.to_dict()),
        ("contact.updated", contact.to_dict()),
    ]


def notify_info(db: Session, msg: Message) -> dict:
    """Dados extras do evento message.created, para a tela decidir se avisa o atendente
    (som/notificação): de quem é o chamado e o nome do contato."""
    contact = db.get(Contact, msg.contact_id)
    ticket = db.get(Ticket, msg.ticket_id) if msg.ticket_id else None
    return {
        "contactName": (contact.internal_name or contact.name) if contact else None,
        "ticket": {"userId": ticket.user_id, "departmentId": ticket.department_id} if ticket else None,
    }


def find_or_create_contact(
    db: Session,
    service: Service,
    number: str | None,
    name: str | None = None,
    jid: str | None = None,
    is_group: bool = False,
) -> tuple[Contact, Events]:
    """Acha o contato pelo jid do WhatsApp (ou pelo número) e completa os dados que faltarem.
    Grupos: o "contato" é o próprio grupo (jid @g.us) e o nome acompanha o nome do grupo."""
    if not number and not jid:
        raise ValueError("Contato sem número e sem jid")
    contact = None
    base = db.query(Contact).filter(Contact.service_id == service.id)
    if jid:
        contact = base.filter(Contact.jid == jid).first()
    if contact is None and number:
        contact = base.filter(Contact.number == number).first()
    if contact:
        changed = False
        if jid and not contact.jid:
            contact.jid, changed = jid, True
        if number and not contact.number:
            contact.number, changed = number, True
        if name and (not contact.name or contact.name == contact.number or (is_group and contact.name != name)):
            contact.name, changed = name, True
        if is_group and not contact.is_group:
            contact.is_group, changed = True, True
        return contact, ([("contact.updated", contact.to_dict())] if changed else [])
    contact = Contact(
        account_id=service.account_id,
        service_id=service.id,
        number=number,
        jid=jid,
        name=name or number or ("Grupo" if is_group else "Contato"),
        is_group=is_group,
    )
    db.add(contact)
    db.flush()
    return contact, [("contact.created", contact.to_dict())]
