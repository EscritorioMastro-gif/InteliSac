from dataclasses import dataclass, field


@dataclass
class SendResult:
    ok: bool
    external_id: str | None = None
    error: str | None = None
    # Dados que o canal devolve sobre o destinatário (ex.: jid do WhatsApp resolvido pelo número)
    extra: dict = field(default_factory=dict)


@dataclass
class Quoted:
    """Mensagem citada ao responder ("responder marcando")."""

    id: str  # id da mensagem no canal (external_id)
    from_me: bool
    text: str
    participant: str | None = None  # em grupo: quem escreveu a mensagem citada


@dataclass
class MediaOut:
    """Arquivo a enviar: o canal baixa pelo link temporário do Supabase Storage."""

    url: str
    mimetype: str
    file_name: str
    kind: str  # image | video | audio | document
    caption: str | None = None
    ptt: bool = False  # áudio gravado = mensagem de voz
    seconds: int | None = None  # duração do áudio
    waveform: list[int] | None = None  # 64 valores 0–100 (barrinhas da mensagem de voz)


class ChannelAdapter:
    """Interface que todo canal implementa."""

    type: str = "base"

    async def send_text(self, service, contact, text: str, quoted: Quoted | None = None) -> SendResult:  # pragma: no cover
        raise NotImplementedError

    async def send_media(self, service, contact, media: MediaOut, quoted: Quoted | None = None) -> SendResult:
        return SendResult(ok=False, error="Este canal ainda não envia arquivos")

    async def revoke(self, service, contact, external_id: str) -> SendResult:
        return SendResult(ok=False, error="Este canal não permite apagar mensagens")
