"""Painel em tempo real (no Digisac: /now/resume e /now/departments-resume)."""

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models import Department, Ticket, User, now

router = APIRouter(prefix="/now", tags=["now"])


@router.get("/resume")
def resume(db: Session = Depends(get_db), user: User = Depends(current_user)):
    acc = user.account_id
    open_q = db.query(Ticket).filter(Ticket.account_id == acc, Ticket.is_open.is_(True))
    today = now().replace(hour=0, minute=0, second=0, microsecond=0)
    closed_today = (
        db.query(Ticket)
        .filter(Ticket.account_id == acc, Ticket.is_open.is_(False), Ticket.ended_at >= today)
        .count()
    )
    by_dep = dict(
        db.query(Ticket.department_id, func.count(Ticket.id))
        .filter(Ticket.account_id == acc, Ticket.is_open.is_(True))
        .group_by(Ticket.department_id)
        .all()
    )
    by_user = dict(
        db.query(Ticket.user_id, func.count(Ticket.id))
        .filter(Ticket.account_id == acc, Ticket.is_open.is_(True), Ticket.user_id.isnot(None))
        .group_by(Ticket.user_id)
        .all()
    )
    deps = db.query(Department).filter(Department.account_id == acc, Department.archived_at.is_(None)).order_by(Department.name)
    users = db.query(User).filter(User.account_id == acc, User.archived_at.is_(None)).order_by(User.name)
    return {
        "openTickets": open_q.count(),
        "queueTickets": open_q.filter(Ticket.user_id.is_(None)).count(),
        "myTickets": open_q.filter(Ticket.user_id == user.id).count(),
        "closedToday": closed_today,
        "departments": [{"id": d.id, "name": d.name, "open": by_dep.get(d.id, 0)} for d in deps],
        "users": [{"id": u.id, "name": u.name, "status": u.status, "open": by_user.get(u.id, 0)} for u in users],
    }
