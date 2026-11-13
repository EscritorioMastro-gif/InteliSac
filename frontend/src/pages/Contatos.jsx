import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import Modal from "../components/Modal";
import Icon from "../components/Icon";
import Avatar from "../components/Avatar";
import { useToast } from "../components/Toast";

export default function Contatos() {
  const toast = useToast();
  const [itens, setItens] = useState([]);
  const [total, setTotal] = useState(0);
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
      .catch((e) => setErro(e.message));
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

  return (
    <div className="page">
      <div className="page-head">
        <h2>Contatos <small className="muted">({total})</small></h2>
        <div className="row gap wrap">
          <div className="search-box search">
            <Icon name="search" size={16} />
            <input placeholder="Nome ou número" value={busca} onChange={(e) => setBusca(e.target.value)} aria-label="Buscar contato" />
          </div>
          <button className="primary" onClick={() => setEditando({ serviceId: services[0]?.id, tagIds: [] })}><Icon name="plus" size={16} />Novo contato</button>
        </div>
      </div>
      <p className="page-sub">Clientes que já falaram com a empresa. Clique em Conversar para abrir o atendimento.</p>
      {erro && <div className="error">{erro}</div>}
      <div className="table-wrap">
        <table className="table">
          <thead><tr><th>Nome</th><th>Número</th><th>Tags</th><th>Chamado</th><th /></tr></thead>
          <tbody>
            {itens.length === 0 && <tr className="empty"><td colSpan={5}>{busca ? "Nenhum contato encontrado." : "Nenhum contato ainda. Eles aparecem aqui quando mandam mensagem."}</td></tr>}
            {itens.map((c) => (
              <tr key={c.id}>
                <td><span className="row gap"><Avatar nome={c.internalName || c.name} size={28} />{c.internalName || c.name}</span></td>
                <td>{c.data?.number}</td>
                <td>{c.tagIds.map((id) => tagById(id)).filter(Boolean).map((t) => <span key={t.id} className="tag" style={{ background: t.color }}>{t.label}</span>)}</td>
                <td>{c.currentTicketId ? <span className="chip">Aberto</span> : <span className="muted">—</span>}</td>
                <td className="right">
                  <button className="link" onClick={() => navigate(`/?contact=${c.id}`)}><Icon name="chat" size={15} />Conversar</button>
                  <button className="link" onClick={() => setEditando(c)}><Icon name="edit" size={15} />Editar</button>
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
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const toggleTag = (id) => set("tagIds", form.tagIds.includes(id) ? form.tagIds.filter((x) => x !== id) : [...form.tagIds, id]);

  return (
    <Modal titulo={inicial.id ? "Editar contato" : "Novo contato"} onClose={onClose}>
      <form onSubmit={(e) => { e.preventDefault(); onSave(form).catch((err) => setErro(err.message)); }}>
        {!inicial.id && (
          <label>Conexão
            <select value={form.serviceId} onChange={(e) => set("serviceId", e.target.value)}>
              {services.map((s) => <option key={s.id} value={s.id}>{s.name} ({s.type})</option>)}
            </select>
          </label>
        )}
        <label>Nome<input value={form.name} onChange={(e) => set("name", e.target.value)} /></label>
        <label>Nome interno<input value={form.internalName} onChange={(e) => set("internalName", e.target.value)} /></label>
        <label>Número (55DDDNNNNNNNNN)<input value={form.number} onChange={(e) => set("number", e.target.value)} disabled={!!inicial.id} /></label>
        <label>E-mail<input type="email" value={form.email} onChange={(e) => set("email", e.target.value)} /></label>
        <label>Observação<textarea rows={2} value={form.note} onChange={(e) => set("note", e.target.value)} /></label>
        <div className="muted small">Tags</div>
        <div className="checks">
          {tags.map((t) => (
            <label key={t.id} className="check"><input type="checkbox" checked={form.tagIds.includes(t.id)} onChange={() => toggleTag(t.id)} /> {t.label}</label>
          ))}
        </div>
        {erro && <div className="error">{erro}</div>}
        <div className="modal-actions">
          <button type="button" onClick={onClose}>Cancelar</button>
          <button className="primary">Salvar</button>
        </div>
      </form>
    </Modal>
  );
}
