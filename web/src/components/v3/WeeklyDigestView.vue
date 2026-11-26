<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  ArrowRight,
  Bookmark,
  Bot,
  CalendarRange,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronUp,
  Clock,
  Copy,
  Cpu,
  ExternalLink,
  Factory,
  Filter,
  Flame,
  Globe,
  Layers,
  Link2,
  RefreshCw,
  Search,
  Share2,
  Sparkles,
  Target,
  TrendingUp,
  X,
} from 'lucide-vue-next'
import type { PublicSiteSettings } from '../../core/auth'
import { appLang, t } from '../../core/i18n'
import { normalizeExternalUrl } from '../../core/legacyAdapter'
import type {
  PortfolioConfig,
  WeeklyDigestDoc,
  WeeklyDigestItem,
  WeeklyDigestsIndexDoc,
  WeeklyPriority,
  WeeklySectorId,
  WorkbenchTab,
} from '../../core/types'
import { triggerHaptic } from '../../core/uiPrefs'

const props = defineProps<{
  doc: WeeklyDigestDoc | null
  indexDoc: WeeklyDigestsIndexDoc | null
  selectedWeekId: string | null
  loading: boolean
  siteSettings: PublicSiteSettings
  watchlist: string[]
  portfolio: PortfolioConfig
  bookmarkedIds: Set<string>
  nowMs: number
}>()

const emit = defineEmits<{
  (e: 'select-week', weekId: string): void
  (e: 'refresh'): void
  (e: 'toggle-bookmark-item', item: WeeklyDigestItem): void
  (e: 'open-qa-item', item: WeeklyDigestItem): void
  (e: 'open-finance-keyword', keyword: string): void
  (e: 'open-weekly-poster', stats: { streakWeeks: number; readCount: number }): void
  (e: 'switch-tab', tab: WorkbenchTab): void
  (e: 'mark-week-visited', weekId: string): void
}>()

// Habit & interactive reaction persistence (strictly zero free-text UGC)
const WEEKLY_HABIT_KEY = 'mirrorbrief_weekly_habit_v1'
type StanceChoice = 'bull' | 'bear' | 'neutral'

interface WeeklyHabitState {
  readByWeek: Record<string, string[]>
  completedWeeks: string[]
  reactionsByItem: Record<string, StanceChoice>
  lastVisitedWeekId: string | null
}

function loadWeeklyHabit(): WeeklyHabitState {
  try {
    const raw = typeof window !== 'undefined' ? window.localStorage.getItem(WEEKLY_HABIT_KEY) : null
    if (!raw) {
      return { readByWeek: {}, completedWeeks: [], reactionsByItem: {}, lastVisitedWeekId: null }
    }
    const parsed = JSON.parse(raw) as Partial<WeeklyHabitState>
    return {
      readByWeek: parsed.readByWeek && typeof parsed.readByWeek === 'object' ? parsed.readByWeek : {},
      completedWeeks: Array.isArray(parsed.completedWeeks) ? parsed.completedWeeks : [],
      reactionsByItem: parsed.reactionsByItem && typeof parsed.reactionsByItem === 'object' ? parsed.reactionsByItem : {},
      lastVisitedWeekId: typeof parsed.lastVisitedWeekId === 'string' ? parsed.lastVisitedWeekId : null,
    }
  } catch {
    return { readByWeek: {}, completedWeeks: [], reactionsByItem: {}, lastVisitedWeekId: null }
  }
}

function saveWeeklyHabit(state: WeeklyHabitState) {
  try {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(WEEKLY_HABIT_KEY, JSON.stringify(state))
    }
  } catch {
    // ignore storage quota errors
  }
}

const habit = ref<WeeklyHabitState>(loadWeeklyHabit())
const viewMode = ref<'skim' | 'deep'>('skim')
const activeSectorFilter = ref<'all' | WeeklySectorId>('all')
const priorityFilter = ref<'all' | 'P0' | 'P0_P1'>('all')
const onlyMyWatchlist = ref(false)
const localQuery = ref('')
const expandedIds = ref<Set<string>>(new Set())
const thesisExpanded = ref(true)
const copiedDigest = ref(false)
const justCompletedCelebration = ref(false)

const SECTOR_VISUALS: Record<
  WeeklySectorId,
  {
    icon: typeof TrendingUp
    pillActive: string
    barClass: string
    badgeClass: string
    tintBg: string
  }
> = {
  macro_finance: {
    icon: TrendingUp,
    pillActive: 'bg-amber-500 text-white border-amber-500',
    barClass: 'bg-amber-500',
    badgeClass: 'bg-amber-500/12 text-amber-700 dark:text-amber-300 border-amber-500/25',
    tintBg: 'bg-amber-500/[0.04]',
  },
  geopolitics: {
    icon: Globe,
    pillActive: 'bg-blue-600 text-white border-blue-600',
    barClass: 'bg-blue-600',
    badgeClass: 'bg-blue-500/12 text-blue-700 dark:text-blue-300 border-blue-500/25',
    tintBg: 'bg-blue-500/[0.04]',
  },
  tech_ai: {
    icon: Cpu,
    pillActive: 'bg-violet-600 text-white border-violet-600',
    barClass: 'bg-violet-600',
    badgeClass: 'bg-violet-500/12 text-violet-700 dark:text-violet-300 border-violet-500/25',
    tintBg: 'bg-violet-500/[0.04]',
  },
  industry_society: {
    icon: Factory,
    pillActive: 'bg-emerald-600 text-white border-emerald-600',
    barClass: 'bg-emerald-600',
    badgeClass: 'bg-emerald-500/12 text-emerald-700 dark:text-emerald-300 border-emerald-500/25',
    tintBg: 'bg-emerald-500/[0.04]',
  },
}

const currentWeekId = computed(() => props.doc?.week_id || props.selectedWeekId || '')

watch(
  () => props.doc?.week_id,
  (wid) => {
    if (!wid) return
    if (habit.value.lastVisitedWeekId !== wid) {
      habit.value = { ...habit.value, lastVisitedWeekId: wid }
      saveWeeklyHabit(habit.value)
    }
    emit('mark-week-visited', wid)
  },
  { immediate: true },
)

onMounted(() => {
  if (props.doc?.week_id) {
    emit('mark-week-visited', props.doc.week_id)
  }
})

const readIdSetForWeek = computed<Set<string>>(() => {
  const wid = currentWeekId.value
  const arr = wid ? habit.value.readByWeek[wid] || [] : []
  return new Set(arr)
})

const totalItemCount = computed(() => {
  if (!props.doc) return 0
  return props.doc.sectors.reduce((acc, s) => acc + s.items.length, 0)
})

const readCountForWeek = computed(() => {
  if (!props.doc) return 0
  let count = 0
  const set = readIdSetForWeek.value
  for (const s of props.doc.sectors) {
    for (const it of s.items) {
      if (set.has(it.id)) count += 1
    }
  }
  return count
})

const progressPct = computed(() => {
  if (totalItemCount.value <= 0) return 0
  return Math.min(100, Math.round((readCountForWeek.value / totalItemCount.value) * 100))
})

const streakWeeks = computed(() => {
  const completedCount = habit.value.completedWeeks.length
  if (completedCount > 0) return completedCount
  return readCountForWeek.value > 0 ? 1 : 0
})

