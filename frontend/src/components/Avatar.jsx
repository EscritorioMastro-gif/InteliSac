// Avatar com iniciais e cor estável por nome (tons que combinam com o verde petróleo).
const CORES = ["#0F5E66", "#2A7F62", "#3C6E91", "#7A5C99", "#B5654A", "#8A7A2E", "#4F6D7A", "#9C4F6B"];

function iniciais(nome) {
  const partes = (nome || "?").trim().split(/\s+/).filter(Boolean);
  if (!partes.length) return "?";
  const a = partes[0][0] || "";
  const b = partes.length > 1 ? partes[partes.length - 1][0] : "";
  return (a + b).toUpperCase() || "?";
}

export default function Avatar({ nome, size = 40 }) {
  let h = 0;
  for (const ch of nome || "") h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  const cor = CORES[h % CORES.length];
  return (
    <div className="avatar" style={{ width: size, height: size, background: cor, fontSize: size * 0.38 }} aria-hidden="true">
      {iniciais(nome)}
    </div>
  );
}
