import json
import os
import glob
import time
import google.generativeai as genai
from datetime import datetime
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# ================= 🔧 智能配置区域 =================
# 自动检测是在 GitHub 云端还是本地
if os.environ.get("GITHUB_ACTIONS"):
    print("☁️ 检测到云端环境：禁用代理，使用直连...")
    # 云端不需要设置 proxy
else:
    print("🏠 检测到本地环境：启用代理 17890...")
    PROXY_PORT = "17890"
    os.environ["HTTP_PROXY"] = f"http://127.0.0.1:{PROXY_PORT}"
    os.environ["HTTPS_PROXY"] = f"http://127.0.0.1:{PROXY_PORT}"

# 获取 Key
API_KEY = os.environ.get("GOOGLE_API_KEY")
if not API_KEY:
    # 本地测试用的备用 Key (如果在本地跑报错，可以在这里填你的Key，但上传时记得删掉或小心泄露)
    # 建议本地运行时在终端 set GOOGLE_API_KEY=xxx
    print("⚠️ 警告：未找到环境变量 GOOGLE_API_KEY")
    API_KEY = "AIzaSy..." # 如果本地跑，请临时填你的Key

MODEL_NAME = "gemini-1.5-flash"

FILES_CONFIG = {
    "finance": { "in": "data_finance.json", "out": "analysis_finance.json", "type": "finance" },
    "global":  { "in": "data_global.json",  "out": "analysis_global.json",  "type": "finance" },
    "tech":    { "in": "data_tech.json",    "out": "analysis_tech.json",    "type": "tech" },
    "general": { "in": "data_general.json", "out": "analysis_general.json", "type": "general" }
}

genai.configure(api_key=API_KEY)

# 关闭安全拦截
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
    for platform in raw_data:
        site_id = platform.get('id', 'unknown')
        items = platform.get('items', [])
        for item in items[:8]: # 稍微减少一点给 AI 的量，提高速度
            title = item.get('title', '').strip()
            url = item.get('url', '')
            if title:
                simplified_lines.append(f"[{site_id}] {title}")
                url_lookup[title] = url
    return "\n".join(simplified_lines), url_lookup

def get_prompt(module_type, data_text):
    base_info = f"Date: {datetime.now().strftime('%Y-%m-%d')}. Data:\n{data_text}"
    format_instruction = "Return strictly pure JSON. No markdown."
    
    if module_type == "finance":
        return f"""
        {base_info}
        Role: Financial Analyst. 
        Tasks: 1. Deduplicate. 2. Sentiment(Bullish/Bearish/Neutral). 3. Impact(Industries/Stocks). 4. Summary.
        Output JSON Structure:
        {{ "economy_summary": "Market Overview...", "items": [ {{ "title": "...", "sentiment": "...", "impact": "...", "summary": "..." }} ] }}
        {format_instruction}
        """
    elif module_type == "tech":
        return f"""
        {base_info}
        Role: Tech Reviewer.
        Tasks: 1. Deduplicate. 2. Prediction(Future impact). 3. Special Note(e.g. GPT-5).
        Output JSON Structure:
        {{ "summary": "Tech Trend...", "items": [ {{ "title": "...", "summary": "...", "prediction": "...", "special_note": "..." }} ] }}
        {format_instruction}
        """
    else:
        return f"""
        {base_info}
        Role: Social Observer. Task: Deduplicate and Comment.
        Output JSON Structure:
        {{ "summary": "Hot Topics...", "items": [ {{ "title": "...", "comment": "..." }} ] }}
        {format_instruction}
        """

def process_module(key, config):
    print(f"Start processing: {key}")
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
        
        # 修复 URL
        for item in ai_json.get("items", []):
            t = item.get("title")
            item['url'] = "#"
            for raw_t, raw_u in url_lookup.items():
                if t in raw_t or raw_t in t:
                    item['url'] = raw_u
                    break
        
        # 补充日期
        ai_json['date'] = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        with open(config['out'], "w", encoding="utf-8") as f:
            json.dump(ai_json, f, ensure_ascii=False, indent=2)
        print(f"✅ Generated: {config['out']}")
        
    except Exception as e:
        print(f"❌ Error {key}: {e}")

if __name__ == "__main__":
    for key, config in FILES_CONFIG.items():
        process_module(key, config)
        time.sleep(2)
