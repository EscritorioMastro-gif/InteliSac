import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { getSocket } from "../socket";
import Icon from "../components/Icon";
import Avatar from "../components/Avatar";
import PageHead from "../components/PageHead";

const STATUS = { online: "Online", away: "Ausente", offline: "Offline" };
const ORDEM_STATUS = { online: 0, away: 1, offline: 2 };

export default function Agora() {
  const [r, setR] = useState(null);
  const [atualizado, setAtualizado] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    const carregar = () =>
      api("/now/resume").then((x) => {
        setR(x);
        setAtualizado(new Date());
      });
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

  const cabecalho = (
    <PageHead icone="pulse" secao="Dia a dia" titulo="Agora" subtitulo="O que está acontecendo no atendimento neste momento.">
      <span className="live-pill" title={atualizado ? `Atualizado às ${atualizado.toLocaleTimeString("pt-BR")}` : undefined}>
        <span className="status-dot online" />Ao vivo
      </span>
    </PageHead>
  );

  if (!r)
    return (
      <div className="page">
        {cabecalho}
        <div className="cards">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="card"><span className="sk sk-line" style={{ width: "60%" }} /><span className="sk" style={{ height: 34, width: "35%" }} /></div>
          ))}
        </div>
      </div>
    );

  const maxDep = Math.max(1, ...r.departments.map((d) => d.open));
  const maxUser = Math.max(1, ...r.users.map((u) => u.open));
  const usuarios = [...r.users].sort((a, b) => (ORDEM_STATUS[a.status] ?? 3) - (ORDEM_STATUS[b.status] ?? 3) || b.open - a.open);
  const online = r.users.filter((u) => u.status === "online").length;

  return (
    <div className="page">
      {cabecalho}
      <div className="cards">
        <div className="card destaque">
          <span><span className="card-ico"><Icon name="chat" size={17} /></span>Chamados abertos</span>
          <strong>{r.openTickets}</strong>
          <small>{online === 1 ? "1 atendente online" : `${online} atendentes online`}</small>
        </div>
        <button type="button" className={`card card-btn ${r.queueTickets > 0 ? "warn" : ""}`} onClick={() => navigate("/")} title="Abrir o Atendimento">
          <span><span className="card-ico"><Icon name="clock" size={17} /></span>Na fila, sem atendente</span>
          <strong>{r.queueTickets}</strong>
          <small>{r.queueTickets > 0 ? "Clientes esperando: veja a aba Fila" : "Ninguém esperando"}</small>
        </button>
        <div className="card">
          <span><span className="card-ico"><Icon name="user" size={17} /></span>Meus chamados</span>
          <strong>{r.myTickets}</strong>
          <small>Com você agora</small>
        </div>
        <div className="card ok">
          <span><span className="card-ico"><Icon name="check" size={17} /></span>Fechados hoje</span>
          <strong>{r.closedToday}</strong>
          <small>Desde a meia-noite</small>
        </div>
      </div>
      <div className="two-cols">
        <section className="panel">
          <div className="panel-head"><Icon name="building" size={18} /><h3>Por departamento</h3><span className="muted small">abertos</span></div>
          <ul className="bars">
            {r.departments.length === 0 && <li className="muted">Nenhum departamento cadastrado.</li>}
            {r.departments.map((d) => (
              <li key={d.id}>
                <span className="bar-name"><span className="ellipsis">{d.name}</span></span>
                <span className="bar-num">{d.open}</span>
                <span className="bar-track"><span className="bar-fill" style={{ width: `${(d.open / maxDep) * 100}%` }} /></span>
              </li>
            ))}
          </ul>
        </section>
        <section className="panel">
          <div className="panel-head"><Icon name="users" size={18} /><h3>Equipe</h3><span className="muted small">abertos</span></div>
          <ul className="bars">
            {usuarios.map((u) => (
              <li key={u.id}>
                <span className="bar-name">
                  <span className="me-avatar"><Avatar nome={u.name} size={30} /><span className={`status-dot ${u.status}`} /></span>
                  <span style={{ minWidth: 0 }}>
                    <span className="ellipsis" style={{ display: "block" }}>{u.name}</span>
                    <span className="bar-status">{STATUS[u.status] || u.status}</span>
                  </span>
                </span>
                <span className="bar-num">{u.open}</span>
                <span className="bar-track"><span className="bar-fill" style={{ width: `${(u.open / maxUser) * 100}%` }} /></span>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
