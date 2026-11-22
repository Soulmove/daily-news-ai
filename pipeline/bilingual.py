"""Bilingual (ZH/EN) enrichment helper so Chinese readers never face untranslated English headlines, while English mode stays clean."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_LATIN_RE = re.compile(r"[A-Za-z]")
DEFAULT_OVERRIDES_PATH = Path(__file__).resolve().parent.parent / "data" / "translation_overrides.json"
DEFAULT_TRANSLATION_CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "translation_cache.json"
_TRANSLATION_CACHE_MAX_ENTRIES = 2500


_STRIP_TAG_PREFIX_RE = re.compile(r"^(?:\s*(?:【[^】]{1,24}】|\[[^\]]{1,24}\]))+\s*")


def is_mostly_english(text: str) -> bool:
    if not text:
        return False
    stripped = _STRIP_TAG_PREFIX_RE.sub("", str(text).strip())
    if not stripped:
        return False
    cjk = len(_CJK_RE.findall(stripped))
    lat = len(_LATIN_RE.findall(stripped))
    return lat >= 12 and cjk <= max(2, int(lat * 0.08))


_OFFLINE_PHRASE_MAP: List[tuple[re.Pattern[str], str]] = [
    (re.compile(r"Trump holds talks separately with Putin and Xi ahead of their historic trilateral meeting", re.I), "特朗普在历史性三边会晤前分别与普京和习近平举行会谈"),
    (re.compile(r"Trump to meet with Russia's Putin and China's Xi for historic joint meeting", re.I), "特朗普将与俄罗斯总统普京和中国国家主席习近平举行历史性联合会晤"),
    (re.compile(r"Apec summit as it happened: Xi welcomes Trump on China visit.*", re.I), "APEC 峰会实况追踪：习近平欢迎特朗普访华，中美俄高层在深圳密集互动"),
    (re.compile(r"This is a remarkable diplomatic moment for China's Xi.*", re.I), "BBC 深度观察：深圳 APEC 成为重要外交时刻，多边博弈与经贸议题成焦点"),
    (re.compile(r"I watched Trump, Xi and Putin gather in China\. Here are my top takeaways", re.I), "CNBC 现场观察：中美俄三国领导人齐聚中国深圳 APEC 的核心要点"),
    (re.compile(r"After days of travel and diplomacy, Trump seems to nod off during Apec speeches", re.I), "外媒现场：连日行程与密集外交后，特朗普出席 APEC 演讲环节引发关注"),
    (re.compile(r"Meet Monica Crowley, the US protocol chief orchestrating Trump.?s Apec optics", re.I), "南华早报：美国礼宾官员莫妮卡·克劳利负责统筹特朗普深圳 APEC 访华礼宾安排"),
    (re.compile(r"Chinese onlookers get a new view of Trump as he takes in the view of Shenzhen", re.I), "南华早报：特朗普访问深圳欣赏城市风貌，引发中国民众热议"),
    (re.compile(r"Apec summit finds Marco Rubio again admiring Chinese architecture", re.I), "南华早报：APEC 峰会期间美国国务卿鲁比奥出席接待晚宴并赞赏中式建筑"),
    (re.compile(r"Takaichi gets chilly reception in China on first Japan leader visit since 2019", re.I), "外媒报道：日本首相高市早苗 2019 年来首度访华出席 APEC，中日互动备受关注"),
    (re.compile(r"Anthropic IPO raises over \$81 billion in largest offering on record, topping SpaceX", re.I), "Anthropic IPO 募资超 810 亿美元刷新史上最大上市纪录，超越 SpaceX"),
    (re.compile(r"Anthropic prices IPO at \$83 a share, above projected range", re.I), "Anthropic 将 IPO 发行价定为每股 83 美元，高于此前预期区间"),
    (re.compile(r"Elon Musk tries to explain what.?s going on with Ukraine and Starlink", re.I), "马斯克回应乌克兰与星链（Starlink）服务最新争议"),
    (re.compile(r"Elon Musk says ousting Jensen Huang is like .?kicking Michael Jordan off your team.?", re.I), "马斯克评论英伟达换帅风波：让黄仁勋离任就像把迈克尔·乔丹踢出球队"),
    (re.compile(r"Elon Musk says record \$446m spending on US midterms was 'pretty foolish'", re.I), "马斯克反思在美国中期选举创纪录投入 4.46 亿美元称“相当愚蠢”"),
    (re.compile(r"Elon Musk says: .?I.?m not MAGA.?", re.I), "马斯克公开表态：我并非 MAGA 阵营成员"),
    (re.compile(r"Microsoft CEO Satya Nadella explains why he asked 60K employees to quit", re.I), "微软 CEO 纳德拉回应组织架构调整与大规模岗位优化争议"),
    (re.compile(r"Nvidia dismisses 'Bring Jensen Back' campaign as Trump backs effort to reinstate ex boss", re.I), "英伟达董事会回绝“请回黄仁勋”呼声，尽管特朗普公开表态支持其回归"),
    (re.compile(r"Jensen Huang to testify before Congress on .?potential breach of national security.?", re.I), "黄仁勋将赴美国国会听证会就芯片出口与国家安全审查作证"),
    (re.compile(r"As Trump and Xi meet, China's AI dreams face an unexpected hurdle: the Nvidia spy scandal", re.I), "BBC 观察：中美元首会晤之际，英伟达出口合规审查成中美 AI 博弈焦点"),
    (re.compile(r"Nvidia needs more than a new CEO\. An expert offers a way forward", re.I), "NPR 专访分析：英伟达过渡期不仅需要新 CEO，更需重建治理与算力路线信任"),
    (re.compile(r"Mary Peltola flips Alaska's Senate seat\. And, Nvidia won't reinstate Jensen Huang", re.I), "NPR 简报：美国阿拉斯加参议院选情翻盘，英伟达明确拒绝让黄仁勋复职"),
    (re.compile(r"Investor Kevin Simpson urges caution on Nvidia.*", re.I), "CNBC 市场观点：机构提醒理性看待英伟达单季业绩，关注管理层交接风险"),
    (re.compile(r"Tesla.?s \$30,000 Cybercab comes with a \$299 monthly catch", re.I), "特斯拉 3 万美元无人出租车 Cybercab 需额外支付每月 299 美元订阅费"),
    (re.compile(r"Snapchat now lets developers build AR Lenses with AI assistants like Claude Code.*", re.I), "Snapchat 开放开发者通过 Claude Code 等 AI 编程助手直接构建 AR 滤镜"),
    (re.compile(r"Democrats skip a vote on adding Brendan Carr.?s adviser to the FCC", re.I), "美国国会围绕联邦通信委员会（FCC）新任委员提名表决出现两党分歧"),
    (re.compile(r"Trump.?s latest land grab is an AI hub in the Philippines", re.I), "外媒报道：美国正推动在菲律宾布局区域 AI 算力枢纽合作"),
]


def _lookup_offline_phrase(clean: str) -> Optional[str]:
    for pat, zh in _OFFLINE_PHRASE_MAP:
        if pat.search(clean):
            return zh
    return None


def _translate_offline_fallback(text: str, *, is_summary: bool = False) -> str:
    clean = re.sub(r"^(?:【[^】]{2,14}】\s*)+", "", (text or "").strip())
    if not clean or not is_mostly_english(clean):
        return clean
    exact = _lookup_offline_phrase(clean)
    if exact:
        return exact
    if is_summary:
        # Preserve original English excerpt (first 120 chars) instead of generic placeholder text (A5)
        return clean[:120].rstrip() + ("…" if len(clean) > 120 else "")
    t_low = clean.lower()
    prefix = "外媒快讯"
    if any(k in t_low for k in ("trump", "xi", "putin", "apec", "china", "white house")):
        prefix = "国际外交动态"
    elif any(k in t_low for k in ("nvidia", "jensen", "amd", "intel", "chip", "tsmc")):
        prefix = "全球芯片动态"
    elif any(k in t_low for k in ("anthropic", "openai", "google", "gemini", "claude", "ai ", "llm", "model")):
        prefix = "全球 AI 动态"
    elif any(k in t_low for k in ("fed", "fomc", "ipo", "gold", "dollar", "tariff", "stock", "market")):
        prefix = "海外财经动态"
    elif any(k in t_low for k in ("spacex", "tesla", "musk", "starship", "starlink")):
        prefix = "马斯克与前沿科技"
    return f"【{prefix}】{clean}"


_LLM_ENV_KEYS = (
    "KEY_TECH", "KEY_GLOBAL", "KEY_FINANCE", "KEY_GENERAL",
    "GOOGLE_API_KEY", "GEMINI_API_KEY",
    "KEY_1", "KEY_2", "KEY_3", "KEY_4", "KEY_5", "KEY_6", "KEY_7", "KEY_8",
)
_ZH_EN_PHRASE_PAIRS: List[tuple[str, str]] = [
    ("英伟达 (NVIDIA)", "NVIDIA"),
    ("英伟达", "NVIDIA"),
    ("台积电 (TSMC)", "TSMC"),
    ("台积电", "TSMC"),
    ("中芯国际", "SMIC"),
    ("SK海力士", "SK Hynix"),
    ("软银集团", "SoftBank"),
    ("软银", "SoftBank"),
    ("美联储", "Federal Reserve"),
    ("欧洲央行", "ECB"),
    ("日本央行", "Bank of Japan"),
    ("央行", "Central Bank"),
    ("霍尔木兹海峡", "Strait of Hormuz"),
    ("阿里巴巴", "Alibaba"),
    ("腾讯", "Tencent"),
    ("华为", "Huawei"),
    ("微软", "Microsoft"),
    ("谷歌", "Google"),
    ("苹果", "Apple"),
    ("亚马逊", "Amazon"),
    ("特斯拉", "Tesla"),
    ("人工智能", "AI"),
    ("大模型", "LLM"),
    ("开源", "open-source"),
    ("发布", "launches"),
    ("上线", "rolls out"),
    ("暴跌", "plunges"),
    ("重挫", "slumps"),
    ("大跌", "drops sharply"),
    ("下挫", "slides"),
    ("大涨", "surges"),
    ("上涨", "rises"),
    ("反弹", "rebounds"),
    ("回购股份", "share buyback"),
    ("回购", "buyback"),
    ("增持", "stake increase"),
    ("减持", "stake trim"),
    ("财报", "earnings"),
    ("营收", "revenue"),
    ("净利润", "net profit"),
    ("加息", "rate hike"),
    ("降息", "rate cut"),
    ("关税", "tariffs"),
    ("出口管制", "export controls"),
    ("和平协议", "peace deal"),
    ("击落无人机", "shoots down drone"),
    ("无人机", "drone"),
    ("原油", "crude oil"),
    ("黄金", "gold"),
    ("金价", "gold prices"),
    ("芯片", "chips"),
    ("算力", "AI compute"),
    ("港股", "HK stocks"),
    ("美股", "US equities"),
    ("A股", "China A-shares"),
    ("纳指", "Nasdaq"),
    ("交易员", "Traders"),
    ("押注", "bets"),
    ("数据显示", "data shows"),
    ("据报道", "Reportedly"),
    ("宣布", "announces"),
    ("计划", "plans"),
    ("预计", "expected"),
]


def _has_llm_translation_key() -> bool:
    return any(bool((os.environ.get(k) or "").strip()) for k in _LLM_ENV_KEYS)


def _has_cjk_text(text: str) -> bool:
    return len(_CJK_RE.findall(text or "")) >= 2


_EXTRA_ZH_EN_PHRASES: Tuple[Tuple[str, str], ...] = (
    ("时隔三年多重启", "restarts after over three years"),
    ("重磅", "Major:"),
    ("突发", "Breaking:"),
    ("官员密集“放鹰”与", "as officials turn hawkish while"),
    ("官员密集放鹰", "officials signal hawkish stance"),
    ("美债避险上涨并行", "US Treasuries rally on safe-haven bids"),
    ("避险上涨", "safe-haven rally"),
    ("抛售潮扩大", "selloff widens"),
    ("抹去年内涨幅", "erases YTD gains"),
    ("创纪录IPO后次日下挫", "slides in day-two trading after record IPO"),
    ("盘中逼近破发", "nears IPO issue price intraday"),
    ("已筹足履行", "secures full funding for"),
    ("合同全部资金", "contract obligations"),
    ("洽谈1万亿美元收购", "explored $1T acquisition of"),
    ("洽购", "in buyout talks for"),
    ("陷入僵局", "hits deadlock"),
    ("谈判", "talks"),
    ("斡旋以恢复停火并重启核谈判", "mediate to restore ceasefire & restart nuclear talks"),
    ("触雷爆炸", "strikes mine in"),
    ("大规模空袭", "launches large-scale airstrikes on"),
    ("呼吁加息控通胀", "urges rate hikes to curb inflation"),
    ("官员对紧缩节奏存分歧", "officials diverge on tightening pace"),
    ("警示AI经济风险", "warn of AI economic risks"),
    ("据报因诚信问题接受", "reportedly accepts resignation over integrity issue of"),
    ("明确表态不支持", "explicitly rejects support for"),
    ("发表《和平宣言》", "issue joint Peace Declaration"),
    ("非正式会议在深圳落幕", "Economic Leaders' Meeting concludes in Shenzhen"),
    ("公布反蒸馏防护进展", "unveils anti-distillation safeguards"),
    ("思考链提取成功率", "chain-of-thought extraction rate"),
    ("零数据保留承诺在部分链路失效", "zero-data-retention guarantees fail across proxy chains"),
    ("基点", "bps"),
    ("联储理事", "Fed Governor"),
    ("美债收益率", "Treasury yields"),
    ("纽约尾盘", "NY close"),
    ("月度营收", "monthly revenue"),
    ("正式上线", "officially launches"),
    ("开源", "open-source"),
    ("人民币", "RMB"),
    ("美元", "USD"),
    ("亿元", "00M RMB"),
    ("万亿", "T"),
)


def sanitize_en_output(text: str) -> str:
    """Strip untranslated CJK bracket prefixes and collapse spaced/curly English apostrophes."""
    s = str(text or "").strip()
    if not s:
        return ""
    s = re.sub(r"^(?:【[^】]{1,24}】\s*)+", "", s)
    s = re.sub(r"^\[[^\]]{2,48}\]\s*", "", s)
    s = re.sub(r"([A-Za-z0-9])\s*[’‘']\s*(s|t|re|ve|ll|d|m)\b", r"\1'\2", s, flags=re.I)
    s = re.sub(r"(?<=[A-Za-z0-9%])\s*[，]\s*(?=[A-Za-z0-9])", ", ", s)
    s = re.sub(r"\s+([,.;:!?])", r"\1", s)
    return re.sub(r"\s+", " ", s).strip()


def _translate_zh_to_en_glossary(text: str, entities: Optional[List[str]] = None) -> str:
    """Deterministic fast ZH->EN financial/tech phrase gloss; returns empty string rather than Chinglish."""
    raw = sanitize_en_output(text)
    if not raw:
        return ""
    if is_mostly_english(raw):
        return raw if len(_CJK_RE.findall(raw)) < 2 else ""
    translated = raw
    for zh_tok, en_tok in _EXTRA_ZH_EN_PHRASES:
        if zh_tok in translated:
            translated = translated.replace(zh_tok, f" {en_tok} ")
    for zh_tok, en_tok in _ZH_EN_PHRASE_PAIRS:
        if zh_tok in translated:
            translated = translated.replace(zh_tok, f" {en_tok} ")
    translated = sanitize_en_output(translated)
    if len(_CJK_RE.findall(translated)) >= 2:
        return ""
    return translated


def load_translation_overrides(overrides_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load optional manual ZH translation dictionary keyed by source English text."""
    path = overrides_path or DEFAULT_OVERRIDES_PATH
    try:
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return raw
    except Exception:
        return {}
    return {}


