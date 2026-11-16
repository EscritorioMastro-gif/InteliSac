"""Segunda revisão de segurança (2026-11-16, com o sistema no ar): o que foi achado testando
https://intelisac.onrender.com por fora e as proteções novas."""

import asyncio
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import realtime, tela
from app.db import SessionLocal
from app.main import asgi
from app.models import User
from app.protecao import CabecalhosDeSeguranca
from app.security import create_tokens

API = "/api/v1"
GW = {"X-Gateway-Secret": "segredo-do-gateway-de-teste"}
GRANDE = b"a" * (3 * 1024 * 1024)


def _login(client, email, password, ip=None):
    headers = {"cf-connecting-ip": ip} if ip else {}
    return client.post(f"{API}/oauth/token", data={"grant_type": "password", "username": email, "password": password}, headers=headers)


def _novo_usuario(client, auth, nome, email, senha="senha-inicial-123", **extra):
    r = client.post(f"{API}/users", json={"name": nome, "email": email, "password": senha, **extra}, headers=auth)
    assert r.status_code == 201, r.text
    tokens = _login(client, email, senha).json()
    return r.json(), tokens, {"Authorization": f"Bearer {tokens['access_token']}"}


# ---------- corpo grande só depois de provar o acesso ----------

def test_corpo_grande_sem_acesso_e_recusado_antes_de_ser_lido(client, auth):
    completo = TestClient(asgi)
    # Antes: o servidor lia e interpretava os 3 MB (até 90 MB!) e só depois recusava (422/401).
    r = completo.post(f"{API}/gateway/events", content=GRANDE, headers={"Content-Type": "application/json"})
    assert r.status_code == 401
    r = completo.post(f"{API}/gateway/events", content=GRANDE, headers={"Content-Type": "application/json", "X-Gateway-Secret": "errado"})
    assert r.status_code == 401
    r = completo.post(f"{API}/messages/media", content=GRANDE, headers={"Content-Type": "application/octet-stream"})
    assert r.status_code == 401
    r = completo.post(f"{API}/messages/media", content=GRANDE, headers={"Content-Type": "application/octet-stream", "Authorization": "Bearer token.falso.aqui"})
    assert r.status_code == 401

    # com o acesso certo o corpo passa e quem responde é a rota
    r = completo.post(f"{API}/gateway/events", content=GRANDE, headers={"Content-Type": "application/json", **GW})
    assert r.status_code == 422  # passou do portão; a rota reclama do JSON inválido
    r = completo.post(f"{API}/messages/media", content=GRANDE, headers={"Content-Type": "application/octet-stream", **auth})
    assert r.status_code == 422  # passou do portão; a rota reclama que não veio arquivo


# ---------- sair e trocar senha encerram os logins ----------

def test_sair_encerra_o_login_no_servidor(client, auth):
    _u, tokens, h = _novo_usuario(client, auth, "Sara Sai", "sara@teste.local")
    assert client.get(f"{API}/me", headers=h).status_code == 200
    assert client.post(f"{API}/oauth/revoke", headers=h).json() is True

    # o token copiado/roubado não serve mais, nem o de renovação
    assert client.get(f"{API}/me", headers=h).status_code == 401
    r = client.post(f"{API}/oauth/token", data={"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"]})
    assert r.status_code == 401
    # entrar de novo funciona, e o admin não foi afetado
    novo = _login(client, "sara@teste.local", "senha-inicial-123")
    assert novo.status_code == 200
    assert client.get(f"{API}/me", headers={"Authorization": f"Bearer {novo.json()['access_token']}"}).status_code == 200
    assert client.get(f"{API}/me", headers=auth).status_code == 200
    assert client.post(f"{API}/oauth/revoke").status_code == 401  # sair exige estar logado


def test_admin_troca_a_senha_e_o_login_antigo_cai(client, auth):
    u, _tokens, h = _novo_usuario(client, auth, "Tiago Troca", "tiago@teste.local")
    assert client.put(f"{API}/users/{u['id']}", json={"password": "senha-trocada-456"}, headers=auth).status_code == 200
    assert client.get(f"{API}/me", headers=h).status_code == 401
    assert _login(client, "tiago@teste.local", "senha-trocada-456").status_code == 200
    # mudar só o nome não derruba ninguém
    h2 = {"Authorization": f"Bearer {_login(client, 'tiago@teste.local', 'senha-trocada-456').json()['access_token']}"}
    client.put(f"{API}/users/{u['id']}", json={"name": "Tiago T."}, headers=auth)
    assert client.get(f"{API}/me", headers=h2).status_code == 200


def test_trocar_a_propria_senha_derruba_os_outros_aparelhos(client, auth):
    _u, _t, h_pc = _novo_usuario(client, auth, "Vera Varios", "vera@teste.local")
    h_celular = {"Authorization": f"Bearer {_login(client, 'vera@teste.local', 'senha-inicial-123').json()['access_token']}"}
    r = client.put(f"{API}/me", json={"currentPassword": "senha-inicial-123", "password": "senha-nova-da-vera"}, headers=h_pc)
    assert r.status_code == 200 and r.json()["tokens"]["access_token"]
    assert client.get(f"{API}/me", headers=h_celular).status_code == 401  # o outro aparelho caiu
    novo = {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}
    assert client.get(f"{API}/me", headers=novo).status_code == 200  # quem trocou segue logado


# ---------- limite de tentativas não tranca o dono da conta ----------

def test_ataque_de_fora_nao_bloqueia_o_login_do_escritorio(client):
    for _ in range(8):
        assert _login(client, "admin@teste.local", "chute", ip="203.0.113.50").status_code == 401
    assert _login(client, "admin@teste.local", "chute", ip="203.0.113.50").status_code == 429
    # o dono, do IP do escritório, entra normalmente
    assert _login(client, "admin@teste.local", "senha-de-teste-123", ip="198.51.100.7").status_code == 200


