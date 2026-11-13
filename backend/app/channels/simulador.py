import uuid

from .base import ChannelAdapter, SendResult


class SimuladorAdapter(ChannelAdapter):
    """Canal de teste: não envia nada para fora; a mensagem só fica registrada no sistema.
    O 'cliente' responde pela tela Simulador, que chama o webhook de entrada."""

    type = "simulador"

    async def send_text(self, service, contact, text: str) -> SendResult:
        return SendResult(ok=True, external_id=f"sim-{uuid.uuid4().hex[:12]}")
