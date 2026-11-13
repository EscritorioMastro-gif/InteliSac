"""Arquivos nas conversas: receber (gateway → Storage), listar com links e enviar (multipart → gateway).
Supabase Storage e gateway simulados."""

import base64

import pytest

from app import storage
from app.channels import whatsapp_qr

API = "/api/v1"
GW = {"X-Gateway-Secret": "segredo-do-gateway-de-teste"}


@pytest.fixture
def fake_storage(monkeypatch):
    guardados = {}

    async def upload(path, data, mimetype):
        if b"FALHA" in data:
            raise storage.StorageError("Storage fora do ar")
        guardados[path] = (data, mimetype)

    def sign_many(paths, expires=3600):
        return {p: f"https://storage.test/{p}?token=abc" for p in paths if p in guardados}

    monkeypatch.setattr(storage, "upload", upload)
    monkeypatch.setattr(storage, "sign_many", sign_many)
    return guardados


@pytest.fixture(scope="module")
def wa(client, auth):
    r = client.post(f"{API}/services", json={"name": "WhatsApp Mídia", "type": "whatsapp"}, headers=auth)
    assert r.status_code == 201
    return r.json()


def _midia(wa, client, msg_id, tipo, media, caption="", label="[Imagem]", text=None, number="5511933332222"):
    msg = {
        "id": msg_id, "jid": f"{number}@s.whatsapp.net", "pnJid": f"{number}@s.whatsapp.net", "number": number,
        "pushName": "Cliente Mídia", "fromMe": False, "type": tipo, "text": text or caption or label,
        "caption": caption, "label": label, "media": media,
    }
    return client.post(f"{API}/gateway/events", json={"type": "message", "serviceId": wa["id"], "message": msg}, headers=GW)


def _contato(client, auth, wa, number="5511933332222"):
    return client.get(f"{API}/contacts", params={"serviceId": wa["id"], "number": number}, headers=auth).json()["data"][0]


def test_recebe_foto_com_legenda_e_lista_com_link(client, auth, wa, fake_storage):
    foto = b"\xff\xd8\xff fake jpeg"
    r = _midia(wa, client, "MID1", "image", {"base64": base64.b64encode(foto).decode(), "mimetype": "image/jpeg", "fileName": None, "size": len(foto)}, caption="Segue o comprovante")
    assert r.status_code == 200 and r.json()["ok"]
    assert len(fake_storage) == 1
    path, (dados, mt) = next(iter(fake_storage.items()))
    assert dados == foto and mt == "image/jpeg" and path.split("/")[0] == wa["accountId"]

    c = _contato(client, auth, wa)
    assert c["lastMessage"] == "Segue o comprovante"
    m = client.get(f"{API}/messages", params={"contactId": c["id"]}, headers=auth).json()["data"][-1]
    assert m["type"] == "image" and m["text"] == "Segue o comprovante"
    assert m["data"]["file"]["mimetype"] == "image/jpeg" and m["data"]["file"]["size"] == len(foto)
    assert m["fileUrl"].startswith("https://storage.test/") and "download=" in m["downloadUrl"]


def test_recebe_pdf_sem_legenda_mostra_rotulo_na_lista(client, auth, wa, fake_storage):
    pdf = b"%PDF-1.4 fake"
    _midia(wa, client, "MID2", "document", {"base64": base64.b64encode(pdf).decode(), "mimetype": "application/pdf", "fileName": "Extrato Outubro.pdf", "size": len(pdf)},
           label="[Documento] Extrato Outubro.pdf")
    c = _contato(client, auth, wa)
    assert c["lastMessage"] == "[Documento] Extrato Outubro.pdf"
    m = client.get(f"{API}/messages", params={"contactId": c["id"]}, headers=auth).json()["data"][-1]
    assert m["text"] == "" and m["data"]["file"]["name"] == "Extrato Outubro.pdf"
    assert "Extrato_Outubro.pdf" in m["data"]["file"]["path"]


