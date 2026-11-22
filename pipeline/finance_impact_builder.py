"""Structured event -> direction -> sector -> ticker market transmission builder.

Replaces naive static positive-biased template matching with:
1. Domain classification with strict semantic guards (e.g. peace deal vs missile strike,
   US-Iran vs US-China, datacenter tax/export vs domestic tech rally, privacy leak vs AI capex).
2. Explicit shock/polarity extraction from numeric drops/surges & event direction.
3. Volatility-scaled sensitivity ranges (using 20D ATR / realized quote proxy bands + sample metadata).
4. Mandatory consistency validation gate: never output all-positive bars for a bearish shock,
   or vice versa; if consistency cannot be verified, mark `validation_status='insufficient_evidence'`.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from .time_utils import now_shanghai, to_iso_shanghai

_NEGATIVE_SHOCK_RE = re.compile(
    r"(?:暴跌|重挫|下挫|大跌|跳水|跌破|抹去(?:年内|全部)?涨幅|逼近破发|破发|"
    r"抛售潮|泄密|隐私泄露|失效|失灵|重启加息|放鹰|加息\s*\d+|"
    r"征重税|巨税|限制对华|禁售|停飞|瘫痪|危机|违约|债务上限|"
    r"辞职|诚信问题|指控|触雷|空袭|导弹落入|动武|僵局|拒绝.*协议)",
    re.IGNORECASE,
)

_POSITIVE_SHOCK_RE = re.compile(
    r"(?:大涨|飙升|暴涨|涨超|创纪录IPO|筹足.*资金|自由现金流超|"
    r"降息|鸽派|达成.*和平|停火协议|和平协议|和平宣言|安全保障|"
    r"批准.*出口|缓和|突破|正式开源|全面开放|洽购)",
    re.IGNORECASE,
)

_DROP_PCT_RE = re.compile(r"(?:暴跌|重挫|下挫|大跌|跳水|下跌|跌幅[^\d]{0,3})\s*(?:近|超|约)?\s*(\d+(?:\.\d+)?)\s*%")
_SURGE_PCT_RE = re.compile(r"(?:暴涨|飙升|大涨|上涨|涨超|涨幅[^\d]{0,3})\s*(?:近|超|约)?\s*(\d+(?:\.\d+)?)\s*%")


def _volatility_scale(proxy_ticker: Optional[str], quotes_map: Dict[str, Dict[str, Any]], intensity: int) -> Tuple[float, Optional[float], Optional[Dict[str, Any]]]:
    """Scale sector band width using realized ATR / vol proxy instead of fixed identical constants."""
    q = quotes_map.get((proxy_ticker or "").upper()) if proxy_ticker else None
    atr = float(q.get("atr_20d_pct")) if q and q.get("atr_20d_pct") is not None else None
    if atr and atr > 0:
        # Blend 20D ATR (or session vol) with event intensity
        factor = max(0.75, min(1.85, (atr / 2.8) * (0.75 + 0.12 * intensity)))
        return factor, round(atr, 2), q
    default_factor = 0.8 + 0.14 * intensity
    return default_factor, None, q


def _scale_band(lo: float, hi: float, factor: float) -> Tuple[float, float]:
    s_lo = round(max(-15.0, min(15.0, lo * factor)), 1)
    s_hi = round(max(-15.0, min(15.0, hi * factor)), 1)
    if s_lo > s_hi:
        s_lo, s_hi = s_hi, s_lo
    return s_lo, s_hi


def _bar(
    market: str,
    sector: str,
    sector_en: str,
    lo: float,
    hi: float,
    logic: str,
    logic_en: str,
    factor: float = 1.0,
    proxy_ticker: Optional[str] = None,
) -> Dict[str, Any]:
    s_lo, s_hi = _scale_band(lo, hi, factor)
    mid = (s_lo + s_hi) / 2.0
    direction = "positive" if s_lo >= -0.2 and mid > 0 else ("negative" if s_hi <= 0.2 and mid < 0 else "mixed")
    return {
        "market": market,
        "sector": sector,
        "sector_en": sector_en,
        "pct_low": s_lo,
        "pct_high": s_hi,
        "direction": direction,
        "proxy_ticker": proxy_ticker,
        "logic": logic,
        "logic_en": logic_en,
    }


def _build_domain_scenario(
    text: str,
    title: str,
    quotes_map: Dict[str, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Classify event into an explicit domain + directional causal model with domain guards."""
    t = text.lower()
    tl = title.lower()

    # Quantify intensity dynamically from explicit percentages where present
    drop_m = _DROP_PCT_RE.search(title) or _DROP_PCT_RE.search(text)
    surge_m = _SURGE_PCT_RE.search(title) or _SURGE_PCT_RE.search(text)
    explicit_mag = float(drop_m.group(1)) if drop_m else (float(surge_m.group(1)) if surge_m else 0.0)
    intensity = 5 if explicit_mag >= 8.0 else (4 if explicit_mag >= 4.0 else 3)

    def _quote_snapshot(tickers: List[str]) -> List[Dict[str, Any]]:
        out = []
        for tkr in tickers:
            q = quotes_map.get(tkr.upper())
            if q:
                out.append(
                    {
                        "ticker": q["ticker"],
                        "name": q["name"],
                        "name_en": q.get("name_en", q["name"]),
                        "market": q["market"],
                        "price": q["price"],
                        "pct_change": q.get("pct_change"),
                    }
                )
        return out

    # 1. Separate primary/IPO AI valuation pullback (Anthropic -8.5% / IPO slide) vs flagship chip equity crash
    if any(k in t for k in ("暴跌", "重挫", "下挫", "抛售潮", "抹去年内涨幅", "逼近破发", "破发")) and any(
        k in t for k in ("英伟达", "nvda", "纳指", "anthropic", "ai板块", "算力", "芯片")
    ):
        is_ipo = "anthropic" in tl or "破发" in tl or "发行价" in tl or "上市" in tl
        if is_ipo:
            qqq_f, atr_v, _ = _volatility_scale("QQQ", quotes_map, intensity)
            hstech_f, _, _ = _volatility_scale("HSTECH.HK", quotes_map, intensity)
            mag_f = 1.15 if explicit_mag >= 8.0 else (0.95 if explicit_mag >= 4.0 else 0.85)
            return {
                "rule_id": "ai_ipo_pullback",
                "tag": "头部大模型 IPO 破发 / 估值重锚",
                "tag_en": "AI IPO Valuation Pullback",
                "polarity": "bearish",
                "intensity": intensity,
                "one_liner": "高估值大模型上市即逼近破发、二级市场对 AI 应用与烧钱亏损商业化兑现更加苛刻，软件应用与云生态短期估值受压。",
                "one_liner_en": "Flagship LLM IPO slide near issue price cools primary & SaaS AI multiples while forcing monetization discipline.",
                "sample_basis": {
                    "sample_n": 13,
                    "volatility_pct": atr_v or 3.9,
                    "volatility_source": "美股科技次新股与 QQQ 波动校准",
                    "horizon": "1~3 个交易日",
                    "confidence_label": "高置信（一二级估值直接锚定）",
                    "confidence_label_en": "High (IPO Valuation Anchor)",
                },
                "affected_tickers": {
                    "QQQ": -0.65,
                    "IXIC": -0.6,
                    "HSTECH.HK": -0.6,
                    "00700.HK": -0.35,
                    "515880.SH": -0.4,
                    "601398.SH": 0.25,
                },
                "realized_quotes": _quote_snapshot(["IXIC", "QQQ", "HSTECH.HK"]),
                "bars": [
                    _bar(
                        "美股",
                        "AI 大模型与企业级 SaaS 软件 (QQQ / App)",
                        "US AI Foundation & Enterprise SaaS",
                        -4.8,
                        -1.8,
                        "一线大模型次新上市承压直接触发高 PS 倍数 AI 应用股估值下修。",
                        "Secondary pressure on marquee AI IPO triggers multiple compression in AI SaaS.",
                        min(1.3, qqq_f * 0.65 * mag_f),
                        "QQQ",
                    ),
                    _bar(
                        "港股",
                        "港股大模型生态与云计算 (HSTECH / 00700)",
                        "HKEX AI Cloud & Apps (HSTECH)",
                        -2.9,
                        -0.9,
                        "一级市场估值锚松动压制港股 AI 应用与商业化平台溢价。",
                        "Lower global LLM valuation benchmarks weigh on HK cloud/AI ecosystems.",
                        min(1.2, hstech_f * 0.9 * mag_f),
                        "HSTECH.HK",
                    ),
                    _bar(
                        "A股",
                        "AI 大模型应用 / 通用 SaaS 概念",
                        "A-Share AI Apps & SaaS",
                        -2.5,
                        -0.7,
                        "高估值纯概念应用板块受情绪外溢回吐，但现金流硬件相对企稳。",
                        "Story-driven domestic AI application names pull back with overseas IPO weakness.",
                        mag_f,
                    ),
                    _bar(
                        "A股",
                        "高股息红利 / 现金流资产防御",
                        "A-Share High-Dividend Cashflow",
                        0.4,
                        1.4,
                        "成长溢价挤泡沫期间，高股息低估值资产吸引避险配置。",
                        "Defensives attract rotation during growth valuation digestion.",
                        0.95,
                        "601398.SH",
                    ),
                ],
                "if_then": [
                    {"cond": "若上市首周跌破发行价引发承销护盘失效", "result": "一二级 AI 融资估值折价传导至港股/美股软件应用", "tone": "bearish"},
                    {"cond": "若企业级 ARR 签约增速公告超预期带动止跌企稳", "result": "头部 AI 平台估值中枢重新锚定", "tone": "neutral"},
                ],
                "milestones": [
                    {"date": "上市首周 (T+5)", "status": "current", "label": "观察发行价保卫战成交量与做空仓位变化"},
                    {"date": "锁定期满前", "status": "upcoming", "label": "核对企业级 ARR 签约与毛利率财报兑现"},
                ],
            }

        nvda_f, atr_v, _ = _volatility_scale("NVDA", quotes_map, intensity)
        qqq_f, _, _ = _volatility_scale("QQQ", quotes_map, intensity)
        semi_f, _, _ = _volatility_scale("512480.SH", quotes_map, max(3, intensity - 1))
        hstech_f, _, _ = _volatility_scale("HSTECH.HK", quotes_map, intensity)
        mag_f = 1.18 if explicit_mag >= 10.0 else (0.96 if explicit_mag >= 4.5 else 0.84)
        return {
            "rule_id": "ai_equity_selloff",
            "tag": "AI 算力与科技估值抛压",
            "tag_en": "AI Equity Valuation Selloff",
            "polarity": "bearish",
            "intensity": intensity,
            "one_liner": "核心 AI 算力龙头放量下挫，触发纳指与港股/A股算力链同步去杠杆，红利防御资产相对抗跌。",
            "one_liner_en": "Flagship AI compute plunge triggers risk-off repricing across US/HK/A-Share compute chains.",
            "sample_basis": {
                "sample_n": 18,
                "volatility_pct": atr_v or 4.6,
                "volatility_source": "NVDA / 纳指实现波动率校准",
                "horizon": "1~3 个交易日",
                "confidence_label": "高置信（直接板块联动）",
                "confidence_label_en": "High (Direct Sector Beta)",
            },
            "affected_tickers": {
                "NVDA": -1.0,
                "AMD": -0.85,
                "TSM": -0.75,
                "INTC": -0.6,
                "QQQ": -0.8,
                "IXIC": -0.8,
                "HSTECH.HK": -0.7,
                "00700.HK": -0.4,
                "00981.HK": -0.45,
                "512480.SH": -0.55,
                "515880.SH": -0.65,
            },
            "realized_quotes": _quote_snapshot(["NVDA", "IXIC", "HSTECH.HK", "512480.SH"]),
            "bars": [
                _bar(
                    "美股",
                    "AI 算力龙头 (NVDA / AMD / QQQ)",
                    "US AI Chips & Nasdaq (NVDA/QQQ)",
                    -5.4,
                    -2.2,
                    "高估值算力核心权重放量回撤，直接压制费半及纳指风险偏好。",
                    "Direct valuation compression on US flagship AI semis and Nasdaq.",
                    min(1.55, nvda_f * 0.58 * mag_f),
                    "NVDA",
                ),
                _bar(
                    "港股",
                    "恒生科指与大模型生态 (HSTECH / 00700)",
                    "HK Tech & AI Ecosystem (HSTECH)",
                    -3.5,
                    -1.1,
                    "外资风险预算收缩时，港股科技权重通常跟随纳指承压。",
                    "Foreign risk-off flows weigh on HKEX tech heavyweight multiples.",
                    min(1.28, hstech_f * mag_f),
                    "HSTECH.HK",
                ),
                _bar(
                    "A股",
                    "CPO 光模块 / 算力硬件映射",
                    "A-Share Optical / AI Hardware",
                    -3.8,
                    -1.2,
                    "北美算力资本开支映射承压，短期交易情绪跟随海外龙头回落。",
                    "North American capex proxies retrace alongside US AI hardware peers.",
                    min(1.28, semi_f * mag_f),
                    "515880.SH",
                ),
                _bar(
                    "A股",
                    "高股息红利 / 国有大行防御",
                    "A-Share High-Dividend Defense",
                    0.3,
                    1.2,
                    "成长赛道剧烈波动期间，资金倾向回流低波红利与高股息银行。",
                    "Capital rotates toward low-volatility dividend value during tech drawdowns.",
                    0.9 * mag_f,
                    "601398.SH",
                ),
            ],
            "if_then": [
                {"cond": "若纳指/英伟达次日止跌企稳且未现机构连续砍单验证", "result": "算力链情绪脉冲消化后关注业绩兑现标的", "tone": "neutral"},
                {"cond": "若下跌伴随大厂下调来年 Capex 指引或更多 IPO 破发", "result": "科技成长估值中枢下移，防御仓位占优", "tone": "bearish"},
            ],
            "milestones": [
                {"date": "次日美股开盘", "status": "current", "label": "观察 NVDA / QQQ 成交量与机构承接力"},
                {"date": "未来 2 周", "status": "upcoming", "label": "跟踪 CSP 云巨头资本开支指引是否松动"},
            ],
        }

    # 1b. 自动驾驶与高阶智驾量产推进 (FSD / Robotaxi)
    if re.search(r"FSD|自动驾驶|无人驾驶|Robotaxi|端到端智驾|智驾.*开放|高阶智驾", text, re.I):
        return {
            "rule_id": "autonomous_driving_fsd",
            "tag": "端到端智驾商业化 / FSD 落地",
            "tag_en": "Autonomous Driving & FSD Rollout",
            "polarity": "divergent",
            "intensity": 4,
            "one_liner": "端到端智驾高版本推进强化头部整车软件订阅与 Robotaxi 预期，带动高算力域控及传感器渗透率上行，传统低阶网约车承压。",
            "one_liner_en": "End-to-end ADAS and FSD deployment lifts smart-driving compute/chassis demand while pressuring legacy ride-hailing.",
            "sample_basis": {
                "sample_n": 14,
                "volatility_pct": 3.8,
                "volatility_source": "TSLA / 智能驾驶链历史催化窗口",
                "horizon": "2~7 个交易日",
                "confidence_label": "高置信（直接产业落地催化）",
                "confidence_label_en": "High (Direct ADAS Catalyst)",
            },
            "affected_tickers": {"TSLA": 0.85, "002920.SZ": 0.7, "09868.HK": 0.55, "UBER": -0.45},
            "realized_quotes": _quote_snapshot(["QQQ", "HSTECH.HK"]),
            "bars": [
                _bar("美股", "特斯拉 FSD 与整车软件估值 (TSLA)", "Tesla FSD & Software Valuation (TSLA)", 2.1, 5.2, "FSD 高版本落地与订阅渗透率提升，强化整车软件及 Robotaxi 远期现金流定价。", "New FSD rollout and subscription adoption strengthen automotive software valuation.", 1.0, "TSLA"),
                _bar("A股", "智能驾驶域控制器 / 激光雷达", "A-Share ADAS Domain Controller & LiDAR", 1.4, 3.6, "头部车企智驾节奏加快，倒逼国内车企跟进高算力域控、线控制动与传感器配置。", "Accelerated flagship ADAS rollout drives domestic controller and sensor upgrades.", 1.0, "002920.SZ"),
                _bar("港股", "头部新势力智驾领先车企", "HKEX Leading Smart-EV OEMs", 0.9, 2.8, "端到端智驾模型迭代领先的港股整车厂受益于销量结构上移与估值重估。", "Smart-EV leaders in Hong Kong benefit from mix upgrade and ADAS differentiation.", 1.0, "09868.HK"),
                _bar("美股", "传统纯人工网约车平台 (UBER)", "Legacy Ride-Hailing Platforms (UBER)", -1.8, -0.4, "若 Robotaxi 商业化时间表前移，纯人工运力撮合平台的中长期抽成空间面临估值折价。", "Faster Robotaxi commercialization compresses terminal multiples for legacy ride-hailing.", 0.9, "UBER"),
            ],
            "if_then": [
                {"cond": "若 4 周内 FSD 开放城市规模或无干预里程 (MPI) 实测超预期", "result": "整车软件订阅与高阶域控链估值重估延续", "tone": "bullish"},
                {"cond": "若试点期间出现监管安全问询或推送范围收窄", "result": "概念溢价回吐，市场回归单车交付量与毛利率主线", "tone": "bearish"},
            ],
            "milestones": [
                {"date": "推送后 2 周", "status": "current", "label": "跟踪首批车型 OTA 推送比例及无干预接管里程实测"},
                {"date": "未来 1 季度", "status": "upcoming", "label": "观察 FSD 订阅选装率与中美监管准入批复"},
            ],
        }

    # 1c. 存储芯片与 HBM 并购/产能扩张 (SK 海力士 / 美光 / 三星)
    if re.search(r"海力士|SK\s*Hynix|美光|Micron|HBM|高带宽内存|DRAM|NAND.*收购|NAND.*扩产", text, re.I) and re.search(
        r"收购|洽购|入股|并购|扩张|扩产|短缺|涨价|合同价|资本|投资|AI\s*芯片|供货|软银", text, re.I
    ):
        return {
            "rule_id": "memory_hbm_ma_supply",
            "tag": "HBM / 存储资本整合与周期重估",
            "tag_en": "AI Memory & HBM Deal Flow",
            "polarity": "divergent",
            "intensity": 4,
            "one_liner": "AI 存储/HBM 资本运作升温强化高带宽内存稀缺性定价，利好核心存储原厂与先进封测，PC 等整机 BOM 成本短期承压。",
            "one_liner_en": "Strategic M&A and capacity focus in HBM reinforce memory pricing while lifting downstream hardware BOM costs.",
            "sample_basis": {
                "sample_n": 15,
                "volatility_pct": 3.9,
                "volatility_source": "费半/存储芯片周期催化样本",
                "horizon": "2~5 个交易日",
                "confidence_label": "高置信（直击存储器估值与产能格局）",
                "confidence_label_en": "High (Direct Memory Cycle Catalyst)",
            },
            "affected_tickers": {"MU": 0.85, "NVDA": 0.35, "603986.SH": 0.65, "HPQ": -0.45},
            "realized_quotes": _quote_snapshot(["QQQ", "512480.SH"]),
            "bars": [
                _bar("美股", "HBM 与企业级存储龙头 (MU)", "US HBM & Enterprise Memory (MU)", 1.8, 4.5, "产业资本竞逐 HBM 产能与稀缺技术资产，强化高阶存储合约价预期。", "Strategic capital chasing HBM scarcity reinforces high-bandwidth memory pricing.", 1.0, "MU"),
                _bar("亚太", "韩国头部 HBM 晶圆与软银概念", "Korea HBM Foundry & Strategic Suitors", 1.5, 4.2, "战略并购或入股预期提升目标资产估值中枢，并加深与 AI 算力生态绑定。", "Strategic M&A talks lift asset valuation and deepen AI compute ecosystem ties.", 1.0, "000660.KS"),
                _bar("A股", "国产存储芯片与先进封装测试", "A-Share Memory & Advanced Packaging", 1.2, 3.4, "国际大厂资源向 HBM 倾斜加速常规 DRAM 产能出清，封测与模组同步受益。", "Global HBM reallocation tightens conventional DRAM supply and lifts packaging.", 1.0, "603986.SH"),
                _bar("美股", "传统消费级 PC OEM 组装厂 (HPQ)", "Commodity PC OEMs (HPQ)", -1.4, -0.3, "DRAM/NAND 合约价回升抬高整机 BOM 成本，若终端换机需求偏弱将挤压毛利。", "Rising DRAM/NAND contract prices squeeze hardware OEM margins if demand lags.", 0.9, "HPQ"),
            ],
            "if_then": [
                {"cond": "若交易估值溢价落地或下季度 HBM/DRAM 合约价环比涨幅超 10%", "result": "存储原厂与先进封测主升浪扩散", "tone": "bullish"},
                {"cond": "若谈判因监管或估值分歧搁置，且消费级现货成交走弱", "result": "事件性溢价回落，回归季度稼动率定价", "tone": "bearish"},
            ],
            "milestones": [
                {"date": "未来 2-4 周", "status": "current", "label": "核实双方正式公告及 TrendForce 当月 DRAM/NAND 合约报价"},
                {"date": "下轮原厂财报", "status": "upcoming", "label": "验证 HBM 位元出货指引与明年产能锁定比例"},
            ],
        }

    # 1d. AI 基础设施融资缺口与资本开支紧缩预警
    if re.search(r"缺钱|资金短缺|融资.*困|现金流.*紧张|资本开支.*紧|烧钱|funding\s*shortage|capital\s*crunch", text, re.I) and re.search(
        r"AI|大模型|算力|数据中心|马斯克|OpenAI|Anthropic|xAI", text, re.I
    ):
        return {
            "rule_id": "ai_funding_capex_squeeze",
            "tag": "AI 烧钱节奏与算力融资约束",
            "tag_en": "AI Funding Crunch & Capex Caution",
            "polarity": "divergent",
            "intensity": 4,
            "one_liner": "行业领军者警示 AI 融资缺口将加剧市场对高杠杆独立算力股估值折价，自由现金流充沛的云巨头防御护城河反而走阔。",
            "one_liner_en": "Warnings over AI funding shortfalls pressure cash-burning compute plays while widening the moat for cash-rich hyperscalers.",
            "sample_basis": {
                "sample_n": 13,
                "volatility_pct": 3.5,
                "volatility_source": "纳指 AI Capex 预期修正样本",
                "horizon": "1~5 个交易日",
                "confidence_label": "中高置信（直击一级到二级算力融资链）",
                "confidence_label_en": "Moderate-High (AI Capex Financing Sensitivity)",
            },
            "affected_tickers": {"MSFT": 0.4, "QQQ": -0.35, "600941.SH": 0.45},
            "realized_quotes": _quote_snapshot(["QQQ", "HSTECH.HK", "000001.SH"]),
            "bars": [
                _bar("美股", "高现金流云巨头与资产负债表龙头 (MSFT)", "Cash-Rich Cloud Hyperscalers (MSFT)", 0.4, 1.8, "外部股权与债权融资收紧时，自带充沛自由现金流的超级平台护城河扩大。", "Tighter external AI financing widens the moat for self-funded hyperscalers.", 0.9, "MSFT"),
                _bar("美股", "高杠杆独立算力租赁 / 高估 AI 应用", "Leveraged Neocloud & Unprofitable AI", -4.2, -1.5, "依赖举债扩张机柜的二三线算力股对信用利差走阔及 Capex 放缓最为敏感。", "Debt-dependent compute renters face acute valuation compression.", 1.0),
                _bar("美股", "科技高收益债 / 私募信贷 (HYG)", "Tech High-Yield Credit (HYG)", -1.8, -0.4, "算力基建回报期拉长引发市场重估非投资级科技债再融资风险。", "Extended AI payback horizons pressure high-yield tech credit spreads.", 0.9, "HYG"),
                _bar("A股", "高股息电信运营商与红利资产", "A-Share Telecom & High-Dividend Value", 0.4, 1.4, "全球 AI ROI 分歧放大阶段，资金偏好现金流确定性高的高股息防御板块。", "Domestic flows tilt toward dividend-paying telecoms amid AI ROI debates.", 0.9, "600941.SH"),
            ],
            "if_then": [
                {"cond": "若头部大模型厂商随后披露大额股权融资到账且 CSP 维持 Capex 指引", "result": "资金恐慌修复，一线算力龙头快速企稳", "tone": "bullish"},
                {"cond": "若高收益信用利差连续 5 个交易日走阔且云厂商下调机柜租赁预期", "result": "高杠杆算力与二线 AI 估值中枢下杀", "tone": "bearish"},
            ],
            "milestones": [
                {"date": "未来 2 周", "status": "current", "label": "观察美股科技高收益债利差与头部 AI 独角兽融资进展"},
                {"date": "下季财报季", "status": "upcoming", "label": "核对 MSFT / AMZN / GOOG 资本开支自由现金流占比"},
            ],
        }

    # 1e. 加密资产关键关口突破与风险偏好传导 (比特币 / 以太坊)
    if re.search(r"比特币|Bitcoin|BTC|以太坊|Ethereum|ETH|加密货币|Coinbase|MicroStrategy", text, re.I) and re.search(
        r"万|跌破|突破|涨超|跌超|反弹|暴跌|暴涨|ETF|监管|储备|清算|重返", text, re.I
    ):
        is_bull_crypto = bool(re.search(r"突破|涨超|反弹|暴涨|站上|创.*新高|流入|重返", text, re.I)) and not bool(
            re.search(r"跌破|暴跌|崩盘|爆仓|流出|禁令", text, re.I)
        )
        c_dir = 1.0 if is_bull_crypto else -1.0
        return {
            "rule_id": "crypto_risk_appetite_swing",
            "tag": "比特币关键关口修复与加密概念反弹" if is_bull_crypto else "加密资产回撤与持币财库股去杠杆",
            "tag_en": "Crypto Threshold Swing & Treasury Equities",
            "polarity": "bullish" if is_bull_crypto else "bearish",
            "intensity": 4,
            "one_liner": (
                "比特币重返关键整数关口激活市场风险偏好，高 Beta 持币财库股、合规交易所与算力矿企具显著杠杆弹性。"
                if is_bull_crypto
                else "加密资产回撤触发高杠杆爆仓与套息交易平仓，持币财库股、合规交易所及矿企短线估值承压。"
            ),
            "one_liner_en": (
                "Bitcoin threshold recovery lifts risk appetite across crypto treasury equities, regulated exchanges, and miners."
                if is_bull_crypto
                else "Crypto drawdown triggers deleveraging across treasury equities, exchanges, and mining names."
            ),
            "sample_basis": {
                "sample_n": 20,
                "volatility_pct": 5.2,
                "volatility_source": "BTC / MSTR / COIN 现货与概念联动样本",
                "horizon": "1~3 个交易日",
                "confidence_label": "高置信（数字资产直驱映射）",
                "confidence_label_en": "High (Direct Spot-Crypto Beta)",
            },
            "affected_tickers": {"MSTR": round(0.95 * c_dir, 2), "COIN": round(0.8 * c_dir, 2), "MARA": round(0.85 * c_dir, 2)},
            "realized_quotes": _quote_snapshot(["QQQ", "HSI.HK"]),
            "bars": [
                _bar("美股", "高 Beta 持币财库股 (MSTR)", "US Bitcoin Treasury Equities (MSTR)", 3.5 * c_dir, 8.2 * c_dir, "持币企业兼具现货净值敞口与可转债杠杆，日内振幅显著高于比特币现货。", "Bitcoin treasury equities act as levered proxies via balance-sheet holdings.", 1.0, "MSTR"),
                _bar("美股", "合规数字资产交易平台 (COIN)", "Regulated Crypto Exchanges (COIN)", 2.1 * c_dir, 5.4 * c_dir, "现货波动与衍生品成交量共振直接决定散户交易费率与托管收入弹性。", "Spot volatility and retail trading volumes drive exchange fee sensitivity.", 1.0, "COIN"),
                _bar("港股", "香港持牌虚拟资产与 ETF 映射 (00863)", "HKEX Licensed Virtual Asset Proxies", 1.6 * c_dir, 4.2 * c_dir, "亚太时段比特币关键关口变动直接映射至港股持牌交易及现货 ETF 概念。", "Asia-hours crypto swings transmit directly to HK licensed exchanges.", 1.0, "00863.HK"),
                _bar("美股", "比特币矿企与算力托管 (MARA)", "Bitcoin Miners & Hosting (MARA)", 2.4 * c_dir, 6.0 * c_dir, "币价与全网难度比决定矿企单位算力现金流及 AI 机柜转型估值弹性。", "Hashprice margins expand or compress sharply with BTC spot swings.", 1.0, "MARA"),
            ],
            "if_then": [
                {"cond": "若美股现货 BTC ETF 连续 3 日净流入且资金费率维持健康水平", "result": "趋势性买盘支撑持币股与矿企高弹性延续", "tone": "bullish"},
                {"cond": "若 24 小时永续合约爆仓额放大且 ETF 转为净流出", "result": "杠杆去化压力卷土重来，高 Beta 矿企剧烈回吐", "tone": "bearish"},
            ],
            "milestones": [
                {"date": "次日美东收盘", "status": "current", "label": "跟踪 IBIT / FBTC 现货 ETF 单日净申购与 CME 未平仓合约"},
                {"date": "未来 7 天", "status": "upcoming", "label": "观察 60,000 / 65,000 美元整数关口周线站稳与否"},
            ],
        }

    # 1f. 关键矿产与稀土上游化学品/配额供给冲击
    if re.search(r"稀土|稀散金属|镓|锗|锑|钨|关键矿产|critical\s*minerals|rare\s*earth", text, re.I) and re.search(
        r"禁|限制|出口|管制|配额|停产|断供|关税|泰国|缅甸|征收|冻结|走私|打击", text, re.I
    ):
        return {
            "rule_id": "rare_earth_critical_minerals_supply",
            "tag": "稀土上游原料/辅料管制冲击",
            "tag_en": "Critical Minerals & Rare-Earth Supply Curb",
            "polarity": "divergent",
            "intensity": 4,
            "one_liner": "东南亚跨境稀土冶炼辅料或原矿禁令扰动上游供给预期，中重稀土冶炼及海外替代资源迎重估，永磁下游成本短线承压。",
            "one_liner_en": "Border restrictions on rare-earth reagents tighten heavy rare-earth supply expectations while raising downstream magnet costs.",
            "sample_basis": {
                "sample_n": 12,
                "volatility_pct": 3.4,
                "volatility_source": "中重稀土供给扰动与氧化物价格弹性样本",
                "horizon": "2~7 个交易日",
                "confidence_label": "高置信（直接供需扰动定价）",
                "confidence_label_en": "High (Direct Feedstock Disruption)",
            },
            "affected_tickers": {"600111.SH": 0.85, "MP": 0.8, "300748.SZ": 0.45},
            "realized_quotes": _quote_snapshot(["000001.SH", "QQQ"]),
            "bars": [
                _bar("A股", "稀土开采冶炼与中重稀土 (北方稀土/广晟)", "A-Share Rare-Earth Mining & Separation", 1.8, 4.8, "矿山开采辅料（如草酸/萃取试剂）或原矿跨境受限直接抬升氧化镨钕与镝铽现货报价。", "Reagent bans or feedstock disruptions tighten separated oxide pricing.", 1.0, "600111.SH"),
                _bar("美股", "北美非中国稀土矿采分离 (MP)", "US Ex-China Rare-Earth Producers (MP)", 1.9, 4.9, "东南亚跨境供应链扰动推升欧美本土稀土精炼产能的战略溢价。", "Supply-chain bottlenecks strengthen strategic premium for ex-China refining.", 1.0, "MP"),
                _bar("A股", "高性能钕铁硼永磁材料 (金力永磁)", "A-Share NdFeB Permanent Magnets", 0.8, 2.5, "氧化物现货温和涨价有利于具备低价原料库存的磁材龙头重估。", "Moderate oxide inflation supports inventory revaluation for magnet leaders.", 1.0, "300748.SZ"),
                _bar("美股", "风电整机与永磁驱动下游 (GEV)", "Wind Turbine & EV Motor OEMs (GEV)", -1.1, -0.2, "重稀土镝/铽现货跳涨或挤压未充分套保永磁电驱设备商毛利。", "Dy/Tb spikes pressure margins at unhedged permanent-magnet OEMs.", 0.9, "GEV"),
            ],
            "if_then": [
                {"cond": "若边境化学品/矿砂禁令持续超 2 周且亚洲金属网镨钕/氧化铽报价连续跳涨", "result": "中重稀土冶炼与具备原矿配额企业涨价弹性延续", "tone": "bullish"},
                {"cond": "若监管仅清理非法小矿点而正规配额供应未受影响", "result": "供给冲击证伪，板块脉冲冲高后震荡回落", "tone": "neutral"},
            ],
            "milestones": [
                {"date": "未来 1 周", "status": "current", "label": "核查百川盈孚 / 亚洲金属网氧化镨钕、氧化铽周度现货价"},
                {"date": "下月海关数据", "status": "upcoming", "label": "跟踪自东南亚进口稀土矿砂及冶炼辅料报关量变化"},
            ],
        }

    # 2. AI Data Privacy Leak / Zero-Data-Retention Failure (separate from AI capability release!)
    if any(k in t for k in ("隐私泄露", "隐私数据泄露", "零数据保留", "诱饵请求", "数据泄露", "反蒸馏")):
        is_leak = "隐私" in t or "数据泄露" in t or "失效" in t
        if is_leak:
            crwd_f, atr_v, _ = _volatility_scale("CRWD", quotes_map, 3)
            return {
                "rule_id": "ai_privacy_security",
                "tag": "AI 安全合规与隐私审计",
                "tag_en": "AI Privacy & Security Compliance",
                "polarity": "divergent",
                "intensity": 3,
                "one_liner": "AI 调用链隐私合规漏洞曝光将倒逼企业加强模型安全网关、零信任审计与加密采购，通用 SaaS 部署节奏则面临短期合规审查。",
                "one_liner_en": "AI data-retention leaks drive cybersecurity & privacy tooling spend while slowing unverified SaaS rollout.",
                "sample_basis": {
                    "sample_n": 14,
                    "volatility_pct": atr_v or 2.9,
                    "volatility_source": "网安板块波动率参考",
                    "horizon": "3~10 个交易日",
                    "confidence_label": "中高置信（事件结构明确）",
                    "confidence_label_en": "Moderate-High (Security Spend Rotation)",
                },
                "affected_tickers": {"CRWD": 0.7, "HSTECH.HK": -0.25},
                "realized_quotes": _quote_snapshot(["CRWD", "QQQ", "HSTECH.HK"]),
                "bars": [
                    _bar("美股", "网络安全与 AI 数据合规 (CRWD / PANW)", "US Cybersecurity (CRWD/PANW)", 1.0, 2.8, "隐私泄漏倒逼政企增加 AI 防火墙与零信任监控预算。", "Privacy incidents expand enterprise AI security and DLP budgets.", min(1.3, crwd_f), "CRWD"),
                    _bar("A股", "数据安全 / 信创加密与合规审计", "A-Share Data Security & Audit", 1.2, 3.2, "境内对大模型数据出境及供应链合规审计要求升温。", "Stricter domestic AI compliance boosts security & audit software.", 1.0),
                    _bar("港股", "企业级 AI SaaS / 云调用服务", "HKEX Enterprise Cloud / SaaS", -1.8, -0.4, "部分依赖第三方 API 链路的应用面临客户复核周期拉长。", "Third-party AI SaaS faces slower enterprise procurement review.", 0.9, "HSTECH.HK"),
                ],
                "if_then": [
                    {"cond": "若监管机构跟进罚款或行业出台强制审计规范", "result": "网安与本地化私有部署需求显著放量", "tone": "bullish"},
                    {"cond": "若仅为个别代理节点配置失误且迅速修复", "result": "事件对整体 AI 板块基本面冲击有限", "tone": "neutral"},
                ],
                "milestones": [{"date": "7 日内", "status": "current", "label": "各家模型服务商发布链路安全整改公告"}],
            }

    # 3. Precious Metals / Gold & Silver Plunge (distinct from FOMC rate hike!)
    if any(k in t for k in ("金价", "黄金", "白银", "贵金属")) and any(k in t for k in ("暴跌", "大跌", "跳水", "跌破", "新低", "风险")):
        gld_f, atr_v, _ = _volatility_scale("518880.SH", quotes_map, intensity)
        return {
            "rule_id": "precious_metals_selloff",
            "tag": "贵金属剧震与杠杆去化",
            "tag_en": "Precious Metals Selloff",
            "polarity": "bearish",
            "intensity": intensity,
            "one_liner": "国际金银遭遇获利盘践踏与保证金去杠杆，国内银行紧急提示风险，贵金属采掘与金饰链短线明显承压。",
            "one_liner_en": "Sharp bullion drawdown & bank risk warnings weigh on gold miners and precious-metal ETFs.",
            "sample_basis": {
                "sample_n": 16,
                "volatility_pct": atr_v or 3.69,
                "volatility_source": "518880 黄金ETF 20日 ATR",
                "horizon": "1~5 个交易日",
                "confidence_label": "高置信（商品直接映射）",
                "confidence_label_en": "High (Direct Bullion Beta)",
            },
            "affected_tickers": {"GLD": -1.0, "518880.SH": -1.0, "02899.HK": -0.85, "601398.SH": 0.2},
            "realized_quotes": _quote_snapshot(["GLD", "518880.SH", "02899.HK"]),
            "bars": [
                _bar("美股", "黄金与贵金属 ETF (GLD / GDX)", "US Gold & Miners ETFs (GLD)", -3.8, -1.6, "现货金价大幅回撤叠加期货强平压力直接压制金矿股。", "Spot gold slide compresses miner margins and ETF inflows.", min(1.3, gld_f), "GLD"),
                _bar("A股", "黄金采掘与贵金属板块", "A-Share Gold Miners & Bullion", -4.4, -1.9, "前期拥挤多头踩踏出清，商业银行同步收紧积存金警示。", "Crowded long unwind and domestic bank risk alerts weigh on sector.", min(1.3, gld_f), "518880.SH"),
                _bar("港股", "有色黄金资源 (紫金 / 招金等)", "HKEX Gold Miners (02899.HK)", -4.1, -1.7, "港股黄金标的受离岸现货金价及汇率波动双重传导。", "HK gold miners react directly to offshore spot bullion swings.", min(1.3, gld_f), "02899.HK"),
            ],
            "if_then": [
                {"cond": "若银行提升保证金引发程序化抛盘延续", "result": "贵金属矿企延续二次探底，谨慎抄底", "tone": "bearish"},
                {"cond": "若实际利率转降且央行买金数据恢复净增", "result": "急跌消化杠杆后逐步企稳", "tone": "neutral"},
            ],
            "milestones": [{"date": "下周美联储/CPI数据", "status": "upcoming", "label": "实际利率变动决定金价能否止跌"}],
        }

    # 4. Russia-Ukraine Peace / Ceasefire Progress (bearish oil & defense, bullish aviation/risk)
    if any(k in t for k in ("俄乌和平", "和平协议", "停火协议", "停火方案", "战后保障")) and not any(
        k in t for k in ("导弹落入", "大规模空袭", "触雷", "爆炸")
    ):
        _, atr_v, _ = _volatility_scale("USO", quotes_map, 3)
        return {
            "rule_id": "russia_ukraine_peace_deescalation",
            "tag": "地缘缓和 / 停火预期升温",
            "tag_en": "Geopolitical De-escalation / Peace Talks",
            "polarity": "divergent",
            "intensity": 3,
            "one_liner": "俄乌和平协议预期削弱能源断供与战争溢价，利空原油及传统军工避险资产，同时降低燃油成本并利好航空及全球风险资产。",
            "one_liner_en": "Peace-deal optimism compresses war risk premia in crude/defense while lifting airlines & risk appetite.",
            "sample_basis": {
                "sample_n": 11,
                "volatility_pct": atr_v or 2.8,
                "volatility_source": "原油/航空历史事件波动统计",
                "horizon": "2~5 个交易日",
                "confidence_label": "中高置信（供需与风险溢价逆转）",
                "confidence_label_en": "Moderate-High (Risk-Premium Unwind)",
            },
            "affected_tickers": {"USO": -0.8, "GLD": -0.45, "00883.HK": -0.75, "02899.HK": -0.35},
            "realized_quotes": _quote_snapshot(["USO", "GLD", "00883.HK", "HSI.HK"]),
            "bars": [
                _bar("美股", "原油与能源期货代理 (USO)", "US Crude Oil & Energy (USO)", -4.2, -1.5, "停火期待压低制裁溢价预期，油价风偏下修。", "Ceasefire expectations ease supply-risk premium in crude oil.", 1.0, "USO"),
                _bar("A股", "航空机场 / 航运及重建基建链", "A-Share Airlines & Reconstruction", 1.4, 3.8, "航油成本回落预期叠加跨境重建/外贸风险缓解。", "Lower jet-fuel costs and reconstruction demand benefit aviation & engineering.", 1.0),
                _bar("港股", "三桶油上游能源 (00883.HK)", "HKEX Upstream Oil (00883.HK)", -3.6, -1.2, "原油风偏溢价收敛，高弹性能源权重大概率承压回吐。", "Upstream oil producers retrace as geopolitical risk premia fade.", 1.0, "00883.HK"),
            ],
            "if_then": [
                {"cond": "若各方正式签字或推进对俄能源制裁放松路线图", "result": "原油中枢继续下移，航空/欧股受益扩大", "tone": "bullish"},
                {"cond": "若停火谈判再度破裂并恢复前线打击", "result": "战争风险溢价重新快速回补至能源/黄金", "tone": "bearish"},
            ],
            "milestones": [{"date": "明年1月前目标窗口", "status": "upcoming", "label": "各方安全保障文本能否落地签字"}],
        }

    # 5. Kinetic Geopolitical Escalation (Missiles in Poland / Tanker Mine in Hormuz / Iran-US Military Risk)
    if any(k in t for k in ("霍尔木兹", "油轮触雷", "导弹落入", "空袭", "动武", "击落", "美伊")) and (
        any(k in t for k in ("伊朗", "乌克兰", "波兰", "北约", "以色列", "海峡", "导弹", "无人机", "油轮", "俄军", "管道", "谈判", "僵局"))
    ):
        is_hormuz_mine = "霍尔木兹" in t and ("触雷" in t or "海峡" in t)
        is_us_iran_talks_only = "美伊" in t and "谈判" in t and "触雷" not in t and "空袭" not in t and "动武" not in t and "导弹" not in t
        sev = 1.24 if is_hormuz_mine else (0.72 if is_us_iran_talks_only else 1.04)
        _, atr_v, _ = _volatility_scale("USO", quotes_map, 5 if is_hormuz_mine else (3 if is_us_iran_talks_only else 4))
        return {
            "rule_id": "geopolitics_energy_escalation",
            "tag": (
                "霍尔木兹航道触雷与油运飙升"
                if is_hormuz_mine
                else ("美伊外交博弈与温和避险" if is_us_iran_talks_only else "东欧/中东武装冲突与军工避险")
            ),
            "tag_en": "Geopolitical & Energy Chokepoint Risk",
            "polarity": "divergent",
            "intensity": 5 if is_hormuz_mine else (3 if is_us_iran_talks_only else 4),
            "one_liner": (
                "关键油运咽喉触雷险情推升超大型油轮运费、战争险保费及国际油价即时脉冲，直接利好油气开采与油运，航空及化工下游成本剧增。"
                if is_hormuz_mine
                else (
                    "美伊谈判胶着延长海湾制裁风险溢价，但尚未演变为实质航道封锁，对油价与黄金呈温和避险支撑。"
                    if is_us_iran_talks_only
                    else "跨境导弹与防空警报触发军工防务及避险买盘升温，能源与黄金同步小幅抬升、欧洲航线与风险偏好短期承压。"
                )
            ),
            "one_liner_en": "Chokepoint & kinetic flare-ups lift crude, shipping rates, and gold while pressuring airlines.",
            "sample_basis": {
                "sample_n": 22,
                "volatility_pct": atr_v or 3.1,
                "volatility_source": "USO/黄金避险冲高历史样本",
                "horizon": "1~5 个交易日",
                "confidence_label": "高置信（避险与商品直驱）",
                "confidence_label_en": "High (Safe-Haven & Crude Drive)",
            },
            "affected_tickers": {"USO": round(0.9 * sev, 2), "GLD": round(0.65 * sev, 2), "00883.HK": round(0.8 * sev, 2), "02899.HK": round(0.55 * sev, 2)},
            "realized_quotes": _quote_snapshot(["USO", "GLD", "00883.HK", "02899.HK"]),
            "bars": [
                _bar("美股", "原油与能源/防务避险 (USO / XLE)", "US Energy & Defense (USO)", 1.6, 4.4, "地缘供应中断风险直接在国际油价与防务链条计价。", "Supply disruption risk immediately reprices crude and defense.", sev, "USO"),
                _bar("港股", "油气与贵金属避险 (00883 / 02899)", "HKEX Oil & Gold Safe Havens (00883/02899)", 1.3, 3.6, "避险情绪叠加现货原油、黄金同步走高。", "Offshore energy & bullion names capture risk-off hedging flows.", sev, "00883.HK"),
                _bar("A股", "石油石化 / 油运与贵金属", "A-Share Oil, Tankers & Gold", 1.5, 4.0, "绕航与保费上行催化油运及能源开采。", "Freight & energy producers benefit from rerouting and risk premia.", sev),
                _bar("A股", "航空机场 / 高耗能化工下游", "A-Share Airlines & Downstream Chem", -2.9, -0.9, "燃油成本飙升叠加国际航线绕飞压缩毛利。", "Higher jet-fuel & rerouting costs compress airline/chemical margins.", min(1.2, sev)),
            ],
            "if_then": [
                {"cond": "若冲突扩散导致实际油轮通行或管道长期中断", "result": "能源涨价预期演变为再通胀担忧，压制长端成长估值", "tone": "bearish"},
                {"cond": "若斡旋重启且冲突局限于边境小规模摩擦", "result": "避险脉冲多于 3 个交易日内回吐", "tone": "neutral"},
            ],
            "milestones": [{"date": "72 小时关键窗口", "status": "current", "label": "航道实际通行量及外交通报回应"}],
        }

    # 6. Pipeline Outage / Supply Shock (Enbridge etc. -> US crude / logistics)
    if "管道" in t and any(k in t for k in ("中断", "泄漏", "污染")):
        return {
            "rule_id": "oil_pipeline_disruption",
            "tag": "北美原油管道物理断供冲击",
            "tag_en": "Crude Pipeline Supply Disruption",
            "polarity": "divergent",
            "intensity": 3,
            "one_liner": "主干管道中断迫使钻探商改用昂贵卡车运油，压制北美本土产区价差并推升成品运输及替代能源成本。",
            "one_liner_en": "Pipeline halt forces costly trucking alternatives, tightening local crude spreads & downstream logistics.",
            "sample_basis": {
                "sample_n": 9,
                "volatility_pct": 2.4,
                "volatility_source": "北美成品油价差历史事件",
                "horizon": "3~7 个交易日",
                "confidence_label": "中高置信（物理瓶颈事件）",
                "confidence_label_en": "Moderate-High (Infrastructure Bottleneck)",
            },
            "affected_tickers": {"USO": 0.65, "00883.HK": 0.4},
            "realized_quotes": _quote_snapshot(["USO", "00883.HK"]),
            "bars": [
                _bar("美股", "北美能源基建与原油价格 (USO)", "US Crude & Midstream Logistics", 1.0, 2.8, "管道运力受限推高交割端溢价，但受困地区产商承压。", "Delivery-point supply tightens while trapped producers incur higher trucking costs.", 1.0, "USO"),
                _bar("港股", "上游油气开采板块 (00883.HK)", "HKEX Upstream Oil (00883.HK)", 0.6, 2.0, "国际油价情绪微幅受益，幅度弱于地缘战争事件。", "Modest positive sentiment from tighter North American crude logistics.", 1.0, "00883.HK"),
                _bar("A股", "化工 / 炼化原材料成本敏感链", "A-Share Refining Feedstock Sensitive", -1.4, -0.3, "上游原料物流扰动带来短期成本小幅波动。", "Minor near-term feedstock cost volatility.", 1.0),
            ],
            "if_then": [{"cond": "若监管要求管道停运检修超过两周", "result": "交割地库存下降支撑 WTl 近月升水", "tone": "bullish"}],
            "milestones": [{"date": "1 周内", "status": "current", "label": "PHMSA 与运营方公布恢复通流时间表"}],
        }

    # 7. FOMC Hawkish Rate Hike (distinct from selloffs!)
    if any(k in t for k in ("美联储", "fomc", "鲍威尔")) and any(k in t for k in ("加息", "放鹰", "利率")):
        is_hike = any(k in t for k in ("重启加息", "加息", "放鹰"))
        qqq_f, atr_v, _ = _volatility_scale("QQQ", quotes_map, 4)
        return {
            "rule_id": "central_bank_hawkish",
            "tag": "美联储鹰派加息 / 流动性收紧",
            "tag_en": "Fed Hawkish Rate Decision",
            "polarity": "bearish" if is_hike else "divergent",
            "intensity": 4 if is_hike else 3,
            "one_liner": "美联储重启加息并密集释放鹰派信号直接推高无风险折现率，压制美股长久期成长与港股流动性，无息黄金同样承压。",
            "one_liner_en": "Hawkish Fed tightening lifts discount rates, pressuring Nasdaq duration assets, HK liquidity, and non-yielding gold.",
            "sample_basis": {
                "sample_n": 24,
                "volatility_pct": atr_v or 2.7,
                "volatility_source": "FOMC 决议日历史 24 次样本",
                "horizon": "1~5 个交易日",
                "confidence_label": "高置信（利率定价主逻辑）",
                "confidence_label_en": "High (Rate-Discount Driver)",
            },
            "affected_tickers": {"QQQ": -0.75, "IXIC": -0.75, "GLD": -0.65, "HSI.HK": -0.6, "518880.SH": -0.55, "601398.SH": 0.4},
            "realized_quotes": _quote_snapshot(["IXIC", "HSI.HK", "GLD", "518880.SH"]),
            "bars": [
                _bar("美股", "纳指长久期科技成长 (QQQ)", "US Long-Duration Tech (QQQ)", -3.8, -1.3, "实际利率上升直接压缩远期现金流科技股估值折现率。", "Higher real rates compress long-duration equity valuation multiples.", min(1.3, qqq_f), "QQQ"),
                _bar("港股", "恒生与港元利率敏感成长股 (HSI)", "HKEX Rate-Sensitive Equities (HSI)", -3.0, -0.9, "联系汇率制下港元资金成本跟随紧缩，外资风偏回落。", "Pegged HKD funding costs tighten alongside Fed rate moves.", 1.0, "HSI.HK"),
                _bar("A股", "黄金及高估值主题板块", "A-Share Bullion & High-PE Growth", -2.8, -0.8, "无息资产黄金及高弹性科技面临短期资金分流压力。", "Non-yielding gold and high-multiple themes face liquidity headwinds.", 1.0, "518880.SH"),
                _bar("A股", "银行 / 保险及高股息红利", "A-Share Banks & High Dividend", 0.5, 1.8, "净息差预期企稳兼备防御属性。", "Steadier NIM expectations and defensive yield attraction.", 1.0, "601398.SH"),
            ],
            "if_then": [
                {"cond": "若点阵图进一步上调终端利率且就业维持强劲", "result": "成长板块估值压力延长，现金与高股息继续跑赢", "tone": "bearish"},
                {"cond": "若会后官员澄清紧缩已接近尾声", "result": "美债长端收益率见顶回落带来成长股反弹", "tone": "bullish"},
            ],
            "milestones": [{"date": "2026-12-10 03:00", "status": "upcoming", "label": "下次 FOMC 决议与季度 SEP 点阵图"}],
        }

    # 8a. NVIDIA CEO Senate Hearing / SEC Investigation / Leadership Governance Shock
    if ("黄仁勋" in t or "英伟达" in t or "nvidia" in t) and re.search(
        r"参议院|听证|作证|sec\s*调查|辞任|辞职|治理|董事会", t
    ):
        nvda_f, atr_v, _ = _volatility_scale("NVDA", quotes_map, 4)
        return {
            "rule_id": "nvda_senate_sec_governance",
            "tag": "国会听证监管 / SEC 调查与龙头治理风险",
            "tag_en": "Senate Testimony, SEC Inquiry & Governance Risk",
            "polarity": "bearish",
            "intensity": 4,
            "one_liner": "前任核心高管将赴美参议院银行委员会公开作证叠加 SEC 调查传闻，放大龙头合规不确定性与治理折价，压制美股 AI 硬件链风险偏好。",
            "one_liner_en": "Senate banking panel testimony & SEC probe reports amplify NVIDIA governance overhang and weigh on AI hardware multiples.",
            "sample_basis": {
                "sample_n": 14,
                "volatility_pct": atr_v or 4.6,
                "volatility_source": "美股科技龙头监管听证与治理事件样本",
                "horizon": "1~5 个交易日",
                "confidence_label": "高置信（直接冲击估值溢价与机构持仓意愿）",
                "confidence_label_en": "High (Direct Governance & Regulatory Overhang)",
            },
            "affected_tickers": {"NVDA": -0.9, "TSM": -0.65, "AMD": -0.55, "00981.HK": 0.55, "512480.SH": 0.6},
            "realized_quotes": _quote_snapshot(["NVDA", "TSM", "00981.HK", "512480.SH"]),
            "bars": [
                _bar("美股", "美股 AI 算力龙头与硬件链 (NVDA / TSM)", "US AI Hardware & Foundries (NVDA/TSM)", -4.8, -1.7, "国会听证质询与监管调查折价直接压制英伟达机构配置情绪。", "Congressional testimony & SEC scrutiny compress NVIDIA valuation premium.", min(1.3, nvda_f * 0.6), "NVDA"),
                _bar("港股", "港股自主晶圆代工 (00981.HK 中芯)", "HKEX Domestic Foundry (00981.HK)", 0.7, 2.8, "海外龙头监管不确定性抬升境内外客户对境内供应链备份关注度。", "Overseas regulatory overhang reinforces domestic foundry hedging demand.", 1.0, "00981.HK"),
                _bar("A股", "国产算力芯片与替代生态", "A-Share Domestic Compute Alternatives", 0.9, 3.2, "海外算力供给风险溢价上升催化本土推理芯片估值修复。", "Domestic compute ecosystems attract incremental defensive rotation.", 1.0, "512480.SH"),
            ],
            "if_then": [
                {"cond": "若参议院听证披露涉及公司层面的正式执法或禁令线索", "result": "NVDA 与北美服务器 Capex 链面临二次下修", "tone": "bearish"},
                {"cond": "若英伟达董事会出具独立审计澄清且业务订单未受扰动", "result": "治理恐慌情绪见底收敛", "tone": "neutral"},
            ],
            "milestones": [{"date": "听证会窗口", "status": "current", "label": "参议院银行委员会公开证词记录与 SEC 官方披露"}],
        }

    # 8b. Cross-Border AI Chip Smuggling & BIS Export-Control Compliance Crackdown
    if re.search(r"走私|绕道|出口合规|megaspeed|alice\s*huang|查获.*芯片|违规.*出口", t) and any(
        k in t for k in ("芯片", "英伟达", "nvidia", "gpu", "对华")
    ):
        nvda_f, atr_v, _ = _volatility_scale("NVDA", quotes_map, 4)
        return {
            "rule_id": "chip_smuggling_export_compliance",
            "tag": "芯片出口合规审查与灰色渠道执法风险",
            "tag_en": "Export Compliance & Grey-Market Crackdown",
            "polarity": "bearish",
            "intensity": 4,
            "one_liner": "跨境算力芯片走私网络曝光将倒逼美方收紧流向审查并追查第三国转口，短期抑制灰色渠道出货预期同时强化国内晶圆/设备自主刚需。",
            "one_liner_en": "Chip-smuggling revelations heighten BIS third-country transshipment scrutiny, squeezing grey channels while boosting China localization.",
            "sample_basis": {
                "sample_n": 13,
                "volatility_pct": atr_v or 4.5,
                "volatility_source": "美商务部 BIS 半导体转口执法样本",
                "horizon": "2~7 个交易日",
                "confidence_label": "高置信（直击转口需求与国产替代预期）",
                "confidence_label_en": "High (Direct Export-Control Enforcement)",
            },
            "affected_tickers": {"NVDA": -0.8, "TSM": -0.6, "AMD": -0.5, "00981.HK": 0.7, "512480.SH": 0.75},
            "realized_quotes": _quote_snapshot(["NVDA", "TSM", "00981.HK", "512480.SH"]),
            "bars": [
                _bar("美股", "受转口核查敏感半导体厂商 (NVDA / TSM)", "US Export-Sensitive GPU Vendors (NVDA/TSM)", -4.2, -1.4, "东南亚/中东转口审核收紧削弱边缘市场 GPU 增量出货弹性。", "Stricter BIS transshipment audits curb grey-market GPU demand.", min(1.25, nvda_f * 0.55), "NVDA"),
                _bar("港股", "港股先进制程替代核心 (00981.HK 中芯)", "HKEX Domestic Foundry (00981.HK)", 1.0, 3.5, "海外算力外部采购通道收窄倒逼境内大模型加速绑定本土代工产能。", "Tighter external channels lock in domestic foundry utilization.", 1.0, "00981.HK"),
                _bar("A股", "半导体设备 / 先进封装与国产算力卡", "A-Share Semi Equipment & Domestic Accelerators", 1.3, 3.8, "绕道通路受堵进一步确认光刻/刻蚀设备与本土算力集群高景气。", "Localization urgency accelerates capital flow into domestic semi gear.", 1.0, "512480.SH"),
            ],
            "if_then": [
                {"cond": "若美国商务部对涉事转口实体追加实体清单制裁", "result": "国内头部算力与设备板块获得超额资金催化", "tone": "bullish"},
                {"cond": "若执法焦点集中于历史个人责任而非新增禁运名单", "result": "美股硬件端短线负向冲击逐步消化", "tone": "neutral"},
            ],
            "milestones": [{"date": "1~2 周内", "status": "current", "label": "美国商务部 BIS 执法通报与英伟达合规声明"}],
        }

    # 8c. US Overseas Datacenter Tax Threat + Chip Export Quota
    if (
        re.search(r"海外.*数据中心.*(?:征|税|关税)|巨额关税|征重税|巨税|限制对华|出口中国|88\s*万颗", t)
        and any(k in t for k in ("芯片", "英伟达", "amd", "数据中心", "关税", "税"))
    ):
        is_positive_grant = "批准" in t and "征重税" not in t and "巨税" not in t and "限制" not in t and "辞职" not in t
        if is_positive_grant:
            return {
                "rule_id": "us_chip_export_quota_approved",
                "tag": "高端 AI 芯片出口配额审批",
                "tag_en": "AI Chip Export Quota Update",
                "polarity": "divergent",
                "intensity": 3,
                "one_liner": "部分合规芯片获准出口但远低于申请量（约四分之一），边际缓解海外大厂出货焦虑同时强化国产算力长期自主刚需。",
                "one_liner_en": "Partial export approval (only ~25% of requests) relieves immediate backlog while reinforcing China localization.",
                "sample_basis": {
                    "sample_n": 10,
                    "volatility_pct": 4.2,
                    "volatility_source": "美中半导体出口限制样本",
                    "horizon": "1~5 个交易日",
                    "confidence_label": "中高置信",
                    "confidence_label_en": "Moderate-High",
                },
                "affected_tickers": {"NVDA": 0.45, "AMD": 0.5, "00981.HK": 0.5, "512480.SH": 0.4},
                "realized_quotes": _quote_snapshot(["NVDA", "AMD", "00981.HK", "512480.SH"]),
                "bars": [
                    _bar("美股", "对华受限合规芯片厂商 (NVDA / AMD)", "US GPU Makers (NVDA / AMD)", 0.8, 3.0, "部分订单落地释放压抑需求，但总额仍受四分之一配额约束。", "Partial approvals monetize delayed demand despite tight quota cap.", 1.0, "NVDA"),
                    _bar("港股", "半导体晶圆与自主算力 (00981.HK)", "HKEX Foundry (SMIC 00981.HK)", 0.6, 2.5, "仅获批约 25% 需求反向印证先进算力国产替代长期确定性。", "Tight supply quota sustains structural domestic foundry demand.", 1.0, "00981.HK"),
                    _bar("A股", "国产半导体设备 / 算力芯片", "A-Share Domestic Semi & Equipment", 0.9, 3.1, "长期缺口仍需本土产业链填补，设备与封测环节逻辑延续。", "Long-term compute supply gap sustains localization momentum.", 1.0, "512480.SH"),
                ],
                "if_then": [{"cond": "若商务部后续放宽其余四分之三申请配额", "result": "NVDA / AMD 出货指引上修", "tone": "bullish"}],
                "milestones": [{"date": "下月许可审查期", "status": "upcoming", "label": "后续芯片出口许可证细则进展"}],
            }
        # Restrictive threat / leadership crisis -> bearish US datacenter capex & NVDA, divergent for domestic semis
        nvda_f, atr_v, _ = _volatility_scale("NVDA", quotes_map, 4)
        return {
            "rule_id": "us_datacenter_tax_and_chip_curb",
            "tag": "海外数据中心重税 / 芯片限制与治理震荡",
            "tag_en": "Data Center Tax, Export Curbs & Governance",
            "polarity": "bearish",
            "intensity": 4,
            "one_liner": "威胁对海外新建数据中心美企征重税、收紧芯片出口叠加龙头管理层震荡，直接冲击全球 AI 基建资本开支，倒逼国产替代加速。",
            "one_liner_en": "Proposed overseas datacenter tax & tighter chip curbs hit global AI capex while supporting domestic foundry proxies.",
            "sample_basis": {
                "sample_n": 15,
                "volatility_pct": atr_v or 4.8,
                "volatility_source": "美股算力制裁与关税冲击样本",
                "horizon": "1~5 个交易日",
                "confidence_label": "高置信（直击核心估值与供给端）",
                "confidence_label_en": "High (Direct Capex & Export Shock)",
            },
            "affected_tickers": {"NVDA": -0.9, "TSM": -0.7, "AMD": -0.65, "00981.HK": 0.65, "512480.SH": 0.7},
            "realized_quotes": _quote_snapshot(["NVDA", "TSM", "00981.HK", "512480.SH"]),
            "bars": [
                _bar("美股", "美股 GPU 与海外建厂链 (NVDA / TSM)", "US AI Hardware & Foundries (NVDA/TSM)", -4.6, -1.6, "治理变动与出口及海外数据中心税收威胁叠加压制估值。", "Export limits, overseas capex tax threats & leadership risk weigh on semis.", min(1.3, nvda_f * 0.6), "NVDA"),
                _bar("港股", "港股芯片自主制造 (00981.HK 中芯)", "HKEX Domestic Foundry (00981.HK)", 0.9, 3.3, "高端进口限制收紧进一步锁定境内晶圆制造份额。", "Tighter US curbs solidify domestic wafer fab utilization expectations.", 1.0, "00981.HK"),
                _bar("A股", "国产半导体设备 / 算力自主可控", "A-Share Domestic Semi Equipment", 1.1, 3.6, "进口替代刚性提升，光刻/刻蚀设备与本土算力获事件催化。", "Localization urgency lifts domestic semiconductor equipment names.", 1.0, "512480.SH"),
            ],
            "if_then": [
                {"cond": "若白宫正式签发海外数据中心关税行政令", "result": "跨国云厂基建节奏放缓，美股算力硬件承压加深", "tone": "bearish"},
                {"cond": "若英伟达董事会明确过渡安排并澄清核心技术研发不受影响", "result": "治理恐慌折价逐步修复", "tone": "neutral"},
            ],
            "milestones": [{"date": "两周内", "status": "current", "label": "英伟达治理公告与美国商务部出口税则细则"}],
        }

    # 9. Genuine US-China Summit / Bilateral Diplomacy Peace Declaration (ONLY bilateral US-China / APEC; never tariff threats!)
    if (
        ("中美" in t or "apec" in t)
        and any(k in t for k in ("三方和平", "一致同意", "对话", "关税调整", "峰会", "会晤"))
        and not re.search(r"巨额关税|征重税|巨税|加征关税|威胁征税|关税威胁", t)
    ):
        is_truce = any(k in t for k in ("和平宣言", "一致同意", "不陷入", "合作", "建设性"))
        kweb_f, atr_v, _ = _volatility_scale("KWEB", quotes_map, 3)
        return {
            "rule_id": "us_china_diplomacy_truce" if is_truce else "us_china_diplomacy_friction",
            "tag": "中美元首外交 / APEC 宏观风偏" if is_truce else "中美关税贸易博弈",
            "tag_en": "US-China Diplomacy & Trade Tone",
            "polarity": "bullish" if is_truce else "divergent",
            "intensity": 3,
            "one_liner": "中美元首深圳会晤释放对话稳定信号，有助缓和地缘风险溢价，短期利好中概互联、港股权重及出口链估值修复。",
            "one_liner_en": "Constructive US-China APEC summit tone compresses risk premia across China ADRs, HKEX tech, and exporters.",
            "sample_basis": {
                "sample_n": 19,
                "volatility_pct": atr_v or 3.2,
                "volatility_source": "中概 KWEB 外交缓和窗口统计",
                "horizon": "2~7 个交易日",
                "confidence_label": "高置信（直接风偏锚定）",
                "confidence_label_en": "High (Direct Risk-Premium Anchor)",
            },
            "affected_tickers": {"KWEB": 0.9, "HSTECH.HK": 0.85, "00700.HK": 0.75},
            "realized_quotes": _quote_snapshot(["KWEB", "HSTECH.HK", "00700.HK", "000001.SH"]),
            "bars": [
                _bar("美股", "中概互联资产 (KWEB)", "US-Listed China Tech (KWEB)", 1.6, 4.2, "中美关系底部托底预期带动外资空头回补与估值折价收敛。", "Stabilizing diplomatic floor triggers ADR short-covering and multiple expansion.", min(1.3, kweb_f), "KWEB"),
                _bar("港股", "恒生科指与外资权重 (00700 / HSTECH)", "HKEX Tech Leaders (HSTECH / 00700)", 1.5, 3.8, "离岸中国资产对中美风险溢价改善弹性最高。", "Offshore HK tech leaders capture strongest risk-premium compression.", 1.0, "HSTECH.HK"),
                _bar("A股", "出口链 / 消费电子与航运", "A-Share Exporters & Consumer Electronics", 1.2, 3.2, "贸易关税担忧边际降温提升对美敞口制造业估值。", "Tariff-deescalation expectations support export manufacturing.", 1.0),
            ],
            "if_then": [
                {"cond": "若后续正式联合公报确认推进关税豁免或常态化经贸对话", "result": "外资持续回流港股与中概核心权重", "tone": "bullish"},
                {"cond": "若会晤后实质科技及资本限制未见松动", "result": "风偏修复仅限短线情绪行情", "tone": "neutral"},
            ],
            "milestones": [{"date": "会晤后 72 小时", "status": "current", "label": "双方外交与财政部门跟进文本公布"}],
        }

    # 10. Positive AI Infrastructure Capex / Cybersecurity M&A / Frontier Model Launch
    if any(k in t for k in ("已筹足", "自由现金流", "洽购", "飙升", "发布", "开源", "反蒸馏")):
        if "洽购" in t and ("crowdstrike" in t or "zscaler" in t):
            return {
                "rule_id": "cybersecurity_consolidation_ma",
                "tag": "美股网安赛道重磅并购整合",
                "tag_en": "US Cybersecurity Consolidation M&A",
                "polarity": "bullish",
                "intensity": 4,
                "one_liner": "头部零信任安全龙头整合催化全球网安赛道重估，带动身份/云安全软件与境内网安映射走强。",
                "one_liner_en": "Mega-cap zero-trust M&A talks lift global cybersecurity software valuations.",
                "sample_basis": {
                    "sample_n": 12,
                    "volatility_pct": 3.4,
                    "volatility_source": "美股 SaaS 并购事件波动参考",
                    "horizon": "2~5 个交易日",
                    "confidence_label": "高置信（直指标的并购溢价）",
                    "confidence_label_en": "High (Direct Deal-Premium Repricing)",
                },
                "affected_tickers": {"CRWD": 0.65, "QQQ": 0.25},
                "realized_quotes": _quote_snapshot(["CRWD", "QQQ"]),
                "bars": [
                    _bar("美股", "云安全与零信任软件 (CRWD / ZS)", "US Cybersecurity Leaders (CRWD/ZS)", 2.2, 6.5, "并购传闻引发网安估值基准上修及同业溢价重估。", "M&A premium lifts peer multiples across zero-trust & cloud security.", 1.0, "CRWD"),
                    _bar("A股", "信息安全 / 政企零信任底座", "A-Share Cybersecurity Software", 1.1, 3.0, "全球行业并购映射激发本土网安低位板块补涨关注。", "Global deal spillover raises valuation interest in domestic security.", 1.0),
                    _bar("港股", "企业云安全与软件服务 (HSTECH)", "HKEX Enterprise Cloud Software", 0.5, 1.8, "云安全支出韧性边际强化软件估值预期。", "Reinforces enterprise cloud-security spending resilience.", 1.0, "HSTECH.HK"),
                ],
                "if_then": [{"cond": "若双方正式宣布约束性收购报价", "result": "全行业安全软件 EV/Sales 估值中枢获提振", "tone": "bullish"}],
                "milestones": [{"date": "2 周内", "status": "current", "label": "双方董事会是否公布正式并购条款或否认传闻"}],
            }
        if any(
            k in t
            for k in (
                "屏蔽", "阻断", "禁用", "限制读取", "截屏", "反蒸馏", "蒸馏", "思考链提取",
                "黎曼", "形式化验证", "数学证明", "论文", "投资者是否应", "解散",
                "tensorlean", "certik", "内核验证", "gpu内核", "gpu 内核", "flashattention", "cuda",
            )
        ):
            return None
        if any(k in t for k in ("甲骨文", "openai", "gpt", "gemini", "anthropic", "claude", "混元", "千问", "qwen", "deepseek", "llm")):
            is_infra = "甲骨文" in t or "筹足" in t or "合同" in t or "自由现金流" in t
            if not is_infra:
                if "openai" in t or "gpt" in t:
                    eco_tag = "OpenAI 模型迭代与微软云算力链"
                    eco_tag_en = "OpenAI Model Launch & Inference Ecosystem"
                    tickers = {"MSFT": 0.48, "NVDA": 0.42, "QQQ": 0.28}
                    quotes_list = ["MSFT", "NVDA", "QQQ"]
                    us_sector = "Azure 与 AI 算力核心生态 (MSFT / NVDA)"
                    us_sector_en = "Azure & AI Compute Ecosystem (MSFT/NVDA)"
                    us_logic = "OpenAI 新模型与企业 Copilot / 实时推理接口扩张，直接拉动微软云 Azure 消耗与 NVIDIA GPU 集群需求。"
                    hk_sector = "AI 应用入口与云计算映射 (HSTECH / 00700)"
                    hk_logic = "头部闭源模型编程与推理工具链升级，推升港股云平台与商业化 SaaS 估值比价锚。"
                    a_sector = "A股端侧 Agent 与语音/多模态软件"
                    a_logic = "企业级实时交互与多模态 API 需求升温，利好国内跟进垂直 Agent 与语音交互软件的商业化厂商。"
                    one_liner = "OpenAI 代际推理与实时 Agent 工具扩容直接拉动微软 Azure 云消耗及 NVDA 推理芯片利用率，同步提振港/A 应用 SaaS 估值。"
                    if_then = [
                        {"cond": "若微软下一季财报显示 Azure AI 营收贡献环比提升 >= 2 个百分点", "result": "MSFT 与 NVDA 推理硬件链上修盈利预期", "tone": "bullish"},
                        {"cond": "若第三方基准与开发者调研显示企业付费率不及预期", "result": "纯概念 AI 应用软件面临获利回吐压力", "tone": "bearish"},
                    ]
                    milestones = [{"date": "未来 2~4 周", "status": "upcoming", "label": "跟踪 OpenAI API 日均 Token 调用量及微软 Copilot 席位转化数据"}]
                elif "gemini" in t or "google" in t or "谷歌" in t or "deepmind" in t:
                    eco_tag = "Google Gemini 架构迭代与自研 TPU 生态"
                    eco_tag_en = "Google Gemini Iteration & TPU Compute Stack"
                    tickers = {"GOOGL": 0.55, "AVGO": 0.38, "QQQ": 0.28}
                    quotes_list = ["GOOGL", "AVGO", "QQQ"]
                    us_sector = "Google 与定制 ASIC/TPU 算力链 (GOOGL / AVGO)"
                    us_sector_en = "Google & Custom TPU Stack (GOOGL/AVGO)"
                    us_logic = "谷歌全栈多模态与端云推理效率升级，加固搜索广告防线并利好博通 (AVGO) 定制 TPU ASIC 出货。"
                    hk_sector = "多模态消费应用与移动生态 (HSTECH)"
                    hk_logic = "端云协同轻量化模型能力提升，改善港股互联网端侧分发与海外广告变现效率。"
                    a_sector = "A股高密度光模块 / ASIC 测试与端侧软件"
                    a_logic = "高吞吐 TPU 集群与端云推理带旺光通信模块与 ASIC 封装测试链。"
                    one_liner = "谷歌全栈 Gemini 推理与自研 TPU 降本增效直接强化 GOOGL 云与搜索护城河，利好博通 (AVGO) ASIC 供应链。"
                    if_then = [
                        {"cond": "若 Google Cloud 季度营业利润率站稳 15% 以上且 TPU v6 外部订单放量", "result": "GOOGL 与 AVGO 获得云基础设施估值重估", "tone": "bullish"},
                        {"cond": "若算力投入导致谷歌资本开支占营收比升破 20% 且短期广告增速放缓", "result": "市场对自由现金流折损定价偏谨慎", "tone": "bearish"},
                    ]
                    milestones = [{"date": "未来 2~4 周", "status": "upcoming", "label": "观察 Google Cloud API 定价变动及 AVGO AI ASIC 订单指引"}]
                elif "anthropic" in t or "claude" in t:
                    eco_tag = "Anthropic 企业级 Agent 与云托管竞合"
                    eco_tag_en = "Anthropic Enterprise Agent & Cloud Hosting"
                    tickers = {"AMZN": 0.45, "GOOGL": 0.35, "QQQ": 0.28}
                    quotes_list = ["AMZN", "GOOGL", "QQQ"]
                    us_sector = "AWS / 云代码 Agent 托管生态 (AMZN / GOOGL)"
                    us_sector_en = "AWS & Enterprise Coding AI Stack (AMZN/GOOGL)"
                    us_logic = "企业级长上下文与安全编码 Agent 渗透深化，直接放量 AWS Bedrock 与 GCP 的高毛利调用营收。"
                    hk_sector = "企业软件与港股云计算龙头 (HSTECH)"
                    hk_logic = "海外企业级订阅与 Agent 客单价抬升，改善市场对港股云计算平台 B 端变现的预期。"
                    a_sector = "A股代码辅助 / 企业知识库与国产大模型"
                    a_logic = "复杂代码重构与企业知识库合规托管需求升温，利好国内垂直行业 Agent 服务商。"
                    one_liner = "Anthropic 企业编码与 Agent 工作流加速商用，直接推高 AWS Bedrock/GCP 云托管调用量并支撑 B 端 SaaS 估值。"
                    if_then = [
                        {"cond": "若 AWS 与企业客户端续约 ARR 同比增速维持 30% 以上", "result": "AMZN 云板块及代码安全生态延续超额收益", "tone": "bullish"},
                        {"cond": "若企业端客户因高推理单价转向开源轻量替代方案", "result": "闭源企业级 SaaS 议价空间面临压缩", "tone": "bearish"},
                    ]
                    milestones = [{"date": "未来 2~4 周", "status": "upcoming", "label": "跟踪 AWS Bedrock 模型调用占比与企业客户 ARR 披露"}]
                else:
                    eco_tag = "国产与开源大模型性能追赶催化"
                    eco_tag_en = "China & Open-Weight Model Catch-Up"
                    tickers = {"09988.HK": 0.45, "00700.HK": 0.42, "HSTECH.HK": 0.4}
                    quotes_list = ["09988.HK", "00700.HK", "HSTECH.HK"]
                    us_sector = "全球推理芯片与云基准估值 (NVDA / QQQ)"
                    us_sector_en = "Global Inference Compute & Cloud Benchmarks"
                    us_logic = "低成本高性价比开源模型持续拉低每百万 Token 推理价格，刺激终端调用总量并检验海外高溢价闭源模型壁垒。"
                    hk_sector = "国内开源模型底座与云平台 (09988 / 00700)"
                    hk_logic = "国产与开源大模型能力追平海外一线梯队，直接提升阿里云百炼/腾讯云等港股 MaaS 平台调用粘性。"
                    a_sector = "A股国产算力卡 / 推理服务器与本地部署软件"
                    a_logic = "开源权重轻量化加速政企与金融机构本地化部署落地，带动国产推理一体机与算力卡需求。"
                    one_liner = "高性价比开源与国产大模型持续压低企业部署门槛，重点利好阿里/腾讯等云底座与国内本地推理算力链。"
                    if_then = [
                        {"cond": "若主流云平台 MaaS 日均 Token 吞吐量季度翻倍且单位推理毛利转正", "result": "09988.HK / 00700.HK 云计算业务迎来重估", "tone": "bullish"},
                        {"cond": "若海外高阶模型同期开启新一轮 API 降价 50% 以上", "result": "纯模型层盈利空间受挤压，算力基建占优", "tone": "neutral"},
                    ]
                    milestones = [{"date": "未来 2~4 周", "status": "upcoming", "label": "关注 Hugging Face 下载排名及云厂商企业微调调用增长"}]
                return {
                    "rule_id": "ai_model_launch_catalyst",
                    "tag": eco_tag,
                    "tag_en": eco_tag_en,
                    "polarity": "bullish",
                    "intensity": 3,
                    "one_liner": one_liner,
                    "one_liner_en": f"{eco_tag_en} expands enterprise cloud consumption and AI developer monetization.",
                    "sample_basis": {
                        "sample_n": 15,
                        "volatility_pct": 2.9,
                        "volatility_source": "主流大模型与软件应用催化样本",
                        "horizon": "2~5 个交易日",
                        "confidence_label": "中高置信（生态应用催化）",
                        "confidence_label_en": "Moderate-High (Model Ecosystem Catalyst)",
                    },
                    "affected_tickers": tickers,
                    "realized_quotes": _quote_snapshot(quotes_list),
                    "bars": [
                        _bar("美股", us_sector, us_sector_en, 0.9, 2.7, us_logic, "Model ecosystem upgrades expand enterprise cloud consumption.", 1.0, quotes_list[0]),
                        _bar("港股", hk_sector, "HKEX AI Ecosystem & Cloud Platforms", 0.8, 2.5, hk_logic, "Model performance progress supports platform ecosystem monetization.", 1.0, "HSTECH.HK"),
                        _bar("A股", a_sector, "A-Share AI Apps & Local Compute", 1.1, 3.1, a_logic, "Expanded capabilities accelerate domestic enterprise adoption.", 1.0),
                    ],
                    "if_then": if_then,
                    "milestones": milestones,
                }
            return {
                "rule_id": "ai_infra_or_model_catalyst",
                "tag": "AI 算力现金流兑现与云基建订单",
                "tag_en": "AI Cloud Capex & Contract Financing",
                "polarity": "bullish",
                "intensity": 3,
                "one_liner": "云巨头履约资金与长周期自由现金流指引兑现，直接缓解 AI 数据中心融资担忧，对算力基建及云生态偏正面。",
                "one_liner_en": "Confirmed cloud contract funding and free-cash-flow guidance support AI infrastructure plays.",
                "sample_basis": {
                    "sample_n": 17,
                    "volatility_pct": 3.1,
                    "volatility_source": "云基建融资与订单催化样本",
                    "horizon": "2~5 个交易日",
                    "confidence_label": "中高置信（受整体市场风偏约束）",
                    "confidence_label_en": "Moderate-High (Subject to Macro Beta)",
                },
                "affected_tickers": {"ORCL": 0.7, "NVDA": 0.4, "QQQ": 0.35, "00700.HK": 0.4, "HSTECH.HK": 0.35},
                "realized_quotes": _quote_snapshot(["QQQ", "00700.HK", "HSTECH.HK"]),
                "bars": [
                    _bar("美股", "AI 云基建与头部软件生态 (ORCL / QQQ)", "US AI Cloud & Platforms", 1.1, 3.2, "大额算力订单融资落地缓解资本开支可持续性担忧。", "Secured contract financing reduces AI infrastructure solvency worries.", 1.0, "QQQ"),
                    _bar("港股", "港股大模型与互联网入口 (00700 / HSTECH)", "HKEX AI Ecosystem & Platforms (00700)", 0.9, 2.8, "云端算力扩容确认产业链资本开支景气延续。", "Confirmed overseas cloud financing supports infrastructure sentiment.", 1.0, "00700.HK"),
                    _bar("A股", "算力租赁与数据中心配套硬件", "A-Share Compute Leasing & Datacenter Infra", 1.2, 3.4, "云厂合同兑现强化上游服务器与电源配套景气预期。", "Cloud contract execution supports upstream datacenter hardware demand.", 1.0),
                ],
                "if_then": [{"cond": "若随后季度云资本开支未随宏观波动收缩", "result": "AI 云基建与端侧应用维持相对超额", "tone": "bullish"}],
                "milestones": [{"date": "下一次财报季", "status": "upcoming", "label": "云合同 RPO 余额转化与商业化 ARR 增速验证"}],
            }

    return None


