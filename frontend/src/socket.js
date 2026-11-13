import { io } from "socket.io-client";
import { api, getTokens } from "./api";

let socket = null;

// Conecta uma vez por sessão. Eventos no formato do Digisac: "message.created", "ticket.updated"...
export function getSocket() {
  if (socket) return socket;
  socket = io({
    path: "/socket.io",
    transports: ["websocket"],
    query: { access_token: getTokens()?.access_token, client: "web" },
  });

  // Toda reconexão usa o token mais recente (ele é renovado a cada hora pelo api.js).
  socket.io.on("reconnect_attempt", () => {
    socket.io.opts.query = { ...socket.io.opts.query, access_token: getTokens()?.access_token };
  });

  // Token vencido: o servidor recusa a conexão. Renova o token e conecta de novo,
  // para o atendimento continuar recebendo mensagens em tempo real o dia todo.
  socket.on("connect_error", async (e) => {
    if (socket.active) return; // queda de rede: o socket.io já tenta de novo sozinho
    console.warn("socket recusado, renovando acesso:", e.message);
    try {
      await api("/me");
    } catch {
      return;
    }
    socket.io.opts.query = { ...socket.io.opts.query, access_token: getTokens()?.access_token };
    setTimeout(() => socket?.connect(), 1000);
  });
  return socket;
}

export function closeSocket() {
  socket?.disconnect();
  socket = null;
}
