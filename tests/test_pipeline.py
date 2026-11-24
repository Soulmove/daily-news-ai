"""Unit tests for Insight Pro V2.0 data pipeline (time parsing, IDs, dedup, verifier, manifest)."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from pipeline.build_briefing import build_briefing_batch
from pipeline.connectors.article_enricher import parse_article_html
from pipeline.dedup import deduplicate_raw_items, title_similarity
from pipeline.fetch_raw import fetch_raw_snapshot
from pipeline.id_utils import (
    canonicalize_url,
    is_generic_quote_or_homepage_url,
    make_event_id,
    make_raw_item_id,
)
from pipeline.manifest import atomic_write_json
from pipeline.time_utils import parse_published_at
from pipeline.verifier import validate_published_briefing, verify_and_enrich_event


class TimeParsingTests(unittest.TestCase):
    def test_epoch_ms_converts_to_shanghai(self):
        # 2026-11-15T13:40:00Z == 2026-11-15T21:40:00+08:00
        # Let's compute exact timestamp via datetime
        from datetime import datetime, timezone
        ts_ms = int(datetime(2026, 11, 15, 13, 40, 0, tzinfo=timezone.utc).timestamp() * 1000)
        iso, prov = parse_published_at(ts_ms, "cls-depth")
        self.assertEqual(iso, "2026-11-15T21:40:00+08:00")
        self.assertEqual(prov, "upstream_epoch")

    def test_rfc2822_and_iso_utc_convert_to_shanghai(self):
        iso1, _ = parse_published_at("Sun, 15 Nov 2026 11:40:51 +0000", "hackernews")
        self.assertEqual(iso1, "2026-11-15T19:40:51+08:00")

        iso2, _ = parse_published_at("2026-11-15T13:44:43.000Z", "mktnews-flash")
        self.assertEqual(iso2, "2026-11-15T21:44:43+08:00")

    def test_naive_local_cst_parses_with_shanghai_tz(self):
        iso, prov = parse_published_at("2026-11-15 21:20:40", "ithome")
        self.assertEqual(iso, "2026-11-15T21:20:40+08:00")
        self.assertEqual(prov, "upstream_local_cst")

    def test_missing_pubdate_returns_none_never_current_time(self):
        self.assertEqual(parse_published_at(None, "weibo"), (None, None))
        self.assertEqual(parse_published_at("", "zhihu"), (None, None))
        self.assertEqual(parse_published_at("not-a-date", "zhihu"), (None, None))


class IdAndUrlTests(unittest.TestCase):
    def test_canonicalize_strips_tracking_and_rejects_placeholders(self):
        self.assertIsNone(canonicalize_url("#"))
        self.assertIsNone(canonicalize_url(""))
        self.assertIsNone(canonicalize_url("javascript:void(0)"))

        cleaned = canonicalize_url("HTTPS://Kaopu.News/story/2026-11-15/test/?utm_source=rss&utm_medium=feed#frag")
        self.assertEqual(cleaned, "https://kaopu.news/story/2026-11-15/test")

        # Preserves functional query params like ?id= or ?wd=
        hn = canonicalize_url("https://news.ycombinator.com/item?id=50506180")
        self.assertEqual(hn, "https://news.ycombinator.com/item?id=50506180")

    def test_rejects_stock_quote_and_bare_homepages(self):
        self.assertTrue(is_generic_quote_or_homepage_url("https://xueqiu.com/s/NVDA", "xueqiu-hotstock"))
        self.assertTrue(is_generic_quote_or_homepage_url("https://xueqiu.com/s/09926", "wallstreetcn-hot"))
        self.assertTrue(is_generic_quote_or_homepage_url("https://wallstreetcn.com/", "wallstreetcn-hot"))
        self.assertFalse(is_generic_quote_or_homepage_url("https://wallstreetcn.com/articles/3785942", "wallstreetcn-hot"))

    def test_stable_deterministic_ids(self):
        id1 = make_raw_item_id("ithome", "https://www.ithome.com/1/027/451.htm", "标题A")
        id2 = make_raw_item_id("ithome", "https://www.ithome.com/1/027/451.htm", "标题A微调")
        self.assertEqual(id1, id2)
        ev1 = make_event_id("tech", id1, "标题A")
        ev1_repeat = make_event_id("tech", id1, "标题A")
        ev_diff = make_event_id("tech", id1, "完全不同的标题B")
        self.assertEqual(ev1, ev1_repeat)
        self.assertNotEqual(ev1, ev_diff)


class DedupAndVerifierTests(unittest.TestCase):
    def test_dedup_merges_same_url_and_similar_titles(self):
        items = [
            {
                "item_id": "zaobao_1",
                "source_id": "zaobao",
                "source_name": "联合早报",
                "source_kind": "news",
                "title": "深陷丑闻的黄仁勋辞职，AI芯片巨头Nvidia陷入动荡",
                "url": "https://www.zaochenbao.com/news/world/202611/1585569.html",
                "canonical_url": "https://www.zaochenbao.com/news/world/202611/1585569.html",
                "published_at": "2026-11-15T19:15:46+08:00",
                "fetched_at": "2026-11-15T21:58:00+08:00",
                "excerpt": None,
            },
            {
                "item_id": "juejin_1",
                "source_id": "juejin",
                "source_name": "稀土掘金",
                "source_kind": "news",
                "title": "黄仁勋辞去英伟达 CEO，结束 33 年掌舵生涯",
                "url": "https://juejin.cn/post/7707194766860025907",
                "canonical_url": "https://juejin.cn/post/7707194766860025907",
                "published_at": None,
                "fetched_at": "2026-11-15T21:58:00+08:00",
                "excerpt": None,
            },
            {
                "item_id": "wallstreetcn_earnings",
                "source_id": "wallstreetcn-hot",
                "source_name": "华尔街见闻",
                "source_kind": "news",
                "title": "英伟达下周公布季度财报与数据中心指引",
                "url": "https://wallstreetcn.com/articles/3785944",
                "canonical_url": "https://wallstreetcn.com/articles/3785944",
                "published_at": None,
                "fetched_at": "2026-11-15T21:58:00+08:00",
                "excerpt": None,
            },
        ]
        clustered = deduplicate_raw_items(items, similarity_threshold=0.45)
        # First two stories about Jensen resignation merge; earnings story stays separate!
        self.assertEqual(len(clustered), 2)
        self.assertEqual(len(clustered[0]["related_sources"]), 2)

    def test_verifier_rejects_quote_urls_and_missing_refs(self):
        ref_lookup = {
            "R001": {
                "item_id": "xueqiu_nvda",
                "source_id": "xueqiu-hotstock",
                "source_name": "雪球 · 热门股票",
                "source_kind": "market_ticker",
                "citable_as_news": False,
                "title": "英伟达",
                "url": "https://xueqiu.com/s/NVDA",
                "canonical_url": "https://xueqiu.com/s/NVDA",
                "published_at": None,
                "fetched_at": "2026-11-15T21:58:00+08:00",
                "excerpt": None,
            },
            "R002": {
                "item_id": "wallstreetcn_1",
                "source_id": "wallstreetcn-hot",
                "source_name": "华尔街见闻 · 最热",
                "source_kind": "news",
                "citable_as_news": True,
                "title": "“AI央行”失去掌舵人，华尔街警告：黄仁勋离开将引爆“AI版量化紧缩”！",
                "url": "https://wallstreetcn.com/articles/3785942",
                "canonical_url": "https://wallstreetcn.com/articles/3785942",
                "published_at": None,
                "fetched_at": "2026-11-15T21:58:00+08:00",
                "excerpt": "华尔街研报讨论管理层变动影响。",
            },
        }
        id_lookup = {v["item_id"]: v for v in ref_lookup.values()}

        # Case 1: Only invalid quote ref -> becomes needs_verification, 0 sources
        bad_ev = verify_and_enrich_event(
            {"title": "黄仁勋辞职传闻冲击芯片股", "fact_summary": "黄仁勋消息引震荡", "source_refs": ["R001", "R999"]},
            category="finance",
            input_batch_id="raw-20261115-215800",
            fetched_at_iso="2026-11-15T21:58:00+08:00",
            ref_lookup=ref_lookup,
            id_lookup=id_lookup,
            prev_events=[],
            prev_batch_id=None,
        )
        self.assertEqual(bad_ev["evidence_status"], "needs_verification")
        self.assertEqual(len(bad_ev["sources"]), 0)
        self.assertEqual(len(bad_ev["verification"]["rejected_refs"]), 2)

        # Case 2: Valid news ref -> single_source with material_depth title_and_excerpt
        good_ev = verify_and_enrich_event(
            {"title": "黄仁勋离开传闻引发华尔街估值讨论", "fact_summary": "华尔街警告黄仁勋离开或引发估值回调", "source_refs": ["R001", "R002"]},
            category="finance",
            input_batch_id="raw-20261115-215800",
            fetched_at_iso="2026-11-15T21:58:00+08:00",
            ref_lookup=ref_lookup,
            id_lookup=id_lookup,
            prev_events=[],
            prev_batch_id=None,
        )
        self.assertEqual(good_ev["evidence_status"], "single_source")
        self.assertEqual(good_ev["material_depth"], "title_and_excerpt")
        self.assertEqual(good_ev["sources"][0]["url"], "https://wallstreetcn.com/articles/3785942")

        ok, errs = validate_published_briefing(
            {
                "batch_id": "smart-20261115-220000",
                "input_batch_id": "raw-20261115-215800",
                "input_cutoff_at": "2026-11-15T21:58:00+08:00",
                "generated_at": "2026-11-15T22:00:00+08:00",
                "category": "finance",
                "events": [good_ev, bad_ev],
            }
        )
        self.assertTrue(ok, errs)

    def test_cross_lingual_similarity_oxford_motors(self):
        sim = title_similarity("牛津大学分子马达研究新进展", "Oxford Molecular Motors")
        self.assertGreaterEqual(sim, 0.25)

    def test_atomic_write_json(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            target = tmp / "sub" / "test.json"
            atomic_write_json(target, {"ok": True})
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"ok": True})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class V3PipelineRegressionTests(unittest.TestCase):
    def test_omnibus_article_split_unique_event_ids(self):
        shared_raw = {
            "item_id": "aihot_b5c527640b00",
            "source_id": "aihot",
            "source_name": "AI资讯",
            "source_kind": "news",
            "source_tier": "aggregator_lead",
            "citable_as_news": True,
            "title": "AI 资讯早报：Qwen4-Max 亮相与芯片管理层传闻",
            "url": "https://aihot.today/daily/2026-11-15",
            "canonical_url": "https://aihot.today/daily/2026-11-15",
            "published_at": "2026-11-15T10:00:00+08:00",
            "fetched_at": "2026-11-15T21:58:00+08:00",
            "excerpt": "今日早报汇总多条 AI 行业要闻。",
        }
        ref_lookup = {"R001": shared_raw}
        id_lookup = {shared_raw["item_id"]: shared_raw}
        used_ids = set()

        ev1 = verify_and_enrich_event(
            {"title": "英伟达 CEO 黄仁勋辞任传闻流出", "fact_summary": "黄仁勋辞任消息引发市场讨论。", "source_refs": ["R001"]},
            category="tech",
            input_batch_id="raw-20261115-215800",
            fetched_at_iso="2026-11-15T21:58:00+08:00",
            ref_lookup=ref_lookup,
            id_lookup=id_lookup,
            prev_events=[],
            prev_batch_id=None,
            require_semantic_match=False,
            used_event_ids=used_ids,
            ordinal=0,
        )
        ev2 = verify_and_enrich_event(
            {"title": "Qwen4-Max 模型首次亮相评测", "fact_summary": "阿里 Qwen4-Max 新模型首次亮相。", "source_refs": ["R001"]},
            category="tech",
            input_batch_id="raw-20261115-215800",
            fetched_at_iso="2026-11-15T21:58:00+08:00",
            ref_lookup=ref_lookup,
            id_lookup=id_lookup,
            prev_events=[],
            prev_batch_id=None,
            require_semantic_match=False,
            used_event_ids=used_ids,
            ordinal=1,
        )
        self.assertNotEqual(ev1["event_id"], ev2["event_id"])
        self.assertNotEqual(ev1["storyline_id"], ev2["storyline_id"])

    def test_reprint_does_not_inflate_independent_count_or_fact_time(self):
        orig = {
            "item_id": "wallstreetcn_orig",
            "source_id": "wallstreetcn-hot",
            "source_name": "华尔街见闻",
            "source_kind": "news",
            "publisher_family": "wallstreetcn",
            "title": "英伟达公布最新季度财报营收大幅增长",
            "url": "https://wallstreetcn.com/articles/111",
            "canonical_url": "https://wallstreetcn.com/articles/111",
            "published_at": "2026-11-15T10:00:00+08:00",
            "fetched_at": "2026-11-15T21:58:00+08:00",
            "excerpt": "官方营收同比大增，超出此前季度基准。",
        }
        reprint = {
            "item_id": "cls_reprint",
            "source_id": "cls-telegraph",
            "source_name": "财联社转载",
            "source_kind": "news",
            "publisher_family": "cls",
            "title": "英伟达公布最新季度财报营收大幅增长！",
            "url": "https://www.cls.cn/detail/222",
            "canonical_url": "https://www.cls.cn/detail/222",
            "published_at": "2026-11-15T14:30:00+08:00",
            "fetched_at": "2026-11-15T21:58:00+08:00",
            "excerpt": "官方营收同比大增，超出此前季度基准。",
        }
        ev = verify_and_enrich_event(
            {"title": "英伟达最新季度财报营收增长", "fact_summary": "英伟达公布季度财报营收同比大幅增长。", "source_refs": ["R001", "R002"]},
            category="finance",
            input_batch_id="raw-20261115-215800",
            fetched_at_iso="2026-11-15T21:58:00+08:00",
            ref_lookup={"R001": orig, "R002": reprint},
            id_lookup={orig["item_id"]: orig, reprint["item_id"]: reprint},
            prev_events=[],
            prev_batch_id=None,
        )
        self.assertEqual(ev["independent_publisher_count"], 1)
        self.assertEqual(ev["reprint_count"], 1)
        self.assertEqual(ev["first_reported_at"], "2026-11-15T10:00:00+08:00")
        self.assertEqual(ev["latest_reported_at"], "2026-11-15T14:30:00+08:00")
        self.assertEqual(ev["published_at"], "2026-11-15T10:00:00+08:00")

    def test_sec_8k_contradiction_adds_rumor_qualifier(self):
        raw = {
            "item_id": "wscn_rumor",
            "source_id": "wallstreetcn-hot",
            "source_name": "华尔街见闻",
            "source_kind": "news",
            "title": "英伟达CEO黄仁勋辞任传闻冲击算力链",
            "url": "https://wallstreetcn.com/articles/3785999",
            "canonical_url": "https://wallstreetcn.com/articles/3785999",
            "published_at": "2026-11-15T20:00:00+08:00",
            "fetched_at": "2026-11-15T21:58:00+08:00",
            "excerpt": "市场传出相关高管辞任讨论，尚未见公司公告。",
        }
        ev = verify_and_enrich_event(
            {
                "title": "英伟达CEO黄仁勋辞任，引发算力股震荡",
                "fact_summary": "黄仁勋辞任引发市场广泛关注。",
                "unverified_claims": ["尚未证实的高管变动消息"],
                "source_refs": ["R001"],
            },
            category="tech",
            input_batch_id="raw-20261115-215800",
            fetched_at_iso="2026-11-15T21:58:00+08:00",
            ref_lookup={"R001": raw},
            id_lookup={raw["item_id"]: raw},
            prev_events=[],
            prev_batch_id=None,
            sec_entity_status={
                "ent_nvidia": {"latest_8k_date": "2026-11-14", "has_recent_502_officer_change": False}
            },
        )
        self.assertTrue(ev["contradictions"])
        self.assertIsNotNone(ev["attribution_warning"])
        self.assertTrue(ev["title"].startswith("报道称：") or "传闻" in ev["title"])
        self.assertIn("尚未见官方披露确认", ev["fact_summary"])

    def test_selective_html_article_lead_parser(self):
        sample_html = """<!doctype html><html><head>
        <meta name="description" content="国家超算中心与行业联合发布新一代国产开源模型评估规范。">
        <script type="application/ld+json">{"datePublished": "2026-11-15T18:30:00+08:00"}</script>
        </head><body>
        <p>Cookie Policy accept all</p>
        <p>今天上午，研发团队正式开源新一代模型推理引擎并公布 Apache 2.0 许可证与性能基准。</p>
        </body></html>"""
        parsed = parse_article_html(sample_html)
        self.assertEqual(parsed["published_at"], "2026-11-15T18:30:00+08:00")
        self.assertIn("Apache 2.0", parsed["lead_excerpt"])

    def test_upstream_fail_isolation_with_connectors(self):
        tmp = Path(tempfile.mkdtemp())
        mock_connectors = {
            "schema_version": "3.0",
            "fetched_at": "2026-11-15T22:00:00+08:00",
            "summary": {"total_connectors": 1, "healthy_connectors": 1, "total_first_party_items": 1, "tech_tools_count": 0, "calendar_events_count": 0},
            "connectors": [{"connector_id": "sec-edgar", "connector_name": "SEC EDGAR", "source_tier": "first_party", "status": "ok", "fetched_at": "2026-11-15T22:00:00+08:00", "latency_ms": 120, "item_count": 1, "calendar_count": 0, "error_message": None}],
            "items": [{
                "item_id": "sec-edgar_test001",
                "source_id": "sec-edgar",
                "source_name": "SEC EDGAR 官方披露",
                "source_kind": "official_filing",
                "source_tier": "first_party",
                "citable_as_news": True,
                "category": "finance",
                "title": "[SEC 8-K] 英伟达 (NVIDIA) 提交监管文件 8-K",
                "url": "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000001/doc.htm",
                "canonical_url": "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000001/doc.htm",
                "published_at": "2026-11-14T00:00:00+08:00",
                "fetched_at": "2026-11-15T22:00:00+08:00",
                "excerpt": "SEC official filing test excerpt.",
            }],
            "tech_tools": [],
            "calendar_events": [],
            "entity_updates": {},
        }
        try:
            with patch("pipeline.fetch_raw.run_all_first_party_connectors", return_value=mock_connectors):
                meta = fetch_raw_snapshot(tmp, respect_cadence=False, skip_deep_fetch=True, upstream_fail_test=True)
            self.assertEqual(meta["crawl_status"], "partial_degraded_aggregator")
            self.assertTrue((tmp / "data/connectors_latest.json").exists())
            self.assertGreaterEqual(meta["summary"]["healthy_connectors"], 1)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_ground_update_and_v3_artifacts_build(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            raw_dir = tmp / "archives/raw/2026-11-15/22-00"
            raw_dir.mkdir(parents=True)
            atomic_write_json(raw_dir / "meta.json", {"batch_id": "raw-20261115-220000", "fetched_at": "2026-11-15T22:00:00+08:00"})
            for fn in ("finance.json", "tech.json", "global.json", "general.json"):
                items = [{"title": f"测试存储芯片供应链动态 {fn}", "url": f"https://example.com/{fn}/1", "published_at": "2026-11-15T20:00:00+08:00"}]
                atomic_write_json(raw_dir / fn, [{"id": "cls-depth", "name": "财联社深度", "kind": "news", "items": items}])
            atomic_write_json(raw_dir / "connectors.json", {
                "schema_version": "3.0",
                "fetched_at": "2026-11-15T22:00:00+08:00",
                "connectors": [],
                "items": [{
                    "item_id": "sec-edgar_nvda1",
                    "source_id": "sec-edgar",
                    "source_name": "SEC EDGAR 官方披露",
                    "source_kind": "official_filing",
                    "source_tier": "first_party",
                    "citable_as_news": True,
                    "category": "finance",
                    "title": "[SEC 10-Q] 英伟达 (NVIDIA) 季报披露",
                    "url": "https://www.sec.gov/Archives/edgar/data/1045810/doc.htm",
                    "canonical_url": "https://www.sec.gov/Archives/edgar/data/1045810/doc.htm",
                    "published_at": "2026-11-15T18:00:00+08:00",
                    "fetched_at": "2026-11-15T22:00:00+08:00",
                    "excerpt": "NVIDIA 10-Q filing excerpt.",
                }],
                "tech_tools": [{
                    "tool_id": "tool_gh_test",
                    "name": "llama.cpp",
                    "repo": "ggml-org/llama.cpp",
                    "summary": "<details open><summary>Release</summary>Added Q4_K quantization support.</details>",
                    "availability_stage": "ga",
                }],
                "calendar_events": [],
                "entity_updates": {"ent_nvidia": {"latest_8k_date": "2026-11-14", "has_recent_502_officer_change": False}},
            })
            # Seed colliding V2 smart doc on tech category
            smart_dir = tmp / "archives/smart/2026-11-15/21-00"
            smart_dir.mkdir(parents=True)
            for c in ("finance", "tech", "global", "general"):
                ev_list = [
                    {
                        "event_id": "evt_a9d2aca38270",
                        "title": "黄仁勋辞任传闻",
                        "fact_summary": "【据关联报道/尚未见官方披露确认】【据关联报道/尚未见官方披露确认】报道称：报道称：市场传闻",
                        "sources": [{"item_id": "aihot_1", "source_id": "aihot", "source_name": "AI资讯", "title": "早报", "url": "https://aihot.today/1"}],
                    },
                    {"event_id": "evt_a9d2aca38270", "title": "Qwen4-Max 亮相", "fact_summary": "Qwen 新模型发布", "sources": [{"item_id": "aihot_1", "source_id": "aihot", "source_name": "AI资讯", "title": "早报", "url": "https://aihot.today/1"}]},
                ] if c == "tech" else [{"event_id": f"evt_{c}_1", "title": f"{c} 要闻", "fact_summary": "存储芯片需求强劲", "sources": [{"item_id": "cls_1", "source_id": "cls-depth", "source_name": "财联社深度", "title": "财联社要闻", "url": f"https://www.cls.cn/{c}/1"}]}]
                atomic_write_json(smart_dir / f"analysis_{c}.json", {"batch_id": "smart-20261115-210000", "events": ev_list})
            atomic_write_json(tmp / "data/manifest.json", {
                "raw": {"latest_path": "archives/raw/2026-11-15/22-00/", "latest_batch_id": "raw-20261115-220000"},
                "smart": {
                    "latest_path": "archives/smart/2026-11-15/21-00/",
                    "latest_batch_id": "smart-20261115-210000",
                    "categories": {c: {"path": f"archives/smart/2026-11-15/21-00/analysis_{c}.json"} for c in ("finance", "tech", "global", "general")},
                },
            })

            meta = build_briefing_batch(tmp, mode="ground_update")
            self.assertEqual(meta["status"], "complete")
            tech_doc = json.loads((tmp / "analysis_tech.json").read_text(encoding="utf-8"))
            ids = [e["event_id"] for e in tech_doc["events"]]
            self.assertEqual(len(ids), len(set(ids)), "Colliding legacy event_ids must be split cleanly!")
            rumor_ev = next(e for e in tech_doc["events"] if "黄仁勋" in e["title"])
            self.assertEqual(rumor_ev["fact_summary"].count("报道称："), 1)
            self.assertEqual(rumor_ev["fact_summary"].count("【据关联报道/尚未见官方披露确认】"), 1)
            tools_doc = json.loads((tmp / "data/tech_tools.json").read_text(encoding="utf-8"))
            llama_tool = next(t for t in tools_doc["tools"] if t["name"] == "llama.cpp")
            self.assertNotIn("<details", llama_tool["summary"])
            self.assertIn("Q4_K quantization", llama_tool["summary"])
            for fn in ("entities_index.json", "storylines_index.json", "calendar.json", "tech_tools.json", "radar.json", "predictions_public.json"):
                self.assertTrue((tmp / "data" / fn).exists(), f"Missing V3 artifact: {fn}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_v31_entity_tuples_negation_and_xbrl_latest(self):
        from pipeline.connectors.base import repair_mojibake
        from pipeline.connectors.github_releases import _clean_notes, _normalize_gh_license
        from pipeline.connectors.sec_edgar import _extract_quarterly_revenue
        from pipeline.entities import ENTITY_REGISTRY, match_entities_with_reasons

        for edef in ENTITY_REGISTRY:
            self.assertIsInstance(edef.validation_milestones, tuple, f"{edef.entity_id} validation_milestones must be tuple")
            self.assertGreater(len(edef.validation_milestones), 0)

        hits = match_entities_with_reasons("美团开源1.6万亿参数智能体模型LongCat-2.5，全程未使用Nvidia GPU训练")
        hit_ids = [h["entity_id"] for h in hits]
        self.assertIn("ent_meituan", hit_ids)
        self.assertEqual(hit_ids[0], "ent_meituan")
        self.assertNotIn("ent_nvidia", hit_ids)

        mock_facts = {
            "facts": {
                "us-gaap": {
                    "RevenueFromContractWithCustomerExcludingAssessedTax": {
                        "units": {"USD": [{"form": "10-K", "val": 26910000000, "end": "2022-01-30", "frame": "CY2021"}]}
                    },
                    "Revenues": {
                        "units": {"USD": [{"form": "10-Q", "val": 57000000000, "end": "2026-07-26", "frame": "CY2026Q2"}]}
                    },
                }
            }
        }
        actuals = _extract_quarterly_revenue(mock_facts)
        self.assertEqual(actuals[0]["period_end"], "2026-07-26")
        self.assertEqual(actuals[0]["value"], 57.0)

        self.assertEqual(repair_mojibake("11æ\x9c\x8816æ\x97¥"), "11月16日")
        self.assertFalse(_clean_notes("\n；ggml-cpu: add support").startswith("；"))
        self.assertIn("多许可证", _normalize_gh_license("NOASSERTION"))

    def test_v31_first_party_date_and_tool_calendar_filtering(self):
        from pipeline.connectors.macro_fomc import _parse_fomc_upcoming_dates
        from pipeline.time_utils import SHANGHAI_TZ
        from datetime import datetime

        # Verify past 2025 FOMC meetings are marked past & bounded, upcoming preserved first
        sample_html = """
        2025 FOMC Meetings January 28-29 March 18-19 2026 FOMC Meetings December 8-9
        """
        parsed = _parse_fomc_upcoming_dates(sample_html, reference_dt=datetime(2026, 11, 16, 12, 0, tzinfo=SHANGHAI_TZ))
        self.assertTrue(len(parsed) <= 3)
        self.assertEqual(parsed[0]["is_past"], False)
        self.assertEqual(parsed[0]["calendar_id"], "cal_fomc_2026-12-09")

    def test_fomc_strict_dom_parser_rejects_footnotes_and_2025(self):
        from pipeline.connectors.macro_fomc import _parse_fomc_upcoming_dates
        from pipeline.time_utils import SHANGHAI_TZ
        from datetime import datetime

        fed_html = """
        <div class="panel panel-default">
          <div class="panel-heading"><h4>2025 FOMC Meetings</h4></div>
          <div class="row fomc-meeting"><div class="fomc-meeting__month">March</div><div class="fomc-meeting__date">18-19*</div></div>
          <div class="row fomc-meeting"><div class="fomc-meeting__month">August</div><div class="fomc-meeting__date">22 (notation vote)</div></div>
        </div>
        <div class="panel panel-default">
          <div class="panel-heading"><h4>2026 FOMC Meetings</h4></div>
          <div class="row fomc-meeting"><div class="fomc-meeting__month">October</div><div class="fomc-meeting__date">27-28</div><div class="fomc-meeting__minutes">(Released October 7, 2026)</div></div>
          <div class="row fomc-meeting"><div class="fomc-meeting__month">December</div><div class="fomc-meeting__date">8-9*</div></div>
        </div>
        <div class="panel panel-default">
          <div class="panel-heading"><h4>2027 FOMC Meetings</h4></div>
          <div class="row fomc-meeting"><div class="fomc-meeting__month">January</div><div class="fomc-meeting__date">26-27</div></div>
          <div class="row fomc-meeting"><div class="fomc-meeting__month">November</div><div class="fomc-meeting__date">16-17</div></div>
          <p>Note: A two-day meeting is scheduled for January 25-26, 2028. Last Update: November 12, 2026</p>
        </div>
        """
        parsed = _parse_fomc_upcoming_dates(fed_html, reference_dt=datetime(2026, 11, 16, 12, 0, tzinfo=SHANGHAI_TZ))
        cids = [e["calendar_id"] for e in parsed]
        self.assertEqual(cids, ["cal_fomc_2026-12-09", "cal_fomc_2027-01-27", "cal_fomc_2027-11-17", "cal_fomc_2026-10-28"])
        self.assertNotIn("cal_fomc_2027-01-26", cids)
        self.assertNotIn("cal_fomc_2027-11-12", cids)
        self.assertNotIn("cal_fomc_2026-10-07", cids)

    def test_entity_conflict_blocks_cross_company_and_omnibus_attachment(self):
        from pipeline.dedup import entities_conflict, is_omnibus_digest_title
        from pipeline.build_briefing import _postprocess_and_prune_cross_category

        self.assertTrue(entities_conflict("[SEC 8-K] 英伟达 (NVIDIA) 提交监管文件", "[SEC 10-Q] AMD 提交监管文件"))
        self.assertTrue(entities_conflict("摩根士丹利下调英伟达目标价至267美元", "富国银行上调沃尔玛评级"))
        self.assertTrue(is_omnibus_digest_title("英伟达黄仁勋卸任、阿里芯片子公司赴港IPO、Qwen4-Max 首次亮相"))
        self.assertTrue(is_omnibus_digest_title("FreeBuf早报 | 台积电确认数据泄露；微软365宕机"))
        self.assertFalse(is_omnibus_digest_title("三星、SK海力士、美光撤诉动议遭美国法院驳回"))

        cat_docs = {
            "finance": {
                "events": [
                    {
                        "event_id": "evt_nvda_ceo",
                        "title": "报道称：英伟达CEO继任不确定性引发市场关注",
                        "fact_summary": "市场讨论英伟达管理层继任安排。",
                        "evidence_status": "multi_source",
                        "source_count": 3,
                        "platform_count": 3,
                        "sources": [
                            {"item_id": "s1", "source_id": "cls-depth", "source_name": "财联社", "title": "英伟达回应CEO继任传闻", "url": "https://cls.cn/1", "published_at": "2026-11-16T08:30:00+08:00"},
                            {"item_id": "s2", "source_id": "wallstreetcn", "source_name": "华尔街见闻", "title": "英伟达董事会评估继任计划", "url": "https://wallstreetcn.com/2", "published_at": "2026-11-16T09:10:00+08:00"},
                            {"item_id": "s3", "source_id": "fastbull", "source_name": "FastBull", "title": "某高管一周前旧闻致歉", "url": "https://fastbull.com/3", "published_at": "2026-11-10T09:30:00+08:00"},
                        ],
                    },
                    {
                        "event_id": "evt_hkex_junk",
                        "title": "[HKEX 03556 高騰比特幣] 基金說明書",
                        "fact_summary": "ETF brochure",
                        "evidence_status": "official_confirmed",
                        "source_count": 1,
                        "platform_count": 1,
                        "sources": [{"item_id": "h1", "source_id": "hkexnews", "source_name": "HKEX", "title": "[HKEX 03556 高騰比特幣] 基金說明書", "url": "https://hkexnews.hk/1", "source_tier": "first_party"}],
                    },
                ],
                "key_changes": [],
            },
            "tech": {
                "events": [
                    {
                        "event_id": "evt_omni",
                        "title": "报道称：英伟达黄仁勋卸任、阿里芯片子公司赴港IPO、Qwen4-Max 首次亮相",
                        "fact_summary": "拼盘早报",
                        "evidence_status": "multi_source",
                        "source_count": 1,
                        "platform_count": 1,
                        "sources": [{"item_id": "a1", "source_id": "aihot", "source_name": "AI", "title": "英伟达黄仁勋卸任、阿里芯片子公司赴港IPO、Qwen4-Max 首次亮相", "url": "https://aihot.today/1"}],
                    },
                    {
                        "event_id": "evt_qwen",
                        "title": "Qwen4-Max 模型性能实测公布",
                        "fact_summary": "单事件测试",
                        "evidence_status": "single_source",
                        "source_count": 1,
                        "platform_count": 1,
                        "sources": [{"item_id": "q1", "source_id": "ithome", "source_name": "IT之家", "title": "2.4万亿参数Qwen4-Max正", "url": "https://ithome.com/1", "published_at": "2026-11-16T09:00:00+08:00"}],
                    },
                ],
                "key_changes": [],
            },
        }
        cat_manifest = {"finance": {"item_count": 2}, "tech": {"item_count": 2}}
        _postprocess_and_prune_cross_category(cat_docs, cat_manifest)
        nvda_ev = cat_docs["finance"]["events"][0]
        self.assertEqual(nvda_ev["first_reported_at"], "2026-11-16T08:30:00+08:00")
        self.assertTrue(all("03556" not in e["title"] for e in cat_docs["finance"]["events"]))
        self.assertTrue(all("赴港IPO、Qwen" not in e["title"] for e in cat_docs["tech"]["events"]))

        # Verify distinct analyst/impact angles on the same company are NOT collapsed across categories
        from pipeline.build_briefing import _same_cross_category_story
        self.assertFalse(
            _same_cross_category_story(
                {"title": "摩根士丹利下调英伟达目标价至267美元", "fact_summary": "涉及继任不确定性与出货评估", "sources": []},
                {"title": "报道称：黄仁勋考虑重返英伟达CEO职位", "fact_summary": "硅谷盟友施压董事会", "sources": []},
            )
        )
        self.assertFalse(
            _same_cross_category_story(
                {"title": "郭明錤：英伟达换帅不确定性利好谷歌TPU长期订单", "fact_summary": "TPU供应链格局变化", "sources": []},
                {"title": "报道称：黄仁勋考虑重返英伟达CEO职位", "fact_summary": "硅谷盟友施压董事会", "sources": []},
            )
        )

    def test_v32_audit_fixes_model_sec_fomc_html_and_feeds(self):
        from datetime import datetime
        from xml.etree import ElementTree as ET
        from pipeline.build_briefing import PRIMARY_MODEL, FALLBACK_MODEL, _build_deterministic_dialectic_comments
        from pipeline.connectors.macro_fomc import _parse_fomc_upcoming_dates
        from pipeline.connectors.sec_edgar import _extract_quarterly_revenue
        from pipeline.fetch_raw import normalize_upstream_items
        from pipeline.time_utils import SHANGHAI_TZ
        from pipeline.v3_builder import build_v3_artifacts

        self.assertEqual(PRIMARY_MODEL, "gemini-4-hydrogen")
        self.assertEqual(FALLBACK_MODEL, "gemini-2.5-flash")

        # 1. SEC XBRL uniform currency check (no USD + TWD mixed in one table)
        mixed_facts = {
            "facts": {
                "us-gaap": {
                    "Revenues": {
                        "units": {
                            "USD": [
                                {"form": "20-F", "frame": "CY2024", "end": "2024-12-31", "filed": "2025-04-17", "val": 88_270_000_000},
                                {"form": "20-F", "frame": "CY2023", "end": "2023-12-31", "filed": "2024-04-18", "val": 69_300_000_000},
                            ],
                            "TWD": [
                                {"form": "20-F", "frame": "CY2024", "end": "2024-12-31", "filed": "2025-04-17", "val": 2_894_000_000_000},
                                {"form": "20-F", "frame": "CY2023", "end": "2023-12-31", "filed": "2024-04-18", "val": 2_161_740_000_000},
                            ],
                        }
                    }
                }
            }
        }
        actuals = _extract_quarterly_revenue(mixed_facts)
        self.assertGreaterEqual(len(actuals), 2)
        self.assertEqual({a["unit"] for a in actuals}, {"十亿美元"})

        # 2. Fetch normalization strips HTML tags, drops >72h stale items & charts/aggregator links
        from pipeline.sources import SOURCE_BY_ID
        source = SOURCE_BY_ID["jin10"]
        norm, _ = normalize_upstream_items(
            source,
            [
                {
                    "title": "美联储理事发表最新讲话",
                    "url": "https://www.cls.cn/detail/1001",
                    "pubDate": "2026-11-16T10:00:00+08:00",
                    "extra": {"hover": '<br/><span class="section-news">通胀仍在观察区间 &amp; 保持耐心</span>'},
                },
                {
                    "title": "11月3日旧闻不应混入实时流",
                    "url": "https://www.cls.cn/detail/old1",
                    "pubDate": "2026-11-03T10:00:00+08:00",
                },
                {
                    "title": "图表页空壳链接",
                    "url": "https://wallstreetcn.com/charts/999",
                    "pubDate": "2026-11-16T10:00:00+08:00",
                },
            ],
            "2026-11-16T12:00:00+08:00",
        )
        self.assertEqual(len(norm), 1)
        self.assertEqual(norm[0]["excerpt"], "通胀仍在观察区间 & 保持耐心")
        self.assertNotIn("<br", norm[0]["excerpt"])

        # 3. Domain-specific dialectic comments (no SEC boilerplate on tech outages)
        tech_cdoc = _build_deterministic_dialectic_comments(
            "tech",
            {
                "batch_id": "b1",
                "input_batch_id": "raw-1",
                "generated_at": "2026-11-16T12:00:00+08:00",
                "events": [
                    {
                        "event_id": "evt_msft_outage",
                        "title": "微软365与Azure云服务部分区域出现中断",
                        "fact_summary": "官方状态页显示路由故障已逐步恢复",
                        "evidence_status": "multi_source",
                        "evidence_label": "多独立来源提及",
                        "sources": [{"source_name": "IT之家", "url": "https://www.ithome.com/0/1.htm"}],
                    }
                ],
            },
            None,
            {},
        )
        tech_comments = tech_cdoc.get("comments", [])
        self.assertTrue(len(tech_comments) >= 1)
        self.assertFalse(any("SEC 10-Q" in (c.get("key_unknown") or "") for c in tech_comments))

        # 4. Build V3 artifacts: verify FOMC differentiation, domain next_catalyst & exported calendar.ics + feed.xml
        tmp_dir = Path(tempfile.mkdtemp(prefix="v32_feeds_"))
        try:
            cat_docs = {
                "tech": {
                    "events": [
                        {
                            "event_id": "evt_sec_bug",
                            "title": "Google披露Chrome零日安全漏洞并提供安全更新",
                            "category": "tech",
                            "entities": ["Google / DeepMind / Gemini"],
                            "entity_ids": ["ent_google"],
                            "importance": "high",
                            "evidence_status": "official_confirmed",
                            "evidence_label": "官方已证实",
                            "first_reported_at": "2026-11-16T09:00:00+08:00",
                            "latest_reported_at": "2026-11-16T10:00:00+08:00",
                            "fact_summary": "Google 发布安全公告修复漏洞。",
                            "sources": [{"source_name": "官方公告", "publisher": "Google", "url": "https://chromereleases.googleblog.com/1", "source_tier": "first_party"}],
                            "is_new_in_batch": True,
                        }
                    ]
                },
                "finance": {"events": []},
                "comprehensive": {"events": []},
                "social": {"events": []},
            }
            fed_html = """
            <div class="panel panel-default">
              <div class="panel-heading"><h4>2026 FOMC Meetings</h4></div>
              <div class="row fomc-meeting"><div class="fomc-meeting__month">December</div><div class="fomc-meeting__date">8-9*</div></div>
            </div>
            <div class="panel panel-default">
              <div class="panel-heading"><h4>2027 FOMC Meetings</h4></div>
              <div class="row fomc-meeting"><div class="fomc-meeting__month">January</div><div class="fomc-meeting__date">26-27</div></div>
            </div>
            """
            fomc_events = _parse_fomc_upcoming_dates(fed_html, reference_dt=datetime(2026, 11, 16, 12, 0, tzinfo=SHANGHAI_TZ))
            self.assertEqual(len(fomc_events), 2)
            self.assertNotEqual(fomc_events[0]["watch_variable"], fomc_events[1]["watch_variable"])

            summary = build_v3_artifacts(
                tmp_dir,
                batch_id="20261116_1200_v3",
                generated_at_iso="2026-11-16T12:00:00+08:00",
                cat_docs=cat_docs,
                prev_cat_events={},
                prev_batch_id=None,
                connectors_payload={"connectors": {}},
                calendar_extra=fomc_events,
            )
            storylines = json.loads((tmp_dir / "data/storylines_index.json").read_text(encoding="utf-8"))["storylines"]
            st_bug = next(iter(storylines.values()))
            self.assertNotIn("SEC 10-Q/8-K", st_bug["next_catalyst"])
            ics_text = (tmp_dir / "data/calendar.ics").read_text(encoding="utf-8")
            self.assertIn("BEGIN:VCALENDAR", ics_text)
            self.assertIn("BEGIN:VEVENT", ics_text)
            self.assertGreaterEqual(summary["calendar_ics_count"], 1)
            rss_text = (tmp_dir / "data/feed.xml").read_text(encoding="utf-8")
            root_xml = ET.fromstring(rss_text)
            self.assertEqual(root_xml.tag, "rss")
            self.assertTrue(len(root_xml.findall("./channel/item")) >= 1)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_v35_direct_rss_breaking_score_confirmed_summit_and_topics(self):
        from datetime import datetime
        from pipeline.connectors.direct_rss import parse_rss_or_atom_xml
        from pipeline.dedup import score_cluster_for_briefing
        from pipeline.entities import match_entities_with_reasons
        from pipeline.time_utils import SHANGHAI_TZ
        from pipeline.v3_builder import build_v3_artifacts

        # 1. Direct RSS XML parsing strips HTML & drops >72h stale items
        sample_rss = b"""<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0"><channel>
          <item>
            <title>Trump arrives in Shenzhen for APEC summit, greeted by Xi</title>
            <link>https://www.bbc.com/news/world-asia-9991</link>
            <pubDate>Wed, 18 Nov 2026 10:30:00 +0000</pubDate>
            <description><![CDATA[<p>Historic airport welcome &amp; trilateral talks.</p>]]></description>
          </item>
          <item>
            <title>Old news from last week</title>
            <link>https://www.bbc.com/news/world-asia-old1</link>
            <pubDate>Tue, 10 Nov 2026 10:00:00 +0000</pubDate>
          </item>
        </channel></rss>"""
        parsed_rss = parse_rss_or_atom_xml(
            sample_rss,
            feed_spec={"id": "rss-bbc-world", "name": "BBC News World", "category": "global", "family": "bbc"},
            fetched_iso="2026-11-19T12:00:00+08:00",
            now_dt=datetime(2026, 11, 19, 12, 0, tzinfo=SHANGHAI_TZ),
        )
        self.assertEqual(len(parsed_rss), 1)
        self.assertEqual(parsed_rss[0]["source_tier"], "direct_media")
        self.assertEqual(parsed_rss[0]["excerpt"], "Historic airport welcome & trilateral talks.")

        # 2. Geopolitical/APEC/Trump breaking items score high (never -10.0 dropped!)
        ents = match_entities_with_reasons("特朗普抵达深圳出席APEC峰会，习近平亲赴机场迎接")
        self.assertTrue(any(e["entity_id"] == "ent_us_china_diplomacy" for e in ents))
        sc, _ = score_cluster_for_briefing(
            {"title": "特朗普抵达深圳出席APEC峰会，习近平亲赴机场迎接", "source_id": "thepaper", "source_kind": "news"},
            watched_match_count=len(ents),
        )
        self.assertGreaterEqual(sc, 40.0)

        # 3. Verifier does NOT poison >=3 independent source confirmed state visits with "报道称："
        ref_lookup = {
            "R1": {"item_id": "i1", "source_id": "zaobao", "source_name": "联合早报", "publisher_family": "zaobao", "title": "习近平深圳机场迎接特朗普抵深出席亚太经合组织峰会，双方将讨论供应链与关税", "url": "https://zaobao.com/1", "published_at": "2026-11-18T18:30:00+08:00"},
            "R2": {"item_id": "i2", "source_id": "thepaper", "source_name": "澎湃新闻", "publisher_family": "thepaper", "title": "中美元首在亚太经合组织深圳峰会围绕供应链与关税举行双边会晤", "url": "https://thepaper.cn/2", "published_at": "2026-11-18T19:45:00+08:00"},
            "R3": {"item_id": "i3", "source_id": "rss-bbc-world", "source_name": "BBC News World", "publisher_family": "bbc", "title": "亚太经合组织深圳工商领导人会议聚焦供应链韧性与关税合作", "url": "https://bbc.com/3", "published_at": "2026-11-18T21:00:00+08:00"},
        }
        verified = verify_and_enrich_event(
            {
                "title": "特朗普抵深出席APEC峰会，习近平亲赴机场迎接",
                "fact_summary": "美国总统特朗普抵达深圳宝安机场，习近平亲赴机场迎接并出席欢迎晚宴。",
                "ai_analysis": "中美高层直接互动有助于管控经贸与科技分歧。",
                "unverified_claims": ["俄媒猜测美俄全面会谈概率偏低"],
                "source_refs": ["R1", "R2", "R3"],
            },
            category="global",
            input_batch_id="raw-test",
            fetched_at_iso="2026-11-19T12:00:00+08:00",
            ref_lookup=ref_lookup,
            id_lookup={},
            prev_events=[],
            prev_batch_id=None,
            require_semantic_match=False,
        )
        self.assertFalse(verified["title"].startswith("报道称："))
        self.assertIsNone(verified["attribution_warning"])

        # 4. Major topics spotlight + fixed non-drifting prediction due dates
        tmp_dir = Path(tempfile.mkdtemp(prefix="v35_topics_"))
        try:
            summary1 = build_v3_artifacts(
                tmp_dir,
                batch_id="b_v35_1",
                generated_at_iso="2026-11-19T12:00:00+08:00",
                cat_docs={"global": {"events": [verified]}, "finance": {"events": []}, "tech": {"events": []}, "general": {"events": []}},
                prev_cat_events={},
                prev_batch_id=None,
                connectors_payload={"connectors": {}},
                raw_items_by_cat={"global": list(ref_lookup.values())},
            )
            self.assertGreaterEqual(summary1["topics_count"], 1)
            topics_doc = json.loads((tmp_dir / "data/topics.json").read_text(encoding="utf-8"))
            self.assertEqual(topics_doc["topics"][0]["topic_id"], "topic_apec_trump_china")
            preds1 = json.loads((tmp_dir / "data/predictions_public.json").read_text(encoding="utf-8"))["predictions"]
            due_map_1 = {p["prediction_id"]: p["due_at"] for p in preds1}
            # Second run 2 days later must NOT roll existing due_at forward!
            build_v3_artifacts(
                tmp_dir,
                batch_id="b_v35_2",
                generated_at_iso="2026-11-21T12:00:00+08:00",
                cat_docs={"global": {"events": [verified]}, "finance": {"events": []}, "tech": {"events": []}, "general": {"events": []}},
                prev_cat_events={},
                prev_batch_id="b_v35_1",
                connectors_payload={"connectors": {}},
                raw_items_by_cat={"global": list(ref_lookup.values())},
            )
            preds2 = json.loads((tmp_dir / "data/predictions_public.json").read_text(encoding="utf-8"))["predictions"]
            for p in preds2:
                if p["prediction_id"] in due_map_1:
                    self.assertEqual(p["due_at"], due_map_1[p["prediction_id"]])
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_v5_phase_a_entity_stage_and_bilingual_guards(self):
        from pipeline.bilingual import enrich_bilingual_events
        from pipeline.entities import match_entities_with_reasons
        from pipeline.verifier import infer_material_stage

        # A6-1: '中俄美元首会晤' must NOT trigger Fed FOMC entity
        hits = match_entities_with_reasons("习近平将主持中俄美元首会晤")
        hit_ids = {h["entity_id"] for h in hits}
        self.assertIn("ent_us_china_diplomacy", hit_ids)
        self.assertNotIn("ent_macro_fomc", hit_ids)

        # True macro USD headline DOES match FOMC
        fed_hits = match_entities_with_reasons("美联储会议纪要偏鹰，美元指数跳升美债承压")
        self.assertIn("ent_macro_fomc", {h["entity_id"] for h in fed_hits})

        # A6-2: Politics/diplomacy and MAGA must NEVER get tech stage badges
        self.assertIsNone(infer_material_stage("马斯克公开表态：我并非 MAGA 阵营成员", category="tech"))
        self.assertIsNone(infer_material_stage("特朗普访问霍尔木兹海峡发表最新声明 beta preview", category="global"))
        self.assertIsNone(infer_material_stage("欧盟宣布正式启动与英国脱欧谈判", category="finance"))
        st = infer_material_stage("Google 正式发布大模型 Gemini 4 Neon，开放 API 调用", category="tech")
        self.assertIsNotNone(st)

        # A5: Placeholder string scrubbed back to original English <=120 char excerpt
        evs = [
            {
                "title": "CNBC Top Markets News",
                "title_en": "Fed minutes show policymakers divided on December hike path amid sticky services inflation",
                "fact_summary": "该条为海外主流媒体英文原报（云端 AI 批次将自动全文精译，您也可直接点击「原文」或切至 EN 模式阅读原版）。",
                "summary_en": "Federal Reserve minutes revealed sharp divisions among policymakers over whether to raise rates again in December as inflation remains elevated.",
                "sources": [{"source_name": "CNBC", "title": "Fed minutes"}],
            }
        ]
        enrich_bilingual_events(evs)
        self.assertNotIn("云端 AI 批次将自动", evs[0]["fact_summary"])
        self.assertTrue(evs[0]["fact_summary"].startswith("Federal Reserve minutes"))

    def test_phase_b4_simplified_zh_and_bullet_hygiene(self):
        from pipeline.v3_builder import _clean_bullet_items, _extract_sentences, normalize_simplified_zh

        self.assertEqual(normalize_simplified_zh("估值倍數與市場表現"), "估值倍数与市场表现")
        bullets = _extract_sentences('官员表示：“市场保持稳健。”\n”\n第二句：“估值倍數回升。”')
        self.assertEqual(bullets, ['官员表示：“市场保持稳健。”', '第二句：“估值倍数回升。”'])
        cleaned = _clean_bullet_items(["a", "”", "• ", "真实进展：估值倍數回升"])
        self.assertEqual(cleaned, ["真实进展：估值倍数回升"])

    def test_phase_c3_bilingual_retry_status_and_manual_overrides(self):
        import os
        from unittest import mock
        from pipeline.bilingual import enrich_bilingual_events, retry_pending_translations

        events = [
            {
                "title": "工信部公布算力基础设施发展新路线图",
                "fact_summary": "工信部强调加快大模型算力网络协同建设。",
            },
            {
                "title": "Unknown startup unveils novel photonic interconnect architecture",
                "fact_summary": "The startup claims lower latency for optical cluster fabrics.",
            },
            {
                "title": "Manual override benchmark test headline for verification",
                "fact_summary": "Manual summary body text in English.",
            },
        ]
        overrides = {
            "Manual override benchmark test headline for verification": {
                "title_zh": "人工兜底译文：验证基准标题已生效",
                "summary_zh": "人工兜底摘要：中文精确译文。",
            }
        }
        with mock.patch.dict(os.environ, {}, clear=True):
            enrich_bilingual_events(events, overrides=overrides, max_retries=1, backoff_base=0.0)

        self.assertEqual(events[0]["translation_status"], "native_zh")
        self.assertEqual(events[1]["translation_status"], "retry_fallback")
        self.assertGreaterEqual(events[1]["translation_attempts"], 1)
        self.assertTrue(events[1]["translation_error"])
        self.assertEqual(events[2]["translation_status"], "manual")
        self.assertEqual(events[2]["title"], "人工兜底译文：验证基准标题已生效")
        self.assertEqual(events[2]["fact_summary"], "人工兜底摘要：中文精确译文。")

        # Retry pending fallback with simulated transient failure -> success on 2nd attempt
        calls = {"n": 0}

        def _flaky_translate(texts, target_lang="zh", *, max_retries=2, backoff_base=0.0, chunk_size=12):
            calls["n"] += 1
            return [f"重试译文：{t[:16]}" for t in texts], 2, None

        with mock.patch("pipeline.bilingual._translate_texts_with_pipeline", side_effect=_flaky_translate):
            resolved = retry_pending_translations(events, overrides={}, max_retries=2, backoff_base=0.0)
        self.assertEqual(resolved, 1)
        self.assertEqual(calls["n"], 2)  # title batch + summary batch
        self.assertEqual(events[1]["translation_status"], "translated")
        self.assertIsNone(events[1]["translation_error"])
        self.assertTrue(events[1]["title"].startswith("重试译文："))

    def test_phase_c4_entity_and_stage_confidence_thresholds(self):
        from pipeline.entities import ENTITY_CONFIDENCE_THRESHOLD, match_entities_with_reasons
        from pipeline.verifier import STAGE_CONFIDENCE_THRESHOLD, infer_material_stage

        # Strong headline match passes threshold
        strong = match_entities_with_reasons("NVIDIA 正式发布新一代 GPU 架构，性能大幅提升")
        self.assertTrue(any(h["entity_id"] == "ent_nvidia" and h["confidence"] >= ENTITY_CONFIDENCE_THRESHOLD for h in strong))

        # Fleeting deep-tail short ASCII non-canonical alias filtered below 0.65
        noisy_tail = "今日宏观市场情绪平稳波动，债券收益率与大宗商品整体横盘震荡，多地监管机构维持现有政策框架不变，" + "研究报告指出行业仍需关注长期现金流与资本开支节奏变化，" * 2 + "附注仅顺带提及端侧 ios。"
        suppressed = match_entities_with_reasons(noisy_tail, min_confidence=ENTITY_CONFIDENCE_THRESHOLD)
        unfiltered = match_entities_with_reasons(noisy_tail, min_confidence=0.0)
        self.assertTrue(any(h["entity_id"] == "ent_apple" for h in unfiltered))
        self.assertFalse(any(h["entity_id"] == "ent_apple" for h in suppressed))

        # Stage confidence: clean product GA passes >= 0.70, mixed speculative political noise suppressed
        good_stage = infer_material_stage("Google 正式发布大模型 Gemini 4 Neon，开放 API 调用", category="tech")
        self.assertIsNotNone(good_stage)
        self.assertGreaterEqual(good_stage["confidence"], STAGE_CONFIDENCE_THRESHOLD)

        noisy_stage = infer_material_stage("特朗普在外交演讲中表示可能测试新型芯片出口政策模型 beta", category="tech")
        self.assertIsNone(noisy_stage)

    def test_realtime_ai_radar_extraction_first_hand_and_timestamps(self):
        from pipeline.connectors.china_realtime import _classify_wire_item
        from pipeline.ai_live_refresh import extract_ai_release_item, merge_live_ai_items_into_doc

        # WorkBuddy computer-use update must classify as tech & route to tencent_hunyuan with full timestamp
        self.assertEqual(_classify_wire_item("腾讯WorkBuddy上线电脑操控能力", "", "global"), "tech")
        wb_item = extract_ai_release_item(
            {
                "item_id": "wscn_wb_1",
                "source_id": "wscn-global-channel",
                "source_name": "华尔街见闻 7×24 全球",
                "title": "腾讯WorkBuddy上线电脑操控能力",
                "url": "https://wallstreetcn.com/livenews/999001",
                "published_at": "2026-11-20T18:54:00+08:00",
                "excerpt": "腾讯WorkBuddy正式上线电脑操控能力，可执行多步桌面操作。",
            },
            "2026-11-20T19:00:00+08:00",
        )
        self.assertIsNotNone(wb_item)
        self.assertEqual(wb_item["company_id"], "tencent_hunyuan")
        self.assertEqual(wb_item["date"], "2026-11-20T18:54:00+08:00")
        self.assertFalse(wb_item["is_first_hand"])

        # DeepSeek mega funding round must also enter DeepSeek lane
        ds_item = extract_ai_release_item(
            {
                "item_id": "cls_ds_1",
                "source_id": "cls-live",
                "source_name": "财联社 7×24 电报",
                "title": "DeepSeek 新一轮千亿级融资落地",
                "url": "https://www.cls.cn/detail/100200",
                "published_at": "2026-11-20T18:40:00+08:00",
            },
            "2026-11-20T19:00:00+08:00",
        )
        self.assertIsNotNone(ds_item)
        self.assertEqual(ds_item["company_id"], "deepseek")
        self.assertEqual(ds_item["category"], "资本与商业")

        # First-hand Hugging Face org drop tagged as is_first_hand=True
        hf_item = extract_ai_release_item(
            {
                "item_id": "hf_tx_1",
                "source_id": "huggingface-hub",
                "source_name": "Hugging Face 官方模型库",
                "title": "[HF] tencent/Hunyuan-ComputerUse-Preview 正式公开模型权重",
                "url": "https://huggingface.co/tencent/Hunyuan-ComputerUse-Preview",
                "published_at": "2026-11-20T18:58:00+08:00",
            },
            "2026-11-20T19:00:00+08:00",
        )
        self.assertIsNotNone(hf_item)
        self.assertEqual(hf_item["company_id"], "tencent_hunyuan")
        self.assertTrue(hf_item["is_first_hand"])
        self.assertEqual(hf_item["source_tier"], "first_party")

        # Pure corporate share buybacks rejected
        self.assertIsNone(
            extract_ai_release_item(
                {
                    "item_id": "spam_1",
                    "source_id": "cls-live",
                    "source_name": "财联社",
                    "title": "腾讯控股拟以50亿元回购股份并注销股本",
                    "url": "https://www.cls.cn/detail/100300",
                    "published_at": "2026-11-20T18:50:00+08:00",
                },
                "2026-11-20T19:00:00+08:00",
            )
        )

        # Merging dedups duplicate wire headlines and sorts newest full ISO timestamp first
        doc, new_ids = merge_live_ai_items_into_doc(
            None,
            [
                {
                    "item_id": "old_1",
                    "source_id": "ithome",
                    "source_name": "IT之家",
                    "title": "腾讯 Hy4 正式开源",
                    "url": "https://www.ithome.com/1/029/841.htm",
                    "published_at": "2026-11-19",
                },
                {
                    "item_id": "old_1_precise",
                    "source_id": "ithome",
                    "source_name": "IT之家",
                    "title": "腾讯 Hy4 正式开源",
                    "url": "https://www.ithome.com/1/029/841.htm",
                    "published_at": "2026-11-19T08:00:00+08:00",
                },
                {
                    "item_id": "wscn_wb_1",
                    "source_id": "wscn-global-channel",
                    "source_name": "华尔街见闻 7×24 全球",
                    "title": "腾讯WorkBuddy上线电脑操控能力",
                    "url": "https://wallstreetcn.com/livenews/999001",
                    "published_at": "2026-11-20T18:54:00+08:00",
                },
                {
                    "item_id": "cls_wb_dup",
                    "source_id": "cls-live",
                    "source_name": "财联社",
                    "title": "腾讯WorkBuddy上线电脑操控能力",
                    "url": "https://www.cls.cn/detail/999002",
                    "published_at": "2026-11-20T18:55:00+08:00",
                },
            ],
            "2026-11-20T19:00:00+08:00",
        )
        tx = next(c for c in doc["companies"] if c["company_id"] == "tencent_hunyuan")
        self.assertEqual(len(tx["items"]), 2)
        self.assertEqual(tx["items"][0]["title"], "腾讯WorkBuddy上线电脑操控能力")
        self.assertEqual(tx["items"][0]["date"], "2026-11-20T18:54:00+08:00")
        self.assertEqual(tx["items"][1]["date"], "2026-11-19T08:00:00+08:00")
        self.assertGreaterEqual(len(new_ids), 2)

    def test_p0_finance_impact_consistency_and_domain_specificity(self) -> None:
        from pipeline.finance_impact_builder import _validate_impact_consistency, build_finance_impact_artifact

        # Explicit consistency gate rejects bearish event with all-positive bars
        ok_bad, reason_bad = _validate_impact_consistency(
            "英伟达单日暴跌14%，市值大幅缩水",
            "市场恐慌抛售芯片股",
            {
                "polarity": "bearish",
                "bars": [
                    {"market": "A股", "sector": "CPO", "pct_low": 1.2, "pct_high": 4.0},
                    {"market": "美股", "sector": "NVDA", "pct_low": 2.0, "pct_high": 5.5},
                ],
            },
        )
        self.assertFalse(ok_bad)
        self.assertIn("冲突", reason_bad)

        events = [
            {
                "event_id": "fi_nvda_crash",
                "title": "英伟达单日暴跌14%，创近期最大跌幅",
                "fact_summary": "受估值回调与出口收紧影响，英伟达单日重挫 14%。",
                "sentiment": "bearish",
                "category": "finance",
                "entities": ["英伟达 (NVIDIA)"],
            },
            {
                "event_id": "fi_ant_slide",
                "title": "Anthropic 上市次日下挫 8.5%，逼近破发",
                "fact_summary": "IPO 首日大涨后次日回调 8.5%。",
                "sentiment": "bearish",
                "category": "finance",
                "entities": ["Anthropic"],
            },
            {
                "event_id": "fi_privacy",
                "title": "头部 AI 平台爆发大规模用户隐私数据泄露事件",
                "fact_summary": "多国隐私监管机构启动合规问询。",
                "sentiment": "bearish",
                "category": "tech",
                "entities": ["OpenAI"],
            },
            {
                "event_id": "fi_peace",
                "title": "俄乌和平协议取得重大突破，双方接近停火",
                "fact_summary": "市场计价欧洲能源风险溢价回落。",
                "category": "global",
                "entities": ["原油 (Crude Oil / Brent / WTI)"],
            },
            {
                "event_id": "fi_missile",
                "title": "导弹落入波兰边境引发欧洲地缘紧张升级",
                "fact_summary": "北约紧急磋商，避险买盘与能源担忧升温。",
                "category": "global",
                "entities": ["原油 (Crude Oil / Brent / WTI)"],
            },
        ]
        doc = build_finance_impact_artifact(all_events=events, batch_id="b_p0_test", generated_at_iso="2026-11-20T18:00:00+08:00")
        by_id = doc["event_impact_map"]

        nvda_imp = by_id["fi_nvda_crash"]
        self.assertEqual(nvda_imp["polarity"], "bearish")
        us_bars = [b for b in nvda_imp["bars"] if b.get("market") == "美股"]
        hk_bars = [b for b in nvda_imp["bars"] if b.get("market") == "港股"]
        self.assertTrue(us_bars and all(b["pct_high"] <= 0 for b in us_bars))
        self.assertTrue(len(hk_bars) >= 1)
        nvda_card = next(c for c in doc["event_impacts"] if c["event_id"] == "fi_nvda_crash")
        self.assertLess(nvda_card.get("affected_tickers", {}).get("NVDA", 0), 0)
        self.assertTrue(nvda_imp.get("sample_basis"))

        ant_imp = by_id["fi_ant_slide"]
        self.assertNotEqual(ant_imp["polarity"], "bullish")

        priv_imp = by_id["fi_privacy"]
        self.assertNotIn("推理成本下降", priv_imp.get("one_liner", ""))

        peace_imp = by_id["fi_peace"]
        missile_imp = by_id["fi_missile"]
        peace_oil = next((b for b in peace_imp["bars"] if "油" in b["sector"] or "Oil" in b["sector"]), None)
        missile_oil = next((b for b in missile_imp["bars"] if "油" in b["sector"] or "Oil" in b["sector"]), None)
        self.assertIsNotNone(peace_oil)
        self.assertIsNotNone(missile_oil)
        self.assertLess(peace_oil["pct_high"], 0)
        self.assertGreater(missile_oil["pct_low"], 0)

    def test_p1_hygiene_dedup_aliases_classification_sec_and_bilingual(self) -> None:
        from pipeline.ai_radar_builder import _infer_company
        from pipeline.bilingual import enrich_bilingual_events
        from pipeline.connectors.china_realtime import _clean as _wire_clean, _classify_wire_item as _wire_classify
        from pipeline.connectors.sec_edgar import _format_sec_filing_description
        from pipeline.entities import match_entities_with_reasons
        from pipeline.v3_builder import _infer_domain_next_catalyst
        from pipeline.verifier import verify_and_enrich_event

        # False positive entity guard: 1万亿美元 / 高盛
        ents_sb = [m["canonical_name"] for m in match_entities_with_reasons("软银计划向SK海力士融资1万亿美元", [])]
        self.assertNotIn("美联储 (Fed / FOMC)", ents_sb)
        ents_gs = [m["canonical_name"] for m in match_entities_with_reasons("高盛上调亚洲半导体评级", [])]
        self.assertNotIn("黄金 (Gold / 避险金属)", ents_gs)

        # Entity alias dedup + internal pipeline jargon scrub
        ref = {
            "item_id": "raw_nv_1",
            "title": "NVIDIA Q3 revenue hits record high",
            "url": "https://reuters.com/tech/nvda-q3-2026",
            "source_id": "reuters-top",
            "source_name": "Reuters",
            "published_at": "2026-11-20T12:00:00+08:00",
            "excerpt": "Data center demand drove strong quarterly performance.",
        }
        ev = verify_and_enrich_event(
            {
                "title": "英伟达季度营收创纪录新高",
                "fact_summary": "[R075] 原始素材仅含标题。已拦截 4 条无效引用（行情页）；英伟达数据中心需求强劲。",
                "entities": ["英伟达", "英伟达 (NVIDIA)"],
                "source_refs": ["raw_nv_1"],
            },
            category="tech",
            input_batch_id="b_hyg",
            fetched_at_iso="2026-11-20T18:00:00+08:00",
            ref_lookup={"raw_nv_1": ref},
            id_lookup={"raw_nv_1": ref},
            prev_events=[],
            prev_batch_id=None,
        )
        self.assertEqual(ev["entities"].count("英伟达 (NVIDIA)"), 1)
        self.assertNotIn("英伟达", [e for e in ev["entities"] if e == "英伟达"])
        self.assertNotIn("R075", ev["fact_summary"])
        self.assertNotIn("已拦截", ev["fact_summary"])
        self.assertNotIn("原始素材仅含标题", ev["fact_summary"])

        # Copilot belongs to Microsoft, not indie_opensource; Iran drone -> global; Hormuz tanker -> geopolitical; SEC 6-K -> readable label
        self.assertEqual(_infer_company("微软 Win11 Copilot 新增本地任务接管")[0], "microsoft")
        self.assertEqual(_wire_classify("伊朗击落一架美军侦察无人机", "霍尔木兹海峡防空拦截动态", "finance"), "global")
        self.assertIn("航运", _infer_domain_next_catalyst({"title": "霍尔木兹油轮触雷引发航道警戒"}, None))
        self.assertIn("月度营收", _format_sec_filing_description("6-K", "", [], "tsm-revenue-202610.htm"))
        self.assertIn("重大", _format_sec_filing_description("8-K", "", ["2.02"], "q3-8k.htm"))
        trunc = _wire_clean("长江证券截至2026年11月20日已累计通过集中竞价交易方式回购公司股份948万股成交总额超过亿元大关后续仍将继续推进计划", 36)
        self.assertTrue(trunc.endswith(("。", "！", "？", "…")))

        # Bilingual native_zh enrichment populates title_en & summary_en without changing translation_status
        zh_ev = {
            "event_id": "zh_bi_1",
            "title": "英伟达宣布新一代AI芯片量产计划",
            "fact_summary": "英伟达宣布下一代数据中心芯片进入量产阶段。",
            "entities": ["英伟达 (NVIDIA)"],
            "sources": [],
        }
        enrich_bilingual_events([zh_ev])
        self.assertEqual(zh_ev["translation_status"], "native_zh")
        self.assertEqual(zh_ev.get("title_en"), "")
        self.assertEqual(zh_ev.get("summary_en"), "")

    def test_re_audit_regressions_fixed(self) -> None:
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from pipeline.ai_live_refresh import merge_live_ai_items_into_doc
        from pipeline.ai_radar_builder import _infer_what_it_does_zh
        from pipeline.build_briefing import _postprocess_and_prune_cross_category, _smart_truncate
        from pipeline.connectors.china_realtime import _classify_wire_item as _wire_classify, refresh_live_wire_file
        from pipeline.finance_impact_builder import build_finance_impact_artifact
        from pipeline.live_reconcile import refresh_and_sanitize_site_data
        from pipeline.manifest import atomic_write_json
        from pipeline.v3_builder import build_v3_artifacts

        # 1. Decimal dot never breaks sentence truncation + dangling parens stripped
        dec = _smart_truncate("美联储本周累跌19.2%引发美股成长板块回调并冲击港股流动性配置。", 18)
        self.assertIn("19.2%", dec)
        self.assertFalse(dec.endswith("19."))
        self.assertTrue(dec.endswith("…"))
        paren = _smart_truncate("美联储（周跌19.2%引发成长板块回调并冲击市场配置预期", 10)
        self.assertNotIn("（周跌", paren)

        # 2. Anthropic SDK must map to Agent/SDK, NOT Multimodal
        sdk_what = _infer_what_it_does_zh("Anthropic 发布 Claude Agent SDK 工具套件", "Includes clear workflow harness for enterprise coders.")
        self.assertIn("Agent", sdk_what)
        self.assertNotIn("多模态生成", sdk_what)

        # 3. OpenAI anti-distillation duplicates collapse into 1
        merged_ai, _ = merge_live_ai_items_into_doc(
            None,
            [
                {"id": "lw1", "title": "OpenAI 指控竞争对手大规模反蒸馏", "source_name": "Reuters", "url": "https://r.com/1", "published_at": "2026-11-21T10:00:00+08:00"},
                {"id": "lw2", "title": "OpenAI 称多款开源模型正通过反蒸馏抽取其推理能力", "source_name": "FT", "url": "https://ft.com/2", "published_at": "2026-11-21T09:00:00+08:00"},
                {"id": "lw3", "title": "外媒：OpenAI 加强 API 权重安全反蒸馏防御机制", "source_name": "36Kr", "url": "https://36kr.com/3", "published_at": "2026-11-21T08:00:00+08:00"},
            ],
            "2026-11-21T12:00:00+08:00",
        )
        openai_items = next(c["items"] for c in merged_ai["companies"] if c["company_id"] == "openai")
        anti_distill_cnt = sum(1 for it in openai_items if "蒸馏" in it["title"])
        self.assertEqual(anti_distill_cnt, 1)

        # 4. Domestic ministry / crypto classification out of global + wire dedup (SoftBank/Hynix)
        self.assertNotEqual(_wire_classify("商务部回应外贸通关便利化举措", "继续支持跨境电商", "global"), "global")
        self.assertEqual(_wire_classify("比特币短线反弹突破关键压力位", "加密货币市场交易量放大", "global"), "finance")
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with patch("pipeline.connectors.china_realtime.fetch_china_realtime_wires", return_value={
                "fetched_at": "2026-11-21T12:00:00+08:00",
                "status": "ok",
                "connector_name": "test",
                "items": [
                    {"id": "w1", "title": "孙正义会见SK海力士高管商讨1万亿美元芯片合作", "category": "tech", "published_at": "2026-11-21T11:00:00+08:00"},
                    {"id": "w2", "title": "快讯：软银孙正义与SK海力士探讨万亿规模AI芯片联盟", "category": "tech", "published_at": "2026-11-21T10:50:00+08:00"},
                    {"id": "w3", "title": "SK海力士回应与孙正义推进半导体投资磋商", "category": "tech", "published_at": "2026-11-21T10:40:00+08:00"},
                ],
            }):
                wire_doc = refresh_live_wire_file(root)
            self.assertEqual(len(wire_doc["items"]), 1)

            # 5. Cross/intra-category dedup + domestic/crypto reclassification
            cat_docs = {
                "finance": {
                    "events": [
                        {"event_id": "e_t1", "category": "finance", "title": "特朗普白宫发布会称拟对海外数据中心征重税", "fact_summary": "白宫提及数据中心税收", "evidence_status": "multi_source", "source_count": 2, "sources": [{"url": "https://a.com/1"}]},
                        {"event_id": "e_btc", "category": "global", "title": "比特币重挫跌破重要关口", "fact_summary": "加密货币承压", "evidence_status": "single_source", "source_count": 1, "sources": [{"url": "https://a.com/2"}]},
                        {"event_id": "e_f2", "category": "finance", "title": "A股银行板块高股息估值修复", "fact_summary": "分红提升", "evidence_status": "single_source", "source_count": 1, "sources": [{"url": "https://a.com/3"}]},
                        {"event_id": "e_f3", "category": "finance", "title": "宁德时代宣布欧洲电池工厂扩产", "fact_summary": "产能扩大", "evidence_status": "single_source", "source_count": 1, "sources": [{"url": "https://a.com/4"}]},
                    ]
                },
                "global": {
                    "events": [
                        {"event_id": "e_t2", "category": "global", "title": "特朗普白宫发布会回应中东局势与数据中心征重税议题", "fact_summary": "同发布会不同切面", "evidence_status": "single_source", "source_count": 1, "sources": [{"url": "https://a.com/5"}]},
                        {"event_id": "e_mof", "category": "global", "title": "商务部发布稳外贸稳外资新一批政策", "fact_summary": "促进国内企业出海", "evidence_status": "single_source", "source_count": 1, "sources": [{"url": "https://a.com/6"}]},
                        {"event_id": "e_rmrb", "category": "global", "title": "人民日报评论员文章强调高质量科技创新", "fact_summary": "国内政策评论", "evidence_status": "single_source", "source_count": 1, "sources": [{"url": "https://a.com/7"}]},
                        {"event_id": "e_g4", "category": "global", "title": "欧央行官员重申对通胀粘性保持警惕", "fact_summary": "欧洲货币政策动态", "evidence_status": "single_source", "source_count": 1, "sources": [{"url": "https://a.com/8"}]},
                    ]
                },
                "tech": {
                    "events": [
                        {"event_id": "e_sig", "category": "tech", "title": "Signal 在 iOS 27 与 Android 端屏蔽截屏（Google Gemini Intelligence）", "fact_summary": "隐私功能更新", "evidence_status": "single_source", "source_count": 1, "sources": [{"url": "https://a.com/9"}]},
                    ]
                },
                "general": {"events": []},
            }
            cat_manifest = {c: {} for c in cat_docs}
            _postprocess_and_prune_cross_category(cat_docs, cat_manifest)
            all_titles = [e["title"] for d in cat_docs.values() for e in d["events"]]
            trump_cnt = sum(1 for t in all_titles if "特朗普白宫发布会" in t)
            self.assertEqual(trump_cnt, 1)
            global_titles = [e["title"] for e in cat_docs["global"]["events"]]
            self.assertFalse(any("比特币" in t or "商务部" in t or "人民日报" in t for t in global_titles))

            # 6. Finance impact: distinct bars across Hormuz mine vs missile vs US-Iran talks + IPO split
            imp_doc = build_finance_impact_artifact(
                all_events=[
                    {"event_id": "fi1", "title": "油轮在霍尔木兹海峡触雷引发航道警戒", "fact_summary": "航运安全升级", "category": "global", "importance": "high", "sources": [{"source_name": "R", "url": "https://r/1"}]},
                    {"event_id": "fi2", "title": "导弹落入波兰边境", "fact_summary": "防空警报拉响", "category": "global", "importance": "high", "sources": [{"source_name": "R", "url": "https://r/2"}]},
                    {"event_id": "fi3", "title": "美伊日内瓦谈判陷入僵局", "fact_summary": "双方立场仍存分歧", "category": "global", "importance": "high", "sources": [{"source_name": "R", "url": "https://r/3"}]},
                    {"event_id": "fi4", "title": "Anthropic 上市次日下挫 8.5%，逼近破发", "fact_summary": "大模型估值承压", "category": "finance", "importance": "high", "sources": [{"source_name": "R", "url": "https://r/4"}]},
                ],
                batch_id="b_imp",
                generated_at_iso="2026-11-21T12:00:00+08:00",
                quotes_doc={"quotes": {}, "indices": []},
            )
            by_eid = imp_doc["event_impact_map"]
            self.assertNotEqual(by_eid["fi1"]["bars"][0]["pct_high"], by_eid["fi3"]["bars"][0]["pct_high"])
            self.assertEqual(imp_doc["event_impacts"][-1]["rule_id"] if "fi4" == imp_doc["event_impacts"][-1]["event_id"] else next(c["rule_id"] for c in imp_doc["event_impacts"] if c["event_id"] == "fi4"), "ai_ipo_pullback")

            # 7. V3: ent_intel vs Signal, SMIC count=0, Predictions NVDA canonical + Qwen 12-16, RSS URL, TSMC 2026 persistence
            atomic_write_json(root / "data" / "sec_companyfacts_cache.json", {
                "ent_tsmc": {"actuals": [{"period_end": "2026-10-31", "metric": "Monthly Revenue", "value": "NT$ 314B"}], "filings": [{"form": "6-K", "filing_date": "2026-11-10", "description": "月度营收公告"}]},
                "ent_smic": {"filings": [{"form": "HKEX", "filing_date": "2026-11-15", "description": "月度公告"}, {"form": "HKEX", "filing_date": "2026-11-08", "description": "业绩"}]},
            })
            v3_summary = build_v3_artifacts(
                root,
                batch_id="b_v3",
                generated_at_iso="2026-11-21T12:00:00+08:00",
                cat_docs=cat_docs,
                prev_cat_events={c: [] for c in cat_docs},
                prev_batch_id=None,
                connectors_payload={
                    "entity_updates": {"ent_smic": {"hkex_filings": [{"form": "HKEX", "filing_date": "2026-11-15", "title": "业绩公告"}, {"form": "HKEX", "filing_date": "2026-11-08", "title": "股东通函"}]}},
                },
            )
            self.assertTrue(v3_summary["entities_count"] > 0)
            ent_doc = json.loads((root / "data" / "entities_index.json").read_text(encoding="utf-8"))
            ent_by_id = {e["entity_id"]: e for e in ent_doc["entities"]}
            self.assertEqual(len(ent_by_id["ent_intel"]["recent_events"]), 0)
            self.assertEqual(ent_by_id["ent_smic"]["change_count_30d"], 0)
            pred_doc = json.loads((root / "data" / "predictions_public.json").read_text(encoding="utf-8"))
            by_pid = {p["prediction_id"]: p for p in pred_doc["predictions"]}
            self.assertEqual(by_pid["pred_seed_nvda_sec_502"]["target_entity"], "英伟达 (NVIDIA)")
            self.assertTrue(str(by_pid["pred_seed_qwen_release_ga"]["due_at"]).startswith("2026-12-16"))
            feed_xml = (root / "feed.xml").read_text(encoding="utf-8")
            self.assertNotIn("soulmove.github.io", feed_xml)
            self.assertIn("111.230.153.15", feed_xml)

            # Fast reconcile with refresh_sec=False must preserve TSMC 2026-10 actuals even when keyed by 10-digit CIK ("0001046179")
            for c, d in cat_docs.items():
                atomic_write_json(root / f"analysis_{c}.json", d)
            atomic_write_json(root / "data" / "manifest.json", {"smart": {"latest_batch_id": "b_v3", "generated_at": "2026-11-21T12:00:00+08:00", "categories": {}}})
            atomic_write_json(root / "data" / "connectors_latest.json", {"entity_updates": {"ent_tsmc": {"financial_actuals": [{"period_end": "2024-12-31", "value": "$90B"}]}}})
            atomic_write_json(root / "data" / "sec_companyfacts_cache.json", {
                "0001046179": {"actuals": [{"period_end": "2026-10-31", "metric": "Monthly Revenue", "value": "NT$ 314B"}], "filings": [{"form": "6-K", "filing_date": "2026-11-10", "description": "月度营收公告"}]},
            })
            refresh_and_sanitize_site_data(root, refresh_sec=False)
            ent_after = {e["entity_id"]: e for e in json.loads((root / "data" / "entities_index.json").read_text(encoding="utf-8"))["entities"]}
            self.assertEqual(ent_after["ent_tsmc"]["financial_actuals"][0]["period_end"], "2026-10-31")

            # Round-3 checks:
            # a) AI privacy leak must NOT match 'mini' -> '轻量'; EN+ZH OpenAI distillation merges cleanly
            priv_what = _infer_what_it_does_zh("近 200 万条诱饵请求测试揭示 AI 隐私泄露（Gemini mini）", "Privacy exposure findings")
            self.assertIn("隐私合规", priv_what)
            self.assertNotIn("轻量", priv_what)
            ai_biling_merge, _ = merge_live_ai_items_into_doc(
                None,
                [
                    {"id": "o_zh", "title": "OpenAI 公布 GPT-6.2 反蒸馏防护进展", "source_name": "IT之家", "url": "https://ithome.com/1", "published_at": "2026-11-21T10:00:00+08:00"},
                    {"id": "o_en", "title": "Combatting adversarial distillation", "source_name": "OpenAI 官方动态", "source_id": "rss-openai-news", "url": "https://openai.com/index/distill", "published_at": "2026-11-21T09:00:00+08:00"},
                ],
                "2026-11-21T12:00:00+08:00",
            )
            oa_items = next(c["items"] for c in ai_biling_merge["companies"] if c["company_id"] == "openai")
            self.assertEqual(len([x for x in oa_items if "蒸馏" in x["title"] or "distill" in x["title"].lower()]), 1)

            # b) Finance Impact: OpenAI GPT-6.2 反蒸馏 must NOT emit Oracle cashflow copy
            anti_imp = build_finance_impact_artifact(
                all_events=[{"event_id": "fi_oai", "title": "OpenAI 公布 GPT-6.2 反蒸馏防护进展", "fact_summary": "思考链提取成功率大幅下降。", "category": "finance", "importance": "high", "sources": [{"source_name": "IT之家", "url": "https://ithome.com/oai"}]}],
                batch_id="b_r3",
                generated_at_iso="2026-11-21T12:00:00+08:00",
                quotes_doc={"quotes": {}, "indices": []},
            )
            self.assertNotIn("甲骨文", json.dumps(anti_imp, ensure_ascii=False))
            self.assertNotIn("自由现金流", json.dumps(anti_imp, ensure_ascii=False))

            # c) Wire re-classification pushes Steam Black Friday & crime news into general (never tech)
            self.assertEqual(_wire_classify("男子专盯老年住户安装虚拟拨号设备，涉帮信罪被刑拘", "警方破获电信诈骗", "tech"), "general")
            self.assertEqual(_wire_classify("Steam 黑五多款游戏新史低：《战地 6》65.34 元", "游戏促销", "tech"), "general")

            # d) Cross-category dedup collapses UK-EU summit & Fed hike vs Cook & Jensen Huang resignation vs return
            dup_docs = {
                "finance": {
                    "events": [
                        {"event_id": "d_f1", "category": "finance", "title": "美联储时隔三年多重启加息25基点，官员密集放鹰", "fact_summary": "10年期美债收益率跌10基点报4.9438%（周跌19.", "evidence_status": "multi_source", "source_count": 2, "sources": [{"source_name": "WCN", "url": "https://x.com/f1"}]},
                        {"event_id": "d_f2", "category": "finance", "title": "特朗普呼吁黄仁勋道歉后重返英伟达", "fact_summary": "美媒称特朗普呼吁复职", "evidence_status": "single_source", "source_count": 1, "sources": [{"source_name": "R", "url": "https://x.com/f2"}]},
                    ]
                },
                "global": {
                    "events": [
                        {"event_id": "d_g1", "category": "global", "title": "美联储理事库克呼吁加息控通胀，官员对紧缩节奏存分歧", "fact_summary": "内部分歧仍在", "evidence_status": "single_source", "source_count": 1, "sources": [{"source_name": "R", "url": "https://x.com/g1"}]},
                        {"event_id": "d_g2", "category": "global", "title": "英国与欧盟举行脱欧后第二次峰会达成青年流动协议", "fact_summary": "英欧谈判突破", "evidence_status": "multi_source", "source_count": 2, "sources": [{"source_name": "R", "url": "https://x.com/g2"}]},
                    ]
                },
                "tech": {
                    "events": [
                        {"event_id": "d_t1", "category": "tech", "title": "英伟达董事会因诚信问题接受黄仁勋辞职", "fact_summary": "董事任命临时管理层", "evidence_status": "single_source", "source_count": 1, "sources": [{"source_name": "WSJ", "url": "https://x.com/t1"}]},
                    ]
                },
                "general": {
                    "events": [
                        {"event_id": "d_gen1", "category": "general", "title": "脱欧十年后英国与欧盟达成系列协议", "fact_summary": "涵盖食品与电力协议", "evidence_status": "single_source", "source_count": 1, "sources": [{"source_name": "BBC", "url": "https://x.com/gen1"}]},
                    ]
                },
            }
            _postprocess_and_prune_cross_category(dup_docs, {c: {} for c in dup_docs})
            flat_titles = [e["title"] for d in dup_docs.values() for e in d["events"]]
            self.assertEqual(sum(1 for t in flat_titles if "美联储" in t), 1)
            self.assertEqual(sum(1 for t in flat_titles if "黄仁勋" in t), 1)
            self.assertEqual(sum(1 for t in flat_titles if "欧盟" in t), 1)

            # e) Legacy broken parenthesis tail '报4.9438%（周跌19.' repaired by reconcile
            for c, d in dup_docs.items():
                atomic_write_json(root / f"analysis_{c}.json", d)
            refresh_and_sanitize_site_data(root, refresh_sec=False)
            fin_repaired = json.loads((root / "analysis_finance.json").read_text(encoding="utf-8"))
            self.assertFalse(fin_repaired["events"][0]["fact_summary"].endswith("19."))
            self.assertNotIn("（周跌19.", fin_repaired["events"][0]["fact_summary"])

    def test_v52_gemini_pool_search_images_ai_radar_sec_entities_and_pruning(self) -> None:
        import os
        from types import SimpleNamespace
        from unittest import mock

        from pipeline.ai_live_refresh import extract_ai_release_item, merge_live_ai_items_into_doc
        from pipeline.ai_radar_builder import AI_NOISE_RE, _infer_company, _infer_what_it_does_zh
        from pipeline.connectors.article_enricher import parse_article_html
        from pipeline.connectors.china_realtime import fetch_china_realtime_wires
        from pipeline.connectors.direct_rss import parse_rss_or_atom_xml
        from pipeline.connectors.gemini_search_hunter import _verify_and_resolve_candidate, _parse_search_published_at
        from pipeline.dedup import score_cluster_for_briefing
        from pipeline.entities import match_entities_with_reasons
        from pipeline.finance_impact_builder import build_finance_impact_artifact
        from pipeline.gemini_pool import (
            collect_api_key_slots,
            get_ordered_key_slots,
            get_quota_summary,
            call_gemini_raw,
        )
        from pipeline.manifest import prune_old_archives
        from pipeline.time_utils import parse_iso_datetime

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # 1. Unified 13-key pool rotates across ALL 13 keys, staggers per scope, cools down 429 keys without secret leak
            env_13 = {
                "KEY_TECH": "sec-t", "KEY_GLOBAL": "sec-g", "KEY_FINANCE": "sec-f", "KEY_GENERAL": "sec-gen",
                "GOOGLE_API_KEY": "sec-goog",
                **{f"KEY_{i}": f"sec-{i}" for i in range(1, 9)},
            }
            with mock.patch.dict(os.environ, env_13, clear=True):
                slots = collect_api_key_slots()
                self.assertEqual(len(slots), 13)
                fin_top = get_ordered_key_slots("briefing:finance", base_dir=root)[0].slot
                tech_top = get_ordered_key_slots("briefing:tech", base_dir=root)[0].slot
                self.assertNotEqual(fin_top, tech_top)

                # Simulate KEY_6 failing with 429 QUOTA_EXHAUSTED on 1st call -> cooldown persisted & skipped on fallback model
                tried_keys = []

                import sys

                class _FakeClient:
                    def __init__(self, api_key):
                        self.api_key = api_key
                        self.models = self

                    def generate_content(self, model, contents, config=None):
                        del contents, config
                        tried_keys.append((self.api_key, model))
                        if self.api_key == "sec-6":
                            raise RuntimeError("429 RESOURCE_EXHAUSTED: exceeded your current quota per day")
                        return SimpleNamespace(text='{"ok": true}')

                fake_types = SimpleNamespace(GenerateContentConfig=lambda **kw: kw)
                fake_genai = SimpleNamespace(Client=_FakeClient, types=fake_types)
                fake_google = SimpleNamespace(genai=fake_genai)
                with mock.patch.dict(sys.modules, {"google": fake_google, "google.genai": fake_genai, "google.genai.types": fake_types}):
                    res1 = call_gemini_raw(
                        scope="search_hunter",
                        prompt="test",
                        models=("gemini-4-hydrogen", "gemini-2.5-flash"),
                        base_dir=root,
                    )
                self.assertTrue(res1.ok)
                # Ensure KEY_6 is skipped immediately and quota summary leaks ZERO secret values
                qsum = get_quota_summary(root)
                self.assertEqual(qsum["exhausted_keys"], 1)
                self.assertNotIn("sec-6", json.dumps(qsum))
                self.assertNotIn("sec-6", (root / "data" / "gemini_quota_state.json").read_text(encoding="utf-8"))

            # 2. Search hunter date honesty & URL reachability resolution
            pub_iso, pub_src, ev_date = _parse_search_published_at("2026-11-18", parse_iso_datetime("2026-11-21T12:00:00+08:00"))
            self.assertEqual(ev_date, "2026-11-18")
            self.assertEqual(pub_src, "search_grounding")
            unk_iso, unk_src, unk_date = _parse_search_published_at("", parse_iso_datetime("2026-11-21T12:00:00+08:00"))
            self.assertIsNone(unk_iso)
            self.assertEqual(unk_src, "unknown")
            self.assertIsNone(unk_date)

            with mock.patch("pipeline.connectors.gemini_search_hunter._probe_url", side_effect=lambda u: "https://icj-cij.org/node/204" if "icj" in u else None):
                resolved = _verify_and_resolve_candidate(
                    {"title": "ICJ rules on Myanmar Rohingya case", "source_name": "ICJ", "url": "https://broken.example.com/404"},
                    [{"uri": "https://vertexaisearch.cloud.google.com/icj-chunk", "title": "ICJ ruling"}],
                )
            self.assertIsNotNone(resolved)
            self.assertEqual(resolved[0], "https://icj-cij.org/node/204")

            # 3. Real images (og:image + RSS media) & real Google News publisher resolution
            art = parse_article_html(
                '<html><head><meta property="og:image" content="/img/hero.jpg"><meta property="og:description" content="详情内容足够长以供摘要抽取使用。"></head><body><p>正文测试段落超过二十四个字符以便解析提取新闻首段信息。</p></body></html>',
                base_url="https://reuters.com/tech/article-1",
            )
            self.assertEqual(art["thumbnail_url"], "https://reuters.com/img/hero.jpg")

            gnews_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
            <rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
              <channel><item>
                <title>Nvidia slumps on SEC probe - Reuters</title>
                <link>https://news.google.com/rss/articles/CBMi123</link>
                <pubDate>Sat, 21 Nov 2026 08:00:00 GMT</pubDate>
                <source url="https://www.reuters.com">Reuters</source>
                <media:content url="https://cdn.reuters.com/thumb.webp" medium="image" />
              </item></channel>
            </rss>"""
            rss_items = parse_rss_or_atom_xml(
                gnews_xml,
                feed_spec={"id": "rss-gnews-world-en", "name": "Google News 英文国际", "category": "global", "family": "gnews-en"},
                fetched_iso="2026-11-21T16:30:00+08:00",
                now_dt=parse_iso_datetime("2026-11-21T16:30:00+08:00"),
            )
            self.assertEqual(len(rss_items), 1)
            self.assertEqual(rss_items[0]["source_name"], "Reuters")
            self.assertEqual(rss_items[0]["publisher_family"], "reuters")
            self.assertEqual(rss_items[0]["title"], "Nvidia slumps on SEC probe")
            self.assertEqual(rss_items[0]["thumbnail_url"], "https://cdn.reuters.com/thumb.webp")

            # 4. Cross-channel china_realtime canonical_url dedup (no duplicate URL in two categories)
            shared_item = {
                "item_id": "wscn_3203673", "source_id": "wscn-global-channel", "source_name": "华尔街见闻",
                "category": "global", "title": "欧盟与印尼签署贸易协定", "url": "https://wallstreetcn.com/livenews/3203673",
                "canonical_url": "https://wallstreetcn.com/livenews/3203673", "published_at": "2026-11-21T10:00:00+08:00",
            }
            with mock.patch("pipeline.connectors.china_realtime._fetch_wallstreetcn_channel", side_effect=[
                {"id": "wscn-global-channel", "name": "全球", "category": "global", "items": [dict(shared_item)], "error": None},
                {"id": "wscn-a-stock-channel", "name": "A股", "category": "finance", "items": [{**shared_item, "category": "finance"}], "error": None},
                {"id": "wscn-us-stock-channel", "name": "美股", "category": "finance", "items": [], "error": None},
                {"id": "wscn-tech-channel", "name": "科技", "category": "tech", "items": [], "error": None},
            ]), mock.patch("pipeline.connectors.china_realtime._fetch_cls_telegraph", return_value={"id": "cls-live", "name": "财联社", "category": "finance", "items": [], "error": None}), mock.patch("pipeline.connectors.china_realtime._fetch_sina_7x24_telegraph", return_value={"id": "sina-7x24", "name": "新浪财经", "category": "finance", "items": [], "error": None}), mock.patch("pipeline.connectors.china_realtime._fetch_rss_flash", return_value={"id": "rss", "name": "RSS", "category": "tech", "items": [], "error": None}):
                wire_res = fetch_china_realtime_wires()
            self.assertEqual(len(wire_res["items"]), 1)

            # 5. AI Radar classification, noise filter & canned filler removal
            self.assertEqual(_infer_company("欧盟央行宣布维持利率", "https://news.google.com/rss/articles/xyz", "Google News 全球")[0], "indie_opensource")
            self.assertEqual(_infer_company("微信香港钱包推出内地消费优惠", "https://example.com/hk", "财经")[0], "indie_opensource")
            self.assertEqual(_infer_company("xAI releases Grok 4 reasoning model", "https://x.ai/blog/grok-4", "xAI")[0], "xai")
            self.assertTrue(AI_NOISE_RE.search("小鹏汽车推出购车 0 首付金融方案"))
            self.assertTrue(AI_NOISE_RE.search("开源鸿蒙 5.1 开发者大会在深圳开幕"))
            self.assertTrue(AI_NOISE_RE.search("南水北调天河大模型工程正式上线"))
            self.assertEqual(_infer_what_it_does_zh("未知模型发布", ""), "")
            ai_live_no_filler = extract_ai_release_item(
                {"id": "x1", "title": "xAI 发布 Grok 4 推理模型", "url": "https://x.ai/grok4", "source_name": "xAI 官方"},
                "2026-11-21T12:00:00+08:00",
            )
            self.assertIsNotNone(ai_live_no_filler)
            self.assertEqual(ai_live_no_filler["company_id"], "xai")
            self.assertEqual(ai_live_no_filler["who_cares"], "")
            self.assertEqual(ai_live_no_filler["limitations"], "")

            # Self-healing existing polluted ai_progress.json removes NIO/OpenHarmony/Tianhe & news.google.com->google
            polluted = {
                "companies": [
                    {"company_id": "google", "company_name": "Google DeepMind", "region": "海外", "flagship_model": "G", "open_source_line": "G", "access_limits": "G", "items": [
                        {"id": "bad_g", "title": "欧洲议会讨论碳关税", "source_url": "https://news.google.com/rss/articles/CBMi1", "source_name": "Google News 全球", "date": "2026-11-21"}
                    ]},
                    {"company_id": "indie_opensource", "company_name": "独立实验室 & 开源黑马", "region": "全球开源", "flagship_model": "I", "open_source_line": "I", "access_limits": "I", "items": [
                        {"id": "bad_xpeng", "title": "小鹏汽车推出 0 首付购车金融优惠方案", "source_url": "https://ithome.com/xpeng", "source_name": "IT之家", "date": "2026-11-21"},
                    ]},
                ],
                "timeline": [],
            }
            healed, _ = merge_live_ai_items_into_doc(polluted, [], "2026-11-21T12:00:00+08:00")
            g_items = next(c["items"] for c in healed["companies"] if c["company_id"] == "google")
            i_items = next(c["items"] for c in healed["companies"] if c["company_id"] == "indie_opensource")
            self.assertEqual(len(g_items), 0)
            self.assertEqual(len(i_items), 0)

            # 6. Corporate gossip exemption & >=3-source SEC 8-K non-downgrade
            corp_sc, _ = score_cluster_for_briefing({"title": "英伟达 CEO 丑闻与 SEC 调查引发股价波动", "related_sources": [{"source_id": "reuters", "source_tier": "direct_media"}]}, watched_match_count=1)
            gossip_sc, _ = score_cluster_for_briefing({"title": "某明星出轨大瓜引发热搜", "related_sources": [{"source_id": "weibo", "source_tier": "news"}]}, watched_match_count=0)
            self.assertGreater(corp_sc, gossip_sc + 30)

            multi_titles = {
                1: "路透社：英伟达宣布 CEO 黄仁勋辞任并启动接替安排",
                2: "Nvidia announces Huang CEO departure and succession process",
                3: "彭博报道英伟达证实黄仁勋辞任 CEO，董事会启动继任安排",
            }
            multi_refs = {
                f"R00{i}": {
                    "item_id": f"it_{i}", "source_id": f"pub_{i}", "source_name": f"Media {i}",
                    "publisher_family": f"fam_{i}", "source_kind": "news", "source_tier": "direct_media",
                    "title": multi_titles[i],
                    "url": f"https://media{i}.com/nvda-{i}", "canonical_url": f"https://media{i}.com/nvda-{i}",
                    "published_at": "2026-11-20T10:00:00+08:00", "fetched_at": "2026-11-21T12:00:00+08:00",
                    "excerpt": "Board confirmed leadership succession process.", "citable_as_news": True,
                }
                for i in (1, 2, 3)
            }
            ev_multi = verify_and_enrich_event(
                {"title": "英伟达宣布CEO黄仁勋辞任并启动接替安排", "fact_summary": "三家外媒报道英伟达公布高管辞任与接替程序。", "source_refs": ["R001", "R002", "R003"], "event_date": "2026-09-16"},
                category="finance", input_batch_id="b1", fetched_at_iso="2026-11-21T12:00:00+08:00",
                ref_lookup=multi_refs, id_lookup={v["item_id"]: v for v in multi_refs.values()},
                prev_events=[], prev_batch_id=None,
                sec_entity_status={"ent_nvidia": {"latest_8k_date": "2026-11-18", "has_recent_502_officer_change": False}},
            )
            self.assertEqual(ev_multi["evidence_status"], "multi_source")
            self.assertEqual(ev_multi["contradictions"], [])
            self.assertIsNotNone(ev_multi["regulatory_note"])
            self.assertFalse(ev_multi["title"].startswith("报道称："))
            self.assertTrue(ev_multi["is_stale_rehash"])
            # Stale rehash events are skipped from fresh acute finance impact shock cards
            fi_stale = build_finance_impact_artifact(all_events=[ev_multi], batch_id="b1", generated_at_iso="2026-11-21T12:00:00+08:00", quotes_doc={"quotes": {}, "indices": []})
            self.assertEqual(fi_stale["total_mapped_events"], 0)

            # 7. Hormuz Trump story must NOT match ent_us_china_diplomacy; Oracle must match ent_oracle
            hormuz_ents = [m["entity_id"] for m in match_entities_with_reasons("特朗普就霍尔木兹海峡油轮触雷发表讲话")]
            self.assertNotIn("ent_us_china_diplomacy", hormuz_ents)
            oracle_ents = [m["entity_id"] for m in match_entities_with_reasons("甲骨文推出新一代云数据库企业AI套件")]
            self.assertIn("ent_oracle", oracle_ents)
            self.assertNotIn("ent_nvidia", oracle_ents)

            # 8. Orphan archive cleanup in prune_old_archives
            (root / "archives" / "raw" / "2026-11-01" / "01-00").mkdir(parents=True)
            (root / "archives" / "raw" / "2026-11-21" / "10-00").mkdir(parents=True)
            atomic_write_json(root / "history" / "raw_index.json", [{"path": "archives/raw/2026-11-21/10-00/"}])
            cleaned_cnt = prune_old_archives(root, "history/raw_index.json", keep_latest=1)
            self.assertEqual(cleaned_cnt, 1)
            self.assertFalse((root / "archives" / "raw" / "2026-11-01").exists())
            self.assertTrue((root / "archives" / "raw" / "2026-11-21" / "10-00").exists())

            # 9. Wire disaster & strategist routing, Insta360 noise rejection, GitHub notes cleanup, & bilingual Chinglish guard
            from pipeline.connectors.china_realtime import _classify_wire_item
            from pipeline.connectors.github_releases import _clean_notes
            from pipeline.ai_radar_builder import AI_NOISE_RE, _infer_company
            from pipeline.bilingual import _translate_zh_to_en_glossary, sanitize_en_output

            self.assertEqual(_classify_wire_item("青海海西州德令哈市发生5.6级地震", "USGS监测显示震源深度10公里", "finance"), "general")
            self.assertEqual(_classify_wire_item("加州发生里氏5.2级地震", "USGS地震信息网播报", "tech"), "global")
            self.assertEqual(_classify_wire_item("资深投资策略师：科技股估值迎来重新定价", "美股半导体板块波动加剧", "tech"), "finance")

            self.assertIsNotNone(AI_NOISE_RE.search("影石 Insta360 Mic Pro 迎来固件升级，混元降噪再增强"))
            self.assertIsNone(AI_NOISE_RE.search("腾讯 WorkBuddy 上线电脑操控能力与企业 Agent 生态"))
            self.assertEqual(_infer_company("腾讯 WorkBuddy 上线电脑操控能力", "https://hunyuan.tencent.com/")[0], "tencent_hunyuan")

            cleaned_gh = _clean_notes("**Full Changelog**: 1,061 commits from abc123 to def456\n* Bump deps by @dependabot[bot]\nAdded FP8 quantization support for Qwen3-Next.", max_len=200)
            self.assertNotIn("1,061 commits", cleaned_gh)
            self.assertNotIn("dependabot", cleaned_gh)
            self.assertIn("FP8 quantization", cleaned_gh)

            self.assertEqual(sanitize_en_output("【国际外交动态】Google’   s Gemini expands"), "Google's Gemini expands")
            self.assertEqual(_translate_zh_to_en_glossary("霍尔木兹海峡油轮触雷引发航运紧张", ["原油"]), "")
            self.assertIn("NVIDIA", _translate_zh_to_en_glossary("英伟达宣布AI芯片算力计划"))

            # 10. Lean pipeline observability, cross-lingual 0-source recovery, Hormuz consolidation & zero AI placeholders
            import os
            from xml.etree import ElementTree as ET
            from pipeline.ai_live_refresh import merge_live_ai_items_into_doc
            from pipeline.connectors.direct_rss import _resolve_rss_publisher
            from pipeline.gemini_pool import get_quota_summary
            from pipeline.manifest import load_json_if_exists
            from pipeline.v3_builder import build_v3_artifacts

            # 10a. direct_rss never outputs "Google News ..." as source_name
            gnews_xml = ET.fromstring("<item><title>美联储决议声明维持利率</title><link>https://news.google.com/rss/articles/abc</link></item>")
            _, pub_zh, _ = _resolve_rss_publisher(gnews_xml, "美联储决议声明维持利率", {"id": "rss-gnews-markets-zh", "name": "Google News A股/美股宏观异动", "family": "gnews-fin-zh"}, "https://news.google.com/rss/articles/abc")
            self.assertNotIn("Google News", pub_zh)

            # 10b. Cross-lingual 0-source recovery (Myanmar ICJ + YouTube $3B) & 2-source non-rumor confirmation
            en_refs = {
                "R147": {
                    "item_id": "icj_1", "source_id": "rss-bbc-world", "source_name": "BBC News",
                    "publisher_family": "bbc", "source_kind": "news", "source_tier": "direct_media",
                    "title": "World Court rules Myanmar committed genocide against Rohingya",
                    "url": "https://bbc.com/news/world-asia-1001", "canonical_url": "https://bbc.com/news/world-asia-1001",
                    "published_at": "2026-11-21T10:00:00+08:00", "fetched_at": "2026-11-21T11:00:00+08:00",
                    "excerpt": "UN International Court of Justice judges delivered landmark verdict.", "citable_as_news": True,
                },
                "R192": {
                    "item_id": "yt_1", "source_id": "rss-theverge", "source_name": "The Verge",
                    "publisher_family": "theverge", "source_kind": "news", "source_tier": "direct_media",
                    "title": "YouTube agrees in principle to $3B settlement over youth social media addiction lawsuits",
                    "url": "https://theverge.com/2026/11/21/yt-3b", "canonical_url": "https://theverge.com/2026/11/21/yt-3b",
                    "published_at": "2026-11-21T10:30:00+08:00", "fetched_at": "2026-11-21T11:00:00+08:00",
                    "excerpt": "Proposed agreement still awaits school district sign-off and judge approval.", "citable_as_news": True,
                },
                "R193": {
                    "item_id": "yt_2", "source_id": "rss-cnbc-tech", "source_name": "CNBC",
                    "publisher_family": "cnbc", "source_kind": "news", "source_tier": "direct_media",
                    "title": "Alphabet unit settles addiction litigation for $3 billion pending court approval",
                    "url": "https://cnbc.com/2026/11/21/yt-settlement", "canonical_url": "https://cnbc.com/2026/11/21/yt-settlement",
                    "published_at": "2026-11-21T10:40:00+08:00", "fetched_at": "2026-11-21T11:00:00+08:00",
                    "excerpt": "School plaintiffs and federal judge review required.", "citable_as_news": True,
                },
            }
            id_lkp = {v["item_id"]: v for v in en_refs.values()}
            myanmar_ev = verify_and_enrich_event(
                {"title": "联合国国际法院裁定缅甸对罗兴亚人犯下种族灭绝罪", "fact_summary": "海牙国际法院作出历史性裁决。", "source_refs": ["R147"]},
                category="global", input_batch_id="b1", fetched_at_iso="2026-11-21T11:30:00+08:00",
                ref_lookup=en_refs, id_lookup=id_lkp, prev_events=[], prev_batch_id=None,
            )
            self.assertGreaterEqual(myanmar_ev["source_count"], 1)
            self.assertEqual(myanmar_ev["publisher_name"], "BBC News")
            self.assertTrue(myanmar_ev["event_time"])
            self.assertIn("source_status", myanmar_ev)

            yt_ev = verify_and_enrich_event(
                {"title": "YouTube 原则上同意支付 30 亿美元和解社交媒体成瘾诉讼，尚待学区签署与法官批准", "fact_summary": "涉多项学校联合诉讼。", "source_refs": ["R192", "R193"], "unverified_claims": ["具体分期细节未公布"]},
                category="tech", input_batch_id="b1", fetched_at_iso="2026-11-21T11:30:00+08:00",
                ref_lookup=en_refs, id_lookup=id_lkp, prev_events=[], prev_batch_id=None,
            )
            self.assertEqual(yt_ev["source_count"], 2)
            self.assertFalse(yt_ev["title"].startswith("报道称："))

            # 10c. Hormuz storyline consolidation collapses 4 split variants into <= 1 storyline
            hormuz_events = []
            for idx, h_title in enumerate([
                "霍尔木兹海峡油轮触雷爆炸，美伊特使在柏林斡旋",
                "美伊谈判僵局与中东局势升温，美媒称以色列考虑动武",
                "美国制裁伊朗石油网络并聚焦核僵局",
                "霍尔木兹海峡多艘油轮触雷起火，美伊对抗升级",
            ]):
                hormuz_events.append(verify_and_enrich_event(
                    {"title": h_title, "fact_summary": h_title, "source_refs": ["R147"]},
                    category="global", input_batch_id="b1", fetched_at_iso="2026-11-21T11:30:00+08:00",
                    ref_lookup=en_refs, id_lookup=id_lkp, prev_events=[], prev_batch_id=None,
                    require_semantic_match=False, ordinal=idx,
                ))
            build_v3_artifacts(
                root, batch_id="smart-test", generated_at_iso="2026-11-21T11:30:00+08:00",
                cat_docs={"global": {"events": hormuz_events}}, prev_cat_events={}, prev_batch_id=None,
                connectors_payload={"items": [], "tech_tools": [], "calendar_events": [], "entity_updates": {}},
            )
            st_doc = load_json_if_exists(root / "data/storylines_index.json", default={})
            hormuz_sts = [k for k, v in (st_doc.get("storylines") or {}).items() if "伊朗" in str(v.get("title") or "") or "霍尔木兹" in str(v.get("title") or "")]
            self.assertLessEqual(len(hormuz_sts), 1)

            # 10d. AI Tracker drops Xiaomi MiMo promo, removes curated placeholders, and caps each lab at 8 items
            self.assertIsNotNone(AI_NOISE_RE.search("小米 MiMo 大模型套餐限免优惠促销来袭"))
            many_openai = [
                {"item_id": f"oa_{i}", "title": f"OpenAI 发布 GPT 特性更新 #{i}", "url": f"https://openai.com/news/upd-{i}", "source_name": "OpenAI 官方", "published_at": "2026-11-21T10:00:00+08:00", "is_first_hand": True}
                for i in range(12)
            ]
            ai_cap_doc, _ = merge_live_ai_items_into_doc({"companies": [{"company_id": "xai", "company_name": "xAI", "region": "海外", "flagship_model": "Grok", "open_source_line": "", "access_limits": "", "items": [{"id": "ai_xai_grok3_colossus", "title": "占位假条", "source_name": "batch_digest", "date": "2026-11-18"}]}], "timeline": []}, many_openai, "2026-11-21T12:00:00+08:00")
            self.assertEqual(len(next(c["items"] for c in ai_cap_doc["companies"] if c["company_id"] == "xai")), 0)
            self.assertLessEqual(len(next(c["items"] for c in ai_cap_doc["companies"] if c["company_id"] == "openai")), 8)

            # 10e. Gemini quota ledger initializes & persists non-secret state file
            with mock.patch.dict(os.environ, {"KEY_1": "AIzaFakeSecretShouldNeverBeWritten12345"}, clear=True):
                qs = get_quota_summary(root)
                self.assertEqual(qs["total_configured_keys"], 1)
                self.assertTrue((root / "data/gemini_quota_state.json").exists())
                raw_q_txt = (root / "data/gemini_quota_state.json").read_text(encoding="utf-8")
                self.assertNotIn("AIzaFakeSecret", raw_q_txt)

    def test_v53_pipeline_fixes_topics_lifecycle_first_hand_tools_calendar_and_pool(self) -> None:
        import os
        from types import SimpleNamespace
        import sys
        from unittest import mock
        from pipeline.ai_radar_builder import AI_NOISE_RE, _infer_company, _infer_what_it_does_zh, build_ai_progress_artifact
        from pipeline.bilingual import is_mostly_english
        from pipeline.connectors.china_realtime import _classify_wire_item
        from pipeline.connectors.github_releases import _clean_notes
        from pipeline.dedup import is_omnibus_digest_title, strip_raw_urls_and_domain_tails
        from pipeline.finance_impact_builder import build_finance_impact_artifact
        from pipeline.gemini_pool import call_gemini_raw
        from pipeline.manifest import atomic_write_json, load_json_if_exists
        from pipeline.topics_builder import build_dynamic_topics
        from pipeline.v3_builder import _infer_domain_next_catalyst, build_v3_artifacts
        from pipeline.verifier import _clean_source_display_name

        # 1. Per-model isolation in gemini_pool: 503 on gemini-4-hydrogen must NOT block fallback model on same key
        calls = []

        class _FallbackClient:
            def __init__(self, api_key):
                self.api_key = api_key
                self.models = self

            def generate_content(self, model, contents, config=None):
                del contents, config
                calls.append((self.api_key, model))
                if model == "gemini-4-hydrogen":
                    raise RuntimeError("503 UNAVAILABLE: overloaded")
                return SimpleNamespace(text='{"ok": true}')

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with mock.patch.dict(os.environ, {"KEY_1": "sec-1"}, clear=True):
                fake_types = SimpleNamespace(GenerateContentConfig=lambda **kw: kw)
                fake_genai = SimpleNamespace(Client=_FallbackClient, types=fake_types)
                fake_google = SimpleNamespace(genai=fake_genai)
                with mock.patch.dict(sys.modules, {"google": fake_google, "google.genai": fake_genai, "google.genai.types": fake_types}):
                    res = call_gemini_raw(
                        scope="default",
                        prompt="hi",
                        models=("gemini-4-hydrogen", "gemini-2.5-flash"),
                        base_dir=root,
                    )
                self.assertTrue(res.ok)
                self.assertEqual(res.model_used, "gemini-2.5-flash")
                self.assertIn(("sec-1", "gemini-2.5-flash"), calls)

            # 2. AI Progress & dedup hygiene: is_first_hand, llama.cpp->indie, 早报丨 digest, no robot boilerplate on layoffs, strip URLs
            self.assertTrue(is_omnibus_digest_title("早报丨曝Claude证明黎曼猜想/余承东更正表述/五月天演唱会"))
            self.assertEqual(strip_raw_urls_and_domain_tails("国内首个模型发布 - http://www.jingjiribao.cn/abc"), "国内首个模型发布")
            self.assertEqual(_infer_company("llama.cpp 发布 b12617", "https://github.com/ggml-org/llama.cpp/releases", "GitHub Releases")[0], "indie_opensource")
            self.assertIsNotNone(AI_NOISE_RE.search("国家水网“天河”大模型在京发布"))
            self.assertEqual(_infer_what_it_does_zh("OpenAI宣布解散部分机器人硬件团队", "OpenAI 调整组织架构，暂停部分机器人研发方向。", is_tool_release=False), "OpenAI 调整组织架构，暂停部分机器人研发方向。")
            self.assertTrue(is_mostly_english("【外媒快讯】OpenAI shares new prompting tips for GPT"))

            # GitHub release cleaner strips empty labels, sycl commits & unmatched brackets
            raw_rel = "Website:\nAttestations:\nsycl: column-blocked gated_delta_net kernel (#32456)\nAdded streaming tool call API for Qwen3."
            cleaned_rel = _clean_notes(raw_rel)
            self.assertNotIn("Website", cleaned_rel)
            self.assertNotIn("Attestations", cleaned_rel)
            self.assertNotIn("sycl:", cleaned_rel)
            self.assertIn("streaming tool call API", cleaned_rel)

            # 3. build_ai_progress_artifact populates is_first_hand & source_tier on every entry
            ai_doc = build_ai_progress_artifact(
                batch_id="b_test",
                generated_at_iso="2026-11-22T12:00:00+08:00",
                cat_docs={
                    "tech": {
                        "events": [
                            {
                                "event_id": "ev_oai_1",
                                "title": "OpenAI 发布全新代理开发工具包",
                                "fact_summary": "OpenAI 在开发者博客公布新版工具链接口。",
                                "first_reported_at": "2026-11-22T10:00:00+08:00",
                                "sources": [{"source_id": "rss-openai-news", "source_name": "OpenAI 官方动态", "url": "https://openai.com/news/agents"}],
                            }
                        ]
                    }
                },
                tech_tools=[
                    {
                        "tool_id": "tool_gh_ggml-org_llama_cpp",
                        "name": "llama.cpp",
                        "repo": "ggml-org/llama.cpp",
                        "latest_version": "b12617",
                        "version_published_at": "2026-11-22T07:04:00+08:00",
                        "release_url": "https://github.com/ggml-org/llama.cpp/releases/tag/b12617",
                        "source_name": "GitHub Releases API",
                        "summary": "Added Qwen3 tensor offload support.",
                    }
                ],
                base_dir=root,
            )
            self.assertGreaterEqual(len(ai_doc["timeline"]), 2)
            self.assertTrue(any(it.get("is_first_hand") is True and it.get("source_tier") == "first_party" for it in ai_doc["timeline"]))
            llama_ai = next(it for it in ai_doc["timeline"] if "llama.cpp" in it["title"])
            self.assertEqual(llama_ai["company_id"], "indie_opensource")

            # 4. Wire classification & source fallback fixes
            self.assertEqual(_classify_wire_item("中越海军在北部湾海域开展联合巡逻", "央视新闻报道联合巡逻任务", "global"), "global")
            self.assertEqual(_classify_wire_item("斗破苍穹剧场版动画定档海报公布", "粉丝关注", "tech"), "general")
            self.assertEqual(_classify_wire_item("长城坦克 300 新配色首支单曲上线", "新车周边", "tech"), "general")
            self.assertEqual(_classify_wire_item("今日迎来小雪节气，北方多地降温", "气象台提醒", "tech"), "general")
            self.assertNotEqual(_clean_source_display_name("Google News 英文国际", "Nvidia AI chip demand rises", "https://www.reuters.com/tech/nvda"), "综合资讯")
            self.assertEqual(_clean_source_display_name("Google News 英文国际", "Nvidia AI chip demand rises", "https://www.reuters.com/tech/nvda"), "路透社")

            # 5. Dynamic topics clustering, 4-stage lifecycle, concluded archive & hotlist filtering
            dyn = build_dynamic_topics(
                root,
                batch_id="b_dyn",
                generated_at_iso="2026-11-22T12:00:00+08:00",
                cat_docs={
                    "global": {
                        "events": [
                            {
                                "event_id": "evt_d1",
                                "category": "global",
                                "importance": "high",
                                "title": "欧盟公布新一轮关键矿产供应链本土化法案草案",
                                "fact_summary": "布鲁塞尔宣布降低单一来源依赖。",
                                "first_reported_at": "2026-11-22T09:00:00+08:00",
                                "sources": [{"source_id": "reuters", "source_name": "路透社", "publisher_family": "reuters", "url": "https://reuters.com/eu-minerals"}],
                            },
                            {
                                "event_id": "evt_d2",
                                "category": "global",
                                "importance": "high",
                                "title": "欧盟关键矿产供应链法案引发欧企投资预期升温",
                                "fact_summary": "多家矿业与精炼企业评估配套补贴方案。",
                                "first_reported_at": "2026-11-22T10:30:00+08:00",
                                "sources": [{"source_id": "ft", "source_name": "金融时报", "publisher_family": "ft", "url": "https://ft.com/eu-minerals"}],
                            },
                            {
                                "event_id": "evt_d3",
                                "category": "global",
                                "importance": "high",
                                "title": "欧盟议会下周将就关键矿产供应链战略储备机制举行投票",
                                "fact_summary": "法案拟设立联合采购与精炼补贴基金。",
                                "first_reported_at": "2026-11-22T11:30:00+08:00",
                                "sources": [{"source_id": "bloomberg", "source_name": "彭博社", "publisher_family": "bloomberg", "url": "https://bloomberg.com/eu-minerals"}],
                            },
                            # 2-node cluster must be rejected under strict Iron Rule 2 & 7
                            {
                                "event_id": "evt_2only_a",
                                "category": "global",
                                "importance": "high",
                                "title": "挪威主权基金调整四季度欧洲能源配置",
                                "fact_summary": "调仓报告。",
                                "first_reported_at": "2026-11-22T11:10:00+08:00",
                                "sources": [{"source_id": "ft", "source_name": "金融时报", "publisher_family": "ft", "url": "https://ft.com/norway-1"}],
                            },
                            {
                                "event_id": "evt_2only_b",
                                "category": "global",
                                "importance": "high",
                                "title": "挪威主权基金减持部分传统油气资产",
                                "fact_summary": "最新持仓披露。",
                                "first_reported_at": "2026-11-22T11:40:00+08:00",
                                "sources": [{"source_id": "reuters", "source_name": "路透社", "publisher_family": "reuters", "url": "https://reuters.com/norway-2"}],
                            },
                        ]
                    }
                },
                storylines={
                    "st_old_ended": {
                        "storyline_id": "st_old_ended",
                        "canonical_title": "某大型峰会圆满闭幕专题",
                        "category": "global",
                        "latest_reported_at": "2026-11-18T10:00:00+08:00",
                        "timeline": [
                            {"title": "开幕致辞", "published_at": "2026-11-17T10:00:00+08:00", "source_name": "新华社", "url": "https://xinhua.cn/1"},
                            {"title": "双边会晤", "published_at": "2026-11-17T16:00:00+08:00", "source_name": "路透社", "url": "https://reuters.com/2"},
                            {"title": "峰会闭幕并发表声明", "published_at": "2026-11-18T10:00:00+08:00", "source_name": "BBC", "url": "https://bbc.com/3"},
                        ],
                    }
                },
                raw_items_by_cat={
                    "global": [
                        {"source_id": "zhihu", "source_kind": "discussion", "title": "欧盟关键矿产供应链热议", "url": "https://zhihu.com/q/1", "published_at": None, "fetched_at": "2026-11-22T11:50:00+08:00"}
                    ]
                },
            )
            self.assertEqual(len(dyn["topics"]), 1)
            self.assertGreaterEqual(len(dyn["topics"][0]["timeline"]), 3)
            self.assertIn(dyn["topics"][0]["lifecycle_status"], ("starting", "ongoing"))
            self.assertGreaterEqual(len(dyn["archived_topics"]), 1)
            self.assertEqual(dyn["archived_topics"][0]["lifecycle_status"], "ended")
            # Ensure zhihu hotlist without published_at was excluded from timeline nodes
            all_tl_titles = [n["title"] for n in dyn["topics"][0]["timeline"]]
            self.assertNotIn("欧盟关键矿产供应链热议", all_tl_titles)

            # 6. Domain catalyst no longer misfires on Tesla FSD / Signal & retrospective calendar skips Anthropic IPO recap
            self.assertNotIn("补丁编号", _infer_domain_next_catalyst({"title": "特斯拉在美国推出 FSD v15 驾驶安全升级"}, None))
            self.assertNotIn("补丁编号", _infer_domain_next_catalyst({"title": "Signal 在 Windows 默认限制截屏增强隐私"}, None))

            # Retrospective article mentioning 周四 must NOT appear in future calendar
            v3_sum = build_v3_artifacts(
                root,
                batch_id="b_cal",
                generated_at_iso="2026-11-22T12:00:00+08:00",
                cat_docs={
                    "tech": {
                        "events": [
                            {
                                "event_id": "evt_anthro_recap",
                                "category": "tech",
                                "importance": "high",
                                "evidence_status": "single_source",
                                "title": "Anthropic IPO后股价表现不佳，引发市场对AI领域更广泛担忧",
                                "fact_summary": "该公司于周四上市后次日承压收跌，市场审视高估值盈利能力。",
                                "first_reported_at": "2026-11-21T09:00:00+08:00",
                                "sources": [{"source_id": "rss-theverge", "source_name": "The Verge", "url": "https://theverge.com/anthro"}],
                            }
                        ]
                    }
                },
                prev_cat_events={},
                prev_batch_id=None,
                connectors_payload={"items": [], "tech_tools": [], "calendar_events": [], "entity_updates": {}},
            )
            cal_doc = load_json_if_exists(root / "data/calendar.json", default={})
            self.assertFalse(any("Anthropic IPO后" in str(c.get("title")) for c in cal_doc.get("events") or []))
            pred_doc = load_json_if_exists(root / "data/predictions_public.json", default={})
            pred_raw = json.dumps(pred_doc, ensure_ascii=False)
            self.assertNotIn("连接器", pred_raw)
            self.assertNotIn("超级热点专题", pred_raw)
            self.assertGreaterEqual(v3_sum["radar_count"], 1)

            # 7. Finance impact differentiates OpenAI vs Gemini rationale (no copy-paste)
            fi_diff = build_finance_impact_artifact(
                cat_docs={
                    "tech": {
                        "events": [
                            {"event_id": "m1", "title": "OpenAI 发布 GPT-Live-1.1 实时语音编程模型", "fact_summary": "支持毫秒级语音和代码流。", "category": "tech", "importance": "high", "sources": [{"source_name": "OpenAI", "url": "https://openai.com/1"}]},
                            {"event_id": "m2", "title": "Google 发布 Gemini 4 Neon 端云推理模型", "fact_summary": "聚焦 TPU 高吞吐低延迟推理。", "category": "tech", "importance": "high", "sources": [{"source_name": "Google", "url": "https://blog.google/1"}]},
                        ]
                    }
                },
                batch_id="b_fi",
                generated_at_iso="2026-11-22T12:00:00+08:00",
                quotes_doc={"quotes": {}, "indices": []},
            )
            imp_map = fi_diff.get("event_impact_map") or {}
            self.assertIn("m1", imp_map)
            self.assertIn("m2", imp_map)
            self.assertNotEqual(imp_map["m1"]["one_liner"], imp_map["m2"]["one_liner"])

    def test_v54_topics_p0_recovery_post_dedup_ai_echo_hf_zh_and_cve_heal(self):
        from unittest import mock
        from pipeline.ai_radar_builder import _infer_what_it_does_zh, build_ai_progress_artifact
        from pipeline.connectors.huggingface_hub import format_hf_tool_summary
        from pipeline.manifest import atomic_write_json, load_json_if_exists
        from pipeline.topics_builder import build_dynamic_topics
        from pipeline.v3_builder import build_v3_artifacts

        # 1. Topics P0: post-dedup <3 rejected, ongoing > starting, overflow archives, broad entity guarded
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data").mkdir(parents=True, exist_ok=True)
            # Seed a curated ongoing topic + an already-concluded APEC topic + a 1-node junk topic
            atomic_write_json(
                root / "data/topics.json",
                {
                    "topics": [
                        {
                            "topic_id": "topic_apec_trump_china",
                            "title": "特朗普访华与 2026 深圳 APEC 峰会实时行程专题",
                            "subtitle": "实时聚合：APEC 峰会",
                            "category": "global",
                            "is_curated": True,
                            "is_auto_clustered": False,
                            "started_at": "2026-11-19T18:00:00+08:00",
                            "timeline": [
                                {"time": "2026-11-19T18:00:00+08:00", "title": "特朗普抵达深圳出席APEC", "source_name": "CNBC", "url": "https://cnbc.com/1"},
                                {"time": "2026-11-20T12:00:00+08:00", "title": "中美元首举行双边会晤", "source_name": "Reuters", "url": "https://reuters.com/2"},
                                {"time": "2026-11-22T06:00:00+08:00", "title": "APEC会议成果深圳展望闭幕", "source_name": "新华社", "url": "https://xinhua.cn/3"},
                            ],
                        },
                        {
                            "topic_id": "topic_nvidia_governance",
                            "title": "英伟达业绩、出口管制与管理层过渡追踪",
                            "subtitle": "跨天持续追踪",
                            "category": "finance",
                            "is_curated": True,
                            "is_auto_clustered": False,
                            "started_at": "2026-11-19T10:00:00+08:00",
                            "timeline": [
                                {"time": "2026-11-19T10:00:00+08:00", "title": "英伟达Q3营收指引超预期", "source_name": "WSJ", "url": "https://wsj.com/1"},
                                {"time": "2026-11-20T14:00:00+08:00", "title": "出口管制规则影响评估更新", "source_name": "Bloomberg", "url": "https://bloomberg.com/2"},
                                {"time": "2026-11-22T12:30:00+08:00", "title": "米哈游等大厂H200交付进展", "source_name": "FT", "url": "https://ft.com/3"},
                            ],
                        },
                        {
                            "topic_id": "topic_bad_1node",
                            "title": "国家数据局刘烈宏赴江西省调研",
                            "is_auto_clustered": True,
                            "timeline": [
                                {"time": "2026-11-22T12:00:00+08:00", "title": "刘烈宏赴江西调研", "source_name": "新华网", "url": "https://xinhua.cn/junk"}
                            ],
                        },
                    ],
                },
            )
            res_tp = build_dynamic_topics(
                root,
                batch_id="b_tp",
                generated_at_iso="2026-11-22T14:30:00+08:00",
                cat_docs={
                    "tech": {
                        "events": [
                            # 3 near-duplicate headlines that collapse to 1 node after dedup -> MUST be rejected!
                            {"event_id": "e_dup1", "title": "某品牌智能手环出货超2亿", "category": "tech", "entity_ids": ["ent_xiaomi"], "first_reported_at": "2026-11-22T13:00:00+08:00", "sources": [{"source_name": "IT之家", "publisher_family": "ithome", "url": "https://it.com/1"}]},
                            {"event_id": "e_dup2", "title": "某品牌智能手环出货超2亿台", "category": "tech", "entity_ids": ["ent_xiaomi"], "first_reported_at": "2026-11-22T13:10:00+08:00", "sources": [{"source_name": "新浪", "publisher_family": "sina", "url": "https://sina.com/2"}]},
                            {"event_id": "e_dup3", "title": "某品牌智能手环累计出货超2亿台", "category": "tech", "entity_ids": ["ent_xiaomi"], "first_reported_at": "2026-11-22T13:20:00+08:00", "sources": [{"source_name": "腾讯", "publisher_family": "qq", "url": "https://qq.com/3"}]},
                            # 3 unrelated Huawei stories must NOT merge into 1 topic
                            {"event_id": "e_hw1", "title": "鸿蒙智行问界新M7新增银色车漆实车上路", "category": "tech", "entity_ids": ["ent_huawei"], "first_reported_at": "2026-11-22T12:00:00+08:00", "sources": [{"source_name": "IT之家", "publisher_family": "ithome", "url": "https://it.com/hw1"}]},
                            {"event_id": "e_hw2", "title": "华为Mate 80国内销量突破百万部", "category": "tech", "entity_ids": ["ent_huawei"], "first_reported_at": "2026-11-22T12:30:00+08:00", "sources": [{"source_name": "新浪", "publisher_family": "sina", "url": "https://sina.com/hw2"}]},
                            {"event_id": "e_hw3", "title": "OSTA O1 Pro搭载全新麒麟芯片认证曝光", "category": "tech", "entity_ids": ["ent_huawei"], "first_reported_at": "2026-11-22T12:40:00+08:00", "sources": [{"source_name": "网易", "publisher_family": "163", "url": "https://163.com/hw3"}]},
                        ]
                    }
                },
                storylines={},
            )
            active_ids = [t["topic_id"] for t in res_tp["topics"]]
            arch_ids = [t["topic_id"] for t in res_tp["archived_topics"]]
            self.assertIn("topic_nvidia_governance", active_ids)
            self.assertEqual(res_tp["topics"][0]["lifecycle_status"], "ongoing")
            self.assertIn("topic_apec_trump_china", arch_ids)
            self.assertNotIn("topic_bad_1node", active_ids)
            self.assertEqual(len(res_tp["topics"]), 1)

        # 2. AI Progress: 国家中医药管理局 filtered out, Iron Rule 4 forbids boilerplate/echo & keeps genuine Chinese summary
        self.assertEqual(_infer_what_it_does_zh("OpenAI发布MedChemBench基准 评估AI药物研发推理", ""), "")
        self.assertEqual(
            _infer_what_it_does_zh(
                "NeonClipping：免费本地YouTube Shorts剪辑工具（2026年11月）",
                "NeonClipping：免费本地YouTube Shorts剪辑工具（2026年11月）explainx.ai",
            ),
            "",
        )
        real_sum = _infer_what_it_does_zh("Ollama 发布 v0.40", "新增支持 Inkling 2 Mini 模型与 Mac 端推理优化。")
        self.assertIn("Inkling 2 Mini", real_sum)

        with tempfile.TemporaryDirectory() as tmp:
            ai_doc = build_ai_progress_artifact(
                batch_id="b_ai",
                generated_at_iso="2026-11-22T14:00:00+08:00",
                cat_docs={
                    "tech": {
                        "events": [
                            {"event_id": "ev_tcm", "title": "国家中医药管理局认证中心：未与任何大模型企业合作，亦未开展测评", "fact_summary": "澄清声明。", "sources": [{"source_id": "wscn", "source_name": "华尔街见闻", "url": "https://wallstreetcn.com/tcm"}]},
                            {"event_id": "ev_bench", "title": "OpenAI发布MedChemBench基准 评估AI药物研发推理", "fact_summary": "OpenAI发布MedChemBench基准 评估AI药物研发推理", "sources": [{"source_id": "gnews", "source_name": "Reuters", "url": "https://reuters.com/medchem"}]},
                        ]
                    }
                },
                tech_tools=[],
                base_dir=Path(tmp),
            )
            tl_titles = [x["title"] for x in ai_doc["timeline"]]
            self.assertFalse(any("中医药" in t for t in tl_titles))
            bench_row = next(x for x in ai_doc["timeline"] if "MedChemBench" in x["title"])
            self.assertEqual(bench_row["what_it_does"], "")

        # 3. Iron Rule 4/5 regression guards: English stopwords, GH/HF cache isolation, wire fluff purge & clean topic headline
        from pipeline.connectors import _try_reuse_cached_connector
        from pipeline.connectors.china_realtime import refresh_live_wire_file
        from pipeline.dedup import title_similarity
        from pipeline.topics_builder import _build_cluster_headline

        self.assertLess(
            title_similarity(
                "Is the Galaxy S26 Ultra still worth buying at the end of 2026?",
                "The game of the year is finally here",
            ),
            0.25,
        )
        fake_prev_tools = [
            {"tool_id": "tool_gh_vllm", "name": "vLLM", "repo": "vllm-project/vllm", "official_url": "https://github.com/vllm-project/vllm"},
            {"tool_id": "tool_hf_qwen", "name": "Qwen/Qwen2-VL-2B-Instruct", "repo": "Qwen/Qwen2-VL-2B-Instruct", "official_url": "https://huggingface.co/Qwen/Qwen2-VL-2B-Instruct"},
        ]
        reused_gh = _try_reuse_cached_connector(
            "github-releases",
            {"connectors": [{"connector_id": "github-releases", "status": "ok", "fetched_at": "2026-11-22T14:30:00+08:00"}]},
            fake_prev_tools,
            [],
            "2026-11-22T14:35:00+08:00",
        )
        self.assertIsNotNone(reused_gh)
        self.assertEqual([t["tool_id"] for t in reused_gh["tech_tools"]], ["tool_gh_vllm"])

        t_clean, _, _ = _build_cluster_headline(
            [
                {"title": "财联社11月22日电，据美国地质调查局消息，秘鲁卡鲁阿马约东北偏北15公里处发生5.0级地震。", "source_name": "财联社", "publisher_name": "财联社"},
                {"title": "欧洲地中海地震中心：秘鲁中部发生5.1级地震，震源深度118公里。", "source_name": "金十数据", "publisher_name": "金十数据"},
                {"title": "秘鲁胡宁省强震引发局部通讯中断", "source_name": "央视新闻", "publisher_name": "央视新闻"},
            ],
            set(),
        )
        self.assertFalse(t_clean.startswith("财联社"))
        t_tesla, _, _ = _build_cluster_headline(
            [
                {"title": "特斯拉开启推送FSD V15全新可视化UI，大范围推送定于12月", "source_name": "IT之家", "publisher_name": "IT之家"},
                {"title": "特斯拉在美推出 FSD v15 实景视图并更新 Robotaxi 方案", "source_name": "新浪", "publisher_name": "新浪"},
                {"title": "特斯拉 FSD v15 全新可视化 UI 采用 3D 高斯重建", "source_name": "财联社", "publisher_name": "财联社"},
            ],
            {"ent_spacex_tesla"},
        )
        self.assertFalse(t_tesla.startswith("SpaceX"))

        with tempfile.TemporaryDirectory() as tmp_lw:
            lw_root = Path(tmp_lw)
            (lw_root / "data").mkdir(parents=True, exist_ok=True)
            atomic_write_json(
                lw_root / "data/live_wire.json",
                {
                    "items": [
                        {"id": "fluff1", "title": "国漫《斗破苍穹》剧场版定档午间开播", "url": "https://ithome.com/f1", "published_at": "2026-11-22T10:00:00+08:00"},
                        {"id": "ok1", "title": "美联储理事强调通胀粘性仍高", "url": "https://wallstreetcn.com/ok1", "published_at": "2026-11-22T10:05:00+08:00"},
                    ]
                },
            )
            with mock.patch("pipeline.connectors.china_realtime.fetch_china_realtime_wires", return_value={"connector_id": "china-realtime-wires", "connector_name": "test", "status": "ok", "fetched_at": "2026-11-22T14:30:00+08:00", "items": []}):
                lw_out = refresh_live_wire_file(lw_root)
            self.assertEqual([x["id"] for x in lw_out["items"]], ["ok1"])

        from pipeline.bilingual import enrich_zh_ai_progress
        from pipeline.topics_builder import _clean_headline_phrase

        echo_doc = {
            "timeline": [
                {
                    "id": "ai_e1",
                    "title": "Grok AI 和 10 亿美元押注后，SpaceX 投资者是否应重新审视？",
                    "title_en": "After Grok AI and $1B bet, should SpaceX investors rethink?",
                    "what_it_does": "",
                    "what_it_does_en": "After Grok AI and $1B bet, should SpaceX investors rethink?",
                },
                {
                    "id": "ai_e2",
                    "title": "NeonClipping：免费本地YouTube Shorts剪辑工具（2026年11月）",
                    "what_it_does": "NeonClipping：免费本地YouTube Shorts剪辑工具（2026年11月）explainx.ai",
                    "what_it_does_en": "",
                },
            ],
            "companies": [],
        }
        enrich_zh_ai_progress(echo_doc, base_dir=root)
        self.assertEqual(echo_doc["timeline"][0]["what_it_does"], "")
        self.assertEqual(echo_doc["timeline"][1]["what_it_does"], "")

        eq_title = _clean_headline_phrase("中国地震台网正式测定：11月22日14时30分，在四川雅安市石棉县（北纬29.1度）发生4.1级地震")
        self.assertFalse(eq_title.startswith("中国地震台网"))
        self.assertNotIn("（", eq_title if "）" not in eq_title else "")

        # 3. HF summary Chinese mapping & stale non-CVE storyline self-healing
        hf_zh = format_hf_tool_summary("image-text-to-text", 916848)
        self.assertIn("图文多模态", hf_zh)
        self.assertIn("91.7 万次", hf_zh)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data").mkdir(parents=True, exist_ok=True)
            atomic_write_json(
                root / "data/storylines_index.json",
                {
                    "storylines": {
                        "st_signal": {
                            "storyline_id": "st_signal",
                            "title": "Signal限制截图并阻止AI代理读取消息，以应对隐私威胁",
                            "category": "tech",
                            "latest_reported_at": "2026-11-22T10:00:00+08:00",
                            "next_catalyst": "等待官方安全响应中心发布补丁编号、受影响版本清单与安全整改指南",
                            "timeline": [{"title": "Signal限制截图", "published_at": "2026-11-22T10:00:00+08:00", "url": "https://signal.org/1"}],
                            "sources": [{"source_name": "The Verge", "url": "https://theverge.com/signal"}],
                        }
                    }
                },
            )
            build_v3_artifacts(
                root,
                batch_id="b_heal",
                generated_at_iso="2026-11-22T14:30:00+08:00",
                cat_docs={},
                prev_cat_events={},
                prev_batch_id=None,
                connectors_payload={
                    "items": [],
                    "tech_tools": [
                        {"tool_id": "openai-sdk", "name": "OpenAI SDK", "latest_version": "3.57.0", "summary": "3.57.0 (2026-11-19)；Features", "source_name": "GitHub Releases"},
                        {"tool_id": "hf-qwen", "name": "Qwen/Qwen2-VL-2B-Instruct", "summary": "模型任务：image-text-to-text；近期下载：916848 次", "source_name": "Hugging Face Hub API"},
                    ],
                    "calendar_events": [],
                    "entity_updates": {},
                },
            )
            st_out = load_json_if_exists(root / "data/storylines_index.json", default={})["storylines"]["st_signal"]
            self.assertNotIn("补丁编号", st_out["next_catalyst"])
            tt_out = load_json_if_exists(root / "data/tech_tools.json", default={})["tools"]
            sdk = next(t for t in tt_out if t["name"] == "OpenAI SDK")
            self.assertTrue(any("\u4e00" <= c <= "\u9fff" for c in sdk["summary"]))
            qwen = next(t for t in tt_out if "Qwen2-VL" in t["name"])
            self.assertNotIn("image-text-to-text", qwen["summary"])

    def test_domain_remediation_iron_rules(self) -> None:
        from pipeline.ai_radar_builder import AI_NOISE_RE
        from pipeline.build_briefing import _same_cross_category_story
        from pipeline.entities import ENTITY_BY_ID, match_entities_with_reasons
        from pipeline.finance_impact_builder import _build_domain_scenario, build_finance_impact_artifact
        from pipeline.manifest import load_json_if_exists
        from pipeline.topics_builder import (
            _clean_headline_phrase,
            _safe_clip_headline,
            _theater_conflict,
            build_dynamic_topics,
        )
        from pipeline.v3_builder import _build_investment_card, _infer_domain_next_catalyst, build_v3_artifacts
        from pipeline.verifier import _clean_source_display_name

        entities_map = {
            eid: {
                "entity_id": eid,
                "canonical_name": e.canonical_name,
                "aliases": list(e.aliases),
                "tickers": [{"symbol": s, "market": "US", "label": s} for s in (e.tickers or ())],
                "operating_variables": list(e.operating_variables or ()),
                "validation_milestones": list(e.validation_milestones or ()),
            }
            for eid, e in ENTITY_BY_ID.items()
        }

        # 1. Finance impact: no bogus AI positive match, no mechanical splicing, 5 new rules work, zero insufficient_evidence
        self.assertIsNone(_build_domain_scenario("Signal 更新客户端默认屏蔽截图，阻断 Siri AI、Gemini 等智能体读取", "Signal", {}))
        self.assertIsNone(_build_domain_scenario("TensorLean 验证黎曼猜想形式化证明", "TensorLean", {}))
        for sample_title in (
            "特斯拉宣布 FSD v15 即将向欧洲与中国用户推送",
            "软银拟千亿美元洽购 SK 海力士 HBM 产能",
            "马斯克警告 AI 行业面临严重资金短缺风险",
            "比特币重返 60,000 美元关键关口",
            "泰国禁止出口用于稀土加工的关键化学品",
        ):
            sc = _build_domain_scenario(sample_title, sample_title, {})
            self.assertIsNotNone(sc, f"Expected domain scenario for {sample_title}")
            self.assertNotIn("基于「", sc["one_liner"])
            self.assertNotIn("受「", sc["one_liner"])

        imp_doc = build_finance_impact_artifact(
            all_events=[
                {
                    "event_id": "e_unmapped",
                    "title": "地方非上市农贸协会召开年度会员例会",
                    "category": "finance",
                    "importance": "normal",
                    "fact_summary": "会员单位总结产销情况。",
                    "sources": [{"source_name": "综合资讯", "url": "https://example.com/1"}],
                },
                {
                    "event_id": "e_fsd",
                    "title": "特斯拉推动 FSD v15 全自动驾驶加速商业化",
                    "category": "tech",
                    "importance": "high",
                    "fact_summary": "端到端架构更新扩展至更多地区。",
                    "sources": [{"source_name": "Reuters", "url": "https://reuters.com/fsd"}],
                },
            ],
            batch_id="b_test",
            generated_at_iso="2026-11-22T15:00:00+08:00",
        )
        for card in imp_doc["event_impacts"]:
            self.assertNotEqual(card.get("validation_status"), "insufficient_evidence")
            self.assertTrue(card.get("bars"))

        # 2. Storylines & entities & verifier rules
        self.assertFalse(any(m["entity_id"] == "ent_tariffs_trade" for m in match_entities_with_reasons("泰国禁止出口用于稀土加工的化学品")))
        cat_crimea = _infer_domain_next_catalyst({"title": "克里米亚大桥恢复通行", "category": "global"}, None)
        self.assertNotIn("Postmortem", cat_crimea)
        btc_card = _build_investment_card(
            {
                "title": "比特币价格重返 60,000 美元大关",
                "fact_summary": "市场关注在 Anthropic、SpaceX 首次公开募股前风险资产反弹。",
                "category": "finance",
                "entity_ids": ["ent_anthropic", "ent_spacex_tesla"],
            },
            entities_map,
        )
        self.assertEqual(btc_card["related_assets"], [])
        self.assertNotEqual(_clean_source_display_name("综合资讯", "Global News Update"), "权威报道")
        eu_card = _build_investment_card(
            {"title": "欧洲议会削减欧盟多年期预算研发经费", "fact_summary": "财政分歧引发关注。", "category": "global"},
            entities_map,
        )
        self.assertFalse(any("毛利率变化" in v for v in eu_card["operating_variables"]))

        # Cross-category dedup matches canonical topics cleanly
        self.assertTrue(
            _same_cross_category_story(
                {"title": "TensorLean 探索黎曼猜想形式化验证", "sources": [{"url": "https://a.com/x"}]},
                {"title": "Lean 形式化工具与黎曼猜想验证进展", "sources": [{"url": "https://b.com/y"}]},
            )
        )

        # 3. Topic rules: no agency-only titles, no mid-word chops, theater guard, <12h never forced to ended
        clean_ir = _clean_headline_phrase("据伊朗塔斯尼姆通讯社：巴林美军基地附近发生无人机袭击")
        self.assertNotEqual(clean_ir, "据伊朗塔斯尼姆通讯社")
        self.assertIn("巴林美军基地", clean_ir)
        self.assertFalse(_safe_clip_headline("特斯拉FSD v15全面推出，Cybercab/Robotaxi加速测试", 28).endswith(("Robotax", "（", "“")))
        self.assertFalse(_safe_clip_headline("雅安发生4.9级地震，震源深度330千米", 18).endswith(("330千", "4.")))
        self.assertTrue(_theater_conflict("乌军打击扎波罗热及克里米亚大桥目标", "伊朗无人机袭击巴林美军基地"))

        # Same-day <12h protection & active/archived dedup + calendar diversification + HF 0-dl drop
        with tempfile.TemporaryDirectory() as tmp2:
            r2 = Path(tmp2)
            (r2 / "data").mkdir(parents=True, exist_ok=True)
            res = build_dynamic_topics(
                r2,
                batch_id="b_tp",
                generated_at_iso="2026-11-22T15:00:00+08:00",
                cat_docs={
                    "global": {
                        "events": [
                            {
                                "event_id": "eq1",
                                "title": "四川雅安石棉县发生地震",
                                "category": "global",
                                "latest_reported_at": "2026-11-22T14:20:00+08:00",
                                "sources": [{"source_name": "新华社", "url": "https://news.cn/eq1"}],
                            },
                            {
                                "event_id": "eq2",
                                "title": "雅安地震应急响应启动",
                                "category": "global",
                                "latest_reported_at": "2026-11-22T14:30:00+08:00",
                                "sources": [{"source_name": "央视新闻", "url": "https://cctv.com/eq2"}],
                            },
                            {
                                "event_id": "eq3",
                                "title": "中国地震台网：四川雅安震源深度10千米",
                                "category": "global",
                                "latest_reported_at": "2026-11-22T14:40:00+08:00",
                                "sources": [{"source_name": "中新社", "url": "https://chinanews.com/eq3"}],
                            },
                        ]
                    }
                },
                storylines={},
            )
            for arch in res["archived_topics"]:
                self.assertNotIn("雅安", arch["title"])
            out = build_v3_artifacts(
                r2,
                batch_id="b_cal",
                generated_at_iso="2026-11-22T15:00:00+08:00",
                cat_docs={},
                prev_cat_events={},
                prev_batch_id=None,
                connectors_payload={
                    "items": [],
                    "tech_tools": [
                        {"tool_id": "hf-zero", "name": "amd/sdxl-turbo-amdnpu-medusa", "downloads": 0, "summary": "模型任务：image-to-image；近期下载：0 次", "source_name": "Hugging Face Hub API"}
                    ],
                    "calendar_events": [],
                    "entity_updates": {},
                },
            )
            tools_out = load_json_if_exists(r2 / "data/tech_tools.json", default={})["tools"]
            self.assertFalse(any("sdxl-turbo-amdnpu-medusa" in t["name"] for t in tools_out))
            cal_out = load_json_if_exists(r2 / "data/calendar.json", default={})["events"]
            self.assertGreaterEqual(len(cal_out), 15)
            cal_types = {c.get("event_type") for c in cal_out}
            self.assertTrue({"politics_macro", "expo_summit", "tech_launch", "central_bank", "earnings_capital"}.issubset(cal_types))
            self.assertTrue(any("全国人民代表大会" in c.get("title", "") for c in cal_out))
            self.assertTrue(any("广交会" in c.get("title", "") and "中国·广州" == c.get("location_display") for c in cal_out))
            self.assertTrue(any("高交会" in c.get("title", "") and "中国·深圳" == c.get("location_display") for c in cal_out))
            self.assertIsNotNone(AI_NOISE_RE.search("SpaceX (SPCX) 投资者是否应重新审视持仓"))

        # 4. Trump overseas datacenter huge-tariff threat must NEVER hit APEC truce, TensorLean GPU -> None
        sc_dc_tax = _build_domain_scenario("特朗普称考虑对在海外建设数据中心的美国企业征收“巨额关税”", "特朗普威胁对海外建数据中心美企征收“巨额关税”", {})
        self.assertIsNotNone(sc_dc_tax)
        self.assertEqual(sc_dc_tax["rule_id"], "us_datacenter_tax_and_chip_curb")
        self.assertNotEqual(sc_dc_tax["rule_id"], "us_china_diplomacy_truce")
        self.assertIsNone(_build_domain_scenario("哥伦比亚大学与 CertiK 发布 TensorLean 验证 DeepSeek FlashAttention GPU 内核", "TensorLean 验证 GPU 内核", {}))

        # 5. Subtopic separation (Riemann vs TensorLean, Fed vs CENTCOM blockade), minor <5.0 quake rejection, active/archive dedup, 神舟24 & COP31 not ended
        from pipeline.topics_builder import _is_minor_quake, _subtopic_conflict

        self.assertTrue(_subtopic_conflict("Lean 社区推进黎曼猜想形式化证明", "哥伦比亚大学与 CertiK 发布 TensorLean 验证 DeepSeek GPU 内核"))
        self.assertTrue(_subtopic_conflict("美联储 12 月 FOMC 利率路径与黄金走低", "美国中央司令部对伊朗实施海上封锁第 130 天"))
        self.assertTrue(_is_minor_quake("中国地震台网正式测定：四川雅安市石棉县发生3.3级地震"))
        self.assertFalse(_is_minor_quake("四川某地发生6.2级地震致多处房屋倒塌"))
        self.assertFalse(_build_domain_scenario("NVIDIA", "NVIDIA", {}) is not None and "基于「" in str(_build_domain_scenario("NVIDIA 宣布", "NVIDIA", {}) or ""))

        with tempfile.TemporaryDirectory() as tmp3:
            r3 = Path(tmp3)
            (r3 / "data").mkdir(parents=True, exist_ok=True)
            res3 = build_dynamic_topics(
                r3,
                batch_id="b_tp3",
                generated_at_iso="2026-11-22T15:30:00+08:00",
                cat_docs={
                    "global": {
                        "events": [
                            {"event_id": "ru1", "title": "俄军袭击扎波罗热330千伏普拉沃贝雷日纳变电站", "category": "global", "latest_reported_at": "2026-11-22T15:00:00+08:00", "sources": [{"source_name": "Reuters", "url": "https://reuters.com/ru1"}]},
                            {"event_id": "ru2", "title": "俄军导弹袭击乌克兰敖德萨基利亚港口设施", "category": "global", "latest_reported_at": "2026-11-22T14:50:00+08:00", "sources": [{"source_name": "AP", "url": "https://apnews.com/ru2"}]},
                            {"event_id": "ru3", "title": "芬兰湾波罗的海俄罗斯船只 Sparta II 遭遇打击", "category": "global", "latest_reported_at": "2026-11-22T14:40:00+08:00", "sources": [{"source_name": "BBC", "url": "https://bbc.com/ru3"}]},
                            {"event_id": "ir1", "title": "伊朗革命卫队宣布袭击巴林美军基地", "category": "global", "latest_reported_at": "2026-11-22T15:10:00+08:00", "sources": [{"source_name": "Al Jazeera", "url": "https://aljazeera.com/ir1"}]},
                            {"event_id": "ir2", "title": "霍尔木兹海峡水雷威胁持续，美国中央司令部强化封锁巡航", "category": "global", "latest_reported_at": "2026-11-22T14:55:00+08:00", "sources": [{"source_name": "Reuters", "url": "https://reuters.com/ir2"}]},
                            {"event_id": "ir3", "title": "美军 F-35 战机在阿联酋基地警戒美伊对峙升温", "category": "global", "latest_reported_at": "2026-11-22T14:45:00+08:00", "sources": [{"source_name": "WSJ", "url": "https://wsj.com/ir3"}]},
                            {"event_id": "sz1", "title": "神舟二十四号载人飞船完成最后一次全区合练准备发射", "category": "tech", "latest_reported_at": "2026-11-22T14:00:00+08:00", "sources": [{"source_name": "新华社", "url": "https://news.cn/sz1"}]},
                            {"event_id": "sz2", "title": "酒泉卫星发射中心测试神舟二十四号箭船状态良好", "category": "tech", "latest_reported_at": "2026-11-22T13:50:00+08:00", "sources": [{"source_name": "央视新闻", "url": "https://cctv.com/sz2"}]},
                            {"event_id": "sz3", "title": "神舟二十四号航天员乘组即将亮相迎发射窗口", "category": "tech", "latest_reported_at": "2026-11-22T13:40:00+08:00", "sources": [{"source_name": "中新社", "url": "https://chinanews.com/sz3"}]},
                        ]
                    }
                },
                storylines={},
            )
            act = res3["topics"]
            ru_tps = [t for t in act if "俄乌" in t["title"]]
            ir_tps = [t for t in act if "美伊" in t["title"]]
            sz_tps = [t for t in act if "神舟" in t["title"]]
            self.assertEqual(len(ru_tps), 1)
            self.assertEqual(len(ir_tps), 1)
            self.assertEqual(len(sz_tps), 1)
            self.assertNotEqual(sz_tps[0]["lifecycle_status"], "ended")
            self.assertEqual(sz_tps[0]["region"], "china")
            self.assertFalse(any("3.3级地震" in t["title"] for t in act + res3["archived_topics"]))

    def test_v7_retention_and_residual_classification_fixes(self):
        import tempfile
        from pathlib import Path

        from pipeline.ai_live_refresh import _sort_key_iso_desc
        from pipeline.calendar_catalog import build_curated_global_calendar
        from pipeline.connectors.china_realtime import _classify_wire_item
        from pipeline.finance_impact_builder import _build_domain_scenario
        from pipeline.manifest import load_json_if_exists
        from pipeline.time_utils import parse_iso_datetime
        from pipeline.topics_builder import _classify_topic_region_and_orgs, _safe_clip_headline, _subtopic_conflict, build_dynamic_topics
        from pipeline.v3_builder import _clamp_storyline_timestamps, _infer_domain_next_catalyst, build_v3_artifacts

        now_dt = parse_iso_datetime("2026-11-22T19:00:00+08:00")
        cal_items = build_curated_global_calendar(now_dt)
        sz_cal = next((c for c in cal_items if "神舟二十四" in c.get("title", "")), None)
        self.assertIsNotNone(sz_cal)
        self.assertEqual(sz_cal["event_type"], "politics_macro")
        cop_cal = next((c for c in cal_items if "COP31" in c.get("title", "")), None)
        self.assertIsNotNone(cop_cal)
        self.assertEqual(cop_cal["region"], "global")

        # Topics: Fed=us (not middle_east), COP31=global & ending_soon, APEC concluded -> ended without NVIDIA/UNFCCC, GTA6 keeps subject
        fed_reg, fed_reg_l, fed_orgs, _ = _classify_topic_region_and_orgs(
            "美联储利率路径、美元走强与黄金大宗异动",
            [{"title": "美国官员：伊朗发动新一轮袭击"}, {"title": "美联储重启加息25个基点"}],
            ["ent_macro_fomc"],
            "finance",
        )
        self.assertEqual(fed_reg, "us")
        self.assertEqual(fed_reg_l, "美国")

        cop_reg, _, _, _ = _classify_topic_region_and_orgs(
            "COP31 安塔利亚气候大会加时磋商与化石燃料案文博弈",
            [{"title": "COP31因分歧过大被迫加时"}],
            [],
            "global",
        )
        self.assertEqual(cop_reg, "global")

        _, _, apec_orgs, _ = _classify_topic_region_and_orgs(
            "特朗普访华与 2026 深圳 APEC 峰会",
            [
                {"title": "特朗普发布30余张APEC深圳会议照片并肯定深圳面貌与中俄美元首会晤"},
                {"title": "习近平出席深圳APEC峰会并发表主旨演讲，峰会闭幕推动亚太合作"},
                {"title": "争夺联合国公海条约秘书处主办权如何考验中国推动全球领导力的努力"},
            ],
            ["ent_us_china_diplomacy"],
            "global",
        )
        self.assertNotIn("英伟达", apec_orgs)
        self.assertNotIn("联合国 UNFCCC", apec_orgs)
        self.assertTrue(_subtopic_conflict("特朗普访华与 2026 深圳 APEC 峰会", "FT 调查：与 Jensen Huang 有情感关系的 Alice Huang 牵涉走私 Nvidia 芯片"))
        self.assertTrue(_subtopic_conflict("《GTA 6》发行首日销售额破纪录", "外电：中国成功发行20亿美元主权债券"))
        gta_clip = _safe_clip_headline("“文娱史上最成功发售，堪比007、星球大战、米老鼠”！GTA 6发行首日收入高达38亿美元", 42)
        self.assertIn("GTA 6", gta_clip)

        with tempfile.TemporaryDirectory() as tmpd:
            rd = Path(tmpd)
            (rd / "data").mkdir(parents=True, exist_ok=True)
            res_tp = build_dynamic_topics(
                rd,
                batch_id="b_v7",
                generated_at_iso="2026-11-22T19:00:00+08:00",
                cat_docs={
                    "global": {
                        "events": [
                            {"event_id": "ap1", "title": "特朗普发布APEC深圳会议照片并肯定深圳面貌，峰会闭幕", "category": "global", "latest_reported_at": "2026-11-22T16:25:00+08:00", "sources": [{"source_name": "凤凰网", "url": "https://a.com/ap1"}]},
                            {"event_id": "ap2", "title": "习近平出席深圳APEC峰会并发表主旨演讲推动亚太合作", "category": "global", "latest_reported_at": "2026-11-22T09:30:00+08:00", "sources": [{"source_name": "新华社", "url": "https://a.com/ap2"}]},
                            {"event_id": "ap3", "title": "西学者：APEC深圳会议的三大象征意义与双重展示", "category": "global", "latest_reported_at": "2026-11-22T15:49:00+08:00", "sources": [{"source_name": "联合早报", "url": "https://a.com/ap3"}]},
                            {"event_id": "ap0", "title": "特朗普抵深出席2026 APEC峰会", "category": "global", "latest_reported_at": "2026-11-20T01:23:00+08:00", "sources": [{"source_name": "BBC", "url": "https://a.com/ap0"}]},
                            {"event_id": "eu1", "title": "欧盟与印度尼西亚历时十年谈判正式签署自由贸易协定", "category": "global", "latest_reported_at": "2026-11-22T12:00:00+08:00", "sources": [{"source_name": "Reuters", "url": "https://eu.com/1"}]},
                            {"event_id": "eu2", "title": "欧洲议会欢迎欧盟与印尼自贸协定正式签署落地", "category": "global", "latest_reported_at": "2026-11-22T11:30:00+08:00", "sources": [{"source_name": "AP", "url": "https://eu.com/2"}]},
                            {"event_id": "eu3", "title": "印尼贸易部披露与欧盟自由贸易协定关税减让细则", "category": "global", "latest_reported_at": "2026-11-22T10:30:00+08:00", "sources": [{"source_name": "BBC", "url": "https://eu.com/3"}]},
                            {"event_id": "cop1", "title": "COP31 安塔利亚气候大会进入第二天加时磋商，终稿草案删去化石燃料条款", "category": "global", "latest_reported_at": "2026-11-22T14:54:00+08:00", "sources": [{"source_name": "BBC", "url": "https://c.com/1"}]},
                            {"event_id": "cop2", "title": "各方核心症结待解，COP31安塔利亚大会继续延期", "category": "global", "latest_reported_at": "2026-11-22T10:42:00+08:00", "sources": [{"source_name": "Reuters", "url": "https://c.com/2"}]},
                            {"event_id": "cop3", "title": "COP31因分歧过大被迫“加时”磋商", "category": "global", "latest_reported_at": "2026-11-22T09:57:00+08:00", "sources": [{"source_name": "AP", "url": "https://c.com/3"}]},
                        ]
                    }
                },
                storylines={},
            )
            act_ids = {t["topic_id"] for t in res_tp["topics"]}
            arch_ids = {t["topic_id"] for t in res_tp["archived_topics"]}
            self.assertIn("topic_apec_trump_china", arch_ids)
            self.assertNotIn("topic_apec_trump_china", act_ids)
            self.assertIn("topic_eu_indonesia_fta", arch_ids)
            cop_tp = next((t for t in res_tp["topics"] if t["topic_id"] == "topic_cop31_climate"), None)
            self.assertIsNotNone(cop_tp)
            self.assertEqual(cop_tp["lifecycle_status"], "ending_soon")
            self.assertEqual(cop_tp["region"], "global")
            self.assertIn("recent_6h_count", cop_tp)

        # Storyline catalysts & monotonic timestamps
        self.assertNotIn("SpaceX", _infer_domain_next_catalyst({"title": "马斯克警告AI行业明年恐因算力变现滞后遭遇数千亿美元资金缺口", "category": "finance"}, {"entity_id": "ent_spacex_tesla", "validation_milestones": ["SpaceX 官方试飞直播与 FAA 许可"]}))
        self.assertNotIn("SpaceX", _infer_domain_next_catalyst({"title": "韩国1至10月对华汽车贸易逆差达42.36亿美元创历史新高，上海产特斯拉领跑在韩进口车销量", "category": "finance"}, {"entity_id": "ent_spacex_tesla", "validation_milestones": ["SpaceX 官方试飞直播与 FAA 许可"]}))
        self.assertIn("BTC", _infer_domain_next_catalyst({"title": "比特币与以太坊经历IPO前抛售后反弹，分别升穿60000美元与1700美元", "category": "finance"}, {"entity_id": "ent_anthropic", "validation_milestones": ["Anthropic 官方公告 / S-1 注册文件"]}))
        st_time = {"first_discovered_at": "2026-11-22T16:25:36+08:00", "first_reported_at": "2026-11-22T13:51:41+08:00", "latest_fact_update_at": "2026-11-22T16:20:10+08:00"}
        _clamp_storyline_timestamps(st_time)
        self.assertLessEqual(st_time["first_discovered_at"], st_time["latest_fact_update_at"])

        # AI progress sort key: date-only 2026-11-21 MUST sort ABOVE 2026-11-16T18:03 and 2026-09-09T12:24
        self.assertGreater(_sort_key_iso_desc("2026-11-21"), _sort_key_iso_desc("2026-11-16T18:03:36+08:00"))
        self.assertGreater(_sort_key_iso_desc("2026-11-21"), _sort_key_iso_desc("2026-09-09T12:24:42+08:00"))

        # Live wire: GTA 6 100FPS with currency note in excerpt -> tech (NEVER finance)
        self.assertEqual(
            _classify_wire_item("《GTA 6》Xbox 版存解锁帧率漏洞：最高可跑到 100FPS，但游戏速度也变快", "以首日 37.9 亿美元（IT之家注：现汇率约合 253.68 亿元人民币）创纪录", "finance"),
            "tech",
        )

        # Finance impact: Senate testimony vs Alice Huang smuggling produce distinct reasoning copy
        sc_senate = _build_domain_scenario("英伟达前 CEO 黄仁勋将赴美国参议院银行委员会公开作证，公司据悉被 SEC 调查", "黄仁勋参议院作证", {})
        sc_smug = _build_domain_scenario("FT 调查称与前英伟达 CEO 黄仁勋存在情感关系的 Alice Huang 牵涉对华芯片走私网络", "Alice Huang 芯片走私调查", {})
        self.assertIsNotNone(sc_senate)
        self.assertIsNotNone(sc_smug)
        self.assertNotEqual(sc_senate["rule_id"], sc_smug["rule_id"])
        self.assertNotEqual(sc_senate["one_liner"], sc_smug["one_liner"])

    def test_v8_severity_tiering_fast_track_and_promo_filter(self) -> None:
        from datetime import datetime, timedelta
        from unittest import mock
        from pipeline.build_briefing import (
            _is_unrelated_company_mashup,
            _postprocess_and_prune_cross_category,
            classify_event_severity,
        )
        from pipeline.connectors.china_realtime import refresh_live_wire_file
        from pipeline.dedup import has_authoritative_primary_source, is_consumer_promo_or_fluff
        from pipeline.time_utils import SHANGHAI_TZ

        # 1. C-tier noise filter rejects promos, game deals, photo-ops, venue protests & minor quakes,
        #    while keeping real financial policy, science breakthroughs & billion-dollar sales records.
        for noise in (
            "TCL 24英寸显示器 699元",
            "蚂蚁电竞 27英寸显示器 6499元",
            "飞利浦 27英寸显示器 1199元",
            "Steam 育碧游戏《极限国度》16.8元 1折史低",
            "传闻《黑色洛城2》预计 2030年发售",
            "特朗普发布30余张APEC深圳会议照片并肯定深圳面貌",
            "菲律宾总统马科斯公开赞扬深圳APEC中国接待",
            "德国初创 Helsing 发布会场地抗议引发围观",
            "四川雅安市石棉县发生3.3级地震",
        ):
            self.assertTrue(is_consumer_promo_or_fluff(noise), f"Expected noise drop for: {noise}")

        for real_news in (
            "沪深北交易所将融资保证金比例下限降至 80%，有望释放 4000 亿元增量资金",
            "菲尔兹奖得主梅纳德回应 AI 证明黎曼猜想",
            "BepiColombo 航天器飞行 8 年进入水星轨道",
            "GTA 6 发行首日销售额高达 38 亿美元创文娱纪录",
        ):
            self.assertFalse(is_consumer_promo_or_fluff(real_news), f"Unexpected noise drop for: {real_news}")

        self.assertTrue(_is_unrelated_company_mashup("通威股份回购、思特威增资、三安光电总经理辞职"))
        self.assertFalse(_is_unrelated_company_mashup("沪深北交易所联合修订融资保证金与做市商规则，释放4000亿元资金"))

        now_dt = datetime(2026, 11, 22, 20, 0, 0, tzinfo=SHANGHAI_TZ)
        fresh_iso = (now_dt - timedelta(hours=1)).isoformat()
        stale_iso = (now_dt - timedelta(hours=65)).isoformat()

        # 2. Hotlist-only items can NEVER be S or A; hotlist-only market recaps & promos are stripped;
        #    >24h old stories lose S-tier & is_new_in_batch; cross-cat 思特威 dedupes; S <= 3 and (S+A)/total <= 25%.
        self.assertFalse(
            has_authoritative_primary_source(
                [{"source_id": "baidu", "source_name": "百度热搜", "source_tier": "aggregator_lead"}]
            )
        )
        cat_docs = {
            "finance": {
                "events": [
                    {
                        "event_id": "fin_400b",
                        "title": "沪深北交易所将融资保证金比例下限降至80%，有望释放4000亿元增量资金",
                        "fact_summary": "三大交易所宣布调整融资保证金下限并同步优化做市机制。",
                        "category": "finance",
                        "evidence_status": "multi_source",
                        "independent_publisher_count": 3,
                        "published_at": fresh_iso,
                        "latest_reported_at": fresh_iso,
                        "is_new_in_batch": True,
                        "sources": [{"source_id": "cls-telegraph", "source_name": "财联社", "source_tier": "direct_media", "url": "https://cls.cn/1"}],
                    },
                    {
                        "event_id": "fin_stale_ipo",
                        "title": "Anthropic 纳斯达克上市总募资 935 亿美元创纪录",
                        "fact_summary": "周四晚间上市交易募资。",
                        "category": "finance",
                        "evidence_status": "official_confirmed",
                        "independent_publisher_count": 4,
                        "published_at": stale_iso,
                        "latest_reported_at": stale_iso,
                        "is_new_in_batch": True,
                        "sources": [{"source_id": "sec-edgar", "source_name": "SEC EDGAR", "source_tier": "first_party", "url": "https://sec.gov/1"}],
                    },
                    {
                        "event_id": "fin_hotlist_btc",
                        "title": "现货黄金跌近3500美元、纳指跌超5%、英伟达跌14%及BTC跌破6万美元",
                        "fact_summary": "多市场前期行情回顾。",
                        "category": "finance",
                        "evidence_status": "multi_source",
                        "independent_publisher_count": 3,
                        "published_at": fresh_iso,
                        "sources": [
                            {"source_id": "baidu", "source_name": "百度热搜", "source_tier": "aggregator_lead", "url": "https://baidu.com/1"},
                            {"source_id": "zhihu", "source_name": "知乎热榜", "source_kind": "discussion", "url": "https://zhihu.com/1"},
                        ],
                    },
                    {
                        "event_id": "fin_smartsens",
                        "title": "思特威拟增资 15 亿元加码高端图像传感器研发",
                        "fact_summary": "公司公告拟增资子公司。",
                        "category": "finance",
                        "evidence_status": "multi_source",
                        "published_at": fresh_iso,
                        "sources": [{"source_id": "wscn-news", "source_name": "华尔街见闻", "source_tier": "direct_media", "url": "https://wscn.com/s1"}],
                    },
                    {
                        "event_id": "fin_mashup",
                        "title": "通威股份回购、隆基绿能定增、三安光电总经理辞职",
                        "fact_summary": "多家公司常规公告汇总。",
                        "category": "finance",
                        "evidence_status": "single_source",
                        "published_at": fresh_iso,
                        "sources": [{"source_id": "jin10", "source_name": "金十数据", "source_tier": "direct_media", "url": "https://jin10.com/m1"}],
                    },
                ]
            },
            "tech": {
                "events": [
                    {
                        "event_id": "tech_smartsens_dup",
                        "title": "芯片厂商思特威宣布增资 15 亿元拓展车载 CIS",
                        "fact_summary": "拓展研发中心。",
                        "category": "tech",
                        "evidence_status": "single_source",
                        "published_at": fresh_iso,
                        "sources": [{"source_id": "ithome", "source_name": "IT之家", "source_tier": "direct_media", "url": "https://ithome.com/s2"}],
                    },
                    {
                        "event_id": "tech_bepi",
                        "title": "BepiColombo 航天器飞行 8 年成功进入水星轨道",
                        "fact_summary": "欧空局与日本宇宙航空研究开发机构联合探测器进入环水星轨道。",
                        "category": "tech",
                        "evidence_status": "multi_source",
                        "published_at": fresh_iso,
                        "sources": [{"source_id": "reuters", "source_name": "Reuters", "source_tier": "direct_media", "url": "https://reuters.com/bepi"}],
                    },
                    {
                        "event_id": "tech_promo_noise",
                        "title": "TCL 24英寸显示器 699元现已开售",
                        "fact_summary": "首发价699元。",
                        "category": "tech",
                        "evidence_status": "single_source",
                        "published_at": fresh_iso,
                        "sources": [{"source_id": "ithome", "source_name": "IT之家", "source_tier": "direct_media", "url": "https://ithome.com/tcl"}],
                    },
                    {
                        "event_id": "tech_hotlist_rumor",
                        "title": "报道称Anthropic数学家声称与Claude合作证明Navier-Stokes方程",
                        "fact_summary": "社交平台热议。",
                        "category": "tech",
                        "evidence_status": "single_source",
                        "published_at": fresh_iso,
                        "sources": [{"source_id": "toutiao", "source_name": "今日头条", "source_tier": "aggregator_lead", "url": "https://toutiao.com/ns"}],
                    },
                ]
            },
            "global": {
                "events": [
                    {
                        "event_id": "glo_photo",
                        "title": "特朗普发布30余张APEC深圳会议照片并肯定深圳面貌",
                        "fact_summary": "社交媒体晒图。",
                        "category": "global",
                        "evidence_status": "multi_source",
                        "published_at": fresh_iso,
                        "sources": [{"source_id": "baidu", "source_name": "百度热搜", "source_tier": "aggregator_lead", "url": "https://baidu.com/p"}],
                    },
                    {
                        "event_id": "glo_fomc",
                        "title": "美联储最新利率决议释放政策分歧信号，美债收益率波动加剧",
                        "fact_summary": "多位美联储官员就后续加息与通胀路径发声。",
                        "category": "global",
                        "evidence_status": "official_confirmed",
                        "published_at": fresh_iso,
                        "sources": [{"source_id": "fed-fomc", "source_name": "美联储官网", "source_tier": "first_party", "url": "https://federalreserve.gov/fomc"}],
                    },
                ]
            },
            "general": {
                "events": [
                    {
                        "event_id": "gen_routine_1",
                        "title": "多地发布冬季交通保畅安全提示",
                        "fact_summary": "常规交通出行提醒。",
                        "category": "general",
                        "evidence_status": "single_source",
                        "published_at": fresh_iso,
                        "sources": [{"source_id": "thepaper", "source_name": "澎湃新闻", "source_tier": "direct_media", "url": "https://thepaper.cn/1"}],
                    },
                    {
                        "event_id": "gen_routine_2",
                        "title": "文旅部公布冬季冰雪旅游推荐线路",
                        "fact_summary": "推荐十条线路。",
                        "category": "general",
                        "evidence_status": "single_source",
                        "published_at": fresh_iso,
                        "sources": [{"source_id": "ifeng", "source_name": "凤凰网", "source_tier": "direct_media", "url": "https://ifeng.com/2"}],
                    },
                ]
            },
        }
        with mock.patch("pipeline.build_briefing.now_shanghai", return_value=now_dt):
            _postprocess_and_prune_cross_category(cat_docs, {})

        remaining = [ev for doc in cat_docs.values() for ev in doc.get("events") or []]
        rem_ids = {ev["event_id"] for ev in remaining}
        self.assertNotIn("fin_hotlist_btc", rem_ids)
        self.assertNotIn("tech_promo_noise", rem_ids)
        self.assertNotIn("glo_photo", rem_ids)
        # Smartsens duplicate across finance/tech must collapse to 1
        self.assertLessEqual(sum(1 for ev in remaining if "思特威" in ev["title"]), 1)
        # 65h old Anthropic IPO demoted out of S and loses is_new_in_batch
        anth = next(ev for ev in remaining if ev["event_id"] == "fin_stale_ipo")
        self.assertNotEqual(anth["severity_tier"], "S")
        self.assertFalse(anth["is_new_in_batch"])
        # Hotlist rumor & mashup never high/S/A
        for ev_id in ("tech_hotlist_rumor", "fin_mashup"):
            obj = next(ev for ev in remaining if ev["event_id"] == ev_id)
            self.assertEqual(obj["severity_tier"], "B")
            self.assertNotEqual(obj["importance"], "high")
        # S <= 3 and (S + A) <= max(3, int(len(remaining) * 0.25))
        s_cnt = sum(1 for ev in remaining if ev.get("severity_tier") == "S")
        sa_cnt = sum(1 for ev in remaining if ev.get("severity_tier") in {"S", "A"})
        self.assertLessEqual(s_cnt, 3)
        self.assertGreaterEqual(s_cnt, 1)
        self.assertLessEqual(sa_cnt, max(3, int(len(remaining) * 0.25)))
        self.assertEqual(next(ev for ev in remaining if ev["event_id"] == "fin_400b")["severity_tier"], "S")

        # Additional V8 regressions caught during live batch 21-13
        self.assertTrue(is_consumer_promo_or_fluff("iPhone Duo行情大跳水，第三方渠道价低于官方1300元"))
        self.assertTrue(is_consumer_promo_or_fluff("新疆乌鲁木齐发生4.5级地震，暂无人员伤亡报告"))
        jinke_tier, _ = classify_event_severity(
            {
                "title": "金科股份控股股东及合伙人因涉嫌信息披露违法违规遭证监会立案",
                "fact_summary": "控股股东被立案，上市公司非涉事主体。",
                "evidence_status": "multi_source",
                "published_at": fresh_iso,
                "sources": [{"source_id": "cls-telegraph", "source_tier": "direct_media"}],
            },
            now_dt,
        )
        self.assertEqual(jinke_tier, "B")
        ex_tier, _ = classify_event_severity(
            {
                "title": "中国三大交易所下调融资保证金比例并减免费用以稳定市场",
                "fact_summary": "沪深北交易所公告。",
                "evidence_status": "single_source",
                "published_at": fresh_iso,
                "sources": [{"source_id": "cls-telegraph", "source_tier": "direct_media"}],
            },
            now_dt,
        )
        self.assertEqual(ex_tier, "S")
        tw_tier, _ = classify_event_severity(
            {
                "title": "台湾地区拟下调融资保证金比例至120%以稳定股市",
                "fact_summary": "台湾地区相关传闻。",
                "evidence_status": "multi_source",
                "published_at": fresh_iso,
                "sources": [{"source_id": "sina-7x24", "source_tier": "direct_media"}],
            },
            now_dt,
        )
        self.assertEqual(tw_tier, "B")

        # 3. Live wire fast-track breaking_highlights + purge old C-tier items (and Taiwan vs Mainland isolation)
        with tempfile.TemporaryDirectory() as tmpd:
            td = Path(tmpd)
            (td / "data").mkdir(parents=True, exist_ok=True)
            (td / "data" / "live_wire.json").write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "id": "old_mon",
                                "title": "飞利浦 27英寸显示器 1199元首发",
                                "category": "tech",
                                "source_name": "IT之家",
                                "url": "https://ithome.com/mon",
                                "published_at": now_dt.isoformat(),
                            },
                            {
                                "id": "old_steam",
                                "title": "Steam 育碧游戏《极限国度》16.8元 1折史低",
                                "category": "general",
                                "source_name": "IT之家",
                                "url": "https://ithome.com/steam",
                                "published_at": now_dt.isoformat(),
                            },
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            mock_wires = {
                "status": "ok",
                "fetched_at": now_dt.isoformat(),
                "connector_name": "7×24 国内/全球实时电报快讯 (2/6)",
                "items": [
                    {
                        "item_id": "w_margin",
                        "title": "沪深北交易所将融资保证金比例下限降至 80%，有望释放 4000 亿元增量资金",
                        "category": "finance",
                        "source_id": "cls-live",
                        "source_name": "财联社 7×24 电报",
                        "url": "https://cls.cn/m1",
                        "published_at": (now_dt - timedelta(minutes=20)).isoformat(),
                        "excerpt": "沪深北交易所调整融资保证金比例。",
                    },
                    {
                        "item_id": "w_sse",
                        "title": "上交所修订科创板做市商规则并推出组合降费",
                        "category": "finance",
                        "source_id": "wscn-a-stock-channel",
                        "source_name": "华尔街见闻 A股快讯",
                        "url": "https://wscn.com/sse1",
                        "published_at": (now_dt - timedelta(minutes=15)).isoformat(),
                        "excerpt": "同步降低交易成本。",
                    },
                    {
                        "item_id": "w_tw",
                        "title": "台湾地区拟下调融资保证金比例至120%以稳定股市",
                        "category": "finance",
                        "source_id": "sina-7x24",
                        "source_name": "新浪财经 7×24 电报",
                        "url": "https://finance.sina.com.cn/tw1",
                        "published_at": (now_dt - timedelta(minutes=10)).isoformat(),
                        "excerpt": "台湾地区稳市传闻。",
                    },
                ],
            }
            with mock.patch("pipeline.connectors.china_realtime.fetch_china_realtime_wires", return_value=mock_wires):
                with mock.patch("pipeline.connectors.china_realtime.now_shanghai", return_value=now_dt):
                    lw = refresh_live_wire_file(td)
            lw_titles = [it["title"] for it in lw["items"]]
            self.assertFalse(any("显示器" in t or "Steam" in t for t in lw_titles))
            brks = lw.get("breaking_highlights") or []
            self.assertEqual(len(brks), 1)
            self.assertIn("4000", brks[0]["title"])
            self.assertNotIn("台湾", "".join(brks[0].get("related_titles") or []))
            self.assertGreaterEqual(brks[0]["related_count"], 1)

    def test_v9_finance_impact_and_ai_progress_refactor(self) -> None:
        from pipeline.ai_live_refresh import extract_ai_release_item, merge_live_ai_items_into_doc
        from pipeline.ai_radar_builder import (
            AI_NOISE_RE,
            build_ai_progress_artifact,
            detect_is_open_source,
            is_foreign_subject_blocked,
        )
        from pipeline.finance_impact_builder import _build_domain_scenario, build_finance_impact_artifact

        # --- Part I: Finance Impact V9 Checks ---
        # 1. Domestic brokerage bottoming report mentioning overseas Fed rates must NOT be Fed hawkish bearish
        sc_cmsc = _build_domain_scenario(
            "招商证券研报：市场多项指标逐步趋近历史底部水平。海外方面提及美联储加息周期与利率变动。",
            "招商证券研报：市场多项指标逐步趋近历史底部水平",
            {},
        )
        self.assertIsNotNone(sc_cmsc)
        self.assertNotEqual(sc_cmsc["rule_id"], "central_bank_hawkish")
        self.assertEqual(sc_cmsc["polarity"], "bullish")

        # 2. Low-impact 3rd-party AI benchmark chatter blocked
        self.assertIsNone(
            _build_domain_scenario(
                "Artificial Analysis评测：OpenAI GPT-6.2 Astra和Sol回答更简短但透明度低于Claude",
                "Artificial Analysis评测：OpenAI GPT-6.2 Astra和Sol回答更简短但透明度低于Claude",
                {},
            )
        )

        # 3. Gold plunge + physical bar rush differentiates miners vs Caibai retail
        sc_gold_div = _build_domain_scenario(
            "金价连续跳水，北京菜百投资金条被抢购一空",
            "金价连续跳水，北京菜百投资金条被抢购一空",
            {},
        )
        self.assertIsNotNone(sc_gold_div)
        self.assertEqual(sc_gold_div["rule_id"], "precious_metals_physical_divergence")
        self.assertEqual(sc_gold_div["polarity"], "divergent")

        # 4. Full build with breaking_highlights yields >= 8 cards, 4000亿 margin cut is bullish, all 4 deep dimensions present
        sample_events = [
            {
                "event_id": "e_cmsc",
                "title": "招商证券研报：市场多项指标逐步趋近历史底部水平",
                "fact_summary": "报告提及海外美联储利率与国内估值磨底。",
                "category": "finance",
                "importance": "normal",
                "latest_reported_at": "2026-11-22T18:00:00+08:00",
                "sources": [{"source_name": "财联社", "url": "https://cls.cn/cmsc"}],
            },
            {
                "event_id": "e_gold_cb",
                "title": "金价连续跳水，北京菜百投资金条被抢购一空",
                "fact_summary": "期货金价回调引发线下买金热情。",
                "category": "finance",
                "importance": "normal",
                "latest_reported_at": "2026-11-22T17:00:00+08:00",
                "sources": [{"source_name": "第一财经", "url": "https://yicai.com/gold"}],
            },
            {
                "event_id": "e_tpu_cut",
                "title": "郭明錤：谷歌削减2027年博通设计的TPU 8i系列出货量约100万颗",
                "fact_summary": "定制芯片供应链排产下调。",
                "category": "tech",
                "importance": "normal",
                "latest_reported_at": "2026-11-22T16:30:00+08:00",
                "sources": [{"source_name": "IT之家", "url": "https://ithome.com/tpu"}],
            },
            {
                "event_id": "e_ai_srv",
                "title": "AI服务器厂商要求涨价最高达45%",
                "fact_summary": "整机硬件需求紧张。",
                "category": "finance",
                "importance": "normal",
                "latest_reported_at": "2026-11-22T16:00:00+08:00",
                "sources": [{"source_name": "华尔街见闻", "url": "https://wscn.com/srv"}],
            },
            {
                "event_id": "e_sam_mem",
                "title": "韩媒爆料三星未来3年大部分存储芯片产能被锁定，客户要求供货保障至2031年",
                "fact_summary": "AI 存储芯片长单锁死。",
                "category": "general",
                "importance": "normal",
                "latest_reported_at": "2026-11-22T15:30:00+08:00",
                "sources": [{"source_name": "财联社", "url": "https://cls.cn/mem"}],
            },
            {
                "event_id": "e_buyback",
                "title": "华友钴业拟以10亿元-15亿元回购股份",
                "fact_summary": "大额回购计划维护股东价值。",
                "category": "finance",
                "importance": "normal",
                "latest_reported_at": "2026-11-22T15:00:00+08:00",
                "sources": [{"source_name": "财联社", "url": "https://cls.cn/hy"}],
            },
            {
                "event_id": "e_hormuz",
                "title": "伊朗就霍尔木兹海峡问题表态，并与阿曼保持密切关系",
                "fact_summary": "海湾航道避险升温。",
                "category": "finance",
                "importance": "normal",
                "latest_reported_at": "2026-11-22T14:30:00+08:00",
                "sources": [{"source_name": "路透社", "url": "https://reuters.com/hz"}],
            },
            {
                "event_id": "e_cop31",
                "title": "联合国COP31气候谈判破裂，未能就化石燃料达成协议",
                "fact_summary": "传统能源与新能源预期分化。",
                "category": "finance",
                "importance": "high",
                "latest_reported_at": "2026-11-22T14:00:00+08:00",
                "sources": [{"source_name": "BBC", "url": "https://bbc.com/cop"}],
            },
            {
                "event_id": "e_rocket",
                "title": "蓝箭航天朱雀三号回收发动机再次点火试车，具备再次使用条件",
                "fact_summary": "商业航天可回收技术突破。",
                "category": "general",
                "importance": "normal",
                "latest_reported_at": "2026-11-22T13:00:00+08:00",
                "sources": [{"source_name": "新华社", "url": "https://news.cn/zq3"}],
            },
        ]
        fi_doc = build_finance_impact_artifact(
            all_events=sample_events,
            batch_id="b_v9",
            generated_at_iso="2026-11-22T22:00:00+08:00",
            quotes_doc={"quotes": {"NVDA": {"ticker": "NVDA", "name": "英伟达", "market": "美股", "price": 125.53, "pct_change": -14.01, "atr_20d_pct": 4.5}}},
            breaking_highlights=[
                {
                    "id": "brk_4000",
                    "title": "沪深北交易所降低融资保证金比例下限至80% 理论上可带来增量资金近4000亿元",
                    "excerpt": "沪深北交易所同步下调做市商门槛并免收上市初费。",
                    "category": "finance",
                    "severity_tier": "S",
                    "source_name": "财联社",
                    "url": "https://cls.cn/4000",
                    "published_at": "2026-11-22T20:30:00+08:00",
                }
            ],
        )
        cards = fi_doc["event_impacts"]
        self.assertGreaterEqual(len(cards), 8)
        margin_card = next((c for c in cards if "4000亿" in c["event_title"] or "80%" in c["event_title"]), None)
        self.assertIsNotNone(margin_card)
        self.assertEqual(margin_card["polarity"], "bullish")
        self.assertFalse(any(c["event_id"] == "e_cmsc" and c["rule_id"] == "central_bank_hawkish" for c in cards))
        for card in cards:
            self.assertIn("status_label", card.get("priced_in_analysis") or {})
            layers = card.get("transmission_layers") or []
            self.assertEqual(len(layers), 3)
            self.assertTrue(any(s.get("code") for s in layers[0].get("stocks") or []))
            precs = card.get("historical_precedents") or []
            self.assertGreaterEqual(len(precs), 2)
            self.assertTrue(all(p.get("date") and p.get("t1_reaction") and p.get("t5_reaction") for p in precs))
            q_rules = card.get("quant_if_then") or []
            self.assertGreaterEqual(len(q_rules), 2)
            self.assertTrue(all(b.get("proxy_ticker") for b in card["bars"]))

        # --- Part II: AI Progress V9 Checks ---
        self.assertFalse(detect_is_open_source("OpenAI发起“反蒸馏战”，大规模封禁账户", "", company_id="openai"))
        self.assertFalse(detect_is_open_source("OpenAI 发布 GPT-6.2 Astra", "", company_id="openai"))
        self.assertTrue(detect_is_open_source("腾讯混元 Hy4 权重正式开源", "", url="https://huggingface.co/tencent/Hy4", company_id="tencent_hunyuan"))
        self.assertTrue(is_foreign_subject_blocked("Signal更新默认屏蔽截图，阻止Siri AI、Gemini等AI智能体读取消息"))
        self.assertIsNotNone(AI_NOISE_RE.search("千问APP学生教师优惠上线 9.9元/月"))
        self.assertIsNotNone(AI_NOISE_RE.search("B站就“AI 大肥鱼”智能体账号泛滥发布调查问卷"))
        self.assertIsNone(extract_ai_release_item({"title": "Signal更新默认屏蔽截图，阻止Siri AI、Gemini读取屏幕", "url": "https://signal.org/x"}, "2026-11-22T22:00:00+08:00"))

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cat_docs = {
                "tech": {
                    "events": [
                        {
                            "event_id": "ant_1",
                            "title": "Claude AI辅助证明黎曼猜想获Lean官方认证，马斯克直呼惊人成就",
                            "fact_summary": "形式化数学验证突破。",
                            "latest_reported_at": "2026-11-22T18:00:00+08:00",
                            "sources": [{"source_name": "财联社", "url": "https://cls.cn/r1"}],
                        },
                        {
                            "event_id": "ant_2",
                            "title": "Anthropic旗下Claude辅助完成黎曼猜想形式化验证获官方认可",
                            "fact_summary": "多家外媒报道。",
                            "latest_reported_at": "2026-11-22T19:00:00+08:00",
                            "sources": [
                                {"source_name": "华尔街见闻", "url": "https://wscn.com/r2"},
                                {"source_id": "anthropic", "source_name": "Anthropic Official", "url": "https://anthropic.com/news/riemann"},
                            ],
                        },
                        {
                            "event_id": "gg_tr1",
                            "title": "谷歌 Gemini API 推出全新工具检索 Tool Retrieval 功能",
                            "fact_summary": "支持动态检索引入大规模工具定义。",
                            "latest_reported_at": "2026-11-22T16:00:00+08:00",
                            "sources": [{"source_name": "IT之家", "url": "https://ithome.com/tr1"}],
                        },
                        {
                            "event_id": "gg_tr2",
                            "title": "Google Gemini API launches Tool Retrieval for large agent toolsets",
                            "fact_summary": "Official Google AI blog update.",
                            "latest_reported_at": "2026-11-22T17:00:00+08:00",
                            "sources": [{"source_id": "rss-google-ai-blog", "source_name": "Google AI Official", "url": "https://blog.google/ai/tool-retrieval"}],
                        },
                        {
                            "event_id": "gg_sig",
                            "title": "Signal更新默认屏蔽截图，阻止Siri AI、Gemini等AI智能体读取消息",
                            "fact_summary": "第三方通讯应用安全策略。",
                            "latest_reported_at": "2026-11-22T15:00:00+08:00",
                            "sources": [{"source_name": "IT之家", "url": "https://ithome.com/sig"}],
                        },
                        {
                            "event_id": "oai_m1",
                            "title": "OpenAI 发布 MedChemBench 化学研究基准",
                            "fact_summary": "化学合成评估基准。",
                            "latest_reported_at": "2026-11-22T14:00:00+08:00",
                            "sources": [{"source_name": "InfoQ", "url": "https://infoq.cn/m1"}],
                        },
                        {
                            "event_id": "oai_m2",
                            "title": "OpenAI introduces MedChemBench benchmark for medicinal chemistry",
                            "fact_summary": "Published on OpenAI research blog.",
                            "latest_reported_at": "2026-11-22T14:30:00+08:00",
                            "sources": [{"source_id": "rss-openai-news", "source_name": "OpenAI News", "url": "https://openai.com/news/medchem"}],
                        },
                    ]
                },
                "global": {
                    "events": [
                        {
                            "event_id": "mm_1",
                            "title": "MiniMax公布AI辅助密码分析研究成果，攻破NIST竞赛候选算法",
                            "fact_summary": "科研密码分析突破。",
                            "latest_reported_at": "2026-11-22T12:00:00+08:00",
                            "sources": [{"source_name": "财联社", "url": "https://cls.cn/mm1"}],
                        },
                        {
                            "event_id": "mm_2",
                            "title": "MiniMax 发布 AI 密码分析研究成果并攻破 NIST 候选算法",
                            "fact_summary": "重复快讯。",
                            "latest_reported_at": "2026-11-22T13:00:00+08:00",
                            "sources": [{"source_name": "新浪财经", "url": "https://sina.com.cn/mm2"}],
                        },
                    ]
                },
            }
            ai_doc = build_ai_progress_artifact(
                batch_id="b_v9_ai",
                generated_at_iso="2026-11-22T22:00:00+08:00",
                cat_docs=cat_docs,
                tech_tools=[],
                base_dir=root,
            )
            self.assertTrue((root / "data/ai_progress_archive.json").exists())
            arch_doc = json.loads((root / "data/ai_progress_archive.json").read_text(encoding="utf-8"))

            comps_by_id = {c["company_id"]: c for c in ai_doc["companies"]}
            self.assertEqual(len(comps_by_id), 23)
            # Zero empty labs
            self.assertEqual(sum(1 for c in comps_by_id.values() if len(c["items"]) == 0), 0)
            # Flagship sync & model_lineage present on every lab
            self.assertIn("GLM-5.4", comps_by_id["zhipu_glm"]["flagship_model"])
            self.assertIn("GPT-6.2", comps_by_id["openai"]["flagship_model"])
            self.assertIn("Gemini 4", comps_by_id["google"]["flagship_model"])
            for c in comps_by_id.values():
                self.assertTrue(len(c.get("model_lineage") or []) >= 3, f"Missing model_lineage on {c['company_id']}")

            # OpenAI closed items NOT marked open-source
            for o_it in comps_by_id["openai"]["items"]:
                self.assertFalse(o_it["is_open_source"], f"OpenAI item wrongly open-source: {o_it['title']}")
                self.assertTrue(o_it.get("milestone_dim") in {"flagship_release", "research_breakthrough", "api_agent_eng", "open_source_eco", "commercial_governance"})

            # OpenAI, Anthropic, Google each retain >=1 first-hand official item even after wire merge
            for must_fh in ("openai", "anthropic", "google"):
                self.assertGreaterEqual(sum(1 for x in comps_by_id[must_fh]["items"] if x.get("is_first_hand")), 1, f"{must_fh} missing first-hand")

            # Intra-org dedup collapses Riemann, Tool Retrieval, MedChemBench, Cryptanalysis to 1 card each
            self.assertEqual(sum(1 for x in comps_by_id["anthropic"]["items"] if "黎曼" in x["title"]), 1)
            riemann_card = next(x for x in comps_by_id["anthropic"]["items"] if "黎曼" in x["title"])
            self.assertTrue(riemann_card["is_first_hand"])
            self.assertGreaterEqual(len(riemann_card.get("related_sources") or []), 2)

            self.assertEqual(sum(1 for x in comps_by_id["google"]["items"] if "工具检索" in x["title"] or "Tool Retrieval" in x["title"]), 1)
            self.assertFalse(any("Signal" in x["title"] for x in comps_by_id["google"]["items"]))
            self.assertEqual(sum(1 for x in comps_by_id["openai"]["items"] if "MedChemBench" in x["title"]), 1)
            self.assertEqual(sum(1 for x in comps_by_id["minimax"]["items"] if "密码分析" in x["title"]), 1)

            # Archive recovers Gemini 4 Neon, Hydrogen/Carbon, Genie 4, 混元 Hy4, NWM 3.0
            arch_titles = " || ".join(it["title"] for it in arch_doc["timeline"])
            for needle in ("Gemini 4 Neon", "Hydrogen", "Genie 4", "Hy4", "NWM 3.0"):
                self.assertIn(needle, arch_titles)

            # Live merge preserves first_hand when secondary wire arrives afterwards
            live_after, _ = merge_live_ai_items_into_doc(
                ai_doc,
                [{"title": "外媒：OpenAI反蒸馏封号打击提取", "url": "https://36kr.com/oai-distill", "source_name": "36氪", "published_at": "2026-11-22T22:10:00+08:00"}],
                "2026-11-22T22:15:00+08:00",
            )
            oai_after = next(c for c in live_after["companies"] if c["company_id"] == "openai")
            distill_card = next(x for x in oai_after["items"] if "反蒸馏" in x["title"])
            self.assertTrue(distill_card["is_first_hand"])
            self.assertFalse(distill_card["is_open_source"])

    def test_v10_breaking_calendar_parser_ai_attribution_and_tools_parity(self) -> None:
        from datetime import datetime, timedelta, timezone
        from pipeline.ai_radar_builder import AI_NOISE_RE, _infer_company
        from pipeline.calendar_catalog import (
            build_event_type_watch_variable,
            extract_breaking_calendar_items,
            parse_relative_schedule_datetime,
        )
        from pipeline.connectors.github_releases import DEFAULT_WATCHED_REPOS
        from pipeline.connectors.huggingface_hub import format_hf_tool_summary

        tz = timezone(timedelta(hours=8))
        anchor = datetime(2026, 11, 22, 15, 0, tzinfo=tz)  # Sunday

        # 1. Full ZH/EN relative dates
        tmw = parse_relative_schedule_datetime("明天马斯克将开发布会展示新硬件", anchor)
        self.assertIsNotNone(tmw)
        self.assertEqual(tmw[0].strftime("%Y-%m-%d"), "2026-11-23")

        nx_mon = parse_relative_schedule_datetime("智谱 AI 将于下周一召开 GLM-5.4 发布会", anchor)
        self.assertIsNotNone(nx_mon)
        self.assertEqual(nx_mon[0].strftime("%Y-%m-%d"), "2026-11-23")

        nx_fri = parse_relative_schedule_datetime("交易所将于下周五正式实施两融新规", anchor)
        self.assertIsNotNone(nx_fri)
        self.assertEqual(nx_fri[0].strftime("%Y-%m-%d"), "2026-11-27")

        en_nx_tue = parse_relative_schedule_datetime("Tesla will host AI event next Tuesday in Austin", anchor)
        self.assertIsNotNone(en_nx_tue)
        self.assertEqual(en_nx_tue[0].strftime("%Y-%m-%d"), "2026-11-24")

        # 2. Breaking schedule extraction across News + Wire + AI; blocks political chatter & earnings boilerplate on politics
        cals = extract_breaking_calendar_items(
            cat_docs={
                "global": {
                    "events": [
                        {
                            "event_id": "evt_pol_bad",
                            "title": "以色列正直党邀请内塔尼亚胡本周一进行组阁谈判",
                            "fact_summary": "以色列政坛博弈持续。",
                            "category": "global",
                            "sources": [{"source_name": "Reuters", "url": "https://r.com/il"}],
                        },
                        {
                            "event_id": "evt_sg_visit",
                            "title": "新加坡总理将于11月23日至25日正式出访",
                            "fact_summary": "双方将举行会谈并发表经贸声明。",
                            "category": "global",
                            "sources": [{"source_name": "联合早报", "url": "https://zaobao.com/sg"}],
                        },
                    ]
                }
            },
            live_wire_items=[
                {
                    "id": "lw_musk",
                    "title": "明天马斯克将主持发布会公布 Optimus 新进展",
                    "published_at": "2026-11-22T14:00:00+08:00",
                    "source_name": "财联社",
                    "url": "https://cls.cn/musk",
                }
            ],
            ai_progress_items=[
                {
                    "id": "ai_zhipu",
                    "title": "智谱下周三发布 GLM-5.4 新版推理旗舰模型",
                    "what_it_does": "发布全新架构与开源权重。",
                    "date": "2026-11-22T16:00:00+08:00",
                    "company_id": "zhipu_glm",
                    "company_name": "智谱 AI",
                    "source_name": "IT之家",
                    "source_url": "https://ithome.com/glm54",
                }
            ],
            generated_dt=anchor,
            existing_calendar_items=[],
        )
        cal_titles = " || ".join(c["title"] for c in cals)
        self.assertNotIn("内塔尼亚胡", cal_titles)
        self.assertIn("新加坡总理", cal_titles)
        self.assertIn("马斯克", cal_titles)
        self.assertIn("GLM-5.4", cal_titles)
        for c in cals:
            self.assertTrue(c.get("is_breaking_schedule"))
            self.assertNotIn("毛利率与下季指引", c.get("watch_variable", ""))
        self.assertNotIn("毛利率与下季指引", build_event_type_watch_variable("politics_macro")[0])

        # 3. AI attribution & noise guard: GPT-6.2 vs Claude belongs to OpenAI + filtered by AI_NOISE_RE; NeonClipping blocked
        self.assertEqual(
            _infer_company("GPT-6.2 Astra和Sol能更快地直达要点，但透明度评分低于Claude")[0],
            "openai",
        )
        self.assertTrue(bool(AI_NOISE_RE.search("NeonClipping：YouTube Shorts 智能剪辑工具")))
        self.assertTrue(bool(AI_NOISE_RE.search("GPT-6.2 Astra和Sol能更快地直达要点，但透明度评分低于Claude")))

        # 4. HF summaries are differentiated across models; GitHub default repos expanded >= 20
        self.assertGreaterEqual(len(DEFAULT_WATCHED_REPOS), 20)
        sum_qwen = format_hf_tool_summary("image-text-to-text", 52000, model_id="Qwen/Qwen3-VL-8B-Instruct", tags=["gguf"])
        sum_ds = format_hf_tool_summary("image-text-to-text", 81000, model_id="deepseek-ai/DeepSeek-VL2-MoE", tags=["fp8"])
        self.assertNotEqual(sum_qwen, sum_ds)
        self.assertIn("Qwen3-VL-8B-Instruct", sum_qwen)
        self.assertIn("DeepSeek-VL2-MoE", sum_ds)

    def test_v11_finance_dedup_nvda_tpu_subject_routing_and_en_ai_filter(self) -> None:
        from datetime import datetime
        from pipeline.ai_live_refresh import merge_live_ai_items_into_doc
        from pipeline.ai_radar_builder import AI_NOISE_RE, _infer_company
        from pipeline.calendar_catalog import parse_relative_schedule_datetime
        from pipeline.finance_impact_builder import (
            _build_domain_scenario,
            build_finance_impact_artifact,
            extract_effective_date_label,
            extract_qualifier_badge,
            infer_event_evidence_tier,
        )
        from pipeline.time_utils import SHANGHAI_TZ

        # 1. Duplicate 80% margin-cut events coalesce into 1 card merging sources & carry-over preserves >= 15 cards
        dup_margin_1 = {
            "event_id": "evt_margin_1",
            "title": "中国证监会批准下调融资保证金比例由100%降至80%并释放近4000亿资金",
            "fact_summary": "沪深北交易所通知自2026年11月30日起正式施行。",
            "category": "finance",
            "severity_tier": "S",
            "published_at": "2026-11-22T20:00:00+08:00",
            "sources": [{"source_name": "中国证监会", "url": "https://csrc.gov.cn/m1"}],
        }
        dup_margin_2 = {
            "event_id": "evt_margin_2",
            "title": "沪深北交易所降低两融保证金比例至80%稳市组合拳落地",
            "fact_summary": "自2026年11月30日起施行，另宣布2027年1月1日起免收费用。",
            "category": "finance",
            "published_at": "2026-11-22T20:10:00+08:00",
            "sources": [{"source_name": "财联社", "url": "https://cls.cn/m2"}],
        }
        nvda_ceo = {
            "event_id": "evt_nvda_ceo",
            "title": "报道称英伟达董事会已秘密启动下一任CEO外部遴选程序",
            "fact_summary": "尚属单一海外媒体报道，英伟达尚未发表正式声明。",
            "category": "tech",
            "published_at": "2026-11-22T21:00:00+08:00",
            "sources": [{"source_name": "IT之家", "url": "https://ithome.com/nvda-ceo"}],
        }
        tpu_shift = {
            "event_id": "evt_tpu_shift",
            "title": "郭明錤：谷歌削减博通TPU 8i约100万颗（占20%），但预计增加联发科TPU 8t出货",
            "fact_summary": "属于ASIC供应链份额调整。",
            "category": "tech",
            "published_at": "2026-11-22T21:30:00+08:00",
            "sources": [{"source_name": "华尔街见闻", "url": "https://wallstreetcn.com/tpu8t"}],
        }
        gemini4 = {
            "event_id": "evt_gem4",
            "title": "Google发布Gemini 4 Neon AI模型，与Claude Opus 5.5和GPT-6.2 Sol竞争",
            "fact_summary": "谷歌推出新一代旗舰多模态模型。",
            "category": "tech",
            "published_at": "2026-11-22T22:00:00+08:00",
            "sources": [{"source_name": "Google Blog", "url": "https://blog.google/gemini4"}],
        }
        cyber = {
            "event_id": "evt_cyber",
            "title": "OpenAI高管称AI已具备自主发现与利用复杂软件漏洞及自主攻击能力",
            "fact_summary": "网络安全防御团队需防范AI自主攻击风险。",
            "category": "tech",
            "published_at": "2026-11-22T22:10:00+08:00",
            "sources": [{"source_name": "Reuters", "url": "https://reuters.com/cyber"}],
        }
        prev_carry = [
            {
                "id": f"imp_prev_{i}",
                "event_id": f"prev_ev_{i}",
                "rule_id": f"prev_rule_{i}",
                "validation_status": "verified",
                "event_title": f"#{i} 宏观流动性与产业链季度跟踪指标 #{i}",
                "event_summary": "前期已验证事件摘要。",
                "category": "finance",
                "published_at": "2026-11-22T12:00:00+08:00",
                "source_name": "财联社",
                "tag": f"前期标签 #{i}",
                "polarity": "bullish",
                "intensity": 3,
                "one_liner": f"前期独立推演逻辑 #{i}",
                "bars": [{"market": "A股", "sector": "权重", "pct_low": 1.0, "pct_high": 2.5, "direction": "positive", "logic": "支撑"}],
                "if_then": [],
                "milestones": [],
            }
            for i in range(12)
        ]

        art = build_finance_impact_artifact(
            all_events=[dup_margin_1, dup_margin_2, nvda_ceo, tpu_shift, gemini4, cyber],
            batch_id="smart-test-v11",
            generated_at_iso="2026-11-22T23:00:00+08:00",
            quotes_doc={"quotes": {}, "indices": []},
            prev_doc={"event_impacts": prev_carry, "event_impact_map": {}},
        )
        impacts = art["event_impacts"]
        self.assertGreaterEqual(len(impacts), 15)
        margin_cards = [c for c in impacts if c["rule_id"] == "a_share_capital_market_reform"]
        self.assertEqual(len(margin_cards), 1)
        self.assertGreaterEqual(len(margin_cards[0]["sources"]), 2)
        self.assertEqual(margin_cards[0]["evidence_tier"], "official")
        self.assertIn("11月30日", margin_cards[0]["effective_date_label"] or "")

        ceo_card = next(c for c in impacts if c["event_id"] == "evt_nvda_ceo")
        self.assertEqual(ceo_card["rule_id"], "nvda_ceo_succession_transition")
        self.assertEqual(ceo_card["evidence_tier"], "single_source")
        self.assertNotIn("参议院", ceo_card["one_liner"])

        tpu_card = next(c for c in impacts if c["event_id"] == "evt_tpu_shift")
        self.assertIn("2454.TW", tpu_card["affected_tickers"])
        self.assertIn("联发科", tpu_card["one_liner"])

        gem_card = next(c for c in impacts if c["event_id"] == "evt_gem4")
        self.assertIn("GOOGL", gem_card["affected_tickers"])
        self.assertIn("Google", gem_card["tag"])

        self.assertFalse(any(c["event_id"] == "evt_cyber" for c in impacts))

        # 2. Qualifier & statutory effective date extractors
        self.assertIn("11月30日", extract_effective_date_label("自2026年11月30日起施行") or "")
        self.assertIn("2027年1月1日", extract_effective_date_label("2027年1月1日起减免费用") or "")
        self.assertIn("45%", extract_qualifier_badge("AI服务器厂商最高涨价45%") or "")
        self.assertIn("45%", extract_qualifier_badge("戴尔、HPE等AI服务器厂商交付前提价，涨幅最高达45%") or "")
        self.assertIsNone(_build_domain_scenario("日本首相高市早苗在APEC会议上被指行为不当并遭日本网友批评", "日本首相高市早苗在APEC会议上被指行为不当", {}))
        self.assertEqual(infer_event_evidence_tier({"sources": [{"source_name": "招商证券"}]}, "招商证券研报")[0], "research")

        anchor = datetime(2026, 11, 22, 18, 0, tzinfo=SHANGHAI_TZ)
        eff_parsed = parse_relative_schedule_datetime("22日通知：自2026年11月30日起正式施行两融新规", anchor)
        self.assertIsNotNone(eff_parsed)
        self.assertEqual(eff_parsed[0].strftime("%Y-%m-%d"), "2026-11-30")

        # 3. English GPT-6.2 comparison headline routes to OpenAI and is filtered by AI_NOISE_RE
        en_t = "GPT-6.2 Astra and Sol get to the point faster but score lower on transparency than Claude"
        self.assertEqual(_infer_company(en_t)[0], "openai")
        self.assertTrue(bool(AI_NOISE_RE.search(en_t)))
        self.assertIsNone(_build_domain_scenario(en_t, en_t, {}))

        mock_ai_doc = {
            "timeline": [
                {
                    "id": "bad_en",
                    "title": "GPT-6.2 表现评析",
                    "title_en": en_t,
                    "what_it_does": "对比基准评测",
                    "company_id": "anthropic",
                    "date": "2026-11-22T20:00:00+08:00",
                    "is_first_hand": True,
                }
            ],
            "companies": [
                {
                    "company_id": "anthropic",
                    "company_name": "Anthropic",
                    "items": [
                        {
                            "id": "bad_en",
                            "title": "GPT-6.2 表现评析",
                            "title_en": en_t,
                            "what_it_does": "对比基准评测",
                            "company_id": "anthropic",
                            "date": "2026-11-22T20:00:00+08:00",
                            "is_first_hand": True,
                        }
                    ],
                }
            ],
        }
        cleaned_ai, _ = merge_live_ai_items_into_doc(mock_ai_doc, [], "2026-11-22T22:00:00+08:00")
        self.assertFalse(any(it.get("id") == "bad_en" for it in cleaned_ai.get("timeline", [])))
        anth = next(c for c in cleaned_ai["companies"] if c["company_id"] == "anthropic")
        self.assertFalse(any("GPT-6.2" in str(it.get("title") or "") for it in anth.get("items", [])))

    def test_v12_deep_enrichment_zero_emojis_google_lineage_and_fee_cut_split(self) -> None:
        import re
        from datetime import datetime
        from pathlib import Path
        import tempfile
        from pipeline.ai_lineage_catalog import HISTORICAL_BASELINE_MILESTONES, LAB_V9_METADATA
        from pipeline.ai_radar_builder import AI_NOISE_RE, _DIM_LABELS
        from pipeline.calendar_catalog import _infer_event_type, _static_global_schedule
        from pipeline.connectors.github_releases import DEFAULT_WATCHED_REPOS
        from pipeline.deep_enrichment_engine import (
            _baseline_model_comparison_matrix,
            enrich_tools_with_ai_comparison,
            run_v12_deep_enrichment,
            strip_colored_emojis,
        )
        from pipeline.finance_impact_builder import _EVIDENCE_LABELS, _build_domain_scenario, extract_effective_date_label, extract_qualifier_badge
        from pipeline.v3_builder import _infer_domain_next_catalyst

        emoji_re = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]")

        # 1. Zero colored emojis in backend label dictionaries & helpers
        for k, (zh, en) in _DIM_LABELS.items():
            self.assertFalse(emoji_re.search(zh), f"_DIM_LABELS[{k}] has emoji: {zh}")
            self.assertFalse(emoji_re.search(en), f"_DIM_LABELS[{k}] has emoji: {en}")
        for k, v in _EVIDENCE_LABELS.items():
            self.assertFalse(emoji_re.search(v), f"_EVIDENCE_LABELS[{k}] has emoji: {v}")
        self.assertFalse(emoji_re.search(extract_effective_date_label("自2026年11月30日起正式施行") or ""))
        self.assertFalse(emoji_re.search(extract_qualifier_badge("最高提价45%") or ""))
        self.assertEqual(strip_colored_emojis("🚀 旗舰模型发布"), "旗舰模型发布")

        # 2. Google DeepMind Gemini 3.5 & 4 Argon lineage + milestones + podcast noise filtering
        google_gens = " ".join(n["generation"] for n in LAB_V9_METADATA["google"]["model_lineage"])
        self.assertIn("Gemini 3.5", google_gens)
        self.assertIn("Argon", google_gens)
        self.assertTrue(any(m.get("company_id") == "google" and "Argon" in m.get("title", "") for m in HISTORICAL_BASELINE_MILESTONES))
        self.assertTrue(bool(AI_NOISE_RE.search("沃尔特·艾萨克森专访节目谈AI未来")))

        # 3. GitHub curated high-star repos include Dify, n8n, ComfyUI, Open WebUI
        repo_names = {r["repo"] for r in DEFAULT_WATCHED_REPOS}
        for must_have in ("langgenius/dify", "n8n-io/n8n", "comfyanonymous/ComfyUI", "open-webui/open-webui"):
            self.assertIn(must_have, repo_names)

        # 4. Finance fee-cut split (46B) never clones 80% margin-cut copy
        fee_scen = _build_domain_scenario(
            "上交所发布2027年降费让利方案预计让利约46亿元",
            "免收上市初费和年费并减半收取债券交易经手费",
            {},
        )
        self.assertIsNotNone(fee_scen)
        self.assertEqual(fee_scen["rule_id"], "a_share_exchange_fee_cut")
        self.assertNotIn("4000", fee_scen["one_liner"])

        # 5. Calendar Guangzhou expos + ministry talent plan -> politics_macro
        static_sched = _static_global_schedule()
        self.assertTrue(any("广州" in str(ev.get("city") or "") and "广交会" in str(ev.get("title") or "") for ev in static_sched))
        self.assertEqual(_infer_event_type({"category": "finance"}, "两部门：实施数据领域高技能人才集群培养计划"), "politics_macro")

        # 6. Riemann theorem catalyst must NEVER become CVE patch boilerplate
        cat_txt = _infer_domain_next_catalyst(
            {"title": "Claude AI 宣称辅助证明黎曼猜想引发学术争议", "fact_summary": "形式化验证团队尚未公布完整 Lean 证明脚本"},
            None,
        )
        self.assertIn("GitHub", cat_txt)
        self.assertNotIn("安全响应中心", cat_txt)

        # 7. Deep enrichment engine deterministic offline coverage (matrix, tools, storylines, events QA, topics)
        matrix = _baseline_model_comparison_matrix()
        self.assertGreaterEqual(len(matrix), 12)
        with tempfile.TemporaryDirectory() as td:
            td_p = Path(td)
            tools = enrich_tools_with_ai_comparison(
                [{"tool_id": "tool_gh_langgenius_dify", "name": "Dify", "repo": "langgenius/dify", "summary": "LLM workflow builder"}],
                td_p,
                generated_at_iso="2026-11-23T10:00:00+08:00",
            )
            self.assertTrue(tools[0].get("pain_point"))
            self.assertTrue(tools[0].get("comparison_note"))
            storylines = {
                "st_test": {
                    "storyline_id": "st_test",
                    "title": "上交所发布2027年度降费让利方案",
                    "category": "finance",
                    "timeline": [{"batch_id": "b1", "event_id": "e1", "timestamp": "2026-11-23T09:00:00+08:00", "title": "上交所宣布降费让利"}],
                }
            }
            cat_docs = {
                "finance": {
                    "events": [
                        {
                            "event_id": "e1",
                            "title": "中国证监会下调融资保证金比例至80%",
                            "fact_summary": "释放增量资金并降低交易成本",
                            "severity_tier": "S",
                            "sources": [{"source_name": "证监会"}],
                        }
                    ]
                }
            }
            topics = [
                {
                    "topic_id": "tp_test",
                    "title": "中美元首深圳APEC峰会成果跟踪",
                    "primary_orgs": ["中方", "美方"],
                    "timeline": [{"title": "双方发布经贸对话纪要", "source_name": "新华社", "timestamp": "2026-11-23T08:00:00+08:00"}],
                }
            ]
            out = run_v12_deep_enrichment(
                td_p,
                generated_at_iso="2026-11-23T10:00:00+08:00",
                cat_docs=cat_docs,
                storylines=storylines,
                major_topics=topics,
                tech_tools=tools,
            )
            self.assertGreaterEqual(len(storylines["st_test"]["timeline"]), 3)
            self.assertTrue(storylines["st_test"].get("stance_comparison"))
            self.assertTrue(cat_docs["finance"]["events"][0].get("deep_qa"))
            self.assertTrue(topics[0].get("brief_overview"))
            self.assertTrue(topics[0].get("comparison_table"))
            self.assertGreaterEqual(out["storylines_multi_node"], 1)

    def test_v13_precision_corrections(self) -> None:
        from pipeline.ai_lineage_catalog import LAB_V9_METADATA
        from pipeline.ai_radar_builder import _auto_absorb_new_lineage_nodes
        from pipeline.build_briefing import calibrate_sitewide_severity_tiers, classify_event_severity
        from pipeline.calendar_catalog import _BREAKING_NOISE_RE, _infer_location
        from pipeline.connectors.china_realtime import _classify_wire_severity, refresh_live_wire_file
        from pipeline.finance_impact_builder import _build_domain_scenario, build_finance_impact_artifact

        # 1. All 23 AI labs have >=5 chronologically ascending lineage nodes with all 7 required fields
        self.assertEqual(len(LAB_V9_METADATA), 23)
        req_fields = ("generation", "release_date", "status", "specs", "pricing_or_license", "filter_keyword", "highlight")
        for cid, meta in LAB_V9_METADATA.items():
            nodes = meta.get("model_lineage") or []
            self.assertGreaterEqual(len(nodes), 5, f"{cid} lineage < 5")
            dates = [n["release_date"] for n in nodes]
            self.assertEqual(dates, sorted(dates), f"{cid} lineage not sorted ascending: {dates}")
            for n in nodes:
                for f in req_fields:
                    self.assertTrue(n.get(f), f"{cid} missing {f} in {n.get('generation')}")

        base_nodes = list(LAB_V9_METADATA["openai"]["model_lineage"])
        absorbed = _auto_absorb_new_lineage_nodes(
            base_nodes,
            [{"title": "OpenAI 正式发布 GPT-6 Turbo", "date": "2027-01-15T10:00:00+08:00", "milestone_dim": "flagship_release"}],
        )
        self.assertTrue(any("GPT-6" in n["generation"] for n in absorbed))
        self.assertEqual([n["release_date"] for n in absorbed], sorted(n["release_date"] for n in absorbed))

        # 2. Calendar spot-quote block & China ETF/exchange/AI location fix
        from pipeline.calendar_catalog import enrich_calendar_item_metadata
        from pipeline.time_utils import parse_iso_datetime
        ref_dt = parse_iso_datetime("2026-11-23T10:00:00+08:00")
        self.assertTrue(bool(_BREAKING_NOISE_RE.search("上海钢联发布电池级碳酸锂早盘中间价 12.4 万元/吨")))
        self.assertEqual(_infer_location({"category": "finance"}, "首批主动ETF在沪深交易所上市")[0], "china")
        self.assertEqual(_infer_location({"category": "finance"}, "沪深北交易所调整融资保证金比例至80%")[0], "china")
        ant_cal = enrich_calendar_item_metadata(
            {"title": "蚂蚁百灵开源医疗健康模型 LingSante-3.1-flash", "source_name": "华尔街见闻"},
            ref_dt,
        )
        self.assertEqual(ant_cal["region"], "china")

        # 3. Heavy-tier fake rejection, duplicate heavy dedupe & real-blockbuster recall
        ev_fake_hw = {"event_id": "f1", "category": "tech", "title": "华为云发布 DeepSeek-V4.1-Flash 模型API降价通知", "sources": [{"source_name": "IT之家"}], "latest_reported_at": "2026-11-23T09:00:00+08:00"}
        ev_fake_us = {"event_id": "f2", "category": "finance", "title": "美股科技股夜盘普遍走高，纳指期货涨0.6%", "sources": [{"source_name": "财联社"}], "latest_reported_at": "2026-11-23T09:00:00+08:00"}
        ev_fake_prop = {"event_id": "f3", "category": "global", "title": "有分析师提议设欧盟AI监管缓冲期", "sources": [{"source_name": "财联社"}], "latest_reported_at": "2026-11-23T09:00:00+08:00"}
        ev_fake_oai = {"event_id": "f4", "category": "tech", "title": "OpenAI科学家提议将行业AI限制与模型智能指标挂钩", "sources": [{"source_name": "Reuters"}], "latest_reported_at": "2026-11-23T09:00:00+08:00"}
        for fev in (ev_fake_hw, ev_fake_us, ev_fake_prop, ev_fake_oai):
            tier, _ = classify_event_severity(fev, now_dt=ref_dt)
            self.assertNotIn(tier, ("S", "A"), f"Fake heavy should not be S/A: {fev['title']} -> {tier}")

        ev_rie = {"event_id": "r1", "category": "tech", "title": "Lean / Mathlib 验证团队发布黎曼猜想形式化证明进展公告", "sources": [{"source_name": "Nature"}, {"source_name": "ArXiv"}], "score": 30.0, "latest_reported_at": "2026-11-23T09:30:00+08:00"}
        ev_apec = {"event_id": "r2", "category": "global", "title": "中美元首在深圳APEC会晤后发表四点联合宣言", "sources": [{"source_name": "新华社"}, {"source_name": "Reuters"}], "score": 30.0, "latest_reported_at": "2026-11-23T09:30:00+08:00"}
        ev_dup1 = {"event_id": "d1", "storyline_id": "st_cop", "category": "global", "title": "COP31气候大会因化石燃料分歧陷入僵局", "sources": [{"source_name": "Reuters"}, {"source_name": "BBC"}], "score": 38.0, "importance": "high", "severity_tier": "A", "latest_reported_at": "2026-11-23T09:20:00+08:00"}
        ev_dup2 = {"event_id": "d2", "storyline_id": "st_cop", "category": "global", "title": "COP31气候峰会仍未就化石燃料退坡达成协议", "sources": [{"source_name": "AFP"}, {"source_name": "FT"}], "score": 36.0, "importance": "high", "severity_tier": "A", "latest_reported_at": "2026-11-23T09:10:00+08:00"}
        cat_docs_test = {"tech": {"events": [ev_rie]}, "global": {"events": [ev_apec, ev_dup1, ev_dup2]}}
        calibrate_sitewide_severity_tiers(cat_docs_test, now_dt=ref_dt)
        self.assertIn(ev_rie.get("severity_tier"), ("S", "A"))
        self.assertIn(ev_apec.get("severity_tier"), ("S", "A"))
        heavy_cop = [e for e in (ev_dup1, ev_dup2) if e.get("severity_tier") in ("S", "A")]
        self.assertEqual(len(heavy_cop), 1, "Duplicate storyline should hold only 1 heavy slot")

        # 4. 7x24 wire heavy calibration (10-15 heavy items + noise filtered)
        self.assertNotIn(_classify_wire_severity("华为云发布DeepSeek降价通知", "", "ithome", "IT之家")[0], ("S", "A"))
        with tempfile.TemporaryDirectory() as tw:
            tw_p = Path(tw)
            items = []
            distinct_topics = [
                "美联储FOMC声明维持联邦基金利率目标区间不变并调整点阵图",
                "中国证监会宣布下调沪深北交易所融资保证金比例至80%",
                "OpenAI正式上线GPT-5.4并公布百万上下文API新定价",
                "SpaceX拟投入440亿美元采购大规模AI训练集群GPU",
                "Lean与Mathlib形式化团队发布黎曼猜想核心引理验证突破",
                "中美元首在深圳APEC会晤后发表四点双边经贸共识宣言",
                "欧盟委员会正式通过高关税调整生效令并公布豁免细则",
                "NVIDIA公布下一代Vera Rubin架构机架供电及NVLink基准",
                "Anthropic递交纳斯达克IPO招股书披露最新年化营收规模",
                "日本央行意外上调政策利率并收紧国债购买操作上限",
                "AI服务器因散热供电与芯片紧张启动最高45%整机提价",
                "韩国政府宣布筹建股市稳定基金平抑科技权重异常波动",
                "OPEC+部长级会议决定延长自愿减产协议并收紧配额核查",
                "BIS宣布扩大高端AI训练芯片出口管制及第三国转口清单",
                "DeepSeek开源新一代MoE推理模型并采用MIT商用许可",
                "沪深交易所迎来首批主动管理型ETF正式挂牌上市交易",
                "朱雀三号可回收火箭发动机完成二次点火地面试车验证",
                "国务院印发新一轮商业航天与数字经济跨境算力支持文件",
            ]
            for i, dt_title in enumerate(distinct_topics):
                items.append({
                    "id": f"w_h_{i}",
                    "title": dt_title,
                    "excerpt": "官方与权威渠道发布重磅进展",
                    "category": "finance",
                    "source_id": "cls",
                    "source_name": "财联社",
                    "url": f"https://cls.cn/{i}",
                    "published_at": f"2026-11-23T10:{i:02d}:00+08:00",
                    "raw_tag": "hot",
                    "tags": ["finance"],
                })
            for i in range(40):
                items.append({
                    "id": f"w_n_{i}",
                    "title": f"某地方公司例行召开第{i}次股东大会审议日常议案",
                    "excerpt": "日常公告",
                    "category": "finance",
                    "source_id": "stcn",
                    "source_name": "证券时报",
                    "url": f"https://stcn.com/{i}",
                    "published_at": f"2026-11-23T09:{i:02d}:00+08:00",
                    "raw_tag": "normal",
                    "tags": [],
                })
            from unittest.mock import patch
            with patch(
                "pipeline.connectors.china_realtime.fetch_china_realtime_wires",
                return_value={"fetched_at": "2026-11-23T10:30:00+08:00", "status": "ok", "connector_name": ["cls", "stcn"], "items": [], "errors": []},
            ):
                wire_doc = refresh_live_wire_file(tw_p, extra_items=items)
            hi_cnt = sum(1 for x in wire_doc["items"] if x.get("importance") == "high")
            self.assertGreaterEqual(hi_cnt, 10)
            self.assertLessEqual(hi_cnt, 15)

        # 5. Finance impact active ETF split + zero colored emojis
        etf_sc = _build_domain_scenario("首批主动ETF在沪深交易所正式挂牌上市", "主动管理型ETF正式破冰", {})
        self.assertIsNotNone(etf_sc)
        self.assertEqual(etf_sc["rule_id"], "a_share_active_etf_launch")
        self.assertNotIn("保证金", etf_sc["one_liner"])
        imp_v13 = build_finance_impact_artifact(
            all_events=[
                {
                    "event_id": "e_etf",
                    "title": "首批主动ETF在沪深交易所上市",
                    "category": "finance",
                    "importance": "high",
                    "fact_summary": "公募主动ETF正式挂牌交易。",
                    "sources": [{"source_name": "新华社", "url": "https://news.cn/etf"}],
                }
            ],
            batch_id="b_v13",
            generated_at_iso="2026-11-23T11:00:00+08:00",
        )
        import re
        raw_imp = json.dumps(imp_v13, ensure_ascii=False)
        self.assertFalse(bool(re.search(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", raw_imp)))

    def test_v14_deep_audit_fixes(self) -> None:
        from datetime import datetime
        from pathlib import Path
        import tempfile
        from unittest.mock import patch

        from pipeline.ai_radar_builder import _match_lab_signature, classify_ai_milestone_dim
        from pipeline.build_briefing import _S_TECH_NOISE_GUARD_RE, _infer_event_heavy_reason_tag
        from pipeline.calendar_catalog import (
            enrich_calendar_item_metadata,
            extract_breaking_calendar_items,
        )
        from pipeline.connectors.china_realtime import refresh_live_wire_file
        from pipeline.deep_enrichment_engine import _build_deterministic_event_qa, _clip_complete_sentence
        from pipeline.entities import match_entities_with_reasons
        from pipeline.time_utils import SHANGHAI_TZ
        from pipeline.v3_builder import (
            _ground_storyline_entities,
            _infer_domain_next_catalyst,
            balance_tech_tools,
        )

        # 1. Deep Q&A: complete-sentence clip & domain-specific templates (no bogus A-share on IPO/US stocks)
        clipped = _clip_complete_sentence(
            "美股科技股周三大幅反弹，芯片板块领涨。然而分析师警告估值偏高，建议短期谨慎追高。",
            26,
        )
        self.assertTrue(clipped.endswith("。"))
        self.assertNotIn("谨慎", clipped)
        qa_ipo = _build_deterministic_event_qa(
            {
                "title": "Anthropic IPO 募资超 810 亿美元刷新史上最大上市纪录",
                "fact_summary": "创纪录 IPO 定价引发美股科创估值再评估。",
                "entities": ["Anthropic"],
            },
            "tech",
        )
        self.assertGreaterEqual(len(qa_ipo), 2)
        for qrow in qa_ipo:
            self.assertNotIn("两融", qrow["answer"])
            self.assertNotIn("保证金", qrow["answer"])

        # 2. Wire 2h cross-source dedup merge, qualitative heavy_reason_tag, and noise blocking
        with tempfile.TemporaryDirectory() as tmp:
            tw_p = Path(tmp) / "live_wire.json"
            items = [
                {
                    "id": "w_powell_1",
                    "title": "美联储主席鲍威尔宣布维持基准利率不变并释放年内降息政策信号",
                    "excerpt": "官方政策决议确认利率维持区间不变。",
                    "category": "macro",
                    "source_id": "wallstreetcn",
                    "source_name": "华尔街见闻",
                    "url": "https://wallstreetcn.com/live/powell-1",
                    "published_at": "2026-11-23T10:15:00+08:00",
                    "raw_tag": "hot",
                    "tags": ["macro"],
                },
                {
                    "id": "w_powell_2",
                    "title": "美联储主席鲍威尔宣布维持基准利率不变，释放后续降息信号",
                    "excerpt": "新浪财经转引美联储最新利率声明。",
                    "category": "macro",
                    "source_id": "sina_finance",
                    "source_name": "新浪财经",
                    "url": "https://finance.sina.com.cn/powell-2",
                    "published_at": "2026-11-23T10:35:00+08:00",
                    "raw_tag": "hot",
                    "tags": ["macro"],
                },
                {
                    "id": "w_noise_1",
                    "title": "某短剧概念股早盘涨停且持续活跃探底回升",
                    "excerpt": "盘面题材股短线异动。",
                    "category": "finance",
                    "source_id": "cls",
                    "source_name": "财联社",
                    "url": "https://cls.cn/noise-1",
                    "published_at": "2026-11-23T10:40:00+08:00",
                    "raw_tag": "hot",
                    "tags": [],
                },
            ]
            with patch(
                "pipeline.connectors.china_realtime.fetch_china_realtime_wires",
                return_value={"fetched_at": "2026-11-23T10:50:00+08:00", "status": "ok", "connector_name": ["cls"], "items": [], "errors": []},
            ):
                wire_doc = refresh_live_wire_file(tw_p, extra_items=items)
            powell_hits = [x for x in wire_doc["items"] if "鲍威尔" in x.get("title", "")]
            self.assertEqual(len(powell_hits), 1)
            self.assertIn("2 源合并", powell_hits[0].get("source_name", ""))
            self.assertEqual(powell_hits[0].get("importance"), "high")
            self.assertTrue(bool(powell_hits[0].get("heavy_reason_tag")))
            noise_hits = [x for x in wire_doc["items"] if "短剧概念股" in x.get("title", "")]
            if noise_hits:
                self.assertNotEqual(noise_hits[0].get("importance"), "high")

        # 3. Event heavy reason tag & noise guard
        self.assertEqual(_infer_event_heavy_reason_tag("沪深北交易所发布主动 ETF 与两融保证金细则", {}), "监管新政")
        self.assertTrue(bool(_S_TECH_NOISE_GUARD_RE.search("短剧概念股早盘涨停持续活跃")))

        # 4. Tech tools balance preserves all HF open weights and filters star-farmed repos
        pool = [{"tool_id": f"tool_sdk_{i}", "name": f"agent-sdk-{i}", "repo": f"org/sdk-{i}"} for i in range(22)]
        pool += [{"tool_id": f"tool_hf_{i}", "name": f"open-weight-{i}", "source_name": "Hugging Face", "tool_type": "开源权重"} for i in range(12)]
        pool.append({"tool_id": "tool_spam_1", "name": "morluto/rea", "repo": "morluto/rea"})
        pool.append({"tool_id": "tool_spam_2", "name": "openclaw", "repo": "openclaw/openclaw"})
        balanced = balance_tech_tools(pool)
        self.assertEqual(sum(1 for t in balanced if str(t.get("tool_id", "")).startswith("tool_hf_")), 12)
        self.assertFalse(any("morluto" in str(t.get("name", "")).lower() or "openclaw" in str(t.get("name", "")).lower() for t in balanced))

        # 5. Calendar future-only & location attribution
        gen_dt = datetime(2026, 11, 23, 12, 0, tzinfo=SHANGHAI_TZ)
        cal_items = extract_breaking_calendar_items(
            cat_docs={
                "finance": {
                    "events": [
                        {"title": "创业板算力ETF今日午后探底回升", "fact_summary": "盘面拉升", "independent_publisher_count": 2, "latest_reported_at": "2026-11-23T11:30:00+08:00"},
                        {"title": "18只主动ETF完成建仓", "fact_summary": "已完成建仓", "independent_publisher_count": 2, "latest_reported_at": "2026-11-23T11:20:00+08:00"},
                        {"title": "蚂蚁阿福健康大模型今日正式上线", "fact_summary": "已上线", "independent_publisher_count": 2, "latest_reported_at": "2026-11-23T11:10:00+08:00"},
                        {"title": "智元精灵G2宣布今日正式进入产线", "fact_summary": "进入产线", "independent_publisher_count": 2, "latest_reported_at": "2026-11-23T11:05:00+08:00"},
                        {"title": "国务院新闻办将于 2026年11月26日 举行专题政策发布会", "fact_summary": "定于下周召开", "independent_publisher_count": 3, "latest_reported_at": "2026-11-23T11:40:00+08:00"},
                    ]
                }
            },
            live_wire_items=[],
            ai_progress_items=[],
            generated_dt=gen_dt,
            existing_calendar_items=[],
        )
        cal_titles = " ".join(str(c.get("title", "")) for c in cal_items)
        for bad_kw in ("探底回升", "完成建仓", "蚂蚁阿福", "进入产线"):
            self.assertNotIn(bad_kw, cal_titles)
        self.assertIn("专题政策发布会", cal_titles)

        loc_meta = enrich_calendar_item_metadata(
            {
                "title": "我国科研团队将在学术大会发布 ZHU·GE 大模型研究成果",
                "title_en": "Chinese researchers to unveil ZHU-GE model findings",
                "source_name": "华尔街见闻",
                "scheduled_at": "2026-11-26T09:00:00+08:00",
            },
            gen_dt,
        )
        self.assertEqual(loc_meta["region"], "china")
        self.assertNotEqual(loc_meta["city"], "纽约")

        # 6. AI Lab Perplexity disambiguation & closed-lab open_source_eco prevention
        self.assertNotEqual(
            _match_lab_signature("openai 首席科学家称困惑度 (perplexity) 指标仍被低估", ("xai", "grok")),
            "perplexity",
        )
        dim_id, _, _ = classify_ai_milestone_dim(
            "OpenAI 代理曾多次攻击 Hugging Face 仓库并触及 limit",
            "安全团队披露测试细节",
            is_open_source=False,
            company_id="openai",
        )
        self.assertNotEqual(dim_id, "open_source_eco")

        # 7. Entity diplomacy precision & storyline domain catalysts / entity grounding
        bessent_hits = match_entities_with_reasons("美财长贝森特警告关税通胀风险，美债收益率飙升")
        self.assertNotIn("ent_us_china_diplomacy", [m.get("entity_id") for m in bessent_hits])

        cat_med = _infer_domain_next_catalyst(
            {"title": "蚂蚁医疗健康大模型发布升级临床辅助系统", "fact_summary": "Focused on hospital total QA capability."},
            None,
        )
        self.assertNotIn("车企", cat_med)
        cat_gold = _infer_domain_next_catalyst(
            {"title": "全球黄金资产面临剧烈抛压，菜百黄金单日跌幅超11%", "fact_summary": "金价急跌"},
            {"entity_id": "ent_oil_energy", "validation_milestones": ["OPEC+ 产量配额会议"]},
        )
        self.assertNotIn("OPEC+", cat_gold)
        self.assertIn("金", cat_gold)

        grounded_ents, _ = _ground_storyline_entities(
            "人形机器人板块大涨，产业链迎估值重构",
            "国产减速器与丝杠订单增长",
            ["人形机器人", "GPT-6.2 Astra"],
            [],
            {},
        )
        self.assertNotIn("GPT-6.2 Astra", grounded_ents)

    def test_v15_edge_case_cleanup(self) -> None:
        from datetime import datetime
        import os
        from pathlib import Path
        import sys
        import tempfile
        from types import SimpleNamespace
        from unittest import mock

        from pipeline.build_briefing import _infer_event_heavy_reason_tag
        from pipeline.calendar_catalog import extract_breaking_calendar_items
        from pipeline.connectors.china_realtime import refresh_live_wire_file
        from pipeline.deep_enrichment_engine import _build_deterministic_event_qa
        from pipeline.finance_impact_builder import _build_domain_scenario
        from pipeline.gemini_pool import call_gemini_raw
        from pipeline.manifest import load_json_if_exists
        from pipeline.time_utils import SHANGHAI_TZ

        # 1. Korea stabilization fund must NOT hit A-share STAR/ChiNext rule
        kr_sc = _build_domain_scenario(
            "韩国股市融资余额大幅下降，政府将审查启动股市平准基金以稳定市场情绪",
            "韩国政府拟动用股市稳定基金缓解杠杆踩踏",
            {},
        )
        self.assertIsNotNone(kr_sc)
        self.assertEqual(kr_sc["rule_id"], "korea_market_stabilization")
        self.assertEqual(kr_sc["tag"], "亚太/韩国股市去杠杆与政府平准基金稳市干预")
        self.assertNotIn("双创", kr_sc["tag"])

        # 2. Gold/commercial bank risk notice -> 大宗与市场剧震, and zero IPO boilerplate in gold/Fed Q&A
        gold_tag = _infer_event_heavy_reason_tag(
            "国际金价剧烈杀跌后反弹，国内银行紧急提示贵金属投资风险",
            {"fact_summary": "瑞银认为明年美联储降息预期有望支撑金价。"},
        )
        self.assertEqual(gold_tag, "大宗与市场剧震")
        qa_gold = _build_deterministic_event_qa(
            {
                "title": "国际金价剧烈杀跌后反弹，国内银行紧急提示贵金属投资风险",
                "fact_summary": "COMEX 黄金大幅波动触发多家银行积存金风险警示。",
                "entities": ["黄金"],
            },
            "finance",
        )
        qa_fed = _build_deterministic_event_qa(
            {
                "title": "美国财政部长贝森特警告美联储过度紧缩风险",
                "fact_summary": "利率预期摇摆加剧美债长端波动。",
                "entities": ["美联储 FOMC 与全球流动性"],
            },
            "finance",
        )
        for qrow in qa_gold + qa_fed:
            blob = f"{qrow.get('answer', '')} {qrow.get('historical_parallel', '')}"
            self.assertNotIn("IPO", blob)
            self.assertNotIn("独角兽", blob)

        # 3. Breaking calendar rejects analyst commentary & already-happened announcements, keeps future-dated policies
        gen_dt = datetime(2026, 11, 23, 13, 0, tzinfo=SHANGHAI_TZ)
        cal_items = extract_breaking_calendar_items(
            cat_docs={
                "finance": {
                    "events": [
                        {
                            "title": "广发证券陈福：多举措协同发力 资本市场内在稳定性有望提升",
                            "fact_summary": "分析师认为自11月25日起流动性将继续改善",
                            "independent_publisher_count": 2,
                            "latest_reported_at": "2026-11-23T12:00:00+08:00",
                        },
                        {
                            "title": "蚂蚁百灵开源医疗健康模型并上线实时视频功能",
                            "fact_summary": "将于下周拓展海外服务",
                            "independent_publisher_count": 2,
                            "latest_reported_at": "2026-11-23T12:05:00+08:00",
                        },
                        {
                            "title": "中国四部门印发一老一小服务发展方案",
                            "fact_summary": "将于明年分阶段评估",
                            "independent_publisher_count": 2,
                            "latest_reported_at": "2026-11-23T12:10:00+08:00",
                        },
                        {
                            "title": "地球系统智能科研平台推出并开源基础代码",
                            "fact_summary": "预计下月开放社区体验",
                            "independent_publisher_count": 2,
                            "latest_reported_at": "2026-11-23T12:15:00+08:00",
                        },
                        {
                            "title": "国务院新闻办将于 2026年11月26日 举行专题政策发布会",
                            "fact_summary": "发布会定于 11月26日 召开",
                            "independent_publisher_count": 3,
                            "latest_reported_at": "2026-11-23T12:20:00+08:00",
                        },
                    ]
                }
            },
            live_wire_items=[],
            ai_progress_items=[],
            generated_dt=gen_dt,
            existing_calendar_items=[],
        )
        cal_titles = " ".join(str(c.get("title", "")) for c in cal_items)
        for bad in ("广发证券", "蚂蚁百灵", "一老一小", "地球系统"):
            self.assertNotIn(bad, cal_titles)
        self.assertIn("专题政策发布会", cal_titles)

        # 4. Wire heavy tier blocks roundups/alliance成立 and deduplicates Korea + active ETF clusters to 1 each
        with tempfile.TemporaryDirectory() as tmp:
            tw_p = Path(tmp) / "live_wire.json"
            wire_items = [
                {
                    "id": "w_roundup",
                    "title": "早间要闻汇总",
                    "excerpt": "证监会与美联储动态一览",
                    "category": "finance",
                    "source_id": "wallstreetcn",
                    "source_name": "华尔街见闻",
                    "url": "https://wallstreetcn.com/roundup",
                    "published_at": "2026-11-23T08:00:00+08:00",
                },
                {
                    "id": "w_alliance",
                    "title": "证券业人工智能应用发展联盟正式成立",
                    "excerpt": "行业联盟聚焦证券 AI 规范与证监会指导",
                    "category": "finance",
                    "source_id": "wallstreetcn",
                    "source_name": "华尔街见闻",
                    "url": "https://wallstreetcn.com/alliance",
                    "published_at": "2026-11-23T09:00:00+08:00",
                },
                {
                    "id": "w_kr1",
                    "title": "韩国财长称随着推出股市稳定基金措施，投资者信心有望改善",
                    "excerpt": "韩国政府表态稳市",
                    "category": "finance",
                    "source_id": "cls",
                    "source_name": "财联社",
                    "url": "https://cls.cn/kr1",
                    "published_at": "2026-11-23T10:00:00+08:00",
                },
                {
                    "id": "w_kr2",
                    "title": "韩国财政部预计最新稳市举措与平准机制将提振市场情绪",
                    "excerpt": "后续稳市工具箱准备中",
                    "category": "finance",
                    "source_id": "wallstreetcn",
                    "source_name": "华尔街见闻",
                    "url": "https://wallstreetcn.com/kr2",
                    "published_at": "2026-11-23T12:30:00+08:00",
                },
                {
                    "id": "w_etf1",
                    "title": "深交所首批主动ETF平稳上市，引入增量资金",
                    "excerpt": "主动ETF挂牌",
                    "category": "finance",
                    "source_id": "sina_finance",
                    "source_name": "新浪财经",
                    "url": "https://finance.sina.com.cn/etf1",
                    "published_at": "2026-11-23T09:30:00+08:00",
                },
                {
                    "id": "w_etf2",
                    "title": "18只主动ETF申赎清单发布，茅台宁德位居前二",
                    "excerpt": "申赎清单披露",
                    "category": "finance",
                    "source_id": "cls",
                    "source_name": "财联社",
                    "url": "https://cls.cn/etf2",
                    "published_at": "2026-11-23T12:45:00+08:00",
                },
            ]
            with mock.patch(
                "pipeline.connectors.china_realtime.fetch_china_realtime_wires",
                return_value={"fetched_at": "2026-11-23T13:00:00+08:00", "status": "ok", "connector_name": ["cls"], "items": [], "errors": []},
            ):
                wire_doc = refresh_live_wire_file(tw_p, extra_items=wire_items)
            hi_items = [x for x in wire_doc["items"] if x.get("importance") == "high"]
            hi_titles = [x.get("title", "") for x in hi_items]
            self.assertFalse(any("早间要闻汇总" in t or "发展联盟" in t for t in hi_titles))
            self.assertEqual(sum(1 for t in hi_titles if "韩国" in t), 1)
            self.assertEqual(sum(1 for t in hi_titles if "主动ETF" in t), 1)

        # 5. Gemini 504 DEADLINE_EXCEEDED fast-fallback without exhausting key
        calls_v15: list[tuple[str, str]] = []

        class _TimeoutClient:
            def __init__(self, api_key, **_kw):
                self.api_key = api_key
                self.models = self

            def generate_content(self, model, contents, config=None):
                del contents, config
                calls_v15.append((self.api_key, model))
                if model == "gemini-4-hydrogen":
                    raise RuntimeError("504 DEADLINE_EXCEEDED: The request timed out.")
                return SimpleNamespace(text='{"ok": true}')

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with mock.patch.dict(os.environ, {"KEY_1": "sec-a", "KEY_2": "sec-b"}, clear=True):
                fake_types = SimpleNamespace(
                    GenerateContentConfig=lambda **kw: kw,
                    HttpOptions=lambda **kw: kw,
                )
                fake_genai = SimpleNamespace(Client=_TimeoutClient, types=fake_types)
                fake_google = SimpleNamespace(genai=fake_genai)
                with mock.patch.dict(sys.modules, {"google": fake_google, "google.genai": fake_genai, "google.genai.types": fake_types}):
                    res_504 = call_gemini_raw(
                        scope="default",
                        prompt="tech",
                        models=("gemini-4-hydrogen", "gemini-2.5-flash"),
                        base_dir=root,
                    )
            self.assertTrue(res_504.ok)
            self.assertEqual(res_504.model_used, "gemini-2.5-flash")
            # Immediate model-level switch after 1st 504 timeout on gemini-4-hydrogen
            self.assertEqual(sum(1 for _k, m in calls_v15 if m == "gemini-4-hydrogen"), 1)
            ledger = load_json_if_exists(root / "data/gemini_quota_state.json", default={})
            for rec in (ledger.get("keys") or {}).values():
                self.assertIsNone(rec.get("exhausted_until"))

    def test_v16_gold_dead_corners_and_storyline_zh_fallback(self):
        """Verify V16 fixes: gold wire tag prioritize commodity, gold Q&A COMEX/TIPS & cache invalidation, and Chinese storyline summary backfill."""
        from pipeline.connectors.china_realtime import _infer_wire_heavy_reason_tag
        from pipeline.deep_enrichment_engine import _build_deterministic_event_qa, _is_bad_cached_event_qa
        from pipeline.v3_builder import build_v3_artifacts

        # 1. Wire heavy tag for gold rebound mentioning Fed in excerpt must NOT get '元首/央行表态'
        wire_tag = _infer_wire_heavy_reason_tag(
            "逢低买盘入场推动黄金反弹 上周曾创3月以来最差单周表现",
            "黄金价格从八个月来最大单周跌幅中反弹，逢低买盘入场，同时市场降低了对美联储12月加息的押注。",
        )
        self.assertEqual(wire_tag, "大宗与市场剧震")

        # 2. Gold event mentioning 'A股黄金股逆市高开' must get COMEX/TIPS Q&A and invalidate stale A-share policy cache
        gold_ev = {
            "event_id": "evt_gold_rebound",
            "title": "逢低买盘入场推动现货黄金回升突破3630美元 A股黄金股逆市高开",
            "fact_summary": "逢低买盘推动现货黄金一度突破3630美元/盎司。",
            "entities": ["黄金"],
        }
        qa_gold = _build_deterministic_event_qa(gold_ev, "finance")
        self.assertTrue(any("COMEX" in q.get("historical_parallel", "") and "TIPS" in q.get("historical_parallel", "") for q in qa_gold))
        for q in qa_gold:
            blob = f"{q.get('question', '')} {q.get('answer', '')} {q.get('historical_parallel', '')}"
            self.assertNotIn("同类境内资本市场政策", blob)
            self.assertNotIn("科创 IPO", blob)
            self.assertNotIn("A 股行业有何实质影响", blob)
        self.assertTrue(
            _is_bad_cached_event_qa(
                gold_ev["title"],
                "finance",
                [{"question": "这项政策对普通投资者与 A 股行业有何实质影响？", "answer": "测试。", "historical_parallel": "参考 2023 年以来同类境内资本市场政策窗口。"}],
            )
        )

        # 3. Storyline with English fact_diff/src0 + Chinese timeline[0].fact_summary backfills Chinese into fact_diff
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "data").mkdir(parents=True, exist_ok=True)
            prev_storylines = {
                "storylines": {
                    "st_libya_test": {
                        "storyline_id": "st_libya_test",
                        "title": "俄罗斯军舰在利比亚港口爆炸后沉没",
                        "category": "global",
                        "entities": [],
                        "entity_ids": [],
                        "current_stage": "新增/修订实质事实",
                        "evidence_status": "corroborated",
                        "evidence_label": "多源证实",
                        "first_reported_at": "2026-11-23T10:00:00+08:00",
                        "latest_reported_at": "2026-11-23T12:00:00+08:00",
                        "fact_diff": {
                            "change_type": "initial",
                            "change_type_label": "初次收录",
                            "new_facts": [],
                            "unchanged_background": [],
                            "corrections": [],
                        },
                        "timeline": [
                            {
                                "batch_id": "smart-prev",
                                "timestamp": "2026-11-23T12:00:00+08:00",
                                "title": "俄罗斯军舰在利比亚港口爆炸后沉没",
                                "fact_summary": "一艘俄罗斯军舰在利比亚班加西港口爆炸后沉没，据称是遭到疑似乌克兰无人机袭击。",
                            }
                        ],
                        "sources": [
                            {
                                "source_name": "Reuters",
                                "title": "Explosion on Russian ship at Libya port caused by suspected drone attack, officials say",
                                "url": "https://www.reuters.com/world/libya-ship-test",
                            }
                        ],
                    }
                }
            }
            atomic_write_json(root / "data/storylines_index.json", prev_storylines)
            build_v3_artifacts(
                root,
                batch_id="smart-20261123-140000",
                generated_at_iso="2026-11-23T14:00:00+08:00",
                cat_docs={
                    "finance": {"events": []},
                    "global": {"events": []},
                    "tech": {"events": []},
                    "general": {"events": []},
                },
                prev_cat_events={},
                prev_batch_id="smart-prev",
                connectors_payload={},
            )
            from pipeline.manifest import load_json_if_exists
            st_doc = load_json_if_exists(root / "data/storylines_index.json", default={})
            st_libya = (st_doc.get("storylines") or {}).get("st_libya_test")
            self.assertIsNotNone(st_libya)
            fd = st_libya.get("fact_diff") or {}
            bg = fd.get("unchanged_background") or []
            self.assertTrue(bg and any("利比亚" in x for x in bg))

    def test_v17_heavy_classifier_alignment_and_brand_clean(self) -> None:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from pipeline.heavy_classifier import (
            GEO_MILITARY_HEAVY_RE,
            HEAVY_NOISE_EXCLUDE_RE,
            infer_heavy_reason_tag,
            sync_today_heavy_into_live_wire,
        )
        from pipeline.deep_enrichment_engine import _build_deterministic_event_qa
        from pipeline.connectors.github_releases import fetch_github_releases
        from pipeline.connectors.gemini_search_hunter import fetch_gemini_search_breaking_news

        # 1. Brokerage buy rating excluded from Heavy; warship sinking promoted to 地缘与军事突发; gold -> 大宗与市场剧震
        self.assertIsNotNone(HEAVY_NOISE_EXCLUDE_RE.search("杰富瑞首次覆盖中微公司给予买入评级，目标价300元"))
        self.assertIsNotNone(GEO_MILITARY_HEAVY_RE.search("俄罗斯军舰在利比亚港口爆炸后沉没"))
        self.assertEqual(
            infer_heavy_reason_tag(
                "国际金价剧烈杀跌后反弹，瑞银预测明年降息预期回归将支撑金价",
                "央行购金与降息预期交织推动贵金属反弹",
            ),
            "大宗与市场剧震",
        )

        # 2. sync_today_heavy_into_live_wire unifies Today S/A into 8-12 deduped Live Wire Heavy items & cleans breaking_highlights
        now_dt = datetime(2026, 11, 23, 14, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        sample_today_events = [
            {
                "event_id": f"evt_t_{i}",
                "title": t,
                "fact_summary": t,
                "category": cat,
                "severity_tier": "S" if i < 2 else "A",
                "importance": "high",
                "latest_reported_at": "2026-11-23T12:30:00+08:00",
                "sources": [{"source_name": src, "url": f"https://example.com/{i}", "is_reprint_copy": False}],
            }
            for i, (t, cat, src) in enumerate([
                ("沪深北交易所将融资保证金比例由100%下调至80%", "finance", "中国证监会"),
                ("俄罗斯军舰在利比亚港口爆炸后沉没，疑遭无人机袭击", "global", "Reuters"),
                ("国际金价剧烈杀跌后反弹，瑞银上调明年目标位", "finance", "Financial Times"),
                ("欧盟与印尼正式签署全面自由贸易协定", "global", "Reuters"),
                ("韩国财长称将审查启动股市平准基金以稳定市场情绪", "finance", "Bloomberg"),
                ("OpenAI 宣布新一轮企业级智能体平台发布", "tech", "OpenAI Blog"),
                ("美联储纪要显示年内通胀回落路径仍具韧性", "finance", "Federal Reserve"),
                ("SpaceX 星舰完成高轨在轨加注验证", "tech", "Reuters"),
                ("国务院常务会议部署制造业设备更新专项政策", "general", "新华社"),
            ])
        ]
        wire_doc = {
            "items": [
                {
                    "id": "w_noise_1",
                    "title": "杰富瑞首次覆盖某某股份给予买入评级",
                    "severity_tier": "A",
                    "importance": "high",
                    "heavy_reason_tag": "巨头重大变动",
                    "source_name": "财联社",
                    "published_at": "2026-11-23T13:50:00+08:00",
                },
                {
                    "id": "w_libya_1",
                    "title": "俄罗斯军舰在利比亚港口爆炸后沉没",
                    "severity_tier": "B",
                    "importance": "normal",
                    "source_name": "Reuters",
                    "published_at": "2026-11-23T13:10:00+08:00",
                },
            ],
            "breaking_highlights": [
                {"id": "bh1", "title": "杰富瑞首次覆盖某某股份给予买入评级", "breaking_label": "巨头重大变动"},
                {"id": "bh2", "title": "国际金价剧烈杀跌后反弹，瑞银称逢低买盘入场", "breaking_label": "元首/央行表态"},
                {"id": "bh3", "title": "俄罗斯军舰在利比亚港口爆炸后沉没", "breaking_label": "巨头重大变动"},
            ],
            "total": 2,
        }
        synced = sync_today_heavy_into_live_wire(
            {"finance": {"events": sample_today_events}, "global": {"events": []}, "tech": {"events": []}, "general": {"events": []}},
            wire_doc,
            now_dt,
        )
        heavy_items = [it for it in synced["items"] if it.get("importance") == "high"]
        self.assertGreaterEqual(len(heavy_items), 8)
        self.assertLessEqual(len(heavy_items), 12)
        self.assertFalse(any("买入评级" in it["title"] for it in heavy_items))
        libya_w = next(it for it in synced["items"] if it["id"] == "w_libya_1")
        self.assertEqual(libya_w["importance"], "high")
        self.assertEqual(libya_w["heavy_reason_tag"], "地缘与军事突发")
        gold_w = next(it for it in heavy_items if "金价" in it["title"])
        self.assertEqual(gold_w["heavy_reason_tag"], "大宗与市场剧震")
        bhs = synced["breaking_highlights"]
        self.assertEqual(len(bhs), 2)
        self.assertEqual(bhs[0]["breaking_label"], "大宗与市场剧震")
        self.assertEqual(bhs[1]["breaking_label"], "地缘与军事突发")

        # 3. Gold Q&A question copy matches general investors & global markets
        qa_gold = _build_deterministic_event_qa({"title": "国际金价杀跌后反弹", "fact_summary": "COMEX黄金走高"}, "finance")
        self.assertEqual(qa_gold[0]["question"], "这件事对普通投资者与全球市场有何影响？")

        # 4. De-exposed connector notes & v3 disclosure
        from types import SimpleNamespace
        from unittest.mock import patch

        stub_304 = SimpleNamespace(status="not_modified_304", ok=True, json_data=None, error=None)
        with (
            patch("pipeline.connectors.github_releases.polite_get", return_value=stub_304),
            patch("pipeline.connectors.gemini_search_hunter._collect_all_keys", return_value=[]),
        ):
            c_rel = fetch_github_releases(None, watched_repos=[{"repo": "langchain-ai/langgraph", "name": "LangGraph"}])
            c_hunt = fetch_gemini_search_breaking_news()
        for forbidden in ("GitHub Actions", "密钥池", "免费 API", "节流期", "ETag", "Gemini"):
            self.assertNotIn(forbidden, c_rel.get("tos_note", ""))
            self.assertNotIn(forbidden, f"{c_hunt.get('connector_name', '')} {c_hunt.get('tos_note', '')}")

        v3_text = Path("pipeline/v3_builder.py").read_text(encoding="utf-8")
        self.assertNotIn("诚实边界说明：当前静态版本暂未接入付费", v3_text)

        # 5. refresh_live_wire_file loads on-disk category events and maintains 8-12 Today<->Wire aligned Heavy items
        from pipeline.connectors.china_realtime import refresh_live_wire_file
        with tempfile.TemporaryDirectory() as td2:
            wroot = Path(td2)
            (wroot / "data").mkdir(parents=True, exist_ok=True)
            (wroot / "analysis_finance.json").write_text(
                json.dumps({"events": sample_today_events}, ensure_ascii=False),
                encoding="utf-8",
            )
            stub_wires = {
                "connector_name": "财联社 / 华尔街见闻",
                "status": "ok",
                "fetched_at": "2026-11-23T14:00:00+08:00",
                "items": [
                    {
                        "id": "w_live_noise",
                        "title": "杰富瑞首次覆盖某股给予买入评级",
                        "excerpt": "券商研报点评",
                        "source_name": "财联社",
                        "published_at": "2026-11-23T13:55:00+08:00",
                    }
                ],
            }
            with patch("pipeline.connectors.china_realtime.fetch_china_realtime_wires", return_value=stub_wires):
                refreshed = refresh_live_wire_file(wroot)
            ref_heavy = [it for it in refreshed["items"] if it.get("importance") == "high"]
            self.assertGreaterEqual(len(ref_heavy), 8)
            self.assertLessEqual(len(ref_heavy), 12)
            self.assertFalse(any("买入评级" in it["title"] for it in ref_heavy))

    def test_v18_wire_hygiene_clustering_lineage_and_dynamic_predictions(self) -> None:
        import json
        import tempfile
        from datetime import datetime
        from pathlib import Path
        from unittest.mock import patch

        from pipeline.ai_radar_builder import _auto_absorb_new_lineage_nodes
        from pipeline.connectors.china_realtime import (
            _dedup_repeated_sentences,
            _is_empty_clock_wire,
            refresh_live_wire_file,
        )
        from pipeline.time_utils import SHANGHAI_TZ
        from pipeline.v3_builder import build_dynamic_live_predictions

        # 1. Empty 6-char clock wires dropped; short factual Fed headlines kept
        self.assertTrue(_is_empty_clock_wire("《商品期货收盘》"))
        self.assertTrue(_is_empty_clock_wire("《股指期货午盘收盘》"))
        self.assertTrue(_is_empty_clock_wire("《台湾证券交易所：投资者应保持理性。》"))
        self.assertFalse(_is_empty_clock_wire("美联储理事强调通胀粘性仍高"))
        self.assertFalse(_is_empty_clock_wire("沪指收盘上涨1.2%报3380点"))

        # 2. Adjacent repeated sentence dedup
        dup_txt = "印尼央行行长称将捍卫印尼盾汇率稳定。印尼央行行长称将捍卫印尼盾汇率稳定。"
        self.assertEqual(_dedup_repeated_sentences(dup_txt), "印尼央行行长称将捍卫印尼盾汇率稳定。")

        # 3. 3h clustering collapses Taiwan margin 5-peat & A-share close 5-peat; drops SK divorce gossip; recalls KOSPI/HBM
        stub_burst = {
            "connector_name": "华尔街见闻 / 财联社 / IT之家",
            "status": "ok",
            "fetched_at": "2026-11-23T15:05:00+08:00",
            "items": [
                {"item_id": "tw1", "title": "台湾交易所上调维持保证金比率至166%", "source_name": "新浪财经 7×24", "published_at": "2026-11-23T14:57:00+08:00"},
                {"item_id": "tw2", "title": "台湾证交所拟调整融资维持担保品比率", "source_name": "华尔街见闻 7×24", "published_at": "2026-11-23T14:58:00+08:00"},
                {"item_id": "tw3", "title": "台交所澄清维持保证金率政策未作变更，保持现行130%不变", "excerpt": "台交所官方发布新闻稿明确融资维持率规则。", "source_name": "财联社 7×24 电报", "published_at": "2026-11-23T14:59:00+08:00"},
                {"item_id": "tw4", "title": "台湾证交所回应融资保证金规则", "source_name": "新浪财经 7×24", "published_at": "2026-11-23T14:59:30+08:00"},
                {"item_id": "tw5", "title": "台股融资担保维持比率调整引发讨论", "source_name": "华尔街见闻 A股快讯", "published_at": "2026-11-23T14:59:45+08:00"},
                {"item_id": "ac1", "title": "《商品期货收盘》", "source_name": "新浪财经", "published_at": "2026-11-23T15:00:00+08:00"},
                {"item_id": "ac2", "title": "A股收盘沪指跌0.6%", "source_name": "新浪财经", "published_at": "2026-11-23T15:00:10+08:00"},
                {"item_id": "ac3", "title": "A股收评：三大指数集体小幅收跌，两市全天成交1.92万亿元", "excerpt": "沪指跌0.62%，创业板指跌0.85%，半导体芯片与券商逆势活跃。", "source_name": "财联社 7×24 电报", "published_at": "2026-11-23T15:01:00+08:00"},
                {"item_id": "sk1", "title": "SK集团会长崔泰源百亿离婚案财产分割二审维持原判", "source_name": "新浪财经", "published_at": "2026-11-23T14:40:00+08:00"},
                {"item_id": "kp1", "title": "韩国KOSPI指数午后大跌3.32%，权重存储芯片股集体下挫", "source_name": "华尔街见闻 7×24", "published_at": "2026-11-23T14:35:00+08:00"},
                {"item_id": "mu1", "title": "美光科技宣布明年320亿美元HBM高带宽内存产能已提前全部售罄", "source_name": "TechCrunch AI & Tech", "published_at": "2026-11-23T14:30:00+08:00"},
            ],
        }
        with tempfile.TemporaryDirectory() as td3:
            wroot3 = Path(td3)
            (wroot3 / "data").mkdir(parents=True, exist_ok=True)
            with patch("pipeline.connectors.china_realtime.fetch_china_realtime_wires", return_value=stub_burst):
                res3 = refresh_live_wire_file(wroot3)
            titles3 = [it["title"] for it in res3["items"]]
            self.assertFalse(any("商品期货收盘" in t for t in titles3))
            tw_kept = [it for it in res3["items"] if "台" in it["title"] and ("保证金" in it["title"] or "维持" in it["title"])]
            self.assertEqual(len(tw_kept), 1)
            self.assertIn("源合并", tw_kept[0]["source_name"])
            ac_kept = [it for it in res3["items"] if "A股" in it["title"] and ("收盘" in it["title"] or "收评" in it["title"])]
            self.assertEqual(len(ac_kept), 1)
            sk_item = next(it for it in res3["items"] if "离婚案" in it["title"])
            self.assertNotEqual(sk_item["importance"], "high")
            kp_item = next(it for it in res3["items"] if "KOSPI" in it["title"])
            mu_item = next(it for it in res3["items"] if "HBM" in it["title"])
            self.assertEqual(kp_item["importance"], "high")
            self.assertEqual(mu_item["importance"], "high")
            # Second cycle with already-merged items + pre-polluted "X / X / Y" source_name must heal & never duplicate
            lw_doc = json.loads((wroot3 / "data/live_wire.json").read_text(encoding="utf-8"))
            for row in lw_doc["items"]:
                if "台" in row["title"] and "源合并" in row["source_name"]:
                    row["source_name"] = "华尔街见闻 7×24 全球 / 华尔街见闻 7×24 全球 / 新浪财经 7×24 · 3 源合并"
            (wroot3 / "data/live_wire.json").write_text(json.dumps(lw_doc, ensure_ascii=False), encoding="utf-8")
            with patch("pipeline.connectors.china_realtime.fetch_china_realtime_wires", return_value=stub_burst):
                res3_second = refresh_live_wire_file(wroot3)
            for row in res3_second["items"]:
                src_head = str(row.get("source_name") or "").split(" · ")[0].split(" 等 ")[0]
                src_segs = [p.strip() for p in src_head.split("/") if p.strip()]
                self.assertEqual(len(src_segs), len(set(src_segs)), msg=f"Duplicate wire source segments: {row.get('source_name')}")

        # 4. NVIDIA lineage auto-absorbs Alpamayo 2 Edge VLA
        nvda_lineage = [{"generation": "Blackwell B200", "release_date": "2024-03", "filter_keyword": "Blackwell"}]
        absorbed = _auto_absorb_new_lineage_nodes(
            nvda_lineage,
            [{"title": "英伟达正式发布 Alpamayo 2 Edge VLA 自动驾驶与具身推理模型", "title_en": "NVIDIA launches Alpamayo 2 Edge VLA", "date": "2026-11-23T09:00:00+08:00", "milestone_dim": "flagship_release"}],
        )
        self.assertTrue(any("Alpamayo 2" in str(n.get("generation")) for n in absorbed))

        # 5. Dynamic live predictions keep 6-10 open live questions from catalysts + S-tier news
        gen_dt = datetime(2026, 11, 23, 16, 0, tzinfo=SHANGHAI_TZ)
        dyn_preds = build_dynamic_live_predictions(
            all_events=[
                {"title": "沪深北交易所宣布融资保证金比例降至80%，11月30日起施行", "severity_tier": "S", "category": "finance"},
                {"title": "韩国财政部称将审查启动股市平准基金应对KOSPI波动", "severity_tier": "S", "category": "global"},
                {"title": "国际金价杀跌后大幅反弹", "severity_tier": "A", "category": "finance"},
            ],
            calendar_items=[{"title": "神舟二十四号发射窗口", "scheduled_at": "2026-11-24T09:00:00+08:00", "is_past": False}],
            wire_items=[],
            generated_dt=gen_dt,
            generated_at_iso="2026-11-23T16:00:00+08:00",
            existing_predictions=[],
            prev_preds_by_id={},
            min_open_live=6,
            max_open_live=10,
        )
        open_live = [p for p in dyn_preds if p.get("mode") == "live" and p.get("status") == "open"]
        self.assertGreaterEqual(len(open_live), 6)
        self.assertLessEqual(len(open_live), 10)
        pids = {p["prediction_id"] for p in open_live}
        self.assertIn("pred_live_shenzhou24_launch", pids)
        self.assertIn("pred_live_margin80_turnover", pids)

    def test_v19_gemini_pool_8models_slug_resolution_rpm_and_1strike_503(self) -> None:
        import os
        import sys
        from types import SimpleNamespace
        from unittest import mock
        from pipeline import gemini_pool

        self.assertEqual(len(gemini_pool.MODEL_QUOTA_SPECS), 8)
        self.assertEqual(len(gemini_pool.TIER1_DEEP_MODELS), 8)
        self.assertEqual(gemini_pool.TIER1_DEEP_MODELS[0], "gemini-4-hydrogen")
        self.assertEqual(len(gemini_pool.TIER2_HIGH_THROUGHPUT_MODELS), 7)
        self.assertEqual(gemini_pool.TIER2_HIGH_THROUGHPUT_MODELS[:2], ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite"))

        called_models: list[str] = []

        class _FakeModels:
            def list(self):
                return [
                    SimpleNamespace(name="models/gemini-4-hydrogen-exp"),
                    SimpleNamespace(name="models/gemini-3.8-flash-preview"),
                    SimpleNamespace(name="models/gemini-3.5-flash-lite-preview"),
                ]

            def generate_content(self, *, model: str, contents: str, config=None):
                del contents, config
                called_models.append(model)
                if len(called_models) == 1:
                    raise RuntimeError("503 UNAVAILABLE overloaded")
                return SimpleNamespace(text='{"ok": true, "model": "' + model + '"}')

        class _FakeClient:
            def __init__(self, api_key=None, http_options=None):
                del api_key, http_options
                self.models = _FakeModels()

        fake_types = SimpleNamespace(
            GenerateContentConfig=lambda **kw: kw,
            HttpOptions=lambda **kw: kw,
        )
        fake_genai = SimpleNamespace(Client=_FakeClient, types=fake_types)
        fake_google = SimpleNamespace(genai=fake_genai)

        with tempfile.TemporaryDirectory() as td:
            with (
                mock.patch.dict(os.environ, {"GEMINI_API_KEY": "AIzaFakeKey1234567890_UnitTestOnly"}, clear=False),
                mock.patch.dict(sys.modules, {"google": fake_google, "google.genai": fake_genai, "google.genai.types": fake_types}),
            ):
                slug_resolved = gemini_pool.resolve_model_slug("gemini-3.8-flash", base_dir=td)
                self.assertEqual(slug_resolved, "gemini-3.8-flash-preview")
                res1 = gemini_pool.call_gemini_json(
                    scope="mega_briefing",
                    prompt='{"test": 1}',
                    tier="tier1",
                    max_output_tokens=4096,
                    timeout_ms=25_000,
                    base_dir=td,
                )
                self.assertTrue(res1.ok)
                self.assertEqual(res1.data, {"ok": True, "model": "gemini-3.8-flash-preview"})
                self.assertEqual(len(called_models), 2)

                res2 = gemini_pool.call_gemini_json(
                    scope="mega_finance_impact",
                    prompt='{"test": 2}',
                    tier="tier2",
                    base_dir=td,
                )
                self.assertTrue(res2.ok)
                self.assertEqual(called_models[-1], "gemini-3.5-flash-lite-preview")

    def test_v19_deterministic_core_base_heavy_formula_and_mega_batch_overlay(self) -> None:
        from unittest import mock
        from pipeline.heavy_classifier import compute_deterministic_heavy_score, is_heavy_noise_excluded
        from pipeline.bilingual import translate_texts_batch
        from pipeline.build_briefing import build_deterministic_events_from_fresh_clusters, _overlay_mega_batch_ai_analysis

        self.assertTrue(is_heavy_noise_excluded("美股盘前涨跌不一，热门中概股盘前微涨"))
        self.assertFalse(is_heavy_noise_excluded("英伟达股价盘中暴力飙升12%，黄仁勋传将重掌帅印"))
        hi_score = compute_deterministic_heavy_score(
            "黄仁勋重掌英伟达帅印，股价飙升12%",
            "证监会与美联储均予以回应",
            independent_publishers=3,
            is_official=True,
            has_authoritative_source=True,
        )
        lo_score = compute_deterministic_heavy_score(
            "某小盘消费股日常经营动态",
            "暂无重大变化",
            independent_publishers=1,
            is_official=False,
            has_authoritative_source=True,
        )
        self.assertGreater(hi_score, lo_score)
        self.assertGreaterEqual(hi_score, 55.0)

        with tempfile.TemporaryDirectory() as td:
            with mock.patch("pipeline.gemini_pool.call_gemini_json") as m_call:
                zh_out, attempts, _ = translate_texts_batch(
                    ["央行宣布下调存款准备金率0.5个百分点", "美联储议息会议纪要公布"],
                    target_lang="zh",
                    chunk_size=60,
                    root_dir=td,
                )
                self.assertEqual(attempts, 0)
                m_call.assert_not_called()
                self.assertEqual(len(zh_out or []), 2)

            raw_by_cat = {
                "finance": [
                    {
                        "id": "raw_fin_1",
                        "title": "黄金剧烈波动后企稳反弹，避险买盘升温",
                        "url": "https://example.com/fin1",
                        "source_name": "财联社",
                        "source_id": "cls",
                        "published_at": "2026-11-24T10:00:00+08:00",
                        "content": "现货黄金盘中拉升超2%，Comex 黄金期货同步走高。",
                        "citable_as_news": True,
                    }
                ],
                "tech": [
                    {
                        "id": "raw_tech_1",
                        "title": "Anthropic launches enterprise Claude upgrade",
                        "url": "https://example.com/tech1",
                        "source_name": "TechCrunch",
                        "source_id": "tc",
                        "published_at": "2026-11-24T10:05:00+08:00",
                        "content": "Enterprise rollout begins across global cloud regions.",
                        "citable_as_news": True,
                    }
                ],
                "global": [],
                "general": [],
            }
            cat_docs = {
                cat_k: build_deterministic_events_from_fresh_clusters(
                    Path(td),
                    cat_k,
                    raw_by_cat,
                    "raw-20261124-101500",
                    "2026-11-24T10:15:00+08:00",
                    "2026-11-24T10:30:00+08:00",
                    "smart-20261124-103000",
                    [],
                    None,
                )[0]
                for cat_k in ("finance", "tech")
            }
            self.assertEqual(len(cat_docs["finance"]["events"]), 1)
            self.assertEqual(len(cat_docs["tech"]["events"]), 1)

            from pipeline.gemini_pool import GeminiCallResult

            with (
                mock.patch("pipeline.build_briefing.collect_api_key_slots", return_value=["k1"]),
                mock.patch("pipeline.gemini_pool.collect_api_key_slots", return_value=["k1"]),
                mock.patch("pipeline.build_briefing.call_gemini_json") as m_mb,
                mock.patch("pipeline.gemini_pool.call_gemini_json") as m_bi,
            ):
                m_bi.return_value = GeminiCallResult(
                    ok=True,
                    data=["Anthropic 推出企业级 Claude 升级", "企业级部署正式启动"],
                    model_used="gemini-3.5-flash-lite",
                )
                m_mb.return_value = GeminiCallResult(
                    ok=True,
                    model_used="gemini-3.8-flash",
                    data={
                        "categories": {
                            "finance": {
                                "key_changes": [],
                                "overview_sections": [],
                                "events": [{
                                    "id": cat_docs["finance"]["events"][0]["event_id"],
                                    "fact_summary": "现货黄金低位拉升逾2%，避险资金重新回流贵金属板块。",
                                    "ai_analysis": "美元与美债实际利率回落支撑金价短期修复，贵金属产业链预期边际改善。",
                                    "deep_qa": [{"question": "为何金价快速反弹？", "answer": "实际利率预期回落叠加避险买盘承接。", "historical_parallel": "类似2023年春季银行风波期间金价走势。"}],
                                }],
                            },
                            "tech": {
                                "key_changes": [],
                                "overview_sections": [],
                                "events": [{
                                    "id": cat_docs["tech"]["events"][0]["event_id"],
                                    "fact_summary": "Anthropic 正式启动企业级 Claude 升级全球云部署。",
                                    "ai_analysis": "进一步扩大在受监管企业生产工作流中的模型渗透率。",
                                    "deep_qa": [],
                                }],
                            },
                        }
                    },
                )
                ov_res = _overlay_mega_batch_ai_analysis(
                    Path(td),
                    cat_docs,
                    input_cutoff_at="2026-11-24T10:30:00+08:00",
                )
                self.assertTrue(ov_res["ok"])
                self.assertEqual(m_mb.call_count, 1)
                self.assertTrue(cat_docs["finance"]["events"][0]["ai_overlaid"])
                self.assertEqual(cat_docs["finance"]["events"][0]["deep_qa"][0]["question"], "为何金价快速反弹？")

    def test_v19_mega_batch2_finance_and_derivative_enrichment(self) -> None:
        from unittest import mock
        from pipeline.gemini_pool import GeminiCallResult
        from pipeline.finance_deep_research import _fetch_batch_cards_ai_research
        from pipeline.deep_enrichment_engine import run_v12_deep_enrichment
        from pipeline.ai_radar_builder import _MODEL_VER_EXTRACT_RE

        self.assertIsNotNone(_MODEL_VER_EXTRACT_RE.search("Anthropic EFS system announced"))
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with mock.patch("pipeline.finance_deep_research.call_gemini_json") as m_fdr:
                m_fdr.return_value = GeminiCallResult(
                    ok=True,
                    model_used="gemini-3.5-flash-lite",
                    data={
                        "items": [
                            {
                                "id": "card_1",
                                "one_liner": "利好头部算力芯片与光模块链条",
                                "expectation_gap": "市场低估下游推理集群扩产斜率",
                                "transmission_layers": [
                                    {"tier": 1, "tier_label": "一阶直接冲击", "summary": "算力需求抬升", "stocks": [{"name": "中际旭创", "code": "300308.SZ", "market": "A股", "exposure_logic": "800G光模块放量", "direction": "positive"}]}
                                ],
                                "historical_precedents": [],
                                "quant_if_then": [],
                            },
                            {
                                "id": "card_2",
                                "one_liner": "避险属性强化支撑黄金板块",
                                "expectation_gap": "央行购金与实际利率定价尚未充分计入",
                                "transmission_layers": [
                                    {"tier": 1, "tier_label": "一阶直接冲击", "summary": "金价反弹修复盈利", "stocks": [{"name": "山东黄金", "code": "600547.SH", "market": "A股", "exposure_logic": "矿产金产量弹性高", "direction": "positive"}]}
                                ],
                                "historical_precedents": [],
                                "quant_if_then": [],
                            },
                        ]
                    },
                )
                res_fdr = _fetch_batch_cards_ai_research(
                    [("card_1", {"event_title": "算力集群资本开支上修", "event_summary": "云厂加码AI基建"}), ("card_2", {"event_title": "国际金价反弹", "event_summary": "现货黄金上涨"})],
                    root,
                )
                self.assertEqual(m_fdr.call_count, 1)
                self.assertEqual(len(res_fdr), 2)

            preserved_qa = [{"question": "Mega-Batch 1 原生深度追问？", "answer": "该回答必须完整保留，不得被确定性模板覆盖。", "historical_parallel": "参考历史同类事件表现。"}]
            cat_docs = {
                "finance": {"events": [{"event_id": "ev_keep", "title": "黄金大涨引发市场热议", "fact_summary": "黄金盘中走高。", "severity_tier": "S", "sources": [{"source_name": "财联社"}], "deep_qa": preserved_qa}]},
                "global": {"events": []},
                "tech": {"events": [{"event_id": "ev_need", "title": "新一代大模型架构发布", "fact_summary": "推理成本显著下探。", "severity_tier": "A", "sources": [{"source_name": "机器之心"}]}]},
                "general": {"events": []},
            }
            with (
                mock.patch("pipeline.deep_enrichment_engine.collect_api_key_slots", return_value=["k1"]),
                mock.patch("pipeline.deep_enrichment_engine.enrich_tools_with_ai_comparison", side_effect=lambda t, r, generated_at_iso="": t),
                mock.patch("pipeline.deep_enrichment_engine.call_gemini_json") as m_mb2b,
            ):
                m_mb2b.return_value = GeminiCallResult(
                    ok=True,
                    model_used="gemini-3.1-flash-lite",
                    data={
                        "topics": {"tp_1": {"brief_overview": "AI 推理架构持续演化。", "comparison_table": {"headers": ["参与方", "立场", "影响"], "rows": [["开源生态", "降本提效", "加速端侧普及"]]}}},
                        "storylines": {"st_1": {"history_nodes": [{"timestamp": "2026-11-24", "stage_tag": "进展", "title": "架构正式落地", "fact_summary": "多方基准验证完成。", "source_name": "财联社"}], "stance_comparison": [{"side": "产业界", "summary": "认可推理效率提升。", "key_sources": ["财联社"]}]}},
                        "event_qa": {"ev_need": [{"question": "推理降本带来什么变化？", "answer": "中小开发者部署门槛大幅降低。", "historical_parallel": "参考过去云计算带宽资费下行周期。"}]},
                    },
                )
                run_v12_deep_enrichment(
                    root,
                    generated_at_iso="2026-11-24T10:30:00+08:00",
                    cat_docs=cat_docs,
                    storylines={"st_1": {"title": "AI 架构演进", "timeline": [{"title": "最新节点"}], "latest_reported_at": "2026-11-24T10:00:00+08:00"}},
                    major_topics=[{"topic_id": "tp_1", "title": "AI 大模型专题", "timeline": [{"title": "节点1"}]}],
                    tech_tools=[],
                )
                self.assertEqual(m_mb2b.call_count, 1)
                self.assertEqual(cat_docs["finance"]["events"][0]["deep_qa"][0]["question"], "Mega-Batch 1 原生深度追问？")
                self.assertEqual(cat_docs["tech"]["events"][0]["deep_qa"][0]["question"], "推理降本带来什么变化？")

    def test_v20_predictions_plain_language_12_to_18_and_early_auto_settle(self) -> None:
        from datetime import datetime
        from unittest import mock
        from pipeline.gemini_pool import GeminiCallResult
        from pipeline.deep_enrichment_engine import verify_live_predictions_settlement_via_tier2
        from pipeline.time_utils import SHANGHAI_TZ
        from pipeline.v3_builder import (
            auto_settle_live_predictions,
            build_dynamic_live_predictions,
            build_v3_artifacts,
        )

        gen_dt = datetime(2026, 11, 24, 12, 0, tzinfo=SHANGHAI_TZ)
        gen_iso = "2026-11-24T12:00:00+08:00"
        slop_legacy = {
            "prediction_id": "pred_live_auto_e6931f8b",
            "mode": "live",
            "status": "open",
            "title": "后续验证：黄仁勋重掌英伟达帅印！股价暴涨31% 未来 7 天是否触发实质进展",
        }
        dyn = build_dynamic_live_predictions(
            all_events=[
                {"title": "黄仁勋重掌英伟达帅印，股价飙涨31%", "severity_tier": "S", "category": "finance"},
                {"title": "神舟二十四号瞄准25日发射", "severity_tier": "A", "category": "tech"},
            ],
            calendar_items=[],
            wire_items=[],
            generated_dt=gen_dt,
            generated_at_iso=gen_iso,
            existing_predictions=[slop_legacy],
            prev_preds_by_id={slop_legacy["prediction_id"]: slop_legacy},
        )
        pids = {p["prediction_id"] for p in dyn}
        self.assertNotIn("pred_live_auto_e6931f8b", pids)
        open_dyn = [p for p in dyn if p.get("mode") == "live" and p.get("status") == "open"]
        self.assertGreaterEqual(len(open_dyn), 12)
        self.assertLessEqual(len(open_dyn), 18)
        cats_present = {p.get("category") for p in open_dyn}
        self.assertEqual(cats_present, {"tech_ai", "market", "macro", "global_space"})
        sz = next(p for p in dyn if p["prediction_id"] == "pred_live_shenzhou24_launch")
        self.assertEqual(sz["target_entity_id"], "ent_china_aerospace")

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "data").mkdir(parents=True, exist_ok=True)
            nvda_seed = {
                "prediction_id": "pred_seed_nvda_sec_502",
                "mode": "live",
                "status": "open",
                "category": "tech_ai",
                "title": "黄仁勋能否在 14 天内正式重返英伟达出任 CEO？",
                "probability_pct": 65,
                "due_at": "2026-11-30T20:00:00+08:00",
                "win_rule": "英伟达官方或 SEC 8-K 公告宣布黄仁勋复职 CEO",
                "lose_rule": "截止日前英伟达未恢复黄仁勋职务或另选他人出任正式 CEO",
                "current_judgment": "等待核验",
                "versions": [{"version": 1, "updated_at": gen_iso, "judgment": "待核验", "probability_pct": 65, "reason": "初始"}],
                "settlement": None,
            }
            settled = auto_settle_live_predictions(
                root,
                predictions=[nvda_seed, slop_legacy] + dyn,
                all_events=[
                    {
                        "title": "在涉嫌间谍事件后，英伟达恢复黄仁勋的CEO职务",
                        "fact_summary": "英伟达董事会已恢复黄仁勋 CEO 职务。",
                        "sources": [{"source_name": "财联社", "url": "https://www.cls.cn/detail/1"}],
                    },
                    {
                        "title": "黄仁勋复职重掌英伟达 股价飙涨逾30%",
                        "fact_summary": "SEC 8-K 同步披露正式任命。",
                        "sources": [{"source_name": "华尔街见闻", "url": "https://wallstreetcn.com/articles/1"}],
                    },
                ],
                entities_map={
                    "ent_nvidia": {
                        "recent_filings": [{"form": "8-K", "filing_date": "2026-11-23", "items": ["5.02,9.01"], "url": "https://www.sec.gov/nvda-8k"}]
                    }
                },
                generated_dt=gen_dt,
                generated_at_iso=gen_iso,
                use_ai=False,
            )
            by_id = {p["prediction_id"]: p for p in settled}
            self.assertNotIn("pred_live_auto_e6931f8b", by_id)
            nv = by_id["pred_seed_nvda_sec_502"]
            self.assertEqual(nv["status"], "settled")
            self.assertEqual(nv["settlement"]["outcome"], "correct")
            self.assertIsNotNone(nv["settlement"].get("brier_score"))
            self.assertTrue((root / "data/predictions_settled_archive.json").exists())

            # Rebuild without NVDA events -> archive permanently keeps status="settled"
            settled_again = auto_settle_live_predictions(
                root,
                predictions=[{**nvda_seed, "status": "open", "settlement": None}],
                all_events=[],
                generated_dt=gen_dt,
                generated_at_iso=gen_iso,
                use_ai=False,
            )
            self.assertEqual(settled_again[0]["status"], "settled")
            self.assertEqual(settled_again[0]["settlement"]["outcome"], "correct")

            # Verify Tier-2 AI settler accepts real catalog E01 & rejects hallucinated E99
            with (
                mock.patch("pipeline.deep_enrichment_engine.collect_api_key_slots", return_value=["k1"]),
                mock.patch("pipeline.deep_enrichment_engine.call_gemini_json") as m_settle,
            ):
                m_settle.return_value = GeminiCallResult(
                    ok=True,
                    model_used="gemini-3.5-flash-lite",
                    data={
                        "settlements": [
                            {"prediction_id": "pred_live_zhipu_glm54_launch", "settle": True, "outcome": "correct", "evidence_id": "E01", "note": "智谱官方正式上线 GLM-5.4 模型。"},
                            {"prediction_id": "pred_live_gold_rebound_window", "settle": True, "outcome": "correct", "evidence_id": "E99", "note": "虚假编号不应通过校验"},
                        ]
                    },
                )
                ai_res = verify_live_predictions_settlement_via_tier2(
                    root,
                    open_predictions=[
                        {"prediction_id": "pred_live_zhipu_glm54_launch", "mode": "live", "status": "open", "title": "智谱 GLM-5.4 能否正式发布", "target_entity": "智谱", "win_rule": "官宣发布", "lose_rule": "推迟"},
                        {"prediction_id": "pred_live_gold_rebound_window", "mode": "live", "status": "open", "title": "现货黄金能否站上 3700 美元", "target_entity": "黄金", "win_rule": "站上3700", "lose_rule": "低于3700"},
                    ],
                    all_events=[{"title": "智谱正式发布 GLM-5.4 并开放 API", "fact_summary": "今日全量上线", "sources": [{"source_name": "机器之心", "url": "https://jiqizhixin.com/glm54"}]}],
                    wire_items=[],
                    generated_at_iso=gen_iso,
                )
                self.assertIn("pred_live_zhipu_glm54_launch", ai_res)
                self.assertEqual(ai_res["pred_live_zhipu_glm54_launch"]["evidence_url"], "https://jiqizhixin.com/glm54")
                self.assertNotIn("pred_live_gold_rebound_window", ai_res)

            # End-to-end build_v3_artifacts sanity on note hygiene & count bounds
            empty_cat = lambda c: {"category": c, "batch_id": "b20", "generated_at": gen_iso, "events": []}
            cat_docs = {c: empty_cat(c) for c in ("finance", "global", "tech", "general")}
            cat_docs["finance"]["events"] = [{
                "event_id": "ev_nvda_ret",
                "category": "finance",
                "title": "黄仁勋重掌英伟达帅印，股价飙升31%",
                "fact_summary": "英伟达董事会恢复黄仁勋 CEO 职务。",
                "sources": [{"source_name": "财联社", "url": "https://cls.cn/nvda"}],
                "latest_reported_at": gen_iso,
                "first_discovered_at": gen_iso,
                "first_reported_at": gen_iso,
                "latest_fact_update_at": gen_iso,
                "evidence_status": "corroborated",
                "evidence_label": "交叉印证",
                "independent_publisher_count": 2,
                "reprint_count": 0,
                "severity_tier": "S",
            }]
            with mock.patch("pipeline.deep_enrichment_engine.collect_api_key_slots", return_value=[]):
                build_v3_artifacts(
                    root,
                    batch_id="smart-20261124-120000",
                    generated_at_iso=gen_iso,
                    cat_docs=cat_docs,
                    prev_cat_events={},
                    prev_batch_id=None,
                    connectors_payload={
                        "entity_updates": {
                            "ent_nvidia": {"sec_filings": [{"form": "8-K", "filing_date": "2026-11-23", "items": ["5.02,9.01"], "url": "https://www.sec.gov/nvda-8k"}]}
                        }
                    },
                )
            pub_doc = json.loads((root / "data/predictions_public.json").read_text(encoding="utf-8"))
            self.assertNotIn("导入导出", pub_doc["note"])
            self.assertNotIn("本地浏览器", pub_doc["note"])
            pub_live_open = [p for p in pub_doc["predictions"] if p.get("mode") == "live" and p.get("status") == "open"]
            pub_live_settled = [p for p in pub_doc["predictions"] if p.get("mode") == "live" and p.get("status") == "settled"]
            self.assertGreaterEqual(len(pub_live_open), 12)
            self.assertLessEqual(len(pub_live_open), 18)
            self.assertEqual(len(pub_live_settled), 1)
            self.assertEqual(pub_live_settled[0]["prediction_id"], "pred_seed_nvda_sec_502")
            self.assertEqual(pub_live_settled[0]["settlement"]["outcome"], "correct")

    def test_v21_tool_dict_sanitize_gold_sanity_wire_routing_and_inverse_etf(self) -> None:
        from datetime import datetime, timedelta, timezone
        from pipeline.bilingual import _extract_tool_summary_text, enrich_zh_tech_tools
        from pipeline.market_quotes import _is_sane_quote
        from pipeline.connectors.china_realtime import _classify_wire_item, refresh_live_wire_file
        from pipeline.finance_impact_builder import build_finance_impact_artifact

        raw_dict_str = "{'name': 'n8n', 'summary': '开源工作流自动化与 AI 编排平台。'}"
        self.assertEqual(_extract_tool_summary_text(raw_dict_str), "开源工作流自动化与 AI 编排平台。")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data").mkdir(parents=True, exist_ok=True)
            tools = [{"tool_id": "t_n8n", "name": "n8n", "summary": raw_dict_str, "summary_zh": "", "summary_en": ""}]
            enrich_zh_tech_tools(tools, base_dir=root)
            self.assertNotIn("{'name':", tools[0]["summary"])
            self.assertIn("工作流", tools[0]["summary"])

            # Gold price sanity bounds check (410 bogus COMEX vs 2650 sane)
            self.assertFalse(_is_sane_quote("GC=F", "commodity_gold", 410.0, -4.0))
            self.assertTrue(_is_sane_quote("GC=F", "commodity_gold", 2650.0, 1.2))

            # Foreign industrial explosion should route to global, not finance
            self.assertEqual(
                _classify_wire_item("哥伦比亚波哥大工业区发生强烈爆炸已致12人死亡", "", "finance"),
                "global",
            )

            # Casualty escalation within 12h merges to higher casualty count (19)
            now_iso = datetime.now(timezone.utc).isoformat()
            prev_iso = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
            res = refresh_live_wire_file(
                base_dir=root,
                extra_items=[
                    {"id": "w_col_1", "title": "哥伦比亚波哥大工业区爆炸已致12人死亡", "excerpt": "救援仍在继续", "url": "https://example.com/1", "source_name": "央视", "category": "global", "published_at": prev_iso, "fetched_at": prev_iso},
                    {"id": "w_col_2", "title": "哥伦比亚波哥大工业区爆炸事故伤亡人数升至19人", "excerpt": "调查已展开", "url": "https://example.com/2", "source_name": "新华社", "category": "global", "published_at": now_iso, "fetched_at": now_iso},
                ],
            )
            merged_col = [it for it in res["items"] if "波哥大" in it.get("title", "")]
            self.assertEqual(len(merged_col), 1)
            self.assertIn("19人", merged_col[0]["title"])

        # Inverse NVDA ETF must NOT match ai_equity_selloff
        fin_doc = build_finance_impact_artifact(
            all_events=[
                {
                    "event_id": "ev_inv_etf",
                    "category": "finance",
                    "title": "做空英伟达两倍ETF大涨63%，资金关注波动对冲",
                    "fact_summary": "杠杆反向ETF产品受机构对冲情绪推动走强。",
                    "sources": [{"source_name": "财联社", "url": "https://cls.cn/inv"}],
                    "latest_reported_at": now_iso,
                    "importance": "medium",
                }
            ],
            batch_id="smart-test",
            generated_at_iso=now_iso,
            quotes_doc={"quotes": {"NVDA": {"ticker": "NVDA", "price": 140.0, "pct_change": 1.2}}},
        )
        inv_matches = [it for it in fin_doc.get("event_impacts", []) if it.get("event_id") == "ev_inv_etf"]
        if inv_matches:
            self.assertNotEqual(inv_matches[0].get("tag"), "AI 算力链回调")
            self.assertNotEqual(inv_matches[0].get("polarity"), "bearish")


if __name__ == "__main__":
    unittest.main()
