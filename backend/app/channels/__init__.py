"""Adaptadores de canal. Cada tipo de conexão (Service.type) tem um adaptador que sabe
enviar mensagens para fora. A entrada chega por:
- whatsapp (QR code): eventos do whatsapp-gateway em POST /api/v1/gateway/events
- outros canais: POST /api/v1/channels/{serviceId}/webhook
"""

from .base import ChannelAdapter, SendResult
from .simulador import SimuladorAdapter
from .whatsapp_cloud import WhatsAppCloudAdapter
from .whatsapp_qr import WhatsAppQrAdapter

_ADAPTERS: dict[str, ChannelAdapter] = {
    "simulador": SimuladorAdapter(),
    "whatsapp": WhatsAppQrAdapter(),
    "whatsapp-business": WhatsAppCloudAdapter(),
}


def get_adapter(service_type: str) -> ChannelAdapter:
    return _ADAPTERS.get(service_type, _ADAPTERS["simulador"])


__all__ = ["ChannelAdapter", "SendResult", "get_adapter"]
