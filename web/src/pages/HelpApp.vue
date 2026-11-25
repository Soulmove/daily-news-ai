<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  BookOpen,
  Bot,
  Calendar,
  CheckCircle2,
  Cloud,
  Compass,
  GitBranch,
  HelpCircle,
  Keyboard,
  MessageSquarePlus,
  Newspaper,
  Radio,
  Search,
  Smartphone,
  TrendingUp,
} from 'lucide-vue-next'
import AppShell from '../components/AppShell.vue'
import { t } from '../core/i18n'
import { readDarkMode, writeDarkMode } from '../core/storage'

const isDark = ref(readDarkMode())

function toggleDark() {
  isDark.value = !isDark.value
  document.documentElement.classList.toggle('dark', isDark.value)
  writeDarkMode(isDark.value)
}

function openFeedback() {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('infofocus-open-feedback'))
  }
}

onMounted(() => {
  document.documentElement.classList.toggle('dark', isDark.value)
})

const coreModules = [
  {
    key: 'today',
    icon: Newspaper,
    titleZh: '1. 今日要闻（精选 / 分类 / 专题 / 破茧）',
    titleEn: '1. Today Briefings (Featured / Topics / Blindspot)',
    descZh: '聚合全球高价值大事，自动标注「官方披露 / 多源交叉 / 单一信源」证据级别。「专题」提供跨媒体多方立场对照，「破茧」主动补全平时较少触及的盲区领域；点开阅读自动静默标记已读，不会打断阅读位置或突然收起。',
    descEn: 'Curates high-signal global events with clear evidence tiers, multi-perspective Topic comparisons, Blindspot domain panels, and calm auto-read tracking.',
  },
  {
    key: 'wire',
    icon: Radio,
    titleZh: '2. 7×24 快讯（实时流 + 重磅事件雷达）',
    titleEn: '2. 7×24 Live Wire (Real-Time Stream & Heavy Radar)',
    descZh: '按分钟滚动收录海内外财经、外交与突发进展，并与全站重磅评估体系实时打通：重大突发自动升级正红呼吸提醒，自动剔除普通券商常规评级等干扰噪音。',
    descEn: 'Minute-by-minute stream of macro, policy, and breaking global items integrated with unified Heavy event radar and noise filtering.',
  },
  {
    key: 'ai_progress',
    icon: Bot,
    titleZh: '3. AI 前沿（23+ 机构演进谱系 + 开源工具库）',
    titleEn: '3. AI Frontier (23+ Labs & Open-Source Tools)',
    descZh: '全量追踪 23+ 家主流 AI 研究机构，清晰区分闭源旗舰与开源权重；内置「模型代际演进谱系」及高星开源工具库，写清“能干什么与有何限制”。',
    descEn: 'Tracks 23+ frontier AI labs with generational model lineage trees, strict open-weight separation, and high-star open-source developer tools.',
  },
  {
    key: 'finance',
    icon: TrendingUp,
    titleZh: '4. 股市传导（A股/美股/港股三阶传导链 + 自动行情同步）',
    titleEn: '4. Market Transmission (3-Tier Chains & Auto Quotes)',
    descZh: '支持「标准看盘 / 紧凑看盘」双视图，每张传导卡片拆解预期差分析、上中下游三阶产业链个股/ETF、历史相似回放与策略推演；核心基准指数与涨幅在后台自动静默刷新，无需手动频繁点击。',
    descEn: 'Dual Standard/Compact views breaking macro events into priced-in divergence, 3-tier sectors/tickers, historical analogs, and automatic quote synchronization.',
  },
  {
    key: 'calendar',
    icon: Calendar,
    titleZh: '5. 催化日历（突发日程动态捕捉 + 重磅月度节点）',
    titleEn: '5. Catalyst Calendar (Dynamic Schedule Capture)',
    descZh: '结合未来确定性政策议程、财报窗口与议息会议，并从每日要闻动态抽取出最新公告的生效日与高官访问日程，支持加入个人自建催化提醒。',
    descEn: 'Combines scheduled macro meetings, policy dates, and dynamically extracted event milestones into a forward-looking calendar.',
  },
  {
    key: 'tracking',
    icon: GitBranch,
    titleZh: '6. 事件追踪（长周期主线 + AI 证据问答）',
    titleEn: '6. Event Tracking (Long-Horizon Storylines & Evidence Q&A)',
    descZh: '把散落多日、多源的连续新闻串联为完整主线脉络与演化进度，一键开启「AI 证据问答」，围绕结构化事实表与原始报道开展可核查追问。',
    descEn: 'Threads multi-day developments into structured timelines with direct access to grounded Evidence Q&A.',
  },
  {
    key: 'forecasts',
    icon: CheckCircle2,
    titleZh: '7. 前瞻验证（客观规则自动结算 + 历史命中率可审计）',
    titleEn: '7. Forecast Verification (Objective Auto-Settlement)',
    descZh: '基于可公开查证的条件触发线（If / Then）开展客观复盘，实时跟踪与历史已结算指标分开统计，每一项命中或偏离均附可追溯依据。',
    descEn: 'Auditable If/Then forecasts separating live tracking from settled history with transparent resolution notes.',
  },
]