def test_falha_ao_baixar_ou_guardar_nao_perde_a_mensagem(client, auth, wa, fake_storage):
    _midia(wa, client, "MID3", "video", {"error": "arquivo grande demais (80 MB)"}, label="[Vídeo]")
    _midia(wa, client, "MID4", "image", {"base64": base64.b64encode(b"FALHA").decode(), "mimetype": "image/png", "size": 5})
    c = _contato(client, auth, wa)
    msgs = client.get(f"{API}/messages", params={"contactId": c["id"]}, headers=auth).json()["data"]
    video, imagem = msgs[-2], msgs[-1]
    assert video["text"] == "[Vídeo]" and "grande demais" in video["data"]["fileError"] and "file" not in video["data"]
    assert imagem["text"] == "[Imagem]" and "Storage fora do ar" in imagem["data"]["fileError"]


def test_envia_documento_assinado_pelo_whatsapp(client, auth, wa, fake_storage, monkeypatch):
    enviados = []

    async def fake_gateway(method, path, json=None, timeout=30.0):
        enviados.append((path, json))
        return {"id": f"SENTMEDIA{len(enviados)}", "jid": json.get("jid")}

    monkeypatch.setattr(whatsapp_qr, "gateway_request", fake_gateway)
    c = _contato(client, auth, wa)
    r = client.post(
        f"{API}/messages/media",
        data={"contactId": c["id"], "caption": "Segue a guia"},
        files={"file": ("Guia DAS 10-2026.pdf", b"%PDF guia", "application/pdf")},
        headers=auth,
    )
    assert r.status_code == 201, r.text
    m = r.json()
    path, payload = enviados[0]
    assert path == f"/sessions/{wa['id']}/send-media"
    assert payload["kind"] == "document" and payload["fileName"] == "Guia DAS 10-2026.pdf" and payload["mimetype"] == "application/pdf"
    assert payload["caption"] == "*Administrador:*\nSegue a guia" and payload["url"].startswith("https://storage.test/")
    assert m["type"] == "document" and m["text"] == "Segue a guia" and m["data"]["signed"] is True
    assert m["data"]["file"]["name"] == "Guia DAS 10-2026.pdf" and m["fileUrl"] and "error" not in m["data"]

    # Foto sem legenda: vai só a assinatura como legenda
    r = client.post(f"{API}/messages/media", data={"contactId": c["id"]}, files={"file": ("foto.jpg", b"\xff\xd8jpeg", "image/jpeg")}, headers=auth)
    assert r.status_code == 201 and enviados[1][1]["kind"] == "image" and enviados[1][1]["caption"] == "*Administrador*"
    assert _contato(client, auth, wa)["lastMessage"] == "[Imagem]"


def test_limites_e_simulador(client, auth, wa, fake_storage, monkeypatch):
    c = _contato(client, auth, wa)
    monkeypatch.setattr(storage, "MAX_BYTES", 10)
    r = client.post(f"{API}/messages/media", data={"contactId": c["id"]}, files={"file": ("grande.pdf", b"x" * 11, "application/pdf")}, headers=auth)
    assert r.status_code == 413
    r = client.post(f"{API}/messages/media", data={"contactId": c["id"]}, files={"file": ("vazio.pdf", b"", "application/pdf")}, headers=auth)
    assert r.status_code == 422

    # Conexão simulador: registra sem gateway e sem assinatura
    monkeypatch.setattr(storage, "MAX_BYTES", 50 * 1024 * 1024)
    sim = next(s for s in client.get(f"{API}/services", headers=auth).json()["data"] if s["type"] == "simulador")
    client.post(f"{API}/simulator/inbound", json={"serviceId": sim["id"], "from": "5511900007777", "name": "Sim Mídia", "text": "oi"}, headers=auth)
    cs = client.get(f"{API}/contacts", params={"serviceId": sim["id"], "number": "5511900007777"}, headers=auth).json()["data"][0]
    r = client.post(f"{API}/messages/media", data={"contactId": cs["id"]}, files={"file": ("planilha.xlsx", b"PK planilha", "")}, headers=auth)
    assert r.status_code == 201
    m = r.json()
    assert m["type"] == "document" and "signed" not in m["data"] and "error" not in m["data"]
    assert m["data"]["file"]["mimetype"].endswith("spreadsheetml.sheet")  # tipo descoberto pelo nome
