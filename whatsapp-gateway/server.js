// InteliSac — gateway do WhatsApp por QR code (Baileys / protocolo do WhatsApp Web).
//
// Cada conexão do tipo "whatsapp" do InteliSac vira uma sessão aqui, identificada pelo id da conexão.
// - Recebe do backend: iniciar sessão (gera QR), desconectar, enviar mensagem.
// - Envia ao backend (POST /api/v1/gateway/events): status/QR da conexão e cada mensagem recebida
//   ou enviada pelo celular/outros aparelhos, na hora em que chega.
// A sessão fica salva em SESSIONS_DIR/<id>; ao reiniciar o gateway, reconecta sozinho sem novo QR.
//
// Rodar:  node --env-file=.env server.js

import { createServer } from "node:http";
import { timingSafeEqual } from "node:crypto";
import { mkdir, readdir, readFile, rm } from "node:fs/promises";
import path from "node:path";
import * as baileys from "@whiskeysockets/baileys";
import pino from "pino";
import QRCode from "qrcode";
import { contatoDoVcard } from "./vcard.js";

const makeWASocket = baileys.makeWASocket ?? baileys.default?.default ?? baileys.default;
const {
  Browsers,
  DisconnectReason,
  downloadMediaMessage,
  fetchLatestBaileysVersion,
  generateMessageIDV2,
  getContentType,
  normalizeMessageContent,
  useMultiFileAuthState,
} = baileys;

const PORT = Number(process.env.PORT || 8020);
// No PC só a própria máquina acessa (127.0.0.1). No Render: HOST=0.0.0.0 (rede interna, sem endereço público).
const HOST = process.env.HOST || "127.0.0.1";
// O Render entrega o endereço interno da API como "nome:porta" (sem http://)
const comHttp = (u) => (u.includes("://") ? u : `http://${u}`);
const BACKEND_URL = comHttp(process.env.BACKEND_URL || "http://127.0.0.1:8010").replace(/\/$/, "");
const SECRET = process.env.GATEWAY_SECRET || "";
const SESSIONS_DIR = path.resolve(process.env.SESSIONS_DIR || "./sessions");
const ID_RE = /^[A-Za-z0-9-]{1,64}$/;

if (!SECRET) {
  console.error("GATEWAY_SECRET não definido. Copie .env.example para .env.");
  process.exit(1);
}
// No servidor (Render), segredo curto não sobe: é ele que protege o envio de mensagens.
if (process.env.RENDER === "true" && SECRET.length < 32) {
  console.error("GATEWAY_SECRET curto demais para produção (mínimo 32 caracteres).");
  process.exit(1);
}
const SECRET_BUF = Buffer.from(SECRET);
function segredoConfere(dado) {
  const b = Buffer.from(String(dado || ""));
  return b.length === SECRET_BUF.length && timingSafeEqual(b, SECRET_BUF);
}

const logger = pino({ level: process.env.LOG_LEVEL || "warn" });
const log = (...args) => console.log(new Date().toISOString(), ...args);

// ---------------------------------------------------------------------------
// Entrega de eventos ao backend: fila em memória, em ordem, com nova tentativa
// se o backend estiver fora do ar (nenhuma mensagem é descartada por isso).
// ---------------------------------------------------------------------------
const queue = [];
let flushing = false;

// A fila guarda o evento já em texto (JSON): um arquivo grande fica na memória uma vez só.
function postEvent(event) {
  queue.push(JSON.stringify(event));
  if (queue.length > 10000) queue.shift();
  flush();
}

// Evento com arquivo (até ~107 MB em base64) demora mais: o backend ainda guarda no Storage antes
// de responder. 15 s + 2 s por MB (se cortasse antes, o mesmo arquivo seria mandado de novo).
const prazoDoEvento = (corpo) => 15000 + Math.ceil(corpo.length / 1048576) * 2000;

