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

        else:
            print(f"❌ 请求失败: {response.status_code}")
            return

        # ================= 📂 存档逻辑 (新增) =================
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H-%M")
        
        # 1. 保存 Latest (覆盖根目录)
        for cat_name, data_list in categorized_data.items():
            with open(FILES[cat_name], "w", encoding="utf-8") as f:
                json.dump(data_list, f, ensure_ascii=False, indent=2)
            print(f"✅ [Latest] 保存成功: {FILES[cat_name]}")

        # 2. 保存 Archive (历史存档)
        archive_dir = os.path.join("archives", "raw", date_str, time_str)
        os.makedirs(archive_dir, exist_ok=True)
        
        for cat_name, data_list in categorized_data.items():
            file_path = os.path.join(archive_dir, FILES[cat_name])
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data_list, f, ensure_ascii=False, indent=2)
            print(f"📦 [Archive] 归档成功: {file_path}")

        # 3. 更新 Index (索引文件)
        history_dir = "history"
        os.makedirs(history_dir, exist_ok=True)
        index_file = os.path.join(history_dir, "raw_index.json")
        
        history_list = []
        if os.path.exists(index_file):
            try:
                with open(index_file, "r", encoding="utf-8") as f:
                    history_list = json.load(f)
            except: pass
        
        # 避免重复添加 (简单去重)
        current_entry = {"display": f"{date_str} {time_str.replace('-', ':')}", "path": f"archives/raw/{date_str}/{time_str}/"}
        # 检查是否已经存在相同的 path
        if not any(entry['path'] == current_entry['path'] for entry in history_list):
            history_list.insert(0, current_entry) # 最新在最前
            # 限制索引长度，比如最近 500 次
            if len(history_list) > 500: history_list = history_list[:500]
            
            with open(index_file, "w", encoding="utf-8") as f:
                json.dump(history_list, f, ensure_ascii=False, indent=2)
            print(f"📇 [Index] 索引更新完毕")

    except Exception as e:
        print(f"❌ 发生错误: {e}")

if __name__ == "__main__":
    # ⚠️ 关键修改：直接运行一次就结束，不要 while True 循环！
    run_spider()
    print("🎉 爬取结束，准备退出...")