name: 🧠 AI Analyst & Comments (Daily 6am)

on:
  schedule:
    - cron: '0 23 * * *' # 北京时间 6:00 (UTC 22:00)
  workflow_dispatch:

permissions:
  contents: write

jobs:
  ai-job:
    runs-on: ubuntu-latest
    steps:
      - name: 📥 下载代码
        uses: actions/checkout@v3

      - name: 🐍 设置 Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: 📦 安装依赖和 google-genai (AI用)
        run: pip install requests google-genai

      # 步骤：运行 AI 模拟评论（生成 comments_*.json）
      - name: 🎭 运行 AI 模拟评论 (30人设)
        env:
          KEY_1: ${{ secrets.KEY_1 }}
          KEY_2: ${{ secrets.KEY_2 }}
          KEY_3: ${{ secrets.KEY_3 }}
          KEY_4: ${{ secrets.KEY_4 }}
          KEY_5: ${{ secrets.KEY_5 }}
          KEY_6: ${{ secrets.KEY_6 }}
          KEY_7: ${{ secrets.KEY_7 }}
          KEY_8: ${{ secrets.KEY_8 }}
        run: python ai_comments.py

      - name: 💾 提交并保存结果
        run: |
          git config --global user.name 'AI Insight Bot'
          git config --global user.email 'ai@bot.com'
          git add data_*.json analysis_*.json comments_*.json
          git commit -m "🧠 Daily Update: News, Analysis & 30-Persona Comments" || exit 0
          git pull --rebase origin main
          git push
