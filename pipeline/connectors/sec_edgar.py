"""SEC EDGAR official filings & XBRL financial metrics connector."""

from __future__ import annotations

from datetime import timedelta
import re
import time
from typing import Any, Dict, List, Optional

from pipeline.connectors.base import HttpCacheStore, SEC_EDGAR_USER_AGENT, polite_get
from pipeline.id_utils import make_raw_item_id
from pipeline.manifest import atomic_write_json, load_json_if_exists
from pipeline.time_utils import now_shanghai, parse_iso_datetime, parse_published_at, to_iso_shanghai

DEFAULT_SEC_ENTITIES = [
    {"entity_id": "ent_nvidia", "ticker": "NVDA", "name": "英伟达 (NVIDIA)", "cik": "0001045810"},
    {"entity_id": "ent_amd", "ticker": "AMD", "name": "AMD", "cik": "0000002488"},
    {"entity_id": "ent_intel", "ticker": "INTC", "name": "英特尔 (Intel)", "cik": "0000050863"},
    {"entity_id": "ent_memory_chips", "ticker": "MU", "name": "美光科技 (Micron)", "cik": "0000723125"},
    {"entity_id": "ent_tsmc", "ticker": "TSM", "name": "台积电 (TSMC ADR)", "cik": "0001046179"},
    {"entity_id": "ent_google", "ticker": "GOOGL", "name": "Alphabet / Google", "cik": "0001652044"},
    {"entity_id": "ent_microsoft", "ticker": "MSFT", "name": "微软 (Microsoft)", "cik": "0000789019"},
]

SEC_FORMS_KEEP = {"10-K", "10-Q", "8-K", "6-K", "20-F"}


def _build_sec_doc_url(cik: str, accession: str, primary_doc: str) -> str:
    cik_num = str(int(cik))
    acc_clean = accession.replace("-", "")
    if primary_doc:
        return f"https://www.sec.gov/Archives/edgar/data/{cik_num}/{acc_clean}/{primary_doc}"
    return f"https://www.sec.gov/Archives/edgar/data/{cik_num}/{acc_clean}/"


def _format_sec_filing_description(form: str, raw_desc: str, items: List[str], primary_doc: str) -> str:
    """Translate bare SEC form codes like '6-K' / '8-K' / '10-Q' into clear Chinese+English titles."""
    f = str(form or "").upper()
    desc = str(raw_desc or "").strip()
    doc_l = str(primary_doc or "").lower()
    item_map = {
        "1.01": "重大确定性协议签署",
        "2.02": "季度/年度经营业绩披露",
        "5.02": "董事/高管人事变动",
        "5.03": "公司章程修订",
        "7.01": "FD 规定重大信息披露",
        "8.01": "其他重大事项公告",
    }
    if f == "6-K":
        if "revenue" in doc_l:
            return "月度营收报告 (Form 6-K Monthly Revenue)"
        if "fsx" in doc_l or "financial" in doc_l:
            return "季度合并审阅财务报表 (Form 6-K Financials)"
        if "board" in doc_l:
            return "董事会重要决议公告 (Form 6-K Board Resolution)"
        if "dividend" in doc_l or "cash" in doc_l:
            return "股息分派公告 (Form 6-K Dividend)"
        if desc and desc.upper() not in {"6-K", "FORM 6-K"}:
            return f"外国发行人重大披露 (Form 6-K · {desc[:48]})"
        return "外国发行人重大披露 / 业绩声明 (Form 6-K)"
    if f == "8-K":
        matched = [item_map[str(it)] for it in (items or []) if str(it) in item_map]
        if matched:
            return f"重大事件公告 (Form 8-K · {' / '.join(matched[:2])})"
        if desc and desc.upper() not in {"8-K", "FORM 8-K"}:
            return f"重大事件公告 (Form 8-K · {desc[:48]})"
        return "重大事件临时公告 (Form 8-K)"
    if f == "10-Q":
        return "美国上市公司季度财务报告 (Form 10-Q)"
    if f == "10-K":
        return "美国上市公司年度财务报告 (Form 10-K)"
    if f == "20-F":
        return "外国私人发行人年度综合报告 (Form 20-F)"
    return desc or f


