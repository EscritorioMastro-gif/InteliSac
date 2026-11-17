// Contador da lista de conversas: número de não lidas, vermelho quando o cliente espera 1h30
// (sem ninguém abrir a conversa OU sem ninguém responder). Sem não lidas mas sem resposta
// há 1h30, mostra um selo vermelho com o tempo.
import Icon from "./Icon";

// Há quanto tempo (Fila e selo de espera): "agora", "12 min", "2 h 5", "3 d"
export function esperaDesde(iso, agora) {
  if (!iso) return "";
  const min = Math.max(0, Math.floor((agora - new Date(iso).getTime()) / 60000));
  if (min < 1) return "agora";
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h} h${min % 60 ? ` ${min % 60}` : ""}`;
  return `${Math.floor(h / 24)} d`;
}

// 1h30 esperando: fica vermelho
const LIMITE_ESPERA_MS = 90 * 60 * 1000;

export default function ContadorEspera({ c, agora }) {
  const desde = (iso) => (iso ? agora - new Date(iso).getTime() : 0);
  const naoLida = c.unread > 0 ? desde(c.unreadSince) : 0;
  const semResposta = desde(c.waitingSince);
  const vermelho = naoLida >= LIMITE_ESPERA_MS || semResposta >= LIMITE_ESPERA_MS;
  const dicas = [];
  if (c.unread > 0) dicas.push(`${c.unread === 1 ? "1 não lida" : `${c.unread} não lidas`}${c.unreadSince ? ` (a mais antiga há ${esperaDesde(c.unreadSince, agora)})` : ""}`);
  if (c.waitingSince) dicas.push(`sem resposta há ${esperaDesde(c.waitingSince, agora)}`);
  const titulo = dicas.join(" · ") || undefined;
  if (c.unread > 0) {
    return <span className={`badge ${vermelho ? "badge-atrasada" : ""}`} title={titulo}>{c.unread}</span>;
  }
  if (vermelho) {
    // conversa já aberta, mas ninguém respondeu: selo com o tempo de espera
    return (
      <span className="badge badge-atrasada badge-espera" title={titulo}>
        <Icon name="clock" size={11} />{esperaDesde(c.waitingSince, agora)}
      </span>
    );
  }
  return null;
}
