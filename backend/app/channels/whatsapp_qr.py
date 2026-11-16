"""WhatsApp por QR code (como o WhatsApp Web). O envio passa pelo whatsapp-gateway."""

from .base import ChannelAdapter, MediaOut, Quoted, SendResult
from .gateway_client import GatewayError, gateway_request


def _destino(contact) -> dict | None:
    if contact.jid:
        return {"jid": contact.jid}
    if contact.number:
        return {"number": contact.number}
    return None


def _quoted(q: Quoted | None) -> dict | None:
    if not q:
        return None
    out = {"id": q.id, "fromMe": q.from_me, "text": q.text}
    if q.participant:
        out["participant"] = q.participant
    return out


class WhatsAppQrAdapter(ChannelAdapter):
    type = "whatsapp"

    async def _post(self, service, path: str, payload: dict, timeout: float = 30.0) -> SendResult:
        try:
            res = await gateway_request("POST", f"/sessions/{service.id}/{path}", payload, timeout=timeout)
        except GatewayError as e:
            return SendResult(ok=False, error=str(e))
        return SendResult(ok=True, external_id=res.get("id"), extra={"jid": res.get("jid")})

    async def send_text(self, service, contact, text: str, quoted: Quoted | None = None, forwarded: bool = False) -> SendResult:
        dest = _destino(contact)
        if not dest:
            return SendResult(ok=False, error="Contato sem número de WhatsApp")
        payload = {"text": text, **dest}
        if quoted:
            payload["quoted"] = _quoted(quoted)
        if forwarded:
            payload["forwarded"] = True
        return await self._post(service, "send", payload)

    async def send_media(self, service, contact, media: MediaOut, quoted: Quoted | None = None, forwarded: bool = False) -> SendResult:
        dest = _destino(contact)
        if not dest:
            return SendResult(ok=False, error="Contato sem número de WhatsApp")
        payload = {
            **dest,
            "url": media.url,
            "mimetype": media.mimetype,
            "fileName": media.file_name,
            "kind": media.kind,
            "caption": media.caption,
            "ptt": media.ptt,
        }
        if media.seconds:
            payload["seconds"] = media.seconds
        if media.waveform:
            payload["waveform"] = media.waveform
        if quoted:
            payload["quoted"] = _quoted(quoted)
        if forwarded:
            payload["forwarded"] = True
        return await self._post(service, "send-media", payload, timeout=180)

    async def revoke(self, service, contact, external_id: str) -> SendResult:
        if not contact.jid:
            return SendResult(ok=False, error="Contato sem identificador do WhatsApp")
        res = await self._post(service, "delete", {"jid": contact.jid, "id": external_id})
        return SendResult(ok=res.ok, error=res.error)

    async def edit(self, service, contact, external_id: str, text: str) -> SendResult:
        if not contact.jid:
            return SendResult(ok=False, error="Contato sem identificador do WhatsApp")
        res = await self._post(service, "edit", {"jid": contact.jid, "id": external_id, "text": text})
        return SendResult(ok=res.ok, error=res.error)
