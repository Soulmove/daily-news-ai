import requests
import json
import time
import os
from datetime import datetime

# ================= 配置区域 =================
# 抓取间隔 (2小时)
INTERVAL = 7200 

# 定义四个分类的数据文件名
FILES = {
    "finance": "data_finance.json",  # 财经
    "tech": "data_tech.json",       # 科技
    "global": "data_global.json",   # 国际
    "general": "data_general.json"  # 综合/娱乐
}

# ================= 核心分类字典 =================
# 在这里定义哪些 ID 属于哪个分类
# 你可以根据需要把 id 从一个列表移动到另一个列表
CATEGORY_MAP = {
    "finance": [
        "wallstreetcn-hot", "wallstreetcn-news", "wallstreetcn-quick",
        "cls-hot", "cls-depth", "cls-telegraph",
        "xueqiu-hotstock", "gelonghui", "jin10", 
        "mktnews-flash", "fastbull-express", "fastbull-news"
    ],
    "tech": [
        "36kr-quick", "36kr-renqi", 
        "sspai", "coolapk", "ithome", "huxiu", 
        "geekpark", "qbitai", "producthunt", 
        "github-trending-today", "hackernews", "v2ex-share", 
        "freebuf", "solidot"
    ],
    "global": [
        "zaobao", "sputniknewscn", "cankaoxiaoxi", "kaopu"
    ],
    "general": [
        "zhihu", "weibo", "douyin", "baidu", 
        "bilibili-hot-search", "tieba", "toutiao", 
        "thepaper", "douban", "hupu", 
        "chongbuluo-hot", "chongbuluo-latest", "nowcoder"
    ]
}

# 把所有 ID 合并成一个大列表，用来发请求
ALL_SOURCES = []
for ids in CATEGORY_MAP.values():
    ALL_SOURCES.extend(ids)

# ===========================================

def get_current_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def run_spider():
    print(f"[{get_current_time()}] 🚀 开始新一轮抓取...")
    
    url = "https://newsnow.busiyi.world/api/s/entire"
    
    headers = {
        "content-type": "application/json",
        "origin": "https://newsnow.busiyi.world",
        "referer": "https://newsnow.busiyi.world/c/hottest",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36 Edg/143.0.0.0"
    }

    payload = { "sources": ALL_SOURCES }

    try:
        print("⏳ 正在请求数据...")
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        
        if response.status_code == 200:
            raw_data = response.json()
            print(f"📦 成功收到数据，开始分类处理...")

            # 初始化 4 个空列表，用来装不同分类的数据
            categorized_data = {
                "finance": [],
                "tech": [],
                "global": [],
                "general": []
            }

            # 遍历原始数据，进行分拣
            for platform in raw_data:
                site_id = platform.get('id')
                items = platform.get('items', [])
                
                if not items: continue

                # 【极简处理】只保留 title 和 url
                clean_items = []
                for item in items:
                    clean_items.append({
                        "title": item.get('title', '').strip(),
                        "url": item.get('url', '')
                    })

                # 构建精简后的平台对象
                clean_platform = {
                    "id": site_id,
                    "items": clean_items
                }

                # 判断这个平台属于哪个分类，扔进对应的列表
                found_category = False
                for cat_name, ids_list in CATEGORY_MAP.items():
                    if site_id in ids_list:
                        categorized_data[cat_name].append(clean_platform)
                        found_category = True
                        break
                
                # 如果没在字典里定义的，默认扔进 general
                if not found_category:
                    categorized_data["general"].append(clean_platform)

            # 写入 4 个独立文件
            for cat_name, data_list in categorized_data.items():
                filename = FILES[cat_name]
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(data_list, f, ensure_ascii=False, indent=2) # indent=2 为了让你打开看时更清晰
                print(f"✅ 已生成: {filename} (包含 {len(data_list)} 个平台)")

        else:
            print(f"❌ 请求失败: {response.status_code}")

    except Exception as e:
        print(f"❌ 发生错误: {e}")

# ================= 主程序 =================
if __name__ == "__main__":
    print(f"🤖 分类爬虫已启动！")
    print(f"数据将分别保存为: {', '.join(FILES.values())}")
    
    while True:
        run_spider()
        print(f"😴 休息 {INTERVAL} 秒...")
        time.sleep(INTERVAL)