function syncCompletionForWeek(wid: string, nextReadSet: Set<string>) {
  if (!props.doc || !wid) return
  const allIds: string[] = []
  for (const s of props.doc.sectors) {
    for (const it of s.items) allIds.push(it.id)
  }
  if (allIds.length === 0) return
  const allDone = allIds.every((id) => nextReadSet.has(id))
  const nextCompleted = new Set(habit.value.completedWeeks)
  if (allDone && !nextCompleted.has(wid)) {
    nextCompleted.add(wid)
    justCompletedCelebration.value = true
    setTimeout(() => {
      justCompletedCelebration.value = false
    }, 3600)
  }
  habit.value = {
    ...habit.value,
    readByWeek: {
      ...habit.value.readByWeek,
      [wid]: Array.from(nextReadSet),
    },
    completedWeeks: Array.from(nextCompleted).sort(),
  }
  saveWeeklyHabit(habit.value)
}

function toggleItemRead(itemId: string) {
  const wid = currentWeekId.value
  if (!wid) return
  triggerHaptic(10)
  const next = new Set(readIdSetForWeek.value)
  if (next.has(itemId)) {
    next.delete(itemId)
  } else {
    next.add(itemId)
  }
  syncCompletionForWeek(wid, next)
}

function markAllWeekItemsRead() {
  const wid = currentWeekId.value
  if (!wid || !props.doc) return
  triggerHaptic(14)
  const next = new Set<string>()
  for (const s of props.doc.sectors) {
    for (const it of s.items) {
      next.add(it.id)
    }
  }
  syncCompletionForWeek(wid, next)
}

function toggleItemExpand(itemId: string) {
  triggerHaptic(8)
  const next = new Set(expandedIds.value)
  if (next.has(itemId)) {
    next.delete(itemId)
  } else {
    next.add(itemId)
  }
  expandedIds.value = next
}

function toggleReaction(itemId: string, choice: StanceChoice) {
  triggerHaptic(10)
  const cur = habit.value.reactionsByItem[itemId]
  const nextMap = { ...habit.value.reactionsByItem }
  if (cur === choice) {
    delete nextMap[itemId]
  } else {
    nextMap[itemId] = choice
  }
  habit.value = {
    ...habit.value,
    reactionsByItem: nextMap,
  }
  saveWeeklyHabit(habit.value)
}

// Match watchlist + portfolio against each weekly item
const personalKeywords = computed<string[]>(() => {
  const out: string[] = []
  for (const w of props.watchlist) {
    const clean = w.trim().toLowerCase()
    if (clean.length >= 2) out.push(clean)
  }
  for (const s of props.portfolio.sectors || []) {
    const clean = s.trim().toLowerCase()
    if (clean.length >= 2) out.push(clean)
  }
  for (const tk of props.portfolio.tickers || []) {
    const clean = tk.trim().toLowerCase()
    if (clean.length >= 2) out.push(clean)
  }
  return Array.from(new Set(out))
})

function getMatchedPersonalTags(item: WeeklyDigestItem): string[] {
  if (personalKeywords.value.length === 0) return []
  const hay = [
    item.title,
    item.fact_summary,
    item.one_line_takeaway,
    item.why_it_matters,
    ...(item.entities || []),
    ...(item.impact_tags || []),
  ]
    .join(' ')
    .toLowerCase()
  return personalKeywords.value.filter((kw) => hay.includes(kw)).slice(0, 3)
}

const personalHitCount = computed(() => {
  if (!props.doc || personalKeywords.value.length === 0) return 0
  let count = 0
  for (const s of props.doc.sectors) {
    for (const it of s.items) {
      if (getMatchedPersonalTags(it).length > 0) count += 1
    }
  }
  return count
})

const p0TopHighlights = computed<WeeklyDigestItem[]>(() => {
  if (!props.doc) return []
  const items: WeeklyDigestItem[] = []
  for (const s of props.doc.sectors) {
    for (const it of s.items) {
      if (it.priority === 'P0') items.push(it)
    }
  }
  return items.sort((a, b) => b.weekly_score - a.weekly_score).slice(0, 6)
})

const filteredSectors = computed(() => {
  if (!props.doc) return []
  const q = localQuery.value.trim().toLowerCase()
  return props.doc.sectors
    .filter((s) => activeSectorFilter.value === 'all' || s.sector_id === activeSectorFilter.value)
    .map((sec) => {
      const filteredItems = sec.items.filter((it) => {
        if (priorityFilter.value === 'P0' && it.priority !== 'P0') return false
        if (priorityFilter.value === 'P0_P1' && it.priority === 'P2') return false
        if (onlyMyWatchlist.value && getMatchedPersonalTags(it).length === 0) return false
        if (q) {
          const blob = [
            it.title,
            it.one_line_takeaway,
            it.fact_summary,
            it.why_it_matters,
            ...(it.entities || []),
            ...(it.impact_tags || []),
          ]
            .join(' ')
            .toLowerCase()
          if (!blob.includes(q)) return false
        }
        return true
      })
      return {
        ...sec,
        filteredItems,
      }
    })
})

const DAY_NAMES_ZH = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

const scheduleBadgeText = computed(() => {
  if (props.siteSettings.weekly_digest_enabled === false) {
    return t('每周盘点定时更新：管理员已设为手动/暂停', 'Weekly schedule: Paused / Manual')
  }
  const day = Number.isFinite(Number(props.siteSettings.weekly_digest_day))
    ? Math.max(0, Math.min(6, Number(props.siteSettings.weekly_digest_day)))
    : props.doc?.schedule?.day ?? 0
  const hour = Number.isFinite(Number(props.siteSettings.weekly_digest_hour))
    ? Math.max(0, Math.min(23, Number(props.siteSettings.weekly_digest_hour)))
    : props.doc?.schedule?.hour ?? 18
  const minute = Number.isFinite(Number(props.siteSettings.weekly_digest_minute))
    ? Math.max(0, Math.min(59, Number(props.siteSettings.weekly_digest_minute)))
    : props.doc?.schedule?.minute ?? 0
  const hh = String(hour).padStart(2, '0')
  const mm = String(minute).padStart(2, '0')
  return t(`每周${DAY_NAMES_ZH[day]?.slice(1) || '日'} ${hh}:${mm} 自动出刊 (Mon-Sun)`, `Every ${['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][day]} ${hh}:${mm} CST`)
})

const nextIssueCountdownText = computed(() => {
  if (props.siteSettings.weekly_digest_enabled === false) return ''
  const day = Number(props.siteSettings.weekly_digest_day ?? props.doc?.schedule?.day ?? 0)
  const hour = Number(props.siteSettings.weekly_digest_hour ?? props.doc?.schedule?.hour ?? 18)
  const minute = Number(props.siteSettings.weekly_digest_minute ?? props.doc?.schedule?.minute ?? 0)

  // Compute current Beijing wall-clock components safely via UTC+8 offset
  const cstNow = new Date(props.nowMs + 8 * 3_600_000)
  const curDay = cstNow.getUTCDay()
  const curHour = cstNow.getUTCHours()
  const curMin = cstNow.getUTCMinutes()

  let deltaDays = (day - curDay + 7) % 7
  const curMinsOfDay = curHour * 60 + curMin
  const targetMinsOfDay = hour * 60 + minute
  if (deltaDays === 0 && curMinsOfDay >= targetMinsOfDay) {
    deltaDays = 7
  }
  const totalDeltaMins = deltaDays * 1440 + (targetMinsOfDay - curMinsOfDay)
  const d = Math.floor(totalDeltaMins / 1440)
  const h = Math.floor((totalDeltaMins % 1440) / 60)
  if (d === 0) {
    return t(`今日 ${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')} 更新（约 ${Math.max(1, h)} 小时后）`, `Updates in ~${Math.max(1, h)}h`)
  }
  return t(`距下期出刊约 ${d} 天 ${h} 时`, `Next issue in ${d}d ${h}h`)
})