def test_ataque_espalhado_no_mesmo_email_tambem_para(client):
    for i in range(50):
        assert _login(client, "admin@teste.local", "chute", ip=f"203.0.113.{i}").status_code == 401
    assert _login(client, "admin@teste.local", "chute", ip="203.0.113.200").status_code == 429


# ---------- QR code só para administrador ----------

@pytest.fixture
def conexao_com_qr(client, auth):
    s = client.post(f"{API}/services", json={"name": "WhatsApp QR", "type": "whatsapp"}, headers=auth).json()
    r = client.post(f"{API}/gateway/events", json={"type": "status", "serviceId": s["id"], "status": "qr", "qr": "data:image/png;base64,QRSECRETO"}, headers=GW)
    assert r.status_code == 200
    return s


def test_qr_code_so_para_administrador(client, auth, conexao_com_qr):
    sid = conexao_com_qr["id"]
    _u, _t, atendente = _novo_usuario(client, auth, "Quico Atendente", "quico@teste.local")

    admin_ve = client.get(f"{API}/services/{sid}", headers=auth).json()
    assert admin_ve["data"]["qrCode"] == "data:image/png;base64,QRSECRETO"

    r = client.get(f"{API}/services/{sid}", headers=atendente).json()
    assert r["data"]["qrCode"] is None and r["data"]["hasQr"] is True and r["data"]["status"] == "qr"
    lista = client.get(f"{API}/services", params={"perPage": 100}, headers=atendente).text
    assert "QRSECRETO" not in lista
    assert client.get(f"{API}/services/{sid}/connection", headers=atendente).status_code == 403


def test_tempo_real_manda_o_qr_so_para_a_sala_dos_admins(client, auth, conexao_com_qr, monkeypatch):
    enviados = []

    async def fake_emit(evento, payload, room=None):
        enviados.append((evento, room, payload))

    monkeypatch.setattr(realtime.sio, "emit", fake_emit)
    sid = conexao_com_qr["id"]
    client.post(f"{API}/gateway/events", json={"type": "status", "serviceId": sid, "status": "qr", "qr": "data:image/png;base64,QRNOVO"}, headers=GW)
    para_todos = [(e, sala, p) for e, sala, p in enviados if sala.startswith("account:")]
    assert para_todos and all("QRNOVO" not in str(p) for _e, _s, p in para_todos)
    so_admins = [(e, sala, p) for e, sala, p in enviados if sala.startswith("admins:")]
    assert len(so_admins) == 1 and so_admins[0][0] == "service.qr" and so_admins[0][2] == {"id": sid, "qrCode": "data:image/png;base64,QRNOVO"}


# ---------- tempo real: versão do acesso e sala dos admins ----------

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


def test_tempo_real_recusa_login_encerrado_e_separa_admins(client, auth, socket_falso):
    salas, derrubados = socket_falso
    u, tokens, h = _novo_usuario(client, auth, "Rita Real", "rita@teste.local")
    asyncio.run(realtime.connect("da-rita", {}, {"access_token": tokens["access_token"]}))
    assert ("da-rita", f"account:{u['accountId']}") in salas
    assert not any(sala.startswith("admins:") for sid, sala in salas if sid == "da-rita")  # atendente não entra

    with SessionLocal() as db:
        adm = db.query(User).filter(User.email == "admin@teste.local").one()
        token_admin = create_tokens(adm.id, adm.account_id, adm.token_version)["access_token"]
    asyncio.run(realtime.connect("do-admin", {}, {"access_token": token_admin}))
    assert ("do-admin", f"admins:{u['accountId']}") in salas

    # a Rita clica em Sair: a tela dela cai na hora e o token antigo não reconecta
    assert client.post(f"{API}/oauth/revoke", headers=h).status_code == 200
    assert "da-rita" in derrubados and "da-rita" not in realtime._conexoes and "do-admin" in realtime._conexoes
    with pytest.raises(Exception):
        asyncio.run(realtime.connect("de-novo", {}, {"access_token": tokens["access_token"]}))


def test_vigia_derruba_quem_teve_a_senha_trocada(client, auth, socket_falso):
    _salas, derrubados = socket_falso
    u, _tokens, _h = _novo_usuario(client, auth, "Zeca Zero", "zeca@teste.local")
    realtime._conexoes["do-zeca"] = (u["id"], time.time() + 3600, 0)
    assert asyncio.run(realtime.desconectar_vencidos()) == 0
    client.put(f"{API}/users/{u['id']}", json={"password": "outra-senha-999"}, headers=auth)
    assert asyncio.run(realtime.desconectar_vencidos()) == 1 and derrubados == ["do-zeca"]


# ---------- sondagem de arquivos e buscadores ----------

def test_sondagem_de_arquivos_recebe_404_e_o_site_nao_e_indexado(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><div id=root></div>", encoding="utf-8")
    monkeypatch.setattr(tela, "DIST", dist.resolve())
    app = FastAPI()
    assert tela.montar(app)
    site = TestClient(CabecalhosDeSeguranca(app))
    for caminho in ("/.env", "/.git/config", "/backend/.env", "/wp-login.php", "/render.yaml", "/x/.htaccess", "/a/b.sql"):
        r = site.get(caminho)
        assert r.status_code == 404 and "<div id=root>" not in r.text, caminho
    for caminho in ("/", "/login", "/contatos", "/respostas"):
        assert site.get(caminho).status_code == 200, caminho
    r = site.get("/robots.txt")
    assert r.status_code == 200 and "Disallow: /" in r.text
    assert site.get("/login").headers["x-robots-tag"] == "noindex, nofollow"
