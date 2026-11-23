"""Curated Global Politics, Expos, Tech Giants & Macro Catalyst Calendar Engine."""

from __future__ import annotations

from datetime import datetime, timedelta
import re
from typing import Any, Dict, List, Optional, Tuple

from pipeline.time_utils import parse_iso_datetime

CALENDAR_EVENT_TYPE_LABELS: Dict[str, str] = {
    "politics_macro": "国家大会与政经",
    "expo_summit": "大型展会与峰会",
    "tech_launch": "企业发布会",
    "central_bank": "央行与宏观",
    "earnings_capital": "财报与资本",
}

CALENDAR_REGION_LABELS: Dict[str, str] = {
    "china": "中国",
    "us": "美国",
    "europe_apac": "欧洲/亚太",
    "global": "全球",
}


def _loc(country: str, city: str) -> str:
    if not city or city == country:
        return country
    return f"{country}·{city}"


def _static_global_schedule() -> List[Dict[str, Any]]:
    """Verified 2026 late-Q4 & 2027 full-year global political, expo, tech & macro catalyst catalog."""
    return [
        # === 1. 国家大会与政经日程 (politics_macro) ===
        {
            "calendar_id": "cal_pol_cn_nbs_pmi_2026_11",
            "title": "中国国家统计局 11 月官方制造业与非制造业 PMI 数据发布",
            "title_en": "China NBS November Official Manufacturing & Non-Manufacturing PMI",
            "scheduled_at": "2026-11-30T09:30:00+08:00",
            "original_time_note": "2026-11-30 09:30 北京时间 (国家统计局例行月度日程)",
            "event_type": "politics_macro",
            "region": "china",
            "country": "中国",
            "city": "北京",
            "certainty": "confirmed_official",
            "certainty_label": "官方例行日程",
            "category": "finance",
            "entity_ids": ["ent_china_macro", "ent_pboc"],
            "watch_variable": "制造业 PMI 荣枯线 (50.0) 与新出口订单、工业品价格分项环比变化",
            "pre_expectation": "重点观察稳增长政策对制造业产需景气度的连续验证",
            "source_name": "国家统计局日程表",
            "source_url": "https://www.stats.gov.cn/",
        },
        {
            "calendar_id": "cal_pol_cn_nbs_cpi_2026_12",
            "title": "中国 11 月 CPI 与 PPI 物价指数官方公布",
            "title_en": "China NBS November CPI & PPI Inflation Release",
            "scheduled_at": "2026-12-09T09:30:00+08:00",
            "original_time_note": "2026-12-09 09:30 北京时间 (国家统计局月度通胀公报)",
            "event_type": "politics_macro",
            "region": "china",
            "country": "中国",
            "city": "北京",
            "certainty": "confirmed_official",
            "certainty_label": "官方例行日程",
            "category": "finance",
            "entity_ids": ["ent_china_macro", "ent_pboc"],
            "watch_variable": "核心 CPI 同比涨幅及 PPI 工业出厂价格环比收窄斜率",
            "pre_expectation": "国内需求修复强度与上游能源成本传导检验",
            "source_name": "国家统计局",
            "source_url": "https://www.stats.gov.cn/",
        },
        {
            "calendar_id": "cal_pol_cn_cewc_2026_12",
            "title": "中央经济工作会议预期召开窗口（定调 2027 财政赤字与扩大内需主线）",
            "title_en": "China Central Economic Work Conference Policy Window (2027 Stance)",
            "scheduled_at": "2026-12-11T18:00:00+08:00",
            "original_time_note": "12 月中旬历年政策窗口（具体日期以新华社通稿为准）",
            "event_type": "politics_macro",
            "region": "china",
            "country": "中国",
            "city": "北京",
            "certainty": "reported_tbd",
            "certainty_label": "年度政策窗口（日期以通稿为准）",
            "is_clock_tbd": True,
            "category": "global",
            "entity_ids": ["ent_china_macro", "ent_pboc"],
            "watch_variable": "广义财政赤字目标表述、两重两新接续力度及新质生产力产业指引",
            "pre_expectation": "定调 2027 年宏观逆周期力度，直接影响港股/A 股跨年主线",
            "source_name": "中国宏观年度政经窗口",
            "source_url": "https://www.gov.cn/",
        },
        {
            "calendar_id": "cal_pol_cn_lpr_2026_12",
            "title": "中国央行 12 月贷款市场报价利率 (LPR) 报价公布",
            "title_en": "PBOC December Loan Prime Rate (1Y & 5Y LPR) Fixing",
            "scheduled_at": "2026-12-21T09:00:00+08:00",
            "original_time_note": "2026-12-21 09:00 北京时间（每月 20 日遇周末顺延至周一）",
            "event_type": "politics_macro",
            "region": "china",
            "country": "中国",
            "city": "北京",
            "certainty": "confirmed_official",
            "certainty_label": "央行例行报价日",
            "category": "finance",
            "entity_ids": ["ent_pboc", "ent_china_macro"],
            "watch_variable": "1 年期及 5 年期以上 LPR 基点变动与商业银行净息差导向",
            "pre_expectation": "房地产按揭利率锚定与实体企业融资成本窗口",
            "source_name": "全国银行间同业拆借中心 / 央行",
            "source_url": "https://www.pbc.gov.cn/",
        },
        {
            "calendar_id": "cal_pol_cn_gdp_2027_01",
            "title": "中国国家统计局 2026 年全年 GDP 与国民经济运行新闻发布会",
            "title_en": "China Full-Year 2026 GDP & Economic Performance Briefing (NBS)",
            "scheduled_at": "2027-01-19T10:00:00+08:00",
            "original_time_note": "2027-01-19 10:00 北京时间（国新办年度经济数据发布窗口）",
            "event_type": "politics_macro",
            "region": "china",
            "country": "中国",
            "city": "北京",
            "certainty": "confirmed_official",
            "certainty_label": "官方年度关键发布日",
            "category": "finance",
            "entity_ids": ["ent_china_macro", "ent_pboc"],
            "watch_variable": "2026 年全年实际 GDP 增速、社会消费品零售及高技术制造业投资增速",
            "pre_expectation": "检验全年 5% 左右增长目标达成质量与年末经济动能",
            "source_name": "国务院新闻办公室 / 国家统计局",
            "source_url": "https://www.stats.gov.cn/",
        },
        {
            "calendar_id": "cal_pol_cn_lpr_2027_01",
            "title": "中国央行 1 月贷款市场报价利率 (LPR) 报价公布",
            "title_en": "PBOC January Loan Prime Rate (1Y & 5Y LPR) Fixing",
            "scheduled_at": "2027-01-20T09:00:00+08:00",
            "original_time_note": "2027-01-20 09:00 北京时间（全国银行间同业拆借中心例行发布）",
            "event_type": "politics_macro",
            "region": "china",
            "country": "中国",
            "city": "北京",
            "certainty": "confirmed_official",
            "certainty_label": "央行例行报价日",
            "category": "finance",
            "entity_ids": ["ent_pboc", "ent_china_macro"],
            "watch_variable": "年初信贷开门红窗口 1Y / 5Y LPR 利率水平调整与否",
            "pre_expectation": "观察开年货币宽松节奏",
            "source_name": "中国人民银行",
            "source_url": "https://www.pbc.gov.cn/",
        },
        {
            "calendar_id": "cal_pol_cn_cppcc_14_5",
            "title": "中国人民政治协商会议第十四届全国委员会第五次会议开幕（全国政协十四届五次会议）",
            "title_en": "5th Session of the 14th CPPCC National Committee Opening (Two Sessions)",
            "scheduled_at": "2027-03-04T15:00:00+08:00",
            "original_time_note": "2027-03-04 15:00 北京人民大会堂（全国两会例行会期）",
            "event_type": "politics_macro",
            "region": "china",
            "country": "中国",
            "city": "北京",
            "certainty": "confirmed_official",
            "certainty_label": "国家重大会议法定会期",
            "category": "global",
            "entity_ids": ["ent_china_macro"],
            "watch_variable": "政协常委会工作报告及人工智能、民营经济、科技自立自强重点提案方向",
            "pre_expectation": "全国两会正式启幕信号，开启年度政策与产业议案密集释放期",
            "source_name": "全国政协官网",
            "source_url": "https://www.cppcc.gov.cn/",
        },
        {
            "calendar_id": "cal_pol_cn_npc_14_5",
            "title": "第十四届全国人民代表大会第五次会议开幕（政府工作报告与年度预算公布）",
            "title_en": "5th Session of the 14th National People's Congress (NPC Two Sessions)",
            "scheduled_at": "2027-03-05T09:00:00+08:00",
            "original_time_note": "2027-03-05 09:00 北京人民大会堂（法定每年 3 月初开幕）",
            "event_type": "politics_macro",
            "region": "china",
            "country": "中国",
            "city": "北京",
            "certainty": "confirmed_official",
            "certainty_label": "国家重大会议法定会期",
            "category": "global",
            "entity_ids": ["ent_china_macro", "ent_pboc"],
            "watch_variable": "2027 年 GDP 增速目标、财政赤字率与超长期特别国债发行额度",
            "pre_expectation": "全年中国宏观政策、军费、科技投入与内需刺激核心量化锚",
            "source_name": "中国人大网",
            "source_url": "http://www.npc.gov.cn/",
        },

        # === 2. 国家级与全球大型展会 / 国际峰会 (expo_summit) ===
        {
            "calendar_id": "cal_expo_cop31_overtime_2026_11",
            "title": "联合国 COP31 气候大会安塔利亚加时磋商与终稿表决窗口",
            "title_en": "UN COP31 Antalya Climate Summit Overtime Text Negotiations",
            "scheduled_at": "2026-11-23T22:00:00+08:00",
            "original_time_note": "2026-11-23 土耳其安塔利亚加时全会最终表决窗口",
            "event_type": "expo_summit",
            "region": "global",
            "country": "土耳其",
            "city": "安塔利亚",
            "certainty": "reported_tbd",
            "certainty_label": "加时谈判关键窗口",
            "is_clock_tbd": True,
            "category": "global",
            "entity_ids": ["ent_geopolitics_energy"],
            "watch_variable": "最终案文是否保留「摆脱化石燃料路线图」及气候融资出资承诺规模",
            "pre_expectation": "决定全球碳市场与油气/新能源中期政策风向",
            "source_name": "UNFCCC COP31",
            "source_url": "https://unfccc.int/",
        },
        {
            "calendar_id": "cal_expo_ces_2027",
            "title": "CES 2027 国际消费电子展（AI 硬件、端侧算力与自动驾驶集中亮相）",
            "title_en": "CES 2027 Consumer Electronics Show (Las Vegas)",
            "scheduled_at": "2027-01-05T09:00:00+08:00",
            "original_time_note": "2027-01-05 ~ 01-08 美国拉斯维加斯",
            "event_type": "expo_summit",
            "region": "us",
            "country": "美国",
            "city": "拉斯维加斯",
            "certainty": "confirmed_official",
            "certainty_label": "官网已定排期",
            "category": "tech",
            "entity_ids": ["ent_nvidia", "ent_ai_infra_tools"],
            "watch_variable": "消费级端侧 AI PC、智能眼镜、Robotaxi 座舱方案及下一代 GPU 发布节奏",
            "pre_expectation": "开年全球硬件与具身智能供应链风向标",
            "source_name": "CTA / CES 官网",
            "source_url": "https://www.ces.tech/",
        },
        {
            "calendar_id": "cal_expo_davos_wef_2027",
            "title": "世界经济论坛 2027 年会（达沃斯论坛 Davos WEF Annual Meeting）",
            "title_en": "World Economic Forum Annual Meeting 2027 (Davos)",
            "scheduled_at": "2027-01-18T15:00:00+08:00",
            "original_time_note": "2027-01-18 ~ 01-22 瑞士达沃斯",
            "event_type": "expo_summit",
            "region": "global",
            "country": "瑞士",
            "city": "达沃斯",
            "certainty": "confirmed_official",
            "certainty_label": "官方已定日程",
            "category": "global",
            "entity_ids": ["ent_us_china_diplomacy"],
            "watch_variable": "各国元首、央行行长与科技领袖关于贸易关税、地缘风险及 AI 监管表态",
            "pre_expectation": "开年跨国资本与全球治理主基调定调窗口",
            "source_name": "World Economic Forum",
            "source_url": "https://www.weforum.org/",
        },
        {
            "calendar_id": "cal_expo_mwc_barcelona_2027",
            "title": "MWC 2027 世界移动通信大会（6G 演进、卫星直连与 AI 手机）",
            "title_en": "MWC Barcelona 2027 Mobile World Congress",
            "scheduled_at": "2027-03-01T16:00:00+08:00",
            "original_time_note": "2027-03-01 ~ 03-04 西班牙巴塞罗那 Fira Gran Via",
            "event_type": "expo_summit",
            "region": "europe_apac",
            "country": "西班牙",
            "city": "巴塞罗那",
            "certainty": "confirmed_official",
            "certainty_label": "GSMA 官网排期",
            "category": "tech",
            "entity_ids": ["ent_huawei", "ent_xiaomi"],
            "watch_variable": "电信运营商 AI 基础设施、端侧智能体手机形态与星地一体通信标准",
            "pre_expectation": "全球通信与智能终端产业链春季核心展示窗口",
            "source_name": "GSMA MWC",
            "source_url": "https://www.mwcbarcelona.com/",
        },
        {
            "calendar_id": "cal_expo_cicpe_hainan_2027",
            "title": "第七届中国国际消费品博览会（消博会 · 海南国际消费中心大展）",
            "title_en": "7th China International Consumer Products Expo (Hainan Expo)",
            "scheduled_at": "2027-04-13T09:00:00+08:00",
            "original_time_note": "2027-04-13 ~ 04-18 中国海南海口（国际会议展览中心）",
            "event_type": "expo_summit",
            "region": "china",
            "country": "中国",
            "city": "海口",
            "certainty": "confirmed_official",
            "certainty_label": "商务部主办国家级展会",
            "category": "finance",
            "entity_ids": ["ent_china_macro"],
            "watch_variable": "首发首秀消费新品规模、海南离岛免税与扩大内需促消费签约数据",
            "pre_expectation": "国家级消费精品展，直接映射可选消费与跨境零售需求",
            "source_name": "消博会官网 / 商务部",
            "source_url": "https://www.hainanexpo.org.cn/",
        },
        {
            "calendar_id": "cal_expo_canton_fair_140_review",
            "title": "第 140 届中国进出口商品交易会（广交会秋交会成果结算与机电新能源订单追踪）",
            "title_en": "140th Canton Fair Autumn Session Outcomes & Export Order Settlement",
            "scheduled_at": "2026-11-28T10:00:00+08:00",
            "original_time_note": "2026 年 11 月下旬 中国广州 · 外贸成交复盘与跨境备货窗口",
            "event_type": "expo_summit",
            "region": "china",
            "country": "中国",
            "city": "广州",
            "certainty": "confirmed_official",
            "certainty_label": "广交会外贸追踪窗口",
            "category": "finance",
            "entity_ids": ["ent_china_macro", "ent_tariffs_trade"],
            "watch_variable": "机电/新能源/储能外贸意向成交兑现率及广交会线上平台续单转化",
            "pre_expectation": "中国外贸风向标秋交会收官后的实单排产与汇率结算验证",
            "source_name": "中国对外贸易中心 / 广交会",
            "source_url": "https://www.cantonfair.org.cn/",
        },
        {
            "calendar_id": "cal_expo_gz_autoshow_2026",
            "title": "第二十四届广州国际汽车展览会（智能驾驶、800V 高压架构与整车年末交付冲刺）",
            "title_en": "24th Guangzhou International Automobile Exhibition (Auto Guangzhou 2026)",
            "scheduled_at": "2026-11-26T09:30:00+08:00",
            "original_time_note": "2026-11-20 ~ 11-29 中国广州广交会展馆",
            "event_type": "expo_summit",
            "region": "china",
            "country": "中国",
            "city": "广州",
            "certainty": "confirmed_official",
            "certainty_label": "官方车展排期",
            "category": "tech",
            "entity_ids": ["ent_china_macro", "ent_huawei"],
            "watch_variable": "车端 VLA 端到端智驾上车进展、固态电池装车时间表与年末促销政策",
            "pre_expectation": "年末国内新能源智能化整车与供应链定价权核心大展",
            "source_name": "广州国际车展组委会",
            "source_url": "https://www.autoshows.cn/",
        },
        {
            "calendar_id": "cal_expo_canton_fair_141_2027",
            "title": "第 141 届中国进出口商品交易会（广交会春季展 · 中国外贸第一展）",
            "title_en": "141st Canton Fair Spring Session (China Import & Export Fair)",
            "scheduled_at": "2027-04-15T09:00:00+08:00",
            "original_time_note": "2027-04-15 ~ 05-05 分三期在中国广州琶洲展馆举行",
            "event_type": "expo_summit",
            "region": "china",
            "country": "中国",
            "city": "广州",
            "certainty": "confirmed_official",
            "certainty_label": "官方固定展期",
            "category": "finance",
            "entity_ids": ["ent_china_macro", "ent_tariffs_trade"],
            "watch_variable": "境外采购商到会人数、新兴市场及欧美出口意向成交额（机电/新能源/智能制造）",
            "pre_expectation": "全球关税变化背景下检验中国制造业出口订单韧性的核心晴雨表",
            "source_name": "中国对外贸易中心 / 广交会",
            "source_url": "https://www.cantonfair.org.cn/",
        },
        {
            "calendar_id": "cal_expo_sz_icif_2027",
            "title": "第二十三届中国（深圳）国际文化产业博览交易会（深圳文博会）",
            "title_en": "23rd China (Shenzhen) International Cultural Industries Fair (ICIF)",
            "scheduled_at": "2027-05-22T09:00:00+08:00",
            "original_time_note": "2027 年 5 月下旬 中国深圳国际会展中心（历年 5 月例行窗口）",
            "event_type": "expo_summit",
            "region": "china",
            "country": "中国",
            "city": "深圳",
            "certainty": "reported_tbd",
            "certainty_label": "年度例行展期窗口",
            "is_clock_tbd": True,
            "category": "general",
            "entity_ids": ["ent_tencent"],
            "watch_variable": "AI 内容生成 (AIGC)、数字影视游戏版权交易额及文旅融合签约项目",
            "pre_expectation": "中国文化数字创意产业年度风向标",
            "source_name": "深圳文博会官网",
            "source_url": "https://www.cnicif.com/",
        },
        {
            "calendar_id": "cal_expo_mwc_shanghai_2027",
            "title": "MWC 上海 2027 世界移动通信大会（5G-A、算网融合与工业 AI）",
            "title_en": "MWC Shanghai 2027 (5G-A & AI Networks)",
            "scheduled_at": "2027-06-23T09:00:00+08:00",
            "original_time_note": "2027-06-23 ~ 06-25 中国上海新国际博览中心",
            "event_type": "expo_summit",
            "region": "china",
            "country": "中国",
            "city": "上海",
            "certainty": "confirmed_official",
            "certainty_label": "GSMA 亚太排期",
            "category": "tech",
            "entity_ids": ["ent_huawei"],
            "watch_variable": "三大运营商 5G-A / 算力网络资本开支计划及 AI 终端发布",
            "pre_expectation": "亚太通信设备与算网融合基础设施核心展",
            "source_name": "GSMA MWC Shanghai",
            "source_url": "https://www.mwcshanghai.com/",
        },
        {
            "calendar_id": "cal_expo_waic_2027",
            "title": "WAIC 2027 世界人工智能大会暨人工智能全球治理高级别会议",
            "title_en": "WAIC 2027 World Artificial Intelligence Conference (Shanghai)",
            "scheduled_at": "2027-07-02T09:00:00+08:00",
            "original_time_note": "2027 年 7 月上旬 中国上海世博中心/世博展览馆",
            "event_type": "expo_summit",
            "region": "china",
            "country": "中国",
            "city": "上海",
            "certainty": "reported_tbd",
            "certainty_label": "年度例行大会窗口",
            "is_clock_tbd": True,
            "category": "tech",
            "entity_ids": ["ent_alibaba", "ent_tencent", "ent_ai_infra_tools"],
            "watch_variable": "国产通用大模型新一代架构、人形机器人量产机型及 AI 芯片产业突破",
            "pre_expectation": "中国最高规格 AI 产学研与全球治理大展",
            "source_name": "世界人工智能大会官网",
            "source_url": "https://www.worldaic.com.cn/",
        },
        {
            "calendar_id": "cal_expo_ciie_10_2027",
            "title": "第十届中国国际进口博览会（进博会 CIIE · 国家展与全球高精尖采购）",
            "title_en": "10th China International Import Expo (CIIE Shanghai)",
            "scheduled_at": "2027-11-05T09:00:00+08:00",
            "original_time_note": "2027-11-05 ~ 11-10 中国上海国家会展中心（历年固定 11 月 5 日开幕）",
            "event_type": "expo_summit",
            "region": "china",
            "country": "中国",
            "city": "上海",
            "certainty": "confirmed_official",
            "certainty_label": "国家级年度固定大展",
            "category": "global",
            "entity_ids": ["ent_china_macro", "ent_tariffs_trade"],
            "watch_variable": "年度意向采购成交额、外资跨国巨头在华研发中心落地及高水平对外开放举措",
            "pre_expectation": "全球跨国企业深耕中国市场与高技术装备进口核心平台",
            "source_name": "中国国际进口博览局",
            "source_url": "https://www.ciie.org/",
        },
        {
            "calendar_id": "cal_expo_chtf_sz_2027",
            "title": "第二十九届中国国际高新技术成果交易会（深圳高交会 CHTF）",
            "title_en": "29th China Hi-Tech Fair (Shenzhen CHTF)",
            "scheduled_at": "2027-11-14T09:00:00+08:00",
            "original_time_note": "2027-11-14 ~ 11-16 中国深圳国际会展中心（宝安）",
            "event_type": "expo_summit",
            "region": "china",
            "country": "中国",
            "city": "深圳",
            "certainty": "confirmed_official",
            "certainty_label": "中国科技第一展年度档期",
            "category": "tech",
            "entity_ids": ["ent_huawei", "ent_byd"],
            "watch_variable": "深圳本土算力、人形机器人、低空经济 eVTOL 与新能源硬科技成果转化规模",
            "pre_expectation": "粤港澳大湾区与全国高新技术成果交易风向标",
            "source_name": "高交会官网",
            "source_url": "https://www.chtf.com/",
        },
        {
            "calendar_id": "cal_expo_zhuhai_airshow_2026_next",
            "title": "中国国际航空航天博览会（珠海航展 · 商业航天与航空国防产业节点）",
            "title_en": "Airshow China (Zhuhai Aviation & Aerospace Expo Window)",
            "scheduled_at": "2028-11-10T09:00:00+08:00",
            "original_time_note": "两年一届单届档期 · 中国广东珠海国际航展中心（下一届将于 2028 年 11 月举行）",
            "event_type": "expo_summit",
            "region": "china",
            "country": "中国",
            "city": "珠海",
            "certainty": "reported_tbd",
            "certainty_label": "双年展既定档期",
            "is_clock_tbd": True,
            "category": "tech",
            "entity_ids": ["ent_china_macro"],
            "watch_variable": "重型运载火箭、隐身战机、无人机集群与民用航空发动机商业订单签约",
            "pre_expectation": "中国商业航天与高端航空装备核心展示平台（双数年 11 月举办）",
            "source_name": "中国航展官网",
            "source_url": "https://www.airshow.com.cn/",
        },

        # === 3. 科技巨头与车企重磅发布会 / 开发者大会 (tech_launch) ===
        {
            "calendar_id": "cal_tech_shenzhou_24_launch",
            "title": "神舟二十四号载人飞船（总装测试与酒泉卫星发射窗口）",
            "title_en": "Shenzhou-24 Crewed Spacecraft Final Rehearsal & Launch Window (Jiuquan)",
            "scheduled_at": "2026-11-24T12:00:00+08:00",
            "original_time_note": "全区合练已完成，待中国载人航天工程办公室公布精确点火时刻",
            "event_type": "politics_macro",
            "region": "china",
            "country": "中国",
            "city": "酒泉",
            "certainty": "reported_tbd",
            "certainty_label": "全区合练已完 · 待发射",
            "is_clock_tbd": True,
            "category": "tech",
            "entity_ids": [],
            "watch_variable": "火箭加注与发射点火时刻官宣、航天员乘组名单公布与空间站对接进展",
            "pre_expectation": "催化中国商业航天、测控通信与航天特种材料关注度",
            "source_name": "中国载人航天工程网",
            "source_url": "https://www.cmse.gov.cn/",
        },
        {
            "calendar_id": "cal_tech_tesla_q4_fsd_node",
            "title": "特斯拉 (Tesla) Q4 全球交付实绩与 FSD v15 / Cybercab 推进节点",
            "title_en": "Tesla Q4 Deliveries Report & FSD v15 / Cybercab Rollout Checkpoint",
            "scheduled_at": "2027-01-02T22:00:00+08:00",
            "original_time_note": "2027-01-02 美东早晨例行公布上季产销量",
            "event_type": "tech_launch",
            "region": "us",
            "country": "美国",
            "city": "奥斯汀",
            "certainty": "confirmed_official",
            "certainty_label": "特斯拉季度例行窗口",
            "category": "tech",
            "entity_ids": ["ent_spacex_tesla"],
            "watch_variable": "单季交付量及储能 GWh 装机量、FSD v15 在欧洲及中国市场准入/开放进展",
            "pre_expectation": "直接决定 TSLA 年度销量增速与高阶智驾软件订阅估值重估",
            "source_name": "Tesla Investor Relations",
            "source_url": "https://ir.tesla.com/",
        },
        {
            "calendar_id": "cal_tech_nvidia_gtc_2027",
            "title": "NVIDIA GTC 2027 全球 AI 开发者大会（黄仁勋主题演讲与下一代架构）",
            "title_en": "NVIDIA GTC 2027 Global AI Conference (San Jose Keynote)",
            "scheduled_at": "2027-03-16T01:00:00+08:00",
            "original_time_note": "2027-03-15 ~ 03-18 美国加州圣何塞 SAP 中心（北京时间 16 日凌晨主题演讲）",
            "event_type": "tech_launch",
            "region": "us",
            "country": "美国",
            "city": "加州圣何塞",
            "certainty": "confirmed_official",
            "certainty_label": "NVIDIA 年度核心大会",
            "category": "tech",
            "entity_ids": ["ent_nvidia", "ent_ai_infra_tools"],
            "watch_variable": "Rubin 下一代 GPU / 机柜液冷互连方案、推理能效比提升与云厂订单路线图",
            "pre_expectation": "全球 AI 算力芯片、光模块 (CPO) 与散热电源产业链最重磅催化大会",
            "source_name": "NVIDIA GTC",
            "source_url": "https://www.nvidia.com/gtc/",
        },
        {
            "calendar_id": "cal_tech_google_io_2027",
            "title": "Google I/O 2027 全球开发者大会（Gemini 大模型、Android AI 与 TPU 生态）",
            "title_en": "Google I/O 2027 Developer Conference (Mountain View)",
            "scheduled_at": "2027-05-19T01:00:00+08:00",
            "original_time_note": "2027 年 5 月中下旬 美国加州山景城（历年 5 月中旬档期）",
            "event_type": "tech_launch",
            "region": "us",
            "country": "美国",
            "city": "加州山景城",
            "certainty": "reported_tbd",
            "certainty_label": "年度开发者大会窗口",
            "is_clock_tbd": True,
            "category": "tech",
            "entity_ids": ["ent_google", "ent_ai_infra_tools"],
            "watch_variable": "Gemini 新一代原生多模态能力、Android 系统级智能体及搜索广告变现更新",
            "pre_expectation": "检验谷歌消费级 AI 生态护城河与自研 TPU 商业效率",
            "source_name": "Google I/O",
            "source_url": "https://io.google/",
        },
        {
            "calendar_id": "cal_tech_msft_build_2027",
            "title": "Microsoft Build 2027 微软全球开发者大会（Azure AI 与 Copilot Agents）",
            "title_en": "Microsoft Build 2027 Conference (Seattle)",
            "scheduled_at": "2027-05-19T23:00:00+08:00",
            "original_time_note": "2027 年 5 月中下旬 美国西雅图",
            "event_type": "tech_launch",
            "region": "us",
            "country": "美国",
            "city": "西雅图",
            "certainty": "reported_tbd",
            "certainty_label": "微软年度开发者窗口",
            "is_clock_tbd": True,
            "category": "tech",
            "entity_ids": ["ent_microsoft", "ent_openai"],
            "watch_variable": "企业级多智能体编排标准、Azure Maia 自研芯片部署与 OpenAI 新模型集成",
            "pre_expectation": "企业级 SaaS 与云计算 AI 商用化落地风向标",
            "source_name": "Microsoft Build",
            "source_url": "https://build.microsoft.com/",
        },
        {
            "calendar_id": "cal_tech_computex_2027",
            "title": "COMPUTEX 2027 台北国际电脑展（芯片巨头与 AI 服务器整机联合发布）",
            "title_en": "COMPUTEX 2027 Taipei Tech Expo",
            "scheduled_at": "2027-06-01T09:00:00+08:00",
            "original_time_note": "2027-06-01 ~ 06-04 中国台北南港展览馆",
            "event_type": "tech_launch",
            "region": "china",
            "country": "中国",
            "city": "台北",
            "certainty": "confirmed_official",
            "certainty_label": "官方已定档期",
            "category": "tech",
            "entity_ids": ["ent_nvidia", "ent_tsmc", "ent_amd"],
            "watch_variable": "NVIDIA / AMD / Intel CEO 主题演讲、AI PC 芯片及先进封装液冷服务器展品",
            "pre_expectation": "半导体与 ODMs 代工厂（广达/鸿海/工业富联等）年度关键节点",
            "source_name": "TAITRA COMPUTEX",
            "source_url": "https://www.computextaipei.com.tw/",
        },
        {
            "calendar_id": "cal_tech_apple_wwdc_2027",
            "title": "Apple WWDC 2027 苹果全球开发者大会（iOS / macOS 与 Apple Intelligence 升级）",
            "title_en": "Apple WWDC 2027 Worldwide Developers Conference (Cupertino)",
            "scheduled_at": "2027-06-08T01:00:00+08:00",
            "original_time_note": "2027 年 6 月上旬 美国加州库比蒂诺 Apple Park（北京时间凌晨 1:00 Keynote）",
            "event_type": "tech_launch",
            "region": "us",
            "country": "美国",
            "city": "加州库比蒂诺",
            "certainty": "reported_tbd",
            "certainty_label": "苹果年度软件开发大会窗口",
            "is_clock_tbd": True,
            "category": "tech",
            "entity_ids": ["ent_apple"],
            "watch_variable": "新一代 OS 架构、端侧大模型隐私开放边界及 Siri 跨应用执行力",
            "pre_expectation": "催化果链硬件换机周期预期与应用生态估值",
            "source_name": "Apple Developer",
            "source_url": "https://developer.apple.com/wwdc/",
        },
        {
            "calendar_id": "cal_tech_huawei_hdc_2027",
            "title": "华为开发者大会 HDC 2027（HarmonyOS 纯血鸿蒙生态与盘古大模型）",
            "title_en": "Huawei Developer Conference HDC 2027 (Dongguan Songshan Lake)",
            "scheduled_at": "2027-06-20T14:30:00+08:00",
            "original_time_note": "2027 年 6 月中下旬 中国广东东莞松山湖",
            "event_type": "tech_launch",
            "region": "china",
            "country": "中国",
            "city": "东莞",
            "certainty": "reported_tbd",
            "certainty_label": "华为年度核心技术大会窗口",
            "is_clock_tbd": True,
            "category": "tech",
            "entity_ids": ["ent_huawei"],
            "watch_variable": "鸿蒙原生应用生态进展、昇腾云全栈 AI 开发工具链与盘古新版本参数",
            "pre_expectation": "国产基础软件与昇腾算力开发生态核心催化点",
            "source_name": "Huawei Developer",
            "source_url": "https://developer.huawei.com/",
        },
        {
            "calendar_id": "cal_tech_apple_fall_2027",
            "title": "苹果 2027 秋季新品发布会预期窗口（旗舰 iPhone 与自研端侧芯片）",
            "title_en": "Apple Fall 2027 Hardware Keynote Window (Next-Gen iPhone & Silicon)",
            "scheduled_at": "2027-09-10T01:00:00+08:00",
            "original_time_note": "2027 年 9 月上旬 美国加州库比蒂诺",
            "event_type": "tech_launch",
            "region": "us",
            "country": "美国",
            "city": "加州库比蒂诺",
            "certainty": "reported_tbd",
            "certainty_label": "历年 9 月硬件旗舰档期",
            "is_clock_tbd": True,
            "category": "tech",
            "entity_ids": ["ent_apple", "ent_tsmc"],
            "watch_variable": "旗舰终端定价策略、2nm/3nm 芯片 NPU 算力跃迁及备货指引",
            "pre_expectation": "全球消费电子与苹果产业链年度最高关注度发布会",
            "source_name": "Apple Events",
            "source_url": "https://www.apple.com/apple-events/",
        },
        {
            "calendar_id": "cal_tech_huawei_connect_2027",
            "title": "华为全联接大会 HUAWEI CONNECT 2027（昇腾超节点与行业数字化底座）",
            "title_en": "HUAWEI CONNECT 2027 (Shanghai)",
            "scheduled_at": "2027-09-18T09:00:00+08:00",
            "original_time_note": "2027 年 9 月中下旬 中国上海世博展览馆",
            "event_type": "tech_launch",
            "region": "china",
            "country": "中国",
            "city": "上海",
            "certainty": "reported_tbd",
            "certainty_label": "华为面向政企与算力年度盛会",
            "is_clock_tbd": True,
            "category": "tech",
            "entity_ids": ["ent_huawei"],
            "watch_variable": "昇腾 AI 集群规模扩展路线、行业大模型商业化样板案例",
            "pre_expectation": "国产算力数据中心及金融/能源行业智能化核心大会",
            "source_name": "Huawei Connect",
            "source_url": "https://www.huawei.com/cn/events/huaweiconnect",
        },

        # === 4. 全球央行与核心宏观数据 (central_bank) ===
        {
            "calendar_id": "cal_cb_us_nfp_2026_12",
            "title": "美国 11 月非农就业人数与失业率报告 (BLS Nonfarm Payrolls)",
            "title_en": "US November Nonfarm Payrolls & Unemployment Rate (BLS)",
            "scheduled_at": "2026-12-04T21:30:00+08:00",
            "original_time_note": "2026-12-04 08:30 EST / 21:30 北京时间（12 月 FOMC 会前核心就业数据）",
            "event_type": "central_bank",
            "region": "us",
            "country": "美国",
            "city": "华盛顿",
            "certainty": "confirmed_official",
            "certainty_label": "美国劳工部法定发布日",
            "category": "finance",
            "entity_ids": ["ent_macro_fomc"],
            "watch_variable": "新增非农就业人数、失业率及平均时薪 (AHE) 同比增速",
            "pre_expectation": "直接决定 12 月 10 日 FOMC 议息会议紧缩节奏权重",
            "source_name": "U.S. Bureau of Labor Statistics",
            "source_url": "https://www.bls.gov/schedule/news_release/empsit.htm",
        },
        {
            "calendar_id": "cal_cb_opec_plus_2026_12",
            "title": "OPEC+ 部长级减产与配额评估会议（霍尔木兹局势下原油供应定调）",
            "title_en": "OPEC+ Ministerial Output & Quota Review Meeting (Vienna)",
            "scheduled_at": "2026-12-06T18:00:00+08:00",
            "original_time_note": "2026 年 12 月初 奥地利维也纳（历年年底产油配额决策窗口）",
            "event_type": "central_bank",
            "region": "global",
            "country": "奥地利",
            "city": "维也纳",
            "certainty": "reported_tbd",
            "certainty_label": "能源产油国季度关键会期",
            "is_clock_tbd": True,
            "category": "finance",
            "entity_ids": ["ent_geopolitics_energy"],
            "watch_variable": "2027 年一季度自愿减产延长力度与中东供应链干扰应急增产缓冲",
            "pre_expectation": "决定布伦特原油中枢价格及全球通胀二次反弹风险",
            "source_name": "OPEC",
            "source_url": "https://www.opec.org/",
        },
        {
            "calendar_id": "cal_cb_us_cpi_2026_12",
            "title": "美国 11 月 CPI 与核心通胀数据公布 (FOMC 决议同日关键前置数据)",
            "title_en": "US November CPI & Core Inflation Report (BLS)",
            "scheduled_at": "2026-12-10T21:30:00+08:00",
            "original_time_note": "2026-12-10 08:30 EST / 21:30 北京时间",
            "event_type": "central_bank",
            "region": "us",
            "country": "美国",
            "city": "华盛顿",
            "certainty": "confirmed_official",
            "certainty_label": "美国劳工部法定发布日",
            "category": "finance",
            "entity_ids": ["ent_macro_fomc"],
            "watch_variable": "核心 CPI 环比折年率、住房租金及服务业超级核心通胀读数",
            "pre_expectation": "能源波动与关税预期下的核心通胀韧性评估",
            "source_name": "U.S. Bureau of Labor Statistics",
            "source_url": "https://www.bls.gov/schedule/news_release/cpi.htm",
        },
        {
            "calendar_id": "cal_cb_ecb_rate_2026_12",
            "title": "欧洲央行 (ECB) 管理委员会货币政策利率决议与行长发布会",
            "title_en": "European Central Bank (ECB) Monetary Policy Rate Decision",
            "scheduled_at": "2026-12-17T21:15:00+08:00",
            "original_time_note": "2026-12-17 14:15 CET / 21:15 北京时间",
            "event_type": "central_bank",
            "region": "europe_apac",
            "country": "德国",
            "city": "法兰克福",
            "certainty": "confirmed_official",
            "certainty_label": "欧洲央行法定议息日",
            "category": "finance",
            "entity_ids": [],
            "watch_variable": "三大关键利率调整幅度与欧元区 2027 年经济增长/通胀最新预测",
            "pre_expectation": "欧盟预算博弈与欧元区制造业分化的货币应对",
            "source_name": "European Central Bank",
            "source_url": "https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html",
        },
        {
            "calendar_id": "cal_cb_boe_rate_2026_12",
            "title": "英国央行 (Bank of England) 货币政策委员会 MPC 利率决议",
            "title_en": "Bank of England MPC Monetary Policy Rate Decision (London)",
            "scheduled_at": "2026-12-17T20:00:00+08:00",
            "original_time_note": "2026-12-17 12:00 GMT / 20:00 北京时间",
            "event_type": "central_bank",
            "region": "europe_apac",
            "country": "英国",
            "city": "伦敦",
            "certainty": "confirmed_official",
            "certainty_label": "英国央行法定议息日",
            "category": "finance",
            "entity_ids": [],
            "watch_variable": "基准银行利率投票比例 (MPC Split) 与英镑/英国国债收益率走向",
            "pre_expectation": "牵动欧洲金融资产与外汇套息流向",
            "source_name": "Bank of England",
            "source_url": "https://www.bankofengland.co.uk/monetary-policy/upcoming-mpc-dates",
        },
        {
            "calendar_id": "cal_cb_boj_rate_2026_12",
            "title": "日本央行 (BoJ) 货币政策委员会议息决议及日元利率前瞻指引",
            "title_en": "Bank of Japan (BoJ) Monetary Policy Meeting Rate Decision",
            "scheduled_at": "2026-12-18T11:00:00+08:00",
            "original_time_note": "2026-12-18 午间公布决议结果（北京时间约 11:00）",
            "event_type": "central_bank",
            "region": "europe_apac",
            "country": "日本",
            "city": "东京",
            "certainty": "confirmed_official",
            "certainty_label": "日本央行已定会期",
            "category": "finance",
            "entity_ids": [],
            "watch_variable": "无担保隔夜拆借目标利率调整节奏与美日利差套息交易 (Carry Trade) 流向",
            "pre_expectation": "日元汇率波动对全球纳指及亚太科技股流动性构成外溢冲击",
            "source_name": "Bank of Japan",
            "source_url": "https://www.boj.or.jp/en/mopo/mpmsche_minu/index.htm",
        },

        # === 5. 财报与资本市场节点 (earnings_capital) ===
        {
            "calendar_id": "cal_cap_anthropic_ipo_week_check",
            "title": "Anthropic 上市首周成交量与发行价承销护盘检验窗口",
            "title_en": "Anthropic Mega-IPO First-Week Stabilization & Greenshoe Test",
            "scheduled_at": "2026-11-27T05:00:00+08:00",
            "original_time_note": "2026-11-27 美股收市（上市首完整周交易检验节点）",
            "event_type": "earnings_capital",
            "region": "us",
            "country": "美国",
            "city": "纽约",
            "certainty": "reported_tbd",
            "certainty_label": "资本市场首周窗口",
            "is_clock_tbd": True,
            "category": "finance",
            "entity_ids": ["ent_anthropic", "ent_ai_infra_tools"],
            "watch_variable": "IPO 首周是否守住发行价、超额配售选择权 (Greenshoe) 动用情况与企业 ARR 指引",
            "pre_expectation": "直接锚定 OpenAI/xAI 等超级大模型独角兽一级到二级估值中枢",
            "source_name": "SEC / 华尔街交易日程",
            "source_url": "https://www.sec.gov/",
        },
        {
            "calendar_id": "cal_cap_tesla_q4_earnings_2027",
            "title": "特斯拉 (TSLA) FY2026 Q4 季度财报公布与马斯克电话会",
            "title_en": "Tesla FY2026 Q4 Earnings Release & Musk Shareholder Call",
            "scheduled_at": "2027-01-28T06:30:00+08:00",
            "original_time_note": "2027 年 1 月下旬 美股盘后（历年 1 月最后一周周三美股盘后）",
            "event_type": "earnings_capital",
            "region": "us",
            "country": "美国",
            "city": "奥斯汀",
            "certainty": "reported_tbd",
            "certainty_label": "美股巨头财报预期窗口",
            "is_clock_tbd": True,
            "category": "finance",
            "entity_ids": ["ent_spacex_tesla"],
            "watch_variable": "汽车业务毛利率（剔除监管积分）、FSD 递延收入确认及 2027 年 Capex 指引",
            "pre_expectation": "新能源车与 AI 自动驾驶核心估值验证日",
            "source_name": "Tesla IR",
            "source_url": "https://ir.tesla.com/",
        },
        {
            "calendar_id": "cal_cap_nvidia_fy27_q4_2027",
            "title": "英伟达 (NVDA) FY2027 第四财季财报及算力需求指引电话会",
            "title_en": "NVIDIA FY2027 Q4 Earnings Call & Datacenter Guidance",
            "scheduled_at": "2027-02-25T05:20:00+08:00",
            "original_time_note": "2027 年 2 月下旬 美股盘后（历年 2 月第四周周三盘后）",
            "event_type": "earnings_capital",
            "region": "us",
            "country": "美国",
            "city": "加州圣克拉拉",
            "certainty": "reported_tbd",
            "certainty_label": "AI 算力链总锚定财报窗口",
            "is_clock_tbd": True,
            "category": "finance",
            "entity_ids": ["ent_nvidia", "ent_tsmc"],
            "watch_variable": "数据中心单季营收增速、新一代芯片产能爬坡毛利率及主权 AI 订单指引",
            "pre_expectation": "决定全球半导体 ETF、光模块与港股/美股科技风偏的关键财报夜",
            "source_name": "NVIDIA IR",
            "source_url": "https://investor.nvidia.com/",
        },
        {
            "calendar_id": "cal_cap_tencent_hkex_fy26_2027",
            "title": "腾讯控股 (00700.HK) 2026 年度业绩公布与资本开支说明会",
            "title_en": "Tencent Holdings FY2026 Annual Results & AI Capex Briefing",
            "scheduled_at": "2027-03-19T18:00:00+08:00",
            "original_time_note": "2027 年 3 月中下旬 香港联交所盘后（历年 3 月中下旬例行年报窗口）",
            "event_type": "earnings_capital",
            "region": "china",
            "country": "中国",
            "city": "深圳/香港",
            "certainty": "reported_tbd",
            "certainty_label": "港股核心权重年报窗口",
            "is_clock_tbd": True,
            "category": "finance",
            "entity_ids": ["ent_tencent"],
            "watch_variable": "AI 算力资本开支预算、混元大模型商业化及年度股份回购加码规模",
            "pre_expectation": "港股恒生科指现金流与股东回报核心风向标",
            "source_name": "HKEX / Tencent IR",
            "source_url": "https://www.tencent.com/zh-cn/investors.html",
        },
        {
            "calendar_id": "cal_cb_us_pce_gdp_2026_11",
            "title": "美国 10 月核心 PCE 物价指数与三季度实际 GDP 修正值公布",
            "title_en": "US October Core PCE Inflation & Q3 GDP Second Estimate",
            "scheduled_at": "2026-11-25T21:30:00+08:00",
            "original_time_note": "2026-11-25 08:30 EST / 21:30 北京时间 (感恩节前夕重要宏观读数)",
            "event_type": "central_bank",
            "region": "us",
            "country": "美国",
            "city": "华盛顿",
            "certainty": "confirmed_official",
            "certainty_label": "美国商务部 BEA 法定发布日",
            "category": "finance",
            "entity_ids": ["ent_macro_fomc"],
            "watch_variable": "核心 PCE 月率/年率与个人消费支出增速，直接影响 12 月 FOMC 利率定调",
            "pre_expectation": "美联储最青睐的通胀标尺，决定美债收益率与美元短线方向",
            "source_name": "US BEA",
            "source_url": "https://www.bea.gov/news/schedule",
        },
        {
            "calendar_id": "cal_pol_cn_ind_profits_2026_11",
            "title": "中国 10 月规模以上工业企业利润同比增速公布",
            "title_en": "China NBS October Industrial Enterprise Profits",
            "scheduled_at": "2026-11-27T09:30:00+08:00",
            "original_time_note": "2026-11-27 09:30 北京时间 (国家统计局月度工业效益公报)",
            "event_type": "politics_macro",
            "region": "china",
            "country": "中国",
            "city": "北京",
            "certainty": "confirmed_official",
            "certainty_label": "官方例行日程",
            "category": "finance",
            "entity_ids": ["ent_china_macro"],
            "watch_variable": "装备制造业与高技术制造业利润改善斜率及PPI传导压降效应",
            "pre_expectation": "A 股顺周期与先进制造三季报后盈利拐点交叉验证",
            "source_name": "国家统计局",
            "source_url": "https://www.stats.gov.cn/",
        },
        {
            "calendar_id": "cal_tech_aws_reinvent_2026",
            "title": "AWS re:Invent 2026 全球云计算与 Bedrock AI 智能体大会",
            "title_en": "AWS re:Invent 2026 Cloud & AI Agent Keynote (Las Vegas)",
            "scheduled_at": "2026-11-30T23:00:00+08:00",
            "original_time_note": "2026-11-30 至 12-04 拉斯维加斯（北京时间 12 月 1 日凌晨开讲）",
            "event_type": "tech_launch",
            "region": "us",
            "country": "美国",
            "city": "拉斯维加斯",
            "certainty": "confirmed_official",
            "certainty_label": "云计算年度旗舰大会",
            "category": "tech",
            "entity_ids": ["ent_amazon_aws", "ent_ai_infra_tools", "ent_anthropic"],
            "watch_variable": "Trainium 新一代自研 AI 芯片性能、Nova 模型升级与企业级 Agent 工具链落地",
            "pre_expectation": "云基础设施 Capex 回报与自研算力替代进度风向标",
            "source_name": "Amazon Web Services",
            "source_url": "https://reinvent.awsevents.com/",
        },
        {
            "calendar_id": "cal_cb_us_ism_mfg_2026_12",
            "title": "美国 11 月 ISM 制造业 PMI 及新订单分项数据发布",
            "title_en": "US November ISM Manufacturing PMI Report",
            "scheduled_at": "2026-12-01T23:00:00+08:00",
            "original_time_note": "2026-12-01 10:00 EST / 23:00 北京时间",
            "event_type": "central_bank",
            "region": "us",
            "country": "美国",
            "city": "华盛顿",
            "certainty": "confirmed_official",
            "certainty_label": "每月首个工作日发布",
            "category": "finance",
            "entity_ids": ["ent_macro_fomc"],
            "watch_variable": "制造业新订单、物价支付指数及就业分项对美国衰退/再通胀预期影响",
            "pre_expectation": "全球工业大宗商品与美股周期板块短线定价锚点",
            "source_name": "ISM",
            "source_url": "https://www.ismworld.org/",
        },
        {
            "calendar_id": "cal_expo_neurips_2026",
            "title": "NeurIPS 2026 神经信息处理系统全球顶级 AI 学术年会",
            "title_en": "NeurIPS 2026 Annual AI Research Conference",
            "scheduled_at": "2026-12-06T09:00:00+08:00",
            "original_time_note": "2026-12-06 至 12-12（官方年度 AI 顶会窗口）",
            "event_type": "expo_summit",
            "region": "global",
            "country": "全球",
            "city": "",
            "certainty": "confirmed_official",
            "certainty_label": "国际顶级 AI 学术年会",
            "is_clock_tbd": True,
            "category": "tech",
            "entity_ids": ["ent_openai", "ent_anthropic", "ent_google", "ent_deepseek"],
            "watch_variable": "世界模型、长程推理架构、Test-time Compute 扩展律最佳论文与前沿开源代码发布",
            "pre_expectation": "2027 年大模型下一代研究范式核心信号源",
            "source_name": "NeurIPS Foundation",
            "source_url": "https://neurips.cc/",
        },
    ]


