"""Novidades de 2026-11-16: tags na lista, Fila por ordem de chegada, editar mensagem,
encaminhar, conversar com um contato recebido (vCard) e o botão "Corrigir meu texto"
(LanguageTool simulado: os testes nunca mandam texto para fora)."""

import uuid
from datetime import timedelta

import httpx
import pytest

from app import corretor, storage
from app.channels import whatsapp_qr
from app.db import SessionLocal
from app.models import Message, Ticket, User, now

API = "/api/v1"
GW = {"X-Gateway-Secret": "segredo-do-gateway-de-teste"}


def _sim(client, auth):
    return next(s for s in client.get(f"{API}/services", headers=auth).json()["data"] if s["type"] == "simulador")


def _cliente(client, auth, sim, numero, nome, texto="oi"):
    r = client.post(f"{API}/simulator/inbound", json={"serviceId": sim["id"], "from": numero, "name": nome, "text": texto}, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()["contactId"]


def _ids_na_aba(client, auth, aba, ids):
    lista = client.get(f"{API}/contacts", params={"filter": aba, "perPage": 200}, headers=auth).json()["data"]
    return [x for x in lista if x["id"] in ids]


def _admin_id():
    with SessionLocal() as db:
        return db.query(User).filter(User.email == "admin@teste.local").one().id


def _evento(client, payload):
    r = client.post(f"{API}/gateway/events", json=payload, headers=GW)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def gateway(monkeypatch):
    chamadas = []

    async def fake(method, path, json=None, timeout=30.0):
        chamadas.append((path.rsplit("/", 1)[-1], json))
        return {"id": f"OUT-{uuid.uuid4().hex[:10]}", "jid": json.get("jid")}

    monkeypatch.setattr(whatsapp_qr, "gateway_request", fake)
    return chamadas


@pytest.fixture(scope="module")
def wa(client, auth):
    r = client.post(f"{API}/services", json={"name": "WhatsApp Novidades", "type": "whatsapp"}, headers=auth)
    assert r.status_code == 201, r.text
    return r.json()


def _do_whatsapp(client, auth, wa, numero, nome, texto, ext_id):
    msg = {"id": ext_id, "jid": f"{numero}@s.whatsapp.net", "pnJid": f"{numero}@s.whatsapp.net", "number": numero,
           "pushName": nome, "fromMe": False, "type": "chat", "text": texto}
    _evento(client, {"type": "message", "serviceId": wa["id"], "message": msg})
    return client.get(f"{API}/contacts", params={"serviceId": wa["id"], "number": numero}, headers=auth).json()["data"][0]


def _mensagens(client, auth, contact_id):
    return client.get(f"{API}/messages", params={"contactId": contact_id}, headers=auth).json()["data"]


# ---------- 3. Fila: quem espera há mais tempo primeiro ----------

def test_fila_mostra_primeiro_quem_espera_ha_mais_tempo(client, auth):
    sim = _sim(client, auth)
    a = _cliente(client, auth, sim, "5516900000101", "Ana Antiga")
    b = _cliente(client, auth, sim, "5516900000102", "Beto Médio")
    c = _cliente(client, auth, sim, "5516900000103", "Caio Novo")
    base = now() - timedelta(hours=3)
    with SessionLocal() as db:
        for i, cid in enumerate((a, b, c)):
            t = db.query(Ticket).filter(Ticket.contact_id == cid, Ticket.is_open.is_(True)).one()
            t.queued_at = base + timedelta(minutes=10 * i)
        db.commit()

    # A Ana manda outra mensagem agora: em "Todos" ela sobe; na Fila não perde o lugar
    _cliente(client, auth, sim, "5516900000101", "Ana Antiga", "alguém aí?")
    fila = _ids_na_aba(client, auth, "queue", (a, b, c))
    assert [x["id"] for x in fila] == [a, b, c]
    assert all(x["queuedAt"] for x in fila)
    assert [x["id"] for x in _ids_na_aba(client, auth, "all", (a, b, c))][0] == a

    # A Ana é assumida e depois devolvida para a fila: volta para o fim (a espera conta de novo)
    admin = _admin_id()
    assert client.post(f"{API}/contacts/{a}/ticket/transfer", json={"userId": admin}, headers=auth).status_code == 200
    assert [x["id"] for x in _ids_na_aba(client, auth, "queue", (a, b, c))] == [b, c]
    assert client.post(f"{API}/contacts/{a}/ticket/transfer", json={"userId": None}, headers=auth).status_code == 200
    assert [x["id"] for x in _ids_na_aba(client, auth, "queue", (a, b, c))] == [b, c, a]


# ---------- 1. tags na lista ----------

def test_tags_do_contato_vem_na_lista(client, auth):
    tag = client.post(f"{API}/tags", json={"label": "Cliente VIP", "color": "#b5654a"}, headers=auth).json()
    cid = _cliente(client, auth, _sim(client, auth), "5516900000201", "Tânia Tag")
    assert client.put(f"{API}/contacts/{cid}", json={"tagIds": [tag["id"]]}, headers=auth).status_code == 200
    item = _ids_na_aba(client, auth, "queue", (cid,))[0]
    assert item["tagIds"] == [tag["id"]]


# ---------- 4. editar mensagem ----------

def test_editar_mensagem_enviada(client, auth, wa, gateway):
    c = _do_whatsapp(client, auth, wa, "5511944440001", "Edu Edição", "Qual o valor?", "IN-ED-1")
    enviada = client.post(f"{API}/messages", json={"contactId": c["id"], "text": "O valor é R$ 100"}, headers=auth).json()
    assert enviada["data"]["signed"] is True

    r = client.put(f"{API}/messages/{enviada['id']}", json={"text": "O valor é R$ 150"}, headers=auth)
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["text"] == "O valor é R$ 150" and m["data"]["edited"] is True
    assert m["data"]["editHistory"][0]["text"] == "O valor é R$ 100" and m["data"]["editedBy"] == _admin_id()
    acao, payload = gateway[-1]
    # o cliente recebe a mensagem editada com a assinatura, como a original
    assert acao == "edit" and payload["id"] == _external_id(enviada["id"])
    assert payload["jid"] == "5511944440001@s.whatsapp.net" and payload["text"].startswith("*") and payload["text"].endswith(":*\nO valor é R$ 150")
    contato = client.get(f"{API}/contacts/{c['id']}", headers=auth).json()
    assert contato["lastMessage"] == "O valor é R$ 150"

    # mesmo texto: não chama o WhatsApp de novo
    n = len(gateway)
    assert client.put(f"{API}/messages/{enviada['id']}", json={"text": "O valor é R$ 150"}, headers=auth).status_code == 200
    assert len(gateway) == n


def test_editar_tem_regras(client, auth, wa, gateway):
    c = _do_whatsapp(client, auth, wa, "5511944440002", "Rui Regras", "Bom dia", "IN-ED-2")
    enviada = client.post(f"{API}/messages", json={"contactId": c["id"], "text": "Bom dia, Rui"}, headers=auth).json()

    # outro atendente não edita a mensagem de quem enviou
    client.post(f"{API}/users", json={"name": "Outro Atendente", "email": "outro.ed@teste.local", "password": "senha-do-outro-1"}, headers=auth)
    tk = client.post(f"{API}/oauth/token", data={"grant_type": "password", "username": "outro.ed@teste.local", "password": "senha-do-outro-1"}).json()
    outro = {"Authorization": f"Bearer {tk['access_token']}"}
    assert client.put(f"{API}/messages/{enviada['id']}", json={"text": "x"}, headers=outro).status_code == 403

    # mensagem do cliente não se edita
    do_cliente = next(m for m in _mensagens(client, auth, c["id"]) if not m["isFromMe"])
    assert client.put(f"{API}/messages/{do_cliente['id']}", json={"text": "x"}, headers=auth).status_code == 422
    # vazia
    assert client.put(f"{API}/messages/{enviada['id']}", json={"text": "  "}, headers=auth).status_code == 422
    # depois de 15 minutos o WhatsApp não aceita
    with SessionLocal() as db:
        db.get(Message, enviada["id"]).created_at = now() - timedelta(minutes=16)
        db.commit()
    r = client.put(f"{API}/messages/{enviada['id']}", json={"text": "Bom dia, Rui!"}, headers=auth)
    assert r.status_code == 422 and "15 minutos" in r.json()["detail"]["message"]


def test_cliente_e_celular_editando_atualizam_a_conversa(client, auth, wa, gateway):
    c = _do_whatsapp(client, auth, wa, "5511944440003", "Cida Corrige", "Preciso da guia de 100", "IN-ED-3")
    r = _evento(client, {"type": "edit", "serviceId": wa["id"], "messageId": "IN-ED-3", "text": "Preciso da guia de outubro", "fromMe": False})
    assert r == {"ok": True}
    m = next(x for x in _mensagens(client, auth, c["id"]) if x["data"].get("edited"))
    assert m["text"] == "Preciso da guia de outubro" and m["data"]["editedBy"] == "contact"
    assert m["data"]["editHistory"][0]["text"] == "Preciso da guia de 100"
    # o mesmo aviso de novo não muda nada
    assert _evento(client, {"type": "edit", "serviceId": wa["id"], "messageId": "IN-ED-3", "text": "Preciso da guia de outubro"})["ignored"] == "sem mudança"

    # mensagem nossa (assinada) editada pelo celular: guarda sem a assinatura
    enviada = client.post(f"{API}/messages", json={"contactId": c["id"], "text": "Segue a guia"}, headers=auth).json()
    ext = _external_id(enviada["id"])
    _evento(client, {"type": "edit", "serviceId": wa["id"], "messageId": ext, "text": "*Fulano:*\nSegue a guia de outubro", "fromMe": True})
    m = next(x for x in _mensagens(client, auth, c["id"]) if x["id"] == enviada["id"])
    assert m["text"] == "Segue a guia de outubro" and m["data"]["editedBy"] == "device"


def _external_id(message_id):
    with SessionLocal() as db:
        return db.get(Message, message_id).external_id


# ---------- 6. encaminhar ----------

def test_encaminhar_texto_e_arquivo_para_outra_conversa(client, auth, wa, gateway, monkeypatch):
    guardados = {}

    async def upload(path, data, mimetype):
        guardados[path] = data

    monkeypatch.setattr(storage, "upload", upload)
    monkeypatch.setattr(storage, "sign_many", lambda paths, expires=3600: {p: f"https://storage.test/{p}?t=1" for p in paths})

    a = _do_whatsapp(client, auth, wa, "5511955550001", "Ana Origem", "Segue o comprovante", "IN-FW-1")
    doc = {"id": "IN-FW-2", "jid": "5511955550001@s.whatsapp.net", "number": "5511955550001", "fromMe": False,
           "type": "document", "text": "", "caption": "", "label": "[Documento] guia.pdf",
           "media": {"base64": "JVBERi0xLjQK", "mimetype": "application/pdf", "fileName": "guia.pdf"}}
    _evento(client, {"type": "message", "serviceId": wa["id"], "message": doc})
    b = _do_whatsapp(client, auth, wa, "5511955550002", "Bia Destino", "Oi", "IN-FW-3")

    origem = {m["type"]: m for m in _mensagens(client, auth, a["id"]) if not m["isFromMe"]}
    r = client.post(f"{API}/messages/forward", json={"messageIds": [origem["document"]["id"], origem["chat"]["id"]], "contactIds": [b["id"]]}, headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["sent"] == 2 and r.json()["failed"] == 0

    # na ordem em que foram enviadas, marcadas como encaminhadas e SEM assinatura
    (acao1, p1), (acao2, p2) = gateway[-2:]
    assert acao1 == "send" and p1["text"] == "Segue o comprovante" and p1["forwarded"] is True
    assert acao2 == "send-media" and p2["forwarded"] is True and p2["kind"] == "document" and p2["fileName"] == "guia.pdf"
    assert p1["jid"] == p2["jid"] == "5511955550002@s.whatsapp.net"
    novas = [m for m in _mensagens(client, auth, b["id"]) if m["isFromMe"] and m["type"] != "ticket"]
    assert [m["type"] for m in novas[-2:]] == ["chat", "document"]
    assert all(m["data"]["forwarded"] and not m["data"].get("signed") for m in novas[-2:])
    assert novas[-1]["data"]["file"]["path"] == origem["document"]["data"]["file"]["path"]

    # encaminhada não se edita
    assert client.put(f"{API}/messages/{novas[-2]['id']}", json={"text": "outro"}, headers=auth).status_code == 422


def test_encaminhar_tem_limites(client, auth, wa, gateway):
    a = _do_whatsapp(client, auth, wa, "5511955550011", "Lia Limite", "Oi", "IN-FW-11")
    msgs = _mensagens(client, auth, a["id"])
    evento = next(m for m in msgs if m["type"] == "ticket")
    texto = next(m for m in msgs if m["type"] == "chat")
    assert client.post(f"{API}/messages/forward", json={"messageIds": [evento["id"]], "contactIds": [a["id"]]}, headers=auth).status_code == 422
    assert client.post(f"{API}/messages/forward", json={"messageIds": [], "contactIds": [a["id"]]}, headers=auth).status_code == 422
    muitos = [str(uuid.uuid4()) for _ in range(21)]
    assert client.post(f"{API}/messages/forward", json={"messageIds": muitos, "contactIds": [a["id"]]}, headers=auth).status_code == 422
    assert client.post(f"{API}/messages/forward", json={"messageIds": [texto["id"]], "contactIds": [str(uuid.uuid4())]}, headers=auth).status_code == 404
    assert client.post(f"{API}/messages/forward", json={"messageIds": [texto["id"]], "contactIds": [a["id"]]}).status_code == 401


# ---------- 5. contato recebido (vCard) ----------

def test_contato_recebido_guarda_numeros_e_abre_conversa(client, auth, wa):
    remetente = _do_whatsapp(client, auth, wa, "5511966660001", "Vera Vcard", "Vou te passar o contato", "IN-VC-0")
    vcard = {"id": "IN-VC-1", "jid": "5511966660001@s.whatsapp.net", "number": "5511966660001", "fromMe": False,
             "type": "vcard", "text": "[Contato] Maria Silva",
             "contacts": [{"name": "Maria Silva", "numbers": ["5516991452133", "+55 (16) 3333-4444", "12"]}]}
    _evento(client, {"type": "message", "serviceId": wa["id"], "message": vcard})
    m = next(x for x in _mensagens(client, auth, remetente["id"]) if x["type"] == "vcard")
    assert m["data"]["contacts"] == [{"name": "Maria Silva", "numbers": ["5516991452133", "551633334444"]}]

    r = client.post(f"{API}/contacts/start", json={"serviceId": wa["id"], "number": "5516991452133", "name": "Maria Silva"}, headers=auth)
    assert r.status_code == 200, r.text
    nova = r.json()
    assert nova["created"] is True and nova["name"] == "Maria Silva" and nova["data"]["number"] == "5516991452133"
    # de novo (ou digitado sem o 55): é o mesmo contato
    de_novo = client.post(f"{API}/contacts/start", json={"serviceId": wa["id"], "number": "(16) 99145-2133"}, headers=auth).json()
    assert de_novo["id"] == nova["id"] and de_novo["created"] is False
    # quem já é contato não duplica
    ja = client.post(f"{API}/contacts/start", json={"serviceId": wa["id"], "number": "5511966660001"}, headers=auth).json()
    assert ja["id"] == remetente["id"] and ja["created"] is False

    assert client.post(f"{API}/contacts/start", json={"serviceId": wa["id"], "number": "123"}, headers=auth).status_code == 422
    assert client.post(f"{API}/contacts/start", json={"serviceId": str(uuid.uuid4()), "number": "5516991452133"}, headers=auth).status_code == 422


# ---------- 2. Corrigir meu texto (LanguageTool) ----------

def _pos(texto, trecho):
    """Posição no jeito do LanguageTool (UTF-16: emoji conta 2)."""
    return len(texto[: texto.index(trecho)].encode("utf-16-le")) // 2


def _m(texto, trecho, troca, categoria="TYPOS", regra="REGRA"):
    return {"offset": _pos(texto, trecho), "length": len(trecho.encode("utf-16-le")) // 2, "message": "x",
            "replacements": [{"value": troca}], "rule": {"id": regra, "category": {"id": categoria}}}


def test_corretor_aplica_so_o_que_e_seguro():
    t = "ola 😀 , voce pode mandar o boleto , da Jucesp? obg"
    matches = [
        _m(t, "voce", "você", regra="PT_SIMPLE_REPLACE_ORTHOGRAPHY_VOCE"),
        _m(t, "boleto ,", "boleto,", "TYPOGRAPHY", "SPACE_BEFORE_PUNCTUATION2"),
        _m(t, "😀 ,", "?", "TYPOGRAPHY", "SPACE_BEFORE_PUNCTUATION2"),  # some com o emoji: recusada
        _m(t, "Jucesp", "Juces", regra="MORFOLOGIK_RULE_PT_BR"),  # nome próprio: recusada
        _m(t, "obg", "obrigado", "STYLE"),  # estilo: recusada
        _m(t, "voce pode", "você pode"),  # sobreposta à primeira: ignorada
    ]
    texto, feitas = corretor.aplicar(t, matches)
    assert texto == "ola 😀 , você pode mandar o boleto, da Jucesp? obg"
    assert [f["to"] for f in feitas] == ["você", "boleto,"]
    assert corretor.maiuscula_no_inicio("oi. tudo bem? sim\nok, site.com.br e R$ 10,00")[0] == "Oi. Tudo bem? Sim\nOk, site.com.br e R$ 10,00"


def test_corretor_chama_o_languagetool_em_portugues():
    pedidos = []
    t = "voce pode me mandar o boleto , obrigado 👍"

    def tratar(req: httpx.Request):
        pedidos.append(dict(httpx.QueryParams(req.content.decode())))
        return httpx.Response(200, json={"matches": [
            _m(t, "voce", "você", regra="PT_SIMPLE_REPLACE_ORTHOGRAPHY_VOCE"),
            _m(t, "boleto ,", "boleto,", "TYPOGRAPHY"),
        ]})

    import asyncio

    async def rodar(transporte):
        async with httpx.AsyncClient(transport=httpx.MockTransport(transporte)) as c:
            return await corretor.corrigir(t, client=c)

    r = asyncio.run(rodar(tratar))
    assert r["text"] == "Você pode me mandar o boleto, obrigado 👍" and r["corrections"] == 3
    assert pedidos[0]["language"] == "pt-BR" and pedidos[0]["disabledRules"] == "UPPERCASE_SENTENCE_START"

    with pytest.raises(corretor.CorretorError, match="Muitas correções"):
        asyncio.run(rodar(lambda req: httpx.Response(429)))
    with pytest.raises(corretor.CorretorError, match="grande demais"):
        asyncio.run(corretor.corrigir("a" * 5001))
    assert asyncio.run(corretor.corrigir("   "))["corrections"] == 0


def test_rota_corrigir_texto(client, auth, monkeypatch):
    async def fake(texto, client=None):
        return {"text": texto.upper(), "corrections": 1, "items": []}

    monkeypatch.setattr(corretor, "corrigir", fake)
    r = client.post(f"{API}/text/correct", json={"text": "oi"}, headers=auth)
    assert r.status_code == 200 and r.json()["text"] == "OI"
    assert client.post(f"{API}/text/correct", json={"text": "oi"}).status_code == 401

    async def fora(texto, client=None):
        raise corretor.CorretorError("O corretor (LanguageTool) não respondeu. Tente de novo.")

    monkeypatch.setattr(corretor, "corrigir", fora)
    r = client.post(f"{API}/text/correct", json={"text": "oi"}, headers=auth)
    assert r.status_code == 503 and "não respondeu" in r.json()["detail"]["message"]
