import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api";
import { getSocket } from "../socket";
import { useMe } from "../App";
import Modal from "../components/Modal";
import Icon from "../components/Icon";
import Avatar from "../components/Avatar";
import { useToast } from "../components/Toast";

const ABAS = [
  { id: "mine", label: "Meus", count: "myTickets" },
  { id: "queue", label: "Fila", count: "queueTickets" },
  { id: "open", label: "Abertos", count: "openTickets" },
  { id: "all", label: "Todos" },
];

const VAZIO = {
  mine: "Nenhuma conversa com você agora. Veja a aba Fila para assumir um atendimento.",
  queue: "Fila vazia: nenhum cliente esperando atendimento.",
  open: "Nenhum chamado aberto no momento.",
  all: "Nenhum contato encontrado.",
};

const hora = (iso) => (iso ? new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }) : "");

function diaDe(iso) {
  const d = new Date(iso);
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

function rotuloDia(iso) {
  const hoje = diaDe(new Date().toISOString());
  const dias = Math.round((hoje - diaDe(iso)) / 86400000);
  if (dias === 0) return "Hoje";
  if (dias === 1) return "Ontem";
  return new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "long", year: dias > 300 ? "numeric" : undefined });
}

function quandoCurto(iso) {
  if (!iso) return "";
  const dias = Math.round((diaDe(new Date().toISOString()) - diaDe(iso)) / 86400000);
  if (dias === 0) return hora(iso);
  if (dias === 1) return "Ontem";
  return new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
}

