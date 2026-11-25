<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  ArrowLeft,
  Bot,
  Calendar,
  Compass,
  Cpu,
  GitBranch,
  Layers,
  Radio,
  Scale,
  TrendingUp,
} from 'lucide-vue-next'
import AppShell from '../components/AppShell.vue'
import { syncHtmlLangAttr, t } from '../core/i18n'
import { readDarkMode, writeDarkMode } from '../core/storage'

const isDark = ref(readDarkMode())

function toggleDark() {
  isDark.value = !isDark.value
  document.documentElement.classList.toggle('dark', isDark.value)
  writeDarkMode(isDark.value)
}

onMounted(() => {
  syncHtmlLangAttr()
  document.documentElement.classList.toggle('dark', isDark.value)
})

const TAB_ENTRIES = [
  { href: './index.html', icon: Compass, zh: '今日要闻', en: 'Today' },
  { href: './index.html?tab=wire', icon: Radio, zh: '7×24 快讯', en: 'Live Wire' },
  { href: './index.html?tab=ai_progress', icon: Bot, zh: 'AI 前沿', en: 'AI Frontier' },
  { href: './index.html?tab=finance', icon: TrendingUp, zh: '股市传导', en: 'Markets' },
  { href: './index.html?tab=briefing', icon: Layers, zh: '今日要闻', en: 'Briefings' },
  { href: './index.html?tab=tracking', icon: GitBranch, zh: '事件追踪', en: 'Tracking' },
  { href: './index.html?tab=calendar', icon: Calendar, zh: '催化日历', en: 'Calendar' },
  { href: './index.html?tab=predictions', icon: Scale, zh: '前瞻验证', en: 'Predictions' },
  { href: './index.html?tab=tools', icon: Cpu, zh: '科技工具库', en: 'Tools' },
] as const
</script>

<template>
  <AppShell
    active-page="briefing"
    :is-dark="isDark"
    :show-history-button="false"
    :show-bookmarks-button="false"
    :show-refresh-button="false"
    @toggle-dark="toggleDark"
  >
    <div class="max-w-3xl mx-auto py-8 sm:py-12">
      <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 sm:p-10 text-center space-y-5 shadow-xs">
        <!-- Logo & 404 Code -->
        <div class="flex flex-col items-center gap-3">
          <img
            :src="'./icon.svg'"
            alt="镜信 MirrorBrief"
            class="w-16 h-16 rounded-2xl border border-slate-200 dark:border-slate-700 bg-[#FAFAFA] object-cover shadow-sm"
          />
          <span class="px-2.5 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 text-xs font-mono font-semibold">
            HTTP 404 · Not Found
          </span>
        </div>

        <div class="space-y-2">
          <h1 class="text-xl sm:text-2xl font-bold text-slate-900 dark:text-white tracking-tight">
            {{ t('这条路没有信息', 'Nothing on this path') }}
          </h1>
          <p class="text-xs sm:text-sm text-slate-500 dark:text-slate-400 max-w-md mx-auto leading-relaxed">
            {{ t(
              '你访问的页面可能已移动、链接拼写有误，或该路径尚未建档。你可以直接回到镜信全球情报工作台，或跳转到下方任一模块：',
              'The page you requested could not be found. Return to the global briefing stream or jump straight to any module below:',
            ) }}
          </p>
        </div>

        <div>
          <a
            href="./index.html"
            class="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-slate-900 dark:bg-blue-600 text-white text-sm font-semibold hover:bg-slate-800 dark:hover:bg-blue-700 transition-colors shadow-xs"
          >
            <ArrowLeft class="w-4 h-4" />
            <span>{{ t('回到全球情报', 'Back to Global Intelligence') }}</span>
          </a>
        </div>

        <div class="pt-4 border-t border-slate-100 dark:border-slate-800 text-left">
          <div class="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-3 text-center">
            {{ t('快速直达各核心模块', 'Quick Module Directory') }}
          </div>
          <div class="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs">
            <a
              v-for="item in TAB_ENTRIES"
              :key="item.href"
              :href="item.href"
              class="flex items-center gap-2 px-3 py-2.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-800/50 text-slate-700 dark:text-slate-200 hover:border-blue-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors font-medium"
            >
              <component :is="item.icon" class="w-3.5 h-3.5 shrink-0 text-slate-500 dark:text-slate-400" />
              <span>{{ t(item.zh, item.en) }}</span>
            </a>
          </div>
        </div>
      </div>
    </div>
  </AppShell>
</template>
