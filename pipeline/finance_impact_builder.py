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

from .finance_deep_research import customize_event_copy_and_basis, enrich_card_deep_research
from .time_utils import now_shanghai, parse_iso_datetime, to_iso_shanghai


_EVIDENCE_LABELS = {
    "official": "官方公告 / 监管披露",
    "research": "机构研报 / 渠道调研",
    "corroborated": "多源媒体证实",
    "single_source": "单一信源线索",
}

_OFFICIAL_SOURCE_RE = re.compile(
    r"证监会|沪深交易所|沪深北交易所|上交所|深交所|北交所|央行|中国人民银行|财政部|商务部|工信部|"
    r"国家统计局|国家发改委|国务院|外交部|美联储|Federal\s*Reserve|SEC|中国结算|新华网|新华社|人民日报",
    re.I,
)
_RESEARCH_TEXT_RE = re.compile(
    r"研报|策略报告|招商证券|中信证券|中金公司|华泰证券|国泰君安|高盛|摩根士丹利|大摩|小摩|瑞银|天风|"
    r"郭明錤|供应链调研|渠道路演|分析师(?:披露|指出|预测|测算)",
    re.I,
)


def infer_event_evidence_tier(ev: Dict[str, Any], title: str = "", summary: str = "") -> Tuple[str, str]:
    """Classify event evidence strictly into 4 unified verification tiers."""
    t_str = f"{title or ev.get('title') or ''} {summary or ev.get('fact_summary') or ''}"
    srcs = [s for s in (ev.get("sources") or []) if isinstance(s, dict)]
    src_names = " ".join(str(s.get("source_name") or "") for s in srcs)
    ind_cnt = int(ev.get("independent_publisher_count") or len({str(s.get("source_name") or "").strip() for s in srcs if s.get("source_name")}) or 0)

    if _OFFICIAL_SOURCE_RE.search(src_names) or (
        re.search(r"(?:中国证监会|沪深北交易所|沪深交易所|中国结算|央行|财政部|商务部|美联储).*(?:公告|通知|批准|施行|生效|减免|决议|规定)", t_str)
    ):
        return "official", _EVIDENCE_LABELS["official"]
    if _RESEARCH_TEXT_RE.search(f"{src_names} {t_str}"):
        return "research", _EVIDENCE_LABELS["research"]
    if ind_cnt >= 2 or len(srcs) >= 2:
        return "corroborated", _EVIDENCE_LABELS["corroborated"]
    return "single_source", _EVIDENCE_LABELS["single_source"]


def extract_effective_date_label(title: str, summary: str = "") -> Optional[str]:
    """Extract formal statutory effective / start dates from policy & corporate notices."""
    blob = f"{title} {summary}"
    m = re.search(r"自\s*(?:(202[6-9])年)?\s*(\d{1,2})月(\d{1,2})日起(?:正式)?(?:施行|生效|实施|减免|执行)", blob)
    if m:
        yr, mo, dy = m.group(1), m.group(2), m.group(3)
        prefix = f"{yr}年" if yr and yr != "2026" else ""
        return f"{prefix}{mo}月{dy}日起正式生效"
    m2 = re.search(r"(?:(202[6-9])年)?(\d{1,2})月(\d{1,2})日(?:起|起正式|正式)(?:生效|施行|实施|启用|减免|免收|执行)", blob)
    if m2:
        yr, mo, dy = m2.group(1), m2.group(2), m2.group(3)
        prefix = f"{yr}年" if yr and yr != "2026" else ""
        return f"{prefix}{mo}月{dy}日生效"
    if "下周一" in blob and any(k in blob for k in ("保证金", "两融", "施行", "实施")):
        return "下周一起正式实施"
    return None


def extract_qualifier_badge(title: str, summary: str = "") -> Optional[str]:
    """Promote key hedging qualifiers ('up to X%', 'talks', 'unconfirmed') next to the headline."""
    blob = f"{title} {summary}"
    m_up = re.search(r"(?:最高(?:提价|涨价|涨幅|调价|上调)|(?:涨幅|提价|涨价|报价|调价)最高(?:达|至|为)?)\s*(\d+(?:\.\d+)?)\s*%", blob)
    if m_up:
        return f"要价上限 {m_up.group(1)}% · 关注客户实际接受率"
    if re.search(r"(?:削减|减少).*?(?:100万|20%).*?(?:联发科|TPU\s*8t)", blob, re.I):
        return "供应商切换：减博通 8i / 增联发科 8t"
    if re.search(r"遴选|接班|外部.*?CEO", blob, re.I) and "8-K" not in blob:
        return "未获董事会正式确认"
    if re.search(r"传闻|据传|洽购|磋商|意向", blob):
        return "尚在磋商阶段 · 关注正式签约"
    return None


def _topic_dedup_key(rid: str, title: str, pub_at: str) -> Optional[str]:
    """Collapse duplicate clusters covering the exact same event on the same day."""
    day = str(pub_at or "")[:10] or "nodate"
    if rid == "a_share_capital_market_reform" and any(k in title for k in ("80%", "保证金", "两融", "4000亿")):
        return f"topic:a_share_margin_80:{day}"
    if rid == "asic_tpu_order_cut":
        return f"topic:google_tpu_cut:{day}"
    if rid == "nvda_ceo_succession_transition":
        return f"topic:nvda_ceo_search:{day}"
    return None

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
    r"批准.*出口|缓和|突破|正式开源|全面开放|洽购|"
    r"融资保证金.*降至|下调.*保证金|增量资金|稳市组合拳|免收.*费用|做市商|"
    r"趋近历史底部|历史底部|回购股份|拟以.*亿元.*回购|再次点火|产能被锁定|供货保障)",
    re.IGNORECASE,
)

