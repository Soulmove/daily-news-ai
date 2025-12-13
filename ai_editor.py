import json
import os
import glob
import time
import google.generativeai as genai
from datetime import datetime
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# ================= 🔧 配置区域 =================
# 1. 代理设置
PROXY_PORT = "17890"  
os.environ["HTTP_PROXY"] = f"http://127.0.0.1:{PROXY_PORT}"
os.environ["HTTPS_PROXY"] = f"http://127.0.0.1:{PROXY_PORT}"

# 从环境变量获取 Key，如果本地没有设置，就用空字符串（防止报错）
# 稍后我会在 GitHub 网站上填入这个 Key，绝对安全
API_KEY = os.environ.get("GOOGLE_API_KEY") 

if not API_KEY:
    print("❌ 错误：未找到 GOOGLE_API_KEY 环境变量！")
    exit(1)

# 3. 模型选择 (1.5-flash 最稳)
MODEL_NAME = "gemini-2.5-flash"

# 4. 文件映射配置
FILES_CONFIG = {
    "finance": { "in": "data_finance.json", "out": "analysis_finance.json", "type": "finance" },
    "global":  { "in": "data_global.json",  "out": "analysis_global.json",  "type": "finance" }, # 国际复用财经逻辑
    "tech":    { "in": "data_tech.json",    "out": "analysis_tech.json",    "type": "tech" },
    "general": { "in": "data_general.json", "out": "analysis_general.json", "type": "general" }
}
# ===============================================

genai.configure(api_key=API_KEY)

# --- 🛡️ 关键设置：关闭安全过滤 ---
# 这一步非常重要！防止 AI 因为看到战争新闻就拒绝回答
safety_settings = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

# --- 🧹 辅助功能：自动清理旧文件 ---
def manage_backups(module_name, content):
    backup_dir = "backups"
    if not os.path.exists(backup_dir): os.makedirs(backup_dir)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(os.path.join(backup_dir, f"{module_name}_{timestamp}.json"), "w", encoding="utf-8") as f:
        json.dump(content, f, ensure_ascii=False)
    files = sorted(glob.glob(os.path.join(backup_dir, f"{module_name}_*.json")))
    if len(files) > 7:
        for old_file in files[:-7]: os.remove(old_file)

# --- 📖 读取并简化数据 ---
def load_and_simplify(filepath):
    if not os.path.exists(filepath):
        print(f"⚠️ 跳过: 找不到 {filepath}")
        return None, None
    
    with open(filepath, "r", encoding="utf-8") as f:
        raw_data = json.load(f)
    
    simplified_lines = []
    url_lookup = {} 

    for platform in raw_data:
        site_id = platform.get('id', 'unknown')
        items = platform.get('items', [])
        # 为了防止内容太长报错，这里先限制前 10 条
        for item in items[:10]: 
            title = item.get('title', '').strip()
            url = item.get('url', '')
            if title:
                simplified_lines.append(f"[{site_id}] {title}")
                url_lookup[title] = url # 存入字典方便找回
                
    return "\n".join(simplified_lines), url_lookup

# --- 🧠 Prompt 生成 ---
def get_prompt(module_type, data_text):
    base_info = f"今天是 {datetime.now().strftime('%Y-%m-%d')}。数据源如下：\n{data_text}"
    
    # 统一要求：必须是纯 JSON
    format_instruction = """
    请直接输出 JSON，不要使用 Markdown 代码块，不要包含 ```json 或 ```。
    确保 JSON 格式合法。
    """

    if module_type == "finance":
        return f"""
        {base_info}
        你是一名金融分析师。任务：
        1. 去重合并。
        2. 判断 sentiment (Bullish/Bearish/Neutral)。
        3. 指出 impact (影响的行业/股票)。
        4. 必须包含 economy_summary (市场情绪总结)。
        输出结构：
        {{
            "economy_summary": "总结...",
            "items": [ {{ "title": "...", "sentiment": "...", "impact": "...", "summary": "..." }} ]
        }}
        {format_instruction}
        """
    elif module_type == "tech":
        return f"""
        {base_info}
        你是一名科技评论家。任务：
        1. 去重。
        2. 预测 prediction (未来影响)。
        3. 标注 special_note (如有 GPT-5.2 等新模型，写功能点，否则留空)。
        输出结构：
        {{
            "summary": "总结...",
            "items": [ {{ "title": "...", "summary": "...", "prediction": "...", "special_note": "..." }} ]
        }}
        {format_instruction}
        """
    else: # general
        return f"""
        {base_info}
        你是热点观察员。任务：去重并评价。
        输出结构：
        {{
            "summary": "总结...",
            "items": [ {{ "title": "...", "comment": "..." }} ]
        }}
        {format_instruction}
        """

# --- 🚀 执行分析主逻辑 ---
def process_module(key, config):
    input_file = config['in']
    output_file = config['out']
    
    print(f"\n🔵 [1/3] 读取 {input_file} ...")
    slim_text, url_lookup = load_and_simplify(input_file)
    
    if not slim_text: 
        print(f"⚠️ {input_file} 是空的或不存在，跳过。")
        return

    print(f"🟡 [2/3] AI 正在分析 (模式: {config['type']})...")
    prompt = get_prompt(config['type'], slim_text)
    
    try:
        model = genai.GenerativeModel(MODEL_NAME)
        
        # 🌟 关键修改：强制使用 JSON MIME Type
        response = model.generate_content(
            prompt, 
            safety_settings=safety_settings, # 关闭安全拦截
            generation_config={"response_mime_type": "application/json"} # 强制 JSON
        )
        
        ai_text = response.text
        
        # 解析 JSON
        try:
            ai_json = json.loads(ai_text)
        except json.JSONDecodeError:
            # 如果万一还是解析失败，尝试手动清理一下
            cleaned_text = ai_text.replace("```json", "").replace("```", "").strip()
            ai_json = json.loads(cleaned_text)

        # 贴回 URL
        for item in ai_json.get("items", []):
            title = item.get("title")
            item['url'] = "#"
            # 简单的模糊匹配找回 URL
            for raw_title, raw_url in url_lookup.items():
                if title in raw_title or raw_title in title:
                    item['url'] = raw_url
                    break
        
        # 补全结构：如果是 finance 模式，确保 categories 结构适配前端
        final_output = ai_json
        # 为了兼容前端，我们可以在这里做一下结构调整，但目前保持原样即可
        # 只要前端能读取 analysis_finance.json 里的 items 即可

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(final_output, f, ensure_ascii=False, indent=2)
            
        manage_backups(key, final_output)
        print(f"🟢 [3/3] 成功！已生成 {output_file}")

    except Exception as e:
        print(f"❌ 处理 {key} 失败: {e}")
        # 如果是安全原因被屏蔽，打印出来
        try:
            if response.prompt_feedback:
                print(f"🛡️ 安全拦截信息: {response.prompt_feedback}")
        except:
            pass

if __name__ == "__main__":
    print(f"🤖 AI 主编上线 (JSON模式 + 无审查版)...")
    
    for key, config in FILES_CONFIG.items():
        print(f"------------------------------------------------")
        print(f"正在处理模块: {key}")
        process_module(key, config)
        print("⏳ 冷却 3 秒...")
        time.sleep(3)
        
    print("\n🎉 全部完成！")