async function flush() {
  if (flushing) return;
  flushing = true;
  while (queue.length) {
    const corpo = queue[0];
    try {
      const res = await fetch(`${BACKEND_URL}/api/v1/gateway/events`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Gateway-Secret": SECRET },
        body: corpo,
        signal: AbortSignal.timeout(prazoDoEvento(corpo)),
      });
      if (res.status >= 500) throw new Error(`backend respondeu ${res.status}`);
      if (!res.ok) log("evento recusado pelo backend:", res.status, (await res.text()).slice(0, 300));
      queue.shift();
    } catch (e) {
      log(`backend indisponível (${e.message}); ${queue.length} evento(s) aguardando, nova tentativa em 5s`);
      flushing = false;
      setTimeout(flush, 5000);
      return;
    }
  }
  flushing = false;
}

// ---------------------------------------------------------------------------
// Sessões
// ---------------------------------------------------------------------------
const sessions = new Map();
const sessionDir = (id) => path.join(SESSIONS_DIR, id);

function setStatus(s, status, { qr = null, reason = null, me = s.me } = {}) {
  Object.assign(s, { status, qr, reason, me });
  postEvent({ type: "status", serviceId: s.id, status, qr, reason, me });
}

function publicState(s) {
  return { serviceId: s.id, status: s.status, reason: s.reason, me: s.me, hasQr: !!s.qr };
}

async function startSession(id) {
  let s = sessions.get(id);
  if (s && ["connecting", "qr", "connected"].includes(s.status)) return s;
  if (!s) {
    s = { id, status: "disconnected", qr: null, reason: null, me: null, sock: null, sent: new Map(), retries: 0 };
    sessions.set(id, s);
  }
  s.stopped = false;
  s.qrCount = 0;
  await connect(s);
  return s;
}

async function connect(s) {
  await mkdir(sessionDir(s.id), { recursive: true });
  const { state, saveCreds } = await useMultiFileAuthState(sessionDir(s.id));
  let version;
  try {
    ({ version } = await fetchLatestBaileysVersion());
  } catch {
    /* sem internet para consultar a versão: usa a embutida na biblioteca */
  }
  setStatus(s, "connecting");
  const sock = makeWASocket({
    ...(version ? { version } : {}),
    auth: state,
    logger,
    browser: Browsers?.windows ? Browsers.windows("InteliSac") : ["InteliSac", "Chrome", "1.0"],
    markOnlineOnConnect: false,
    syncFullHistory: false,
    generateHighQualityLinkPreview: false,
  });
  s.sock = sock;
  s.connectedAt = null;
  sock.ev.on("creds.update", saveCreds);
  sock.ev.on("connection.update", (u) => onConnectionUpdate(s, sock, u).catch((e) => log(`[${s.id}] erro em connection.update`, e)));
  sock.ev.on("messages.upsert", (m) => onMessages(s, sock, m).catch((e) => log(`[${s.id}] erro ao processar mensagem`, e)));
  sock.ev.on("messages.update", (u) => onStatus(s, u));
}

// ✓ / ✓✓ / ✓✓ azul: status das mensagens que NÓS enviamos (pelo InteliSac, celular ou outro aparelho)
const ACK = { 0: "error", 1: "pending", 2: "sent", 3: "delivered", 4: "read", 5: "played" };

function onStatus(s, updates) {
  for (const { key, update } of updates || []) {
    // Mensagem editada (pelo cliente, pelo celular ou por outro aparelho): manda o texto novo
    const editada = update?.message?.editedMessage?.message;
    if (key?.id && editada) {
      const texto = textoDe(normalizeMessageContent(editada));
      if (texto) postEvent({ type: "edit", serviceId: s.id, messageId: key.id, text: texto, fromMe: !!key.fromMe });
      continue;
    }
    if (!key?.id || !key.fromMe || update?.status === undefined || update?.status === null) continue;
    const ack = ACK[update.status];
    if (ack) postEvent({ type: "ack", serviceId: s.id, messageId: key.id, ack });
  }
}

// Nome dos grupos (cache de 1 h para não consultar o WhatsApp a cada mensagem)
const nomesGrupo = new Map();
async function nomeDoGrupo(sock, jid) {
  const c = nomesGrupo.get(jid);
  if (c && Date.now() - c.em < 3600_000) return c.nome;
  try {
    const meta = await sock.groupMetadata(jid);
    nomesGrupo.set(jid, { nome: meta?.subject || null, em: Date.now() });
    return meta?.subject || null;
  } catch {
    return c?.nome || null;
  }
}

