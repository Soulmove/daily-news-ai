import requests
import json
import os
from datetime import datetime

# ================= 配置区域 =================
# 定义四个分类的数据文件名
FILES = {
    "finance": "data_finance.json",
    "tech": "data_tech.json",
    "global": "data_global.json",
    "general": "data_general.json"
}

# 核心分类字典
CATEGORY_MAP = {
    "finance": ["wallstreetcn-hot", "wallstreetcn-news", "wallstreetcn-quick", "cls-hot", "cls-depth", "xueqiu-hotstock", "gelonghui", "jin10", "mktnews-flash", "fastbull-express", "fastbull-news"],
    "tech": ["36kr-quick", "36kr-renqi", "sspai", "coolapk", "ithome", "huxiu", "geekpark", "qbitai", "producthunt", "github-trending-today", "hackernews", "v2ex-share", "freebuf", "solidot"],
    "global": ["zaobao", "sputniknewscn", "cankaoxiaoxi", "kaopu"],
    "general": ["zhihu", "weibo", "douyin", "baidu", "bilibili-hot-search", "tieba", "toutiao", "thepaper", "douban", "hupu", "chongbuluo-hot", "chongbuluo-latest", "nowcoder"]
}

ALL_SOURCES = []
for ids in CATEGORY_MAP.values():
    ALL_SOURCES.extend(ids)

def run_spider():
    print(f"[{datetime.now()}] 🚀 云端爬虫启动...")
    
    url = "https://newsnow.busiyi.world/api/s/entire"
    headers = {
        "content-type": "application/json",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    payload = { "sources": ALL_SOURCES }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        if response.status_code == 200:
            raw_data = response.json()
            categorized_data = { "finance": [], "tech": [], "global": [], "general": [] }

            for platform in raw_data:
                site_id = platform.get('id')
                items = platform.get('items', [])
                if not items: continue

                clean_items = []
                for item in items:
                    clean_items.append({
                        "title": item.get('title', '').strip(),
                        "url": item.get('url', '')
                    })

                clean_platform = { "id": site_id, "items": clean_items }

                found = False
                for cat_name, ids_list in CATEGORY_MAP.items():
                    if site_id in ids_list:
                        categorized_data[cat_name].append(clean_platform)
                        found = True
                        break
                if not found: categorized_data["general"].append(clean_platform)

            for cat_name, data_list in categorized_data.items():
                with open(FILES[cat_name], "w", encoding="utf-8") as f:
                    json.dump(data_list, f, ensure_ascii=False, indent=2)
                print(f"✅ 保存成功: {FILES[cat_name]} ({len(data_list)} 平台)")
        else:
            print(f"❌ 请求失败: {response.status_code}")

    except Exception as e:
        print(f"❌ 发生错误: {e}")

if __name__ == "__main__":
    # ⚠️ 关键修改：直接运行一次就结束，不要 while True 循环！
    run_spider()
    print("🎉 爬取结束，准备退出...")
