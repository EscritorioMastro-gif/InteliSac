"""Proteções da API para ficar na internet.

- limite de tentativas de login (por IP e por e-mail), em memória;
- teto de tamanho do corpo das requisições (antes de ler tudo na memória);
- cabeçalhos de segurança em todas as respostas.
"""

import threading
import time
from collections import deque

from starlette.requests import Request

from .config import settings


# ---------------------------------------------------------------------------
# IP de quem chamou. No Render as requisições passam pela Cloudflare: o IP real vem em
# CF-Connecting-IP (a Cloudflare sobrescreve esse cabeçalho, não dá para falsificar de fora).
# ---------------------------------------------------------------------------
def ip_do_cliente(request: Request) -> str:
    cf = request.headers.get("cf-connecting-ip")
    if cf:
        return cf.strip()
    if settings.is_production:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[-1].strip()  # o último é o que o proxy do Render viu
    return request.client.host if request.client else "?"


# ---------------------------------------------------------------------------
# Limite de tentativas
# ---------------------------------------------------------------------------
class Limite:
    """Conta falhas numa janela de tempo. Passou de `maximo` → bloqueado até a falha mais antiga sair."""

    def __init__(self, maximo: int, janela_segundos: int):
        self.maximo = maximo
        self.janela = janela_segundos
        self._falhas: dict[str, deque] = {}
        self._lock = threading.Lock()

    def _limpa(self, chave: str, agora: float) -> deque:
        fila = self._falhas.setdefault(chave, deque())
        while fila and agora - fila[0] > self.janela:
            fila.popleft()
        return fila

    def espera(self, chave: str) -> int:
        """Segundos até poder tentar de novo (0 = liberado)."""
        agora = time.monotonic()
        with self._lock:
            fila = self._limpa(chave, agora)
            if len(fila) < self.maximo:
                return 0
            return max(1, int(self.janela - (agora - fila[0])) + 1)

    def falhou(self, chave: str) -> None:
        agora = time.monotonic()
        with self._lock:
            self._limpa(chave, agora).append(agora)
            if len(self._falhas) > 20_000:  # não deixa crescer sem fim com IPs aleatórios
                for k in [k for k, f in self._falhas.items() if not f][:10_000]:
                    del self._falhas[k]

    def zera(self, chave: str) -> None:
        with self._lock:
            self._falhas.pop(chave, None)

    def zera_tudo(self) -> None:
        with self._lock:
            self._falhas.clear()


# 30 senhas erradas do mesmo IP em 5 min, ou 10 no mesmo e-mail em 15 min → espera.
login_por_ip = Limite(30, 5 * 60)
login_por_email = Limite(10, 15 * 60)


# ---------------------------------------------------------------------------
# Teto do corpo das requisições (ASGI puro: barra antes de ler o arquivo inteiro)
# ---------------------------------------------------------------------------
MB = 1024 * 1024
TETOS = (
    ("/api/v1/gateway/events", 90 * MB),  # arquivo recebido no WhatsApp (até 50 MB) vem em base64
    ("/api/v1/messages/media", 55 * MB),  # envio de arquivo (até 50 MB)
)
TETO_PADRAO = 2 * MB


def teto_para(path: str) -> int:
    for prefixo, teto in TETOS:
        if path.startswith(prefixo):
            return teto
    return TETO_PADRAO


class CorpoGrandeDemais(Exception):
    pass


class LimiteDeCorpo:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        teto = teto_para(scope.get("path", ""))
        for nome, valor in scope.get("headers", []):
            if nome == b"content-length":
                try:
                    if int(valor) > teto:
                        return await _responde_413(send, teto)
                except ValueError:
                    pass
        recebido = 0
        respondeu = False

        async def receive_com_teto():
            nonlocal recebido
            msg = await receive()
            if msg["type"] == "http.request":
                recebido += len(msg.get("body", b""))
                if recebido > teto:
                    raise CorpoGrandeDemais()
            return msg

        async def send_marcando(msg):
            nonlocal respondeu
            if msg["type"] == "http.response.start":
                respondeu = True
            await send(msg)

        try:
            await self.app(scope, receive_com_teto, send_marcando)
        except CorpoGrandeDemais:
            if not respondeu:
                await _responde_413(send, teto)


async def _responde_413(send, teto: int):
    corpo = ('{"detail":{"message":"Arquivo ou requisição maior que %d MB"}}' % (teto // MB)).encode()
    await send({
        "type": "http.response.start",
        "status": 413,
        "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(corpo)).encode())],
    })
    await send({"type": "http.response.body", "body": corpo})


# ---------------------------------------------------------------------------
# Cabeçalhos de segurança
# ---------------------------------------------------------------------------
CABECALHOS_API = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"permissions-policy", b"camera=(), geolocation=(), microphone=(self)"),
    (b"cache-control", b"no-store"),
    (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
]
HSTS = (b"strict-transport-security", b"max-age=31536000")


class CabecalhosDeSeguranca:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_com_cabecalhos(msg):
            if msg["type"] == "http.response.start":
                headers = list(msg.get("headers", []))
                existentes = {k.lower() for k, _ in headers}
                extras = CABECALHOS_API + ([HSTS] if settings.is_production else [])
                headers += [(k, v) for k, v in extras if k not in existentes]
                msg = {**msg, "headers": headers}
            await send(msg)

        await self.app(scope, receive, send_com_cabecalhos)
