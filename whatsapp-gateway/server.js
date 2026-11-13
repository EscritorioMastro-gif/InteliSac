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
import { mkdir, readdir, readFile, rm } from "node:fs/promises";
import path from "node:path";
import * as baileys from "@whiskeysockets/baileys";
import pino from "pino";
import QRCode from "qrcode";

const makeWASocket = baileys.makeWASocket ?? baileys.default?.default ?? baileys.default;
const {
  Browsers,
  DisconnectReason,
  fetchLatestBaileysVersion,
  generateMessageIDV2,
  getContentType,
  normalizeMessageContent,
  useMultiFileAuthState,
} = baileys;

const PORT = Number(process.env.PORT || 8020);
const BACKEND_URL = (process.env.BACKEND_URL || "http://127.0.0.1:8010").replace(/\/$/, "");
const SECRET = process.env.GATEWAY_SECRET || "";
const SESSIONS_DIR = path.resolve(process.env.SESSIONS_DIR || "./sessions");
const ID_RE = /^[A-Za-z0-9-]{1,64}$/;

if (!SECRET) {
  console.error("GATEWAY_SECRET não definido. Copie .env.example para .env.");
  process.exit(1);
}

const logger = pino({ level: process.env.LOG_LEVEL || "warn" });
const log = (...args) => console.log(new Date().toISOString(), ...args);

// ---------------------------------------------------------------------------
// Entrega de eventos ao backend: fila em memória, em ordem, com nova tentativa
// se o backend estiver fora do ar (nenhuma mensagem é descartada por isso).
// ---------------------------------------------------------------------------
const queue = [];
let flushing = false;

function postEvent(event) {
  queue.push(event);
  if (queue.length > 10000) queue.shift();
  flush();
}

async function flush() {
  if (flushing) return;
  flushing = true;
  while (queue.length) {
    const ev = queue[0];
    try {
      const res = await fetch(`${BACKEND_URL}/api/v1/gateway/events`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Gateway-Secret": SECRET },
        body: JSON.stringify(ev),
        signal: AbortSignal.timeout(15000),
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
]);

function toSeconds(t) {
  if (!t) return null;
  if (typeof t === "number") return t;
  if (typeof t.toNumber === "function") return t.toNumber();
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

function parseContent(ctype, c) {
  switch (ctype) {
    case "conversation":
      return { type: "chat", text: c.conversation };
    case "extendedTextMessage":
      return { type: "chat", text: c.extendedTextMessage?.text };
    case "imageMessage":
      return { type: "image", text: c.imageMessage?.caption || "[Imagem]" };
    case "videoMessage":
      return { type: "video", text: c.videoMessage?.caption || "[Vídeo]" };
    case "audioMessage":
      return { type: c.audioMessage?.ptt ? "ptt" : "audio", text: "[Áudio]" };
    case "documentMessage": {
      const d = c.documentMessage || {};
      return { type: "document", text: `[Documento] ${d.fileName || ""}${d.caption ? "\n" + d.caption : ""}`.trim() };
    }
    case "stickerMessage":
      return { type: "sticker", text: "[Figurinha]" };
    case "locationMessage":
    case "liveLocationMessage": {
      const l = c[ctype] || {};
      return { type: "location", text: `[Localização] https://maps.google.com/?q=${l.degreesLatitude},${l.degreesLongitude}` };
    }
    case "contactMessage":
      return { type: "vcard", text: `[Contato] ${c.contactMessage?.displayName || ""}`.trim() };
    case "contactsArrayMessage":
      return { type: "vcard", text: `[Contatos] ${(c.contactsArrayMessage?.contacts || []).map((x) => x.displayName).join(", ")}` };
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

async function onMessages(s, sock, { messages, type }) {
  for (const msg of messages || []) {
    const key = msg.key || {};
    const jid = key.remoteJid || "";
    if (!jid || jid.endsWith("@g.us") || jid.endsWith("@broadcast") || jid.endsWith("@newsletter")) continue; // grupos/status: ainda não
    const secs = toSeconds(msg.messageTimestamp);
    // "notify" = mensagem nova. "append" = mensagem adicionada (ex.: enviada do celular); aceita só as recentes.
    if (type !== "notify" && !(type === "append" && secs && Date.now() / 1000 - secs < 600)) continue;
    if (key.fromMe && s.sent.has(key.id)) continue; // enviada pelo próprio InteliSac
    const content = normalizeMessageContent(msg.message);
    if (!content) continue;
    const ctype = getContentType(content);
    if (!ctype || IGNORED_TYPES.has(ctype)) continue;
    const parsed = parseContent(ctype, content);
    if (!parsed?.text) continue;
    const pnJid = await resolvePhoneJid(sock, key);
    postEvent({
      type: "message",
      serviceId: s.id,
      message: {
        id: key.id,
        jid,
        pnJid,
        number: pnJid ? pnJid.split("@")[0].split(":")[0] : null,
        pushName: key.fromMe ? null : msg.pushName || null,
        fromMe: !!key.fromMe,
        type: parsed.type,
        text: parsed.text,
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

async function sendText(s, { jid, number, text }) {
  if (!s?.sock || s.status !== "connected") throw httpError(409, "WhatsApp desconectado");
  if (!text || !String(text).trim()) throw httpError(422, "Mensagem vazia");
  let to = jid;
  if (!to) {
    const digits = String(number || "").replace(/\D/g, "");
    if (!digits) throw httpError(422, "Informe jid ou number");
    const [found] = (await s.sock.onWhatsApp(digits)) || [];
    if (!found?.exists) throw httpError(404, "Este número não tem WhatsApp");
    to = found.jid;
  }
  // O id é gerado antes do envio para o "eco" da própria mensagem não voltar como mensagem nova.
  const messageId = generateMessageIDV2 ? generateMessageIDV2(s.sock.user?.id) : undefined;
  if (messageId) rememberSent(s, messageId);
  const sent = await s.sock.sendMessage(to, { text: String(text) }, messageId ? { messageId } : {});
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
// HTTP (só escuta em 127.0.0.1; o backend é o único cliente)
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
    if (req.method === "GET" && url.pathname === "/health") {
      return reply(200, { ok: true, sessions: [...sessions.values()].map(publicState), pendingEvents: queue.length });
    }
    if (req.headers["x-gateway-secret"] !== SECRET) return reply(401, { message: "Não autorizado" });
    const [root, id, action = ""] = url.pathname.split("/").filter(Boolean);
    if (root !== "sessions" || !id || !ID_RE.test(id)) return reply(404, { message: "Rota não encontrada" });
    const s = sessions.get(id);

    if (req.method === "GET" && action === "") {
      return reply(200, s ? { ...publicState(s), qr: s.qr } : { serviceId: id, status: "disconnected", me: null, qr: null });
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

server.listen(PORT, "127.0.0.1", async () => {
  log(`gateway WhatsApp ouvindo em http://127.0.0.1:${PORT} (backend: ${BACKEND_URL})`);
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
