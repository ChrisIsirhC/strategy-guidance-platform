"""A small, revocable-by-password persistent login for the shared admin account."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from pathlib import Path

import streamlit.components.v1 as components


LOGIN_LIFETIME_SECONDS = 30 * 24 * 60 * 60
_COMPONENT = components.declare_component(
    "strategy_admin_auth", path=str(Path(__file__).resolve().parent / "admin_auth_component")
)


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _signing_key(username: str, password: str) -> bytes:
    # Changing the configured password invalidates existing browser logins.
    return hashlib.sha256(f"strategy-admin-v1\0{username}\0{password}".encode()).digest()


def create_login_token(username: str, password: str, *, now: int | None = None) -> str:
    issued = int(time.time() if now is None else now)
    payload = _encode(json.dumps({"u": username, "iat": issued, "exp": issued + LOGIN_LIFETIME_SECONDS}, separators=(",", ":")).encode())
    signature = _encode(hmac.new(_signing_key(username, password), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{signature}"


def validate_login_token(token: str, username: str, password: str, *, now: int | None = None) -> bool:
    if not token or not password:
        return False
    try:
        payload, signature = token.split(".")
        expected = _encode(hmac.new(_signing_key(username, password), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return False
        values = json.loads(_decode(payload))
        current = int(time.time() if now is None else now)
        return (
            values.get("u") == username
            and isinstance(values.get("iat"), int)
            and isinstance(values.get("exp"), int)
            and values["iat"] <= current < values["exp"]
            and values["exp"] - values["iat"] == LOGIN_LIFETIME_SECONDS
        )
    except (ValueError, TypeError, KeyError, UnicodeError, json.JSONDecodeError):
        return False


def admin_auth_bridge(action: str = "read", token: str = "") -> str | None:
    """Read/write browser storage through a tiny Streamlit component."""
    return _COMPONENT(action=action, token=token, key="strategy-admin-auth", default=None)
