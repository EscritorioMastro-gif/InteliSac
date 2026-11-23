// Lista dos atalhos de teclado (abre com "?" ou pelo menu do usuário).
import Modal from "./Modal";

const GRUPOS = [
  {
    titulo: "Em qualquer tela",
    itens: [
      [["Ctrl", "K"], "Busca rápida: telas, conversas e ações"],
      [["?"], "Mostrar estes atalhos"],
      [["Esc"], "Fechar janelas e menus"],
    ],
  },
  {
    titulo: "Atendimento",
    itens: [
      [["Alt", "↑"], "Conversa de cima na lista"],
      [["Alt", "↓"], "Conversa de baixo na lista"],
      [["Enter"], "Enviar a mensagem"],
      [["Shift", "Enter"], "Quebrar linha"],
      [["/"], "Respostas rápidas (no começo do campo)"],
      [["Ctrl", "V"], "Colar print ou arquivo na conversa"],
      [["Esc"], "Cancelar resposta, edição ou seleção"],
    ],
  },
];

export default function Atalhos({ onClose }) {
  return (
    <Modal titulo="Atalhos do teclado" subtitulo="Trabalhe mais rápido sem tirar a mão do teclado." icone="keyboard" onClose={onClose} largura="520px">
      <div className="atalhos">
        {GRUPOS.map((g) => (
          <section key={g.titulo}>
            <h4>{g.titulo}</h4>
            <dl>
              {g.itens.map(([teclas, texto]) => (
                <div key={texto} className="atalho">
                  <dt>{teclas.map((t, i) => <kbd key={i}>{t}</kbd>)}</dt>
                  <dd>{texto}</dd>
                </div>
              ))}
            </dl>
          </section>
        ))}
      </div>
      <div className="modal-actions">
        <button type="button" className="primary" onClick={onClose} data-autofocus>Entendi</button>
      </div>
    </Modal>
  );
}
