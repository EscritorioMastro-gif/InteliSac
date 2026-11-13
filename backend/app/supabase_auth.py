"""Login e cadastro de usuários no Supabase Auth (GoTrue).

O InteliSac continua emitindo o próprio token (JWT) para o site e o tempo real; o Supabase só
confere e-mail/senha e guarda as senhas. Cada usuário do InteliSac fica ligado ao usuário do
Supabase pelo campo users.auth_user_id.

Chaves (backend/.env):
  SUPABASE_URL               https://<ref>.supabase.co
  SUPABASE_ANON_KEY          chave publishable/anon  → login (password grant)
  SUPABASE_SERVICE_ROLE_KEY  chave secret/service_role → criar usuário, trocar senha (admin)
"""

import httpx

from .config import settings


class AuthServiceError(Exception):
    """Supabase fora do ar ou chave errada (não é senha errada)."""


def _headers(key: str) -> dict:
    h = {"apikey": key, "Content-Type": "application/json"}
    if key.startswith("eyJ"):  # chaves antigas (anon/service_role) são JWT e vão também no Authorization
        h["Authorization"] = f"Bearer {key}"
    return h


def _admin_headers() -> dict:
    if not settings.supabase_service_role_key:
        raise AuthServiceError("SUPABASE_SERVICE_ROLE_KEY não configurada no backend/.env")
    return _headers(settings.supabase_service_role_key)


def _error_text(res: httpx.Response) -> str:
    try:
        body = res.json()
    except ValueError:
        return res.text[:200]
    return body.get("msg") or body.get("message") or body.get("error_description") or body.get("error") or str(body)[:200]


async def sign_in(email: str, password: str) -> dict | None:
    """Confere e-mail/senha no Supabase. Devolve o usuário do Supabase ou None se a senha estiver errada."""
    url = f"{settings.supabase_url}/auth/v1/token?grant_type=password"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.post(url, json={"email": email, "password": password}, headers=_headers(settings.supabase_anon_key))
    except httpx.HTTPError as e:
        raise AuthServiceError(f"Supabase Auth indisponível: {e}") from e
    if res.status_code == 200:
        return res.json().get("user") or {}
    if res.status_code in (400, 422):  # invalid_credentials / email_not_confirmed
        return None
    raise AuthServiceError(f"Supabase Auth respondeu {res.status_code}: {_error_text(res)}")


def _admin(method: str, path: str, json: dict | None = None, params: dict | None = None) -> httpx.Response:
    try:
        with httpx.Client(timeout=15) as client:
            return client.request(method, f"{settings.supabase_url}/auth/v1{path}", json=json, params=params, headers=_admin_headers())
    except httpx.HTTPError as e:
        raise AuthServiceError(f"Supabase Auth indisponível: {e}") from e


def find_user_by_email(email: str) -> dict | None:
    email = email.strip().lower()
    page = 1
    while True:
        res = _admin("GET", "/admin/users", params={"page": page, "per_page": 200})
        if res.status_code != 200:
            raise AuthServiceError(f"Não consegui listar usuários do Supabase ({res.status_code}): {_error_text(res)}")
        users = res.json().get("users", [])
        for u in users:
            if (u.get("email") or "").lower() == email:
                return u
        if len(users) < 200:
            return None
        page += 1


def list_users() -> list[dict]:
    res = _admin("GET", "/admin/users", params={"page": 1, "per_page": 200})
    if res.status_code != 200:
        raise AuthServiceError(f"Não consegui listar usuários do Supabase ({res.status_code}): {_error_text(res)}")
    return res.json().get("users", [])


def create_user(email: str, password: str, name: str | None = None) -> dict:
    res = _admin(
        "POST",
        "/admin/users",
        json={"email": email, "password": password, "email_confirm": True, "user_metadata": {"name": name} if name else {}},
    )
    if res.status_code in (200, 201):
        return res.json()
    raise AuthServiceError(f"Supabase recusou criar o usuário: {_error_text(res)}")


def update_user(auth_user_id: str, **fields) -> dict:
    res = _admin("PUT", f"/admin/users/{auth_user_id}", json=fields)
    if res.status_code == 200:
        return res.json()
    raise AuthServiceError(f"Supabase recusou atualizar o usuário: {_error_text(res)}")


def check_keys() -> dict:
    """Valida URL e chaves sem mexer em nada. Usado por python -m app.users_cli check."""
    out = {"url": bool(settings.supabase_url), "anon": False, "service_role": False}
    if "supabase.com/dashboard" in settings.supabase_url:
        out["url"] = False
        out["error"] = "SUPABASE_URL é o endereço do painel. Use o Project URL: https://<ref>.supabase.co"
        return out
    try:
        with httpx.Client(timeout=15) as client:
            r = client.get(f"{settings.supabase_url}/auth/v1/settings", headers=_headers(settings.supabase_anon_key))
        if r.status_code == 200 and "json" in r.headers.get("content-type", ""):
            out["anon"] = True
            out["signup_enabled"] = not r.json().get("disable_signup", False)
        elif r.status_code == 200:
            out["url"] = False
            out["error"] = "SUPABASE_URL não respondeu como API do Supabase. Use o Project URL: https://<ref>.supabase.co"
            return out
    except httpx.HTTPError as e:
        out["error"] = str(e)
        return out
    if settings.supabase_service_role_key.startswith("sb_publishable_"):
        out["error"] = "SUPABASE_SERVICE_ROLE_KEY está com a chave publishable. Use a chave secret (sb_secret_...)."
        return out
    if settings.supabase_service_role_key:
        try:
            out["service_role"] = _admin("GET", "/admin/users", params={"page": 1, "per_page": 1}).status_code == 200
        except AuthServiceError as e:
            out["error"] = str(e)
    return out
