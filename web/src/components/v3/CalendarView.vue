<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Calendar, Check, ChevronDown, ChevronRight, Clock, ExternalLink, MapPin, Pencil, Plus, Trash2, Zap } from 'lucide-vue-next'
import EmptySearchState from '../EmptySearchState.vue'
import SmartTime from '../SmartTime.vue'
import { pickBiText, t } from '../../core/i18n'
import { centerPillIntoView } from '../../core/dom'
import { stripEmoji } from '../../core/icons'
import { normalizeExternalUrl } from '../../core/legacyAdapter'
import { matchesSmartQuery } from '../../core/search'
import { formatShanghaiDateOnly, parseTimestampMs } from '../../core/time'
import type { CatalystEvent, WatchlistItem } from '../../core/types'

const props = defineProps<{
  events: CatalystEvent[]
  customEvents: CatalystEvent[]
  watchlist: WatchlistItem[]
  searchQuery?: string
  nowMs?: number
}>()

const emit = defineEmits<{
  (e: 'add-custom-catalyst', ev: CatalystEvent): void
  (e: 'update-custom-catalyst', ev: CatalystEvent): void
  (e: 'delete-custom-catalyst', calendarId: string): void
  (e: 'save-catalyst-actual', payload: { calendarId: string; actualResult: string; deviation: string }): void
  (e: 'clear-catalyst-actual', calendarId: string): void
  (e: 'open-storyline', storylineId: string): void
  (e: 'jump-event-id', eventId: string): void
  (e: 'clear-search'): void
}>()

const internalNowMs = ref(Date.now())
let timerId: ReturnType<typeof setInterval> | null = null
onMounted(() => {
  timerId = setInterval(() => {
    internalNowMs.value = Date.now()
  }, 60_000)
})
onBeforeUnmount(() => {
  if (timerId) clearInterval(timerId)
})
const effectiveNowMs = computed(() => props.nowMs ?? internalNowMs.value)

const certaintyFilter = ref<'all' | 'confirmed_official' | 'tbd'>('all')
const eventTypeFilter = ref<string>('all')
const regionFilter = ref<string>('all')
const quickJumpKey = ref<string>('')
const onlyWatched = ref(false)
const showPastEvents = ref(false)
const selectedDayFilter = ref<string | null>(null)
const expandedDetailIds = ref<Set<string>>(new Set())
const allDetailsExpanded = ref(false)
const showCustomForm = ref(false)
const editingCustomId = ref<string | null>(null)
const editingId = ref<string | null>(null)
const draftActual = ref('')
const draftDeviation = ref('')
const subActionMsg = ref<string | null>(null)

// Custom form fields
const cTitle = ref('')
const cDate = ref('2026-11-25T20:00')
const cVar = ref('')
const cExpect = ref('')

function setFeedbackMsg(msg: string) {
  subActionMsg.value = msg
  setTimeout(() => {
    if (subActionMsg.value === msg) subActionMsg.value = null
  }, 3500)
}

interface QuickJumpPillSpec {
  id: string
  zh: string
  en: string
  re: RegExp
}

const QUICK_JUMP_BY_REGION: Record<string, readonly QuickJumpPillSpec[]> = {
  all: [
    { id: 'gz_canton', zh: '广州广交会', en: 'Canton Fair', re: /广州|广交会|canton\s*fair/i },
    { id: 'sz_tech', zh: '深圳高交/APEC', en: 'Shenzhen Expos', re: /深圳|高交会|文博会|apec.*深圳|深圳.*apec/i },
    { id: 'us_fomc', zh: '美联储 FOMC', en: 'Fed FOMC', re: /fomc|美联储.*议息|美联储.*利率|powell/i },
    { id: 'us_gtc', zh: 'NVIDIA GTC', en: 'NVIDIA GTC', re: /\bgtc\b|英伟达.*gtc/i },
    { id: 'eu_mwc', zh: '巴塞罗那 MWC', en: 'MWC Barcelona', re: /巴塞罗那|barcelona|mwc\s*barcelona|mobile world congress/i },
  ],
  china: [
    { id: 'gz_canton', zh: '广州广交会', en: 'Canton Fair', re: /广州|广交会|canton\s*fair/i },
    { id: 'sz_tech', zh: '深圳高交/APEC', en: 'Shenzhen Expos', re: /深圳|高交会|文博会|apec.*深圳|深圳.*apec/i },
    { id: 'sh_waic', zh: '上海进博/WAIC', en: 'Shanghai Expos', re: /上海|进博会|waic|世界人工智能大会|mwc\s*shanghai|上海.*mwc/i },
    { id: 'bj_npc', zh: '北京两会/中关村', en: 'Beijing Policy/Tech', re: /两会|全国人代会|全国政协|中关村论坛|服贸会|北京/i },
    { id: 'hn_boao', zh: '海南消博/博鳌', en: 'Hainan Expo/Boao', re: /海南|海口|博鳌|消博会/i },
  ],
  us: [
    { id: 'us_fomc', zh: '美联储 FOMC', en: 'Fed FOMC', re: /fomc|美联储.*议息|美联储.*利率|fed\s*rate/i },
    { id: 'us_ces', zh: 'CES 拉斯维加斯', en: 'CES Vegas', re: /\bces\b|拉斯维加斯/i },
    { id: 'us_gtc', zh: 'NVIDIA GTC', en: 'NVIDIA GTC', re: /\bgtc\b|英伟达.*gtc|圣何塞/i },
    { id: 'us_wwdc', zh: 'Apple WWDC', en: 'Apple WWDC', re: /wwdc|苹果.*开发/i },
    { id: 'us_io', zh: 'Google I/O', en: 'Google I/O', re: /google\s*i\/o|谷歌.*i\/o/i },
    { id: 'us_cpi', zh: '美国 CPI / PCE', en: 'US CPI / PCE', re: /美国.*(?:cpi|pce|非农)|cpi|pce/i },
  ],
  europe_apac: [
    { id: 'eu_mwc', zh: '巴塞罗那 MWC', en: 'MWC Barcelona', re: /巴塞罗那|barcelona|mwc\s*barcelona|mobile world congress/i },
    { id: 'eu_cb', zh: '欧洲/日本央行', en: 'ECB / BOJ', re: /欧洲央行|\becb\b|日本央行|\bboj\b|法兰克福|东京/i },
    { id: 'tw_computex', zh: '台北 COMPUTEX', en: 'COMPUTEX Taipei', re: /computex|台北/i },
    { id: 'eu_auto', zh: '慕尼黑/巴黎车展', en: 'Munich/Paris Motor', re: /慕尼黑|巴黎|iaa|davos|伦敦/i },
  ],
  global: [
    { id: 'gl_davos', zh: '达沃斯 WEF', en: 'Davos WEF', re: /达沃斯|davos|\bwef\b/i },
    { id: 'gl_cop', zh: 'UNFCCC COP', en: 'Climate COP', re: /\bcop\d+|联合国气候/i },
    { id: 'gl_opec', zh: 'OPEC+ 部长会', en: 'OPEC+ Ministerial', re: /opec/i },
    { id: 'gl_g20', zh: 'G20 / APEC', en: 'G20 / APEC', re: /\bg20\b|\bapec\b|\bg7\b/i },
  ],
}

const activeQuickJumpPills = computed<readonly QuickJumpPillSpec[]>(() => {
  return QUICK_JUMP_BY_REGION[regionFilter.value] || QUICK_JUMP_BY_REGION.all
})

watch(regionFilter, () => {
  quickJumpKey.value = ''
})

/** B3: Strict distinction between clock-TBD events, ended dates, and active countdowns */
function isClockTbd(ev: CatalystEvent): boolean {
  if (ev.is_clock_tbd || ev.certainty === 'tbd' || ev.certainty === 'reported_tbd') return true
  const note = ev.original_time_note || ''
  return /钟点待定|时间待定|待官方|TBD/i.test(note)
}

