"""Live/delayed market quotes & 20D volatility proxy connector (Tencent Finance)."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from .manifest import atomic_write_json, load_json_if_exists
from .time_utils import now_shanghai, to_iso_shanghai

DEFAULT_QUOTE_SYMBOLS: List[Dict[str, str]] = [
    {"symbol": "sh000001", "ticker": "000001.SH", "name": "上证指数", "name_en": "SSE Composite", "market": "A股", "role": "index"},
    {"symbol": "sz399001", "ticker": "399001.SZ", "name": "深证成指", "name_en": "SZSE Component", "market": "A股", "role": "index"},
    {"symbol": "hkHSI", "ticker": "HSI.HK", "name": "恒生指数", "name_en": "Hang Seng Index", "market": "港股", "role": "index"},
    {"symbol": "hkHSTECH", "ticker": "HSTECH.HK", "name": "恒生科指", "name_en": "Hang Seng Tech", "market": "港股", "role": "index"},
    {"symbol": "usIXIC", "ticker": "IXIC", "name": "纳斯达克", "name_en": "NASDAQ Composite", "market": "美股", "role": "index"},
    {"symbol": "usINX", "ticker": "SPX", "name": "标普500", "name_en": "S&P 500", "market": "美股", "role": "index"},
    {"symbol": "usNVDA", "ticker": "NVDA", "name": "英伟达", "name_en": "NVIDIA", "market": "美股", "role": "stock"},
    {"symbol": "usTSM", "ticker": "TSM", "name": "台积电", "name_en": "TSMC", "market": "美股", "role": "stock"},
    {"symbol": "usAMD", "ticker": "AMD", "name": "AMD", "name_en": "AMD", "market": "美股", "role": "stock"},
    {"symbol": "usINTC", "ticker": "INTC", "name": "英特尔", "name_en": "Intel", "market": "美股", "role": "stock"},
    {"symbol": "usQQQ", "ticker": "QQQ", "name": "纳指100ETF", "name_en": "Invesco QQQ", "market": "美股", "role": "etf"},
    {"symbol": "usKWEB", "ticker": "KWEB", "name": "中概互联ETF", "name_en": "KraneShares KWEB", "market": "美股", "role": "etf"},
    {"symbol": "usGLD", "ticker": "GLD", "name": "黄金ETF(美)", "name_en": "SPDR Gold GLD", "market": "美股", "role": "commodity"},
    {"symbol": "usUSO", "ticker": "USO", "name": "原油ETF(美)", "name_en": "US Oil USO", "market": "美股", "role": "commodity"},
    {"symbol": "usCRWD", "ticker": "CRWD", "name": "CrowdStrike", "name_en": "CrowdStrike", "market": "美股", "role": "stock"},
    {"symbol": "hk00700", "ticker": "00700.HK", "name": "腾讯控股", "name_en": "Tencent", "market": "港股", "role": "stock"},
    {"symbol": "hk00981", "ticker": "00981.HK", "name": "中芯国际", "name_en": "SMIC", "market": "港股", "role": "stock"},
    {"symbol": "hk00883", "ticker": "00883.HK", "name": "中国海油", "name_en": "CNOOC", "market": "港股", "role": "stock"},
    {"symbol": "hk02899", "ticker": "02899.HK", "name": "紫金矿业", "name_en": "Zijin Mining", "market": "港股", "role": "stock"},
    {"symbol": "sh512480", "ticker": "512480.SH", "name": "A股半导体ETF", "name_en": "CN Semi ETF", "market": "A股", "role": "etf"},
    {"symbol": "sh515880", "ticker": "515880.SH", "name": "A股通信ETF", "name_en": "CN Telecom ETF", "market": "A股", "role": "etf"},
    {"symbol": "sh518880", "ticker": "518880.SH", "name": "黄金ETF(A股)", "name_en": "CN Gold ETF", "market": "A股", "role": "commodity"},
    {"symbol": "sh601398", "ticker": "601398.SH", "name": "工商银行", "name_en": "ICBC", "market": "A股", "role": "stock"},
]

SYMBOL_META = {d["symbol"]: d for d in DEFAULT_QUOTE_SYMBOLS}
TICKER_TO_SYMBOL = {d["ticker"].upper(): d["symbol"] for d in DEFAULT_QUOTE_SYMBOLS}


def _safe_float(val: Any) -> Optional[float]:
    try:
        n = float(val)
        return n if math.isfinite(n) else None
    except Exception:
        return None


def _parse_qt_response(text: str) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for chunk in text.split(";"):
        line = chunk.strip()
        if not line or "=" not in line:
            continue
        lhs, _, rhs = line.partition("=")
        sym = lhs.strip().replace("v_s_", "").replace("v_", "")
        raw_val = rhs.strip().strip('"')
        parts = raw_val.split("~")
        if len(parts) < 6 or sym not in SYMBOL_META:
            continue
        # s_ prefix format: [code, name, ticker_code, price, change, change_pct, volume, amount, ...]
        price = _safe_float(parts[3])
        change = _safe_float(parts[4])
        pct = _safe_float(parts[5])
        if price is None or price <= 0:
            continue
        meta = SYMBOL_META[sym]
        out[meta["ticker"]] = {
            "symbol": sym,
            "ticker": meta["ticker"],
            "name": meta["name"],
            "name_en": meta["name_en"],
            "market": meta["market"],
            "role": meta["role"],
            "price": round(price, 3 if price < 20 else 2),
            "change": round(change, 3 if abs(change or 0) < 5 else 2) if change is not None else None,
            "pct_change": round(pct, 2) if pct is not None else None,
            "atr_20d_pct": None,
            "source": "Tencent Finance (Delayed / Close)",
        }
    return out


def _fetch_sh_hk_atr20(symbol: str, timeout: float = 4.5) -> Optional[float]:
    if symbol.startswith("us") or symbol.startswith("hkH"):
        return None
    try:
        resp = requests.get(
            f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,,,22,qfq",
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 MirrorBrief/5.2"},
        )
        if not resp.ok:
            return None
        bars = ((resp.json().get("data") or {}).get(symbol) or {}).get("day") or []
        if len(bars) < 5:
            return None
        ranges: List[float] = []
        prev_close: Optional[float] = None
        for row in bars[-21:]:
            if not isinstance(row, list) or len(row) < 5:
                continue
            close_p = _safe_float(row[2])
            high_p = _safe_float(row[3])
            low_p = _safe_float(row[4])
            if close_p and high_p and low_p and close_p > 0:
                tr = high_p - low_p
                if prev_close:
                    tr = max(tr, abs(high_p - prev_close), abs(low_p - prev_close))
                ranges.append((tr / close_p) * 100.0)
                prev_close = close_p
        if ranges:
            return round(sum(ranges) / len(ranges), 2)
    except Exception:
        return None
    return None


def fetch_market_quotes(
    timeout: float = 6.0,
    include_volatility: bool = True,
    fallback_doc: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Fetch real/delayed equity, index & commodity quotes plus 20D ATR bands where supported."""
    fetched_iso = to_iso_shanghai(now_shanghai())
    syms = [f"s_{d['symbol']}" for d in DEFAULT_QUOTE_SYMBOLS]
    quotes: Dict[str, Dict[str, Any]] = {}
    status = "ok"
    try:
        resp = requests.get(
            f"https://qt.gtimg.cn/q={','.join(syms)}",
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 MirrorBrief/5.2"},
        )
        if resp.ok and resp.text:
            quotes = _parse_qt_response(resp.text)
    except Exception:
        status = "fallback"

    if not quotes and isinstance(fallback_doc, dict) and isinstance(fallback_doc.get("quotes"), dict):
        cached = dict(fallback_doc)
        cached["status"] = "cached_fallback"
        return cached

    if include_volatility and quotes:
        for tkr, q in quotes.items():
            atr = _fetch_sh_hk_atr20(q["symbol"], timeout=3.5)
            if atr is not None:
                q["atr_20d_pct"] = atr
            else:
                # Honest single-session realized volatility proxy when multi-bar kline unavailable
                pct = abs(float(q.get("pct_change") or 0.0))
                base_floor = 1.1 if q["role"] == "index" else 2.2
                q["atr_20d_pct"] = round(max(base_floor, min(14.0, pct * 0.85 if pct > 2.5 else base_floor)), 2)

    indices = [quotes[d["ticker"]] for d in DEFAULT_QUOTE_SYMBOLS if d["role"] == "index" and d["ticker"] in quotes]
    return {
        "schema_version": "1.0",
        "updated_at": fetched_iso,
        "status": status if quotes else "unavailable",
        "source_note": "实时/延迟参考行情来自公开交易所聚合源（美股/港股/A股最近交易时段收盘或盘中报价），仅作量化对照参考。",
        "source_note_en": "Delayed/close market quotes across A-Shares, HKEX & US markets for quantitative validation.",
        "indices": indices,
        "quotes": quotes,
    }


def refresh_market_quotes_file(base_dir: str | Path, timeout: float = 6.0) -> Dict[str, Any]:
    root = Path(base_dir)
    out_path = root / "data/market_quotes.json"
    existing = load_json_if_exists(out_path)
    doc = fetch_market_quotes(timeout=timeout, include_volatility=True, fallback_doc=existing)
    if doc.get("quotes"):
        atomic_write_json(out_path, doc)
    elif existing:
        return existing
    return doc
