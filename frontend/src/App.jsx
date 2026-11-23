import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { NavLink, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api, getTokens, logout } from "./api";
import { closeSocket, getSocket } from "./socket";
import Icon from "./components/Icon";
import Avatar from "./components/Avatar";
import BrandMark from "./components/BrandMark";
import CommandPalette from "./components/CommandPalette";
import Atalhos from "./components/Atalhos";
import { ConfirmProvider } from "./components/Confirm";
import { ToastProvider, useToast } from "./components/Toast";
import { useAvisos } from "./avisos";
import { gravarPref, lerPref, menuDo } from "./menu";
import Login from "./pages/Login";
import Atendimento from "./pages/Atendimento";
import Contatos from "./pages/Contatos";
import Cadastro from "./pages/Cadastro";
import Agora from "./pages/Agora";
import Simulador from "./pages/Simulador";
import Conexoes from "./pages/Conexoes";
import ApiModulo from "./pages/ApiModulo";

const MeContext = createContext(null);
export const useMe = () => useContext(MeContext);

export const STATUS_LABEL = { online: "Online", away: "Ausente", offline: "Offline" };
const STATUS_DICA = { online: "Recebendo atendimentos", away: "Volto já", offline: "Fora do atendimento" };
const CHAVE_MENU = "intelisac.menuRecolhido";

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

// Tela estreita: o menu fica só com os ícones
function useMedia(consulta) {
  const [bate, setBate] = useState(() => window.matchMedia?.(consulta).matches ?? false);
  useEffect(() => {
    const mq = window.matchMedia?.(consulta);
    if (!mq) return undefined;
    const mudou = () => setBate(mq.matches);
    mq.addEventListener("change", mudou);
    return () => mq.removeEventListener("change", mudou);
  }, [consulta]);
  return bate;
}