async function onConnectionUpdate(s, sock, { connection, lastDisconnect, qr }) {
  if (sock !== s.sock) return; // evento de um socket antigo
  if (qr) {
    s.qrCount += 1;
    const dataUrl = await QRCode.toDataURL(qr, { margin: 1, width: 320 });
    setStatus(s, "qr", { qr: dataUrl });
    log(`[${s.id}] QR code gerado (${s.qrCount})`);
  }
  if (connection === "open") {
    s.retries = 0;
    s.qrCount = 0;
    s.connectedAt = Date.now();
    const u = sock.user || {};
    const number = (u.id || "").split(":")[0].split("@")[0] || null;
    setStatus(s, "connected", { me: { jid: u.id || null, lid: u.lid || null, name: u.name || u.verifiedName || null, number } });
    log(`[${s.id}] conectado (${number})`);
  }
  if (connection === "close") {
    const code = lastDisconnect?.error?.output?.statusCode;
    s.sock = null;
    if (s.stopped) return;
    if (code === DisconnectReason.loggedOut) {
      await rm(sessionDir(s.id), { recursive: true, force: true });
      setStatus(s, "disconnected", { reason: "logged_out", me: null });
      log(`[${s.id}] aparelho removido pelo celular — será preciso ler o QR de novo`);
      return;
    }
    if (!s.connectedAt && s.qrCount > 0 && code === DisconnectReason.timedOut) {
      await rm(sessionDir(s.id), { recursive: true, force: true }); // nunca pareou: nada a guardar
      setStatus(s, "disconnected", { reason: "qr_timeout", me: null });
      log(`[${s.id}] QR code expirou sem leitura`);
      return;
    }
    s.retries += 1;
    const wait = code === DisconnectReason.restartRequired ? 0 : Math.min(30000, 2000 * s.retries);
    setStatus(s, "connecting", { reason: `reconectando (código ${code ?? "?"})` });
    log(`[${s.id}] conexão caiu (código ${code}); reconectando em ${wait / 1000}s`);
    setTimeout(() => {
      if (!s.stopped) connect(s).catch((e) => log(`[${s.id}] falha ao reconectar`, e));
    }, wait);
  }
}

// ---------------------------------------------------------------------------
// Mensagens
// ---------------------------------------------------------------------------
const IGNORED_TYPES = new Set([
  "protocolMessage",
  "senderKeyDistributionMessage",
  "reactionMessage",
  "pollUpdateMessage",
  "messageContextInfo",
  "keepInChatMessage",
  "editedMessage",
  "encReactionMessage",
  // Avisos internos do WhatsApp que chegam junto quando alguém edita ou apaga uma mensagem
  // (o texto novo / o "apagada" já vêm por outro caminho): não viram mensagem na conversa
  "secretEncryptedMessage",
  "encEventResponseMessage",
  "encCommentMessage",
  "pinInChatMessage",
]);

// Números do WhatsApp podem vir como Long (protobuf)
function toNum(t) {
  if (!t) return null;
  if (typeof t === "number") return t;
  if (typeof t.toNumber === "function") return t.toNumber();
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}
const toSeconds = toNum;

// Mesmo limite do backend (storage.MAX_BYTES) e da tela: 80 MB por arquivo
const MAX_MEDIA_BYTES = Number(process.env.MAX_MEDIA_MB || 80) * 1024 * 1024;

async function baixarMidia(s, sock, msg, info) {
  if (info.size && info.size > MAX_MEDIA_BYTES) {
    return { error: `arquivo grande demais (${Math.round(info.size / 1048576)} MB)` };
  }
  try {
    const buf = await downloadMediaMessage(msg, "buffer", {}, { logger, reuploadRequest: sock.updateMediaMessage });
    if (buf.length > MAX_MEDIA_BYTES) return { error: `arquivo grande demais (${Math.round(buf.length / 1048576)} MB)` };
    return { base64: buf.toString("base64"), mimetype: info.mimetype, fileName: info.fileName, size: buf.length };
  } catch (e) {
    log(`[${s.id}] não consegui baixar a mídia ${msg.key?.id}: ${e.message}`);
    return { error: `não consegui baixar o arquivo: ${e.message}` };
  }
}

