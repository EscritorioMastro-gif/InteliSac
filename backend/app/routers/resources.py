"""Cadastros simples gerados pela fábrica genérica (crud.make_crud_router)."""

from fastapi import HTTPException

from .. import supabase_auth
from ..config import settings
from ..crud import make_crud_router
from ..models import (
    SERVICE_TYPES,
    Department,
    QuickReply,
    Role,
    Service,
    Tag,
    TicketTopic,
    User,
)
from ..security import hash_password


def _sync_supabase_user(obj: User, password: str | None, email_changed: bool, creating: bool) -> None:
    """Cria/vincula/atualiza o usuário no Supabase Auth. A senha não fica no banco do InteliSac."""
    if not settings.supabase_service_role_key:
        raise HTTPException(422, detail={"message": "Configure SUPABASE_SERVICE_ROLE_KEY no backend/.env para gerenciar usuários do Supabase."})
    try:
        if obj.auth_user_id:
            fields = {}
            if email_changed:
                fields.update(email=obj.email, email_confirm=True)
            if password:
                fields["password"] = password
            if fields:
                supabase_auth.update_user(obj.auth_user_id, **fields)
        elif password or creating:
            existing = supabase_auth.find_user_by_email(obj.email)
            if existing:
                obj.auth_user_id = existing["id"]
                if password:
                    supabase_auth.update_user(existing["id"], password=password)
            elif password:
                obj.auth_user_id = supabase_auth.create_user(obj.email, password, obj.name)["id"]
            else:
                raise HTTPException(
                    422,
                    detail={"message": "Informe uma senha, ou crie antes o usuário no Supabase (Authentication → Users) com este e-mail."},
                )
            obj.password_hash = ""  # passa a entrar só pelo Supabase
    except supabase_auth.AuthServiceError as e:
        raise HTTPException(502, detail={"message": str(e)})


def _user_hook(db, obj: User, body: dict, actor: User, creating: bool):
    email_changed = False
    if "email" in body:
        email = (body["email"] or "").strip().lower()
        clash = db.query(User).filter(User.email == email, User.id != obj.id).first()
        if clash:
            raise HTTPException(422, detail={"message": "Já existe um usuário com esse e-mail"})
        email_changed = email != obj.email
        obj.email = email
    password = body.get("password") or None
    if password and len(password) < 8:
        raise HTTPException(422, detail={"message": "A senha precisa ter pelo menos 8 caracteres"})
    if settings.supabase_auth_enabled:
        _sync_supabase_user(obj, password, email_changed and not creating, creating)
    elif password:
        obj.password_hash = hash_password(password)
    elif creating:
        raise HTTPException(422, detail={"message": "Informe uma senha"})
    if "departmentIds" in body:
        ids = body["departmentIds"] or []
        obj.departments = (
            db.query(Department)
            .filter(Department.account_id == actor.account_id, Department.id.in_(ids))
            .all()
        )


def _service_hook(db, obj: Service, body: dict, actor: User, creating: bool):
    if obj.type not in SERVICE_TYPES:
        raise HTTPException(422, detail={"message": f"Tipo inválido. Use: {', '.join(SERVICE_TYPES)}"})
    # Só ajustes conhecidos entram em data (status/QR/número vêm do gateway e não podem ser apagados)
    if "signMessages" in body:
        obj.data = {**(obj.data or {}), "signMessages": bool(body["signMessages"])}
    if creating and obj.type == "simulador":
        obj.is_connected = True


routers = [
    make_crud_router("/departments", Department, "department", {"name": "name"}, search="name",
                     required=("name",), order_by=Department.name),
    make_crud_router("/tags", Tag, "tag", {"label": "label", "color": "color"}, search="label",
                     required=("label",), order_by=Tag.label),
    make_crud_router("/ticket-topics", TicketTopic, "ticketTopics", {"name": "name"}, search="name",
                     required=("name",), order_by=TicketTopic.name),
    make_crud_router("/quick-replies", QuickReply, "quickReplies",
                     {"title": "title", "text": "text", "departmentId": "department_id"},
                     search="title", required=("title", "text"), admin_write=False, order_by=QuickReply.title),
    make_crud_router("/roles", Role, "role", {"name": "name", "permissions": "permissions"},
                     search="name", required=("name",), order_by=Role.name),
    make_crud_router("/services", Service, "service", {"name": "name", "type": "type"},
                     search="name", required=("name", "type"), before_save=_service_hook, order_by=Service.name),
    make_crud_router("/users", User, "user",
                     {"name": "name", "isAdmin": "is_admin", "roleId": "role_id", "status": "status"},
                     search="name", required=("name", "email"), before_save=_user_hook, order_by=User.name),
]