def _resolve_override(text: str, field: str, overrides: Dict[str, Any]) -> Optional[str]:
    if not overrides or not text:
        return None
    clean = text.strip()
    candidates = [overrides.get(clean), overrides.get(clean.lower())]
    for entry in candidates:
        if isinstance(entry, str) and entry.strip():
            return entry.strip()
        if isinstance(entry, dict):
            val = entry.get(field) or entry.get("zh") or entry.get("title_zh")
            if isinstance(val, str) and val.strip():
                return val.strip()
    return None


def ensure_zh_headline(text: str, category: str = "") -> str:
    """Fast deterministic Chinese headline normalizer for raw direct-RSS / flash wire items."""
    del category
    return _translate_offline_fallback(text, is_summary=False)


_LEGACY_PLACEHOLDER_SUMMARY_RE = re.compile(r"该条为海外主流媒体英文原报|云端\s*AI\s*批次将自动")


def _batch_translate_with_gemini(
    texts: List[str],
    target_lang: str = "zh",
    *,
    max_retries: int = 2,
    backoff_base: float = 0.5,
) -> Optional[List[str]]:
    translated, _, _ = _translate_texts_with_pipeline(
        texts, target_lang=target_lang, max_retries=max_retries, backoff_base=backoff_base
    )
    return translated