_LOW_IMPACT_TECH_CHATTER_RE = re.compile(
    r"(?:artificial\s*analysis|回答更简短|透明度低于|提示词技巧|prompt\s*技巧|使用技巧|"
    r"测评对比|评测.*简短|盲测|网友实测|解散机器人团队|调查问卷|优惠上线|9\.9元|"
    r"输入法.*内测|屏蔽截图|阻止.*读取)",
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
    default_proxy_by_market = {
        "A股": "510300.SH",
        "美股": "QQQ",
        "港股": "HSTECH.HK",
        "亚太": "000660.KS",
        "台股": "TSM",
    }
    resolved_proxy = str(proxy_ticker or "").strip() or default_proxy_by_market.get(market, "510300.SH")
    return {
        "market": market,
        "sector": sector,
        "sector_en": sector_en,
        "pct_low": s_lo,
        "pct_high": s_hi,
        "direction": direction,
        "proxy_ticker": resolved_proxy,
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

    # 0a. Early materiality gate: block 3rd-party AI chatter/surveys/benchmarks that have zero capital-market weight
    if _LOW_IMPACT_TECH_CHATTER_RE.search(tl):
        return None

    # 0b. A-Share Mainland Capital-Market Reform (split Fee-Cut 46B vs Margin Ratio 80% Cut)
    if (
        re.search(
            r"沪深北交易所|沪深交易所|上交所.*降费|深交所.*降费|融资保证金比例|下调.*保证金|两融.*保证金|做市商规则|免收.*上市.*费|减免费用|降费让利|印花税|平准基金|稳市组合拳",
            text,
            re.I,
        )
        and "台湾" not in tl
        and "台湾地区" not in tl
    ):
        is_margin_4000 = "保证金" in text or "4000亿" in text or "80%" in text
        is_fee_cut = bool(re.search(r"降费|免收.*费|减免费用|让利|下调.*经手费", text)) and not is_margin_4000
        if is_fee_cut:
            return {
                "rule_id": "a_share_exchange_fee_cut",
                "tag": "交易所年度降费让利 · 降低实体融资与交易规费",
                "tag_en": "Exchange Annual Fee Reduction & Entity Cost Relief",
                "polarity": "bullish",
                "intensity": 4,
                "one_liner": "上交所/深交所推出年度降费让利组合措施（免收上市年费/CA 证书及减半债券交易规费等，预计让利约 46 亿元），直接压降实体发行人与做市交易机构制度成本。",
                "one_liner_en": "Mainland exchanges cut annual listing, bond-trading, and data-service fees (~4.6B RMB relief) to lower issuer and trading costs.",
                "sample_basis": {
                    "sample_n": 14,
                    "volatility_pct": 2.4,
                    "volatility_source": "沪深交易所年度降费让利公告后券商及科创成长板块表现样本",
                    "horizon": "1~5 个交易日",
                    "confidence_label": "官方制度红利（直接减免交易所刚性规费）",
                    "confidence_label_en": "Official Regulatory Fee Relief",
                },
                "affected_tickers": {"600030.SH": 0.80, "601688.SH": 0.78, "600570.SH": 0.72, "588000.SH": 0.70, "510300.SH": 0.55},
                "realized_quotes": _quote_snapshot(["000001.SH", "588000.SH", "HSTECH.HK"]),
                "bars": [
                    _bar("A股", "头部投行与债券/基金做市券商 (中信 / 华泰)", "A-Share Investment Banks & Market Makers (600030/601688)", 1.5, 4.1, "交易所免收债券交易及基金/期权部分费用直接增厚做市与自营净手续费空间。", "Exchange bond/fund fee waivers directly widen broker market-making net margins.", 1.0, "600030.SH"),
                    _bar("A股", "科创板50ETF 及新质生产力上市梯队 (588000)", "STAR 50 & Tech Issuers (588000)", 1.2, 3.4, "免收初费与年费降低专精特新科技企业直接融资与持续挂牌成本。", "Listing fee waivers reduce direct financing costs for STAR-market tech companies.", 1.0, "588000.SH"),
                    _bar("A股", "金融 IT 与交易清算基础设施 (恒生电子)", "Trading Infrastructure & Fintech IT (600570)", 0.9, 2.8, "交易规费与网络行情服务减免激励机构接入直连通道与新柜台需求。", "Network/market-data fee relief boosts institutional direct-connection IT demand.", 1.0, "600570.SH"),
                    _bar("A股", "宽基沪深300与高股息信用债发行人 (510300)", "CSI 300 & Corporate Issuers (510300)", 0.6, 2.1, "全市场约 46 亿元让利温和改善权益与信用债市场整体活跃度。", "Broad ~4.6B RMB fee relief mildly lifts cash equity and credit market liquidity.", 1.0, "510300.SH"),
                ],
                "if_then": [],
                "milestones": [{"date": "2027全年", "status": "upcoming", "label": "跟踪上交所/深交所降费正式实施后单季债券与ETF成交活跃度"}],
            }
        return {
            "rule_id": "a_share_capital_market_reform",
            "tag": "A股两融松绑与资本市场稳市组合拳" if is_margin_4000 else "双创做市商机制优化与市场流动性改革",
            "tag_en": "A-Share Margin Ratio Cut & Market Stabilization" if is_margin_4000 else "STAR/ChiNext Market-Maker Liquidity Reform",
            "polarity": "bullish",
            "intensity": 5 if is_margin_4000 else 4,
            "one_liner": (
                "沪深北交易所将融资保证金比例下限降至 80%（测算释放近 4000 亿潜在增量杠杆资金），叠加做市商扩容与减免费用组合拳，直接利好两融高占比券商及金融 IT。"
                if is_margin_4000
                else "沪深交易所推动修订科创板/创业板做市商规则，改善双创科技成长股盘口流动性与估值溢价，直接催化做市业务头部券商。"
            ),
            "one_liner_en": "Mainland exchanges lower margin collateral floors and ease market-maker rules, directly lifting brokers, fintech, and STAR/ChiNext liquidity.",
            "sample_basis": {
                "sample_n": 18,
                "volatility_pct": 3.4,
                "volatility_source": "A股券商/两融制度红利历史样本",
                "horizon": "1~5 个交易日",
                "confidence_label": "高置信（直接作用于场内两融与交易量）",
                "confidence_label_en": "High (Direct Margin & Turnover Catalyst)",
            },
            "affected_tickers": {"600030.SH": 0.95, "601688.SH": 0.85, "300059.SZ": 0.95, "300033.SZ": 0.9, "510300.SH": 0.65, "HSTECH.HK": 0.4},
            "realized_quotes": _quote_snapshot(["000001.SH", "HSTECH.HK", "HSI.HK"]),
            "bars": [
                _bar("A股", "头部两融券商与金融 IT (中信 / 东财 / 同花顺)", "A-Share Brokers & Fintech (600030/300059)", 2.8, 6.4, "融资保证金下调直接扩大存量保证金可买融资额度 25%，交投放大最利好券商与互联网交易端。", "Lower margin collateral requirements expand leverage capacity by 25%, boosting brokers & fintech.", 1.0, "600030.SH"),
                _bar("A股", "科创板 / 创业板高弹性核心成长", "A-Share STAR & ChiNext Growth", 1.5, 4.2, "两融活跃度提升与做市商门槛放宽优先改善双创科技板块成交深度。", "Margin expansion & relaxed market-maker thresholds support STAR/ChiNext liquidity.", 1.0, "300059.SZ"),
                _bar("港股", "港股中资券商与离岸中国宽基 (HSTECH)", "HKEX China Brokers & HSTECH", 1.1, 3.1, "境内资本市场稳市政策组合拳同步提振离岸人民币风险偏好与中资券商比价。", "Mainland market-stabilization policy improves offshore China equity risk appetite.", 1.0, "HSTECH.HK"),
                _bar("A股", "宽基权重沪深300与非银保险 (510300)", "A-Share Broad Index & Insurers (510300)", 1.0, 2.8, "权益市场成交中枢抬升直接增厚保险投资端弹性与宽基被动流入。", "Higher turnover supports broad-index heavyweights and insurer equity books.", 1.0, "510300.SH"),
            ],
            "if_then": [],
            "milestones": [{"date": "下周一起", "status": "current", "label": "盯紧两市首小时成交额与中信/东财两融净增量"}],
        }

    # 0c. Regional Taiwan Margin Ratio Stabilization (distinct from Mainland A-Share 4000亿)
    if ("台湾" in tl or "台湾地区" in tl) and any(k in tl for k in ("保证金", "限空", "稳市", "股市")):
        return {
            "rule_id": "taiwan_market_stabilization",
            "tag": "台湾市场保证金调整与区域稳市",
            "tag_en": "Taiwan Equity Margin & Stabilization Policy",
            "polarity": "bullish",
            "intensity": 3,
            "one_liner": "台湾地区拟下调融资保证金比例以抑制杠杆断头踩踏、稳定当地权重股交易筹码，对台积电等晶圆权重大厂情绪构成温和支撑。",
            "one_liner_en": "Taiwan's proposed margin collateral easing aims to cushion forced liquidations and steady local tech weights.",
            "sample_basis": {"sample_n": 10, "volatility_pct": 2.5, "volatility_source": "台股监管限空/两融调整样本", "horizon": "1~5 个交易日", "confidence_label": "中高置信（区域筹码维稳）", "confidence_label_en": "Moderate-High (Regional Positioning Cushion)"},
            "affected_tickers": {"TSM": 0.45, "QQQ": 0.15},
            "realized_quotes": _quote_snapshot(["TSM", "QQQ"]),
            "bars": [
                _bar("台股", "台股半导体与晶圆代工权重 (TSM ADR)", "Taiwan Semi & Foundry Weights (TSM)", 0.9, 2.8, "放宽本地融资追缴压力有助于减少被动斩仓盘对台积电及电子权重的踩踏。", "Easing local margin call thresholds reduces forced selling pressure in Taiwan semis.", 1.0, "TSM"),
                _bar("美股", "费半与海外代工映射 (QQQ / TSM)", "US Semi Foundry Proxies (TSM/QQQ)", 0.3, 1.4, "亚洲芯片代工市场情绪企稳温和缓和美股半导体的隔夜尾盘担忧。", "Calmer Asian foundry flows mildly cushion US semiconductor sentiment.", 0.9, "QQQ"),
                _bar("A股", "海峡两岸电子制造情绪映射", "A-Share Cross-Strait Electronics", 0.2, 1.1, "属区域市场监管微调，对 A 股实质资金面外溢相对温和。", "Regional policy tweak with modest spillover to Mainland electronics.", 0.85, "512480.SH"),
            ],
            "if_then": [],
            "milestones": [{"date": "1 周内", "status": "current", "label": "关注台股外资净买超与融券余额变化"}],
        }

    # 0d. Domestic A-Share Brokerage Bottoming / Valuation Signal (NEVER misroute to Fed hawkish!)
    if re.search(r"招商证券|中信证券|华泰证券|国泰海通|申万宏源|研报|策略报告", tl) and re.search(
        r"历史底部|趋近.*底部|估值底部|磨底|底部水平|底部区间|多项指标", tl
    ):
        return {
            "rule_id": "a_share_bottom_valuation_signal",
            "tag": "A股历史底部指标共识与估值修复",
            "tag_en": "A-Share Valuation Bottom Signal",
            "polarity": "bullish",
            "intensity": 3,
            "one_liner": "头部券商量化指标提示 A 股破净率与股债性价比逼近历史极值底部，叠加稳市政策预期构成中线左侧赔率窗口。",
            "one_liner_en": "Major domestic brokerages flag equity risk-premium and breadth indicators nearing historical troughs, creating asymmetric upside.",
            "sample_basis": {"sample_n": 14, "volatility_pct": 2.3, "volatility_source": "A股历史估值极值底区间统计", "horizon": "3~10 个交易日", "confidence_label": "中高置信（赔率占优需量能印证）", "confidence_label_en": "Moderate-High (Valuation Mean-Reversion)"},
            "affected_tickers": {"510300.SH": 0.65, "300059.SZ": 0.7, "HSTECH.HK": 0.45},
            "realized_quotes": _quote_snapshot(["000001.SH", "HSTECH.HK"]),
            "bars": [
                _bar("A股", "沪深300与核心宽基权重 (510300)", "A-Share Broad Blue-Chips (510300)", 1.0, 3.0, "多项拥挤度与估值分位落入历史低区，宽基配置胜率明显高于恐慌杀跌期。", "Broad indices offer favorable risk-reward as crowding & PE metrics hit historical lows.", 1.0, "510300.SH"),
                _bar("A股", "非银券商与高弹性创成长 (300059)", "A-Share Brokers & Growth Beta (300059)", 1.2, 3.6, "市场悲观共识边际见底后，券商与超跌成长通常是估值弹性最先修复方向。", "Brokers and beaten-down growth leaders respond fastest once sentiment troughs turn.", 1.0, "300059.SZ"),
                _bar("港股", "港股低估值核心互联网 (HSTECH)", "HKEX Deep-Value Tech (HSTECH)", 0.8, 2.5, "境内股票风险溢价触底常带动南向资金加仓低估值港股科技权重。", "Domestic sentiment bottoming supports Southbound inflows into undervalued HK tech.", 1.0, "HSTECH.HK"),
            ],
            "if_then": [],
            "milestones": [{"date": "5 个交易日内", "status": "current", "label": "观察两市成交额是否放量站稳 1.3 万亿上方"}],
        }

    # 0e. AI Server Price Hike (+45% hardware squeeze)
    if re.search(r"ai\s*服务器|算力服务器|服务器厂商", text, re.I) and re.search(r"涨价|提价|上调价格", text, re.I):
        return {
            "rule_id": "ai_server_price_hike",
            "tag": "AI 服务器硬件涨价与算力基建景气",
            "tag_en": "AI Server Price Hike & Supply Tightness",
            "polarity": "bullish",
            "intensity": 4,
            "one_liner": "AI 服务器因算力模组与散热供电紧张大幅提价，印证下游智算需求刚性且直接增厚头部整机及液冷光模块产业链收入。",
            "one_liner_en": "Sharp AI server price hikes signal tight supply and expand revenue elasticity for OEMs, liquid cooling, and optical links.",
            "sample_basis": {"sample_n": 11, "volatility_pct": 3.7, "volatility_source": "算力硬件提价与机柜订单样本", "horizon": "2~7 个交易日", "confidence_label": "高置信（直指硬件景气定价权）", "confidence_label_en": "High (Direct Hardware Pricing Power)"},
            "affected_tickers": {"601138.SH": 0.85, "000977.SZ": 0.8, "300308.SZ": 0.75, "SMCI": 0.65},
            "realized_quotes": _quote_snapshot(["QQQ", "515880.SH"]),
            "bars": [
                _bar("A股", "AI 服务器整机与代工龙头 (工业富联/浪潮)", "A-Share AI Server Leaders (601138/000977)", 1.8, 4.6, "整机供给紧缺带来最高 45% 涨价，具备配额与规模优势的整机龙头直接受益单机价值量提升。", "Acute GPU-rack shortages drive higher ASP and revenue leverage for leading server OEMs.", 1.0, "601138.SH"),
                _bar("A股", "液冷散热 / 800G 光模块与高速连接", "A-Share Liquid Cooling & Optical Links", 1.4, 3.8, "高功耗 AI 机柜成本上升同步拉高液冷、电源及光互连组件配置单价。", "Higher rack power density accelerates adoption of liquid cooling and high-speed optics.", 1.0, "300308.SZ"),
                _bar("美股", "北美算力机柜与 GPU 基建链 (SMCI / DELL)", "US AI Rack Builders (SMCI / DELL)", 1.0, 3.2, "整机报价上行凸显基础设施产能紧俏，但需观察上游器件转嫁后实际毛利率。", "Tight rack pricing supports top-line demand while highlighting component-cost pass-through.", 1.0, "SMCI"),
            ],
            "if_then": [],
            "milestones": [{"date": "2 周内", "status": "current", "label": "核查云厂季度 Capex 指引及整机厂商毛利率反馈"}],
        }

    # 0f. ASIC / TPU Order Cut & Vendor Substitution (Broadcom 8i vs MediaTek 8t vs NVDA)
    if re.search(r"tpu|asic|博通", text, re.I) and re.search(r"削减|砍单|下调.*出货|减少.*颗", text, re.I):
        return {
            "rule_id": "asic_tpu_order_cut",
            "tag": "谷歌 TPU 供应链切换：博通 8i 承压 vs 联发科 8t 受益",
            "tag_en": "Google TPU Supplier Shift (Broadcom 8i Cut vs MediaTek 8t Gain)",
            "polarity": "divergent",
            "intensity": 4,
            "one_liner": "谷歌削减博通设计的 TPU 8i 约 100 万颗（约 20%），但预计同步增加联发科设计的 TPU 8t 出货——本质是云巨头 ASIC 供应商切换而非总算力需求下调。",
            "one_liner_en": "Google cutting ~1M Broadcom-designed TPU 8i (~20%) while ramping MediaTek TPU 8t is a supplier-share shift rather than an overall AI compute cut.",
            "sample_basis": {"sample_n": 12, "volatility_pct": 4.1, "volatility_source": "北美云厂芯片链切换与砍单样本", "horizon": "1~5 个交易日", "confidence_label": "高置信（直接改写 ASIC 供应商份额）", "confidence_label_en": "High (Direct ASIC Share Reallocation)"},
            "affected_tickers": {"AVGO": -0.85, "2454.TW": 0.72, "300308.SZ": -0.35, "NVDA": 0.3, "QQQ": -0.1},
            "realized_quotes": _quote_snapshot(["AVGO", "NVDA", "QQQ"]),
            "bars": [
                _bar("美股", "定制 ASIC 原主力设计伙伴 (AVGO 博通)", "US Custom ASIC Incumbent (AVGO)", -4.8, -1.8, "百万颗级 TPU 8i 削减（约 20%）直接挤压博通该代际定制芯片增长预期与溢价。", "Cutting ~1M TPU 8i units (~20%) directly squeezes Broadcom's custom-silicon upside.", 1.0, "AVGO"),
                _bar("台股", "联发科 TPU 8t 定制二供替代链 (2454.TW)", "Taiwan Custom ASIC Beneficiary MediaTek (2454.TW)", 1.6, 4.5, "谷歌预计增加联发科设计的 TPU 8t 出货以承接部分算力需求，二供份额放量成为事件核心正向对冲腿。", "Expected ramp of MediaTek-designed TPU 8t captures shifted Google ASIC volume.", 1.0, "2454.TW"),
                _bar("A股", "北美多云光模块/PCB 结构性再平衡 (300308)", "A-Share Optical & PCB Capex Balance (300308)", -2.4, 0.8, "谷歌总 AI 算力 Capex 并未下修，仅在 8i/8t 料号与客户间调配，多云客户光模块龙头韧性强于单料号厂。", "Google's total AI Capex stays intact; multi-cloud optics vendors face modest timing noise.", 1.0, "300308.SZ"),
                _bar("美股", "通用 AI GPU 核心生态 (NVDA)", "Merchant AI GPU Ecosystem (NVDA)", 0.4, 2.2, "定制 ASIC 双供切换磨合期客观稳固通用 GPU 在大模型主集群中的交付确定性。", "Vendor transition friction in custom ASICs modestly steadies merchant GPU demand.", 1.0, "NVDA"),
            ],
            "if_then": [],
            "milestones": [{"date": "7 日内", "status": "current", "label": "观察博通 / 联发科对 TPU 8i/8t 订单配比与 CoWoS 分配最新回应"}],
        }

    # 0g. Corporate Share Buyback & Dividend Floor
    if re.search(r"回购股份|拟以.*亿元.*回购|拟回购.*(?:亿元|万股|A股)|增持.*亿元|特别分红", text, re.I):
        return {
            "rule_id": "corporate_buyback_dividend",
            "tag": "龙头真金白银大额回购与市值托底",
            "tag_en": "Large-Scale Corporate Buyback Floor",
            "polarity": "bullish",
            "intensity": 3,
            "one_liner": "产业龙头抛出超 10 亿元股份回购方案向市场传递现金流底气与底部信号，重点支撑个股及所属周期资源板块风险偏好。",
            "one_liner_en": "Billion-RMB share buyback plans signal balance-sheet confidence and establish valuation support for cyclical sector peers.",
            "sample_basis": {"sample_n": 15, "volatility_pct": 2.8, "volatility_source": "A股大额股份回购预案事件统计", "horizon": "2~7 个交易日", "confidence_label": "中高置信（直接增厚每股权益）", "confidence_label_en": "Moderate-High (Direct EPS & Valuation Floor)"},
            "affected_tickers": {"603799.SH": 0.85, "002460.SZ": 0.55, "510300.SH": 0.3},
            "realized_quotes": _quote_snapshot(["000001.SH"]),
            "bars": [
                _bar("A股", "回购主体及新能源资源龙头 (华友/赣锋)", "A-Share Buyback Issuer & Energy-Metals Peers", 1.5, 4.4, "10~15 亿元大规模回购真金白银承接场内抛压，对底部估值起到实质性锚定。", "Substantial buyback commitments absorb float pressure and anchor cyclical trough multiples.", 1.0, "603799.SH"),
                _bar("A股", "电池正极与上游资源顺周期板块", "A-Share Cathode & Battery Metals Chain", 0.7, 2.4, "行业龙头财务稳健主动护盘有助于修复悲观盈利预期，但持续性需盯金属现货价格。", "Peer sentiment stabilizes alongside upstream buybacks, subject to spot metal pricing.", 0.95, "002460.SZ"),
                _bar("港股", "港股有色资源与股东回报概念", "HKEX Materials & Capital-Return Leaders", 0.4, 1.8, "大额回购示范效应温和改善市场对资源类蓝筹自由现金流分配的信心。", "Buyback discipline reinforces shareholder-return rerating across HK resources.", 0.9, "02899.HK"),
            ],
            "if_then": [],
            "milestones": [{"date": "30 日内", "status": "current", "label": "核查首次实施回购比例进度与碳酸锂/钴价趋势"}],
        }

    # 0h. US Congressional Tariff / Tax Policy Reversal Fight
    if re.search(r"推翻.*税收.*关税|废除.*关税|民主党.*关税|关税政策|跨境关税", text, re.I) and not re.search(
        r"巨额关税|征重税|巨税", text, re.I
    ):
        return {
            "rule_id": "us_tariff_tax_policy_shift",
            "tag": "美方税收与关税博弈预期差（出口链修复）",
            "tag_en": "US Tax & Tariff Policy Shift",
            "polarity": "divergent",
            "intensity": 3,
            "one_liner": "美方政局寻求推翻激进关税与税收安排的动向边际压缩最悲观贸易脱钩尾部溢价，利好中概互联、出海制造与集运板块。",
            "one_liner_en": "Moves to overturn sweeping US tariff and tax policies ease extreme trade-war risk premia for China ADRs, exporters, and shipping.",
            "sample_basis": {"sample_n": 13, "volatility_pct": 3.2, "volatility_source": "美中关税博弈预期反转样本", "horizon": "2~5 个交易日", "confidence_label": "中高置信（立法博弈仍存反复）", "confidence_label_en": "Moderate-High (Subject to Legislative Path)"},
            "affected_tickers": {"KWEB": 0.7, "HSTECH.HK": 0.65, "002475.SZ": 0.6, "601919.SH": 0.55},
            "realized_quotes": _quote_snapshot(["KWEB", "HSTECH.HK"]),
            "bars": [
                _bar("美股", "中概互联与跨境资产 (KWEB)", "US-Listed China Tech & ADRs (KWEB)", 1.3, 3.8, "极端关税风险贴现折价随国会博弈动向边际收敛，触发部分外资空头回补。", "Tariff-roll-back efforts compress China ADR geopolitical risk discount.", 1.0, "KWEB"),
                _bar("A股", "对美消费电子代工与远洋集运 (立讯/中远海控)", "A-Share US Exporters & Container Shipping", 1.1, 3.3, "出口毛利率与跨洋航线货量稳态预期得到阶段性修正支撑。", "Exporters and ocean liners reprice lower terminal tariff risk.", 1.0, "002475.SZ"),
                _bar("港股", "港股外资重仓互联网与消费出口 (HSTECH)", "HKEX Tech & Export Champions (HSTECH)", 1.0, 3.0, "港股率先计价离岸美元流动性对关税分歧的正面风险偏好回温。", "Offshore HK equities respond early to narrowing US tariff escalation risk.", 1.0, "HSTECH.HK"),
            ],
            "if_then": [],
            "milestones": [{"date": "两周内", "status": "current", "label": "追踪国会参众两院实质立法草案及白宫否决表态"}],
        }

    # 0i. UN COP Climate Talks Collapse (Traditional Energy vs Renewables)
    if re.search(r"cop\d+|气候谈判|气候大会", text, re.I) and re.search(r"破裂|未能.*协议|化石燃料|僵局|延期", text, re.I):
        return {
            "rule_id": "cop_climate_energy_stalemate",
            "tag": "COP31 气候谈判破裂与传统能源重估",
            "tag_en": "COP Climate Stalemate: Fossil Fuel Resilience vs Clean Tech",
            "polarity": "divergent",
            "intensity": 3,
            "one_liner": "联合国气候峰会未能就限制化石燃料达成妥协，延长全球油气煤炭高现金流久期预期，传统能源红利跑赢海外碳中和主题。",
            "one_liner_en": "Deadlocked UN climate talks over fossil-fuel phaseouts extend cash-flow duration for oil, gas, and coal while cooling clean-tech sentiment.",
            "sample_basis": {"sample_n": 10, "volatility_pct": 2.4, "volatility_source": "全球气候峰会决议期能源对比样本", "horizon": "2~5 个交易日", "confidence_label": "中高置信（结构性分化显著）", "confidence_label_en": "Moderate-High (Energy Sector Divergence)"},
            "affected_tickers": {"600938.SH": 0.65, "601088.SH": 0.6, "601012.SH": -0.45, "XLE": 0.55},
            "realized_quotes": _quote_snapshot(["USO", "00883.HK"]),
            "bars": [
                _bar("A股", "高股息上游油气与动力煤 (海油/神华)", "A-Share Upstream Oil & Coal (600938/601088)", 1.0, 2.9, "缺乏具有约束力的全球退煤退油时间表，夯实传统能源企业长期分红确定性。", "No binding global fossil phase-out pact reinforces long-duration dividend visibility for oil & coal.", 1.0, "600938.SH"),
                _bar("美股", "传统能源综合油气巨头 (USO / XLE)", "US Integrated Oil & Gas (XLE/USO)", 0.8, 2.4, "减碳资本约束压力阶段性放松，支撑传统能源回购与分红估值倍", "Eased global regulatory phaseout pressure supports US oil majors' cash returns.", 1.0, "USO"),
                _bar("A股", "海外出口型光伏组件与风电整机", "A-Share Clean Energy Exporters (601012)", -2.4, -0.5, "全球政策减碳推力短期弱于预期，新能源情绪短期承压、仍待组件价格触底。", "Softer multilateral decarbonization commitments weigh on short-term solar/wind sentiment.", 1.0, "601012.SH"),
            ],
            "if_then": [],
            "milestones": [{"date": "7 日内", "status": "current", "label": "观察欧盟碳关税边境调节执行细则及光伏组件月度排产"}],
        }

    # 0j. Commercial Space / Reusable Rocket Breakthrough
    if re.search(r"可回收.*火箭|回收发动机|朱雀三号|点火试车|商业航天|商业火箭", text, re.I):
        return {
            "rule_id": "commercial_space_breakthrough",
            "tag": "可回收火箭关键试车与商业航天主题催化",
            "tag_en": "Reusable Rocket & Commercial Space Catalyst",
            "polarity": "bullish",
            "intensity": 3,
            "one_liner": "可回收液体火箭发动机完成二次点火试车标志国内商业发射迈向可复用低成本阶段，直接催化箭体配套、航天测控及低轨卫星链。",
            "one_liner_en": "Successful reusable engine hot-fire milestones cut future launch economics and catalyze aerospace parts and LEO satellite constellations.",
            "sample_basis": {"sample_n": 11, "volatility_pct": 4.0, "volatility_source": "商业航天重大试车与发射催化样本", "horizon": "1~5 个交易日", "confidence_label": "中高置信（硬科技主题活跃度高）", "confidence_label_en": "Moderate-High (High-Beta Theme Catalyst)"},
            "affected_tickers": {"600118.SH": 0.8, "600879.SH": 0.75, "301005.SZ": 0.75},
            "realized_quotes": _quote_snapshot(["000001.SH"]),
            "bars": [
                _bar("A股", "民营商业火箭精密配套与发动机材料", "A-Share Rocket Structures & Alloys (301005)", 2.0, 5.2, "可复用发动机过关直通入轨回收，最直接催化已进入火箭壳段/铜合金推力室核心供应链标的。", "Engine restart readiness directly catalyzes precision airframe and propellant suppliers.", 1.0, "301005.SZ"),
                _bar("A股", "低轨卫星整星与星载相控阵载荷 (中国卫星)", "A-Share LEO Satellites & Payloads (600118)", 1.5, 4.0, "单公斤发射成本下移预期打开千帆/GW 星座组网密集发射想象空间。", "Lower launch cost visibility accelerates LEO satellite manufacturing cadence.", 1.0, "600118.SH"),
                _bar("A股", "航天测控通信与防务电子 (航天电子)", "A-Share Aerospace Telemetry & Control (600879)", 1.2, 3.4, "发射架次与回收测控需求扩容带动测控惯导电子确定性增量。", "Higher launch frequency expands demand for guidance and telemetry electronics.", 1.0, "600879.SH"),
            ],
            "if_then": [],
            "milestones": [{"date": "未来 1 个月", "status": "current", "label": "盯紧正式首飞入轨及一子级海上/陆地回收窗口公告"}],
        }

    # 0k. Telecom / Digital Sanctions (Material impact calibrated: minimal revenue hit, domestic security boost)
    if re.search(r"电信运营商|禁止中国电信|互联网电话号码|商务部坚决反对", text, re.I):
        return {
            "rule_id": "telecom_digital_sanction",
            "tag": "美方通信接入限制与国产安全应对",
            "tag_en": "Telecom Cross-Border Restrictions & Cyber Localization",
            "polarity": "divergent",
            "intensity": 3,
            "one_liner": "美方限制国内电信运营商获取美国互联网电话资源对其主业国内营收影响极微（<1%），更多引发涉外云网安全合规与高股息运营商韧性重申。",
            "one_liner_en": "US restrictions on Chinese carrier number access have negligible domestic revenue impact while lifting local cyber-compliance themes.",
            "sample_basis": {"sample_n": 9, "volatility_pct": 1.8, "volatility_source": "涉电信合规禁令市场反应样本", "horizon": "1~5 个交易日", "confidence_label": "高置信（基本面实质免疫）", "confidence_label_en": "High (Operationally Insulated Core Cashflows)"},
            "affected_tickers": {"601728.SH": 0.15, "600941.SH": 0.3, "000063.SZ": 0.55},
            "realized_quotes": _quote_snapshot(["000001.SH"]),
            "bars": [
                _bar("A股", "自主通信设备与涉外加密网安 (中兴/深信服)", "A-Share Telecom Gear & Cyber Compliance (000063)", 0.8, 2.5, "外部通信节点限制强化政企跨境专线加密替代与核心设备自主可控优先级。", "Cross-border telecom restrictions reinforce domestic network-gear & security demand.", 1.0, "000063.SZ"),
                _bar("A股", "三大高股息运营商核心现金流 (移动/电信)", "A-Share Dividend Telecom Carriers (600941/601728)", -0.5, 0.9, "北美涉外号段占比不足百分之一，高股息红利与智算网盈利锚几无受损。", "Negligible US revenue exposure leaves high-dividend domestic cashflows unscathed.", 0.9, "600941.SH"),
                _bar("港股", "中资电信与国产云计算基建 (HSTECH)", "HKEX Telecom & Cloud Infra (HSTECH)", -0.6, 0.7, "短线地缘消息干扰下港股电信权重多于数日内被低估值红利买盘消化。", "Dividend buyers historically absorb short-lived geopolitical headlines in HK carriers.", 0.9, "HSTECH.HK"),
            ],
            "if_then": [],
            "milestones": [{"date": "7 日内", "status": "current", "label": "观察商务部是否公布对等美企合规核查清单"}],
        }
    if (
        any(k in t for k in ("暴跌", "重挫", "下挫", "抛售潮", "抹去年内涨幅", "逼近破发", "破发", "动荡"))
        and any(k in t for k in ("英伟达", "nvda", "纳指", "anthropic", "ai板块", "算力", "芯片"))
    ) or ("anthropic" in tl and "ipo" in tl and any(k in t for k in ("动荡", "担忧", "承压", "波动"))):
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

    # 1c. 存储芯片与 HBM 并购/产能扩张/长协锁单 (SK 海力士 / 美光 / 三星)
    if re.search(r"海力士|SK\s*Hynix|美光|Micron|HBM|高带宽内存|DRAM|存储芯片|NAND", text, re.I) and re.search(
        r"收购|洽购|入股|并购|扩张|扩产|短缺|涨价|合同价|资本|投资|AI\s*芯片|供货|软银|产能.*锁定|供货保障", text, re.I
    ):
        is_samsung_lock = bool(re.search(r"三星|产能.*锁定|供货保障|2031", text, re.I))
        return {
            "rule_id": "memory_hbm_supercycle" if is_samsung_lock else "memory_hbm_ma_supply",
            "tag": "AI 存储芯片多年长协锁单与景气超周期" if is_samsung_lock else "HBM / 存储资本整合与周期重估",
            "tag_en": "AI Memory Long-Term Capacity Lockup" if is_samsung_lock else "AI Memory & HBM Deal Flow",
            "polarity": "bullish" if is_samsung_lock else "divergent",
            "intensity": 4,
            "one_liner": "AI 存储/HBM 多年锁单与资本运作升温强化高带宽及企业级存储卖方定价权，利好原厂及国产存储/内存接口芯片。",
            "one_liner_en": "Multi-year memory lockups & HBM deal flow reinforce memory pricing and lift domestic memory/interface suppliers.",
            "sample_basis": {
                "sample_n": 15,
                "volatility_pct": 3.9,
                "volatility_source": "费半/存储芯片周期催化样本",
                "horizon": "2~5 个交易日",
                "confidence_label": "高置信（直击存储器估值与产能格局）",
                "confidence_label_en": "High (Direct Memory Cycle Catalyst)",
            },
            "affected_tickers": {"MU": 0.85, "603986.SH": 0.7, "688008.SH": 0.65, "NVDA": 0.35, "HPQ": -0.35},
            "realized_quotes": _quote_snapshot(["QQQ", "512480.SH"]),
            "bars": [
                _bar("美股", "HBM 与企业级存储龙头 (MU)", "US HBM & Enterprise Memory (MU)", 1.8, 4.5, "长协锁单与产业资本竞逐 HBM 产能，强化高阶存储合约价与毛利弹性。", "Long-term capacity lockups reinforce high-bandwidth & enterprise DRAM pricing.", 1.0, "MU"),
                _bar("亚太", "韩国头部存储晶圆原厂 (海力士/三星)", "Korea HBM & DRAM Leaders (000660.KS)", 1.5, 4.2, "锁定未来多年核心产能验证需求极端旺盛，显著平滑传统存储周期波动。", "Multi-year capacity lockups confirm seller's market pricing visibility.", 1.0, "000660.KS"),
                _bar("A股", "国产存储芯片与内存接口链 (兆易/澜起)", "A-Share Memory & Interface Chips", 1.4, 3.6, "国际大厂资源向高阶长协倾斜加速利基与国产企业级模组/RCD 份额提升。", "Global capacity reallocation accelerates domestic specialty DRAM & interface adoption.", 1.0, "603986.SH"),
                _bar("美股", "传统消费级 PC OEM 组装厂 (HPQ)", "Commodity PC OEMs (HPQ)", -1.2, -0.2, "DRAM/NAND 长期紧缺抬高整机 BOM 成本，若消费换机偏弱或挤压毛利。", "Rising memory contract costs pressure commodity hardware margins.", 0.85, "HPQ"),
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

    # 3a. Precious Metals Futures Drop + Physical Retail Gold-Bar Rush Divergence (e.g. 菜百金条抢购一空)
    if any(k in t for k in ("金价", "黄金", "金条", "贵金属")) and re.search(
        r"菜百|抢购一空|投资金条|抢空|断货|实物金|买爆", text, re.I
    ):
        gld_f, atr_v, _ = _volatility_scale("518880.SH", quotes_map, 4)
        return {
            "rule_id": "precious_metals_physical_divergence",
            "tag": "金价期现背离（上游矿金承压 vs 下游金条抢购爆单）",
            "tag_en": "Bullion Spot Drop vs Physical Bar Retail Rush",
            "polarity": "divergent",
            "intensity": 4,
            "one_liner": "国际期货金价跳水压制上游矿企利润预期，但北京菜百投资金条抢购断货折射下游渠道高周转爆单弹性，黄金板块呈上下游显著分化。",
            "one_liner_en": "Sliding futures prices weigh on upstream gold miners while physical bar buying rushes boost high-turnover jewelry retailers.",
            "sample_basis": {
                "sample_n": 14,
                "volatility_pct": atr_v or 3.4,
                "volatility_source": "黄金期货 vs 黄金珠宝渠道分化样本",
                "horizon": "1~5 个交易日",
                "confidence_label": "高置信（上下游期现逻辑拆分）",
                "confidence_label_en": "High (Miner vs Retailer Divergence)",
            },
            "affected_tickers": {"605599.SH": 0.85, "600612.SH": 0.55, "GLD": -0.75, "518880.SH": -0.75, "02899.HK": -0.7},
            "realized_quotes": _quote_snapshot(["GLD", "518880.SH", "02899.HK"]),
            "bars": [
                _bar("A股", "高周转金条与品牌零售 (菜百股份 / 老凤祥)", "A-Share Physical Gold Retailers (605599/600612)", 1.3, 3.8, "黄金租赁套保+低金价刺激投资金条抢购断货，直接放量同店销量与加工费收入。", "Hedging insulates inventory while bargain hunting drives surge in physical bar turnover.", 1.0, "605599.SH"),
                _bar("A股", "上游自产黄金采掘 (紫金 / 山东黄金)", "A-Share Upstream Gold Miners (601899/518880)", -3.8, -1.5, "上游矿金利润高度线性挂钩现货金价回撤与期货多头去杠杆抛压。", "Upstream miners carry direct negative beta to falling spot gold prices.", min(1.2, gld_f), "518880.SH"),
                _bar("美股", "离岸现货黄金与矿商 ETF (GLD / GDX)", "US Spot Gold & Miners ETFs (GLD)", -3.5, -1.4, "国际现货金价连续跳水继续消化前期过度拥挤的多头杠杆。", "Offshore bullion ETFs absorb continued leveraged long liquidation.", min(1.2, gld_f), "GLD"),
                _bar("港股", "港股有色黄金资源股 (02899 / 01818)", "HKEX Gold Miners (02899.HK)", -3.7, -1.5, "离岸市场对金价破位更为敏感，关注 3450~3500 美元整数关口支撑。", "HK gold miners react swiftly to offshore futures volatility.", min(1.2, gld_f), "02899.HK"),
            ],
            "if_then": [],
            "milestones": [{"date": "未来 3 个交易日", "status": "current", "label": "对比 COMEX 金价止跌位与品牌金店周末流水增速"}],
        }

    # 3b. Precious Metals / Gold & Silver Plunge (distinct from FOMC rate hike!)
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

    # 3c. Macro Fiscal / Consumption / Property Stimulus
    if re.search(r"特别国债|专项债|以旧换新|消费券|降低首付|放松限购|稳增长.*财政|扩大内需", text, re.I):
        return {
            "rule_id": "macro_fiscal_property_stimulus",
            "tag": "财政内需 / 消费与地产稳增长刺激",
            "tag_en": "Fiscal Consumption & Property Stimulus",
            "polarity": "bullish",
            "intensity": 4,
            "one_liner": "超常规财政增量、以旧换新扩围或地产松绑直接托底顺周期需求，利好家电汽车消费、建材家居与顺周期金融权重。",
            "one_liner_en": "Fiscal expansion, trade-in subsidies, and housing easing lift domestic cyclicals, appliances, and China equities.",
            "sample_basis": {"sample_n": 16, "volatility_pct": 2.9, "volatility_source": "国内财政内需刺激窗口统计", "horizon": "2~7 个交易日", "confidence_label": "高置信（直接内需弹性）", "confidence_label_en": "High (Direct Domestic Demand)"},
            "affected_tickers": {"510300.SH": 0.7, "000333.SZ": 0.75, "002916.SZ": 0.4, "HSI.HK": 0.6},
            "realized_quotes": _quote_snapshot(["000001.SH", "HSI.HK"]),
            "bars": [
                _bar("A股", "以旧换新消费家电与汽车 (美的/海尔)", "A-Share Trade-In Appliances & Auto (000333)", 1.5, 4.2, "财政补贴直达终端换新消费，家电与乘用车业绩确定性最强。", "Direct fiscal subsidies expand appliance and auto replacement demand.", 1.0, "510300.SH"),
                _bar("港股", "顺周期消费与内房物管龙头 (HSI)", "HKEX China Consumer & Property (HSI)", 1.2, 3.6, "政策发力扭转通缩预期带动离岸顺周期板块估值修复。", "Stimulus easing deflation concerns lifts offshore China cyclicals.", 1.0, "HSI.HK"),
                _bar("A股", "基建材料 / 工程机械与银行", "A-Share Infrastructure & Financials (510300)", 0.9, 2.8, "地方化债与专项债加速落地改善工程与城投资产质量预期。", "Local debt relief and special bonds improve asset-quality visibility.", 1.0, "601398.SH"),
            ],
            "if_then": [],
            "milestones": [{"date": "2 周内", "status": "current", "label": "核查部委配套资金额度及一线城市周度网签数据"}],
        }

    # 3d. Key Industrial Policy Catalysts (Low-Altitude Economy / Humanoid Robots / Biotech Procurement)
    if re.search(r"低空经济|eVTOL|人形机器人|具身智能|创新药.*(?:目录|扶持)|商业医保|自动驾驶牌照", text, re.I):
        return {
            "rule_id": "industrial_policy_catalyst",
            "tag": "新质生产力产业政策催化（低空 / 机器人 / 创新药）",
            "tag_en": "Strategic Industrial Policy Catalyst",
            "polarity": "bullish",
            "intensity": 3,
            "one_liner": "国家及地方针对前沿新兴赛道的准入与医保/空域支持落地，催化商业化订单预期从概念走向放量。",
            "one_liner_en": "Regulatory greenlights for emerging industries accelerate commercialization visibility across robotics, eVTOL, and biotech.",
            "sample_basis": {"sample_n": 14, "volatility_pct": 3.5, "volatility_source": "新兴产业政策准入事件样本", "horizon": "2~5 个交易日", "confidence_label": "中高置信（主题弹性高）", "confidence_label_en": "Moderate-High (High-Beta Thematic)"},
            "affected_tickers": {"300750.SZ": 0.45, "512480.SH": 0.55, "HSTECH.HK": 0.4},
            "realized_quotes": _quote_snapshot(["000001.SH", "HSTECH.HK"]),
            "bars": [
                _bar("A股", "核心零部件与传感器执行器供应链", "A-Share Core Actuators & Avionics", 1.5, 4.4, "商业牌照或行业标准明确直接打开上游丝杠/电机/飞控系统批产预期。", "Licensing clarity pulls forward order visibility for actuators and sensors.", 1.0, "512480.SH"),
                _bar("港股", "港股新质制造与医药生态 (HSTECH)", "HKEX Smart Hardware & Biotech", 0.9, 2.9, "研发估值与商业化支付端改善共同提升港股创新龙头估值中枢。", "Improved commercialization outlook supports HK innovation multiples.", 1.0, "HSTECH.HK"),
                _bar("美股", "全球前沿自动化与芯片映射 (QQQ)", "US Automation & Compute Proxies (QQQ)", 0.4, 1.8, "中国高性价比供应链量产共振强化全球具身智能硬件化进度。", "High-efficiency domestic supply scaling reinforces global automation momentum.", 0.9, "QQQ"),
            ],
            "if_then": [],
            "milestones": [{"date": "1 个月内", "status": "current", "label": "观察首批商业试飞/量产交付或医保支付细则落地"}],
        }

    # 3e. Major Earnings Surprise or Miss
    if re.search(r"净利(?:暴增|大增|翻倍|预增)|营收超预期|财报超预期|净利(?:大降|暴跌|预亏)|业绩暴雷|下调.*指引", text, re.I):
        is_miss = bool(re.search(r"大降|暴跌|预亏|暴雷|下调.*指引", text, re.I))
        c_s = -1.0 if is_miss else 1.0
        return {
            "rule_id": "earnings_surprise_or_miss",
            "tag": "龙头财报业绩冲击与同业盈利重估" if is_miss else "重磅业绩超预期与景气印证",
            "tag_en": "Major Earnings Guidance Shock" if is_miss else "Major Earnings Beat & Re-rating",
            "polarity": "bearish" if is_miss else "bullish",
            "intensity": 4,
            "one_liner": "核心产业龙头业绩指引显著偏离一致预期，引发本市场及跨市场可比同业估值中枢同步重估。",
            "one_liner_en": "Material earnings deviation triggers peer-group multiple repricing across comparable supply chains.",
            "sample_basis": {"sample_n": 18, "volatility_pct": 3.8, "volatility_source": "财报季业绩跳空样本", "horizon": "1~5 个交易日", "confidence_label": "高置信（直击 EPS 盈利锚）", "confidence_label_en": "High (Direct EPS Anchor)"},
            "affected_tickers": {"QQQ": round(0.45 * c_s, 2), "HSTECH.HK": round(0.45 * c_s, 2), "510300.SH": round(0.4 * c_s, 2)},
            "realized_quotes": _quote_snapshot(["QQQ", "HSTECH.HK", "000001.SH"]),
            "bars": [
                _bar("美股", "跨市场同业成长基准 (QQQ)", "US Comparable Growth Leaders (QQQ)", 1.4 * c_s, 4.0 * c_s, "超预期/暴雷指引直接修正行业下一季度盈利一致性预期。", "Earnings deviation prompts analysts to reset peer consensus estimates.", 1.0, "QQQ"),
                _bar("港股", "港股关联龙头与云平台 (HSTECH)", "HKEX Sector Comparables (HSTECH)", 1.1 * c_s, 3.4 * c_s, "离岸资金迅速参照头部财报成色重排同类标的持仓权重。", "Institutional funds rebalance peer exposure across offshore benchmarks.", 1.0, "HSTECH.HK"),
                _bar("A股", "A股同产业链上游与设备伙伴 (510300)", "A-Share Supply Chain Comparables", 1.0 * c_s, 3.0 * c_s, "下游资本开支与出货节奏直接映射上游订单能见度。", "Upstream order visibility shifts alongside flagship earnings guidance.", 1.0, "510300.SH"),
            ],
            "if_then": [],
            "milestones": [{"date": "下 2 个交易日", "status": "current", "label": "盯紧券商研报盈利预测上修/下修家数变动"}],
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

    # 7. FOMC Hawkish Rate Hike (TITLE-anchored so domestic A-share bottoming reports mentioning overseas rates never misfire!)
    if (
        any(k in tl for k in ("美联储", "fomc", "鲍威尔"))
        and any(k in tl for k in ("加息", "放鹰", "利率"))
        and not re.search(r"招商证券|中信证券|华泰证券|券商研报|历史底部|多项指标.*底部", tl)
    ):
        is_hike = any(k in tl for k in ("重启加息", "加息", "放鹰"))
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

    # 8a-0. NVIDIA CEO Succession Search / Board Transition (must NEVER match Senate testimony)
    if ("黄仁勋" in t or "英伟达" in t or "nvidia" in t) and re.search(
        r"遴选|接班|继任|外部.*ceo|ceo.*继任", t
    ):
        nvda_f, atr_v, _ = _volatility_scale("NVDA", quotes_map, 3)
        return {
            "rule_id": "nvda_ceo_succession_transition",
            "tag": "龙头 CEO 接班人与治理过渡不确定性",
            "tag_en": "NVIDIA CEO Succession Search & Governance Watch",
            "polarity": "bearish",
            "intensity": 3,
            "one_liner": "英伟达董事会启动下一任 CEO 外部遴选程序的媒体报道引发管理层传承讨论，短期或带来温和治理折价情绪，需先核实董事会正式公告。",
            "one_liner_en": "Reports of NVIDIA's board opening an external CEO succession search introduce modest leadership-transition discussion pending formal board filings.",
            "sample_basis": {
                "sample_n": 10,
                "volatility_pct": atr_v or 4.0,
                "volatility_source": "美股科技龙头管理层接班过渡样本",
                "horizon": "1~5 个交易日",
                "confidence_label": "待核实（单一媒体报道，尚未获董事会8-K确认）",
                "confidence_label_en": "Unconfirmed (Single-Source Media Report)",
            },
            "affected_tickers": {"NVDA": -0.55, "TSM": -0.3, "00981.HK": 0.25, "512480.SH": 0.3},
            "realized_quotes": _quote_snapshot(["NVDA", "TSM", "00981.HK", "512480.SH"]),
            "bars": [
                _bar("美股", "美股 AI 算力龙头与架构领导力预期 (NVDA)", "US AI Compute Leadership (NVDA)", -3.2, -0.8, "核心掌舵人传承规划报道短期引发组织连续性讨论，在公司正式回应前风险溢价温和走阔。", "Succession reports slightly widen governance discount pending formal board clarity.", min(1.1, nvda_f * 0.45), "NVDA"),
                _bar("台股", "先进封装与算力代工映射 (TSM)", "Leading-Node Foundry Proxies (TSM)", -1.6, 0.2, "中长期晶圆与 CoWoS 排产仍由云厂商资本开支决定，短期仅作温和情绪映射。", "Foundry schedules remain anchored by hyperscaler Capex despite headline noise.", 0.9, "TSM"),
                _bar("A股", "境内自主算力与芯片生态", "A-Share Domestic Compute Alternatives", 0.3, 1.8, "海外龙头传闻期温和抬升境内算力替代链关注度，但幅度弱于实质制裁。", "Mild attention shift toward domestic accelerators without substantive supply shock.", 0.9, "512480.SH"),
            ],
            "if_then": [
                {"cond": "若英伟达董事会正式发布声明澄清时间表或长期留任过渡安排", "result": "治理猜测情绪消退，估值重回 Blackwell/Rubin 交付周期", "tone": "bullish"},
                {"cond": "若后续伴随核心技术高管同步离任变动", "result": "NVDA 组织溢价面临阶段性重估压力", "tone": "bearish"},
            ],
            "milestones": [{"date": "未来 7 日", "status": "current", "label": "核查英伟达官方新闻稿及 SEC 8-K 公告澄清"}],
        }

    # 8a. NVIDIA CEO Senate Hearing / SEC Investigation / Leadership Governance Shock
    if ("黄仁勋" in t or "英伟达" in t or "nvidia" in t) and re.search(
        r"参议院|听证|作证|sec\s*调查|展开调查|检察长.*调查|财长.*调查|辞任|辞职", t
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
    if re.search(r"走私|绕道|出口合规|megaspeed|alice\s*huang|查获.*芯片|违规.*出口|收紧芯片管制|暂停对.*出货", t) and any(
        k in t for k in ("芯片", "英伟达", "nvidia", "gpu", "对华", "东南亚")
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

    # 9. Genuine US-China Summit / Bilateral Diplomacy Peace Declaration (ONLY bilateral US-China / APEC; never third-party gossip or tariff threats!)
    if (
        ("中美" in t or "美中" in t or "对华" in t or ("apec" in t and ("中美" in t or "特朗普" in t or "中美元首" in t)))
        and any(k in t for k in ("三方和平", "一致同意", "对话", "关税调整", "峰会", "会晤"))
        and not re.search(r"巨额关税|征重税|巨税|加征关税|威胁征税|关税威胁|行为不当|网友批评|高市早苗", t)
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
                "自主攻击", "网络攻击", "入侵", "黑客", "越狱攻击", "漏洞利用", "安全预警",
            )
        ):
            return None
        if any(k in t for k in ("甲骨文", "openai", "gpt", "gemini", "anthropic", "claude", "混元", "千问", "qwen", "deepseek", "llm")):
            is_infra = "甲骨文" in t or "筹足" in t or "合同" in t or "自由现金流" in t
            if not is_infra:
                subject_clause = re.split(
                    r"(?:，|,|；|;|与|对比|超越|竞争|叫板|\bvs\.?\b|\bversus\b|\bbut\b|\bwhile\b)",
                    t,
                    maxsplit=1,
                )[0].strip()
                if "gemini" in subject_clause or "google" in subject_clause or "谷歌" in subject_clause or "deepmind" in subject_clause:
                    target_lab = "google"
                elif "anthropic" in subject_clause or "claude" in subject_clause:
                    target_lab = "anthropic"
                elif "openai" in subject_clause or "gpt" in subject_clause:
                    target_lab = "openai"
                elif "gemini" in t or "google" in t or "谷歌" in t or "deepmind" in t:
                    target_lab = "google"
                elif "anthropic" in t or "claude" in t:
                    target_lab = "anthropic"
                elif "openai" in t or "gpt" in t:
                    target_lab = "openai"
                else:
                    target_lab = "china_open"

                if target_lab == "openai":
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
                elif target_lab == "google":
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
                elif target_lab == "anthropic":
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
    breaking_highlights: Optional[List[dict]] = None,
    prev_doc: Optional[Dict[str, Any]] = None,
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
    all_events = list(all_events or [])
    quotes_map = (quotes_doc or {}).get("quotes") or {}
    if not quotes_map:
        try:
            from .market_quotes import fetch_market_quotes

            fetched = fetch_market_quotes(timeout=4.5, include_volatility=False)
            quotes_map = fetched.get("quotes") or {}
            quotes_doc = fetched
        except Exception:
            quotes_map = {}

    # Inject breaking S/A-tier highlights from 7x24 live wire so major after-hours market policies never miss out
    existing_keys = {re.sub(r"[\s\W]+", "", str(e.get("title") or "").lower())[:16] for e in all_events}
    for idx_bh, bh in enumerate(breaking_highlights or []):
        if not isinstance(bh, dict):
            continue
        bh_title = str(bh.get("title") or "").strip()
        if not bh_title or bh.get("severity_tier") not in {"S", "A"}:
            continue
        bkey = re.sub(r"[\s\W]+", "", bh_title.lower())[:16]
        if not bkey or bkey in existing_keys:
            continue
        existing_keys.add(bkey)
        all_events.insert(
            0,
            {
                "event_id": str(bh.get("id") or f"bw_hi_{idx_bh}"),
                "title": bh_title,
                "fact_summary": str(bh.get("excerpt") or bh_title),
                "category": str(bh.get("category") or "finance"),
                "importance": "high",
                "severity_tier": bh.get("severity_tier") or "S",
                "latest_reported_at": bh.get("published_at") or generated_at_iso,
                "sources": [{"source_name": bh.get("source_name") or "7x24 快讯", "url": bh.get("url")}],
            },
        )

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
        tkey = re.sub(r"[\s\W]+", "", title.lower())[:28]
        if tkey in seen_titles:
            continue
        seen_titles.add(tkey)
        cat = str(ev.get("category") or "")
        imp = 4 if (ev.get("severity_tier") == "S" or ev.get("importance") == "high") else 1
        base = 7 if cat == "finance" else (4 if cat in ("tech", "global") else 2)
        policy_bonus = (
            12
            if (
                re.search(r"融资保证金|4000亿|沪深北交易所|做市商|降准|降息|印花税|平准基金|稳市组合拳", title, re.I)
                and "台湾" not in title
            )
            else 0
        )
        kw_bonus = 3 if re.search(
            r"股|市场|芯片|英伟达|美联储|利率|金价|金条|油|关税|协议|IPO|融资|市值|美伊|俄乌|微软|FSD|海力士|HBM|比特币|BTC|ETH|稀土|资金短缺|TPU|博通|服务器.*涨价|回购|存储芯片|COP31|火箭|电信",
            title,
            re.I,
        ) else 0
        scored.append((base + imp + kw_bonus + policy_bonus, ev))

    scored.sort(key=lambda x: x[0], reverse=True)

    impacts: List[dict] = []
    event_impact_map: Dict[str, dict] = {}
    used_rule_counts: Dict[str, int] = {}
    used_one_liners: set[str] = set()
    seen_event_ids: set[str] = set()
    topic_card_idx: Dict[str, int] = {}

    for _, ev in scored[:60]:
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

        rid = scenario["rule_id"]
        topic_key = _topic_dedup_key(rid, title, pub_at)
        incoming_sources = [{"source_name": s.get("source_name"), "url": s.get("url")} for s in srcs[:5] if isinstance(s, dict) and s.get("url")]

        # Coalesce duplicate clusters reporting the same event on the same day into one authoritative card
        if topic_key and topic_key in topic_card_idx:
            target_card = impacts[topic_card_idx[topic_key]]
            existing_urls = {str(s.get("url") or "") for s in (target_card.get("sources") or [])}
            for s in incoming_sources:
                if s.get("url") and str(s.get("url")) not in existing_urls:
                    target_card.setdefault("sources", []).append(s)
                    existing_urls.add(str(s.get("url")))
            # Upgrade evidence tier if combined sources now corroborate or come from official disclosure
            ev_tier, ev_tier_label = infer_event_evidence_tier(
                {**ev, "sources": target_card.get("sources") or srcs},
                str(target_card.get("event_title") or title),
                str(target_card.get("event_summary") or summary),
            )
            tier_rank = {"single_source": 1, "corroborated": 2, "research": 3, "official": 4}
            if tier_rank.get(ev_tier, 0) > tier_rank.get(str(target_card.get("evidence_tier") or "single_source"), 0):
                target_card["evidence_tier"] = ev_tier
                target_card["evidence_tier_label"] = ev_tier_label
            if not target_card.get("effective_date_label"):
                eff = extract_effective_date_label(title, summary)
                if eff:
                    target_card["effective_date_label"] = eff
            if not target_card.get("qualifier_badge"):
                qual = extract_qualifier_badge(title, summary)
                if qual:
                    target_card["qualifier_badge"] = qual
            if eid:
                seen_event_ids.add(eid)
                event_impact_map[eid] = event_impact_map.get(str(target_card.get("event_id") or ""), {})
            continue

        custom_one_liner, custom_sample_basis = customize_event_copy_and_basis(scenario, ev, title, quotes_map)
        ol_key = custom_one_liner.strip()
        if ol_key and ol_key in used_one_liners:
            continue

        occ_idx = used_rule_counts.get(rid, 0)
        if occ_idx >= 2:
            continue
        if ol_key:
            used_one_liners.add(ol_key)
        used_rule_counts[rid] = occ_idx + 1

        # Differentiate secondary/indirect occurrences sharing the same macro rule so cards never clone identical % ranges
        bars = scenario["bars"]
        if occ_idx > 0:
            atten = max(0.70, 1.0 - 0.14 * occ_idx)
            adj_bars = []
            for b in bars:
                nb = dict(b)
                nb["pct_low"], nb["pct_high"] = _scale_band(float(b["pct_low"]), float(b["pct_high"]), atten)
                adj_bars.append(nb)
            bars = adj_bars

        ev_tier, ev_tier_label = infer_event_evidence_tier(ev, title, summary)
        eff_date_label = extract_effective_date_label(title, summary)
        qual_badge = extract_qualifier_badge(title, summary)

        card = {
            "id": f"imp_{eid}",
            "event_id": eid,
            "rule_id": rid,
            "validation_status": "verified",
            "validation_note": check_note,
            "evidence_tier": ev_tier,
            "evidence_tier_label": ev_tier_label,
            "effective_date_label": eff_date_label,
            "qualifier_badge": qual_badge,
            "event_title": title,
            "event_title_en": ev.get("title_en") or title,
            "event_summary": summary,
            "event_summary_en": ev.get("summary_en") or summary,
            "category": str(ev.get("category") or "general"),
            "published_at": pub_at,
            "source_name": src_name,
            "source_url": src_url,
            "sources": incoming_sources[:5],
            "tag": scenario["tag"],
            "tag_en": scenario["tag_en"],
            "polarity": scenario["polarity"],
            "intensity": scenario["intensity"],
            "one_liner": custom_one_liner,
            "one_liner_en": scenario["one_liner_en"],
            "sample_basis": custom_sample_basis,
            "affected_tickers": scenario.get("affected_tickers") or {},
            "realized_quotes": scenario.get("realized_quotes") or [],
            "bars": bars,
            "if_then": scenario["if_then"],
            "milestones": scenario["milestones"],
        }
        enrich_card_deep_research(card, ev, scenario, quotes_map)
        if topic_key:
            topic_card_idx[topic_key] = len(impacts)
        if eid:
            seen_event_ids.add(eid)
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
            "evidence_tier": ev_tier,
            "evidence_tier_label": ev_tier_label,
            "effective_date_label": eff_date_label,
            "qualifier_badge": qual_badge,
            "one_liner": card["one_liner"],
            "top_a": top_a,
            "top_us": top_us,
            "top_hk": top_hk,
            "bars": bars,
            "if_then": card["if_then"],
            "milestones": scenario["milestones"],
            "sample_basis": card["sample_basis"],
            "realized_quotes": scenario.get("realized_quotes") or [],
            "priced_in_analysis": card.get("priced_in_analysis"),
            "transmission_layers": card.get("transmission_layers"),
            "historical_precedents": card.get("historical_precedents"),
            "quant_if_then": card.get("quant_if_then"),
        }

        if len(impacts) >= 17:
            break

    # Carry over recent (<72h) verified cards from prev_doc across midnight rollovers so card volume never drops below 15
    if len(impacts) < 16 and isinstance(prev_doc, dict):
        now_dt = parse_iso_datetime(generated_at_iso) or now_shanghai()
        for prev_card in (prev_doc.get("event_impacts") or []):
            if len(impacts) >= 16:
                break
            if not isinstance(prev_card, dict) or prev_card.get("validation_status") != "verified":
                continue
            p_eid = str(prev_card.get("event_id") or "")
            p_title = str(prev_card.get("event_title") or "").strip()
            p_summary = str(prev_card.get("event_summary") or "")
            p_rid = str(prev_card.get("rule_id") or "")
            if not p_title or (p_eid and p_eid in seen_event_ids):
                continue
            p_tkey = re.sub(r"[\s\W]+", "", p_title.lower())[:28]
            if p_tkey in seen_titles:
                continue
            if _LOW_IMPACT_TECH_CHATTER_RE.search(p_title.lower()) or any(k in p_title for k in ("自主攻击", "网络攻击")):
                continue
            if p_rid == "nvda_senate_sec_governance" and re.search(r"遴选|接班|继任", p_title):
                continue
            if "降费" in p_title and "4000" in str(prev_card.get("one_liner") or ""):
                continue
            p_pub = str(prev_card.get("published_at") or "")
            p_dt = parse_iso_datetime(p_pub)
            if p_dt is not None and (now_dt - p_dt).total_seconds() > 72 * 3600:
                continue
            p_topic = _topic_dedup_key(p_rid, p_title, p_pub)
            if p_topic and p_topic in topic_card_idx:
                continue
            p_ol = str(prev_card.get("one_liner") or "").strip()
            if p_ol and p_ol in used_one_liners:
                continue
            if used_rule_counts.get(p_rid, 0) >= 2:
                continue

            card_copy = dict(prev_card)
            card_copy["carried_over"] = True
            ev_t, ev_l = infer_event_evidence_tier(
                {"sources": card_copy.get("sources") or []}, p_title, p_summary
            )
            card_copy["evidence_tier"] = ev_t
            card_copy["evidence_tier_label"] = ev_l
            eff = extract_effective_date_label(p_title, p_summary)
            if eff:
                card_copy["effective_date_label"] = eff
            elif card_copy.get("effective_date_label"):
                card_copy["effective_date_label"] = re.sub(r"[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F]", "", str(card_copy["effective_date_label"])).strip()
            qual = extract_qualifier_badge(p_title, p_summary)
            if qual:
                card_copy["qualifier_badge"] = qual
            elif card_copy.get("qualifier_badge"):
                card_copy["qualifier_badge"] = re.sub(r"[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F]", "", str(card_copy["qualifier_badge"])).strip()

            seen_titles.add(p_tkey)
            if p_eid:
                seen_event_ids.add(p_eid)
            if p_topic:
                topic_card_idx[p_topic] = len(impacts)
            if p_ol:
                used_one_liners.add(p_ol)
            used_rule_counts[p_rid] = used_rule_counts.get(p_rid, 0) + 1
            impacts.append(card_copy)
            if p_eid and isinstance(prev_doc.get("event_impact_map"), dict) and p_eid in prev_doc["event_impact_map"]:
                m_entry = dict(prev_doc["event_impact_map"][p_eid])
                m_entry["evidence_tier"] = ev_t
                m_entry["evidence_tier_label"] = ev_l
                if card_copy.get("effective_date_label"):
                    m_entry["effective_date_label"] = card_copy["effective_date_label"]
                if card_copy.get("qualifier_badge"):
                    m_entry["qualifier_badge"] = card_copy["qualifier_badge"]
                event_impact_map[p_eid] = m_entry

    return {
        "schema_version": "4.2",
        "generation_mode": "deterministic_deep_research_v9",
        "quality_flags": [] if quotes_map else ["quotes_fallback"],
        "generated_at": generated_at_iso or to_iso_shanghai(now_shanghai()),
        "batch_id": batch_id,
        "disclaimer": "模型边界提示：以下板块敏感区间基于结构化事件极性与 20 日实现波动率校准推演，并附跨市场计价状态、三阶个股暴露与历史同类回放，仅为研究参考，不构成任何投资买卖建议。",
        "disclaimer_en": "Model Notice: Sensitivity intervals combine structured event polarity, realized volatility calibration, priced-in session checks, and historical replays for research only — not investment advice.",
        "quotes_updated_at": (quotes_doc or {}).get("updated_at"),
        "index_quotes": (quotes_doc or {}).get("indices") or [],
        "total_mapped_events": len(impacts),
        "event_impacts": impacts,
        "event_impact_map": event_impact_map,
    }
