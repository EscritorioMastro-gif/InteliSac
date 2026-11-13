"""Login e cadastro de usuários pelo Supabase Auth (Supabase simulado)."""

import pytest

from app import supabase_auth
from app.config import settings

API = "/api/v1"

# "Supabase" falso: e-mail -> (id, senha)
FAKE = {"gabriel@exemplo.com": ("auth-gabriel", "SenhaForte!1")}


@pytest.fixture
def supabase_on(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "https://projeto.supabase.co")
    monkeypatch.setattr(settings, "supabase_anon_key", "chave-anon")
    monkeypatch.setattr(settings, "supabase_service_role_key", "chave-secreta")
    calls = {"created": [], "updated": []}

    async def sign_in(email, password):
        rec = FAKE.get(email)
        return {"id": rec[0], "email": email} if rec and rec[1] == password else None

    def find_user_by_email(email):
        rec = FAKE.get(email)
        return {"id": rec[0], "email": email, "email_confirmed_at": "2026-11-13"} if rec else None

    def create_user(email, password, name=None):
        FAKE[email] = (f"auth-{len(FAKE)}", password)
        calls["created"].append(email)
        return {"id": FAKE[email][0]}

    def update_user(auth_user_id, **fields):
        calls["updated"].append((auth_user_id, fields))
        for email, (uid, _pw) in list(FAKE.items()):
            if uid == auth_user_id and "password" in fields:
                FAKE[email] = (uid, fields["password"])
        return {"id": auth_user_id}

    monkeypatch.setattr(supabase_auth, "sign_in", sign_in)
    monkeypatch.setattr(supabase_auth, "find_user_by_email", find_user_by_email)
    monkeypatch.setattr(supabase_auth, "create_user", create_user)
    monkeypatch.setattr(supabase_auth, "update_user", update_user)
    return calls


def _login(client, email, password):
    return client.post(f"{API}/oauth/token", data={"grant_type": "password", "username": email, "password": password})


def test_usuario_do_supabase_nao_cadastrado_no_intelisac(client, supabase_on):
    r = _login(client, "gabriel@exemplo.com", "SenhaForte!1")
    assert r.status_code == 403 and r.json()["detail"]["error"] == "not_registered"


def test_vincular_usuario_existente_sem_senha_e_logar(client, auth, supabase_on):
    r = client.post(f"{API}/users", json={"name": "Gabriel", "email": "Gabriel@Exemplo.com", "isAdmin": True}, headers=auth)
    assert r.status_code == 201, r.text
    u = r.json()
    assert u["authProvider"] == "supabase" and supabase_on["created"] == []

    assert _login(client, "gabriel@exemplo.com", "errada").status_code == 401
    r = _login(client, "gabriel@exemplo.com", "SenhaForte!1")
    assert r.status_code == 200
    me = client.get(f"{API}/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).json()
    assert me["email"] == "gabriel@exemplo.com" and me["isAdmin"] is True


def test_admin_cria_atendente_e_troca_senha(client, auth, supabase_on):
    r = client.post(f"{API}/users", json={"name": "Ana", "email": "ana@exemplo.com", "password": "senha-da-ana-1"}, headers=auth)
    assert r.status_code == 201 and supabase_on["created"] == ["ana@exemplo.com"]
    assert _login(client, "ana@exemplo.com", "senha-da-ana-1").status_code == 200

    uid = r.json()["id"]
    assert client.put(f"{API}/users/{uid}", json={"password": "curta"}, headers=auth).status_code == 422
    assert client.put(f"{API}/users/{uid}", json={"password": "nova-senha-ana-2"}, headers=auth).status_code == 200
    assert supabase_on["updated"][-1][1] == {"password": "nova-senha-ana-2"}
    assert _login(client, "ana@exemplo.com", "nova-senha-ana-2").status_code == 200

    # Sem senha e sem usuário no Supabase: não deixa criar
    r = client.post(f"{API}/users", json={"name": "Sem Senha", "email": "sem@exemplo.com"}, headers=auth)
    assert r.status_code == 422


def test_arquivado_nao_entra(client, auth, supabase_on):
    uid = next(u["id"] for u in client.get(f"{API}/users", headers=auth).json()["data"] if u["email"] == "ana@exemplo.com")
    client.post(f"{API}/users/{uid}/archive", json={}, headers=auth)
    assert _login(client, "ana@exemplo.com", "nova-senha-ana-2").status_code == 403


def test_admin_do_seed_com_senha_local_continua_entrando(client, supabase_on):
    assert _login(client, "admin@teste.local", "senha-de-teste-123").status_code == 200


def test_supabase_fora_do_ar(client, supabase_on, monkeypatch):
    async def fora(email, password):
        raise supabase_auth.AuthServiceError("timeout")

    monkeypatch.setattr(supabase_auth, "sign_in", fora)
    assert _login(client, "gabriel@exemplo.com", "SenhaForte!1").status_code == 503
    # Quem tem senha local ainda entra (acesso de emergência)
    assert _login(client, "admin@teste.local", "senha-de-teste-123").status_code == 200
