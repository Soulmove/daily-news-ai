"""Bilingual (ZH/EN) enrichment helper so Chinese readers never face untranslated English headlines, while English mode stays clean."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional, Tuple

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_LATIN_RE = re.compile(r"[A-Za-z]")
DEFAULT_OVERRIDES_PATH = Path(__file__).resolve().parent.parent / "data" / "translation_overrides.json"


def is_mostly_english(text: str) -> bool:
    if not text:
        return False
    cjk = len(_CJK_RE.findall(text))
    lat = len(_LATIN_RE.findall(text))
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


_LLM_ENV_KEYS = ("KEY_GLOBAL", "KEY_1", "KEY_2", "KEY_3", "KEY_4", "KEY_5", "KEY_6", "KEY_7", "KEY_8", "GEMINI_API_KEY")
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


def _translate_zh_to_en_glossary(text: str, entities: Optional[List[str]] = None) -> str:
    """Deterministic fast ZH->EN financial/tech phrase gloss when LLM translation is unavailable."""
    raw = re.sub(r"^(?:【[^】]{2,18}】\s*)+", "", str(text or "").strip())
    if not raw:
        return ""
    if is_mostly_english(raw):
        return raw
    translated = raw
    for zh_tok, en_tok in _EXTRA_ZH_EN_PHRASES:
        if zh_tok in translated:
            translated = translated.replace(zh_tok, f" {en_tok} ")
    for zh_tok, en_tok in _ZH_EN_PHRASE_PAIRS:
        if zh_tok in translated:
            translated = translated.replace(zh_tok, f" {en_tok} ")
    translated = re.sub(r"\s+", " ", translated).strip()
    nums = re.findall(r"\d+(?:\.\d+)?%?", raw)
    if entities and len(_CJK_RE.findall(translated)) > len(_LATIN_RE.findall(translated)):
        ent_en_map = {
            "英伟达 (NVIDIA)": "NVIDIA",
            "美联储 FOMC 与全球流动性": "Federal Reserve",
            "台积电 (TSMC)": "TSMC",
            "中芯国际 (SMIC)": "SMIC",
            "阿里巴巴 / 通义千问 (Qwen)": "Alibaba Qwen",
            "腾讯混元 (Hunyuan)": "Tencent Hunyuan",
            "中美外交与元首峰会 / APEC": "US-China APEC",
            "黄金 (Gold / 避险金属)": "Gold",
            "原油 (Crude Oil / Brent / WTI)": "Crude Oil",
        }
        clean_ents = []
        for e in entities[:2]:
            es = str(e or "").strip()
            mapped = ent_en_map.get(es)
            if not mapped:
                ascii_m = re.findall(r"[A-Za-z0-9.\-/]{2,}", es)
                mapped = " ".join(ascii_m) if ascii_m else ""
            if mapped:
                clean_ents.append(mapped)
        if clean_ents:
            ent_tag = ", ".join(clean_ents)
            if nums:
                return f"[{ent_tag} · {' / '.join(nums[:3])}] {translated}"
            return f"[{ent_tag}] {translated}"
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


def _translate_texts_with_pipeline(
    texts: List[str],
    target_lang: str = "zh",
    *,
    max_retries: int = 2,
    backoff_base: float = 0.5,
    chunk_size: int = 12,
) -> Tuple[Optional[List[str]], int, Optional[str]]:
    """Translate in bounded chunks with exponential backoff retries across Gemini keys/models."""
    key_names = (
        "KEY_GLOBAL", "KEY_1", "KEY_2", "KEY_3", "KEY_4", "KEY_5", "KEY_6", "KEY_7", "KEY_8",
        "GOOGLE_API_KEY", "KEY_TECH", "KEY_FINANCE", "KEY_GENERAL",
    )
    keys: List[str] = []
    for kn in key_names:
        v = (os.environ.get(kn) or "").strip()
        if v and v not in keys:
            keys.append(v)
    if not keys or not texts:
        return None, 0, "no_api_key" if texts and not keys else None
    try:
        from google import genai
        from google.genai import types
    except Exception as exc:
        return None, 0, type(exc).__name__

    lang_desc = "自然流畅、专业简洁的中文新闻表达" if target_lang == "zh" else "concise, journalistic English"
    all_out: List[str] = []
    total_attempts = 0
    last_error: Optional[str] = None

    for start in range(0, len(texts), max(1, chunk_size)):
        chunk = texts[start : start + max(1, chunk_size)]
        prompt = (
            f"将下面 JSON 数组中的每条新闻文本精准翻译为{lang_desc}，保留专有名词与数字，严禁增删条目。\n"
            f"只输出严格 JSON 字符串数组（长度必须与输入完全一致）：\n"
            + json.dumps(chunk, ensure_ascii=False)
        )
        chunk_result: Optional[List[str]] = None
        for attempt in range(max_retries + 1):
            total_attempts += 1
            for api_key in keys[:5]:
                client = genai.Client(api_key=api_key)
                for model_name in ("gemini-4-hydrogen", "gemini-2.5-flash"):
                    try:
                        resp = client.models.generate_content(
                            model=model_name,
                            contents=prompt,
                            config=types.GenerateContentConfig(temperature=0.1, response_mime_type="application/json"),
                        )
                        parsed = json.loads(resp.text or "[]")
                        if isinstance(parsed, list) and len(parsed) == len(chunk):
                            chunk_result = [str(x).strip() for x in parsed]
                            break
                    except Exception as exc:
                        last_error = f"{type(exc).__name__}: {str(exc)[:80]}"
                        continue
                if chunk_result is not None:
                    break
            if chunk_result is not None:
                break
            if attempt < max_retries and backoff_base > 0:
                time.sleep(min(4.0, backoff_base * (2 ** attempt)))
        if chunk_result is None:
            return None, total_attempts, last_error or "chunk_translation_failed"
        all_out.extend(chunk_result)

    return all_out, total_attempts, None


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

    use_llm_en = _has_llm_translation_key()
    if zh_titles_src:
        en_trans = (
            _translate_texts_with_pipeline(zh_titles_src, "en", max_retries=max_retries, backoff_base=backoff_base)[0]
            if use_llm_en
            else None
        )
        for pos, ev_idx in enumerate(zh_titles_idx):
            ev = events[ev_idx]
            ev["title_en"] = (en_trans[pos] if en_trans and en_trans[pos] else None) or _translate_zh_to_en_glossary(
                zh_titles_src[pos], ev.get("entities")
            )
    if zh_sums_src:
        en_sum_trans = (
            _translate_texts_with_pipeline(zh_sums_src, "en", max_retries=max_retries, backoff_base=backoff_base)[0]
            if use_llm_en
            else None
        )
        for pos, ev_idx in enumerate(zh_sums_idx):
            ev = events[ev_idx]
            ev["summary_en"] = (en_sum_trans[pos] if en_sum_trans and en_sum_trans[pos] else None) or _translate_zh_to_en_glossary(
                zh_sums_src[pos], ev.get("entities")
            )
    if zh_ai_src:
        en_ai_trans = (
            _translate_texts_with_pipeline(zh_ai_src, "en", max_retries=max_retries, backoff_base=backoff_base)[0]
            if use_llm_en
            else None
        )
        for pos, ev_idx in enumerate(zh_ai_idx):
            ev = events[ev_idx]
            ev["ai_analysis_en"] = (en_ai_trans[pos] if en_ai_trans and en_ai_trans[pos] else None) or _translate_zh_to_en_glossary(
                zh_ai_src[pos], ev.get("entities")
            )


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
    en_idx: List[tuple[int, int]] = []
    en_src: List[str] = []
    for ti, tp in enumerate(topic_list):
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
                    en_idx.append((ti, ni))
                    en_src.append(t)
            else:
                node["title_zh"] = t
                node.setdefault("translation_status", "native_zh")
            s = str(node.get("summary") or "").strip()
            if _LEGACY_PLACEHOLDER_SUMMARY_RE.search(s):
                s = str(node.get("summary_en") or node.get("title_en") or node.get("title") or "")[:120]
                node["summary"] = s
                node["summary_zh"] = s
            elif s and is_mostly_english(s):
                node["summary_en"] = s
                manual_s = _resolve_override(s, "summary_zh", manual_dict)
                node["summary"] = manual_s or _translate_offline_fallback(s, is_summary=True)
                node["summary_zh"] = node["summary"]

    if en_src:
        translated, attempts, err = _translate_texts_with_pipeline(
            en_src, "zh", max_retries=max_retries, backoff_base=backoff_base
        )
        for pos, (ti, ni) in enumerate(en_idx):
            src_t = en_src[pos]
            node = topic_list[ti]["timeline"][ni]
            node["translation_attempts"] = max(attempts, 1)
            if translated and translated[pos]:
                zh_t = translated[pos]
                node["translation_status"] = "translated"
                node["translation_error"] = None
            else:
                exact_t = _lookup_offline_phrase(src_t)
                if exact_t:
                    zh_t = exact_t
                    node["translation_status"] = "translated"
                    node["translation_error"] = None
                else:
                    zh_t = _translate_offline_fallback(src_t)
                    node["translation_status"] = "retry_fallback"
                    node["translation_error"] = err or "llm_unavailable_fallback"
            node["title_zh"] = zh_t
            node["title"] = zh_t

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
    if zh_topic_src:
        tp_en = (
            _translate_texts_with_pipeline(zh_topic_src, "en", max_retries=max_retries, backoff_base=backoff_base)[0]
            if _has_llm_translation_key()
            else None
        )
        for pos, ti in enumerate(zh_topic_idx):
            topic_list[ti]["title_en"] = (tp_en[pos] if tp_en and tp_en[pos] else None) or _translate_zh_to_en_glossary(
                zh_topic_src[pos], topic_list[ti].get("entities")
            )
    if zh_node_src:
        nd_en = (
            _translate_texts_with_pipeline(zh_node_src, "en", max_retries=max_retries, backoff_base=backoff_base)[0]
            if _has_llm_translation_key()
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

    llm_out: Optional[List[str]] = None
    if _has_llm_translation_key():
        batch_texts = [t for _, _, t in pending_refs[:max_llm_items]]
        llm_out, _, _ = _translate_texts_with_pipeline(batch_texts, "en", max_retries=1, backoff_base=0.3)

    for idx, (rec, dst_k, zh_src) in enumerate(pending_refs):
        cand = llm_out[idx] if (llm_out and idx < len(llm_out) and llm_out[idx]) else None
        if not cand or _has_cjk_text(cand):
            ents = rec.get("entities") or ([rec.get("company_name")] if rec.get("company_name") else None)
            cand = _translate_zh_to_en_glossary(zh_src, ents)
        if cand and cand != rec.get(dst_k):
            rec[dst_k] = cand
            changed = True
    return changed