function isEventPast(ev: CatalystEvent): boolean {
  if (ev.is_past) return true
  if (!ev.scheduled_at) return false
  const ms = parseTimestampMs(ev.scheduled_at)
  if (ms === null) return false
  const todayStr = formatShanghaiDateOnly(new Date(effectiveNowMs.value).toISOString())
  const evDateStr = formatShanghaiDateOnly(ev.scheduled_at)
  if (evDateStr < todayStr) return true
  if (!isClockTbd(ev) && ms < effectiveNowMs.value - 2 * 3_600_000) return true
  return false
}

function getReviewTarget(ev: CatalystEvent): { type: 'storyline' | 'event'; id: string } | null {
  if (ev.storyline_id) return { type: 'storyline', id: ev.storyline_id }
  if (ev.event_id) return { type: 'event', id: ev.event_id }
  if (ev.calendar_id.startsWith('cal_evt_')) {
    return { type: 'event', id: ev.calendar_id.slice('cal_evt_'.length) }
  }
  return null
}

function openReview(ev: CatalystEvent) {
  const target = getReviewTarget(ev)
  if (!target) return
  if (target.type === 'storyline') {
    emit('open-storyline', target.id)
  } else {
    emit('jump-event-id', target.id)
  }
}

function formatCountdown(ev: CatalystEvent): { label: string; toneClass: string } | null {
  if (isEventPast(ev)) {
    return {
      label: t('已结束', 'Ended'),
      toneClass: 'bg-slate-100 text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700',
    }
  }
  if (!ev.scheduled_at) return null
  const dayDelta = computeDayDelta(ev)
  if (isClockTbd(ev)) {
    if (dayDelta !== null && dayDelta >= 1) {
      return {
        label: dayDelta === 1 ? t('明天 · 距离开启还有 1 天', 'Tomorrow · 1d') : t(`距窗口约 ${dayDelta} 天`, `~${dayDelta}d out`),
        toneClass: dayDelta === 1
          ? 'bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-950/50 dark:text-amber-300 dark:border-amber-800'
          : 'bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-950/50 dark:text-amber-300 dark:border-amber-800',
      }
    }
    return {
      label: t('当日待定', 'Today TBD'),
      toneClass: 'bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-950/50 dark:text-amber-300 dark:border-amber-800',
    }
  }
  const ms = parseTimestampMs(ev.scheduled_at)
  if (ms === null) return null
  const diffMs = ms - effectiveNowMs.value
  if (diffMs < 0) {
    return {
      label: t('正在进行', 'In Progress'),
      toneClass: 'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/50 dark:text-blue-300 dark:border-blue-800',
    }
  }
  if (dayDelta === 0) {
    const hours = Math.max(1, Math.floor(diffMs / 3_600_000))
    return {
      label: hours <= 1 ? t('即将开始', 'Starting Soon') : t(`今日 · 还剩 ${hours} 小时`, `Today · ${hours}h left`),
      toneClass: 'bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/50 dark:text-rose-300 dark:border-rose-800',
    }
  }
  const days = dayDelta !== null ? dayDelta : Math.max(1, Math.ceil(diffMs / 86_400_000))
  if (days === 1) {
    return {
      label: t('距离开启还有 1 天', 'Tomorrow · 1d left'),
      toneClass: 'bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-950/50 dark:text-amber-200 dark:border-amber-800',
    }
  }
  return {
    label: t(`距离开启还有 ${days} 天`, `In ${days}d`),
    toneClass: 'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/50 dark:text-blue-300 dark:border-blue-800',
  }
}

const watchedEntityIds = computed(
  () => new Set(props.watchlist.map((w) => w.entity_id).filter(Boolean) as string[]),
)

const allUniqueEvents = computed(() => {
  const byId = new Map<string, CatalystEvent>()
  for (const ev of [...props.customEvents, ...props.events]) {
    if (!byId.has(ev.calendar_id)) {
      byId.set(ev.calendar_id, ev)
    }
  }
  return Array.from(byId.values())
})

const searchActive = computed(() => Boolean((props.searchQuery || '').trim()))

const searchMatchedAll = computed(() => {
  const q = (props.searchQuery || '').trim()
  if (!q) return allUniqueEvents.value
  return allUniqueEvents.value.filter((ev) => {
    const hay = `${ev.title} ${ev.watch_variable} ${ev.original_time_note || ''} ${ev.pre_expectation || ''} ${ev.actual_result || ''} ${ev.post_deviation || ''} ${ev.source_name} ${(ev.entity_ids || []).join(' ')}`
    return matchesSmartQuery(hay, q)
  })
})

const EVENT_TYPE_TABS = computed(() => {
  const base = searchMatchedAll.value.filter((ev) => showPastEvents.value || searchActive.value || !isEventPast(ev))
  const countOf = (et: string) => (et === 'all' ? base.length : base.filter((ev) => (ev.event_type || 'politics_macro') === et).length)
  const list = [
    { id: 'all', label: t('全部分类', 'All Types'), count: countOf('all') },
    { id: 'politics_macro', label: t('国家大会与政经', 'Politics & Macro'), count: countOf('politics_macro') },
    { id: 'expo_summit', label: t('大型展会与峰会', 'Expos & Summits'), count: countOf('expo_summit') },
    { id: 'tech_launch', label: t('企业发布会', 'Tech Launches'), count: countOf('tech_launch') },
    { id: 'central_bank', label: t('央行与宏观', 'Central Banks'), count: countOf('central_bank') },
    { id: 'earnings_capital', label: t('财报与资本', 'Earnings & Capital'), count: countOf('earnings_capital') },
  ]
  return list
})

const REGION_TABS = computed(() => {
  const base = searchMatchedAll.value.filter((ev) => {
    if (!showPastEvents.value && !searchActive.value && isEventPast(ev)) return false
    if (eventTypeFilter.value !== 'all' && (ev.event_type || 'politics_macro') !== eventTypeFilter.value) return false
    return true
  })
  const countOf = (reg: string) => (reg === 'all' ? base.length : base.filter((ev) => (ev.region || 'global') === reg).length)
  return [
    { id: 'all', label: t('全部地区', 'All Regions'), count: countOf('all') },
    { id: 'china', label: t('中国', 'China'), count: countOf('china') },
    { id: 'us', label: t('美国', 'US'), count: countOf('us') },
    { id: 'europe_apac', label: t('欧洲/亚太', 'Europe/APAC'), count: countOf('europe_apac') },
    { id: 'global', label: t('全球', 'Global'), count: countOf('global') },
  ].filter((tab) => tab.id === 'all' || tab.count > 0 || regionFilter.value === tab.id)
})

const filteredAll = computed(() => {
  return searchMatchedAll.value.filter((ev) => {
    if (eventTypeFilter.value !== 'all' && (ev.event_type || 'politics_macro') !== eventTypeFilter.value) {
      return false
    }
    if (regionFilter.value !== 'all' && (ev.region || 'global') !== regionFilter.value) {
      return false
    }
    if (certaintyFilter.value === 'confirmed_official' && (ev.certainty !== 'confirmed_official' || isClockTbd(ev))) {
      return false
    }
    if (certaintyFilter.value === 'tbd' && ev.certainty === 'confirmed_official' && !isClockTbd(ev)) {
      return false
    }
    if (onlyWatched.value) {
      const hitEnt = ev.entity_ids?.some((id) => watchedEntityIds.value.has(id))
      const hitKw = props.watchlist.some((w) =>
        w.keywords.some((kw) => ev.title.toLowerCase().includes(kw.toLowerCase())),
      )
      if (!hitEnt && !hitKw) return false
    }
    if (selectedDayFilter.value) {
      const evDay = ev.scheduled_at ? formatShanghaiDateOnly(ev.scheduled_at) : ''
      if (evDay !== selectedDayFilter.value) return false
    }
    if (quickJumpKey.value) {
      const spec = activeQuickJumpPills.value.find((p) => p.id === quickJumpKey.value)
      if (spec) {
        // Match STRICTLY against title / title_en / city — never original_time_note ("北京时间")
        const txt = `${ev.title} ${ev.title_en || ''} ${ev.city || ''}`
        if (!spec.re.test(txt)) return false
      }
    }
    return true
  })
})