// Mídia: text = legenda ou rótulo (se o arquivo não puder ser baixado, o rótulo aparece na conversa)
function midia(type, node, label, fileName) {
  const caption = node?.caption || "";
  return {
    type,
    text: caption || label,
    caption,
    label,
    media: { mimetype: node?.mimetype || null, fileName: fileName || null, size: toNum(node?.fileLength) },
  };
}

// Texto de uma mensagem (ou a legenda do arquivo)
function textoDe(c) {
  if (!c) return null;
  return (
    c.conversation || c.extendedTextMessage?.text || c.imageMessage?.caption || c.videoMessage?.caption ||
    c.documentMessage?.caption || null
  );
}

function parseContent(ctype, c) {
  switch (ctype) {
    case "conversation":
      return { type: "chat", text: c.conversation };
    case "extendedTextMessage":
      return { type: "chat", text: c.extendedTextMessage?.text };
    case "imageMessage":
      return midia("image", c.imageMessage, "[Imagem]");
    case "videoMessage":
      return midia("video", c.videoMessage, "[Vídeo]");
    case "audioMessage":
      return midia(c.audioMessage?.ptt ? "ptt" : "audio", c.audioMessage, "[Áudio]");
    case "documentMessage":
      return midia("document", c.documentMessage, `[Documento] ${c.documentMessage?.fileName || ""}`.trim(), c.documentMessage?.fileName);
    case "stickerMessage":
      return midia("sticker", c.stickerMessage, "[Figurinha]");
    case "locationMessage":
    case "liveLocationMessage": {
      const l = c[ctype] || {};
      return { type: "location", text: `[Localização] https://maps.google.com/?q=${l.degreesLatitude},${l.degreesLongitude}` };
    }
    case "contactMessage":
      return {
        type: "vcard",
        text: `[Contato] ${c.contactMessage?.displayName || ""}`.trim(),
        contacts: [contatoDoVcard(c.contactMessage)],
      };
    case "contactsArrayMessage": {
      const lista = c.contactsArrayMessage?.contacts || [];
      return { type: "vcard", text: `[Contatos] ${lista.map((x) => x.displayName).join(", ")}`, contacts: lista.map(contatoDoVcard) };
    }
    case "buttonsResponseMessage":
      return { type: "chat", text: c.buttonsResponseMessage?.selectedDisplayText };
    case "listResponseMessage":
      return { type: "chat", text: c.listResponseMessage?.title };
    case "templateButtonReplyMessage":
      return { type: "chat", text: c.templateButtonReplyMessage?.selectedDisplayText };
    default:
      return { type: "chat", text: `[${ctype}]` };
  }
}

async function resolvePhoneJid(sock, key) {
  for (const j of [key.remoteJidAlt, key.senderPn, key.remoteJid]) {
    if (j && j.endsWith("@s.whatsapp.net")) return j;
  }
  if (key.remoteJid?.endsWith("@lid")) {
    try {
      const pn = await sock.signalRepository?.lidMapping?.getPNForLID?.(key.remoteJid);
      if (pn) return pn.includes("@") ? pn : `${pn}@s.whatsapp.net`;
    } catch {
      /* sem mapeamento LID → número ainda */
    }
  }
  return null;
}

// Quem mandou a mensagem dentro de um grupo (número quando o WhatsApp informa)
async function remetenteDoGrupo(sock, key) {
  const part = key.participant || "";
  let pn = [key.participantAlt, part].find((j) => j && j.endsWith("@s.whatsapp.net")) || null;
  if (!pn && part.endsWith("@lid")) {
    try {
      const r = await sock.signalRepository?.lidMapping?.getPNForLID?.(part);
      if (r) pn = r.includes("@") ? r : `${r}@s.whatsapp.net`;
    } catch {
      /* sem mapeamento */
    }
  }
  return { jid: part || null, number: pn ? pn.split("@")[0].split(":")[0] : null };
}

