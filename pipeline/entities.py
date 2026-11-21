"""Canonical entity registry, alias resolution, ticker/market disambiguation, and domain pilot metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Dict, List, Optional, Sequence


@dataclass(frozen=True)
class TickerRef:
    symbol: str
    market: str
    exchange: str
    currency: str = "USD"

    def to_dict(self) -> Dict[str, str]:
        return {
            "symbol": self.symbol,
            "market": self.market,
            "exchange": self.exchange,
            "currency": self.currency,
            "label": f"{self.symbol}.{self.market} ({self.exchange})",
        }


@dataclass(frozen=True)
class EntityDef:
    entity_id: str
    canonical_name: str
    entity_type: str  # "company" | "industry" | "tech" | "macro"
    sector: str
    aliases: tuple[str, ...]
    tickers: tuple[TickerRef, ...] = ()
    cik: Optional[str] = None
    hkex_code: Optional[str] = None
    cninfo_code: Optional[str] = None
    github_repos: tuple[str, ...] = ()
    hf_orgs: tuple[str, ...] = ()
    required_context: tuple[str, ...] = ()
    operating_variables: tuple[str, ...] = ()
    supply_chain_upstream: tuple[str, ...] = ()
    supply_chain_downstream: tuple[str, ...] = ()
    validation_milestones: tuple[str, ...] = ()
    default_watched: bool = False


ENTITY_REGISTRY: List[EntityDef] = [
    EntityDef(
        entity_id="ent_nvidia",
        canonical_name="英伟达 (NVIDIA)",
        entity_type="company",
        sector="半导体 / AI算力",
        aliases=("英伟达", "nvidia", "nvda", "黄仁勋", "jensen huang", "blackwell", "rubin", "cuda"),
        tickers=(TickerRef("NVDA", "US", "NASDAQ", "USD"),),
        cik="0001045810",
        operating_variables=("数据中心营收季度环比", "Blackwell/Rubin 晶圆与机柜出货节奏", "毛利率指南 vs 实际", "高带宽内存 HBM 采购成本"),
        supply_chain_upstream=("台积电 (TSM.US)", "SK海力士 / 美光 (HBM)", "ASML 先进光刻"),
        supply_chain_downstream=("微软 (MSFT.US)", "谷歌 (GOOGL.US)", "Meta (META.US)", "xAI / OpenAI"),
        validation_milestones=("SEC 10-Q/8-K 官方披露", "季度数据中心营收与下季指引", "CUDA/TensorRT 生态发布"),
        default_watched=True,
    ),
    EntityDef(
        entity_id="ent_memory_chips",
        canonical_name="存储芯片 (DRAM / HBM / NAND)",
        entity_type="industry",
        sector="半导体",
        aliases=("存储芯片", "dram", "nand", "hbm", "hbm4", "hbm3e", "高带宽内存", "内存价格", "美光", "micron", "sk海力士", "sk hynix"),
        tickers=(TickerRef("MU", "US", "NASDAQ", "USD"),),
        cik="0000723125",
        operating_variables=("DRAM 合约价季度涨跌幅", "NAND Flash 现货/合约价格分化", "HBM 产能利用率与良率", "晶圆资本开支 (CapEx)"),
        supply_chain_upstream=("ASML 光刻机", "半导体硅片与特种气体"),
        supply_chain_downstream=("英伟达 GPU 模组", "AI 服务器", "消费级 PC/手机 OEM"),
        validation_milestones=("美光季报库存天数与毛利率", "TrendForce/官方季报价格口径核对"),
        default_watched=True,
    ),
    EntityDef(
        entity_id="ent_tsmc",
        canonical_name="台积电 (TSMC)",
        entity_type="company",
        sector="半导体代工",
        aliases=("台积电", "tsmc", "cowos", "2nm", "3nm"),
        tickers=(
            TickerRef("TSM", "US", "NYSE", "USD"),
            TickerRef("2330", "TW", "TWSE", "TWD"),
        ),
        cik="0001046179",
        operating_variables=("CoWoS 先进封装月产能", "3nm/2nm 营收占比", "月度/季度营收及出口管制影响"),
        supply_chain_upstream=("ASML EUV", "光刻胶与晶圆材料"),
        supply_chain_downstream=("英伟达", "苹果", "AMD", "博通"),
        validation_milestones=("月度营收公告", "季度法说会资本开支指引"),
        default_watched=True,
    ),
    EntityDef(
        entity_id="ent_amd",
        canonical_name="AMD (超威半导体)",
        entity_type="company",
        sector="半导体 / AI算力",
        aliases=("amd", "超威半导体", "mi300", "mi325", "mi350", "rocm", "苏姿丰"),
        tickers=(TickerRef("AMD", "US", "NASDAQ", "USD"),),
        cik="0000002488",
        operating_variables=("Data Center GPU 年度销售目标", "ROCm 生态采纳", "服务器 CPU 市占率"),
        supply_chain_upstream=("台积电", "三星/海力士 HBM"),
        supply_chain_downstream=("微软 Azure", "Meta", "Oracle"),
        validation_milestones=("SEC 10-Q/8-K 季报", "ROCm GitHub Release"),
    ),
    EntityDef(
        entity_id="ent_intel",
        canonical_name="英特尔 (Intel)",
        entity_type="company",
        sector="半导体",
        aliases=("英特尔", "intel", "18a", "intc"),
        tickers=(TickerRef("INTC", "US", "NASDAQ", "USD"),),
        cik="0000050863",
        operating_variables=("Intel Foundry 代工亏损收敛", "18A 制程良率与外部客户", "PC/数据中心市占"),
        validation_milestones=("SEC 8-K/10-Q 官方披露",),
    ),
    EntityDef(
        entity_id="ent_smic",
        canonical_name="中芯国际 (SMIC)",
        entity_type="company",
        sector="半导体代工",
        aliases=("中芯国际", "smic", "00981", "688981"),
        tickers=(
            TickerRef("00981", "HK", "HKEX", "HKD"),
            TickerRef("688981", "SH", "SSE科创板", "CNY"),
        ),
        hkex_code="00981",
        cninfo_code="688981",
        operating_variables=("晶圆出货量与产能利用率", "12英寸产线扩产资本开支", "平均售价 ASP 变动"),
        validation_milestones=("港交所披露易季度业绩", "上交所/巨潮公告"),
    ),
    EntityDef(
        entity_id="ent_cambricon",
        canonical_name="寒武纪 (Cambricon)",
        entity_type="company",
        sector="半导体 / 国产AI芯片",
        aliases=("寒武纪", "cambricon", "688256", "思元"),
        tickers=(TickerRef("688256", "SH", "SSE科创板", "CNY"),),
        cninfo_code="688256",
        operating_variables=("存货与预付款项变动（反映流片备货）", "单季营收与应收账款回收"),
        validation_milestones=("巨潮资讯/上交所季报与公告",),
    ),
    EntityDef(
        entity_id="ent_qwen_alibaba",
        canonical_name="阿里巴巴 / 通义千问 (Qwen)",
        entity_type="tech",
        sector="AI 模型与云平台",
        aliases=("qwen", "qwen3", "qwen4", "通义千问", "阿里云", "alibaba", "阿里巴巴", "阿里芯片"),
        tickers=(
            TickerRef("09988", "HK", "HKEX", "HKD"),
            TickerRef("BABA", "US", "NYSE", "USD"),
        ),
        hkex_code="09988",
        github_repos=("QwenLM/Qwen3",),
        hf_orgs=("Qwen",),
        operating_variables=("Qwen 开源模型权重许可与下载活跃度", "阿里云 AI 相关收入增速", "平头哥芯片独立资本化进展"),
        validation_milestones=("Hugging Face Qwen 仓库更新", "港交所 09988 公告与季度财报"),
        default_watched=True,
    ),
    EntityDef(
        entity_id="ent_deepseek",
        canonical_name="DeepSeek (深度求索)",
        entity_type="tech",
        sector="AI 模型与开源推理",
        aliases=("deepseek", "深度求索", "deepseek-r1", "deepseek-v3", "deepseek-v4"),
        github_repos=("deepseek-ai/DeepSeek-V3",),
        hf_orgs=("deepseek-ai",),
        operating_variables=("模型权重开源许可与推理成本定价", "API 吞吐与上下文限制变更", "官方仓库与arXiv技术报告"),
        validation_milestones=("Hugging Face deepseek-ai 模型卡", "arXiv 技术论文更新"),
        default_watched=True,
    ),
    EntityDef(
        entity_id="ent_openai",
        canonical_name="OpenAI",
        entity_type="company",
        sector="AI 模型与应用",
        aliases=("openai", "chatgpt", "gpt-5", "gpt-4", "sora", "o3", "o4"),
        operating_variables=("模型发布状态 (宣布/候补/GA)", "API 定价与企业席位营收", "与微软云算力合约及监管合规"),
        validation_milestones=("OpenAI 官方发布日志", "API 文档与状态页"),
        default_watched=True,
    ),
    EntityDef(
        entity_id="ent_anthropic",
        canonical_name="Anthropic / Claude",
        entity_type="company",
        sector="AI 模型与安全",
        aliases=("anthropic", "claude"),
        operating_variables=("Claude 模型能力与企业 API 份额", "融资/上市监管文件与亚马逊/谷歌云合作"),
        validation_milestones=("Anthropic 官方公告 / S-1 注册文件",),
    ),
    EntityDef(
        entity_id="ent_google",
        canonical_name="Google / DeepMind / Gemini",
        entity_type="company",
        sector="AI 模型与云基础设施",
        aliases=("google", "谷歌", "gemini", "deepmind", "tpu", "project zero", "alphabet"),
        tickers=(TickerRef("GOOGL", "US", "NASDAQ", "USD"),),
        cik="0001652044",
        hf_orgs=("google",),
        operating_variables=("Gemini 模型调用量与产品集成", "Google Cloud 运营利润率", "TPU 资本开支"),
        validation_milestones=("SEC 10-Q/8-K", "Hugging Face google 模型卡"),
    ),
    EntityDef(
        entity_id="ent_microsoft",
        canonical_name="微软 (Microsoft)",
        entity_type="company",
        sector="云基础设施 / AI算力需求方",
        aliases=("微软", "microsoft", "azure", "copilot", "msft"),
        tickers=(TickerRef("MSFT", "US", "NASDAQ", "USD"),),
        cik="0000789019",
        operating_variables=("Azure 云增速中 AI 贡献占比", "资本开支 (CapEx) 季度变化"),
        validation_milestones=("SEC 10-Q/10-K 季报",),
    ),
    EntityDef(
        entity_id="ent_huawei",
        canonical_name="华为 / 盘古 / 昇腾",
        entity_type="company",
        sector="AI 模型与算力底座",
        aliases=("华为", "盘古", "openpangu", "pangu", "昇腾", "ascend", "鸿蒙"),
        operating_variables=("开源盘古与 Agent 生态采纳", "昇腾算力集群交付与编译器生态"),
        validation_milestones=("华为云官方开发者发布页",),
    ),
    EntityDef(
        entity_id="ent_tencent",
        canonical_name="腾讯 (Tencent)",
        entity_type="company",
        sector="互联网 / AI模型与应用",
        aliases=("腾讯", "tencent", "混元", "hunyuan", "00700", "微信小程序", "微信生态", "微信支付"),
        tickers=(TickerRef("00700", "HK", "HKEX", "HKD"),),
        hkex_code="00700",
        operating_variables=("云与企业服务AI增量", "资本开支与回购节奏", "游戏/广告基本盘"),
        validation_milestones=("港交所 00700 公告与季报",),
    ),
    EntityDef(
        entity_id="ent_meituan",
        canonical_name="美团 (Meituan / LongCat)",
        entity_type="company",
        sector="本地生活 / AI大模型",
        aliases=("美团", "meituan", "longcat", "03690"),
        tickers=(TickerRef("03690", "HK", "HKEX", "HKD"),),
        hkex_code="03690",
        operating_variables=("开源大模型 LongCat 生态与权重可用性", "核心本地商业经营利润"),
        validation_milestones=("港交所 03690 公告", "模型开源仓库发布"),
    ),
    EntityDef(
        entity_id="ent_apple",
        canonical_name="苹果 (Apple)",
        entity_type="company",
        sector="消费电子与端侧AI",
        aliases=("apple", "苹果公司", "iphone", "macbook", "ios", "aapl", "apple intelligence"),
        tickers=(TickerRef("AAPL", "US", "NASDAQ", "USD"),),
        cik="0000320193",
        required_context=("apple", "iphone", "macbook", "ios", "ipad", "aapl", "库克", "市值", "股价", "苹果公司", "端侧", "芯片"),
        operating_variables=("端侧 AI 换机周期", "大中华区出货量", "自研芯片/NPU进展"),
        validation_milestones=("SEC 10-Q/10-K", "苹果开发者文档与发布"),
    ),
    EntityDef(
        entity_id="ent_ai_infra_tools",
        canonical_name="AI 推理与框架生态 (vLLM / llama.cpp / Transformers)",
        entity_type="tech",
        sector="AI 开源基础设施",
        aliases=("vllm", "llama.cpp", "transformers", "pytorch", "sglang", "ai agent", "coding agent", "agentic", "智能体", "mcp"),
        github_repos=(
            "vllm-project/vllm",
            "ggml-org/llama.cpp",
            "huggingface/transformers",
            "pytorch/pytorch",
            "sgl-project/sglang",
        ),
        operating_variables=("版本更新与新硬件架构支持 (Blackwell/FP8/ROCm)", "吞吐优化与依赖兼容变动"),
        validation_milestones=("GitHub Releases 官方版本说明",),
        default_watched=True,
    ),
    EntityDef(
        entity_id="ent_macro_fomc",
        canonical_name="美联储 FOMC 与全球流动性",
        entity_type="macro",
        sector="宏观利率与汇率",
        aliases=("美联储", "fomc", "fed", "降息", "加息", "鲍威尔", "美元指数", "美元汇率", "美元流动性", "美元走强", "美元走弱", "强美元", "联邦储备", "准备金率", "cpi"),
        operating_variables=("联邦基金目标利率区间", "点阵图与资产负债表缩表节奏", "美债长端收益率与美元指数"),
        validation_milestones=("Federal Reserve 官方 FOMC 声明与日历",),
        default_watched=True,
    ),
    EntityDef(
        entity_id="ent_us_china_diplomacy",
        canonical_name="中美外交与元首峰会",
        entity_type="macro",
        sector="国际关系与地缘宏观",
        aliases=("特朗普", "川普", "trump", "习近平", "白宫", "外交部", "中美", "中美元首", "中美俄", "访华", "鲁比奥", "贝森特"),
        required_context=("中国", "中方", "中美", "习近平", "访华", "来华", "深圳", "北京", "apec", "china", "beijing", "shenzhen", "xi", "双边", "三边", "峰会", "对华", "关税"),
        operating_variables=("中美元首双边/多边会晤成果", "双边经贸关税与科技治理共识", "地缘政治风险溢价"),
        validation_milestones=("中美官方联合声明 / 外交部与白宫新闻发布会",),
        default_watched=True,
    ),
    EntityDef(
        entity_id="ent_apec_g20_summits",
        canonical_name="APEC / 重大国际峰会与经贸协定",
        entity_type="macro",
        sector="全球治理与多边经贸",
        aliases=("apec", "亚太经合组织", "深圳峰会", "领导人非正式会议", "三边会晤", "g20", "g7", "达沃斯", "自贸协定", "联合公报"),
        operating_variables=("多边经贸协定与关税削减落地", "亚太供应链与AI安全治理框架"),
        validation_milestones=("峰会东道主宣言与双边经贸协议原文",),
        default_watched=True,
    ),
    EntityDef(
        entity_id="ent_tariffs_trade",
        canonical_name="全球关税、制裁与出口管制",
        entity_type="macro",
        sector="贸易政策与供应链安全",
        aliases=("关税", "tariff", "出口管制", "实体清单", "芯片禁令", "制裁", "贸易战", "碳关税", "稀土"),
        operating_variables=("美欧对华关税税率与豁免清单", "高端芯片/光刻设备出口限制边界"),
        validation_milestones=("美国商务部 BIS / USTR 与中方商务部正式公告",),
    ),
    EntityDef(
        entity_id="ent_spacex_tesla",
        canonical_name="SpaceX / 特斯拉 / 马斯克生态",
        entity_type="company",
        sector="商业航天、自动驾驶与 AI",
        aliases=("spacex", "星舰", "starship", "筷子夹", "马斯克", "musk", "特斯拉", "tesla", "optimus", "grok", "xai", "starlink", "星链"),
        tickers=(TickerRef("TSLA", "US", "NASDAQ", "USD"),),
        cik="0001318605",
        operating_variables=("星舰可复用回收里程碑与发射频次", "Tesla 汽车毛利率、FSD 与 Optimus 进展", "xAI / Grok 算力集群与商业化"),
        validation_milestones=("SpaceX 官方试飞直播与 FAA 许可", "Tesla SEC 10-Q/10-K 与交付数据"),
        default_watched=True,
    ),
    EntityDef(
        entity_id="ent_xai",
        canonical_name="xAI / Grok",
        entity_type="company",
        sector="AI 模型与算力",
        aliases=("xai", "x.ai", "grok", "grok-3", "grok-4", "grok 4", "colossus"),
        github_repos=("xai-org/grok-1",),
        hf_orgs=("xai-org",),
        operating_variables=("Grok 模型能力迭代与 API 调用规模", "Colossus 超算集群扩展节奏"),
        validation_milestones=("xAI 官方博客与 Hugging Face xai-org 更新",),
        default_watched=True,
    ),
    EntityDef(
        entity_id="ent_bytedance",
        canonical_name="字节跳动 / 豆包 (Seed)",
        entity_type="tech",
        sector="AI 模型与应用",
        aliases=("豆包", "doubao", "seedance", "seed-", "bytedance", "字节跳动", "火山引擎"),
        hf_orgs=("ByteDance-Seed", "ByteDance"),
        operating_variables=("豆包日活与多模态视频模型商用规模", "火山引擎大模型推理调用量"),
        validation_milestones=("ByteDance Seed 官方技术报告与 Hugging Face 更新",),
    ),
    EntityDef(
        entity_id="ent_zhipu",
        canonical_name="智谱 AI (GLM)",
        entity_type="tech",
        sector="AI 模型与开源推理",
        aliases=("智谱", "zhipu", "glm-4", "glm-5", "chatglm", "bigmodel"),
        hf_orgs=("THUDM", "zai-org"),
        operating_variables=("GLM 系列开源与 API 企业落地进展",),
        validation_milestones=("Zhipu / Z.ai 官方模型卡发布",),
    ),
    EntityDef(
        entity_id="ent_oracle",
        canonical_name="甲骨文 (Oracle)",
        entity_type="company",
        sector="云基础设施 / 数据库",
        aliases=("甲骨文", "oracle", "orcl", "oci"),
        tickers=(TickerRef("ORCL", "US", "NYSE", "USD"),),
        cik="0001341439",
        operating_variables=("OCI 云基础设施积压订单 (RPO) 增速", "企业数据库云化迁移利润率"),
        validation_milestones=("SEC 10-Q/10-K 季报披露",),
    ),
    EntityDef(
        entity_id="ent_geopolitics_energy",
        canonical_name="地缘冲突、能源与大宗商品",
        entity_type="macro",
        sector="能源安全与避险资产",
        aliases=("普京", "俄乌", "泽连斯基", "伊朗", "以色列", "中东", "霍尔木兹", "原油", "opec", "现货黄金", "金价", "台海"),
        operating_variables=("布伦特/WTI 原油供给中断风险", "黄金避险买盘与主权风险溢价"),
        validation_milestones=("各方官方停火/谈判声明与 OPEC+ 产量决议",),
    ),
]

ENTITY_BY_ID: Dict[str, EntityDef] = {e.entity_id: e for e in ENTITY_REGISTRY}


_NEGATED_MENTION_PREFIX_RE = re.compile(
    r"(?:未用|未使用|不用|无需|不依赖|脱钩|摆脱|绕开|非|without|no)\s*$",
    re.I,
)


def _find_alias_pos(text_lower: str, alias: str, *, allow_negated: bool = False) -> Optional[int]:
    a = alias.lower().strip()
    if not a:
        return None
    if a.isascii():
        # Word boundary match for short ASCII aliases (e.g. 'ai', 'mu', 'fed', 'amd') to prevent false substrings
        pat = re.compile(rf"(?<![a-z0-9]){re.escape(a)}(?![a-z0-9])")
        for m in pat.finditer(text_lower):
            if not allow_negated and _NEGATED_MENTION_PREFIX_RE.search(text_lower[max(0, m.start() - 12) : m.start()]):
                continue
            return m.start()
        return None
    idx = text_lower.find(a)
    while idx != -1:
        before_char = text_lower[idx - 1 : idx] if idx > 0 else ""
        after_char = text_lower[idx + len(a) : idx + len(a) + 1]
        if a == "美元":
            # Never treat numeric amounts like "1万亿美元" / "3600美元" or "美元首" as USD/Fed entity!
            if after_char in ("首", "左", "以") or (before_char and (before_char.isdigit() or before_char in ("万", "亿", "千", "百", "多", "余", "约", "逾", "超", "近", "破"))):
                idx = text_lower.find(a, idx + len(a))
                continue
            win = text_lower[max(0, idx - 6) : min(len(text_lower), idx + 12)]
            if not any(k in win for k in ("美元指数", "美元汇率", "强美元", "弱美元", "美元兑", "美元贬", "美元涨", "美元走")):
                idx = text_lower.find(a, idx + len(a))
                continue
        if a == "黄金":
            if after_char in ("周", "时", "段", "期"):
                idx = text_lower.find(a, idx + len(a))
                continue
        if a == "中美" and after_char == "洲":
            idx = text_lower.find(a, idx + len(a))
            continue
        if allow_negated or not _NEGATED_MENTION_PREFIX_RE.search(text_lower[max(0, idx - 10) : idx]):
            return idx
        idx = text_lower.find(a, idx + len(a))
    return None


def _match_alias(text_lower: str, alias: str) -> bool:
    return _find_alias_pos(text_lower, alias, allow_negated=False) is not None


ENTITY_CONFIDENCE_THRESHOLD = 0.65


def _score_entity_confidence(edef: EntityDef, hit_aliases: Sequence[str], earliest_pos: int) -> float:
    """Compute deterministic [0, 0.99] confidence for a matched entity mention."""
    hit_set = {a.lower() for a in hit_aliases if a}
    score = 0.58
    if earliest_pos < 80:
        score += 0.18
    elif earliest_pos < 130:
        score += 0.08

    if edef.canonical_name.lower() in hit_set:
        score += 0.16

    has_cjk_2 = any(bool(re.search(r"[\u4e00-\u9fff]", a)) and len(a) >= 2 for a in hit_aliases)
    max_len = max((len(a) for a in hit_aliases), default=0)
    if has_cjk_2 or max_len >= 4:
        score += 0.10 if earliest_pos < 130 else 0.05
    elif max_len <= 3 and len(hit_set) <= 1:
        score -= 0.08

    if len(hit_set) >= 2:
        score += 0.10
    if edef.required_context:
        score += 0.06
    return round(max(0.0, min(0.99, score)), 2)


def match_entities_with_reasons(
    text: str,
    explicit_entities: Optional[Sequence[str]] = None,
    min_confidence: float = ENTITY_CONFIDENCE_THRESHOLD,
) -> List[Dict[str, Any]]:
    """
    Resolve canonical entities referenced in an event or text with explicit explanation strings.
    Enforces disambiguation rules (e.g. '苹果' fruit vs 'Apple', '未用 Nvidia' excluded as primary subject).
    """
    combined = " ".join([text or "", *(explicit_entities or [])])
    lowered = combined.lower()
    scored_matches: List[tuple[int, Dict[str, Any]]] = []

    for edef in ENTITY_REGISTRY:
        if edef.required_context and not any(_find_alias_pos(lowered, ctx, allow_negated=True) is not None for ctx in edef.required_context):
            continue
        hit_positions = []
        for al in edef.aliases:
            pos = _find_alias_pos(lowered, al, allow_negated=False)
            if pos is not None:
                hit_positions.append((pos, al))
        if hit_positions:
            hit_positions.sort(key=lambda x: x[0])
            earliest_pos = hit_positions[0][0]
            hit_aliases = [al for _, al in hit_positions]
            scored_matches.append(
                (
                    earliest_pos,
                    {
                        "entity_id": edef.entity_id,
                        "canonical_name": edef.canonical_name,
                        "entity_type": edef.entity_type,
                        "sector": edef.sector,
                        "matched_aliases": hit_aliases[:3],
                        "tickers": [t.to_dict() for t in edef.tickers],
                        "reason": f"正文/实体匹配关键词「{' / '.join(hit_aliases[:2])}」",
                    },
                )
            )
    scored_matches.sort(key=lambda x: x[0])
    registry_by_id = {ed.entity_id: ed for ed in ENTITY_REGISTRY}
    filtered: List[Dict[str, Any]] = []
    for earliest_pos, m in scored_matches:
        edef = registry_by_id.get(m["entity_id"])
        if edef is None:
            continue
        hit_aliases = [al for al in edef.aliases if _find_alias_pos(lowered, al, allow_negated=False) is not None]
        conf = _score_entity_confidence(edef, hit_aliases, earliest_pos)
        if conf < min_confidence:
            continue
        enriched = dict(m)
        enriched["confidence"] = conf
        filtered.append(enriched)
    return filtered


def build_entities_index_base() -> Dict[str, Dict[str, Any]]:
    """Build initial canonical entity index skeleton before enriching with events & first-party data."""
    out: Dict[str, Dict[str, Any]] = {}
    for edef in ENTITY_REGISTRY:
        out[edef.entity_id] = {
            "entity_id": edef.entity_id,
            "canonical_name": edef.canonical_name,
            "entity_type": edef.entity_type,
            "sector": edef.sector,
            "aliases": list(edef.aliases),
            "tickers": [t.to_dict() for t in edef.tickers],
            "cik": edef.cik,
            "hkex_code": edef.hkex_code,
            "cninfo_code": edef.cninfo_code,
            "github_repos": list(edef.github_repos),
            "hf_orgs": list(edef.hf_orgs),
            "operating_variables": list(edef.operating_variables),
            "supply_chain_upstream": list(edef.supply_chain_upstream),
            "supply_chain_downstream": list(edef.supply_chain_downstream),
            "validation_milestones": list(edef.validation_milestones),
            "default_watched": edef.default_watched,
            "financial_actuals": [],
            "recent_filings": [],
            "model_updates": [],
            "recent_events": [],
            "change_count_30d": 0,
            "last_event_at": None,
        }
    return out
