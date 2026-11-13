import Icon from "./Icon";

// Situação da mensagem enviada, como no WhatsApp: relógio = enviando, ✓ = enviada,
// ✓✓ cinza = entregue no celular do cliente, ✓✓ azul = lida (ou áudio ouvido).
const ACK = {
  pending: { icon: "clock", label: "Enviando" },
  sent: { icon: "check", label: "Enviada" },
  delivered: { icon: "checks", label: "Entregue" },
  read: { icon: "checks", label: "Lida", lida: true },
  played: { icon: "checks", label: "Ouvida", lida: true },
};

export default function Tiques({ m }) {
  if (!m.isFromMe || m.data?.error || m.data?.deleted) return null;
  const a = ACK[m.data?.ack];
  if (!a) return null;
  return (
    <span className={`ack ${a.lida ? "lida" : ""}`} title={a.label} aria-label={a.label}>
      <Icon name={a.icon} size={15} />
    </span>
  );
}
