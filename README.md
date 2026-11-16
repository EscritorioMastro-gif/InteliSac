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

No dia a dia:

- **✓ / ✓✓ / ✓✓ azul** em cada mensagem enviada (enviada, entregue, lida ou áudio ouvido), vindos do
  WhatsApp pelo evento `ack` do gateway. Só avançam: um aviso atrasado não volta de "lida" para "entregue".
- **Aviso de mensagem nova**: som e notificação do Windows/navegador (botões *Som* e *Avisos* no rodapé
  do menu; a escolha fica no navegador de cada atendente). Avisa só o chamado do atendente ou a fila dos
  departamentos dele (administrador: toda a fila). Clicar na notificação abre a conversa. Com a aba em
  segundo plano, o título mostra quantas chegaram, ex. `(3) InteliSac`.
- **Grupos**: viram uma conversa com o nome do grupo; cada mensagem mostra quem do grupo escreveu.
- **Foto do contato**: baixada do WhatsApp em segundo plano e guardada no Storage
  (`<conta>/avatars/<contato>.jpg`); atualiza a cada 7 dias.

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
`ticket.updated`, `message.updated` (✓✓, apagada), `contact.created/updated/destroyed`, `service.updated` (status/QR do WhatsApp)…

## Publicar no Render

O `render.yaml` cria **2 serviços** (região Virginia, plano `0.5c-512mb` = 0,5 CPU · 512 MB, US$ 7/mês cada):

| Serviço | O que é | Endereço |
|---|---|---|
| `intelisac` | tela + API + tempo real (o build monta o React em `frontend/dist` e a API entrega) | `https://intelisac.onrender.com` (ou com sufixo, se o nome estiver ocupado) |
| `intelisac-whatsapp` | conexão do WhatsApp, **privado** (sem endereço na internet) + disco de 1 GB com a sessão | só na rede interna do Render |

Banco, arquivos e login continuam no Supabase.

**Primeira vez**

1. Render → **New → Blueprint** → escolha o repositório `InteliSac` (libere o acesso do Render a ele no GitHub, se pedir).
2. O Render pede 4 valores — copie do `backend/.env` do PC (mesmos nomes):
   `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`.
   Os segredos `JWT_SECRET` e `GATEWAY_SECRET` o Render gera sozinho.
   Opcional: `ANTHROPIC_API_KEY` (Environment do serviço `intelisac`) liga o botão **Corrigir** com o
   Claude Sonnet 5.5 (pago por uso; modelo trocável em `CORRETOR_MODELO`). Sem ela o botão usa o LanguageTool grátis.
3. **Apply**. O primeiro build leva alguns minutos. As migrações do banco rodam quando a API liga.
4. Troca do WhatsApp do PC para o Render (o WhatsApp só pode rodar num lugar):
   1. no InteliSac do **PC**: Conexões → **Desconectar** (tira o aparelho do PC do celular);
   2. feche o InteliSac do PC (os 3 servidores);
   3. no InteliSac do **Render**: Conexões → **Conectar** → leia o QR no celular.

**Atualizar depois:** commit + push no GitHub e **Manual Deploy** nos 2 serviços
(`autoDeployTrigger: off`: nada vai para o ar sem você mandar).

**Segurança no ar:** a API não sobe com chave faltando/fraca (`JWT_SECRET`, `GATEWAY_SECRET`,
Supabase, banco Postgres), `/docs` fica fechado, o Simulador fica desligado (`ENABLE_SIMULATOR`)
e a tela sai com CSP (só scripts do próprio site; só conversa com a própria API e o Supabase).
Também: limite de tentativas de login (por e-mail+IP, por IP e por e-mail), **Sair** e troca de senha
encerram os logins no servidor (`users.token_version`), arquivos grandes só são recebidos depois de
conferido o login/segredo, QR code de conexão só para administradores, pedidos com cara de arquivo
(`/.env`, `/x.php`) recebem 404 e o site pede para não ser indexado. Logins (ok, recusado,
bloqueado) e saídas aparecem nos **Logs** do serviço no Render, com o IP.

## Próximos passos

Levar as rotinas fiscais (NF-e, NFS, cobrança) do Digisac para a API do InteliSac.
