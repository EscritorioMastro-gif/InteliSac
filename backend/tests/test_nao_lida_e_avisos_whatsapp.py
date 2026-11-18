"""Novidades de 2026-11-18: "Marcar como não lida" e os avisos internos do WhatsApp
([secretEncryptedMessage], que chega quando alguém edita ou apaga) não virarem mensagem."""

import pytest

API = "/api/v1"
GW = {"X-Gateway-Secret": "segredo-do-gateway-de-teste"}


def _sim(client, auth):
    return next(s for s in client.get(f"{API}/services", headers=auth).json()["data"] if s["type"] == "simulador")


def _contato(client, auth, cid):
    return client.get(f"{API}/contacts/{cid}", headers=auth).json()


def test_marcar_como_nao_lida(client, auth):
    sim = _sim(client, auth)
    r = client.post(f"{API}/simulator/inbound", json={"serviceId": sim["id"], "from": "5511900091001", "name": "Cliente Não Lida", "text": "oi"}, headers=auth)
    cid = r.json()["contactId"]
    client.post(f"{API}/contacts/{cid}/mark-read", headers=auth)
    assert _contato(client, auth, cid)["unread"] == 0

    assert client.post(f"{API}/contacts/{cid}/mark-unread", headers=auth).status_code == 200
    c = _contato(client, auth, cid)
    assert c["unread"] == 1 and c["unreadSince"]

    # de novo não soma nem muda a hora
    antes = c["unreadSince"]
    client.post(f"{API}/contacts/{cid}/mark-unread", headers=auth)
    c = _contato(client, auth, cid)
    assert c["unread"] == 1 and c["unreadSince"] == antes

    # abrir a conversa volta a zerar
    client.post(f"{API}/contacts/{cid}/mark-read", headers=auth)
    assert _contato(client, auth, cid)["unread"] == 0


def test_marcar_como_nao_lida_contato_inexistente(client, auth):
    assert client.post(f"{API}/contacts/00000000-0000-0000-0000-000000000000/mark-unread", headers=auth).status_code == 404


@pytest.fixture(scope="module")
def service(client, auth):
    r = client.post(f"{API}/services", json={"name": "WhatsApp Avisos", "type": "whatsapp"}, headers=auth)
    assert r.status_code == 201, r.text
    return r.json()


def test_aviso_interno_do_whatsapp_nao_vira_mensagem(client, auth, service):
    base = {"jid": "5511988880000@s.whatsapp.net", "number": "5511988880000", "pushName": "Cliente Edita", "fromMe": False, "type": "chat"}
    r = client.post(f"{API}/gateway/events", json={"type": "message", "serviceId": service["id"], "message": {**base, "id": "WAOK1", "text": "oi"}}, headers=GW)
    assert r.json()["ok"]
    for i, aviso in enumerate(["[secretEncryptedMessage]", "[pinInChatMessage]"]):
        r = client.post(f"{API}/gateway/events", json={"type": "message", "serviceId": service["id"], "message": {**base, "id": f"WAAV{i}", "text": aviso}}, headers=GW)
        assert r.json().get("ignored") == "aviso interno do WhatsApp"

    c = next(x for x in client.get(f"{API}/contacts", params={"serviceId": service["id"]}, headers=auth).json()["data"] if x["data"].get("number") == "5511988880000")
    msgs = [m for m in client.get(f"{API}/messages", params={"contactId": c["id"]}, headers=auth).json()["data"] if m["type"] == "chat"]
    assert [m["text"] for m in msgs] == ["oi"]
    assert c["unread"] == 1 and c["lastMessage"] == "oi"
