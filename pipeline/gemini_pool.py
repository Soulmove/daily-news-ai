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
import re
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
    "briefing:mega": ("KEY_1", "KEY_FINANCE", "KEY_TECH", "KEY_GLOBAL", "KEY_GENERAL", "GOOGLE_API_KEY"),
    "search_hunter": ("KEY_6", "KEY_7", "KEY_8", "GOOGLE_API_KEY", "KEY_4", "KEY_2"),
    "ai_radar": ("KEY_5", "KEY_8", "GOOGLE_API_KEY", "KEY_4", "KEY_TECH", "KEY_3"),
    "bilingual": ("KEY_2", "KEY_4", "KEY_6", "KEY_8", "GOOGLE_API_KEY", "KEY_GLOBAL"),
    "mega_derivative": ("KEY_3", "KEY_5", "KEY_7", "KEY_GENERAL", "GOOGLE_API_KEY", "KEY_2"),
    "mega_finance_impact": ("KEY_FINANCE", "KEY_1", "KEY_3", "KEY_7", "GOOGLE_API_KEY", "KEY_4"),
    "mega_predictions": ("KEY_4", "KEY_8", "KEY_2", "KEY_GLOBAL", "GOOGLE_API_KEY", "KEY_6"),
    "deep_ai_matrix": ("KEY_1", "KEY_TECH", "KEY_5", "GOOGLE_API_KEY", "KEY_2"),
    "deep_github_tools": ("KEY_2", "KEY_6", "KEY_TECH", "GOOGLE_API_KEY", "KEY_3"),
    "deep_storylines": ("KEY_3", "KEY_GLOBAL", "KEY_7", "GOOGLE_API_KEY", "KEY_4"),
    "deep_event_qa": ("KEY_4", "KEY_FINANCE", "KEY_8", "GOOGLE_API_KEY", "KEY_5"),
    "deep_topics_cal": ("KEY_5", "KEY_GENERAL", "KEY_1", "GOOGLE_API_KEY", "KEY_6"),
    "deep_finance_impact": ("KEY_FINANCE", "KEY_1", "KEY_3", "GOOGLE_API_KEY", "KEY_4"),
    "weekly_digest": ("KEY_1", "KEY_FINANCE", "KEY_GLOBAL", "KEY_TECH", "KEY_3", "GOOGLE_API_KEY"),
}

# Verified per-key model quota specs across all 8 Gemini models (total 1,120 RPD/key x 13 = 14,560 RPD, all 250K TPM)
MODEL_QUOTA_SPECS: Dict[str, Dict[str, Any]] = {
    "gemini-4-hydrogen": {"tier": 1, "rpm": 5, "rpd": 20, "soft_rpd": 18, "min_interval_sec": 13.0, "tokens": ("gemini", "4", "hydrogen"), "exclude": ("lite",)},
    "gemini-3.8-flash": {"tier": 1, "rpm": 5, "rpd": 20, "soft_rpd": 18, "min_interval_sec": 13.0, "tokens": ("gemini", "3.8", "flash"), "exclude": ("lite", "pro")},
    "gemini-3.6-flash": {"tier": 1, "rpm": 5, "rpd": 20, "soft_rpd": 18, "min_interval_sec": 13.0, "tokens": ("gemini", "3.6", "flash"), "exclude": ("lite", "pro")},
    "gemini-3-flash": {"tier": 1, "rpm": 5, "rpd": 20, "soft_rpd": 18, "min_interval_sec": 13.0, "tokens": ("gemini", "3", "flash"), "exclude": ("3.1", "3.5", "3.6", "3.8", "lite", "pro")},
    "gemini-2.5-flash": {"tier": 1, "rpm": 5, "rpd": 20, "soft_rpd": 18, "min_interval_sec": 13.0, "tokens": ("gemini", "2.5", "flash"), "exclude": ("lite", "pro")},
    "gemini-2.5-flash-lite": {"tier": 1, "rpm": 10, "rpd": 20, "soft_rpd": 18, "min_interval_sec": 6.5, "tokens": ("gemini", "2.5", "flash", "lite"), "exclude": ()},
    "gemini-3.5-flash-lite": {"tier": 2, "rpm": 15, "rpd": 500, "soft_rpd": 475, "min_interval_sec": 4.2, "tokens": ("gemini", "3.5", "flash", "lite"), "exclude": ()},
    "gemini-3.1-flash-lite": {"tier": 2, "rpm": 15, "rpd": 500, "soft_rpd": 475, "min_interval_sec": 4.2, "tokens": ("gemini", "3.1", "flash", "lite"), "exclude": ()},
}

