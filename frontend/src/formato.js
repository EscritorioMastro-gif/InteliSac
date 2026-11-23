// Formatos usados em várias telas.

// 5516991452133 → +55 16 99145-2133
export function fmtNumero(n) {
  const d = String(n || "").replace(/\D/g, "");
  if (d.startsWith("55") && (d.length === 12 || d.length === 13)) {
    const local = d.slice(4);
    return `+55 ${d.slice(2, 4)} ${local.slice(0, local.length - 4)}-${local.slice(-4)}`;
  }
  return d ? `+${d}` : "";
}

// ----- links dentro do texto das mensagens -----
// Só vira link o que começa com http://, https:// ou www. (nada de javascript:, data: ou outros esquemas).
const URL_RE = /(?:https?:\/\/|www\.)[^\s<>"'`]+/gi;
const PONTUACAO_FINAL = /[.,;:!?…*_~'"»]$/; // fim de frase ou marca do WhatsApp (*negrito*, _itálico_)
const FECHA = { ")": "(", "]": "[", "}": "{" };

// "veja https://site.com/a." → o ponto é da frase; "(https://x.com/a_(b))" → o último ")" é da frase
function apararFim(u) {
  for (;;) {
    const ult = u.slice(-1);
    if (PONTUACAO_FINAL.test(ult)) {
      u = u.slice(0, -1);
      continue;
    }
    if (FECHA[ult] && u.split(ult).length - 1 > u.split(FECHA[ult]).length - 1) {
      u = u.slice(0, -1);
      continue;
    }
    return u;
  }
}

function hrefDe(u) {
  try {
    const url = new URL(/^www\./i.test(u) ? `https://${u}` : u);
    if (url.protocol !== "http:" && url.protocol !== "https:") return null;
    if (!url.hostname || (!url.hostname.includes(".") && url.hostname !== "localhost")) return null;
    return url.href;
  } catch {
    return null;
  }
}

// "Oi, veja https://x.com." → [{ texto: "Oi, veja " }, { texto: "https://x.com", href: "https://x.com/" }, { texto: "." }]
export function separarLinks(texto) {
  const s = String(texto ?? "");
  const partes = [];
  let pos = 0;
  for (const m of s.matchAll(URL_RE)) {
    const ini = m.index;
    // "www." colado em outra palavra ou num e-mail (joao@www.x) não é link; "_www.x_" (itálico) é
    if (/^www\./i.test(m[0]) && ini > 0 && /[A-Za-z0-9À-ÿ@/.-]/.test(s[ini - 1])) continue;
    const bruto = apararFim(m[0]);
    const href = bruto.length > 4 ? hrefDe(bruto) : null;
    if (!href) continue;
    if (ini > pos) partes.push({ texto: s.slice(pos, ini) });
    partes.push({ texto: bruto, href });
    pos = ini + bruto.length;
  }
  if (pos < s.length) partes.push({ texto: s.slice(pos) });
  return partes;
}

// Texto escuro em tag de cor clara (amarelo, verde-claro...) e branco nas escuras
export function corDoTexto(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex || "");
  if (!m) return "#fff";
  const n = parseInt(m[1], 16);
  return 0.299 * ((n >> 16) & 255) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255) > 165 ? "#17282b" : "#fff";
}
