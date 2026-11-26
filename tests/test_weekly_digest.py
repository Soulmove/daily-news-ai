"""Unit tests for 2-stage Weekly Major Events Digest distillation & strict deduplication."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest

from pipeline.time_utils import SHANGHAI_TZ
from pipeline.weekly_digest import (
    SECTOR_IDS,
    build_and_write_weekly_digest,
    compute_natural_week_bounds,
    distill_weekly_candidates,
)


def _sample_event(
    eid: str,
    title: str,
    category: str,
    *,
    storyline_id: str = "",
    severity: str = "A",
    evidence_status: str = "multi_source",
    source_name: str = "路透社",
    url: str = "https://www.reuters.com/world/sample",
    summary: str = "权威多源交叉核验核心进展与关键数据披露。",
) -> dict:
    return {
        "event_id": eid,
        "storyline_id": storyline_id or None,
        "title": title,
        "category": category,
        "severity_tier": severity,
        "evidence_status": evidence_status,
        "fact_summary": summary,
        "ai_analysis": "该事件对产业链与市场预期存在实质性影响。",
        "speculation_or_outlook": "下周需跟踪官方最新统计口径。",
        "entities": ["重点实体"],
        "sources": [{"source_name": source_name, "url": url, "source_tier": "direct_media"}],
        "latest_reported_at": "2026-11-26T10:00:00+08:00",
    }


class WeeklyDigestTests(unittest.TestCase):
    def test_monday_to_sunday_window_calculation(self) -> None:
        # 2026-11-26 is Thursday -> Mon 2026-11-23 to Sun 2026-11-29
        thu = datetime(2026, 11, 26, 17, 0, tzinfo=SHANGHAI_TZ)
        bounds = compute_natural_week_bounds(thu)
        self.assertEqual(bounds["week_id"], "2026-W48")
        self.assertEqual(bounds["week_start"], "2026-11-23")
        self.assertEqual(bounds["week_end"], "2026-11-29")
        self.assertEqual(len(bounds["dates"]), 7)

    def test_distills_dedups_filters_noise_and_separates_four_sectors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            day1 = root / "archives" / "smart" / "2026-11-24" / "10-00"
            day2 = root / "archives" / "smart" / "2026-11-26" / "13-00"
            day1.mkdir(parents=True)
            day2.mkdir(parents=True)

            # Same story appears across Monday/Tuesday/Thursday AND across categories with slightly different phrasing
            ev_gold_1 = _sample_event(
                "evt_g1",
                "现货黄金跌破3500美元/盎司创一年新低",
                "finance",
                storyline_id="st_gold",
                severity="S",
                evidence_status="official_confirmed",
                source_name="新华社",
                url="https://news.cn/gold1",
            )
            ev_gold_2 = _sample_event(
                "evt_g2",
                "现货黄金跌破3500美元关口创近一年来新低",
                "global",
                severity="A",
                source_name="彭博社",
                url="https://bloomberg.com/gold2",
            )
            ev_nvda = _sample_event(
                "evt_nvda",
                "英伟达发布新一代Rubin算力架构与HBM4供应链预期",
                "tech",
                severity="S",
                source_name="GitHub Releases",
                url="https://github.com/nvidia/releases",
            )
            ev_geo = _sample_event(
                "evt_geo",
                "联合国安理会就中东霍尔木兹海峡航运安全举行紧急磋商",
                "global",
                severity="S",
                source_name="联合国新闻",
                url="https://news.un.org/123",
            )
            ev_ind = _sample_event(
                "evt_ind",
                "欧洲航司因航空燃油成本飙升发布财年利润预警",
                "finance",
                severity="A",
                summary="航空燃油成本上涨拖累公司财年净利润下滑。",
                source_name="财新",
                url="https://caixin.com/air",
            )
            # Noise items that MUST be filtered out
            ev_promo = _sample_event(
                "evt_noise_1",
                "某品牌27英寸4K显示器首销到手价999元限免优惠",
                "tech",
                source_name="微博热搜",
            )
            ev_roundup = _sample_event(
                "evt_noise_2",
                "早间要闻汇总：盘前必读财经大事一览",
                "finance",
                source_name="财经汇总",
            )

            (day1 / "analysis_finance.json").write_text(
                json.dumps({"events": [ev_gold_1, ev_roundup]}, ensure_ascii=False), encoding="utf-8"
            )
            (day2 / "analysis_global.json").write_text(
                json.dumps({"events": [ev_gold_2, ev_geo]}, ensure_ascii=False), encoding="utf-8"
            )
            (day2 / "analysis_tech.json").write_text(
                json.dumps({"events": [ev_nvda, ev_promo]}, ensure_ascii=False), encoding="utf-8"
            )
            (day2 / "analysis_finance.json").write_text(
                json.dumps({"events": [ev_ind]}, ensure_ascii=False), encoding="utf-8"
            )

            thu = datetime(2026, 11, 26, 17, 0, tzinfo=SHANGHAI_TZ)
            stage1 = distill_weekly_candidates(root, ref_dt=thu)
            titles = [it["title"] for it in stage1["items"]]

            # Noise rejected
            self.assertFalse(any("999元" in t or "早间要闻" in t for t in titles))
            # Duplicate gold events collapsed into ONE entry cleanly
            gold_hits = [it for it in stage1["items"] if "黄金" in it["title"]]
            self.assertEqual(len(gold_hits), 1)
            self.assertGreaterEqual(gold_hits[0]["day_span"], 2)
            # Strictly separated across the 4 sectors
            by_sector = {s: stage1["sector_buckets"][s] for s in SECTOR_IDS}
            self.assertTrue(any("黄金" in x["title"] for x in by_sector["macro_finance"]))
            self.assertTrue(any("英伟达" in x["title"] for x in by_sector["tech_ai"]))
            self.assertTrue(any("联合国" in x["title"] or "海峡" in x["title"] for x in by_sector["geopolitics"]))
            self.assertTrue(any("航司" in x["title"] for x in by_sector["industry_society"]))

            # Stage 2 deterministic write outputs weekly_digest.json + archive + index
            doc = build_and_write_weekly_digest(root, ref_dt=thu, use_ai=False)
            self.assertEqual(doc["week_id"], "2026-W48")
            self.assertEqual(len(doc["sectors"]), 4)
            self.assertTrue((root / "data" / "weekly_digest.json").is_file())
            self.assertTrue((root / "data" / "weekly_digests" / "2026-W48.json").is_file())
            idx = json.loads((root / "data" / "weekly_digests_index.json").read_text(encoding="utf-8"))
            self.assertEqual(idx["latest_week_id"], "2026-W48")