def _extract_tsmc_6k_revenue_actuals(
    cik: str,
    recent: dict,
    headers: Dict[str, str],
) -> List[Dict[str, Any]]:
    """Fallback when SEC CompanyFacts IFRS endpoint stops at 2024: extract 2025/2026 TSMC revenue from official 6-K reports."""
    if cik != "0001046179":
        return []
    forms = recent.get("form") or []
    acc_nums = recent.get("accessionNumber") or []
    primary_docs = recent.get("primaryDocument") or []
    filing_dates = recent.get("filingDate") or []
    report_dates = recent.get("reportDate") or []
    out: List[Dict[str, Any]] = []
    seen_periods: set[str] = set()
    for i, form in enumerate(forms):
        if form != "6-K":
            continue
        pdoc = str(primary_docs[i] if i < len(primary_docs) else "")
        if "revenue" not in pdoc.lower():
            continue
        acc = str(acc_nums[i] if i < len(acc_nums) else "")
        if not acc or not pdoc:
            continue
        rdate = str(report_dates[i] if i < len(report_dates) else "")
        fdate = str(filing_dates[i] if i < len(filing_dates) else "")
        if not rdate or rdate in seen_periods:
            continue
        url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{pdoc}"
        res = polite_get(url, headers={**headers, "Accept": "text/html"}, cache=None, timeout=(5, 8), expect_json=False)
        if not res.ok or not res.text:
            continue
        plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", res.text))
        m_mon = re.search(r"revenue\s+for\s+[A-Za-z]+\s+20\d{2}\s+was\s+approximately\s+NT\$\s*([\d,.]+)\s*billion", plain, re.I)
        if m_mon:
            val_b = float(m_mon.group(1).replace(",", ""))
            seen_periods.add(rdate)
            out.append(
                {
                    "metric": "月度合并营收 (TSMC 6-K)",
                    "value": f"NT${val_b:,.2f}B",
                    "raw_val": round(val_b * 1e9, 0),
                    "unit": "TWD",
                    "period_end": rdate,
                    "filed": fdate,
                    "form": "6-K",
                    "frame": rdate[:7],
                    "concept": "ifrs-6k-monthly-revenue",
                }
            )
        if len(out) >= 4:
            break
    return out


def _extract_quarterly_revenue(companyfacts: dict) -> List[Dict[str, Any]]:
    facts = companyfacts.get("facts", {})
    us_gaap = facts.get("us-gaap", {})
    ifrs_full = facts.get("ifrs-full", {})

    concept_sources = [
        (us_gaap, "RevenueFromContractWithCustomerExcludingAssessedTax", "USD"),
        (us_gaap, "Revenues", "USD"),
        (us_gaap, "SalesRevenueNet", "USD"),
        (us_gaap, "SalesRevenueGoodsNet", "USD"),
        (ifrs_full, "Revenue", "USD"),
        (ifrs_full, "Revenue", "TWD"),
    ]
    by_cur_end: Dict[str, Dict[str, tuple[str, dict, str]]] = {}

    for ns, concept, cur in concept_sources:
        node = ns.get(concept)
        if not isinstance(node, dict):
            continue
        unit_rows = node.get("units", {}).get(cur, [])
        if not unit_rows:
            continue
        cur_map = by_cur_end.setdefault(cur, {})
        rows = [
            x
            for x in unit_rows
            if x.get("form") in {"10-Q", "10-K", "20-F", "6-K"} and x.get("val") is not None and x.get("end")
        ]
        for r in rows:
            end_d = str(r["end"])
            frame = str(r.get("frame") or "")
            is_q = frame.endswith(("Q1", "Q2", "Q3", "Q4"))
            prev = cur_map.get(end_d)
            if prev is None:
                cur_map[end_d] = (concept, r, cur)
            else:
                prev_frame = str(prev[1].get("frame") or "")
                prev_is_q = prev_frame.endswith(("Q1", "Q2", "Q3", "Q4"))
                prev_filed = str(prev[1].get("filed") or "")
                curr_filed = str(r.get("filed") or "")
                if (is_q and not prev_is_q) or (is_q == prev_is_q and curr_filed > prev_filed):
                    cur_map[end_d] = (concept, r, cur)

    # Keep ONE consistent reporting currency across all returned periods (never mix USD & TWD in one company table)
    chosen_map: Dict[str, tuple[str, dict, str]] = {}
    if by_cur_end:
        best_cur = max(
            by_cur_end.keys(),
            key=lambda c: (
                min(len(by_cur_end[c]), 4),
                1 if c == "USD" else 0,
                max(by_cur_end[c].keys()) if by_cur_end[c] else "",
            ),
        )
        chosen_map = by_cur_end[best_cur]

    sorted_ends = sorted(chosen_map.keys(), reverse=True)[:4]
    out: List[Dict[str, Any]] = []
    for ed in sorted_ends:
        concept, r, cur = chosen_map[ed]
        val = float(r["val"])
        unit_label = "十亿美元" if cur == "USD" else f"十亿{cur}"
        out.append(
            {
                "metric": f"营业收入 ({cur})",
                "concept": concept,
                "value": round(val / 1e9, 2),
                "unit": unit_label,
                "period_end": ed,
                "frame": r.get("frame") or r.get("fp") or r.get("form"),
                "form": r.get("form"),
                "filed": r.get("filed"),
                "source_url": "https://www.sec.gov/search-filings/edgar-application-programming-interfaces",
            }
        )
    return out