async function onMessages(s, sock, { messages, type }) {
  for (const msg of messages || []) {
    const key = msg.key || {};
    const jid = key.remoteJid || "";
    if (!jid || jid.endsWith("@broadcast") || jid.endsWith("@newsletter")) continue; // status/canais: não
    const grupo = jid.endsWith("@g.us");
    const secs = toSeconds(msg.messageTimestamp);
    // "notify" = mensagem nova. "append" = mensagem adicionada (ex.: enviada do celular); aceita só as recentes.
    if (type !== "notify" && !(type === "append" && secs && Date.now() / 1000 - secs < 600)) continue;
    if (key.fromMe && s.sent.has(key.id)) continue; // enviada pelo próprio InteliSac
    const content = normalizeMessageContent(msg.message);
    if (!content) continue;
    const ctype = getContentType(content);
    // "Apagar para todos" feito pelo cliente (ou pelo celular/outro aparelho): avisa o backend
    if (ctype === "protocolMessage") {
      const pm = content.protocolMessage;
      if ((pm?.type ?? 0) === 0 && pm?.key?.id) {
        postEvent({ type: "revoke", serviceId: s.id, messageId: pm.key.id, fromMe: !!key.fromMe });
      }
      continue;
    }
    if (!ctype || IGNORED_TYPES.has(ctype)) continue;
    const parsed = parseContent(ctype, content);
    if (!parsed?.text) continue;
    const pnJid = grupo ? null : await resolvePhoneJid(sock, key);
    const media = parsed.media ? await baixarMidia(s, sock, msg, parsed.media) : null;
    let groupName = null;
    let sender = null;
    if (grupo) {
      groupName = await nomeDoGrupo(sock, jid);
      if (!key.fromMe) sender = { ...(await remetenteDoGrupo(sock, key)), name: msg.pushName || null };
    }
    // Resposta citando outra mensagem
    const ctx = content[ctype]?.contextInfo;
    const qm = ctx?.quotedMessage ? normalizeMessageContent(ctx.quotedMessage) : null;
    const quotedText = qm
      ? qm.conversation || qm.extendedTextMessage?.text || qm.imageMessage?.caption || qm.videoMessage?.caption ||
        qm.documentMessage?.fileName || (qm.audioMessage ? "[Áudio]" : qm.imageMessage ? "[Imagem]" : null)
      : null;
    postEvent({
      type: "message",
      serviceId: s.id,
      message: {
        id: key.id,
        jid,
        pnJid,
        number: pnJid ? pnJid.split("@")[0].split(":")[0] : null,
        pushName: key.fromMe || grupo ? null : msg.pushName || null,
        isGroup: grupo,
        groupName,
        sender,
        fromMe: !!key.fromMe,
        type: parsed.type,
        text: parsed.text,
        caption: parsed.caption ?? null,
        label: parsed.label ?? null,
        media,
        quotedId: ctx?.stanzaId || null,
        quotedText: quotedText || null,
        contacts: parsed.contacts || null,
        timestamp: secs,
      },
    });
  }
}

function rememberSent(s, id) {
  const now = Date.now();
  s.sent.set(id, now);
  for (const [k, t] of s.sent) if (now - t > 15 * 60 * 1000) s.sent.delete(k);
}

function httpError(status, message) {
  return Object.assign(new Error(message), { status });
}

// Mensagem citada ("responder marcando"): o WhatsApp precisa da chave e de um conteúdo de prévia.
function citada(to, quoted) {
  if (!quoted?.id) return undefined;
  return {
    // em grupo, a citação precisa dizer quem escreveu a mensagem original (participant)
    key: { remoteJid: to, fromMe: !!quoted.fromMe, id: quoted.id, ...(quoted.participant ? { participant: quoted.participant } : {}) },
    message: { conversation: String(quoted.text || "") },
  };
}

// Mensagem encaminhada: o WhatsApp mostra "Encaminhada" em cima
const ENCAMINHADA = { isForwarded: true, forwardingScore: 1 };

// Opções de envio: id gerado antes (o "eco" não volta como mensagem nova) + citação
function opcoesEnvio(s, to, quoted) {
  const messageId = generateMessageIDV2 ? generateMessageIDV2(s.sock.user?.id) : undefined;
  if (messageId) rememberSent(s, messageId);
  const q = citada(to, quoted);
  return { ...(messageId ? { messageId } : {}), ...(q ? { quoted: q } : {}) };
}

