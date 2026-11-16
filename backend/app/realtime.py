"""Tempo real via socket.io — mesmo formato de evento do Digisac (`message.created`, `ticket.updated`...).

O cliente conecta mandando o token no `auth` do socket.io ({"access_token": "<jwt>"}). O token não vai
no endereço (?access_token=), porque o endereço aparece nos logs do servidor.
Cada conexão recebe os eventos da sua conta. Quem fica com o token vencido, sai ("Sair"), troca a
senha ou é arquivado é desconectado (a tela renova o token e conecta de novo; quem perdeu o acesso
não volta).

O QR code de conexão do WhatsApp só vai para administradores (evento `service.qr`, sala dos admins).
"""

import asyncio
import logging
import time

import socketio

from .config import settings
from .security import decode_token

log = logging.getLogger("intelisac.realtime")

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=settings.cors_origins)

# sid → (user_id, expiração do token em epoch, versão do acesso)
_conexoes: dict[str, tuple[str, float, int]] = {}
VIGIA_SEGUNDOS = 60


def _usuario(user_id: str) -> tuple[bool, bool, int] | None:
    """(ativo, é admin, versão do acesso) ou None se não existe."""
    from .db import SessionLocal
    from .models import User

    with SessionLocal() as db:
        user = db.get(User, user_id)
        if not user:
            return None
        return user.archived_at is None, bool(user.is_admin), int(user.token_version or 0)


@sio.event
async def connect(sid, environ, auth=None):
    token = None
    if isinstance(auth, dict):
        token = auth.get("access_token") or auth.get("token")
    data = decode_token(token or "")
    info = await asyncio.to_thread(_usuario, data["sub"]) if data else None
    try:
        versao = int((data or {}).get("ver") or 0)
    except (TypeError, ValueError):
        versao = -1
    if not data or not info or not info[0] or info[2] != versao:
        raise socketio.exceptions.ConnectionRefusedError("unauthorized")
    await sio.save_session(sid, {"user_id": data["sub"], "account_id": data["acc"]})
    _conexoes[sid] = (data["sub"], float(data.get("exp") or 0), versao)
    await sio.enter_room(sid, f"account:{data['acc']}")
    await sio.enter_room(sid, f"user:{data['sub']}")
    if info[1]:
        await sio.enter_room(sid, f"admins:{data['acc']}")


@sio.event
async def disconnect(sid, *_args):
    _conexoes.pop(sid, None)


def _situacao(user_ids: set[str]) -> dict[str, int]:
    """{user_id: versão do acesso} só dos usuários ATIVOS."""
    from .db import SessionLocal
    from .models import User

    with SessionLocal() as db:
        linhas = db.query(User.id, User.token_version).filter(User.id.in_(user_ids), User.archived_at.is_(None)).all()
    return {uid: int(ver or 0) for uid, ver in linhas}


async def desconectar_vencidos() -> int:
    """Uma rodada do vigia: derruba token vencido, usuário arquivado e login encerrado. Devolve quantos caíram."""
    if not _conexoes:
        return 0
    agora = time.time()
    fora = {sid for sid, (_uid, exp, _v) in _conexoes.items() if exp and exp <= agora}
    try:
        atuais = await asyncio.to_thread(_situacao, {uid for uid, _e, _v in _conexoes.values()})
    except Exception as e:  # banco fora: tenta na próxima rodada
        log.warning("vigia do tempo real sem banco: %s", e)
        atuais = None
    if atuais is not None:
        fora |= {sid for sid, (uid, _exp, ver) in _conexoes.items() if atuais.get(uid) != ver}
    for sid in fora:
        _conexoes.pop(sid, None)
        await sio.disconnect(sid)
    return len(fora)


async def derrubar_usuario(user_id: str) -> int:
    """Desconecta na hora todas as telas abertas de um usuário (usado no "Sair")."""
    sids = [sid for sid, (uid, _e, _v) in _conexoes.items() if uid == user_id]
    for sid in sids:
        _conexoes.pop(sid, None)
        await sio.disconnect(sid)
    return len(sids)


async def vigiar_conexoes() -> None:
    while True:
        await asyncio.sleep(VIGIA_SEGUNDOS)
        try:
            await desconectar_vencidos()
        except Exception as e:  # o vigia nunca pode parar
            log.warning("vigia do tempo real: %s", e)


async def emit(account_id: str, event: str, payload: dict) -> None:
    await sio.emit(event, payload, room=f"account:{account_id}")


def service_publico(d: dict) -> dict:
    """Conexão sem o QR code (quem lê o QR liga um WhatsApp ao sistema: só administrador vê)."""
    data = dict(d.get("data") or {})
    if data.get("qrCode"):
        data["qrCode"] = None
        data["hasQr"] = True
    return {**d, "data": data}


async def emit_service(service) -> None:
    """Estado da conexão para todos (sem QR) + o QR só para os administradores."""
    completo = service.to_dict()
    await sio.emit("service.updated", service_publico(completo), room=f"account:{service.account_id}")
    await sio.emit(
        "service.qr",
        {"id": service.id, "qrCode": (completo.get("data") or {}).get("qrCode")},
        room=f"admins:{service.account_id}",
    )