function priorityMeta(priority: WeeklyPriority) {
  if (priority === 'P0') {
    return {
      label: t('P0 战略重磅', 'P0 Critical'),
      short: 'P0',
      badgeClass: 'bg-rose-600 text-white border-rose-600 shadow-xs',
      softClass: 'bg-rose-500/12 text-rose-700 dark:text-rose-300 border-rose-500/25',
    }
  }
  if (priority === 'P1') {
    return {
      label: t('P1 重点催化', 'P1 Key'),
      short: 'P1',
      badgeClass: 'bg-[#007AFF] text-white border-[#007AFF]',
      softClass: 'bg-[#007AFF]/12 text-[#007AFF] dark:text-[#0A84FF] border-[#007AFF]/25',
    }
  }
  return {
    label: t('P2 值得关注', 'P2 Watch'),
    short: 'P2',
    badgeClass: 'bg-zinc-600 text-white border-zinc-600',
    softClass: 'bg-zinc-500/10 text-zinc-600 dark:text-zinc-300 border-zinc-500/20',
  }
}

function getSectorName(sid: WeeklySectorId): string {
  const sec = props.doc?.sectors.find((s) => s.sector_id === sid)
  if (sec) return appLang.value === 'en' ? sec.title_en : sec.title
  const fallback: Record<WeeklySectorId, string> = {
    macro_finance: t('宏观与金融市场', 'Macro & Markets'),
    geopolitics: t('国际地缘与政策', 'Geopolitics & Policy'),
    tech_ai: t('科技与 AI 前沿', 'Tech & AI'),
    industry_society: t('产业与综合要闻', 'Industry & Real Economy'),
  }
  return fallback[sid] || sid
}

function jumpToSector(sid: WeeklySectorId) {
  triggerHaptic(8)
  activeSectorFilter.value = sid
  viewMode.value = 'deep'
}

function buildCopyDigestText(): string {
  if (!props.doc) return ''
  const lines: string[] = [
    `【镜信每周盘点 · ${props.doc.week_id} (${props.doc.date_range_label})】`,
    `本周总基调：${props.doc.week_theme}`,
    '',
    '核心主线：',
    ...props.doc.executive_thesis.map((th, i) => `${i + 1}. ${th}`),
    '',
  ]
  for (const sec of props.doc.sectors) {
    if (sec.items.length === 0) continue
    lines.push(`=== ${sec.title} (${sec.items.length}项) ===`)
    if (sec.sector_takeaway) lines.push(`板块综述：${sec.sector_takeaway}`)
    for (const it of sec.items) {
      lines.push(`- [${it.priority}] ${it.title}：${it.one_line_takeaway}`)
    }
    lines.push('')
  }
  if (props.doc.next_week_catalysts.length > 0) {
    lines.push('下周重点盯防：')
    for (const c of props.doc.next_week_catalysts) {
      lines.push(`- ${c.date} · ${c.title}（${c.why_watch}）`)
    }
  }
  lines.push('')
  lines.push('来源：镜信 MirrorBrief (https://mirrorinfo.xyz/?tab=weekly)')
  return lines.join('\n')
}

async function copyWeeklyDigestText() {
  const text = buildCopyDigestText()
  if (!text) return
  triggerHaptic(10)
  try {
    await navigator.clipboard.writeText(text)
    copiedDigest.value = true
    setTimeout(() => {
      copiedDigest.value = false
    }, 2400)
  } catch {
    // ignore clipboard restrictions
  }
}
</script>

