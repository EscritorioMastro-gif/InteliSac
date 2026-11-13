"""Fluxo completo: cliente manda mensagem → chamado na fila → atendente responde e assume
→ transfere → fecha com assunto."""

API = "/api/v1"


def test_login_invalido(client):
    r = client.post(f"{API}/oauth/token", data={"grant_type": "password", "username": "admin@teste.local", "password": "x"})
    assert r.status_code == 401


def test_refresh_token(client):
    r = client.post(
        f"{API}/oauth/token",
        data={"grant_type": "password", "username": "admin@teste.local", "password": "senha-de-teste-123"},
    )
    refresh = r.json()["refresh_token"]
    r2 = client.post(f"{API}/oauth/token", data={"grant_type": "refresh_token", "refresh_token": refresh})
    assert r2.status_code == 200 and r2.json()["access_token"]


def test_sem_token_bloqueia(client):
    assert client.get(f"{API}/contacts").status_code == 401


def test_me(client, auth):
    r = client.get(f"{API}/me", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["isAdmin"] is True and body["account"]["name"] == "InteliSac"
    assert len(body["departments"]) == 3


def test_crud_departamento(client, auth):
    r = client.post(f"{API}/departments", json={"name": "Pessoal"}, headers=auth)
    assert r.status_code == 201
    dep_id = r.json()["id"]
    assert client.put(f"{API}/departments/{dep_id}", json={"name": "Depto Pessoal"}, headers=auth).json()["name"] == "Depto Pessoal"
    lista = client.get(f"{API}/departments", params={"q": "Pessoal"}, headers=auth).json()
    assert lista["total"] == 1 and set(lista) >= {"data", "total", "limit", "skip", "currentPage", "lastPage"}
    assert client.post(f"{API}/departments/{dep_id}/archive", json={}, headers=auth).json()["archivedAt"]
    assert client.get(f"{API}/departments", params={"q": "Pessoal"}, headers=auth).json()["total"] == 0


def test_fluxo_completo(client, auth):
    service = client.get(f"{API}/services", headers=auth).json()["data"][0]
    assert service["type"] == "simulador"

    # 1) Cliente manda mensagem → contato criado + chamado aberto na fila
    r = client.post(
        f"{API}/simulator/inbound",
        json={"serviceId": service["id"], "from": "5511999990000", "name": "Maria Teste", "text": "Bom dia, preciso da guia"},
        headers=auth,
    )
    assert r.status_code == 200, r.text
    contact_id = r.json()["contactId"]
    contact = client.get(f"{API}/contacts/{contact_id}", headers=auth).json()
    assert contact["unread"] == 1
    ticket = contact["currentTicket"]
    assert ticket["isOpen"] and ticket["userId"] is None and ticket["origin"] == "contact"

    fila = client.get(f"{API}/contacts", params={"filter": "queue"}, headers=auth).json()
    assert any(c["id"] == contact_id for c in fila["data"])

    # 2) Atendente responde → assume o chamado
    r = client.post(f"{API}/messages", json={"contactId": contact_id, "text": "Bom dia Maria!"}, headers=auth)
    assert r.status_code == 201
    assert r.json()["isFromMe"] is True and r.json()["ticketId"] == ticket["id"]
    me = client.get(f"{API}/me", headers=auth).json()
    t = client.get(f"{API}/tickets/{ticket['id']}", headers=auth).json()
    assert t["userId"] == me["id"]
    mine = client.get(f"{API}/contacts", params={"filter": "mine"}, headers=auth).json()
    assert any(c["id"] == contact_id for c in mine["data"])

    # 3) Transferir para Financeiro (fila)
    fin = next(d for d in me["departments"] if d["name"] == "Financeiro")
    r = client.post(
        f"{API}/contacts/{contact_id}/ticket/transfer",
        json={"departmentId": fin["id"], "userId": None, "comments": "Assunto de boleto"},
        headers=auth,
    )
    assert r.status_code == 200 and r.json()["departmentId"] == fin["id"] and r.json()["userId"] is None
    assert len(client.get(f"{API}/tickets/{ticket['id']}", headers=auth).json()["transfers"]) == 1

    # 4) Fechar com assunto
    topic = client.get(f"{API}/ticket-topics", headers=auth).json()["data"][0]
    r = client.post(
        f"{API}/contacts/{contact_id}/ticket/close",
        json={"ticketTopicIds": [topic["id"]], "comments": "Guia enviada"},
        headers=auth,
    )
    assert r.status_code == 200
    t = client.get(f"{API}/tickets/{ticket['id']}", headers=auth).json()
    assert t["isOpen"] is False and t["endedAt"] and t["ticketTopicIds"] == [topic["id"]]
    assert client.get(f"{API}/contacts/{contact_id}", headers=auth).json()["currentTicketId"] is None

    # Histórico: mensagens + eventos do chamado (type=ticket), em ordem, com quem fez cada ação
    msgs = client.get(f"{API}/messages", params={"where[contactId]": contact_id}, headers=auth).json()["data"]
    tipos = [m["type"] for m in msgs]
    assert tipos[0] == "ticket" and tipos[-1] == "ticket" and tipos.count("chat") == 2
    eventos = [m["text"] for m in msgs if m["type"] == "ticket"]
    assert eventos == [
        f"Chamado {ticket['protocol']} aberto pelo cliente",
        "Chamado transferido por Administrador para Financeiro (fila) · “Assunto de boleto”",
        f"Chamado {ticket['protocol']} fechado por Administrador · Assunto: {topic['name']}",
    ]
    # Simulador não assina: o texto enviado é o original
    assert next(m for m in msgs if m["isFromMe"] and m["type"] == "chat")["data"].get("signed") is None

    # 5) Atendente manda mensagem sem chamado aberto → abre chamado automático com ele
    r = client.post(f"{API}/messages", json={"contactId": contact_id, "text": "Maria, chegou a guia?"}, headers=auth)
    novo = client.get(f"{API}/contacts/{contact_id}", headers=auth).json()["currentTicket"]
    assert novo["origin"] == "automatic" and novo["userId"] == me["id"] and novo["protocol"] != ticket["protocol"]
    msgs = client.get(f"{API}/messages", params={"where[contactId]": contact_id}, headers=auth).json()["data"]
    assert f"Chamado {novo['protocol']} aberto por Administrador" in [m["text"] for m in msgs]

    # 6) Assumir: transferir para si mesmo no mesmo departamento vira "assumido por"
    client.post(f"{API}/contacts/{contact_id}/ticket/transfer", json={"departmentId": novo["departmentId"], "userId": None}, headers=auth)
    client.post(f"{API}/contacts/{contact_id}/ticket/transfer", json={"departmentId": novo["departmentId"], "userId": me["id"]}, headers=auth)
    msgs = client.get(f"{API}/messages", params={"where[contactId]": contact_id}, headers=auth).json()["data"]
    assert msgs[-1]["text"] == "Chamado assumido por Administrador"

    resumo = client.get(f"{API}/now/resume", headers=auth).json()
    assert resumo["openTickets"] >= 1 and resumo["closedToday"] >= 1


def test_webhook_token(client, auth):
    service = client.get(f"{API}/services", headers=auth).json()["data"][0]
    r = client.post(f"{API}/channels/{service['id']}/webhook", json={"from": "1", "text": "oi"}, headers={"X-Channel-Token": "errado"})
    assert r.status_code == 401
