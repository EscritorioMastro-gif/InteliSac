// Módulo API: chaves para outros sistemas (rotinas de guias, cobrança...) mandarem mensagens e
// documentos pelo WhatsApp do InteliSac. Só administrador + a senha do módulo.
import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import Icon from "../components/Icon";
import Modal from "../components/Modal";
import PageHead from "../components/PageHead";
import { useConfirm } from "../components/Confirm";
import { useToast } from "../components/Toast";

// Passe do módulo (30 min): só na memória desta aba. Atualizar a página pede a senha de novo.
let passe = null; // { token, ate }
const passeValido = () => (passe && passe.ate > Date.now() ? passe.token : null);

const dataHora = (iso) =>
  iso ? new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—";

function useCopiar() {
  const toast = useToast();
  return async (texto, aviso = "Copiado") => {
    try {
      await navigator.clipboard.writeText(texto);
      toast.show(aviso);
    } catch {
      toast.show("Não consegui copiar: selecione e copie com Ctrl+C", "error");
    }
  };
}

export default function ApiModulo() {
  const toast = useToast();
  const copiar = useCopiar();
  const confirmar = useConfirm();
  const [estado, setEstado] = useState("carregando"); // carregando | definir | bloqueado | liberado
  const [chaves, setChaves] = useState([]);
  const [conexoes, setConexoes] = useState([]);
  const [modal, setModal] = useState(null); // "nova" | "senha"
  const [criada, setCriada] = useState(null);
  const [erro, setErro] = useState("");

  const cab = () => ({ "X-Modulo-Token": passeValido() || "" });

  const bloquear = useCallback(() => {
    passe = null;
    setChaves([]);
    setCriada(null);
    setModal(null);
    setEstado("bloqueado");
  }, []);

  const carregar = useCallback(async () => {
    try {
      const r = await api("/integracao/chaves", { headers: { "X-Modulo-Token": passeValido() || "" } });
      setChaves(r.data);
      setEstado("liberado");
      api("/services", { params: { perPage: 100 } }).then((s) => setConexoes(s.data)).catch(() => {});
    } catch (e) {
      bloquear();
      if (!/senha do módulo/i.test(e.message)) setErro(e.message);
    }
  }, [bloquear]);

  useEffect(() => {
    if (passeValido()) {
      carregar();
      return;
    }
    api("/integracao/modulo")
      .then((r) => setEstado(r.configured ? "bloqueado" : "definir"))
      .catch((e) => setErro(e.message));
  }, [carregar]);

  // o passe vence sozinho: volta para a tela da senha
  useEffect(() => {
    if (estado !== "liberado" || !passe) return undefined;
    const t = setTimeout(bloquear, Math.max(0, passe.ate - Date.now()));
    return () => clearTimeout(t);
  }, [estado, bloquear]);

  const liberar = (r) => {
    passe = { token: r.token, ate: Date.now() + r.expiresIn * 1000 - 5000 };
    setErro("");
    carregar();
  };

  const revogar = async (c) => {
    const ok = await confirmar({
      titulo: `Revogar a chave “${c.name}”?`,
      texto: "Os sistemas que usam essa chave param de funcionar na hora. Não dá para desfazer: será preciso criar outra chave.",
      ok: "Revogar",
      perigo: true,
    });
    if (!ok) return;
    try {
      await api(`/integracao/chaves/${c.id}`, { method: "DELETE", headers: cab() });
      toast.show("Chave revogada");
      carregar();
    } catch (e) {
      toast.show(e.message, "error");
    }
  };

  if (estado === "carregando") return <div className="page muted">{erro || "Carregando…"}</div>;
  if (estado !== "liberado") return <Cadeado definir={estado === "definir"} onOk={liberar} erroInicial={erro} />;

  const base = `${window.location.origin}/api/v1`;
  const whatsapp = conexoes.filter((s) => s.type === "whatsapp");
  const idConexao = whatsapp[0]?.id || "<id da conexão>";

  return (
    <div className="page api-page">
      <PageHead
        icone="key"
        secao="Configurações"
        titulo="API"
        contagem={chaves.filter((c) => !c.revokedAt).length || null}
        subtitulo="Chaves para outros sistemas (rotinas de guias, cobrança, avisos…) mandarem mensagens e documentos pelo WhatsApp do InteliSac. Cada sistema com a sua chave: se uma vazar, é só revogar aquela."
      >
        <button onClick={() => setModal("senha")}><Icon name="key" size={16} />Trocar senha</button>
        <button onClick={bloquear} title="Fecha o módulo (pede a senha de novo)"><Icon name="lock" size={16} />Bloquear</button>
        <button className="primary" onClick={() => setModal("nova")}><Icon name="plus" size={16} />Nova chave</button>
      </PageHead>

      <div className="table-wrap">
        <table className="table">
          <thead><tr><th>Nome</th><th>Chave</th><th>Criada</th><th>Último uso</th><th>Situação</th><th /></tr></thead>
          <tbody>
            {chaves.length === 0 && (
              <tr className="empty">
                <td colSpan={6}>
                  <div className="empty-state">
                    <span className="empty-icon"><Icon name="key" size={24} /></span>
                    <strong>Nenhuma chave ainda</strong>
                    <span>Crie uma chave para cada sistema que vai mandar mensagens pelo InteliSac.</span>
                    <button className="primary" onClick={() => setModal("nova")}><Icon name="plus" size={16} />Nova chave</button>
                  </div>
                </td>
              </tr>
            )}
            {chaves.map((c) => (
              <tr key={c.id} className={c.revokedAt ? "revogada" : ""}>
                <td><strong>{c.name}</strong></td>
                <td><code>{c.prefix}…</code></td>
                <td>{dataHora(c.createdAt)}{c.createdByName && <div className="muted small">por {c.createdByName}</div>}</td>
                <td>{c.lastUsedAt ? dataHora(c.lastUsedAt) : <span className="muted">nunca</span>}</td>
                <td>{c.revokedAt ? <span className="status off">Revogada {dataHora(c.revokedAt)}</span> : <span className="status ok">Ativa</span>}</td>
                <td className="right">{!c.revokedAt && <button className="link danger" onClick={() => revogar(c)}><Icon name="ban" size={15} />Revogar</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <section className="panel-box api-docs">
        <div className="panel-box-head"><Icon name="plug" /><h3>Como conectar outro sistema</h3></div>
        <p className="muted small">
          Mesmo formato da API do Digisac: um sistema que já manda pelo Digisac funciona trocando só o <b>endereço</b>, a <b>chave</b> e o <b>ID da conexão</b>.
        </p>
        <div className="api-fields">
          <div>
            <span>Endereço da API</span>
            <div className="copy-line"><code>{base}</code><button className="link" onClick={() => copiar(base)}><Icon name="copy" size={14} />Copiar</button></div>
          </div>
          <div>
            <span>Cabeçalho de cada chamada</span>
            <div className="copy-line"><code>Authorization: Bearer &lt;sua chave&gt;</code></div>
          </div>
          {whatsapp.map((s) => (
            <div key={s.id}>
              <span>ID da conexão “{s.name}” (serviceId)</span>
              <div className="copy-line"><code>{s.id}</code><button className="link" onClick={() => copiar(s.id)}><Icon name="copy" size={14} />Copiar</button></div>
            </div>
          ))}
        </div>

        <table className="table api-rotas">
          <thead><tr><th>O que fazer</th><th>Chamada</th></tr></thead>
          <tbody>
            <tr><td>Testar a chave (mostra as conexões)</td><td><code>GET /integracao/ping</code></td></tr>
            <tr><td>Achar ou criar o contato (devolve o que já existe)</td><td><code>POST /contacts</code> <span className="muted">{"{ name, number, serviceId }"}</span></td></tr>
            <tr><td>Procurar contato pelo número</td><td><code>GET /contacts?where[data.number]=55…&amp;where[serviceId]=…</code></td></tr>
            <tr><td>Mandar texto</td><td><code>POST /messages</code> <span className="muted">{"{ contactId, text }"}</span></td></tr>
            <tr><td>Mandar documento (guia em PDF, até 80 MB)</td><td><code>POST /messages</code> <span className="muted">{"{ contactId, text, file: { base64, mimetype, name } }"}</span></td></tr>
            <tr><td>Ver se tem atendimento aberto</td><td><code>GET /tickets?where[contactId]=…&amp;where[isOpen]=true</code></td></tr>
            <tr><td>Mensagens do atendimento</td><td><code>GET /messages?where[contactId]=…&amp;where[ticketId]=…</code></td></tr>
            <tr><td>Fechar o atendimento</td><td><code>POST /contacts/&#123;id&#125;/ticket/close</code></td></tr>
          </tbody>
        </table>

        <div className="row" style={{ marginTop: 14 }}>
          <strong>Exemplo em Python</strong>
          <button className="link" onClick={() => copiar(exemplo(base, idConexao), "Exemplo copiado")}><Icon name="copy" size={14} />Copiar exemplo</button>
        </div>
        <pre className="code-box">{exemplo(base, idConexao)}</pre>

        <ul className="api-notas">
          <li>O envio pela API <b>não abre atendimento</b> e não aparece como de nenhum atendente (fica “Integração · nome da chave”). Se o cliente responder, o atendimento abre na Fila, como sempre.</li>
          <li>Sem assinatura do colaborador. Para o cliente saber quem mandou, escreva no próprio texto.</li>
          <li>Limite de <b>40 envios por minuto por chave</b>, para proteger o número de WhatsApp. Acima disso a resposta é 429: espere e tente de novo.</li>
          <li>Se o WhatsApp recusar (desconectado, número sem WhatsApp), a resposta é erro 502 com o motivo. A mensagem fica registrada na conversa como “não enviada”.</li>
          <li>Chave errada ou revogada: 401. A chave só alcança contatos, atendimentos e mensagens. Usuários, conexões e configurações ficam fora.</li>
        </ul>
      </section>

      {modal === "nova" && (
        <NovaChave
          onClose={() => { setModal(null); setCriada(null); }}
          criada={criada}
          onCriar={async (nome) => {
            const c = await api("/integracao/chaves", { method: "POST", body: { name: nome }, headers: cab() });
            setCriada(c);
            carregar();
          }}
          copiar={copiar}
        />
      )}
      {modal === "senha" && (
        <TrocarSenha
          onClose={() => setModal(null)}
          onOk={async (body) => {
            await api("/integracao/modulo/senha", { method: "POST", body, headers: cab() });
            setModal(null);
            toast.show("Senha do módulo trocada");
          }}
        />
      )}
    </div>
  );
}

function exemplo(base, idConexao) {
  return `import base64, requests

BASE = "${base}"
H = {"Authorization": "Bearer SUA_CHAVE_AQUI", "Content-Type": "application/json"}
CONEXAO = "${idConexao}"

# 1) acha ou cria o contato (número com 55 + DDD)
contato = requests.post(f"{BASE}/contacts", headers=H, timeout=30, json={
    "name": "Padaria Pão Quente", "number": "5516999999999", "serviceId": CONEXAO}).json()["id"]

# 2) manda o texto
requests.post(f"{BASE}/messages", headers=H, timeout=30, json={
    "contactId": contato, "text": "Olá! Segue a guia do DAS de novembro."}).raise_for_status()

# 3) manda o PDF da guia
pdf = base64.b64encode(open("DAS-11-2026.pdf", "rb").read()).decode()
requests.post(f"{BASE}/messages", headers=H, timeout=90, json={
    "contactId": contato, "text": "",
    "file": {"base64": pdf, "mimetype": "application/pdf", "name": "DAS-11-2026.pdf"}}).raise_for_status()
`;
}

function Cadeado({ definir, onOk, erroInicial }) {
  const [senha, setSenha] = useState("");
  const [confirma, setConfirma] = useState("");
  const [ver, setVer] = useState(false);
  const [erro, setErro] = useState(erroInicial || "");
  const [enviando, setEnviando] = useState(false);

  const enviar = async (e) => {
    e.preventDefault();
    setErro("");
    if (definir && senha !== confirma) return setErro("As duas senhas não são iguais");
    if (definir && senha.length < 8) return setErro("Use pelo menos 8 caracteres");
    setEnviando(true);
    try {
      const r = await api(definir ? "/integracao/modulo/definir" : "/integracao/modulo/entrar", { method: "POST", body: { password: senha } });
      setSenha("");
      setConfirma("");
      onOk(r);
    } catch (err) {
      setErro(err.message);
      setEnviando(false);
    }
  };

  return (
    <div className="page">
      <form className="lock-box" onSubmit={enviar}>
        <div className="lock-icon"><Icon name="lock" size={26} /></div>
        <h2>{definir ? "Crie a senha do módulo API" : "Módulo API protegido"}</h2>
        <p className="muted">
          {definir
            ? "Primeiro acesso: defina a senha que vai proteger as chaves de API. Ela fica guardada só de forma cifrada e é pedida toda vez que alguém abrir este módulo."
            : "Digite a senha do módulo para ver e criar chaves de API."}
        </p>
        <label>
          Senha do módulo
          <div className="pass-field">
            <input type={ver ? "text" : "password"} value={senha} onChange={(e) => setSenha(e.target.value)} autoFocus autoComplete={definir ? "new-password" : "current-password"} />
            <button type="button" className="icon-btn" onClick={() => setVer((v) => !v)} aria-label={ver ? "Esconder senha" : "Mostrar senha"}><Icon name={ver ? "eyeOff" : "eye"} size={17} /></button>
          </div>
        </label>
        {definir && (
          <label>
            Repita a senha
            <input type={ver ? "text" : "password"} value={confirma} onChange={(e) => setConfirma(e.target.value)} autoComplete="new-password" />
          </label>
        )}
        {erro && <div className="error">{erro}</div>}
        <button className="primary" disabled={enviando || !senha}>
          <Icon name={definir ? "check" : "lock"} size={16} />{enviando ? "Conferindo…" : definir ? "Criar senha e entrar" : "Entrar"}
        </button>
      </form>
    </div>
  );
}

function NovaChave({ criada, onCriar, onClose, copiar }) {
  const [nome, setNome] = useState("");
  const [erro, setErro] = useState("");
  const [enviando, setEnviando] = useState(false);
  const criar = async (e) => {
    e.preventDefault();
    setEnviando(true);
    setErro("");
    try {
      await onCriar(nome.trim());
    } catch (err) {
      setErro(err.message);
    } finally {
      setEnviando(false);
    }
  };
  return (
    <Modal titulo={criada ? "Chave criada" : "Nova chave de API"} subtitulo={criada ? undefined : "Dê um nome que diga qual sistema vai usar a chave."} icone={criada ? "check" : "key"} onClose={onClose} largura="560px">
      {criada ? (
        <>
          <div className="key-warning"><Icon name="alert" size={16} />Copie agora e guarde num lugar seguro: a chave inteira não aparece de novo.</div>
          <label>
            Chave “{criada.name}”
            <div className="copy-line key-show">
              <input readOnly value={criada.key} onFocus={(e) => e.target.select()} />
              <button className="primary" type="button" onClick={() => copiar(criada.key, "Chave copiada")}><Icon name="copy" size={15} />Copiar</button>
            </div>
          </label>
          <p className="muted small">Cole no sistema que vai usar (no lugar do token do Digisac). Não mande a chave por WhatsApp ou e-mail.</p>
          <div className="modal-actions"><button className="primary" onClick={onClose}>Pronto, copiei</button></div>
        </>
      ) : (
        <form onSubmit={criar}>
          <label>
            Nome (para saber quem usa)
            <input value={nome} onChange={(e) => setNome(e.target.value)} placeholder="Ex.: Sistema Fiscal · guias do DAS" autoFocus maxLength={120} />
          </label>
          {erro && <div className="error">{erro}</div>}
          <div className="modal-actions">
            <button type="button" onClick={onClose}>Cancelar</button>
            <button className="primary" disabled={enviando || !nome.trim()}><Icon name="key" size={16} />{enviando ? "Criando…" : "Criar chave"}</button>
          </div>
        </form>
      )}
    </Modal>
  );
}

function TrocarSenha({ onClose, onOk }) {
  const [atual, setAtual] = useState("");
  const [nova, setNova] = useState("");
  const [confirma, setConfirma] = useState("");
  const [erro, setErro] = useState("");
  const [enviando, setEnviando] = useState(false);
  const salvar = async (e) => {
    e.preventDefault();
    setErro("");
    if (nova !== confirma) return setErro("As duas senhas novas não são iguais");
    if (nova.length < 8) return setErro("Use pelo menos 8 caracteres");
    setEnviando(true);
    try {
      await onOk({ currentPassword: atual, password: nova });
    } catch (err) {
      setErro(err.message);
      setEnviando(false);
    }
  };
  return (
    <Modal titulo="Trocar a senha do módulo API" icone="lock" onClose={onClose}>
      <form onSubmit={salvar}>
        <label>Senha atual<input type="password" value={atual} onChange={(e) => setAtual(e.target.value)} autoComplete="current-password" autoFocus /></label>
        <label>Senha nova<input type="password" value={nova} onChange={(e) => setNova(e.target.value)} autoComplete="new-password" /></label>
        <label>Repita a senha nova<input type="password" value={confirma} onChange={(e) => setConfirma(e.target.value)} autoComplete="new-password" /></label>
        {erro && <div className="error">{erro}</div>}
        <div className="modal-actions">
          <button type="button" onClick={onClose}>Cancelar</button>
          <button className="primary" disabled={enviando}>{enviando ? "Salvando…" : "Trocar senha"}</button>
        </div>
      </form>
    </Modal>
  );
}
