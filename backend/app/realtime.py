"""Tempo real via socket.io — mesmo formato de evento do Digisac (`message.created`, `ticket.updated`...).

O cliente conecta mandando o token no `auth` do socket.io ({"access_token": "<jwt>"}). O token não vai
no endereço (?access_token=), porque o endereço aparece nos logs do servidor.
Cada conexão recebe os eventos da sua conta. Quem fica com o token vencido ou é arquivado é
desconectado pelo vigia (a tela renova o token e conecta de novo; arquivado não volta).
"""

import asyncio
import logging
import time

import socketio

from .config import settings
from .security import decode_token

log = logging.getLogger("intelisac.realtime")

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=settings.cors_origins)

# sid → (user_id, expiração do token em epoch)
_conexoes: dict[str, tuple[str, float]] = {}
VIGIA_SEGUNDOS = 60


def _usuario_ativo(user_id: str) -> bool:
    from .db import SessionLocal
    from .models import User

    with SessionLocal() as db:
        user = db.get(User, user_id)
        return bool(user and user.archived_at is None)


@sio.event
async def connect(sid, environ, auth=None):
    token = None
    if isinstance(auth, dict):
        token = auth.get("access_token") or auth.get("token")
    data = decode_token(token or "")
    if not data or not await asyncio.to_thread(_usuario_ativo, data["sub"]):
        raise socketio.exceptions.ConnectionRefusedError("unauthorized")
    await sio.save_session(sid, {"user_id": data["sub"], "account_id": data["acc"]})
    _conexoes[sid] = (data["sub"], float(data.get("exp") or 0))
    await sio.enter_room(sid, f"account:{data['acc']}")
    await sio.enter_room(sid, f"user:{data['sub']}")


@sio.event
async def disconnect(sid, *_args):
    _conexoes.pop(sid, None)


def _arquivados(user_ids: set[str]) -> set[str]:
    from .db import SessionLocal
    from .models import User

    with SessionLocal() as db:
        ativos = {
            u.id for u in db.query(User.id).filter(User.id.in_(user_ids), User.archived_at.is_(None)).all()
        }
    return user_ids - ativos


async def desconectar_vencidos() -> int:
    """Uma rodada do vigia: derruba token vencido e usuário arquivado. Devolve quantos caíram."""
    if not _conexoes:
        return 0
    agora = time.time()
    fora = {sid for sid, (_uid, exp) in _conexoes.items() if exp and exp <= agora}
    try:
        arquivados = await asyncio.to_thread(_arquivados, {uid for uid, _ in _conexoes.values()})
    except Exception as e:  # banco fora: tenta na próxima rodada
        log.warning("vigia do tempo real sem banco: %s", e)
        arquivados = set()
    fora |= {sid for sid, (uid, _exp) in _conexoes.items() if uid in arquivados}
    for sid in fora:
        _conexoes.pop(sid, None)
        await sio.disconnect(sid)
    return len(fora)


async def vigiar_conexoes() -> None:
    while True:
        await asyncio.sleep(VIGIA_SEGUNDOS)
        try:
            await desconectar_vencidos()
        except Exception as e:  # o vigia nunca pode parar
            log.warning("vigia do tempo real: %s", e)


async def emit(account_id: str, event: str, payload: dict) -> None:
    await sio.emit(event, payload, room=f"account:{account_id}")