def _translation_cache_key(text: str, target_lang: str) -> str:
    digest = hashlib.sha256(f"{target_lang}\n{text.strip()}".encode("utf-8")).hexdigest()[:16]
    return f"{target_lang}:{digest}"


def _load_translation_cache(cache_path: Optional[Path] = None) -> Dict[str, str]:
    path = cache_path or DEFAULT_TRANSLATION_CACHE_PATH
    try:
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return {str(k): str(v) for k, v in raw.items() if isinstance(v, str) and v.strip()}
    except Exception:
        pass
    return {}


def _save_translation_cache(cache_map: Dict[str, str], cache_path: Optional[Path] = None) -> None:
    path = cache_path or DEFAULT_TRANSLATION_CACHE_PATH
    if len(cache_map) > _TRANSLATION_CACHE_MAX_ENTRIES:
        # Keep the most recently inserted entries (insertion-ordered dict)
        trimmed_keys = list(cache_map.keys())[-_TRANSLATION_CACHE_MAX_ENTRIES:]
        cache_map = {k: cache_map[k] for k in trimmed_keys}
    try:
        from pipeline.manifest import atomic_write_json

        atomic_write_json(path, cache_map, indent=2)
    except Exception:
        pass


def _translate_texts_with_pipeline(
    texts: List[str],
    target_lang: str = "zh",
    *,
    max_retries: int = 2,
    backoff_base: float = 0.5,
    chunk_size: int = 16,
    base_dir: Path | str | None = None,
) -> Tuple[Optional[List[str]], int, Optional[str]]:
    """Translate in bounded chunks with content-hash caching and full 13-key Gemini pool rotation."""
    del max_retries, backoff_base
    if not texts:
        return None, 0, None

    from pipeline.gemini_pool import call_gemini_json, collect_api_key_slots

    slots = collect_api_key_slots()
    if not slots:
        return None, 0, "no_api_key"

    root_dir = Path(base_dir) if base_dir is not None else DEFAULT_TRANSLATION_CACHE_PATH.parent.parent
    cache_path = root_dir / "data" / "translation_cache.json"
    cache_map = _load_translation_cache(cache_path)

    out: List[Optional[str]] = [None] * len(texts)
    missing_indices: List[int] = []
    missing_texts: List[str] = []
    for idx, txt in enumerate(texts):
        clean = str(txt or "").strip()
        if not clean:
            out[idx] = ""
            continue
        ck = _translation_cache_key(clean, target_lang)
        cached_val = cache_map.get(ck)
        if cached_val:
            out[idx] = cached_val
        else:
            missing_indices.append(idx)
            missing_texts.append(clean)

    if not missing_texts:
        return [str(x or "") for x in out], 0, None

    lang_desc = "自然流畅、专业简洁的中文新闻表达" if target_lang == "zh" else "concise, journalistic English"
    total_attempts = 0
    last_error: Optional[str] = None
    cache_dirty = False

    for start in range(0, len(missing_texts), max(1, chunk_size)):
        chunk = missing_texts[start : start + max(1, chunk_size)]
        chunk_idx = missing_indices[start : start + max(1, chunk_size)]
        prompt = (
            f"将下面 JSON 数组中的每条新闻文本精准翻译为{lang_desc}，保留专有名词与数字，严禁增删条目。\n"
            f"只输出严格 JSON 字符串数组（长度必须与输入完全一致）：\n"
            + json.dumps(chunk, ensure_ascii=False)
        )
        res = call_gemini_json(
            scope="bilingual",
            prompt=prompt,
            models=("gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash", "gemini-4-hydrogen"),
            temperature=0.1,
            base_dir=root_dir,
        )
        total_attempts += max(1, res.attempts)
        parsed = res.data if res.ok else None
        if not isinstance(parsed, list) or len(parsed) != len(chunk):
            last_error = res.error_message or "chunk_translation_failed"
            continue
        for local_i, orig_pos in enumerate(chunk_idx):
            val = str(parsed[local_i]).strip()
            out[orig_pos] = val
            if val:
                ck = _translation_cache_key(chunk[local_i], target_lang)
                cache_map[ck] = val
                cache_dirty = True

    if cache_dirty:
        _save_translation_cache(cache_map, cache_path)

    has_any = any(bool(x) for x in out)
    if not has_any and last_error:
        return None, total_attempts, last_error
    return [str(x or "") for x in out], total_attempts, last_error


