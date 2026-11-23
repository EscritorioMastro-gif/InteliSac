import { useEffect, useRef } from "react";
import Icon from "./Icon";

// Janelas abertas, da de baixo para a de cima: só a de cima responde ao Esc e ao Tab
// (ex.: confirmação aberta por cima de um formulário).
const pilha = [];

const FOCAVEIS =
  'a[href], button:not([disabled]), input:not([disabled]):not([type=hidden]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export default function Modal({ titulo, subtitulo, icone, tom, onClose, children, largura }) {
  const ref = useRef(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    const eu = {};
    pilha.push(eu);
    const antes = document.activeElement;
    const onKey = (e) => {
      if (pilha[pilha.length - 1] !== eu) return;
      if (e.key === "Escape") {
        closeRef.current();
        return;
      }
      // Tab fica dentro da janela (não vai parar nos botões da tela de trás)
      if (e.key === "Tab" && ref.current) {
        const lista = [...ref.current.querySelectorAll(FOCAVEIS)].filter((el) => el.offsetParent !== null);
        if (!lista.length) return;
        const primeiro = lista[0];
        const ultimo = lista[lista.length - 1];
        if (!ref.current.contains(document.activeElement)) {
          e.preventDefault();
          primeiro.focus();
        } else if (e.shiftKey && document.activeElement === primeiro) {
          e.preventDefault();
          ultimo.focus();
        } else if (!e.shiftKey && document.activeElement === ultimo) {
          e.preventDefault();
          primeiro.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    // Foca o campo marcado (data-autofocus) ou o primeiro campo do formulário, só ao abrir
    if (!ref.current?.contains(document.activeElement)) {
      const first = ref.current?.querySelector("[data-autofocus], input:not([type=hidden]):not([disabled]), select, textarea");
      (first || ref.current)?.focus();
    }
    return () => {
      document.removeEventListener("keydown", onKey);
      const i = pilha.indexOf(eu);
      if (i >= 0) pilha.splice(i, 1);
      // devolve o foco para onde estava (o botão que abriu a janela)
      if (antes && typeof antes.focus === "function" && document.contains(antes)) antes.focus();
    };
  }, []);

  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <div
        className={`modal ${tom ? `modal-${tom}` : ""}`}
        ref={ref}
        tabIndex={-1}
        style={largura ? { maxWidth: largura } : undefined}
        role="dialog"
        aria-modal="true"
        aria-label={titulo}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="modal-head">
          {icone && <span className="modal-icon"><Icon name={icone} size={19} /></span>}
          <div className="modal-titles">
            <h3>{titulo}</h3>
            {subtitulo && <p>{subtitulo}</p>}
          </div>
          <button type="button" className="icon-btn modal-close" onClick={onClose} aria-label="Fechar" title="Fechar (Esc)"><Icon name="x" /></button>
        </div>
        {children}
      </div>
    </div>
  );
}
