"""Financial Transmission & Stock Market Impact Radar (data/finance_impact.json).

Translates breaking macro, geopolitical, and tech news into beginner-friendly:
1. Causal transmission chains (News -> Macro Variable -> A-Share & US-Share Sectors);
2. Quantified scenario sensitivity bands (historical/stress-test ranges, honestly framed as analytical frameworks, not guaranteed tips);
3. Chronological event milestone nodes (Happened -> Current Inflection -> Next Catalyst Date);
4. Interactive What-If Macro Simulator presets (Fed rate decision, US-China tariffs, Gold/USD swings, AI Capex).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


_TRANSMISSION_PLAYBOOKS: List[Dict[str, Any]] = [
    {
        "playbook_id": "fin_fed_rate_gold",
        "pattern": re.compile(r"(?:美联储|fomc|加息|降息|沃勒|美元指数|现货黄金|金价|美债)", re.I),
        "title": "美联储鹰派加息预期升温与美元/黄金剧烈波动",
        "title_en": "Hawkish Fed Rate Expectations & USD / Gold Volatility",
        "category_tag": "央行利率与全球流动性",
        "category_tag_en": "Central Bank & Liquidity",
        "beginner_explainer": (
            "利率就是“借钱的成本”。一旦美联储官员释放加息或推迟降息信号，美债收益率和美元会走强——"
            "这会让“不生息的黄金”瞬间失去吸引力（资金流向吃利息的美元），同时让“靠未来画大饼的高估值科技股”折现承压；"
            "反过来，银行和现金流稳健的高股息红利板块往往更抗跌。"
        ),
        "beginner_explainer_en": (
            "Higher Fed rate expectations strengthen the USD and Treasury yields, pressuring non-yielding gold and high-multiple growth stocks "
            "while favoring defensive high-dividend banks and cash-rich value names."
        ),
        "transmission_chain": [
            "美联储纪要偏鹰 / 官员提及加息 50bp 风险",
            "美元指数走强突破 103.8 + 美债收益率上行",
            "无息资产黄金短线失血（跌破 3800 美元关口）",
            "资金从高估值成长股切换至高股息防御板块",
        ],
        "transmission_chain_en": [
            "Hawkish FOMC minutes / 50bp hike debate",
            "USD Index climbs above 103.8 + yields rise",
            "Gold breaks lower below $3,800 on higher opportunity cost",
            "Rotation from high-beta growth into defensive dividend sectors",
        ],
        "a_share_impacts": [
            {"sector": "黄金与有色金属（贵金属）", "sector_en": "A-Share Gold & Nonferrous", "direction": "negative", "range_text": "短期承压 -2% ~ -5%", "range_text_en": "Short-term pressure -2% to -5%", "logic": "美元走强直接压制国际金价与 LME 基本金属定价。"},
            {"sector": "银行 / 电力 / 高股息红利", "sector_en": "A-Share Banks & High Dividend", "direction": "positive", "range_text": "避险抗跌 +1% ~ +2.5%", "range_text_en": "Defensive +1% to +2.5%", "logic": "外围流动性收紧期，低估值高分红资产成资金避风港。"},
            {"sector": "外资重仓蓝筹 / 成长赛道", "sector_en": "Foreign-Owned Blue Chips & Growth", "direction": "negative", "range_text": "估值扰动 -1.5% ~ -3.5%", "range_text_en": "Valuation drag -1.5% to -3.5%", "logic": "中美利差扩大阶段，北向资金短期偏好趋于谨慎。"},
        ],
        "us_share_impacts": [
            {"sector": "纳斯达克高估值科技 (QQQ / ARKK)", "sector_en": "Nasdaq Growth Tech (QQQ)", "direction": "negative", "range_text": "敏感区间 -2% ~ -5%", "range_text_en": "Sensitivity -2% to -5%", "logic": "折现率抬升直接压缩远期盈利型科技股估值倍数。"},
            {"sector": "黄金 ETF / 矿业股 (GLD / GDX)", "sector_en": "Gold & Miners (GLD / GDX)", "direction": "negative", "range_text": "波动区间 -2.5% ~ -6%", "range_text_en": "Swing -2.5% to -6%", "logic": "实际利率上行对黄金形成最直接的逆风。"},
            {"sector": "美国金融与短债现金类 (XLF / SGOV)", "sector_en": "US Financials & T-Bills (XLF)", "direction": "positive", "range_text": "息差受益 +1% ~ +3%", "range_text_en": "Net interest benefit +1% to +3%", "logic": "高利率维持更久有利银行净息差与货币基金收益。"},
        ],
        "scenarios": [
            {
                "label": "鸽派反转（12月按兵不动 + 释放降息预期）",
                "label_en": "Dovish Pivot (Hold + Cut Signal)",
                "probability_hint": "基准情景参考",
                "trigger": "通胀回落或就业降温，FOMC 声明删除进一步紧缩措辞",
                "a_share_outcome": "A股成长科技与黄金有色快速修复 +2% ~ +4.5%，外资回流",
                "us_share_outcome": "纳指 QQQ 反弹 +2% ~ +4%，现货黄金收复 3850–3950 美元区间",
                "severity": "bullish",
            },
            {
                "label": "温和鹰派（12月加息 25bp 或点阵图上移）",
                "label_en": "Mild Hawkish (+25bp or Higher Dots)",
                "probability_hint": "警惕情景",
                "trigger": "FOMC 决议落实加息 25bp，但暗示后续视数据而定",
                "a_share_outcome": "有色黄金与成长承压 -2% ~ -4%，红利与银行相对跑赢",
                "us_share_outcome": "纳指回撤 -2.5% ~ -5%，美元指数测试 105 关口",
                "severity": "bearish",
            },
            {
                "label": "超预期强鹰（释放 50bp 或连续加息信号）",
                "label_en": "Shock Hawkish (50bp Signal)",
                "probability_hint": "尾部冲击",
                "trigger": "油价飙升或通胀反弹迫使美联储强化激进紧缩路径",
                "a_share_outcome": "短期风险偏好明显收缩 -3% ~ -5%，仅高股息与现金避险",
                "us_share_outcome": "高贝塔科技与加密资产面临 -5% ~ -8% 流动性回撤风险",
                "severity": "extreme",
            },
        ],
        "milestones": [
            {"date": "2026-11-18", "status": "done", "label": "美联储公布 10 月会议纪要（偏鹰，美元跳升、黄金破 3800）"},
            {"date": "2026-11-19", "status": "current", "label": "美联储理事沃勒表态引爆市场对 12 月路径分歧"},
            {"date": "2026-12-10", "status": "upcoming", "label": "12 月 FOMC 议息决议 + 最新点阵图落地（核心验证日）"},
        ],
    },
    {
        "playbook_id": "fin_us_china_apec_trade",
        "pattern": re.compile(r"(?:apec|特朗普.*(?:访华|深圳|中国|会晤)|中美元首|自贸协定|关税|中概股)", re.I),
        "title": "特朗普访华与深圳 APEC 经贸外交博弈对中美股市传导",
        "title_en": "Trump China Visit & Shenzhen APEC Trade Impact on A-Shares & US Stocks",
        "category_tag": "地缘外交与关税预期",
        "category_tag_en": "Geopolitics & Tariffs",
        "beginner_explainer": (
            "大国元首面对面会晤直接决定未来 6–12 个月的「关税税率」和「科技出口限制」。"
            "只要双方释放缓和或阶段性经贸协议信号，之前被压低估值的中概股、A股出口链和航运就会迎来“预期差修复”；"
            "相反，如果谈拢有限或科技限制加码，资金会迅速转向 A 股国产替代（半导体设备/信创）。"
        ),
        "beginner_explainer_en": (
            "US-China leader summits directly reprice tariff risk and tech export controls. Any de-escalation sparks relief rallies in Chinese ADRs "
            "and export chains, whereas renewed curbs rotate domestic A-share capital into semiconductor self-sufficiency."
        ),
        "transmission_chain": [
            "中美元首深圳 APEC 会晤及多边经贸谈判（中韩自贸二阶段等）",
            "市场重估未来关税清单与跨境供应链成本",
            "离岸人民币汇率与外资风险偏好同步定价",
            "A股出口链/国产替代与美股中概股 (KWEB) 出现方向性分化",
        ],
        "transmission_chain_en": [
            "US-China APEC summit & regional FTA negotiations",
            "Repricing of tariff schedules and cross-border supply chain costs",
            "Offshore RMB & global risk appetite re-rating",
            "Divergence across A-share exporters, domestic chips, and US China ADRs (KWEB)",
        ],
        "a_share_impacts": [
            {"sector": "出口链 / 消费电子 / 跨境航运", "sector_en": "A-Share Exporters & Shipping", "direction": "mixed", "range_text": "若关税缓和 +3% ~ +6%；若加码 -2% ~ -5%", "range_text_en": "Relief +3% to +6%; Curbs -2% to -5%", "logic": "对美敞口高的家电、消费电子与海运最敏感关税边际变化。"},
            {"sector": "国产半导体设备 / 自主信创", "sector_en": "Domestic Semis & Localization", "direction": "positive", "range_text": "政策催化弹性 +2% ~ +5%", "range_text_en": "Policy catalyst +2% to +5%", "logic": "无论外部管制松紧，算力与核心元器件自主可控仍是长期确定性主线。"},
        ],
        "us_share_impacts": [
            {"sector": "在美中概股 ETF (KWEB / FXI)", "sector_en": "China Internet ADRs (KWEB)", "direction": "mixed", "range_text": "公报催化弹性 ±3% ~ ±6%", "range_text_en": "Communique swing ±3% to ±6%", "logic": "海外机构对中美关系温度计最直接的交易载体。"},
            {"sector": "在华营收占比高美股 (AAPL / TSLA / NVDA)", "sector_en": "China-Exposed US Giants", "direction": "mixed", "range_text": "事件窗口 ±2% ~ ±4%", "range_text_en": "Event window ±2% to ±4%", "logic": "关税豁免或芯片出口细则直接左右亚太区营收指引。"},
        ],
        "scenarios": [
            {
                "label": "超预期缓和（联合声明明确关税豁免/AI 治理对话机制）",
                "label_en": "De-escalation Framework",
                "probability_hint": "乐观催化",
                "trigger": "会后公报出现具体关税谈判时间表或经贸工作组重启",
                "a_share_outcome": "A股出口链、航运、恒生科技同步修复 +3% ~ +6%",
                "us_share_outcome": "KWEB 中概股领涨 +4% ~ +7%，苹果/特斯拉供应链受益",
                "severity": "bullish",
            },
            {
                "label": "原则性沟通（气氛平稳但无实质关税松动）",
                "label_en": "Status Quo Diplomacy",
                "probability_hint": "中性基准",
                "trigger": "双方强调管控分歧，核心关税与芯片管制维持现状",
                "a_share_outcome": "短线冲高回落 -1% ~ +1%，资金回归内需与业绩主线",
                "us_share_outcome": "KWEB 维持区间震荡 ±1.5%，美股重新跟随美联储定价",
                "severity": "neutral",
            },
            {
                "label": "意外摩擦（新增芯片出口审查或关税加码表态）",
                "label_en": "Renewed Friction / Export Curbs",
                "probability_hint": "风险对冲",
                "trigger": "美方收紧 AI 芯片/算力出口条款或追加关税威胁",
                "a_share_outcome": "出口链承压 -2% ~ -5%，但国产半导体/军工/自主可控逆势走强 +2% ~ +5%",
                "us_share_outcome": "半导体设备与中概股短线承压 -3% ~ -6%",
                "severity": "bearish",
            },
        ],
        "milestones": [
            {"date": "2026-11-18", "status": "done", "label": "特朗普抵达深圳，APEC 欢迎宴会及多国双边谈判启动"},
            {"date": "2026-11-19", "status": "current", "label": "中美元首会晤、中韩自贸二阶段谈判完成、三边高层接触"},
            {"date": "2026-11-23", "status": "upcoming", "label": "观察中美官方是否落地具体经贸/关税/AI 书面后续成果"},
        ],
    },
    {
        "playbook_id": "fin_ai_ipo_nvidia",
        "pattern": re.compile(r"(?:anthropic|ipo|英伟达|nvidia|nvda|算力|混元|光模块|amd)", re.I),
        "title": "Anthropic 千亿级超级 IPO 与英伟达换帅/算力链重估",
        "title_en": "Anthropic Record IPO & NVIDIA Governance Transition Re-rating",
        "category_tag": "AI 资本开支与算力链",
        "category_tag_en": "AI Capex & Compute Chain",
        "beginner_explainer": (
            "Anthropic 创纪录 IPO（募资超 800–1000 亿美元）意味着全球资本市场给“大模型公司”定下了全新估值锚——"
            "融资来的钱最终会大举买算力卡、光模块、服务器和数据中心电力；"
            "同时英伟达虽然业绩亮眼但面临管理层交接与出口审查，会导致资金在「英伟达单核」与「AMD/自研芯片/国产算力」之间重新切分。"
        ),
        "beginner_explainer_en": (
            "Anthropic's historic IPO sets a fresh valuation anchor for frontier AI labs and injects massive capital into compute, optics, and data centers, "
            "while NVIDIA's leadership transition sparks rotation across AMD, custom ASICs, and domestic compute peers."
        ),
        "transmission_chain": [
            "Anthropic IPO 发行价 $83 超预期、灰市活跃 + 腾讯/微软加码云与芯片",
            "一级/二级市场抬升 AI 大模型与云算力基础设施估值锚",
            "资金关注上游光模块、服务器散热液冷、电力及 AMD 等替代方案",
            "英伟达管理层过渡期带来短线波动，分流部分资金至二线算力标的",
        ],
        "transmission_chain_en": [
            "Anthropic prices IPO at $83 above range + hyperscalers expand AI cloud",
            "Market re-rates AI model labs and cloud compute infrastructure",
            "Capital flows to optical transceivers, liquid cooling, power & AMD alternatives",
            "NVIDIA leadership transition triggers short-term volatility and peer rotation",
        ],
        "a_share_impacts": [
            {"sector": "CPO 光模块 / 液冷服务器 / PCB 算力链", "sector_en": "A-Share Optical & AI Servers", "direction": "positive", "range_text": "情绪催化 +2% ~ +5%", "range_text_en": "Sentiment boost +2% to +5%", "logic": "海外头部大模型巨额募资直接强化 2027 年全球算力基建资本开支预期。"},
            {"sector": "AI 应用 / 大模型云服务（腾讯/阿里链）", "sector_en": "China AI Cloud & Apps", "direction": "positive", "range_text": "估值映射 +1.5% ~ +4%", "range_text_en": "Valuation comp +1.5% to +4%", "logic": "Anthropic 高估值上市打开国内头部云厂与大模型生态的估值想象空间。"},
        ],
        "us_share_impacts": [
            {"sector": "AI 芯片竞争格局 (NVDA / AMD / INTC)", "sector_en": "US AI Semis (NVDA / AMD)", "direction": "mixed", "range_text": "龙头震荡 ±3% ~ ±5%；AMD/封装链获关注", "range_text_en": "Leader ±3% to ±5%; challengers bid", "logic": "英伟达业绩超预期但受高层交接压制，AMD MI450X 与英特尔封装合作获增量关注。"},
            {"sector": "云巨头与数据中心电力 (AMZN / GOOGL / VST)", "sector_en": "Hyperscalers & AI Power", "direction": "positive", "range_text": "中线受益 +1.5% ~ +3.5%", "range_text_en": "Medium-term tailwind +1.5% to +3.5%", "logic": "Anthropic 股东云厂商（亚马逊/谷歌）账面投资浮盈叠加云算力消耗锁定。"},
        ],
        "scenarios": [
            {
                "label": "上市首日大涨 >20%（验证 AI 超级周期热情）",
                "label_en": "IPO Pops >20% on Debut",
                "probability_hint": "灰市指向情景",
                "trigger": "Anthropic 挂牌首日站稳 $100 以上，成交活跃不破发",
                "a_share_outcome": "A股光模块、算力租赁与 AI 应用板块共振走强 +2.5% ~ +5%",
                "us_share_outcome": "美股 AI 软件与算力基建股普涨 +2% ~ +4.5%",
                "severity": "bullish",
            },
            {
                "label": "高开低走 / 虹吸效应抽血旧科技",
                "label_en": "IPO Liquidity Drain / Sell-the-News",
                "probability_hint": "警惕情景",
                "trigger": "千亿级新股抽走二级市场存量科技资金，获利盘兑现",
                "a_share_outcome": "高位算力股短期获利回吐 -2% ~ -4%，资金切往低位应用",
                "us_share_outcome": "传统 SaaS 与高估值 AI 概念短线回调 -2% ~ -4%",
                "severity": "bearish",
            },
        ],
        "milestones": [
            {"date": "2026-11-12", "status": "done", "label": "英伟达 SEC 8-K 披露管理层过渡与激励安排"},
            {"date": "2026-11-19", "status": "current", "label": "Anthropic 定价每股 $83 募资创纪录，灰市预期高开"},
            {"date": "2026-12-03", "status": "upcoming", "label": "跟踪英伟达 SEC 继任进展与 Anthropic 上市后首个交易月表现"},
        ],
    },
]

_MACRO_SIMULATOR_PRESETS: List[Dict[str, Any]] = [
    {
        "id": "sim_fed_hike_25",
        "driver": "美联储利率",
        "driver_en": "Fed Rate",
        "label": "意外加息 +25bp",
        "label_en": "Surprise Hike +25bp",
        "summary": "美元与美债收益率跳升，全球成长股估值折现承压，黄金短线失血，银行/高股息占优。",
        "summary_en": "USD & yields jump; growth multiples compress and gold drops while banks/dividends outperform.",
        "impacts": [
            {"market": "美股", "name": "纳指科技 (QQQ)", "pct_low": -4.5, "pct_high": -2.0},
            {"market": "大宗", "name": "现货黄金 (GLD)", "pct_low": -4.0, "pct_high": -2.0},
            {"market": "A股", "name": "有色与高弹性成长", "pct_low": -3.5, "pct_high": -1.5},
            {"market": "A股", "name": "银行/高股息红利", "pct_low": 0.5, "pct_high": 2.0},
        ],
    },
    {
        "id": "sim_fed_cut_25",
        "driver": "美联储利率",
        "driver_en": "Fed Rate",
        "label": "释放降息 -25bp",
        "label_en": "Rate Cut -25bp",
        "summary": "全球无风险利率回落，美元走弱，黄金和纳指成长股同步获得估值修复，外资回流新兴市场。",
        "summary_en": "Risk-free yields ease and USD softens, lifting gold, Nasdaq growth, and EM/China inflows.",
        "impacts": [
            {"market": "美股", "name": "纳指科技 (QQQ)", "pct_low": 2.0, "pct_high": 4.5},
            {"market": "大宗", "name": "现货黄金 (GLD)", "pct_low": 2.0, "pct_high": 4.0},
            {"market": "A股", "name": "成长科技与创新药", "pct_low": 1.8, "pct_high": 4.0},
            {"market": "中概", "name": "恒生科技 / KWEB", "pct_low": 2.5, "pct_high": 5.0},
        ],
    },
    {
        "id": "sim_tariff_ease",
        "driver": "中美经贸关税",
        "driver_en": "US-China Tariffs",
        "label": "达成关税缓和框架",
        "label_en": "Tariff Relief Deal",
        "summary": "压制估值的最大外生不确定性消退，人民币汇率走强，出口链、航运与中概互联网迎来戴维斯双击。",
        "summary_en": "External overhang lifts; RMB firms up, sparking strong rallies in exporters, shipping, and China ADRs.",
        "impacts": [
            {"market": "中概", "name": "中概互联 (KWEB)", "pct_low": 4.0, "pct_high": 7.5},
            {"market": "A股", "name": "出口链 / 家电 / 航运", "pct_low": 3.0, "pct_high": 6.0},
            {"market": "美股", "name": "消费电子巨头 (AAPL)", "pct_low": 1.5, "pct_high": 3.5},
            {"market": "A股", "name": "防御避险板块", "pct_low": -1.5, "pct_high": 0.0},
        ],
    },
    {
        "id": "sim_tariff_escalate",
        "driver": "中美经贸关税",
        "driver_en": "US-China Tariffs",
        "label": "关税/芯片限制加码",
        "label_en": "New Tariffs / Chip Curbs",
        "summary": "外需与海外算力链短期承压，但会强烈催化 A 股自主可控（国产半导体设备、信创软件）与内需避险。",
        "summary_en": "Exporters & global semis face headwinds while domestic A-share chip localization rallies on policy urgency.",
        "impacts": [
            {"market": "A股", "name": "国产半导体 / 信创", "pct_low": 2.0, "pct_high": 5.5},
            {"market": "A股", "name": "对美出口链 / 消费电子", "pct_low": -5.0, "pct_high": -2.0},
            {"market": "中概", "name": "中概互联 (KWEB)", "pct_low": -6.0, "pct_high": -2.5},
            {"market": "美股", "name": "半导体设备板块", "pct_low": -4.0, "pct_high": -1.5},
        ],
    },
]


def build_finance_impact_artifact(
    *,
    batch_id: str,
    generated_at_iso: str,
    cat_docs: Dict[str, dict],
) -> Dict[str, Any]:
    """Build data/finance_impact.json linking live current-batch news to A-share/US-share transmission cards."""
    all_events: List[dict] = []
    for cat in ("finance", "global", "tech", "general"):
        all_events.extend((cat_docs.get(cat) or {}).get("events") or [])

    cards: List[Dict[str, Any]] = []
    for pb in _TRANSMISSION_PLAYBOOKS:
        pat = pb["pattern"]
        matched: List[Dict[str, Any]] = []
        for ev in all_events:
            blob = f"{ev.get('title', '')} {ev.get('fact_summary', '')}"
            if pat.search(blob):
                src0 = (ev.get("sources") or [{}])[0]
                matched.append(
                    {
                        "event_id": ev.get("event_id"),
                        "title": ev.get("title"),
                        "category": ev.get("category"),
                        "source_name": src0.get("source_name") or "本批简报",
                        "url": src0.get("url"),
                    }
                )
        card = {k: v for k, v in pb.items() if k != "pattern"}
        card["matched_events"] = matched[:5]
        card["matched_count"] = len(matched)
        card["heat_level"] = "高热共振" if len(matched) >= 3 else ("持续发酵" if len(matched) >= 1 else "常规跟踪")
        cards.append(card)

    cards.sort(key=lambda c: c["matched_count"], reverse=True)
    return {
        "schema_version": "4.0",
        "generated_at": generated_at_iso,
        "batch_id": batch_id,
        "disclaimer_zh": (
            "透明声明：以下板块传导逻辑与涨跌幅敏感区间基于历史同类宏观事件波动规律与产业链敞口测算，"
            "旨在帮助投资者建立“看懂新闻背后逻辑”的情景推演框架，不构成具体个股买卖建议，投资需结合自身风险承受能力独立判断。"
        ),
        "disclaimer_en": (
            "Transparency notice: Sector transmission chains and sensitivity bands are calibrated from historical macro volatility "
            "to help readers build structured scenario frameworks — not financial advice or guaranteed return forecasts."
        ),
        "cards": cards,
        "simulator_presets": _MACRO_SIMULATOR_PRESETS,
    }
