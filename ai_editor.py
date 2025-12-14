import json
import os
import time
import google.generativeai as genai
from datetime import datetime
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# ================= 🔧 智能配置区域 =================
# 自动检测是在 GitHub 云端还是本地
if os.environ.get("GITHUB_ACTIONS"):
    print("☁️ 检测到云端环境：禁用代理，使用直连...")
else:
    print("🏠 检测到本地环境：启用代理 17890...")
    PROXY_PORT = "17890"
    os.environ["HTTP_PROXY"] = f"http://127.0.0.1:{PROXY_PORT}"
    os.environ["HTTPS_PROXY"] = f"http://127.0.0.1:{PROXY_PORT}"

# 模型名称 (使用 gemini-pro 以支持长文本处理)
MODEL_NAME = "gemini-pro"

# 定义模块对应的 Key 环境变量名 和 文件配置
FILES_CONFIG = {
    "finance": { 
        "in": "data_finance.json", 
        "out": "analysis_finance.json", 
        "type": "finance",
        "key_env": "KEY_FINANCE"
    },
    "global": { 
        "in": "data_global.json",  
        "out": "analysis_global.json",  
        "type": "global",
        "key_env": "KEY_GLOBAL"
    },
    "tech": { 
        "in": "data_tech.json",    
        "out": "analysis_tech.json",    
        "type": "tech",
        "key_env": "KEY_TECH"
    },
    "general": { 
        "in": "data_general.json", 
        "out": "analysis_general.json", 
        "type": "general",
        "key_env": "KEY_GENERAL"
    }
}

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
    
    # 🔥 修改点：移除单源限制，改为总量的“熔断保护”
    # 以前是每个平台只读 25 条，现在改为单个模块最多读 500 条（防止 API 超时）
    # 500 条足够覆盖该模块下所有平台的全部热搜了
    TOTAL_SAFETY_CAP = 500 
    total_count = 0
    
    for platform in raw_data:
        site_id = platform.get('id', 'unknown')
        items = platform.get('items', [])
        
        # 这里不再限制单个平台的 items 数量，有多少读多少
        for item in items:
            if total_count >= TOTAL_SAFETY_CAP: 
                print(f"⚠️ 达到安全上限 {TOTAL_SAFETY_CAP} 条，停止读取剩余数据以保护 API。")
                break
            
            title = item.get('title', '').strip()
            url = item.get('url', '')
            if title:
                # 格式优化：去掉多余空格，节省 Token
                simplified_lines.append(f"[{site_id}]{title}")
                url_lookup[title] = url
                total_count += 1
        
        if total_count >= TOTAL_SAFETY_CAP: break
                
    print(f"📊 {filepath} 共读取到 {total_count} 条有效数据供 AI 分析。")
    return "\n".join(simplified_lines), url_lookup