<template>
  <section class="space-y-3 sm:space-y-4 ios-fade-in" data-testid="weekly-digest-view">
    <!-- Loading state -->
    <div v-if="loading && !doc" class="ios-card p-6 sm:p-8 text-center space-y-2">
      <RefreshCw class="w-5 h-5 text-[#007AFF] animate-spin mx-auto" />
      <p class="text-sm font-medium text-zinc-600 dark:text-zinc-300">
        {{ t('正在提纯载入本周大事盘点…', 'Loading weekly major events digest…') }}
      </p>
    </div>

    <!-- Empty state -->
    <div v-else-if="!doc" class="ios-card p-6 sm:p-8 text-center space-y-3">
      <CalendarRange class="w-8 h-8 text-[#007AFF] mx-auto" :stroke-width="1.5" />
      <div class="space-y-1">
        <h2 class="text-base font-bold text-zinc-900 dark:text-white">
          {{ t('本周盘点尚未生成或正在同步', 'Weekly digest not generated yet') }}
        </h2>
        <p class="text-xs text-zinc-500 dark:text-zinc-400">
          {{ scheduleBadgeText }}
        </p>
      </div>
      <button
        type="button"
        @click="emit('refresh')"
        class="ios-tap mobile-pressable inline-flex items-center gap-1.5 px-4 min-h-[38px] rounded-xl bg-[#007AFF] text-white text-xs font-semibold"
      >
        <RefreshCw class="w-3.5 h-3.5" />
        <span>{{ t('重新检测周刊数据', 'Reload Weekly Digest') }}</span>
      </button>
    </div>

    <template v-else>
      <!-- 1. Editorial Weekly Cover Card (Habit Loop + Mode Switcher + Schedule) -->
      <div
        class="ios-card overflow-hidden border border-[#007AFF]/15 bg-gradient-to-br from-[#007AFF]/[0.05] via-white to-amber-500/[0.04] dark:from-[#0A84FF]/[0.12] dark:via-[#131823] dark:to-amber-500/[0.05]"
      >
        <div class="p-4 sm:p-5 space-y-3.5">
          <!-- Top Meta Strip: Issue Badge, Date Window, Schedule Countdown, Past Issue Selector -->
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="flex flex-wrap items-center gap-1.5">
              <span class="jx-badge bg-[#007AFF] text-white">
                <CalendarRange class="w-3 h-3" :stroke-width="1.8" />
                <span>{{ t('每周盘点', 'Weekly Digest') }}</span>
              </span>
              <span class="jx-badge bg-black/[0.05] dark:bg-white/[0.08] text-zinc-800 dark:text-zinc-100 font-mono">
                {{ doc.week_id }} · {{ doc.date_range_label }}
              </span>
              <span
                v-if="streakWeeks > 0"
                class="jx-badge bg-amber-500/14 text-amber-700 dark:text-amber-300 border border-amber-500/25"
                data-testid="weekly-streak-badge"
              >
                <Flame class="w-3 h-3" :stroke-width="1.8" />
                <span>{{ t(`连续追更 ${streakWeeks} 周`, `${streakWeeks}w Streak`) }}</span>
              </span>
            </div>

            <div class="flex flex-wrap items-center gap-1.5">
              <span class="inline-flex items-center gap-1 px-2.5 h-7 rounded-full bg-[#F5F5F7] dark:bg-[#2C2C2E] text-[11px] font-medium text-zinc-600 dark:text-zinc-300">
                <Clock class="w-3 h-3 text-[#007AFF] shrink-0" :stroke-width="1.75" />
                <span>{{ scheduleBadgeText }}</span>
                <span v-if="nextIssueCountdownText" class="hidden sm:inline text-zinc-400">· {{ nextIssueCountdownText }}</span>
              </span>

              <select
                v-if="indexDoc && indexDoc.issues.length > 1"
                :value="doc.week_id"
                @change="(e) => emit('select-week', (e.target as HTMLSelectElement).value)"
                class="h-7 px-2.5 rounded-full bg-white dark:bg-[#1C1C1E] border border-black/[0.08] dark:border-white/[0.12] text-[11px] font-semibold text-zinc-800 dark:text-zinc-100"
                :aria-label="t('切换往期周刊', 'Select weekly issue')"
              >
                <option v-for="iss in indexDoc.issues" :key="iss.week_id" :value="iss.week_id">
                  {{ iss.week_id }} ({{ iss.date_range }})
                </option>
              </select>
            </div>
          </div>

          <!-- Week Theme Headline -->
          <div class="space-y-1.5">
            <h1 class="text-lg sm:text-[21px] font-bold tracking-tight text-zinc-950 dark:text-white leading-snug">
              {{ doc.week_theme }}
            </h1>
            <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11.5px] text-zinc-500 dark:text-zinc-400">
              <span>
                {{
                  t(
                    `跨 ${doc.stats.raw_scanned} 条日间事件去重提纯 -> 收录 ${doc.stats.selected_items} 项周度大事（含 ${doc.stats.p0_count} 项 P0 战略要闻）`,
                    `Distilled from ${doc.stats.raw_scanned} items into ${doc.stats.selected_items} non-duplicate events (${doc.stats.p0_count} P0)`,
                  )
                }}
              </span>
              <span v-if="doc.model_used" class="inline-flex items-center gap-1 text-violet-600 dark:text-violet-400 font-medium">
                <Sparkles class="w-3 h-3" />
                <span>{{ t('规则提纯 + AI 主编综述', 'Distilled + AI Synthesis') }}</span>
              </span>
            </div>
          </div>

          <!-- Keywords clickable filter pills -->
          <div v-if="doc.keywords.length > 0" class="flex flex-wrap items-center gap-1.5">
            <span class="text-[11px] font-medium text-zinc-400 mr-0.5">{{ t('本周热词:', 'Themes:') }}</span>
            <button
              v-for="kw in doc.keywords"
              :key="kw"
              type="button"
              @click="localQuery = localQuery === kw ? '' : kw; triggerHaptic(6)"
              class="ios-tap px-2.5 h-6 rounded-full text-[11px] font-semibold border transition-colors"
              :class="
                localQuery === kw
                  ? 'bg-[#007AFF] text-white border-[#007AFF]'
                  : 'bg-white/80 dark:bg-white/[0.06] text-zinc-700 dark:text-zinc-200 border-black/[0.06] dark:border-white/[0.1] hover:border-[#007AFF]/40'
              "
            >
              # {{ kw }}
            </button>
          </div>

          <!-- Habit Progress Strip -->
          <div class="rounded-2xl bg-white/80 dark:bg-[#1C1C1E]/80 border border-black/[0.06] dark:border-white/[0.08] px-3.5 py-2.5 space-y-2">
            <div class="flex flex-wrap items-center justify-between gap-2 text-xs">
              <div class="flex items-center gap-2 font-semibold text-zinc-900 dark:text-zinc-100">
                <span>{{ t('本周盘点补课进度', 'Weekly Catch-up Progress') }}</span>
                <span class="font-mono text-[#007AFF] dark:text-[#0A84FF] tabular-nums">
                  {{ readCountForWeek }}/{{ totalItemCount }} ({{ progressPct }}%)
                </span>
                <span v-if="progressPct === 100 && totalItemCount > 0" class="jx-badge bg-emerald-500/15 text-emerald-700 dark:text-emerald-300">
                  <Check class="w-3 h-3" :stroke-width="2" />
                  <span>{{ t('本周已通关', 'Completed') }}</span>
                </span>
              </div>

              <div class="flex items-center gap-1.5">
                <button
                  v-if="totalItemCount > 0 && readCountForWeek < totalItemCount"
                  type="button"
                  @click="markAllWeekItemsRead"
                  class="ios-tap mobile-pressable inline-flex items-center gap-1 px-2.5 h-7 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-[11px] font-semibold"
                >
                  <CheckCheck class="w-3.5 h-3.5" :stroke-width="1.75" />
                  <span>{{ t('一键全标已盘点', 'Mark All Done') }}</span>
                </button>
                <button
                  v-else-if="totalItemCount > 0"
                  type="button"
                  @click="emit('open-weekly-poster', { streakWeeks, readCount: readCountForWeek })"
                  class="ios-tap mobile-pressable inline-flex items-center gap-1 px-2.5 h-7 rounded-xl bg-amber-500 hover:bg-amber-600 text-white text-[11px] font-semibold"
                >
                  <Share2 class="w-3 h-3" />
                  <span>{{ t('晒本周战绩海报', 'Share Completion') }}</span>
                </button>
              </div>
            </div>

            <div class="h-1.5 w-full rounded-full bg-black/[0.06] dark:bg-white/[0.08] overflow-hidden">
              <div
                class="h-full rounded-full bg-gradient-to-r from-[#007AFF] to-emerald-500 transition-all duration-300"
                :style="{ width: `${progressPct}%` }"
              />
            </div>

            <div
              v-if="justCompletedCelebration"
              class="jx-collapse-reveal text-[11px] font-semibold text-emerald-700 dark:text-emerald-300 flex items-center gap-1.5"
            >
              <Check class="w-3.5 h-3.5 shrink-0" />
              <span>{{ t('本周大事已全部盘点完成，已累计您的连续追更记录，下周同一时间不见不散。', 'All weekly major events reviewed! Streak updated.') }}</span>
            </div>
          </div>

          <!-- Dual Mode Switcher + Share / Copy / Refresh Actions -->
          <div class="flex flex-wrap items-center justify-between gap-2 pt-0.5">
            <div class="ios-segmented p-1" role="tablist" :aria-label="t('阅读模式切换', 'Reading mode switcher')">
              <button
                type="button"
                role="tab"
                :aria-selected="viewMode === 'skim'"
                @click="viewMode = 'skim'; triggerHaptic(10)"
                class="ios-segmented-btn min-h-[34px] px-3.5 text-xs sm:text-[13px] gap-1.5"
                :class="viewMode === 'skim' ? 'ios-segmented-btn-active' : 'text-zinc-600 dark:text-zinc-400'"
                data-testid="weekly-mode-skim"
              >
                <Layers class="w-3.5 h-3.5 text-[#007AFF]" :stroke-width="1.75" />
                <span>{{ t('大概看 · 3分钟速览', 'Skim · 3-Min Brief') }}</span>
              </button>
              <button
                type="button"
                role="tab"
                :aria-selected="viewMode === 'deep'"
                @click="viewMode = 'deep'; triggerHaptic(10)"
                class="ios-segmented-btn min-h-[34px] px-3.5 text-xs sm:text-[13px] gap-1.5"
                :class="viewMode === 'deep' ? 'ios-segmented-btn-active' : 'text-zinc-600 dark:text-zinc-400'"
                data-testid="weekly-mode-deep"
              >
                <Bot class="w-3.5 h-3.5 text-violet-600 dark:text-violet-400" :stroke-width="1.75" />
                <span>{{ t('细看 · 分板块深研', 'Deep Dive · By Sector') }}</span>
              </button>
            </div>

            <div class="flex flex-wrap items-center gap-1.5">
              <button
                type="button"
                @click="emit('open-weekly-poster', { streakWeeks, readCount: readCountForWeek })"
                class="ios-tap mobile-pressable inline-flex items-center gap-1.5 min-h-[34px] px-3 rounded-xl bg-[#007AFF] hover:bg-[#0066D6] text-white text-xs font-semibold shadow-xs"
                data-testid="weekly-poster-btn"
              >
                <Share2 class="w-3.5 h-3.5" :stroke-width="1.75" />
                <span>{{ t('生成周刊海报', 'Poster') }}</span>
              </button>
              <button
                type="button"
                @click="copyWeeklyDigestText"
                class="ios-tap mobile-pressable inline-flex items-center gap-1.5 min-h-[34px] px-3 rounded-xl bg-white dark:bg-[#1C1C1E] border border-black/[0.08] dark:border-white/[0.12] text-zinc-800 dark:text-zinc-100 text-xs font-semibold"
                data-testid="weekly-copy-btn"
              >
                <Check v-if="copiedDigest" class="w-3.5 h-3.5 text-emerald-500" />
                <Copy v-else class="w-3.5 h-3.5" />
                <span>{{ copiedDigest ? t('已复制复盘', 'Copied') : t('复制本周复盘', 'Copy Text') }}</span>
              </button>
              <button
                type="button"
                @click="emit('refresh')"
                class="ios-tap mobile-pressable inline-flex items-center justify-center w-[34px] h-[34px] rounded-xl bg-white dark:bg-[#1C1C1E] border border-black/[0.08] dark:border-white/[0.12] text-zinc-600 dark:text-zinc-300"
                :title="t('刷新本周盘点', 'Refresh')"
              >
                <RefreshCw class="w-3.5 h-3.5" :class="{ 'animate-spin': loading }" />
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- 2. Strict Sector Separation & Priority Filter Bar -->
      <div class="ios-card p-3 space-y-2.5 mobile-sticky-subbar">
        <div class="flex items-center gap-1.5 overflow-x-auto no-scrollbar scroll-fade-x">
          <button
            type="button"
            @click="activeSectorFilter = 'all'; triggerHaptic(6)"
            class="ios-tap mobile-pressable inline-flex items-center gap-1.5 h-8 px-3 rounded-xl border text-xs font-semibold whitespace-nowrap shrink-0 transition-colors"
            :class="
              activeSectorFilter === 'all'
                ? 'bg-zinc-900 dark:bg-white text-white dark:text-zinc-900 border-zinc-900 dark:border-white'
                : 'bg-[#F5F5F7] dark:bg-[#2C2C2E] text-zinc-700 dark:text-zinc-300 border-transparent'
            "
            data-testid="weekly-sector-all"
          >
            <span>{{ t('全部 4 大板块', 'All 4 Sectors') }}</span>
            <span class="font-mono text-[10.5px] opacity-80">{{ doc.stats.selected_items }}</span>
          </button>

          <button
            v-for="sec in doc.sectors"
            :key="sec.sector_id"
            type="button"
            @click="activeSectorFilter = activeSectorFilter === sec.sector_id ? 'all' : sec.sector_id; triggerHaptic(6)"
            class="ios-tap mobile-pressable inline-flex items-center gap-1.5 h-8 px-3 rounded-xl border text-xs font-semibold whitespace-nowrap shrink-0 transition-colors"
            :class="
              activeSectorFilter === sec.sector_id
                ? SECTOR_VISUALS[sec.sector_id].pillActive
                : 'bg-[#F5F5F7] dark:bg-[#2C2C2E] text-zinc-700 dark:text-zinc-200 border-transparent hover:border-black/10'
            "
            :data-testid="`weekly-sector-tab-${sec.sector_id}`"
          >
            <component :is="SECTOR_VISUALS[sec.sector_id].icon" class="w-3.5 h-3.5 shrink-0" :stroke-width="1.75" />
            <span>{{ appLang === 'en' ? sec.title_en : sec.title }}</span>
            <span class="font-mono text-[10.5px] opacity-80">{{ sec.item_count }}</span>
          </button>
        </div>

        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="flex flex-wrap items-center gap-1.5">
            <div class="ios-segmented p-0.5">
              <button
                type="button"
                @click="priorityFilter = 'all'"
                class="ios-segmented-btn h-7 px-2.5 text-[11px]"
                :class="priorityFilter === 'all' ? 'ios-segmented-btn-active' : 'text-zinc-500'"
              >
                {{ t('全部优先级', 'All Priorities') }}
              </button>
              <button
                type="button"
                @click="priorityFilter = 'P0'"
                class="ios-segmented-btn h-7 px-2.5 text-[11px]"
                :class="priorityFilter === 'P0' ? 'ios-segmented-btn-active text-rose-600' : 'text-zinc-500'"
              >
                {{ t(`仅看 P0 (${doc.stats.p0_count})`, `P0 Only (${doc.stats.p0_count})`) }}
              </button>
              <button
                type="button"
                @click="priorityFilter = 'P0_P1'"
                class="ios-segmented-btn h-7 px-2.5 text-[11px]"
                :class="priorityFilter === 'P0_P1' ? 'ios-segmented-btn-active' : 'text-zinc-500'"
              >
                {{ t('P0 + P1 重点', 'P0 + P1') }}
              </button>
            </div>

            <button
              v-if="personalKeywords.length > 0"
              type="button"
              @click="onlyMyWatchlist = !onlyMyWatchlist; triggerHaptic(8)"
              class="ios-tap inline-flex items-center gap-1 h-7 px-2.5 rounded-xl text-[11px] font-semibold border transition-colors"
              :class="
                onlyMyWatchlist
                  ? 'bg-amber-500 text-white border-amber-500'
                  : 'bg-[#F5F5F7] dark:bg-[#2C2C2E] text-zinc-700 dark:text-zinc-200 border-transparent'
              "
            >
              <Filter class="w-3 h-3" />
              <span>{{ t(`与我关注共振 (${personalHitCount})`, `Matches (${personalHitCount})`) }}</span>
            </button>
          </div>

          <div class="relative flex-1 min-w-[160px] max-w-xs">
            <Search class="w-3.5 h-3.5 text-zinc-400 absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input
              v-model="localQuery"
              type="search"
              :placeholder="t('在本周大事内检索…', 'Search inside weekly digest…')"
              class="w-full h-8 pl-8 pr-7 rounded-xl bg-[#F5F5F7] dark:bg-[#2C2C2E] text-xs text-zinc-900 dark:text-white placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-[#007AFF]/40"
            />
            <button
              v-if="localQuery"
              type="button"
              @click="localQuery = ''"
              class="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-600"
              :aria-label="t('清除筛选', 'Clear')"
            >
              <X class="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      <!-- 3. Executive 3-Bullet Thesis & P0 Fast Overview (Especially valuable in Skim Mode) -->
      <div class="ios-card overflow-hidden">
        <button
          type="button"
          @click="thesisExpanded = !thesisExpanded"
          class="w-full px-4 py-3 flex items-center justify-between gap-2 text-left hover:bg-black/[0.02] dark:hover:bg-white/[0.02]"
        >
          <div class="flex items-center gap-2 min-w-0">
            <Sparkles class="w-4 h-4 text-[#007AFF] shrink-0" :stroke-width="1.75" />
            <span class="text-sm font-bold text-zinc-950 dark:text-white">
              {{ t('一分钟主线提纯 · 本周核心研判与 P0 重磅榜', 'Executive Summary & P0 Watchlist') }}
            </span>
          </div>
          <ChevronUp v-if="thesisExpanded" class="w-4 h-4 text-zinc-400 shrink-0" />
          <ChevronDown v-else class="w-4 h-4 text-zinc-400 shrink-0" />
        </button>

        <div v-if="thesisExpanded" class="px-4 pb-4 pt-1 border-t border-black/[0.05] dark:border-white/[0.07] space-y-3 jx-collapse-reveal">
          <div class="grid grid-cols-1 md:grid-cols-3 gap-2">
            <div
              v-for="(line, idx) in doc.executive_thesis"
              :key="idx"
              class="ios-surface-2 px-3 py-2.5 flex items-start gap-2"
            >
              <span class="w-5 h-5 rounded-md bg-[#007AFF]/14 text-[#007AFF] dark:text-[#0A84FF] font-mono text-[11px] font-bold inline-flex items-center justify-center shrink-0 mt-0.5">
                0{{ idx + 1 }}
              </span>
              <p class="text-xs leading-relaxed text-zinc-800 dark:text-zinc-100 font-medium">
                {{ line }}
              </p>
            </div>
          </div>

          <div v-if="p0TopHighlights.length > 0 && viewMode === 'skim'" class="space-y-1.5">
            <div class="text-[11px] font-bold text-rose-600 dark:text-rose-400 uppercase tracking-wide flex items-center gap-1.5">
              <span class="jx-heavy-dot" />
              <span>{{ t('本周最高优先级 P0 大事直通车（按所属板块归类）', 'Top P0 Strategic Events') }}</span>
            </div>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
              <button
                v-for="p0 in p0TopHighlights"
                :key="p0.id"
                type="button"
                @click="jumpToSector(p0.sector_id)"
                class="ios-tap text-left rounded-xl border border-rose-500/20 bg-rose-500/[0.04] hover:bg-rose-500/[0.08] px-3 py-2 flex items-start justify-between gap-2 transition-colors"
              >
                <div class="min-w-0 space-y-0.5">
                  <div class="flex items-center gap-1.5 text-[10.5px]">
                    <span class="font-bold text-rose-600 dark:text-rose-400">P0</span>
                    <span class="text-zinc-500 dark:text-zinc-400 truncate">{{ getSectorName(p0.sector_id) }}</span>
                  </div>
                  <div class="text-xs font-semibold text-zinc-900 dark:text-white line-clamp-1">
                    {{ p0.title }}
                  </div>
                </div>
                <ArrowRight class="w-3.5 h-3.5 text-rose-500 shrink-0 mt-1" />
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- 4. Strictly Separated 4-Sector Event Panels -->
      <div class="space-y-3.5">
        <section
          v-for="sec in filteredSectors"
          :key="sec.sector_id"
          class="ios-card overflow-hidden"
          :data-testid="`weekly-sector-card-${sec.sector_id}`"
        >
          <!-- Sector Header with Distinct Visual Accent Bar -->
          <div
            class="px-4 py-3 border-b border-black/[0.06] dark:border-white/[0.08] flex flex-wrap items-center justify-between gap-2"
            :class="SECTOR_VISUALS[sec.sector_id].tintBg"
          >
            <div class="flex items-start gap-2.5 min-w-0">
              <span class="w-1 h-9 rounded-full shrink-0 mt-0.5" :class="SECTOR_VISUALS[sec.sector_id].barClass" />
              <div class="min-w-0 space-y-0.5">
                <div class="flex flex-wrap items-center gap-2">
                  <component :is="SECTOR_VISUALS[sec.sector_id].icon" class="w-4 h-4 shrink-0" :stroke-width="1.8" />
                  <h2 class="text-[15px] font-bold text-zinc-950 dark:text-white">
                    {{ appLang === 'en' ? sec.title_en : sec.title }}
                  </h2>
                  <span class="jx-badge border" :class="SECTOR_VISUALS[sec.sector_id].badgeClass">
                    {{ sec.filteredItems.length }} {{ t('条', 'items') }}
                  </span>
                  <span
                    v-if="sec.p0_count > 0"
                    class="jx-badge bg-rose-500/12 text-rose-700 dark:text-rose-300 border border-rose-500/25"
                  >
                    {{ sec.p0_count }} P0
                  </span>
                </div>
                <p class="text-xs text-zinc-600 dark:text-zinc-300 leading-relaxed">
                  {{ sec.sector_takeaway || sec.subtitle }}
                </p>
              </div>
            </div>
          </div>

          <!-- Empty Sector Notice -->
          <div v-if="sec.filteredItems.length === 0" class="px-4 py-5 text-xs text-zinc-500 dark:text-zinc-400">
            {{ t('当前筛选条件下该板块暂无匹配事件，可放宽优先级或搜索词查看。', 'No matching events in this sector under current filters.') }}
          </div>

          <!-- Items List (Dual Layout: Skim Compact vs Deep Research) -->
          <div v-else class="divide-y divide-black/[0.06] dark:divide-white/[0.07]">
            <article
              v-for="item in sec.filteredItems"
              :key="item.id"
              class="px-4 py-3.5 transition-colors"
              :class="[
                item.priority === 'P0' ? 'border-l-[3px] border-l-[#DC2626]' : '',
                readIdSetForWeek.has(item.id) ? 'bg-black/[0.015] dark:bg-white/[0.015]' : '',
              ]"
              :data-testid="`weekly-item-${item.id}`"
            >
              <!-- Skim Mode Row (with expandable inline Deep Peek) -->
              <template v-if="viewMode === 'skim' && !expandedIds.has(item.id)">
                <div class="flex items-start gap-2.5">
                  <button
                    type="button"
                    @click="toggleItemRead(item.id)"
                    class="ios-tap mt-0.5 w-6 h-6 rounded-full border flex items-center justify-center shrink-0 transition-all"
                    :class="
                      readIdSetForWeek.has(item.id)
                        ? 'bg-emerald-500 border-emerald-500 text-white scale-105'
                        : 'border-zinc-300 dark:border-zinc-600 text-transparent hover:border-[#007AFF]'
                    "
                    :title="readIdSetForWeek.has(item.id) ? t('标记为未盘点', 'Mark unread') : t('打卡：已阅补课', 'Mark reviewed')"
                    :data-testid="`weekly-check-${item.id}`"
                  >
                    <Check class="w-3.5 h-3.5" :stroke-width="2.4" />
                  </button>

                  <div class="min-w-0 flex-1 space-y-1">
                    <div class="flex flex-wrap items-center gap-1.5">
                      <span class="jx-badge border" :class="priorityMeta(item.priority).badgeClass">
                        {{ priorityMeta(item.priority).short }}
                      </span>
                      <span
                        v-if="getMatchedPersonalTags(item).length > 0"
                        class="jx-badge bg-amber-500/14 text-amber-700 dark:text-amber-300 border border-amber-500/25"
                      >
                        {{ t('自选共振', 'Watchlist Hit') }}
                      </span>
                      <span class="text-[11px] text-zinc-400 font-mono tabular-nums">
                        {{ item.first_seen }}<template v-if="item.day_span > 1"> · {{ t(`跨${item.day_span}天`, `${item.day_span}d`) }}</template>
                        · {{ item.source_count }}{{ t('源', ' src') }}
                      </span>
                    </div>

                    <h3
                      @click="toggleItemExpand(item.id)"
                      class="text-[14.5px] font-bold leading-snug cursor-pointer transition-colors"
                      :class="readIdSetForWeek.has(item.id) ? 'text-zinc-500 dark:text-zinc-400' : 'text-zinc-950 dark:text-white hover:text-[#007AFF]'"
                    >
                      {{ appLang === 'en' && item.title_en ? item.title_en : item.title }}
                    </h3>

                    <p class="text-xs text-zinc-600 dark:text-zinc-300 leading-relaxed">
                      {{ item.one_line_takeaway }}
                    </p>
                  </div>

                  <div class="flex items-center gap-1 shrink-0">
                    <button
                      type="button"
                      @click="emit('open-qa-item', item)"
                      class="ios-tap w-8 h-8 rounded-xl bg-[#F5F5F7] dark:bg-[#2C2C2E] hover:bg-[#007AFF]/12 text-[#007AFF] dark:text-[#0A84FF] inline-flex items-center justify-center"
                      :title="t('AI 证据复盘追问', 'AI Evidence Q&A')"
                    >
                      <Bot class="w-3.5 h-3.5" :stroke-width="1.75" />
                    </button>
                    <button
                      type="button"
                      @click="toggleItemExpand(item.id)"
                      class="ios-tap inline-flex items-center gap-1 px-2.5 h-8 rounded-xl bg-[#F5F5F7] dark:bg-[#2C2C2E] hover:bg-black/[0.08] dark:hover:bg-white/[0.12] text-xs font-semibold text-zinc-700 dark:text-zinc-200"
                    >
                      <span>{{ t('细看', 'Expand') }}</span>
                      <ChevronDown class="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              </template>

              <!-- Deep Dive Mode Card (or Expanded Inline Item inside Skim) -->
              <template v-else>
                <div class="space-y-3 jx-collapse-reveal">
                  <div class="flex items-start justify-between gap-2">
                    <div class="flex flex-wrap items-center gap-1.5">
                      <span class="jx-badge border" :class="priorityMeta(item.priority).badgeClass">
                        {{ priorityMeta(item.priority).label }}
                      </span>
                      <span
                        v-if="item.priority_reason"
                        class="text-[11px] font-medium px-2 py-0.5 rounded-md bg-black/[0.04] dark:bg-white/[0.06] text-zinc-600 dark:text-zinc-300"
                      >
                        {{ item.priority_reason }}
                      </span>
                      <span
                        v-if="getMatchedPersonalTags(item).length > 0"
                        class="jx-badge bg-amber-500/14 text-amber-700 dark:text-amber-300 border border-amber-500/25"
                      >
                        {{ t('命中自选:', 'Hit:') }} {{ getMatchedPersonalTags(item).join(', ') }}
                      </span>
                      <span class="text-[11px] text-zinc-400 font-mono tabular-nums">
                        {{ item.first_seen }}<template v-if="item.last_seen !== item.first_seen"> ~ {{ item.last_seen }}</template>
                        <template v-if="item.day_span > 1"> · {{ t(`持续 ${item.day_span} 天`, `${item.day_span} days`) }}</template>
                        · {{ item.source_count }} {{ t('家信源', 'sources') }}
                      </span>
                    </div>

                    <button
                      v-if="viewMode === 'skim'"
                      type="button"
                      @click="toggleItemExpand(item.id)"
                      class="ios-tap inline-flex items-center gap-1 px-2 h-7 rounded-lg text-[11px] font-semibold text-zinc-500 hover:bg-black/[0.05] dark:hover:bg-white/[0.08] shrink-0"
                    >
                      <span>{{ t('收起', 'Collapse') }}</span>
                      <ChevronUp class="w-3.5 h-3.5" />
                    </button>
                  </div>

                  <h3 class="text-[15.5px] sm:text-base font-bold text-zinc-950 dark:text-white leading-snug">
                    {{ appLang === 'en' && item.title_en ? item.title_en : item.title }}
                  </h3>

                  <!-- Distilled Core Fact -->
                  <p class="text-[13px] text-zinc-700 dark:text-zinc-200 leading-relaxed">
                    <span class="font-semibold text-zinc-900 dark:text-white mr-1">{{ t('事实提纯：', 'Core Fact:') }}</span>
                    {{ item.fact_summary }}
                  </p>

                  <!-- Two-Column Insights: Why It Matters + Next Week Watch -->
                  <div class="grid grid-cols-1 md:grid-cols-2 gap-2">
                    <div class="ios-surface-2 px-3 py-2.5 space-y-1">
                      <div class="text-[11px] font-bold text-[#007AFF] dark:text-[#0A84FF] flex items-center gap-1">
                        <Sparkles class="w-3 h-3" />
                        <span>{{ t('深度影响与逻辑研判', 'Why It Matters') }}</span>
                      </div>
                      <p class="text-xs leading-relaxed text-zinc-700 dark:text-zinc-200">
                        {{ item.why_it_matters }}
                      </p>
                    </div>

                    <div class="ios-surface-2 px-3 py-2.5 space-y-1">
                      <div class="text-[11px] font-bold text-amber-600 dark:text-amber-400 flex items-center gap-1">
                        <Target class="w-3 h-3" />
                        <span>{{ t('下周跟踪看点', 'Next-Week Watchpoint') }}</span>
                      </div>
                      <p class="text-xs leading-relaxed text-zinc-700 dark:text-zinc-200">
                        {{ item.next_week_watch }}
                      </p>
                    </div>
                  </div>

                  <!-- Evolution Timeline Strip when multi-day progression exists -->
                  <div v-if="item.evolution_steps && item.evolution_steps.length > 1" class="rounded-xl border border-black/[0.06] dark:border-white/[0.08] px-3 py-2 space-y-1.5">
                    <div class="text-[11px] font-bold text-zinc-500 dark:text-zinc-400">
                      {{ t(`本周事件演化轨迹（${item.evolution_steps.length} 个关键节点）`, `Weekly Progression (${item.evolution_steps.length} steps)`) }}
                    </div>
                    <div class="space-y-1">
                      <div
                        v-for="(st, stIdx) in item.evolution_steps"
                        :key="stIdx"
                        class="flex items-baseline gap-2 text-[11.5px]"
                      >
                        <span class="font-mono text-[10.5px] text-[#007AFF] dark:text-[#0A84FF] shrink-0">{{ st.date }}</span>
                        <span class="text-zinc-700 dark:text-zinc-300 line-clamp-1">{{ st.headline }}</span>
                      </div>
                    </div>
                  </div>

                  <!-- Entities, Assets & Verified Sources -->
                  <div class="flex flex-wrap items-center gap-1.5 text-[11px]">
                    <span
                      v-for="ent in item.entities.slice(0, 4)"
                      :key="ent"
                      class="px-2 py-0.5 rounded-md bg-black/[0.04] dark:bg-white/[0.06] text-zinc-700 dark:text-zinc-300 font-medium"
                    >
                      {{ ent }}
                    </span>
                    <span
                      v-for="asset in (item.impact_tags || []).slice(0, 3)"
                      :key="asset"
                      class="px-2 py-0.5 rounded-md bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 font-medium"
                    >
                      {{ asset }}
                    </span>
                    <template v-for="(src, sIdx) in item.sources.slice(0, 3)" :key="`${item.id}-src-${sIdx}`">
                      <a
                        v-if="normalizeExternalUrl(src.url)"
                        :href="normalizeExternalUrl(src.url) || undefined"
                        target="_blank"
                        rel="noopener noreferrer"
                        class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md border border-black/[0.08] dark:border-white/[0.12] text-zinc-600 dark:text-zinc-300 hover:border-[#007AFF] hover:text-[#007AFF] transition-colors"
                      >
                        <span>{{ src.source_name }}</span>
                        <ExternalLink class="w-2.5 h-2.5" />
                      </a>
                    </template>
                  </div>

                  <!-- Tactile Interactive Bar (Read Check, Structured Stance, AI Q&A, Market Cross-Link, Bookmark) -->
                  <div class="flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-black/[0.05] dark:border-white/[0.06]">
                    <div class="flex flex-wrap items-center gap-1.5">
                      <button
                        type="button"
                        @click="toggleItemRead(item.id)"
                        class="ios-tap mobile-pressable inline-flex items-center gap-1.5 h-8 px-3 rounded-xl text-xs font-semibold transition-all"
                        :class="
                          readIdSetForWeek.has(item.id)
                            ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border border-emerald-500/30'
                            : 'bg-[#F5F5F7] dark:bg-[#2C2C2E] text-zinc-700 dark:text-zinc-200 hover:bg-emerald-500/10'
                        "
                        :data-testid="`weekly-deep-check-${item.id}`"
                      >
                        <Check class="w-3.5 h-3.5" :stroke-width="2.2" />
                        <span>{{ readIdSetForWeek.has(item.id) ? t('已阅补课', 'Reviewed') : t('标记已盘点', 'Mark Done') }}</span>
                      </button>

                      <!-- Zero-UGC Structured Reaction Buttons -->
                      <button
                        type="button"
                        @click="toggleReaction(item.id, 'bull')"
                        class="ios-tap mobile-pressable inline-flex items-center gap-1 h-8 px-2.5 rounded-xl text-[11px] font-semibold border transition-colors"
                        :class="
                          habit.reactionsByItem[item.id] === 'bull'
                            ? 'bg-emerald-600 text-white border-emerald-600'
                            : 'bg-white dark:bg-[#1C1C1E] text-zinc-600 dark:text-zinc-300 border-black/[0.08] dark:border-white/[0.1]'
                        "
                      >
                        <span>{{ t('看重延续', 'Bullish Follow') }}</span>
                      </button>
                      <button
                        type="button"
                        @click="toggleReaction(item.id, 'bear')"
                        class="ios-tap mobile-pressable inline-flex items-center gap-1 h-8 px-2.5 rounded-xl text-[11px] font-semibold border transition-colors"
                        :class="
                          habit.reactionsByItem[item.id] === 'bear'
                            ? 'bg-rose-600 text-white border-rose-600'
                            : 'bg-white dark:bg-[#1C1C1E] text-zinc-600 dark:text-zinc-300 border-black/[0.08] dark:border-white/[0.1]'
                        "
                      >
                        <span>{{ t('风险重估', 'Risk Alert') }}</span>
                      </button>
                    </div>

                    <div class="flex flex-wrap items-center gap-1.5">
                      <button
                        type="button"
                        @click="emit('open-qa-item', item)"
                        class="ios-tap mobile-pressable inline-flex items-center gap-1 h-8 px-2.5 rounded-xl bg-[#007AFF]/10 hover:bg-[#007AFF]/18 text-[#007AFF] dark:text-[#0A84FF] text-xs font-semibold"
                      >
                        <Bot class="w-3.5 h-3.5" :stroke-width="1.75" />
                        <span>{{ t('AI 复盘追问', 'AI Review') }}</span>
                      </button>
                      <button
                        type="button"
                        @click="emit('open-finance-keyword', item.entities[0] || item.impact_tags?.[0] || item.title.slice(0, 8))"
                        class="ios-tap mobile-pressable inline-flex items-center gap-1 h-8 px-2.5 rounded-xl bg-[#F5F5F7] dark:bg-[#2C2C2E] hover:bg-black/[0.08] dark:hover:bg-white/[0.12] text-zinc-700 dark:text-zinc-200 text-xs font-semibold"
                      >
                        <TrendingUp class="w-3.5 h-3.5" :stroke-width="1.75" />
                        <span>{{ t('股市传导', 'Markets') }}</span>
                      </button>
                      <button
                        type="button"
                        @click="emit('toggle-bookmark-item', item)"
                        class="ios-tap mobile-pressable inline-flex items-center gap-1 h-8 px-2.5 rounded-xl border text-xs font-semibold transition-colors"
                        :class="
                          bookmarkedIds.has(item.id)
                            ? 'bg-amber-500/15 border-amber-500/35 text-amber-700 dark:text-amber-300'
                            : 'bg-white dark:bg-[#1C1C1E] border-black/[0.08] dark:border-white/[0.1] text-zinc-600 dark:text-zinc-300'
                        "
                      >
                        <Bookmark class="w-3.5 h-3.5" :stroke-width="1.75" />
                        <span>{{ bookmarkedIds.has(item.id) ? t('已收藏', 'Saved') : t('收藏', 'Save') }}</span>
                      </button>
                    </div>
                  </div>
                </div>
              </template>
            </article>
          </div>
        </section>
      </div>

      <!-- 5. Cross-Sector Threads + Next-Week Catalysts Bridge -->
      <div
        v-if="doc.cross_sector_threads.length > 0 || doc.next_week_catalysts.length > 0"
        class="grid grid-cols-1 lg:grid-cols-2 gap-3"
      >
        <!-- Cross-Sector Causal Threads -->
        <div v-if="doc.cross_sector_threads.length > 0" class="ios-card p-4 space-y-2.5">
          <div class="flex items-center gap-2">
            <Link2 class="w-4 h-4 text-violet-600 dark:text-violet-400 shrink-0" :stroke-width="1.75" />
            <h3 class="text-sm font-bold text-zinc-950 dark:text-white">
              {{ t('跨板块共振暗线（独立梳理，不混杂正文）', 'Cross-Sector Causal Threads') }}
            </h3>
          </div>
          <div class="space-y-2">
            <div
              v-for="(th, idx) in doc.cross_sector_threads"
              :key="idx"
              class="ios-surface-2 p-3 space-y-1.5"
            >
              <div class="flex flex-wrap items-center gap-1.5 text-[11px] font-semibold">
                <button
                  type="button"
                  @click="jumpToSector(th.from_sector)"
                  class="px-2 py-0.5 rounded-md bg-white dark:bg-[#1C1C1E] text-zinc-700 dark:text-zinc-200 hover:text-[#007AFF]"
                >
                  {{ getSectorName(th.from_sector) }}
                </button>
                <ArrowRight class="w-3 h-3 text-zinc-400" />
                <button
                  type="button"
                  @click="jumpToSector(th.to_sector)"
                  class="px-2 py-0.5 rounded-md bg-white dark:bg-[#1C1C1E] text-zinc-700 dark:text-zinc-200 hover:text-[#007AFF]"
                >
                  {{ getSectorName(th.to_sector) }}
                </button>
              </div>
              <div class="text-xs font-bold text-zinc-900 dark:text-white">
                {{ th.title }}
              </div>
              <p class="text-xs text-zinc-600 dark:text-zinc-300 leading-relaxed">
                {{ th.logic }}
              </p>
            </div>
          </div>
        </div>

        <!-- Next Week Catalysts & Prediction Bridge -->
        <div class="ios-card p-4 space-y-2.5">
          <div class="flex items-center justify-between gap-2">
            <div class="flex items-center gap-2">
              <Target class="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" :stroke-width="1.75" />
              <h3 class="text-sm font-bold text-zinc-950 dark:text-white">
                {{ t('下周重点盯防 & 前瞻押注', 'Next-Week Catalysts & Forecasts') }}
              </h3>
            </div>
            <button
              type="button"
              @click="emit('switch-tab', 'predictions')"
              class="ios-tap inline-flex items-center gap-1 px-2.5 h-7 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-[11px] font-semibold shrink-0"
            >
              <span>{{ t('去前瞻区压注', 'Forecasts') }}</span>
              <ArrowRight class="w-3 h-3" />
            </button>
          </div>

          <div v-if="doc.next_week_catalysts.length === 0" class="ios-surface-2 p-3 text-xs text-zinc-500">
            {{ t('下周日历正在随 24h 数据流实时同步，可前往「预测日程」查看完整日程表。', 'Check Forecasts & Calendar tab for full upcoming schedule.') }}
          </div>
          <div v-else class="space-y-2">
            <div
              v-for="(cat, idx) in doc.next_week_catalysts"
              :key="idx"
              class="ios-surface-2 p-3 space-y-1"
            >
              <div class="flex flex-wrap items-center justify-between gap-1.5 text-[11px]">
                <span class="font-mono font-bold text-[#007AFF] dark:text-[#0A84FF]">{{ cat.date }}</span>
                <span class="text-zinc-500 dark:text-zinc-400">{{ getSectorName(cat.sector_id) }}</span>
              </div>
              <div class="text-xs font-bold text-zinc-900 dark:text-white">
                {{ cat.title }}
              </div>
              <p class="text-xs text-zinc-600 dark:text-zinc-300 leading-relaxed">
                {{ cat.why_watch }}
              </p>
            </div>
          </div>
        </div>
      </div>
    </template>
  </section>
</template>
