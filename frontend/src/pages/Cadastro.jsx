// Tela genérica de cadastro (lista + formulário), usada para departamentos, tags, usuários etc.
import { useCallback, useEffect, useState } from "react";
import { api, resource } from "../api";
import Modal from "../components/Modal";
import Icon from "../components/Icon";
import { useToast } from "../components/Toast";

export default function Cadastro({ titulo, subtitulo, path, campos, colunas, arquivar = false }) {
  const res = resource(path);
  const toast = useToast();
  const [itens, setItens] = useState([]);
  const [carregando, setCarregando] = useState(true);
  const [busca, setBusca] = useState("");
  const [arquivados, setArquivados] = useState(false);
  const [editando, setEditando] = useState(null);
  const cols = colunas || campos.filter((c) => !["password", "departments", "checkbox"].includes(c.type)).slice(0, 3);

  const carregar = useCallback(() => {
    api(path, { params: { q: busca || undefined, perPage: 200, archived: arquivados || undefined } })
      .then((r) => setItens(r.data))
      .catch((e) => toast.show(e.message, "error"))
      .finally(() => setCarregando(false));
  }, [path, busca, arquivados, toast]);

  useEffect(() => {
    const t = setTimeout(carregar, 200);
    return () => clearTimeout(t);
  }, [carregar]);

  const alternarArquivo = async (it) => {
    try {
      await res.archive(it.id, !it.archivedAt);
      toast.show(it.archivedAt ? "Desarquivado" : "Arquivado");
      carregar();
    } catch (e) {
      toast.show(e.message, "error");
    }
  };

  const excluir = async (it) => {
    if (!window.confirm("Excluir este item? Essa ação não pode ser desfeita.")) return;
    try {
      await res.deleteById(it.id);
      toast.show("Excluído");
      carregar();
    } catch (e) {
      toast.show(e.message, "error");
    }
  };

  return (
    <div className="page">
      <div className="page-head">
        <h2>{titulo}</h2>
        <div className="row gap wrap">
          <div className="search-box search">
            <Icon name="search" size={16} />
            <input placeholder="Buscar" value={busca} onChange={(e) => setBusca(e.target.value)} aria-label={`Buscar em ${titulo}`} />
          </div>
          {arquivar && (
            <label className="check"><input type="checkbox" checked={arquivados} onChange={(e) => setArquivados(e.target.checked)} /> Mostrar arquivados</label>
          )}
          <button className="primary" onClick={() => setEditando({})}><Icon name="plus" size={16} />Novo</button>
        </div>
      </div>
      {subtitulo && <p className="page-sub">{subtitulo}</p>}
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>{cols.map((c) => <th key={c.name}>{c.label}</th>)}<th /></tr>
          </thead>
          <tbody>
            {!carregando && itens.length === 0 && (
              <tr className="empty"><td colSpan={cols.length + 1}>{busca ? "Nada encontrado para essa busca." : "Nada cadastrado ainda. Clique em Novo para começar."}</td></tr>
            )}
            {itens.map((it) => (
              <tr key={it.id} className={it.archivedAt ? "archived" : ""}>
                {cols.map((c) => (
                  <td key={c.name}>
                    {c.type === "color" ? <span className="swatch" style={{ background: it[c.name] }} /> : null}
                    {c.render ? c.render(it[c.name], it) : String(it[c.name] ?? "")}
                  </td>
                ))}
                <td className="right">
                  <button className="link" onClick={() => setEditando(it)}><Icon name="edit" size={15} />Editar</button>
                  {arquivar ? (
                    <button className="link" onClick={() => alternarArquivo(it)}><Icon name="archive" size={15} />{it.archivedAt ? "Desarquivar" : "Arquivar"}</button>
                  ) : (
                    <button className="link danger" onClick={() => excluir(it)}><Icon name="trash" size={15} />Excluir</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {editando && (
        <Formulario
          titulo={editando.id ? `Editar — ${titulo}` : `Novo — ${titulo}`}
          campos={campos}
          inicial={editando}
          onClose={() => setEditando(null)}
          onSave={async (body) => {
            if (editando.id) await res.updateById(editando.id, body);
            else await res.create(body);
            toast.show(editando.id ? "Alterações salvas" : "Cadastrado com sucesso");
            setEditando(null);
            carregar();
          }}
        />
      )}
    </div>
  );
}

function valorInicial(c, inicial) {
  if (c.skipLoad) return "";
  if (inicial[c.name] !== undefined && inicial[c.name] !== null) return inicial[c.name];
  if (c.type === "checkbox") return false;
  if (c.type === "departments") return [];
  if (c.type === "color") return "#0f5e66";
  return c.options?.[0] ?? "";
}

function Formulario({ titulo, campos, inicial, onClose, onSave }) {
  const [form, setForm] = useState(() => Object.fromEntries(campos.map((c) => [c.name, valorInicial(c, inicial)])));
  const [deps, setDeps] = useState([]);
  const [erro, setErro] = useState("");
  const [salvando, setSalvando] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    if (campos.some((c) => c.type === "departments")) api("/departments", { params: { perPage: 200 } }).then((r) => setDeps(r.data));
  }, [campos]);

  const salvar = async (e) => {
    e.preventDefault();
    const body = { ...form };
    campos.forEach((c) => c.type === "password" && !body[c.name] && delete body[c.name]);
    setErro("");
    setSalvando(true);
    try {
      await onSave(body);
    } catch (err) {
      setErro(err.message);
      setSalvando(false);
    }
  };

  return (
    <Modal titulo={titulo} onClose={onClose}>
      <form onSubmit={salvar}>
        {campos.map((c) => {
          if (c.type === "textarea")
            return <label key={c.name}>{c.label}<textarea rows={4} value={form[c.name]} onChange={(e) => set(c.name, e.target.value)} /></label>;
          if (c.type === "select")
            return (
              <label key={c.name}>{c.label}
                <select value={form[c.name]} onChange={(e) => set(c.name, e.target.value)}>
                  {c.options.map((o) => <option key={o} value={o}>{o}</option>)}
                </select>
              </label>
            );
          if (c.type === "checkbox")
            return <label key={c.name} className="check" style={{ margin: "12px 0" }}><input type="checkbox" checked={!!form[c.name]} onChange={(e) => set(c.name, e.target.checked)} /> {c.label}</label>;
          if (c.type === "departments")
            return (
              <div key={c.name}>
                <div className="field-title">{c.label}</div>
                <div className="checks">
                  {deps.map((d) => (
                    <label key={d.id} className="check">
                      <input
                        type="checkbox"
                        checked={form[c.name].includes(d.id)}
                        onChange={() => set(c.name, form[c.name].includes(d.id) ? form[c.name].filter((x) => x !== d.id) : [...form[c.name], d.id])}
                      /> {d.name}
                    </label>
                  ))}
                </div>
              </div>
            );
          return (
            <label key={c.name}>{c.label}
              <input
                type={c.type || "text"}
                value={form[c.name]}
                onChange={(e) => set(c.name, e.target.value)}
                autoComplete={c.type === "password" ? "new-password" : "off"}
                minLength={c.type === "password" && form[c.name] ? 8 : undefined}
              />
            </label>
          );
        })}
        {erro && <div className="error">{erro}</div>}
        <div className="modal-actions">
          <button type="button" onClick={onClose}>Cancelar</button>
          <button className="primary" disabled={salvando}>{salvando ? "Salvando…" : "Salvar"}</button>
        </div>
      </form>
    </Modal>
  );
}
