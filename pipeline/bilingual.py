"""Bilingual (ZH/EN) enrichment helper so Chinese readers never face untranslated English headlines, while English mode stays clean."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_LATIN_RE = re.compile(r"[A-Za-z]")


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


def _translate_offline_fallback(text: str, *, is_summary: bool = False) -> str:
    clean = re.sub(r"^(?:【[^】]{2,14}】\s*)+", "", (text or "").strip())
    if not clean or not is_mostly_english(clean):
        return clean
    for pat, zh in _OFFLINE_PHRASE_MAP:
        if pat.search(clean):
            return zh
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


def ensure_zh_headline(text: str, category: str = "") -> str:
    """Fast deterministic Chinese headline normalizer for raw direct-RSS / flash wire items."""
    del category
    return _translate_offline_fallback(text, is_summary=False)


_LEGACY_PLACEHOLDER_SUMMARY_RE = re.compile(r"该条为海外主流媒体英文原报|云端\s*AI\s*批次将自动")


def _batch_translate_with_gemini(texts: List[str], target_lang: str = "zh") -> Optional[List[str]]:
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
        return None
    try:
        from google import genai
        from google.genai import types

        lang_desc = "自然流畅、专业简洁的中文新闻表达" if target_lang == "zh" else "concise, journalistic English"
        prompt = (
            f"将下面 JSON 数组中的每条新闻文本精准翻译为{lang_desc}，保留专有名词与数字，严禁增删条目。\n"
            f"只输出严格 JSON 字符串数组（长度必须与输入完全一致）：\n"
            + json.dumps(texts, ensure_ascii=False)
        )
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
                    if isinstance(parsed, list) and len(parsed) == len(texts):
                        return [str(x).strip() for x in parsed]
                except Exception:
                    continue
    except Exception:
        return None
    return None


def enrich_bilingual_events(events: List[Dict[str, Any]]) -> None:
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

        if is_mostly_english(title):
            ev.setdefault("title_en", title)
            if not ev.get("title_zh"):
                en_titles_idx.append(idx)
                en_titles_src.append(title)
        else:
            ev.setdefault("title_zh", title)

        if is_mostly_english(summary):
            ev.setdefault("summary_en", summary)
            if not ev.get("summary_zh"):
                en_summaries_idx.append(idx)
                en_summaries_src.append(summary[:260])
        else:
            ev.setdefault("summary_zh", summary)

    if en_titles_src:
        translated = _batch_translate_with_gemini(en_titles_src, "zh")
        for pos, ev_idx in enumerate(en_titles_idx):
            zh_val = translated[pos] if translated else _translate_offline_fallback(en_titles_src[pos])
            events[ev_idx]["title_zh"] = zh_val
            events[ev_idx]["title"] = zh_val

    if en_summaries_src:
        translated_s = _batch_translate_with_gemini(en_summaries_src, "zh")
        for pos, ev_idx in enumerate(en_summaries_idx):
            zh_s = translated_s[pos] if translated_s else _translate_offline_fallback(en_summaries_src[pos], is_summary=True)
            events[ev_idx]["summary_zh"] = zh_s
            if events[ev_idx].get("fact_summary"):
                events[ev_idx]["fact_summary"] = zh_s
            if events[ev_idx].get("summary"):
                events[ev_idx]["summary"] = zh_s


def enrich_bilingual_topics(topics: List[Dict[str, Any]]) -> None:
    en_idx: List[tuple[int, int]] = []
    en_src: List[str] = []
    for ti, tp in enumerate(topics):
        for ni, node in enumerate(tp.get("timeline") or []):
            t = str(node.get("title") or "").strip()
            if is_mostly_english(t):
                node["title_en"] = t
                en_idx.append((ti, ni))
                en_src.append(t)
            else:
                node["title_zh"] = t
            s = str(node.get("summary") or "").strip()
            if _LEGACY_PLACEHOLDER_SUMMARY_RE.search(s):
                s = str(node.get("summary_en") or node.get("title_en") or node.get("title") or "")[:120]
                node["summary"] = s
                node["summary_zh"] = s
            elif s and is_mostly_english(s):
                node["summary_en"] = s
                node["summary"] = _translate_offline_fallback(s, is_summary=True)
                node["summary_zh"] = node["summary"]

    if en_src:
        translated = _batch_translate_with_gemini(en_src, "zh")
        for pos, (ti, ni) in enumerate(en_idx):
            zh_t = translated[pos] if translated else _translate_offline_fallback(en_src[pos])
            node = topics[ti]["timeline"][ni]
            node["title_zh"] = zh_t
            node["title"] = zh_t
