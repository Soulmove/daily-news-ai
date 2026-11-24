"""Live/delayed market quotes & 20D volatility proxy connector (Tencent Finance)."""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
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
    {"symbol": "sz399006", "ticker": "399006.SZ", "name": "创业板指", "name_en": "ChiNext Index", "market": "A股", "role": "index_extra"},
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

GOLD_FUTURE_META: Dict[str, Dict[str, str]] = {
    "hf_GC": {"symbol": "hf_GC", "ticker": "GC=F", "name": "COMEX黄金", "name_en": "COMEX Gold", "market": "商品", "role": "commodity"},
    "hf_XAU": {"symbol": "hf_XAU", "ticker": "XAUUSD", "name": "现货黄金", "name_en": "Spot Gold", "market": "商品", "role": "commodity"},
}

SYMBOL_META = {d["symbol"]: d for d in DEFAULT_QUOTE_SYMBOLS}
TICKER_TO_SYMBOL = {d["ticker"].upper(): d["symbol"] for d in DEFAULT_QUOTE_SYMBOLS}

_QUOTE_PRICE_BOUNDS: Dict[str, tuple[float, float]] = {
    "GC=F": (1500.0, 10000.0),
    "XAUUSD": (1500.0, 10000.0),
    "XAU": (1500.0, 10000.0),
    "GLD": (100.0, 1000.0),
    "518880.SH": (2.0, 30.0),
    "000001.SH": (1500.0, 10000.0),
    "399001.SZ": (4000.0, 30000.0),
    "399006.SZ": (1000.0, 6000.0),
    "HSI.HK": (10000.0, 40000.0),
    "HSTECH.HK": (2000.0, 15000.0),
    "IXIC": (8000.0, 40000.0),
    "SPX": (2500.0, 12000.0),
}


def _safe_float(val: Any) -> Optional[float]:
    try:
        n = float(val)
        return n if math.isfinite(n) else None
    except Exception:
        return None


def _is_sane_quote(
    ticker: str,
    role: str,
    price: Optional[float],
    pct_change: Optional[float],
    fallback_quote: Optional[Dict[str, Any]] = None,
) -> bool:
    if price is None or price <= 0:
        return False
    bounds = _QUOTE_PRICE_BOUNDS.get(ticker.upper())
    if bounds and not (bounds[0] <= price <= bounds[1]):
        return False
    max_pct = 25.0 if role in ("index", "index_extra", "commodity") else 65.0
    if pct_change is not None and abs(pct_change) > max_pct:
        return False
    if isinstance(fallback_quote, dict):
        prev_p = _safe_float(fallback_quote.get("price"))
        if prev_p and prev_p > 0 and (price >= prev_p * 3.0 or price <= prev_p * 0.3):
            return False
    return True


def _detect_session_status(dt_sh) -> str:
    if dt_sh.weekday() >= 5:
        return "closed"
    hm = dt_sh.hour * 60 + dt_sh.minute
    if (9 * 60 + 15 <= hm <= 11 * 60 + 35) or (13 * 60 <= hm <= 16 * 60 + 15) or (hm >= 21 * 60 or hm <= 5 * 60 + 15):
        return "trading"
    if 11 * 60 + 35 < hm < 13 * 60:
        return "lunch_break"
    return "closed"


