"""Integração WhatsApp (QR code) com um gateway falso: status/QR, mensagens recebidas,
mensagens enviadas pelo celular, deduplicação e envio pelo sistema."""

import pytest

from app.channels import whatsapp_qr
from app.channels.gateway_client import GatewayError

API = "/api/v1"
GW = {"X-Gateway-Secret": "segredo-do-gateway-de-teste"}


@pytest.fixture(scope="module")
def service(client, auth):
    r = client.post(f"{API}/services", json={"name": "WhatsApp Atendimento", "type": "whatsapp"}, headers=auth)
    assert r.status_code == 201, r.text
    return r.json()


def _event(client, payload, headers=GW):
    return client.post(f"{API}/gateway/events", json=payload, headers=headers)


def test_evento_sem_segredo_recusado(client, service):
    r = _event(client, {"type": "status", "serviceId": service["id"], "status": "qr"}, headers={"X-Gateway-Secret": "x"})
    assert r.status_code == 401


def test_status_qr_e_conectado(client, auth, service):
    r = _event(client, {"type": "status", "serviceId": service["id"], "status": "qr", "qr": "data:image/png;base64,AAA"})
    assert r.status_code == 200
    s = client.get(f"{API}/services/{service['id']}", headers=auth).json()
    assert s["data"]["status"] == "qr" and s["data"]["qrCode"].startswith("data:image") and s["isConnected"] is False

    me = {"jid": "5511900000000:12@s.whatsapp.net", "number": "5511900000000", "name": "Mastro"}
    _event(client, {"type": "status", "serviceId": service["id"], "status": "connected", "me": me})
    s = client.get(f"{API}/services/{service['id']}", headers=auth).json()
    assert s["isConnected"] is True and s["data"]["qrCode"] is None and s["data"]["me"]["number"] == "5511900000000"


def test_mensagem_recebida_lid_dedupe_e_celular(client, auth, service):
    msg = {
        "id": "WAMSG001",
        "jid": "123456789012345@lid",
        "pnJid": "5511977776666@s.whatsapp.net",
        "number": "5511977776666",
        "pushName": "João Cliente",
        "fromMe": False,
        "type": "chat",
        "text": "Olá, preciso falar com o fiscal",
        "timestamp": 1794571200,
    }
    r = _event(client, {"type": "message", "serviceId": service["id"], "message": msg})
    assert r.status_code == 200 and r.json()["ok"]

    contatos = client.get(f"{API}/contacts", params={"serviceId": service["id"]}, headers=auth).json()["data"]
    assert len(contatos) == 1
    c = contatos[0]
    assert c["name"] == "João Cliente" and c["data"]["number"] == "5511977776666" and c["data"]["jid"] == "123456789012345@lid"
    assert c["unread"] == 1 and c["currentTicketId"]

    # Mesmo evento de novo (gateway reenviou): não duplica
    assert _event(client, {"type": "message", "serviceId": service["id"], "message": msg}).json().get("duplicate") is True

    # Mensagem enviada pelo celular/Digisac (fromMe) no mesmo chamado
    eco = {**msg, "id": "WAMSG002", "fromMe": True, "pushName": None, "text": "Oi João, já te atendo"}
    _event(client, {"type": "message", "serviceId": service["id"], "message": eco})
    msgs = client.get(f"{API}/messages", params={"contactId": c["id"]}, headers=auth).json()["data"]
    chats = [m for m in msgs if m["type"] == "chat"]
    assert [m["isFromMe"] for m in chats] == [False, True]
    assert chats[1]["data"]["origin"] == "device" and chats[1]["userId"] is None
    assert client.get(f"{API}/contacts/{c['id']}", headers=auth).json()["unread"] == 1


def test_envio_pelo_sistema_usa_jid(client, auth, service, monkeypatch):
    chamadas = []

    async def fake_gateway(method, path, json=None, timeout=30.0):
        chamadas.append((method, path, json))
        return {"id": "SENT001", "jid": json.get("jid")}

    monkeypatch.setattr(whatsapp_qr, "gateway_request", fake_gateway)
    c = client.get(f"{API}/contacts", params={"serviceId": service["id"]}, headers=auth).json()["data"][0]
    r = client.post(f"{API}/messages", json={"contactId": c["id"], "text": "Segue a guia"}, headers=auth)
    assert r.status_code == 201
    # O cliente recebe assinado; no InteliSac fica o texto original
    assert chamadas == [("POST", f"/sessions/{service['id']}/send", {"text": "*Administrador:*\nSegue a guia", "jid": "123456789012345@lid"})]
    m = r.json()
    assert m["isFromMe"] and m["userId"] and "error" not in m["data"]
    assert m["text"] == "Segue a guia" and m["data"]["signed"] is True

    # O "eco" dessa mensagem, se chegasse, seria ignorado pelo id
    eco = {"id": "SENT001", "jid": "123456789012345@lid", "fromMe": True, "type": "chat", "text": "Segue a guia"}
    assert _event(client, {"type": "message", "serviceId": service["id"], "message": eco}).json().get("duplicate") is True