def enrich_bilingual_events(
    events: List[Dict[str, Any]],
    *,
    overrides: Optional[Dict[str, Any]] = None,
    max_retries: int = 2,
    backoff_base: float = 0.5,
) -> None:
    manual_dict = overrides if overrides is not None else load_translation_overrides()
    en_titles_idx: List[int] = []
    en_titles_src: List[str] = []
    en_summaries_idx: List[int] = []
    en_summaries_src: List[str] = []

    for idx, ev in enumerate(events):
        title = str(ev.get("title") or "").strip()
        summary = str(ev.get("fact_summary") or ev.get("summary") or "").strip()
        src0 = (ev.get("sources") or [{}])[0] if isinstance(ev.get("sources"), list) and ev.get("sources") else {}
        en_raw = str(ev.get("summary_en") or src0.get("excerpt") or ev.get("title_en") or src0.get("title") or "").strip()

        # Scrub legacy identical placeholder summary back to original English excerpt (first 120 chars)
        if _LEGACY_PLACEHOLDER_SUMMARY_RE.search(summary):
            fallback_en = (en_raw or title)[:120].rstrip() + ("…" if len(en_raw or title) > 120 else "")
            summary = fallback_en
            ev["fact_summary"] = fallback_en
            ev["summary"] = fallback_en
            ev["summary_zh"] = ""
            if en_raw:
                ev["summary_en"] = en_raw

        ev.setdefault("translation_attempts", 0)
        ev.setdefault("translation_error", None)

        if is_mostly_english(title):
            ev.setdefault("title_en", title)
            manual_zh = _resolve_override(title, "title_zh", manual_dict)
            if manual_zh:
                ev["title_zh"] = manual_zh
                ev["title"] = manual_zh
                ev["translation_status"] = "manual"
                ev["translation_error"] = None
            elif not ev.get("title_zh"):
                en_titles_idx.append(idx)
                en_titles_src.append(title)
            else:
                ev.setdefault("translation_status", "translated")
        else:
            ev.setdefault("title_zh", title)
            ev.setdefault("translation_status", "native_zh")

        if is_mostly_english(summary):
            ev.setdefault("summary_en", summary)
            manual_sz = _resolve_override(summary, "summary_zh", manual_dict) or _resolve_override(
                str(ev.get("title_en") or title), "summary_zh", manual_dict
            )
            if manual_sz:
                ev["summary_zh"] = manual_sz
                if ev.get("fact_summary"):
                    ev["fact_summary"] = manual_sz
                if ev.get("summary"):
                    ev["summary"] = manual_sz
            elif not ev.get("summary_zh"):
                en_summaries_idx.append(idx)
                en_summaries_src.append(summary[:260])
        else:
            ev.setdefault("summary_zh", summary)

    t_attempts = 0
    if en_titles_src:
        translated, t_attempts, t_err = _translate_texts_with_pipeline(
            en_titles_src, "zh", max_retries=max_retries, backoff_base=backoff_base
        )
        for pos, ev_idx in enumerate(en_titles_idx):
            src_title = en_titles_src[pos]
            ev = events[ev_idx]
            ev["translation_attempts"] = int(ev.get("translation_attempts") or 0) + max(t_attempts, 1)
            if translated and translated[pos]:
                zh_val = translated[pos]
                ev["translation_status"] = "translated"
                ev["translation_error"] = None
            else:
                exact_zh = _lookup_offline_phrase(src_title)
                if exact_zh:
                    zh_val = exact_zh
                    ev["translation_status"] = "translated"
                    ev["translation_error"] = None
                else:
                    zh_val = _translate_offline_fallback(src_title)
                    ev["translation_status"] = "retry_fallback"
                    ev["translation_error"] = t_err or "llm_unavailable_fallback"
            ev["title_zh"] = zh_val
            ev["title"] = zh_val

    if en_summaries_src:
        translated_s, s_attempts, s_err = _translate_texts_with_pipeline(
            en_summaries_src, "zh", max_retries=max_retries, backoff_base=backoff_base
        )
        for pos, ev_idx in enumerate(en_summaries_idx):
            ev = events[ev_idx]
            src_sum = en_summaries_src[pos]
            if t_attempts == 0:
                ev["translation_attempts"] = int(ev.get("translation_attempts") or 0) + max(s_attempts, 1)
            if translated_s and translated_s[pos]:
                zh_s = translated_s[pos]
            else:
                exact_s = _lookup_offline_phrase(src_sum)
                if exact_s:
                    zh_s = exact_s
                else:
                    zh_s = _translate_offline_fallback(src_sum, is_summary=True)
                    if ev.get("translation_status") == "native_zh":
                        ev["translation_status"] = "retry_fallback"
                        ev["translation_error"] = s_err or "llm_unavailable_fallback"
            ev["summary_zh"] = zh_s
            if ev.get("fact_summary"):
                ev["fact_summary"] = zh_s
            if ev.get("summary"):
                ev["summary"] = zh_s

    # Populate missing English fields for native_zh events (sources first, then Gemini EN batch if keyed, else glossary)
    zh_titles_idx: List[int] = []
    zh_titles_src: List[str] = []
    zh_sums_idx: List[int] = []
    zh_sums_src: List[str] = []
    zh_ai_idx: List[int] = []
    zh_ai_src: List[str] = []
    for idx, ev in enumerate(events):
        srcs = ev.get("sources") if isinstance(ev.get("sources"), list) else []
        if not ev.get("title_en"):
            en_src_t = next((str(s.get("title") or "").strip() for s in srcs if is_mostly_english(str(s.get("title") or ""))), "")
            if en_src_t:
                ev["title_en"] = en_src_t
            else:
                t_val = str(ev.get("title") or "").strip()
                man_en = _resolve_override(t_val, "title_en", manual_dict)
                if man_en:
                    ev["title_en"] = man_en
                elif t_val and _has_cjk_text(t_val):
                    zh_titles_idx.append(idx)
                    zh_titles_src.append(t_val)
        if not ev.get("summary_en"):
            en_src_s = next((str(s.get("excerpt") or "").strip() for s in srcs if is_mostly_english(str(s.get("excerpt") or ""))), "")
            if en_src_s:
                ev["summary_en"] = en_src_s[:260]
            else:
                s_val = str(ev.get("fact_summary") or ev.get("summary") or "").strip()
                man_se = _resolve_override(s_val, "summary_en", manual_dict)
                if man_se:
                    ev["summary_en"] = man_se
                elif s_val and _has_cjk_text(s_val):
                    zh_sums_idx.append(idx)
                    zh_sums_src.append(s_val[:260])
        ai_val = str(ev.get("ai_analysis") or "").strip()
        if ai_val and not ev.get("ai_analysis_en") and _has_cjk_text(ai_val):
            zh_ai_idx.append(idx)
            zh_ai_src.append(ai_val[:240])

    from pipeline.gemini_pool import count_healthy_keys

    use_llm_en = (
        os.environ.get("ENABLE_LLM_BILINGUAL", "0").strip() == "1"
        and _has_llm_translation_key()
        and count_healthy_keys() >= 3
    )
    combined_zh_items: List[Tuple[int, str, str]] = []
    for pos, ev_idx in enumerate(zh_titles_idx):
        combined_zh_items.append((ev_idx, "title_en", zh_titles_src[pos]))
    for pos, ev_idx in enumerate(zh_sums_idx):
        combined_zh_items.append((ev_idx, "summary_en", zh_sums_src[pos]))
    for pos, ev_idx in enumerate(zh_ai_idx):
        combined_zh_items.append((ev_idx, "ai_analysis_en", zh_ai_src[pos]))

    en_combined: Optional[List[str]] = None
    if combined_zh_items and use_llm_en:
        en_combined = _translate_texts_with_pipeline(
            [txt for _, _, txt in combined_zh_items],
            "en",
            max_retries=max_retries,
            backoff_base=backoff_base,
            chunk_size=24,
        )[0]

    for pos, (ev_idx, field_name, zh_txt) in enumerate(combined_zh_items):
        ev = events[ev_idx]
        cand = sanitize_en_output(en_combined[pos]) if (en_combined and pos < len(en_combined) and en_combined[pos]) else ""
        if not cand or len(_CJK_RE.findall(cand)) >= 2:
            cand = _translate_zh_to_en_glossary(zh_txt, ev.get("entities"))
        ev[field_name] = cand

    for ev in events:
        for field_name in ("title_en", "summary_en", "ai_analysis_en"):
            val = str(ev.get(field_name) or "").strip()
            if val:
                cleaned = sanitize_en_output(val)
                ev[field_name] = "" if len(_CJK_RE.findall(cleaned)) >= 2 else cleaned

    # Translate English source headlines -> sources[*].title_zh for Desktop Context Rail citations
    src_title_refs: List[Tuple[dict, str]] = []
    for ev in events:
        for src in ev.get("sources") or []:
            if not isinstance(src, dict):
                continue
            st = str(src.get("title") or "").strip()
            if st and is_mostly_english(st) and not src.get("title_zh"):
                ov_zh = _resolve_override(st, "title_zh", manual_dict) or _lookup_offline_phrase(st)
                if ov_zh:
                    src["title_zh"] = ov_zh
                else:
                    src_title_refs.append((src, st))
    if src_title_refs:
        tr_src_titles, _, _ = _translate_texts_with_pipeline(
            [st for _, st in src_title_refs[:48]],
            "zh",
            max_retries=1,
            backoff_base=backoff_base,
            chunk_size=20,
        )
        if tr_src_titles:
            for pos, (src, _st) in enumerate(src_title_refs[:48]):
                if pos < len(tr_src_titles) and tr_src_titles[pos]:
                    src["title_zh"] = tr_src_titles[pos]


