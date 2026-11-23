"""Unified Quota-Aware 13-Key Gemini API Pool for InfoFocus Pipeline.

Replaces scattered, hardcoded `keys[:5]` / `keys[:6]` loops across briefing, search hunter,
AI radar, and bilingual modules with:
  - Full discovery across all 13 configured keys (KEY_TECH, KEY_GLOBAL, KEY_FINANCE,
    KEY_GENERAL, GOOGLE_API_KEY/GEMINI_API_KEY, KEY_1..KEY_8)
  - Scope-staggered starting offsets so categories don't hammer the same front keys
  - Thread-safe persistent cooldown & quota ledger in `data/gemini_quota_state.json`
    (stores only key slot names and 8-char SHA256 fingerprints — never raw API keys)
  - Per-key failure diagnostics and quota health summaries for `manifest.json`
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import threading
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pipeline.manifest import atomic_write_json, load_json_if_exists

ALL_KEY_ENV_NAMES: Tuple[str, ...] = (
    "KEY_TECH",
    "KEY_GLOBAL",
    "KEY_FINANCE",
    "KEY_GENERAL",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "KEY_1",
    "KEY_2",
    "KEY_3",
    "KEY_4",
    "KEY_5",
    "KEY_6",
    "KEY_7",
    "KEY_8",
)

# Staggered starting order per caller/category so concurrent or hourly runs balance across all 13 keys
_SCOPE_PRIORITY: Dict[str, Tuple[str, ...]] = {
    "briefing:finance": ("KEY_FINANCE", "KEY_1", "KEY_2", "KEY_3", "GOOGLE_API_KEY"),
    "comments:finance": ("KEY_FINANCE", "KEY_2", "KEY_1", "KEY_3", "GOOGLE_API_KEY"),
    "briefing:global": ("KEY_GLOBAL", "KEY_3", "KEY_4", "KEY_5", "GOOGLE_API_KEY"),
    "comments:global": ("KEY_GLOBAL", "KEY_4", "KEY_3", "KEY_5", "GOOGLE_API_KEY"),
    "briefing:tech": ("KEY_TECH", "KEY_5", "KEY_6", "KEY_7", "GOOGLE_API_KEY"),
    "comments:tech": ("KEY_TECH", "KEY_6", "KEY_5", "KEY_7", "GOOGLE_API_KEY"),
    "briefing:general": ("KEY_GENERAL", "KEY_7", "KEY_8", "KEY_1", "GOOGLE_API_KEY"),
    "comments:general": ("KEY_GENERAL", "KEY_8", "KEY_7", "KEY_1", "GOOGLE_API_KEY"),
    "search_hunter": ("KEY_6", "KEY_7", "KEY_8", "GOOGLE_API_KEY", "KEY_4", "KEY_2"),
    "ai_radar": ("KEY_5", "KEY_8", "GOOGLE_API_KEY", "KEY_4", "KEY_TECH", "KEY_3"),
    "bilingual": ("KEY_2", "KEY_4", "KEY_6", "KEY_8", "GOOGLE_API_KEY", "KEY_GLOBAL"),
    "deep_ai_matrix": ("KEY_1", "KEY_TECH", "KEY_5", "GOOGLE_API_KEY", "KEY_2"),
    "deep_github_tools": ("KEY_2", "KEY_6", "KEY_TECH", "GOOGLE_API_KEY", "KEY_3"),
    "deep_storylines": ("KEY_3", "KEY_GLOBAL", "KEY_7", "GOOGLE_API_KEY", "KEY_4"),
    "deep_event_qa": ("KEY_4", "KEY_FINANCE", "KEY_8", "GOOGLE_API_KEY", "KEY_5"),
    "deep_topics_cal": ("KEY_5", "KEY_GENERAL", "KEY_1", "GOOGLE_API_KEY", "KEY_6"),
    "deep_finance_impact": ("KEY_FINANCE", "KEY_1", "KEY_3", "KEY_7", "GOOGLE_API_KEY", "KEY_4"),
}

_POOL_LOCK = threading.RLock()
_SCOPE_CURSORS: Dict[str, int] = {}
_MEMORY_STATE: Dict[str, Dict[str, Any]] = {}


@dataclass(frozen=True)
class KeySlot:
    slot: str
    fingerprint: str
    secret: str


@dataclass
class GeminiCallResult:
    ok: bool
    data: Any = None
    text: str = ""
    raw_response: Any = None
    model_used: Optional[str] = None
    key_slot: Optional[str] = None
    attempts: int = 0
    per_key_errors: List[Dict[str, str]] = field(default_factory=list)
    quota_exhausted: bool = False
    degraded: bool = False
    error_message: Optional[str] = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_date_str(now: Optional[datetime] = None) -> str:
    return (now or _utc_now()).strftime("%Y-%m-%d")


def _iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc(ts: Any) -> Optional[datetime]:
    if not ts or not isinstance(ts, str):
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _fingerprint_key(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:8]


def collect_api_key_slots(preferred_first: Sequence[str] = ()) -> List[KeySlot]:
    """Collect all unique Gemini API keys from the 13 configured environment variables."""
    ordered_names: List[str] = []
    for n in preferred_first:
        if n not in ordered_names:
            ordered_names.append(n)
    for n in ALL_KEY_ENV_NAMES:
        if n not in ordered_names:
            ordered_names.append(n)

    seen_secrets: set[str] = set()
    slots: List[KeySlot] = []
    for name in ordered_names:
        val = (os.environ.get(name) or "").strip()
        if not val or val in seen_secrets:
            continue
        seen_secrets.add(val)
        slots.append(KeySlot(slot=name, fingerprint=_fingerprint_key(val), secret=val))
    return slots


def _state_file_path(base_dir: Path | str | None) -> Optional[Path]:
    if base_dir is None:
        return None
    return Path(base_dir) / "data" / "gemini_quota_state.json"


def _load_quota_ledger(base_dir: Path | str | None = ".") -> Dict[str, Any]:
    now = _utc_now()
    today = _utc_date_str(now)
    path = _state_file_path(base_dir)
    mem_key = str(path.resolve()) if path is not None else "__memory__"

    raw: Any = None
    if path is not None and path.exists():
        try:
            raw = load_json_if_exists(path, default={})
        except Exception:
            raw = None
    if not isinstance(raw, dict):
        raw = _MEMORY_STATE.get(mem_key) or {}

    keys_map = raw.get("keys") if isinstance(raw.get("keys"), dict) else {}
    normalized_keys: Dict[str, Dict[str, Any]] = {}
    for slot, rec in keys_map.items():
        if not isinstance(rec, dict):
            continue
        rec_copy = dict(rec)
        # Roll daily counters cleanly at UTC midnight and clear expired cooldowns/exhaustion
        if rec_copy.get("date_utc") != today:
            rec_copy["date_utc"] = today
            rec_copy["daily_calls"] = 0
            rec_copy["exhausted_until"] = None
            rec_copy["model_exhausted_until"] = {}
        else:
            ex_dt = _parse_utc(rec_copy.get("exhausted_until"))
            if ex_dt and ex_dt <= now:
                rec_copy["exhausted_until"] = None
            cd_dt = _parse_utc(rec_copy.get("cooldown_until"))
            if cd_dt and cd_dt <= now:
                rec_copy["cooldown_until"] = None
            mod_ex = rec_copy.get("model_exhausted_until")
            if isinstance(mod_ex, dict):
                rec_copy["model_exhausted_until"] = {
                    m: ts for m, ts in mod_ex.items()
                    if (_parse_utc(ts) or now) > now
                }
            else:
                rec_copy["model_exhausted_until"] = {}
        normalized_keys[slot] = rec_copy

    ledger = {
        "schema_version": "4.1",
        "date_utc": today,
        "updated_at": _iso_utc(now),
        "keys": normalized_keys,
    }
    _MEMORY_STATE[mem_key] = ledger
    return ledger


def _save_quota_ledger(ledger: Dict[str, Any], base_dir: Path | str | None = ".") -> None:
    ledger["updated_at"] = _iso_utc(_utc_now())
    path = _state_file_path(base_dir)
    mem_key = str(path.resolve()) if path is not None else "__memory__"
    _MEMORY_STATE[mem_key] = ledger
    if path is not None:
        try:
            # Ensure data dir exists and write safely without ever storing raw secret strings
            atomic_write_json(path, ledger)
        except Exception:
            pass


def _ensure_slot_record(ledger: Dict[str, Any], slot: KeySlot) -> Dict[str, Any]:
    keys_map = ledger.setdefault("keys", {})
    rec = keys_map.get(slot.slot)
    if not isinstance(rec, dict):
        rec = {
            "slot": slot.slot,
            "fingerprint": slot.fingerprint,
            "date_utc": _utc_date_str(),
            "daily_calls": 0,
            "cooldown_until": None,
            "exhausted_until": None,
            "model_exhausted_until": {},
            "last_error_code": None,
            "last_error": None,
            "last_success_at": None,
            "consecutive_errors": 0,
        }
        keys_map[slot.slot] = rec
    else:
        rec["fingerprint"] = slot.fingerprint
    return rec


def _classify_gemini_error(exc: Exception) -> Tuple[str, str, int, bool, bool]:
    """
    Classify Gemini SDK/HTTP errors cleanly.
    Returns: (error_code, short_msg, cooldown_seconds, is_daily_exhausted, is_model_not_found)
    """
    msg = str(exc or "").strip()
    low = msg.lower()
    short_msg = f"{type(exc).__name__}: {msg[:120]}"

    if "404" in low or "not_found" in low or "is not found for api version" in low or "not supported for generatecontent" in low:
        return "MODEL_NOT_FOUND", short_msg, 0, False, True

    if any(k in low for k in ("api_key_invalid", "api key not valid", "permission_denied", "401", "403", "unauthenticated", "suspended")):
        return "AUTH_INVALID", short_msg, 24 * 3600, True, False

    if "429" in low or "resource_exhausted" in low or "quota" in low or "rate limit" in low:
        is_daily = any(
            k in low
            for k in ("perday", "per_day", "per day", "daily", "rpd", "requestsperday", "limit: 0")
        )
        if is_daily:
            return "QUOTA_EXHAUSTED", short_msg, 6 * 3600, True, False
        return "RATE_LIMIT_429", short_msg, 60, False, False

    if any(k in low for k in ("500", "502", "503", "504", "unavailable", "deadline", "timeout", "timed out", "connection")):
        return "TRANSIENT_ERROR", short_msg, 20, False, False

    return "API_ERROR", short_msg, 45, False, False


def _is_slot_available_for_model(rec: Dict[str, Any], model_name: str, now: datetime) -> bool:
    ex_dt = _parse_utc(rec.get("exhausted_until"))
    if ex_dt and ex_dt > now:
        return False
    mod_cd = rec.get("model_cooldown_until") or {}
    mc_dt = _parse_utc(mod_cd.get(model_name))
    if mc_dt and mc_dt > now:
        return False
    if not mod_cd:
        cd_dt = _parse_utc(rec.get("cooldown_until"))
        if cd_dt and cd_dt > now:
            return False
    mod_ex = rec.get("model_exhausted_until") or {}
    m_dt = _parse_utc(mod_ex.get(model_name))
    if m_dt and m_dt > now:
        return False
    return True


def get_ordered_key_slots(
    scope: str = "default",
    *,
    base_dir: Path | str | None = ".",
) -> List[KeySlot]:
    """Return all available keys ordered by scope stagger, daily load, and round-robin cursor."""
    preferred = _SCOPE_PRIORITY.get(scope, ())
    all_slots = collect_api_key_slots(preferred)
    if not all_slots:
        return []

    with _POOL_LOCK:
        ledger = _load_quota_ledger(base_dir)
        now = _utc_now()
        healthy: List[Tuple[int, int, KeySlot]] = []
        cooled: List[KeySlot] = []

        cursor = _SCOPE_CURSORS.get(scope, 0)
        _SCOPE_CURSORS[scope] = (cursor + 1) % max(1, len(all_slots))

        for idx, slot in enumerate(all_slots):
            rec = _ensure_slot_record(ledger, slot)
            ex_dt = _parse_utc(rec.get("exhausted_until"))
            cd_dt = _parse_utc(rec.get("cooldown_until"))
            if (ex_dt and ex_dt > now) or (cd_dt and cd_dt > now):
                cooled.append(slot)
                continue
            daily_calls = int(rec.get("daily_calls") or 0)
            rotated_pos = (idx - cursor) % len(all_slots)
            healthy.append((daily_calls, rotated_pos, slot))

        healthy.sort(key=lambda item: (item[0], item[1]))
        return [item[2] for item in healthy] + cooled


def count_healthy_keys(base_dir: Path | str | None = ".") -> int:
    """Count keys not currently cooled down or exhausted."""
    slots = collect_api_key_slots()
    if not slots:
        return 0
    with _POOL_LOCK:
        ledger = _load_quota_ledger(base_dir)
        now = _utc_now()
        cnt = 0
        for s in slots:
            rec = _ensure_slot_record(ledger, s)
            ex_dt = _parse_utc(rec.get("exhausted_until"))
            cd_dt = _parse_utc(rec.get("cooldown_until"))
            if (not ex_dt or ex_dt <= now) and (not cd_dt or cd_dt <= now):
                cnt += 1
        return cnt


def get_quota_summary(base_dir: Path | str | None = ".") -> Dict[str, Any]:
    """Build safe quota telemetry (zero secrets) for manifest.json & ensure ledger persists cleanly."""
    slots = collect_api_key_slots()
    with _POOL_LOCK:
        ledger = _load_quota_ledger(base_dir)
        path = _state_file_path(base_dir)
        if slots:
            for slot in slots:
                _ensure_slot_record(ledger, slot)
            if path is not None and not path.exists():
                _save_quota_ledger(ledger, base_dir)
        now = _utc_now()
        healthy = 0
        cooled = 0
        exhausted = 0
        total_calls = 0
        key_rows: List[Dict[str, Any]] = []

        slot_map = {s.slot: s for s in slots}
        ordered_names = list(slot_map.keys()) + [k for k in (ledger.get("keys") or {}).keys() if k not in slot_map]
        for name in ordered_names:
            rec = (ledger.get("keys") or {}).get(name) or {}
            ex_dt = _parse_utc(rec.get("exhausted_until"))
            cd_dt = _parse_utc(rec.get("cooldown_until"))
            has_mod_ex = any(
                (dt is not None and dt > now)
                for dt in (_parse_utc(v) for v in (rec.get("model_exhausted_until") or {}).values())
            )
            has_mod_cd = any(
                (dt is not None and dt > now)
                for dt in (_parse_utc(v) for v in (rec.get("model_cooldown_until") or {}).values())
            )
            calls = int(rec.get("daily_calls") or 0)
            total_calls += calls
            if (ex_dt and ex_dt > now) or has_mod_ex:
                status = "exhausted"
                exhausted += 1
            elif (cd_dt and cd_dt > now) or has_mod_cd:
                status = "cooldown"
                cooled += 1
            elif name in slot_map:
                status = "healthy"
                healthy += 1
            else:
                status = "unconfigured"
            key_rows.append(
                {
                    "slot": name,
                    "status": status,
                    "daily_calls": calls,
                    "cooldown_until": rec.get("cooldown_until"),
                    "exhausted_until": rec.get("exhausted_until"),
                    "last_error_code": rec.get("last_error_code"),
                    "last_error": rec.get("last_error"),
                    "last_success_at": rec.get("last_success_at"),
                }
            )

        return {
            "total_configured_keys": len(slots),
            "healthy_keys": healthy,
            "cooled_down_keys": cooled,
            "exhausted_keys": exhausted,
            "daily_calls_total": total_calls,
            "date_utc": ledger.get("date_utc"),
            "updated_at": ledger.get("updated_at"),
            "keys": key_rows,
        }


def call_gemini_raw(
    *,
    scope: str,
    prompt: str,
    models: Sequence[str] = ("gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"),
    temperature: float = 0.2,
    response_mime_type: Optional[str] = None,
    tools: Optional[List[Any]] = None,
    base_dir: Path | str | None = ".",
) -> GeminiCallResult:
    """
    Execute a quota-aware Gemini generate_content call across all 13 keys.
    Per-model isolation: rate-limits or 503s on one model never block fallback models on the same key.
    """
    slots = get_ordered_key_slots(scope, base_dir=base_dir)
    if not slots:
        return GeminiCallResult(ok=False, error_message="no_api_key")

    try:
        from google import genai
        from google.genai import types
    except Exception as exc:
        return GeminiCallResult(ok=False, error_message=f"{type(exc).__name__}: {exc}")

    unique_models = list(dict.fromkeys([m for m in models if m]))
    unavailable_models: set[str] = set()
    failed_slots_by_model: Dict[str, set[str]] = {}
    per_key_errors: List[Dict[str, str]] = []
    attempts = 0
    max_attempts = min(14, max(8, len(slots)))
    deadline = time.monotonic() + 150.0
    saw_quota_exhaustion = False

    for model_name in unique_models:
        if model_name in unavailable_models or attempts >= max_attempts or time.monotonic() >= deadline:
            continue
        failed_for_model = failed_slots_by_model.setdefault(model_name, set())
        transient_errors_for_model = 0
        for slot in slots:
            if slot.slot in failed_for_model or attempts >= max_attempts or time.monotonic() >= deadline:
                continue
            with _POOL_LOCK:
                ledger = _load_quota_ledger(base_dir)
                rec = _ensure_slot_record(ledger, slot)
                if not _is_slot_available_for_model(rec, model_name, _utc_now()):
                    continue

            max_transient_tries = 1
            for _try_idx in range(max_transient_tries):
                attempts += 1
                try:
                    http_opts = types.HttpOptions(timeout=75_000) if hasattr(types, "HttpOptions") else None
                    client = (
                        genai.Client(api_key=slot.secret, http_options=http_opts)
                        if http_opts is not None
                        else genai.Client(api_key=slot.secret)
                    )
                    cfg_kwargs: Dict[str, Any] = {"temperature": temperature}
                    if response_mime_type:
                        cfg_kwargs["response_mime_type"] = response_mime_type
                    if tools:
                        cfg_kwargs["tools"] = tools
                    resp = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(**cfg_kwargs),
                    )
                    text = getattr(resp, "text", None) or ""
                    if text.strip():
                        with _POOL_LOCK:
                            ledger = _load_quota_ledger(base_dir)
                            rec = _ensure_slot_record(ledger, slot)
                            rec["daily_calls"] = int(rec.get("daily_calls") or 0) + 1
                            rec["last_success_at"] = _iso_utc(_utc_now())
                            rec["last_error_code"] = None
                            rec["last_error"] = None
                            rec["consecutive_errors"] = 0
                            _save_quota_ledger(ledger, base_dir)
                        return GeminiCallResult(
                            ok=True,
                            text=text,
                            raw_response=resp,
                            model_used=model_name,
                            key_slot=slot.slot,
                            attempts=attempts,
                            per_key_errors=per_key_errors,
                            quota_exhausted=saw_quota_exhaustion,
                            degraded=False,
                        )
                    # Empty response text without exception: move cleanly to next key
                    per_key_errors.append(
                        {"slot": slot.slot, "model": model_name, "code": "EMPTY_RESPONSE", "error": "Empty model response text"}
                    )
                    break
                except Exception as exc:
                    err_code, short_msg, cd_secs, is_daily, is_missing_model = _classify_gemini_error(exc)
                    if is_missing_model:
                        unavailable_models.add(model_name)
                        per_key_errors.append(
                            {"slot": slot.slot, "model": model_name, "code": err_code, "error": short_msg}
                        )
                        break

                    now = _utc_now()
                    if err_code == "AUTH_INVALID":
                        # Key itself is invalid across all models
                        for m in unique_models:
                            failed_slots_by_model.setdefault(m, set()).add(slot.slot)
                    else:
                        if is_daily or err_code == "RATE_LIMIT_429":
                            saw_quota_exhaustion = saw_quota_exhaustion or is_daily
                        failed_for_model.add(slot.slot)

                    with _POOL_LOCK:
                        ledger = _load_quota_ledger(base_dir)
                        rec = _ensure_slot_record(ledger, slot)
                        rec["daily_calls"] = int(rec.get("daily_calls") or 0) + 1
                        rec["last_error_code"] = err_code
                        rec["last_error"] = short_msg
                        rec["consecutive_errors"] = int(rec.get("consecutive_errors") or 0) + 1
                        until_iso = _iso_utc(now + timedelta(seconds=cd_secs))
                        if err_code == "AUTH_INVALID":
                            rec["exhausted_until"] = until_iso
                        elif is_daily:
                            rec.setdefault("model_exhausted_until", {})[model_name] = until_iso
                        else:
                            rec.setdefault("model_cooldown_until", {})[model_name] = until_iso
                        _save_quota_ledger(ledger, base_dir)

                    per_key_errors.append(
                        {"slot": slot.slot, "model": model_name, "code": err_code, "error": short_msg}
                    )
                    if err_code == "TRANSIENT_ERROR":
                        transient_errors_for_model += 1
                        if transient_errors_for_model >= 2:
                            unavailable_models.add(model_name)
                    break

            if model_name in unavailable_models or time.monotonic() >= deadline:
                break

    last_msg = per_key_errors[-1]["error"] if per_key_errors else "All healthy Gemini keys exhausted or in cooldown"
    if not per_key_errors:
        saw_quota_exhaustion = count_healthy_keys(base_dir) == 0
    return GeminiCallResult(
        ok=False,
        attempts=attempts,
        per_key_errors=per_key_errors,
        quota_exhausted=saw_quota_exhaustion,
        degraded=True,
        error_message=last_msg,
    )


def _extract_json_payload(raw_text: str) -> Any:
    cleaned = (raw_text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").lstrip("json").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        m = __import__("re").search(r"(\{[\s\S]*\}|\[[\s\S]*\])", cleaned)
        if m:
            return json.loads(m.group(1))
        raise


def call_gemini_json(
    *,
    scope: str,
    prompt: str,
    models: Sequence[str] = ("gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"),
    temperature: float = 0.25,
    tools: Optional[List[Any]] = None,
    base_dir: Path | str | None = ".",
) -> GeminiCallResult:
    """Execute a Gemini call and parse strict JSON output, recording diagnostics cleanly."""
    res = call_gemini_raw(
        scope=scope,
        prompt=prompt,
        models=models,
        temperature=temperature,
        response_mime_type=None if tools else "application/json",
        tools=tools,
        base_dir=base_dir,
    )
    if not res.ok:
        return res
    try:
        res.data = _extract_json_payload(res.text)
        return res
    except Exception as exc:
        res.ok = False
        res.degraded = True
        res.error_message = f"JSON parse error ({res.key_slot}/{res.model_used}): {exc}"
        res.per_key_errors.append(
            {
                "slot": res.key_slot or "unknown",
                "model": res.model_used or "unknown",
                "code": "JSON_PARSE_ERROR",
                "error": str(exc)[:120],
            }
        )
        return res
