"""Cria a conta inicial, o administrador e dados de exemplo.  Rodar:  python -m app.seed"""

import os

from . import migrate
from .db import SessionLocal
from .models import Account, Department, QuickReply, Service, Tag, TicketTopic, User
from .security import hash_password


def run() -> None:
    migrate.upgrade()
    db = SessionLocal()
    try:
        email = os.getenv("SEED_ADMIN_EMAIL", "admin@intelisac.local").lower()
        if db.query(User).filter(User.email == email).first():
            print(f"Seed já aplicado ({email}).")
            return
        account = Account(name=os.getenv("SEED_ACCOUNT_NAME", "InteliSac"), alias="intelisac")
        db.add(account)
        db.flush()

        deps = [Department(account_id=account.id, name=n) for n in ("Atendimento", "Financeiro", "Fiscal")]
        db.add_all(deps)
        db.flush()
        account.default_department_id = deps[0].id

        admin = User(
            account_id=account.id,
            name=os.getenv("SEED_ADMIN_NAME", "Administrador"),
            email=email,
            password_hash=hash_password(os.getenv("SEED_ADMIN_PASSWORD", "intelisac-dev-2026")),
            is_admin=True,
            departments=deps,
        )
        db.add(admin)
        db.add(Service(account_id=account.id, name="Simulador", type="simulador", is_connected=True))
        db.add_all([TicketTopic(account_id=account.id, name=n) for n in ("Dúvida", "Envio de documentos", "Cobrança")])
        db.add_all([
            Tag(account_id=account.id, label="Cliente", color="#2E7D32"),
            Tag(account_id=account.id, label="Prospect", color="#F9A825"),
        ])
        db.add(QuickReply(
            account_id=account.id,
            title="Saudação",
            text="Olá! Aqui é da InteliSac, em que posso ajudar?",
        ))
        db.commit()
        print(f"Seed aplicado. Login: {email} (senha em SEED_ADMIN_PASSWORD no .env)")
    finally:
        db.close()


if __name__ == "__main__":
    run()
