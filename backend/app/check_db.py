"""Testa a conexão com o banco configurado em DATABASE_URL (sem mostrar a senha).

Rodar:  python -m app.check_db
Saída 0 = conectou; 1 = problema (a mensagem diz o que corrigir).
"""

import os
import sys

from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url


def _fail(msg: str) -> None:
    print(f"ERRO: {msg}")
    sys.exit(1)


def main() -> None:
    from .config import settings  # carrega o backend/.env

    raw = os.getenv("DATABASE_URL", "")
    if "[YOUR-PASSWORD]" in raw or "<SENHA>" in raw:
        _fail("a DATABASE_URL ainda tem [YOUR-PASSWORD]. Troque pela senha do banco do Supabase.")

    try:
        url = make_url(settings.database_url)
    except Exception:
        _fail("a DATABASE_URL não é um endereço válido. Se a senha tem símbolos (@ # / ? %), "
              "troque a senha do banco por uma só com letras e números.")

    print(f"Banco: {url.render_as_string(hide_password=True)}")
    if url.get_backend_name() == "sqlite":
        print("Ainda está usando o SQLite local (backend/intelisac.db). Cole a URI do Supabase em DATABASE_URL.")
        sys.exit(1)

    host = url.host or ""
    if host.startswith("db.") and host.endswith(".supabase.co"):
        print("AVISO: esta é a conexão direta (só IPv6). Se não conectar, use a do 'Session pooler' (porta 5432).")
    if url.port == 6543:
        print("AVISO: porta 6543 = pooler em modo transação. Funciona, mas o recomendado é o Session pooler (5432).")

    from .db import engine

    try:
        with engine.connect() as conn:
            version = conn.execute(text("select version()")).scalar_one()
            tables = set(inspect(conn).get_table_names())
            revision = None
            if "alembic_version" in tables:
                revision = conn.execute(text("select version_num from alembic_version")).scalar_one_or_none()
    except Exception as e:  # noqa: BLE001 — mostrar o motivo de forma simples
        msg = str(e).splitlines()[0]
        if "password authentication failed" in msg:
            _fail("senha recusada. Confira a senha do banco (Project Settings → Database → Reset password se precisar).")
        if "Tenant or user not found" in msg:
            _fail("usuário/projeto não encontrado. No Session pooler o usuário é 'postgres.<ref-do-projeto>', "
                  "não só 'postgres'. Copie a URI de novo pelo botão Connect.")
        if "could not translate host name" in msg or "getaddrinfo" in msg or "Name or service not known" in msg:
            _fail("endereço do servidor não encontrado. Use a URI do 'Session pooler' (o host termina em pooler.supabase.com).")
        _fail(f"não conectou: {msg}")

    print(f"Conectado: {version.split(',')[0]}")
    app_tables = sorted(t for t in tables if t != "alembic_version")
    if revision:
        print(f"Migração aplicada: {revision} · {len(app_tables)} tabelas do InteliSac")
    else:
        print("Banco vazio (nenhuma migração ainda). Próximo passo: python -m app.seed")
    sys.exit(0)


if __name__ == "__main__":
    main()
