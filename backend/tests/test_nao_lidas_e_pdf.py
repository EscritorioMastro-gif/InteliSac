"""Novidades de 2026-11-17: hora da mensagem não lida mais antiga (a lista pinta o contador de
vermelho depois de 1h30) e a tela poder mostrar PDF num quadro dentro do sistema."""

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from starlette.requests import Request

from app import tela
from app.db import SessionLocal
from app.migrate import alembic_config
from app.models import Contact

API = "/api/v1"


def _sim(client, auth):
    return next(s for s in client.get(f"{API}/services", headers=auth).json()["data"] if s["type"] == "simulador")


def _cliente(client, auth, sim, numero, texto="oi"):
    r = client.post(f"{API}/simulator/inbound", json={"serviceId": sim["id"], "from": numero, "name": "Cliente Espera", "text": texto}, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()["contactId"]


def _contato(client, auth, cid):
    return client.get(f"{API}/contacts/{cid}", headers=auth).json()


def _iso(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def test_nao_lida_guarda_a_hora_da_primeira(client, auth):
    sim = _sim(client, auth)
    cid = _cliente(client, auth, sim, "5511900081001", "primeira")
    c = _contato(client, auth, cid)
    assert c["unread"] == 1 and c["unreadSince"]
    primeira = _iso(c["unreadSince"])

    # a segunda mensagem não muda a hora: conta a partir da mais antiga sem leitura
    _cliente(client, auth, sim, "5511900081001", "segunda")
    c = _contato(client, auth, cid)
    assert c["unread"] == 2 and _iso(c["unreadSince"]) == primeira

    # resposta do atendente não zera (só abrir a conversa zera, como já era)
    r = client.post(f"{API}/messages", json={"contactId": cid, "text": "já vejo"}, headers=auth)
    assert r.status_code in (200, 201), r.text
    assert _iso(_contato(client, auth, cid)["unreadSince"]) == primeira

    # abriu a conversa: zera
    assert client.post(f"{API}/contacts/{cid}/mark-read", headers=auth).status_code == 200
    c = _contato(client, auth, cid)
    assert c["unread"] == 0 and c["unreadSince"] is None

    # nova mensagem depois de lida: começa a contar de novo
    _cliente(client, auth, sim, "5511900081001", "terceira")
    c = _contato(client, auth, cid)
    assert c["unread"] == 1 and _iso(c["unreadSince"]) > primeira


def test_fechar_chamado_zera_a_espera(client, auth):
    sim = _sim(client, auth)
    cid = _cliente(client, auth, sim, "5511900081002")
    assert _contato(client, auth, cid)["unreadSince"]
    r = client.post(f"{API}/contacts/{cid}/ticket/close", json={}, headers=auth)
    assert r.status_code == 200, r.text
    c = _contato(client, auth, cid)
    assert c["unread"] == 0 and c["unreadSince"] is None
    with SessionLocal() as db:
        assert db.get(Contact, cid).unread_since is None


def test_lista_traz_a_hora_da_espera(client, auth):
    sim = _sim(client, auth)
    cid = _cliente(client, auth, sim, "5511900081003")
    lista = client.get(f"{API}/contacts", params={"perPage": 200}, headers=auth).json()["data"]
    item = next(x for x in lista if x["id"] == cid)
    assert item["unreadSince"] and item["unread"] == 1


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


def test_migracao_preenche_as_conversas_que_ja_tinham_nao_lidas():
    banco = Path(tempfile.mkdtemp(prefix="intelisac-mig-")) / "m.db"
    engine = sa.create_engine(f"sqlite:///{banco.as_posix()}")
    cfg = alembic_config()
    base = datetime(2026, 11, 17, 10, 0, tzinfo=timezone.utc)
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "0007")
        meta = sa.MetaData()
        meta.reflect(conn, only=["contacts", "messages"])
        contatos, mensagens = meta.tables["contacts"], meta.tables["messages"]
        conn.execute(contatos.insert(), [
            _linha(contatos, id="c-tres", unread=3, last_message_at=base + timedelta(minutes=50)),
            _linha(contatos, id="c-zero", unread=0, last_message_at=base),
            _linha(contatos, id="c-sem-msg", unread=2, last_message_at=base + timedelta(minutes=7)),
        ])
        # c-tres: cliente mandou 10:00, 10:10 (lidas), atendente 10:20, cliente 10:30, 10:40, 10:50
        horarios = [(0, False), (10, False), (20, True), (30, False), (40, False), (50, False)]
        conn.execute(mensagens.insert(), [
            _linha(mensagens, id=f"m{i}", contact_id="c-tres", is_from_me=eu, created_at=base + timedelta(minutes=m))
            for i, (m, eu) in enumerate(horarios)
        ])
        command.upgrade(cfg, "0008")
        linhas = dict(conn.execute(sa.text("SELECT id, unread_since FROM contacts")).all())
    engine.dispose()
    # 3 não lidas = a 3ª do cliente de trás para frente (10:30)
    assert str(linhas["c-tres"]).startswith("2026-11-17 10:30")
    assert linhas["c-zero"] is None
    # sem mensagens do cliente guardadas: usa a hora da última mensagem
    assert str(linhas["c-sem-msg"]).startswith("2026-11-17 10:07")


def test_tela_deixa_abrir_pdf_do_storage_num_quadro(monkeypatch):
    monkeypatch.setattr(tela.settings, "supabase_url", "https://projeto.supabase.co")
    req = Request({"type": "http", "headers": [(b"host", b"intelisac.onrender.com")]})
    regras = dict(p.split(" ", 1) for p in tela.csp(req).split("; "))
    assert regras["frame-src"] == "https://projeto.supabase.co"
    # o resto continua fechado: nenhum site pode pôr o InteliSac num quadro, nada de plugin
    assert regras["frame-ancestors"] == "'none'"
    assert regras["object-src"] == "'none'"