async function sendText(s, { jid, number, text, quoted, forwarded }) {
  if (!s?.sock || s.status !== "connected") throw httpError(409, "WhatsApp desconectado");
  if (!text || !String(text).trim()) throw httpError(422, "Mensagem vazia");
  const to = await destino(s, { jid, number });
  const content = { text: String(text), ...(forwarded ? { contextInfo: ENCAMINHADA } : {}) };
  const sent = await s.sock.sendMessage(to, content, opcoesEnvio(s, to, quoted));
  rememberSent(s, sent.key.id);
  return { id: sent.key.id, jid: to };
}

// Editar uma mensagem de texto enviada por este número (o WhatsApp aceita até 15 min depois)
async function editar(s, { jid, id, text }) {
  if (!s?.sock || s.status !== "connected") throw httpError(409, "WhatsApp desconectado");
  if (!jid || !id || !text || !String(text).trim()) throw httpError(422, "Informe jid, id e text");
  const sent = await s.sock.sendMessage(jid, { text: String(text), edit: { remoteJid: jid, fromMe: true, id } }, opcoesEnvio(s, jid));
  rememberSent(s, sent.key.id);
  return { ok: true };
}

// Apagar para todos (só mensagens enviadas por este número)
async function revoke(s, { jid, id }) {
  if (!s?.sock || s.status !== "connected") throw httpError(409, "WhatsApp desconectado");
  if (!jid || !id) throw httpError(422, "Informe jid e id");
  const sent = await s.sock.sendMessage(jid, { delete: { remoteJid: jid, fromMe: true, id } }, opcoesEnvio(s, jid));
  rememberSent(s, sent.key.id);
  return { ok: true };
}

async function destino(s, { jid, number }) {
  if (jid) return jid;
  const digits = String(number || "").replace(/\D/g, "");
  if (!digits) throw httpError(422, "Informe jid ou number");
  const [found] = (await s.sock.onWhatsApp(digits)) || [];
  if (!found?.exists) throw httpError(404, "Este número não tem WhatsApp");
  return found.jid;
}

// Envia arquivo. O backend manda um link temporário (Supabase Storage); o WhatsApp baixa daí.
async function sendMedia(s, { jid, number, url, mimetype, fileName, kind, caption, ptt, quoted, seconds, waveform, forwarded }) {
  if (!s?.sock || s.status !== "connected") throw httpError(409, "WhatsApp desconectado");
  if (!url) throw httpError(422, "Informe url do arquivo");
  const to = await destino(s, { jid, number });
  const legenda = caption ? String(caption) : undefined;
  let content;
  if (kind === "image") content = { image: { url }, caption: legenda, mimetype };
  else if (kind === "video") content = { video: { url }, caption: legenda, mimetype };
  else if (kind === "audio") {
    content = { audio: { url }, mimetype: ptt ? "audio/ogg; codecs=opus" : mimetype, ptt: !!ptt };
    // duração e "barrinhas" calculadas pelo backend (como numa gravação feita no celular)
    if (seconds) content.seconds = Math.round(seconds);
    if (ptt && Array.isArray(waveform) && waveform.length) content.waveform = Uint8Array.from(waveform);
  }
  else content = { document: { url }, mimetype: mimetype || "application/octet-stream", fileName: fileName || "arquivo", caption: legenda };
  if (forwarded) content.contextInfo = ENCAMINHADA;
  // Áudio não tem legenda no WhatsApp: a legenda/assinatura ("*Gabriel:*") vai como texto logo ANTES
  if (kind === "audio" && legenda) {
    const t = await s.sock.sendMessage(to, { text: legenda }, opcoesEnvio(s, to));
    rememberSent(s, t.key.id);
  }
  const sent = await s.sock.sendMessage(to, content, opcoesEnvio(s, to, quoted));
  rememberSent(s, sent.key.id);
  return { id: sent.key.id, jid: to };
}

async function logout(s) {
  s.stopped = true;
  try {
    await s.sock?.logout();
  } catch {
    /* já desconectado */
  }
  try {
    s.sock?.end(undefined);
  } catch {
    /* ignore */
  }
  s.sock = null;
  await rm(sessionDir(s.id), { recursive: true, force: true });
  setStatus(s, "disconnected", { reason: "logged_out", me: null });
}

