import google.generativeai as genai
import os
import time

# ================= 配置区域 =================
# 1. 你的 API Key (请确保没有多余的空格)
API_KEY = "AIzaSyBqUIl6PwE9SiF4DhqOSwvl2B1hbn_c1LE"  # <--- 请在这里粘贴你的 Key

# 2. 你的代理端口 (根据你之前的截图是 17890)
PROXY_PORT = "17890"

# 3. 使用最省流、最便宜的模型进行测试
MODEL_NAME = "gemini-2.5-flash" 
# ===========================================

# 自动配置网络环境 (挂梯子)
os.environ["HTTP_PROXY"] = f"http://127.0.0.1:{PROXY_PORT}"
os.environ["HTTPS_PROXY"] = f"http://127.0.0.1:{PROXY_PORT}"

def start_chat():
    print(f"🔌 正在尝试连接 Google 服务器 (端口 {PROXY_PORT})...")
    print(f"🤖 当前模型: {MODEL_NAME}")
    
    # 配置 API
    try:
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel(MODEL_NAME)
        
        # 开启一个聊天会话
        chat = model.start_chat(history=[])
        
        print("\n✅ 连接成功！现在你可以跟 AI 聊天了 (输入 'exit' 退出)")
        print("-" * 40)

        while True:
            # 获取用户输入
            user_input = input("\n你: ")
            
            if user_input.lower() in ['exit', 'quit', '退出']:
                print("👋 拜拜！")
                break
            
            if not user_input.strip():
                continue

            print("AI 正在思考...", end="\r")
            
            try:
                # 发送消息给 AI
                response = chat.send_message(user_input)
                # 打印回复
                print(f"AI: {response.text}")
                
            except Exception as e:
                print(f"\n❌ 发送失败: {e}")
                if "429" in str(e):
                    print("⚠️ 原因：额度超限。请不要发太快，歇一会再试。")
                elif "404" in str(e):
                    print("⚠️ 原因：模型名字写错了，或者该模型不可用。")
                else:
                    print("⚠️ 原因：可能是网络断了，或者 Key 无效。")

    except Exception as e:
        print(f"\n❌ 初始化失败，连不上服务器。")
        print(f"错误详情: {e}")
        print("💡 检查一下你的 Key 是不是过期的？或者端口号变了？")

if __name__ == "__main__":
    start_chat()