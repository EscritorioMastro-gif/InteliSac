"""WhatsApp por QR code (como o WhatsApp Web). O envio passa pelo whatsapp-gateway."""

from .base import ChannelAdapter, SendResult
from .gateway_client import GatewayError, gateway_request


class WhatsAppQrAdapter(ChannelAdapter):
    type = "whatsapp"

    async def send_text(self, service, contact, text: str) -> SendResult:
        payload = {"text": text}
        if contact.jid:
            payload["jid"] = contact.jid
        elif contact.number:
            payload["number"] = contact.number
        else:
            return SendResult(ok=False, error="Contato sem número de WhatsApp")
        try:
            res = await gateway_request("POST", f"/sessions/{service.id}/send", payload)
        except GatewayError as e:
            return SendResult(ok=False, error=str(e))
        return SendResult(ok=True, external_id=res.get("id"), extra={"jid": res.get("jid")})
