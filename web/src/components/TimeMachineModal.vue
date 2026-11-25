<script setup lang="ts">
import { computed, ref, toRef } from 'vue'
import {
  AlertCircle,
  ArrowRight,
  Calendar,
  CheckCircle2,
  Clock,
  Layers,
  RefreshCw,
  RotateCcw,
  Sparkles,
  X,
} from 'lucide-vue-next'
import SmartTime from './SmartTime.vue'
import { useDialogBehavior } from '../core/dialog'
import { appLang, t } from '../core/i18n'
import { formatShanghaiDateOnly, formatShanghaiDateTime } from '../core/time'
import type { HistoryIndexEntry } from '../core/types'

const props = defineProps<{
  isOpen: boolean
  mode: 'smart' | 'raw'
  entries: HistoryIndexEntry[]
  loading: boolean
  error: string | null
  currentHistoryPath: string | null
  nowMs?: number
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'select', entry: HistoryIndexEntry): void
  (e: 'return-latest'): void
  (e: 'retry'): void
}>()

const dialogEl = ref<HTMLElement | null>(null)
const dateRange = ref<'all' | 'today' | '3d' | '7d'>('all')
const query = ref('')
const effectiveNowMs = computed(() => props.nowMs ?? Date.now())

const { onBackdropClick, onCloseButton } = useDialogBehavior({
  isOpen: toRef(props, 'isOpen'),
  containerRef: dialogEl,
  onClose: () => emit('close'),
})

const filteredEntries = computed(() => {
  const q = query.value.trim().toLowerCase()
  const nowDate = formatShanghaiDateOnly(new Date().toISOString())
  const nowMs = Date.now()

  return props.entries.filter((entry) => {
    const rawIso = entry.generated_at || entry.fetched_at || entry.display || ''
    const dStr = rawIso ? formatShanghaiDateOnly(rawIso) : ''
    if (dateRange.value === 'today' && dStr !== nowDate) return false
    if (dateRange.value === '3d' || dateRange.value === '7d') {
      const days = dateRange.value === '3d' ? 3 : 7
      const parsed = Date.parse(rawIso)
      if (!Number.isNaN(parsed) && nowMs - parsed > days * 86_400_000) return false
    }
    if (!q) return true
    return (
      dStr.toLowerCase().includes(q) ||
      (entry.display || '').toLowerCase().includes(q) ||
      (entry.batch_id || '').toLowerCase().includes(q)
    )
  })
})

const groupedEntries = computed(() => {
  const groups: { date: string; isToday: boolean; items: HistoryIndexEntry[] }[] = []
  const byDate = new Map<string, HistoryIndexEntry[]>()
  const todayStr = formatShanghaiDateOnly(new Date().toISOString())

  for (const entry of filteredEntries.value) {
    const rawIso = entry.generated_at || entry.fetched_at || (entry.display?.slice(0, 10) || '')
    const dateKey = rawIso ? formatShanghaiDateOnly(rawIso) : t('未知日期', 'Unknown Date')
    const bucket = byDate.get(dateKey)
    if (bucket) {
      bucket.push(entry)
    } else {
      const list = [entry]
      byDate.set(dateKey, list)
      groups.push({ date: dateKey, isToday: dateKey === todayStr, items: list })
    }
  }
  return groups
})

function parseEntryIso(entry: HistoryIndexEntry): string | null {
  const direct = entry.input_cutoff_at || entry.generated_at || entry.fetched_at
  if (direct) return direct
  const disp = (entry.display || '').trim()
  const m = disp.match(/^(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})/)
  if (m) return `${m[1]}T${m[2]}:00+08:00`
  const pm = (entry.path || '').match(/(\d{4}-\d{2}-\d{2})\/(\d{2})-(\d{2})/)
  if (pm) return `${pm[1]}T${pm[2]}:${pm[3]}:00+08:00`
  return null
}

function isNormalizedActive(entryPath: string): boolean {
  if (!props.currentHistoryPath) return false
  return entryPath.replace(/\/+$/, '') === props.currentHistoryPath.replace(/\/+$/, '')
}

function extractTimeClock(entry: HistoryIndexEntry): string {
  const full = entry.display || formatShanghaiDateTime(entry.generated_at || entry.fetched_at)
  const m = full.match(/(\d{2}:\d{2})/)
  return m ? m[1] : full
}
</script>

