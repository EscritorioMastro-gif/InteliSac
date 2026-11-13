# Banco no Supabase e WhatsApp por QR code

## 1. Supabase (banco de dados)

### O que criar

1. Em supabase.com, **New project**.
2. **Region:** South America (São Paulo), para ficar perto do escritório.
3. **Database password:** crie uma senha forte **só com letras e números**. Símbolos como `@ # / ?`
   quebram a connection string, a menos que sejam codificados. Guarde essa senha.

### Chaves que o InteliSac precisa

| Quando | Chave | Onde achar no Supabase | Onde colocar |
|---|---|---|---|
| **Agora** | `DATABASE_URL` | Botão **Connect** (topo do projeto) → **Connection string** → **Session pooler** → URI. Troque `[YOUR-PASSWORD]` pela senha do banco | `backend/.env` |
| Fase de mídia (fotos, áudios, PDF) | `SUPABASE_URL` | Project Settings → API → Project URL (`https://<ref>.supabase.co`) | `backend/.env` |
| Fase de mídia | `SUPABASE_SERVICE_ROLE_KEY` | Project Settings → API Keys → chave **secret / service_role** | `backend/.env` |

**Não** precisamos da chave `anon`/`publishable`: o site do InteliSac nunca fala direto com o Supabase.
Só o backend acessa.

A `DATABASE_URL` fica neste formato (porta **5432**, Session pooler):

```
postgresql://postgres.<ref-do-projeto>:<SENHA>@aws-0-sa-east-1.pooler.supabase.com:5432/postgres
```

Por que usar o *Session pooler*: a conexão direta do Supabase só funciona por IPv6, e muitas
redes e o Render usam IPv4. O pooler funciona nos dois.

> Não cole chaves no chat. Cole direto no `backend/.env`, que fica só no seu computador e está no
> `.gitignore`. A `SERVICE_ROLE_KEY` dá acesso total ao banco.

### Ligar o InteliSac no Supabase

1. No `backend/.env`, troque a linha `DATABASE_URL=sqlite:///./intelisac.db` pela URI do Supabase.
2. Teste a conexão. O teste mostra o que corrigir e nunca exibe a senha:

```bash
cd C:\Users\gabri\projetos\InteliSac\backend; .\.venv\Scripts\python.exe -m app.check_db
```

3. Crie as tabelas e o administrador:

```bash
cd C:\Users\gabri\projetos\InteliSac\backend; .\.venv\Scripts\python.exe -m app.seed
```

4. Suba o backend normalmente. A cada versão nova, o backend aplica as migrações sozinho ao iniciar
   (`alembic upgrade head`).

Plano grátis do Supabase: o projeto é **pausado após 7 dias sem uso**. Para produção, vale o plano pago.

### Arquivos das conversas (Supabase Storage)

Fotos, áudios, vídeos e documentos ficam no bucket **privado** `intelisac-midia`. O backend cria o
bucket sozinho ao iniciar. Só o backend acessa o bucket, usando a chave secret. A tela recebe links
assinados que valem 1 hora; ao reabrir a conversa, links novos são gerados.

- Limite: **50 MB por arquivo**, que é o padrão do Supabase. No plano Pro dá para subir em
  Storage → Settings → "Upload file size limit". Depois, ajuste `MAX_BYTES` em
  `backend/app/storage.py` e `MAX_ARQUIVO` em `frontend/src/components/Midia.jsx`.
- Plano Pro: 100 GB de arquivos e 250 GB de download por mês incluídos, mais backup diário.
- Arquivos recebidos que não puderem ser baixados ou guardados continuam aparecendo na conversa
  como "[Imagem]", "[Documento] nome.pdf" etc., com o aviso do motivo.

## 2. Login pelo Supabase Auth

Com o Supabase Auth ligado, o e-mail e a senha de cada pessoa ficam no Supabase (Authentication →
Users), e não no banco do InteliSac. Quem entra também precisa estar cadastrado e ativo em
**Usuários** no InteliSac, com o mesmo e-mail. É isso que define se a pessoa é admin ou atendente e
quais departamentos ela vê.

### Chaves (Project Settings → API Keys) no `backend/.env`

| Variável | Qual chave |
|---|---|
| `SUPABASE_URL` | Project URL, `https://<ref>.supabase.co` |
| `SUPABASE_ANON_KEY` | chave **publishable** (ou a antiga **anon**). Usada para conferir login |
| `SUPABASE_SERVICE_ROLE_KEY` | chave **secret** (ou a antiga **service_role**). Usada para criar usuários e trocar senhas. Nunca compartilhe |

### Primeiro acesso (sua conta)

1. Supabase → **Authentication → Sign In / Providers**: desligue **Allow new users to sign up**.
   Assim ninguém cria conta sozinho.
