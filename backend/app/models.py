"""Modelo de dados do InteliSac.

Os nomes no JSON seguem o padrão do Digisac (camelCase: contactId, currentTicketId, isOpen...)
para que integrações escritas para um sirvam no outro com poucas mudanças.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def new_id() -> str:
    return str(uuid.uuid4())


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


user_departments = Table(
    "user_departments",
    Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("department_id", ForeignKey("departments.id", ondelete="CASCADE"), primary_key=True),
)

contact_tags = Table(
    "contact_tags",
    Base.metadata,
    Column("contact_id", ForeignKey("contacts.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)

ticket_topics_link = Table(
    "ticket_ticket_topics",
    Base.metadata,
    Column("ticket_id", ForeignKey("tickets.id", ondelete="CASCADE"), primary_key=True),
    Column("ticket_topic_id", ForeignKey("ticket_topics.id", ondelete="CASCADE"), primary_key=True),
)


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    alias: Mapped[str] = mapped_column(String(100), unique=True)
    default_department_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    ticket_seq: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "alias": self.alias,
            "defaultDepartmentId": self.default_department_id,
            "createdAt": iso(self.created_at),
        }


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    permissions: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    def to_dict(self):
        return {
            "id": self.id,
            "accountId": self.account_id,
            "name": self.name,
            "permissions": self.permissions or [],
            "createdAt": iso(self.created_at),
        }


class Department(Base):
    __tablename__ = "departments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    def to_dict(self):
        return {
            "id": self.id,
            "accountId": self.account_id,
            "name": self.name,
            "archivedAt": iso(self.archived_at),
            "createdAt": iso(self.created_at),
        }


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("auth_user_id", name="uq_users_auth_user_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    role_id: Mapped[str | None] = mapped_column(ForeignKey("roles.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    # Vazio quando a senha fica no Supabase Auth (auth_user_id preenchido)
    password_hash: Mapped[str] = mapped_column(String(300), default="")
    auth_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    # Sobe a cada "Sair" ou troca de senha: os logins emitidos antes deixam de valer.
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    status: Mapped[str] = mapped_column(String(20), default="offline")  # online | away | offline
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    departments: Mapped[list["Department"]] = relationship(secondary=user_departments, lazy="selectin")
    role: Mapped["Role | None"] = relationship(lazy="selectin")

    def to_dict(self):
        return {
            "id": self.id,
            "accountId": self.account_id,
            "roleId": self.role_id,
            "name": self.name,
            "email": self.email,
            "isAdmin": self.is_admin,
            "status": self.status,
            "authProvider": "supabase" if self.auth_user_id else "local",
            "departmentIds": [d.id for d in self.departments],
            "archivedAt": iso(self.archived_at),
            "createdAt": iso(self.created_at),
        }


class Tag(Base):
    __tablename__ = "tags"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(120))
    color: Mapped[str] = mapped_column(String(20), default="#52658C")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    def to_dict(self):
        return {
            "id": self.id,
            "accountId": self.account_id,
            "label": self.label,
            "color": self.color,
            "createdAt": iso(self.created_at),
        }


class CorretorConta(Base):
    """Gasto do botão "Corrigir" (Claude) e o saldo da Anthropic informado pelo administrador.
    A Anthropic não diz o saldo para o sistema: o InteliSac desconta do saldo informado o custo
    de cada correção e avisa os administradores quando estiver acabando."""

    __tablename__ = "corretor_conta"
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True)
    mes: Mapped[str] = mapped_column(String(7), default="")  # "2026-11"
    gasto_mes_usd: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    correcoes_mes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    saldo_usd: Mapped[float | None] = mapped_column(Float, nullable=True)  # informado depois da recarga
    saldo_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    gasto_desde_saldo_usd: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    aviso_abaixo_usd: Mapped[float] = mapped_column(Float, default=3.0, server_default="3")
    sem_credito_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ApiKey(Base):
    """Chave de API para outros sistemas (rotinas que disparam mensagens e guias).
    A chave inteira só aparece uma vez, na criação; aqui fica só o hash (SHA-256) e o começo."""

    __tablename__ = "api_keys"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    prefix: Mapped[str] = mapped_column(String(20))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "prefix": self.prefix,
            "createdBy": self.created_by,
            "createdAt": iso(self.created_at),
            "lastUsedAt": iso(self.last_used_at),
            "revokedAt": iso(self.revoked_at),
        }


class ModuloApi(Base):
    """Senha extra para entrar no módulo API (além de ser administrador)."""

    __tablename__ = "modulo_api"
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True)
    senha_hash: Mapped[str] = mapped_column(String(300))
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    atualizado_por: Mapped[str | None] = mapped_column(String(36), nullable=True)


class QuickReply(Base):
    __tablename__ = "quick_replies"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    text: Mapped[str] = mapped_column(Text)
    department_id: Mapped[str | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    def to_dict(self):
        return {
            "id": self.id,
            "accountId": self.account_id,
            "title": self.title,
            "text": self.text,
            "departmentId": self.department_id,
            "createdAt": iso(self.created_at),
        }


class TicketTopic(Base):
    __tablename__ = "ticket_topics"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    def to_dict(self):
        return {
            "id": self.id,
            "accountId": self.account_id,
            "name": self.name,
            "archivedAt": iso(self.archived_at),
            "createdAt": iso(self.created_at),
        }


SERVICE_TYPES = (
    "simulador",
    "whatsapp",  # QR code (WhatsApp Web), via whatsapp-gateway/
    "whatsapp-business",
    "telegram",
    "instagram",
    "facebook-messenger",
    "email",
    "sms",
    "webchat",
)


class Service(Base):
    """Conexão / canal de atendimento (no Digisac: 'services')."""

    __tablename__ = "services"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    type: Mapped[str] = mapped_column(String(40), default="simulador")
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    webhook_token: Mapped[str] = mapped_column(String(64), default=lambda: uuid.uuid4().hex)
    is_connected: Mapped[bool] = mapped_column(Boolean, default=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    def to_dict(self):
        return {
            "id": self.id,
            "accountId": self.account_id,
            "name": self.name,
            "type": self.type,
            "data": self.data or {},
            "isConnected": self.is_connected,
            "archivedAt": iso(self.archived_at),
            "createdAt": iso(self.created_at),
        }


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (UniqueConstraint("service_id", "jid", name="uq_contacts_service_jid"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    service_id: Mapped[str] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    internal_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    number: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    # Identificador do contato no canal (WhatsApp: 5511...@s.whatsapp.net ou ...@lid)
    jid: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_group: Mapped[bool] = mapped_column(Boolean, default=False)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    unread: Mapped[int] = mapped_column(Integer, default=0)
    # Hora da mais antiga das mensagens não lidas (a tela pinta de vermelho depois de 1h30)
    unread_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Desde quando o cliente espera resposta de uma pessoa (vale mesmo com a conversa já aberta)
    waiting_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_ticket_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # Foto do perfil do WhatsApp guardada no Storage; atualizada de tempos em tempos
    avatar_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    avatar_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    tags: Mapped[list["Tag"]] = relationship(secondary=contact_tags, lazy="selectin")

    def to_dict(self):
        return {
            "id": self.id,
            "accountId": self.account_id,
            "serviceId": self.service_id,
            "name": self.name,
            "internalName": self.internal_name,
            "data": {"number": self.number, "email": self.email, "jid": self.jid},
            "note": self.note,
            "isGroup": self.is_group,
            "hasAvatar": bool(self.avatar_path),
            "blocked": self.blocked,
            "unread": self.unread,
            "unreadSince": iso(self.unread_since) if self.unread else None,
            "waitingSince": iso(self.waiting_since),
            "currentTicketId": self.current_ticket_id,
            "lastMessage": self.last_message,
            "lastMessageAt": iso(self.last_message_at),
            "tagIds": [t.id for t in self.tags],
            "createdAt": iso(self.created_at),
        }


class Ticket(Base):
    """Chamado / atendimento. Um contato tem no máximo 1 chamado aberto (currentTicketId)."""

    __tablename__ = "tickets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    contact_id: Mapped[str] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), index=True)
    department_id: Mapped[str | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    protocol: Mapped[str] = mapped_column(String(40), index=True)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    origin: Mapped[str] = mapped_column(String(20), default="contact")  # contact | automatic | manual
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    # Quando entrou na fila (aberto sem atendente ou transferido para a fila): ordem da aba Fila
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    topics: Mapped[list["TicketTopic"]] = relationship(secondary=ticket_topics_link, lazy="selectin")

    def to_dict(self):
        return {
            "id": self.id,
            "accountId": self.account_id,
            "contactId": self.contact_id,
            "departmentId": self.department_id,
            "userId": self.user_id,
            "protocol": self.protocol,
            "isOpen": self.is_open,
            "origin": self.origin,
            "comments": self.comments,
            "ticketTopicIds": [t.id for t in self.topics],
            "startedAt": iso(self.started_at),
            "queuedAt": iso(self.queued_at),
            "endedAt": iso(self.ended_at),
            "lastMessageAt": iso(self.last_message_at),
        }


class TicketTransfer(Base):
    __tablename__ = "ticket_transfers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), index=True)
    from_department_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    to_department_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    from_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    to_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    def to_dict(self):
        return {
            "id": self.id,
            "ticketId": self.ticket_id,
            "fromDepartmentId": self.from_department_id,
            "toDepartmentId": self.to_department_id,
            "fromUserId": self.from_user_id,
            "toUserId": self.to_user_id,
            "byUserId": self.by_user_id,
            "comments": self.comments,
            "createdAt": iso(self.created_at),
        }


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("service_id", "external_id", name="uq_messages_service_external"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    contact_id: Mapped[str] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), index=True)
    ticket_id: Mapped[str | None] = mapped_column(
        ForeignKey("tickets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    service_id: Mapped[str] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"))
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # chat | image | audio | ptt | video | document | location | reaction | ticket (evento do chamado)
    type: Mapped[str] = mapped_column(String(20), default="chat")
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_from_me: Mapped[bool] = mapped_column(Boolean, default=False)
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "accountId": self.account_id,
            "contactId": self.contact_id,
            "ticketId": self.ticket_id,
            "serviceId": self.service_id,
            "userId": self.user_id,
            "type": self.type,
            "text": self.text,
            "isFromMe": self.is_from_me,
            "data": self.data or {},
            "timestamp": iso(self.created_at),
            "createdAt": iso(self.created_at),
        }
