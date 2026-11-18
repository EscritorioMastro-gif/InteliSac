"""Módulo API: senha do módulo, chaves de API e o fluxo das rotinas que disparam guias
(mesmo formato da API do Digisac). Gateway e Storage simulados."""

import base64
import uuid

import pytest

from app import integracao, storage
from app.channels import whatsapp_qr
from app.db import SessionLocal
from app.models import ApiKey, ModuloApi, User
from app.protecao import TETO_MENSAGEM_COM_ARQUIVO

API = "/api/v1"
GW = {"X-Gateway-Secret": "segredo-do-gateway-de-teste"}
SENHA = "senha-do-modulo-de-teste"


@pytest.fixture(autouse=True)
def limites_zerados():
    integracao.envios.zera_tudo()
    from app.routers import integracao as rota

    rota.tentativas.zera_tudo()
    yield


@pytest.fixture
def gateway(monkeypatch):
    chamadas = []

    async def fake(method, path, json=None, timeout=30.0):
        chamadas.append((path.rsplit("/", 1)[-1], json))
        return {"id": f"OUT-{uuid.uuid4().hex[:10]}", "jid": json.get("jid") or f"{json.get('number')}@s.whatsapp.net"}

    monkeypatch.setattr(whatsapp_qr, "gateway_request", fake)
    return chamadas


@pytest.fixture(scope="module")
def wa(client, auth):
    return client.post(f"{API}/services", json={"name": "WhatsApp Integração", "type": "whatsapp"}, headers=auth).json()


@pytest.fixture(scope="module")
def passe(client, auth):
    """Define a senha do módulo (primeiro acesso) e devolve o cabeçalho do passe."""
    with SessionLocal() as db:
        db.query(ModuloApi).delete()
        db.commit()
    assert client.get(f"{API}/integracao/modulo", headers=auth).json() == {"configured": False}
    r = client.post(f"{API}/integracao/modulo/definir", json={"password": SENHA}, headers=auth)
    assert r.status_code == 200, r.text
    return {**auth, "X-Modulo-Token": r.json()["token"]}


@pytest.fixture(scope="module")
def chave(client, passe):
    r = client.post(f"{API}/integracao/chaves", json={"name": "Rotina de guias"}, headers=passe)
    assert r.status_code == 201, r.text
    return r.json()


def test_senha_do_modulo(client, auth, passe):
    assert client.get(f"{API}/integracao/modulo", headers=auth).json() == {"configured": True}
    # não dá para definir de novo, nem ver as chaves sem o passe
    assert client.post(f"{API}/integracao/modulo/definir", json={"password": "outra-senha-123"}, headers=auth).status_code == 409
    r = client.get(f"{API}/integracao/chaves", headers=auth)
    assert r.status_code == 403 and r.json()["detail"]["error"] == "modulo_bloqueado"
    # senha errada é 403 (não derruba o login da tela) e trava depois de 5
    for _ in range(5):
        assert client.post(f"{API}/integracao/modulo/entrar", json={"password": "errada"}, headers=auth).status_code == 403
    assert client.post(f"{API}/integracao/modulo/entrar", json={"password": SENHA}, headers=auth).status_code == 429
    from app.routers import integracao as rota

    rota.tentativas.zera_tudo()
    r = client.post(f"{API}/integracao/modulo/entrar", json={"password": SENHA}, headers=auth)
    assert r.status_code == 200 and r.json()["expiresIn"] == 1800
    assert client.get(f"{API}/integracao/chaves", headers={**auth, "X-Modulo-Token": r.json()["token"]}).status_code == 200
    # senha nunca fica em texto puro no banco
    with SessionLocal() as db:
        assert SENHA not in db.query(ModuloApi).one().senha_hash
    # trocar a senha pede a atual
    assert client.post(f"{API}/integracao/modulo/senha", json={"currentPassword": "x", "password": "nova-senha-123"}, headers=passe).status_code == 403
    assert client.post(f"{API}/integracao/modulo/senha", json={"currentPassword": SENHA, "password": "curta"}, headers=passe).status_code == 422


def test_atendente_nao_entra_no_modulo(client, auth):
    client.post(f"{API}/users", json={"name": "Ana Atendente", "email": "ana.api@teste.local", "password": "senha-da-ana-1"}, headers=auth)
    tk = client.post(f"{API}/oauth/token", data={"grant_type": "password", "username": "ana.api@teste.local", "password": "senha-da-ana-1"}).json()
    h = {"Authorization": f"Bearer {tk['access_token']}"}
    assert client.get(f"{API}/integracao/modulo", headers=h).status_code == 403
    assert client.post(f"{API}/integracao/modulo/entrar", json={"password": SENHA}, headers=h).status_code == 403


