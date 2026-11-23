// Avisos rápidos no topo da tela ("Chamado transferido", erros etc.).
// Mouse em cima pausa o tempo (dá para ler com calma); o X fecha na hora.
import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import Icon from "./Icon";

const ToastContext = createContext({ show: () => {} });
export const useToast = () => useContext(ToastContext);

const ICONE = { ok: "check", error: "alert", info: "info" };
const DURACAO = { ok: 3200, info: 4000, error: 6500 };

let seq = 0;

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const timers = useRef(new Map()); // id -> { timer, inicio, restante }

  const remover = useCallback((id) => {
    clearTimeout(timers.current.get(id)?.timer);
    timers.current.delete(id);
    setToasts((t) => t.filter((x) => x.id !== id));
  }, []);

  const agendar = useCallback(
    (id, ms) => {
      timers.current.set(id, { timer: setTimeout(() => remover(id), ms), inicio: Date.now(), restante: ms });
    },
    [remover]
  );

  const show = useCallback(
    (text, kind = "ok") => {
      const id = ++seq;
      const dur = DURACAO[kind] || DURACAO.ok;
      setToasts((t) => [...t.slice(-3), { id, text, kind, dur }]); // no máximo 4 na tela
      agendar(id, dur);
    },
    [agendar]
  );

  const pausar = (id) => {
    const t = timers.current.get(id);
    if (!t) return;
    clearTimeout(t.timer);
    timers.current.set(id, { ...t, timer: null, restante: Math.max(800, t.restante - (Date.now() - t.inicio)) });
  };

  const retomar = (id) => {
    const t = timers.current.get(id);
    if (t && !t.timer) agendar(id, t.restante);
  };

  const value = useMemo(() => ({ show }), [show]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toasts" aria-live="polite">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`toast ${t.kind}`}
            role={t.kind === "error" ? "alert" : "status"}
            onMouseEnter={() => pausar(t.id)}
            onMouseLeave={() => retomar(t.id)}
          >
            <span className="toast-icon"><Icon name={ICONE[t.kind] || "check"} size={16} /></span>
            <span className="toast-text">{t.text}</span>
            <button type="button" className="toast-close" onClick={() => remover(t.id)} aria-label="Fechar aviso"><Icon name="x" size={14} /></button>
            <span className="toast-bar" style={{ animationDuration: `${t.dur}ms` }} />
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
