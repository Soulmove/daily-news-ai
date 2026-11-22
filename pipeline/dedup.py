"""URL-first, title-similarity deduplication, reprint detection, and briefing prioritization."""

from __future__ import annotations

from functools import lru_cache

from datetime import timedelta
import re
from typing import Dict, List, Optional, Set, Tuple

from pipeline.time_utils import now_shanghai, parse_iso_datetime

_TABLOID_NOISE_RE = re.compile(r"(?:婚外情|间谍|丑闻|跳起|宝莱坞|大瓜|出轨|明星八卦|搞笑)")
_MATERIAL_CORPORATE_OR_SECURITY_RE = re.compile(
    r"(?:ceo|首席执行官|高管|董事会|辞任|辞职|复职|重返|sec|监管调查|听证会|国家安全|出口管制|股价|暴跌|重挫|财报|ipo|英伟达|nvidia)",
    re.I,
)
_EXTRAORDINARY_CLAIM_RE = re.compile(r"(?:证明|猜想|裁定|和解|收购|并购|破产|ipo|违约|制裁)", re.I)
_COMMUNITY_GOSSIP_IDS = {"zhihu", "weibo", "tieba", "douyin", "hupu", "coolapk", "v2ex-share"}
_SOCIAL_HOTLIST_IDS = frozenset({
    "baidu", "toutiao", "weibo", "zhihu", "douyin", "bilibili-hot-search",
    "tieba", "douban", "hupu", "coolapk", "v2ex-share", "nowcoder",
    "chongbuluo-hot", "chongbuluo-latest", "pcbeta-windows11",
})
_SOCIAL_HOTLIST_NAMES_RE = re.compile(
    r"(?:百度热搜|今日头条|微博热搜|知乎热榜|抖音热点|B站热搜|贴吧|豆瓣|虎扑|酷安|V2EX|牛客|虫部落|远景论坛)"
)

_CONSUMER_DEVICE_RE = re.compile(
    r"(?:显示器|电竞屏|耳机|音箱|键鼠|机械键盘|鼠标|路由器|充电宝|数码相框|扫地机器人|投影仪|平板|电视|冰箱|空调|洗衣机|洗碗机|吹风机|剃须刀|咖啡机|电动牙刷|智能手表|手环)"
)
_CONSUMER_PROMO_PRICE_RE = re.compile(
    r"(?:\d{2,5}\s*元|首销|首发价|到手价|补贴价|国补后|预售|开售|上架|现货开售|五折|半价|满减|优惠券|优惠|\d{2,3}\s*英寸\s*(?:2K|4K|OLED|IPS|VA|Fast)?|\d{3}\s*Hz)",
    re.I,
)
_GAME_PROMO_PLATFORM_RE = re.compile(
    r"(?:Steam|Epic|PSN|PlayStation|Xbox|Switch|育碧|Ubisoft|EA|暴雪|《极限国度》|《黑色洛城)",
    re.I,
)
_GAME_PROMO_DEAL_RE = re.compile(
    r"(?:史低|新史低|\d+(?:\.\d+)?\s*折|免费领|喜加一|促销|特惠|打折|帧率|\d+\s*FPS|203\d年发售|重制版|导剪版|DLC)",
    re.I,
)
_CORP_FINANCE_GUARD_RE = re.compile(
    r"(?:财报|营收|净利润|IPO|上市|并购|收购|增资|回购|证监会|沪深北|上交所|深交所|出口管制|关税|反垄断|首日销售额\s*\d+\s*亿美元|收入高达\s*\d+\s*亿美元)",
    re.I,
)
_PHOTO_OR_VENUE_FLUFF_RE = re.compile(
    r"(?:发布\s*\d+余?张.*照片|晒出?\s*\d*余?张?.*照片|会议照片并肯定|肯定(?:深圳)?城市?面貌|赞扬.*(?:接待|欢迎)|公开赞扬.*APEC|欣赏.*城市风貌|"
    r"发布会?(?:遭到|遭遇)?场地抗议|场地外?抗议|Helsing.*抗议|"
    r"今日小雪|小雪节气|大雪节气|立冬节气|冬至节气|首支单曲|主题曲|动画电影|剧场版|斗破苍穹)",
    re.I,
)
_MINOR_QUAKE_NOISE_RE = re.compile(r"(?<!\d)[0-4](?:\.\d+)?\s*级地震")
_SEVERE_DISASTER_GUARD_RE = re.compile(r"(?:遇难|死亡|伤亡|海啸|倒塌|受灾|应急响应|救援)")

