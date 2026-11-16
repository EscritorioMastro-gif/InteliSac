import { createContext, useContext, useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api, getTokens, logout } from "./api";
import { closeSocket, getSocket } from "./socket";
import Icon from "./components/Icon";
import Avatar from "./components/Avatar";
import BrandMark from "./components/BrandMark";
import { ToastProvider, useToast } from "./components/Toast";
import { useAvisos } from "./avisos";
import Login from "./pages/Login";
import Atendimento from "./pages/Atendimento";
import Contatos from "./pages/Contatos";
import Cadastro from "./pages/Cadastro";
import Agora from "./pages/Agora";
import Simulador from "./pages/Simulador";
import Conexoes from "./pages/Conexoes";

const MeContext = createContext(null);
export const useMe = () => useContext(MeContext);

const MENU = [
  { to: "/", label: "Atendimento", icon: "chat", end: true },
  { to: "/agora", label: "Agora", icon: "pulse" },
  { to: "/contatos", label: "Contatos", icon: "contacts" },
  { to: "/respostas", label: "Respostas rápidas", icon: "zap" },
  { to: "/simulador", label: "Simulador", icon: "phone", simulador: true },
  { section: "Configurações", admin: true },
  { to: "/conexoes", label: "Conexões", icon: "plug", admin: true },
  { to: "/usuarios", label: "Usuários", icon: "user", admin: true },
  { to: "/departamentos", label: "Departamentos", icon: "building", admin: true },
  { to: "/assuntos", label: "Assuntos", icon: "list", admin: true },
  { to: "/tags", label: "Tags", icon: "tag", admin: true },
];

const STATUS_LABEL = { online: "Online", away: "Ausente", offline: "Offline" };

function useSocketOnline() {
  const [online, setOnline] = useState(true);
  useEffect(() => {
    const s = getSocket();
    let timer = null;
    const up = () => {
      clearTimeout(timer);
      setOnline(true);
    };
    // Só mostra o aviso se ficar desconectado por mais de 3 s (evita piscar em quedas rápidas)
    const down = () => {
      clearTimeout(timer);
      timer = setTimeout(() => setOnline(false), 3000);
    };
    if (!s.connected) down();
    s.on("connect", up);
    s.on("disconnect", down);
    s.on("connect_error", down);
    return () => {
      clearTimeout(timer);
      s.off("connect", up);
      s.off("disconnect", down);
      s.off("connect_error", down);
    };
  }, []);
  return online;
}

// Administradores: crédito do botão Corrigir (Claude). Atualiza ao entrar, a cada 30 min e na hora
// em que o servidor avisa (saldo acabando, crédito acabou, saldo novo informado).
function useCorretorAdmin(me) {
  const [estado, setEstado] = useState(null);
  const [dispensado, setDispensado] = useState(null);
  const admin = !!me?.isAdmin;
  useEffect(() => {
    if (!admin) return undefined;
    const carregar = () => api("/text/correct/status").then(setEstado).catch(() => {});
    carregar();
    const t = setInterval(carregar, 30 * 60 * 1000);
    const s = getSocket();
    s.on("corretor.updated", setEstado);
    return () => {
      clearInterval(t);
      s.off("corretor.updated", setEstado);
    };
  }, [admin]);
  // "Agora não" esconde o aviso até ele mudar (ex.: de "acabando" para "acabou")
  const alerta = estado?.alert && dispensado !== estado.alert ? estado.alert : null;
  return { estado, alerta, dispensar: () => setDispensado(estado?.alert) };
}

