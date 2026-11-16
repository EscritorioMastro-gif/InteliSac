"""WhatsApp Business Cloud API (oficial da Meta) — ainda não implementado (Fase 1).

Configuração esperada em Service.data:
    {"phoneNumberId": "...", "accessToken": "...", "verifyToken": "..."}

Envio:  POST https://graph.facebook.com/v21.0/{phoneNumberId}/messages
        {"messaging_product": "whatsapp", "to": "55DDDNNNNNNNN", "type": "text", "text": {"body": "..."}}
Entrada: a Meta chama o webhook da conexão com `entry[].changes[].value.messages[]`.
"""

from .base import ChannelAdapter, SendResult


class WhatsAppCloudAdapter(ChannelAdapter):
    type = "whatsapp-business"

    async def send_text(self, service, contact, text: str, quoted=None, forwarded=False) -> SendResult:
        return SendResult(ok=False, error="Canal WhatsApp Cloud ainda não implementado (Fase 1)")