_MARKET_PRICE_RE = re.compile(
    r"(?:现货黄金|黄金价格|金价|纳指|标普|道指|沪指|创业板指|A股|美股|港股|恒指|"
    r"英伟达.*跌|比特币|以太坊|\bBTC\b|\bETH\b|跌破|重返|涨超|跌超|暴跌|重挫|收盘|行情)",
    re.I,
)


def is_hotlist_aggregator_source(source_id: str, source_name: str = "") -> bool:
    sid = (source_id or "").lower().strip()
    if sid in _SOCIAL_HOTLIST_IDS:
        return True
    if not sid and _SOCIAL_HOTLIST_NAMES_RE.search(str(source_name or "")):
        return True
    return False


def has_authoritative_primary_source(sources: List[dict]) -> bool:
    """Return True iff at least one source is a genuine media/official/tech outlet (not pure social hotlists)."""
    if not sources:
        return False
    for s in sources:
        if not isinstance(s, dict):
            continue
        sid = str(s.get("source_id") or "").lower().strip()
        sname = str(s.get("publisher_name") or s.get("source_name") or "")
        tier = str(s.get("source_tier") or "")
        kind = str(s.get("source_kind") or "news")
        if is_hotlist_aggregator_source(sid, sname):
            continue
        if tier in {"first_party", "direct_media", "tech_material"}:
            return True
        if kind in {"news", "official_filing", "regulatory_release", "repo_release", "model_card"}:
            return True
    return False


def is_consumer_promo_or_fluff(title: str, excerpt: str = "") -> bool:
    """Reject C-tier retail hardware promos, phone retail discounts, game discounts/FPS/distant releases, photo-ops, venue protests, and minor quakes."""
    t = str(title or "").strip()
    if not t:
        return False
    blob = f"{t} {str(excerpt or '')[:160]}"
    if _PHOTO_OR_VENUE_FLUFF_RE.search(t):
        return True
    blob_disaster_clean = re.sub(r"(?:暂无|无|未造成|没有)(?:任何)?(?:人员)?伤亡(?:报告)?", "", blob)
    if _MINOR_QUAKE_NOISE_RE.search(t) and not _SEVERE_DISASTER_GUARD_RE.search(blob_disaster_clean):
        return True
    if _CORP_FINANCE_GUARD_RE.search(t):
        return False
    if re.search(
        r"(?:iPhone|华为\s*Mate|小米\s*\d+|OPPO|vivo|荣耀|三星\s*Galaxy).*(?:行情大跳水|第三方渠道价|低于官方\s*\d+\s*元|破发\s*\d+\s*元|直降\s*\d+\s*元|百亿补贴)",
        t,
        re.I,
    ):
        return True
    if _CONSUMER_DEVICE_RE.search(t) and _CONSUMER_PROMO_PRICE_RE.search(blob):
        return True
    if re.search(r"\b(?:TCL|飞利浦|Philips|AOC|蚂蚁电竞|HKC|KOORUI|泰坦军团|创维|Redmi|小米|三星|LG)\b.*\d{2,5}\s*元", t, re.I):
        return True
    if _GAME_PROMO_PLATFORM_RE.search(t) and _GAME_PROMO_DEAL_RE.search(blob):
        return True
    if re.search(r"(?:203\d年发售|史低\s*\d+(?:\.\d+)?\s*元|\d+折史低|新史低)", t):
        return True
    return False

