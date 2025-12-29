import json
import os
import time
from datetime import datetime

# ================= 📦 新版 SDK 导入 =================
# 必须先在 requirements.txt 或 workflow 中安装 google-genai
from google import genai
from google.genai import types

# ================= 🔧 智能配置区域 =================
if os.environ.get("GITHUB_ACTIONS"):
    print("☁️ 检测到云端环境：禁用代理，使用直连...")
else:
    print("🏠 检测到本地环境：启用代理 17890...")
    PROXY_PORT = "17890"
    os.environ["HTTP_PROXY"] = f"http://127.0.0.1:{PROXY_PORT}"
    os.environ["HTTPS_PROXY"] = f"http://127.0.0.1:{PROXY_PORT}"

# 💡 提示：新版 SDK 通常使用 'gemini-2.0-flash' 或 'gemini-1.5-flash'
# 如果你的账号有 'gemini-3.0-flash' 权限，可以在这里修改
MODEL_NAME = "gemini-3-flash-preview"

FILES_CONFIG = {
    "finance": { "in": "data_finance.json", "out": "analysis_finance.json", "type": "finance", "key_env": "KEY_FINANCE" },
    "global": { "in": "data_global.json",  "out": "analysis_global.json",  "type": "global",  "key_env": "KEY_GLOBAL" },
    "tech": { "in": "data_tech.json",    "out": "analysis_tech.json",    "type": "tech",    "key_env": "KEY_TECH" },
    "general": { "in": "data_general.json", "out": "analysis_general.json", "type": "general", "key_env": "KEY_GENERAL" }
}

def load_and_simplify(filepath):
    if not os.path.exists(filepath): return None, None
    with open(filepath, "r", encoding="utf-8") as f: raw_data = json.load(f)
    
    simplified_lines = []
    url_lookup = {}
    
    # 保持较大的读取量，确保 AI 有足够素材
    TOTAL_SAFETY_CAP = 2000 
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
    
    # 提示词保持原样，未做修改
    if module_type == "finance":
        return f"""
        {base_info}
        角色：金牌财经编辑。
        任务：生成一份条理清晰、分点陈述的市场早报。
        
        【economy_summary 格式严格要求】：
        禁止写成一段话！必须按以下【标题】+【分点】格式输出，并在每点之间换行：
        
        【📈 市场核心】
        1. 核心事件A...
        2. 核心事件B...
        
        【💰 资金与情绪】
        1. 资金流向分析...
        2. 市场情绪判断...
        
        【🏗️ 行业异动】
        1. 领涨板块...
        2. 领跌板块...

        输出 JSON: {{ "economy_summary": "...", "items": [ {{ "title": "...", "sentiment": "Bullish/Bearish/Mixed", "impact": "...", "summary": "..." }} ] }}
        {format_instruction}
        """
    elif module_type == "tech":
        return f"""
        {base_info}
        角色：科技前沿观察员。
        
        【summary 格式严格要求】：
        分点输出，禁止长篇大论：
        
        【🚀 颠覆性突破】
        1. ...
        
        【🤖 AI 与大模型】
        1. ...
        
        【📱 硬件与芯片】
        1. ...
        
        输出 JSON: {{ "summary": "...", "items": [ {{ "title": "...", "summary": "...", "prediction": "...", "special_note": "AI/芯片/无" }} ] }}
        {format_instruction}
        """
    elif module_type == "global":
        return f"""
        {base_info}
        角色：国际局势观察员。
        
        【economy_summary 格式严格要求】：
        分点输出：
        
        【🌍 地缘焦点】
        1. ...
        
        【⚔️ 战争与冲突】
        1. ...
        
        【🤝 外交动态】
        1. ...
        
        输出 JSON: {{ "economy_summary": "...", "items": [ {{ "title": "...", "sentiment": "...", "impact": "...", "summary": "..." }} ] }}
        {format_instruction}
        """
    else:
        return f"""
        {base_info}
        角色：热搜挖掘机。
        
        【summary 格式严格要求，字数不低于400字】：
        分点输出：
        
        【🔥 全民热议】
        1. ...
        
        【🍉 吃瓜一线】
        1. ...
        
        输出 JSON: {{ "summary": "...", "items": [ {{ "title": "...", "comment": "..." }} ] }}
        {format_instruction}
        """

def process_module(key, config):
    print(f"🔄 Processing: {key} (Model: {MODEL_NAME})")
    
    current_api_key = os.environ.get(config['key_env']) or os.environ.get("GOOGLE_API_KEY")
    if not current_api_key:
        print(f"❌ Skip {key}: No API Key found.")
        return

    # ================= ⚡ 新版 SDK 调用逻辑 =================
    try:
        # 1. 初始化客户端
        client = genai.Client(api_key=current_api_key)
        
        slim_text, url_lookup = load_and_simplify(config['in'])
        if not slim_text: return
        
        # 2. 发送请求 (使用新版 generate_content 方法)
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=get_prompt(config['type'], slim_text),
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                safety_settings=[
                    types.SafetySetting(
                        category="HARM_CATEGORY_HARASSMENT",
                        threshold="BLOCK_NONE"
                    ),
                    types.SafetySetting(
                        category="HARM_CATEGORY_HATE_SPEECH",
                        threshold="BLOCK_NONE"
                    ),
                    types.SafetySetting(
                        category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
                        threshold="BLOCK_NONE"
                    ),
                    types.SafetySetting(
                        category="HARM_CATEGORY_DANGEROUS_CONTENT",
                        threshold="BLOCK_NONE"
                    )
                ]
            )
        )
        
        # 3. 解析 JSON 响应
        # 新版 SDK 的 response.text 直接返回字符串
        if not response.text:
            print(f"⚠️ Warning {key}: Empty response from API.")
            return

        ai_json = json.loads(response.text)
        
        # 4. URL 回填逻辑 (保持不变)
        for item in ai_json.get("items", []):
            t = item.get("title")
            item['url'] = "#"
            # 简单的模糊匹配
            for raw_t, raw_u in url_lookup.items():
                if t and (t in raw_t or raw_t in t):
                    item['url'] = raw_u
                    break
        
        ai_json['date'] = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        # 5. 保存文件
        with open(config['out'], "w", encoding="utf-8") as f:
            json.dump(ai_json, f, ensure_ascii=False, indent=2)
        print(f"✅ Generated: {config['out']}")
        
    except Exception as e:
        print(f"❌ Error {key}: {e}")
        # 打印更多调试信息（如果存在）
        if hasattr(e, 'response'):
             print(f"🔍 API Response Info: {e.response}")

if __name__ == "__main__":
    for key, config in FILES_CONFIG.items():
        process_module(key, config)
        # 稍微增加延时，防止触发新 API 的速率限制
        time.sleep(8)