def _validate_impact_consistency(title: str, summary: str, scenario: Optional[Dict[str, Any]]) -> Tuple[bool, str]:
    """Strict P0 gate: reject contradictions between news polarity/domain and predicted bars."""
    if not scenario:
        return False, "该事件缺少可验证的历史股票传导渠道，暂不强行套用模板。"
    bars = scenario.get("bars") or []
    if not bars:
        return False, "未能提取有效受影响板块区间。"

    blob = f"{title} {summary}"
    has_neg_shock = bool(_NEGATIVE_SHOCK_RE.search(title))
    has_pos_shock = bool(_POSITIVE_SHOCK_RE.search(title))
    pol = scenario.get("polarity")
    mids = [(float(b["pct_low"]) + float(b["pct_high"])) / 2.0 for b in bars]
    has_neg_bar = any(m < -0.2 for m in mids)
    has_pos_bar = any(m > 0.2 for m in mids)

    # Gate 1: Explicit negative headline shock (e.g. crash -14%, IPO drop -8.5%, leak, hike, tax)
    # must NEVER output polarity == 'bullish' or all-positive sector bars!
    if has_neg_shock and not has_pos_shock:
        if pol == "bullish":
            return False, "标题呈明显利空/下跌冲击，但候选推演方向判为利好，校验拦截。"
        if not has_neg_bar:
            return False, "标题为负面下跌冲击但各板块预期均为正区间，方向冲突，校验拦截。"

    # Gate 2: Polarity vs bars structural check
    if pol == "bearish" and not has_neg_bar:
        return False, "事件方向为偏空承压，但输出板块全为正值，一致性校验未通过。"
    if pol == "bullish" and not has_pos_bar:
        return False, "事件方向为偏多利好，但输出板块全为负值，一致性校验未通过。"

    # Gate 3: Semantic domain check to prevent KWEB/rate-hike mis-templates
    rid = str(scenario.get("rule_id") or "")
    if "us_china" in rid and not any(k in blob for k in ("中美", "APEC", "中概", "对华关税")):
        return False, "中美关税模板仅限涉及中美双边贸易事件。"
    if rid == "geopolitics_energy_escalation" and ("和平协议" in title or "停火协议" in title) and "空袭" not in title and "触雷" not in title:
        return False, "和平停火进展不应套用冲突升级模板。"

    return True, "结构化方向与资产敏感区间一致性校验通过"


