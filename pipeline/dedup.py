"""URL-first, title-similarity deduplication, reprint detection, and briefing prioritization."""

from __future__ import annotations

from functools import lru_cache

from datetime import timedelta
import re
from typing import Dict, List, Optional, Set, Tuple

from pipeline.time_utils import now_shanghai, parse_iso_datetime

_TABLOID_NOISE_RE = re.compile(r"(?:婚外情|间谍|丑闻|跳起|宝莱坞|大瓜|出轨|明星八卦|搞笑)")
_COMMUNITY_GOSSIP_IDS = {"zhihu", "weibo", "tieba", "douyin", "hupu"}

_CLEAN_RE = re.compile(r"[\s\W_]+", re.UNICODE)
_ASCII_WORD_RE = re.compile(r"[a-z0-9]{2,}")
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?%?")
_FILING_PREFIX_RE = re.compile(r"^\[(SEC|HKEX|巨潮)\s+([^\]]+)\]", re.I)
_DIGEST_LABEL_RE = re.compile(r"(?:早报|晚报|日报|午报|周报|一周要闻|热点速递|每日资讯)\s*[|｜:：]")
_CORPORATE_ACTION_RE = re.compile(r"(?:大行评级|目标价|下调|上调|首予|买入评级|财报|营收|净利润|ipo|赴港|上市|提交.*文件|裁员|收购|退市)", re.I)
_RATING_SUBJECT_RE = re.compile(r"(?:下调|上调|维持|首予|给予|重申)\s*([A-Za-z0-9\u4e00-\u9fff·]{2,14}?)(?:目标价|评级|买入|增持|减持)")
_MULTI_EVENT_VERBS_RE = re.compile(
    r"(?:卸任|辞任|复职|ipo|上市|亮相|发布|上线|推出|融资|裁员|收购|宕机|泄露|警告|停飞|下调|上调|回应)",
    re.I,
)
_GENERIC_BUCKET_ENTITIES = {"ent_ai_infra_tools", "ent_macro_fomc", "ent_semiconductor_equipment"}

# Cross-lingual concept aliases so English and Chinese titles on the same event can match
_CONCEPT_ALIASES = {
    "nvidia": "英伟达",
    "jensen": "黄仁勋",
    "huang": "黄仁勋",
    "openai": "openai",
    "anthropic": "anthropic",
    "microsoft": "微软",
    "azure": "微软云",
    "apple": "苹果",
    "spacex": "spacex",
    "tesla": "特斯拉",
    "minecraft": "我的世界",
    "oxford": "牛津",
    "deepseek": "deepseek",
    "bitcoin": "比特币",
    "tsmc": "台积电",
    "meta": "meta",
    "iran": "伊朗",
    "ukraine": "乌克兰",
    "russia": "俄罗斯",
    "molecular": "分子",
    "motor": "马达",
    "motors": "马达",
    "quantum": "量子",
    "semiconductor": "半导体",
    "chip": "芯片",
    "chips": "芯片",
    "robot": "机器人",
    "robotics": "机器人",
    "macbook": "苹果",
    "energy": "耗能",
    "english": "英语",
    "generative": "生成",
}


def extract_tokens(text: str) -> Set[str]:
    """Extract CJK bigrams + normalized ASCII words + concept aliases for similarity matching."""
    if not text:
        return set()
    lowered = text.lower()
    tokens: Set[str] = set()

    for word in _ASCII_WORD_RE.findall(lowered):
        tokens.add(word)
        alias = _CONCEPT_ALIASES.get(word)
        if alias:
            tokens.add(alias)
            alias_cjk = [ch for ch in alias if "\u4e00" <= ch <= "\u9fff"]
            for i in range(len(alias_cjk) - 1):
                tokens.add(alias_cjk[i] + alias_cjk[i + 1])

    for run in re.findall(r"[\u4e00-\u9fff]+", lowered):
        for i in range(len(run) - 1):
            tokens.add(run[i : i + 2])

    for num in _NUMBER_RE.findall(lowered):
        tokens.add(num)

    return tokens


