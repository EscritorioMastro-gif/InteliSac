"""Publicação no Render: a API entrega a tela e entende os endereços internos do Render."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import config, tela
from app.protecao import CabecalhosDeSeguranca


@pytest.fixture
def site(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>InteliSac</title><div id=root></div>", encoding="utf-8")
    (dist / "assets" / "index-abc123.js").write_text("console.log(1)", encoding="utf-8")
    (dist / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    (tmp_path / "segredo.env").write_text("JWT_SECRET=nao-pode-sair", encoding="utf-8")
    monkeypatch.setattr(tela, "DIST", dist.resolve())
    monkeypatch.setattr(tela.settings, "supabase_url", "https://projeto.supabase.co")
    app = FastAPI()

    @app.get("/api/v1/health")
    def health():
        return {"ok": True}

    assert tela.montar(app) is True
    return TestClient(CabecalhosDeSeguranca(app))


def test_tela_abre_em_qualquer_rota_com_csp(site):
    for caminho in ("/", "/login", "/contatos", "/conexoes"):
        r = site.get(caminho)
        assert r.status_code == 200 and "<div id=root>" in r.text, caminho
        csp = r.headers["content-security-policy"]
        assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp
        assert "https://projeto.supabase.co" in csp and "ws://testserver" in csp
        assert r.headers["cache-control"] == "no-cache"
        assert r.headers["x-frame-options"] == "DENY"


def test_arquivos_da_tela_com_cache_longo(site):
    r = site.get("/assets/index-abc123.js")
    assert r.status_code == 200 and "immutable" in r.headers["cache-control"]
    assert site.get("/favicon.svg").status_code == 200


def test_api_continua_api(site):
    assert site.get("/api/v1/health").json() == {"ok": True}
    r = site.get("/api/v1/nao-existe")
    assert r.status_code == 404 and "<div id=root>" not in r.text


def test_nao_entrega_arquivo_fora_da_pasta_da_tela(site):
    for caminho in ("/../segredo.env", "/%2e%2e/segredo.env", "/assets/../../segredo.env"):
        r = site.get(caminho)
        assert "nao-pode-sair" not in r.text, caminho


def test_sem_tela_montada_nao_liga(tmp_path, monkeypatch):
    monkeypatch.setattr(tela, "DIST", tmp_path / "nao-existe")
    assert tela.montar(FastAPI()) is False


def test_enderecos_do_render(monkeypatch):
    assert config._com_http("intelisac-whatsapp-abcd:10000") == "http://intelisac-whatsapp-abcd:10000"
    assert config._com_http("http://127.0.0.1:8020/") == "http://127.0.0.1:8020"
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://intelisac.onrender.com/")
    assert config._cors_padrao() == "https://intelisac.onrender.com"
    monkeypatch.delenv("RENDER_EXTERNAL_URL")
    assert "http://localhost:5180" in config._cors_padrao()


def test_no_render_simulador_desligado_e_cors_do_endereco_publico(tmp_path):
    """Roda num Python separado, como o Render: RENDER=true e endereço público."""
    import json
    import os
    import subprocess
    import sys

    env = {**os.environ, "RENDER": "true", "RENDER_EXTERNAL_URL": "https://intelisac.onrender.com"}
    # vazio (e não ausente): o .env local do PC não pode preencher esses valores no teste
    env["CORS_ORIGINS"] = ""
    env["ENABLE_SIMULATOR"] = ""
    codigo = (
        "import json; from app.config import settings as s; "
        "print(json.dumps([s.is_production, s.enable_simulator, s.cors_origins]))"
    )
    saida = subprocess.run([sys.executable, "-c", codigo], env=env, capture_output=True, text=True, check=True,
                           cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    assert json.loads(saida.stdout.strip().splitlines()[-1]) == [True, False, ["https://intelisac.onrender.com"]]
