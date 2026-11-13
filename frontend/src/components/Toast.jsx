// Avisos rápidos no canto da tela ("Chamado transferido", erros etc.).
import { createContext, useCallback, useContext, useMemo, useState } from "react";
import Icon from "./Icon";

const ToastContext = createContext({ show: () => {} });
export const useToast = () => useContext(ToastContext);

let seq = 0;

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const show = useCallback((text, kind = "ok") => {
    const id = ++seq;
    setToasts((t) => [...t, { id, text, kind }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), kind === "error" ? 6000 : 3000);
  }, []);

  const value = useMemo(() => ({ show }), [show]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.kind}`} onClick={() => setToasts((all) => all.filter((x) => x.id !== t.id))}>
            <Icon name={t.kind === "error" ? "x" : "check"} size={16} />
            <span>{t.text}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
