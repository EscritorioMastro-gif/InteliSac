import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _database_url() -> str:
    """Aceita a connection string do Supabase como ela vem (postgresql://...) e
    usa o driver psycopg 3."""
    url = os.getenv("DATABASE_URL", "sqlite:///./intelisac.db").strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def _com_http(url: str) -> str:
    """O Render entrega o endereço interno como "nome:porta" (sem http://)."""
    url = url.strip().rstrip("/")
    return url if "://" in url or not url else f"http://{url}"


def _cors_padrao() -> str:
    # No Render a tela e a API ficam no mesmo endereço público (RENDER_EXTERNAL_URL).
    externo = os.getenv("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
    return externo or "http://localhost:5180,http://localhost:8010"


def _flag(name: str, default: bool) -> bool:
    v = os.getenv(name)
    return default if v is None or v.strip() == "" else v.strip().lower() in ("1", "true", "sim", "yes", "on")


JWT_PADRAO = "dev-secret-troque"
# No Render a variável RENDER=true existe sempre; APP_ENV=production vale para outro servidor.
PRODUCAO = os.getenv("RENDER", "").lower() == "true" or os.getenv("APP_ENV", "").lower() == "production"


class Settings:
    is_production: bool = PRODUCAO
    # Simulador: finge ser um cliente mandando mensagem. Só para testes (desligado em produção).
    enable_simulator: bool = _flag("ENABLE_SIMULATOR", not PRODUCAO)
    database_url: str = _database_url()
    jwt_secret: str = os.getenv("JWT_SECRET", JWT_PADRAO)
    access_token_minutes: int = int(os.getenv("ACCESS_TOKEN_MINUTES", "60"))
    refresh_token_days: int = int(os.getenv("REFRESH_TOKEN_DAYS", "7"))
    cors_origins: list[str] = [
        o.strip().rstrip("/") for o in (os.getenv("CORS_ORIGINS") or _cors_padrao()).split(",") if o.strip()
    ]
    # Gateway do WhatsApp por QR code (pasta whatsapp-gateway/)
    whatsapp_gateway_url: str = _com_http(os.getenv("WHATSAPP_GATEWAY_URL") or "http://127.0.0.1:8020")
    gateway_secret: str = os.getenv("GATEWAY_SECRET", "")
    # Supabase Auth: quando configurado, e-mail e senha dos usuários ficam no Supabase.
    supabase_url: str = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    supabase_anon_key: str = os.getenv("SUPABASE_ANON_KEY", "").strip()
    supabase_service_role_key: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

    @property
    def supabase_auth_enabled(self) -> bool:
        return bool(self.supabase_url and self.supabase_anon_key)

    def problemas_de_producao(self) -> list[str]:
        """O que impede de subir na internet com segurança (vazio = ok)."""
        erros = []
        if self.jwt_secret == JWT_PADRAO or len(self.jwt_secret) < 32:
            erros.append("JWT_SECRET ausente, padrão ou curto (mínimo 32 caracteres)")
        if len(self.gateway_secret) < 32:
            erros.append("GATEWAY_SECRET ausente ou curto (mínimo 32 caracteres)")
        if not self.cors_origins or any("localhost" in o or "127.0.0.1" in o or o == "*" for o in self.cors_origins):
            erros.append("CORS_ORIGINS precisa ser o endereço público do InteliSac (sem localhost e sem *)")
        if not (self.supabase_url and self.supabase_anon_key and self.supabase_service_role_key):
            erros.append("SUPABASE_URL, SUPABASE_ANON_KEY e SUPABASE_SERVICE_ROLE_KEY são obrigatórias")
        if self.database_url.startswith("sqlite"):
            erros.append("DATABASE_URL precisa apontar para o Postgres do Supabase")
        return erros


settings = Settings()
