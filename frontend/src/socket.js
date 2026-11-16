import { io } from "socket.io-client";
import { api, getTokens } from "./api";

let socket = null;

// Conecta uma vez por sessão. Eventos no formato do Digisac: "message.created", "ticket.updated"...
export function getSocket() {
  if (socket) return socket;
  // O token vai no "auth" (não no endereço, que fica gravado nos logs do servidor).
  // Função: cada conexão/reconexão pega o token mais recente (renovado pelo api.js).
  socket = io({
    path: "/socket.io",
    transports: ["websocket"],
    auth: (cb) => cb({ access_token: getTokens()?.access_token, client: "web" }),
  });

  // Renova o acesso (o api.js usa o refresh_token) e conecta de novo.
  const renovarEConectar = async () => {
    try {
      await api("/me");
    } catch {
      return; // sem acesso (usuário arquivado ou saiu): fica desconectado
    }
    setTimeout(() => socket?.connect(), 1000);
  };

  // Token vencido: o servidor recusa a conexão.
  socket.on("connect_error", (e) => {
    if (socket.active) return; // queda de rede: o socket.io já tenta de novo sozinho
    console.warn("socket recusado, renovando acesso:", e.message);
    renovarEConectar();
  });

  // O servidor derruba quem ficou com o token vencido (a cada hora): renova e volta,
  // para o atendimento continuar recebendo mensagens em tempo real o dia todo.
  socket.on("disconnect", (motivo) => {
    if (motivo === "io server disconnect") renovarEConectar();
  });
  return socket;
}

export function closeSocket() {
  socket?.disconnect();
  socket = null;
}
