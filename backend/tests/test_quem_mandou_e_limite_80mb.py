"""Novidades de 2026-11-18: arquivos de até 80 MB (enviar e receber) e quem mandou a última
mensagem de cada conversa (a lista de Atendimento mostra embaixo do nome do contato)."""

import asyncio
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import sqlalchemy as sa
from alembic import command

from app import protecao, storage, ticketing
from app.db import SessionLocal
from app.migrate import alembic_config
from app.models import Contact

API = "/api/v1"
MB = 1024 * 1024


# ---------- limite de 80 MB ----------

def test_limite_de_arquivo_e_80_mb():
    assert storage.MAX_BYTES == 80 * MB
    em_base64 = 80 * MB * 4 / 3  # o arquivo em base64 ocupa 1/3 a mais
    assert protecao.teto_para("/api/v1/messages/media") > 80 * MB  # envio pela tela
    assert protecao.teto_para("/api/v1/gateway/events") > em_base64  # recebido no WhatsApp
    assert protecao.teto_para("/api/v1/messages") > em_base64  # outro sistema (chave de API)
    assert protecao.teto_para("/api/v1/contacts") == 2 * MB  # o resto continua pequeno


def _post_com_tamanho(path: str, tamanho: int, headers: dict) -> tuple[bool, int | None]:
    """Passa uma requisição pelo teto de corpo só com o tamanho declarado: (chegou na rota?, status)."""
    chegou, status = [], []

    async def rota(scope, receive, send):
        chegou.append(True)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        if msg["type"] == "http.response.start":
            status.append(msg["status"])

    cabecalhos = [(k.lower().encode(), v.encode()) for k, v in headers.items()] + [(b"content-length", str(tamanho).encode())]
    scope = {"type": "http", "method": "POST", "path": path, "headers": cabecalhos}
    asyncio.run(protecao.LimiteDeCorpo(rota)(scope, receive, send))
    return bool(chegou), (status[0] if status else None)


def test_teto_do_corpo_deixa_passar_80_mb_e_barra_acima(client, auth):
    # tela mandando um arquivo de 80 MB (mais os campos do formulário): passa
    assert _post_com_tamanho(f"{API}/messages/media", 80 * MB + 4096, auth) == (True, None)
    assert _post_com_tamanho(f"{API}/messages/media", 90 * MB, auth) == (False, 413)
    # sem login nem chega a mandar o arquivo
    assert _post_com_tamanho(f"{API}/messages/media", 80 * MB, {}) == (False, 401)
    # arquivo de 80 MB recebido no WhatsApp chega em base64 (~107 MB)
    gw = {"X-Gateway-Secret": "segredo-do-gateway-de-teste"}
    assert _post_com_tamanho(f"{API}/gateway/events", 108 * MB, gw) == (True, None)
    assert _post_com_tamanho(f"{API}/gateway/events", 130 * MB, gw) == (False, 413)


def test_supabase_recusando_pelo_tamanho_diz_onde_aumentar():
    # arquivo acima do limite configurado no projeto do Supabase (padrão 50 MB)
    recusa = httpx.Response(400, json={"statusCode": "413", "error": "Payload too large", "message": "The object exceeded the maximum allowed size"})
    assert "Upload file size limit" in storage._erro(recusa) and "80 MB" in storage._erro(recusa)
    assert "Upload file size limit" in storage._erro(httpx.Response(413, json={"message": "Payload too large"}))
    # os outros erros continuam com a mensagem do Supabase
    assert storage._erro(httpx.Response(400, json={"message": "Bucket not found"})) == "Bucket not found"


# ---------- quem mandou a última mensagem ----------

def _sim(client, auth):
    return next(s for s in client.get(f"{API}/services", headers=auth).json()["data"] if s["type"] == "simulador")


