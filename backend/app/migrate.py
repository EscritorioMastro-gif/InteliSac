"""Aplica as migrações do banco (alembic upgrade head). Rodar:  python -m app.migrate"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text

BACKEND_DIR = Path(__file__).resolve().parent.parent

# No Supabase, as tabelas do esquema "public" ficam expostas pela API automática do Supabase
# (Data API / PostgREST). Com RLS ligado e sem nenhuma política, essa API não acessa nada.
# O backend conecta como dono das tabelas (usuário postgres) e não é afetado.
_ENABLE_RLS_ALL = """
DO $$
DECLARE r record;
BEGIN
  FOR r IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND NOT rowsecurity LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', r.tablename);
  END LOOP;
END $$;
"""


def alembic_config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    return cfg


def protect_public_tables() -> None:
    from .db import engine

    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as conn:
        conn.execute(text(_ENABLE_RLS_ALL))


def upgrade() -> None:
    command.upgrade(alembic_config(), "head")
    protect_public_tables()


if __name__ == "__main__":
    upgrade()
    print("Banco atualizado (alembic head).")