def test_chave_criada_aparece_uma_vez_e_so_o_hash_fica(client, passe, chave):
    assert chave["key"].startswith("isk_") and len(chave["key"]) > 40 and chave["prefix"] == chave["key"][:12]
    lista = client.get(f"{API}/integracao/chaves", headers=passe).json()["data"]
    item = next(c for c in lista if c["id"] == chave["id"])
    assert "key" not in item and item["name"] == "Rotina de guias" and item["createdByName"]
    with SessionLocal() as db:
        guardada = db.get(ApiKey, chave["id"])
        assert guardada.key_hash == integracao.hash_chave(chave["key"]) and chave["key"] not in str(guardada.__dict__)


def test_chave_so_alcanca_as_rotas_da_integracao(client, wa, chave):
    h = {"Authorization": f"Bearer {chave['key']}"}
    r = client.get(f"{API}/integracao/ping", headers=h)
    assert r.status_code == 200 and r.json()["key"] == "Rotina de guias" and any(s["type"] == "whatsapp" for s in r.json()["services"])
    for metodo, caminho in (("GET", "/users"), ("GET", "/me"), ("GET", "/integracao/chaves"), ("POST", "/services"),
                            ("GET", "/text/correct/status"), ("POST", "/messages/forward"), ("DELETE", "/contacts/x")):
        assert client.request(metodo, f"{API}{caminho}", headers=h, json={}).status_code in (403,), caminho
    assert client.get(f"{API}/contacts", headers={"Authorization": "Bearer isk_" + "x" * 40}).status_code == 401