def _cliente(client, auth, sim, numero, texto="oi"):
    r = client.post(f"{API}/simulator/inbound", json={"serviceId": sim["id"], "from": numero, "name": "Cliente Quem", "text": texto}, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()["contactId"]


def _contato(client, auth, cid):
    return client.get(f"{API}/contacts/{cid}", headers=auth).json()


def test_lista_diz_quem_mandou_a_ultima_mensagem(client, auth):
    eu = client.get(f"{API}/me", headers=auth).json()["id"]
    sim = _sim(client, auth)
    cid = _cliente(client, auth, sim, "5511900082001", "bom dia")
    assert _contato(client, auth, cid)["lastMessageSender"] == {"fromMe": False}

    r = client.post(f"{API}/messages", json={"contactId": cid, "text": "bom dia, em que posso ajudar?"}, headers=auth)
    assert r.status_code in (200, 201), r.text
    assert _contato(client, auth, cid)["lastMessageSender"] == {"fromMe": True, "userId": eu}
    # a lista de conversas traz o mesmo dado
    lista = client.get(f"{API}/contacts", params={"perPage": 200}, headers=auth).json()["data"]
    assert next(x for x in lista if x["id"] == cid)["lastMessageSender"] == {"fromMe": True, "userId": eu}

    # fechar o chamado grava um aviso na conversa, mas a última mensagem continua sendo a do atendente
    assert client.post(f"{API}/contacts/{cid}/ticket/close", json={}, headers=auth).status_code == 200
    c = _contato(client, auth, cid)
    assert c["lastMessage"] == "bom dia, em que posso ajudar?" and c["lastMessageSender"] == {"fromMe": True, "userId": eu}

    _cliente(client, auth, sim, "5511900082001", "obrigado")
    assert _contato(client, auth, cid)["lastMessageSender"] == {"fromMe": False}


def test_quem_mandou_celular_integracao_e_grupo(client, auth):
    sim = _sim(client, auth)
    cid = _cliente(client, auth, sim, "5511900082002")
    with SessionLocal() as db:
        contato = db.get(Contact, cid)
        ticketing.register_message(db, contato, "respondi pelo celular", is_from_me=True, data={"origin": "device"}, open_if_needed=False)
        assert contato.last_message_sender == {"fromMe": True, "via": "device"}
        ticketing.register_message(db, contato, "segue a guia", is_from_me=True, data={"api": {"keyId": "k1", "keyName": "Fiscal"}}, open_if_needed=False)
        assert contato.last_message_sender == {"fromMe": True, "via": "api", "name": "Fiscal"}
        # grupo: quem falou (o nome; sem nome, o número)
        ticketing.register_message(db, contato, "oi pessoal", is_from_me=False, data={"sender": {"jid": "1@lid", "number": "5511977776666", "name": "Maria"}})
        assert contato.last_message_sender == {"fromMe": False, "name": "Maria"}
        ticketing.register_message(db, contato, "oi", is_from_me=False, data={"sender": {"jid": "2@lid", "number": "5511955554444", "name": None}})
        assert contato.last_message_sender == {"fromMe": False, "name": "5511955554444"}
        db.rollback()


def _linha(tabela, **valores):
    """Preenche as colunas obrigatórias com valores quaisquer (o teste só olha as que passou)."""
    linha = {}
    for col in tabela.columns:
        if col.name in valores:
            linha[col.name] = valores[col.name]
        elif not col.nullable and col.server_default is None:
            t = col.type
            if isinstance(t, sa.Boolean):
                linha[col.name] = False
            elif isinstance(t, sa.Integer):
                linha[col.name] = 0
            elif isinstance(t, sa.DateTime):
                linha[col.name] = datetime(2026, 1, 1, tzinfo=timezone.utc)
            elif isinstance(t, sa.JSON):
                linha[col.name] = {}
            else:
                linha[col.name] = f"x-{col.name}"
    return linha


def test_migracao_preenche_quem_mandou_nas_conversas_que_ja_existem():
    banco = Path(tempfile.mkdtemp(prefix="intelisac-mig-")) / "m.db"
    engine = sa.create_engine(f"sqlite:///{banco.as_posix()}")
    cfg = alembic_config()
    base = datetime(2026, 11, 18, 9, 0, tzinfo=timezone.utc)
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "0009")
        meta = sa.MetaData()
        meta.reflect(conn, only=["contacts", "messages"])
        contatos, mensagens = meta.tables["contacts"], meta.tables["messages"]
        conn.execute(contatos.insert(), [
            _linha(contatos, id=cid, last_message_at=base)
            for cid in ("cliente", "atendente", "celular", "api", "grupo")
        ] + [_linha(contatos, id="sem-conversa", last_message_at=None)])
        # (contato, minuto, é nosso, colaborador, tipo, data)
        seq = [
            ("cliente", 0, True, "u1", "chat", {}),
            ("cliente", 5, False, None, "chat", {}),                 # a última é do cliente
            ("atendente", 0, False, None, "chat", {}),
            ("atendente", 5, True, "u1", "chat", {"signed": True}),  # a última é do colaborador u1
            ("atendente", 9, True, "u2", "ticket", {}),              # aviso do chamado não conta
            ("celular", 0, True, None, "chat", {"origin": "device"}),
            ("api", 0, True, None, "document", {"api": {"keyId": "k", "keyName": "Fiscal"}}),
            ("grupo", 0, False, None, "chat", {"sender": {"jid": "1@lid", "number": "5511977776666", "name": "Maria"}}),
        ]
        conn.execute(mensagens.insert(), [
            _linha(mensagens, id=f"q{i}", contact_id=c, created_at=base + timedelta(minutes=m), is_from_me=eu, user_id=u, type=t, data=d)
            for i, (c, m, eu, u, t, d) in enumerate(seq)
        ])
        command.upgrade(cfg, "0010")
        linhas = {cid: (json.loads(v) if v else None) for cid, v in conn.execute(sa.text("SELECT id, last_message_sender FROM contacts")).all()}
    engine.dispose()
    assert linhas["cliente"] == {"fromMe": False}
    assert linhas["atendente"] == {"fromMe": True, "userId": "u1"}
    assert linhas["celular"] == {"fromMe": True, "via": "device"}
    assert linhas["api"] == {"fromMe": True, "via": "api", "name": "Fiscal"}
    assert linhas["grupo"] == {"fromMe": False, "name": "Maria"}
    assert linhas["sem-conversa"] is None
