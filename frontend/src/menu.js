// Itens do menu lateral. Também alimentam a busca rápida (Ctrl+K).
export const MENU = [
  { section: "Dia a dia" },
  { to: "/", label: "Atendimento", icon: "chat", end: true, badge: "fila", desc: "Conversas, fila e chamados" },
  { to: "/agora", label: "Agora", icon: "pulse", desc: "Painel do atendimento em tempo real" },
  { to: "/contatos", label: "Contatos", icon: "contacts", desc: "Clientes e números" },
  { to: "/respostas", label: "Respostas rápidas", icon: "zap", desc: "Textos prontos para usar com /atalho" },
  { to: "/simulador", label: "Simulador", icon: "phone", simulador: true, desc: "Testar como se fosse o cliente" },
  { section: "Configurações", admin: true },
  { to: "/conexoes", label: "Conexões", icon: "plug", admin: true, desc: "WhatsApp e outros canais" },
  { to: "/usuarios", label: "Usuários", icon: "user", admin: true, desc: "Quem acessa o InteliSac" },
  { to: "/departamentos", label: "Departamentos", icon: "building", admin: true, desc: "Filas de atendimento" },
  { to: "/assuntos", label: "Assuntos", icon: "list", admin: true, desc: "Motivos escolhidos ao fechar um chamado" },
  { to: "/tags", label: "Tags", icon: "tag", admin: true, desc: "Etiquetas para organizar os contatos" },
  { to: "/api", label: "API", icon: "key", admin: true, desc: "Chaves para outros sistemas mandarem mensagens" },
];

export const menuDo = (me) => MENU.filter((m) => (!m.admin || me?.isAdmin) && (!m.simulador || me?.features?.simulator));

// Preferências deste navegador (menu recolhido etc.)
export function lerPref(chave, padrao = false) {
  try {
    const v = localStorage.getItem(chave);
    return v === null ? padrao : v === "1";
  } catch {
    return padrao;
  }
}

export function gravarPref(chave, v) {
  try {
    localStorage.setItem(chave, v ? "1" : "0");
  } catch {
    /* navegador sem armazenamento: vale só até recarregar */
  }
}
