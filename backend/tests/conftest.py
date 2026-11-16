import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="intelisac-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_tmp / 'test.db').as_posix()}"
os.environ["JWT_SECRET"] = "segredo-de-teste-com-mais-de-32-bytes!"
os.environ["SEED_ADMIN_EMAIL"] = "admin@teste.local"
os.environ["SEED_ADMIN_PASSWORD"] = "senha-de-teste-123"
os.environ["GATEWAY_SECRET"] = "segredo-do-gateway-de-teste"
os.environ["WHATSAPP_GATEWAY_URL"] = "http://127.0.0.1:9"  # porta fechada: simula gateway fora do ar
# Os testes nunca usam o Supabase de verdade (valores vazios impedem o .env de preencher)
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_ANON_KEY"] = ""
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import seed  # noqa: E402
from app.main import app  # noqa: E402


def pytest_configure(config):
    config.addinivalue_line("markers", "fotos_de_verdade: roda a busca da foto do perfil (com WhatsApp falso)")


@pytest.fixture(autouse=True)
def limites_de_login_zerados():
    """Cada teste começa sem tentativas de login erradas contadas (todos vêm do mesmo IP)."""
    from app import protecao

    protecao.login_por_ip.zera_tudo()
    protecao.login_por_email.zera_tudo()
    yield


@pytest.fixture(autouse=True)
def sem_busca_de_fotos(request, monkeypatch):
    """A busca da foto do perfil roda em segundo plano e falaria com o WhatsApp; nos testes
    gerais fica desligada (test_avisos_grupos_fotos testa ela de propósito)."""
    if "fotos_de_verdade" in request.keywords:
        return
    from app import avatars

    async def nada(*_a, **_k):
        return None

    monkeypatch.setattr(avatars, "refresh", nada)
    monkeypatch.setattr(avatars, "refresh_many", nada)


@pytest.fixture(scope="session")
def client():
    seed.run()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def auth(client):
    r = client.post(
        "/api/v1/oauth/token",
        data={"grant_type": "password", "username": "admin@teste.local", "password": "senha-de-teste-123"},
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
