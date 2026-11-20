"""Per-Event Financial Transmission & Market Impact Engine (data/finance_impact.json).

Applies structured, visual A-Share & US-Share impact forecasts directly to EVERY
market-moving breaking event (no standalone gimmicky simulator):
1. Matches every major event across finance/global/tech/general to causal transmission logic;
2. Outputs numeric sector impact bands (`pct_low`, `pct_high`) for clean horizontal bar charts;
3. Provides an `event_impact_map` keyed by `event_id` so every news card in the app
   displays inline market predictions right next to the news itself.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


_EVENT_MARKET_RULES: List[Dict[str, Any]] = [
    {
        "rule_id": "fed_rate_gold_usd",
        "pattern": re.compile(r"(?:美联储|fomc|加息|降息|沃勒|鲍威尔|美元指数|现货黄金|金价|美债|通胀|cpi|非农)", re.I),
        "tag": "央行利率 · 流动性",
        "tag_en": "Fed & Liquidity",
        "polarity": "divergent",
        "intensity": 5,
        "one_liner": "利率预期直接改写全球资产折现率：鹰派利空黄金与高估值成长股，利好美元与高股息银行；鸽派则反向修复。",
        "one_liner_en": "Rate expectations reprice global discount rates: hawkish surprises weigh on gold and growth tech while supporting banks/USD.",
        "bars": [
            {"market": "A股", "sector": "黄金与有色金属", "sector_en": "A-Share Gold & Metals", "pct_low": -4.5, "pct_high": -1.8, "direction": "negative", "logic": "实际利率与美元走强压制贵金属定价"},
            {"market": "A股", "sector": "银行 / 高股息红利", "sector_en": "A-Share Banks & Dividend", "pct_low": 0.8, "pct_high": 2.4, "direction": "positive", "logic": "高利率与避险期资金偏好稳定分红"},
            {"market": "美股", "sector": "纳指成长科技 (QQQ)", "sector_en": "Nasdaq Growth (QQQ)", "pct_low": -4.0, "pct_high": -1.5, "direction": "negative", "logic": "美债收益率抬升压缩远期估值倍数"},
            {"market": "大宗", "sector": "现货黄金 (GLD)", "sector_en": "Spot Gold (GLD)", "pct_low": -5.0, "pct_high": -2.0, "direction": "negative", "logic": "无息资产短线遭遇美元虹吸"},
        ],
        "if_then": [
            {"cond": "若释放降息/暂停加息", "result": "纳指 & 黄金快速修复 +2%~+4.5%", "tone": "bullish"},
            {"cond": "若加息 +25bp 落地", "result": "黄金有色承压 -2%~-4%，红利抗跌", "tone": "bearish"},
        ],
        "milestones": [
            {"date": "已发生", "status": "done", "label": "纪要/官员偏鹰表态引发利率重定价"},
            {"date": "当前", "status": "current", "label": "市场博弈 12 月议息路径与美元 104 关口"},
            {"date": "12-10", "status": "upcoming", "label": "FOMC 议息决议与最新点阵图落地验证"},
        ],
    },
    {
        "rule_id": "us_china_apec_tariff",
        "pattern": re.compile(r"(?:apec|特朗普.*(?:访华|深圳|中国|会晤|关税)|中美元首|自贸协定|关税|贸易战|关税豁免)", re.I),
        "tag": "地缘外交 · 关税",
        "tag_en": "Geopolitics & Tariffs",
        "polarity": "divergent",
        "intensity": 5,
        "one_liner": "大国高层会晤重估未来关税清单与科技管制边界：释放缓和催化中概与出口链修复，摩擦升级则利好国产替代。",
        "one_liner_en": "US-China summits reprice tariff schedules and export curbs, swinging Chinese ADRs, exporters, and domestic semiconductors.",
        "bars": [
            {"market": "美股", "sector": "中概互联 (KWEB)", "sector_en": "China ADRs (KWEB)", "pct_low": 2.5, "pct_high": 6.0, "direction": "positive", "logic": "外交缓和信号最直接修复外资风险偏好"},
            {"market": "A股", "sector": "出口链 / 消费电子 / 航运", "sector_en": "Exporters & Shipping", "pct_low": 2.0, "pct_high": 5.0, "direction": "positive", "logic": "对美敞口高的家电与航运对关税边际最敏感"},
            {"market": "A股", "sector": "国产半导体设备 / 信创", "sector_en": "Domestic Semis", "pct_low": 1.8, "pct_high": 4.5, "direction": "positive", "logic": "无论管制松紧，自主可控均为中线确定主线"},
            {"market": "美股", "sector": "在华营收美股 (AAPL/TSLA)", "sector_en": "China-Exposed US Tech", "pct_low": 1.2, "pct_high": 3.5, "direction": "positive", "logic": "供应链与亚太市场关税担忧阶段缓解"},
        ],
        "if_then": [
            {"cond": "若落地关税豁免/联合公报", "result": "KWEB 领涨 +4%~+7%，A股出口链 +3%~+6%", "tone": "bullish"},
            {"cond": "若加码芯片/关税限制", "result": "出口链 -2%~-5%，国产半导体逆势 +2%~+5%", "tone": "bearish"},
        ],
        "milestones": [
            {"date": "已发生", "status": "done", "label": "元首抵深与多边经贸谈判启动"},
            {"date": "当前", "status": "current", "label": "双边会晤与经贸框架磋商窗口"},
            {"date": "下周", "status": "upcoming", "label": "追踪联合声明与具体关税清单细则"},
        ],
    },
    {
        "rule_id": "ai_compute_ipo_chip",
        "pattern": re.compile(r"(?:anthropic|ipo|英伟达|nvidia|nvda|算力|光模块|amd|台积电|tsmc|hbm|存储芯片|数据中心|液冷)", re.I),
        "tag": "AI 算力 · 芯片链",
        "tag_en": "AI Compute & Semis",
        "polarity": "bullish",
        "intensity": 5,
        "one_liner": "AI 巨头巨额融资与芯片路线迭代锁定全球算力资本开支，直接拉动上游光模块、服务器液冷与芯片封装订单。",
        "one_liner_en": "Massive AI capital raises and silicon roadmaps anchor 2027 capex across optics, cooling, foundries, and GPU peers.",
        "bars": [
            {"market": "A股", "sector": "CPO 光模块 / 液冷 / PCB", "sector_en": "A-Share Optics & Cooling", "pct_low": 2.2, "pct_high": 5.5, "direction": "positive", "logic": "海外云厂与大模型资本开支直接转化为订单"},
            {"market": "A股", "sector": "国产算力 / 封测与存储", "sector_en": "Domestic Compute & Memory", "pct_low": 1.5, "pct_high": 4.0, "direction": "positive", "logic": "HBM 紧缺与算力国产化双轮驱动"},
            {"market": "美股", "sector": "算力芯片 (NVDA / AMD / TSM)", "sector_en": "US AI Semis", "pct_low": 1.8, "pct_high": 4.8, "direction": "positive", "logic": "核心业绩与二线替代方案同步重估"},
            {"market": "美股", "sector": "云巨头与 AI 电力 (AMZN/VST)", "sector_en": "Hyperscalers & Power", "pct_low": 1.2, "pct_high": 3.2, "direction": "positive", "logic": "大模型训练推理锁定云消耗与数据中心电力"},
        ],
        "if_then": [
            {"cond": "若挂牌/财报超预期", "result": "光模块与算力链共振 +2.5%~+5.5%", "tone": "bullish"},
            {"cond": "若高开抽血或出口收紧", "result": "高位算力短线回吐 -2%~-4%", "tone": "bearish"},
        ],
        "milestones": [
            {"date": "已发生", "status": "done", "label": "头部芯片财报/大模型 IPO 定价超预期"},
            {"date": "当前", "status": "current", "label": "二级市场重估 AI 算力与云厂商估值锚"},
            {"date": "下月", "status": "upcoming", "label": "验证云巨头季度 Capex 指引与出货量"},
        ],
    },
    {
        "rule_id": "ai_model_software_agent",
        "pattern": re.compile(r"(?:gemini|neon|carbon|hydrogen|openai|gpt-6|claude|qwen|千问|kimi|混元|deepseek|大模型|智能体|agent|开源模型)", re.I),
        "tag": "AI 模型 · 应用商业化",
        "tag_en": "AI Models & Software",
        "polarity": "bullish",
        "intensity": 4,
        "one_liner": "新一代高性价比推理模型（如 Gemini 4 Neon、GPT-6.2、Qwen4、混元 Hy4）大幅压低 Token 成本，直接引爆 AI 应用、编程与端侧换机潮。",
        "one_liner_en": "Faster, cheaper frontier models slash inference unit costs, accelerating SaaS/Agent adoption and edge device upgrades.",
        "bars": [
            {"market": "A股", "sector": "AI 应用软件 / Agent / 办公", "sector_en": "A-Share AI Apps & SaaS", "pct_low": 1.8, "pct_high": 4.6, "direction": "positive", "logic": "底层模型降本增效直接打开应用端商业利润率"},
            {"market": "A股", "sector": "端侧 AI 硬件 (AI手机/PC/耳机)", "sector_en": "Edge AI Hardware", "pct_low": 1.2, "pct_high": 3.5, "direction": "positive", "logic": "轻量高智模型加速本地离线部署与换机周期"},
            {"market": "美股", "sector": "云平台与 AI 软件 (GOOGL/MSFT)", "sector_en": "Cloud & AI Platforms", "pct_low": 1.5, "pct_high": 3.8, "direction": "positive", "logic": "头部模型迭代巩固开发者粘性与云 API 收入"},
            {"market": "美股", "sector": "传统无壁垒工具软件", "sector_en": "Legacy SaaS", "pct_low": -3.0, "pct_high": -1.0, "direction": "negative", "logic": "原生多模态与编程 Agent 挤压单点旧软件生存空间"},
        ],
        "if_then": [
            {"cond": "若 API 调用量/付费转化爆发", "result": "AI 应用与云厂迎来戴维斯双击 +2%~+5%", "tone": "bullish"},
            {"cond": "若价格战吞噬毛利", "result": "纯模型套壳公司承压 -2%~-4%", "tone": "bearish"},
        ],
        "milestones": [
            {"date": "已发生", "status": "done", "label": "新一轮旗舰/端侧模型密集发布并公布定价"},
            {"date": "当前", "status": "current", "label": "开发者实测迁移与企业 API 接入高峰期"},
            {"date": "下季", "status": "upcoming", "label": "核验云厂 AI 收入占比与爆款应用留存"},
        ],
    },
    {
        "rule_id": "oil_energy_geopolitics",
        "pattern": re.compile(r"(?:原油|油价|opec|中东|伊朗|以色列|红海|霍尔木兹|俄乌|停火|天然气|航运|油轮)", re.I),
        "tag": "能源原油 · 地缘风险",
        "tag_en": "Energy & Geopolitics",
        "polarity": "divergent",
        "intensity": 4,
        "one_liner": "地缘冲突或产油国决议直接左右国际油价与海运运价：油价飙升利好油气采掘与油运，但推高通胀并挤压航空/化工利润。",
        "one_liner_en": "Geopolitical shocks reprice crude oil and freight: upstream energy & tankers benefit while airlines and inflation-sensitive growth face margin squeeze.",
        "bars": [
            {"market": "A股", "sector": "石油石化 / 油运 / 煤炭", "sector_en": "Oil & Tankers", "pct_low": 2.0, "pct_high": 5.0, "direction": "positive", "logic": "布伦特油价与 VLCC 运价跳升直接增厚上游盈利"},
            {"market": "A股", "sector": "航空机场 / 基础化工", "sector_en": "Airlines & Chemicals", "pct_low": -3.2, "pct_high": -1.2, "direction": "negative", "logic": "航油与原材料成本上升挤压毛利率"},
            {"market": "美股", "sector": "美国能源板块 (XLE / XOM)", "sector_en": "US Energy (XLE)", "pct_low": 1.8, "pct_high": 4.2, "direction": "positive", "logic": "现金流随油价中枢上移同步扩张"},
            {"market": "大宗", "sector": "布伦特原油 / 黄金避险", "sector_en": "Brent Crude & Gold", "pct_low": 2.0, "pct_high": 6.0, "direction": "positive", "logic": "供给中断溢价与地缘避险共振"},
        ],
        "if_then": [
            {"cond": "若冲突升级/海峡受阻", "result": "油气与黄金急涨 +3%~+6%，航空承压", "tone": "bearish"},
            {"cond": "若达成停火/增产协议", "result": "油价回落 -3%~-6%，航空与成长股反弹", "tone": "bullish"},
        ],
        "milestones": [
            {"date": "已发生", "status": "done", "label": "产油区/航道局势出现突发变量"},
            {"date": "当前", "status": "current", "label": "原油期货计入风险溢价，观察是否实质断供"},
            {"date": "下周", "status": "upcoming", "label": "关注 OPEC+ 产量指引及外交斡旋结果"},
        ],
    },
    {
        "rule_id": "china_macro_policy_ev",
        "pattern": re.compile(r"(?:央行|降准|统计局|gdp|消费|地产|房地产|楼市|新能源车|电动车|特斯拉|tesla|比亚迪|机器人|智驾|自动驾驶|锂电)", re.I),
        "tag": "内需政策 · 新能源智驾",
        "tag_en": "China Policy & EV/Robotics",
        "polarity": "bullish",
        "intensity": 4,
        "one_liner": "国内宏观稳增长政策或新能源/智驾产业突破，直接提振内需消费、汽车智能化供应链及港股顺周期资产估值。",
        "one_liner_en": "Pro-growth policy or EV/robotics breakthroughs lift China domestic demand, smart-auto supply chains, and HK cyclical equities.",
        "bars": [
            {"market": "A股", "sector": "汽车智能化 / 机器人 / 锂电", "sector_en": "Smart EV & Robotics", "pct_low": 1.8, "pct_high": 4.5, "direction": "positive", "logic": "政策补贴或智驾放量带动全产业链订单"},
            {"market": "A股", "sector": "大消费 / 顺周期 / 券商", "sector_en": "Consumer & Brokers", "pct_low": 1.2, "pct_high": 3.5, "direction": "positive", "logic": "流动性宽松与稳增长预期改善风险偏好"},
            {"market": "美股", "sector": "新能源车与智驾 (TSLA / LI)", "sector_en": "EV & Autonomy", "pct_low": 1.5, "pct_high": 4.2, "direction": "positive", "logic": "Robotaxi 与人形机器人进度成为核心定价因子"},
        ],
        "if_then": [
            {"cond": "若配套细则/销量超预期", "result": "智驾机器人与顺周期走强 +2%~+5%", "tone": "bullish"},
            {"cond": "若数据不及预期", "result": "顺周期短线回撤 -1.5%~-3%", "tone": "bearish"},
        ],
        "milestones": [
            {"date": "已发生", "status": "done", "label": "政策吹风或头部车企发布最新销量/技术进展"},
            {"date": "当前", "status": "current", "label": "资金围绕龙头产业链进行业绩与估值切换"},
            {"date": "月底", "status": "upcoming", "label": "追踪月度官方宏观/乘联会高频验证数据"},
        ],
    },
    {
        "rule_id": "crypto_fintech_hk_tech",
        "pattern": re.compile(r"(?:比特币|btc|以太坊|加密|稳定币|港股|恒生|腾讯|阿里|拼多多|财报|回购|营收)", re.I),
        "tag": "科技财报 · 风险资产",
        "tag_en": "Tech Earnings & Risk Assets",
        "polarity": "bullish",
        "intensity": 3,
        "one_liner": "头部互联网与金融科技财报/回购及加密监管动态，直接牵引港股科技指数、中概股与美股高弹性风险资产情绪。",
        "one_liner_en": "Big-tech earnings, buybacks, and fintech/crypto milestones steer Hang Seng Tech and high-beta US risk sentiment.",
        "bars": [
            {"market": "港股", "sector": "恒生科技 / 互联网龙头", "sector_en": "Hang Seng Tech", "pct_low": 1.5, "pct_high": 4.2, "direction": "positive", "logic": "利润率改善与大额回购提供底部估值支撑"},
            {"market": "A股", "sector": "金融科技 / 跨境支付", "sector_en": "Fintech & Payments", "pct_low": 1.2, "pct_high": 3.8, "direction": "positive", "logic": "成交活跃度回升与数字资产合规化催化"},
            {"market": "美股", "sector": "科技与加密概念 (COIN/MSTR)", "sector_en": "US Tech & Crypto", "pct_low": 2.0, "pct_high": 5.5, "direction": "positive", "logic": "高弹性资金跟随风险偏好迅速放大波动"},
        ],
        "if_then": [
            {"cond": "若业绩指引/回购超预期", "result": "恒生科技与相关链条走强 +2%~+4.5%", "tone": "bullish"},
            {"cond": "若增速放缓或监管收紧", "result": "高弹性标的回调 -2%~-5%", "tone": "bearish"},
        ],
        "milestones": [
            {"date": "已发生", "status": "done", "label": "财报披露或监管政策动态落地"},
            {"date": "当前", "status": "current", "label": "机构重估季度盈利预测与资金仓位"},
            {"date": "下周", "status": "upcoming", "label": "观察南向/外资连续净流入持续性"},
        ],
    },
]


def _match_rule(text: str) -> Optional[Dict[str, Any]]:
    for rule in _EVENT_MARKET_RULES:
        if rule["pattern"].search(text):
            return rule
    return None


def _adjust_polarity_by_title(title: str, default_polarity: str) -> str:
    t = title.lower()
    if any(k in t for k in ("暴跌", "跳水", "跌破", "重挫", "加息", "制裁", "禁令", "冲突", "停飞", "宕机", "警告", "下调")):
        return "bearish"
    if any(k in t for k in ("大涨", "新高", "突破", "发布", "降息", "达成", "缓和", "超预期", "首日", "创纪录", "获批")):
        return "bullish"
    return default_polarity


def build_finance_impact_artifact(
    *,
    batch_id: str,
    generated_at_iso: str,
    cat_docs: Dict[str, dict],
) -> Dict[str, Any]:
    """Attach quantified visual market impact predictions directly to every major market-moving event."""
    all_events: List[dict] = []
    for cat in ("finance", "global", "tech", "general"):
        for ev in (cat_docs.get(cat) or {}).get("events") or []:
            all_events.append({**ev, "_cat": cat})

    event_impacts: List[Dict[str, Any]] = []
    event_impact_map: Dict[str, Dict[str, Any]] = {}
    rule_usage_counts: Dict[str, int] = {}

    for ev in all_events:
        eid = str(ev.get("event_id") or "")
        title = str(ev.get("title") or "").strip()
        summary = str(ev.get("fact_summary") or ev.get("summary") or "")
        if not eid or not title:
            continue
        matched_rule = _match_rule(f"{title} {summary}")
        if not matched_rule:
            continue

        rid = matched_rule["rule_id"]
        src0 = (ev.get("sources") or [{}])[0]
        polarity = _adjust_polarity_by_title(title, matched_rule["polarity"])
        bars = [dict(b) for b in matched_rule["bars"]]

        # Compact inline badge data stored in event_impact_map for EVERY matched event card
        top_a = next((b for b in bars if b["market"] in ("A股", "港股")), bars[0])
        top_us = next((b for b in bars if b["market"] in ("美股", "大宗")), bars[-1])
        inline_summary = {
            "event_id": eid,
            "tag": matched_rule["tag"],
            "tag_en": matched_rule["tag_en"],
            "polarity": polarity,
            "intensity": matched_rule["intensity"],
            "one_liner": matched_rule["one_liner"],
            "top_a": top_a,
            "top_us": top_us,
            "bars": bars,
            "if_then": matched_rule["if_then"],
            "milestones": matched_rule["milestones"],
        }
        event_impact_map[eid] = inline_summary

        # Keep dedicated Markets tab crisp & high-signal (up to 3 top events per theme, max 16 total)
        if rule_usage_counts.get(rid, 0) < 3 and len(event_impacts) < 16:
            rule_usage_counts[rid] = rule_usage_counts.get(rid, 0) + 1
            event_impacts.append(
                {
                    "id": f"imp_{eid}",
                    "event_id": eid,
                    "rule_id": rid,
                    "event_title": title,
                    "event_title_en": str(ev.get("title_en") or title),
                    "event_summary": summary[:160],
                    "category": ev.get("_cat", "finance"),
                    "published_at": str(ev.get("first_reported_at") or ev.get("latest_reported_at") or generated_at_iso),
                    "source_name": str(src0.get("source_name") or "镜信情报"),
                    "source_url": str(src0.get("url") or ""),
                    "tag": matched_rule["tag"],
                    "tag_en": matched_rule["tag_en"],
                    "polarity": polarity,
                    "intensity": matched_rule["intensity"],
                    "one_liner": matched_rule["one_liner"],
                    "one_liner_en": matched_rule["one_liner_en"],
                    "bars": bars,
                    "if_then": matched_rule["if_then"],
                    "milestones": matched_rule["milestones"],
                }
            )

    # Sort highest intensity & most recent first
    event_impacts.sort(key=lambda x: (int(x.get("intensity", 3)), str(x.get("published_at", ""))), reverse=True)

    return {
        "schema_version": "5.0",
        "generated_at": generated_at_iso,
        "batch_id": batch_id,
        "disclaimer": "量化区间为基于历史传导规律的事件推演参考，不构成任何具体个股买卖建议。",
        "disclaimer_en": "Impact ranges are event-driven analytical models for reference only, not financial advice.",
        "total_mapped_events": len(event_impact_map),
        "event_impacts": event_impacts,
        "event_impact_map": event_impact_map,
    }
