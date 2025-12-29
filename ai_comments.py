import json
import os
import time
import random
from datetime import datetime
from google import genai
from google.genai import types

# ================= 🔧 模型与策略配置 (可自定义) =================

# 1. 定义你可用的模型池
# 格式: "别名": "谷歌官方模型ID"
MODEL_REGISTRY = {
    "smart": "gemini-3-flash-preview",       # 或 gemini-2.0-pro-exp-02-05 (用于需要深度的评论)
    "cheap": "gemini-2.5-flash", # 或 gemini-1.5-flash (用于普通吃瓜评论，节省成本)
    "latest": "gemini-2.5-flash"     # 你想尝试的新模型
}

# 2. 默认模型 (如果没有特别指定，就用这个)
DEFAULT_MODEL = "cheap"

# 3. 角色分组配置
# 在这里的关键词会被分配给 "smart" 模型，其他的默认去 "cheap"
# 比如：医生、分析师、博主 需要更有逻辑，所以用好模型
HIGH_INTEL_KEYWORDS = [
    "医生", "分析师", "博主", "老师", "创业者", 
    "大厂", "律师", "公务员", "老干部", "悲观主义者"
]

# ================= 🎭 30种职业与人设定义 =================
# 程序会自动根据上面的关键词，把这些人分成两组去跑不同的 AI
PERSONAS = [
    "出租车司机 (老练/愤世嫉俗)", "大一新生 (清澈/充满希望)", "菜市场大妈 (务实/关心物价)", 
    "互联网大厂P7 (焦虑/满口黑话)", "退休老干部 (严肃/宏大叙事)", "三甲医院医生 (冷静/疲惫)", 
    "全职妈妈 (细腻/担忧)", "城中村房东 (悠闲/凡尔赛)", "小学班主任 (操心/严厉)", 
    "金融分析师 (理性/数据流)", "不知名摇滚乐手 (叛逆/讽刺)", "小卖部老板 (八卦/通透)", 
    "大模型创业者 (狂热/激进)", "外卖小哥 (匆忙/最懂人间)", "海归留学生 (夹杂英文/比较视角)", 
    "工地包工头 (豪爽/直接)", "考研党 (紧绷/迷茫)", "资深股民 (大起大落/甚至有点疯)", 
    "00后整顿职场 (直接/无所谓)", "古风汉服爱好者 (文艺/感性)", "科技博主 (专业/挑刺)", 
    "家庭主妇 (精打细算)", "中学物理老师 (严谨/较真)", "国企员工 (稳重/打太极)", 
    "健身教练 (正能量/鸡血)", "二次元宅男 (玩梗/幽默)", "美容院老板娘 (圆滑/颜控)", 
    "基层公务员 (谨慎/正能量)", "暴发户 (炫耀/粗俗)", "AI悲观主义者 (恐惧/末日论)"
]

# ================= 📂 文件配置 =================
FILES_CONFIG = {
    "finance": { "in": "data_finance.json", "out": "comments_finance.json", "name": "财经/市场" },
    "global": { "in": "data_global.json",  "out": "comments_global.json",  "name": "国际/宏观" },
    "tech": { "in": "data_tech.json",    "out": "comments_tech.json",    "name": "科技/AI" },
    "general": { "in": "data_general.json", "out": "comments_general.json", "name": "娱乐/吃瓜" }
}

KEY_VARS = ["KEY_1", "KEY_2", "KEY_3", "KEY_4", "KEY_5", "KEY_6", "KEY_7", "KEY_8"]

def get_random_client():
    """随机抽取一个有效的 Client"""
    valid_keys = [os.environ.get(k) for k in KEY_VARS if os.environ.get(k)]
    if not valid_keys:
        print("❌ 错误：未检测到任何 API Key，请在 Secrets 中配置 KEY_1 到 KEY_8")
        return None
    selected_key = random.choice(valid_keys)
    # 统一使用 v1alpha 以获得最大模型兼容性
    return genai.Client(api_key=selected_key, http_options={'api_version': 'v1alpha'})