def fetch_sec_edgar(
    cache: HttpCacheStore,
    base_dir: str = ".",
    *,
    entities: Optional[List[dict]] = None,
    fetch_facts_for_top_n: int = 7,
) -> Dict[str, Any]:
    """Fetch official SEC EDGAR recent filings & selected XBRL GAAP revenue metrics."""
    targets = entities or DEFAULT_SEC_ENTITIES
    fetched_iso = to_iso_shanghai(now_shanghai())
    t0 = time.monotonic()

    items: List[dict] = []
    entity_updates: Dict[str, dict] = {}
    errors: List[str] = []
    facts_cache_path = f"{base_dir}/data/sec_companyfacts_cache.json"
    facts_cache = load_json_if_exists(facts_cache_path, default={})
    if not isinstance(facts_cache, dict):
        facts_cache = {}
    facts_dirty = False

    headers = {"User-Agent": SEC_EDGAR_USER_AGENT, "Accept": "application/json"}

    for idx, target in enumerate(targets):
        cik = str(target["cik"]).zfill(10)
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        res = polite_get(url, headers=headers, cache=None, timeout=(5, 10), expect_json=True)
        if not res.ok or not isinstance(res.json_data, dict):
            errors.append(f"{target['ticker']}: {res.error_message}")
            continue

        data = res.json_data
        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        filing_dates = recent.get("filingDate", [])
        report_dates = recent.get("reportDate", [])
        accessions = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])
        primary_descs = recent.get("primaryDocDescription", [])
        item_codes = recent.get("items", [])

        ent_filings: List[dict] = []
        now_dt = now_shanghai()
        for i in range(min(len(forms), 40)):
            form = str(forms[i] or "")
            if form not in SEC_FORMS_KEEP:
                continue
            fdate = str(filing_dates[i] or "")
            acc = str(accessions[i] or "")
            pdoc = str(primary_docs[i] or "")
            pdesc = str(primary_descs[i] or "")
            icodes = item_codes[i] if i < len(item_codes) else []
            if isinstance(icodes, str):
                icodes = [icodes] if icodes else []
            doc_url = _build_sec_doc_url(cik, acc, pdoc)
            pub_iso, _ = parse_published_at(fdate, "sec-edgar")
            pdoc_val = str(primary_docs[i] if i < len(primary_docs) else "")
            readable_desc = _format_sec_filing_description(form, pdesc, icodes, pdoc_val)
            filing_rec = {
                "form": form,
                "filing_date": fdate,
                "report_date": report_dates[i] if i < len(report_dates) else None,
                "items": icodes,
                "description": readable_desc,
                "url": doc_url,
            }
            ent_filings.append(filing_rec)
            # Only push SEC filings <= 14 days old into today's daily news stream; keep up to 6 in EntityDrawer
            pub_dt = parse_iso_datetime(pub_iso) if pub_iso else None
            is_recent_news = bool(pub_dt and (now_dt - pub_dt) <= timedelta(days=7))
            if len(ent_filings) == 1 and is_recent_news:
                items_str = f" (Items: {','.join(str(c) for c in icodes)})" if icodes else ""
                title = f"[SEC {form}] {target['name']} 提交监管文件 {form}{items_str} ({fdate})"
                excerpt = f"SEC EDGAR 官方披露：{data.get('name', target['name'])} (CIK {cik}) 于 {fdate} 提交 {form}{items_str}。"
                items.append(
                    {
                        "item_id": make_raw_item_id("sec-edgar", doc_url, title),
                        "source_id": "sec-edgar",
                        "source_name": "SEC EDGAR 官方披露",
                        "source_kind": "official_filing",
                        "source_tier": "first_party",
                        "publisher_family": "sec-edgar",
                        "citable_as_news": True,
                        "category": "finance",
                        "title": title,
                        "url": doc_url,
                        "canonical_url": doc_url,
                        "published_at": pub_iso,
                        "published_at_source": "sec_filing_date",
                        "fetched_at": fetched_iso,
                        "excerpt": excerpt,
                        "entity_ids": [target["entity_id"]],
                        "filing_meta": filing_rec,
                    }
                )
            if len(ent_filings) >= 6:
                break

        # Refresh cached companyfacts dynamically (>180 days old, missing, or mixing currencies)
        actuals = facts_cache.get(cik, {}).get("actuals", [])
        mixed_currencies = len({str(a.get("unit") or "") for a in actuals if a.get("unit")}) > 1
        stale_cutoff = (now_dt - timedelta(days=180)).strftime("%Y-%m-%d")
        cache_is_stale = not actuals or str(actuals[0].get("period_end") or "") < stale_cutoff or mixed_currencies
        if idx < fetch_facts_for_top_n and cache_is_stale:
            facts_url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
            f_res = polite_get(facts_url, headers=headers, cache=cache, timeout=(6, 12), expect_json=True)
            if f_res.ok and isinstance(f_res.json_data, dict):
                fresh_actuals = _extract_quarterly_revenue(f_res.json_data)
                if cik == "0001046179":
                    extra_tsmc = _extract_tsmc_6k_revenue_actuals(cik, recent, headers)
                    if extra_tsmc:
                        by_end = {str(a.get("period_end")): a for a in fresh_actuals}
                        for row in extra_tsmc:
                            by_end[str(row["period_end"])] = row
                        fresh_actuals = sorted(by_end.values(), key=lambda x: str(x["period_end"]), reverse=True)[:4]
                if fresh_actuals:
                    actuals = fresh_actuals
                    facts_cache[cik] = {"updated_at": fetched_iso, "actuals": actuals}
                    facts_dirty = True

        cutoff_502 = (now_dt - timedelta(days=21)).strftime("%Y-%m-%d")
        entity_updates[target["entity_id"]] = {
            "latest_8k_date": next((f["filing_date"] for f in ent_filings if f["form"] == "8-K"), None),
            "has_recent_502_officer_change": any(
                "5.02" in ",".join(str(x) for x in (f.get("items") or []))
                for f in ent_filings
                if f["form"] == "8-K" and f["filing_date"] >= cutoff_502
            ),
            "recent_filings": ent_filings[:6],
            "financial_actuals": actuals,
            "checked_at": fetched_iso,
        }

    if facts_dirty:
        atomic_write_json(facts_cache_path, facts_cache)

    status = "ok" if items else ("error" if errors else "empty")
    if items and errors:
        status = "partial"

    return {
        "connector_id": "sec-edgar",
        "connector_name": "SEC EDGAR 官方监管披露与 XBRL 财报库",
        "source_tier": "first_party",
        "status": status,
        "fetched_at": fetched_iso,
        "latency_ms": int((time.monotonic() - t0) * 1000),
        "item_count": len(items),
        "error_message": "; ".join(errors[:2]) if errors else None,
        "tos_note": "SEC 公开数据，已附带合规声明式 User-Agent 与保守请求节流。",
        "items": items,
        "entity_updates": entity_updates,
    }
