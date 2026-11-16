"""Revisão de segurança (2026-11-16): o que protege o InteliSac na internet."""

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from app import realtime, supabase_auth
from app.config import Settings, settings
from app.db import SessionLocal
from app.main import asgi
from app.models import User
from app.security import create_tokens

API = "/api/v1"


def _login(client, email, password):
    return client.post(f"{API}/oauth/token", data={"grant_type": "password", "username": email, "password": password})


# ---------- login ----------

def test_muitas_senhas_erradas_bloqueiam_o_email(client):
    for _ in range(8):
        assert _login(client, "admin@teste.local", "errada").status_code == 401
    r = _login(client, "admin@teste.local", "errada")
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0
    # bloqueado vale até para a senha certa (quem está tentando não sabe se acertou)
    assert _login(client, "admin@teste.local", "senha-de-teste-123").status_code == 429


def test_muitas_senhas_erradas_do_mesmo_ip(client):
    for i in range(20):
        assert _login(client, f"alguem{i}@teste.local", "errada").status_code == 401
    assert _login(client, "admin@teste.local", "senha-de-teste-123").status_code == 429


def test_login_com_corpo_estranho_nao_quebra(client):
    r = client.post(f"{API}/oauth/token", content="[1, 2]", headers={"Content-Type": "application/json"})
    assert r.status_code == 400
    r = client.post(f"{API}/oauth/token", content="{nao é json", headers={"Content-Type": "application/json"})
    assert r.status_code == 400


def test_conta_do_supabase_com_mesmo_email_nao_entra_sem_vinculo(client, auth, monkeypatch):
    """Cadastro público do Supabase: alguém cria conta com o e-mail de um colaborador que ainda
    não foi vinculado. Antes, o e-mail igual bastava para entrar como esse colaborador."""
    r = client.post(f"{API}/users", json={"name": "Carla Local", "email": "carla@teste.local", "password": "senha-local-123"}, headers=auth)
    assert r.status_code == 201, r.text

    monkeypatch.setattr(settings, "supabase_url", "https://projeto.supabase.co")
    monkeypatch.setattr(settings, "supabase_anon_key", "chave-anon")

    async def sign_in(email, password):  # o "invasor" criou essa conta no Supabase
        return {"id": "conta-do-invasor", "email": email} if password == "senha-do-invasor" else None

    monkeypatch.setattr(supabase_auth, "sign_in", sign_in)
    r = _login(client, "carla@teste.local", "senha-do-invasor")
    assert r.status_code == 403 and r.json()["detail"]["error"] == "not_registered"
    with SessionLocal() as db:
        assert db.query(User).filter(User.email == "carla@teste.local").one().auth_user_id is None


# ---------- simulador e webhook ----------

def test_simulador_nao_injeta_mensagem_no_whatsapp_de_verdade(client, auth):
    wa = client.post(f"{API}/services", json={"name": "WhatsApp Real", "type": "whatsapp"}, headers=auth).json()
    r = client.post(f"{API}/simulator/inbound", json={"serviceId": wa["id"], "from": "5516900001111", "text": "falsa"}, headers=auth)
    assert r.status_code == 404
    # nem pelo webhook (o WhatsApp por QR só recebe pelo gateway, com o segredo dele)
    with SessionLocal() as db:
        from app.models import Service

        token = db.get(Service, wa["id"]).webhook_token
    r = client.post(f"{API}/channels/{wa['id']}/webhook", json={"from": "1", "text": "oi"}, headers={"X-Channel-Token": token})
    assert r.status_code == 401


def test_simulador_desligado_em_producao(client, auth, monkeypatch):
    sim = next(s for s in client.get(f"{API}/services", headers=auth).json()["data"] if s["type"] == "simulador")
    monkeypatch.setattr(settings, "enable_simulator", False)
    r = client.post(f"{API}/simulator/inbound", json={"serviceId": sim["id"], "from": "5516900002222", "text": "oi"}, headers=auth)
    assert r.status_code == 404
    assert client.get(f"{API}/me", headers=auth).json()["features"] == {"simulator": False}


# ---------- configuração de produção ----------

