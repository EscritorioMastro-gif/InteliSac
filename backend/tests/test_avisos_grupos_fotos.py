"""Atendimento do dia a dia: ✓/✓✓ (confirmação de entrega e leitura), mensagens de grupo,
dados do aviso de mensagem nova e foto do perfil do contato."""

import asyncio
import uuid

import pytest

from app import avatars, storage
from app.channels import whatsapp_qr
from app.db import SessionLocal
from app.models import Contact
from app.routers import gateway as gateway_router

API = "/api/v1"
GW = {"X-Gateway-Secret": "segredo-do-gateway-de-teste"}


def _event(client, payload):
    r = client.post(f"{API}/gateway/events", json=payload, headers=GW)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def service(client, auth):
    s = client.post(f"{API}/services", json={"name": "WhatsApp Avisos", "type": "whatsapp"}, headers=auth).json()
    me = {"jid": "5516900000000:3@s.whatsapp.net", "number": "5516900000000", "name": "Mastro"}
    _event(client, {"type": "status", "serviceId": s["id"], "status": "connected", "me": me})
    return s


@pytest.fixture
def enviados(monkeypatch):
    lista = []

    async def fake(method, path, json=None, timeout=30.0):
        lista.append((path, json))
        return {"id": f"ENV-{uuid.uuid4().hex[:10]}", "jid": json.get("jid")}

    monkeypatch.setattr(whatsapp_qr, "gateway_request", fake)
    return lista


@pytest.fixture
def emitidos(monkeypatch):
    lista = []

    async def fake_emit(account_id, name, payload):
        lista.append((name, payload))

    monkeypatch.setattr(gateway_router, "emit", fake_emit)
    return lista


def _recebe(client, service, **campos):
    msg = {"id": f"IN-{uuid.uuid4().hex[:10]}", "fromMe": False, "type": "chat", "text": "Olá", **campos}
    _event(client, {"type": "message", "serviceId": service["id"], "message": msg})
    return msg


def _mensagem(client, auth, contact_id, msg_id):
    msgs = client.get(f"{API}/messages", params={"contactId": contact_id, "perPage": 100}, headers=auth).json()["data"]
    return next(m for m in msgs if m["id"] == msg_id)


def _contato(client, auth, service, **filtro):
    return client.get(f"{API}/contacts", params={"serviceId": service["id"], **filtro}, headers=auth).json()["data"][0]


# ---------- ✓ enviada / ✓✓ entregue / ✓✓ azul lida ----------

def test_tiques_so_avancam(client, auth, service, enviados, emitidos):
    _recebe(client, service, jid="5516988887777@s.whatsapp.net", number="5516988887777", pushName="Ana Tiques")
    c = _contato(client, auth, service, number="5516988887777")
    m = client.post(f"{API}/messages", json={"contactId": c["id"], "text": "Recebi, obrigado"}, headers=auth).json()
    assert m["data"]["ack"] == "sent"
    ext = enviados[-1]
    with SessionLocal() as db:
        from app.models import Message

        ext_id = db.get(Message, m["id"]).external_id

    def ack(valor):
        return _event(client, {"type": "ack", "serviceId": service["id"], "messageId": ext_id, "ack": valor})

    assert ack("delivered") == {"ok": True}
    assert _mensagem(client, auth, c["id"], m["id"])["data"]["ack"] == "delivered"
    atualizado = [p for n, p in emitidos if n == "message.updated"]
    assert atualizado and atualizado[-1]["id"] == m["id"] and atualizado[-1]["data"]["ack"] == "delivered"

    # chegou atrasado: não volta para ✓
    assert ack("sent").get("ignored")
    assert ack("read") == {"ok": True}
    # erro depois de entregue/lida não faz sentido: ignora
    assert ack("error").get("ignored")
    assert ack("delivered").get("ignored")
    assert ack("played") == {"ok": True}  # áudio ouvido
    assert _mensagem(client, auth, c["id"], m["id"])["data"]["ack"] == "played"
    # mensagem desconhecida ou valor inválido: ignora sem erro
    assert _event(client, {"type": "ack", "serviceId": service["id"], "messageId": "NAO-EXISTE", "ack": "read"}).get("ignored")
    assert ack("qualquer").get("ignored")
    assert ext[1]["text"].endswith("Recebi, obrigado")


