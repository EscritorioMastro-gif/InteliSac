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


class Settings:
    database_url: str = _database_url()
    jwt_secret: str = os.getenv("JWT_SECRET", "dev-secret-troque")
    access_token_minutes: int = int(os.getenv("ACCESS_TOKEN_MINUTES", "60"))
    refresh_token_days: int = int(os.getenv("REFRESH_TOKEN_DAYS", "30"))
    cors_origins: list[str] = [
        o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5180").split(",") if o.strip()
    ]
    # Gateway do WhatsApp por QR code (pasta whatsapp-gateway/)
    whatsapp_gateway_url: str = os.getenv("WHATSAPP_GATEWAY_URL", "http://127.0.0.1:8020").rstrip("/")
    gateway_secret: str = os.getenv("GATEWAY_SECRET", "")
    # Supabase Auth: quando configurado, e-mail e senha dos usuários ficam no Supabase.
    supabase_url: str = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    supabase_anon_key: str = os.getenv("SUPABASE_ANON_KEY", "").strip()
    supabase_service_role_key: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

    @property
    def supabase_auth_enabled(self) -> bool:
        return bool(self.supabase_url and self.supabase_anon_key)


settings = Settings()