def test_contato_manual_resolve_jid_pelo_numero(client, auth, service, monkeypatch):
    async def fake_gateway(method, path, json=None, timeout=30.0):
        assert "jid" not in json and json["number"] == "5511955554444"
        return {"id": "SENT002", "jid": "551155554444@s.whatsapp.net"}  # WhatsApp devolveu sem o 9

    monkeypatch.setattr(whatsapp_qr, "gateway_request", fake_gateway)
    c = client.post(f"{API}/contacts", json={"serviceId": service["id"], "name": "Maria", "number": "5511955554444"}, headers=auth).json()
    client.post(f"{API}/messages", json={"contactId": c["id"], "text": "Bom dia Maria"}, headers=auth)
    assert client.get(f"{API}/contacts/{c['id']}", headers=auth).json()["data"]["jid"] == "551155554444@s.whatsapp.net"


def test_disparo_pelo_digisac_nao_abre_chamado(client, auth, service):
    """Mensagem enviada pelo celular/Digisac (ex.: rotina de cobrança) para quem não tem
    chamado aberto fica só no histórico; se o cliente responder, abre chamado na fila."""
    envio = {"id": "DGS001", "jid": "5511944443333@s.whatsapp.net", "pnJid": "5511944443333@s.whatsapp.net",
             "number": "5511944443333", "fromMe": True, "type": "chat", "text": "Bom dia! Pode enviar o extrato?"}
    _event(client, {"type": "message", "serviceId": service["id"], "message": envio})
    c = client.get(f"{API}/contacts", params={"serviceId": service["id"], "number": "5511944443333"}, headers=auth).json()["data"][0]
    assert c["currentTicketId"] is None and c["unread"] == 0
    msgs = client.get(f"{API}/messages", params={"contactId": c["id"]}, headers=auth).json()["data"]
    assert len(msgs) == 1 and msgs[0]["ticketId"] is None

    resposta = {**envio, "id": "DGS002", "fromMe": False, "pushName": "Padaria Sol", "text": "Segue o extrato"}
    _event(client, {"type": "message", "serviceId": service["id"], "message": resposta})
    c = client.get(f"{API}/contacts/{c['id']}", headers=auth).json()
    assert c["currentTicket"]["origin"] == "contact" and c["currentTicket"]["userId"] is None and c["unread"] == 1


def test_desligar_assinatura_nao_apaga_status(client, auth, service, monkeypatch):
    enviados = []

    async def fake_gateway(method, path, json=None, timeout=30.0):
        enviados.append(json["text"])
        return {"id": f"SENT-NS-{len(enviados)}", "jid": json.get("jid")}

    monkeypatch.setattr(whatsapp_qr, "gateway_request", fake_gateway)
    r = client.put(f"{API}/services/{service['id']}", json={"name": "WhatsApp Atendimento", "signMessages": False}, headers=auth)
    assert r.status_code == 200
    s = r.json()
    # o ajuste não pode apagar o status/número que vieram do gateway
    assert s["data"]["signMessages"] is False and s["data"]["status"] == "connected" and s["data"]["me"]["number"]
    c = client.get(f"{API}/contacts", params={"serviceId": service["id"], "q": "João"}, headers=auth).json()["data"][0]
    m = client.post(f"{API}/messages", json={"contactId": c["id"], "text": "sem assinatura"}, headers=auth).json()
    assert enviados == ["sem assinatura"] and "signed" not in m["data"]
    client.put(f"{API}/services/{service['id']}", json={"signMessages": True}, headers=auth)


def test_gateway_fora_do_ar(client, auth, service, monkeypatch):
    async def fora(method, path, json=None, timeout=30.0):
        raise GatewayError("Serviço do WhatsApp fora do ar.", status=503)

    monkeypatch.setattr(whatsapp_qr, "gateway_request", fora)
    c = client.get(f"{API}/contacts", params={"serviceId": service["id"], "q": "João"}, headers=auth).json()["data"][0]
    m = client.post(f"{API}/messages", json={"contactId": c["id"], "text": "teste"}, headers=auth).json()
    assert "fora do ar" in m["data"]["error"]

    # Botão Conectar com gateway desligado: erro claro (porta 9 fechada no conftest)
    r = client.post(f"{API}/services/{service['id']}/start", headers=auth)
    assert r.status_code == 503 and "whatsapp-gateway" in r.json()["detail"]["message"]