def test_rotina_de_guias_como_no_digisac(client, auth, wa, chave, gateway, monkeypatch):
    """O mesmo passo a passo do Sistema Fiscal: acha/cria o contato, manda texto e o PDF da guia,
    confere se tem chamado aberto e fecha. Sem chamado aberto e sem 'assumir' nada."""
    guardados = {}

    async def upload(path, data, mimetype):
        guardados[path] = data

    monkeypatch.setattr(storage, "upload", upload)
    monkeypatch.setattr(storage, "sign_many", lambda paths, expires=3600: {p: f"https://storage.test/{p}?t=1" for p in paths})
    h = {"Authorization": f"Bearer {chave['key']}", "Content-Type": "application/json"}

    # contato novo, e o mesmo número de novo devolve o mesmo contato (200)
    r = client.post(f"{API}/contacts", json={"name": "Padaria Guia", "number": "5516991230001", "serviceId": wa["id"]}, headers=h)
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    r = client.post(f"{API}/contacts", json={"name": "Padaria Guia", "number": "5516991230001", "serviceId": wa["id"]}, headers=h)
    assert r.status_code == 200 and r.json()["id"] == cid
    achado = client.get(f"{API}/contacts", params={"where[data.number]": "5516991230001", "where[serviceId]": wa["id"], "perPage": 1}, headers=h).json()
    assert achado["data"][0]["id"] == cid

    # texto e PDF (base64 no JSON, como o Digisac)
    r = client.post(f"{API}/messages", json={"contactId": cid, "serviceId": wa["id"], "type": "chat", "text": "Segue a guia do DAS."}, headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["data"]["api"]["keyName"] == "Rotina de guias" and r.json()["userId"] is None
    pdf = b"%PDF-1.4 guia de teste"
    r = client.post(f"{API}/messages", json={"contactId": cid, "serviceId": wa["id"], "text": "",
                                              "file": {"base64": base64.b64encode(pdf).decode(), "mimetype": "application/pdf", "name": "DAS-11-2026.pdf"}}, headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["type"] == "document" and r.json()["data"]["file"]["name"] == "DAS-11-2026.pdf"
    assert list(guardados.values()) == [pdf]
    (a1, p1), (a2, p2) = gateway[-2:]
    assert a1 == "send" and p1["text"] == "Segue a guia do DAS." and "*" not in p1["text"]  # sem assinatura
    assert a2 == "send-media" and p2["kind"] == "document" and p2["fileName"] == "DAS-11-2026.pdf"

    # não abriu chamado (não enche a Fila): a rotina vê "sem atendimento aberto"
    t = client.get(f"{API}/tickets", params={"where[contactId]": cid, "where[isOpen]": "true", "perPage": 1}, headers=h).json()
    assert t["total"] == 0

    # o cliente responde: chamado abre na Fila; um envio da rotina não assume o chamado
    _evento = {"type": "message", "serviceId": wa["id"], "message": {"id": "IN-API-1", "jid": "5516991230001@s.whatsapp.net",
               "number": "5516991230001", "fromMe": False, "type": "chat", "text": "Recebi, obrigado"}}
    assert client.post(f"{API}/gateway/events", json=_evento, headers=GW).status_code == 200
    client.post(f"{API}/messages", json={"contactId": cid, "text": "Disponha!"}, headers=h)
    t = client.get(f"{API}/tickets", params={"where[contactId]": cid, "where[isOpen]": "true"}, headers=h).json()
    assert t["total"] == 1 and t["data"][0]["userId"] is None
    msgs = client.get(f"{API}/messages", params={"where[contactId]": cid, "where[ticketId]": t["data"][0]["id"], "perPage": 30}, headers=h).json()["data"]
    assert any(m["isFromMe"] is False for m in msgs)

    # fechar o chamado pela chave
    assert client.post(f"{API}/contacts/{cid}/ticket/close", json={}, headers=h).json() is True
    with SessionLocal() as db:
        robo = db.query(User).filter(User.name == integracao.NOME_ROBO).one()
        assert robo.archived_at is not None and not robo.is_admin and robo.password_hash == ""
    # o robô não aparece na lista de usuários da tela
    assert all(u["name"] != integracao.NOME_ROBO for u in client.get(f"{API}/users", params={"perPage": 200}, headers=auth).json()["data"])


def test_envio_que_falha_no_whatsapp_responde_erro(client, wa, chave, monkeypatch):
    from app.channels.gateway_client import GatewayError

    async def fora(method, path, json=None, timeout=30.0):
        raise GatewayError("WhatsApp desconectado", status=409)

    monkeypatch.setattr(whatsapp_qr, "gateway_request", fora)
    h = {"Authorization": f"Bearer {chave['key']}"}
    cid = client.post(f"{API}/contacts", json={"name": "Falha", "number": "5516991230002", "serviceId": wa["id"]}, headers=h).json()["id"]
    r = client.post(f"{API}/messages", json={"contactId": cid, "text": "oi"}, headers=h)
    assert r.status_code == 502 and "desconectado" in r.json()["detail"]["message"] and r.json()["detail"]["id"]


def test_limite_de_envios_por_chave(client, wa, chave, gateway):
    h = {"Authorization": f"Bearer {chave['key']}"}
    cid = client.post(f"{API}/contacts", json={"name": "Limite", "number": "5516991230003", "serviceId": wa["id"]}, headers=h).json()["id"]
    for _ in range(40):
        assert client.post(f"{API}/messages", json={"contactId": cid, "text": "oi"}, headers=h).status_code == 201
    r = client.post(f"{API}/messages", json={"contactId": cid, "text": "oi"}, headers=h)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0


def test_arquivo_grande_so_com_chave_valida(client, chave):
    from fastapi.testclient import TestClient

    from app.main import asgi

    completo = TestClient(asgi)
    grande = b'{"text": "' + b"a" * (3 * 1024 * 1024) + b'"}'
    # sem chave (ou com chave inventada) é recusado antes de ler o corpo
    assert completo.post(f"{API}/messages", content=grande, headers={"Content-Type": "application/json"}).status_code == 401
    falsa = {"Content-Type": "application/json", "Authorization": "Bearer isk_" + "y" * 43}
    assert completo.post(f"{API}/messages", content=grande, headers=falsa).status_code == 401
    # com a chave certa o corpo passa do portão (a rota reclama: falta o contato)
    ok = {"Content-Type": "application/json", "Authorization": f"Bearer {chave['key']}"}
    assert completo.post(f"{API}/messages", content=grande, headers=ok).status_code == 404
    # o teto acompanha o arquivo de 80 MB, que em base64 ocupa 1/3 a mais (~107 MB)
    assert 107 * 1024 * 1024 < TETO_MENSAGEM_COM_ARQUIVO <= 112 * 1024 * 1024


def test_chave_revogada_para_na_hora(client, passe, wa):
    nova = client.post(f"{API}/integracao/chaves", json={"name": "Temporária"}, headers=passe).json()
    h = {"Authorization": f"Bearer {nova['key']}"}
    assert client.get(f"{API}/integracao/ping", headers=h).status_code == 200
    assert client.delete(f"{API}/integracao/chaves/{nova['id']}", headers=passe).json()["revokedAt"]
    assert client.get(f"{API}/integracao/ping", headers=h).status_code == 401
    assert client.post(f"{API}/integracao/chaves", json={"name": "  "}, headers=passe).status_code == 422


def test_tela_do_modulo_abre_pelo_endereco(tmp_path, monkeypatch):
    """F5 em /api abre a tela (o React cuida); /api/qualquer-coisa continua 404 da API."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app import tela

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><div id=root></div>", encoding="utf-8")
    monkeypatch.setattr(tela, "DIST", dist.resolve())
    app = FastAPI()
    tela.montar(app)
    site = TestClient(app)
    assert site.get("/api").status_code == 200 and "<div id=root>" in site.get("/api").text
    assert site.get("/api/v1/nao-existe").status_code == 404
    assert site.get("/api/").status_code == 404