def build_curated_global_calendar(generated_dt: datetime) -> List[Dict[str, Any]]:
    """Return upcoming/recent verified 5-category catalyst items enriched with region & countdown."""
    items: List[Dict[str, Any]] = []
    cutoff = generated_dt - timedelta(days=3)
    for raw in _static_global_schedule():
        s_dt = parse_iso_datetime(str(raw.get("scheduled_at") or ""))
        if s_dt is None or s_dt < cutoff:
            continue
        rec = dict(raw)
        rec.setdefault("is_past", False)
        rec.setdefault("storyline_id", None)
        rec.setdefault("actual_result", None)
        items.append(enrich_calendar_item_metadata(rec, generated_dt))
    return items


_ZH_WEEKDAYS = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
_EN_WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

_BREAKING_NOISE_RE = re.compile(
    r"(?:围巾|座驾|同框|开了个玩笑|花絮|是否将举行|没有这方面的信息|美方代表有哪些|发言人回应|外交部回应|"
    r"邀请.{0,12}组阁|呼吁.{0,10}停火|考虑.{0,10}征税|传闻称|或将讨论|股市表现|股价表现|涨停|跌停|大跌|大涨|"
    r"IPO后|上市后|复盘|盘点|回顾|闭幕|落幕|已于|此前|上周|昨日|昨天|after\s+ipo|post-?ipo)",
    re.I,
)

