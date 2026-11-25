<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  Bot,
  CheckCircle2,
  Cloud,
  Compass,
  Globe2,
  KeyRound,
  Search,
  ShieldCheck,
  TrendingUp,
} from 'lucide-vue-next'
import AppShell from '../components/AppShell.vue'
import { t } from '../core/i18n'
import { readDarkMode, writeDarkMode } from '../core/storage'

const isDark = ref(readDarkMode())

function applyDarkClass(dark: boolean) {
  if (typeof document !== 'undefined') {
    document.documentElement.classList.toggle('dark', dark)
  }
}

function toggleDark() {
  isDark.value = !isDark.value
  applyDarkClass(isDark.value)
  writeDarkMode(isDark.value)
}

onMounted(() => {
  applyDarkClass(isDark.value)
})
</script>

<template>
  <AppShell
    active-page="about"
    :is-dark="isDark"
    :show-history-button="false"
    :show-bookmarks-button="false"
    :show-refresh-button="false"
    @toggle-dark="toggleDark"
  >
    <div class="max-w-4xl mx-auto space-y-6">
      <!-- Hero: Brand Mission -->
      <section class="rounded-2xl border border-indigo-200/80 dark:border-indigo-900/70 bg-gradient-to-br from-white via-indigo-50/30 to-cyan-50/30 dark:from-slate-900 dark:via-slate-900 dark:to-slate-900 p-5 sm:p-7 space-y-3 shadow-xs">
        <div class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-indigo-600 text-white text-xs font-semibold">
          <Compass class="w-3.5 h-3.5" />
          <span>{{ t('镜信 MirrorBrief · 一镜照见全球真实大事', 'MirrorBrief · One Mirror to See the Real World') }}</span>
        </div>
        <h1 class="text-xl sm:text-2xl font-bold text-slate-900 dark:text-white tracking-tight leading-snug">
          {{ t('不被算法困在「信息茧房」，每天 3 分钟看清全世界、AI 前沿与股市脉络', 'Break Free from Algorithmic Bubbles — Understand the World, AI Progress & Markets in 3 Minutes') }}
        </h1>
        <p class="text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
          {{ t(
            '平时刷信息流多看几条单一话题，推荐算法就会把视野锁死在同温层里，真正影响时代走向、科技浪潮与资产波动的全球大事反而被淹没。镜信专为「破茧」而生：依托镜信自研多模型协同核验引擎与云端自动化聚合管线，7×24 小时自动汇聚全球 75+ 路公开权威信源，并用清晰直白的语言讲透“发生了什么、证据有多强、会影响哪些产业与板块”。',
            'Social feeds lock you into narrow echo chambers while hiding world-shifting diplomacy, AI breakthroughs, and macro shocks. Built on MirrorBrief Cloud Engine, we continuously cross-verify 75+ global sources into plain-language briefings, verified timelines, and market transmission maps.'
          ) }}
        </p>
      </section>

      <!-- Pillar 1: What Problems Does 镜信 Solve? -->
      <section class="space-y-3">
        <div class="flex items-center gap-2 px-1">
          <Globe2 class="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
          <h2 class="text-lg font-bold text-slate-900 dark:text-white">
            {{ t('一、镜信能帮你解决什么问题？', '1. What Problems Does MirrorBrief Solve?') }}
          </h2>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <article class="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 space-y-2">
            <h3 class="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
              <Compass class="w-4 h-4 text-indigo-600 shrink-0" />
              <span>{{ t('1. 打破算法茧房，全球大事一个不漏', '1. Break the Echo Chamber') }}</span>
            </h3>
            <p class="text-xs sm:text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
              {{ t(
                '「今日要闻」聚合全球动态、财经宏观、前沿科技与行业政策，提供专题多方立场对照表与「破茧」跨领域盲区雷达，避免陷入单一视角。',
                'Today brings together global developments, macroeconomics, frontier tech, and policy briefs with balanced stance tables and our cross-domain Blindspot Radar.'
              ) }}
            </p>
          </article>

          <article class="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 space-y-2">
            <h3 class="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
              <Bot class="w-4 h-4 text-violet-600 shrink-0" />
              <span>{{ t('2. AI 前沿全景库：看懂每代模型能干什么', '2. Global AI Frontier: Plain-English Utility') }}</span>
            </h3>
            <p class="text-xs sm:text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
              {{ t(
                '覆盖海内外 23+ 家主流 AI 机构与高星开源生态，沉淀模型代际演进谱系、能力对比矩阵与开源工具库，用大白话写清每个模型的适用场景与真实边界。',
                'Covers 23+ leading AI labs and open-source ecosystems with model lineage trees, comparison matrices, and curated high-star tools.'
              ) }}
            </p>
          </article>

          <article class="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 space-y-2">
            <h3 class="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
              <TrendingUp class="w-4 h-4 text-emerald-600 shrink-0" />
              <span>{{ t('3. 股市传导雷达：看清事件与市场的因果链', '3. Market Transmission Radar (A-Shares, HK & US)') }}</span>
            </h3>
            <p class="text-xs sm:text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
              {{ t(
                '「股市传导」把重大政策、利率波动与地缘冲突拆解为预期差评估、上中下游三阶产业链、历史相似事件回放与触发式策略推演，并自动同步核心指数行情。',
                'Breaks macro catalysts into priced-in divergence, three-tier supply chains, historical analogs, and rule-based scenarios with live index auto-sync.'
              ) }}
            </p>
          </article>

          <article class="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 space-y-2">
            <h3 class="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
              <ShieldCheck class="w-4 h-4 text-amber-600 shrink-0" />
              <span>{{ t('4. 证据分级核验 + 全站中英双语阅读', '4. Tiered Evidence & Bilingual ZH/EN') }}</span>
            </h3>
            <p class="text-xs sm:text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
              {{ t(
                '汇聚 75+ 路海内外权威资讯与一手官方披露交叉核验，清晰区分「官方披露 / 多源交叉 / 单一信源」；外文重磅自动精译，并支持一键切换中英文界面。',
                'Cross-verifies 75+ global feeds and official filings into clear evidence tiers, with bilingual compilation and one-click Chinese/English toggle.'
              ) }}
            </p>
          </article>
        </div>
      </section>

      <!-- Pillar 2: How to Use -->
      <section class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 sm:p-6 space-y-4">
        <div class="flex items-center gap-2">
          <CheckCircle2 class="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
          <h2 class="text-lg font-bold text-slate-900 dark:text-white">
            {{ t('二、怎么用最高效？（每天 3 分钟上手指南）', '2. How to Use MirrorBrief in 3 Minutes a Day') }}
          </h2>
        </div>

        <ol class="space-y-3 text-xs sm:text-sm text-slate-700 dark:text-slate-300 leading-relaxed">
          <li class="rounded-xl border border-slate-200/80 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-800/40 p-3.5 space-y-1">
            <div class="font-bold text-slate-900 dark:text-white">{{ t('1. 打开「今日要闻」（1 分钟掌握全球要事）', '1. Open "Today" (1-minute global overview)') }}</div>
            <p v-if="t('zh', 'en') === 'zh'">先看顶部重磅要闻与「专题」视角切换，再点开「破茧」补齐平时较少关注的跨领域重大进展；已阅读条目会自动安静沉淀，不会打断当前浏览节奏。</p>
            <p v-else>Review top heavy headlines and Topic viewpoints, then check Blindspot panels for cross-domain coverage without disruptive card jumping.</p>
          </li>
          <li class="rounded-xl border border-slate-200/80 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-800/40 p-3.5 space-y-1">
            <div class="font-bold text-slate-900 dark:text-white">{{ t('2. 点「AI 前沿」与「股市传导」（2 分钟深度洞察）', '2. Explore "AI Frontier" & "Markets" (2-minute deep dive)') }}</div>
            <p v-if="t('zh', 'en') === 'zh'">• 关注技术：切换至<strong>「AI 前沿」</strong>查看 23+ 家机构动态、代际演进树与高星开源工具推荐。<br />• 关注市场：切换至<strong>「股市传导」</strong>（支持标准/紧凑双视图），查看传导逻辑链、核心指数实时动向及「催化日历 / 前瞻验证」客观复盘。</p>
            <p v-else>• Tech builders: Open <strong>AI Frontier</strong> for 23+ labs, lineage trees, and verified open-source tools.<br />• Market watchers: Open <strong>Markets</strong> (Standard/Compact view) alongside <strong>Calendar</strong> and objective <strong>Forecasts</strong> verification.</p>
          </li>
          <li class="rounded-xl border border-slate-200/80 dark:border-slate-800 bg-white/80 dark:bg-slate-800/40 p-3.5 space-y-1">
            <div class="font-bold text-slate-900 dark:text-white flex items-center gap-1.5">
              <Search class="w-4 h-4 text-slate-400" />
              <span>{{ t('3. 云端自研智能聚合 + 免配置即时追问', '3. Cloud Intelligence Engine + Zero-Config Q&A') }}</span>
            </div>
            <p v-if="t('zh', 'en') === 'zh'">所有全球信源汇聚、多源交叉核验、双语精译与重磅识别均由<strong>镜信云端自动化聚合管线</strong>全天候完成，<strong>用户完全免填 API Key 开箱即用</strong>；在任意事件点击<strong>「AI 证据问答」</strong>即可围绕一手证据深入追问。</p>
            <p v-else>All global ingestion, cross-verification, bilingual compilation, and heavy event scoring run automatically on <strong>MirrorBrief Cloud Engine</strong>—<strong>no API key required</strong>. Click <strong>Ask AI</strong> on any brief for evidence-grounded Q&amp;A.</p>
          </li>
          <li class="rounded-xl border border-slate-200/80 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-800/40 p-3.5 space-y-1">
            <div class="font-bold text-slate-900 dark:text-white flex items-center gap-1.5">
              <Cloud class="w-4 h-4 text-emerald-500" />
              <span>{{ t('4. 注册登录开启多端加密云同步', '4. Encrypted Cloud Sync') }}</span>
            </div>
            <p v-if="t('zh', 'en') === 'zh'">点击右上角<strong>「登录 / 注册」</strong>后，你的自选关注词、收藏夹、研究笔记、自建催化日程与已读进度将经高强度加密自动跨电脑与手机端同步。</p>
            <p v-else>Sign in to securely encrypt and sync your watchlist, bookmarks, notes, custom catalysts, and read history across desktop and mobile.</p>
          </li>
        </ol>
      </section>

      <!-- Pillar 3: Privacy & Honest Boundaries -->
      <section class="rounded-2xl border border-amber-200/80 dark:border-amber-900/70 bg-amber-50/40 dark:bg-amber-950/20 p-5 sm:p-6 space-y-3">
        <h2 class="text-base font-bold text-amber-950 dark:text-amber-200 flex items-center gap-2">
          <KeyRound class="w-4 h-4 text-amber-600" />
          <span>{{ t('三、隐私安全与透明声明', '3. Privacy & Honest Boundaries') }}</span>
        </h2>
        <ul class="text-xs sm:text-sm text-slate-700 dark:text-slate-300 space-y-1.5 leading-relaxed">
          <li v-if="t('zh', 'en') === 'zh'">• <strong>数据加密保护</strong>：账号密码采用单向加盐哈希校验，云端同步的个人研究数据全程密文存储；你在问答窗中可选填的自有模型密钥仅存于当前浏览器本地，绝不上传服务器。</li>
          <li v-else>• <strong>Encrypted Storage</strong>: Credentials use irreversible salted hashing and personal research payloads are stored encrypted at rest; optional custom model keys remain strictly in browser <code class="font-mono">localStorage</code>.</li>
          <li v-if="t('zh', 'en') === 'zh'">• <strong>定时自动更新</strong>：后台定时同步全球 75+ 路权威信源并经由镜信多模型协同核验引擎完成去重核验与双语整理，所有条目严格标明真实生成与信源发布时间。</li>
          <li v-else>• <strong>Transparent Cadence</strong>: Automatically ingests 75+ global sources via MirrorBrief Cloud Engine with strict origin timestamps and no synthetic backfill.</li>
          <li v-if="t('zh', 'en') === 'zh'">• <strong>理性参考边界</strong>：「股市传导」中的敏感区间、历史相似事件回放与前瞻推演旨在辅助建立宏观分析框架，不构成具体证券投资建议。</li>
          <li v-else>• <strong>Research Only</strong>: Transmission maps, historical analogs, and forecast tracking are analytical tools—not personalized financial or investment advice.</li>
        </ul>

        <div class="pt-2 flex flex-wrap gap-3">
          <a
            href="./index.html"
            class="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-colors"
          >
            {{ t('立即进入镜信工作台', 'Open MirrorBrief') }}
          </a>
          <a
            href="./help.html"
            class="px-4 py-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-200 text-sm font-medium hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
          >
            {{ t('查看使用帮助手册', 'Read Help Manual') }}
          </a>
        </div>
      </section>
    </div>
  </AppShell>
</template>
