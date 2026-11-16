// Cliente HTTP da API /api/v1 — guarda os tokens e renova com refresh_token em caso de 401.

const BASE = "/api/v1";
const KEY = "intelisac.tokens";

export function getTokens() {
  try {
    return JSON.parse(localStorage.getItem(KEY)) || null;
  } catch {
    return null;
  }
}

function setTokens(tokens) {
  try {
    if (tokens) localStorage.setItem(KEY, JSON.stringify(tokens));
    else localStorage.removeItem(KEY);
  } catch {
    /* navegador sem storage: segue só em memória */
  }
}

async function tokenRequest(fields) {
  const res = await fetch(`${BASE}/oauth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams(fields),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body?.detail?.message || "Falha no login");
  setTokens(body);
  return body;
}

export const login = (email, password) =>
  tokenRequest({ grant_type: "password", username: email, password });

// Sair: avisa o servidor (os logins deste usuário deixam de valer em qualquer aparelho) e limpa o navegador.
export async function logout() {
  const t = getTokens();
  setTokens(null);
  if (!t?.access_token) return;
  try {
    await fetch(`${BASE}/oauth/revoke`, { method: "POST", headers: { Authorization: `Bearer ${t.access_token}` } });
  } catch {
    /* sem internet: o navegador já esqueceu o login */
  }
}

// Quando vence o token de acesso (segundos desde 1970), lido de dentro do próprio token.
function venceEm(token) {
  try {
    return JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))).exp || 0;
  } catch {
    return 0;
  }
}

let refreshing = null;

async function refresh() {
  const t = getTokens();
  if (!t?.refresh_token) throw new Error("Sessão expirada");
  refreshing ||= tokenRequest({ grant_type: "refresh_token", refresh_token: t.refresh_token }).finally(() => {
    refreshing = null;
  });
  return refreshing;
}

export async function api(path, { method = "GET", body, params } = {}, retry = true) {
  const url = new URL(BASE + path, window.location.origin);
  Object.entries(params || {}).forEach(([k, v]) => v !== undefined && v !== null && url.searchParams.set(k, v));
  const headers = { "Content-Type": "application/json" };
  const t = getTokens();
  if (t?.access_token) headers.Authorization = `Bearer ${t.access_token}`;
  const res = await fetch(url, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  if (res.status === 401 && retry && t?.refresh_token) {
    try {
      await refresh();
    } catch {
      logout();
      window.location.href = "/login";
      throw new Error("Sessão expirada");
    }
    return api(path, { method, body, params }, false);
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error(data?.detail?.message || `Erro ${res.status}`);
  return data;
}

// Envio de arquivo (multipart). Mesmo esquema de token/renovação do api().
export async function apiForm(path, formData, retry = true) {
  // O servidor confere o login ANTES de receber o arquivo: renova aqui se estiver para vencer,
  // para o envio não ser recusado no meio do caminho.
  const atual = getTokens();
  if (retry && atual?.refresh_token && venceEm(atual.access_token) * 1000 < Date.now() + 60000) {
    await refresh().catch(() => {});
  }
  const headers = {};
  const t = getTokens();
  if (t?.access_token) headers.Authorization = `Bearer ${t.access_token}`;
  const res = await fetch(BASE + path, { method: "POST", headers, body: formData });
  if (res.status === 401 && retry && t?.refresh_token) {
    await refresh();
    return apiForm(path, formData, false);
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error(data?.detail?.message || `Erro ${res.status}`);
  return data;
}

// Mesmo formato da fábrica genérica do Digisac: resource("/departments").fetchMany() etc.
export function resource(path) {
  return {
    fetchMany: (params) => api(path, { params }),
    fetchById: (id) => api(`${path}/${id}`),
    create: (body) => api(path, { method: "POST", body }),
    updateById: (id, body) => api(`${path}/${id}`, { method: "PUT", body }),
    deleteById: (id) => api(`${path}/${id}`, { method: "DELETE" }),
    archive: (id, archive = true) => api(`${path}/${id}/archive`, { method: "POST", body: { archive } }),
  };
}
