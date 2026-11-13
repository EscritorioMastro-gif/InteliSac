from dataclasses import dataclass, field


@dataclass
class SendResult:
    ok: bool
    external_id: str | None = None
    error: str | None = None
    # Dados que o canal devolve sobre o destinatário (ex.: jid do WhatsApp resolvido pelo número)
    extra: dict = field(default_factory=dict)


class ChannelAdapter:
    """Interface que todo canal implementa."""

    type: str = "base"

    async def send_text(self, service, contact, text: str) -> SendResult:  # pragma: no cover
        raise NotImplementedError