def test_producao_recusa_configuracao_fraca():
    fraca = Settings()
    fraca.jwt_secret = "dev-secret-troque"
    fraca.gateway_secret = "curto"
    fraca.cors_origins = ["http://localhost:5180"]
    fraca.supabase_url = fraca.supabase_anon_key = fraca.supabase_service_role_key = ""
    fraca.database_url = "sqlite:///x.db"
    assert len(fraca.problemas_de_producao()) == 5

    forte = Settings()
    forte.jwt_secret = "j" * 48
    forte.gateway_secret = "g" * 64
    forte.cors_origins = ["https://intelisac.onrender.com"]
    forte.supabase_url, forte.supabase_anon_key, forte.supabase_service_role_key = "https://x.supabase.co", "a", "s"
    forte.database_url = "postgresql+psycopg://u:p@h/db"
    assert forte.problemas_de_producao() == []


# ---------- teto de corpo e cabeçalhos (app completo, como no servidor) ----------

def test_cabecalhos_de_seguranca_e_teto_do_corpo(client):
    completo = TestClient(asgi)
    r = completo.get(f"{API}/health")
    assert r.status_code == 200
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["cache-control"] == "no-store"
    assert "microphone=(self)" in r.headers["permissions-policy"]

    grande = b"x" * (3 * 1024 * 1024)
    r = completo.post(f"{API}/contacts", content=grande, headers={"Content-Type": "application/json"})
    assert r.status_code == 413
    # envio de arquivo tem teto maior (até 50 MB): 3 MB passa do teto e chega na rota (401 sem login)
    r = completo.post(f"{API}/messages/media", content=grande, headers={"Content-Type": "application/octet-stream"})
    assert r.status_code in (401, 422)


# ---------- tempo real ----------

@pytest.fixture
def socket_falso(monkeypatch):
    salas, derrubados = [], []

    async def save_session(sid, data):
        pass

    async def enter_room(sid, room):
        salas.append((sid, room))

    async def disconnect(sid):
        derrubados.append(sid)

    monkeypatch.setattr(realtime.sio, "save_session", save_session)
    monkeypatch.setattr(realtime.sio, "enter_room", enter_room)
    monkeypatch.setattr(realtime.sio, "disconnect", disconnect)
    realtime._conexoes.clear()
    yield salas, derrubados
    realtime._conexoes.clear()


def _admin_id():
    with SessionLocal() as db:
        u = db.query(User).filter(User.email == "admin@teste.local").one()
        return u.id, u.account_id


def test_tempo_real_so_com_token_no_auth(client, socket_falso):
    salas, _ = socket_falso
    uid, acc = _admin_id()
    token = create_tokens(uid, acc)["access_token"]
    # token no endereço (aparece nos logs) não vale mais
    with pytest.raises(Exception):
        asyncio.run(realtime.connect("s1", {"QUERY_STRING": f"access_token={token}"}, None))
    asyncio.run(realtime.connect("s2", {}, {"access_token": token}))
    assert ("s2", f"account:{acc}") in salas and "s2" in realtime._conexoes


def test_tempo_real_derruba_token_vencido_e_usuario_arquivado(client, auth, socket_falso):
    _, derrubados = socket_falso
    r = client.post(f"{API}/users", json={"name": "Duda", "email": "duda@teste.local", "password": "senha-da-duda-1"}, headers=auth)
    duda = r.json()["id"]
    uid, _acc = _admin_id()
    realtime._conexoes.update({
        "vencido": (uid, time.time() - 5, 0),
        "valido": (uid, time.time() + 3600, 0),
        "da-duda": (duda, time.time() + 3600, 0),
    })
    client.post(f"{API}/users/{duda}/archive", json={}, headers=auth)
    assert asyncio.run(realtime.desconectar_vencidos()) == 2
    assert set(derrubados) == {"vencido", "da-duda"} and set(realtime._conexoes) == {"valido"}

    # e quem está arquivado nem conecta
    with SessionLocal() as db:
        u = db.get(User, duda)
        token = create_tokens(u.id, u.account_id)["access_token"]
        assert u.archived_at is not None
    with pytest.raises(Exception):
        asyncio.run(realtime.connect("s3", {}, {"access_token": token}))
