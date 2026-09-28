import datetime
import copy
import hashlib
import json
import os
from pathlib import Path
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


def _stable_id(report_type: str, path: str, value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(f"{report_type}|{path}|{raw}".encode("utf-8")).hexdigest()[:24]


def _ensure_ids(report_type: str, payload: Any) -> Any:
    data = copy.deepcopy(payload)
    if report_type == "weekly" and isinstance(data, list):
        for team_index, team in enumerate(data):
            team.setdefault("_id", _stable_id(report_type, f"team:{team_index}", team.get("team_name", "")))
            for category in ("this_week", "next_week"):
                for entry_index, entry in enumerate(team.get(category, [])):
                    entry.setdefault("_id", _stable_id(
                        report_type, f"{team.get('team_name')}:{category}:{entry_index}", entry
                    ))
    elif report_type == "monthly" and isinstance(data, dict):
        for category in ("performance", "plan"):
            for entry_index, entry in enumerate(data.get(category, [])):
                entry.setdefault("_id", _stable_id(report_type, f"{category}:{entry_index}", entry))
    return data


def _merge_entry_list(base: list, local: list, remote: list) -> list:
    base_by_id = {item.get("_id"): item for item in base if item.get("_id")}
    local_by_id = {item.get("_id"): item for item in local if item.get("_id")}
    remote_by_id = {item.get("_id"): item for item in remote if item.get("_id")}

    deleted_ids = set(base_by_id) - set(local_by_id)
    merged = [copy.deepcopy(item) for item in remote if item.get("_id") not in deleted_ids]
    merged_index = {item.get("_id"): index for index, item in enumerate(merged)}

    for item_id, local_item in local_by_id.items():
        locally_changed = item_id not in base_by_id or local_item != base_by_id[item_id]
        if not locally_changed:
            continue
        if item_id in merged_index:
            merged[merged_index[item_id]] = copy.deepcopy(local_item)
        else:
            merged.append(copy.deepcopy(local_item))

    base_order = [item.get("_id") for item in base if item.get("_id")]
    local_order = [item.get("_id") for item in local if item.get("_id")]
    if local_order != base_order:
        current = {item.get("_id"): item for item in merged}
        ordered = [current[item_id] for item_id in local_order if item_id in current]
        ordered.extend(item for item in merged if item.get("_id") not in set(local_order))
        merged = ordered
    return merged


def _merge_payload(report_type: str, base: Any, local: Any, remote: Any) -> Any:
    base = _ensure_ids(report_type, base)
    local = _ensure_ids(report_type, local)
    remote = _ensure_ids(report_type, remote)
    if report_type == "monthly":
        merged = copy.deepcopy(remote if isinstance(remote, dict) else {})
        for key in ("month", "department"):
            if local.get(key) != base.get(key):
                merged[key] = copy.deepcopy(local.get(key))
        for category in ("performance", "plan"):
            merged[category] = _merge_entry_list(
                base.get(category, []), local.get(category, []), remote.get(category, [])
            )
        return merged

    base_teams = {team.get("_id"): team for team in base}
    local_teams = {team.get("_id"): team for team in local}
    remote_teams = {team.get("_id"): team for team in remote}
    deleted_team_ids = set(base_teams) - set(local_teams)
    result = []
    for remote_team in remote:
        team_id = remote_team.get("_id")
        if team_id in deleted_team_ids:
            continue
        local_team = local_teams.get(team_id)
        base_team = base_teams.get(team_id, {})
        if local_team is None:
            result.append(copy.deepcopy(remote_team))
            continue
        merged_team = copy.deepcopy(remote_team)
        if local_team.get("team_name") != base_team.get("team_name"):
            merged_team["team_name"] = local_team.get("team_name", "")
        for category in ("this_week", "next_week"):
            merged_team[category] = _merge_entry_list(
                base_team.get(category, []), local_team.get(category, []), remote_team.get(category, [])
            )
        result.append(merged_team)
    existing_ids = {team.get("_id") for team in result}
    result.extend(copy.deepcopy(team) for team in local if team.get("_id") not in existing_ids and team.get("_id") not in base_teams)
    return result


def load_state(report_type: str, local_file: str, default: Any) -> Any:
    if supabase_enabled():
        response = requests.get(_endpoint(), headers=_headers(), params={
            "report_type": f"eq.{report_type}", "period_start": f"eq.{_period_start(report_type).isoformat()}",
            "select": "payload,updated_at", "limit": "1",
        }, timeout=10)
        response.raise_for_status()
        rows = response.json()
        payload = _ensure_ids(report_type, rows[0]["payload"] if rows else default)
        st.session_state[f"_storage_baseline_{report_type}"] = copy.deepcopy(payload)
        st.session_state[f"_storage_updated_at_{report_type}"] = rows[0]["updated_at"] if rows else None
        return payload
    period_file = os.path.join("data", "periods", f"{report_type}_{_period_start(report_type).isoformat()}.json")
    candidate_files = [period_file, local_file]
    for candidate_file in candidate_files:
        if not os.path.exists(candidate_file):
            continue
        try:
            with open(candidate_file, "r", encoding="utf-8") as file:
                return _ensure_ids(report_type, json.load(file))
        except (OSError, json.JSONDecodeError):
            pass
    return default


def load_state_for_period(report_type: str, period_start: datetime.date, default: Any) -> Any:
    """Load an explicitly selected period without changing the current-period state."""
    if not supabase_enabled():
        period_file = os.path.join("data", "periods", f"{report_type}_{period_start.isoformat()}.json")
        if os.path.exists(period_file):
            try:
                with open(period_file, "r", encoding="utf-8") as file:
                    return json.load(file)
            except (OSError, json.JSONDecodeError):
                pass
        return default
    response = requests.get(_endpoint(), headers=_headers(), params={
        "report_type": f"eq.{report_type}",
        "period_start": f"eq.{period_start.isoformat()}",
        "select": "payload",
        "limit": "1",
    }, timeout=10)
    response.raise_for_status()
    rows = response.json()
    return rows[0]["payload"] if rows else default


def load_prior_states(
    report_type: str, before_period: datetime.date, limit: int = 24
) -> list[dict[str, Any]]:
    """Return older report states in newest-first order."""
    if supabase_enabled():
        response = requests.get(_endpoint(), headers=_headers(), params={
            "report_type": f"eq.{report_type}",
            "period_start": f"lt.{before_period.isoformat()}",
            "select": "period_start,payload",
            "order": "period_start.desc",
            "limit": str(limit),
        }, timeout=10)
        response.raise_for_status()
        return response.json()

    rows = []
    period_dir = Path("data") / "periods"
    for path in period_dir.glob(f"{report_type}_*.json") if period_dir.exists() else []:
        try:
            period = datetime.date.fromisoformat(path.stem.removeprefix(f"{report_type}_"))
            if period >= before_period:
                continue
            with path.open("r", encoding="utf-8") as file:
                rows.append({"period_start": period.isoformat(), "payload": json.load(file)})
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    rows.sort(key=lambda row: row["period_start"], reverse=True)
    return rows[:limit]


def save_state_for_period(report_type: str, period_start: datetime.date, payload: Any) -> None:
    """Save a future/past period without overwriting the period currently on screen."""
    if supabase_enabled():
        response = requests.post(_endpoint(), headers=_headers("resolution=merge-duplicates,return=minimal"),
            params={"on_conflict": "report_type,period_start"}, json={"report_type": report_type,
            "period_start": period_start.isoformat(), "payload": payload,
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}, timeout=10)
        response.raise_for_status()
        return
    period_dir = os.path.join("data", "periods")
    os.makedirs(period_dir, exist_ok=True)
    with open(os.path.join(period_dir, f"{report_type}_{period_start.isoformat()}.json"), "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def save_state(report_type: str, payload: Any, local_file: str) -> Any:
    payload = _ensure_ids(report_type, payload)
    if supabase_enabled():
        period = _period_start(report_type).isoformat()
        base = st.session_state.get(f"_storage_baseline_{report_type}", copy.deepcopy(payload))
        for _ in range(4):
            current = requests.get(_endpoint(), headers=_headers(), params={
                "report_type": f"eq.{report_type}", "period_start": f"eq.{period}",
                "select": "payload,updated_at", "limit": "1",
            }, timeout=10)
            current.raise_for_status()
            rows = current.json()
            remote = _ensure_ids(report_type, rows[0]["payload"] if rows else ({} if report_type == "monthly" else []))
            merged = _merge_payload(report_type, base, payload, remote) if rows else payload
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            if not rows:
                response = requests.post(_endpoint(), headers=_headers("resolution=ignore-duplicates,return=representation"),
                    params={"on_conflict": "report_type,period_start"}, json={"report_type": report_type,
                    "period_start": period, "payload": merged, "updated_at": now}, timeout=10)
            else:
                response = requests.patch(_endpoint(), headers=_headers("return=representation"), params={
                    "report_type": f"eq.{report_type}", "period_start": f"eq.{period}",
                    "updated_at": f"eq.{rows[0]['updated_at']}",
                }, json={"payload": merged, "updated_at": now}, timeout=10)
            response.raise_for_status()
            saved_rows = response.json()
            if saved_rows:
                saved = _ensure_ids(report_type, saved_rows[0]["payload"])
                st.session_state[f"_storage_baseline_{report_type}"] = copy.deepcopy(saved)
                st.session_state[f"_storage_updated_at_{report_type}"] = saved_rows[0].get("updated_at", now)
                return saved
        raise RuntimeError("다른 사용자의 저장과 계속 충돌했습니다. 화면을 새로고침한 뒤 다시 시도해 주세요.")
    with open(local_file, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
    return payload


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
