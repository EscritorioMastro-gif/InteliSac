import { useEffect, useRef } from "react";
import Icon from "./Icon";

export default function Modal({ titulo, onClose, children, largura }) {
  const ref = useRef(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") closeRef.current();
    };
    document.addEventListener("keydown", onKey);
    // Foca o primeiro campo do formulário só ao abrir
    const first = ref.current?.querySelector("input:not([type=hidden]):not([disabled]), select, textarea");
    first?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <div className="modal" ref={ref} style={largura ? { maxWidth: largura } : undefined} role="dialog" aria-modal="true" aria-label={titulo} onMouseDown={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3>{titulo}</h3>
          <button className="icon-btn" onClick={onClose} aria-label="Fechar"><Icon name="x" /></button>
        </div>
        {children}
      </div>
    </div>
  );
}
