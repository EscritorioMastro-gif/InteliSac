import { useEffect, useState } from "react";
import { api } from "../api";
import { getSocket } from "../socket";
import Icon from "../components/Icon";
import Avatar from "../components/Avatar";

const STATUS = { online: "Online", away: "Ausente", offline: "Offline" };

export default function Agora() {
  const [r, setR] = useState(null);

  useEffect(() => {
    const carregar = () => api("/now/resume").then(setR);
    carregar();
    const s = getSocket();
    let t = null;
    const agendar = () => {
      clearTimeout(t);
      t = setTimeout(carregar, 400);
    };
    ["ticket.created", "ticket.updated", "user.updated"].forEach((e) => s.on(e, agendar));
    return () => {
      ["ticket.created", "ticket.updated", "user.updated"].forEach((e) => s.off(e, agendar));
      clearTimeout(t);
    };
  }, []);

  if (!r) return <div className="center muted">Carregando…</div>;

  return (
    <div className="page">
      <div className="page-head"><h2>Agora</h2><span className="chip"><span className="status-dot online" />Atualiza em tempo real</span></div>
      <p className="page-sub">O que está acontecendo no atendimento neste momento.</p>
      <div className="cards">
        <div className="card"><span><Icon name="chat" size={16} />Chamados abertos</span><strong>{r.openTickets}</strong></div>
        <div className="card"><span><Icon name="clock" size={16} />Na fila (sem atendente)</span><strong>{r.queueTickets}</strong></div>
        <div className="card"><span><Icon name="user" size={16} />Meus chamados</span><strong>{r.myTickets}</strong></div>
        <div className="card"><span><Icon name="check" size={16} />Fechados hoje</span><strong>{r.closedToday}</strong></div>
      </div>
      <div className="two-cols">
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Departamento</th><th className="right">Abertos</th></tr></thead>
            <tbody>{r.departments.map((d) => <tr key={d.id}><td>{d.name}</td><td className="right"><strong>{d.open}</strong></td></tr>)}</tbody>
          </table>
        </div>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Atendente</th><th>Status</th><th className="right">Abertos</th></tr></thead>
            <tbody>
              {r.users.map((u) => (
                <tr key={u.id}>
                  <td><span className="row gap"><Avatar nome={u.name} size={26} />{u.name}</span></td>
                  <td><span className="row gap" style={{ gap: 6 }}><span className={`status-dot ${u.status}`} />{STATUS[u.status] || u.status}</span></td>
                  <td className="right"><strong>{u.open}</strong></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
