"""Arquivos das conversas (fotos, áudios, vídeos, documentos) no Supabase Storage.

- Bucket PRIVADO `intelisac-midia`: só o backend (chave secret) grava e lê.
- A tela recebe links assinados que expiram (padrão 1 h), gerados a cada carregamento.
- Caminho: <conta>/<contato>/<aleatório>-<nome-do-arquivo>
"""

import mimetypes
import re
import unicodedata
import uuid
from urllib.parse import quote

import httpx

from .config import settings

BUCKET = "intelisac-midia"
# 50 MB por arquivo = limite padrão do Supabase. No plano Pro dá para subir em
# Storage → Settings → "Upload file size limit"; depois aumente aqui também.
MAX_BYTES = 50 * 1024 * 1024
LINK_SECONDS = 3600


class StorageError(Exception):
    pass


def _headers(extra: dict | None = None) -> dict:
    key = settings.supabase_service_role_key
    if not settings.supabase_url or not key:
        raise StorageError("Supabase Storage não configurado (SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY no backend/.env)")
    h = {"apikey": key}
    if key.startswith("eyJ"):  # chave antiga (JWT) também vai no Authorization
        h["Authorization"] = f"Bearer {key}"
    if extra:
        h.update(extra)
    return h


def _url(path: str) -> str:
    return f"{settings.supabase_url}/storage/v1{path}"


def _erro(res: httpx.Response) -> str:
    try:
        body = res.json()
        return body.get("message") or body.get("error") or str(body)[:200]
    except ValueError:
        return res.text[:200]


def ensure_bucket() -> bool:
    """Cria o bucket privado se não existir. Devolve True se criou."""
    with httpx.Client(timeout=30) as c:
        r = c.get(_url(f"/bucket/{BUCKET}"), headers=_headers())
        if r.status_code == 200:
            return False
        r = c.post(
            _url("/bucket"),
            headers=_headers({"Content-Type": "application/json"}),
            json={"id": BUCKET, "name": BUCKET, "public": False},
        )
        if r.status_code in (200, 201):
            return True
        if "already exists" in _erro(r).lower():
            return False
        raise StorageError(f"Não consegui criar o bucket ({r.status_code}): {_erro(r)}")


def safe_name(name: str | None, mimetype: str | None = None) -> str:
    name = (name or "").strip().replace("\\", "/").split("/")[-1]
    if not name:
        ext = mimetypes.guess_extension((mimetype or "").split(";")[0].strip()) or ""
        name = f"arquivo{ext}"
    # tira acentos ("ção" → "cao"); o nome original fica salvo na mensagem
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "arquivo"
    return base[-90:]


def object_path(account_id: str, contact_id: str, name: str | None, mimetype: str | None = None) -> str:
    return f"{account_id}/{contact_id}/{uuid.uuid4().hex[:12]}-{safe_name(name, mimetype)}"


async def upload(path: str, data: bytes, mimetype: str, upsert: bool = False) -> None:
    if len(data) > MAX_BYTES:
        raise StorageError(f"Arquivo maior que {MAX_BYTES // (1024 * 1024)} MB")
    try:
        async with httpx.AsyncClient(timeout=120) as c:
            r = await c.post(
                _url(f"/object/{BUCKET}/{quote(path)}"),
                headers=_headers({"Content-Type": mimetype or "application/octet-stream", "x-upsert": "true" if upsert else "false"}),
                content=data,
            )
    except httpx.HTTPError as e:
        raise StorageError(f"Supabase Storage indisponível: {e}") from e
    if r.status_code not in (200, 201):
        raise StorageError(f"Supabase Storage recusou o arquivo ({r.status_code}): {_erro(r)}")


def _full(signed: str) -> str:
    signed = signed or ""
    if signed.startswith("http"):
        return signed
    if not signed.startswith("/storage/v1"):
        signed = "/storage/v1" + (signed if signed.startswith("/") else "/" + signed)
    return f"{settings.supabase_url}{signed}"


def sign_many(paths: list[str], expires: int = LINK_SECONDS) -> dict[str, str]:
    """{caminho: link assinado} para vários arquivos numa chamada só."""
    paths = [p for p in dict.fromkeys(paths) if p]
    if not paths:
        return {}
    with httpx.Client(timeout=30) as c:
        r = c.post(
            _url(f"/object/sign/{BUCKET}"),
            headers=_headers({"Content-Type": "application/json"}),
            json={"expiresIn": expires, "paths": paths},
        )
    if r.status_code != 200:
        raise StorageError(f"Não consegui gerar os links ({r.status_code}): {_erro(r)}")
    out = {}
    for item in r.json():
        if item.get("signedURL") and not item.get("error"):
            out[item["path"]] = _full(item["signedURL"])
    return out


def sign_one(path: str, expires: int = LINK_SECONDS) -> str:
    link = sign_many([path], expires).get(path)
    if not link:
        raise StorageError("Não consegui gerar o link do arquivo")
    return link


def attach_urls(messages: list[dict]) -> list[dict]:
    """Coloca fileUrl (ver) e downloadUrl (baixar) nas mensagens que têm arquivo."""
    paths = [((m.get("data") or {}).get("file") or {}).get("path") for m in messages]
    if not any(paths):
        return messages
    try:
        links = sign_many([p for p in paths if p])
    except StorageError:
        return messages  # a tela mostra "arquivo indisponível"
    for m, p in zip(messages, paths):
        if p and p in links:
            nome = ((m.get("data") or {}).get("file") or {}).get("name") or "arquivo"
            m["fileUrl"] = links[p]
            m["downloadUrl"] = links[p] + ("&" if "?" in links[p] else "?") + "download=" + quote(nome)
    return messages


def media_kind(mimetype: str | None) -> str:
    mt = (mimetype or "").lower()
    if mt.startswith("image/") and "svg" not in mt:
        return "image"
    if mt.startswith("video/"):
        return "video"
    if mt.startswith("audio/"):
        return "audio"
    return "document"


LABELS = {
    "image": "[Imagem]",
    "sticker": "[Figurinha]",
    "video": "[Vídeo]",
    "audio": "[Áudio]",
    "ptt": "[Áudio]",
    "document": "[Documento]",
}
