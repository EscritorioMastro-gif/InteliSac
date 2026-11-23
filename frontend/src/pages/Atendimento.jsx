import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, apiForm } from "../api";
import { getSocket } from "../socket";
import { useMe } from "../App";
import Modal from "../components/Modal";
import Icon from "../components/Icon";
import Avatar from "../components/Avatar";
import Tiques from "../components/Tiques";
import Midia, { MAX_ARQUIVO, MAX_ARQUIVO_MB, fmtBytes } from "../components/Midia";
import ContadorEspera, { esperaDesde } from "../components/ContadorEspera";
import PreviaConversa from "../components/PreviaConversa";
import EmojiPicker from "../components/EmojiPicker";
import TextoComLinks from "../components/TextoComLinks";
import { useToast } from "../components/Toast";
import { useConfirm } from "../components/Confirm";
import { corDoTexto, fmtNumero } from "../formato";

const ABAS = [
  { id: "mine", label: "Meus", count: "myTickets" },
  { id: "queue", label: "Fila", count: "queueTickets" },
  { id: "open", label: "Abertos", count: "openTickets" },
  { id: "all", label: "Todos" },
];

const VAZIO = {
  mine: "Nenhuma conversa com você agora. Veja a aba Fila para assumir um atendimento.",
  queue: "Nenhum cliente esperando atendimento.",
  open: "Nenhum chamado aberto no momento.",
  all: "Nenhum contato encontrado.",
};

const TITULO_VAZIO = { mine: "Tudo em dia", queue: "Fila vazia", open: "Nada aberto", all: "Nenhum contato" };

const hora = (iso) => (iso ? new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }) : "");

function diaDe(iso) {
  const d = new Date(iso);
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

function rotuloDia(iso) {
  const hoje = diaDe(new Date().toISOString());
  const dias = Math.round((hoje - diaDe(iso)) / 86400000);
  if (dias === 0) return "Hoje";
  if (dias === 1) return "Ontem";
  return new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "long", year: dias > 300 ? "numeric" : undefined });
}

function quandoCurto(iso) {
  if (!iso) return "";
  const dias = Math.round((diaDe(new Date().toISOString()) - diaDe(iso)) / 86400000);
  if (dias === 0) return hora(iso);
  if (dias === 1) return "Ontem";
  return new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
}

// Avisos internos do WhatsApp (chegavam quando alguém editava ou apagava uma mensagem):
// os que já ficaram gravados não aparecem na conversa nem na lista
const AVISOS_INTERNOS = new Set(["[secretEncryptedMessage]", "[encEventResponseMessage]", "[encCommentMessage]", "[pinInChatMessage]"]);
const ehAvisoInterno = (texto) => AVISOS_INTERNOS.has((texto || "").trim());

// ?contact= da página: só aceita um código de contato (um link com outro texto não monta outro endereço da API)
const ID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function idDaUrl(params) {
  const v = params.get("contact");
  return v && ID_RE.test(v) ? v : null;
}

// Cor estável por pessoa, para diferenciar quem fala num grupo
const CORES_GRUPO = ["#0f5e66", "#2a7f62", "#3c6e91", "#7a5c99", "#b5654a", "#8a7a2e", "#9c4f6b", "#4f6d7a"];
function corDe(chave) {
  let h = 0;
  for (const ch of chave || "") h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return CORES_GRUPO[h % CORES_GRUPO.length];
}

// Tags do contato em miniatura (na lista mostra até `max` e "+N")
function TagsMini({ ids, tags, max = 2 }) {
  const lista = (ids || []).map((id) => tags.find((t) => t.id === id)).filter(Boolean);
  if (!lista.length) return null;
  const visiveis = lista.slice(0, max);
  return (
    <span className="tags-mini" title={lista.map((t) => t.label).join(", ")}>
      {visiveis.map((t) => (
        <span key={t.id} className="tag-mini" style={{ background: t.color, color: corDoTexto(t.color) }}>{t.label}</span>
      ))}
      {lista.length > max && <span className="tag-mini mais">+{lista.length - max}</span>}
    </span>
  );
}


// O WhatsApp só deixa editar até 15 minutos depois do envio
const LIMITE_EDICAO_MS = 15 * 60 * 1000;

// Mouse parado este tempo num contato da lista: abre a prévia da conversa
const ESPERA_PREVIA_MS = 1500;

const primeiroNome = (nome) => String(nome || "").trim().split(/\s+/)[0] || "";

