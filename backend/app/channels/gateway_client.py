"""Cliente HTTP do gateway WhatsApp (pasta whatsapp-gateway/, Node + Baileys)."""

import httpx

from ..config import settings


class GatewayError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


async def gateway_request(method: str, path: str, json: dict | None = None, timeout: float = 30.0) -> dict:
    url = f"{settings.whatsapp_gateway_url}{path}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            res = await client.request(method, url, json=json, headers={"X-Gateway-Secret": settings.gateway_secret})
    except httpx.HTTPError as e:
        raise GatewayError(
            "Serviço do WhatsApp fora do ar. Inicie o whatsapp-gateway (npm start).", status=503
        ) from e
    try:
        body = res.json()
    except ValueError:
        body = {}
    if res.status_code >= 400:
        raise GatewayError(body.get("message") or f"Gateway respondeu {res.status_code}", status=res.status_code)
    return body
