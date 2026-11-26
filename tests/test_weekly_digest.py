"""Unit tests for 2-stage Weekly Major Events Digest distillation & strict deduplication."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest

from pipeline.time_utils import SHANGHAI_TZ
from pipeline.weekly_digest import (
    _CLICHE_PATTERNS,
    SECTOR_IDS,
    _is_title_parrot,
    _make_plain_title,
    _scrub_cliches,
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
    ai_analysis: str = "这件事直接关系接下来几天的资金风向和产业链节奏。",
) -> dict:
    return {
        "event_id": eid,
        "storyline_id": storyline_id or None,
        "title": title,
        "category": category,
        "severity_tier": severity,
        "evidence_status": evidence_status,
        "fact_summary": summary,
        "ai_analysis": ai_analysis,
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

    def test_plain_language_cliche_scrub_and_next_week_outlook_with_live_predictions(self) -> None:
        self.assertEqual(
            _scrub_cliches("持续推进全面从严，深化国际航天领域的科技交流。央行放出8000亿资金托底市场。", fallback="备选"),
            "央行放出8000亿资金托底市场。",
        )
        self.assertEqual(_scrub_cliches("展现开放包容姿态，密切关注后续动态。", fallback="等真金白银落地再看"), "等真金白银落地再看")
        self.assertTrue(_is_title_parrot("黄仁勋回归重任英伟达CEO", "黄仁勋回归，重任CEO！英伟达盘前暴涨"))
        self.assertFalse(_is_title_parrot("换帅风波两天后收场，开盘直接大涨26%", "黄仁勋回归，重任CEO！英伟达盘前暴涨"))
        self.assertIn("8000亿元", _make_plain_title("央行：为保持银行体系流动性充裕，2026年11月25日开展8000亿元MLF操作"))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            day2 = root / "archives" / "smart" / "2026-11-26" / "13-00"
            day2.mkdir(parents=True)
            (root / "data").mkdir(parents=True, exist_ok=True)

            ev_fomc = _sample_event(
                "evt_fed",
                "美联储12月加息概率升至97%",
                "finance",
                severity="S",
                summary="交易员几乎认定下月还会加一次息，美元走高压住大宗商品。",
                ai_analysis="持续推进货币紧缩引发市场广泛关注。美元走高会让新兴市场资金承压。",
            )
            ev_ai = _sample_event(
                "evt_ai",
                "Qwen 4 即将开源引爆算力预期",
                "tech",
                severity="S",
                summary="开源旗舰将压低推理成本，中小团队能用更便宜显卡跑大模型。",
            )
            (day2 / "analysis_finance.json").write_text(json.dumps({"events": [ev_fomc]}, ensure_ascii=False), encoding="utf-8")
            (day2 / "analysis_tech.json").write_text(json.dumps({"events": [ev_ai]}, ensure_ascii=False), encoding="utf-8")

            (root / "data" / "calendar.json").write_text(
                json.dumps(
                    {
                        "events": [
                            {
                                "title": "美国核心PCE物价数据公布",
                                "category": "finance",
                                "scheduled_at": "2026-11-28T21:30:00+08:00",
                                "is_past": False,
                                "watch_variable": "看核心同比有没有超过2.8%",
                            },
                            {
                                "title": "已结束历史日程",
                                "category": "global",
                                "scheduled_at": "2026-11-20T10:00:00+08:00",
                                "is_past": True,
                            },
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (root / "data" / "predictions_public.json").write_text(
                json.dumps(
                    {
                        "predictions": [
                            {
                                "prediction_id": "pred_fed_dec",
                                "title": "美联储12月议息会议是否继续加息25个基点？",
                                "status": "open",
                                "category": "macro",
                                "due_at": "2026-12-10T04:30:00+08:00",
                                "probability_pct": 82,
                                "win_rule": "官方宣布加息25bp即判YES",
                            },
                            {
                                "prediction_id": "pred_qwen_ga",
                                "title": "阿里 Qwen 4 旗舰模型能否在 12 月 16 日前开源？",
                                "status": "open",
                                "category": "tech_ai",
                                "due_at": "2026-12-16T20:00:00+08:00",
                                "probability_pct": 74,
                            },
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            thu = datetime(2026, 11, 26, 18, 0, tzinfo=SHANGHAI_TZ)
            doc = build_and_write_weekly_digest(root, ref_dt=thu, use_ai=False)
            self.assertGreaterEqual(len(doc["next_week_outlook"]), 2)
            linked_ids = {o.get("linked_prediction_id") for o in doc["next_week_outlook"]}
            self.assertTrue("pred_fed_dec" in linked_ids or "pred_qwen_ga" in linked_ids)
            self.assertTrue(any("PCE" in c["title"] for c in doc["next_week_catalysts"]))
            self.assertFalse(any("已结束" in c["title"] for c in doc["next_week_catalysts"]))

            serialized = json.dumps(doc, ensure_ascii=False)
            self.assertIsNone(_CLICHE_PATTERNS.search(serialized))
