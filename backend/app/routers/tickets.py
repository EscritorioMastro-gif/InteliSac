from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user, paginate
from ..models import Ticket, TicketTransfer, User

router = APIRouter(prefix="/tickets", tags=["tickets"])


def _where(request: Request, name: str) -> str | None:
    return request.query_params.get(name) or request.query_params.get(f"where[{name}]")


@router.get("")
def list_tickets(
    request: Request,
    page: int = 1,
    perPage: int = 40,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    query = db.query(Ticket).filter(Ticket.account_id == user.account_id)
    is_open = _where(request, "isOpen")
    if is_open is not None:
        query = query.filter(Ticket.is_open.is_(is_open.lower() == "true"))
    for field, col in (("contactId", Ticket.contact_id), ("departmentId", Ticket.department_id), ("userId", Ticket.user_id)):
        value = _where(request, field)
        if value:
            query = query.filter(col == value)
    protocol = _where(request, "protocol")
    if protocol:
        query = query.filter(Ticket.protocol == protocol)
    return paginate(query.order_by(Ticket.started_at.desc()), page, perPage)


@router.get("/{ticket_id}")
def get_ticket(ticket_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ticket = db.query(Ticket).filter(Ticket.account_id == user.account_id, Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(404, detail={"message": "Chamado não encontrado"})
    data = ticket.to_dict()
    data["transfers"] = [
        t.to_dict()
        for t in db.query(TicketTransfer).filter(TicketTransfer.ticket_id == ticket.id).order_by(TicketTransfer.created_at)
    ]
    return data
