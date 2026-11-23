import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import Modal from "../components/Modal";
import Icon from "../components/Icon";
import Avatar from "../components/Avatar";
import PageHead from "../components/PageHead";
import { useToast } from "../components/Toast";
import { corDoTexto, fmtNumero } from "../formato";

export default function Contatos() {
  const toast = useToast();
  const [itens, setItens] = useState([]);
  const [total, setTotal] = useState(0);
  const [carregando, setCarregando] = useState(true);
  const [busca, setBusca] = useState("");
  const [services, setServices] = useState([]);
  const [tags, setTags] = useState([]);
  const [editando, setEditando] = useState(null);
  const [erro, setErro] = useState("");
  const navigate = useNavigate();

  const carregar = useCallback(() => {
    api("/contacts", { params: { q: busca || undefined, perPage: 100 } })
      .then((r) => {
        setItens(r.data);
        setTotal(r.total);
      })
      .catch((e) => setErro(e.message))
      .finally(() => setCarregando(false));
  }, [busca]);

  useEffect(() => {
    const t = setTimeout(carregar, 200);
    return () => clearTimeout(t);
  }, [carregar]);

  useEffect(() => {
    api("/services", { params: { perPage: 100 } }).then((r) => setServices(r.data));
    api("/tags", { params: { perPage: 200 } }).then((r) => setTags(r.data));
  }, []);

  const tagById = (id) => tags.find((t) => t.id === id);
  const novo = () => setEditando({ serviceId: services[0]?.id, tagIds: [] });

  return (
    <div className="page">
      <PageHead icone="contacts" secao="Dia a dia" titulo="Contatos" contagem={carregando ? null : total} subtitulo="Clientes que já falaram com a empresa. Clique em Conversar para abrir o atendimento.">
        <div className="search-box search">
          <Icon name="search" size={16} />
          <input placeholder="Nome ou número" value={busca} onChange={(e) => setBusca(e.target.value)} onKeyDown={(e) => e.key === "Escape" && setBusca("")} aria-label="Buscar contato" />
          {busca && <button type="button" className="icon-btn search-clear" onClick={() => setBusca("")} aria-label="Limpar busca" title="Limpar busca"><Icon name="x" size={15} /></button>}
        </div>
        <button className="primary" onClick={novo}><Icon name="plus" size={16} />Novo contato</button>
      </PageHead>
      {erro && <div className="error">{erro}</div>}
      <div className="table-wrap">
        <table className="table">
          <thead><tr><th>Nome</th><th>Número</th><th>Tags</th><th>Chamado</th><th /></tr></thead>
          <tbody>
            {carregando &&
              [0, 1, 2, 3].map((i) => (
                <tr key={i} className="sk-row">
                  <td><span className="row gap"><span className="sk sk-circle" style={{ width: 32, height: 32 }} /><span className="sk sk-line" style={{ width: 140 }} /></span></td>
                  <td><span className="sk sk-line" style={{ width: 110 }} /></td>
                  <td><span className="sk sk-line" style={{ width: 70 }} /></td>
                  <td><span className="sk sk-line" style={{ width: 50 }} /></td>
                  <td />
                </tr>
              ))}
            {!carregando && itens.length === 0 && (
              <tr className="empty">
                <td colSpan={5}>
                  <div className="empty-state">
                    <span className="empty-icon"><Icon name={busca ? "search" : "contacts"} size={24} /></span>
                    <strong>{busca ? "Nenhum contato encontrado" : "Nenhum contato ainda"}</strong>
                    <span>{busca ? "Confira o nome ou o número digitado." : "Eles aparecem aqui quando mandam mensagem, ou cadastre um agora."}</span>
                    {busca ? <button onClick={() => setBusca("")}>Limpar busca</button> : <button className="primary" onClick={novo}><Icon name="plus" size={16} />Novo contato</button>}
                  </div>
                </td>
              </tr>
            )}
            {itens.map((c) => (
              <tr key={c.id}>
                <td>
                  <span className="row gap">
                    <Avatar nome={c.internalName || c.name} size={32} url={c.avatarUrl} grupo={c.isGroup} />
                    <span style={{ minWidth: 0 }}>
                      <strong>{c.internalName || c.name}</strong>
                      {c.internalName && c.name && c.internalName !== c.name && <div className="muted small">{c.name}</div>}
                    </span>
                  </span>
                </td>
                <td className="mono small nowrap">{c.isGroup ? <span className="chip chip-soft"><Icon name="users" size={12} />Grupo</span> : fmtNumero(c.data?.number) || c.data?.number}</td>
                <td>
                  {c.tagIds.map((id) => tagById(id)).filter(Boolean).map((t) => (
                    <span key={t.id} className="tag" style={{ background: t.color, color: corDoTexto(t.color) }}>{t.label}</span>
                  ))}
                </td>
                <td>{c.currentTicketId ? <span className="chip ok">Aberto</span> : <span className="muted">—</span>}</td>
                <td className="right">
                  <span className="row-actions">
                    <button className="link" onClick={() => navigate(`/?contact=${c.id}`)}><Icon name="chat" size={15} />Conversar</button>
                    <button className="link" onClick={() => setEditando(c)}><Icon name="edit" size={15} />Editar</button>
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {editando && (
        <ContatoForm
          inicial={editando}
          services={services}
          tags={tags}
          onClose={() => setEditando(null)}
          onSave={async (body) => {
            if (editando.id) await api(`/contacts/${editando.id}`, { method: "PUT", body });
            else await api("/contacts", { method: "POST", body });
            toast.show(editando.id ? "Contato atualizado" : "Contato criado");
            setEditando(null);
            carregar();
          }}
        />
      )}
    </div>
  );
}

function ContatoForm({ inicial, services, tags, onClose, onSave }) {
  const [form, setForm] = useState({
    serviceId: inicial.serviceId || "",
    name: inicial.name || "",
    internalName: inicial.internalName || "",
    number: inicial.data?.number || "",
    email: inicial.data?.email || "",
    note: inicial.note || "",
    tagIds: inicial.tagIds || [],
  });
  const [erro, setErro] = useState("");
  const [salvando, setSalvando] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const toggleTag = (id) => set("tagIds", form.tagIds.includes(id) ? form.tagIds.filter((x) => x !== id) : [...form.tagIds, id]);

  const salvar = async (e) => {
    e.preventDefault();
    setErro("");
    setSalvando(true);
    try {
      await onSave(form);
    } catch (err) {
      setErro(err.message);
      setSalvando(false);
    }
  };

  return (
    <Modal titulo={inicial.id ? "Editar contato" : "Novo contato"} icone={inicial.id ? "edit" : "contacts"} onClose={onClose} largura="540px">
      <form onSubmit={salvar}>
        {!inicial.id && (
          <label>Conexão
            <select value={form.serviceId} onChange={(e) => set("serviceId", e.target.value)}>
              {services.map((s) => <option key={s.id} value={s.id}>{s.name} ({s.type})</option>)}
            </select>
          </label>
        )}
        <div className="form-grid">
          <label>Nome<input value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="Como aparece no WhatsApp" /></label>
          <label>Nome interno<input value={form.internalName} onChange={(e) => set("internalName", e.target.value)} placeholder="Ex.: Padaria Pão Quente" /><span className="field-hint">Só a equipe vê. Tem prioridade na lista.</span></label>
        </div>
        <div className="form-grid">
          <label>Número
            <input value={form.number} onChange={(e) => set("number", e.target.value)} disabled={!!inicial.id} inputMode="numeric" placeholder="5516999999999" />
            <span className="field-hint">{inicial.id ? "O número não muda depois de criado." : "55 + DDD + número, só dígitos."}</span>
          </label>
          <label>E-mail<input type="email" value={form.email} onChange={(e) => set("email", e.target.value)} placeholder="opcional" /></label>
        </div>
        <label>Observação<textarea rows={2} value={form.note} onChange={(e) => set("note", e.target.value)} placeholder="Anotações para a equipe" /></label>
        <div className="field-title">Tags</div>
        <div className="toggle-chips">
          {tags.length === 0 && <span className="toggle-empty">Nenhuma tag cadastrada (Configurações → Tags).</span>}
          {tags.map((t) => {
            const on = form.tagIds.includes(t.id);
            return (
              <button
                key={t.id}
                type="button"
                aria-pressed={on}
                className={`toggle-chip ${on ? "on" : ""}`}
                style={on ? { background: t.color, borderColor: t.color, color: corDoTexto(t.color) } : undefined}
                onClick={() => toggleTag(t.id)}
              >
                {on ? <Icon name="check" size={14} /> : <span className="dot" style={{ background: t.color }} />}{t.label}
              </button>
            );
          })}
        </div>
        {erro && <div className="error">{erro}</div>}
        <div className="modal-actions">
          <button type="button" onClick={onClose}>Cancelar</button>
          <button className="primary" disabled={salvando}><Icon name="check" size={16} />{salvando ? "Salvando…" : "Salvar"}</button>
        </div>
      </form>
    </Modal>
  );
}
