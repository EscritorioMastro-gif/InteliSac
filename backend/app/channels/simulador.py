import uuid

from .base import ChannelAdapter, MediaOut, Quoted, SendResult


class SimuladorAdapter(ChannelAdapter):
    """Canal de teste: não envia nada para fora; a mensagem só fica registrada no sistema.
    O 'cliente' responde pela tela Simulador, que chama o webhook de entrada."""

    type = "simulador"

    async def send_text(self, service, contact, text: str, quoted: Quoted | None = None, forwarded: bool = False) -> SendResult:
        return SendResult(ok=True, external_id=f"sim-{uuid.uuid4().hex[:12]}")

    async def send_media(self, service, contact, media: MediaOut, quoted: Quoted | None = None, forwarded: bool = False) -> SendResult:
        return SendResult(ok=True, external_id=f"sim-{uuid.uuid4().hex[:12]}")

    async def revoke(self, service, contact, external_id: str) -> SendResult:
        return SendResult(ok=True)

    async def edit(self, service, contact, external_id: str, text: str) -> SendResult:
        return SendResult(ok=True)
