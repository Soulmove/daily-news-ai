"""Timezone-aware date/time parsing and formatting utilities (Asia/Shanghai)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import re
from typing import Any, Optional, Tuple

SHANGHAI_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")

# Naive date formats returned by Chinese upstream sources (ithome, zaobao, ifeng)
_NAIVE_DT_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?$")


def now_shanghai() -> datetime:
    """Return current timezone-aware datetime in Asia/Shanghai."""
    return datetime.now(SHANGHAI_TZ)


def to_iso_shanghai(dt: datetime) -> str:
    """Serialize a datetime to ISO-8601 string in Asia/Shanghai (+08:00)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=SHANGHAI_TZ)
    return dt.astimezone(SHANGHAI_TZ).isoformat(timespec="seconds")


def parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp string into a timezone-aware Asia/Shanghai datetime."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=SHANGHAI_TZ)
    return dt.astimezone(SHANGHAI_TZ)


def parse_epoch_ms(value: Any) -> Optional[datetime]:
    """Parse integer/float epoch timestamps in seconds or milliseconds."""
    if isinstance(value, bool):
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if num <= 0:
        return None
    # Distinguish seconds (~1.7e9) from milliseconds (~1.7e12)
    if num > 1e11:
        num /= 1000.0
    try:
        dt = datetime.fromtimestamp(num, tz=timezone.utc).astimezone(SHANGHAI_TZ)
    except (OverflowError, OSError, ValueError):
        return None
    if dt.year < 2020 or dt.year > 2035:
        return None
    return dt


def parse_published_at(raw_value: Any, source_id: str = "") -> Tuple[Optional[str], Optional[str]]:
    """
    Parse an upstream published timestamp into (iso_shanghai_str, provenance).
    Returns (None, None) if absent or invalid; never invents current time.
    """
    if raw_value is None or raw_value == "" or raw_value is False:
        return None, None

    if isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool):
        dt = parse_epoch_ms(raw_value)
        if dt is not None:
            return to_iso_shanghai(dt), "upstream_epoch"
        return None, None

    if isinstance(raw_value, str):
        text = raw_value.strip()
        if not text:
            return None, None

        # Pure numeric string
        if re.fullmatch(r"\d{10,13}", text):
            dt = parse_epoch_ms(int(text))
            if dt is not None:
                return to_iso_shanghai(dt), "upstream_epoch"

        # Naive YYYY-MM-DD HH:MM(:SS)
        naive_m = _NAIVE_DT_RE.match(text)
        if naive_m:
            year, month, day, hour, minute, sec = naive_m.groups()
            try:
                dt = datetime(
                    int(year), int(month), int(day),
                    int(hour), int(minute), int(sec or 0),
                    tzinfo=SHANGHAI_TZ,
                )
                return to_iso_shanghai(dt), "upstream_local_cst"
            except ValueError:
                return None, None

        # ISO 8601 with timezone
        dt_iso = parse_iso_datetime(text)
        if dt_iso is not None:
            return to_iso_shanghai(dt_iso), "upstream_iso"

        # RFC 2822 (e.g. Sun, 15 Nov 2026 11:40:51 +0000 / GMT)
        try:
            dt_rfc = parsedate_to_datetime(text)
            if dt_rfc.tzinfo is None:
                dt_rfc = dt_rfc.replace(tzinfo=timezone.utc)
            return to_iso_shanghai(dt_rfc.astimezone(SHANGHAI_TZ)), "upstream_rfc2822"
        except (TypeError, ValueError):
            pass

    return None, None


def format_batch_id(prefix: str, dt: datetime) -> str:
    """Create a deterministic sortable batch ID such as raw-20261115-220500."""
    local_dt = dt.astimezone(SHANGHAI_TZ) if dt.tzinfo else dt.replace(tzinfo=SHANGHAI_TZ)
    return f"{prefix}-{local_dt.strftime('%Y%m%d-%H%M%S')}"