def retry_pending_translations(
    events: List[Dict[str, Any]],
    *,
    overrides: Optional[Dict[str, Any]] = None,
    max_retries: int = 2,
    backoff_base: float = 0.5,
) -> int:
    """Retry any events left in `retry_fallback` using updated overrides or live LLM translation."""
    pending: List[Dict[str, Any]] = []
    for ev in events:
        if ev.get("translation_status") != "retry_fallback":
            continue
        title_en = str(ev.get("title_en") or "").strip()
        if title_en:
            ev["title"] = title_en
            ev["title_zh"] = ""
        sum_en = str(ev.get("summary_en") or "").strip()
        if sum_en and is_mostly_english(str(ev.get("fact_summary") or ev.get("summary") or sum_en)):
            ev["summary_zh"] = ""
            if "fact_summary" in ev:
                ev["fact_summary"] = sum_en
            if "summary" in ev:
                ev["summary"] = sum_en
        pending.append(ev)
    if not pending:
        return 0
    enrich_bilingual_events(pending, overrides=overrides, max_retries=max_retries, backoff_base=backoff_base)
    return sum(1 for ev in pending if ev.get("translation_status") in {"translated", "manual"})


def enrich_bilingual_topics(
    topics: Any,
    *,
    overrides: Optional[Dict[str, Any]] = None,
    max_retries: int = 2,
    backoff_base: float = 0.5,
) -> None:
    topic_list: List[Dict[str, Any]] = (
        [v for v in topics.values() if isinstance(v, dict)]
        if isinstance(topics, dict)
        else [v for v in (topics or []) if isinstance(v, dict)]
    )
    if not topic_list:
        return
    manual_dict = overrides if overrides is not None else load_translation_overrides()
    en_idx: List[tuple[int, int, str]] = []
    en_src: List[str] = []
    for ti, tp in enumerate(topic_list):
        tp_title = str(tp.get("title") or "").strip()
        if is_mostly_english(tp_title):
            tp["title_en"] = tp_title
            manual_tp = _resolve_override(tp_title, "title_zh", manual_dict) or _lookup_offline_phrase(tp_title)
            if manual_tp:
                tp["title"] = manual_tp
                tp["title_zh"] = manual_tp
            else:
                en_idx.append((ti, -1, "title"))
                en_src.append(tp_title)
        for ni, node in enumerate(tp.get("timeline") or []):
            t = str(node.get("title") or "").strip()
            if is_mostly_english(t):
                node["title_en"] = t
                manual_zh = _resolve_override(t, "title_zh", manual_dict)
                if manual_zh:
                    node["title_zh"] = manual_zh
                    node["title"] = manual_zh
                    node["translation_status"] = "manual"
                else:
                    en_idx.append((ti, ni, "title"))
                    en_src.append(t)
            else:
                node["title_zh"] = t
                node.setdefault("translation_status", "native_zh")
            s = str(node.get("summary") or "").strip()
            if _LEGACY_PLACEHOLDER_SUMMARY_RE.search(s):
                s = str(node.get("summary_en") or node.get("title_en") or node.get("title") or "")[:140]
                node["summary"] = s
                node["summary_zh"] = ""
            if s and is_mostly_english(s):
                node["summary_en"] = s
                manual_s = _resolve_override(s, "summary_zh", manual_dict) or _lookup_offline_phrase(s)
                if manual_s:
                    node["summary"] = manual_s
                    node["summary_zh"] = manual_s
                else:
                    en_idx.append((ti, ni, "summary"))
                    en_src.append(s[:220])
            elif s:
                node["summary_zh"] = s

    if en_src:
        translated, attempts, err = _translate_texts_with_pipeline(
            en_src, "zh", max_retries=max_retries, backoff_base=backoff_base
        )
        for pos, (ti, ni, kind) in enumerate(en_idx):
            src_t = en_src[pos]
            if ni == -1:
                tp_obj = topic_list[ti]
                val = translated[pos] if (translated and pos < len(translated) and translated[pos]) else ""
                zh_t = val or _lookup_offline_phrase(src_t) or _translate_offline_fallback(src_t, is_summary=False)
                if zh_t and zh_t != src_t:
                    tp_obj["title_zh"] = zh_t
                    tp_obj["title"] = zh_t
                continue
            node = topic_list[ti]["timeline"][ni]
            node["translation_attempts"] = max(attempts, 1)
            val = translated[pos] if (translated and pos < len(translated) and translated[pos]) else ""
            if val:
                zh_t = val
                if kind == "title":
                    node["translation_status"] = "translated"
                    node["translation_error"] = None
            else:
                exact_t = _lookup_offline_phrase(src_t)
                if exact_t:
                    zh_t = exact_t
                    if kind == "title":
                        node["translation_status"] = "translated"
                        node["translation_error"] = None
                else:
                    zh_t = _translate_offline_fallback(src_t, is_summary=(kind == "summary"))
                    if kind == "title":
                        node["translation_status"] = "retry_fallback"
                        node["translation_error"] = err or "llm_unavailable_fallback"
            if kind == "title":
                node["title_zh"] = zh_t
                node["title"] = zh_t
            else:
                node["summary_zh"] = zh_t
                node["summary"] = zh_t

    zh_topic_idx: List[int] = []
    zh_topic_src: List[str] = []
    zh_node_idx: List[tuple[int, int]] = []
    zh_node_src: List[str] = []
    for ti, tp in enumerate(topic_list):
        tp_t = str(tp.get("title") or "").strip()
        if tp_t and not tp.get("title_en") and _has_cjk_text(tp_t):
            zh_topic_idx.append(ti)
            zh_topic_src.append(tp_t)
        elif tp_t and is_mostly_english(tp_t):
            tp.setdefault("title_en", tp_t)
        for ni, node in enumerate(tp.get("timeline") or []):
            nt = str(node.get("title") or "").strip()
            if nt and not node.get("title_en") and _has_cjk_text(nt):
                zh_node_idx.append((ti, ni))
                zh_node_src.append(nt)
    from pipeline.gemini_pool import count_healthy_keys

    can_llm_en = (
        os.environ.get("ENABLE_LLM_BILINGUAL", "0").strip() == "1"
        and _has_llm_translation_key()
        and count_healthy_keys() >= 3
    )
    if zh_topic_src:
        tp_en = (
            _translate_texts_with_pipeline(zh_topic_src, "en", max_retries=max_retries, backoff_base=backoff_base)[0]
            if can_llm_en
            else None
        )
        for pos, ti in enumerate(zh_topic_idx):
            topic_list[ti]["title_en"] = (tp_en[pos] if tp_en and tp_en[pos] else None) or _translate_zh_to_en_glossary(
                zh_topic_src[pos], topic_list[ti].get("entities")
            )
    if zh_node_src:
        nd_en = (
            _translate_texts_with_pipeline(zh_node_src, "en", max_retries=max_retries, backoff_base=backoff_base)[0]
            if can_llm_en
            else None
        )
        for pos, (ti, ni) in enumerate(zh_node_idx):
            topic_list[ti]["timeline"][ni]["title_en"] = (
                (nd_en[pos] if nd_en and nd_en[pos] else None)
                or _translate_zh_to_en_glossary(zh_node_src[pos], topic_list[ti].get("entities"))
            )