const timeline7Days = computed(() => {
  const countsByDay = new Map<string, number>()
  for (const ev of searchMatchedAll.value) {
    if (!ev.scheduled_at || isEventPast(ev)) continue
    const d = formatShanghaiDateOnly(ev.scheduled_at)
    countsByDay.set(d, (countsByDay.get(d) || 0) + 1)
  }
  const wdNames = [t('周日', 'Sun'), t('周一', 'Mon'), t('周二', 'Tue'), t('周三', 'Wed'), t('周四', 'Thu'), t('周五', 'Fri'), t('周六', 'Sat')]
  const days = []
  for (let i = 0; i < 7; i++) {
    const ms = effectiveNowMs.value + i * 86_400_000
    const ymd = formatShanghaiDateOnly(new Date(ms).toISOString())
    const wd = new Date(ms + 8 * 3_600_000).getUTCDay()
    days.push({
      ymd,
      shortDate: ymd.slice(5).replace('-', '/'),
      label: i === 0 ? t('今天', 'Today') : i === 1 ? t('明天', 'Tmrw') : wdNames[wd],
      count: countsByDay.get(ymd) || 0,
    })
  }
  return days
})

function toggleDayFilter(ymd: string) {
  selectedDayFilter.value = selectedDayFilter.value === ymd ? null : ymd
  if (selectedDayFilter.value) {
    openBuckets.value = { imminent: true, week: true, month: true, long_term: true }
  }
}

function isCardDetailExpanded(calendarId: string): boolean {
  return allDetailsExpanded.value || expandedDetailIds.value.has(calendarId) || editingId.value === calendarId
}

function toggleCardDetail(calendarId: string) {
  const next = new Set(expandedDetailIds.value)
  if (next.has(calendarId)) next.delete(calendarId)
  else next.add(calendarId)
  expandedDetailIds.value = next
}

function toggleAllCardDetails() {
  allDetailsExpanded.value = !allDetailsExpanded.value
  if (!allDetailsExpanded.value) {
    expandedDetailIds.value = new Set()
  }
}

function dateBlockParts(ev: CatalystEvent): { month: string; day: string; weekday: string } {
  if (!ev.scheduled_at) return { month: t('排期', 'Plan'), day: 'TBD', weekday: '' }
  const ymd = formatShanghaiDateOnly(ev.scheduled_at)
  const [, mStr, dStr] = ymd.split('-')
  const ms = Date.parse(`${ymd}T12:00:00+08:00`)
  const wdNames = [t('周日', 'Sun'), t('周一', 'Mon'), t('周二', 'Tue'), t('周三', 'Wed'), t('周四', 'Thu'), t('周五', 'Fri'), t('周六', 'Sat')]
  const wd = Number.isFinite(ms) ? wdNames[new Date(ms + 8 * 3_600_000).getUTCDay()] : ''
  return {
    month: t(`${Number(mStr)}月`, `M${Number(mStr)}`),
    day: dStr || '--',
    weekday: wd,
  }
}

const upcomingEvents = computed(() =>
  filteredAll.value
    .filter((ev) => !isEventPast(ev))
    .sort((a, b) => (a.scheduled_at || '9999-12-31').localeCompare(b.scheduled_at || '9999-12-31')),
)

const pastEvents = computed(() =>
  filteredAll.value
    .filter((ev) => isEventPast(ev))
    .sort((a, b) => (b.scheduled_at || '').localeCompare(a.scheduled_at || '')),
)

const mergedEvents = computed(() =>
  showPastEvents.value || searchActive.value
    ? [...upcomingEvents.value, ...pastEvents.value]
    : upcomingEvents.value,
)

type CalendarBucketId = 'imminent' | 'week' | 'month' | 'long_term'
const openBuckets = ref<Record<CalendarBucketId, boolean>>({
  imminent: true,
  week: true,
  month: false,
  long_term: false,
})

const shouldAutoExpandAll = computed(
  () =>
    searchActive.value ||
    eventTypeFilter.value === 'expo_summit' ||
    regionFilter.value === 'china' ||
    Boolean(quickJumpKey.value) ||
    Boolean(selectedDayFilter.value),
)

function toggleQuickJump(id: string) {
  quickJumpKey.value = quickJumpKey.value === id ? '' : id
  if (quickJumpKey.value) {
    openBuckets.value = { imminent: true, week: true, month: true, long_term: true }
    nextTick(() => {
      const el = document.querySelector('[data-testid="calendar-event-row"]')
      if (el && typeof el.scrollIntoView === 'function') {
        el.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
      }
    })
  }
}

function getCardLocationLabel(ev: CatalystEvent): string {
  const loc = String(ev.location_display || '').trim()
  if (loc) return loc
  const c = String(ev.country || '').trim()
  const city = String(ev.city || '').trim()
  if (c && city) return `${c}·${city}`
  if (city) return city
  if (c) return c
  if (ev.region === 'china') return '中国'
  if (ev.region === 'us') return '美国'
  return ''
}

function computeDayDelta(ev: CatalystEvent): number | null {
  if (ev.scheduled_at) {
    const todayStr = formatShanghaiDateOnly(new Date(effectiveNowMs.value).toISOString())
    const evStr = formatShanghaiDateOnly(ev.scheduled_at)
    const tMs = Date.parse(`${todayStr}T00:00:00Z`)
    const eMs = Date.parse(`${evStr}T00:00:00Z`)
    if (Number.isFinite(tMs) && Number.isFinite(eMs)) {
      return Math.round((eMs - tMs) / 86_400_000)
    }
  }
  return typeof ev.countdown_days === 'number' ? ev.countdown_days : null
}

function classifyBucket(ev: CatalystEvent): CalendarBucketId {
  const d = computeDayDelta(ev)
  if (d !== null) {
    if (d <= 2) return 'imminent'
    if (d <= 7) return 'week'
    if (d <= 30) return 'month'
    return 'long_term'
  }
  return ev.is_breaking_schedule ? 'imminent' : 'long_term'
}

function shortHighlightName(title: string): string {
  const clean = title.replace(/（[^）]*）|\([^)]*\)/g, '').trim()
  return clean.length > 14 ? `${clean.slice(0, 13)}…` : clean
}

const groupedUpcomingBuckets = computed(() => {
  const buckets: Record<CalendarBucketId, CatalystEvent[]> = {
    imminent: [],
    week: [],
    month: [],
    long_term: [],
  }
  for (const ev of upcomingEvents.value) {
    buckets[classifyBucket(ev)].push(ev)
  }
  // Within imminent bucket, prioritize breaking schedules first, then nearest time
  buckets.imminent.sort((a, b) => {
    const ba = a.is_breaking_schedule ? 0 : 1
    const bb = b.is_breaking_schedule ? 0 : 1
    if (ba !== bb) return ba - bb
    return (a.scheduled_at || '9999-12-31').localeCompare(b.scheduled_at || '9999-12-31')
  })

  const specs: { id: CalendarBucketId; title: string; titleEn: string; accent: string }[] = [
    {
      id: 'imminent',
      title: '突发排期与 48 小时临近（今天 / 明天）',
      titleEn: 'Breaking & Next 48 Hours',
      accent: 'border-rose-200/80 dark:border-rose-900/60 bg-rose-50/40 dark:bg-rose-950/20',
    },
    {
      id: 'week',
      title: '本周内（3 ~ 7 天）',
      titleEn: 'This Week (3–7d)',
      accent: 'border-amber-200/80 dark:border-amber-900/60 bg-amber-50/35 dark:bg-amber-950/20',
    },
    {
      id: 'month',
      title: '本月后续（8 ~ 30 天）',
      titleEn: 'Later This Month (8–30d)',
      accent: 'border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-800/40',
    },
    {
      id: 'long_term',
      title: '远期与年度大事件（> 30 天 / 待定）',
      titleEn: 'Long-Term & Annual (>30d / TBD)',
      accent: 'border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-800/40',
    },
  ]

  return specs
    .map((sp) => {
      const list = buckets[sp.id]
      const previews = list.slice(0, 2).map((e) => shortHighlightName(pickBiText(e.title, e.title_en))).join('、')
      return {
        ...sp,
        events: list,
        previewHint: previews,
        isOpen: shouldAutoExpandAll.value ? list.length > 0 : openBuckets.value[sp.id],
      }
    })
    .filter((b) => b.events.length > 0)
})