const faqs = [
  {
    qZh: 'Q1：我需要自己申请或填写任何 AI API 密钥才能使用吗？',
    qEn: 'Q1: Do I need to configure my own AI API key to use MirrorBrief?',
    aZh: '完全不需要。镜信采用云端自研智能聚合与多模型协同核验引擎（MirrorBrief Cloud Engine），7×24 小时自动监控全球 75+ 路公开新闻源、监管机构官网、高星开源仓库与行业公开资料并完成结构化整理。普通用户完全免配置，打开即看；仅在需要极速深度追问自定义提示词时，支持选填自带密钥。',
    aEn: 'Not at all. MirrorBrief runs on MirrorBrief Cloud Engine, 24/7 monitoring 75+ authoritative news, regulatory, and open-source feeds and generating structured briefings automatically. No API key is needed; bringing your own key is strictly optional for custom Q&A prompts.',
  },
  {
    qZh: 'Q2：如何快速全站搜索、筛选「未读」或管理自选关注？',
    qEn: 'Q2: How do I search across modules, filter unread items, or sync watchlists?',
    aZh: '桌面端按 ⌘K / Ctrl+K 或点击顶部搜索框即可跨「今日要闻 / 7×24 快讯 / AI 前沿 / 股市传导 / 催化日历 / 事件追踪」全局即时检索。点开新闻卡片即自动静默记为已读，配合左上角未读筛选可零遗漏复盘。',
    aEn: 'Press Cmd+K / Ctrl+K (or tap Search) to query across all 7 modules instantly. Opening a card marks it read seamlessly without jumping your scroll position.',
  },
  {
    qZh: 'Q3：怎么在电脑、手机网页端之间同步阅读记录？',
    qEn: 'Q3: How do my read progress, bookmarks, and notes sync across devices?',
    aZh: '点击右上角登录或注册账号后，您的关注词、收藏夹、自建日历日程与已读/未读进度会自动加密上传并实时跨电脑与手机网页端云端同步，随时换机接续阅读。',
    aEn: 'Sign in from the header on any device. Your watchlist, bookmarks, custom calendar items, notes, and read history encrypt and sync automatically across desktop and mobile web.',
  },
  {
    qZh: 'Q4：对内容纠偏或产品建议有疑问，去哪里联系管理员？',
    qEn: 'Q4: How can I report a content issue or submit product feedback?',
    aZh: '您可以在任意页面顶部菜单或左侧边栏底部点击「意见反馈」，提交问题描述或建议，并在反馈弹窗「我的反馈记录」页签实时查看管理员受理状态与官方回复。',
    aEn: 'Click Feedback from the header menu or left rail footer on any page. You can track admin status updates and official replies inside the "My Feedback" tab.',
  },
]
</script>

