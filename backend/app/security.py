import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt

from .config import settings

_ITER = 260_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITER)
    return f"pbkdf2_sha256${_ITER}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _algo, iters, salt_hex, hash_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except ValueError:
        return False


def _encode(payload: dict, expires: timedelta) -> str:
    data = {**payload, "exp": datetime.now(timezone.utc) + expires}
    return jwt.encode(data, settings.jwt_secret, algorithm="HS256")


def create_tokens(user_id: str, account_id: str) -> dict:
    access_exp = timedelta(minutes=settings.access_token_minutes)
    access = _encode({"sub": user_id, "acc": account_id, "typ": "access"}, access_exp)
    refresh = _encode(
        {"sub": user_id, "acc": account_id, "typ": "refresh"}, timedelta(days=settings.refresh_token_days)
    )
    return {
        "access_token": access,
        "refresh_token": refresh,
        "expires_in": int(access_exp.total_seconds()),
        "token_type": "Bearer",
    }


def decode_token(token: str, expected_type: str = "access") -> dict | None:
    try:
        data = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    if data.get("typ") != expected_type:
        return None
    return data
