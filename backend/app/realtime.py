"""Tempo real via socket.io — mesmo protocolo e formato de evento do Digisac.

O cliente conecta com `?access_token=<jwt>` e recebe eventos `recurso.ação`
(ex.: `message.created`, `ticket.updated`) da sua conta.
"""

from urllib.parse import parse_qs

import socketio

from .config import settings
from .security import decode_token

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=settings.cors_origins or "*")


@sio.event
async def connect(sid, environ, auth=None):
    token = None
    if isinstance(auth, dict):
        token = auth.get("access_token") or auth.get("token")
    if not token:
        qs = parse_qs(environ.get("QUERY_STRING", ""))
        token = (qs.get("access_token") or [None])[0]
    data = decode_token(token or "")
    if not data:
        raise socketio.exceptions.ConnectionRefusedError("unauthorized")
    await sio.save_session(sid, {"user_id": data["sub"], "account_id": data["acc"]})
    await sio.enter_room(sid, f"account:{data['acc']}")
    await sio.enter_room(sid, f"user:{data['sub']}")


async def emit(account_id: str, event: str, payload: dict) -> None:
    await sio.emit(event, payload, room=f"account:{account_id}")