const allBucketsExpanded = computed(() =>
  groupedUpcomingBuckets.value.length > 0 && groupedUpcomingBuckets.value.every((b) => b.isOpen),
)

function toggleBucket(id: CalendarBucketId) {
  openBuckets.value = { ...openBuckets.value, [id]: !openBuckets.value[id] }
}

function toggleExpandAllBuckets() {
  const expand = !allBucketsExpanded.value
  openBuckets.value = {
    imminent: true,
    week: expand,
    month: expand,
    long_term: expand,
  }
}

const breakingCount = computed(() => upcomingEvents.value.filter((e) => e.is_breaking_schedule).length)

function startCreateCustom() {
  editingCustomId.value = null
  cTitle.value = ''
  cDate.value = '2026-11-25T20:00'
  cVar.value = ''
  cExpect.value = ''
  showCustomForm.value = !showCustomForm.value
}

function startEditCustom(ev: CatalystEvent) {
  editingCustomId.value = ev.calendar_id
  cTitle.value = ev.title
  cDate.value = ev.scheduled_at ? ev.scheduled_at.slice(0, 16) : ''
  cVar.value = ev.watch_variable || ''
  cExpect.value = ev.pre_expectation || ''
  showCustomForm.value = true
}

function submitCustom() {
  if (!cTitle.value.trim()) return
  const iso = cDate.value ? `${cDate.value}:00+08:00` : null
  const basePayload: CatalystEvent = {
    calendar_id: editingCustomId.value || `cal_custom_${Date.now().toString(36)}`,
    title: cTitle.value.trim(),
    scheduled_at: iso,
    original_time_note: iso ? `${cDate.value} Asia/Shanghai` : 'TBD',
    timezone: 'Asia/Shanghai',
    certainty: iso ? 'confirmed_official' : 'tbd',
    certainty_label: iso ? '自建已排期' : '待定 TBD',
    category: 'custom',
    entity_ids: [],
    watch_variable: cVar.value.trim() || t('自定义关注指标', 'Custom watch variable'),
    pre_expectation: cExpect.value.trim() || null,
    actual_result: null,
    source_name: t('本地自定义催化', 'Custom Catalyst'),
    source_url: null,
    is_custom: true,
  }
  if (editingCustomId.value) {
    const existing = props.customEvents.find((c) => c.calendar_id === editingCustomId.value)
    emit('update-custom-catalyst', {
      ...existing,
      ...basePayload,
      actual_result: existing?.actual_result ?? null,
      post_deviation: existing?.post_deviation ?? null,
    })
  } else {
    emit('add-custom-catalyst', basePayload)
  }
  editingCustomId.value = null
  cTitle.value = ''
  cVar.value = ''
  cExpect.value = ''
  showCustomForm.value = false
}

function startEditActual(ev: CatalystEvent) {
  editingId.value = ev.calendar_id
  draftActual.value = ev.actual_result || ''
  draftDeviation.value = ev.post_deviation || ''
}

function submitActual(id: string) {
  emit('save-catalyst-actual', {
    calendarId: id,
    actualResult: draftActual.value.trim(),
    deviation: draftDeviation.value.trim(),
  })
  editingId.value = null
}

function resetLocalFilters() {
  certaintyFilter.value = 'all'
  eventTypeFilter.value = 'all'
  regionFilter.value = 'all'
  quickJumpKey.value = ''
  onlyWatched.value = false
  selectedDayFilter.value = null
  showPastEvents.value = true
}

function resetAll() {
  resetLocalFilters()
  emit('clear-search')
}
</script>

