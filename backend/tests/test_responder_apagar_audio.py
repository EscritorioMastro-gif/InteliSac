"""Responder marcando (citação), apagar para todos e mensagem de voz. Gateway e Storage simulados;
a conversão de áudio usa o ffmpeg de verdade."""

import subprocess
import uuid
from datetime import timedelta

import pytest

from app import storage
from app.channels import whatsapp_qr
from app.db import SessionLocal
from app.models import Message

API = "/api/v1"
GW = {"X-Gateway-Secret": "segredo-do-gateway-de-teste"}
NUM = "5511922221111"


@pytest.fixture
def fake_storage(monkeypatch):
    guardados = {}

    async def upload(path, data, mimetype):
        guardados[path] = (data, mimetype)

    monkeypatch.setattr(storage, "upload", upload)
    monkeypatch.setattr(storage, "sign_many", lambda paths, expires=3600: {p: f"https://storage.test/{p}?t=1" for p in paths if p in guardados})
    return guardados


@pytest.fixture
def gateway(monkeypatch):
    chamadas = []

    async def fake(method, path, json=None, timeout=30.0):
        chamadas.append((path.rsplit("/", 1)[-1], json))
        return {"id": f"OUT-{uuid.uuid4().hex[:10]}", "jid": json.get("jid")}

    monkeypatch.setattr(whatsapp_qr, "gateway_request", fake)
    return chamadas


@pytest.fixture(scope="module")
def conversa(client, auth):
    wa = client.post(f"{API}/services", json={"name": "WhatsApp Respostas", "type": "whatsapp"}, headers=auth).json()
    msg = {"id": "IN1", "jid": f"{NUM}@s.whatsapp.net", "pnJid": f"{NUM}@s.whatsapp.net", "number": NUM,
           "pushName": "Cliente Citação", "fromMe": False, "type": "chat", "text": "Qual o valor do DAS?"}
    client.post(f"{API}/gateway/events", json={"type": "message", "serviceId": wa["id"], "message": msg}, headers=GW)
    c = client.get(f"{API}/contacts", params={"serviceId": wa["id"], "number": NUM}, headers=auth).json()["data"][0]
    return wa, c


def _msgs(client, auth, c):
    return client.get(f"{API}/messages", params={"contactId": c["id"]}, headers=auth).json()["data"]


def _external_id(message_id):
    db = SessionLocal()
    try:
        return db.get(Message, message_id).external_id
    finally:
        db.close()


def test_responder_citando_mensagem_do_cliente(client, auth, conversa, gateway):
    wa, c = conversa
    pergunta = next(m for m in _msgs(client, auth, c) if m["text"] == "Qual o valor do DAS?")
    r = client.post(f"{API}/messages", json={"contactId": c["id"], "text": "R$ 76,60", "replyToId": pergunta["id"]}, headers=auth)
    assert r.status_code == 201
    acao, payload = gateway[-1]
    assert acao == "send" and payload["quoted"] == {"id": "IN1", "fromMe": False, "text": "Qual o valor do DAS?"}
    assert r.json()["data"]["replyTo"]["id"] == pergunta["id"] and r.json()["data"]["replyTo"]["fromMe"] is False


def test_citar_mensagem_de_outra_conversa_e_recusado(client, auth, conversa, gateway):
    _, c = conversa
    sim = next(s for s in client.get(f"{API}/services", headers=auth).json()["data"] if s["type"] == "simulador")
    client.post(f"{API}/simulator/inbound", json={"serviceId": sim["id"], "from": "5511900003333", "name": "Outro", "text": "oi"}, headers=auth)
    outro = client.get(f"{API}/contacts", params={"serviceId": sim["id"], "number": "5511900003333"}, headers=auth).json()["data"][0]
    alheia = _msgs(client, auth, outro)[-1]
    r = client.post(f"{API}/messages", json={"contactId": c["id"], "text": "x", "replyToId": alheia["id"]}, headers=auth)
    assert r.status_code == 422


def test_cliente_responde_citando_e_apaga(client, auth, conversa):
    wa, c = conversa
    base = {"jid": f"{NUM}@s.whatsapp.net", "pnJid": f"{NUM}@s.whatsapp.net", "number": NUM, "fromMe": False, "type": "chat"}
    # citando uma mensagem nossa (OUT… veio do teste anterior) e uma que não está no InteliSac
    nossa = next(m for m in _msgs(client, auth, c) if m["isFromMe"] and m["type"] == "chat")
    client.post(f"{API}/gateway/events", headers=GW, json={"type": "message", "serviceId": wa["id"], "message": {**base, "id": "IN2", "text": "Obrigado!", "quotedId": _external_id(nossa["id"]), "quotedText": "R$ 76,60"}})
    client.post(f"{API}/gateway/events", headers=GW, json={"type": "message", "serviceId": wa["id"], "message": {**base, "id": "IN3", "text": "e essa?", "quotedId": "NAOEXISTE", "quotedText": "mensagem antiga"}})
    msgs = _msgs(client, auth, c)
    obrigado = next(m for m in msgs if m["text"] == "Obrigado!")
    antiga = next(m for m in msgs if m["text"] == "e essa?")
    assert obrigado["data"]["replyTo"]["id"] == nossa["id"] and obrigado["data"]["replyTo"]["fromMe"] is True
    assert antiga["data"]["replyTo"] == {"id": None, "text": "mensagem antiga", "fromMe": None}

    # cliente apaga a mensagem para todos
    r = client.post(f"{API}/gateway/events", headers=GW, json={"type": "revoke", "serviceId": wa["id"], "messageId": "IN3", "fromMe": False})
    assert r.status_code == 200
    antiga = next(m for m in _msgs(client, auth, c) if m["text"] == "e essa?")
    assert antiga["data"]["deleted"] is True and antiga["data"]["deletedBy"] == "contact"


