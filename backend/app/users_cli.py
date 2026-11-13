"""Comandos de usuários / Supabase Auth.

  python -m app.users_cli check                      confere SUPABASE_URL e as chaves
  python -m app.users_cli list                       lista os usuários do Supabase Auth e se estão no InteliSac
  python -m app.users_cli link --email X [--admin]   cadastra/vincula no InteliSac um usuário que já existe
                                                     no Supabase Auth (todos os departamentos)
  python -m app.users_cli archive --email X          arquiva um usuário do InteliSac (ex.: o admin do seed)

Nenhum comando mostra ou pede senha.
"""

import argparse
import sys

from . import migrate, supabase_auth
from .config import settings
from .db import SessionLocal
from .models import Account, Department, User, now


def _need_supabase():
    if not settings.supabase_auth_enabled:
        sys.exit("Supabase Auth não configurado: preencha SUPABASE_URL e SUPABASE_ANON_KEY no backend/.env")


def cmd_check(_args):
    _need_supabase()
    r = supabase_auth.check_keys()
    print("SUPABASE_URL:", "ok" if r.get("url") else "faltando")
    print("SUPABASE_ANON_KEY (login):", "ok" if r.get("anon") else "NÃO funcionou")
    print("SUPABASE_SERVICE_ROLE_KEY (gerenciar usuários):", "ok" if r.get("service_role") else "NÃO funcionou / faltando")
    if "signup_enabled" in r:
        print("Cadastro público no Supabase:", "LIGADO (recomendo desligar)" if r["signup_enabled"] else "desligado")
    if r.get("error"):
        print("Detalhe:", r["error"])
    sys.exit(0 if r.get("anon") and r.get("service_role") else 1)


def cmd_list(_args):
    _need_supabase()
    db = SessionLocal()
    try:
        users = supabase_auth.list_users()
        if not users:
            print("Nenhum usuário no Supabase Auth ainda.")
        for u in users:
            email = (u.get("email") or "").lower()
            local = db.query(User).filter((User.auth_user_id == u["id"]) | (User.email == email)).first()
            situacao = "não cadastrado no InteliSac"
            if local:
                situacao = ("ADMIN" if local.is_admin else "atendente") + (" (arquivado)" if local.archived_at else "")
                situacao += "" if local.auth_user_id else " — ainda não vinculado"
            confirmado = "confirmado" if u.get("email_confirmed_at") else "e-mail NÃO confirmado"
            print(f"- {email} · {confirmado} · {situacao}")
    finally:
        db.close()


def cmd_link(args):
    _need_supabase()
    migrate.upgrade()
    email = args.email.strip().lower()
    auth_user = supabase_auth.find_user_by_email(email)
    if not auth_user:
        sys.exit(f"{email} não existe no Supabase Auth. Crie em Authentication → Users → Add user.")
    if not auth_user.get("email_confirmed_at"):
        print("Aviso: o e-mail ainda não está confirmado no Supabase; o login só funciona depois de confirmado.")
    db = SessionLocal()
    try:
        account = db.query(Account).order_by(Account.created_at).first()
        if not account:
            sys.exit("Nenhuma conta no banco. Rode antes: python -m app.seed")
        user = db.query(User).filter((User.auth_user_id == auth_user["id"]) | (User.email == email)).first()
        created = user is None
        if created:
            user = User(account_id=account.id, email=email, name=args.name or email.split("@")[0], password_hash="")
            db.add(user)
            user.departments = db.query(Department).filter(Department.account_id == account.id, Department.archived_at.is_(None)).all()
        user.auth_user_id = auth_user["id"]
        user.password_hash = ""
        user.archived_at = None
        if args.admin:
            user.is_admin = True
        if args.name:
            user.name = args.name
        db.commit()
        papel = "administrador" if user.is_admin else "atendente"
        print(f"{'Criado' if created else 'Atualizado'} no InteliSac: {email} ({papel}), vinculado ao Supabase Auth.")
    finally:
        db.close()


def cmd_archive(args):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == args.email.strip().lower()).first()
        if not user:
            sys.exit("Usuário não encontrado no InteliSac.")
        user.archived_at = now()
        db.commit()
        print(f"Arquivado: {user.email} (não consegue mais entrar).")
    finally:
        db.close()


def main():
    p = argparse.ArgumentParser(prog="python -m app.users_cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    link = sub.add_parser("link")
    link.add_argument("--email", required=True)
    link.add_argument("--name")
    link.add_argument("--admin", action="store_true")
    link.set_defaults(fn=cmd_link)
    arch = sub.add_parser("archive")
    arch.add_argument("--email", required=True)
    arch.set_defaults(fn=cmd_archive)
    args = p.parse_args()
    try:
        args.fn(args)
    except supabase_auth.AuthServiceError as e:
        sys.exit(f"Erro no Supabase: {e}")


if __name__ == "__main__":
    main()
