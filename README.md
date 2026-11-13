# InteliSac

Plataforma de atendimento multicanal (estilo Digisac) feita do zero.
Contato → chamado (protocolo) → mensagens, com departamentos, fila, transferência,
fechamento com assunto, respostas rápidas e WhatsApp real, tudo em tempo real.

- `docs/01-analise-digisac.md` — o que a engenharia reversa (REA) mostrou do Digisac
- `docs/02-endpoints-digisac.txt` — ~390 endpoints da API do Digisac extraídos do código
- `docs/03-arquitetura-intelisac.md` — modelo de dados, regras e roteiro das próximas fases
- `docs/04-supabase-e-whatsapp.md` — **chaves do Supabase, login pelo Supabase Auth e como conectar o WhatsApp**

## Estrutura

```
backend/           Python 3.13 + FastAPI + SQLAlchemy + Alembic + socket.io   (porta 8010)
frontend/          React 18 + Vite                                            (porta 5180)
whatsapp-gateway/  Node 24 + Baileys — WhatsApp por QR code                   (porta 8020)
```

Banco: SQLite local (`backend/intelisac.db`) ou PostgreSQL do Supabase. É só trocar a
`DATABASE_URL` no `backend/.env`; as tabelas são criadas pelas migrações (`backend/migrations/`).

## Rodar no Windows (PowerShell)

Primeira vez — backend:

```bash
cd C:\Users\gabri\projetos\InteliSac\backend
```

```bash
python -m venv .venv
```

```bash
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

```bash
copy .env.example .env
```

```bash
.\.venv\Scripts\python.exe -m app.seed
```

Primeira vez — frontend e gateway do WhatsApp:

```bash
cd C:\Users\gabri\projetos\InteliSac\frontend; npm install
```

```bash
cd C:\Users\gabri\projetos\InteliSac\whatsapp-gateway; npm install
```

O `GATEWAY_SECRET` precisa ser igual em `backend/.env` e `whatsapp-gateway/.env`
(nesta máquina isso já está configurado).

Dia a dia (três terminais):

```bash
cd C:\Users\gabri\projetos\InteliSac\backend; .\.venv\Scripts\python.exe -m uvicorn app.main:asgi --port 8010
```

```bash
cd C:\Users\gabri\projetos\InteliSac\whatsapp-gateway; npm start
```

```bash
cd C:\Users\gabri\projetos\InteliSac\frontend; npm run dev
```

Abrir http://localhost:5180 e entrar com o usuário do seed (`SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD` no `backend/.env`).

Testes do backend:

```bash
cd C:\Users\gabri\projetos\InteliSac\backend; .\.venv\Scripts\python.exe -m pytest -q
```

## WhatsApp

**Conexões → Nova conexão → WhatsApp (QR code)**, e no celular: *Aparelhos conectados → Conectar um
aparelho*. Todos os atendentes usam essa mesma conexão. Detalhes e cuidados em
`docs/04-supabase-e-whatsapp.md`.

Para testar sem WhatsApp, use o menu **Simulador**: você digita como se fosse o cliente.

## API (compatível com o formato do Digisac)

Base `http://localhost:8010/api/v1` — documentação interativa em `http://localhost:8010/docs`.

| Método | Caminho | O que faz |
|---|---|---|
| POST | `/oauth/token` | Login (`grant_type=password` ou `refresh_token`) |
| GET/PUT | `/me`, `/me/status` | Usuário logado |
| CRUD | `/departments` `/users` `/tags` `/quick-replies` `/ticket-topics` `/services` `/roles` | Cadastros (lista `{data,total,limit,skip,currentPage,lastPage}`) |
| CRUD | `/contacts` | Contatos (`?filter=mine|queue|open|all`, `?q=`, `?where[serviceId]=`) |
| POST | `/contacts/{id}/ticket/open` · `/transfer` · `/close` | Ações do chamado atual |
| GET/POST | `/messages` | Histórico (`?contactId=`) e envio (abre chamado se precisar) |
| GET | `/tickets`, `/tickets/{id}` | Chamados (`?isOpen=true`, histórico de transferências) |
| GET | `/now/resume` | Painel em tempo real |
| POST | `/services/{id}/start` · `/logout` | Conectar (QR code) / desconectar o WhatsApp |
| POST | `/gateway/events` | Eventos do whatsapp-gateway (header `X-Gateway-Secret`) |
| POST | `/channels/{serviceId}/webhook` | Entrada de mensagens de outros canais (header `X-Channel-Token`) |

Eventos socket.io (`/socket.io`, `?access_token=`): `message.created`, `ticket.created`,
`ticket.updated`, `contact.created/updated/destroyed`, `service.updated` (status/QR do WhatsApp)…

## Próximos passos

Ligar o banco no Supabase (ver `docs/04`), depois mídia (fotos, áudios, PDFs) com Supabase Storage.
