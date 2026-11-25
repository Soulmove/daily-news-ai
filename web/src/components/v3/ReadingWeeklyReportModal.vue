<script setup lang="ts">
import { computed, ref, toRef } from 'vue'
import { AlertTriangle, BarChart3, CheckCircle2, Compass, Layers, Sparkles, X } from 'lucide-vue-next'
import { useDialogBehavior } from '../../core/dialog'
import { appLang, t } from '../../core/i18n'
import { computeEchoChamberReport, computeWeeklyReadingReport } from '../../core/readingProgress'
import { CATEGORIES, type CategoryKey } from '../../core/types'

const props = defineProps<{
  isOpen: boolean
  nowMs?: number
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'jump-panorama'): void
}>()

const dialogEl = ref<HTMLElement | null>(null)
const { onBackdropClick, onCloseButton } = useDialogBehavior({
  isOpen: toRef(props, 'isOpen'),
  containerRef: dialogEl,
  onClose: () => emit('close'),
})

const weeklyReport = computed(() => {
  void props.isOpen
  return computeWeeklyReadingReport(props.nowMs ?? Date.now())
})

const echoReport = computed(() => {
  void props.isOpen
  return computeEchoChamberReport(props.nowMs ?? Date.now())
})

const maxDailyReads = computed(() => {
  const vals = weeklyReport.value.dailyBreakdown.map((d) => d.readCount)
  return Math.max(4, ...vals)
})

function catName(cat: CategoryKey): string {
  const found = CATEGORIES.find((c) => c.id === cat)
  return appLang.value === 'en' ? (found?.nameEn || cat) : (found?.name || cat)
}

function catShort(cat: CategoryKey): string {
  const found = CATEGORIES.find((c) => c.id === cat)
  return appLang.value === 'en' ? (found?.shortNameEn || cat) : (found?.shortName || cat)
}

const scoreColorClass = computed(() => {
  const s = echoReport.value.status
  if (s === 'echo_risk') return 'text-amber-700 dark:text-amber-300 bg-amber-500/10 dark:bg-amber-400/10'
  if (s === 'balanced') return 'text-emerald-700 dark:text-emerald-300 bg-emerald-500/10 dark:bg-emerald-400/10'
  return 'text-zinc-700 dark:text-zinc-200 bg-[#F5F5F7] dark:bg-[#2C2C2E]'
})
</script>

