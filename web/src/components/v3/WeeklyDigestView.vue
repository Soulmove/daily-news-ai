<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  Activity,
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Bookmark,
  Bot,
  Calendar,
  CalendarRange,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronUp,
  Clock,
  Compass,
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
  Scale,
  Search,
  Share2,
  ShieldAlert,
  SlidersHorizontal,
  Sparkles,
  Target,
  TrendingUp,
  X,
} from 'lucide-vue-next'
import type { PublicSiteSettings } from '../../core/auth'
import { appLang, t } from '../../core/i18n'
import { normalizeExternalUrl } from '../../core/legacyAdapter'
import {
  loadWeeklyHabitState,
  saveWeeklyHabitState,
  type WeeklyHabitState,
  type WeeklyItemStanceChoice,
  type WeeklyOutlookIntuitionChoice,
} from '../../core/storage'
import type {
  CatalystEvent,
  CrowdPredictionStat,
  PortfolioConfig,
  PredictionRecord,
  WatchlistItem,
  WeeklyDigestDoc,
  WeeklyDigestItem,
  WeeklyDigestsIndexDoc,
  WeeklyNextOutlookItem,
  WeeklyOutlookDirection,
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
  watchlist: WatchlistItem[]
  portfolio: PortfolioConfig
  bookmarkedIds: Set<string>
  predictions?: PredictionRecord[]
  crowdStats?: Record<string, CrowdPredictionStat>
  calendarEvents?: CatalystEvent[]
  habitSyncNonce?: number
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
  (e: 'jump-prediction', predictionId?: string | null): void
  (e: 'open-qa-prediction', rec: PredictionRecord): void
  (e: 'mark-week-visited', weekId: string): void
  (e: 'habit-changed'): void
}>()

type StanceChoice = WeeklyItemStanceChoice
type OutlookIntuition = WeeklyOutlookIntuitionChoice

const habit = ref<WeeklyHabitState>(loadWeeklyHabitState())
const viewMode = ref<'skim' | 'deep' | 'outlook'>('skim')
const activeSectorFilter = ref<'all' | WeeklySectorId>('all')
const priorityFilter = ref<'all' | 'P0' | 'P0_P1'>('all')
const onlyMyWatchlist = ref(false)
const localQuery = ref('')
const filtersOpen = ref(false)
const expandedIds = ref<Set<string>>(new Set())
const thesisExpanded = ref(typeof window !== 'undefined' ? window.innerWidth >= 640 : true)
const copiedDigest = ref(false)
const justCompletedCelebration = ref(false)
const popBurstKey = ref('')
let popBurstTimer: ReturnType<typeof setTimeout> | null = null

function triggerPopBurst(key: string) {
  popBurstKey.value = key
  if (popBurstTimer) clearTimeout(popBurstTimer)
  popBurstTimer = setTimeout(() => {
    popBurstKey.value = ''
  }, 520)
}

watch(
  () => props.habitSyncNonce,
  () => {
    habit.value = loadWeeklyHabitState()
  },
)

const hasActiveSecondaryFilters = computed(
  () => priorityFilter.value !== 'all' || onlyMyWatchlist.value || Boolean(localQuery.value.trim()),
)

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
      saveWeeklyHabitState(habit.value)
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
  return (props.doc.sectors || []).reduce((acc, s) => acc + (s.items || []).length, 0)
})

