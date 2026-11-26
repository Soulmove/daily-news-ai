"""Unit tests for 2-stage Weekly Major Events Digest distillation & strict deduplication."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pipeline.time_utils import SHANGHAI_TZ
from pipeline.weekly_digest import (
    _CLICHE_PATTERNS,
    SECTOR_IDS,
    _is_title_parrot,
    _make_plain_title,
    _scrub_cliches,
    build_and_write_weekly_digest,
    classify_weekly_sector,
    compute_natural_week_bounds,
    distill_weekly_candidates,
    is_weekly_intraday_noise,
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

    def test_intraday_tick_filter_sector_routing_and_two_call_batched_ai(self) -> None:
        self.assertTrue(is_weekly_intraday_noise("WTI原油日内下跌1%，现报80.50美元/桶。布伦特原油现跌0.8%。"))
        self.assertTrue(is_weekly_intraday_noise("恒指、恒生科技指数均转跌。"))
        self.assertTrue(is_weekly_intraday_noise("三星电子跌幅扩大至9%，SK海力士跌8.6%。"))
        self.assertEqual(
            classify_weekly_sector(
                {
                    "category": "global",
                    "title": "三星电子与SK海力士签署新一代HBM4存储芯片量产供应协议",
                    "fact_summary": "韩国存储芯片两大厂商推进下一代AI算力高带宽内存研发。",
                }
            ),
            "tech_ai",
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            day = root / "archives" / "smart" / "2026-11-26" / "13-00"
            day.mkdir(parents=True)
            distinct_finance = [
                ("央行开展8000亿中期借贷便利操作缓解年末资金压力", ["央行"]),
                ("财政部增发3000亿超长期特别国债支持装备更新", ["财政部"]),
                ("两融融资保证金下调方案引发沪深券商开户回暖", ["证监会"]),
                ("十年期美债收益率回落至4.15%带动新兴市场汇市走稳", ["美债"]),
                ("欧洲央行释放十二月可能暂停降息的最新会议纪要", ["欧央行"]),
                ("日本央行行长暗示春季薪资谈判若超预期将继续加息", ["日央行"]),
            ]
            distinct_tech = [
                ("阿里通义千问发布下一代旗舰开源推理模型降低调用费", ["Qwen"]),
                ("台积电熊本二厂提前进入三纳米光刻机安装调试阶段", ["台积电"]),
                ("微软宣布向欧洲工业云基础设施追加一百亿美元资本开支", ["微软"]),
                ("华为升腾新一代算力集群完成万卡训练兼容性验证", ["华为"]),
                ("谷歌发布轻量端侧多模态小模型适配安卓旗舰芯片", ["谷歌"]),
                ("宇树人形机器人完成汽车总装线连续八小时实景测试", ["宇树"]),
            ]
            distinct_geo = [
                ("联合国安理会审议红海商业航道护航机制延期草案", ["联合国"]),
                ("欧盟与印尼签署关键矿产加工关税减免框架协议", ["欧盟"]),
                ("OPEC主要产油国部长会议讨论明年一季度配额执行率", ["OPEC"]),
                ("拉美四国宣布打通跨境光伏电站特高压联网标准", ["拉美"]),
            ]
            fin_evs = [
                _sample_event(
                    f"evt_m_{i}",
                    title,
                    "finance",
                    summary=f"{title}，坚决拥护上级决策。核心资金规模达到 {100 + i * 37} 亿元。",
                )
                for i, (title, _ents) in enumerate(distinct_finance)
            ]
            for ev, (_, ents) in zip(fin_evs, distinct_finance):
                ev["entities"] = ents
            tech_evs = [
                _sample_event(
                    f"evt_t_{i}",
                    title,
                    "tech",
                    summary=f"{title}，推理成本下降 {20 + i * 5}%，开发者今日可直接部署。",
                )
                for i, (title, _ents) in enumerate(distinct_tech)
            ]
            for ev, (_, ents) in zip(tech_evs, distinct_tech):
                ev["entities"] = ents
            geo_evs = [
                _sample_event(
                    f"evt_g_{i}",
                    title,
                    "global",
                    summary=f"{title}，正式文本已于周四对外公布时间表。",
                )
                for i, (title, _ents) in enumerate(distinct_geo)
            ]
            for ev, (_, ents) in zip(geo_evs, distinct_geo):
                ev["entities"] = ents
            tick_ev = _sample_event("evt_tick_noise", "WTI原油日内下跌1%，现报80.50美元/桶。", "finance")

            (day / "analysis_finance.json").write_text(json.dumps({"events": fin_evs + [tick_ev]}, ensure_ascii=False), encoding="utf-8")
            (day / "analysis_tech.json").write_text(json.dumps({"events": tech_evs}, ensure_ascii=False), encoding="utf-8")
            (day / "analysis_global.json").write_text(json.dumps({"events": geo_evs}, ensure_ascii=False), encoding="utf-8")

            calls: list[dict] = []

            class _FakeRes:
                def __init__(self, data: dict):
                    self.ok = True
                    self.data = data
                    self.model_used = "gemini-3-flash-preview"

            def fake_gemini(scope: str, prompt: str, **kwargs):
                calls.append({"scope": scope, "prompt": prompt})
                if scope == "weekly_digest":
                    return _FakeRes(
                        {
                            "week_theme": "大资金稳字当头，AI 拼成本落地",
                            "executive_thesis": ["央行放水稳住资金面。", "大模型开始拼实打实的推理成本。", "贸易谈判先挑硬骨头啃。"],
                            "keywords": ["央行流动性", "AI 降本"],
                            "sectors_summary": {
                                "macro_finance": "钱袋子稳住了",
                                "geopolitics": "谈判桌上有松动",
                                "tech_ai": "推理越做越便宜",
                                "industry_society": "产业链忙着抢单",
                            },
                            "cross_sector_threads": [
                                {"title": "算力降本传导制造", "from_sector": "tech_ai", "to_sector": "macro_finance", "logic": "芯片降本推高软件盈利预期。"}
                            ],
                            "next_week_catalysts": [
                                {"date": "2026-12-01", "title": "制造业PMI出炉", "sector_id": "macro_finance", "why_watch": "看有没有站上50荣枯线", "action_hint": "盯紧资金开盘流向"}
                            ],
                            "next_week_outlook": [
                                {
                                    "id": "outlook_1",
                                    "sector_id": "macro_finance",
                                    "topic": "大盘开盘承接力度",
                                    "direction": "volatile",
                                    "direction_label": "先震荡后选方向",
                                    "confidence_pct": 66,
                                    "plain_forecast": "资金会在前两天先试探量能能不能站稳，再决定加仓还是缩手。",
                                    "if_up_trigger": "成交量连续两天放大就偏强。",
                                    "if_down_trigger": "高开低走就小心。",
                                    "watch_time": "下周一二",
                                    "linked_prediction_id": None,
                                }
                            ],
                        }
                    )
                # Batch rewrite items call: extract IDs requested in batch prompt
                import re as _re
                ids = _re.findall(r'"(wk_[^"]+)"', prompt)
                return _FakeRes(
                    {
                        "items": [
                            {
                                "id": rid,
                                "plain_title": f"大白话短标 {rid[-4:]}",
                                "one_line_takeaway": f"真金白银落地影响资金节奏 {rid[-4:]}",
                                "why_it_matters": f"这件事直接改变行业里的订单和资金成本预期，影响接下来两周排产 {rid[-4:]}。",
                                "next_week_watch": f"下周三前盯紧具体成交与招标数字 {rid[-4:]}",
                            }
                            for rid in dict.fromkeys(ids)
                        ]
                    }
                )

            thu = datetime(2026, 11, 26, 18, 0, tzinfo=SHANGHAI_TZ)
            with patch("pipeline.weekly_digest.count_healthy_keys", return_value=5), patch(
                "pipeline.weekly_digest.call_gemini_json", side_effect=fake_gemini
            ):
                doc = build_and_write_weekly_digest(root, ref_dt=thu, use_ai=True)

            self.assertEqual(doc["generation_mode"], "ai_weekly_assisted_v1")
            all_items = [it for sec in doc["sectors"] for it in sec["items"]]
            self.assertEqual(len(all_items), 16)
            self.assertFalse(any("WTI原油" in it["title"] for it in all_items))
            self.assertTrue(all(it["next_week_watch"].startswith("下周三前盯紧") for it in all_items))
            # 1 editorial call + 2 batched item calls for 16 items (12 + 4)
            self.assertEqual([c["scope"] for c in calls], ["weekly_digest", "weekly_digest_items", "weekly_digest_items"])
            self.assertNotIn("坚决拥护", json.dumps(doc, ensure_ascii=False))
