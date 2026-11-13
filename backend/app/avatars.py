"""Foto do perfil dos contatos e grupos do WhatsApp.

O WhatsApp entrega um link temporário da foto; o InteliSac baixa a imagem e guarda no Storage
(<conta>/avatars/<contato>.jpg), para a lista de conversas não depender desse link.
Atualiza de novo depois de 7 dias. Tudo roda em segundo plano (não atrasa a tela).
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import httpx

from . import storage
from .channels.gateway_client import GatewayError, gateway_request
from .db import SessionLocal
from .models import Contact, Service, now
from .realtime import emit

log = logging.getLogger("intelisac.avatars")
REFRESH_EVERY = timedelta(days=7)
MAX_FOTO = 2 * 1024 * 1024
_em_andamento: set[str] = set()
_limite = asyncio.Semaphore(3)
# Link assinado de cada foto, reaproveitado por 45 min (o link vale 1 h): a lista de conversas
# recarrega a cada mensagem e, com link novo toda vez, as fotos seriam baixadas de novo.
_links: dict[str, tuple[str, float]] = {}
LINK_REUSO_SEGUNDOS = 45 * 60


def needs_refresh(contact: Contact) -> bool:
    if not contact.jid:
        return False
    if contact.avatar_checked_at is None:
        return True
    visto = contact.avatar_checked_at if contact.avatar_checked_at.tzinfo else contact.avatar_checked_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - visto > REFRESH_EVERY


async def refresh_many(contact_ids: list[str]) -> None:
    await asyncio.gather(*(refresh(cid) for cid in contact_ids), return_exceptions=True)


async def refresh(contact_id: str) -> None:
    if contact_id in _em_andamento:
        return
    _em_andamento.add(contact_id)
    try:
        async with _limite:
            await _refresh(contact_id)
    except Exception as e:  # foto é só visual: nunca derruba nada
        log.warning("foto do contato %s: %s", contact_id, e)
    finally:
        _em_andamento.discard(contact_id)


async def _refresh(contact_id: str) -> None:
    db = SessionLocal()
    try:
        contact = db.get(Contact, contact_id)
        if not contact or not contact.jid:
            return
        service = db.get(Service, contact.service_id)
        if not service or service.type != "whatsapp" or not service.is_connected:
            return  # sem conexão agora: tenta numa próxima vez
        try:
            res = await gateway_request("GET", f"/sessions/{service.id}/photo?jid={quote(contact.jid)}", timeout=20)
        except GatewayError:
            return
        link = res.get("url")
        caminho = None
        if link:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as c:
                r = await c.get(link)
            if r.status_code == 200 and 0 < len(r.content) <= MAX_FOTO:
                caminho = f"{contact.account_id}/avatars/{contact.id}.jpg"
                await storage.upload(caminho, r.content, r.headers.get("content-type") or "image/jpeg", upsert=True)
        _links.pop(f"{contact.account_id}/avatars/{contact.id}.jpg", None)  # foto trocada: link novo
        mudou = caminho != contact.avatar_path or bool(caminho)
        contact.avatar_path = caminho
        contact.avatar_checked_at = now()
        db.commit()
        if mudou:
            await emit(contact.account_id, "contact.updated", attach_avatars([contact.to_dict()], {contact.id: caminho})[0])
    finally:
        db.close()


def attach_avatars(contacts: list[dict], paths: dict[str, str | None]) -> list[dict]:
    """Coloca avatarUrl (link assinado, 1 h) nos contatos que têm foto guardada."""
    validos = list(dict.fromkeys(p for p in paths.values() if p))
    if not validos:
        return contacts
    agora = time.monotonic()
    links = {p: _links[p][0] for p in validos if p in _links and _links[p][1] > agora}
    faltam = [p for p in validos if p not in links]
    if faltam:
        try:
            novos = storage.sign_many(faltam)
        except storage.StorageError:
            novos = {}
        for p, link in novos.items():
            _links[p] = (link, agora + LINK_REUSO_SEGUNDOS)
        links.update(novos)
    for c in contacts:
        p = paths.get(c["id"])
        if p and p in links:
            c["avatarUrl"] = links[p]
    return contacts