<template>
  <div
    v-if="isOpen"
    class="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-5 bg-slate-900/60 backdrop-blur-xs"
    role="dialog"
    aria-modal="true"
    aria-labelledby="weekly-report-title"
    @click.self="onBackdropClick"
  >
    <div
      ref="dialogEl"
      tabindex="-1"
      class="w-full max-w-2xl max-h-[88vh] overflow-y-auto rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-2xl flex flex-col focus:outline-none"
    >
      <header class="sticky top-0 z-10 bg-white/95 dark:bg-slate-900/95 backdrop-blur px-5 py-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between gap-2">
        <div class="min-w-0">
          <h2 id="weekly-report-title" class="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
            <BarChart3 class="w-4 h-4 text-blue-600 shrink-0" />
            <span>{{ t('信息茧房与跨领域视野体检', 'Domain Diversity & Echo-Chamber Checkup') }}</span>
          </h2>
          <p class="text-xs text-slate-500 mt-0.5">
            {{ t('基于本机近 7 日已读领域分布计算，帮你识别潜在视野盲区（无时长/防沉迷限制）', 'Computed from your 7-day topic distribution to spot blind spots') }}
          </p>
        </div>
        <button
          type="button"
          @click="onCloseButton"
          class="w-8 h-8 rounded-lg border border-slate-200 dark:border-slate-700 inline-flex items-center justify-center text-slate-500 hover:text-slate-900 dark:hover:text-white"
          :aria-label="t('关闭视野体检', 'Close report')"
        >
          <X class="w-4 h-4" />
        </button>
      </header>

      <div class="p-5 space-y-5 text-xs sm:text-sm">
        <div class="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
          <div class="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-800/40 p-3">
            <div class="text-[11px] text-slate-500">{{ t('近 7 日深读简报', '7-Day Briefs') }}</div>
            <div class="text-lg font-extrabold text-slate-900 dark:text-white tabular-nums mt-0.5">
              {{ weeklyReport.totalReadCount }} {{ t('条', 'items') }}
            </div>
          </div>
          <div class="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-800/40 p-3">
            <div class="text-[11px] text-slate-500">{{ t('活跃天数', 'Active Days') }}</div>
            <div class="text-lg font-extrabold text-slate-900 dark:text-white tabular-nums mt-0.5">
              {{ weeklyReport.activeDays }} / 7 {{ t('天', 'days') }}
            </div>
          </div>
          <div class="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-800/40 p-3 col-span-2 sm:col-span-1">
            <div class="text-[11px] text-slate-500">{{ t('连续关注天数', 'Streak') }}</div>
            <div class="text-lg font-extrabold text-slate-900 dark:text-white tabular-nums mt-0.5">
              {{ weeklyReport.streakDays }} {{ t('天', 'days') }}
            </div>
          </div>
        </div>

        <div class="rounded-xl border border-slate-200 dark:border-slate-800 p-4 space-y-2.5">
          <div class="flex items-center justify-between text-xs font-semibold text-slate-700 dark:text-slate-200">
            <span>{{ t('近 7 日每日已读条数', '7-Day Daily Briefs Read') }}</span>
            <span class="text-[11px] font-normal text-slate-400">{{ t('无时长限制 · 自由浏览', 'No timer limits') }}</span>
          </div>
          <div class="relative grid grid-cols-7 gap-2 h-24 items-end pt-3">
            <div
              v-for="d in weeklyReport.dailyBreakdown"
              :key="d.date"
              class="flex flex-col items-center gap-1 h-full justify-end"
            >
              <span class="text-[10px] font-mono text-slate-500 tabular-nums">{{ d.readCount }}</span>
              <div
                class="w-full max-w-[24px] rounded-t-md transition-all bg-blue-500/85"
                :style="{ height: `${Math.max(4, Math.round((d.readCount / maxDailyReads) * 60))}px` }"
                :title="`${d.date}: ${d.readCount}`"
              />
              <span class="text-[10px] text-slate-400 tabular-nums">{{ d.date.slice(5) }}</span>
            </div>
          </div>
        </div>

        <div class="rounded-xl p-4 space-y-3" :class="scoreColorClass">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="flex items-center gap-2 font-bold">
              <AlertTriangle v-if="echoReport.status === 'echo_risk'" class="w-4 h-4 shrink-0" />
              <CheckCircle2 v-else-if="echoReport.status === 'balanced'" class="w-4 h-4 shrink-0" />
              <Compass v-else class="w-4 h-4 shrink-0" />
              <span>
                {{ t('跨领域视野分布', 'Domain Diversity Score') }}：
                <strong class="font-mono text-base tabular-nums">
                  {{ echoReport.diversityScore !== null ? `${echoReport.diversityScore} / 100` : t('待评估', 'Pending') }}
                </strong>
              </span>
            </div>
            <span class="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-white/80 dark:bg-[#1C1C1E]/80">
              {{ appLang === 'en' ? echoReport.statusLabelEn : echoReport.statusLabel }}
            </span>
          </div>

          <p class="text-xs leading-relaxed">
            {{ appLang === 'en' ? echoReport.recommendationEn : echoReport.recommendation }}
          </p>

          <div class="space-y-1.5 pt-1">
            <div
              v-for="item in weeklyReport.categoryDistribution"
              :key="item.category"
              class="flex items-center gap-2 text-xs"
            >
              <span class="w-24 sm:w-28 shrink-0 font-medium truncate">{{ catName(item.category) }}</span>
              <div class="flex-1 h-2 rounded-full bg-white/70 dark:bg-slate-900/50 overflow-hidden">
                <div
                  class="h-full rounded-full bg-current opacity-80"
                  :style="{ width: `${item.pct}%` }"
                />
              </div>
              <span class="w-16 text-right font-mono tabular-nums shrink-0">{{ item.pct }}% ({{ item.count }})</span>
            </div>
          </div>

          <div v-if="echoReport.blindspotCategories.length > 0" class="flex flex-wrap items-center gap-1.5 pt-1 text-xs">
            <span class="font-semibold">{{ t('待补充领域盲区：', 'Blindspot domains:') }}</span>
            <span
              v-for="cat in echoReport.blindspotCategories"
              :key="cat"
              class="px-2 py-0.5 rounded bg-white/80 dark:bg-slate-900/70 font-medium"
            >
              {{ catShort(cat) }}
            </span>
          </div>

          <div v-if="echoReport.topEntities.length > 0" class="flex flex-wrap items-center gap-1.5 text-xs">
            <Sparkles class="w-3.5 h-3.5 shrink-0" />
            <span>{{ t('高频聚焦主体：', 'Top Entities:') }}</span>
            <span
              v-for="ent in echoReport.topEntities"
              :key="ent.name"
              class="px-2 py-0.5 rounded bg-white/70 dark:bg-slate-900/60"
            >
              {{ ent.name }} ({{ ent.count }})
            </span>
          </div>
        </div>
      </div>

      <footer class="px-5 py-3.5 border-t border-slate-200 dark:border-slate-800 flex items-center justify-between gap-2 text-xs">
        <button
          type="button"
          @click="emit('jump-panorama'); onCloseButton()"
          class="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-indigo-600 text-white font-semibold hover:bg-indigo-700"
        >
          <Layers class="w-3.5 h-3.5" />
          <span>{{ t('查看破茧盲区视角', 'Explore Blindspot Radar') }}</span>
        </button>
        <button
          type="button"
          @click="onCloseButton"
          class="px-3.5 py-2 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300"
        >
          {{ t('关闭', 'Close') }}
        </button>
      </footer>
    </div>
  </div>
</template>