# ---------- aviso de mensagem nova ----------

def test_evento_de_mensagem_nova_traz_dados_do_aviso(client, auth, service, emitidos):
    _recebe(client, service, jid="5516977776666@s.whatsapp.net", number="5516977776666", pushName="Bruno Aviso", text="Bom dia")
    criadas = [p for n, p in emitidos if n == "message.created" and p.get("text") == "Bom dia"]
    assert len(criadas) == 1
    ev = criadas[0]
    assert ev["contactName"] == "Bruno Aviso" and ev["isFromMe"] is False
    # chamado novo fica na fila (sem atendente): a tela avisa quem atende o departamento
    assert ev["ticket"]["userId"] is None and ev["ticket"]["departmentId"]

    # depois que alguém assume, o aviso traz o atendente
    c = _contato(client, auth, service, number="5516977776666")
    me = client.get(f"{API}/me", headers=auth).json()
    client.post(f"{API}/contacts/{c['id']}/ticket/transfer", json={"departmentId": ev["ticket"]["departmentId"], "userId": me["id"]}, headers=auth)
    _recebe(client, service, jid="5516977776666@s.whatsapp.net", number="5516977776666", pushName="Bruno Aviso", text="Tudo certo?")
    ev2 = [p for n, p in emitidos if n == "message.created" and p.get("text") == "Tudo certo?"][0]
    assert ev2["ticket"]["userId"] == me["id"]


# ---------- grupos ----------

GRUPO = "120363041234567890@g.us"


def test_mensagem_de_grupo_vira_conversa_do_grupo(client, auth, service, enviados):
    remetente = {"jid": "5516966665555@s.whatsapp.net", "number": "5516966665555", "name": "Carla do Financeiro"}
    recebida = _recebe(
        client, service, jid=GRUPO, isGroup=True, groupName="Mastro x Padaria Sol",
        sender=remetente, pushName="Carla do Financeiro", number="5516966665555", text="Segue o boleto",
    )
    contatos = client.get(f"{API}/contacts", params={"serviceId": service["id"], "q": "Padaria Sol"}, headers=auth).json()["data"]
    assert len(contatos) == 1
    g = contatos[0]
    # o contato é o grupo (nome do grupo, sem número), não a pessoa que escreveu
    assert g["isGroup"] is True and g["name"] == "Mastro x Padaria Sol" and g["data"]["jid"] == GRUPO
    assert not g["data"].get("number") and g["currentTicketId"] and g["unread"] == 1
    msgs = client.get(f"{API}/messages", params={"contactId": g["id"]}, headers=auth).json()["data"]
    chat = [m for m in msgs if m["type"] == "chat"]
    assert chat[-1]["text"] == "Segue o boleto" and chat[-1]["data"]["sender"] == remetente

    # a pessoa não vira contato separado
    assert not client.get(f"{API}/contacts", params={"serviceId": service["id"], "number": "5516966665555"}, headers=auth).json()["data"]

    # grupo renomeado no WhatsApp: o nome acompanha
    _recebe(client, service, jid=GRUPO, isGroup=True, groupName="Padaria Sol - Contábil", sender=remetente, text="Mudei o nome")
    assert client.get(f"{API}/contacts/{g['id']}", headers=auth).json()["name"] == "Padaria Sol - Contábil"

    # responder citando no grupo: o WhatsApp precisa saber quem escreveu a mensagem citada
    r = client.post(f"{API}/messages", json={"contactId": g["id"], "text": "Recebido", "replyToId": chat[-1]["id"]}, headers=auth)
    assert r.status_code == 201, r.text
    caminho, payload = enviados[-1]
    assert caminho.endswith("/send") and payload["jid"] == GRUPO
    assert payload["quoted"] == {"id": recebida["id"], "fromMe": False, "text": "Segue o boleto", "participant": remetente["jid"]}
    assert r.json()["data"]["replyTo"]["senderName"] == "Carla do Financeiro"