export default function Atendimento() {
  const me = useMe();
  const toast = useToast();
  const confirmar = useConfirm();
  const [params, setParams] = useSearchParams();
  const [aba, setAba] = useState("mine");
  const [busca, setBusca] = useState("");
  const [contatos, setContatos] = useState([]);
  const [contagens, setContagens] = useState({});
  const [carregandoLista, setCarregandoLista] = useState(true);
  const [selId, setSelId] = useState(() => idDaUrl(params));
  const [contato, setContato] = useState(null);
  const [mensagens, setMensagens] = useState([]);
  const [texto, setTexto] = useState("");
  const [sugIdx, setSugIdx] = useState(0);
  const [enviando, setEnviando] = useState(false);
  const [deps, setDeps] = useState([]);
  const [usuarios, setUsuarios] = useState([]);
  const [assuntos, setAssuntos] = useState([]);
  const [respostas, setRespostas] = useState([]);
  const [modal, setModal] = useState(null);
  const [anexos, setAnexos] = useState([]);
  const [arrastando, setArrastando] = useState(false);
  const [imagemAberta, setImagemAberta] = useState(null);
  const [pdfAberto, setPdfAberto] = useState(null);
  const mensagensEm = useRef(0);
  const [respondendo, setRespondendo] = useState(null);
  const [editando, setEditando] = useState(null);
  const [rascunho, setRascunho] = useState("");
  const [selecionadas, setSelecionadas] = useState(null); // encaminhar: ids marcados (null = fora do modo seleção)
  const [tags, setTags] = useState([]);
  const [correcao, setCorrecao] = useState(null); // { antes, depois, n }
  const [corrigindo, setCorrigindo] = useState(false);
  const [agora, setAgora] = useState(() => Date.now());
  const [destaque, setDestaque] = useState(null);
  const [gravando, setGravando] = useState(false);
  const [tempoGravacao, setTempoGravacao] = useState(0);
  const [enviandoAudio, setEnviandoAudio] = useState(false);
  const [emojiAberto, setEmojiAberto] = useState(false);
  const [menuContato, setMenuContato] = useState(null); // clique direito na lista: { contato, x, y }
  const [previa, setPrevia] = useState(null); // prévia ao passar o mouse: { contato, ancora }
  const previaRef = useRef(null);
  previaRef.current = previa;
  const previaAbrir = useRef(null);
  const previaFechar = useRef(null);
  const gravacaoRef = useRef(null);
  const arquivoRef = useRef(null);
  const fimRef = useRef(null);
  const textoRef = useRef(null);
  const selRef = useRef(selId);
  selRef.current = selId;
  const contatoDaUrl = idDaUrl(params);
  // rolagem da conversa: só desce sozinha se você já estava no fim (senão aparece "↓ N novas")
  const listaMsgRef = useRef(null);
  const noFimRef = useRef(true);
  const pularProFimRef = useRef(true);
  const [longeDoFim, setLongeDoFim] = useState(false);
  const [novasAbaixo, setNovasAbaixo] = useState(0);
  // rascunho por conversa: o que você escreveu numa conversa não vai junto para a outra
  const rascunhosRef = useRef(new Map());
  const selAnteriorRef = useRef(selId);
  const estadoRef = useRef({});
  estadoRef.current = { texto, editando, rascunho };
  const contatosRef = useRef([]);
  contatosRef.current = contatos;
  const contatoRef = useRef(null);
  contatoRef.current = contato;
  const mostrandoConversa = !!contato && contato.id === selId;

  // Clique na notificação muda o ?contact= da página: abre essa conversa
  useEffect(() => {
    if (contatoDaUrl !== selRef.current) setSelId(contatoDaUrl);
  }, [contatoDaUrl]);

  const carregarLista = useCallback(() => {
    api("/contacts", { params: { filter: aba, q: busca || undefined, perPage: 100 } })
      .then((r) => setContatos(r.data))
      .catch((e) => toast.show(e.message, "error"))
      .finally(() => setCarregandoLista(false));
    api("/now/resume").then(setContagens).catch(() => {});
  }, [aba, busca, toast]);

  const carregarConversa = useCallback((id) => {
    if (!id) return;
    // clicou em outra conversa antes de esta carregar: a resposta atrasada é ignorada
    api(`/contacts/${id}`)
      .then((c) => id === selRef.current && setContato(c))
      .catch((e) => {
        toast.show(e.message, "error");
        if (id === selRef.current && contatoRef.current?.id !== id) setSelId(null);
      });
    api("/messages", { params: { contactId: id, perPage: 100 } }).then((r) => {
      if (id !== selRef.current) return;
      mensagensEm.current = Date.now();
      setMensagens(r.data);
    });
  }, [toast]);

  // O link do arquivo vale 1 h: se a conversa está aberta há mais tempo, pega um link novo antes de mostrar
  const abrirPdf = useCallback((m) => {
    if (Date.now() - mensagensEm.current < 50 * 60 * 1000) {
      setPdfAberto(m);
      return;
    }
    api("/messages", { params: { contactId: m.contactId, perPage: 100 } })
      .then((r) => {
        mensagensEm.current = Date.now();
        setMensagens(r.data);
        setPdfAberto(r.data.find((x) => x.id === m.id) || m);
      })
      .catch((e) => toast.show(e.message, "error"));
  }, [toast]);

  useEffect(() => {
    const t = setTimeout(carregarLista, 200);
    return () => clearTimeout(t);
  }, [carregarLista]);

  const carregarTags = useCallback(() => {
    api("/tags", { params: { perPage: 200 } }).then((r) => setTags(r.data)).catch(() => {});
  }, []);

  useEffect(() => {
    Promise.all([
      api("/departments", { params: { perPage: 200 } }),
      api("/users", { params: { perPage: 200 } }),
      api("/ticket-topics", { params: { perPage: 200 } }),
      api("/quick-replies", { params: { perPage: 200 } }),
    ]).then(([d, u, t, q]) => {
      setDeps(d.data);
      setUsuarios(u.data);
      setAssuntos(t.data);
      setRespostas(q.data);
    });
    carregarTags();
    // tag criada, renomeada ou apagada em outra tela: atualiza aqui
    const s = getSocket();
    ["tag.created", "tag.updated", "tag.destroyed"].forEach((ev) => s.on(ev, carregarTags));
    return () => ["tag.created", "tag.updated", "tag.destroyed"].forEach((ev) => s.off(ev, carregarTags));
  }, [carregarTags]);

  // O relógio da lista anda sozinho: "espera X min" da Fila e o contador vermelho depois de 1h30
  useEffect(() => {
    setAgora(Date.now());
    const t = setInterval(() => setAgora(Date.now()), 30000);
    return () => clearInterval(t);
  }, [aba]);

  useEffect(() => {
    const anterior = selAnteriorRef.current;
    if (anterior !== selId) {
      const st = estadoRef.current;
      const escrito = (st.editando ? st.rascunho : st.texto) || "";
      if (anterior) {
        if (escrito.trim()) rascunhosRef.current.set(anterior, escrito);
        else rascunhosRef.current.delete(anterior);
      }
      setTexto(selId ? rascunhosRef.current.get(selId) || "" : "");
      setRascunho("");
      selAnteriorRef.current = selId;
    }
    setRespondendo(null);
    setEditando(null);
    setSelecionadas(null);
    setCorrecao(null);
    setEmojiAberto(false);
    setNovasAbaixo(0);
    setLongeDoFim(false);
    noFimRef.current = true;
    pularProFimRef.current = true;
    if (!selId) {
      setContato(null);
      setMensagens([]);
      return;
    }
    setMensagens([]);
    carregarConversa(selId);
    api(`/contacts/${selId}/mark-read`, { method: "POST" }).catch(() => {});
  }, [selId, carregarConversa]);

  // Tempo real
  useEffect(() => {
    const s = getSocket();
    let t = null;
    const recarregar = () => {
      clearTimeout(t);
      t = setTimeout(carregarLista, 300);
    };
    const onMsg = (m) => {
      if (m.contactId === selRef.current) {
        setMensagens((prev) => (prev.some((x) => x.id === m.id) ? prev : [...prev, m]));
        if (!m.isFromMe) api(`/contacts/${m.contactId}/mark-read`, { method: "POST" }).catch(() => {});
      }
      recarregar();
    };
    const onTicket = (tk) => {
      if (tk.contactId === selRef.current) api(`/contacts/${tk.contactId}`).then((c) => c.id === selRef.current && setContato(c));
      recarregar();
    };
    // Mensagem alterada (ex.: apagada pelo cliente ou por um colega): troca na conversa aberta
    const onMsgAtualizada = (m) => {
      if (m.contactId !== selRef.current) return;
      setMensagens((prev) =>
        prev.map((x) => {
          if (x.id !== m.id) return x;
          // Mesmo arquivo: mantém o link já carregado (a imagem não pisca a cada ✓ que chega)
          const mesmoArquivo = x.fileUrl && x.data?.file?.path && x.data.file.path === m.data?.file?.path;
          return mesmoArquivo ? { ...m, fileUrl: x.fileUrl, downloadUrl: x.downloadUrl } : m;
        })
      );
    };
    s.on("message.created", onMsg);
    s.on("message.updated", onMsgAtualizada);
    s.on("ticket.created", onTicket);
    s.on("ticket.updated", onTicket);
    s.on("contact.updated", recarregar);
    s.on("contact.created", recarregar);
    return () => {
      s.off("message.created", onMsg);
      s.off("message.updated", onMsgAtualizada);
      s.off("ticket.created", onTicket);
      s.off("ticket.updated", onTicket);
      s.off("contact.updated", recarregar);
      s.off("contact.created", recarregar);
      clearTimeout(t);
    };
  }, [carregarLista]);

  // Desce até a última mensagem quando a conversa abre ou chega mensagem nova (não quando uma é só
  // alterada). Se você está lendo mais acima, não pula: o botão "↓" mostra quantas chegaram.
  const descer = (suave = false) => {
    const el = listaMsgRef.current;
    if (!el) return;
    if (suave) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    else el.scrollTop = el.scrollHeight;
  };
  const ultima = mensagens[mensagens.length - 1];
  const ultimaId = ultima?.id;
  const ultimaEhMinha = !!ultima?.isFromMe && ultima?.userId === me.id;
  const ultimaEhEvento = ultima?.type === "ticket";
  useEffect(() => {
    if (!ultimaId || !mostrandoConversa) return;
    if (pularProFimRef.current || noFimRef.current || ultimaEhMinha) {
      pularProFimRef.current = false;
      noFimRef.current = true;
      descer();
      setNovasAbaixo(0);
    } else if (!ultimaEhEvento) {
      setNovasAbaixo((n) => n + 1);
    }
  }, [ultimaId, mostrandoConversa]); // eslint-disable-line react-hooks/exhaustive-deps

  // Foto ou vídeo que termina de carregar muda a altura: continua no fim se você estava lá
  useEffect(() => {
    const el = listaMsgRef.current;
    if (!el) return undefined;
    const carregou = () => noFimRef.current && descer();
    el.addEventListener("load", carregou, true);
    el.addEventListener("loadedmetadata", carregou, true);
    return () => {
      el.removeEventListener("load", carregou, true);
      el.removeEventListener("loadedmetadata", carregou, true);
    };
  }, [mostrandoConversa]);

  const aoRolar = (e) => {
    const el = e.currentTarget;
    const perto = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
    noFimRef.current = perto;
    setLongeDoFim(!perto);
    if (perto) setNovasAbaixo(0);
  };

  // Contador da gravação de áudio
  useEffect(() => {
    if (!gravando) return undefined;
    const t = setInterval(() => {
      const g = gravacaoRef.current;
      if (!g) return;
      const s = Math.floor((Date.now() - g.inicio) / 1000);
      setTempoGravacao(s);
      if (s >= 600) enviarGravacaoRef.current?.(); // limite de 10 minutos: envia o que gravou
    }, 250);
    return () => clearInterval(t);
  }, [gravando]);

  // Trocar de conversa ou sair da tela descarta uma gravação em andamento
  useEffect(() => () => descartarGravacao(), [selId]);

  // Campo de texto cresce conforme o conteúdo
  useEffect(() => {
    const el = textoRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [texto]);

  const selecionar = (id) => {
    setSelId(id);
    setParams(id ? { contact: id } : {});
  };
  const selecionarRef = useRef(selecionar);
  selecionarRef.current = selecionar;

  // Alt+↑ / Alt+↓: conversa de cima / de baixo na lista, sem tirar a mão do teclado
  useEffect(() => {
    const onKey = (e) => {
      if (!e.altKey || e.ctrlKey || e.metaKey || (e.key !== "ArrowDown" && e.key !== "ArrowUp")) return;
      if (document.querySelector(".modal, .cmd")) return;
      const lista = contatosRef.current;
      if (!lista.length) return;
      e.preventDefault();
      const i = lista.findIndex((c) => c.id === selRef.current);
      const j = i < 0 ? 0 : e.key === "ArrowDown" ? Math.min(i + 1, lista.length - 1) : Math.max(i - 1, 0);
      if (lista[j].id !== selRef.current) selecionarRef.current(lista[j].id);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // a conversa aberta fica visível na lista (ex.: depois de Alt+↓)
  useEffect(() => {
    if (selId) document.querySelector(".chat-list li.sel")?.scrollIntoView({ block: "nearest" });
  }, [selId]);

  const trocarAba = (id) => {
    if (id === aba) return;
    setCarregandoLista(true);
    setContatos([]);
    setAba(id);
  };

  // Marcar como não lida (igual ao WhatsApp): se a conversa está aberta, sai dela,
  // senão a tela já marcaria como lida de novo
  const marcarNaoLida = async (c) => {
    setMenuContato(null);
    try {
      await api(`/contacts/${c.id}/mark-unread`, { method: "POST" });
      if (c.id === selRef.current) selecionar(null);
      carregarLista();
      toast.show("Conversa marcada como não lida");
    } catch (err) {
      toast.show(err.message, "error");
    }
  };

  const marcarLida = async (c) => {
    setMenuContato(null);
    try {
      await api(`/contacts/${c.id}/mark-read`, { method: "POST" });
      carregarLista();
    } catch (err) {
      toast.show(err.message, "error");
    }
  };

  // Menu do clique direito fecha com clique fora, Esc ou mudança de tamanho da janela
  useEffect(() => {
    if (!menuContato) return undefined;
    const fechar = () => setMenuContato(null);
    const esc = (e) => e.key === "Escape" && fechar();
    document.addEventListener("mousedown", fechar);
    document.addEventListener("keydown", esc);
    window.addEventListener("resize", fechar);
    return () => {
      document.removeEventListener("mousedown", fechar);
      document.removeEventListener("keydown", esc);
      window.removeEventListener("resize", fechar);
    };
  }, [menuContato]);

  // Emoji entra onde está o cursor do campo de mensagem
  const fecharEmoji = useCallback(() => setEmojiAberto(false), []);
  const inserirEmoji = (emoji) => {
    const el = textoRef.current;
    const ini = el?.selectionStart ?? texto.length;
    const fim = el?.selectionEnd ?? texto.length;
    setTexto(texto.slice(0, ini) + emoji + texto.slice(fim));
    requestAnimationFrame(() => {
      if (!textoRef.current) return;
      textoRef.current.focus();
      const pos = ini + emoji.length;
      textoRef.current.setSelectionRange(pos, pos);
    });
  };

  // ----- prévia da conversa: mouse parado 1,5 s num contato da lista -----
  const fecharPrevia = useCallback(() => {
    clearTimeout(previaAbrir.current);
    clearTimeout(previaFechar.current);
    setPrevia(null);
  }, []);

  const entrarNoContato = (c, el) => {
    clearTimeout(previaAbrir.current);
    clearTimeout(previaFechar.current);
    if (previaRef.current?.contato.id === c.id) return; // voltou da prévia para o mesmo contato
    setPrevia(null);
    if (c.id === selRef.current) return; // conversa já aberta ao lado
    previaAbrir.current = setTimeout(() => {
      if (el.isConnected) setPrevia({ contato: c, ancora: el.getBoundingClientRect() });
    }, ESPERA_PREVIA_MS);
  };

  const sairDoContato = () => {
    clearTimeout(previaAbrir.current);
    clearTimeout(previaFechar.current);
    // um instante para levar o mouse até a prévia (dá para rolar as mensagens dentro dela)
    previaFechar.current = setTimeout(() => setPrevia(null), 250);
  };

  // Trocar de conversa, de aba ou de busca (e sair da tela) fecha a prévia
  useEffect(() => fecharPrevia, [selId, aba, busca, fecharPrevia]);

  // O contato saiu da lista (ex.: outro colega assumiu): a prévia dele fecha
  useEffect(() => {
    const aberta = previaRef.current;
    if (aberta && !contatos.some((c) => c.id === aberta.contato.id)) fecharPrevia();
  }, [contatos, fecharPrevia]);

  const enviar = async (e) => {
    e?.preventDefault();
    const t = texto.trim();
    if (!t || !selId || enviando) return;
    setEmojiAberto(false);
    if (editando) return salvarEdicao(t);
    const citando = respondendo;
    setTexto("");
    setRespondendo(null);
    setCorrecao(null);
    setEnviando(true);
    try {
      const m = await api("/messages", { method: "POST", body: { contactId: selId, text: t, replyToId: citando?.id } });
      setMensagens((prev) => (prev.some((x) => x.id === m.id) ? prev : [...prev, m]));
      if (m.data?.error) toast.show(`Mensagem não enviada: ${m.data.error}`, "error");
    } catch (err) {
      toast.show(err.message, "error");
      setTexto(t);
      setRespondendo(citando);
    } finally {
      setEnviando(false);
      textoRef.current?.focus();
    }
  };

  // ----- responder marcando e apagar -----
  const responder = (m) => {
    if (editando) cancelarEdicao();
    setRespondendo(m);
    textoRef.current?.focus();
  };

  // ----- editar (só texto enviado por você, até 15 min) -----
  const podeEditar = (m) =>
    m.isFromMe && m.type === "chat" && m.userId === me.id && !m.data?.deleted && !m.data?.error && !m.data?.forwarded &&
    Date.now() - new Date(m.createdAt).getTime() < LIMITE_EDICAO_MS;

  const editar = (m) => {
    if (!editando) setRascunho(texto); // guarda o que estava escrito para devolver depois
    setRespondendo(null);
    setCorrecao(null);
    setEditando(m);
    setTexto(m.text || "");
    setTimeout(() => {
      const el = textoRef.current;
      if (el) {
        el.focus();
        el.setSelectionRange(el.value.length, el.value.length);
      }
    }, 0);
  };

  const cancelarEdicao = () => {
    setEditando(null);
    setCorrecao(null);
    setTexto(rascunho);
    setRascunho("");
  };

  const salvarEdicao = async (t) => {
    const m = editando;
    if (t === (m.text || "")) return cancelarEdicao();
    setEnviando(true);
    try {
      const atualizada = await api(`/messages/${m.id}`, { method: "PUT", body: { text: t } });
      setMensagens((prev) => prev.map((x) => (x.id === atualizada.id ? { ...x, ...atualizada } : x)));
      setEditando(null);
      setCorrecao(null);
      setTexto(rascunho);
      setRascunho("");
      toast.show("Mensagem editada");
    } catch (err) {
      toast.show(err.message, "error");
    } finally {
      setEnviando(false);
      textoRef.current?.focus();
    }
  };

  // ----- corrigir meu texto (ortografia e pontuação) -----
  const corrigirTexto = async () => {
    const original = texto;
    if (!original.trim() || corrigindo) return;
    setCorrigindo(true);
    try {
      const r = await api("/text/correct", { method: "POST", body: { text: original } });
      if (r.aviso) toast.show(r.aviso, "error"); // ex.: crédito acabou e esta correção usou o corretor grátis
      if (!r.corrections || r.text === original) {
        setCorrecao(null);
        toast.show("Nenhuma correção: o texto parece certo");
      } else {
        setTexto(r.text);
        setCorrecao({ antes: original, depois: r.text, n: r.corrections });
      }
    } catch (err) {
      toast.show(err.message, "error");
    } finally {
      setCorrigindo(false);
      textoRef.current?.focus();
    }
  };

  const desfazerCorrecao = () => {
    if (!correcao) return;
    setTexto(correcao.antes);
    setCorrecao(null);
    textoRef.current?.focus();
  };

  // ----- encaminhar: marca as mensagens e escolhe para quem -----
  const podeEncaminhar = (m) => m.type !== "ticket" && !m.data?.deleted;

  const iniciarSelecao = (m) => {
    if (editando) cancelarEdicao();
    setRespondendo(null);
    setSelecionadas(new Set([m.id]));
  };

  const alternarSelecao = (m) => {
    if (!podeEncaminhar(m)) return;
    setSelecionadas((prev) => {
      const s = new Set(prev);
      if (s.has(m.id)) s.delete(m.id);
      else if (s.size < 20) s.add(m.id);
      else toast.show("Dá para encaminhar até 20 mensagens por vez", "error");
      return s;
    });
  };

  useEffect(() => {
    if (!selecionadas) return undefined;
    const onKey = (e) => e.key === "Escape" && !modal && setSelecionadas(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selecionadas, modal]);

  const encaminhar = async (destinos) => {
    const ids = mensagens.filter((m) => selecionadas?.has(m.id)).map((m) => m.id);
    const r = await api("/messages/forward", { method: "POST", body: { messageIds: ids, contactIds: destinos.map((d) => d.id) } });
    setModal(null);
    setSelecionadas(null);
    const para = destinos.length === 1 ? destinos[0].nome : `${destinos.length} conversas`;
    if (r.failed) toast.show(`${r.failed} de ${r.sent + r.failed} não foram enviadas para ${para}. Veja a conversa.`, "error");
    else toast.show(`${r.sent === 1 ? "Mensagem encaminhada" : `${r.sent} mensagens encaminhadas`} para ${para}`);
  };

  // ----- contato recebido (vCard): abrir conversa com ele -----
  const conversarCom = async (c, numero) => {
    try {
      const r = await api("/contacts/start", { method: "POST", body: { serviceId: contato.serviceId, number: numero, name: c.name || undefined } });
      trocarAba("all");
      selecionar(r.id);
      toast.show(r.created ? `Contato ${r.name} criado. Escreva a primeira mensagem.` : `Conversa com ${r.internalName || r.name}`);
    } catch (e) {
      toast.show(e.message, "error");
    }
  };

  const salvarTags = async (tagIds) => {
    await api(`/contacts/${selId}`, { method: "PUT", body: { tagIds } });
    setModal(null);
    toast.show("Tags atualizadas");
    carregarConversa(selId);
    carregarLista();
  };

  const podeApagar = (m) =>
    m.isFromMe && m.type !== "ticket" && !m.data?.deleted && !m.data?.error &&
    (m.userId === me.id || me.isAdmin) &&
    Date.now() - new Date(m.createdAt).getTime() < 60 * 3600 * 1000;

  const apagar = async (m) => {
    const ok = await confirmar({
      titulo: "Apagar para todos?",
      texto: "O cliente também deixa de ver a mensagem. A equipe continua vendo que ela foi apagada.",
      ok: "Apagar",
      perigo: true,
    });
    if (!ok) return;
    try {
      const atualizada = await api(`/messages/${m.id}`, { method: "DELETE" });
      setMensagens((prev) => prev.map((x) => (x.id === atualizada.id ? atualizada : x)));
      toast.show("Mensagem apagada para todos");
    } catch (e) {
      toast.show(e.message, "error");
    }
  };

  const irPara = (id) => {
    if (!id) return;
    const el = document.getElementById(`msg-${id}`);
    if (!el) return toast.show("A mensagem citada não está entre as últimas carregadas", "error");
    el.scrollIntoView({ block: "center", behavior: "smooth" });
    setDestaque(id);
    setTimeout(() => setDestaque(null), 1600);
  };

  // ----- gravar áudio (mensagem de voz) -----
  const descartarGravacao = () => {
    const g = gravacaoRef.current;
    gravacaoRef.current = null;
    if (g) {
      try {
        g.rec.onstop = null;
        if (g.rec.state !== "inactive") g.rec.stop();
      } catch {
        /* já parado */
      }
      g.stream.getTracks().forEach((t) => t.stop());
    }
    setGravando(false);
  };

  const iniciarGravacao = async () => {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      return toast.show("Este navegador não permite gravar áudio", "error");
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const tipo = ["audio/ogg;codecs=opus", "audio/webm;codecs=opus", "audio/webm", "audio/mp4"].find((t) => MediaRecorder.isTypeSupported(t));
      const rec = new MediaRecorder(stream, tipo ? { mimeType: tipo } : undefined);
      const partes = [];
      rec.ondataavailable = (e) => e.data.size && partes.push(e.data);
      rec.start(250);
      gravacaoRef.current = { rec, stream, partes, inicio: Date.now() };
      setTempoGravacao(0);
      setGravando(true);
    } catch (e) {
      toast.show(e.name === "NotAllowedError" ? "Permita o uso do microfone no navegador para gravar áudio" : `Microfone indisponível: ${e.message}`, "error");
    }
  };

  const enviarGravacao = async () => {
    const g = gravacaoRef.current;
    if (!g || !selId) return;
    gravacaoRef.current = null;
    setGravando(false);
    const blob = await new Promise((resolve) => {
      g.rec.onstop = () => resolve(new Blob(g.partes, { type: g.rec.mimeType || "audio/webm" }));
      g.rec.stop();
    });
    g.stream.getTracks().forEach((t) => t.stop());
    if (Date.now() - g.inicio < 800 || blob.size < 1500) return toast.show("Áudio muito curto", "error");
    const citando = respondendo;
    setRespondendo(null);
    setEnviandoAudio(true);
    try {
      const fd = new FormData();
      fd.append("contactId", selId);
      fd.append("voice", "true");
      if (citando) fd.append("replyToId", citando.id);
      fd.append("file", blob, `gravacao.${(blob.type.split("/")[1] || "webm").split(";")[0]}`);
      const m = await apiForm("/messages/media", fd);
      setMensagens((prev) => (prev.some((x) => x.id === m.id) ? prev : [...prev, m]));
      if (m.data?.error) toast.show(`Áudio não enviado: ${m.data.error}`, "error");
    } catch (e) {
      toast.show(e.message, "error");
    } finally {
      setEnviandoAudio(false);
    }
  };
  const enviarGravacaoRef = useRef(null);
  enviarGravacaoRef.current = enviarGravacao;

  // ----- arquivos: clipe, arrastar e soltar, Ctrl+V -----
  const abrirAnexos = (lista) => {
    const files = [...(lista || [])].filter(Boolean);
    if (!files.length || !selId) return;
    const grandes = files.filter((f) => f.size > MAX_ARQUIVO);
    if (grandes.length) toast.show(`Arquivo maior que ${MAX_ARQUIVO_MB} MB não pode ser enviado: ${grandes.map((f) => f.name).join(", ")}`, "error");
    const ok = files.filter((f) => f.size <= MAX_ARQUIVO && f.size > 0);
    if (ok.length) setAnexos(ok);
  };

  const enviarAnexos = async (legenda) => {
    const lista = anexos;
    const citando = respondendo;
    for (let i = 0; i < lista.length; i++) {
      const fd = new FormData();
      fd.append("contactId", selId);
      fd.append("caption", i === 0 ? legenda : "");
      if (i === 0 && citando) fd.append("replyToId", citando.id);
      // print colado vem como "image.png": dá um nome melhor
      const f = lista[i];
      fd.append("file", f, f.name && f.name !== "image.png" ? f.name : `print-${new Date().toISOString().slice(0, 19).replace(/[T:]/g, "-")}.png`);
      const m = await apiForm("/messages/media", fd);
      setMensagens((prev) => (prev.some((x) => x.id === m.id) ? prev : [...prev, m]));
      if (m.data?.error) toast.show(`Arquivo não enviado: ${m.data.error}`, "error");
    }
    setAnexos([]);
    setRespondendo(null);
    toast.show(lista.length > 1 ? `${lista.length} arquivos enviados` : "Arquivo enviado");
  };

  const onPaste = (e) => {
    const files = [...(e.clipboardData?.files || [])];
    if (files.length) {
      e.preventDefault();
      abrirAnexos(files);
    }
  };

  const sugestoes = useMemo(() => {
    if (!texto.startsWith("/")) return [];
    const termo = texto.slice(1).toLowerCase();
    return respostas.filter((r) => r.title.toLowerCase().includes(termo) || r.text.toLowerCase().includes(termo)).slice(0, 6);
  }, [texto, respostas]);

  useEffect(() => setSugIdx(0), [sugestoes.length]);

  const usarSugestao = (r) => {
    setTexto(r.text);
    textoRef.current?.focus();
  };

  const onKeyDown = (e) => {
    if (sugestoes.length) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        return setSugIdx((i) => (i + 1) % sugestoes.length);
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        return setSugIdx((i) => (i - 1 + sugestoes.length) % sugestoes.length);
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        return usarSugestao(sugestoes[sugIdx]);
      }
      if (e.key === "Escape") return setTexto("");
    }
    if (e.key === "Escape" && editando) return cancelarEdicao();
    if (e.key === "Escape" && respondendo) return setRespondendo(null);
    if (e.key === "Enter" && !e.shiftKey) enviar(e);
  };

  const acao = async (fn, ok) => {
    try {
      await fn();
      toast.show(ok);
      carregarConversa(selId);
      carregarLista();
    } catch (err) {
      toast.show(err.message, "error");
    }
  };

  const ticket = contato?.currentTicket;
  const nomeDep = (id) => deps.find((d) => d.id === id)?.name || "Sem departamento";
  const nomeUser = (id) => usuarios.find((u) => u.id === id)?.name || "Atendente";
  const nomeContato = contato?.internalName || contato?.name || "Cliente";
  // Quem mandou a última mensagem (aparece na lista, embaixo do nome do contato)
  const quemMandou = (c) => {
    const s = c.lastMessageSender;
    if (!s || !c.lastMessage) return null;
    if (!s.fromMe) {
      if (!c.isGroup) return { rotulo: "Cliente", dica: "Última mensagem: enviada pelo cliente" };
      return { rotulo: primeiroNome(s.name) || "Participante", dica: `Última mensagem: enviada por ${s.name || "um participante do grupo"}` };
    }
    if (s.userId === me.id) return { rotulo: "Você", dica: "Última mensagem: enviada por você" };
    if (s.userId) return { rotulo: primeiroNome(nomeUser(s.userId)), dica: `Última mensagem: enviada por ${nomeUser(s.userId)}` };
    if (s.via === "api") return { rotulo: "Integração", dica: `Última mensagem: enviada por outro sistema${s.name ? ` (chave ${s.name})` : ""}` };
    if (s.via === "device") return { rotulo: "Celular", dica: "Última mensagem: enviada pelo celular / outro aparelho" };
    return { rotulo: "Atendente", dica: "Última mensagem: enviada pela equipe" };
  };
  const autorCitacao = (r) =>
    r.fromMe === false ? r.senderName || nomeContato : r.fromMe ? (r.userId ? nomeUser(r.userId) : "Você (celular)") : "Mensagem citada";
  const resumoMsg = (m) => {
    if (m.text) return m.text;
    if (m.type === "document") return `[Documento] ${m.data?.file?.name || ""}`;
    return { image: "[Imagem]", sticker: "[Figurinha]", video: "[Vídeo]", audio: "[Áudio]", ptt: "[Mensagem de voz]" }[m.type] || "[Mensagem]";
  };
  const quemApagou = (d) =>
    d.deletedBy === "contact" ? "pelo cliente" : d.deletedBy === "device" ? "pelo celular / outro aparelho" : d.deletedBy ? `por ${nomeUser(d.deletedBy)}` : "";
  const sobreEdicao = (d) => {
    const quem = d.editedBy === "contact" ? "pelo cliente" : d.editedBy === "device" ? "pelo celular / outro aparelho" : d.editedBy ? `por ${nomeUser(d.editedBy)}` : "";
    const antes = (d.editHistory || []).map((h) => `“${h.text}”`).join("\n");
    return `Editada ${quem}${d.editedAt ? ` às ${hora(d.editedAt)}` : ""}${antes ? `\nAntes:\n${antes}` : ""}`;
  };
  const fmtTempo = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

  // Mensagens agrupadas por dia
  const itens = [];
  let ultimoDia = null;
  for (const m of mensagens) {
    if (m.type === "chat" && ehAvisoInterno(m.text)) continue;
    const dia = rotuloDia(m.createdAt);
    if (dia !== ultimoDia) {
      itens.push({ sep: dia, id: `sep-${m.id}` });
      ultimoDia = dia;
    }
    itens.push(m);
  }

  return (
    <div className={`chat ${selId ? "has-selection" : ""}`}>
      <section className="chat-list">
        <div className="chat-list-head">
          <div className="chat-list-title">
            <h2>Atendimento</h2>
            {contagens.queueTickets > 0 && aba !== "queue" && (
              <button type="button" className="chip chip-btn warn-chip" onClick={() => trocarAba("queue")} title="Ver quem está esperando na fila">
                <Icon name="clock" size={12} />{contagens.queueTickets} na fila
              </button>
            )}
          </div>
          <div className="search-box">
            <Icon name="search" size={16} />
            <input
              placeholder="Buscar nome ou número"
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              onKeyDown={(e) => e.key === "Escape" && setBusca("")}
              aria-label="Buscar conversa"
            />
            {busca && <button type="button" className="icon-btn search-clear" onClick={() => setBusca("")} aria-label="Limpar busca" title="Limpar busca (Esc)"><Icon name="x" size={15} /></button>}
          </div>
          <div className="tabs" role="tablist">
            {ABAS.map((a) => (
              <button key={a.id} role="tab" aria-selected={aba === a.id} className={aba === a.id ? "active" : ""} onClick={() => trocarAba(a.id)}>
                {a.label}
                {a.count && contagens[a.count] > 0 && <span className="count">{contagens[a.count]}</span>}
              </button>
            ))}
          </div>
        </div>
        <ul onScroll={fecharPrevia}>
          {carregandoLista &&
            [0, 1, 2, 3, 4, 5].map((i) => (
              <li key={`sk${i}`} className="sk-item" aria-hidden="true">
                <span className="sk sk-circle" style={{ width: 40, height: 40 }} />
                <div className="grow">
                  <span className="sk sk-line" style={{ width: `${55 + ((i * 13) % 30)}%`, height: 11 }} />
                  <span className="sk sk-line" style={{ width: `${70 + ((i * 7) % 25)}%` }} />
                </div>
              </li>
            ))}
          {!carregandoLista && contatos.length === 0 && (
            <li className="chat-empty">
              <div className="empty-state">
                <span className="empty-icon"><Icon name={busca ? "search" : aba === "mine" || aba === "queue" ? "check" : "inbox"} size={24} /></span>
                <strong>{busca ? "Nada encontrado" : TITULO_VAZIO[aba]}</strong>
                <span>{busca ? "Nenhuma conversa para essa busca." : VAZIO[aba]}</span>
                {busca ? (
                  <button type="button" onClick={() => setBusca("")}>Limpar busca</button>
                ) : aba === "mine" && contagens.queueTickets > 0 ? (
                  <button type="button" className="primary" onClick={() => trocarAba("queue")}><Icon name="clock" size={15} />Ver a fila ({contagens.queueTickets})</button>
                ) : null}
              </div>
            </li>
          )}
          {contatos.map((c) => {
            const quem = quemMandou(c);
            const rascunhoDela = c.id !== selId ? rascunhosRef.current.get(c.id) : null;
            return (
            <li
              key={c.id}
              className={`${c.id === selId ? "sel" : ""} ${c.unread > 0 ? "unread" : ""}`}
              onClick={() => { fecharPrevia(); selecionar(c.id); }}
              onContextMenu={(e) => {
                e.preventDefault();
                fecharPrevia();
                setMenuContato({ contato: c, x: e.clientX, y: e.clientY });
              }}
              onMouseEnter={(e) => entrarNoContato(c, e.currentTarget)}
              onMouseLeave={sairDoContato}
            >
              <Avatar nome={c.internalName || c.name} url={c.avatarUrl} grupo={c.isGroup} />
              <div className="grow">
                <div className="row">
                  <span className="name-line">
                    <strong className="ellipsis">
                      {c.isGroup && <Icon name="users" size={14} className="group-mark" title="Grupo" />}
                      {c.internalName || c.name}
                    </strong>
                    <TagsMini ids={c.tagIds} tags={tags} />
                  </span>
                  {aba === "queue" && c.queuedAt ? (
                    <span className="time-small wait" title={`Na fila desde ${new Date(c.queuedAt).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}`}>
                      <Icon name="clock" size={12} />{esperaDesde(c.queuedAt, agora)}
                    </span>
                  ) : (
                    <span className="time-small">{quandoCurto(c.lastMessageAt)}</span>
                  )}
                </div>
                <div className="row" style={{ marginTop: 2 }}>
                  <span className="muted ellipsis preview">
                    {rascunhoDela ? (
                      <><span className="draft" title="Você começou a escrever e não enviou">Rascunho: </span>{rascunhoDela}</>
                    ) : (
                      <>
                        {quem && !ehAvisoInterno(c.lastMessage) && <span className="quem" title={quem.dica}>{quem.rotulo}: </span>}
                        {(!ehAvisoInterno(c.lastMessage) && c.lastMessage) || c.data?.number}
                      </>
                    )}
                  </span>
                  <ContadorEspera c={c} agora={agora} />
                </div>
              </div>
            </li>
            );
          })}
        </ul>
      </section>

      <section
        className={`chat-main ${arrastando ? "dragging" : ""}`}
        onDragOver={(e) => {
          if (contato && e.dataTransfer?.types?.includes("Files")) {
            e.preventDefault();
            setArrastando(true);
          }
        }}
        onDragLeave={(e) => {
          if (!e.currentTarget.contains(e.relatedTarget)) setArrastando(false);
        }}
        onDrop={(e) => {
          if (!contato) return;
          e.preventDefault();
          setArrastando(false);
          abrirAnexos(e.dataTransfer?.files);
        }}
      >
        {arrastando && <div className="drop-overlay"><Icon name="paperclip" size={28} />Solte para enviar para {contato?.internalName || contato?.name}</div>}
        {!selId ? (
          <div className="chat-placeholder">
            <div className="big-icon"><Icon name="chat" size={34} /></div>
            <strong>Selecione uma conversa</strong>
            <span>As mensagens novas aparecem aqui em tempo real.</span>
            <div className="placeholder-tips">
              <div><span>Buscar conversa, tela ou ação</span><span><kbd>Ctrl</kbd><kbd>K</kbd></span></div>
              <div><span>Conversa de cima / de baixo</span><span><kbd>Alt</kbd><kbd>↑</kbd><kbd>↓</kbd></span></div>
              <div><span>Respostas rápidas no campo</span><span><kbd>/</kbd></span></div>
            </div>
          </div>
        ) : !mostrandoConversa ? (
          <>
            <header className="chat-head" aria-busy="true">
              <div className="who">
                <button className="icon-btn back-btn" onClick={() => selecionar(null)} aria-label="Voltar para a lista"><Icon name="arrowLeft" /></button>
                <span className="sk sk-circle" style={{ width: 42, height: 42 }} />
                <div className="who-text" style={{ display: "grid", gap: 9 }}>
                  <span className="sk sk-line" style={{ width: 190, height: 13 }} />
                  <span className="sk sk-line" style={{ width: 280, maxWidth: "100%" }} />
                </div>
              </div>
            </header>
            <div className="sk-chat" aria-label="Carregando a conversa">
              {[38, 62, 45, 30, 55].map((w, i) => (
                <span key={i} className={`sk sk-bubble ${i % 2 ? "me" : ""}`} style={{ width: `${w}%` }} />
              ))}
            </div>
          </>
        ) : (
          <>
            <header className="chat-head">
              <div className="who">
                <button className="icon-btn back-btn" onClick={() => selecionar(null)} aria-label="Voltar para a lista"><Icon name="arrowLeft" /></button>
                <Avatar nome={contato.internalName || contato.name} size={42} url={contato.avatarUrl} grupo={contato.isGroup} />
                <div className="who-text">
                  <div className="who-line">
                    <strong className="ellipsis">{contato.internalName || contato.name}</strong>
                    {contato.isGroup ? <span className="chip"><Icon name="users" size={12} />Grupo do WhatsApp</span> : <span className="who-number">{fmtNumero(contato.data?.number) || contato.data?.number}</span>}
                  </div>
                  <div className="meta">
                    {ticket ? (
                      <>
                        <span className="chip mono" title="Protocolo do chamado">#{ticket.protocol}</span>
                        <span className="chip" title="Departamento"><Icon name="building" size={12} />{nomeDep(ticket.departmentId)}</span>
                        {ticket.userId ? (
                          <span className={`chip ${ticket.userId === me.id ? "ok" : ""}`} title={`Atendente: ${nomeUser(ticket.userId)}`}><Icon name="user" size={12} />{ticket.userId === me.id ? "Com você" : nomeUser(ticket.userId)}</span>
                        ) : (
                          <span className="chip warn"><Icon name="clock" size={12} />Na fila</span>
                        )}
                      </>
                    ) : (
                      <span className="chip chip-soft">Sem chamado aberto</span>
                    )}
                    <TagsMini ids={contato.tagIds} tags={tags} max={4} />
                    <button type="button" className="chip chip-btn" onClick={() => setModal("tags")} title="Escolher as tags deste contato">
                      <Icon name={contato.tagIds?.length ? "edit" : "plus"} size={12} />{contato.tagIds?.length ? "Tags" : "Tag"}
                    </button>
                  </div>
                </div>
              </div>
              <div className="actions">
                {ticket ? (
                  <>
                    {ticket.userId !== me.id && (
                      <button className="primary" onClick={() => acao(() => api(`/contacts/${selId}/ticket/transfer`, { method: "POST", body: { departmentId: ticket.departmentId, userId: me.id } }), "Chamado assumido por você")} title="Passar este chamado para você">
                        <Icon name="check" size={16} /><span>Assumir</span>
                      </button>
                    )}
                    <button onClick={() => setModal("transferir")} title="Mudar o departamento ou o atendente"><Icon name="transfer" size={16} /><span>Transferir</span></button>
                    <button className="ghost-danger" onClick={() => setModal("fechar")} title="Encerrar o atendimento"><Icon name="x" size={16} /><span>Fechar</span></button>
                  </>
                ) : (
                  <button className="primary" onClick={() => acao(() => api(`/contacts/${selId}/ticket/open`, { method: "POST", body: {} }), "Chamado aberto")}>
                    <Icon name="plus" size={16} /><span>Abrir chamado</span>
                  </button>
                )}
                <span className="actions-sep" aria-hidden="true" />
                <button className="icon-btn head-icon" onClick={() => marcarNaoLida(contato)} title="Marcar como não lida (sai da conversa e ela volta com o contador na lista)" aria-label="Marcar como não lida">
                  <Icon name="unread" size={19} />
                </button>
                <button className="icon-btn head-icon" onClick={() => selecionar(null)} title="Sair da conversa (o chamado continua como está)" aria-label="Sair da conversa">
                  <Icon name="logout" size={19} />
                </button>
              </div>
            </header>

            <div className="messages-wrap">
            <div className={`messages ${selecionadas ? "selecting" : ""}`} ref={listaMsgRef} onScroll={aoRolar}>
              {itens.map((m) => {
                if (m.sep) return <div key={m.id} className="day-sep">{m.sep}</div>;
                if (m.type === "ticket") {
                  // Eventos antigos não tinham o nome no texto: completa com quem fez a ação
                  const texto = m.userId && !/ por |pelo cliente/.test(m.text || "") ? `${m.text} por ${nomeUser(m.userId)}` : m.text;
                  return <div key={m.id} className="event"><Icon name="clock" size={13} />{texto} · {hora(m.createdAt)}</div>;
                }
                const apagada = m.data?.deleted;
                const r = m.data?.replyTo;
                const contatosVcard = m.type === "vcard" ? m.data?.contacts || [] : [];
                const marcada = selecionadas?.has(m.id);
                return (
                  <div
                    key={m.id}
                    id={`msg-${m.id}`}
                    className={`bubble ${m.isFromMe ? "me" : "them"} ${m.data?.error ? "failed" : ""} ${m.data?.file && !apagada ? "has-media" : ""} ${apagada ? "deleted" : ""} ${destaque === m.id ? "highlight" : ""} ${marcada ? "marked" : ""} ${editando?.id === m.id ? "editing" : ""}`}
                    onClickCapture={selecionadas ? (e) => { e.preventDefault(); e.stopPropagation(); alternarSelecao(m); } : undefined}
                  >
                    {selecionadas && podeEncaminhar(m) && (
                      <span className={`sel-check ${marcada ? "on" : ""}`} role="checkbox" aria-checked={!!marcada} aria-label="Marcar para encaminhar">
                        {marcada && <Icon name="check" size={13} />}
                      </span>
                    )}
                    {!apagada && !selecionadas && (
                      <div className="bubble-actions">
                        <button type="button" className="icon-btn" onClick={() => responder(m)} title="Responder marcando esta mensagem" aria-label="Responder"><Icon name="reply" size={15} /></button>
                        {podeEditar(m) && (
                          <button type="button" className="icon-btn" onClick={() => editar(m)} title="Editar mensagem (até 15 min depois do envio)" aria-label="Editar"><Icon name="edit" size={15} /></button>
                        )}
                        <button type="button" className="icon-btn" onClick={() => iniciarSelecao(m)} title="Encaminhar para outra conversa" aria-label="Encaminhar"><Icon name="forward" size={15} /></button>
                        {podeApagar(m) && (
                          <button type="button" className="icon-btn" onClick={() => apagar(m)} title="Apagar para todos" aria-label="Apagar para todos"><Icon name="trash" size={15} /></button>
                        )}
                      </div>
                    )}
                    {m.data?.forwarded && !apagada && <div className="fwd-label"><Icon name="forward" size={12} />Encaminhada</div>}
                    {m.isFromMe && m.userId && (
                      <div className="author" title={m.data?.signed ? "O cliente recebeu a mensagem assinada com este nome" : undefined}>
                        {nomeUser(m.userId)}{m.data?.signed && <span className="signed"> · assinada</span>}
                      </div>
                    )}
                    {m.isFromMe && !m.userId && m.data?.origin === "device" && <div className="author device">Pelo celular / outro aparelho</div>}
                    {m.isFromMe && !m.userId && m.data?.api && <div className="author device" title="Enviada por outro sistema, com uma chave de API">Integração · {m.data.api.keyName}</div>}
                    {!m.isFromMe && m.data?.sender && (
                      <div className="author sender" style={{ color: corDe(m.data.sender.jid || m.data.sender.number) }}>
                        {m.data.sender.name || m.data.sender.number || "Participante"}
                        {m.data.sender.name && m.data.sender.number && <span className="sender-number"> · {m.data.sender.number}</span>}
                      </div>
                    )}
                    {r && (
                      <button type="button" className="quote" onClick={() => irPara(r.id)} title={r.id ? "Ir para a mensagem citada" : undefined}>
                        <strong>{autorCitacao(r)}</strong>
                        <span>{r.text}</span>
                      </button>
                    )}
                    {apagada ? (
                      <>
                        <div className="deleted-label"><Icon name="ban" size={14} /> Mensagem apagada {quemApagou(m.data)}</div>
                        {(m.text || m.data?.file) && <div className="deleted-original" title="Conteúdo original, visível só para a equipe">{resumoMsg(m)}</div>}
                      </>
                    ) : (
                      <>
                        <Midia m={m} onAbrirImagem={setImagemAberta} onAbrirPdf={abrirPdf} onLinkExpirado={() => carregarConversa(selId)} />
                        {contatosVcard.length > 0 ? (
                          <div className="vcards">
                            {contatosVcard.map((c, i) => (
                              <div key={i} className="vcard">
                                <span className="vcard-icon"><Icon name="user" size={18} /></span>
                                <div className="vcard-info">
                                  <strong className="ellipsis">{c.name || "Contato"}</strong>
                                  {(c.numbers || []).length === 0 && <small className="muted">Sem número no contato</small>}
                                  {(c.numbers || []).map((n) => (
                                    <div key={n} className="vcard-num">
                                      <span>{fmtNumero(n)}</span>
                                      <button type="button" className="link" onClick={() => conversarCom(c, n)} title="Abrir uma conversa com este número no InteliSac">
                                        <Icon name="chat" size={14} />Conversar
                                      </button>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            ))}
                          </div>
                        ) : (
                          m.text && <div className="text"><TextoComLinks texto={m.text} /></div>
                        )}
                        {m.data?.fileError && <div className="fail small">Arquivo não pôde ser salvo ({m.data.fileError})</div>}
                      </>
                    )}
                    <div className="time">
                      {m.data?.edited && !apagada && <span className="edited" title={sobreEdicao(m.data)}>editada ·</span>}
                      {hora(m.createdAt)}
                      {m.data?.error && <span className="fail"> · não enviada</span>}
                      <Tiques m={m} />
                    </div>
                  </div>
                );
              })}
              <div ref={fimRef} />
            </div>
            {longeDoFim && (
              <button
                type="button"
                className="jump-end"
                onClick={() => {
                  descer(true);
                  setNovasAbaixo(0);
                }}
                title={novasAbaixo ? `${novasAbaixo} ${novasAbaixo === 1 ? "mensagem nova" : "mensagens novas"}: ir para o fim` : "Ir para a última mensagem"}
                aria-label="Ir para a última mensagem"
              >
                <Icon name="arrowDown" size={19} />
                {novasAbaixo > 0 && <span className="jump-count">{novasAbaixo}</span>}
              </button>
            )}
            </div>

            {selecionadas ? (
              <div className="select-bar">
                <button type="button" className="icon-btn" onClick={() => setSelecionadas(null)} title="Cancelar (Esc)" aria-label="Cancelar encaminhamento"><Icon name="x" size={18} /></button>
                <span className="grow">
                  <strong>{selecionadas.size}</strong> {selecionadas.size === 1 ? "mensagem marcada" : "mensagens marcadas"}
                  <span className="muted"> · clique nas mensagens para marcar ou desmarcar</span>
                </span>
                <button type="button" className="primary" disabled={!selecionadas.size} onClick={() => setModal("encaminhar")}>
                  <Icon name="forward" size={16} /><span>Encaminhar</span>
                </button>
              </div>
            ) : (
            <>
            {respondendo && (
              <div className="reply-bar">
                <Icon name="reply" size={16} />
                <div className="quote static">
                  <strong>Respondendo {autorCitacao({ fromMe: respondendo.isFromMe, userId: respondendo.userId, senderName: respondendo.data?.sender?.name })}</strong>
                  <span>{resumoMsg(respondendo)}</span>
                </div>
                <button type="button" className="icon-btn" onClick={() => setRespondendo(null)} title="Cancelar resposta (Esc)" aria-label="Cancelar resposta"><Icon name="x" size={16} /></button>
              </div>
            )}
            {editando && (
              <div className="reply-bar edit-bar">
                <Icon name="edit" size={16} />
                <div className="quote static">
                  <strong>Editando mensagem · o cliente vê a versão nova com “Editada”</strong>
                  <span>{editando.text}</span>
                </div>
                <button type="button" className="icon-btn" onClick={cancelarEdicao} title="Cancelar edição (Esc)" aria-label="Cancelar edição"><Icon name="x" size={16} /></button>
              </div>
            )}
            {correcao && texto === correcao.depois && (
              <div className="fix-bar" role="status">
                <Icon name="check" size={14} />
                <span>{correcao.n === 1 ? "1 correção feita" : `${correcao.n} correções feitas`}. Confira antes de enviar.</span>
                <button type="button" className="link" onClick={desfazerCorrecao}>Desfazer</button>
              </div>
            )}

            {gravando ? (
              <div className="composer recording">
                <button type="button" className="icon-btn" onClick={descartarGravacao} title="Descartar gravação" aria-label="Descartar gravação"><Icon name="trash" size={20} /></button>
                <div className="rec-box" role="status">
                  <span className="rec-dot" aria-hidden="true" />
                  <span className="rec-time">{fmtTempo(tempoGravacao)}</span>
                  <span className="rec-wave" aria-hidden="true"><i /><i /><i /><i /><i /></span>
                  <span className="muted grow ellipsis">Gravando… clique na seta para enviar</span>
                </div>
                <button type="button" className="primary send-btn" onClick={enviarGravacao} title="Enviar áudio" aria-label="Enviar áudio"><Icon name="send" size={17} /></button>
              </div>
            ) : (
            <form className={`composer ${editando ? "is-editing" : ""}`} onSubmit={enviar}>
              {sugestoes.length > 0 && (
                <ul className="suggestions" role="listbox" aria-label="Respostas rápidas">
                  <li className="suggestions-head" role="presentation">
                    <span>Respostas rápidas</span>
                    <span><kbd>↑</kbd><kbd>↓</kbd> escolher · <kbd>Enter</kbd> usar</span>
                  </li>
                  {sugestoes.map((r, i) => (
                    <li key={r.id} role="option" aria-selected={i === sugIdx} className={i === sugIdx ? "sel" : ""} onMouseDown={(e) => { e.preventDefault(); usarSugestao(r); }}>
                      <strong>/{r.title}</strong><span className="muted">{r.text}</span>
                    </li>
                  ))}
                </ul>
              )}
              <input
                ref={arquivoRef}
                type="file"
                multiple
                hidden
                onChange={(e) => {
                  abrirAnexos(e.target.files);
                  e.target.value = "";
                }}
              />
              {emojiAberto && <EmojiPicker onEscolher={inserirEmoji} onFechar={fecharEmoji} />}
              <div className="composer-box">
              <button
                type="button"
                className={`icon-btn attach-btn emoji-btn ${emojiAberto ? "on" : ""}`}
                onClick={() => setEmojiAberto((v) => !v)}
                title="Emojis"
                aria-label="Emojis"
                aria-expanded={emojiAberto}
              >
                <Icon name="smile" size={20} />
              </button>
              {!editando && (
                <button type="button" className="icon-btn attach-btn" onClick={() => arquivoRef.current?.click()} title="Anexar arquivo (ou arraste para a conversa / cole um print com Ctrl+V)" aria-label="Anexar arquivo">
                  <Icon name="paperclip" size={20} />
                </button>
              )}
              <textarea
                ref={textoRef}
                placeholder={editando ? "Texto novo da mensagem…" : `Mensagem para ${contato.isGroup ? "o grupo" : nomeContato}…`}
                value={texto}
                onChange={(e) => setTexto(e.target.value)}
                onKeyDown={onKeyDown}
                onPaste={onPaste}
                rows={1}
                aria-label="Mensagem"
              />
              {texto.trim() && !texto.startsWith("/") && (
                <button type="button" className="fix-btn" onClick={corrigirTexto} disabled={corrigindo || enviando} title="Corrigir meu texto: ortografia e pontuação (você confere antes de enviar)">
                  <Icon name="wand" size={16} /><span>{corrigindo ? "Corrigindo…" : "Corrigir"}</span>
                </button>
              )}
              </div>
              {editando ? (
                <button className="primary send-btn" disabled={enviando || !texto.trim()} title="Salvar edição (Enter)" aria-label="Salvar edição">
                  <Icon name="check" size={18} />
                </button>
              ) : texto.trim() ? (
                <button className="primary send-btn" disabled={enviando} title="Enviar (Enter)" aria-label="Enviar">
                  <Icon name="send" size={17} />
                </button>
              ) : (
                <button type="button" className="primary send-btn" onClick={iniciarGravacao} disabled={enviandoAudio} title="Gravar mensagem de voz" aria-label="Gravar áudio">
                  <Icon name="mic" size={18} />
                </button>
              )}
              <div className="composer-hint" aria-hidden="true">
                <span><kbd>Enter</kbd> envia</span>
                <span><kbd>Shift</kbd><kbd>Enter</kbd> nova linha</span>
                <span><kbd>/</kbd> respostas rápidas</span>
              </div>
            </form>
            )}
            </>
            )}
          </>
        )}
      </section>

      {menuContato && (
        <ul
          className="context-menu"
          role="menu"
          style={{ left: Math.min(menuContato.x, window.innerWidth - 230), top: Math.min(menuContato.y, window.innerHeight - 110) }}
          onMouseDown={(e) => e.stopPropagation()}
        >
          <li role="menuitem" onClick={() => { const c = menuContato.contato; setMenuContato(null); selecionar(c.id); }}>
            <Icon name="chat" size={16} />Abrir conversa
          </li>
          {menuContato.contato.unread > 0 ? (
            <li role="menuitem" onClick={() => marcarLida(menuContato.contato)}>
              <Icon name="checks" size={16} />Marcar como lida
            </li>
          ) : (
            <li role="menuitem" onClick={() => marcarNaoLida(menuContato.contato)}>
              <Icon name="unread" size={16} />Marcar como não lida
            </li>
          )}
        </ul>
      )}

      {previa && (
        <PreviaConversa
          key={previa.contato.id}
          contato={previa.contato}
          ancora={previa.ancora}
          meId={me.id}
          nomeUser={nomeUser}
          onMouseEnter={() => clearTimeout(previaFechar.current)}
          onMouseLeave={sairDoContato}
        />
      )}

      {anexos.length > 0 && (
        <AnexoModal
          arquivos={anexos}
          destino={contato?.internalName || contato?.name}
          legendaInicial={texto}
          onClose={() => setAnexos([])}
          onEnviar={async (legenda) => {
            await enviarAnexos(legenda);
            if (legenda && legenda === texto.trim()) setTexto("");
          }}
        />
      )}

      {imagemAberta && (
        <Modal titulo={imagemAberta.data?.file?.name || "Imagem"} icone="image" onClose={() => setImagemAberta(null)} largura="min(92vw, 1100px)">
          <div className="lightbox">
            <img src={imagemAberta.fileUrl} alt={imagemAberta.data?.file?.name || ""} />
          </div>
          <div className="modal-actions">
            <a className="btn-link" href={imagemAberta.downloadUrl || imagemAberta.fileUrl} target="_blank" rel="noreferrer">
              <Icon name="download" size={16} /> Baixar
            </a>
          </div>
        </Modal>
      )}

      {pdfAberto && (
        <Modal titulo={pdfAberto.data?.file?.name || "PDF"} icone="file" onClose={() => setPdfAberto(null)} largura="min(96vw, 1100px)">
          <iframe
            className="pdf-quadro"
            src={`${pdfAberto.fileUrl}#view=FitH`}
            title={pdfAberto.data?.file?.name || "PDF"}
            referrerPolicy="no-referrer"
          />
          <div className="modal-actions">
            <a className="btn-sec" href={pdfAberto.fileUrl} target="_blank" rel="noreferrer">
              <Icon name="external" size={16} /> Abrir em outra aba
            </a>
            <a className="btn-link" href={pdfAberto.downloadUrl || pdfAberto.fileUrl} target="_blank" rel="noreferrer">
              <Icon name="download" size={16} /> Baixar
            </a>
          </div>
        </Modal>
      )}

      {modal === "transferir" && (
        <TransferirModal
          deps={deps}
          usuarios={usuarios}
          meId={me.id}
          atual={ticket}
          onClose={() => setModal(null)}
          onOk={async (body) => {
            await api(`/contacts/${selId}/ticket/transfer`, { method: "POST", body });
            setModal(null);
            toast.show("Chamado transferido");
            carregarConversa(selId);
            carregarLista();
          }}
        />
      )}
      {modal === "fechar" && (
        <FecharModal
          assuntos={assuntos}
          protocolo={ticket?.protocol}
          onClose={() => setModal(null)}
          onOk={async (body) => {
            await api(`/contacts/${selId}/ticket/close`, { method: "POST", body });
            setModal(null);
            toast.show("Chamado fechado");
            carregarConversa(selId);
            carregarLista();
          }}
        />
      )}
      {modal === "tags" && contato && (
        <TagsModal tags={tags} atuais={contato.tagIds || []} nome={nomeContato} onClose={() => setModal(null)} onOk={salvarTags} />
      )}
      {modal === "encaminhar" && selecionadas && (
        <EncaminharModal quantidade={selecionadas.size} onClose={() => setModal(null)} onOk={encaminhar} />
      )}
    </div>
  );
}

function TagsModal({ tags, atuais, nome, onClose, onOk }) {
  const [sel, setSel] = useState(atuais);
  const [erro, setErro] = useState("");
  const [salvando, setSalvando] = useState(false);
  const toggle = (id) => setSel((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  const salvar = async () => {
    setSalvando(true);
    try {
      await onOk(sel);
    } catch (e) {
      setErro(e.message);
      setSalvando(false);
    }
  };
  return (
    <Modal titulo="Tags do contato" subtitulo={nome} icone="tag" onClose={onClose}>
      <div className="toggle-chips" role="group" aria-label="Tags">
        {tags.length === 0 && <span className="toggle-empty">Nenhuma tag cadastrada ainda (Configurações → Tags).</span>}
        {tags.map((t) => {
          const on = sel.includes(t.id);
          return (
            <button
              key={t.id}
              type="button"
              aria-pressed={on}
              className={`toggle-chip ${on ? "on" : ""}`}
              style={on ? { background: t.color, borderColor: t.color, color: corDoTexto(t.color) } : undefined}
              onClick={() => toggle(t.id)}
            >
              {on ? <Icon name="check" size={14} /> : <span className="dot" style={{ background: t.color }} />}{t.label}
            </button>
          );
        })}
      </div>
      {erro && <div className="error">{erro}</div>}
      <div className="modal-actions">
        <span className="muted small spacer">{sel.length === 1 ? "1 tag marcada" : `${sel.length} tags marcadas`}</span>
        <button onClick={onClose}>Cancelar</button>
        <button className="primary" disabled={salvando} onClick={salvar}><Icon name="check" size={16} />{salvando ? "Salvando…" : "Salvar"}</button>
      </div>
    </Modal>
  );
}

function EncaminharModal({ quantidade, onClose, onOk }) {
  const [busca, setBusca] = useState("");
  const [lista, setLista] = useState([]);
  const [escolhidos, setEscolhidos] = useState([]); // [{ id, nome }]
  const [erro, setErro] = useState("");
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => {
      api("/contacts", { params: { filter: "all", q: busca.trim() || undefined, perPage: 30 } })
        .then((r) => setLista(r.data))
        .catch((e) => setErro(e.message));
    }, 200);
    return () => clearTimeout(t);
  }, [busca]);

  const toggle = (c) => {
    const nome = c.internalName || c.name;
    setEscolhidos((atual) => {
      if (atual.some((x) => x.id === c.id)) return atual.filter((x) => x.id !== c.id);
      if (atual.length >= 10) {
        setErro("Escolha até 10 conversas por vez");
        return atual;
      }
      setErro("");
      return [...atual, { id: c.id, nome }];
    });
  };

  const confirmar = async () => {
    setEnviando(true);
    setErro("");
    try {
      await onOk(escolhidos);
    } catch (e) {
      setErro(e.message);
      setEnviando(false);
    }
  };

  return (
    <Modal titulo={`Encaminhar ${quantidade === 1 ? "1 mensagem" : `${quantidade} mensagens`}`} subtitulo="Escolha até 10 conversas" icone="forward" onClose={enviando ? () => {} : onClose} largura="520px">
      <div className="search-box">
        <Icon name="search" size={16} />
        <input autoFocus placeholder="Buscar conversa por nome ou número" value={busca} onChange={(e) => setBusca(e.target.value)} aria-label="Buscar conversa" />
      </div>
      {escolhidos.length > 0 && (
        <div className="picked">
          {escolhidos.map((c) => (
            <button key={c.id} type="button" className="chip" onClick={() => setEscolhidos((a) => a.filter((x) => x.id !== c.id))} title="Tirar">
              {c.nome}<Icon name="x" size={12} />
            </button>
          ))}
        </div>
      )}
      <ul className="pick-list">
        {lista.length === 0 && <li className="muted small" style={{ cursor: "default" }}>Nenhuma conversa encontrada.</li>}
        {lista.map((c) => {
          const marcado = escolhidos.some((x) => x.id === c.id);
          return (
            <li key={c.id} className={marcado ? "sel" : ""} onClick={() => toggle(c)}>
              <span className={`sel-check static ${marcado ? "on" : ""}`} aria-hidden="true">{marcado && <Icon name="check" size={13} />}</span>
              <Avatar nome={c.internalName || c.name} url={c.avatarUrl} grupo={c.isGroup} size={32} />
              <div className="grow" style={{ minWidth: 0 }}>
                <strong className="ellipsis" style={{ display: "block" }}>{c.internalName || c.name}</strong>
                <small className="muted">{c.isGroup ? "Grupo" : fmtNumero(c.data?.number)}</small>
              </div>
            </li>
          );
        })}
      </ul>
      <p className="muted small" style={{ margin: "8px 0 0" }}>Vai como “Encaminhada”, sem a assinatura do seu nome.</p>
      {erro && <div className="error">{erro}</div>}
      <div className="modal-actions">
        <button onClick={onClose} disabled={enviando}>Cancelar</button>
        <button className="primary" disabled={enviando || !escolhidos.length} onClick={confirmar}>
          <Icon name="forward" size={16} />{enviando ? "Encaminhando…" : `Encaminhar${escolhidos.length > 1 ? ` (${escolhidos.length})` : ""}`}
        </button>
      </div>
    </Modal>
  );
}

function AnexoModal({ arquivos, destino, legendaInicial, onClose, onEnviar }) {
  const [legenda, setLegenda] = useState((legendaInicial || "").trim());
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState("");
  const previews = useMemo(
    () => arquivos.map((f) => (f.type.startsWith("image/") ? URL.createObjectURL(f) : null)),
    [arquivos]
  );
  useEffect(() => () => previews.forEach((u) => u && URL.revokeObjectURL(u)), [previews]);

  const enviar = async () => {
    setErro("");
    setEnviando(true);
    try {
      await onEnviar(legenda.trim());
    } catch (e) {
      setErro(e.message);
      setEnviando(false);
    }
  };

  return (
    <Modal titulo={`Enviar ${arquivos.length > 1 ? `${arquivos.length} arquivos` : "arquivo"}`} subtitulo={`Para ${destino || "o contato"}`} icone="paperclip" onClose={enviando ? () => {} : onClose} largura="560px">
      <div className="anexos">
        {arquivos.map((f, i) => (
          <div key={i} className="anexo">
            {previews[i] ? <img src={previews[i]} alt={f.name} /> : <span className="media-doc-icon"><Icon name="file" size={22} /></span>}
            <div className="grow">
              <strong className="ellipsis" style={{ display: "block" }}>{f.name || "print.png"}</strong>
              <small className="muted">{fmtBytes(f.size)}</small>
            </div>
          </div>
        ))}
      </div>
      <label>
        Legenda (opcional{arquivos.length > 1 ? ", vai no primeiro arquivo" : ""})
        <textarea
          rows={2}
          value={legenda}
          onChange={(e) => setLegenda(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              if (!enviando) enviar();
            }
          }}
        />
      </label>
      {erro && <div className="error">{erro}</div>}
      <div className="modal-actions">
        <button onClick={onClose} disabled={enviando}>Cancelar</button>
        <button className="primary" onClick={enviar} disabled={enviando}>
          <Icon name="send" size={16} />{enviando ? "Enviando…" : "Enviar"}
        </button>
      </div>
    </Modal>
  );
}

const STATUS_ATENDENTE = { online: "Online", away: "Ausente", offline: "Offline" };
const ORDEM_STATUS = { online: 0, away: 1, offline: 2 };

function TransferirModal({ deps, usuarios, meId, atual, onClose, onOk }) {
  const [departmentId, setDep] = useState(atual?.departmentId || deps[0]?.id || "");
  const [userId, setUser] = useState("");
  const [comments, setComments] = useState("");
  const [erro, setErro] = useState("");
  const [salvando, setSalvando] = useState(false);
  const daEquipe = usuarios
    .filter((u) => !departmentId || u.departmentIds.includes(departmentId) || u.isAdmin)
    .sort((a, b) => (ORDEM_STATUS[a.status] ?? 3) - (ORDEM_STATUS[b.status] ?? 3) || a.name.localeCompare(b.name));
  const confirmar = async () => {
    setSalvando(true);
    try {
      await onOk({ departmentId, userId: userId || null, comments });
    } catch (e) {
      setErro(e.message);
      setSalvando(false);
    }
  };
  const destino = userId ? usuarios.find((u) => u.id === userId)?.name : "a fila";
  return (
    <Modal titulo="Transferir chamado" subtitulo={atual?.protocol ? `Protocolo #${atual.protocol}` : undefined} icone="transfer" onClose={onClose} largura="520px">
      <label>Departamento
        <select value={departmentId} onChange={(e) => { setDep(e.target.value); setUser(""); }}>
          {deps.map((d) => <option key={d.id} value={d.id}>{d.name}{d.id === atual?.departmentId ? " (atual)" : ""}</option>)}
        </select>
      </label>
      <div className="field-title">Quem vai atender</div>
      <div className="pick-cards" role="radiogroup" aria-label="Quem vai atender">
        <button type="button" role="radio" aria-checked={!userId} className={`pick-card ${!userId ? "sel" : ""}`} onClick={() => setUser("")}>
          <span className="pick-radio" aria-hidden="true" />
          <span className="pick-ico"><Icon name="inbox" size={17} /></span>
          <span className="grow">Deixar na fila do departamento<small>Quem estiver livre assume</small></span>
        </button>
        {daEquipe.map((u) => (
          <button key={u.id} type="button" role="radio" aria-checked={userId === u.id} className={`pick-card ${userId === u.id ? "sel" : ""}`} onClick={() => setUser(u.id)}>
            <span className="pick-radio" aria-hidden="true" />
            <span className="me-avatar"><Avatar nome={u.name} size={32} /><span className={`status-dot ${u.status}`} /></span>
            <span className="grow">{u.name}{u.id === meId ? " (você)" : ""}<small>{STATUS_ATENDENTE[u.status] || u.status}{u.id === atual?.userId ? " · atendendo agora" : ""}</small></span>
          </button>
        ))}
      </div>
      <label>Comentário (opcional)<textarea value={comments} onChange={(e) => setComments(e.target.value)} rows={2} placeholder="Ex.: cliente quer falar sobre o boleto de novembro" /></label>
      {erro && <div className="error">{erro}</div>}
      <div className="modal-actions">
        <button onClick={onClose}>Cancelar</button>
        <button className="primary" disabled={salvando} onClick={confirmar}><Icon name="transfer" size={16} />{salvando ? "Transferindo…" : `Transferir para ${destino}`}</button>
      </div>
    </Modal>
  );
}

function FecharModal({ assuntos, protocolo, onClose, onOk }) {
  const [sel, setSel] = useState([]);
  const [comments, setComments] = useState("");
  const [erro, setErro] = useState("");
  const [salvando, setSalvando] = useState(false);
  const toggle = (id) => setSel((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  const confirmar = async () => {
    setSalvando(true);
    try {
      await onOk({ ticketTopicIds: sel, comments });
    } catch (e) {
      setErro(e.message);
      setSalvando(false);
    }
  };
  return (
    <Modal titulo="Fechar chamado" subtitulo={protocolo ? `Protocolo #${protocolo}` : undefined} icone="check" onClose={onClose}>
      <div className="field-title">Assunto do atendimento</div>
      <div className="toggle-chips" role="group" aria-label="Assunto do atendimento">
        {assuntos.length === 0 && <span className="toggle-empty">Nenhum assunto cadastrado (Configurações → Assuntos).</span>}
        {assuntos.map((a) => {
          const on = sel.includes(a.id);
          return (
            <button key={a.id} type="button" aria-pressed={on} className={`toggle-chip ${on ? "on" : ""}`} onClick={() => toggle(a.id)}>
              {on && <Icon name="check" size={14} />}{a.name}
            </button>
          );
        })}
      </div>
      <label>Comentário (opcional)<textarea value={comments} onChange={(e) => setComments(e.target.value)} rows={3} placeholder="Como o atendimento terminou" /></label>
      {erro && <div className="error">{erro}</div>}
      <div className="modal-actions">
        <button onClick={onClose}>Cancelar</button>
        <button className="danger" disabled={salvando} onClick={confirmar}><Icon name="check" size={16} />{salvando ? "Fechando…" : "Fechar chamado"}</button>
      </div>
    </Modal>
  );
}
