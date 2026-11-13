# InteliSac — arquitetura e roteiro

Objetivo: plataforma de atendimento multicanal própria, com o mesmo modelo do Digisac
(contato → chamado → mensagens, departamentos, conexões, tempo real), começando do zero.

## Decisões (escolhas nossas, não copiadas)

| Item | Escolha | Por quê |
|---|---|---|
| Backend | Python 3.13 + FastAPI + SQLAlchemy | Mesma base do sistema Extrato → Domínio |
| Banco | SQLite em desenvolvimento; PostgreSQL (Supabase) em produção | Troca só a `DATABASE_URL` |
| Tempo real | python-socketio (protocolo socket.io, igual ao Digisac) | Eventos `recurso.ação` |
| Login | `POST /api/v1/oauth/token` (password + refresh_token), JWT | Mesmo contrato do Digisac |
| Frontend | React 18 + Vite | Mesmo stack do Digisac |
| Canais | Adaptadores plugáveis (`backend/app/channels/`) | Começa com o **simulador**; WhatsApp entra depois |

## Modelo de dados (MVP)

```
Account ─┬─ User ──(N:N)── Department
         ├─ Role (lista de permissões, nomes iguais aos do Digisac)
         ├─ Service (conexão/canal: simulador, whatsapp, whatsapp-business, telegram, email, webchat…)
         ├─ Contact ──(N:N)── Tag
         │     └─ currentTicketId
         ├─ Ticket (protocolo, isOpen, departmentId, userId, origin, startedAt, endedAt)
         │     ├─ TicketTransfer (histórico de transferências)
         │     └─ topics (N:N TicketTopic, escolhidos ao fechar)
         ├─ Message (type chat|ticket|image…, text, isFromMe, contactId, ticketId, userId)
         ├─ QuickReply
         └─ TicketTopic
```

## Regras de atendimento implementadas

1. Mensagem do cliente sem chamado aberto → abre chamado (`origin: contact`) no departamento padrão, **na fila** (sem atendente).
2. Atendente envia mensagem para contato sem chamado → abre chamado (`origin: automatic`) já com ele.
3. Atendente que responde um chamado na fila assume o chamado.
4. Transferir: muda departamento e/ou atendente, grava histórico e uma mensagem `type: ticket` no chat.
5. Fechar: grava assuntos e comentário, zera `currentTicketId`, mensagem `type: ticket`.
6. Toda mudança emite evento socket (`message.created`, `ticket.created`, `ticket.updated`, `contact.updated`).
7. Atendente comum só vê chamados dos departamentos dele (ou atribuídos a ele); admin vê tudo.

## Roteiro

| Fase | Entregas |
|---|---|
| **0 — feito** | Login, usuários, departamentos, tags, respostas rápidas, assuntos, conexões, contatos, chamados (abrir/transferir/fechar), mensagens, tempo real, painel "Agora", simulador de cliente |
| **1 — feito (QR code)** | WhatsApp por QR code via `whatsapp-gateway/` (Baileys): QR ao vivo na tela, texto entrando e saindo em tempo real, roda em paralelo com o Digisac. Banco pronto para Supabase (Postgres + migrações Alembic). API oficial da Meta fica para quando houver campanhas |
| 2 — Mídia | Upload/download de arquivos (imagem, áudio, PDF), armazenamento (Supabase Storage) |
| 3 — Produtividade | Atalho `/` para respostas rápidas, agendamentos, horários de expediente, mensagem fora de horário, distribuição automática (rodízio) |
| 4 — Gestão | Relatórios de chamados, exportação CSV, avaliação (NPS) ao fechar, cargos com permissões granulares |
| 5 — Automação | Bot de menu (URA) por departamento, campanhas com templates HSM, webhooks de saída, tokens de API |
| 6 — IA | Resumo do chamado, sugestão de resposta por base de conhecimento, transcrição de áudio (Claude API) |
| 7 — CRM | Funil/Kanban, pessoas e organizações |
