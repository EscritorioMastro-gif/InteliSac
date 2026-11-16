"""A API também entrega a tela (React já montado em frontend/dist).

No Render é um serviço só: tela, API e tempo real no mesmo endereço (sem CORS, login e socket juntos).
Em desenvolvimento a tela continua no Vite (porta 5180); se existir um frontend/dist montado, ela
também abre em http://localhost:8010.

Cabeçalhos da página: CSP que só deixa rodar script do próprio site e só conversar com a própria
API/tempo real e com o Supabase (fotos, áudios e arquivos). Um script injetado não consegue mandar
o login guardado no navegador para outro lugar.
"""

import os
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from .config import settings

DIST = Path(os.getenv("FRONTEND_DIST") or Path(__file__).resolve().parents[2] / "frontend" / "dist").resolve()
# As telas do sistema são /login, /contatos... (sem ponto). Pedido com cara de arquivo (.env, x.php,
# .git/config) que não existe na tela é sondagem: responde 404 em vez de devolver a página.
_CARA_DE_ARQUIVO = re.compile(r"(^|/)\.|\.[A-Za-z0-9]{1,8}$")


class _Arquivos(StaticFiles):
    """JS/CSS do build têm o hash no nome: podem ficar em cache por 1 ano."""

    async def get_response(self, path, scope):
        resposta = await super().get_response(path, scope)
        if resposta.status_code == 200:
            resposta.headers["cache-control"] = "public, max-age=31536000, immutable"
        return resposta


def csp(request: Request) -> str:
    host = request.headers.get("host", "")
    ws = f"{'wss' if settings.is_production else 'ws'}://{host}" if host else ""
    supa = settings.supabase_url
    return "; ".join(
        [
            "default-src 'self'",
            "script-src 'self'",
            "style-src 'self'",
            f"img-src 'self' data: blob: {supa}".strip(),
            f"media-src 'self' blob: {supa}".strip(),
            f"connect-src 'self' {ws}".strip(),
            "font-src 'self'",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        ]
    )


def montar(app: FastAPI) -> bool:
    """Liga a entrega da tela. Chamar DEPOIS de incluir as rotas da API. Devolve se ligou."""
    index = DIST / "index.html"
    if not index.is_file():
        return False
    if (DIST / "assets").is_dir():
        app.mount("/assets", _Arquivos(directory=DIST / "assets"), name="assets")

    @app.get("/robots.txt", include_in_schema=False)
    def robots():
        return PlainTextResponse("User-agent: *\nDisallow: /\n")

    @app.get("/{caminho:path}", include_in_schema=False)
    def tela(caminho: str, request: Request):
        if caminho == "api" or caminho.startswith("api/"):
            raise HTTPException(404, detail={"message": "Rota não encontrada"})
        if caminho:
            arquivo = (DIST / caminho).resolve()
            if arquivo.is_file() and DIST in arquivo.parents:
                return FileResponse(arquivo)
            if _CARA_DE_ARQUIVO.search(caminho) or "\\" in caminho:
                raise HTTPException(404, detail={"message": "Não encontrado"})
        # Qualquer outra rota (/, /login, /contatos...) é a própria tela: o React decide o que mostrar.
        return HTMLResponse(
            index.read_text(encoding="utf-8"),
            headers={"content-security-policy": csp(request), "cache-control": "no-cache"},
        )

    return True