2. Supabase → **Authentication → Users → Add user → Create new user**: seu e-mail e senha, com
   **Auto Confirm User** marcado.
3. Confira as chaves e vincule sua conta como administrador do InteliSac:

```bash
cd C:\Users\gabri\projetos\InteliSac\backend; .\.venv\Scripts\python.exe -m app.users_cli check
```

```bash
cd C:\Users\gabri\projetos\InteliSac\backend; .\.venv\Scripts\python.exe -m app.users_cli link --email SEU_EMAIL --admin --name "Seu Nome"
```

4. Entre no InteliSac com seu e-mail e senha. Depois arquive o admin de teste do seed:

```bash
cd C:\Users\gabri\projetos\InteliSac\backend; .\.venv\Scripts\python.exe -m app.users_cli archive --email admin@intelisac.local
```

### Atendentes

Em **Usuários → Novo** no InteliSac, informe e-mail e senha: o InteliSac cria o usuário no Supabase
sozinho. Se a pessoa já existir no Supabase, deixe a senha vazia e ela é só vinculada. Trocar a senha
em **Usuários → Editar** também troca no Supabase. Para ver quem está em cada lado:
`python -m app.users_cli list`.

Usuários antigos com senha local (como o admin do seed) continuam entrando pela senha local até
receberem uma senha nova pelo InteliSac. A partir daí, passam a usar o Supabase.

## 3. WhatsApp por QR code

### Como funciona

```
Celular do número ── (aparelho conectado) ── whatsapp-gateway (porta 8020, Node/Baileys)
                                                   │  eventos em tempo real
                                                   ▼
Atendentes (site, porta 5180) ◄── socket.io ── backend (porta 8010) ── banco (SQLite/Supabase)
```

- A conexão é **uma só** para a empresa. **Todos os atendentes** conversam por ela: cada um vê os
  chamados dos seus departamentos (e os atribuídos a ele), e o admin vê todos.
- O InteliSac entra no celular como um **aparelho conectado**, igual ao WhatsApp Web. O **Digisac
  continua funcionando** em paralelo.
- Mensagem do cliente chega → abre chamado na **Fila** do departamento padrão. O atendente que
  responder assume o chamado.
- Mensagens enviadas pelo celular ou pelo Digisac também aparecem no InteliSac, marcadas como
  "Enviada pelo celular / outro aparelho". Elas **não abrem chamado** sozinhas. Por exemplo, os
  disparos da rotina de cobrança só entram no histórico, e se o cliente responder, abre chamado.

### Conectar

1. Suba os três serviços (ver README).
2. No InteliSac: **Conexões → Nova conexão → Canal "WhatsApp (QR code)" → Criar e conectar**.
3. No celular do número: WhatsApp → **Configurações → Aparelhos conectados → Conectar um aparelho** →
   leia o QR code da tela.
4. O status muda para **Conectado** e as mensagens passam a chegar no **Atendimento** em tempo real.

A sessão fica salva em `whatsapp-gateway/sessions/`. Se o gateway reiniciar, ele **reconecta sozinho**,
sem pedir QR de novo. Essa pasta equivale a acesso ao número: não copie nem compartilhe.

### Cuidados (leia antes de usar com clientes)

- **Conexão não oficial.** O WhatsApp pode bloquear números que usam clientes não oficiais,
  principalmente com envio em massa. Use para atendimento normal e não para disparos em massa.
  Campanhas devem esperar a API oficial.
- **Computador ligado.** O `whatsapp-gateway` precisa ficar rodando. Se ele cair, o celular continua
  recebendo normalmente. Ao voltar, o WhatsApp entrega ao InteliSac as mensagens que chegaram
  nesse intervalo.
- **Limite de aparelhos.** O WhatsApp aceita poucos aparelhos conectados por número (hoje, 4). Com o
  Digisac e WhatsApp Web em algum PC, pode ser preciso remover um.
- **Dois sistemas no mesmo número.** Enquanto o Digisac estiver ligado, cada mensagem de cliente
  abre chamado nos dois. Combine com a equipe por qual sistema responder, para ninguém responder
  duas vezes.
- **Arquivos:**
  - **Recebidos:** foto, vídeo, áudio, documento e figurinha ficam salvos e aparecem na conversa.
    A foto abre grande ao clicar, e tudo tem o botão Baixar.
  - **Enviados:** pelo clipe, arrastando para a conversa ou colando um print com Ctrl+V. A legenda
    vai assinada com o nome do colaborador.
- **Ainda não suportado:** grupos (ignorados), confirmação de leitura, gravar áudio pelo navegador.
- Se o aparelho for removido pelo celular, o status vira "Desconectado". É só clicar em **Conectar**
  e ler o QR de novo.