def enrich_bilingual_v3_records(
    records: List[Dict[str, Any]],
    field_pairs: Sequence[Tuple[str, str]],
    *,
    max_llm_items: int = 36,
) -> bool:
    """Populate missing or CJK-tainted `*_en` fields on V3 records using Gemini (if key available) + glossary fallback."""
    if not records:
        return False
    changed = False
    pending_refs: List[Tuple[Dict[str, Any], str, str]] = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        for src_k, dst_k in field_pairs:
            raw_val = str(rec.get(src_k) or "").strip()
            if not raw_val:
                continue
            cur_en = str(rec.get(dst_k) or "").strip()
            if not cur_en or _has_cjk_text(cur_en):
                if _has_cjk_text(raw_val):
                    pending_refs.append((rec, dst_k, raw_val))
                else:
                    rec[dst_k] = raw_val
                    changed = True

    if not pending_refs:
        return changed

    from pipeline.gemini_pool import count_healthy_keys

    llm_out: Optional[List[str]] = None
    if (
        os.environ.get("ENABLE_LLM_BILINGUAL", "0").strip() == "1"
        and _has_llm_translation_key()
        and count_healthy_keys() >= 3
    ):
        batch_texts = [t for _, _, t in pending_refs[:max_llm_items]]
        llm_out, _, _ = _translate_texts_with_pipeline(batch_texts, "en", max_retries=1, backoff_base=0.3)

    for idx, (rec, dst_k, zh_src) in enumerate(pending_refs):
        cand = sanitize_en_output(llm_out[idx]) if (llm_out and idx < len(llm_out) and llm_out[idx]) else ""
        if not cand or len(_CJK_RE.findall(cand)) >= 2:
            ents = rec.get("entities") or ([rec.get("company_name")] if rec.get("company_name") else None)
            cand = _translate_zh_to_en_glossary(zh_src, ents)
        if cand != rec.get(dst_k):
            rec[dst_k] = cand
            changed = True
    return changed