def load_news_summary(filepath):
    """读取新闻数据"""
    if not os.path.exists(filepath): return ""
    with open(filepath, "r", encoding="utf-8") as f: data = json.load(f)
    summary = []
    count = 0
    for platform in data:
        items = platform.get('items', [])
        for item in items:
            if count >= 15: break
            summary.append(f"- {item.get('title')}")
            count += 1
    return "\n".join(summary)

def assign_model_to_personas():
    """将角色分配到不同的模型批次"""
    batches = {}
    
    for persona in PERSONAS:
        # 默认模型
        assigned_alias = DEFAULT_MODEL
        
        # 检查是否属于高智商组
        for kw in HIGH_INTEL_KEYWORDS:
            if kw in persona:
                assigned_alias = "smart"
                break
        
        real_model_name = MODEL_REGISTRY.get(assigned_alias, MODEL_REGISTRY[DEFAULT_MODEL])
        
        if real_model_name not in batches:
            batches[real_model_name] = []
        batches[real_model_name].append(persona)
        
    return batches

def process_batch(client, model_name, personas_list, news_text, category_name):
    """处理单个批次的生成请求"""
    if not personas_list: return []
    
    print(f"   ⚡ 使用模型 [{model_name}] 生成 {len(personas_list)} 个角色的评论...")
    
    prompt = f"""
    你是一个全网舆情模拟器。请阅读今天的【{category_name}】板块热搜新闻：
    {news_text}

    任务：模拟以下列表中的不同职业/人设的真实网友，针对上述新闻发表简短评论。
    
    【待模拟角色列表】：
    {', '.join(personas_list)}

    要求：
    1. **完全代入角色**：语气、用词、关注点必须符合人设。
    2. **情绪多样化**：包含愤怒、调侃、焦虑、开心、讽刺等不同情绪。
    3. **口语化**：像真实的社交媒体评论，不要书面语，可以带Emoji。
    4. **严格JSON输出**：只返回 JSON 数组，不要Markdown标记。

    输出格式示例：
    [
        {{
            "role": "角色全名",
            "name": "有趣的网名",
            "content": "评论内容...",
            "emotion": "情绪标签"
        }}
    ]
    """

    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.85 # 稍微调高一点，增加多样性
            )
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"   ⚠️ 模型 {model_name} 生成部分失败: {e}")
        return []

def generate_comments(category_key, config):
    client = get_random_client()
    if not client: return

    print(f"🔄 [开始任务] 板块：{config['name']}")
    
    news_text = load_news_summary(config['in'])
    if not news_text:
        print(f"⚠️ {config['in']} 无数据，跳过。")
        return

    # 1. 分配任务批次
    batches = assign_model_to_personas()
    all_comments = []

    # 2. 分批次调用不同模型
    for model_name, personas_sublist in batches.items():
        # 这里可以加入随机延时，防止 API 限流
        time.sleep(1) 
        
        # 为了容错，每个批次重新获取一个 Client (负载均衡)
        batch_client = get_random_client() or client
        
        comments = process_batch(batch_client, model_name, personas_sublist, news_text, config['name'])
        if comments:
            all_comments.extend(comments)

    # 3. 结果混洗 (避免同一种模型的评论挨在一起)
    random.shuffle(all_comments)

    # 4. 保存结果
    if all_comments:
        output_data = {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "category": category_key,
            "comments": all_comments
        }
        
        with open(config['out'], "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
            
        print(f"✅ {config['out']} 生成完毕！共 {len(all_comments)} 条评论。\n")
    else:
        print(f"❌ {config['name']} 生成失败，无有效评论。\n")

if __name__ == "__main__":
    print(f"🤖 多模型混合评论生成器启动...")
    print(f"📋 模型注册表: {json.dumps(MODEL_REGISTRY, indent=2)}")
    
    for key, config in FILES_CONFIG.items():
        generate_comments(key, config)

        time.sleep(3) # 板块之间稍微歇一下
