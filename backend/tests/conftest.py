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