export const dolares = (v) => `US$ ${(Number(v) || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

function Layout() {
  const [me, setMe] = useState(null);
  const [erro, setErro] = useState("");
  const navigate = useNavigate();
  const online = useSocketOnline();
  const toast = useToast();
  const avisos = useAvisos(me);
  const corretor = useCorretorAdmin(me);

  const alternarNotificacao = async () => {
    const r = await avisos.alternarNotificacao();
    if (r === "on") toast.show("Notificações ligadas: você é avisado mesmo com o InteliSac minimizado");
    else if (r === "off") toast.show("Notificações desligadas");
    else if (r === "denied")
      toast.show("O navegador está bloqueando as notificações. Clique no cadeado ao lado do endereço e permita Notificações.", "error");
    else if (r === "unsupported") toast.show("Este navegador não mostra notificações", "error");
  };

  useEffect(() => {
    api("/me")
      .then(async (u) => {
        // Quem entra aparece como online para a equipe
        if (u.status === "offline") u = { ...u, ...(await api("/me/status", { method: "PUT", body: { status: "online" } }).catch(() => ({}))) };
        setMe(u);
      })
      .catch((e) => setErro(e.message));
  }, []);

  const mudarStatus = async (status) => {
    const u = await api("/me/status", { method: "PUT", body: { status } });
    setMe((m) => ({ ...m, status: u.status }));
  };

  const sair = async () => {
    await api("/me/status", { method: "PUT", body: { status: "offline" } }).catch(() => {});
    await logout(); // avisa o servidor: os logins deste usuário deixam de valer
    closeSocket();
    navigate("/login");
  };

  if (erro)
    return (
      <div className="center">
        <div className="error">Não foi possível carregar: {erro}</div>
        <button className="primary" onClick={sair}>Entrar de novo</button>
      </div>
    );
  if (!me) return <div className="center muted">Carregando…</div>;

  return (
    <MeContext.Provider value={me}>
      <div className="shell">
        <aside className="sidebar">
          <div className="brand">
            <BrandMark />
            <span className="brand-name">Inteli<span>Sac</span></span>
          </div>
          <nav>
            {MENU.filter((m) => (!m.admin || me.isAdmin) && (!m.simulador || me.features?.simulator)).map((m) =>
              m.section ? (
                <div key={m.section} className="nav-section">{m.section}</div>
              ) : (
                <NavLink key={m.to} to={m.to} end={m.end} title={m.label}>
                  <Icon name={m.icon} />
                  <span>{m.label}</span>
                </NavLink>
              )
            )}
          </nav>
          <div className="me-avisos">
            <button
              type="button"
              className={avisos.som ? "on" : ""}
              onClick={avisos.alternarSom}
              aria-pressed={avisos.som}
              title={avisos.som ? "Som de mensagem nova ligado (clique para desligar)" : "Som de mensagem nova desligado (clique para ligar)"}
            >
              <Icon name={avisos.som ? "volume" : "volumeOff"} size={16} /><span>Som</span>
            </button>
            <button
              type="button"
              className={avisos.notificacoes ? "on" : ""}
              onClick={alternarNotificacao}
              aria-pressed={avisos.notificacoes}
              title={
                avisos.permissao === "denied"
                  ? "Notificações bloqueadas no navegador"
                  : avisos.notificacoes
                    ? "Notificação na tela ligada (clique para desligar)"
                    : "Notificação na tela desligada (clique para ligar)"
              }
            >
              <Icon name={avisos.notificacoes ? "bell" : "bellOff"} size={16} /><span>Avisos</span>
            </button>
          </div>
          <div className="me-box">
            <Avatar nome={me.name} size={34} />
            <div className="me-info">
              <strong className="ellipsis" title={me.email}>{me.name}</strong>
              <div className="row gap" style={{ gap: 6 }}>
                <span className={`status-dot ${me.status}`} />
                <select value={me.status} onChange={(e) => mudarStatus(e.target.value)} aria-label="Meu status">
                  {Object.entries(STATUS_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </div>
            </div>
            <button className="icon-btn" onClick={sair} title="Sair" aria-label="Sair"><Icon name="logout" /></button>
          </div>
        </aside>
        <main className="content">
          {!online && (
            <div className="conn-banner"><Icon name="wifiOff" size={16} /> Sem conexão em tempo real com o servidor. Tentando reconectar…</div>
          )}
          {avisos.mostrarConvite && (
            <div className="notif-banner">
              <Icon name="bell" size={16} />
              <span className="grow">Quer ser avisado quando chegar mensagem, mesmo com o InteliSac minimizado?</span>
              <button className="primary small-btn" onClick={alternarNotificacao}>Ativar notificações</button>
              <button className="small-btn" onClick={avisos.dispensarConvite}>Agora não</button>
            </div>
          )}
          {corretor.alerta && (
            <div className="conn-banner credit-banner" role="alert">
              <Icon name="wand" size={16} />
              <span className="grow">
                {corretor.alerta === "sem_credito"
                  ? "O crédito da Anthropic acabou: o botão Corrigir está usando o corretor grátis, mais simples."
                  : `O crédito do botão Corrigir (Claude) está acabando: restam cerca de ${dolares(corretor.estado?.estimatedBalanceUsd)}.`}{" "}
                Recarregue na Anthropic e depois informe o saldo novo em Conexões.
              </span>
              <a className="btn-link small-btn" href="https://console.anthropic.com/" target="_blank" rel="noreferrer">Abrir a Anthropic</a>
              <button className="small-btn" onClick={() => navigate("/conexoes")}>Informar saldo</button>
              <button className="small-btn" onClick={corretor.dispensar}>Agora não</button>
            </div>
          )}
          <Routes>
            <Route path="/" element={<Atendimento />} />
            <Route path="/agora" element={<Agora />} />
            <Route path="/contatos" element={<Contatos />} />
            {me.features?.simulator && <Route path="/simulador" element={<Simulador />} />}
            <Route path="/departamentos" element={<Cadastro titulo="Departamentos" subtitulo="Filas de atendimento. Cada atendente vê os chamados dos seus departamentos." path="/departments" campos={[{ name: "name", label: "Nome" }]} arquivar />} />
            <Route path="/assuntos" element={<Cadastro titulo="Assuntos de chamado" subtitulo="Motivos escolhidos ao fechar um chamado, usados nos relatórios." path="/ticket-topics" campos={[{ name: "name", label: "Nome" }]} arquivar />} />
            <Route path="/tags" element={<Cadastro titulo="Tags" subtitulo="Etiquetas para organizar os contatos." path="/tags" campos={[{ name: "label", label: "Nome" }, { name: "color", label: "Cor", type: "color" }]} colunas={[{ name: "label", label: "Nome", render: (v, it) => <span className="tag" style={{ background: it.color }}>{v}</span> }]} />} />
            <Route path="/respostas" element={<Cadastro titulo="Respostas rápidas" subtitulo="No atendimento, digite / e o atalho para inserir o texto." path="/quick-replies" campos={[{ name: "title", label: "Atalho" }, { name: "text", label: "Texto", type: "textarea" }]} colunas={[{ name: "title", label: "Atalho", render: (v) => <strong>/{v}</strong> }, { name: "text", label: "Texto", render: (v) => <span className="muted">{v}</span> }]} />} />
            <Route path="/conexoes" element={<Conexoes />} />
            <Route path="/usuarios" element={<Cadastro titulo="Usuários" subtitulo="Quem acessa o InteliSac. O login usa e-mail e senha do Supabase." path="/users" arquivar campos={[
              { name: "name", label: "Nome" },
              { name: "email", label: "E-mail", type: "email" },
              { name: "password", label: "Senha (mínimo 8 caracteres · ao editar, deixe vazio para manter a atual)", type: "password", skipLoad: true },
              { name: "isAdmin", label: "Administrador (gerencia configurações e vê todos os chamados)", type: "checkbox" },
              { name: "departmentIds", label: "Departamentos que atende", type: "departments" },
            ]} colunas={[
              { name: "name", label: "Nome", render: (v, it) => <span className="row gap"><Avatar nome={v} size={28} />{v}</span> },
              { name: "email", label: "E-mail" },
              { name: "isAdmin", label: "Perfil", render: (v) => (v ? <span className="chip">Administrador</span> : "Atendente") },
              { name: "status", label: "Status", render: (v) => <span className="row gap" style={{ gap: 6 }}><span className={`status-dot ${v}`} />{STATUS_LABEL[v] || v}</span> },
            ]} />} />
            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
        </main>
      </div>
    </MeContext.Provider>
  );
}

// Confere o login a cada mudança de rota (e não só quando a página carrega),
// para entrar direto no sistema logo depois do login.
function RequireAuth({ children }) {
  useLocation();
  return getTokens() ? children : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <ToastProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/*" element={<RequireAuth><Layout /></RequireAuth>} />
      </Routes>
    </ToastProvider>
  );
}
