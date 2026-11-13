"""InteliSac — API.  Rodar:  uvicorn app.main:asgi --reload --port 8010"""

from contextlib import asynccontextmanager

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import logging

from . import migrate, storage
from .config import settings
from .realtime import sio
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
    yield


app = FastAPI(title="InteliSac API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


# App ASGI final: socket.io em /socket.io + FastAPI no resto.
asgi = socketio.ASGIApp(sio, other_asgi_app=app, socketio_path="socket.io")
