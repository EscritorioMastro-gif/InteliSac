"""InteliSac — API.  Rodar:  uvicorn app.main:asgi --reload --port 8010"""

from contextlib import asynccontextmanager

import asyncio
import logging

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import migrate, realtime, storage
from .config import settings
from .protecao import CabecalhosDeSeguranca, LimiteDeCorpo
from .realtime import sio

# Na internet, não sobe com chave fraca ou faltando (melhor parar do que ficar exposto).
if settings.is_production and settings.problemas_de_producao():
    raise RuntimeError("Configuração insegura para produção: " + "; ".join(settings.problemas_de_producao()))
from .routers import auth, channels, contacts, gateway, me, messages, now, resources, tickets


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Cria/atualiza as tabelas (SQLite local ou Postgres do Supabase) pelas migrações do Alembic.
    migrate.upgrade()
    # Bucket privado dos arquivos das conversas (sem Supabase configurado, só os arquivos ficam fora)
    if settings.supabase_url and settings.supabase_service_role_key:
        try:
            storage.ensure_bucket()
        except storage.StorageError as e:
            logging.getLogger("intelisac").warning("Storage indisponível: %s", e)
    # Desconecta do tempo real quem teve o acesso vencido ou o usuário arquivado
    vigia = asyncio.create_task(realtime.vigiar_conexoes())
    yield
    vigia.cancel()


# Documentação automática da API (/docs) só fora da produção: na internet ela vira um mapa para ataque.
_docs = {} if not settings.is_production else {"docs_url": None, "redoc_url": None, "openapi_url": None}
app = FastAPI(title="InteliSac API", version="0.1.0", lifespan=lifespan, **_docs)
# O login vai no cabeçalho Authorization (não em cookie): credenciais do CORS ficam desligadas.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

API = "/api/v1"
for r in (
    auth.router,
    me.router,
    contacts.router,
    messages.router,
    tickets.router,
    channels.router,
    gateway.router,
    now.router,
):
    app.include_router(r, prefix=API)
for r in resources.routers:
    app.include_router(r, prefix=API)


@app.get(API + "/health")
def health():
    return {"ok": True, "app": "InteliSac"}


# App ASGI final: socket.io em /socket.io + FastAPI no resto (com teto de corpo e cabeçalhos de segurança).
asgi = socketio.ASGIApp(sio, other_asgi_app=CabecalhosDeSeguranca(LimiteDeCorpo(app)), socketio_path="socket.io")
