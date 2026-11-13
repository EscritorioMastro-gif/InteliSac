// Avatar: foto do perfil do WhatsApp quando houver; senão iniciais com cor estável por nome
// (tons que combinam com o verde petróleo). Grupos sem foto mostram o ícone de pessoas.
import { useEffect, useState } from "react";
import Icon from "./Icon";

const CORES = ["#0F5E66", "#2A7F62", "#3C6E91", "#7A5C99", "#B5654A", "#8A7A2E", "#4F6D7A", "#9C4F6B"];

function iniciais(nome) {
  const partes = (nome || "?").trim().split(/\s+/).filter(Boolean);
  if (!partes.length) return "?";
  const a = partes[0][0] || "";
  const b = partes.length > 1 ? partes[partes.length - 1][0] : "";
  return (a + b).toUpperCase() || "?";
}

export default function Avatar({ nome, size = 40, url, grupo = false }) {
  const [falhou, setFalhou] = useState(false);
  useEffect(() => setFalhou(false), [url]); // link novo: tenta a foto de novo
  let h = 0;
  for (const ch of nome || "") h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  const cor = CORES[h % CORES.length];
  if (url && !falhou) {
    return <img className="avatar avatar-img" src={url} alt="" width={size} height={size} style={{ width: size, height: size }} onError={() => setFalhou(true)} />;
  }
  return (
    <div className="avatar" style={{ width: size, height: size, background: cor, fontSize: size * 0.38 }} aria-hidden="true">
      {grupo ? <Icon name="users" size={size * 0.5} /> : iniciais(nome)}
    </div>
  );
}