TIER1_DEEP_MODELS: Tuple[str, ...] = (
    "gemini-4-hydrogen",
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3-flash",
    "gemini-2.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
)

TIER2_HIGH_THROUGHPUT_MODELS: Tuple[str, ...] = (
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3-flash",
    "gemini-2.5-flash",
)

_POOL_LOCK = threading.RLock()
_SCOPE_CURSORS: Dict[str, int] = {}
_MEMORY_STATE: Dict[str, Dict[str, Any]] = {}
_LAST_CALL_MONO: Dict[Tuple[str, str, str], float] = {}
_RESOLVED_MODELS_CACHE: Dict[str, Tuple[float, Dict[str, str]]] = {}
_SKIP_NON_TEXT_RE = re.compile(r"(?:embedding|imagen|veo|tts|audio|robotics|aqa|lyria|gemma-3n-e)", re.I)


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
            rec_copy["model_daily_calls"] = {}
            rec_copy["exhausted_until"] = None
            rec_copy["model_exhausted_until"] = {}
        else:
            if not isinstance(rec_copy.get("model_daily_calls"), dict):
                rec_copy["model_daily_calls"] = {}
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

    resolved_models = raw.get("resolved_models") if isinstance(raw.get("resolved_models"), dict) else {}
    resolved_models_at = raw.get("resolved_models_at")
    ledger = {
        "schema_version": "4.2",
        "date_utc": today,
        "updated_at": _iso_utc(now),
        "resolved_models": resolved_models,
        "resolved_models_at": resolved_models_at,
        "keys": normalized_keys,
    }
    _MEMORY_STATE[mem_key] = ledger
    return ledger


def _canonical_model_key(model_name: str) -> str:
    slug = re.sub(r"^models/", "", str(model_name or "").strip().lower())
    if slug in MODEL_QUOTA_SPECS:
        return slug
    for canon, spec in MODEL_QUOTA_SPECS.items():
        tokens = spec.get("tokens") or ()
        excludes = spec.get("exclude") or ()
        if all(t in slug for t in tokens) and not any(ex in slug for ex in excludes):
            return canon
    if "3.0" in slug and "flash" in slug and not any(ex in slug for ex in ("lite", "pro")):
        return "gemini-3-flash"
    return slug


def _match_model_slug(logical_name: str, live_slugs: Sequence[str]) -> Optional[str]:
    clean_live = [re.sub(r"^models/", "", s.strip()) for s in live_slugs if s and str(s).strip()]
    low_map = {s.lower(): s for s in clean_live}
    ln = logical_name.lower()
    if ln in low_map:
        return low_map[ln]
    for suf in ("-preview", "-latest"):
        if f"{ln}{suf}" in low_map:
            return low_map[f"{ln}{suf}"]
    spec = MODEL_QUOTA_SPECS.get(ln)
    if not spec:
        return None
    tokens = list(spec.get("tokens") or ())
    excludes = list(spec.get("exclude") or ())
    candidates: List[Tuple[int, int, str]] = []
    for raw_s in clean_live:
        ls = raw_s.lower()
        if _SKIP_NON_TEXT_RE.search(ls):
            continue
        if any(ex in ls for ex in excludes):
            continue
        alt_ok = ln == "gemini-3-flash" and "3.0" in ls and "flash" in ls
        if not (all(t in ls for t in tokens) or alt_ok):
            continue
        score = 0 if ls.startswith(ln) else (1 if "preview" in ls else 2)
        if "-exp" in ls:
            score += 2
        candidates.append((score, len(ls), raw_s))
    if not candidates:
        return None
    candidates.sort(key=lambda x: (x[0], x[1], x[2]))
    return candidates[0][2]