def test_apagar_para_todos(client, auth, conversa, gateway):
    wa, c = conversa
    m = client.post(f"{API}/messages", json={"contactId": c["id"], "text": "mensagem errada"}, headers=auth).json()
    assert client.get(f"{API}/contacts/{c['id']}", headers=auth).json()["lastMessage"] == "mensagem errada"
    r = client.delete(f"{API}/messages/{m['id']}", headers=auth)
    assert r.status_code == 200 and r.json()["data"]["deleted"] is True and r.json()["data"]["deletedBy"]
    # a prévia na lista de conversas não mostra mais o texto apagado
    assert client.get(f"{API}/contacts/{c['id']}", headers=auth).json()["lastMessage"] == "[Mensagem apagada]"
    acao, payload = gateway[-1]
    assert acao == "delete" and payload == {"jid": f"{NUM}@s.whatsapp.net", "id": _external_id(m["id"])}
    assert client.delete(f"{API}/messages/{m['id']}", headers=auth).status_code == 422  # já apagada

    # mensagem do cliente não pode ser apagada para todos
    do_cliente = next(x for x in _msgs(client, auth, c) if not x["isFromMe"] and x["type"] == "chat")
    assert client.delete(f"{API}/messages/{do_cliente['id']}", headers=auth).status_code == 422

    # passou do prazo do WhatsApp (~2,5 dias)
    velha = client.post(f"{API}/messages", json={"contactId": c["id"], "text": "antiga"}, headers=auth).json()
    db = SessionLocal()
    obj = db.get(Message, velha["id"])
    obj.created_at = obj.created_at - timedelta(days=3)
    db.commit()
    db.close()
    r = client.delete(f"{API}/messages/{velha['id']}", headers=auth)
    assert r.status_code == 422 and "2 dias" in r.json()["detail"]["message"]


def test_so_quem_enviou_ou_admin_apaga(client, auth, conversa, gateway):
    _, c = conversa
    client.post(f"{API}/users", json={"name": "Atendente Ana", "email": "ana.apagar@teste.local", "password": "senha-ana-123"}, headers=auth)
    tok = client.post(f"{API}/oauth/token", data={"grant_type": "password", "username": "ana.apagar@teste.local", "password": "senha-ana-123"}).json()["access_token"]
    ana = {"Authorization": f"Bearer {tok}"}
    do_admin = client.post(f"{API}/messages", json={"contactId": c["id"], "text": "do admin"}, headers=auth).json()
    assert client.delete(f"{API}/messages/{do_admin['id']}", headers=ana).status_code == 403
    da_ana = client.post(f"{API}/messages", json={"contactId": c["id"], "text": "da Ana"}, headers=ana).json()
    assert client.delete(f"{API}/messages/{da_ana['id']}", headers=ana).status_code == 200


def test_mensagem_de_voz_convertida_para_ogg_opus(client, auth, conversa, gateway, fake_storage, tmp_path):
    import imageio_ffmpeg

    gravado = tmp_path / "gravacao.webm"
    subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1.5",
         "-c:a", "libopus", str(gravado)],
        check=True,
    )
    _, c = conversa
    r = client.post(
        f"{API}/messages/media",
        data={"contactId": c["id"], "voice": "true"},
        files={"file": ("gravacao.webm", gravado.read_bytes(), "audio/webm;codecs=opus")},
        headers=auth,
    )
    assert r.status_code == 201, r.text
    m = r.json()
    acao, payload = gateway[-1]
    # assinatura do áudio: o gateway manda "*Nome:*" como texto logo antes da mensagem de voz
    assert acao == "send-media" and payload["ptt"] is True and payload["kind"] == "audio" and payload["caption"] == "*Administrador:*"
    assert payload["mimetype"] == "audio/ogg; codecs=opus"
    # duração e forma de onda vão junto (como numa gravação do celular)
    assert payload["seconds"] in (1, 2) and len(payload["waveform"]) == 64 and max(payload["waveform"]) == 100
    dados, mt = fake_storage[m["data"]["file"]["path"]]
    assert dados[:4] == b"OggS" and mt == "audio/ogg; codecs=opus"
    # sem início negativo (senão o WhatsApp diz "há algo errado com o arquivo de áudio")
    saida = tmp_path / "convertido.ogg"
    saida.write_bytes(dados)
    info = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", str(saida)], capture_output=True, text=True).stderr
    inicio = float(info.split("start: ")[1].split(",")[0])
    assert inicio >= 0, info
    assert m["type"] == "ptt" and m["text"] == "" and m["data"]["signed"] is True
    assert 1.3 <= m["data"]["file"]["duration"] <= 1.7
    assert m["fileUrl"]
