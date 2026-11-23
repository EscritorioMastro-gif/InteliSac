// Texto de mensagem com os links clicáveis: abrem em outra aba, sem dar ao site acesso a esta
// tela (noopener) e sem contar de onde veio (noreferrer: o endereço tem o código da conversa).
// O texto mostrado é o próprio endereço; passando o mouse aparece o endereço completo de destino.
import { Fragment, useMemo } from "react";
import { separarLinks } from "../formato";

export default function TextoComLinks({ texto }) {
  const partes = useMemo(() => separarLinks(texto), [texto]);
  return partes.map((p, i) =>
    p.href ? (
      <a key={i} className="msg-link" href={p.href} target="_blank" rel="noopener noreferrer" title={`Abrir em outra aba: ${p.href}`}>
        {p.texto}
      </a>
    ) : (
      <Fragment key={i}>{p.texto}</Fragment>
    )
  );
}