def title_similarity(title_a: str, title_b: str) -> float:
    """Compute overlap coefficient / Jaccard blend between two titles."""
    ta = extract_tokens(title_a)
    tb = extract_tokens(title_b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    if inter == 0:
        return 0.0
    jaccard = inter / len(ta | tb)
    overlap = inter / min(len(ta), len(tb))
    return 0.45 * jaccard + 0.55 * overlap


def _extract_filing_subject(text: str) -> Optional[str]:
    """Identify distinct regulatory filing issuer (company/code) so SEC/HKEX/CNInfo filings never cross-attach."""
    t = (text or "").strip()
    m = _FILING_PREFIX_RE.match(t)
    if not m:
        return None
    kind = m.group(1).upper()
    rest = t[m.end():].strip()
    if kind in {"HKEX", "巨潮"}:
        parts = m.group(2).split()
        return f"{kind}:{parts[0]}" if parts else kind
    # For [SEC 8-K] 英伟达 (NVIDIA) ... or [SEC 10-Q] AMD ...
    head = rest.split("提交", 1)[0].strip().lower()
    return f"SEC:{head[:24]}" if head else None


@lru_cache(maxsize=8192)
def _cached_primary_entities(txt: str) -> frozenset[str]:
    from pipeline.entities import match_entities_with_reasons

    hits = match_entities_with_reasons(txt)
    return frozenset(
        h["entity_id"]
        for h in hits
        if h.get("entity_id") and h["entity_id"] not in _GENERIC_BUCKET_ENTITIES
    )


def entities_conflict(
    text_a: str,
    text_b: str,
    *,
    item_a: Optional[dict] = None,
    item_b: Optional[dict] = None,
) -> bool:
    """
    Return True when two texts/items clearly refer to different primary companies, filings,
    or model releases so generic shared words ('下调', '目标价', 'SEC', 'AI') never merge them.
    """
    f_a = _extract_filing_subject(text_a)
    f_b = _extract_filing_subject(text_b)
    if f_a and f_b and f_a != f_b:
        return True
    if (f_a and not f_b) or (f_b and not f_a):
        # Never fold a standalone regulatory filing ([SEC 8-K] NVDA) into a gossip article or vice versa
        if (item_a or {}).get("source_kind") == "official_filing" or (item_b or {}).get("source_kind") == "official_filing":
            return True

    def _primary_entity_set(txt: str, item: Optional[dict]) -> Set[str]:
        explicit = {
            str(e)
            for e in ((item or {}).get("entity_ids") or [])
            if e and e not in _GENERIC_BUCKET_ENTITIES
        }
        if explicit:
            return explicit
        return set(_cached_primary_entities(txt))

    ents_a = _primary_entity_set(text_a, item_a)
    ents_b = _primary_entity_set(text_b, item_b)
    if ents_a and ents_b and not (ents_a & ents_b):
        return True
    # Guard when one headline clearly names a primary tracked company/action target and the other names an untracked target (e.g. Walmart/Cisco/Cerebras ratings vs NVIDIA)
    if bool(ents_a) != bool(ents_b):
        other_text = text_b if ents_a else text_a
        if _RATING_SUBJECT_RE.search(other_text) or _CORPORATE_ACTION_RE.search(other_text):
            return True
    # Also guard analyst rating / single-company headlines where both match the same rating verb on different untracked names
    m_a = _RATING_SUBJECT_RE.search(text_a)
    m_b = _RATING_SUBJECT_RE.search(text_b)
    if m_a and m_b and m_a.group(1).lower() != m_b.group(1).lower():
        return True
    # Also guard regulatory filing prefixes
    if (f_a or f_b) and ents_a != ents_b and (ents_a or ents_b):
        if not (ents_a and ents_b and (ents_a & ents_b)):
            return True
    return False


def is_omnibus_digest_title(title: str) -> bool:
    """Detect multi-topic daily digests / roundups (e.g. '早报 | A；B' or 'X卸任、Y赴港IPO、Z亮相')."""
    t = (title or "").strip()
    if not t:
        return False
    if _DIGEST_LABEL_RE.search(t):
        return True
    segments = [seg.strip() for seg in re.split(r"[、；;|｜]+", t) if len(seg.strip()) >= 4]
    if len(segments) >= 2:
        from pipeline.entities import match_entities_with_reasons

        seg_ents: List[Set[str]] = []
        verb_segs = 0
        for seg in segments:
            ids = {
                h["entity_id"]
                for h in match_entities_with_reasons(seg)
                if h.get("entity_id") not in _GENERIC_BUCKET_ENTITIES
            }
            if ids:
                seg_ents.append(ids)
            if _MULTI_EVENT_VERBS_RE.search(seg):
                verb_segs += 1
        distinct_union = set().union(*seg_ents) if seg_ents else set()
        if verb_segs >= 2 and (len(distinct_union) >= 2 or len(segments) >= 3):
            return True
        if len(segments) >= 3 and len(distinct_union) >= 2 and "联合" not in t and "撤诉" not in t:
            return True
    return False


def get_publisher_family(source_id: str, url: str = "") -> str:
    """Group multi-feed channels from the same outlet (e.g. cls-hot/cls-telegraph -> cls) into one family."""
    sid = (source_id or "unknown").lower().strip()
    if sid.startswith("wallstreetcn"):
        return "wallstreetcn"
    if sid.startswith("cls"):
        return "cls"
    if sid.startswith("fastbull"):
        return "fastbull"
    if sid.startswith("chongbuluo"):
        return "chongbuluo"
    if sid.startswith("36kr"):
        return "36kr"
    return sid.split("-")[0] if "-" in sid and sid.split("-")[0] in {"tencent", "bilibili"} else sid


def _source_rank_key(src: dict) -> tuple:
    """Order citations so first-party official / excerpted primary reports appear before omnibus hotlists."""
    tier = src.get("source_tier") or ""
    tier_score = 0 if tier == "first_party" else (1 if tier == "tech_material" else 2)
    is_omnibus = 1 if (src.get("source_id") == "aihot" or src.get("source_kind") == "discussion") else 0
    has_excerpt = 0 if src.get("excerpt") else 1
    pub = src.get("published_at") or ""
    return (tier_score, is_omnibus, has_excerpt, 0 if pub else 1)


_MAJOR_BREAKING_RE = re.compile(
    r"(?:(?:特朗普|川普)[^。！？\n]{0,28}(?:访华|来华|中国|深圳|北京|apec|会晤|普京|关税|贸易|元首)|"
    r"trump[^.\n]{0,40}(?:china|xi\b|apec|shenzhen|beijing|putin|tariff|summit|trilateral|visit|trade)|"
    r"习近平|普京|中美元首|中美俄|访华|apec|g20|习特会|"
    r"美联储|fomc|央行|降息|加息|关税|停火|ipo|募资|并购|星舰|starship|筷子夹|火箭回收|"
    r"历史新高|暴跌|跳水|零日漏洞|大规模宕机|达成协议|联合声明|自贸协定)",
    re.I,
)

_TRIVIA_FLUFF_RE = re.compile(
    r"(?:围巾|座驾|同框|开了个玩笑|表情包|穿着|发型|花絮|合影细节|整理围巾|穿搭|美食|打卡|全妆|人字拖|三角梅|"
    r"midterm|fcc\s+nominee|fda\s+nominee|nsf\s+pick|skip a vote|boycott vote)",
    re.I,
)


def score_cluster_for_briefing(cluster: dict, watched_match_count: int = 0) -> Tuple[float, List[str]]:
    """
    Task 2 candidate prioritization score balancing:
    major breaking significance, watchlist relevance (capped so tech never starves geopolitics/macro),
    source independence, material depth, first-party backing, freshness decay & noise penalty.
    """
    reasons: List[str] = []
    score = 0.0
    title_str = str(cluster.get("title") or "")
    excerpt_str = str(cluster.get("excerpt") or "")
    text_blob = f"{title_str} {excerpt_str}"
    is_trivia = bool(_TRIVIA_FLUFF_RE.search(title_str))

    if watched_match_count > 0:
        score += 22.0 + min(watched_match_count, 2) * 5.0
        reasons.append("命中核心/关注对象")

    if not is_trivia and _MAJOR_BREAKING_RE.search(text_blob):
        score += 24.0
        reasons.append("命中全球重大突发/宏观政策信号")
    elif is_trivia:
        score -= 26.0
        reasons.append("花絮/琐碎政治提名降权")

    related = cluster.get("related_sources") or [cluster]
    indep_families = {get_publisher_family(s.get("source_id", "")) for s in related if s.get("source_id")}
    indep_cnt = len(indep_families)
    if indep_cnt >= 2:
        score += min(indep_cnt, 6) * 9.0
        reasons.append(f"{indep_cnt} 家独立来源报道")
    elif indep_cnt == 1:
        score += 4.0

    has_first_party = any(s.get("source_tier") in {"first_party", "tech_material", "direct_media"} for s in related)
    if has_first_party:
        score += 18.0
        reasons.append("含一手官方或权威直连媒体")

    if cluster.get("excerpt") or any(s.get("excerpt") for s in related):
        score += 10.0
        reasons.append("含摘要或正文首段")

    pub_iso = cluster.get("published_at")
    if pub_iso:
        score += 5.0
        reasons.append("含原文发布时间")
        pub_dt = parse_iso_datetime(pub_iso)
        if pub_dt is not None:
            age_hours = (now_shanghai() - pub_dt).total_seconds() / 3600.0
            if age_hours <= 6.0:
                score += 18.0
                reasons.append("6小时内即时动态")
            elif age_hours <= 24.0:
                score += 10.0
            elif age_hours > 168.0:
                score -= 36.0
                reasons.append("超过7天陈旧条目降权")
            elif age_hours > 48.0:
                score -= 18.0
                reasons.append("超过48小时历史报道降权")

    if is_omnibus_digest_title(title_str):
        score -= 48.0
        reasons.append("拼盘早报/多事件合集降权")
    if _TABLOID_NOISE_RE.search(title_str):
        score -= 28.0
        reasons.append("含八卦/情绪化表述降权")

    # Single community discussion post (e.g. standalone zhihu/weibo/tieba) without news corroboration OR breaking macro signal
    all_community = bool(related) and all(
        (s.get("source_id") in _COMMUNITY_GOSSIP_IDS or s.get("source_kind") == "discussion")
        for s in related
    )
    if all_community and indep_cnt <= 1 and not _MAJOR_BREAKING_RE.search(text_blob):
        score -= 14.0
        reasons.append("单一社区热榜讨论降权")

    return round(score, 2), reasons


def deduplicate_raw_items(items: List[dict], similarity_threshold: float = 0.58) -> List[dict]:
    """
    Deduplicate raw items in two phases:
      1. Exact canonical_url match merges duplicates while preserving all source tags.
      2. High-similarity title match merges obvious cross-platform syndication
         while retaining every source URL, title, published_at, and `is_reprint_copy`
         markers so divergent reports are preserved without inflating independent evidence counts.
    """
    by_url: Dict[str, dict] = {}
    url_order: List[dict] = []

    for item in items:
        canon = item.get("canonical_url")
        sid = item.get("source_id", "")
        source_entry = {
            "item_id": item.get("item_id"),
            "source_id": sid,
            "source_name": item.get("source_name"),
            "source_kind": item.get("source_kind", "news"),
            "source_tier": item.get("source_tier"),
            "publisher_family": item.get("publisher_family") or get_publisher_family(sid, canon or ""),
            "title": item.get("title"),
            "url": item.get("url"),
            "published_at": item.get("published_at"),
            "fetched_at": item.get("fetched_at"),
            "excerpt": item.get("excerpt"),
            "is_reprint_copy": False,
        }
        if canon and canon in by_url:
            existing = by_url[canon]
            if not any(s.get("source_id") == source_entry["source_id"] for s in existing["related_sources"]):
                source_entry["is_reprint_copy"] = True
                existing["related_sources"].append(source_entry)
            if not existing.get("published_at") and item.get("published_at"):
                existing["published_at"] = item.get("published_at")
            if not existing.get("excerpt") and item.get("excerpt"):
                existing["excerpt"] = item.get("excerpt")
            continue

        cloned = dict(item)
        cloned["related_sources"] = [source_entry]
        cloned["_tokens"] = extract_tokens(item.get("title", ""))
        if canon:
            by_url[canon] = cloned
        url_order.append(cloned)

    # Phase 2: obvious cross-platform title clustering & syndicated reprint tagging
    clusters: List[dict] = []
    for candidate in url_order:
        if candidate.get("source_kind") == "market_ticker":
            clusters.append(candidate)
            continue

        cand_tokens = candidate["_tokens"]
        cand_title = candidate.get("title", "")
        cand_dt = parse_iso_datetime(candidate.get("published_at")) if candidate.get("published_at") else None
        matched_cluster = None
        matched_score = 0.0
        if len(cand_tokens) >= 3:
            for existing in clusters:
                if existing.get("source_kind") in {"market_ticker", "official_filing", "repo_release", "model_card"}:
                    continue
                if candidate.get("source_kind") in {"official_filing", "repo_release", "model_card"}:
                    continue
                ex_tokens = existing["_tokens"]
                if not ex_tokens:
                    continue
                ex_title = existing.get("title", "")
                if entities_conflict(cand_title, ex_title, item_a=candidate, item_b=existing):
                    continue
                ex_dt = parse_iso_datetime(existing.get("published_at")) if existing.get("published_at") else None
                if cand_dt and ex_dt and abs((cand_dt - ex_dt).total_seconds()) > 48 * 3600:
                    continue
                inter = len(cand_tokens & ex_tokens)
                if inter < 3:
                    continue
                jaccard = inter / len(cand_tokens | ex_tokens)
                overlap = inter / min(len(cand_tokens), len(ex_tokens))
                score = 0.45 * jaccard + 0.55 * overlap
                if score >= similarity_threshold or (inter >= 5 and overlap >= 0.33):
                    matched_cluster = existing
                    matched_score = score
                    break

        if matched_cluster is not None:
            for s in candidate["related_sources"]:
                if not any(es.get("item_id") == s.get("item_id") for es in matched_cluster["related_sources"]):
                    s_copy = dict(s)
                    same_family = any(
                        es.get("publisher_family") == s_copy.get("publisher_family")
                        for es in matched_cluster["related_sources"]
                    )
                    if same_family or matched_score >= 0.82:
                        s_copy["is_reprint_copy"] = True
                    matched_cluster["related_sources"].append(s_copy)
            if not matched_cluster.get("published_at") and candidate.get("published_at"):
                matched_cluster["published_at"] = candidate["published_at"]
            if not matched_cluster.get("excerpt") and candidate.get("excerpt"):
                matched_cluster["excerpt"] = candidate["excerpt"]
        else:
            clusters.append(candidate)

    for c in clusters:
        c.pop("_tokens", None)
        rel = c.get("related_sources") or []
        rel.sort(key=_source_rank_key)
        c["related_sources"] = rel
        if rel:
            best = rel[0]
            c["primary_source_id"] = best.get("source_id")
        indep = {
            s.get("publisher_family") or get_publisher_family(s.get("source_id", ""))
            for s in rel
            if not s.get("is_reprint_copy")
        }
        if not indep and rel:
            indep = {rel[0].get("publisher_family") or "unknown"}
        c["independent_publisher_count"] = len(indep)
    return clusters
