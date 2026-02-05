import json
import os
import time
import random
from datetime import datetime
from google import genai
from google.genai import types

# ================= 🔧 模型与策略配置 =================
MODEL_REGISTRY = {
    "smart": "gemini-3-flash-preview",       # 聪明/专业角色用
    "cheap": "gemini-2.5-flash", # 普通/吃瓜角色用
}

DEFAULT_MODEL = "cheap"

# 🌟 智能分组关键词：包含这些词的角色会分配给 "smart" 模型
HIGH_INTEL_KEYWORDS = [
    "医生", "分析师", "博主", "老师", "创业者", "捞偏门", 
    "大厂", "律师", "公务员", "老干部", "首富", 
    "马斯克", "马云", "老板", "商家", "学霸", "失业人员"
]

# ================= 🎭 40+ 种职业与人设定义 (已扩展) =================
PERSONAS = [
    # --- 新增角色 ---
    "跨境电商商家 (焦虑/关注汇率与关税)", 
    "世界首富 (凡尔赛/宏观视角)", 
    "上市公司老板 (画大饼/危机感)", 
    "国内电商商家 (卷王/抱怨退货率)", 
    "埃隆马斯克 (硬核/第一性原理/英语口癖)", 
    "马云 (退隐/哲理/太极)", 
    "失业人员 (迷茫/自嘲/寻找机会)", 
    "高中生 (刷题累/吐槽教育/玩梗)", 
    "数学老师 (逻辑严密/喜欢推理)", 
    "语文老师 (感性/引经据典)", 
    "捞偏门的人 (容易找点捷径突破口和有对信息敏锐的洞察能力/能注意到平常人注意不到的信息差)", 
    
    # --- 原有角色 ---
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
    valid_keys = [os.environ.get(k) for k in KEY_VARS if os.environ.get(k)]
    if not valid_keys:
        print("❌ 错误：未检测到 API Key")
        return None
    return genai.Client(api_key=random.choice(valid_keys), http_options={'api_version': 'v1alpha'})

def load_news_summary(filepath):
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
    batches = {}
    for persona in PERSONAS:
        assigned_alias = DEFAULT_MODEL
        for kw in HIGH_INTEL_KEYWORDS:
            if kw in persona:
                assigned_alias = "smart"
                break
        real_model_name = MODEL_REGISTRY.get(assigned_alias, MODEL_REGISTRY[DEFAULT_MODEL])
        if real_model_name not in batches: batches[real_model_name] = []
        batches[real_model_name].append(persona)
    return batches

def process_batch(client, model_name, personas_list, news_text, category_name):
    if not personas_list: return []
    print(f"   ⚡ [{model_name}] 生成 {len(personas_list)} 个角色评论...")
    
    # 🔥🔥🔥 核心 Prompt 修改：增加随机性和长短不一的要求 🔥🔥🔥
    prompt = f"""
    你是一个全网舆情模拟器。请阅读今天的【{category_name}】板块热搜新闻：
    {news_text}

    任务：模拟以下列表中的不同职业/人设的真实网友，针对上述新闻发表评论。
    
    【待模拟角色列表】：
    {', '.join(personas_list)}

    【⚠️ 严格的风格要求】：
    1. **完全代入角色**：如果是马斯克就要像马斯克（提第一性原理/火星/Doge），如果是学生就要像学生（作业/考试）。
    2. **字数随机化**：
       - 大部分评论保持简短（30-60字）。
       - **必须有 3-5 个角色发表“长篇大论”**（100-150字），进行深度分析或情绪发泄。
       - 极少数角色可以只发几个字（如“牛逼”、“甚至有点想笑”）。
    3. **Emoji 随机化**：
       - 有些人（如00后/销售）喜欢狂用 Emoji。
       - 有些人（如老师/大佬/老干部）非常严肃，**绝对不用** Emoji。
    4. **拒绝死板**：不要每个人的格式都一样，要像真实的评论区一样混乱而真实。

    输出 JSON 数组格式：
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
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.9) # 温度调高，增加随机性
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"   ⚠️ 错误: {e}")
        return []

def generate_comments(category_key, config):
    client = get_random_client()
    if not client: return
    print(f"🔄 处理板块：{config['name']}")
    news_text = load_news_summary(config['in'])
    if not news_text: return

    batches = assign_model_to_personas()
    all_comments = []

    for model_name, personas_sublist in batches.items():
        time.sleep(1)
        batch_client = get_random_client() or client
        comments = process_batch(batch_client, model_name, personas_sublist, news_text, config['name'])
        if comments: all_comments.extend(comments)

    random.shuffle(all_comments)
    
    # 随机选取 30 条左右，避免太多
    final_comments = all_comments[:35] if len(all_comments) > 35 else all_comments

    if final_comments:
        output_data = { "date": datetime.now().strftime("%Y-%m-%d %H:%M"), "category": category_key, "comments": final_comments }
        with open(config['out'], "w", encoding="utf-8") as f: json.dump(output_data, f, ensure_ascii=False, indent=2)
        print(f"✅ 完成！生成 {len(final_comments)} 条评论。\n")

if __name__ == "__main__":
    print(f"🤖 AI 模拟评论启动...")
    for key, config in FILES_CONFIG.items():
        generate_comments(key, config)
        time.sleep(2)