def get_prompt(module_type, data_text):
    base_info = f"Date:{datetime.now().strftime('%Y-%m-%d')}\nData(Full List):\n{data_text}"
    format_instruction = "Strictly JSON format only. No Markdown."
    
    # 针对海量数据的 Prompt 优化
    if module_type == "finance":
        return f"""
        {base_info}
        Role: 首席金融分析师。
        任务：
        1. 【全量扫描】：你现在拥有该板块所有的实时热点数据。请综合分析所有信息。
        2. 【去重与聚合】：合并讨论同一事件的条目。
        3. 【情绪与影响】：判断利好(Bullish)/利空(Bearish)，并指出受影响的行业。
        4. 【深度综述】：economy_summary 必须包含今日市场的核心主线、资金流向暗示以及宏观情绪。
        
        输出 JSON:
        {{ "economy_summary": "深度综述(300字)...", "items": [ {{ "title": "核心事件标题", "sentiment": "Bullish/Bearish/Mixed", "impact": "影响板块", "summary": "详细分析(含逻辑与预测)..." }} ] }}
        {format_instruction}
        """
    elif module_type == "tech":
        return f"""
        {base_info}
        Role: 科技产业观察家。
        任务：
        1. 【全量扫描】：分析列表中的每一条科技动态。
        2. 【筛选重磅】：从海量信息中提取最具颠覆性的技术或产品。
        3. 【趋势研判】：summary 需包含技术原理或商业影响；prediction 需预测未来格局。
        4. 【特别关注】：AI、芯片、大模型相关新闻请在 special_note 标注。
        
        输出 JSON:
        {{ "summary": "科技趋势总览(300字)...", "items": [ {{ "title": "新闻标题", "summary": "深度摘要...", "prediction": "未来预测...", "special_note": "AI/芯片/无" }} ] }}
        {format_instruction}
        """
    elif module_type == "global":
        return f"""
        {base_info}
        Role: 国际局势专家。
        任务：
        1. 扫描全球各地的突发事件和外交动态。
        2. economy_summary 需体现地缘政治对全球经济的潜在冲击。
        3. 重点关注：战争、大国博弈、能源危机。
        
        输出 JSON:
        {{ "economy_summary": "全球局势综述...", "items": [ {{ "title": "事件标题", "sentiment": "Bullish(和平)/Bearish(冲突)", "impact": "涉及国家", "summary": "深度推演..." }} ] }}
        {format_instruction}
        """
    else:
        return f"""
        {base_info}
        Role: 互联网舆情分析师。
        任务：
        1. 从海量热搜中提炼今日全民关注的焦点。
        2. comment 字段需要辛辣点评或深度解读社会现象。
        3. 忽略纯广告。
        
        输出 JSON:
        {{ "summary": "全网热点综述...", "items": [ {{ "title": "热搜标题", "comment": "深度点评..." }} ] }}
        {format_instruction}
        """

def process_module(key, config):
    print(f"🔄 开始处理模块: {key} (使用 Key: ...{config['key_env'][-4:] if config['key_env'] else 'None'})")
    
    # 1. 获取对应的 Key
    current_api_key = os.environ.get(config['key_env'])
    if not current_api_key:
        print(f"⚠️ 警告: 未找到环境变量 {config['key_env']}，尝试使用默认 GOOGLE_API_KEY")
        current_api_key = os.environ.get("GOOGLE_API_KEY")
    
    if not current_api_key:
        print(f"❌ 错误: 没有任何可用的 API Key，跳过 {key}")
        return

    # 2. 配置 GenAI
    genai.configure(api_key=current_api_key)
    
    # 3. 加载全量数据
    slim_text, url_lookup = load_and_simplify(config['in'])
    if not slim_text: 
        print(f"⚠️ {key} 模块没有原始数据，跳过。")
        return
    
    try:
        # 4. 调用 AI
        model = genai.GenerativeModel(MODEL_NAME)
        print(f"🤖 AI 正在阅读 {key} 模块的海量数据并撰写报告...")
        
        # 增加 timeout 防止数据太多导致连接中断
        response = model.generate_content(
            get_prompt(config['type'], slim_text),
            safety_settings=safety_settings,
            generation_config={"response_mime_type": "application/json"}
        )
        
        # 5. 解析结果
        ai_json = json.loads(response.text)
        
        # 6. 还原 URL
        for item in ai_json.get("items", []):
            t = item.get("title")
            item['url'] = "#"
            for raw_t, raw_u in url_lookup.items():
                # 模糊匹配以找回链接
                if t in raw_t or raw_t in t:
                    item['url'] = raw_u
                    break
        
        # 7. 补充日期
        ai_json['date'] = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        # 8. 保存
        with open(config['out'], "w", encoding="utf-8") as f:
            json.dump(ai_json, f, ensure_ascii=False, indent=2)
        print(f"✅ 成功生成: {config['out']}")
        
    except Exception as e:
        print(f"❌ 模块 {key} 处理失败: {e}")

if __name__ == "__main__":
    for key, config in FILES_CONFIG.items():
        process_module(key, config)
        # 多 Key 并发可以稍微快点，但为了稳妥还是停 2 秒
        time.sleep(2)
