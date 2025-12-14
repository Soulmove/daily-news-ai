import json
import os
import time
import google.generativeai as genai
from datetime import datetime
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# ================= 🔧 智能配置区域 =================
if os.environ.get("GITHUB_ACTIONS"):
    print("☁️ 检测到云端环境：禁用代理，使用直连...")
else:
    print("🏠 检测到本地环境：启用代理 17890...")
    PROXY_PORT = "17890"
    os.environ["HTTP_PROXY"] = f"http://127.0.0.1:{PROXY_PORT}"
    os.environ["HTTPS_PROXY"] = f"http://127.0.0.1:{PROXY_PORT}"

# 🔒 锁定 gemini-2.5-flash
MODEL_NAME = "gemini-2.5-flash"

FILES_CONFIG = {
    "finance": { "in": "data_finance.json", "out": "analysis_finance.json", "type": "finance", "key_env": "KEY_FINANCE" },
    "global": { "in": "data_global.json",  "out": "analysis_global.json",  "type": "global",  "key_env": "KEY_GLOBAL" },
    "tech": { "in": "data_tech.json",    "out": "analysis_tech.json",    "type": "tech",    "key_env": "KEY_TECH" },
    "general": { "in": "data_general.json", "out": "analysis_general.json", "type": "general", "key_env": "KEY_GENERAL" }
}

safety_settings = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

def load_and_simplify(filepath):
    if not os.path.exists(filepath): return None, None
    with open(filepath, "r", encoding="utf-8") as f: raw_data = json.load(f)
    
    simplified_lines = []
    url_lookup = {}
    
    # 保持较大的读取量，确保 AI 有足够素材
    TOTAL_SAFETY_CAP = 1000 
    total_count = 0
    
    for platform in raw_data:
        site_id = platform.get('id', 'unknown')
        items = platform.get('items', [])
        for item in items:
            if total_count >= TOTAL_SAFETY_CAP: break
            title = item.get('title', '').strip()
            url = item.get('url', '')
            if title:
                simplified_lines.append(f"[{site_id}]{title}")
                url_lookup[title] = url
                total_count += 1
        if total_count >= TOTAL_SAFETY_CAP: break
                
    print(f"📊 {filepath} 读取到 {total_count} 条数据。")
    return "\n".join(simplified_lines), url_lookup

def get_prompt(module_type, data_text):
    base_info = f"Date:{datetime.now().strftime('%Y-%m-%d')}\nData:\n{data_text}"
    format_instruction = "Return strictly pure JSON only. No Markdown."
    
    # 🔥🔥🔥 核心修改区：超强版 Prompt 🔥🔥🔥
    if module_type == "finance":
        return f"""
        {base_info}
        角色：一个只说中文的首席金融分析师。
        任务：从海量数据中挖掘有价值的市场信息。
        要求：
        1. 【数量强制】：至少输出 30 条以上独立的新闻条目 (Items)。禁止过度合并！
        2. 【覆盖广度】：必须包含：宏观政策(央行/财政)、股市异动(个股/板块)、行业动态(地产/汽车/科技)、国际金融(美联储/汇率)、大宗商品。
        3. 【细节保留】：summary 必须包含具体数字（如涨跌幅%、金额、日期），拒绝模糊描述。
        4. 【深度综述】：economy_summary 需 300-500 字，深度复盘今日资金流向与市场情绪。
        
        输出 JSON: {{ "economy_summary": "...", "items": [ {{ "title": "...", "sentiment": "Bullish/Bearish/Mixed", "impact": "具体板块/股票", "summary": "详实分析..." }} ] }}
        {format_instruction}
        """
    elif module_type == "tech":
        return f"""
        {base_info}
        角色：一个只说中文的科技产业观察家。
        任务：从海量数据中挖掘有价值的市场信息。
        要求：
        1. 【数量强制】：至少输出 20-50 条独立新闻。
        2. 【细分领域】：覆盖 AI大模型、芯片半导体、智能硬件(手机/汽车)、互联网巨头动态、前沿黑科技。
        3. 【深度解读】：summary 需解释技术原理或商业影响；prediction 必须给出具体预测。
        4. 【特别关注】：AI 相关新闻必须详细展开。
        
        输出 JSON: {{ "summary": "...", "items": [ {{ "title": "...", "summary": "...", "prediction": "...", "special_note": "AI/芯片/无" }} ] }}
        {format_instruction}
        """
    elif module_type == "global":
        return f"""
        {base_info}
        角色：一个只说中文的国际局势专家。
        任务：从海量数据中挖掘有价值的市场信息。
        要求：
        1. 【数量强制】：至少输出 10 条以上。
        2. 【关注点】：战争冲突、大国外交、能源危机、贸易制裁。
        3. 【经济关联】：必须分析该政治事件对经济/市场的潜在冲击。
        
        输出 JSON: {{ "economy_summary": "...", "items": [ {{ "title": "...", "sentiment": "...", "impact": "...", "summary": "..." }} ] }}
        {format_instruction}
        """
    else:
        return f"""
        {base_info}
        Role: 一个只说中文的互联网舆情分析师。
        任务：提炼全网热点。
        要求：
        1. 【数量强制】：至少 30 条。
        2. 【去重】：去除广告，保留社会民生、娱乐八卦、网络热梗。
        3. 【点评】：comment 需辛辣幽默。
        
        输出 JSON: {{ "summary": "...", "items": [ {{ "title": "...", "comment": "..." }} ] }}
        {format_instruction}
        """

def process_module(key, config):
    print(f"🔄 Processing: {key} (Model: {MODEL_NAME})")
    
    current_api_key = os.environ.get(config['key_env']) or os.environ.get("GOOGLE_API_KEY")
    if not current_api_key:
        print(f"❌ Skip {key}: No API Key found.")
        return

    genai.configure(api_key=current_api_key)
    
    slim_text, url_lookup = load_and_simplify(config['in'])
    if not slim_text: return
    
    try:
        model = genai.GenerativeModel(MODEL_NAME)
        response = model.generate_content(
            get_prompt(config['type'], slim_text),
            safety_settings=safety_settings,
            generation_config={"response_mime_type": "application/json"}
        )
        
        ai_json = json.loads(response.text)
        
        # 链接还原逻辑
        for item in ai_json.get("items", []):
            t = item.get("title")
            item['url'] = "#"
            # 模糊匹配优化：只要标题包含关键词就算匹配
            for raw_t, raw_u in url_lookup.items():
                if t in raw_t or raw_t in t:
                    item['url'] = raw_u
                    break
        
        ai_json['date'] = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        with open(config['out'], "w", encoding="utf-8") as f:
            json.dump(ai_json, f, ensure_ascii=False, indent=2)
        print(f"✅ Generated: {config['out']} (包含 {len(ai_json.get('items', []))} 条新闻)")
        
    except Exception as e:
        print(f"❌ Error {key}: {e}")

if __name__ == "__main__":
    for key, config in FILES_CONFIG.items():
        process_module(key, config)
        time.sleep(5) # 稍微延长间隔，让 Key 喘口气

