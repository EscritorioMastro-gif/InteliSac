# Análise do Digisac (engenharia reversa com REA)

Data: 2026-11-13 · Alvo: `https://mastrocontabil.digisac.biz/login` · Sem login (só a parte pública do app)

## Como foi feito

1. Abri a tela de login num Chrome isolado (perfil temporário, sem sessão) e usei o REA
   (`analyze_web_bundle`) para capturar e analisar o JavaScript que o navegador carrega.
   - Evidência REA: `ev_0b8c3c571696b5e9be03d009d4507ecfce8f8342a3981bef4f49ede9d6bef8e3`
   - Captura de tela do login: `ev_fdfc1eafc447493ad6b79455c8ca867cb3a548e6f23a3d4cb06353603354d7e3`
2. Baixei os mesmos 3 arquivos públicos (`/assets/*.js`) e conferi que o SHA-256 bate com o
   que o REA registrou. Depois li o código minificado para resolver os nomes de endpoints.
3. Cruzei com o que já tinha sido verificado ao vivo na API (rotina de cobrança, set/2026).

Importante: a análise é estática. Nenhuma tela interna foi aberta e nada foi executado com
login. O que está marcado como **observado** está literalmente no código. **Inferido** é
dedução minha. **Desconhecido** precisa de login ou do servidor.

## Arquitetura do Digisac (observado)

| Camada | O que é |
|---|---|
| Frontend | SPA **React** empacotada com **Vite** (3 arquivos: `index` 1,7 MB, `vendor` 170 KB, `app` 14 MB) |
| Estado | Redux + redux-saga (padrão `yield Ri(...)`, `yield un(...)`) |
| HTTP | axios, `baseURL = https://<conta>.digisac.biz/api/v1` (ou `VITE_API_URL`) |
| Login | OAuth2 *password grant*: `POST /oauth/token` (form-urlencoded) com `grant_type=password`, `client_id`, `client_secret`, `username`, `password`, `scope="*"`, `account_alias`. Renovação com `grant_type=refresh_token` |
| Autorização | Header `Authorization: Bearer <token>` + headers `impersonate` e `branch`. 2FA via header `X-Digisac-OTP` |
| Tempo real | **socket.io** (`transports: ["websocket"]`), query `access_token`, `client=web`. Endereço vem do header `x-socket-address` da resposta de `GET /me` |
| Eventos | Nome no formato `<recurso>.<ação>`: `message.created`, `message.updated`, `ticket.created`, `ticket.updated`, `contact.created/updated/destroyed`, `service.*`, `user.*`, `department.*`, `tag.*`, `campaign.*`, `bot.*`, `kanbanCard.*`, `pipeline.*` etc. |
| Monitoramento | Elastic APM (RUM) |
| Idioma | i18n com pt-BR, en-US, es |

### Fábrica genérica de recursos (observado)

Quase toda a API é criada por uma função única (`$1(caminho)`) que gera, para cada recurso:

```
GET    /recurso            (lista, params where/include/perPage/page)
GET    /recurso/count      POST /recurso/count
GET    /recurso/{id}
POST   /recurso            (criar)
PUT    /recurso/{id}       (editar)
DELETE /recurso/{id}
POST   /recurso/many       DELETE /recurso/many
```

Recursos criados assim: `contacts, tickets, messages, users, departments, tags, quick-replies,
ticket-topics, services, roles, permissions, custom-fields, campaigns, bots, bot-versions,
schedule, integrations, interactive-messages, whatsapp-business-templates, knowledge-base,
knowledge-base-item, pipelines, people, organizations, notifications, files, stickers,
dashboard, now, absence, answers, questions, categories, acceptance-terms, terms,
auth-history, credit-movements, contact-block-lists, service-events, admin/accounts, admin/users`.

A lista completa com ~390 chamadas diretas está em [02-endpoints-digisac.txt](02-endpoints-digisac.txt).

### Respostas da API (observado ao vivo em set/2026)

- Listas: `{ data: [...], total, limit, skip, currentPage, lastPage, from, to }`
- Filtros: `where[campo]=valor`, `perPage`, `page`, `include[]`
- Abrir chamado: enviar mensagem (`POST /messages`) abre chamado automático (`origin: "automatic"`);
  mensagem do cliente sem chamado aberto também abre.
