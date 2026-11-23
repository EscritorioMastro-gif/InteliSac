// Tela genérica de cadastro (lista + formulário), usada para departamentos, tags, usuários etc.
import { useCallback, useEffect, useState } from "react";
import { api, resource } from "../api";
import Modal from "../components/Modal";
import Icon from "../components/Icon";
import PageHead from "../components/PageHead";
import { useToast } from "../components/Toast";
import { useConfirm } from "../components/Confirm";

// Cores prontas para tags: as mesmas do sistema (avatares e avisos)
const CORES = ["#0f5e66", "#1c8590", "#2a7f62", "#3c6e91", "#52658c", "#7a5c99", "#9c4f6b", "#b5654a", "#c0392b", "#b7791f", "#8a7a2e", "#4f6d7a"];

export default function Cadastro({ icone, secao, titulo, subtitulo, item = "item", feminino = false, path, campos, colunas, arquivar = false }) {
  const res = resource(path);
  const toast = useToast();
  const confirmar = useConfirm();
  const [itens, setItens] = useState([]);
  const [carregando, setCarregando] = useState(true);
  const [busca, setBusca] = useState("");
  const [arquivados, setArquivados] = useState(false);
  const [editando, setEditando] = useState(null);
  const cols = colunas || campos.filter((c) => !["password", "departments", "checkbox"].includes(c.type)).slice(0, 3);
  const singular = titulo.toLowerCase();
  const rotuloNovo = `${feminino ? "Nova" : "Novo"} ${item}`;

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
      toast.show(it.archivedAt ? "Desarquivado" : "Arquivado. Marque “Mostrar arquivados” para ver de novo.");
      carregar();
    } catch (e) {
      toast.show(e.message, "error");
    }
  };

  const excluir = async (it) => {
    const nome = it.label || it.name || it.title || "este item";
    const ok = await confirmar({
      titulo: `Excluir “${nome}”?`,
      texto: "Essa ação não pode ser desfeita.",
      ok: "Excluir",
      perigo: true,
    });
    if (!ok) return;
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
      <PageHead icone={icone} secao={secao} titulo={titulo} contagem={carregando ? null : itens.length} subtitulo={subtitulo}>
        <div className="search-box search">
          <Icon name="search" size={16} />
          <input placeholder={`Buscar em ${singular}`} value={busca} onChange={(e) => setBusca(e.target.value)} onKeyDown={(e) => e.key === "Escape" && setBusca("")} aria-label={`Buscar em ${titulo}`} />
          {busca && <button type="button" className="icon-btn search-clear" onClick={() => setBusca("")} aria-label="Limpar busca" title="Limpar busca"><Icon name="x" size={15} /></button>}
        </div>
        {arquivar && (
          <label className="switch-row compact">
            <input type="checkbox" checked={arquivados} onChange={(e) => setArquivados(e.target.checked)} />
            <span className="switch" aria-hidden="true" />
            <span>Mostrar arquivados</span>
          </label>
        )}
        <button className="primary" onClick={() => setEditando({})}><Icon name="plus" size={16} />{rotuloNovo}</button>
      </PageHead>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>{cols.map((c) => <th key={c.name}>{c.label}</th>)}<th /></tr>
          </thead>
          <tbody>
            {carregando &&
              [0, 1, 2].map((i) => (
                <tr key={i} className="sk-row">
                  {cols.map((c) => <td key={c.name}><span className="sk sk-line" style={{ width: `${40 + ((i * 17) % 40)}%` }} /></td>)}
                  <td />
                </tr>
              ))}
            {!carregando && itens.length === 0 && (
              <tr className="empty">
                <td colSpan={cols.length + 1}>
                  <div className="empty-state">
                    <span className="empty-icon"><Icon name={busca ? "search" : icone || "list"} size={24} /></span>
                    <strong>{busca ? "Nada encontrado" : "Nada cadastrado ainda"}</strong>
                    <span>{busca ? "Tente outra palavra ou limpe a busca." : `Clique em ${rotuloNovo} para começar.`}</span>
                    {busca ? (
                      <button onClick={() => setBusca("")}>Limpar busca</button>
                    ) : (
                      <button className="primary" onClick={() => setEditando({})}><Icon name="plus" size={16} />{rotuloNovo}</button>
                    )}
                  </div>
                </td>
              </tr>
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
                  <span className="row-actions">
                    <button className="link" onClick={() => setEditando(it)}><Icon name="edit" size={15} />Editar</button>
                    {arquivar ? (
                      <button className="link" onClick={() => alternarArquivo(it)}><Icon name="archive" size={15} />{it.archivedAt ? "Desarquivar" : "Arquivar"}</button>
                    ) : (
                      <button className="link danger" onClick={() => excluir(it)}><Icon name="trash" size={15} />Excluir</button>
                    )}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {editando && (
        <Formulario
          titulo={editando.id ? `Editar ${item}` : rotuloNovo}
          icone={editando.id ? "edit" : icone || "plus"}
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

function Formulario({ titulo, icone, campos, inicial, onClose, onSave }) {
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

  const dica = (c) => c.dica && <span className="field-hint">{c.dica}</span>;

  return (
    <Modal titulo={titulo} icone={icone} onClose={onClose}>
      <form onSubmit={salvar}>
        {campos.map((c) => {
          if (c.type === "textarea")
            return <label key={c.name}>{c.label}<textarea rows={4} value={form[c.name]} placeholder={c.placeholder} onChange={(e) => set(c.name, e.target.value)} />{dica(c)}</label>;
          if (c.type === "select")
            return (
              <label key={c.name}>{c.label}
                <select value={form[c.name]} onChange={(e) => set(c.name, e.target.value)}>
                  {c.options.map((o) => <option key={o} value={o}>{o}</option>)}
                </select>
                {dica(c)}
              </label>
            );
          if (c.type === "checkbox")
            return (
              <label key={c.name} className="switch-row">
                <input type="checkbox" checked={!!form[c.name]} onChange={(e) => set(c.name, e.target.checked)} />
                <span className="switch" aria-hidden="true" />
                <span className="grow">{c.label}{dica(c)}</span>
              </label>
            );
          if (c.type === "color")
            return (
              <div key={c.name}>
                <div className="field-title">{c.label}</div>
                <div className="color-field" role="radiogroup" aria-label={c.label}>
                  {CORES.map((cor) => (
                    <button
                      key={cor}
                      type="button"
                      role="radio"
                      aria-checked={form[c.name]?.toLowerCase() === cor}
                      aria-label={`Cor ${cor}`}
                      title={cor}
                      className={`color-swatch ${form[c.name]?.toLowerCase() === cor ? "on" : ""}`}
                      style={{ background: cor }}
                      onClick={() => set(c.name, cor)}
                    />
                  ))}
                  <input type="color" value={form[c.name]} onChange={(e) => set(c.name, e.target.value)} title="Outra cor" aria-label="Outra cor" />
                  {"label" in form && <span className="tag color-preview" style={{ background: form[c.name] }}>{form.label || "Prévia"}</span>}
                </div>
                {dica(c)}
              </div>
            );
          if (c.type === "departments")
            return (
              <div key={c.name}>
                <div className="field-title">{c.label}</div>
                <div className="toggle-chips">
                  {deps.length === 0 && <span className="toggle-empty">Nenhum departamento cadastrado.</span>}
                  {deps.map((d) => {
                    const on = form[c.name].includes(d.id);
                    return (
                      <button
                        key={d.id}
                        type="button"
                        aria-pressed={on}
                        className={`toggle-chip ${on ? "on" : ""}`}
                        onClick={() => set(c.name, on ? form[c.name].filter((x) => x !== d.id) : [...form[c.name], d.id])}
                      >
                        {on && <Icon name="check" size={14} />}{d.name}
                      </button>
                    );
                  })}
                </div>
                {dica(c)}
              </div>
            );
          return (
            <label key={c.name}>{c.label}
              <input
                type={c.type || "text"}
                value={form[c.name]}
                placeholder={c.placeholder}
                onChange={(e) => set(c.name, e.target.value)}
                autoComplete={c.type === "password" ? "new-password" : "off"}
                minLength={c.type === "password" && form[c.name] ? 8 : undefined}
              />
              {dica(c)}
            </label>
          );
        })}
        {erro && <div className="error">{erro}</div>}
        <div className="modal-actions">
          <button type="button" onClick={onClose}>Cancelar</button>
          <button className="primary" disabled={salvando}><Icon name="check" size={16} />{salvando ? "Salvando…" : "Salvar"}</button>
        </div>
      </form>
    </Modal>
  );
}
