"""Canonical source registry, categories, kinds, and retired source tracking."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class SourceDef:
    id: str
    name: str
    category: str
    kind: str  # "news" | "discussion" | "repo" | "market_ticker"
    home_url: str
    expected_interval_minutes: int = 30
    citable_as_news: bool = True


# Active sources verified against newsnow.busiyi.world
ACTIVE_SOURCES: List[SourceDef] = [
    # Finance (12)
    SourceDef("wallstreetcn-hot", "华尔街见闻 · 最热", "finance", "news", "https://wallstreetcn.com/", 30),
    SourceDef("wallstreetcn-news", "华尔街见闻 · 资讯", "finance", "news", "https://wallstreetcn.com/", 30),
    SourceDef("wallstreetcn-quick", "华尔街见闻 · 快讯", "finance", "news", "https://wallstreetcn.com/", 15),
    SourceDef("cls-hot", "财联社 · 热门", "finance", "news", "https://www.cls.cn", 20),
    SourceDef("cls-depth", "财联社 · 深度", "finance", "news", "https://www.cls.cn", 30),
    SourceDef("cls-telegraph", "财联社 · 电报", "finance", "news", "https://www.cls.cn", 15),
    SourceDef("gelonghui", "格隆汇", "finance", "news", "https://www.gelonghui.com", 20),
    SourceDef("jin10", "金十数据", "finance", "news", "https://www.jin10.com", 15),
    SourceDef("mktnews-flash", "MKTNews 快讯", "finance", "news", "https://mktnews.net", 15),
    SourceDef("fastbull-express", "法布财经 · 快讯", "finance", "news", "https://www.fastbull.cn", 15),
    SourceDef("fastbull-news", "法布财经 · 头条", "finance", "news", "https://www.fastbull.cn", 30),
    SourceDef("xueqiu-hotstock", "雪球 · 热门股票", "finance", "market_ticker", "https://xueqiu.com", 15, citable_as_news=False),

    # Tech (12)
    SourceDef("aihot", "AIHOT 前沿", "tech", "news", "https://aihot.news/all", 15),
    SourceDef("ithome", "IT之家", "tech", "news", "https://www.ithome.com", 20),
    SourceDef("sspai", "少数派", "tech", "news", "https://sspai.com", 30),
    SourceDef("juejin", "稀土掘金", "tech", "news", "https://juejin.cn", 20),
    SourceDef("coolapk", "酷安", "tech", "discussion", "https://coolapk.com", 30),
    SourceDef("hackernews", "Hacker News", "tech", "discussion", "https://news.ycombinator.com/", 20),
    SourceDef("github-trending-today", "GitHub Trending", "tech", "repo", "https://github.com/trending", 60),
    SourceDef("producthunt", "Product Hunt", "tech", "repo", "https://www.producthunt.com/", 60),
    SourceDef("v2ex-share", "V2EX 分享", "tech", "discussion", "https://v2ex.com/", 30),
    SourceDef("freebuf", "FreeBuf 安全", "tech", "news", "https://www.freebuf.com/", 30),
    SourceDef("solidot", "Solidot 奇客", "tech", "news", "https://solidot.org", 60),
    SourceDef("pcbeta-windows11", "远景论坛 Win11", "tech", "discussion", "https://bbs.pcbeta.com", 30),

    # Global (4)
    SourceDef("zaobao", "联合早报", "global", "news", "https://www.zaobao.com", 30),
    SourceDef("sputniknewscn", "卫星通讯社", "global", "news", "https://sputniknews.cn", 30),
    SourceDef("cankaoxiaoxi", "参考消息", "global", "news", "https://china.cankaoxiaoxi.com", 30),
    SourceDef("kaopu", "靠谱新闻", "global", "news", "https://kaopu.news/", 30),

    # General / Society & Hotspots (15)
    SourceDef("thepaper", "澎湃新闻", "general", "news", "https://www.thepaper.cn", 30),
    SourceDef("ifeng", "凤凰网热点", "general", "news", "https://www.ifeng.com", 20),
    SourceDef("tencent-hot", "腾讯新闻综合早报", "general", "news", "https://news.qq.com", 30),
    SourceDef("toutiao", "今日头条", "general", "news", "https://www.toutiao.com", 20),
    SourceDef("baidu", "百度热搜", "general", "news", "https://www.baidu.com", 20),
    SourceDef("zhihu", "知乎热榜", "general", "discussion", "https://www.zhihu.com", 20),
    SourceDef("weibo", "微博热搜", "general", "discussion", "https://weibo.com", 15),
    SourceDef("douyin", "抖音热点", "general", "discussion", "https://www.douyin.com", 20),
    SourceDef("bilibili-hot-search", "B站热搜", "general", "discussion", "https://www.bilibili.com", 20),
    SourceDef("tieba", "百度贴吧热议", "general", "discussion", "https://tieba.baidu.com", 30),
    SourceDef("douban", "豆瓣热门电影", "general", "discussion", "https://www.douban.com", 60),
    SourceDef("hupu", "虎扑主干道", "general", "discussion", "https://hupu.com", 30),
    SourceDef("chongbuluo-hot", "虫部落 · 最热", "general", "discussion", "https://www.chongbuluo.com", 60),
    SourceDef("chongbuluo-latest", "虫部落 · 最新", "general", "discussion", "https://www.chongbuluo.com", 60),
    SourceDef("nowcoder", "牛客热榜", "general", "discussion", "https://www.nowcoder.com", 30),
]

RETIRED_SOURCES: List[Dict[str, str]] = [
    {"id": "36kr-quick", "name": "36氪快讯", "category": "tech", "reason": "上游 newsnow 接口返回 HTTP 500 (Invalid source id)"},
    {"id": "36kr-renqi", "name": "36氪人气", "category": "tech", "reason": "上游 newsnow 接口返回 HTTP 500 (Invalid source id)"},
    {"id": "huxiu", "name": "虎嗅", "category": "tech", "reason": "上游 newsnow 接口返回 HTTP 500 (Invalid source id)"},
    {"id": "geekpark", "name": "极客公园", "category": "tech", "reason": "上游 newsnow 接口返回 HTTP 500 (Invalid source id)"},
    {"id": "qbitai", "name": "量子位", "category": "tech", "reason": "上游 newsnow 接口返回 HTTP 500 (Invalid source id)"},
]

SOURCE_BY_ID: Dict[str, SourceDef] = {s.id: s for s in ACTIVE_SOURCES}

CATEGORIES = ("finance", "global", "tech", "general")

CATEGORY_LABELS: Dict[str, str] = {
    "finance": "财经/市场",
    "global": "国际/宏观",
    "tech": "科技/AI",
    "general": "社会/热点",
}

CATEGORY_FILES: Dict[str, str] = {
    cat: f"data_{cat}.json" for cat in CATEGORIES
}


def get_sources_by_category() -> Dict[str, List[SourceDef]]:
    grouped: Dict[str, List[SourceDef]] = {cat: [] for cat in CATEGORIES}
    for s in ACTIVE_SOURCES:
        grouped[s.category].append(s)
    return grouped