<template>
  <AppShell
    active-page="help"
    :is-dark="isDark"
    :show-history-button="false"
    :show-bookmarks-button="false"
    :show-refresh-button="false"
    @toggle-dark="toggleDark"
  >
    <div class="max-w-4xl mx-auto space-y-6">
      <!-- Hero -->
      <section class="rounded-2xl border border-indigo-200/80 dark:border-indigo-900/70 bg-gradient-to-br from-white via-indigo-50/40 to-sky-50/40 dark:from-slate-900 dark:via-slate-900 dark:to-slate-900 p-5 sm:p-7 space-y-3">
        <div class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-indigo-600 text-white text-xs font-semibold">
          <BookOpen class="w-3.5 h-3.5" />
          <span>{{ t('镜信使用帮助手册 · MirrorBrief Handbook', 'MirrorBrief Help & User Guide') }}</span>
        </div>
        <h1 class="text-xl sm:text-2xl font-bold text-slate-900 dark:text-white tracking-tight">
          {{ t('3 分钟快速上手 + 7 大核心模块实战指南', '3-Minute Quick Start & 7-Module Field Manual') }}
        </h1>
        <p class="text-xs sm:text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
          {{ t(
            '这份指南帮助你用最短时间掌握「今日要闻、7×24 快讯、AI 前沿、股市传导、催化日历、事件追踪、前瞻验证」全部核心能力与多端协同技巧。',
            'Learn how to navigate Today Briefings, Live Wire, AI Frontier, Market Transmission, Catalyst Calendar, Event Tracking, and Objective Forecasts in minutes.',
          ) }}
        </p>
      </section>

      <!-- Section 1: 3-Minute Quick Start -->
      <section class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 sm:p-6 space-y-4">
        <div class="flex items-center gap-2">
          <Compass class="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
          <h2 class="text-lg font-bold text-slate-900 dark:text-white">
            {{ t('一、3 分钟快速上手路径', '1. 3-Minute Quick Start') }}
          </h2>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-3 gap-3.5">
          <div class="rounded-xl border border-slate-200/80 dark:border-slate-800 bg-slate-50/80 dark:bg-slate-800/40 p-4 space-y-1.5">
            <div class="text-xs font-bold text-indigo-600 dark:text-indigo-400">{{ t('第 1 分钟 · 看要闻', 'Minute 1 · Headlines') }}</div>
            <div class="text-sm font-bold text-slate-900 dark:text-white">{{ t('扫「今日要闻」与红色重磅', 'Scan Heavy Briefs') }}</div>
            <p class="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
              {{ t('先看正红色呼吸标注的重磅头条，按「国际 / 财经 / 科技 / 破茧」快速查漏；点开阅读后自动记已读，页面位置保持稳定。', 'Start with crimson Heavy alerts, check Topic stance tables and Blindspot radar; cards stay expanded silently when read.') }}
            </p>
          </div>
          <div class="rounded-xl border border-slate-200/80 dark:border-slate-800 bg-slate-50/80 dark:bg-slate-800/40 p-4 space-y-1.5">
            <div class="text-xs font-bold text-emerald-600 dark:text-emerald-400">{{ t('第 2 分钟 · 查传导', 'Minute 2 · Deep Dive') }}</div>
            <div class="text-sm font-bold text-slate-900 dark:text-white">{{ t('切「股市传导 / AI 前沿」', 'Inspect Markets & AI') }}</div>
            <p class="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
              {{ t('按需切换「股市传导」看 A 股/美股/港股三阶产业链，或看「AI 前沿」23+ 机构发布与开源工具推荐；遇到疑问点「AI 证据问答」即问即答。', 'Switch between Markets (3-tier causal chains & auto-synced quotes) and AI Frontier, or tap Ask AI for source-grounded answers.') }}
            </p>
          </div>
          <div class="rounded-xl border border-slate-200/80 dark:border-slate-800 bg-slate-50/80 dark:bg-slate-800/40 p-4 space-y-1.5">
            <div class="text-xs font-bold text-sky-600 dark:text-sky-400">{{ t('第 3 分钟 · 追后续', 'Minute 3 · Track & Sync') }}</div>
            <div class="text-sm font-bold text-slate-900 dark:text-white">{{ t('看「日历 / 验证」并云同步', 'Calendar & Cloud Sync') }}</div>
            <p class="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
              {{ t('查看「催化日历」提前锚定重要政策与财报节点，在「前瞻验证」追踪条件推演结算结果；登录账号即可在电脑与手机端无缝接续。', 'Review upcoming catalysts, inspect forecast settlement accuracy, and sign in to sync progress across devices.') }}
            </p>
          </div>
        </div>
      </section>

      <!-- Section 2: 7 Core Modules -->
      <section class="space-y-3">
        <div class="flex items-center gap-2 px-1">
          <Search class="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
          <h2 class="text-lg font-bold text-slate-900 dark:text-white">
            {{ t('二、7 大核心模块实战手册', '2. 7 Core Modules Field Manual') }}
          </h2>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3.5">
          <article
            v-for="mod in coreModules"
            :key="mod.key"
            class="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4.5 space-y-2"
          >
            <h3 class="text-sm sm:text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
              <component :is="mod.icon" class="w-4 h-4 text-indigo-600 dark:text-indigo-400 shrink-0" :stroke-width="1.75" />
              <span>{{ t(mod.titleZh, mod.titleEn) }}</span>
            </h3>
            <p class="text-xs sm:text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
              {{ t(mod.descZh, mod.descEn) }}
            </p>
          </article>
        </div>
      </section>

      <!-- Section 3: Shortcuts & Multi-Device Sync -->
      <section class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 sm:p-6 space-y-4">
        <div class="flex items-center gap-2">
          <Keyboard class="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
          <h2 class="text-lg font-bold text-slate-900 dark:text-white">
            {{ t('三、快捷键、多端协同与常见问题 FAQ', '3. Shortcuts, Multi-Device Sync & FAQ') }}
          </h2>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
          <div class="rounded-xl border border-slate-200 dark:border-slate-800 px-3.5 py-2.5 flex items-center justify-between gap-2 bg-slate-50/70 dark:bg-slate-800/40">
            <span class="font-medium text-slate-700 dark:text-slate-200 flex items-center gap-1.5">
              <Search class="w-3.5 h-3.5 text-slate-400" />
              {{ t('全站跨模块搜索', 'Global Search') }}
            </span>
            <kbd class="px-2 py-0.5 rounded-md bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 font-mono text-[11px] text-slate-700 dark:text-slate-200">⌘K / Ctrl+K</kbd>
          </div>
          <div class="rounded-xl border border-slate-200 dark:border-slate-800 px-3.5 py-2.5 flex items-center justify-between gap-2 bg-slate-50/70 dark:bg-slate-800/40">
            <span class="font-medium text-slate-700 dark:text-slate-200 flex items-center gap-1.5">
              <Cloud class="w-3.5 h-3.5 text-slate-400" />
              {{ t('账号云端同步', 'Cloud Sync') }}
            </span>
            <span class="font-semibold text-emerald-600 dark:text-emerald-400">{{ t('登录后自动开启', 'Auto on Sign-In') }}</span>
          </div>
          <div class="rounded-xl border border-slate-200 dark:border-slate-800 px-3.5 py-2.5 flex items-center justify-between gap-2 bg-slate-50/70 dark:bg-slate-800/40">
            <span class="font-medium text-slate-700 dark:text-slate-200 flex items-center gap-1.5">
              <Smartphone class="w-3.5 h-3.5 text-slate-400" />
              {{ t('移动端体验', 'Mobile & Android') }}
            </span>
            <a href="./index.html?app=android" class="font-semibold text-indigo-600 dark:text-indigo-400 hover:underline">{{ t('进入极简视图', 'Mobile View') }}</a>
          </div>
        </div>

        <div class="space-y-3 pt-1">
          <article
            v-for="item in faqs"
            :key="item.qZh"
            class="rounded-xl border border-slate-200/80 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/30 p-4 space-y-1.5"
          >
            <h3 class="text-xs sm:text-sm font-bold text-slate-900 dark:text-white flex items-center gap-1.5">
              <HelpCircle class="w-4 h-4 text-indigo-600 dark:text-indigo-400 shrink-0" />
              <span>{{ t(item.qZh, item.qEn) }}</span>
            </h3>
            <p class="text-xs sm:text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
              {{ t(item.aZh, item.aEn) }}
            </p>
          </article>
        </div>

        <div class="pt-2 flex flex-wrap items-center gap-3 text-xs">
          <a href="./index.html" class="px-4 py-2 rounded-lg bg-indigo-600 text-white font-semibold hover:bg-indigo-700 transition-colors">
            {{ t('返回镜信工作台', 'Back to Workbench') }}
          </a>
          <button
            type="button"
            @click="openFeedback"
            class="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 font-medium text-slate-700 dark:text-slate-200"
          >
            <MessageSquarePlus class="w-3.5 h-3.5" />
            <span>{{ t('打开意见反馈', 'Open Feedback') }}</span>
          </button>
          <a href="./about.html" class="px-4 py-2 rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-200">
            {{ t('关于镜信', 'About MirrorBrief') }}
          </a>
          <a href="./privacy.html" class="px-4 py-2 rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-200">
            {{ t('隐私政策', 'Privacy Policy') }}
          </a>
        </div>
      </section>
    </div>
  </AppShell>
</template>