export default function Atendimento() {
  const me = useMe();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const [aba, setAba] = useState("mine");
  const [busca, setBusca] = useState("");
  const [contatos, setContatos] = useState([]);
  const [contagens, setContagens] = useState({});
  const [carregandoLista, setCarregandoLista] = useState(true);
  const [selId, setSelId] = useState(params.get("contact"));
  const [contato, setContato] = useState(null);
  const [mensagens, setMensagens] = useState([]);
  const [texto, setTexto] = useState("");
  const [sugIdx, setSugIdx] = useState(0);
  const [enviando, setEnviando] = useState(false);
  const [deps, setDeps] = useState([]);
  const [usuarios, setUsuarios] = useState([]);
  const [assuntos, setAssuntos] = useState([]);
  const [respostas, setRespostas] = useState([]);
  const [modal, setModal] = useState(null);
  const fimRef = useRef(null);
  const textoRef = useRef(null);
  const selRef = useRef(selId);
  selRef.current = selId;

  const carregarLista = useCallback(() => {
    api("/contacts", { params: { filter: aba, q: busca || undefined, perPage: 100 } })
      .then((r) => setContatos(r.data))
      .catch((e) => toast.show(e.message, "error"))
      .finally(() => setCarregandoLista(false));
    api("/now/resume").then(setContagens).catch(() => {});
  }, [aba, busca, toast]);

  const carregarConversa = useCallback((id) => {
    if (!id) return;
    api(`/contacts/${id}`).then(setContato).catch((e) => toast.show(e.message, "error"));
    api("/messages", { params: { contactId: id, perPage: 100 } }).then((r) => setMensagens(r.data));
  }, [toast]);

  useEffect(() => {
    const t = setTimeout(carregarLista, 200);
    return () => clearTimeout(t);
  }, [carregarLista]);

  useEffect(() => {
    Promise.all([
      api("/departments", { params: { perPage: 200 } }),
      api("/users", { params: { perPage: 200 } }),
      api("/ticket-topics", { params: { perPage: 200 } }),
      api("/quick-replies", { params: { perPage: 200 } }),
    ]).then(([d, u, t, q]) => {
      setDeps(d.data);
      setUsuarios(u.data);
      setAssuntos(t.data);
      setRespostas(q.data);
    });
  }, []);

  useEffect(() => {
    if (!selId) {
      setContato(null);
      setMensagens([]);
      return;
    }
    carregarConversa(selId);
    api(`/contacts/${selId}/mark-read`, { method: "POST" }).catch(() => {});
  }, [selId, carregarConversa]);

  // Tempo real
  useEffect(() => {
    const s = getSocket();
    let t = null;
    const recarregar = () => {
      clearTimeout(t);
      t = setTimeout(carregarLista, 300);
    };
    const onMsg = (m) => {
      if (m.contactId === selRef.current) {
        setMensagens((prev) => (prev.some((x) => x.id === m.id) ? prev : [...prev, m]));
        if (!m.isFromMe) api(`/contacts/${m.contactId}/mark-read`, { method: "POST" }).catch(() => {});
      }
      recarregar();
    };
    const onTicket = (tk) => {
      if (tk.contactId === selRef.current) api(`/contacts/${tk.contactId}`).then(setContato);
      recarregar();
    };
    s.on("message.created", onMsg);
    s.on("ticket.created", onTicket);
    s.on("ticket.updated", onTicket);
    s.on("contact.updated", recarregar);
    s.on("contact.created", recarregar);
    return () => {
      s.off("message.created", onMsg);
      s.off("ticket.created", onTicket);
      s.off("ticket.updated", onTicket);
      s.off("contact.updated", recarregar);
      s.off("contact.created", recarregar);
      clearTimeout(t);
    };
  }, [carregarLista]);

  useEffect(() => {
    fimRef.current?.scrollIntoView({ block: "end" });
  }, [mensagens]);

  // Campo de texto cresce conforme o conteúdo
  useEffect(() => {
    const el = textoRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [texto]);

  const selecionar = (id) => {
    setSelId(id);
    setParams(id ? { contact: id } : {});
  };

  const enviar = async (e) => {
    e?.preventDefault();
    const t = texto.trim();
    if (!t || !selId || enviando) return;
    setTexto("");
    setEnviando(true);
    try {
      const m = await api("/messages", { method: "POST", body: { contactId: selId, text: t } });
      setMensagens((prev) => (prev.some((x) => x.id === m.id) ? prev : [...prev, m]));
      if (m.data?.error) toast.show(`Mensagem não enviada: ${m.data.error}`, "error");
    } catch (err) {
      toast.show(err.message, "error");
      setTexto(t);
    } finally {
      setEnviando(false);
      textoRef.current?.focus();
    }
  };

  const sugestoes = useMemo(() => {
    if (!texto.startsWith("/")) return [];
    const termo = texto.slice(1).toLowerCase();
    return respostas.filter((r) => r.title.toLowerCase().includes(termo) || r.text.toLowerCase().includes(termo)).slice(0, 6);
  }, [texto, respostas]);

  useEffect(() => setSugIdx(0), [sugestoes.length]);

  const usarSugestao = (r) => {
    setTexto(r.text);
    textoRef.current?.focus();
  };

  const onKeyDown = (e) => {
    if (sugestoes.length) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        return setSugIdx((i) => (i + 1) % sugestoes.length);
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        return setSugIdx((i) => (i - 1 + sugestoes.length) % sugestoes.length);
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        return usarSugestao(sugestoes[sugIdx]);
      }
      if (e.key === "Escape") return setTexto("");
    }
    if (e.key === "Enter" && !e.shiftKey) enviar(e);
  };

  const acao = async (fn, ok) => {
    try {
      await fn();
      toast.show(ok);
      carregarConversa(selId);
      carregarLista();
    } catch (err) {
      toast.show(err.message, "error");
    }
  };

  const ticket = contato?.currentTicket;
  const nomeDep = (id) => deps.find((d) => d.id === id)?.name || "Sem departamento";
  const nomeUser = (id) => usuarios.find((u) => u.id === id)?.name || "Atendente";

  // Mensagens agrupadas por dia
  const itens = [];
  let ultimoDia = null;
  for (const m of mensagens) {
    const dia = rotuloDia(m.createdAt);
    if (dia !== ultimoDia) {
      itens.push({ sep: dia, id: `sep-${m.id}` });
      ultimoDia = dia;
    }
    itens.push(m);
  }

  return (
    <div className={`chat ${selId ? "has-selection" : ""}`}>
      <section className="chat-list">
        <div className="chat-list-head">
          <h2>Atendimento</h2>
          <div className="search-box">
            <Icon name="search" size={16} />
            <input placeholder="Buscar nome ou número" value={busca} onChange={(e) => setBusca(e.target.value)} aria-label="Buscar conversa" />
          </div>
          <div className="tabs" role="tablist">
            {ABAS.map((a) => (
              <button key={a.id} role="tab" aria-selected={aba === a.id} className={aba === a.id ? "active" : ""} onClick={() => setAba(a.id)}>
                {a.label}
                {a.count && contagens[a.count] > 0 && <span className="count">{contagens[a.count]}</span>}
              </button>
            ))}
          </div>
        </div>
        <ul>
          {!carregandoLista && contatos.length === 0 && (
            <li className="chat-empty" style={{ cursor: "default" }}>
              <Icon name="inbox" size={28} />
              <span>{busca ? "Nenhuma conversa encontrada para essa busca." : VAZIO[aba]}</span>
            </li>
          )}
          {contatos.map((c) => (
            <li key={c.id} className={`${c.id === selId ? "sel" : ""} ${c.unread > 0 ? "unread" : ""}`} onClick={() => selecionar(c.id)}>
              <Avatar nome={c.internalName || c.name} />
              <div className="grow">
                <div className="row">
                  <strong className="ellipsis">{c.internalName || c.name}</strong>
                  <span className="time-small">{quandoCurto(c.lastMessageAt)}</span>
                </div>
                <div className="row" style={{ marginTop: 2 }}>
                  <span className="muted ellipsis preview">{c.lastMessage || c.data?.number}</span>
                  {c.unread > 0 && <span className="badge">{c.unread}</span>}
                </div>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section className="chat-main">
        {!contato ? (
          <div className="chat-placeholder">
            <div className="big-icon"><Icon name="chat" size={30} /></div>
            <strong>Selecione uma conversa</strong>
            <span>As mensagens novas aparecem aqui em tempo real.</span>
          </div>
        ) : (
          <>
            <header className="chat-head">
              <div className="who">
                <button className="icon-btn back-btn" onClick={() => selecionar(null)} aria-label="Voltar para a lista"><Icon name="arrowLeft" /></button>
                <Avatar nome={contato.internalName || contato.name} size={40} />
                <div style={{ minWidth: 0 }}>
                  <strong className="ellipsis">{contato.internalName || contato.name}</strong>{" "}
                  <span className="muted small">{contato.data?.number}</span>
                  <div className="meta">
                    {ticket ? (
                      <>
                        <span className="chip" title="Protocolo do chamado">#{ticket.protocol}</span>
                        <span className="chip">{nomeDep(ticket.departmentId)}</span>
                        {ticket.userId ? <span className="chip"><Icon name="user" size={12} />{nomeUser(ticket.userId)}</span> : <span className="chip warn"><Icon name="clock" size={12} />Na fila</span>}
                      </>
                    ) : (
                      <span className="muted small">Sem chamado aberto</span>
                    )}
                  </div>
                </div>
              </div>
              <div className="actions">
                {ticket ? (
                  <>
                    {ticket.userId !== me.id && (
                      <button className="primary" onClick={() => acao(() => api(`/contacts/${selId}/ticket/transfer`, { method: "POST", body: { departmentId: ticket.departmentId, userId: me.id } }), "Chamado assumido por você")}>
                        <Icon name="check" size={16} /><span>Assumir</span>
                      </button>
                    )}
                    <button onClick={() => setModal("transferir")}><Icon name="transfer" size={16} /><span>Transferir</span></button>
                    <button className="ghost-danger" onClick={() => setModal("fechar")}><Icon name="x" size={16} /><span>Fechar</span></button>
                  </>
                ) : (
                  <button className="primary" onClick={() => acao(() => api(`/contacts/${selId}/ticket/open`, { method: "POST", body: {} }), "Chamado aberto")}>
                    <Icon name="plus" size={16} /><span>Abrir chamado</span>
                  </button>
                )}
              </div>
            </header>

            <div className="messages">
              {itens.map((m) => {
                if (m.sep) return <div key={m.id} className="day-sep">{m.sep}</div>;
                if (m.type === "ticket") {
                  // Eventos antigos não tinham o nome no texto: completa com quem fez a ação
                  const texto = m.userId && !/ por |pelo cliente/.test(m.text || "") ? `${m.text} por ${nomeUser(m.userId)}` : m.text;
                  return <div key={m.id} className="event"><Icon name="clock" size={13} />{texto} · {hora(m.createdAt)}</div>;
                }
                return (
                  <div key={m.id} className={`bubble ${m.isFromMe ? "me" : "them"} ${m.data?.error ? "failed" : ""}`}>
                    {m.isFromMe && m.userId && (
                      <div className="author" title={m.data?.signed ? "O cliente recebeu a mensagem assinada com este nome" : undefined}>
                        {nomeUser(m.userId)}{m.data?.signed && <span className="signed"> · assinada</span>}
                      </div>
                    )}
                    {m.isFromMe && !m.userId && m.data?.origin === "device" && <div className="author device">Pelo celular / outro aparelho</div>}
                    <div className="text">{m.text}</div>
                    <div className="time">
                      {hora(m.createdAt)}
                      {m.data?.error && <span className="fail"> · não enviada</span>}
                    </div>
                  </div>
                );
              })}
              <div ref={fimRef} />
            </div>

            <form className="composer" onSubmit={enviar}>
              {sugestoes.length > 0 && (
                <ul className="suggestions" role="listbox">
                  {sugestoes.map((r, i) => (
                    <li key={r.id} role="option" aria-selected={i === sugIdx} className={i === sugIdx ? "sel" : ""} onMouseDown={(e) => { e.preventDefault(); usarSugestao(r); }}>
                      <strong>/{r.title}</strong><span className="muted">{r.text}</span>
                    </li>
                  ))}
                </ul>
              )}
              <textarea
                ref={textoRef}
                placeholder="Escreva uma mensagem…  ( / para respostas rápidas · Shift+Enter quebra linha )"
                value={texto}
                onChange={(e) => setTexto(e.target.value)}
                onKeyDown={onKeyDown}
                rows={1}
                aria-label="Mensagem"
              />
              <button className="primary" disabled={!texto.trim() || enviando} title="Enviar (Enter)" aria-label="Enviar">
                <Icon name="send" size={17} />
              </button>
            </form>
          </>
        )}
      </section>

      {modal === "transferir" && (
        <TransferirModal
          deps={deps}
          usuarios={usuarios}
          atual={ticket}
          onClose={() => setModal(null)}
          onOk={async (body) => {
            await api(`/contacts/${selId}/ticket/transfer`, { method: "POST", body });
            setModal(null);
            toast.show("Chamado transferido");
            carregarConversa(selId);
            carregarLista();
          }}
        />
      )}
      {modal === "fechar" && (
        <FecharModal
          assuntos={assuntos}
          protocolo={ticket?.protocol}
          onClose={() => setModal(null)}
          onOk={async (body) => {
            await api(`/contacts/${selId}/ticket/close`, { method: "POST", body });
            setModal(null);
            toast.show("Chamado fechado");
            carregarConversa(selId);
            carregarLista();
          }}
        />
      )}
    </div>
  );
}

function TransferirModal({ deps, usuarios, atual, onClose, onOk }) {
  const [departmentId, setDep] = useState(atual?.departmentId || deps[0]?.id || "");
  const [userId, setUser] = useState("");
  const [comments, setComments] = useState("");
  const [erro, setErro] = useState("");
  const [salvando, setSalvando] = useState(false);
  const daEquipe = usuarios.filter((u) => !departmentId || u.departmentIds.includes(departmentId) || u.isAdmin);
  const confirmar = async () => {
    setSalvando(true);
    try {
      await onOk({ departmentId, userId: userId || null, comments });
    } catch (e) {
      setErro(e.message);
      setSalvando(false);
    }
  };
  return (
    <Modal titulo="Transferir chamado" onClose={onClose}>
      <label>Departamento
        <select value={departmentId} onChange={(e) => { setDep(e.target.value); setUser(""); }}>
          {deps.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
      </label>
      <label>Atendente
        <select value={userId} onChange={(e) => setUser(e.target.value)}>
          <option value="">Deixar na fila do departamento</option>
          {daEquipe.map((u) => <option key={u.id} value={u.id}>{u.name}{u.status === "online" ? " · online" : ""}</option>)}
        </select>
      </label>
      <label>Comentário (opcional)<textarea value={comments} onChange={(e) => setComments(e.target.value)} rows={3} placeholder="Ex.: cliente quer falar sobre o boleto de novembro" /></label>
      {erro && <div className="error">{erro}</div>}
      <div className="modal-actions">
        <button onClick={onClose}>Cancelar</button>
        <button className="primary" disabled={salvando} onClick={confirmar}><Icon name="transfer" size={16} />{salvando ? "Transferindo…" : "Transferir"}</button>
      </div>
    </Modal>
  );
}

function FecharModal({ assuntos, protocolo, onClose, onOk }) {
  const [sel, setSel] = useState([]);
  const [comments, setComments] = useState("");
  const [erro, setErro] = useState("");
  const [salvando, setSalvando] = useState(false);
  const toggle = (id) => setSel((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  const confirmar = async () => {
    setSalvando(true);
    try {
      await onOk({ ticketTopicIds: sel, comments });
    } catch (e) {
      setErro(e.message);
      setSalvando(false);
    }
  };
  return (
    <Modal titulo={`Fechar chamado${protocolo ? ` #${protocolo}` : ""}`} onClose={onClose}>
      <div className="field-title">Assunto do atendimento</div>
      <div className="checks">
        {assuntos.length === 0 && <span className="muted small">Nenhum assunto cadastrado (Configurações → Assuntos).</span>}
        {assuntos.map((a) => (
          <label key={a.id} className="check"><input type="checkbox" checked={sel.includes(a.id)} onChange={() => toggle(a.id)} /> {a.name}</label>
        ))}
      </div>
      <label>Comentário (opcional)<textarea value={comments} onChange={(e) => setComments(e.target.value)} rows={3} /></label>
      {erro && <div className="error">{erro}</div>}
      <div className="modal-actions">
        <button onClick={onClose}>Cancelar</button>
        <button className="danger" disabled={salvando} onClick={confirmar}><Icon name="check" size={16} />{salvando ? "Fechando…" : "Fechar chamado"}</button>
      </div>
    </Modal>
  );
}