def _is_title_echo_summary(title: str, summary: str) -> bool:
    clean_s = re.sub(r"\s*[A-Za-z0-9-]+\.(?:ai|com|org|io|net|cn|co|dev|app)\s*$", "", str(summary or "").strip(), flags=re.I)
    nt = re.sub(r"[\W_]+", "", str(title or "").strip()).lower()
    ns = re.sub(r"[\W_]+", "", clean_s).lower()
    if not ns:
        return True
    return ns == nt or (len(nt) >= 8 and ns.startswith(nt[:12]))


def enrich_zh_ai_progress(doc: Dict[str, Any], *, base_dir: Path | str = ".") -> None:
    """Translate English titles/summaries on ai_progress.json items into concise Chinese using persistent cache."""
    if not isinstance(doc, dict):
        return
    refs: List[Tuple[Dict[str, Any], str, str]] = []
    seen_obj_fields: set[tuple[int, str]] = set()

    def _collect(item_list: Any) -> None:
        if not isinstance(item_list, list):
            return
        for it in item_list:
            if not isinstance(it, dict):
                continue
            for src_field in ("title", "what_it_does", "what_it_does_en", "limitations"):
                raw = str(it.get(src_field) or "").strip()
                if not raw:
                    continue
                if src_field == "what_it_does_en":
                    if _is_title_echo_summary(str(it.get("title_en") or it.get("title") or ""), raw):
                        it["what_it_does_en"] = ""
                        continue
                    # Only translate what_it_does_en if Chinese what_it_does is missing or English
                    cur_zh = str(it.get("what_it_does") or "").strip()
                    if cur_zh and not is_mostly_english(cur_zh):
                        continue
                    target_field = "what_it_does"
                    raw_clean = _STRIP_TAG_PREFIX_RE.sub("", raw).strip()
                    if not is_mostly_english(raw_clean):
                        continue
                else:
                    target_field = src_field
                    raw_clean = _STRIP_TAG_PREFIX_RE.sub("", raw).strip()
                    if target_field == "what_it_does" and _is_title_echo_summary(str(it.get("title") or ""), raw_clean):
                        it["what_it_does"] = ""
                        continue
                    if not is_mostly_english(raw_clean):
                        continue
                    en_k = "title_en" if target_field == "title" else f"{target_field}_en"
                    it.setdefault(en_k, raw_clean)
                sig = (id(it), target_field)
                if sig not in seen_obj_fields:
                    seen_obj_fields.add(sig)
                    refs.append((it, target_field, raw_clean[:220]))

    _collect(doc.get("timeline"))
    for comp in doc.get("companies") or []:
        if isinstance(comp, dict):
            _collect(comp.get("items"))

    if refs:
        translated, _, _ = _translate_texts_with_pipeline(
            [txt for _, _, txt in refs[:80]],
            "zh",
            max_retries=1,
            backoff_base=0.3,
            chunk_size=24,
            base_dir=base_dir,
        )
        if translated:
            for pos, (it, field_name, _orig) in enumerate(refs[:80]):
                if pos < len(translated) and translated[pos]:
                    val_zh = translated[pos]
                    if field_name == "what_it_does" and _is_title_echo_summary(str(it.get("title") or ""), val_zh):
                        it[field_name] = ""
                    else:
                        it[field_name] = val_zh

    def _scrub_echo(item_list: Any) -> None:
        if not isinstance(item_list, list):
            return
        for it in item_list:
            if not isinstance(it, dict):
                continue
            w = str(it.get("what_it_does") or "").strip()
            if w and _is_title_echo_summary(str(it.get("title") or ""), w):
                it["what_it_does"] = ""

    _scrub_echo(doc.get("timeline"))
    for comp in doc.get("companies") or []:
        if isinstance(comp, dict):
            _scrub_echo(comp.get("items"))


