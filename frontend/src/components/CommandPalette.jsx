// Busca rápida (Ctrl+K): vai para qualquer tela, abre uma conversa pelo nome ou número
// e executa ações (status, som, avisos...) sem tirar a mão do teclado.
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import Icon from "./Icon";
import Avatar from "./Avatar";
import { fmtNumero } from "../formato";

const semAcento = (s) =>
  String(s || "")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();

export default function CommandPalette({ paginas, acoes, onFechar }) {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [contatos, setContatos] = useState([]);
  const [buscando, setBuscando] = useState(false);
  const [idx, setIdx] = useState(0);
  const listaRef = useRef(null);
  const antes = useRef(document.activeElement);

  // devolve o foco para onde estava ao fechar
  useEffect(() => () => antes.current?.focus?.(), []);

  // Conversas: busca no servidor a partir de 2 letras
  useEffect(() => {
    const termo = q.trim();
    if (termo.length < 2) {
      setContatos([]);
      setBuscando(false);
      return undefined;
    }
    setBuscando(true);
    let vivo = true;
    const t = setTimeout(() => {
      api("/contacts", { params: { filter: "all", q: termo, perPage: 8 } })
        .then((r) => vivo && setContatos(r.data))
        .catch(() => vivo && setContatos([]))
        .finally(() => vivo && setBuscando(false));
    }, 220);
    return () => {
      vivo = false;
      clearTimeout(t);
    };
  }, [q]);

  const itens = useMemo(() => {
    const termo = semAcento(q.trim());
    const bate = (...txt) => !termo || txt.some((x) => semAcento(x).includes(termo));
    const pag = paginas
      .filter((p) => bate(p.label, p.desc))
      .map((p) => ({ grupo: "Ir para", id: `p${p.to}`, icone: p.icon, rotulo: p.label, dica: p.desc, run: () => navigate(p.to) }));
    const ac = acoes.filter((a) => bate(a.rotulo, a.dica)).map((a) => ({ grupo: "Ações", ...a }));
    const ct = contatos.map((c) => ({
      grupo: "Conversas",
      id: `c${c.id}`,
      contato: c,
      rotulo: c.internalName || c.name,
      dica: c.isGroup ? "Grupo do WhatsApp" : fmtNumero(c.data?.number) || c.data?.number,
      run: () => navigate(`/?contact=${c.id}`),
    }));
    return termo ? [...ct, ...pag, ...ac] : [...pag, ...ac];
  }, [q, paginas, acoes, contatos, navigate]);

  useEffect(() => setIdx(0), [q, contatos]);
  useEffect(() => {
    listaRef.current?.querySelector(".cmd-item.sel")?.scrollIntoView({ block: "nearest" });
  }, [idx]);

  const executar = (it) => {
    onFechar();
    it.run();
  };

  const onKeyDown = (e) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setIdx((i) => (itens.length ? (i + 1) % itens.length : 0));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setIdx((i) => (itens.length ? (i - 1 + itens.length) % itens.length : 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (itens[idx]) executar(itens[idx]);
    } else if (e.key === "Escape") {
      e.preventDefault();
      onFechar();
    } else if (e.key === "Tab") {
      e.preventDefault(); // o foco fica no campo de busca
    }
  };

  let grupoAtual = null;
  return (
    <div className="cmd-backdrop" onMouseDown={onFechar}>
      <div className="cmd" role="dialog" aria-modal="true" aria-label="Busca rápida" onMouseDown={(e) => e.stopPropagation()}>
        <div className="cmd-search">
          <Icon name="search" size={19} />
          <input
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Buscar tela, ação ou conversa (nome ou número)…"
            aria-label="Buscar"
            aria-controls="cmd-lista"
            aria-activedescendant={itens[idx] ? `cmd-${itens[idx].id}` : undefined}
          />
          {buscando && <span className="cmd-spin" aria-label="Buscando" />}
          <kbd>Esc</kbd>
        </div>
        <ul className="cmd-list" id="cmd-lista" role="listbox" ref={listaRef}>
          {itens.length === 0 && (
            <li className="cmd-empty">
              {q.trim().length >= 2 && buscando ? "Buscando conversas…" : "Nada encontrado. Tente outro nome, número ou tela."}
            </li>
          )}
          {itens.map((it, i) => {
            const cabecalho = it.grupo !== grupoAtual ? it.grupo : null;
            grupoAtual = it.grupo;
            return (
              <li key={it.id} role="presentation">
                {cabecalho && <div className="cmd-group">{cabecalho}</div>}
                <div
                  id={`cmd-${it.id}`}
                  role="option"
                  aria-selected={i === idx}
                  className={`cmd-item ${i === idx ? "sel" : ""}`}
                  onMouseMove={() => i !== idx && setIdx(i)}
                  onClick={() => executar(it)}
                >
                  {it.contato ? (
                    <Avatar nome={it.rotulo} url={it.contato.avatarUrl} grupo={it.contato.isGroup} size={30} />
                  ) : (
                    <span className="cmd-ico"><Icon name={it.icone || "chevronRight"} size={17} /></span>
                  )}
                  <span className="cmd-text">
                    <strong>{it.rotulo}</strong>
                    {it.dica && <small>{it.dica}</small>}
                  </span>
                  {it.contato?.currentTicketId && <span className="chip">Chamado aberto</span>}
                  {i === idx && <span className="cmd-enter"><Icon name="enter" size={14} /></span>}
                </div>
              </li>
            );
          })}
        </ul>
        <div className="cmd-foot">
          <span><kbd>↑</kbd><kbd>↓</kbd> navegar</span>
          <span><kbd>Enter</kbd> abrir</span>
          <span><kbd>Ctrl</kbd><kbd>K</kbd> abre e fecha</span>
        </div>
      </div>
    </div>
  );
}