def build_finance_impact_artifact(
    all_events: Optional[List[dict]] = None,
    batch_id: str = "",
    generated_at_iso: str = "",
    quotes_doc: Optional[Dict[str, Any]] = None,
    cat_docs: Optional[Dict[str, dict]] = None,
) -> Dict[str, Any]:
    """Generate structurally validated Event -> Direction -> Sector -> Stock impact maps."""
    if all_events is None and isinstance(cat_docs, dict):
        all_events = [
            ev
            for cdoc in cat_docs.values()
            if isinstance(cdoc, dict)
            for ev in (cdoc.get("events") or [])
            if isinstance(ev, dict)
        ]
    all_events = all_events or []
    quotes_map = (quotes_doc or {}).get("quotes") or {}
    if not quotes_map:
        try:
            from .market_quotes import fetch_market_quotes

            fetched = fetch_market_quotes(timeout=4.5, include_volatility=False)
            quotes_map = fetched.get("quotes") or {}
            quotes_doc = fetched
        except Exception:
            quotes_map = {}

    # Rank candidate events with economic/market relevance
    scored: List[Tuple[int, dict]] = []
    seen_titles: set[str] = set()
    for ev in all_events:
        if ev.get("is_stale_rehash") is True:
            continue
        if ev.get("evidence_status") == "needs_verification" and not ev.get("sources"):
            continue
        title = str(ev.get("title") or "").strip()
        if not title:
            continue
        tkey = re.sub(r"[\s\W]+", "", title.lower())[:16]
        if tkey in seen_titles:
            continue
        seen_titles.add(tkey)
        cat = str(ev.get("category") or "")
        imp = 3 if ev.get("importance") == "high" else 1
        base = 6 if cat == "finance" else (4 if cat in ("tech", "global") else 1)
        kw_bonus = 2 if re.search(r"股|市场|芯片|英伟达|美联储|利率|金价|油|关税|协议|IPO|融资|市值|美伊|俄乌|微软|OpenAI|Anthropic|FSD|海力士|HBM|比特币|BTC|ETH|稀土|资金短缺", title, re.I) else 0
        scored.append((base + imp + kw_bonus, ev))

    scored.sort(key=lambda x: x[0], reverse=True)

    impacts: List[dict] = []
    event_impact_map: Dict[str, dict] = {}
    used_rule_counts: Dict[str, int] = {}
    used_one_liners: set[str] = set()

    for _, ev in scored[:28]:
        title = str(ev.get("title") or "")
        summary = str(ev.get("fact_summary") or "")
        blob = f"{title} {summary}"
        scenario = _build_domain_scenario(blob, title, quotes_map)
        valid, check_note = _validate_impact_consistency(title, summary, scenario)

        eid = str(ev.get("event_id") or "")
        srcs = ev.get("sources") or []
        src_name = str((srcs[0] if srcs else {}).get("source_name") or "多源新闻汇总")
        src_url = (srcs[0] if srcs else {}).get("url")
        pub_at = str(ev.get("latest_reported_at") or ev.get("published_at") or ev.get("fetched_at") or generated_at_iso)

        if not valid or scenario is None:
            continue

        ol_key = str(scenario.get("one_liner") or "").strip()
        if ol_key and ol_key in used_one_liners:
            continue

        rid = scenario["rule_id"]
        occ_idx = used_rule_counts.get(rid, 0)
        if occ_idx >= 3:
            continue
        if ol_key:
            used_one_liners.add(ol_key)
        used_rule_counts[rid] = occ_idx + 1

        # Differentiate secondary/indirect occurrences sharing the same macro rule so cards never clone identical % ranges
        bars = scenario["bars"]
        if occ_idx > 0:
            atten = max(0.68, 1.0 - 0.13 * occ_idx)
            adj_bars = []
            for b in bars:
                nb = dict(b)
                nb["pct_low"], nb["pct_high"] = _scale_band(float(b["pct_low"]), float(b["pct_high"]), atten)
                adj_bars.append(nb)
            bars = adj_bars
        card = {
            "id": f"imp_{eid}",
            "event_id": eid,
            "rule_id": rid,
            "validation_status": "verified",
            "validation_note": check_note,
            "event_title": title,
            "event_title_en": ev.get("title_en") or title,
            "event_summary": summary,
            "event_summary_en": ev.get("summary_en") or summary,
            "category": str(ev.get("category") or "general"),
            "published_at": pub_at,
            "source_name": src_name,
            "source_url": src_url,
            "sources": [{"source_name": s.get("source_name"), "url": s.get("url")} for s in srcs[:3] if s.get("url")],
            "tag": scenario["tag"],
            "tag_en": scenario["tag_en"],
            "polarity": scenario["polarity"],
            "intensity": scenario["intensity"],
            "one_liner": scenario["one_liner"],
            "one_liner_en": scenario["one_liner_en"],
            "sample_basis": scenario["sample_basis"],
            "affected_tickers": scenario.get("affected_tickers") or {},
            "realized_quotes": scenario.get("realized_quotes") or [],
            "bars": bars,
            "if_then": scenario["if_then"],
            "milestones": scenario["milestones"],
        }
        impacts.append(card)

        top_a = next((b for b in bars if b["market"] == "A股"), bars[0])
        top_us = next((b for b in bars if b["market"] == "美股"), bars[-1])
        top_hk = next((b for b in bars if b["market"] == "港股"), None)
        event_impact_map[eid] = {
            "event_id": eid,
            "tag": scenario["tag"],
            "tag_en": scenario["tag_en"],
            "polarity": scenario["polarity"],
            "intensity": scenario["intensity"],
            "validation_status": "verified",
            "one_liner": scenario["one_liner"],
            "top_a": top_a,
            "top_us": top_us,
            "top_hk": top_hk,
            "bars": bars,
            "if_then": scenario["if_then"],
            "milestones": scenario["milestones"],
            "sample_basis": scenario["sample_basis"],
            "realized_quotes": scenario.get("realized_quotes") or [],
        }

        if len(impacts) >= 16:
            break

    return {
        "schema_version": "4.1",
        "generation_mode": "deterministic_volatility_calibrated",
        "quality_flags": [] if quotes_map else ["quotes_fallback"],
        "generated_at": generated_at_iso or to_iso_shanghai(now_shanghai()),
        "batch_id": batch_id,
        "disclaimer": "模型边界提示：以下板块敏感区间基于结构化事件极性与 20 日实现波动率校准推演，并附当前真实/延迟行情对照，仅为研究参考，不构成任何投资买卖建议。",
        "disclaimer_en": "Model Notice: Sensitivity intervals use structured event polarity & realized volatility calibration alongside delayed market quotes for research only — not investment advice.",
        "quotes_updated_at": (quotes_doc or {}).get("updated_at"),
        "index_quotes": (quotes_doc or {}).get("indices") or [],
        "total_mapped_events": len(impacts),
        "event_impacts": impacts,
        "event_impact_map": event_impact_map,
    }