<template>
  <section class="space-y-3" :aria-label="t('催化事件日历', 'Catalyst Calendar')">
    <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-3 sm:p-4 space-y-2.5 shadow-xs">
      <!-- Slim Top Header Bar -->
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div class="flex flex-wrap items-center gap-2 min-w-0">
          <h2 class="text-[15px] sm:text-lg font-bold text-zinc-900 dark:text-white flex items-center gap-1.5">
            <Calendar class="w-4 h-4 text-[#007AFF] shrink-0" :stroke-width="1.5" />
            <span>{{ t(`催化日历 (${mergedEvents.length})`, `Calendar (${mergedEvents.length})`) }}</span>
          </h2>
          <span
            v-if="breakingCount > 0"
            class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300"
          >
            <span class="jx-sonar-dot jx-sonar-amber" aria-hidden="true" />
            <Zap class="w-3 h-3" />
            <span>{{ t(`${breakingCount} 突发排期`, `${breakingCount} Breaking`) }}</span>
          </span>
        </div>

        <div class="flex flex-wrap items-center gap-1.5">
          <button
            v-if="groupedUpcomingBuckets.length > 1"
            type="button"
            @click="toggleExpandAllBuckets"
            class="inline-flex items-center gap-1 px-2.5 min-h-[32px] rounded-xl sm:rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-[11px] font-medium text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 whitespace-nowrap"
          >
            <span>{{ allBucketsExpanded ? t('一键收起', 'Collapse All') : t('全部展开', 'Expand All') }}</span>
          </button>
          <button
            type="button"
            @click="toggleAllCardDetails"
            class="inline-flex items-center gap-1 px-2.5 min-h-[32px] rounded-xl sm:rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-[11px] font-medium text-slate-600 dark:text-slate-300 hover:bg-slate-50 whitespace-nowrap"
          >
            <span>{{ allDetailsExpanded ? t('收起详情', 'Hide Details') : t('全部展开详情', 'All Details') }}</span>
          </button>
          <button
            type="button"
            @click="startCreateCustom"
            class="inline-flex items-center gap-1 px-2.5 min-h-[32px] rounded-xl sm:rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-[11px] font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700 whitespace-nowrap"
          >
            <Plus class="w-3.5 h-3.5" />
            <span>{{ showCustomForm && editingCustomId ? t('取消编辑', 'Cancel') : t('新增节点', 'Add') }}</span>
          </button>
        </div>
      </div>

      <div
        v-if="subActionMsg"
        class="rounded-lg bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 px-3 py-1.5 text-xs text-emerald-800 dark:text-emerald-200 flex items-center gap-1.5"
      >
        <Check class="w-3.5 h-3.5 shrink-0" />
        <span>{{ subActionMsg }}</span>
      </div>

      <!-- Visual 7-Day Catalyst Density Timeline Strip -->
      <div class="grid grid-cols-7 gap-1 pt-0.5" data-testid="calendar-timeline-strip">
        <button
          v-for="day in timeline7Days"
          :key="day.ymd"
          type="button"
          @click="toggleDayFilter(day.ymd)"
          class="flex flex-col items-center justify-center py-1.5 px-1 rounded-xl border text-center transition-colors min-w-0"
          :class="
            selectedDayFilter === day.ymd
              ? 'bg-[#007AFF] text-white border-[#007AFF] shadow-xs'
              : day.count > 0
                ? 'bg-slate-50 dark:bg-slate-800/80 border-slate-200 dark:border-slate-700 text-slate-800 dark:text-slate-100 hover:border-[#007AFF]/50'
                : 'bg-white/60 dark:bg-slate-900/40 border-slate-100 dark:border-slate-800 text-slate-400'
          "
        >
          <span class="text-[10px] font-medium truncate">{{ day.label }}</span>
          <span class="text-[11px] font-mono font-bold tabular-nums leading-tight">{{ day.shortDate }}</span>
          <span
            class="mt-0.5 inline-flex items-center justify-center min-w-[16px] h-3.5 px-1 rounded-full text-[9.5px] font-bold tabular-nums"
            :class="
              selectedDayFilter === day.ymd
                ? 'bg-white/25 text-white'
                : day.count > 0
                  ? 'bg-amber-500/15 text-amber-700 dark:text-amber-300'
                  : 'text-slate-300 dark:text-slate-600'
            "
          >
            {{ day.count }}
          </span>
        </button>
      </div>

      <!-- Custom Catalyst Form -->
      <form
        v-if="showCustomForm"
        @submit.prevent="submitCustom"
        class="pt-3 border-t border-slate-200 dark:border-slate-800 grid grid-cols-1 sm:grid-cols-12 gap-2 text-xs"
      >
        <input
          v-model="cTitle"
          type="text"
          :placeholder="t('事件名称，如 英伟达 FY27Q3 财报电话会', 'Event title, e.g. NVIDIA Earnings Call')"
          class="sm:col-span-4 h-10 sm:h-9 px-3 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-white"
        />
        <input
          v-model="cDate"
          type="datetime-local"
          class="sm:col-span-3 h-10 sm:h-9 px-2.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-white"
        />
        <input
          v-model="cVar"
          type="text"
          :placeholder="t('核心观察变量 (如数据中心毛利率)', 'Key variable (e.g. gross margin)')"
          class="sm:col-span-3 h-10 sm:h-9 px-2.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-white"
        />
        <button
          type="submit"
          class="sm:col-span-2 h-10 sm:h-9 rounded-lg bg-emerald-600 text-white font-semibold hover:bg-emerald-700"
        >
          {{ editingCustomId ? t('保存修改', 'Save Changes') : t('保存节点', 'Save Event') }}
        </button>
        <input
          v-model="cExpect"
          type="text"
          :placeholder="t('事前基线预期（可选：用于事后对照偏差）', 'Pre-event expectation (optional)')"
          class="sm:col-span-12 h-10 sm:h-9 px-3 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-white"
        />
      </form>

      <!-- Mobile Scrollable Pill Bars + Compact Action Controls (< sm) -->
      <div class="sm:hidden space-y-2 pt-1.5 border-t border-slate-100 dark:border-slate-800 text-[11px]">
        <div class="flex items-center gap-1.5 overflow-x-auto no-scrollbar scroll-fade-x">
          <button
            v-for="tab in EVENT_TYPE_TABS"
            :key="`m-type-${tab.id}`"
            type="button"
            @click="(e) => { eventTypeFilter = tab.id; centerPillIntoView(e) }"
            class="mobile-pressable min-h-[30px] px-2.5 rounded-lg font-medium whitespace-nowrap shrink-0 transition-colors"
            :class="eventTypeFilter === tab.id ? 'bg-[#007AFF] text-white font-semibold' : 'bg-[#F5F5F7] dark:bg-slate-800 text-slate-600 dark:text-slate-300'"
          >
            {{ tab.label }} <span class="opacity-75 tabular-nums">{{ tab.count }}</span>
          </button>
        </div>
        <div class="flex items-center gap-1.5 overflow-x-auto no-scrollbar scroll-fade-x">
          <button
            v-for="reg in REGION_TABS"
            :key="`m-reg-${reg.id}`"
            type="button"
            @click="(e) => { regionFilter = reg.id; centerPillIntoView(e) }"
            class="mobile-pressable inline-flex items-center gap-1 min-h-[30px] px-2.5 rounded-lg border font-medium whitespace-nowrap shrink-0 transition-colors"
            :class="regionFilter === reg.id ? 'bg-slate-900 text-white border-slate-900 dark:bg-white dark:text-slate-900 dark:border-white font-semibold' : 'bg-white text-slate-600 border-slate-200 dark:bg-slate-900 dark:text-slate-300 dark:border-slate-700'"
          >
            <MapPin v-if="reg.id !== 'all'" class="w-3 h-3 shrink-0" :stroke-width="1.75" />
            <span>{{ reg.label }}</span>
            <span class="opacity-70 tabular-nums">{{ reg.count }}</span>
          </button>
        </div>
        <div class="flex flex-wrap items-center gap-1.5">
          <select
            v-model="certaintyFilter"
            :aria-label="t('确定性', 'Certainty')"
            class="h-8 px-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-[#F5F5F7] dark:bg-slate-800 text-slate-800 dark:text-slate-100 font-medium shrink-0"
          >
            <option value="all">{{ t('全部时效', 'All Timing') }}</option>
            <option value="confirmed_official">{{ t('已确认时间', 'Confirmed') }}</option>
            <option value="tbd">{{ t('时间待定', 'TBD') }}</option>
          </select>
          <button
            type="button"
            @click="onlyWatched = !onlyWatched"
            class="mobile-pressable h-8 px-2.5 rounded-lg border font-medium whitespace-nowrap shrink-0"
            :class="onlyWatched ? 'bg-[#007AFF] text-white border-[#007AFF]' : 'bg-white text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700'"
          >
            {{ t('仅看关注', 'Watchlist') }}
          </button>
          <button
            v-if="pastEvents.length > 0"
            type="button"
            @click="showPastEvents = !showPastEvents"
            class="mobile-pressable h-8 px-2.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 whitespace-nowrap shrink-0"
          >
            {{ showPastEvents ? t('隐藏已结束', 'Hide Past') : t(`已结束(${pastEvents.length})`, `Past(${pastEvents.length})`) }}
          </button>
        </div>
      </div>

      <!-- Desktop Dual-Dimension Category & Region Filters (>= sm) -->
      <div class="hidden sm:block space-y-2 pt-2 border-t border-slate-100 dark:border-slate-800 text-xs">
        <div class="flex flex-wrap items-center gap-1.5">
          <button
            v-for="tab in EVENT_TYPE_TABS"
            :key="tab.id"
            type="button"
            @click="eventTypeFilter = tab.id"
            class="min-h-[28px] px-2.5 rounded-lg font-medium whitespace-nowrap shrink-0 transition-colors"
            :class="eventTypeFilter === tab.id ? 'bg-[#007AFF] text-white font-semibold' : 'bg-[#F5F5F7] dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200/70'"
          >
            {{ tab.label }} <span class="opacity-75 tabular-nums">{{ tab.count }}</span>
          </button>
          <span class="mx-1 text-slate-300 dark:text-slate-700">|</span>
          <button
            v-for="reg in REGION_TABS"
            :key="reg.id"
            type="button"
            @click="regionFilter = reg.id"
            class="inline-flex items-center gap-1 min-h-[26px] px-2.5 rounded-lg border font-medium whitespace-nowrap shrink-0 transition-colors"
            :class="regionFilter === reg.id ? 'bg-slate-900 text-white border-slate-900 dark:bg-white dark:text-slate-900 dark:border-white font-semibold' : 'bg-white text-slate-600 border-slate-200 dark:bg-slate-900 dark:text-slate-300 dark:border-slate-700'"
          >
            <MapPin v-if="reg.id !== 'all'" class="w-3 h-3 shrink-0" :stroke-width="1.75" />
            <span>{{ reg.label }}</span>
            <span class="opacity-70 tabular-nums">{{ reg.count }}</span>
          </button>
        </div>

        <div class="flex flex-wrap items-center justify-between gap-2 pt-1.5 border-t border-slate-100 dark:border-slate-800 text-xs">
          <div class="flex flex-wrap items-center gap-1.5">
            <button
              type="button"
              @click="certaintyFilter = 'all'"
              class="min-h-[28px] px-2.5 rounded-lg border font-medium whitespace-nowrap"
              :class="certaintyFilter === 'all' ? 'bg-slate-900 text-white border-slate-900 dark:bg-blue-600 dark:border-blue-600' : 'bg-white text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700'"
            >
              {{ t(`全部 (${searchMatchedAll.length})`, `All (${searchMatchedAll.length})`) }}
            </button>
            <button
              type="button"
              @click="certaintyFilter = 'confirmed_official'"
              class="min-h-[28px] px-2.5 rounded-lg border font-medium whitespace-nowrap"
              :class="certaintyFilter === 'confirmed_official' ? 'bg-emerald-600 text-white border-emerald-600' : 'bg-white text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700'"
            >
              {{ t('已确认排期时间', 'Confirmed Time') }}
            </button>
            <button
              type="button"
              @click="certaintyFilter = 'tbd'"
              class="min-h-[28px] px-2.5 rounded-lg border font-medium whitespace-nowrap"
              :class="certaintyFilter === 'tbd' ? 'bg-amber-600 text-white border-amber-600' : 'bg-white text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700'"
            >
              {{ t('时间待定 (TBD)', 'Time TBD') }}
            </button>
          </div>

          <div class="flex flex-wrap items-center gap-2.5">
            <button
              v-if="pastEvents.length > 0"
              type="button"
              @click="showPastEvents = !showPastEvents"
              class="min-h-[28px] px-2.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-100 whitespace-nowrap"
            >
              {{ showPastEvents ? t('隐藏已结束日程', 'Hide Past Events') : t(`显示已结束 (${pastEvents.length})`, `Show Past (${pastEvents.length})`) }}
            </button>
            <label class="inline-flex items-center gap-1.5 cursor-pointer text-slate-600 dark:text-slate-300">
              <input v-model="onlyWatched" type="checkbox" class="rounded border-slate-300 text-blue-600" />
              <span>{{ t('仅看命中关注词', 'Watchlist Hits Only') }}</span>
            </label>
          </div>
        </div>
      </div>

      <!-- Region-Linked Quick-Jump Pills (visible across Desktop & Mobile) -->
      <div class="flex items-center gap-1.5 overflow-x-auto sm:flex-wrap no-scrollbar scroll-fade-x pt-1 text-[11px]" data-testid="calendar-quick-jump-strip">
        <span class="text-slate-500 dark:text-slate-400 font-medium shrink-0">{{ t('核心大展与大事直达：', 'Quick Jump:') }}</span>
        <button
          v-for="pill in activeQuickJumpPills"
          :key="pill.id"
          type="button"
          @click="(e) => { toggleQuickJump(pill.id); centerPillIntoView(e) }"
          class="mobile-pressable inline-flex items-center gap-1 min-h-[26px] px-2.5 rounded-full border font-medium transition-colors whitespace-nowrap shrink-0"
          :class="quickJumpKey === pill.id ? 'bg-indigo-600 text-white border-indigo-600 font-semibold' : 'bg-indigo-50/60 dark:bg-indigo-950/30 text-indigo-700 dark:text-indigo-300 border-indigo-200/80 dark:border-indigo-800/70 hover:bg-indigo-100'"
          data-testid="calendar-quick-jump-pill"
        >
          <MapPin class="w-3 h-3 shrink-0" :stroke-width="1.75" />
          <span>{{ t(pill.zh, pill.en) }}</span>
        </button>
      </div>
    </div>

    <EmptySearchState
      v-if="mergedEvents.length === 0"
      :query="props.searchQuery"
      :has-extra-filters="certaintyFilter !== 'all' || eventTypeFilter !== 'all' || regionFilter !== 'all' || Boolean(quickJumpKey) || onlyWatched || (!showPastEvents && pastEvents.length > 0)"
      @clear-query="emit('clear-search')"
      @clear-filters-only="resetLocalFilters"
      @reset="resetAll"
    />

    <!-- Time-Window Collapsible Groups -->
    <div v-else class="space-y-4">
      <div
        v-for="grp in groupedUpcomingBuckets"
        :key="grp.id"
        class="space-y-2.5"
        :data-calendar-bucket="grp.id"
      >
        <button
          type="button"
          @click="toggleBucket(grp.id)"
          class="w-full rounded-xl border px-3.5 py-2.5 flex items-center justify-between gap-2 text-left transition-colors hover:opacity-95"
          :class="grp.accent"
          :aria-expanded="grp.isOpen"
        >
          <div class="min-w-0 flex flex-wrap items-center gap-2">
            <span class="text-xs sm:text-sm font-bold text-slate-900 dark:text-white">
              {{ pickBiText(grp.title, grp.titleEn) }}
            </span>
            <span class="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-white/80 dark:bg-slate-900/70 text-slate-700 dark:text-slate-200 tabular-nums">
              {{ t(`共 ${grp.events.length} 项`, `${grp.events.length} items`) }}
            </span>
            <span
              v-if="!grp.isOpen && grp.previewHint"
              class="text-[11px] text-slate-500 dark:text-slate-400 truncate max-w-[260px] sm:max-w-md"
            >
              {{ t(`含 ${grp.previewHint}，点击展开`, `Incl. ${grp.previewHint} · Tap to expand`) }}
            </span>
          </div>
          <component :is="grp.isOpen ? ChevronDown : ChevronRight" class="w-4 h-4 text-slate-500 shrink-0" />
        </button>

        <div v-if="grp.isOpen" class="ios-card overflow-hidden divide-y divide-slate-100 dark:divide-slate-800/80">
          <article
            v-for="ev in grp.events"
            :key="ev.calendar_id"
            data-testid="calendar-event-row"
            class="transition-colors hover:bg-slate-50/75 dark:hover:bg-slate-800/35"
          >
            <!-- Mobile Compact 2-Line Summary (< sm: Full-Width Unclipped Title) -->
            <div
              role="button"
              tabindex="0"
              @click="toggleCardDetail(ev.calendar_id)"
              @keydown.enter.prevent="toggleCardDetail(ev.calendar_id)"
              class="mobile-pressable flex sm:hidden flex-col gap-1.5 px-3 py-2.5 cursor-pointer select-none"
            >
              <div class="flex items-start justify-between gap-1.5 min-w-0">
                <div class="flex flex-wrap items-center gap-1.5 min-w-0 flex-1">
                  <span
                    class="shrink-0 inline-flex items-center justify-center px-2 h-[22px] rounded-md font-mono text-[10.5px] font-bold tabular-nums border whitespace-nowrap"
                    :class="ev.is_breaking_schedule
                      ? 'bg-amber-500 text-white border-amber-500'
                      : 'bg-[#007AFF]/10 text-[#007AFF] dark:bg-[#0A84FF]/15 dark:text-[#66B2FF] border-[#007AFF]/20'"
                  >
                    {{ ev.scheduled_at ? formatShanghaiDateOnly(ev.scheduled_at).slice(5).replace('-', '/') : '--/--' }} {{ dateBlockParts(ev).weekday }}
                  </span>
                  <span
                    v-if="getCardLocationLabel(ev)"
                    class="inline-flex items-center gap-0.5 px-1.5 h-[22px] rounded-md bg-indigo-50 text-indigo-700 border border-indigo-200/80 dark:bg-indigo-950/50 dark:text-indigo-300 dark:border-indigo-800 text-[10px] font-semibold shrink-0 whitespace-nowrap"
                    data-testid="calendar-card-location"
                  >
                    <MapPin class="w-2.5 h-2.5 shrink-0" :stroke-width="1.75" />
                    <span>{{ getCardLocationLabel(ev) }}</span>
                  </span>
                  <span
                    v-if="ev.is_breaking_schedule"
                    class="inline-flex items-center gap-1 px-1.5 h-[22px] rounded-md text-[10px] font-bold bg-amber-100 text-amber-900 border border-amber-300 dark:bg-amber-950/70 dark:text-amber-200 dark:border-amber-700 shrink-0 whitespace-nowrap"
                  >
                    <span class="jx-sonar-dot jx-sonar-amber" aria-hidden="true" />
                    <Zap class="w-2.5 h-2.5" />
                    <span>{{ t('突发', 'Breaking') }}</span>
                  </span>
                  <span
                    v-else-if="ev.event_type_label"
                    class="inline-flex items-center px-1.5 h-[22px] rounded-md bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300 text-[10px] font-medium shrink-0 whitespace-nowrap"
                  >
                    {{ stripEmoji(ev.event_type_label) }}
                  </span>
                </div>

                <div class="flex items-center gap-1 shrink-0">
                  <span
                    v-if="formatCountdown(ev)"
                    class="px-1.5 h-[22px] inline-flex items-center rounded-full text-[10px] font-semibold border tabular-nums whitespace-nowrap"
                    :class="formatCountdown(ev)!.toneClass"
                  >
                    {{ formatCountdown(ev)!.label }}
                  </span>
                  <ChevronDown
                    class="w-4 h-4 text-slate-400 transition-transform shrink-0"
                    :class="{ 'rotate-180 text-[#007AFF]': isCardDetailExpanded(ev.calendar_id) }"
                  />
                </div>
              </div>

              <h3 class="text-[13.5px] font-semibold text-slate-900 dark:text-white leading-snug line-clamp-2 w-full">
                {{ pickBiText(ev.title, ev.title_en) }}
              </h3>
            </div>

            <!-- Desktop Compact Single-Row Summary (42-48px high density) -->
            <div
              role="button"
              tabindex="0"
              @click="toggleCardDetail(ev.calendar_id)"
              @keydown.enter.prevent="toggleCardDetail(ev.calendar_id)"
              class="hidden sm:flex min-h-[44px] px-3 py-2 items-center justify-between gap-2.5 cursor-pointer select-none"
            >
              <div class="min-w-0 flex items-center gap-2 flex-1">
                <span
                  class="shrink-0 inline-flex items-center justify-center w-[52px] h-[26px] rounded-lg font-mono text-[11px] font-bold tabular-nums border"
                  :class="ev.is_breaking_schedule
                    ? 'bg-amber-500 text-white border-amber-500'
                    : 'bg-[#007AFF]/10 text-[#007AFF] dark:bg-[#0A84FF]/15 dark:text-[#66B2FF] border-[#007AFF]/20'"
                >
                  {{ ev.scheduled_at ? formatShanghaiDateOnly(ev.scheduled_at).slice(5).replace('-', '/') : '--/--' }}
                </span>

                <span
                  v-if="getCardLocationLabel(ev)"
                  class="hidden sm:inline-flex items-center gap-1 px-2 h-[22px] rounded-md bg-indigo-50 text-indigo-700 border border-indigo-200/80 dark:bg-indigo-950/50 dark:text-indigo-300 dark:border-indigo-800 text-[10.5px] font-semibold whitespace-nowrap shrink-0"
                  data-testid="calendar-card-location"
                >
                  <MapPin class="w-2.5 h-2.5 shrink-0" :stroke-width="1.75" />
                  <span>{{ getCardLocationLabel(ev) }}</span>
                </span>

                <span
                  v-if="ev.is_breaking_schedule"
                  class="inline-flex items-center gap-1 px-1.5 h-[22px] rounded-md text-[10px] font-bold bg-amber-100 text-amber-900 border border-amber-300 dark:bg-amber-950/70 dark:text-amber-200 dark:border-amber-700 shrink-0 whitespace-nowrap"
                >
                  <span class="jx-sonar-dot jx-sonar-amber" aria-hidden="true" />
                  <Zap class="w-2.5 h-2.5" />
                  <span>{{ t('突发', 'Breaking') }}</span>
                </span>
                <span
                  v-else-if="ev.event_type_label"
                  class="hidden md:inline-flex items-center px-1.5 h-[22px] rounded-md bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300 text-[10.5px] font-medium shrink-0 whitespace-nowrap"
                >
                  {{ stripEmoji(ev.event_type_label) }}
                </span>

                <h3 class="text-[13px] sm:text-[13.5px] font-semibold text-slate-900 dark:text-white truncate min-w-0">
                  {{ pickBiText(ev.title, ev.title_en) }}
                </h3>
              </div>

              <div class="flex items-center gap-2 shrink-0">
                <span
                  v-if="formatCountdown(ev)"
                  class="px-2 h-[22px] inline-flex items-center rounded-full text-[10.5px] font-semibold border tabular-nums whitespace-nowrap"
                  :class="formatCountdown(ev)!.toneClass"
                >
                  {{ formatCountdown(ev)!.label }}
                </span>
                <ChevronDown
                  class="w-4 h-4 text-slate-400 transition-transform shrink-0"
                  :class="{ 'rotate-180 text-[#007AFF]': isCardDetailExpanded(ev.calendar_id) }"
                />
              </div>
            </div>

            <!-- Collapsible Detail Drawer (Watch Variable, Location on Mobile, Baseline & Tracking) -->
            <div v-if="isCardDetailExpanded(ev.calendar_id)" class="px-3 pb-3 pt-2 border-t border-slate-100 dark:border-slate-800/80 bg-slate-50/50 dark:bg-slate-900/50 space-y-2 text-xs">
              <div class="sm:hidden text-[13px] font-bold text-slate-900 dark:text-white leading-snug">
                {{ pickBiText(ev.title, ev.title_en) }}
              </div>
              <div class="flex flex-wrap items-center gap-1.5 text-[11px]">
                <span
                  v-if="getCardLocationLabel(ev)"
                  class="sm:hidden inline-flex items-center gap-1 px-2 py-0.5 rounded bg-indigo-50 text-indigo-700 border border-indigo-200 dark:bg-indigo-950/50 dark:text-indigo-300 font-semibold whitespace-nowrap"
                  data-testid="calendar-card-location"
                >
                  <MapPin class="w-3 h-3 shrink-0" :stroke-width="1.75" />
                  <span>{{ getCardLocationLabel(ev) }}</span>
                </span>
                <span
                  class="px-2 py-0.5 rounded font-semibold border"
                  :class="isClockTbd(ev)
                    ? 'bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-950/60 dark:text-amber-200 dark:border-amber-800'
                    : 'bg-emerald-50 text-emerald-800 border-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-200 dark:border-emerald-800'"
                >
                  {{ isClockTbd(ev) ? t('日程窗口', 'Window') : ev.certainty_label }}
                </span>
                <span v-if="ev.event_type_label" class="px-2 py-0.5 rounded bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300 font-medium">
                  {{ stripEmoji(ev.event_type_label) }}
                </span>
              </div>
              <p class="text-xs text-slate-700 dark:text-slate-200 leading-relaxed">
                <strong>{{ t('观察变量：', 'Watch Variable: ') }}</strong>{{ pickBiText(ev.watch_variable, ev.watch_variable_en) }}
              </p>
              <div class="flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-500">
                <div class="flex flex-wrap items-center gap-2">
                  <span v-if="ev.original_time_note" class="inline-flex items-center gap-1">
                    <Clock class="w-3 h-3 shrink-0" :stroke-width="1.75" />
                    <span>{{ ev.original_time_note }}</span>
                  </span>
                </div>
                <div class="flex items-center gap-2">
                  <template v-if="ev.is_custom">
                    <button type="button" @click="startEditCustom(ev)" class="inline-flex items-center gap-1 px-2 py-0.5 rounded border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300">
                      <Pencil class="w-3 h-3" /><span>{{ t('编辑', 'Edit') }}</span>
                    </button>
                    <button type="button" @click="emit('delete-custom-catalyst', ev.calendar_id)" class="inline-flex items-center gap-1 px-2 py-0.5 rounded border border-red-200 dark:border-red-800 text-red-600 dark:text-red-400">
                      <Trash2 class="w-3 h-3" /><span>{{ t('删除', 'Delete') }}</span>
                    </button>
                  </template>
                  <a
                    v-if="normalizeExternalUrl(ev.source_url)"
                    :href="normalizeExternalUrl(ev.source_url)!"
                    target="_blank"
                    rel="noopener noreferrer"
                    @click.stop
                    class="text-blue-600 dark:text-blue-400 hover:underline inline-flex items-center gap-1"
                  >
                    <span>{{ ev.source_name }}</span>
                    <ExternalLink class="w-3 h-3" />
                  </a>
                  <span v-else class="text-slate-400">{{ ev.source_name }}（{{ t('暂无直链', 'No Link') }}）</span>
                </div>
              </div>

              <div class="rounded-lg bg-white dark:bg-slate-800/60 p-2.5 border border-slate-200/80 dark:border-slate-700/80 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                <div class="min-w-0">
                  <div class="font-semibold text-slate-500 mb-0.5">{{ t('事前基线预期（永久保留不覆盖）', 'Pre-Event Baseline (Preserved)') }}</div>
                  <div class="text-slate-700 dark:text-slate-200">{{ pickBiText(ev.pre_expectation, ev.pre_expectation_en) || t('无事前预测记录', 'No baseline logged') }}</div>
                </div>
                <button
                  v-if="!(ev.actual_result || ev.post_deviation || editingId === ev.calendar_id)"
                  type="button"
                  @click="startEditActual(ev)"
                  class="self-start sm:self-center shrink-0 inline-flex items-center px-2.5 min-h-[28px] rounded-lg border border-blue-200 dark:border-blue-800 bg-white dark:bg-slate-900 text-[11px] font-medium text-blue-600 dark:text-blue-400 hover:bg-blue-50 whitespace-nowrap"
                >
                  {{ t('+ 录入实际结果', '+ Log Actual') }}
                </button>
              </div>

              <div
                v-if="ev.actual_result || ev.post_deviation || editingId === ev.calendar_id"
                class="rounded-lg bg-blue-50/50 dark:bg-blue-950/20 p-2.5 border border-blue-200/70 dark:border-blue-900/70 space-y-1.5"
              >
                <div class="font-semibold text-blue-800 dark:text-blue-300">{{ t('事后实际结果与偏差', 'Post-Event Actual & Deviation') }}</div>
                <div class="text-slate-800 dark:text-slate-100">{{ ev.actual_result }}</div>
                <div v-if="ev.post_deviation" class="text-[11px] text-violet-700 dark:text-violet-300">{{ t('偏差备注：', 'Deviation: ') }}{{ ev.post_deviation }}</div>
                <div v-if="editingId === ev.calendar_id" class="space-y-2 pt-1">
                  <input v-model="draftActual" type="text" :placeholder="t('录入实际结果', 'Record actual outcome')" class="w-full h-9 px-2.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900" />
                  <input v-model="draftDeviation" type="text" :placeholder="t('与事前预期的偏差对比', 'Deviation vs expectation')" class="w-full h-9 px-2.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900" />
                  <div class="flex gap-2">
                    <button type="button" @click="submitActual(ev.calendar_id)" class="px-3.5 min-h-[30px] rounded-lg bg-blue-600 text-white font-semibold">{{ t('保存', 'Save') }}</button>
                    <button type="button" @click="editingId = null" class="px-3.5 min-h-[30px] rounded-lg border border-slate-300 dark:border-slate-600">{{ t('取消', 'Cancel') }}</button>
                  </div>
                </div>
                <div v-else class="flex flex-wrap items-center gap-2">
                  <button type="button" @click="startEditActual(ev)" class="text-[11px] font-medium text-blue-600 dark:text-blue-400 hover:underline">{{ t('更新实际结果', 'Update Actual') }}</button>
                  <button type="button" @click="emit('clear-catalyst-actual', ev.calendar_id)" class="text-[11px] text-slate-500 hover:text-red-600">{{ t('清除实录', 'Clear') }}</button>
                </div>
              </div>
            </div>
          </article>
        </div>
      </div>

      <!-- Past Events Section (visible when toggled or searching) -->
      <div v-if="(showPastEvents || searchActive) && pastEvents.length > 0" class="space-y-2.5 pt-2 border-t border-slate-200 dark:border-slate-800">
        <div class="text-xs font-semibold text-slate-500">
          {{ t(`已结束日程 (${pastEvents.length})`, `Past Events (${pastEvents.length})`) }}
        </div>
        <div class="grid grid-cols-1 xl:grid-cols-2 gap-3">
          <article
            v-for="ev in pastEvents"
            :key="ev.calendar_id"
            class="rounded-xl border border-slate-200 dark:border-slate-800 bg-white/85 dark:bg-slate-900/80 p-3.5 sm:p-4 space-y-2.5"
          >
            <div class="flex flex-wrap items-center justify-between gap-2 text-xs">
              <div class="flex flex-wrap items-center gap-1.5">
                <span class="px-2 py-0.5 rounded font-semibold border bg-slate-100 text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700">
                  {{ ev.actual_result ? t('已结束 · 已归档结果', 'Ended · Result Logged') : t('已结束 · 待录入结果', 'Ended · Record Result') }}
                </span>
                <span v-if="ev.scheduled_at" class="font-semibold text-slate-700 dark:text-slate-200 tabular-nums">
                  {{ formatShanghaiDateOnly(ev.scheduled_at) }}
                </span>
                <button
                  v-if="getReviewTarget(ev)"
                  type="button"
                  @click="openReview(ev)"
                  class="px-2 py-0.5 rounded-md bg-blue-50 text-blue-700 border border-blue-200 dark:bg-blue-950/50 dark:text-blue-300 dark:border-blue-800 font-semibold hover:underline"
                >
                  {{ t('查看复盘 →', 'View Review →') }}
                </button>
              </div>
              <a
                v-if="normalizeExternalUrl(ev.source_url)"
                :href="normalizeExternalUrl(ev.source_url)!"
                target="_blank"
                rel="noopener noreferrer"
                @click.stop
                class="text-blue-600 dark:text-blue-400 hover:underline inline-flex items-center gap-1"
              >
                <span>{{ ev.source_name }}</span>
                <ExternalLink class="w-3 h-3" />
              </a>
              <span v-else-if="ev.source_name" class="text-xs text-slate-400">{{ ev.source_name }}（{{ t('暂无直链', 'No Link') }}）</span>
            </div>
            <h3 class="text-sm font-bold text-slate-900 dark:text-white">{{ pickBiText(ev.title, ev.title_en) }}</h3>
            <p class="text-xs text-slate-600 dark:text-slate-300">
              <strong>{{ t('观察变量：', 'Watch Variable: ') }}</strong>{{ pickBiText(ev.watch_variable, ev.watch_variable_en) }}
            </p>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
              <div class="rounded-lg bg-slate-50 dark:bg-slate-800/60 p-2.5 border border-slate-200/80 dark:border-slate-700/80">
                <div class="font-semibold text-slate-500 mb-0.5">{{ t('事前基线预期', 'Pre-Event Baseline') }}</div>
                <div class="text-slate-700 dark:text-slate-200">{{ pickBiText(ev.pre_expectation, ev.pre_expectation_en) || t('无事前预测记录', 'No baseline') }}</div>
              </div>
              <div class="rounded-lg bg-blue-50/50 dark:bg-blue-950/20 p-2.5 border border-blue-200/70 dark:border-blue-900/70 space-y-1">
                <div class="font-semibold text-blue-800 dark:text-blue-300">{{ t('事后实际结果与偏差', 'Post-Event Actual') }}</div>
                <div class="text-slate-800 dark:text-slate-100">{{ ev.actual_result || t('可补录历史实际结果', 'Record actual outcome') }}</div>
                <div v-if="editingId === ev.calendar_id" class="space-y-1.5 pt-1">
                  <input v-model="draftActual" type="text" :placeholder="t('录入实际结果', 'Record actual outcome')" class="w-full h-8 px-2 rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900" />
                  <input v-model="draftDeviation" type="text" :placeholder="t('偏差对比', 'Deviation')" class="w-full h-8 px-2 rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900" />
                  <div class="flex gap-1.5">
                    <button type="button" @click="submitActual(ev.calendar_id)" class="px-2.5 py-1 rounded bg-blue-600 text-white font-semibold">{{ t('保存', 'Save') }}</button>
                    <button type="button" @click="editingId = null" class="px-2.5 py-1 rounded border border-slate-300 dark:border-slate-600">{{ t('取消', 'Cancel') }}</button>
                  </div>
                </div>
                <button v-else type="button" @click="startEditActual(ev)" class="text-[11px] font-medium text-blue-600 dark:text-blue-400 hover:underline">
                  {{ ev.actual_result ? t('更新实录', 'Update') : t('+ 录入实录', '+ Log') }}
                </button>
              </div>
            </div>
          </article>
        </div>
      </div>
    </div>
  </section>
</template>