_CLEAN_RE = re.compile(r"[\s\W_]+", re.UNICODE)
_ASCII_WORD_RE = re.compile(r"[a-z0-9]{2,}")
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?%?")
_FILING_PREFIX_RE = re.compile(r"^\[(SEC|HKEX|巨潮)\s+([^\]]+)\]", re.I)
_DIGEST_LABEL_RE = re.compile(r"(?:早报|晚报|日报|午报|周报|一周要闻|热点速递|每日资讯|晨报|夜报)\s*[|｜丨:：/]")
_RAW_URL_TAIL_RE = re.compile(r"\s*[-–—|｜]?\s*https?://\S+|\s*[-–—|｜]?\s*\bwww\.[A-Za-z0-9.-]+\.[a-z]{2,}\S*", re.I)


def strip_raw_urls_and_domain_tails(text: Optional[str]) -> str:
    """Strip inline/trailing raw http URLs and bare www.domain tokens without mangling normal prose."""
    s = str(text or "").strip()
    if not s:
        return ""
    s = _RAW_URL_TAIL_RE.sub("", s)
    s = re.sub(r"\s+[-–—|｜]+\s*$", "", s)
    return re.sub(r"\s{2,}", " ", s).strip()
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


_EN_STOPWORDS = frozenset({
    "the", "of", "to", "in", "is", "it", "on", "at", "by", "an", "as", "be", "or", "if",
    "so", "no", "up", "do", "we", "he", "my", "us", "are", "was", "for", "and", "not",
    "but", "has", "had", "its", "all", "can", "may", "new", "now", "out", "our", "who",
    "how", "why", "get", "got", "one", "two", "day", "his", "her", "she", "you", "your",
    "they", "them", "that", "this", "with", "from", "have", "will", "what", "when",
    "into", "over", "more", "than", "been", "were", "said", "says", "just", "also",
    "here", "there", "their", "could", "would", "should", "about", "after", "still",
    "worth", "good", "end", "year", "years", "time", "first", "last",
})


def extract_tokens(text: str) -> Set[str]:
    """Extract CJK bigrams + normalized ASCII words + concept aliases for similarity matching."""
    if not text:
        return set()
    lowered = text.lower()
    tokens: Set[str] = set()

    for word in _ASCII_WORD_RE.findall(lowered):
        if word in _EN_STOPWORDS:
            continue
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
    if t.count("/") >= 2 and len(t) > 36:
        return True
    segments = [seg.strip() for seg in re.split(r"[、；;|｜丨/]+", t) if len(seg.strip()) >= 4]
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
    if sid.startswith("wallstreetcn") or sid.startswith("wscn"):
        return "wallstreetcn"
    if sid.startswith("cls"):
        return "cls"
    if sid.startswith("fastbull"):
        return "fastbull"
    if sid.startswith("chongbuluo"):
        return "chongbuluo"
    if sid.startswith("36kr"):
        return "36kr"
    if sid.startswith("rss-gnews-") or "news.google.com" in (url or "").lower():
        return "gnews-aggregator"
    return sid.split("-")[0] if "-" in sid and sid.split("-")[0] in {"tencent", "bilibili", "rss"} and not sid.startswith("rss-gnews-") else sid