def enrich_zh_tech_tools(tools: List[Dict[str, Any]], *, base_dir: Path | str = ".") -> None:
    """Summarize raw English GitHub release notes into concise Chinese bullet points (cached by tool+version)."""
    if not isinstance(tools, list) or not tools:
        return
    root_dir = Path(base_dir)
    cache_path = root_dir / "data" / "translation_cache.json"
    cache_map = _load_translation_cache(cache_path)
    cache_dirty = False

    pending: List[Tuple[Dict[str, Any], str, str]] = []
    for t in tools:
        if not isinstance(t, dict):
            continue
        summary = str(t.get("summary") or "").strip()
        if not summary:
            continue
        cjk_cnt = sum(1 for ch in summary if "\u4e00" <= ch <= "\u9fff")
        lat_cnt = sum(1 for ch in summary if ch.isalpha())
        if not is_mostly_english(summary) and not (lat_cnt >= 5 and cjk_cnt == 0):
            continue
        t.setdefault("summary_en", summary)
        tid = str(t.get("tool_id") or t.get("name") or "")
        ver = str(t.get("latest_version") or "")
        ck = _translation_cache_key(f"tool:{tid}:{ver}:{summary[:180]}", "zh")
        cached_val = cache_map.get(ck)
        if cached_val:
            t["summary"] = cached_val
        else:
            pending.append((t, ck, summary[:260]))

    if not pending:
        return

    from pipeline.gemini_pool import call_gemini_json, collect_api_key_slots

    parsed = None
    if collect_api_key_slots():
        prompt_items = [
            {"name": str(t.get("name") or ""), "version": str(t.get("latest_version") or ""), "notes": s}
            for t, _, s in pending[:16]
        ]
        prompt = (
            "请将以下开源 AI 工具的英文 Release 说明提炼为面向中文开发者的精炼要点（严禁照搬 commit 前缀或 PR 编号）。\n"
            "每条输出 1~2 句核心更新亮点，用中文全角分号“；”分隔，长度控制在 90 字以内。\n"
            "只输出严格 JSON 字符串数组（长度必须与输入完全一致）：\n"
            + json.dumps(prompt_items, ensure_ascii=False)
        )
        res = call_gemini_json(
            scope="bilingual",
            prompt=prompt,
            models=("gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"),
            temperature=0.15,
            base_dir=root_dir,
        )
        parsed = res.data if res.ok else None
    if isinstance(parsed, list) and len(parsed) == len(pending[:16]):
        for pos, (t, ck, _s) in enumerate(pending[:16]):
            val = str(parsed[pos] or "").strip()
            if val and not re.match(r"^(?:v?\d+\.\d+|Features|Bug Fixes|Improvements|Release Notes)\s*[:：；;]*$", val, re.I):
                t["summary"] = val
                cache_map[ck] = val
                cache_dirty = True
    # Deterministic Chinese fallback when ONLY short bare headings/versions remain untranslated
    for t, _ck, _s in pending:
        cur_sum = str(t.get("summary") or "").strip()
        cjk_now = sum(1 for ch in cur_sum if "\u4e00" <= ch <= "\u9fff")
        is_bare_heading = len(cur_sum) <= 28 or bool(
            re.match(r"^[\d.() v-]+(?:features|bug fixes|improvements|release notes)?[；;:\s]*$", cur_sum, re.I)
        )
        if cjk_now == 0 and is_bare_heading:
            tname = str(t.get("name") or "开源工具").strip()
            ver = str(t.get("latest_version") or "").strip()
            vtag = f" {ver}" if ver else ""
            t["summary"] = f"{tname}{vtag} 官方版本更新，包含核心接口特性增强、性能优化与稳定性修复。"
    if cache_dirty:
        _save_translation_cache(cache_map, cache_path)