// ---------------------------------------------------------------------------
// HTTP (o backend é o único cliente; exige o X-Gateway-Secret)
// ---------------------------------------------------------------------------
function readJson(req) {
  return new Promise((resolve, reject) => {
    let data = "";
    req.on("data", (c) => {
      data += c;
      if (data.length > 1e6) reject(httpError(413, "Corpo muito grande"));
    });
    req.on("end", () => {
      try {
        resolve(data ? JSON.parse(data) : {});
      } catch {
        reject(httpError(400, "JSON inválido"));
      }
    });
    req.on("error", reject);
  });
}

const server = createServer(async (req, res) => {
  const reply = (code, body) => {
    res.writeHead(code, { "Content-Type": "application/json; charset=utf-8" });
    res.end(JSON.stringify(body));
  };
  try {
    const url = new URL(req.url, "http://localhost");
    const autorizado = segredoConfere(req.headers["x-gateway-secret"]);
    if (req.method === "GET" && url.pathname === "/health") {
      // Sem o segredo, só diz que está no ar (o número conectado não aparece)
      if (!autorizado) return reply(200, { ok: true });
      return reply(200, { ok: true, sessions: [...sessions.values()].map(publicState), pendingEvents: queue.length });
    }
    if (!autorizado) return reply(401, { message: "Não autorizado" });
    const [root, id, action = ""] = url.pathname.split("/").filter(Boolean);
    if (root !== "sessions" || !id || !ID_RE.test(id)) return reply(404, { message: "Rota não encontrada" });
    const s = sessions.get(id);

    if (req.method === "GET" && action === "") {
      return reply(200, s ? { ...publicState(s), qr: s.qr } : { serviceId: id, status: "disconnected", me: null, qr: null });
    }
    // Foto do perfil (contato ou grupo). Sem foto ou privacidade fechada: url null
    if (req.method === "GET" && action === "photo") {
      if (!s?.sock || s.status !== "connected") return reply(409, { message: "WhatsApp desconectado" });
      const alvo = url.searchParams.get("jid");
      if (!alvo) return reply(422, { message: "Informe jid" });
      try {
        return reply(200, { url: (await s.sock.profilePictureUrl(alvo, "image")) || null });
      } catch (e) {
        return reply(200, { url: null, reason: e.message });
      }
    }
    if (req.method !== "POST") return reply(405, { message: "Método não permitido" });
    const body = await readJson(req);

    if (action === "start") return reply(200, publicState(await startSession(id)));
    if (action === "logout") {
      if (s) await logout(s);
      else await rm(sessionDir(id), { recursive: true, force: true });
      return reply(200, { serviceId: id, status: "disconnected" });
    }
    if (action === "send") return reply(200, await sendText(s, body));
    if (action === "send-media") return reply(200, await sendMedia(s, body));
    if (action === "delete") return reply(200, await revoke(s, body));
    if (action === "edit") return reply(200, await editar(s, body));
    return reply(404, { message: "Ação desconhecida" });
  } catch (e) {
    if (!e.status) log("erro na requisição", e);
    return reply(e.status || 500, { message: e.message || "Erro interno" });
  }
});

async function restoreSessions() {
  await mkdir(SESSIONS_DIR, { recursive: true });
  for (const entry of await readdir(SESSIONS_DIR, { withFileTypes: true })) {
    if (!entry.isDirectory() || !ID_RE.test(entry.name)) continue;
    let creds;
    try {
      creds = JSON.parse(await readFile(path.join(SESSIONS_DIR, entry.name, "creds.json"), "utf8"));
    } catch {
      continue;
    }
    if (!creds?.me?.id) continue; // QR nunca lido: não reabre sozinho
    log(`[${entry.name}] restaurando sessão salva`);
    startSession(entry.name).catch((e) => log(`[${entry.name}] falha ao restaurar`, e));
  }
}

server.listen(PORT, HOST, async () => {
  log(`gateway WhatsApp ouvindo em http://${HOST}:${PORT} (backend: ${BACKEND_URL})`);
  await restoreSessions();
});

function shutdown() {
  log("encerrando (as sessões continuam salvas)...");
  for (const s of sessions.values()) {
    s.stopped = true;
    try {
      s.sock?.end(undefined);
    } catch {
      /* ignore */
    }
  }
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(0), 3000).unref();
}
process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
