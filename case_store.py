"""Persistence layer for manager-authored strategy cases.

The daily strategy text remains sourced from the Tencent shared sheets.  This
module stores only the separate, manager-authored case content.  Supabase is
the production backend when configured; a small JSON store is intentionally
kept as a local development fallback so the UI can be exercised before the
cloud project is provisioned.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent
LOCAL_CASES_PATH = ROOT / "data" / "strategy_cases.local.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _secret(name: str, default: str = "") -> str:
    """Read a Streamlit secret when available, then an environment variable."""
    try:
        import streamlit as st

        value = st.secrets.get(name)
        if value is not None:
            return str(value)
    except Exception:
        pass
    return os.getenv(name, default)


def supabase_configured() -> bool:
    # Never accept an anonymous/publishable key for editorial writes.
    return bool(
        _secret("SUPABASE_URL")
        and (
            _secret("SUPABASE_SECRET_KEY")
            or _secret("SUPABASE_SERVICE_ROLE_KEY")
        )
    )


def admin_credentials() -> tuple[str, str]:
    # The real password is supplied through local Streamlit secrets or the
    # deployment platform.  Keeping the fallback empty prevents an accidental
    # production login if secrets were not configured.
    return _secret("ADMIN_USERNAME", "admin"), _secret("ADMIN_PASSWORD", "")


def _read_local() -> list[dict[str, Any]]:
    try:
        payload = json.loads(LOCAL_CASES_PATH.read_text(encoding="utf-8"))
        return payload if isinstance(payload, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _write_local(rows: list[dict[str, Any]]) -> None:
    LOCAL_CASES_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_CASES_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


class CaseStore:
    def __init__(self) -> None:
        self.remote = None
        self.remote_expected = supabase_configured()
        self.initialization_error = ""
        try:
            import streamlit as st
            hostname = urlparse(str(getattr(st.context, "url", "") or "")).hostname
        except Exception:
            hostname = None
        self.local_fallback = hostname in {"localhost", "127.0.0.1", "::1"} or os.getenv("CASE_STORE_LOCAL") == "1"
        if self.remote_expected:
            try:
                import httpx
                from supabase import ClientOptions, create_client

                key = (
                    _secret("SUPABASE_SECRET_KEY")
                    or _secret("SUPABASE_SERVICE_ROLE_KEY")
                )
                # Some local environments route HTTPS_PROXY through a proxy
                # that cannot complete TLS to Supabase. Keep this exception
                # scoped to the database client; other application requests
                # still respect the user's proxy configuration.
                self.remote = create_client(
                    _secret("SUPABASE_URL"),
                    key,
                    options=ClientOptions(httpx_client=httpx.Client(trust_env=False, timeout=30)),
                )
            except Exception as exc:
                self.initialization_error = f"案例数据库连接失败：{type(exc).__name__}"

    def _require_backend(self) -> None:
        if self.initialization_error:
            raise RuntimeError(self.initialization_error)
        if not self.local_fallback and self.remote is None:
            raise RuntimeError("案例数据库尚未配置。请联系管理员设置 Supabase。")

    @property
    def backend_name(self) -> str:
        return "Supabase" if self.remote is not None else ("本地开发存储" if self.local_fallback else "未配置")

    def list_cases(self, *, published_only: bool = False, strategy: str = "") -> list[dict[str, Any]]:
        self._require_backend()
        if self.remote is not None:
            query = self.remote.table("strategy_cases").select("*").order("case_date", desc=True).order("updated_at", desc=True)
            if published_only:
                query = query.eq("status", "published")
            if strategy:
                query = query.eq("strategy", strategy)
            response = query.execute()
            return list(response.data or [])

        rows = _read_local()
        if published_only:
            rows = [row for row in rows if row.get("status") == "published"]
        if strategy:
            rows = [row for row in rows if row.get("strategy") == strategy]
        return sorted(rows, key=lambda row: (row.get("case_date", ""), row.get("updated_at", "")), reverse=True)

    def get_case(self, case_id: str) -> dict[str, Any] | None:
        self._require_backend()
        if self.remote is not None:
            response = self.remote.table("strategy_cases").select("*").eq("id", case_id).limit(1).execute()
            return (response.data or [None])[0]
        return next((row for row in _read_local() if row.get("id") == case_id), None)

    def save_case(self, values: dict[str, Any], *, actor: str) -> dict[str, Any]:
        self._require_backend()
        now = _now()
        case_id = str(values.get("id") or uuid.uuid4())
        record = {
            "id": case_id,
            "title": str(values.get("title", "")).strip(),
            "strategy": str(values.get("strategy", "")).strip(),
            "manager": str(values.get("manager", "")).strip(),
            "case_date": str(values.get("case_date", "")).strip(),
            "background": str(values.get("background", "")),
            "judgement": str(values.get("judgement", "")),
            "action": str(values.get("action", "")),
            "result": str(values.get("result", "")),
            "review": str(values.get("review", "")),
            "source_date_key": str(values.get("source_date_key", "")).strip(),
            "source_cell": str(values.get("source_cell", "")).strip(),
            "status": values.get("status", "draft") if values.get("status") in {"draft", "published"} else "draft",
            "updated_by": actor,
            "updated_at": now,
        }
        if self.remote is not None:
            existing = self.get_case(case_id)
            if existing:
                record["created_by"] = existing.get("created_by", actor)
                record["created_at"] = existing.get("created_at", now)
                record["published_at"] = existing.get("published_at")
            else:
                record["created_by"] = actor
                record["created_at"] = now
                record["published_at"] = now if record["status"] == "published" else None
            if record["status"] == "published" and not record.get("published_at"):
                record["published_at"] = now
            response = self.remote.table("strategy_cases").upsert(record).execute()
            return (response.data or [record])[0]

        rows = _read_local()
        old = next((row for row in rows if row.get("id") == case_id), None)
        record["created_by"] = (old or {}).get("created_by", actor)
        record["created_at"] = (old or {}).get("created_at", now)
        record["published_at"] = (old or {}).get("published_at")
        if record["status"] == "published" and not record["published_at"]:
            record["published_at"] = now
        if old:
            rows = [record if row.get("id") == case_id else row for row in rows]
        else:
            rows.append(record)
        _write_local(rows)
        return record

    def delete_case(self, case_id: str) -> bool:
        """Delete exactly one selected case, returning False if it no longer exists."""
        self._require_backend()
        if not case_id or not case_id.strip():
            raise ValueError("必须指定要删除的案例。")
        if self.remote is not None:
            response = self.remote.table("strategy_cases").delete().eq("id", case_id).select("id").execute()
            return any(row.get("id") == case_id for row in (response.data or []))

        rows = _read_local()
        remaining = [row for row in rows if row.get("id") != case_id]
        if len(remaining) == len(rows):
            return False
        _write_local(remaining)
        return True