def _source_rank_key(src: dict) -> tuple:
    """Order citations so first-party official & authoritative direct media outrank community discussions & omnibus hotlists."""
    tier = src.get("source_tier") or ""
    kind = src.get("source_kind") or "news"
    sid = (src.get("source_id") or "").lower()
    is_hotlist = is_hotlist_aggregator_source(sid, str(src.get("source_name") or ""))
    if tier == "first_party":
        tier_score = 0
    elif tier == "direct_media":
        tier_score = 1
    elif tier == "tech_material":
        tier_score = 2
    elif kind == "news" and not is_hotlist:
        tier_score = 3
    elif kind == "repo":
        tier_score = 4
    else:
        tier_score = 5
    is_omnibus = 1 if (sid == "aihot" or is_hotlist or kind == "discussion" or src.get("is_reprint_copy")) else 0
    has_excerpt = 0 if src.get("excerpt") else 1
    has_thumb = 0 if src.get("thumbnail_url") else 1
    return (tier_score, is_omnibus, has_excerpt, has_thumb)


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

    if is_consumer_promo_or_fluff(title_str, excerpt_str):
        score -= 60.0
        reasons.append("消费带货/游戏促销/花边噪音降权")

    if is_omnibus_digest_title(title_str):
        score -= 48.0
        reasons.append("拼盘早报/多事件合集降权")
    if _TABLOID_NOISE_RE.search(title_str) and not _MATERIAL_CORPORATE_OR_SECURITY_RE.search(title_str):
        score -= 20.0
        reasons.append("含八卦/情绪化表述降权")

    # Social/hotlist-only clusters (e.g. baidu/toutiao/zhihu/weibo/tieba) without authoritative media corroboration
    all_hotlist = bool(related) and not has_authoritative_primary_source(related)
    if all_hotlist:
        score -= 18.0
        reasons.append("仅社媒热榜聚合（缺权威/一线信源）")
        if _MARKET_PRICE_RE.search(text_blob):
            score -= 40.0
            reasons.append("金融行情缺乏专业财经主信源")
        if _EXTRAORDINARY_CLAIM_RE.search(title_str):
            score -= 18.0
            reasons.append("重大科学/司法/并购传闻仅见热榜讨论（缺权威媒体交叉）")

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
            "thumbnail_url": item.get("thumbnail_url"),
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
            if not existing.get("thumbnail_url") and item.get("thumbnail_url"):
                existing["thumbnail_url"] = item.get("thumbnail_url")
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
            if not matched_cluster.get("thumbnail_url") and candidate.get("thumbnail_url"):
                matched_cluster["thumbnail_url"] = candidate["thumbnail_url"]
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
            if not c.get("thumbnail_url"):
                c["thumbnail_url"] = next((s.get("thumbnail_url") for s in rel if s.get("thumbnail_url")), None)
        indep = {
            s.get("publisher_family") or get_publisher_family(s.get("source_id", ""))
            for s in rel
            if not s.get("is_reprint_copy")
        }
        if not indep and rel:
            indep = {rel[0].get("publisher_family") or "unknown"}
        c["independent_publisher_count"] = len(indep)
    return clusters


def smart_truncate(text: str, max_len: int = 180) -> str:
    """Truncate text cleanly at sentence/clause boundaries without splitting decimal numbers or unmatched brackets."""
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    if not s or len(s) <= max_len:
        return s
    cut = s[: max_len - 1]
    min_pos = int(max_len * 0.45)
    best_end = -1
    for m in re.finditer(r"[。！？；!?]|(?<!\d)\.(?!\d)(?=\s|$|[”\"）)\u4e00-\u9fa5])", cut):
        if m.start() >= min_pos:
            best_end = m.start()
    if best_end >= min_pos:
        return cut[: best_end + 1].rstrip()
    open_idx = max(cut.rfind("（"), cut.rfind("("))
    close_idx = max(cut.rfind("）"), cut.rfind(")"))
    if open_idx > close_idx and open_idx >= min(3, min_pos):
        cut = cut[:open_idx].rstrip()
    # Avoid orphan closing parenthesis when truncating or stripping prefixes
    if cut.count("）") > cut.count("（") and cut.endswith("）"):
        cut = cut[:-1].rstrip("。，；： ")
    if cut.count(")") > cut.count("(") and cut.endswith(")"):
        cut = cut[:-1].rstrip(".,;: ")
    # Avoid breaking inside a numeric decimal like "19.2%" at the very edge
    cut = re.sub(r"\d+\.$", lambda m: cut[m.start() : m.end() - 1] if m.start() > 0 else "", cut).rstrip()
    clause_m = re.match(r"^(.+[，,;；：:\s])[^，,;；：:\s]{1,12}$", cut)
    if clause_m and len(clause_m.group(1)) >= int(max_len * 0.5):
        cut = clause_m.group(1).rstrip()
    return cut.rstrip(" ，、,;；：:(（「“") + "…"