def resolve_available_model_slugs(
    slots: Optional[Sequence[KeySlot]] = None,
    *,
    base_dir: Path | str | None = ".",
    force: bool = False,
) -> Dict[str, str]:
    """Query client.models.list() once per 6h and resolve exact API slugs for all 8 registered models."""
    path = _state_file_path(base_dir)
    cache_key = str(path.resolve()) if path is not None else "__memory__"
    now_mono = time.monotonic()

    with _POOL_LOCK:
        if not force and cache_key in _RESOLVED_MODELS_CACHE:
            cached_ts, cached_map = _RESOLVED_MODELS_CACHE[cache_key]
            if (now_mono - cached_ts) < 21600.0:
                return dict(cached_map)
        ledger = _load_quota_ledger(base_dir)
        persisted = ledger.get("resolved_models")
        persisted_at = _parse_utc(ledger.get("resolved_models_at"))
        if not force and isinstance(persisted, dict) and persisted and persisted_at and (_utc_now() - persisted_at).total_seconds() < 21600.0:
            _RESOLVED_MODELS_CACHE[cache_key] = (now_mono, dict(persisted))
            return dict(persisted)

    use_slots = list(slots) if slots else collect_api_key_slots()
    if not use_slots:
        return {}
    try:
        from google import genai
        from google.genai import types
    except Exception:
        return {}

    live_slugs: List[str] = []
    for slot in use_slots[:3]:
        try:
            http_opts = types.HttpOptions(timeout=8_000) if hasattr(types, "HttpOptions") else None
            client = genai.Client(api_key=slot.secret, http_options=http_opts) if http_opts is not None else genai.Client(api_key=slot.secret)
            if not (hasattr(client, "models") and hasattr(client.models, "list")):
                break
            listed = list(client.models.list())
            for item in listed:
                m_name = str(getattr(item, "name", "") or "").strip()
                if not m_name:
                    continue
                short_name = re.sub(r"^models/", "", m_name)
                if _SKIP_NON_TEXT_RE.search(short_name):
                    continue
                actions = getattr(item, "supported_actions", None) or getattr(item, "supported_generation_methods", None) or ()
                actions_low = {str(a).lower() for a in actions}
                if actions_low and not any("generatecontent" in a for a in actions_low):
                    continue
                live_slugs.append(short_name)
            if live_slugs:
                break
        except Exception:
            continue

    resolved_map: Dict[str, str] = {}
    if live_slugs:
        for logical_name in MODEL_QUOTA_SPECS:
            matched = _match_model_slug(logical_name, live_slugs)
            if matched:
                resolved_map[logical_name] = matched
        with _POOL_LOCK:
            _RESOLVED_MODELS_CACHE[cache_key] = (time.monotonic(), dict(resolved_map))
            ledger = _load_quota_ledger(base_dir)
            ledger["resolved_models"] = dict(resolved_map)
            ledger["resolved_models_at"] = _iso_utc(_utc_now())
            _save_quota_ledger(ledger, base_dir)
        print(f"[gemini_pool] Resolved {len(resolved_map)}/{len(MODEL_QUOTA_SPECS)} live models: {resolved_map}", flush=True)
    return resolved_map