def _fetch_sina_gold_quotes(
    timeout: float = 3.5,
    quote_hhmm: str = "",
    fallback_quotes: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    try:
        resp = requests.get(
            "https://hq.sinajs.cn/list=hf_GC,hf_XAU",
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 MirrorBrief/5.2", "Referer": "https://finance.sina.com.cn"},
        )
        if not resp.ok or not resp.text:
            return out
        for line in resp.text.splitlines():
            if "=" not in line or "hq_str_" not in line:
                continue
            lhs, _, rhs = line.partition("=")
            sym = lhs.split("hq_str_")[-1].strip()
            meta = GOLD_FUTURE_META.get(sym)
            if not meta:
                continue
            raw_val = rhs.strip().strip(";").strip().strip('"')
            parts = raw_val.split(",")
            if len(parts) < 8:
                continue
            price = _safe_float(parts[0])
            prev_close = _safe_float(parts[7]) or _safe_float(parts[8] if len(parts) > 8 else None)
            if price is None or price <= 0:
                continue
            change = round(price - prev_close, 2) if (prev_close and prev_close > 0) else None
            pct = round(((price - prev_close) / prev_close) * 100.0, 2) if (prev_close and prev_close > 0) else None
            fb_q = (fallback_quotes or {}).get(meta["ticker"])
            if not _is_sane_quote(meta["ticker"], meta["role"], price, pct, fb_q):
                continue
            src_time = str(parts[6] or "").strip()[:5] if ":" in str(parts[6] or "") else quote_hhmm
            out[meta["ticker"]] = {
                "symbol": sym,
                "ticker": meta["ticker"],
                "name": meta["name"],
                "name_en": meta["name_en"],
                "market": meta["market"],
                "role": meta["role"],
                "price": round(price, 2),
                "change": change,
                "pct_change": pct,
                "atr_20d_pct": fb_q.get("atr_20d_pct") if isinstance(fb_q, dict) else 1.8,
                "quote_time_hhmm": src_time or quote_hhmm,
                "source": "Sina Finance COMEX/Spot Gold",
            }
    except Exception:
        return {}
    return out


def _parse_qt_response(
    text: str,
    *,
    quote_hhmm: str = "",
    fallback_quotes: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Dict[str, Any]]:
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
        meta = SYMBOL_META[sym]
        fb_q = (fallback_quotes or {}).get(meta["ticker"])
        if not _is_sane_quote(meta["ticker"], meta["role"], price, pct, fb_q):
            continue
        out[meta["ticker"]] = {
            "symbol": sym,
            "ticker": meta["ticker"],
            "name": meta["name"],
            "name_en": meta["name_en"],
            "market": meta["market"],
            "role": meta["role"],
            "price": round(float(price), 3 if float(price) < 20 else 2),
            "change": round(change, 3 if abs(change or 0) < 5 else 2) if change is not None else None,
            "pct_change": round(pct, 2) if pct is not None else None,
            "atr_20d_pct": fb_q.get("atr_20d_pct") if isinstance(fb_q, dict) else None,
            "quote_time_hhmm": quote_hhmm,
            "source": "Tencent Finance (Live / Delayed)",
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
    """Fetch live/delayed equity, index & commodity quotes with sanity bounds & COMEX/spot gold."""
    now_dt = now_shanghai()
    fetched_iso = to_iso_shanghai(now_dt)
    quote_hhmm = now_dt.strftime("%H:%M")
    session_status = _detect_session_status(now_dt)
    fb_quotes = (
        dict(fallback_doc.get("quotes"))
        if isinstance(fallback_doc, dict) and isinstance(fallback_doc.get("quotes"), dict)
        else {}
    )
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
            quotes = _parse_qt_response(resp.text, quote_hhmm=quote_hhmm, fallback_quotes=fb_quotes)
    except Exception:
        status = "fallback"

    # Merge COMEX & Spot Gold quotes from Sina (safe per-ticker bounds prevent wrong-contract/scale errors)
    gold_quotes = _fetch_sina_gold_quotes(timeout=min(3.5, timeout), quote_hhmm=quote_hhmm, fallback_quotes=fb_quotes)
    for g_tkr, g_item in gold_quotes.items():
        quotes[g_tkr] = g_item

    # Keep valid cached ticker entries if individual symbols failed or failed sanity check
    for tkr, fb_q in fb_quotes.items():
        if tkr not in quotes and isinstance(fb_q, dict) and _is_sane_quote(tkr, str(fb_q.get("role") or "stock"), _safe_float(fb_q.get("price")), _safe_float(fb_q.get("pct_change"))):
            quotes[tkr] = dict(fb_q)

    if not quotes and fb_quotes:
        cached = dict(fallback_doc or {})
        cached["status"] = "cached_fallback"
        return cached

    if include_volatility and quotes:
        targets = [q for q in quotes.values() if not str(q.get("symbol") or "").startswith("hf_")]
        with ThreadPoolExecutor(max_workers=6) as pool:
            atr_map = {q["ticker"]: pool.submit(_fetch_sh_hk_atr20, q["symbol"], 2.5) for q in targets}
            for tkr, fut in atr_map.items():
                try:
                    atr = fut.result(timeout=3.0)
                except Exception:
                    atr = None
                q = quotes[tkr]
                if atr is not None:
                    q["atr_20d_pct"] = atr
                elif q.get("atr_20d_pct") is None:
                    pct = abs(float(q.get("pct_change") or 0.0))
                    base_floor = 1.1 if q.get("role") in ("index", "index_extra") else 2.2
                    q["atr_20d_pct"] = round(max(base_floor, min(14.0, pct * 0.85 if pct > 2.5 else base_floor)), 2)

    indices = [quotes[d["ticker"]] for d in DEFAULT_QUOTE_SYMBOLS if d["role"] == "index" and d["ticker"] in quotes]
    return {
        "schema_version": "1.0",
        "updated_at": fetched_iso,
        "quote_time_hhmm": quote_hhmm,
        "session_status": session_status,
        "status": status if quotes else "unavailable",
        "source_note": "实时/延迟参考行情来自公开交易所聚合源（A股/港股/美股/COMEX黄金盘中或最近收盘报价），全站统一口径，仅作量化对照参考。",
        "source_note_en": "Live/delayed market quotes across A-Shares, HKEX, US equities & COMEX Gold for quantitative validation.",
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