// Números do menu (quantos esperam na fila): atualiza quando um chamado muda
function useResumo(meId) {
  const [r, setR] = useState(null);
  useEffect(() => {
    if (!meId) return undefined;
    const carregar = () => api("/now/resume").then(setR).catch(() => {});
    carregar();
    const s = getSocket();
    let t = null;
    const agendar = () => {
      clearTimeout(t);
      t = setTimeout(carregar, 800);
    };
    const eventos = ["ticket.created", "ticket.updated", "connect"];
    eventos.forEach((e) => s.on(e, agendar));
    return () => {
      clearTimeout(t);
      eventos.forEach((e) => s.off(e, agendar));
    };
  }, [meId]);
  return r;
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

// Cartão do usuário no rodapé do menu: abre o menu com status, atalhos e Sair
function MeCard({ me, onStatus, onSair, onAtalhos }) {
  const [aberto, setAberto] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!aberto) return undefined;
    const fora = (e) => !ref.current?.contains(e.target) && setAberto(false);
    const esc = (e) => e.key === "Escape" && setAberto(false);
    document.addEventListener("mousedown", fora);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", fora);
      document.removeEventListener("keydown", esc);
    };
  }, [aberto]);

  return (
    <div className="me-box" ref={ref}>
      {aberto && (
        <div className="me-menu" role="menu" aria-label="Meu usuário">
          <div className="me-menu-head">
            <strong className="ellipsis">{me.name}</strong>
            <small className="ellipsis">{me.email}</small>
          </div>
          <div className="me-menu-label">Meu status</div>
          {Object.entries(STATUS_LABEL).map(([v, l]) => (
            <button
              key={v}
              type="button"
              role="menuitemradio"
              aria-checked={me.status === v}
              className={me.status === v ? "on" : ""}
              onClick={() => {
                setAberto(false);
                onStatus(v);
              }}
            >
              <span className={`status-dot ${v}`} />
              <span className="grow">{l}<small>{STATUS_DICA[v]}</small></span>
              {me.status === v && <Icon name="check" size={15} />}
            </button>
          ))}
          <hr />
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setAberto(false);
              onAtalhos();
            }}
          >
            <Icon name="keyboard" size={16} /><span className="grow">Atalhos do teclado</span><kbd>?</kbd>
          </button>
          <button type="button" role="menuitem" className="danger" onClick={onSair}>
            <Icon name="logout" size={16} /><span className="grow">Sair</span>
          </button>
        </div>
      )}
      <button
        type="button"
        className={`me-card ${aberto ? "open" : ""}`}
        onClick={() => setAberto((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={aberto}
        title={`${me.name} · ${STATUS_LABEL[me.status] || me.status}`}
      >
        <span className="me-avatar">
          <Avatar nome={me.name} size={34} />
          <span className={`status-dot ${me.status}`} />
        </span>
        <span className="me-info">
          <strong className="ellipsis">{me.name}</strong>
          <small>{STATUS_LABEL[me.status] || me.status}</small>
        </span>
        <Icon name="chevronUp" size={16} className="me-chevron" />
      </button>
    </div>
  );
}

function Layout() {
  const [me, setMe] = useState(null);
  const [erro, setErro] = useState("");
  const [recolhido, setRecolhido] = useState(() => lerPref(CHAVE_MENU));
  const [paleta, setPaleta] = useState(false);
  const [atalhos, setAtalhos] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const online = useSocketOnline();
  const toast = useToast();
  const avisos = useAvisos(me);
  const corretor = useCorretorAdmin(me);
  const resumo = useResumo(me?.id);
  const estreito = useMedia("(max-width: 1100px)");

  const alternarNotificacao = useCallback(async () => {
    const r = await avisos.alternarNotificacao();
    if (r === "on") toast.show("Notificações ligadas: você é avisado mesmo com o InteliSac minimizado");
    else if (r === "off") toast.show("Notificações desligadas", "info");
    else if (r === "denied")
      toast.show("O navegador está bloqueando as notificações. Clique no cadeado ao lado do endereço e permita Notificações.", "error");
    else if (r === "unsupported") toast.show("Este navegador não mostra notificações", "error");
  }, [avisos, toast]);

  const alternarSom = useCallback(() => {
    toast.show(avisos.som ? "Som de mensagem nova desligado" : "Som de mensagem nova ligado", "info");
    avisos.alternarSom();
  }, [avisos, toast]);

  const alternarMenu = useCallback(() => {
    setRecolhido((v) => {
      gravarPref(CHAVE_MENU, !v);
      return !v;
    });
  }, []);

  useEffect(() => {
    api("/me")
      .then(async (u) => {
        // Quem entra aparece como online para a equipe
        if (u.status === "offline") u = { ...u, ...(await api("/me/status", { method: "PUT", body: { status: "online" } }).catch(() => ({}))) };
        setMe(u);
      })
      .catch((e) => setErro(e.message));
  }, []);

  // Ctrl+K abre a busca rápida; "?" (fora de um campo de texto) mostra os atalhos
  useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaleta((v) => !v);
        return;
      }
      const digitando = e.target.closest?.("input, textarea, select, [contenteditable='true']");
      if (e.key === "?" && !digitando && !e.ctrlKey && !e.metaKey && !e.altKey && !document.querySelector(".modal, .cmd")) {
        e.preventDefault();
        setAtalhos(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const mudarStatus = useCallback(
    async (status) => {
      try {
        const u = await api("/me/status", { method: "PUT", body: { status } });
        setMe((m) => ({ ...m, status: u.status }));
        toast.show(`Seu status agora é ${STATUS_LABEL[u.status] || u.status}`, "info");
      } catch (e) {
        toast.show(e.message, "error");
      }
    },
    [toast]
  );

  const sair = useCallback(async () => {
    await api("/me/status", { method: "PUT", body: { status: "offline" } }).catch(() => {});
    await logout(); // avisa o servidor: os logins deste usuário deixam de valer
    closeSocket();
    navigate("/login");
  }, [navigate]);

  const menu = useMemo(() => menuDo(me), [me]);
  const acoes = useMemo(() => {
    if (!me) return [];
    return [
      ...Object.entries(STATUS_LABEL)
        .filter(([v]) => v !== me.status)
        .map(([v, l]) => ({ id: `st-${v}`, icone: "user", rotulo: `Mudar meu status para ${l}`, dica: STATUS_DICA[v], run: () => mudarStatus(v) })),
      { id: "som", icone: avisos.som ? "volumeOff" : "volume", rotulo: avisos.som ? "Desligar o som de mensagem nova" : "Ligar o som de mensagem nova", run: alternarSom },
      { id: "notif", icone: avisos.notificacoes ? "bellOff" : "bell", rotulo: avisos.notificacoes ? "Desligar as notificações" : "Ligar as notificações", dica: "Aviso do Windows quando chega mensagem", run: alternarNotificacao },
      { id: "menu", icone: "sidebar", rotulo: recolhido ? "Expandir o menu lateral" : "Recolher o menu lateral", run: alternarMenu },
      { id: "atalhos", icone: "keyboard", rotulo: "Ver os atalhos do teclado", run: () => setAtalhos(true) },
      { id: "sair", icone: "logout", rotulo: "Sair do InteliSac", run: sair },
    ];
  }, [me, avisos.som, avisos.notificacoes, recolhido, mudarStatus, alternarSom, alternarNotificacao, alternarMenu, sair]);

  if (erro)
    return (
      <div className="center">
        <div className="error">Não foi possível carregar: {erro}</div>
        <button className="primary" onClick={sair}>Entrar de novo</button>
      </div>
    );
  if (!me)
    return (
      <div className="center boot">
        <BrandMark size={46} />
        <span className="boot-bar" />
        <span className="muted">Carregando o InteliSac…</span>
      </div>
    );

  const fila = resumo?.queueTickets || 0;

  return (
    <MeContext.Provider value={me}>
      <div className={`shell ${recolhido || estreito ? "menu-recolhido" : ""}`}>
        <aside className="sidebar">
          <div className="side-top">
            <div className="brand">
              <BrandMark />
              <span className="brand-name">Inteli<span>Sac</span></span>
            </div>
            <button
              type="button"
              className="icon-btn side-toggle"
              onClick={alternarMenu}
              title={recolhido ? "Expandir menu" : "Recolher menu"}
              aria-label={recolhido ? "Expandir menu" : "Recolher menu"}
              aria-pressed={recolhido}
            >
              <Icon name="sidebar" size={18} />
            </button>
          </div>

          <button type="button" className="side-search" onClick={() => setPaleta(true)} title="Busca rápida: telas, conversas e ações (Ctrl+K)">
            <Icon name="search" size={16} />
            <span className="side-search-label">Buscar…</span>
            <kbd>Ctrl K</kbd>
          </button>

          <nav aria-label="Menu principal">
            {menu.map((m) =>
              m.section ? (
                <div key={m.section} className="nav-section">{m.section}</div>
              ) : (
                <NavLink key={m.to} to={m.to} end={m.end} title={m.label}>
                  <span className="nav-ico">
                    <Icon name={m.icon} />
                    {m.badge === "fila" && fila > 0 && <span className="nav-dot" aria-hidden="true" />}
                  </span>
                  <span className="nav-label">{m.label}</span>
                  {m.badge === "fila" && fila > 0 && (
                    <span className="nav-badge" title={fila === 1 ? "1 cliente esperando na fila" : `${fila} clientes esperando na fila`}>{fila}</span>
                  )}
                </NavLink>
              )
            )}
          </nav>

          <div className="side-foot">
            <div className="me-avisos">
              <button
                type="button"
                className={avisos.som ? "on" : ""}
                onClick={alternarSom}
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
            <MeCard me={me} onStatus={mudarStatus} onSair={sair} onAtalhos={() => setAtalhos(true)} />
          </div>
        </aside>

        <main className="content">
          {!online && (
            <div className="conn-banner" role="status">
              <span className="conn-pulse" aria-hidden="true" />
              <Icon name="wifiOff" size={16} /> Sem conexão em tempo real com o servidor. Tentando reconectar…
            </div>
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
          {/* a chave pela rota recomeça a tela (ex.: de Tags para Assuntos, que usam o mesmo cadastro) */}
          <div className="route" key={location.pathname}>
            <Routes>
              <Route path="/" element={<Atendimento />} />
              <Route path="/agora" element={<Agora />} />
              <Route path="/contatos" element={<Contatos />} />
              {me.features?.simulator && <Route path="/simulador" element={<Simulador />} />}
              <Route path="/departamentos" element={<Cadastro icone="building" secao="Configurações" titulo="Departamentos" item="departamento" subtitulo="Filas de atendimento. Cada atendente vê os chamados dos seus departamentos." path="/departments" campos={[{ name: "name", label: "Nome", placeholder: "Ex.: Fiscal, Departamento Pessoal" }]} arquivar />} />
              <Route path="/assuntos" element={<Cadastro icone="list" secao="Configurações" titulo="Assuntos de chamado" item="assunto" subtitulo="Motivos escolhidos ao fechar um chamado, usados nos relatórios." path="/ticket-topics" campos={[{ name: "name", label: "Nome", placeholder: "Ex.: Guia de imposto, 2ª via de boleto" }]} arquivar />} />
              <Route path="/tags" element={<Cadastro icone="tag" secao="Configurações" titulo="Tags" item="tag" feminino subtitulo="Etiquetas para organizar os contatos." path="/tags" campos={[{ name: "label", label: "Nome", placeholder: "Ex.: Cliente VIP" }, { name: "color", label: "Cor", type: "color" }]} colunas={[{ name: "label", label: "Nome", render: (v, it) => <span className="tag" style={{ background: it.color }}>{v}</span> }]} />} />
              <Route path="/respostas" element={<Cadastro icone="zap" secao="Dia a dia" titulo="Respostas rápidas" item="resposta rápida" feminino subtitulo="No atendimento, digite / e o atalho para inserir o texto." path="/quick-replies" campos={[{ name: "title", label: "Atalho", placeholder: "Ex.: bomdia", dica: "No campo de mensagem, digite /bomdia para usar este texto." }, { name: "text", label: "Texto", type: "textarea", placeholder: "Bom dia! Como posso ajudar?" }]} colunas={[{ name: "title", label: "Atalho", render: (v) => <code className="shortcut">/{v}</code> }, { name: "text", label: "Texto", render: (v) => <span className="muted clamp-2">{v}</span> }]} />} />
              <Route path="/conexoes" element={<Conexoes />} />
              {me.isAdmin && <Route path="/api" element={<ApiModulo />} />}
              <Route path="/usuarios" element={<Cadastro icone="user" secao="Configurações" titulo="Usuários" item="usuário" subtitulo="Quem acessa o InteliSac. O login usa e-mail e senha do Supabase." path="/users" arquivar campos={[
                { name: "name", label: "Nome", placeholder: "Nome e sobrenome" },
                { name: "email", label: "E-mail", type: "email", placeholder: "nome@empresa.com.br" },
                { name: "password", label: "Senha", type: "password", skipLoad: true, dica: "Mínimo de 8 caracteres. Ao editar, deixe vazio para manter a senha atual." },
                { name: "isAdmin", label: "Administrador", type: "checkbox", dica: "Gerencia as configurações e vê todos os chamados." },
                { name: "departmentIds", label: "Departamentos que atende", type: "departments" },
              ]} colunas={[
                { name: "name", label: "Nome", render: (v, it) => <span className="row gap"><Avatar nome={v} size={30} /><span><strong>{v}</strong></span></span> },
                { name: "email", label: "E-mail", render: (v) => <span className="muted">{v}</span> },
                { name: "isAdmin", label: "Perfil", render: (v) => (v ? <span className="chip">Administrador</span> : <span className="chip chip-soft">Atendente</span>) },
                { name: "status", label: "Status", render: (v) => <span className="row gap" style={{ gap: 7 }}><span className={`status-dot ${v}`} />{STATUS_LABEL[v] || v}</span> },
              ]} />} />
              <Route path="*" element={<Navigate to="/" />} />
            </Routes>
          </div>
        </main>
      </div>
      {paleta && <CommandPalette paginas={menu.filter((m) => !m.section)} acoes={acoes} onFechar={() => setPaleta(false)} />}
      {atalhos && <Atalhos onClose={() => setAtalhos(false)} />}
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
      <ConfirmProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/*" element={<RequireAuth><Layout /></RequireAuth>} />
        </Routes>
      </ConfirmProvider>
    </ToastProvider>
  );
}