_BREAKING_ACTION_RE = re.compile(
    r"(?:发布会|新品发布|开发布会|发布|推出|上线|开源|预告|开幕|召开|举行|公布|揭晓|出访|访问|启程|表决|听证|生效|施行|实施|减免|免收|执行|上市|挂牌|财报|电话会|交付|峰会|论坛|会谈|"
    r"\blaunch(?:es|ing)?\b|\bunveil(?:s|ing)?\b|\bkeynote\b|\bsummit\b|\bvisit(?:s|ing)?\b|\bearnings\b|\btake effect\b|\beffective\b|\bvote\b)",
    re.I,
)


def parse_relative_schedule_datetime(
    text: str,
    anchor_dt: datetime,
) -> Optional[Tuple[datetime, str, bool]]:
    """Parse explicit or ZH/EN relative dates anchored on anchor_dt -> (dt, note, is_clock_tbd)."""
    if not text or not isinstance(text, str):
        return None
    s = re.sub(r"\s+", " ", text).strip()
    base_hour = 10

    # 0. Statutory / policy effective dates take priority over article datelines (e.g. 自2026年11月30日起施行)
    m_eff = re.search(
        r"(?:自|将于)\s*(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日(?:起|起正式)?(?:施行|生效|实施|减免|免收|执行)",
        s,
    )
    if m_eff:
        yr = int(m_eff.group(1) or anchor_dt.year)
        mo = int(m_eff.group(2))
        dy = int(m_eff.group(3))
        if not m_eff.group(1) and anchor_dt.month == 12 and mo == 1:
            yr += 1
        try:
            dt = anchor_dt.replace(year=yr, month=mo, day=dy, hour=9, minute=0, second=0, microsecond=0)
            return dt, f"{yr}-{mo:02d}-{dy:02d} 政策/新规生效日", True
        except ValueError:
            pass

    # 1. Explicit date range: M月D日至D日 / M月D日-D日 / YYYY年M月D日
    m_date = re.search(
        r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日(?:\s*(?:至|到|-|~)\s*(?:\d{1,2}月)?(\d{1,2})日)?(?:\s*(?:上午|下午|晚间|晚)?\s*(\d{1,2})[:：](\d{2}))?",
        s,
    )
    if m_date:
        yr = int(m_date.group(1) or anchor_dt.year)
        mo = int(m_date.group(2))
        dy = int(m_date.group(3))
        end_dy = m_date.group(4)
        if not m_date.group(1) and anchor_dt.month == 12 and mo == 1:
            yr += 1
        hr = int(m_date.group(5)) if m_date.group(5) else base_hour
        mn = int(m_date.group(6)) if m_date.group(6) else 0
        is_tbd = not bool(m_date.group(5))
        try:
            dt = anchor_dt.replace(year=yr, month=mo, day=dy, hour=min(23, hr), minute=min(59, mn), second=0, microsecond=0)
            note = (
                f"{yr}-{mo:02d}-{dy:02d} 至 {int(end_dy):02d} 日日程窗口"
                if end_dy
                else (f"{yr}-{mo:02d}-{dy:02d} {hr:02d}:{mn:02d}" if not is_tbd else f"{yr}-{mo:02d}-{dy:02d} 日程窗口 (具体钟点待定)")
            )
            return dt, note, is_tbd
        except ValueError:
            return None

    # 2. Relative ZH tokens: 今天 / 明天 / 明晚 / 后天
    if re.search(r"(?:今晚|今夜|今日|今天)", s):
        is_night = "今晚" in s or "今夜" in s
        dt = anchor_dt.replace(hour=20 if is_night else 14, minute=0, second=0, microsecond=0)
        return dt, f"{dt.strftime('%Y-%m-%d')} {'晚间' if is_night else '当日'}突发排期", True

    if re.search(r"(?:明晚|明日|明天)", s):
        is_night = "明晚" in s
        dt = (anchor_dt + timedelta(days=1)).replace(hour=20 if is_night else 10, minute=0, second=0, microsecond=0)
        return dt, f"{dt.strftime('%Y-%m-%d')} {'明晚' if is_night else '明日'}日程（基于信源发布时间推算）", True

    if "后天" in s:
        dt = (anchor_dt + timedelta(days=2)).replace(hour=10, minute=0, second=0, microsecond=0)
        return dt, f"{dt.strftime('%Y-%m-%d')} 后天日程（基于信源发布时间推算）", True

    # 3. Relative ZH week: 下周[一..日] / 本周[一..日] / 下周末 / 本周末
    m_nxw = re.search(r"下周([一二三四五六日天])", s)
    if m_nxw:
        wd = _ZH_WEEKDAYS[m_nxw.group(1)]
        days_ahead = (7 - anchor_dt.weekday()) + wd
        dt = (anchor_dt + timedelta(days=days_ahead)).replace(hour=10, minute=0, second=0, microsecond=0)
        return dt, f"{dt.strftime('%Y-%m-%d')} 下周{m_nxw.group(1)}日程窗口 (来源报道推算)", True

    m_curw = re.search(r"(?:本周|将于周|定于周|拟于周|预计周)([一二三四五六日天])", s)
    if m_curw:
        wd = _ZH_WEEKDAYS[m_curw.group(1)]
        days_ahead = (wd - anchor_dt.weekday()) % 7
        if days_ahead == 0 and anchor_dt.hour >= 18:
            days_ahead = 7
        dt = (anchor_dt + timedelta(days=days_ahead)).replace(hour=10, minute=0, second=0, microsecond=0)
        return dt, f"{dt.strftime('%Y-%m-%d')} 周{m_curw.group(1)}日程窗口 (来源报道推算)", True

    if "下周末" in s:
        days_ahead = (7 - anchor_dt.weekday()) + 5
        dt = (anchor_dt + timedelta(days=days_ahead)).replace(hour=10, minute=0, second=0, microsecond=0)
        return dt, f"{dt.strftime('%Y-%m-%d')} 下周末日程窗口", True

    if "本周末" in s:
        days_ahead = max(0, 5 - anchor_dt.weekday())
        dt = (anchor_dt + timedelta(days=days_ahead)).replace(hour=10, minute=0, second=0, microsecond=0)
        return dt, f"{dt.strftime('%Y-%m-%d')} 本周末日程窗口", True

    if "下周" in s:
        days_ahead = 7 - anchor_dt.weekday()
        dt = (anchor_dt + timedelta(days=days_ahead)).replace(hour=10, minute=0, second=0, microsecond=0)
        return dt, f"{dt.strftime('%Y-%m-%d')} 下周窗口 (具体日期以官方公布为准)", True

    m_days = re.search(r"(\d{1,2})\s*[天日]后", s)
    if m_days:
        delta = int(m_days.group(1))
        if 1 <= delta <= 60:
            dt = (anchor_dt + timedelta(days=delta)).replace(hour=10, minute=0, second=0, microsecond=0)
            return dt, f"{dt.strftime('%Y-%m-%d')}（约 {delta} 天后日程）", True

    if "下月中旬" in s:
        ny = anchor_dt.year + (1 if anchor_dt.month == 12 else 0)
        nm = 1 if anchor_dt.month == 12 else anchor_dt.month + 1
        dt = anchor_dt.replace(year=ny, month=nm, day=15, hour=10, minute=0, second=0, microsecond=0)
        return dt, f"{ny}-{nm:02d} 中旬预期窗口", True

    # 4. English relative cues
    if re.search(r"\btomorrow\b", s, re.I):
        dt = (anchor_dt + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
        return dt, f"{dt.strftime('%Y-%m-%d')} Tomorrow schedule window", True

    m_en_wd = re.search(r"\bnext\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", s, re.I)
    if m_en_wd:
        wd = _EN_WEEKDAYS[m_en_wd.group(1).lower()]
        days_ahead = (7 - anchor_dt.weekday()) + wd
        dt = (anchor_dt + timedelta(days=days_ahead)).replace(hour=10, minute=0, second=0, microsecond=0)
        return dt, f"{dt.strftime('%Y-%m-%d')} Next {m_en_wd.group(1).capitalize()} window", True

    if re.search(r"\bnext\s+week\b", s, re.I):
        days_ahead = 7 - anchor_dt.weekday()
        dt = (anchor_dt + timedelta(days=days_ahead)).replace(hour=10, minute=0, second=0, microsecond=0)
        return dt, f"{dt.strftime('%Y-%m-%d')} Next week schedule window", True

    m_en_days = re.search(r"\bin\s+(\d{1,2})\s+days\b", s, re.I)
    if m_en_days:
        delta = int(m_en_days.group(1))
        if 1 <= delta <= 60:
            dt = (anchor_dt + timedelta(days=delta)).replace(hour=10, minute=0, second=0, microsecond=0)
            return dt, f"{dt.strftime('%Y-%m-%d')} In {delta} days", True

    return None


def build_event_type_watch_variable(event_type: str, title: str = "") -> Tuple[str, str]:
    """Return strict domain-appropriate watch variables (never inject earnings margins into politics/tech)."""
    low = (title or "").lower()
    if event_type == "central_bank":
        return (
            "利率决策区间、通胀/就业关键读数及央行前瞻指引措辞变化",
            "Official policy rate band, inflation/payroll print & forward guidance tone",
        )
    if event_type == "earnings_capital":
        if "ipo" in low or "上市" in low or "挂牌" in low:
            return (
                "最终发行价、募资规模、机构基石锁仓比例与首周交易承盘",
                "Final IPO pricing, proceeds size, anchor lockups & first-week trading",
            )
        return (
            "官方披露实值营收/利润、毛利率与下季资本开支指引",
            "Reported revenue/EPS, gross margin & next-quarter Capex guidance",
        )
    if event_type == "tech_launch":
        return (
            "新品/模型实测规格、定价策略、开放可用时间及产业链生态协同",
            "Released specs/benchmarks, pricing, GA availability & ecosystem impact",
        )
    if event_type == "expo_summit":
        return (
            "重磅峰会议程、高层政策/行业表态、首发成果与产业签约动向",
            "Keynote agenda, high-level statements, product unveilings & signed deals",
        )
    return (
        "官方联合公报、新规生效细则、关键表决结果及对经贸/产业链影响",
        "Official communique, effective rule details, vote outcome & trade impact",
    )


def extract_breaking_calendar_items(
    *,
    cat_docs: Dict[str, dict],
    live_wire_items: List[dict],
    ai_progress_items: List[dict],
    generated_dt: datetime,
    existing_calendar_items: List[dict],
) -> List[Dict[str, Any]]:
    """Dynamically extract breaking upcoming schedules from News, 7x24 Live Wire & AI Frontier."""
    from pipeline.dedup import title_similarity
    from pipeline.time_utils import to_iso_shanghai

    candidates: List[Dict[str, Any]] = []
    for doc in (cat_docs or {}).values():
        for ev in (doc.get("events") or []):
            if not isinstance(ev, dict):
                continue
            indep_c = int(ev.get("independent_publisher_count") or len(ev.get("sources") or []))
            title = str(ev.get("title") or "").strip()
            if ev.get("contradictions") or (ev.get("attribution_warning") and indep_c < 2):
                continue
            if title.startswith(("报道称", "消息称", "传闻")) and indep_c < 2:
                continue
            srcs = ev.get("sources") or []
            candidates.append(
                {
                    "id": str(ev.get("event_id") or ""),
                    "channel": "news",
                    "title": title,
                    "title_en": ev.get("title_en"),
                    "body": f"{ev.get('fact_summary') or ''} {ev.get('speculation_or_outlook') or ''}",
                    "anchor_iso": ev.get("first_reported_at") or ev.get("published_at") or ev.get("fetched_at"),
                    "category": ev.get("category") or "global",
                    "entity_ids": list(ev.get("entity_ids") or []),
                    "storyline_id": ev.get("storyline_id"),
                    "event_id": ev.get("event_id"),
                    "source_name": (srcs[0].get("source_name") if srcs else "今日要闻"),
                    "source_url": (srcs[0].get("url") if srcs else None),
                }
            )

    for lw in (live_wire_items or [])[:60]:
        if not isinstance(lw, dict):
            continue
        candidates.append(
            {
                "id": str(lw.get("id") or lw.get("event_id") or ""),
                "channel": "live_wire",
                "title": str(lw.get("title") or "").strip(),
                "title_en": lw.get("title_en"),
                "body": str(lw.get("summary") or lw.get("excerpt") or ""),
                "anchor_iso": lw.get("published_at") or lw.get("fetched_at"),
                "category": lw.get("category") or "finance",
                "entity_ids": list(lw.get("entity_ids") or []),
                "storyline_id": None,
                "event_id": lw.get("event_id"),
                "source_name": str(lw.get("source_name") or "7x24快讯"),
                "source_url": lw.get("url"),
            }
        )

    for ai in (ai_progress_items or [])[:50]:
        if not isinstance(ai, dict) or ai.get("is_baseline_milestone"):
            continue
        candidates.append(
            {
                "id": str(ai.get("id") or ""),
                "channel": "ai_progress",
                "title": str(ai.get("title") or "").strip(),
                "title_en": ai.get("title_en"),
                "body": str(ai.get("what_it_does") or ""),
                "anchor_iso": ai.get("date"),
                "category": "tech",
                "entity_ids": [str(ai.get("company_id"))] if ai.get("company_id") else [],
                "storyline_id": None,
                "event_id": ai.get("event_id"),
                "source_name": str(ai.get("source_name") or ai.get("company_name") or "AI前沿"),
                "source_url": ai.get("source_url"),
            }
        )

    known_titles = [str(c.get("title") or "") for c in existing_calendar_items]
    known_storylines = {str(c.get("storyline_id")) for c in existing_calendar_items if c.get("storyline_id")}
    known_date_entities = {
        (str(c.get("scheduled_at") or "")[:10], eid)
        for c in existing_calendar_items
        for eid in (c.get("entity_ids") or [])
        if c.get("scheduled_at") and eid
    }

    extracted: List[Dict[str, Any]] = []
    seen_new_titles: List[str] = []

    for cand in candidates:
        title = cand["title"]
        if len(title) < 6:
            continue
        if cand["storyline_id"] and cand["storyline_id"] in known_storylines:
            continue
        combined = f"{title} {cand['body']}"
        if _BREAKING_NOISE_RE.search(combined):
            continue
        if not _BREAKING_ACTION_RE.search(combined):
            continue

        anchor_dt = parse_iso_datetime(str(cand["anchor_iso"] or "")) or generated_dt
        parsed = parse_relative_schedule_datetime(combined, anchor_dt)
        if not parsed:
            continue
        sched_dt, orig_note, is_clock_tbd = parsed
        if sched_dt.date() < generated_dt.date() or (sched_dt.date() - generated_dt.date()).days > 120:
            continue

        if any(title_similarity(title, kt) >= 0.45 for kt in known_titles + seen_new_titles):
            continue
        sched_date = sched_dt.strftime("%Y-%m-%d")
        eids = cand["entity_ids"]
        if any((sched_date, eid) in known_date_entities for eid in eids):
            continue

        # Infer event_type BEFORE choosing watch_variable so domain boilerplate is 100% accurate
        draft = enrich_calendar_item_metadata(
            {
                "calendar_id": f"cal_brk_{cand['channel']}_{cand['id'] or len(extracted)}",
                "title": title,
                "title_en": cand.get("title_en"),
                "scheduled_at": to_iso_shanghai(sched_dt),
                "original_time_note": orig_note,
                "timezone": "Asia/Shanghai",
                "certainty": "reported_tbd",
                "certainty_label": "突发排期预告",
                "is_breaking_schedule": True,
                "source_channel": cand["channel"],
                "is_past": False,
                "is_clock_tbd": is_clock_tbd,
                "category": cand["category"],
                "entity_ids": eids,
                "storyline_id": cand["storyline_id"],
                "event_id": cand["event_id"],
                "pre_expectation": "突发消息/报道排期线索；请等待官方正式日程落地",
                "pre_expectation_en": "Breaking schedule signal from recent news/wire; await official confirmation.",
                "actual_result": None,
                "source_name": cand["source_name"],
                "source_url": cand["source_url"],
            },
            generated_dt,
        )
        wv_zh, wv_en = build_event_type_watch_variable(draft["event_type"], title)
        draft["watch_variable"] = wv_zh
        draft["watch_variable_en"] = wv_en

        extracted.append(draft)
        seen_new_titles.append(title)
        if cand["storyline_id"]:
            known_storylines.add(cand["storyline_id"])
        for eid in eids:
            known_date_entities.add((sched_date, eid))
        if len(extracted) >= 12:
            break

    return extracted


def _infer_event_type(item: Dict[str, Any], blob_low: str) -> str:
    cur = str(item.get("event_type") or "").strip()
    if cur in CALENDAR_EVENT_TYPE_LABELS:
        return cur
    if any(k in blob_low for k in ("fomc", "美联储", "欧洲央行", "ecb", "boe", "英国央行", "boj", "日本央行", "cpi", "非农", "pce", "opec+", "议息", "利率")):
        return "central_bank"
    if any(k in blob_low for k in ("证监会", "沪深北交易所", "沪深交易所", "融资保证金", "稳股市", "减免费用", "人代会", "政协", "两会", "中央经济", "统计局", "pmi", "gdp", "lpr", "外交部", "预算", "政府工作", "两部门", "三部门", "多部门", "部委", "国家数据局", "人社部", "培养计划", "实施方案", "行动计划", "高技能人才", "专项规划", "神舟", "载人飞船", "空间站", "航天工程", "卫星发射", "探月", "火箭发射")):
        return "politics_macro"
    if any(k in blob_low for k in ("apec", "g20", "cop31", "气候大会", "广交会", "高交会", "进博会", "消博会", "文博会", "航展", "达沃斯", "waic", "ces", "mwc", "峰会", "会晤", "博览会")):
        return "expo_summit"
    if any(k in blob_low for k in ("财报", "业绩", "ipo", "上市", "募资", "股东大会", "目标价", "年报", "季报")):
        return "earnings_capital"
    if any(k in blob_low for k in ("发布会", "wwdc", "gtc", "build", "google i/o", "hdc", "fsd", "科技日", "devday", "推出")):
        return "tech_launch"
    cat = str(item.get("category") or "")
    if cat == "finance":
        return "earnings_capital"
    if cat == "tech":
        return "tech_launch"
    return "expo_summit" if "会" in blob_low else "politics_macro"


def _infer_location(item: Dict[str, Any], blob: str) -> Tuple[str, str, str]:
    reg = str(item.get("region") or "").strip()
    country = str(item.get("country") or "").strip()
    city = str(item.get("city") or "").strip()
    low = blob.lower()
    if reg in CALENDAR_REGION_LABELS and country:
        return reg, country, city
    city_rules = [
        ("深圳", "china", "中国", "深圳"),
        ("广州", "china", "中国", "广州"),
        ("上海", "china", "中国", "上海"),
        ("北京", "china", "中国", "北京"),
        ("海南|海口", "china", "中国", "海口"),
        ("珠海", "china", "中国", "珠海"),
        ("酒泉", "china", "中国", "酒泉"),
        ("东莞", "china", "中国", "东莞"),
        ("台北", "china", "中国", "台北"),
        ("香港", "china", "中国", "香港"),
        ("中国|央行|统计局|人大|政协|神舟", "china", "中国", "北京"),
        ("拉斯维加斯|ces", "us", "美国", "拉斯维加斯"),
        ("奥斯汀|tesla|特斯拉", "us", "美国", "奥斯汀"),
        ("硅谷|加州|圣何塞|库比蒂诺|apple|wwdc|gtc|google|nvidia|英伟达", "us", "美国", "加州"),
        ("西雅图|microsoft|微软", "us", "美国", "西雅图"),
        ("纽约|anthropic|纳斯达克|华尔街", "us", "美国", "纽约"),
        ("fomc|美联储|华盛顿|非农|bls|cpi|白宫|特朗普", "us", "美国", "华盛顿"),
        ("达沃斯|davos", "global", "瑞士", "达沃斯"),
        ("巴塞罗那|mwc", "europe_apac", "西班牙", "巴塞罗那"),
        ("安塔利亚|cop31", "global", "土耳其", "安塔利亚"),
        ("法兰克福|ecb|欧洲央行", "europe_apac", "德国", "法兰克福"),
        ("伦敦|英国央行|boe", "europe_apac", "英国", "伦敦"),
        ("东京|日本央行|boj", "europe_apac", "日本", "东京"),
        ("维也纳|opec", "global", "奥地利", "维也纳"),
        ("欧盟|欧洲议会|欧洲", "europe_apac", "欧洲", "布鲁塞尔"),
    ]
    for pat, r_k, c_k, ct_k in city_rules:
        if re.search(pat, low, re.I):
            return r_k, c_k, ct_k
    return "global", "全球", ""


def enrich_calendar_item_metadata(item: Dict[str, Any], generated_dt: datetime) -> Dict[str, Any]:
    """Attach event_type, region, location_display, and countdown_days onto any calendar record."""
    out = dict(item)
    blob = f"{out.get('title') or ''} {out.get('original_time_note') or ''} {out.get('source_name') or ''}"
    et = _infer_event_type(out, blob.lower())
    reg, country, city = _infer_location(out, blob)

    out["event_type"] = et
    out["event_type_label"] = CALENDAR_EVENT_TYPE_LABELS.get(et, "重磅排期")
    out["region"] = reg
    out["region_label"] = CALENDAR_REGION_LABELS.get(reg, "全球")
    out["country"] = country
    out["city"] = city
    out["location_display"] = _loc(country, city)

    s_dt = parse_iso_datetime(str(out.get("scheduled_at") or ""))
    if s_dt is not None:
        delta_days = (s_dt.date() - generated_dt.date()).days
        out["countdown_days"] = delta_days
    else:
        out["countdown_days"] = None
    return out
