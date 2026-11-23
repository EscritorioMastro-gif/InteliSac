// Prévia da conversa: aparece ao lado da lista quando o mouse fica 1,5 s parado num contato.
// Mostra só as últimas mensagens: não abre a conversa e não marca como lida.
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { api } from "../api";
import { getSocket } from "../socket";
import Avatar from "./Avatar";
import Icon from "./Icon";
import TextoComLinks from "./TextoComLinks";

const QUANTAS = 15;
const LARGURA = 360;

const ROTULO = { image: "Imagem", sticker: "Figurinha", video: "Vídeo", audio: "Áudio", ptt: "Mensagem de voz", document: "Documento" };
const ICONE = { image: "image", sticker: "image", audio: "volume", ptt: "mic" };

// Hoje: "14:32". Outro dia: "17/11 14:32"
function quando(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const hora = d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  if (d.toDateString() === new Date().toDateString()) return hora;
  return `${d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })} ${hora}`;
}

function Anexo({ m }) {
  const [falhou, setFalhou] = useState(false);
  const f = m.data.file;
  if ((m.type === "image" || m.type === "sticker") && m.fileUrl && !falhou) {
    return <img className="previa-img" src={m.fileUrl} alt={f.name || ROTULO[m.type]} onError={() => setFalhou(true)} />;
  }
  return (
    <div className="previa-anexo">
      <Icon name={ICONE[m.type] || "file"} size={14} />
      <span>{ROTULO[m.type] || "Arquivo"}{m.type === "document" && f.name ? ` · ${f.name}` : ""}</span>
    </div>
  );
}

function Mensagem({ m, meId, nomeUser }) {
  if (m.type === "ticket") return <div className="previa-evento">{m.text} · {quando(m.createdAt)}</div>;
  const d = m.data || {};
  let autor = null;
  if (!m.isFromMe) autor = d.sender ? d.sender.name || d.sender.number || "Participante" : null;
  else if (m.userId) autor = m.userId === meId ? "Você" : nomeUser(m.userId);
  else if (d.api) autor = `Integração · ${d.api.keyName}`;
  else if (d.origin === "device") autor = "Pelo celular / outro aparelho";
  return (
    <div className={`previa-msg ${m.isFromMe ? "me" : "them"} ${d.error ? "failed" : ""}`}>
      {autor && <div className="previa-autor">{autor}</div>}
      {d.deleted ? (
        <div className="previa-anexo"><Icon name="ban" size={13} /><span>Mensagem apagada</span></div>
      ) : (
        <>
          {d.file && <Anexo m={m} />}
          {m.text && <div className="previa-texto"><TextoComLinks texto={m.text} /></div>}
          {!d.file && !m.text && <div className="previa-anexo"><span>[Mensagem]</span></div>}
        </>
      )}
      <div className="previa-hora">{quando(m.createdAt)}{d.error && <span className="fail"> · não enviada</span>}</div>
    </div>
  );
}

export default function PreviaConversa({ contato, ancora, meId, nomeUser, onMouseEnter, onMouseLeave }) {
  const [mensagens, setMensagens] = useState(null); // null = carregando
  const [erro, setErro] = useState("");
  const [topo, setTopo] = useState(null);
  const caixa = useRef(null);
  const lista = useRef(null);
  const nome = contato.internalName || contato.name;

  useEffect(() => {
    let vivo = true;
    api("/messages", { params: { contactId: contato.id, perPage: QUANTAS } })
      .then((r) => vivo && setMensagens(r.data))
      .catch((e) => vivo && setErro(e.message));
    // Mensagem que chega (ou muda) com a prévia aberta aparece na hora
    const s = getSocket();
    const nova = (m) => {
      if (m.contactId === contato.id) setMensagens((prev) => (!prev || prev.some((x) => x.id === m.id) ? prev : [...prev, m]));
    };
    const mudou = (m) => {
      if (m.contactId === contato.id) setMensagens((prev) => prev && prev.map((x) => (x.id === m.id ? { ...m, fileUrl: m.fileUrl || x.fileUrl } : x)));
    };
    s.on("message.created", nova);
    s.on("message.updated", mudou);
    return () => {
      vivo = false;
      s.off("message.created", nova);
      s.off("message.updated", mudou);
    };
  }, [contato.id]);

  // Fica na altura do contato, sem sair da tela; a lista começa nas mensagens mais novas
  useLayoutEffect(() => {
    if (lista.current) lista.current.scrollTop = lista.current.scrollHeight;
    if (caixa.current) setTopo(Math.max(8, Math.min(ancora.top - 8, window.innerHeight - caixa.current.offsetHeight - 8)));
  }, [mensagens, erro, ancora]);

  // A primeira das não lidas: conta as mensagens do cliente de trás para a frente
  let primeiraNaoLida = null;
  if (mensagens && contato.unread > 0) {
    let faltam = contato.unread;
    for (let i = mensagens.length - 1; i >= 0 && faltam > 0; i--) {
      if (!mensagens[i].isFromMe && mensagens[i].type !== "ticket") {
        faltam -= 1;
        primeiraNaoLida = mensagens[i].id;
      }
    }
  }

  const esquerda = Math.max(8, Math.min(ancora.right + 8, window.innerWidth - LARGURA - 8));
  return (
    <div
      ref={caixa}
      className="previa"
      role="tooltip"
      aria-label={`Prévia da conversa com ${nome}`}
      style={{ left: esquerda, top: topo ?? ancora.top, visibility: topo === null ? "hidden" : "visible" }}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <div className="previa-head">
        <Avatar nome={nome} url={contato.avatarUrl} grupo={contato.isGroup} size={32} />
        <div className="previa-nome">
          <strong>{nome}</strong>
          <small>Prévia · não marca como lida</small>
        </div>
        {contato.unread > 0 && <span className="badge" title={contato.unread === 1 ? "1 não lida" : `${contato.unread} não lidas`}>{contato.unread}</span>}
      </div>
      <div className="previa-msgs" ref={lista}>
        {erro && <div className="previa-vazio">{erro}</div>}
        {!erro && mensagens === null && <div className="previa-vazio">Carregando…</div>}
        {!erro && mensagens?.length === 0 && <div className="previa-vazio">Nenhuma mensagem nesta conversa ainda.</div>}
        {!erro && mensagens?.map((m) => (
          <div key={m.id} className="previa-item">
            {m.id === primeiraNaoLida && <div className="previa-novas">{contato.unread === 1 ? "Não lida" : "Não lidas"}</div>}
            <Mensagem m={m} meId={meId} nomeUser={nomeUser} />
          </div>
        ))}
      </div>
      <div className="previa-pe">Clique no contato para abrir a conversa</div>
    </div>
  );
}
