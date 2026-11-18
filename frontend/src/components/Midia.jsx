// Conteúdo de arquivo dentro de uma mensagem: foto, figurinha, vídeo, áudio ou documento.
import { useRef } from "react";
import Icon from "./Icon";

// Tamanho máximo de arquivo: o mesmo do backend (storage.MAX_BYTES) e do gateway do WhatsApp
export const MAX_ARQUIVO_MB = 80;
export const MAX_ARQUIVO = MAX_ARQUIVO_MB * 1024 * 1024;

export function fmtBytes(n) {
  if (!n && n !== 0) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1).replace(".", ",")} MB`;
}

function extensao(nome) {
  const m = /\.([a-z0-9]{1,5})$/i.exec(nome || "");
  return m ? m[1].toUpperCase() : "ARQUIVO";
}

// PDF dá para ver dentro do sistema (o navegador mostra num quadro); os outros só baixando
export function ehPdf(f) {
  return /pdf/i.test(f?.mimetype || "");
}

export default function Midia({ m, onAbrirImagem, onAbrirPdf, onLinkExpirado }) {
  const avisou = useRef(false);
  const f = m.data?.file;
  if (!f) return null;
  const expirou = () => {
    // o link assinado vale 1 h; se a conversa ficou aberta mais que isso, recarrega uma vez
    if (!avisou.current) {
      avisou.current = true;
      onLinkExpirado?.();
    }
  };
  if (!m.fileUrl) {
    return (
      <div className="media-missing"><Icon name="file" size={16} /> Arquivo indisponível no momento</div>
    );
  }
  const baixar = (
    <a className="media-dl" href={m.downloadUrl || m.fileUrl} target="_blank" rel="noreferrer" title={`Baixar ${f.name}`}>
      <Icon name="download" size={14} /> Baixar
    </a>
  );
  if (m.type === "image" || m.type === "sticker") {
    return (
      <div className="media">
        <img
          className={m.type === "sticker" ? "media-sticker" : "media-img"}
          src={m.fileUrl}
          alt={f.name}
          loading="lazy"
          onError={expirou}
          onClick={() => onAbrirImagem?.(m)}
        />
        {m.type === "image" && baixar}
      </div>
    );
  }
  if (m.type === "video") {
    return (
      <div className="media">
        <video className="media-video" src={m.fileUrl} controls preload="metadata" onError={expirou} />
        {baixar}
      </div>
    );
  }
  if (m.type === "audio" || m.type === "ptt") {
    return (
      <div className="media">
        {m.type === "ptt" && <span className="media-voice-label"><Icon name="mic" size={13} /> Mensagem de voz</span>}
        <audio className="media-audio" src={m.fileUrl} controls preload="metadata" onError={expirou} />
        {baixar}
      </div>
    );
  }
  if (ehPdf(f) && onAbrirPdf) {
    return (
      <div className="media-doc">
        <button type="button" className="media-doc-main" onClick={() => onAbrirPdf(m)} title={`Visualizar ${f.name}`}>
          <span className="media-doc-icon"><Icon name="file" size={22} /><em>PDF</em></span>
          <span className="media-doc-info">
            <strong>{f.name}</strong>
            <small>{fmtBytes(f.size)}</small>
          </span>
        </button>
        <span className="media-doc-acoes">
          <button type="button" className="media-doc-btn" onClick={() => onAbrirPdf(m)} title="Visualizar">
            <Icon name="eye" size={15} /> Visualizar
          </button>
          <a className="media-doc-btn" href={m.downloadUrl || m.fileUrl} target="_blank" rel="noreferrer" title={`Baixar ${f.name}`}>
            <Icon name="download" size={15} /> Baixar
          </a>
        </span>
      </div>
    );
  }
  return (
    <a className="media-doc" href={m.downloadUrl || m.fileUrl} target="_blank" rel="noreferrer" title={`Baixar ${f.name}`}>
      <span className="media-doc-icon"><Icon name="file" size={22} /><em>{extensao(f.name)}</em></span>
      <span className="media-doc-info">
        <strong>{f.name}</strong>
        <small>{fmtBytes(f.size)}</small>
      </span>
      <Icon name="download" size={18} />
    </a>
  );
}