def resolve_model_slug(
    logical_name: str,
    *,
    resolved_map: Optional[Dict[str, str]] = None,
    base_dir: Path | str | None = ".",
) -> str:
    clean = re.sub(r"^models/", "", str(logical_name or "").strip())
    if not clean:
        return clean
    if resolved_map and clean in resolved_map:
        return resolved_map[clean]
    if resolved_map is None:
        m = resolve_available_model_slugs(base_dir=base_dir)
        if clean in m:
            return m[clean]
    return clean


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
            "model_daily_calls": {},
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
    canon_m = _canonical_model_key(model_name)
    mod_cd = rec.get("model_cooldown_until") or {}
    for key_m in (model_name, canon_m):
        mc_dt = _parse_utc(mod_cd.get(key_m))
        if mc_dt and mc_dt > now:
            return False
    if not mod_cd:
        cd_dt = _parse_utc(rec.get("cooldown_until"))
        if cd_dt and cd_dt > now:
            return False
    mod_ex = rec.get("model_exhausted_until") or {}
    for key_m in (model_name, canon_m):
        m_dt = _parse_utc(mod_ex.get(key_m))
        if m_dt and m_dt > now:
            return False
    spec = MODEL_QUOTA_SPECS.get(canon_m)
    if spec:
        mod_calls = rec.get("model_daily_calls") or {}
        used_today = int(mod_calls.get(canon_m) or mod_calls.get(model_name) or 0)
        if used_today >= int(spec.get("soft_rpd") or spec.get("rpd") or 20):
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
    models: Optional[Sequence[str]] = None,
    tier: Optional[str] = None,
    temperature: float = 0.2,
    max_output_tokens: Optional[int] = None,
    timeout_ms: int = 25_000,
    response_mime_type: Optional[str] = None,
    tools: Optional[List[Any]] = None,
    base_dir: Path | str | None = ".",
) -> GeminiCallResult:
    """
    Execute a quota-aware, RPM/RPD-paced Gemini generate_content call across all 13 keys and 8 models.
    Features:
      - Dynamic `client.models.list()` slug mapping (preserving exact `-preview` / version slugs)
      - Per-key per-model RPM cooldown pacing (13s for 5-RPM models, 4.2s for 15-RPM models) + soft RPD cap
      - Fast 25s timeout + 1-strike 503/504 instant model failover (zero wasted retries on congested models)
    """
    slots = get_ordered_key_slots(scope, base_dir=base_dir)
    if not slots:
        return GeminiCallResult(ok=False, error_message="no_api_key")

    try:
        from google import genai
        from google.genai import types
    except Exception as exc:
        return GeminiCallResult(ok=False, error_message=f"{type(exc).__name__}: {exc}")

    requested_models = list(models) if models else list(TIER2_HIGH_THROUGHPUT_MODELS if tier == "tier2" else TIER1_DEEP_MODELS)
    resolved_map = resolve_available_model_slugs(slots, base_dir=base_dir)
    unique_models: List[str] = []
    for raw_m in requested_models:
        if not raw_m:
            continue
        mapped_m = resolve_model_slug(raw_m, resolved_map=resolved_map, base_dir=base_dir)
        if mapped_m not in unique_models:
            unique_models.append(mapped_m)

    root_key = str(Path(base_dir).resolve()) if base_dir is not None else "__memory__"
    unavailable_models: set[str] = set()
    failed_slots_by_model: Dict[str, set[str]] = {}
    per_key_errors: List[Dict[str, str]] = []
    attempts = 0
    max_attempts = min(24, max(12, len(slots) + 8))
    deadline = time.monotonic() + 180.0
    saw_quota_exhaustion = False

    for model_idx, model_name in enumerate(unique_models):
        if model_name in unavailable_models or attempts >= max_attempts or time.monotonic() >= deadline:
            continue
        canon_m = _canonical_model_key(model_name)
        spec = MODEL_QUOTA_SPECS.get(canon_m, {"rpm": 5, "min_interval_sec": 13.0})
        min_interval = float(spec.get("min_interval_sec") or 13.0)
        has_fallback_after = model_idx < len(unique_models) - 1
        req_timeout_ms = max(5_000, int(timeout_ms))
        failed_for_model = failed_slots_by_model.setdefault(model_name, set())

        # Order candidate slots for THIS model: ready (RPM cooled down) keys first, lowest per-model RPD first
        with _POOL_LOCK:
            ledger = _load_quota_ledger(base_dir)
            now_utc = _utc_now()
            now_mono = time.monotonic()
            candidate_rows: List[Tuple[int, int, int, int, KeySlot]] = []
            for pos, s in enumerate(slots):
                if s.slot in failed_for_model:
                    continue
                rec = _ensure_slot_record(ledger, s)
                if not _is_slot_available_for_model(rec, model_name, now_utc):
                    continue
                mod_calls = int((rec.get("model_daily_calls") or {}).get(canon_m) or 0)
                total_calls = int(rec.get("daily_calls") or 0)
                last_m_ts = _LAST_CALL_MONO.get((root_key, s.fingerprint, canon_m), 0.0)
                in_rpm_window = 1 if (last_m_ts > 0.0 and (now_mono - last_m_ts) < min_interval) else 0
                candidate_rows.append((in_rpm_window, mod_calls, total_calls, pos, s))
            candidate_rows.sort(key=lambda r: (r[0], r[1], r[2], r[3]))

        for in_rpm_window, _, _, _, slot in candidate_rows:
            if slot.slot in failed_for_model or attempts >= max_attempts or time.monotonic() >= deadline:
                continue
            if in_rpm_window and has_fallback_after:
                # Skip throttled keys when another model is ready; never trip 6/5 RPM limit
                continue
            with _POOL_LOCK:
                ledger = _load_quota_ledger(base_dir)
                rec = _ensure_slot_record(ledger, slot)
                if not _is_slot_available_for_model(rec, model_name, _utc_now()):
                    continue
                _LAST_CALL_MONO[(root_key, slot.fingerprint, canon_m)] = time.monotonic()

            attempts += 1
            try:
                http_opts = types.HttpOptions(timeout=req_timeout_ms) if hasattr(types, "HttpOptions") else None
                client = (
                    genai.Client(api_key=slot.secret, http_options=http_opts)
                    if http_opts is not None
                    else genai.Client(api_key=slot.secret)
                )
                cfg_kwargs: Dict[str, Any] = {"temperature": temperature}
                if max_output_tokens is not None and int(max_output_tokens) > 0:
                    cfg_kwargs["max_output_tokens"] = int(max_output_tokens)
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
                        mod_counts = rec.setdefault("model_daily_calls", {})
                        mod_counts[canon_m] = int(mod_counts.get(canon_m) or 0) + 1
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
                per_key_errors.append(
                    {"slot": slot.slot, "model": model_name, "code": "EMPTY_RESPONSE", "error": "Empty model response text"}
                )
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
                    mod_counts = rec.setdefault("model_daily_calls", {})
                    mod_counts[canon_m] = int(mod_counts.get(canon_m) or 0) + 1
                    rec["last_error_code"] = err_code
                    rec["last_error"] = short_msg
                    rec["consecutive_errors"] = int(rec.get("consecutive_errors") or 0) + 1
                    until_iso = _iso_utc(now + timedelta(seconds=cd_secs))
                    if err_code == "AUTH_INVALID":
                        rec["exhausted_until"] = until_iso
                    elif is_daily:
                        rec.setdefault("model_exhausted_until", {})[canon_m] = until_iso
                    else:
                        rec.setdefault("model_cooldown_until", {})[canon_m] = until_iso
                    _save_quota_ledger(ledger, base_dir)

                per_key_errors.append(
                    {"slot": slot.slot, "model": model_name, "code": err_code, "error": short_msg}
                )
                if err_code == "TRANSIENT_ERROR":
                    low_err = short_msg.lower()
                    is_1strike = any(
                        k in low_err
                        for k in ("503", "unavailable", "high demand", "504", "deadline", "timeout", "timed out")
                    )
                    if is_1strike:
                        # Instant 0s model switch: 1 strike of 503 high demand or 504 timeout marks this model unavailable this run
                        unavailable_models.add(model_name)

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
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*```\s*$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        m = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", cleaned)
        if m:
            return json.loads(m.group(1))
        raise


def call_gemini_json(
    *,
    scope: str,
    prompt: str,
    models: Optional[Sequence[str]] = None,
    tier: Optional[str] = None,
    temperature: float = 0.25,
    max_output_tokens: Optional[int] = None,
    timeout_ms: int = 25_000,
    tools: Optional[List[Any]] = None,
    base_dir: Path | str | None = ".",
) -> GeminiCallResult:
    """Execute a Gemini call and parse strict JSON output, recording diagnostics cleanly."""
    res = call_gemini_raw(
        scope=scope,
        prompt=prompt,
        models=models,
        tier=tier,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        timeout_ms=timeout_ms,
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
