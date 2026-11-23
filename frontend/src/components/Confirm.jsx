// Confirmação no estilo do sistema (no lugar do window.confirm do navegador).
// Uso: const confirmar = useConfirm(); if (!(await confirmar({ titulo, texto, ok: "Apagar", perigo: true }))) return;
import { createContext, useCallback, useContext, useRef, useState } from "react";
import Modal from "./Modal";

const ConfirmContext = createContext(async (o) => window.confirm(o?.texto || o?.titulo || "Confirmar?"));
export const useConfirm = () => useContext(ConfirmContext);

export function ConfirmProvider({ children }) {
  const [pedido, setPedido] = useState(null);
  const resolver = useRef(null);

  const confirmar = useCallback(
    (opcoes) =>
      new Promise((resolve) => {
        resolver.current?.(false); // um pedido novo cancela o anterior
        resolver.current = resolve;
        setPedido(opcoes || {});
      }),
    []
  );

  const responder = (v) => {
    resolver.current?.(v);
    resolver.current = null;
    setPedido(null);
  };

  return (
    <ConfirmContext.Provider value={confirmar}>
      {children}
      {pedido && (
        <Modal
          titulo={pedido.titulo || "Confirmar"}
          icone={pedido.perigo ? "alert" : pedido.icone || "info"}
          tom={pedido.perigo ? "perigo" : undefined}
          onClose={() => responder(false)}
          largura="440px"
        >
          {pedido.texto && <p className="confirm-text">{pedido.texto}</p>}
          <div className="modal-actions">
            {/* o foco começa em Cancelar: Enter sem querer não apaga nada */}
            <button type="button" onClick={() => responder(false)} data-autofocus>{pedido.cancelar || "Cancelar"}</button>
            <button type="button" className={pedido.perigo ? "danger" : "primary"} onClick={() => responder(true)}>
              {pedido.ok || "Confirmar"}
            </button>
          </div>
        </Modal>
      )}
    </ConfirmContext.Provider>
  );
}