# ---------- foto do perfil ----------

class _RespostaFoto:
    status_code = 200
    content = b"\xff\xd8\xff" + b"0" * 500
    headers = {"content-type": "image/jpeg"}


class _ClienteFoto:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url):
        assert url == "https://pps.whatsapp.test/foto.jpg"
        return _RespostaFoto()


@pytest.mark.fotos_de_verdade
def test_foto_do_perfil_guardada_e_na_lista(client, auth, service, monkeypatch):
    _recebe(client, service, jid="5516955554444@s.whatsapp.net", number="5516955554444", pushName="Diego Foto")
    c = _contato(client, auth, service, number="5516955554444")
    pedidos, guardados, eventos = [], {}, []

    async def fake_gateway(method, path, json=None, timeout=30.0):
        pedidos.append(path)
        return {"url": "https://pps.whatsapp.test/foto.jpg"}

    async def fake_upload(path, data, mimetype, upsert=False):
        guardados[path] = (len(data), mimetype, upsert)
        return path

    async def fake_emit(account_id, name, payload):
        eventos.append((name, payload))

    monkeypatch.setattr(avatars, "gateway_request", fake_gateway)
    monkeypatch.setattr(avatars.httpx, "AsyncClient", _ClienteFoto)
    monkeypatch.setattr(avatars, "emit", fake_emit)
    monkeypatch.setattr(storage, "upload", fake_upload)
    monkeypatch.setattr(storage, "sign_many", lambda paths, expires=3600: {p: f"https://storage.test/{p}?t=1" for p in paths})
    avatars._links.clear()

    asyncio.run(avatars.refresh(c["id"]))

    caminho = f"{c['accountId']}/avatars/{c['id']}.jpg"
    assert pedidos == [f"/sessions/{service['id']}/photo?jid=5516955554444%40s.whatsapp.net"]
    assert guardados == {caminho: (503, "image/jpeg", True)}
    assert eventos and eventos[0][0] == "contact.updated" and eventos[0][1]["avatarUrl"].startswith("https://storage.test/")
    with SessionLocal() as db:
        contato = db.get(Contact, c["id"])
        assert contato.avatar_path == caminho and not avatars.needs_refresh(contato)

    lista = client.get(f"{API}/contacts", params={"serviceId": service["id"], "number": "5516955554444"}, headers=auth).json()["data"]
    assert lista[0]["hasAvatar"] is True and lista[0]["avatarUrl"] == f"https://storage.test/{caminho}?t=1"
    # o link é reaproveitado (a lista recarrega a cada mensagem e a foto não precisa baixar de novo)
    monkeypatch.setattr(storage, "sign_many", lambda paths, expires=3600: pytest.fail("deveria reaproveitar o link"))
    assert client.get(f"{API}/contacts/{c['id']}", headers=auth).json()["avatarUrl"] == lista[0]["avatarUrl"]


@pytest.mark.fotos_de_verdade
def test_contato_sem_foto_nao_busca_toda_hora(client, auth, service, monkeypatch):
    _recebe(client, service, jid="5516944443333@s.whatsapp.net", number="5516944443333", pushName="Elisa Sem Foto")
    c = _contato(client, auth, service, number="5516944443333")

    async def fake_gateway(method, path, json=None, timeout=30.0):
        return {"url": None}  # sem foto ou foto só para contatos

    async def fake_emit(*a):
        pass

    monkeypatch.setattr(avatars, "gateway_request", fake_gateway)
    monkeypatch.setattr(avatars, "emit", fake_emit)
    asyncio.run(avatars.refresh(c["id"]))
    with SessionLocal() as db:
        contato = db.get(Contact, c["id"])
        assert contato.avatar_path is None and contato.avatar_checked_at is not None
        assert not avatars.needs_refresh(contato)  # só tenta de novo daqui a 7 dias
    assert "avatarUrl" not in client.get(f"{API}/contacts/{c['id']}", headers=auth).json()
