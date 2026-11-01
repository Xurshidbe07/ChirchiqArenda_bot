"""Admin panel uchun JWT (HS256) — tashqi kutubxonasiz.

Oqim:
  1. Admin botga /admin yuboradi -> make_admin_token(user_id) -> 12 soatlik token.
  2. Mini App manzili: {WEBAPP_URL}/admin?t=<token>. Tokensiz sahifa 403.
  3. Sahifa har API so'rovida tokenni X-Admin-Token sarlavhasida yuboradi;
     server tokenni va Telegram initData'ni (admin ekanligini) birga tekshiradi.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from bot.config import config


class TokenError(ValueError):
    pass


def _secret() -> bytes:
    if config.admin_jwt_secret:
        return config.admin_jwt_secret.encode()
    # ADMIN_JWT_SECRET berilmagan bo'lsa bot tokenidan hosil qilamiz (tokenni bilmagan odam yasay olmaydi)
    return hashlib.sha256(("admin-jwt:" + config.bot_token).encode()).digest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def make_admin_token(user_id: int, hours: int | None = None) -> str:
    now = int(time.time())
    ttl = (hours or config.admin_token_hours) * 3600
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64(json.dumps({"sub": user_id, "role": "admin", "iat": now, "exp": now + ttl},
                              separators=(",", ":")).encode())
    signing = f"{header}.{payload}".encode()
    sig = _b64(hmac.new(_secret(), signing, hashlib.sha256).digest())
    return f"{header}.{payload}.{sig}"


def verify_admin_token(token: str) -> dict:
    """Tokenni tekshiradi va payload'ni qaytaradi. Xato bo'lsa TokenError."""
    try:
        header, payload, sig = token.strip().split(".")
    except ValueError:
        raise TokenError("TOKEN_MALFORMED")
    expected = _b64(hmac.new(_secret(), f"{header}.{payload}".encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(expected, sig):
        raise TokenError("TOKEN_INVALID")
    try:
        data = json.loads(_unb64(payload))
    except (ValueError, json.JSONDecodeError):
        raise TokenError("TOKEN_MALFORMED")
    if data.get("role") != "admin" or not isinstance(data.get("sub"), int):
        raise TokenError("TOKEN_INVALID")
    if int(data.get("exp", 0)) < time.time():
        raise TokenError("TOKEN_EXPIRED")
    return data