<template>
  <div
    v-if="isOpen"
    class="ios-sheet-backdrop p-0 sm:p-4"
    role="dialog"
    aria-modal="true"
    aria-labelledby="time-machine-title"
    @click.self="onBackdropClick"
  >
    <div
      ref="dialogEl"
      tabindex="-1"
      class="ios-sheet-panel sm:max-w-2xl max-h-[86vh] flex flex-col focus:outline-none"
    >
      <div class="bg-white dark:bg-[#1C1C1E] px-4 pt-2.5 pb-3 border-b border-black/[0.06] dark:border-white/[0.08]">
        <div class="w-9 h-1 rounded-full bg-zinc-300 dark:bg-zinc-600 mx-auto mb-2 sm:hidden" />
        <div class="flex items-center justify-between gap-3">
          <h2 id="time-machine-title" class="text-[17px] font-semibold tracking-tight text-zinc-950 dark:text-white flex items-center gap-2">
            <Calendar class="w-4 h-4 text-[#007AFF]" :stroke-width="1.5" />
            <span>{{ t('历史归档', 'Archive') }}</span>
          </h2>
          <button
            type="button"
            @click="onCloseButton"
            class="w-11 h-11 -mr-2 inline-flex items-center justify-center rounded-xl text-zinc-400 hover:text-zinc-700 dark:hover:text-white"
            :aria-label="t('关闭', 'Close')"
          >
            <X class="w-5 h-5" :stroke-width="1.5" />
          </button>
        </div>

        <div class="mt-2.5">
          <div class="ios-segmented w-full sm:w-auto flex sm:inline-flex">
            <button
              v-for="pill in [
                { id: 'all', zh: '全部', en: 'All' },
                { id: 'today', zh: '今日', en: 'Today' },
                { id: '3d', zh: '近 3 天', en: '3D' },
                { id: '7d', zh: '近 7 天', en: '7D' },
              ]"
              :key="pill.id"
              type="button"
              @click="dateRange = pill.id as any"
              class="ios-segmented-btn flex-1 sm:flex-initial min-h-[32px] px-3"
              :class="
                dateRange === pill.id
                  ? 'ios-segmented-btn-active'
                  : 'text-zinc-600 dark:text-zinc-400'
              "
            >
              {{ appLang === 'en' ? pill.en : pill.zh }}
            </button>
          </div>
        </div>
      </div>

      <div
        v-if="currentHistoryPath"
        class="px-5 py-2.5 bg-indigo-50 dark:bg-indigo-950/50 border-b border-indigo-200/80 dark:border-indigo-900 flex items-center justify-between gap-2 text-xs"
      >
        <span class="text-indigo-900 dark:text-indigo-200 font-medium truncate">
          {{ t('正在查看历史快照：', 'Viewing archive: ') }}<code class="font-mono">{{ currentHistoryPath }}</code>
        </span>
        <button
          type="button"
          @click="emit('return-latest')"
          class="inline-flex items-center gap-1 px-3 py-1 rounded-full font-semibold bg-indigo-600 text-white hover:bg-indigo-700 shrink-0"
        >
          <RotateCcw class="w-3.5 h-3.5" />
          <span>{{ t('回到最新实时', 'Return to Latest') }}</span>
        </button>
      </div>

      <div class="flex-1 overflow-y-auto px-5 sm:px-6 py-5 bg-slate-50/70 dark:bg-slate-950/50">
        <div v-if="loading" class="py-16 text-center text-sm text-slate-500">
          {{ t('正在加载历史时间轴...', 'Loading archive timeline...') }}
        </div>

        <div
          v-else-if="error"
          class="p-4 rounded-2xl bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 text-sm text-red-800 dark:text-red-200 flex items-center justify-between gap-3"
        >
          <div class="flex items-center gap-2">
            <AlertCircle class="w-4 h-4 shrink-0" />
            <span>{{ error }}</span>
          </div>
          <button
            type="button"
            @click="emit('retry')"
            class="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium bg-white dark:bg-slate-800 border border-red-200"
          >
            <RefreshCw class="w-3.5 h-3.5" />
            <span>{{ t('重试', 'Retry') }}</span>
          </button>
        </div>

        <div v-else-if="groupedEntries.length === 0" class="py-16 text-center text-sm text-slate-500">
          {{ t('该筛选条件下暂无归档记录。', 'No archive snapshots match this filter.') }}
        </div>

        <div v-else class="relative border-l-2 border-indigo-200/80 dark:border-indigo-900/80 ml-2.5 pl-5 space-y-6">
          <section v-for="(group, gIdx) in groupedEntries" :key="group.date" class="relative space-y-2.5">
            <span
              class="absolute -left-[29px] top-1 w-3.5 h-3.5 rounded-full border-2 border-white dark:border-slate-900 shadow-xs"
              :class="group.isToday ? 'bg-indigo-600 ring-4 ring-indigo-500/20' : 'bg-slate-400 dark:bg-slate-600'"
            />

            <div class="flex items-center justify-between gap-2">
              <div class="flex items-center gap-2">
                <h3 class="text-sm font-bold text-slate-900 dark:text-white tracking-tight">{{ group.date }}</h3>
                <span
                  v-if="group.isToday"
                  class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-indigo-100 text-indigo-700 dark:bg-indigo-950/70 dark:text-indigo-300"
                >
                  {{ t('今日', 'Today') }}
                </span>
              </div>
              <span class="text-[11px] text-slate-400 tabular-nums">
                {{ group.items.length }} {{ t('期快照', 'snapshots') }}
              </span>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              <button
                v-for="(entry, eIdx) in group.items"
                :key="entry.path"
                type="button"
                @click="emit('select', entry)"
                class="group text-left p-3.5 rounded-2xl border transition-all duration-150 flex flex-col justify-between gap-2.5 bg-white dark:bg-slate-900"
                :class="
                  isNormalizedActive(entry.path)
                    ? 'border-indigo-500 ring-2 ring-indigo-500/20 shadow-sm'
                    : 'border-slate-200/90 dark:border-slate-800 hover:border-indigo-400 dark:hover:border-indigo-600 hover:shadow-md hover:-translate-y-0.5'
                "
              >
                <div class="flex items-start justify-between gap-2">
                  <div class="flex items-center gap-2">
                    <span class="text-lg font-extrabold tracking-tight text-slate-900 dark:text-white tabular-nums font-mono">
                      {{ extractTimeClock(entry) }}
                    </span>
                    <span
                      v-if="gIdx === 0 && eIdx === 0 && !currentHistoryPath"
                      class="px-1.5 py-0.5 rounded-md text-[10px] font-bold bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300"
                    >
                      {{ t('最新', 'Latest') }}
                    </span>
                    <span
                      v-else-if="isNormalizedActive(entry.path)"
                      class="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-md text-[10px] font-bold bg-indigo-600 text-white"
                    >
                      <CheckCircle2 class="w-3 h-3" />
                      {{ t('当前', 'Active') }}
                    </span>
                  </div>
                  <ArrowRight class="w-4 h-4 text-slate-300 group-hover:text-indigo-600 dark:group-hover:text-indigo-400 group-hover:translate-x-0.5 transition-all shrink-0" />
                </div>

                <div class="flex flex-wrap items-center gap-1.5 text-[11px]">
                  <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200/70 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800 font-medium">
                    <Layers class="w-3 h-3" />
                    {{ (entry.categories?.length ?? 4) }}/4 {{ t('全频道', 'channels') }}
                  </span>
                  <span
                    v-if="entry.has_comments"
                    class="px-2 py-0.5 rounded-md bg-violet-50 text-violet-700 border border-violet-200/70 dark:bg-violet-950/40 dark:text-violet-300 dark:border-violet-800 font-medium"
                  >
                    {{ t('含 AI 视角', 'AI Views') }}
                  </span>
                </div>

                <div class="flex items-center justify-between gap-2 text-[11px] text-slate-400 pt-1 border-t border-slate-100 dark:border-slate-800/80">
                  <span class="inline-flex items-center gap-1 truncate">
                    <Clock class="w-3 h-3 shrink-0" />
                    {{ t('更新 ', 'Updated ') }}<SmartTime :iso="parseEntryIso(entry)" :now-ms="effectiveNowMs" />
                  </span>
                </div>
              </button>
            </div>
          </section>
        </div>
      </div>
    </div>
  </div>
</template>
