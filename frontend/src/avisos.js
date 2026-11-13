// Aviso de mensagem nova: som, notificação na tela (Windows/navegador) e contador no título da aba.
// Avisa só o que é do atendente: chamado dele, ou na fila de um departamento dele (admin: toda a fila).
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getSocket } from "./socket";

const CHAVE_SOM = "intelisac.som";
const CHAVE_NOTIF = "intelisac.notificacoes";
const CHAVE_DISPENSOU = "intelisac.convite-notificacoes";
const TITULO = "InteliSac";

function ler(chave, padrao) {
  try {
    const v = localStorage.getItem(chave);
    return v === null ? padrao : v === "1";
  } catch {
    return padrao;
  }
}

function gravar(chave, v) {
  try {
    localStorage.setItem(chave, v ? "1" : "0");
  } catch {
    /* navegador sem armazenamento: vale só até recarregar */
  }
}

const suportaNotificacao = () => typeof window !== "undefined" && "Notification" in window;

// ----- som (gerado na hora, sem arquivo) -----
let ctx = null;
function audio() {
  const AC = window.AudioContext || window.webkitAudioContext;
  if (!AC) return null;
  if (!ctx) ctx = new AC();
  return ctx;
}

// O navegador só libera som depois de um clique ou tecla na página
function destravarAudio() {
  const c = audio();
  if (c && c.state === "suspended") c.resume().catch(() => {});
}

export function tocarSom() {
  const c = audio();
  if (!c || c.state !== "running") return;
  const t0 = c.currentTime;
  [
    [880, 0],
    [1318.5, 0.14],
  ].forEach(([freq, atraso]) => {
    const o = c.createOscillator();
    const g = c.createGain();
    o.type = "sine";
    o.frequency.value = freq;
    g.gain.setValueAtTime(0.0001, t0 + atraso);
    g.gain.exponentialRampToValueAtTime(0.22, t0 + atraso + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + atraso + 0.24);
    o.connect(g).connect(c.destination);
    o.start(t0 + atraso);
    o.stop(t0 + atraso + 0.26);
  });
}

// ----- regras -----
export function meInteressa(m, me) {
  if (!m || !me || m.isFromMe || m.type === "ticket") return false;
  const t = m.ticket;
  if (!t) return !!me.isAdmin;
  if (t.userId) return t.userId === me.id;
  return !!me.isAdmin || !t.departmentId || (me.departmentIds || []).includes(t.departmentId);
}

const ROTULO = { image: "📷 Imagem", sticker: "Figurinha", video: "🎥 Vídeo", audio: "🎵 Áudio", ptt: "🎤 Mensagem de voz", document: "📄 Documento" };

export function resumoAviso(m) {
  const corpo = m.text || ROTULO[m.type] || "Nova mensagem";
  const quem = m.data?.sender?.name || m.data?.sender?.number;
  return (quem ? `${quem}: ${corpo}` : corpo).slice(0, 180);
}

const focado = () => document.visibilityState === "visible" && document.hasFocus();
const conversaAberta = () => (window.location.pathname === "/" ? new URLSearchParams(window.location.search).get("contact") : null);

export function useAvisos(me) {
  const navigate = useNavigate();
  const [som, setSom] = useState(() => ler(CHAVE_SOM, true));
  const [notif, setNotif] = useState(() => ler(CHAVE_NOTIF, true));
  const [permissao, setPermissao] = useState(() => (suportaNotificacao() ? Notification.permission : "unsupported"));
  const [convite, setConvite] = useState(() => !ler(CHAVE_DISPENSOU, false));
  const atual = useRef({});
  atual.current = { som, notif, me, navigate };

  // Primeiro clique/tecla na página libera o som
  useEffect(() => {
    window.addEventListener("pointerdown", destravarAudio);
    window.addEventListener("keydown", destravarAudio);
    return () => {
      window.removeEventListener("pointerdown", destravarAudio);
      window.removeEventListener("keydown", destravarAudio);
    };
  }, []);

  useEffect(() => {
    let pendentes = 0;
    const titulo = () => {
      document.title = pendentes ? `(${pendentes}) ${TITULO}` : TITULO;
    };
    const voltou = () => {
      if (focado()) {
        pendentes = 0;
        titulo();
      }
    };
    const onMsg = (m) => {
      const { som: comSom, notif: comNotif, me: eu, navigate: ir } = atual.current;
      if (!meInteressa(m, eu)) return;
      const naTela = focado();
      if (naTela && conversaAberta() === m.contactId) return; // já está lendo essa conversa
      if (comSom) tocarSom();
      if (naTela) return; // a lista já mostra a conversa com o número de não lidas
      pendentes += 1;
      titulo();
      if (comNotif && suportaNotificacao() && Notification.permission === "granted") {
        try {
          const n = new Notification(m.contactName || "Nova mensagem", {
            body: resumoAviso(m),
            tag: `intelisac-${m.contactId}`,
            renotify: true,
          });
          n.onclick = () => {
            window.focus();
            ir(`/?contact=${m.contactId}`);
            n.close();
          };
        } catch {
          /* navegador que não deixa criar notificação por aqui */
        }
      }
    };
    const s = getSocket();
    s.on("message.created", onMsg);
    window.addEventListener("focus", voltou);
    document.addEventListener("visibilitychange", voltou);
    return () => {
      s.off("message.created", onMsg);
      window.removeEventListener("focus", voltou);
      document.removeEventListener("visibilitychange", voltou);
      document.title = TITULO;
    };
  }, []);

  const alternarSom = useCallback(() => {
    setSom((v) => {
      gravar(CHAVE_SOM, !v);
      if (!v) {
        destravarAudio();
        setTimeout(tocarSom, 60); // amostra do som ao ligar
      }
      return !v;
    });
  }, []);

  const dispensarConvite = useCallback(() => {
    gravar(CHAVE_DISPENSOU, true);
    setConvite(false);
  }, []);

  // Liga/desliga. Na primeira vez pede a permissão do navegador. Devolve o resultado para a tela avisar.
  const alternarNotificacao = useCallback(async () => {
    if (!suportaNotificacao()) return "unsupported";
    let p = Notification.permission;
    if (p === "default") {
      p = await Notification.requestPermission();
      setPermissao(p);
      dispensarConvite();
      if (p === "granted") {
        gravar(CHAVE_NOTIF, true);
        setNotif(true);
        return "on";
      }
      return p;
    }
    setPermissao(p);
    if (p === "denied") return "denied";
    const novo = !notif;
    gravar(CHAVE_NOTIF, novo);
    setNotif(novo);
    return novo ? "on" : "off";
  }, [notif, dispensarConvite]);

  return {
    som,
    alternarSom,
    notificacoes: notif && permissao === "granted",
    permissao,
    alternarNotificacao,
    mostrarConvite: convite && permissao === "default",
    dispensarConvite,
  };
}