const readCountForWeek = computed(() => {
  if (!props.doc) return 0
  let count = 0
  const set = readIdSetForWeek.value
  for (const s of props.doc.sectors || []) {
    for (const it of s.items || []) {
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
  for (const s of props.doc.sectors || []) {
    for (const it of s.items || []) allIds.push(it.id)
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
  saveWeeklyHabitState(habit.value)
  emit('habit-changed')
}

function toggleItemRead(itemId: string) {
  const wid = currentWeekId.value
  if (!wid) return
  triggerHaptic(10)
  triggerPopBurst(`read-${itemId}`)
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
  triggerPopBurst('read-all')
  const next = new Set<string>()
  for (const s of props.doc.sectors || []) {
    for (const it of s.items || []) {
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
  triggerPopBurst(`react-${itemId}-${choice}`)
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
  saveWeeklyHabitState(habit.value)
  emit('habit-changed')
}

function toggleOutlookIntuition(outlookId: string, choice: OutlookIntuition) {
  triggerHaptic(10)
  triggerPopBurst(`outlook-${outlookId}-${choice}`)
  const key = `${currentWeekId.value || 'cur'}::${outlookId}`
  const cur = habit.value.outlookStancesById[key]
  const nextMap = { ...habit.value.outlookStancesById }
  if (cur === choice) {
    delete nextMap[key]
  } else {
    nextMap[key] = choice
  }
  habit.value = {
    ...habit.value,
    outlookStancesById: nextMap,
  }
  saveWeeklyHabitState(habit.value)
  emit('habit-changed')
}

function getOutlookIntuition(outlookId: string): OutlookIntuition | undefined {
  const key = `${currentWeekId.value || 'cur'}::${outlookId}`
  return habit.value.outlookStancesById[key]
}

// Match watchlist + portfolio against each weekly item
const personalKeywords = computed<string[]>(() => {
  const out: string[] = []
  const pushKw = (raw: unknown) => {
    if (typeof raw !== 'string') return
    const clean = raw.trim().toLowerCase()
    if (clean.length >= 2) out.push(clean)
  }
  for (const w of props.watchlist || []) {
    if (typeof w === 'string') {
      pushKw(w)
      continue
    }
    if (!w || w.muted) continue
    pushKw(w.label)
    for (const kw of w.keywords || []) pushKw(kw)
  }
  for (const s of props.portfolio?.sectors || []) {
    pushKw(s)
  }
  for (const tk of props.portfolio?.tickers || []) {
    pushKw(tk)
  }
  return Array.from(new Set(out))
})

function getMatchedPersonalTags(item: WeeklyDigestItem): string[] {
  if (personalKeywords.value.length === 0) return []
  const hay = [
    item.plain_title || '',
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
  for (const s of props.doc.sectors || []) {
    for (const it of s.items || []) {
      if (getMatchedPersonalTags(it).length > 0) count += 1
    }
  }
  return count
})

const p0TopHighlights = computed<WeeklyDigestItem[]>(() => {
  if (!props.doc) return []
  const items: WeeklyDigestItem[] = []
  for (const s of props.doc.sectors || []) {
    for (const it of s.items || []) {
      if (it.priority === 'P0') items.push(it)
    }
  }
  return items.sort((a, b) => b.weekly_score - a.weekly_score).slice(0, 6)
})

const filteredSectors = computed(() => {
  if (!props.doc) return []
  const q = localQuery.value.trim().toLowerCase()
  return (props.doc.sectors || [])
    .filter((s) => activeSectorFilter.value === 'all' || s.sector_id === activeSectorFilter.value)
    .map((sec) => {
      const filteredItems = (sec.items || []).filter((it) => {
        if (priorityFilter.value === 'P0' && it.priority !== 'P0') return false
        if (priorityFilter.value === 'P0_P1' && it.priority === 'P2') return false
        if (onlyMyWatchlist.value && getMatchedPersonalTags(it).length === 0) return false
        if (q) {
          const blob = [
            it.plain_title || '',
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

const openStationPredictions = computed<PredictionRecord[]>(() =>
  (props.predictions || []).filter((p) => p.status === 'open'),
)

function resolveLinkedPrediction(outlook: WeeklyNextOutlookItem): PredictionRecord | null {
  const preds = openStationPredictions.value
  if (preds.length === 0) return null
  if (outlook.linked_prediction_id) {
    const exact = preds.find((p) => p.prediction_id === outlook.linked_prediction_id)
    if (exact) return exact
  }
  const hay = `${outlook.topic} ${outlook.plain_forecast}`.toLowerCase()
  const terms = ['美联储', '加息', '降息', '两融', '保证金', '黄仁勋', '英伟达', 'qwen', '阿里', '黄金', '原油', '神舟']
  for (const p of preds) {
    const pt = (p.title || '').toLowerCase()
    for (const term of terms) {
      if (hay.includes(term) && pt.includes(term)) return p
    }
  }
  return null
}

const outlookItems = computed<WeeklyNextOutlookItem[]>(() => {
  const list = props.doc?.next_week_outlook || []
  if (activeSectorFilter.value === 'all') return list
  return list.filter((o) => o.sector_id === activeSectorFilter.value)
})

const unlinkedOpenPredictions = computed<PredictionRecord[]>(() => {
  const linked = new Set<string>()
  for (const o of props.doc?.next_week_outlook || []) {
    const pr = resolveLinkedPrediction(o)
    if (pr) linked.add(pr.prediction_id)
  }
  return openStationPredictions.value.filter((p) => !linked.has(p.prediction_id)).slice(0, 4)
})

const mergedUpcomingSchedule = computed<
  { date: string; title: string; sectorLabel: string; watch: string }[]
>(() => {
  const rows: { date: string; title: string; sectorLabel: string; watch: string }[] = []
  const seenTitles = new Set<string>()
  for (const c of props.doc?.next_week_catalysts || []) {
    const key = (c.title || '').trim().toLowerCase()
    if (!key || seenTitles.has(key)) continue
    seenTitles.add(key)
    rows.push({
      date: c.date,
      title: c.title,
      sectorLabel: getSectorName(c.sector_id),
      watch: c.why_watch,
    })
  }
  for (const ce of props.calendarEvents || []) {
    if (ce.is_past) continue
    const key = (ce.title || '').trim().toLowerCase()
    if (!key || seenTitles.has(key)) continue
    seenTitles.add(key)
    const d = ce.scheduled_at
      ? ce.scheduled_at.slice(0, 10)
      : ce.original_time_note || t('下周关注窗口', 'Upcoming')
    rows.push({
      date: d,
      title: ce.title,
      sectorLabel: ce.region_label || ce.category || '',
      watch: ce.watch_variable || ce.pre_expectation || '',
    })
    if (rows.length >= 6) break
  }
  return rows
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
  return t(
    `每周${DAY_NAMES_ZH[day]?.slice(1) || '日'} ${hh}:${mm} 自动出刊 (Mon-Sun)`,
    `Every ${['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][day]} ${hh}:${mm} CST`,
  )
})

const nextIssueCountdownText = computed(() => {
  if (props.siteSettings.weekly_digest_enabled === false) return ''
  const day = Number(props.siteSettings.weekly_digest_day ?? props.doc?.schedule?.day ?? 0)
  const hour = Number(props.siteSettings.weekly_digest_hour ?? props.doc?.schedule?.hour ?? 18)
  const minute = Number(props.siteSettings.weekly_digest_minute ?? props.doc?.schedule?.minute ?? 0)

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
    return t(
      `今日 ${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')} 更新（约 ${Math.max(1, h)} 小时后）`,
      `Updates in ~${Math.max(1, h)}h`,
    )
  }
  return t(`距下期约 ${d} 天 ${h} 时`, `Next in ${d}d ${h}h`)
})

function priorityMeta(priority: WeeklyPriority) {
  if (priority === 'P0') {
    return {
      label: t('P0 必看重磅', 'P0 Must Read'),
      short: 'P0',
      badgeClass: 'bg-rose-600 text-white border-rose-600 shadow-xs',
    }
  }
  if (priority === 'P1') {
    return {
      label: t('P1 重要进展', 'P1 Key'),
      short: 'P1',
      badgeClass: 'bg-[#007AFF] text-white border-[#007AFF]',
    }
  }
  return {
    label: t('P2 顺带了解', 'P2 Note'),
    short: 'P2',
    badgeClass: 'bg-zinc-600 text-white border-zinc-600',
  }
}

function outlookDirectionMeta(dir: WeeklyOutlookDirection) {
  if (dir === 'up') {
    return {
      icon: ArrowUpRight,
      borderClass: 'border-l-[3px] border-l-emerald-500',
      badgeClass: 'bg-emerald-500/12 text-emerald-700 dark:text-emerald-300 border-emerald-500/25',
      barColor: 'bg-emerald-500',
    }
  }
  if (dir === 'down') {
    return {
      icon: ArrowDownRight,
      borderClass: 'border-l-[3px] border-l-rose-500',
      badgeClass: 'bg-rose-500/12 text-rose-700 dark:text-rose-300 border-rose-500/25',
      barColor: 'bg-rose-500',
    }
  }
  if (dir === 'volatile') {
    return {
      icon: Activity,
      borderClass: 'border-l-[3px] border-l-amber-500',
      badgeClass: 'bg-amber-500/12 text-amber-700 dark:text-amber-300 border-amber-500/25',
      barColor: 'bg-amber-500',
    }
  }
  return {
    icon: Compass,
    borderClass: 'border-l-[3px] border-l-[#007AFF]',
    badgeClass: 'bg-[#007AFF]/12 text-[#007AFF] dark:text-[#0A84FF] border-[#007AFF]/25',
    barColor: 'bg-[#007AFF]',
  }
}

function getSectorName(sid: WeeklySectorId): string {
  const sec = props.doc?.sectors?.find((s) => s.sector_id === sid)
  if (sec) return appLang.value === 'en' ? sec.title_en : sec.title
  const fallback: Record<WeeklySectorId, string> = {
    macro_finance: t('宏观与金融市场', 'Macro & Markets'),
    geopolitics: t('国际地缘与政策', 'Geopolitics & Policy'),
    tech_ai: t('科技与 AI 前沿', 'Tech & AI'),
    industry_society: t('产业与综合要闻', 'Industry & Real Economy'),
  }
  return fallback[sid] || sid
}

function getDisplayTitle(item: WeeklyDigestItem): string {
  if (appLang.value === 'en' && item.title_en) return item.title_en
  return item.plain_title || item.title
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
    `本周主线：${props.doc.week_theme}`,
    '',
    '30秒先看这几件事：',
    ...(props.doc.executive_thesis || []).map((th, i) => `${i + 1}. ${th}`),
    '',
  ]
  for (const sec of props.doc.sectors || []) {
    if ((sec.items || []).length === 0) continue
    lines.push(`=== ${sec.title} (${sec.items.length}条) ===`)
    if (sec.sector_takeaway) lines.push(`人话小结：${sec.sector_takeaway}`)
    for (const it of sec.items) {
      lines.push(`- [${it.priority}] ${it.plain_title || it.title} -> ${it.one_line_takeaway}`)
    }
    lines.push('')
  }
  if ((props.doc.next_week_outlook || []).length > 0) {
    lines.push('=== 下周走向推演 ===')
    for (const o of props.doc.next_week_outlook || []) {
      lines.push(`- ${o.topic}（${o.direction_label}）：${o.plain_forecast}`)
    }
    lines.push('')
  }
  if ((props.doc.next_week_catalysts || []).length > 0) {
    lines.push('下周重要日子：')
    for (const c of props.doc.next_week_catalysts || []) {
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
        {{ t('正在载入本周大事盘点与下周走向…', 'Loading weekly digest and next-week outlook…') }}
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
      <!-- 1. Editorial Weekly Cover Card -->
      <div
        class="ios-card overflow-hidden border border-[#007AFF]/15 bg-gradient-to-br from-[#007AFF]/[0.05] via-white to-amber-500/[0.04] dark:from-[#0A84FF]/[0.12] dark:via-[#131823] dark:to-amber-500/[0.05]"
      >
        <div class="p-4 sm:p-5 space-y-3.5">
          <!-- Meta Row -->
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
                v-if="indexDoc && (indexDoc.issues || []).length > 1"
                :value="doc.week_id"
                @change="(e) => emit('select-week', (e.target as HTMLSelectElement).value)"
                class="h-7 px-2.5 rounded-full bg-white dark:bg-[#1C1C1E] border border-black/[0.08] dark:border-white/[0.12] text-[11px] font-semibold text-zinc-800 dark:text-zinc-100"
                :aria-label="t('切换往期周刊', 'Select weekly issue')"
              >
                <option v-for="iss in indexDoc.issues || []" :key="iss.week_id" :value="iss.week_id">
                  {{ iss.week_id }} ({{ iss.date_range }})
                </option>
              </select>
            </div>
          </div>

          <!-- Plain Theme Headline -->
          <div class="space-y-1">
            <h1 class="text-[17px] sm:text-[20px] font-bold tracking-tight text-zinc-950 dark:text-white leading-snug">
              {{ doc.week_theme }}
            </h1>
            <div class="text-[11px] sm:text-[11.5px] text-zinc-500 dark:text-zinc-400">
              {{
                t(
                  `筛掉 ${doc.stats.raw_scanned} 条快讯水文，只留 ${doc.stats.selected_items} 件真大事（${doc.stats.p0_count} 件 P0 重磅）`,
                  `Distilled ${doc.stats.raw_scanned} items into ${doc.stats.selected_items} key events (${doc.stats.p0_count} P0)`,
                )
              }}
            </div>
          </div>

          <!-- Clickable Keyword Pills (desktop / tablet only to preserve mobile first-screen feed visibility) -->
          <div v-if="(doc.keywords || []).length > 0" class="hidden sm:flex flex-wrap items-center gap-1.5">
            <span class="text-[11px] font-medium text-zinc-400 mr-0.5">{{ t('本周关键词:', 'Themes:') }}</span>
            <button
              v-for="kw in doc.keywords || []"
              :key="kw"
              type="button"
              @click="localQuery = localQuery === kw ? '' : kw; if (viewMode === 'outlook') viewMode = 'deep'; triggerHaptic(6)"
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

          <!-- Slim Habit Progress Bar -->
          <div class="rounded-xl bg-white/85 dark:bg-[#1C1C1E]/85 border border-black/[0.06] dark:border-white/[0.08] px-3 py-2 space-y-1.5">
            <div class="flex items-center justify-between gap-2 text-xs">
              <div class="flex items-center gap-1.5 font-semibold text-zinc-900 dark:text-zinc-100 min-w-0">
                <span class="truncate">{{ t('追更进度', 'Catch-up') }}</span>
                <span class="font-mono text-[#007AFF] dark:text-[#0A84FF] tabular-nums shrink-0">
                  {{ readCountForWeek }}/{{ totalItemCount }} ({{ progressPct }}%)
                </span>
                <span v-if="progressPct === 100 && totalItemCount > 0" class="jx-badge bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 shrink-0">
                  <Check class="w-3 h-3" :stroke-width="2" />
                  <span>{{ t('已扫清', 'Done') }}</span>
                </span>
              </div>

              <div class="flex items-center gap-1.5 shrink-0">
                <button
                  v-if="totalItemCount > 0 && readCountForWeek < totalItemCount"
                  type="button"
                  @click="markAllWeekItemsRead"
                  class="ios-tap mobile-pressable inline-flex items-center gap-1 px-2.5 min-h-[30px] rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-[11px] font-semibold"
                  :class="popBurstKey === 'read-all' ? 'jx-pop-active jx-burst-ring' : ''"
                >
                  <CheckCheck class="w-3.5 h-3.5" :stroke-width="1.75" />
                  <span>{{ t('全标已看', 'Mark All') }}</span>
                </button>
                <button
                  v-else-if="totalItemCount > 0"
                  type="button"
                  @click="emit('open-weekly-poster', { streakWeeks, readCount: readCountForWeek })"
                  class="ios-tap mobile-pressable inline-flex items-center gap-1 px-2.5 min-h-[30px] rounded-lg bg-amber-500 hover:bg-amber-600 text-white text-[11px] font-semibold"
                >
                  <Share2 class="w-3 h-3" />
                  <span>{{ t('晒战绩海报', 'Share Poster') }}</span>
                </button>
              </div>
            </div>

            <div class="h-1.5 w-full rounded-full bg-black/[0.06] dark:bg-white/[0.08] overflow-hidden">
              <div
                class="h-full rounded-full bg-gradient-to-r from-[#007AFF] to-emerald-500 transition-all duration-300"
                :class="progressPct > 0 ? 'jx-progress-shimmer' : ''"
                :style="{ width: `${progressPct}%` }"
              />
            </div>

            <div
              v-if="justCompletedCelebration"
              class="jx-collapse-reveal text-[11px] font-semibold text-emerald-700 dark:text-emerald-300 flex items-center gap-1.5"
            >
              <Check class="w-3.5 h-3.5 shrink-0" />
              <span>{{ t(`这周大事已全部盘完，${scheduleBadgeText} 新刊见。`, `All weekly events reviewed! Streak updated (${scheduleBadgeText}).`) }}</span>
            </div>
          </div>

          <!-- 3-Mode Switcher (fits 390px cleanly with zero right-edge clipping) + Actions -->
          <div class="flex flex-wrap items-center justify-between gap-2 pt-0.5">
            <div class="ios-segmented p-1 grid grid-cols-3 w-full sm:w-auto sm:inline-flex" role="tablist" :aria-label="t('周刊视图切换', 'Weekly mode switcher')">
              <button
                type="button"
                role="tab"
                :aria-selected="viewMode === 'skim'"
                @click="viewMode = 'skim'; triggerHaptic(10)"
                class="ios-segmented-btn min-h-[36px] px-2 sm:px-3 text-xs sm:text-[13px] gap-1"
                :class="viewMode === 'skim' ? 'ios-segmented-btn-active' : 'text-zinc-600 dark:text-zinc-400'"
                data-testid="weekly-mode-skim"
              >
                <Layers class="w-3.5 h-3.5 text-[#007AFF] shrink-0" :stroke-width="1.75" />
                <span class="sm:hidden">{{ t('大概看', 'Skim') }}</span>
                <span class="hidden sm:inline">{{ t('大概看 · 3分钟', 'Skim · 3m') }}</span>
              </button>
              <button
                type="button"
                role="tab"
                :aria-selected="viewMode === 'deep'"
                @click="viewMode = 'deep'; triggerHaptic(10)"
                class="ios-segmented-btn min-h-[36px] px-2 sm:px-3 text-xs sm:text-[13px] gap-1"
                :class="viewMode === 'deep' ? 'ios-segmented-btn-active' : 'text-zinc-600 dark:text-zinc-400'"
                data-testid="weekly-mode-deep"
              >
                <Bot class="w-3.5 h-3.5 text-violet-600 dark:text-violet-400 shrink-0" :stroke-width="1.75" />
                <span class="sm:hidden">{{ t('细看', 'Deep') }}</span>
                <span class="hidden sm:inline">{{ t('细看 · 4板块', 'Deep Dive') }}</span>
              </button>
              <button
                type="button"
                role="tab"
                :aria-selected="viewMode === 'outlook'"
                @click="viewMode = 'outlook'; triggerHaptic(10)"
                class="ios-segmented-btn min-h-[36px] px-2 sm:px-3 text-xs sm:text-[13px] gap-1"
                :class="viewMode === 'outlook' ? 'ios-segmented-btn-active' : 'text-zinc-600 dark:text-zinc-400'"
                data-testid="weekly-mode-outlook"
              >
                <span class="jx-sonar-dot jx-sonar-emerald shrink-0" aria-hidden="true" />
                <span class="sm:hidden">{{ t('下周走向', 'Outlook') }}</span>
                <span class="hidden sm:inline">{{ t('下周走向 · 动态', 'Next Week') }}</span>
                <span
                  v-if="(doc.next_week_outlook || []).length > 0"
                  class="px-1.5 py-0.2 rounded-md bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 text-[10px] font-mono tabular-nums shrink-0"
                >
                  {{ (doc.next_week_outlook || []).length }}
                </span>
              </button>
            </div>

            <div class="flex flex-wrap items-center gap-1.5 w-full sm:w-auto justify-end">
              <button
                type="button"
                @click="emit('open-weekly-poster', { streakWeeks, readCount: readCountForWeek })"
                class="ios-tap mobile-pressable inline-flex items-center gap-1.5 min-h-[36px] px-3 rounded-xl bg-[#007AFF] hover:bg-[#0066D6] text-white text-xs font-semibold shadow-xs"
                data-testid="weekly-poster-btn"
              >
                <Share2 class="w-3.5 h-3.5" :stroke-width="1.75" />
                <span>{{ t('生成周刊海报', 'Poster') }}</span>
              </button>
              <button
                type="button"
                @click="copyWeeklyDigestText"
                class="ios-tap mobile-pressable inline-flex items-center gap-1.5 min-h-[36px] px-3 rounded-xl bg-white dark:bg-[#1C1C1E] border border-black/[0.08] dark:border-white/[0.12] text-zinc-800 dark:text-zinc-100 text-xs font-semibold"
                data-testid="weekly-copy-btn"
              >
                <Check v-if="copiedDigest" class="w-3.5 h-3.5 text-emerald-500" />
                <Copy v-else class="w-3.5 h-3.5" />
                <span>{{ copiedDigest ? t('已复制', 'Copied') : t('复制本周复盘', 'Copy Text') }}</span>
              </button>
              <button
                type="button"
                @click="emit('refresh')"
                class="ios-tap mobile-pressable inline-flex items-center justify-center w-9 h-9 rounded-xl bg-white dark:bg-[#1C1C1E] border border-black/[0.08] dark:border-white/[0.12] text-zinc-600 dark:text-zinc-300"
                :title="t('刷新周刊与实时预测', 'Refresh')"
                :aria-label="t('刷新周刊与实时预测', 'Refresh')"
              >
                <RefreshCw class="w-3.5 h-3.5" :class="{ 'animate-spin': loading }" />
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- 2. Compact 1-Row Sticky Sector Switcher + Inline Filter Trigger -->
      <div class="ios-card px-2.5 py-2 mobile-sticky-subbar flex items-center gap-1.5">
        <div class="flex items-center gap-1.5 min-w-0 flex-1 overflow-x-auto no-scrollbar scroll-fade-x pr-4">
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
            <span>{{ t('全部板块', 'All Sectors') }}</span>
            <span class="font-mono text-[10.5px] opacity-80">{{ doc.stats.selected_items }}</span>
          </button>

          <button
            v-for="sec in doc.sectors || []"
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

        <button
          v-if="viewMode !== 'outlook'"
          type="button"
          @click="filtersOpen = !filtersOpen; triggerHaptic(6)"
          class="ios-tap mobile-pressable inline-flex items-center gap-1 h-8 px-2.5 rounded-xl text-[11.5px] font-semibold shrink-0 transition-colors border"
          :class="
            filtersOpen || hasActiveSecondaryFilters
              ? 'bg-[#007AFF] text-white border-[#007AFF]'
              : 'bg-[#F5F5F7] dark:bg-[#2C2C2E] text-zinc-700 dark:text-zinc-200 border-transparent'
          "
          data-testid="weekly-filter-toggle"
        >
          <SlidersHorizontal class="w-3.5 h-3.5" />
          <span class="hidden sm:inline">{{ t('筛选', 'Filter') }}</span>
        </button>
      </div>

      <!-- Collapsible Secondary Filter Strip (hidden by default to pull real news above the fold) -->
      <div
        v-if="viewMode !== 'outlook' && (filtersOpen || hasActiveSecondaryFilters)"
        class="jx-collapse-reveal ios-card px-3 py-2.5 flex flex-wrap items-center justify-between gap-2"
      >
        <div class="flex flex-wrap items-center gap-1.5">
          <div class="ios-segmented p-0.5">
            <button
              type="button"
              @click="priorityFilter = 'all'"
              class="ios-segmented-btn h-7 px-2.5 text-[11px]"
              :class="priorityFilter === 'all' ? 'ios-segmented-btn-active' : 'text-zinc-500'"
            >
              {{ t('全部重要度', 'All') }}
            </button>
            <button
              type="button"
              @click="priorityFilter = 'P0'"
              class="ios-segmented-btn h-7 px-2.5 text-[11px]"
              :class="priorityFilter === 'P0' ? 'ios-segmented-btn-active text-rose-600' : 'text-zinc-500'"
            >
              {{ t(`只看 P0 重磅 (${doc.stats.p0_count})`, `P0 Only (${doc.stats.p0_count})`) }}
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
            <span>{{ t(`与我关注相关 (${personalHitCount})`, `Matches (${personalHitCount})`) }}</span>
          </button>
        </div>

        <div class="relative flex-1 min-w-[160px] max-w-xs">
          <Search class="w-3.5 h-3.5 text-zinc-400 absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
          <input
            v-model="localQuery"
            type="search"
            :placeholder="t('搜本周事件或关键词…', 'Search this week…')"
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

      <!-- Smooth Animated Mode Transition (Skim / Deep Dive / Next-Week Outlook) -->
      <Transition name="jx-tab" mode="out-in">
      <!-- ====================================================================== -->
      <!-- MODE 3: NEXT-WEEK OUTLOOK & LIVE PREDICTIONS (下周预测走向动态)          -->
      <!-- ====================================================================== -->
      <div v-if="viewMode === 'outlook'" key="outlook" class="space-y-3.5" data-testid="weekly-outlook-panel">
          <!-- Intro strip -->
          <div class="ios-card px-4 py-3 flex flex-wrap items-center justify-between gap-2 bg-gradient-to-r from-emerald-500/[0.06] via-white to-[#007AFF]/[0.05] dark:from-emerald-500/[0.12] dark:via-[#131823] dark:to-[#0A84FF]/[0.08]">
            <div class="space-y-0.5">
              <div class="flex items-center gap-2 text-sm font-bold text-zinc-950 dark:text-white">
                <span class="jx-sonar-dot jx-sonar-emerald" aria-hidden="true" />
                <span>{{ t('下周怎么走 · 实时预测与红线剧本（大白话直说）', 'Next-Week Outlook & Live Station Forecasts') }}</span>
              </div>
              <p class="text-xs text-zinc-600 dark:text-zinc-300">
                {{ t('不谈空话：每条直接给倾向判断、顺风加码条件、翻车红线，并与站内实时概率押注打通。', 'Actionable scenarios with clear upside triggers, downside lines, and live station odds.') }}
              </p>
            </div>
            <button
              type="button"
              @click="emit('switch-tab', 'predictions')"
              class="ios-tap mobile-pressable inline-flex items-center gap-1.5 h-8 px-3 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold shrink-0"
            >
              <Scale class="w-3.5 h-3.5" />
              <span>{{ t('进入全部预测押注区', 'Open Prediction Arena') }}</span>
            </button>
          </div>

          <!-- Outlook Scenario Cards Grid -->
          <div v-if="outlookItems.length === 0" class="ios-card p-6 text-center text-xs text-zinc-500">
            {{ t('当前选中板块暂无独立下周走向推演，可切换“全部 4 大板块”查看完整推演。', 'Select All 4 Sectors to see all outlook tracks.') }}
          </div>
          <div v-else class="grid grid-cols-1 lg:grid-cols-2 gap-3">
            <article
              v-for="item in outlookItems"
              :key="item.id"
              class="ios-card jx-card-interactive p-4 space-y-3"
              :class="outlookDirectionMeta(item.direction).borderClass"
              :data-testid="`weekly-outlook-card-${item.id}`"
            >
              <!-- Card Header -->
              <div class="flex flex-wrap items-start justify-between gap-2">
                <div class="flex flex-wrap items-center gap-1.5">
                  <span class="jx-badge border" :class="SECTOR_VISUALS[item.sector_id].badgeClass">
                    <component :is="SECTOR_VISUALS[item.sector_id].icon" class="w-3 h-3" />
                    <span>{{ getSectorName(item.sector_id) }}</span>
                  </span>
                  <span class="jx-badge border font-semibold" :class="outlookDirectionMeta(item.direction).badgeClass">
                    <component :is="outlookDirectionMeta(item.direction).icon" class="w-3.5 h-3.5" />
                    <span>{{ item.direction_label }}</span>
                  </span>
                </div>
                <span class="text-[11px] font-mono text-zinc-500 dark:text-zinc-400">
                  {{ item.watch_time }}
                </span>
              </div>

              <!-- Topic & Confidence Bar -->
              <div class="space-y-1.5">
                <div class="flex items-center justify-between gap-2">
                  <h3 class="text-[15.5px] font-bold text-zinc-950 dark:text-white leading-snug">
                    {{ item.topic }}
                  </h3>
                  <span class="text-xs font-mono font-bold text-zinc-700 dark:text-zinc-200 tabular-nums shrink-0">
                    {{ t(`把握 ${item.confidence_pct}%`, `${item.confidence_pct}%`) }}
                  </span>
                </div>
                <div class="h-1.5 w-full rounded-full bg-black/[0.06] dark:bg-white/[0.08] overflow-hidden">
                  <div
                    class="h-full rounded-full transition-all duration-300"
                    :class="outlookDirectionMeta(item.direction).barColor"
                    :style="{ width: `${item.confidence_pct}%` }"
                  />
                </div>
              </div>

              <!-- Plain Forecast -->
              <p class="text-[13px] text-zinc-800 dark:text-zinc-100 leading-relaxed font-medium">
                {{ item.plain_forecast }}
              </p>

              <!-- 2 Concrete Triggers -->
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                <div class="rounded-xl bg-emerald-500/[0.07] border border-emerald-500/20 px-3 py-2 space-y-0.5">
                  <div class="font-bold text-emerald-700 dark:text-emerald-300 flex items-center gap-1 text-[11px]">
                    <ArrowUpRight class="w-3.5 h-3.5" />
                    <span>{{ t('顺风剧本（出现就偏强）', 'Bullish Trigger') }}</span>
                  </div>
                  <p class="text-zinc-700 dark:text-zinc-200 leading-relaxed">{{ item.if_up_trigger }}</p>
                </div>

                <div class="rounded-xl bg-rose-500/[0.07] border border-rose-500/20 px-3 py-2 space-y-0.5">
                  <div class="font-bold text-rose-700 dark:text-rose-300 flex items-center gap-1 text-[11px]">
                    <ShieldAlert class="w-3.5 h-3.5" />
                    <span>{{ t('逆风红线（踩到就小心）', 'Risk Redline') }}</span>
                  </div>
                  <p class="text-zinc-700 dark:text-zinc-200 leading-relaxed">{{ item.if_down_trigger }}</p>
                </div>
              </div>

              <!-- Live Dynamic Station Prediction Bridge -->
              <template v-if="resolveLinkedPrediction(item)">
                <div
                  class="rounded-xl bg-[#007AFF]/[0.06] dark:bg-[#0A84FF]/[0.12] border border-[#007AFF]/20 px-3 py-2.5 space-y-2"
                  data-testid="outlook-live-prediction-box"
                >
                  <div class="flex items-start justify-between gap-2">
                    <div class="space-y-0.5 min-w-0">
                      <div class="text-[10.5px] font-bold text-[#007AFF] dark:text-[#0A84FF] uppercase tracking-wide flex items-center gap-1">
                        <Scale class="w-3 h-3" />
                        <span>{{ t('关联站内实时押注题', 'Live Station Market') }}</span>
                      </div>
                      <div class="text-xs font-bold text-zinc-900 dark:text-white leading-snug">
                        {{ resolveLinkedPrediction(item)!.title }}
                      </div>
                    </div>
                    <span class="px-2 py-0.5 rounded-md bg-white dark:bg-[#1C1C1E] font-mono text-[11px] font-bold text-[#007AFF] shrink-0">
                      AI {{ Math.round(resolveLinkedPrediction(item)!.probability_pct ?? 50) }}%
                    </span>
                  </div>

                  <div class="flex flex-wrap items-center justify-between gap-2 text-[11px]">
                    <div class="text-zinc-600 dark:text-zinc-300 font-mono">
                      <template v-if="crowdStats?.[resolveLinkedPrediction(item)!.prediction_id]">
                        <span>
                          {{
                            t(
                              `已有 ${crowdStats[resolveLinkedPrediction(item)!.prediction_id].vote_count} 人投票`,
                              `${crowdStats[resolveLinkedPrediction(item)!.prediction_id].vote_count} votes`,
                            )
                          }}
                        </span>
                        <span v-if="crowdStats[resolveLinkedPrediction(item)!.prediction_id].unlocked && crowdStats[resolveLinkedPrediction(item)!.prediction_id].crowd_avg_pct != null">
                          · {{ t(`人类共识 ${Math.round(crowdStats[resolveLinkedPrediction(item)!.prediction_id].crowd_avg_pct || 0)}%`, `Crowd ${Math.round(crowdStats[resolveLinkedPrediction(item)!.prediction_id].crowd_avg_pct || 0)}%`) }}
                        </span>
                        <span v-if="crowdStats[resolveLinkedPrediction(item)!.prediction_id].user_prob_pct != null" class="text-emerald-600 dark:text-emerald-400 font-semibold">
                          · {{ t(`我押 ${crowdStats[resolveLinkedPrediction(item)!.prediction_id].user_prob_pct}%`, `My vote ${crowdStats[resolveLinkedPrediction(item)!.prediction_id].user_prob_pct}%`) }}
                        </span>
                      </template>
                      <template v-else>
                        <span class="text-[#007AFF] dark:text-[#0A84FF] font-semibold">
                          {{ t(`抢先成为首位预判者 · 截止 ${resolveLinkedPrediction(item)!.due_at.slice(0, 10)}`, `Be first to forecast · Due ${resolveLinkedPrediction(item)!.due_at.slice(0, 10)}`) }}
                        </span>
                      </template>
                    </div>

                    <div class="flex items-center gap-1.5">
                      <button
                        type="button"
                        @click="emit('open-qa-prediction', resolveLinkedPrediction(item)!)"
                        class="ios-tap px-2.5 h-7 rounded-lg bg-white dark:bg-[#1C1C1E] text-zinc-700 dark:text-zinc-200 font-semibold border border-black/[0.08] dark:border-white/[0.1]"
                      >
                        {{ t('AI 推演', 'AI View') }}
                      </button>
                      <button
                        type="button"
                        @click="emit('jump-prediction', resolveLinkedPrediction(item)!.prediction_id)"
                        class="ios-tap px-2.5 h-7 rounded-lg bg-[#007AFF] hover:bg-[#0066D6] text-white font-semibold"
                        data-testid="outlook-jump-pred-btn"
                      >
                        {{
                          crowdStats?.[resolveLinkedPrediction(item)!.prediction_id]?.user_prob_pct != null
                            ? t('去改预判', 'Update Vote')
                            : t('去押注一票', 'Vote Now')
                        }}
                      </button>
                    </div>
                  </div>
                </div>
              </template>

              <!-- 1-Tap Habit Intuition Check-in -->
              <div class="flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-black/[0.05] dark:border-white/[0.06] text-[11px]">
                <span class="text-zinc-500 dark:text-zinc-400 font-medium">{{ t('你自己的直觉判断：', 'Your weekly call:') }}</span>
                <div class="flex items-center gap-1.5">
                  <button
                    type="button"
                    @click="toggleOutlookIntuition(item.id, 'up')"
                    class="ios-tap px-2.5 h-7 rounded-lg font-semibold border transition-colors"
                    :class="[
                      getOutlookIntuition(item.id) === 'up'
                        ? 'bg-emerald-600 text-white border-emerald-600'
                        : 'bg-white dark:bg-[#1C1C1E] text-zinc-600 dark:text-zinc-300 border-black/[0.08] dark:border-white/[0.1]',
                      popBurstKey === `outlook-${item.id}-up` ? 'jx-pop-active jx-burst-ring' : '',
                    ]"
                    data-testid="outlook-stance-up"
                  >
                    {{ t('我看顺风', 'Bullish') }}
                  </button>
                  <button
                    type="button"
                    @click="toggleOutlookIntuition(item.id, 'volatile')"
                    class="ios-tap px-2.5 h-7 rounded-lg font-semibold border transition-colors"
                    :class="[
                      getOutlookIntuition(item.id) === 'volatile'
                        ? 'bg-amber-500 text-white border-amber-500'
                        : 'bg-white dark:bg-[#1C1C1E] text-zinc-600 dark:text-zinc-300 border-black/[0.08] dark:border-white/[0.1]',
                      popBurstKey === `outlook-${item.id}-volatile` ? 'jx-pop-active jx-burst-ring' : '',
                    ]"
                  >
                    {{ t('我看震荡', 'Choppy') }}
                  </button>
                  <button
                    type="button"
                    @click="toggleOutlookIntuition(item.id, 'down')"
                    class="ios-tap px-2.5 h-7 rounded-lg font-semibold border transition-colors"
                    :class="[
                      getOutlookIntuition(item.id) === 'down'
                        ? 'bg-rose-600 text-white border-rose-600'
                        : 'bg-white dark:bg-[#1C1C1E] text-zinc-600 dark:text-zinc-300 border-black/[0.08] dark:border-white/[0.1]',
                      popBurstKey === `outlook-${item.id}-down` ? 'jx-pop-active jx-burst-ring' : '',
                    ]"
                  >
                    {{ t('我看承压', 'Cautious') }}
                  </button>
                </div>
              </div>
            </article>
          </div>

          <!-- Upcoming Calendar + Other Live Station Predictions -->
          <div class="grid grid-cols-1 lg:grid-cols-2 gap-3">
            <div class="ios-card p-4 space-y-2.5">
              <div class="flex items-center justify-between gap-2">
                <div class="flex items-center gap-2">
                  <Calendar class="w-4 h-4 text-[#007AFF]" :stroke-width="1.75" />
                  <h3 class="text-sm font-bold text-zinc-950 dark:text-white">
                    {{ t('下周关键日子与盯盘点', 'Upcoming Key Dates') }}
                  </h3>
                </div>
                <button
                  type="button"
                  @click="emit('switch-tab', 'calendar')"
                  class="text-[11px] font-semibold text-[#007AFF] hover:underline"
                >
                  {{ t('查看全部日程', 'Full Calendar') }}
                </button>
              </div>
              <div v-if="mergedUpcomingSchedule.length === 0" class="ios-surface-2 p-3 text-xs text-zinc-500">
                {{ t('下周日程正在随全站数据实时更新中。', 'Calendar updating from live feed.') }}
              </div>
              <div v-else class="space-y-2">
                <div v-for="(ev, idx) in mergedUpcomingSchedule" :key="idx" class="ios-surface-2 px-3 py-2 space-y-0.5">
                  <div class="flex items-center justify-between gap-2 text-[11px]">
                    <span class="font-mono font-bold text-[#007AFF] dark:text-[#0A84FF]">{{ ev.date }}</span>
                    <span class="text-zinc-500 dark:text-zinc-400">{{ ev.sectorLabel }}</span>
                  </div>
                  <div class="text-xs font-bold text-zinc-900 dark:text-white">{{ ev.title }}</div>
                  <p v-if="ev.watch" class="text-[11.5px] text-zinc-600 dark:text-zinc-300">{{ ev.watch }}</p>
                </div>
              </div>
            </div>

            <div class="ios-card p-4 space-y-2.5">
              <div class="flex items-center justify-between gap-2">
                <div class="flex items-center gap-2">
                  <Target class="w-4 h-4 text-emerald-600 dark:text-emerald-400" :stroke-width="1.75" />
                  <h3 class="text-sm font-bold text-zinc-950 dark:text-white">
                    {{ t('更多进行中的实时预测题', 'More Live Forecasts') }}
                  </h3>
                </div>
                <button
                  type="button"
                  @click="emit('switch-tab', 'predictions')"
                  class="text-[11px] font-semibold text-emerald-600 hover:underline"
                >
                  {{ t('去投票赢连胜', 'Open Arena') }}
                </button>
              </div>
              <div v-if="unlinkedOpenPredictions.length === 0 && openStationPredictions.length === 0" class="ios-surface-2 p-3 text-xs text-zinc-500">
                {{ t('当前实时预测题目已在上方走向卡片全部展示。', 'All open forecasts are shown above.') }}
              </div>
              <div v-else class="space-y-2">
                <div
                  v-for="pr in unlinkedOpenPredictions.length > 0 ? unlinkedOpenPredictions : openStationPredictions.slice(0, 4)"
                  :key="pr.prediction_id"
                  class="ios-surface-2 px-3 py-2.5 flex items-center justify-between gap-2"
                >
                  <div class="min-w-0 space-y-0.5">
                    <div class="text-xs font-bold text-zinc-900 dark:text-white line-clamp-1">{{ pr.title }}</div>
                    <div class="text-[11px] font-mono text-zinc-500 dark:text-zinc-400">
                      AI {{ Math.round(pr.probability_pct ?? 50) }}% · {{ t('截止', 'Due') }} {{ pr.due_at.slice(0, 10) }}
                    </div>
                  </div>
                  <button
                    type="button"
                    @click="emit('jump-prediction', pr.prediction_id)"
                    class="ios-tap px-2.5 h-7 rounded-lg bg-[#007AFF] text-white text-[11px] font-semibold shrink-0"
                  >
                    {{ t('去押注', 'Vote') }}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      <!-- ====================================================================== -->
      <!-- MODES 1 & 2: SKIM / DEEP DIVE WEEKLY EVENTS                             -->
      <!-- ====================================================================== -->
      <div v-else :key="viewMode" class="space-y-3.5">
        <!-- Executive 3-Bullet Plain Thesis & P0 Fast Overview -->
        <div class="ios-card overflow-hidden">
          <button
            type="button"
            @click="thesisExpanded = !thesisExpanded"
            class="w-full px-4 py-3 flex items-center justify-between gap-2 text-left hover:bg-black/[0.02] dark:hover:bg-white/[0.02]"
          >
            <div class="flex items-center gap-2 min-w-0">
              <Sparkles class="w-4 h-4 text-[#007AFF] shrink-0" :stroke-width="1.75" />
              <span class="text-sm font-bold text-zinc-950 dark:text-white">
                {{ t('30 秒先看这 3 件事 · 本周必看重磅速览', '30-Second Brief & Top P0 Events') }}
              </span>
            </div>
            <ChevronUp v-if="thesisExpanded" class="w-4 h-4 text-zinc-400 shrink-0" />
            <ChevronDown v-else class="w-4 h-4 text-zinc-400 shrink-0" />
          </button>

          <div v-if="thesisExpanded" class="px-4 pb-4 pt-1 border-t border-black/[0.05] dark:border-white/[0.07] space-y-3 jx-collapse-reveal">
            <div class="grid grid-cols-1 md:grid-cols-3 gap-2">
              <div
                v-for="(line, idx) in doc.executive_thesis || []"
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
                <span>{{ t('本周最高优先级 P0 必看大事（点哪条直接进对应板块细看）', 'Top P0 Events Across 4 Sectors') }}</span>
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
                      {{ getDisplayTitle(p0) }}
                    </div>
                  </div>
                  <ArrowRight class="w-3.5 h-3.5 text-rose-500 shrink-0 mt-1" />
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- Strictly Separated 4-Sector Event Panels -->
        <div class="space-y-3.5">
          <section
            v-for="sec in filteredSectors"
            :key="sec.sector_id"
            class="ios-card overflow-hidden"
            :data-testid="`weekly-sector-card-${sec.sector_id}`"
          >
            <!-- Sector Header -->
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
              {{ t('当前筛选条件下该板块没有匹配新闻，可放宽重要度或清掉搜索词。', 'No matching events in this sector under current filters.') }}
            </div>

            <!-- Items List -->
            <div v-else class="divide-y divide-black/[0.06] dark:divide-white/[0.07]">
              <article
                v-for="item in sec.filteredItems"
                :key="item.id"
                class="px-4 py-3.5 transition-colors hover:bg-black/[0.015] dark:hover:bg-white/[0.02]"
                :class="[
                  item.priority === 'P0' ? 'border-l-[3px] border-l-[#DC2626]' : '',
                  readIdSetForWeek.has(item.id) ? 'bg-black/[0.015] dark:bg-white/[0.015]' : '',
                ]"
                :data-testid="`weekly-item-${item.id}`"
              >
                <!-- Skim Row -->
                <template v-if="viewMode === 'skim' && !expandedIds.has(item.id)">
                  <div class="flex items-start gap-2.5">
                    <button
                      type="button"
                      @click="toggleItemRead(item.id)"
                      class="ios-tap mt-0.5 w-6 h-6 rounded-full border flex items-center justify-center shrink-0 transition-all"
                      :class="[
                        readIdSetForWeek.has(item.id)
                          ? 'bg-emerald-500 border-emerald-500 text-white scale-105'
                          : 'border-zinc-300 dark:border-zinc-600 text-transparent hover:border-[#007AFF]',
                        popBurstKey === `read-${item.id}` ? 'jx-pop-active jx-burst-ring' : '',
                      ]"
                      :title="readIdSetForWeek.has(item.id) ? t('取消已看', 'Mark unread') : t('打卡：我已看完', 'Mark reviewed')"
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
                          {{ t('与我关注相关', 'Watchlist Hit') }}
                        </span>
                        <span class="text-[11px] text-zinc-400 font-mono tabular-nums">
                          {{ item.first_seen }}<template v-if="item.day_span > 1"> · {{ t(`连跟${item.day_span}天`, `${item.day_span}d`) }}</template>
                          · {{ item.source_count }}{{ t('家信源', ' src') }}
                        </span>
                      </div>

                      <h3
                        @click="toggleItemExpand(item.id)"
                        class="text-[14.5px] font-bold leading-snug cursor-pointer transition-colors"
                        :class="readIdSetForWeek.has(item.id) ? 'text-zinc-500 dark:text-zinc-400' : 'text-zinc-950 dark:text-white hover:text-[#007AFF]'"
                      >
                        {{ getDisplayTitle(item) }}
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
                        :title="t('AI 大白话深问', 'AI Q&A')"
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

                <!-- Deep Mode Card -->
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
                          <template v-if="item.day_span > 1"> · {{ t(`连跟 ${item.day_span} 天`, `${item.day_span} days`) }}</template>
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

                    <div class="space-y-0.5">
                      <h3 class="text-[15.5px] sm:text-base font-bold text-zinc-950 dark:text-white leading-snug">
                        {{ getDisplayTitle(item) }}
                      </h3>
                      <p
                        v-if="item.plain_title && item.plain_title !== item.title && item.title.length > 28"
                        class="text-[11px] text-zinc-400 leading-snug"
                      >
                        {{ t('原新闻标题：', 'Original headline:') }} {{ item.title }}
                      </p>
                    </div>

                    <p class="text-[13px] text-zinc-700 dark:text-zinc-200 leading-relaxed">
                      <span class="font-semibold text-zinc-900 dark:text-white mr-1">{{ t('发生了什么：', 'Core Fact:') }}</span>
                      {{ item.fact_summary }}
                    </p>

                    <!-- Two Plain-Language Analysis Boxes -->
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-2">
                      <div class="ios-surface-2 px-3 py-2.5 space-y-1">
                        <div class="text-[11px] font-bold text-[#007AFF] dark:text-[#0A84FF] flex items-center gap-1">
                          <Sparkles class="w-3 h-3" />
                          <span>{{ t('说人话：这事有啥实际影响', 'Plain-Talk Impact') }}</span>
                        </div>
                        <p class="text-xs leading-relaxed text-zinc-700 dark:text-zinc-200">
                          {{ item.why_it_matters }}
                        </p>
                      </div>

                      <div class="ios-surface-2 px-3 py-2.5 space-y-1">
                        <div class="text-[11px] font-bold text-amber-600 dark:text-amber-400 flex items-center gap-1">
                          <Target class="w-3 h-3" />
                          <span>{{ t('下周盯紧哪个信号', 'Next-Week Signal') }}</span>
                        </div>
                        <p class="text-xs leading-relaxed text-zinc-700 dark:text-zinc-200">
                          {{ item.next_week_watch }}
                        </p>
                      </div>
                    </div>

                    <!-- Evolution Timeline Strip -->
                    <div v-if="item.evolution_steps && item.evolution_steps.length > 1" class="rounded-xl border border-black/[0.06] dark:border-white/[0.08] px-3 py-2 space-y-1.5">
                      <div class="text-[11px] font-bold text-zinc-500 dark:text-zinc-400">
                        {{ t(`这事本周怎么演变过来的（${item.evolution_steps.length} 个节点）`, `Weekly Progression (${item.evolution_steps.length} steps)`) }}
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

                    <!-- Entities, Impact Tags & Primary Sources -->
                    <div class="flex flex-wrap items-center gap-1.5 text-[11px]">
                      <span
                        v-for="ent in (item.entities || []).slice(0, 4)"
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
                      <template v-for="(src, sIdx) in (item.sources || []).slice(0, 3)" :key="`${item.id}-src-${sIdx}`">
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

                    <!-- Tactile Action Row -->
                    <div class="flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-black/[0.05] dark:border-white/[0.06]">
                      <div class="flex flex-wrap items-center gap-1.5">
                        <button
                          type="button"
                          @click="toggleItemRead(item.id)"
                          class="ios-tap mobile-pressable inline-flex items-center gap-1.5 h-8 px-3 rounded-xl text-xs font-semibold transition-all"
                          :class="[
                            readIdSetForWeek.has(item.id)
                              ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border border-emerald-500/30'
                              : 'bg-[#F5F5F7] dark:bg-[#2C2C2E] text-zinc-700 dark:text-zinc-200 hover:bg-emerald-500/10',
                            popBurstKey === `read-${item.id}` ? 'jx-pop-active jx-burst-ring' : '',
                          ]"
                          :data-testid="`weekly-deep-check-${item.id}`"
                        >
                          <Check class="w-3.5 h-3.5" :stroke-width="2.2" />
                          <span>{{ readIdSetForWeek.has(item.id) ? t('已看打卡', 'Reviewed') : t('标记已看', 'Mark Done') }}</span>
                        </button>

                        <button
                          type="button"
                          @click="toggleReaction(item.id, 'bull')"
                          class="ios-tap mobile-pressable inline-flex items-center gap-1 h-8 px-2.5 rounded-xl text-[11px] font-semibold border transition-colors"
                          :class="[
                            habit.reactionsByItem[item.id] === 'bull'
                              ? 'bg-emerald-600 text-white border-emerald-600'
                              : 'bg-white dark:bg-[#1C1C1E] text-zinc-600 dark:text-zinc-300 border-black/[0.08] dark:border-white/[0.1]',
                            popBurstKey === `react-${item.id}-bull` ? 'jx-pop-active jx-burst-ring' : '',
                          ]"
                        >
                          <span>{{ t('还会发酵', 'Ongoing') }}</span>
                        </button>
                        <button
                          type="button"
                          @click="toggleReaction(item.id, 'bear')"
                          class="ios-tap mobile-pressable inline-flex items-center gap-1 h-8 px-2.5 rounded-xl text-[11px] font-semibold border transition-colors"
                          :class="[
                            habit.reactionsByItem[item.id] === 'bear'
                              ? 'bg-rose-600 text-white border-rose-600'
                              : 'bg-white dark:bg-[#1C1C1E] text-zinc-600 dark:text-zinc-300 border-black/[0.08] dark:border-white/[0.1]',
                            popBurstKey === `react-${item.id}-bear` ? 'jx-pop-active jx-burst-ring' : '',
                          ]"
                        >
                          <span>{{ t('小心反转', 'Reversal Risk') }}</span>
                        </button>
                      </div>

                      <div class="flex flex-wrap items-center gap-1.5">
                        <button
                          type="button"
                          @click="emit('open-qa-item', item)"
                          class="ios-tap mobile-pressable inline-flex items-center gap-1 h-8 px-2.5 rounded-xl bg-[#007AFF]/10 hover:bg-[#007AFF]/18 text-[#007AFF] dark:text-[#0A84FF] text-xs font-semibold"
                        >
                          <Bot class="w-3.5 h-3.5" :stroke-width="1.75" />
                          <span>{{ t('AI 深问', 'AI Review') }}</span>
                        </button>
                        <button
                          type="button"
                          @click="emit('open-finance-keyword', (item.entities || [])[0] || item.impact_tags?.[0] || item.title.slice(0, 8))"
                          class="ios-tap mobile-pressable inline-flex items-center gap-1 h-8 px-2.5 rounded-xl bg-[#F5F5F7] dark:bg-[#2C2C2E] hover:bg-black/[0.08] dark:hover:bg-white/[0.12] text-zinc-700 dark:text-zinc-200 text-xs font-semibold"
                        >
                          <TrendingUp class="w-3.5 h-3.5" :stroke-width="1.75" />
                          <span>{{ t('看股市传导', 'Markets') }}</span>
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

        <!-- Bottom Preview Teaser -> Jump straight into Next-Week Outlook Tab -->
        <div
          v-if="(doc.next_week_outlook || []).length > 0"
          class="ios-card p-4 space-y-3 border border-emerald-500/20 bg-gradient-to-br from-emerald-500/[0.04] to-white dark:from-emerald-500/[0.1] dark:to-[#131823]"
        >
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="flex items-center gap-2">
              <span class="jx-sonar-dot jx-sonar-emerald" aria-hidden="true" />
              <h3 class="text-sm font-bold text-zinc-950 dark:text-white">
                {{ t('下周走向抢先看（不讲空话，看剧本与赔率）', 'Next-Week Outlook Preview') }}
              </h3>
            </div>
            <button
              type="button"
              @click="viewMode = 'outlook'; triggerHaptic(10)"
              class="ios-tap inline-flex items-center gap-1 px-3 h-8 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold"
            >
              <span>{{ t(`展开全部 ${(doc.next_week_outlook || []).length} 条下周走向 + 押注`, `All ${(doc.next_week_outlook || []).length} Scenarios`) }}</span>
              <ArrowRight class="w-3.5 h-3.5" />
            </button>
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
            <div
              v-for="o in (doc.next_week_outlook || []).slice(0, 2)"
              :key="o.id"
              class="ios-surface-2 px-3 py-2.5 space-y-1 cursor-pointer hover:ring-1 hover:ring-emerald-500/40"
              @click="viewMode = 'outlook'"
            >
              <div class="flex items-center justify-between gap-2 text-[11px]">
                <span class="font-bold text-emerald-700 dark:text-emerald-300">{{ o.direction_label }}</span>
                <span class="font-mono text-zinc-400">{{ o.watch_time }}</span>
              </div>
              <div class="text-xs font-bold text-zinc-900 dark:text-white">{{ o.topic }}</div>
              <p class="text-xs text-zinc-600 dark:text-zinc-300 line-clamp-2 leading-relaxed">{{ o.plain_forecast }}</p>
            </div>
          </div>
        </div>

        <!-- Cross-Sector Threads & Key Next-Week Calendar -->
        <div
          v-if="(doc.cross_sector_threads || []).length > 0 || mergedUpcomingSchedule.length > 0"
          class="grid grid-cols-1 lg:grid-cols-2 gap-3"
        >
          <div v-if="(doc.cross_sector_threads || []).length > 0" class="ios-card p-4 space-y-2.5">
            <div class="flex items-center gap-2">
              <Link2 class="w-4 h-4 text-violet-600 dark:text-violet-400 shrink-0" :stroke-width="1.75" />
              <h3 class="text-sm font-bold text-zinc-950 dark:text-white">
                {{ t('几件事怎么串在一起（跨板块暗线）', 'Cross-Sector Causal Threads') }}
              </h3>
            </div>
            <div class="space-y-2">
              <div
                v-for="(th, idx) in doc.cross_sector_threads || []"
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

          <div class="ios-card p-4 space-y-2.5">
            <div class="flex items-center justify-between gap-2">
              <div class="flex items-center gap-2">
                <Target class="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" :stroke-width="1.75" />
                <h3 class="text-sm font-bold text-zinc-950 dark:text-white">
                  {{ t('下周关键日子与盯盘点', 'Upcoming Catalysts & Forecasts') }}
                </h3>
              </div>
              <button
                type="button"
                @click="emit('switch-tab', 'predictions')"
                class="ios-tap inline-flex items-center gap-1 px-2.5 h-7 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-[11px] font-semibold shrink-0"
              >
                <span>{{ t('去前瞻区押注', 'Forecasts') }}</span>
                <ArrowRight class="w-3 h-3" />
              </button>
            </div>

            <div v-if="mergedUpcomingSchedule.length === 0" class="ios-surface-2 p-3 text-xs text-zinc-500">
              {{ t('下周日历正在随 24h 数据流实时同步，可前往「预测日程」查看完整日程表。', 'Check Forecasts & Calendar tab for full upcoming schedule.') }}
            </div>
            <div v-else class="space-y-2">
              <div
                v-for="(cat, idx) in mergedUpcomingSchedule.slice(0, 4)"
                :key="idx"
                class="ios-surface-2 p-3 space-y-1"
              >
                <div class="flex flex-wrap items-center justify-between gap-1.5 text-[11px]">
                  <span class="font-mono font-bold text-[#007AFF] dark:text-[#0A84FF]">{{ cat.date }}</span>
                  <span class="text-zinc-500 dark:text-zinc-400">{{ cat.sectorLabel }}</span>
                </div>
                <div class="text-xs font-bold text-zinc-900 dark:text-white">
                  {{ cat.title }}
                </div>
                <p v-if="cat.watch" class="text-xs text-zinc-600 dark:text-zinc-300 leading-relaxed">
                  {{ cat.watch }}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
      </Transition>
    </template>
  </section>
</template>