- Fechar: `POST /contacts/{id}/ticket/close` (fecha o chamado **atual** do contato).
- Transferir: `POST /contacts/{id}/ticket/transfer` com `{ departmentId, userId, comments, byUserId }`.
- `contact.currentTicketId` preenchido ⇔ contato tem 1 chamado aberto.
- Tipos de mensagem vistos: `chat, document, image, audio, ptt, video, reaction, location, ticket`
  (o tipo `ticket` registra eventos do chamado no histórico: abertura, transferência, fechamento).

## Módulos (menu em pt-BR, observado no dicionário de tradução)

| Módulo | Rota | Para que serve |
|---|---|---|
| Chat / Atendimento | `/` , `/contacts/:id` | Fila de conversas, conversa, envio de mídia, respostas rápidas, transferir, fechar |
| Contatos | `/contacts` | Cadastro, importação CSV, campos personalizados, bloqueio, tags, grupos de WhatsApp |
| Chamados | `/ticket-history`, `/ticket-reports` | Histórico de protocolos, relatórios, exportação |
| Assuntos de chamados | `/ticket-topics` | Motivo do atendimento (escolhido ao fechar) |
| Departamentos | `/departments` | Filas de atendimento |
| Distribuição de chamados | `/distribution` | Regras de distribuição automática entre atendentes |
| Usuários | `/users` | Atendentes, importação em massa, status, horário |
| Cargos | `/roles` | Perfis com permissões granulares (ex.: `tickets.transfer`, `contacts.view.number`) |
| Conexões | `/services` | Canais: WhatsApp (QR code), WhatsApp Business API (WABA), Telegram, Instagram, Messenger, E-mail, SMS, Webchat, Reclame Aqui |
| Respostas rápidas | `/quick-replies` | Textos prontos com atalho |
| Tags | `/tags` | Etiquetas de contato |
| Agendamentos | `/schedules` | Mensagens programadas |
| Campanhas | `/campaigns` | Disparo em massa (com pausa, intervalo, estatísticas) |
| Templates (HSM) | `/whatsapp-business-templates` | Modelos aprovados da Meta |
| Mensagens interativas | `/interactive-messages` | Botões e listas |
| Bots | `/bots` (v1, v2, v3 + simulador) | Fluxos automáticos de atendimento |
| Bases de conhecimento | `/knowledge-base` | Arquivos/URLs/mensagens para IA sugerir respostas |
| Funil de vendas / Kanban | `/pipelines`, `/kanban-boards` | CRM com cartões por contato |
| Pessoas e Organizações | `/people`, `/organizations` | CRM (pessoa física/jurídica ligada a contatos) |
| Estatísticas / Agora | `/now`, `/dashboard` | Dados em tempo real, por departamento/usuário/período |
| Avaliações | `/evaluation` | Pesquisa de satisfação (NPS) ao fechar |
| Feriados e Horários | `/holiday`, `/timetables` | Expediente, mensagem fora de horário |
| Integrações / Webhooks / API | `/integrations`, `/settings/webhooks` | Webhooks com eventos `message.created`, `ticket.updated` etc. e tokens de API pessoais (`/me/tokens`) |
| Empresa / Plano / Créditos | `/company`, `/plan`, `/credits` | Conta, plano, consumo de IA e créditos WABA |
| Ações de segurança | `/auth-history` | Log de login, 2FA |

### Funções de IA (observado — nomes de endpoints)

`/messages/magic-text` (reescrever texto), `/messages/{id}/summarize`, `/contacts/{id}/ticket/summary`,
`/knowledge-base/suggest-by-message`, `/knowledge-base/suggest-by-ticket`, `/bots/suggest-agent-prompt`,
`transcripts/{id}` (transcrição de áudio), `/ai-consumption`.

## Desconhecido (precisa de login ou do servidor)

- Formato exato dos JSONs de cada tela interna (só temos os que testamos em set/2026).
- Como o servidor conecta no WhatsApp (o front só mostra QR code e screenshot do serviço —
  `GET /services/{id}/screenshot` sugere um navegador headless no servidor, **inferido**).
- Regras de distribuição automática e de bots (ficam no servidor).
- Banco de dados e linguagem do backend (nada disso aparece no front).

Se quiser aprofundar, o próximo passo é entrar com usuário e senha e observar as telas internas
(o REA grava os formatos das respostas sem guardar valores sensíveis).
