import datetime
import json
import os
from typing import Any

import requests
import streamlit as st


def _secret(name: str) -> str | None:
    try:
        value = st.secrets.get(name)
    except Exception:
        value = None
    return str(value).strip() if value else os.getenv(name)


def supabase_enabled() -> bool:
    return bool(_secret("SUPABASE_URL") and _secret("SUPABASE_KEY"))


def _headers(prefer: str | None = None) -> dict[str, str]:
    key = _secret("SUPABASE_KEY") or ""
    headers = {"apikey": key, "Content-Type": "application/json"}
    if not key.startswith("sb_secret_"):
        headers["Authorization"] = f"Bearer {key}"
    if prefer:
        headers["Prefer"] = prefer
    return headers


def _endpoint() -> str:
    return f"{(_secret('SUPABASE_URL') or '').rstrip('/')}/rest/v1/report_states"


def _period_start(report_type: str, today: datetime.date | None = None) -> datetime.date:
    today = today or datetime.date.today()
    return today.replace(day=1) if report_type == "monthly" else today - datetime.timedelta(days=today.weekday())


def load_state(report_type: str, local_file: str, default: Any) -> Any:
    if supabase_enabled():
        response = requests.get(_endpoint(), headers=_headers(), params={
            "report_type": f"eq.{report_type}", "period_start": f"eq.{_period_start(report_type).isoformat()}",
            "select": "payload", "limit": "1",
        }, timeout=10)
        response.raise_for_status()
        rows = response.json()
        return rows[0]["payload"] if rows else default
    if os.path.exists(local_file):
        try:
            with open(local_file, "r", encoding="utf-8") as file:
                return json.load(file)
        except (OSError, json.JSONDecodeError):
            pass
    return default


def save_state(report_type: str, payload: Any, local_file: str) -> None:
    if supabase_enabled():
        period = _period_start(report_type).isoformat()
        response = requests.post(_endpoint(), headers=_headers("resolution=merge-duplicates,return=minimal"),
            params={"on_conflict": "report_type,period_start"}, json={"report_type": report_type,
            "period_start": period, "payload": payload,
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}, timeout=10)
        response.raise_for_status()
        return
    with open(local_file, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


@st.cache_data(ttl=60, show_spinner=False)
def cleanup_old_states(today_iso: str) -> int:
    """이번 달과 전달만 남기고 더 오래된 보고 기간을 삭제한다."""
    if not supabase_enabled():
        return 0
    this_month = datetime.date.fromisoformat(today_iso).replace(day=1)
    cutoff = (this_month - datetime.timedelta(days=1)).replace(day=1)
    response = requests.delete(_endpoint(), headers=_headers("return=representation"),
        params={"period_start": f"lt.{cutoff.isoformat()}", "select": "id"}, timeout=10)
    response.raise_for_status()
    return len(response.json())
