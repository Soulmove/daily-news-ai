<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import {
  Bookmark,
  Calendar,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  Compass,
  Filter,
  GitBranch,
  Plus,
  RotateCcw,
  Scale,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  X,
  Zap,
} from 'lucide-vue-next'
import EventCard from '../EventCard.vue'
import EmptySearchState from '../EmptySearchState.vue'
import LoadingSkeleton from '../LoadingSkeleton.vue'
import SmartTime from '../SmartTime.vue'
import TopicSpotlight from './TopicSpotlight.vue'
import { appLang, pickBiText, t } from '../../core/i18n'
import { centerPillIntoView } from '../../core/dom'
import { isEventRead } from '../../core/storage'
import { formatShanghaiDateOnly, parseTimestampMs } from '../../core/time'
import {
  WATCHLIST_PRESETS,
  type WatchlistPresetTemplate,
} from '../../core/thumbnails'
import { feedDensity, lockBodyScroll, setFeedDensity, unlockBodyScroll } from '../../core/uiPrefs'
import {
  countMatchingNotesForSubject,
  dedupeVisibleTodayEvents,
  DEFAULT_PAGE_SIZE,
  filterActiveBreakingHighlights,
  isInsideQuietHours,
  matchesFreshnessBucket,
  matchEventAgainstWatchlist,
  paginateItems,
  selectLeadEventIndex,
  sortEvents,
  type EventSortMode,
} from '../../core/v3Logic'
import { filterSmartEvents, isEventMuted } from '../../core/search'
import { normalizeExternalUrl } from '../../core/legacyAdapter'
import type { FreshnessBucket } from '../../core/urlState'
import type {
  AlertRuleSettings,
  BreakingHighlightItem,
  CatalystEvent,
  EntityProfile,
  InlineEventImpact,
  LiveWireItem,
  MajorTopicSpotlight,
  ResearchNote,
  SimulatedPerspective,
  SmartEvent,
  WatchlistItem,
  WatchlistKind,
} from '../../core/types'

const props = defineProps<{
  allEvents: SmartEvent[]
  entities: EntityProfile[]
  topics?: MajorTopicSpotlight[]
  archivedTopics?: MajorTopicSpotlight[]
  selectedTopicId?: string | null
  calendarEvents?: CatalystEvent[]
  watchlist: WatchlistItem[]
  mutedSet: Set<string>
  downweightedSet: Set<string>
  readLaterSet: Set<string>
  readLaterEvents?: SmartEvent[]
  hideReprints: boolean
  alertRules: AlertRuleSettings
  readIds: Set<string>
  legacyReadTitles: Set<string>
  bookmarkedIds: Set<string>
  previousSeenIds: Set<string>
  previousVisitedAt?: string | null
  previousBatchId: string | null
  liveWireItems?: LiveWireItem[]
  breakingHighlights?: BreakingHighlightItem[]
  nowMs: number
  freshBucket: FreshnessBucket
  searchQuery?: string
  readLaterDisplayCount?: number
  eventImpactMap?: Record<string, InlineEventImpact>
  isLoggedIn?: boolean
  todayReadCount?: number
  savedNoteMap?: Record<string, string>
  researchNotes?: ResearchNote[]
  commentsMap?: Record<string, SimulatedPerspective[]>
  loading?: boolean
  topicsLoading?: boolean
  activeSection?: 'feed' | 'pillars' | 'topics' | 'cocoon'
  openWatchlistNonce?: number
}>()

const emit = defineEmits<{
  (e: 'add-watchlist', item: WatchlistItem): void
  (e: 'remove-watchlist', id: string): void
  (e: 'apply-preset', preset: WatchlistPresetTemplate): void
  (e: 'open-onboarding'): void
  (e: 'open-weekly-report'): void
  (e: 'open-notes'): void
  (e: 'save-note', payload: { event: SmartEvent; content: string }): void
  (e: 'toggle-mute-event', key: string): void
  (e: 'unmute-all'): void
  (e: 'toggle-downweight-event', key: string): void
  (e: 'toggle-read-later', eventId: string): void
  (e: 'toggle-hide-reprints', val: boolean): void
  (e: 'update:freshBucket', val: FreshnessBucket): void
  (e: 'update:activeSection', val: 'feed' | 'pillars' | 'topics' | 'cocoon'): void
  (e: 'update-alert-rules', rules: AlertRuleSettings): void
  (e: 'toggle-read', event: SmartEvent): void
  (e: 'mark-read', event: SmartEvent): void
  (e: 'mark-all-read', events: SmartEvent[]): void
  (e: 'toggle-bookmark', event: SmartEvent): void
  (e: 'copy-link', event: SmartEvent): void
  (e: 'select-entity', entityName: string): void
  (e: 'open-storyline', storylineId: string): void
  (e: 'open-qa', event: SmartEvent): void
  (e: 'open-detail', event: SmartEvent): void
  (e: 'open-qa-topic', topic: MajorTopicSpotlight): void
  (e: 'jump-to-event', event: SmartEvent): void
  (e: 'jump-event-id', eventId: string, fallbackUrl?: string | null): void
  (e: 'switch-tab', tab: 'calendar' | 'predictions' | 'tracking' | 'briefing' | 'wire'): void
  (e: 'clear-search'): void
  (e: 'open-auth'): void
}>()

const filterDrawerOpen = ref(false)
const showAllNonMatched = ref(false)
const onlyReadLater = ref(false)
const onlyNewSinceVisit = ref(false)
const onlyHeavy = ref(false)
const wirePulseIdx = ref(0)
const wirePulseExpanded = ref(false)
const antiEchoMode = ref(false)
const expandedEventIds = ref<Set<string>>(new Set())

// Freeze read baseline for lead-story ordering during active session so markRead never re-sorts or collapses cards!
const sessionReadIds = ref<Set<string>>(new Set(props.readIds))
const sessionLegacyReadTitles = ref<Set<string>>(new Set(props.legacyReadTitles))
const eventBatchKey = computed(() =>
  props.allEvents
    .slice(0, 6)
    .map((e) => e.event_id)
    .join('|'),
)
watch(eventBatchKey, () => {
  sessionReadIds.value = new Set(props.readIds)
  sessionLegacyReadTitles.value = new Set(props.legacyReadTitles)
})

watch(
  () => props.openWatchlistNonce,
  (n) => {
    if (n && n > 0) {
      filterDrawerOpen.value = true
    }
  },
)

function setExpandedEvent(eventId: string, isExpanded: boolean) {
  const next = new Set(expandedEventIds.value)
  if (isExpanded) next.add(eventId)
  else next.delete(eventId)
  expandedEventIds.value = next
}

const TOPICS_SEEN_KEY = 'jx_topics_seen_batch_v1'
const topicsBatchSig = computed(() => {
  const tops = props.topics || []
  const latestUpd = tops[0]?.updated_at || ''
  return `${props.previousBatchId || 'cur'}:${tops.length}:${latestUpd}`
})
const seenTopicsBatchSig = ref<string>(
  typeof window !== 'undefined' ? window.localStorage.getItem(TOPICS_SEEN_KEY) || '' : '',
)
const topicsUnseenBadgeCount = computed(() => {
  if (seenTopicsBatchSig.value && seenTopicsBatchSig.value === topicsBatchSig.value) return 0
  return updatedTopicsSinceVisitCount.value
})
function markTopicsTabSeen() {
  seenTopicsBatchSig.value = topicsBatchSig.value
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(TOPICS_SEEN_KEY, topicsBatchSig.value)
  }
}
const internalSection = ref<'feed' | 'pillars' | 'topics' | 'cocoon'>(props.activeSection || 'feed')
const todaySection = computed<'feed' | 'pillars' | 'topics' | 'cocoon'>({
  get: () => props.activeSection ?? internalSection.value,
  set: (v) => {
    internalSection.value = v
    emit('update:activeSection', v)
  },
})
watch(
  todaySection,
  (sec) => {
    if (sec === 'topics') markTopicsTabSeen()
  },
)

watch(
  () => props.activeSection,
  (val) => {
    if (val) internalSection.value = val
  },
)

const sortBy = ref<EventSortMode>('relevance')
const visibleLimit = ref(DEFAULT_PAGE_SIZE)
const newKind = ref<WatchlistKind>('industry')
const newLabel = ref('')
const newKeywords = ref('')
const newMarket = ref('')

function onDrawerKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && filterDrawerOpen.value) {
    e.preventDefault()
    e.stopPropagation()
    filterDrawerOpen.value = false
  }
}

watch(filterDrawerOpen, (open) => {
  if (open) {
    lockBodyScroll()
    if (typeof window !== 'undefined') window.addEventListener('keydown', onDrawerKeydown, true)
  } else {
    unlockBodyScroll()
    if (typeof window !== 'undefined') window.removeEventListener('keydown', onDrawerKeydown, true)
  }
})

onUnmounted(() => {
  if (filterDrawerOpen.value) unlockBodyScroll()
  if (typeof window !== 'undefined') window.removeEventListener('keydown', onDrawerKeydown, true)
})

const activeFilterCount = computed(() => {
  let n = 0
  if (props.freshBucket !== 'all') n += 1
  if (onlyReadLater.value) n += 1
  if (onlyNewSinceVisit.value) n += 1
  if (antiEchoMode.value) n += 1
  if (sortBy.value !== 'relevance') n += 1
  return n
})

const hasReturnBaseline = computed(() => Boolean(props.previousVisitedAt || props.previousBatchId))

const newSinceVisitEventIds = computed(() => {
  const out = new Set<string>()
  if (!hasReturnBaseline.value) return out
  const prevMs = props.previousVisitedAt ? parseTimestampMs(props.previousVisitedAt) : null
  for (const ev of baseEligibleEvents.value) {
    if (!isVerifiedSourceEvent(ev)) continue
    const evMs = parseTimestampMs(ev.latest_reported_at || ev.latest_fact_update_at || ev.first_reported_at || ev.fetched_at)
    const newerTs = prevMs !== null && evMs !== null && evMs > prevMs
    const unseenInBatch = Boolean(props.previousBatchId && !props.previousSeenIds.has(ev.event_id))
    if (newerTs || unseenInBatch) {
      out.add(ev.event_id)
    }
  }
  return out
})

const updatedTopicsSinceVisitCount = computed(() => {
  if (!hasReturnBaseline.value) return 0
  const prevMs = props.previousVisitedAt ? parseTimestampMs(props.previousVisitedAt) : null
  return (props.topics || []).filter((tp) => {
    if (prevMs !== null) {
      const tpMs = parseTimestampMs(tp.updated_at)
      if (tpMs !== null && tpMs > prevMs) return true
    }
    return (tp.recent_6h_count ?? 0) > 0
  }).length
})

function matchingNotesForEvent(ev: SmartEvent): number {
  if (!props.researchNotes || props.researchNotes.length === 0) return 0
  return countMatchingNotesForSubject(props.researchNotes, {
    eventId: ev.event_id,
    storylineId: ev.storyline_id,
    entityIds: ev.entity_ids,
    entities: ev.entities,
  })
}

const wirePulseItems = computed<LiveWireItem[]>(() => (props.liveWireItems || []).slice(0, 2))
const activeWirePulse = computed<LiveWireItem | null>(() => {
  const list = wirePulseItems.value
  if (!list.length) return null
  return list[wirePulseIdx.value % list.length]
})

const visibleUnreadEvents = computed(() => {
  const list =
    sortedMatchedList.value.length > 0
      ? pagedMatched.value.visible.map((x) => x.event)
      : pagedFallback.value.visible.map((x) => x.event)
  return list.filter((ev) => !isEventRead(ev, props.readIds, props.legacyReadTitles))
})

const KIND_LABELS = computed<Record<WatchlistKind, string>>(() => ({
  company: t('公司', 'Company'),
  ticker: t('标的/代码', 'Ticker'),
  industry: t('行业主题', 'Industry'),
  tech: t('技术路线', 'Tech'),
  event: t('持续事件', 'Event'),
}))

const quietActive = computed(() => isInsideQuietHours(props.alertRules, new Date(props.nowMs)))

interface ScoredItem {
  event: SmartEvent
  matched: boolean
  score: number
  matchReasons: string[]
  downweighted: boolean
  isReadLater: boolean
}

const baseEligibleEvents = computed(() => {
  const q = (props.searchQuery || '').trim()
  const preFiltered = q
    ? filterSmartEvents(props.allEvents, {
        query: q,
        sourceId: 'all',
        evidence: 'all',
      })
    : props.allEvents

  return dedupeVisibleTodayEvents(preFiltered, props.hideReprints, {
    alertRules: props.alertRules,
    mutedSet: props.mutedSet,
    watchlist: props.watchlist,
    downweightedSet: props.downweightedSet,
    nowMs: props.nowMs,
  })
})

const bucketCounts = computed(() => {
  const base = baseEligibleEvents.value
  return {
    all: base.length,
    unread: base.filter((e) => matchesFreshnessBucket(e, 'unread', props.readIds, props.legacyReadTitles)).length,
    first_discovery: base.filter((e) => matchesFreshnessBucket(e, 'first_discovery', props.readIds, props.legacyReadTitles)).length,
    old_progress: base.filter((e) => matchesFreshnessBucket(e, 'old_progress', props.readIds, props.legacyReadTitles)).length,
  }
})

const readLaterCount = computed(() =>
  props.readLaterDisplayCount !== undefined
    ? props.readLaterDisplayCount
    : baseEligibleEvents.value.filter((e) => props.readLaterSet.has(e.event_id)).length,
)

const mutedItemsDetail = computed(() => {
  const byKey = new Map<string, string>()
  for (const ev of props.allEvents) {
    if (ev.event_id) byKey.set(ev.event_id, ev.title)
    if (ev.storyline_id) byKey.set(ev.storyline_id, ev.title)
  }
  return Array.from(props.mutedSet).map((key) => ({
    key,
    label: byKey.get(key) || t(`已屏蔽事件/主线 (${key.slice(0, 18)})`, `Muted thread (${key.slice(0, 18)})`),
  }))
})

const isHeavyEvent = (ev: SmartEvent) =>
  ev.severity_tier === 'S' || ev.severity_tier === 'A' || ev.importance === 'high'

const heavyTodayCount = computed(() =>
  baseEligibleEvents.value.filter((ev) => isVerifiedSourceEvent(ev) && isHeavyEvent(ev)).length,
)

const isVerifiedSourceEvent = (ev: SmartEvent) =>
  (ev.sources?.length ?? 0) > 0 && ev.evidence_status !== 'needs_verification'

const unverifiedTodayEvents = computed(() =>
  baseEligibleEvents.value.filter((ev) => !isVerifiedSourceEvent(ev)),
)

const batchAnchorMs = computed(() => {
  let maxMs = 0
  for (const ev of baseEligibleEvents.value) {
    const m = Date.parse(ev.latest_reported_at || ev.first_reported_at || ev.published_at || ev.fetched_at || '')
    if (!Number.isNaN(m) && m > maxMs) maxMs = m
  }
  return maxMs || props.nowMs
})

const scoredResults = computed(() => {
  const matchedList: ScoredItem[] = []
  const fallbackList: ScoredItem[] = []
  const anchorMs = batchAnchorMs.value
  const cmpScoredDesc = (a: ScoredItem, b: ScoredItem) =>
    b.score - a.score ||
    String(b.event.latest_reported_at || b.event.published_at || '').localeCompare(
      String(a.event.latest_reported_at || a.event.published_at || ''),
    ) ||
    String(a.event.event_id).localeCompare(String(b.event.event_id))

  if (onlyReadLater.value) {
    const rlPool = props.readLaterEvents && props.readLaterEvents.length > 0
      ? props.readLaterEvents
      : props.allEvents.filter((e) => props.readLaterSet.has(e.event_id))
    for (const ev of rlPool) {
      matchedList.push({
        event: ev,
        matched: true,
        score: 100,
        matchReasons: [t('已加入稍后深读清单', 'In Read Later')],
        downweighted: false,
        isReadLater: true,
      })
    }
    return { matchedList, fallbackList }
  }

  for (const ev of baseEligibleEvents.value) {
    if (!isVerifiedSourceEvent(ev)) {
      continue
    }
    if (onlyHeavy.value && !isHeavyEvent(ev)) {
      continue
    }
    if (onlyNewSinceVisit.value && !newSinceVisitEventIds.value.has(ev.event_id)) {
      continue
    }
    if (!matchesFreshnessBucket(ev, props.freshBucket, props.readIds, props.legacyReadTitles)) {
      continue
    }
    const res = matchEventAgainstWatchlist(ev, props.watchlist, props.mutedSet, props.downweightedSet, anchorMs)
    const entry: ScoredItem = {
      event: ev,
      matched: res.matched,
      score: res.score,
      matchReasons: res.matchReasons,
      downweighted: res.downweighted,
      isReadLater: props.readLaterSet.has(ev.event_id),
    }
    if (entry.matched) {
      matchedList.push(entry)
    } else {
      fallbackList.push(entry)
    }
  }

  if (antiEchoMode.value && !onlyReadLater.value) {
    // Anti-echo-chamber mode: ignore personal watchlist bias and interleave top global events evenly across all 4 domains
    const allItems = [...matchedList, ...fallbackList]
    const byCat = new Map<string, ScoredItem[]>()
    for (const item of allItems) {
      const cat = item.event.category || 'general'
      const indep = item.event.independent_publisher_count || item.event.sources?.length || 1
      const objectiveScore =
        indep * 14 +
        (item.event.evidence_status === 'official_confirmed' ? 24 : 0) +
        (item.event.is_new_in_batch ? 15 : 0)
      const enriched: ScoredItem = {
        ...item,
        matched: true,
        score: objectiveScore,
        matchReasons: [t('破茧全视野 · 无兴趣偏置跨领域呈现', 'Unbiased Panorama · Cross-Domain Balanced')],
      }
      const arr = byCat.get(cat) ?? []
      arr.push(enriched)
      byCat.set(cat, arr)
    }
    for (const arr of byCat.values()) {
      arr.sort(cmpScoredDesc)
    }
    const order = ['global', 'finance', 'tech', 'general']
    const interleaved: ScoredItem[] = []
    let idx = 0
    let added = true
    while (added) {
      added = false
      for (const cat of order) {
        const arr = byCat.get(cat)
        if (arr && idx < arr.length) {
          interleaved.push(arr[idx])
          added = true
        }
      }
      idx += 1
    }
    return { matchedList: interleaved, fallbackList: [] }
  }

  matchedList.sort(cmpScoredDesc)
  fallbackList.sort(cmpScoredDesc)
  return { matchedList, fallbackList }
})

const DOMAIN_META = computed<{ key: 'global' | 'finance' | 'tech' | 'general'; label: string; color: string }[]>(() => [
  { key: 'global', label: t('全球动态', 'Global Developments'), color: 'bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/50 dark:text-rose-300 dark:border-rose-800' },
  { key: 'finance', label: t('财经宏观', 'Finance & Macro'), color: 'bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-950/50 dark:text-amber-300 dark:border-amber-800' },
  { key: 'tech', label: t('前沿科技', 'Tech & AI'), color: 'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/50 dark:text-blue-300 dark:border-blue-800' },
  { key: 'general', label: t('综合焦点', 'Top Headlines'), color: 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/50 dark:text-emerald-300 dark:border-emerald-800' },
])

/** Anti-Echo-Chamber Blindspot Radar: picks 1 high-impact story from EACH of the 4 global pillars outside the user's Watchlist */
const blindspotDiscovery = computed(() => {
  const anchorMs = batchAnchorMs.value
  const matchedIdSet = new Set(
    props.allEvents
      .filter((ev) => matchEventAgainstWatchlist(ev, props.watchlist, props.mutedSet, props.downweightedSet, anchorMs).matched)
      .map((ev) => ev.event_id),
  )

  const cards: { ev: SmartEvent; domainLabel: string; domainColor: string; isBlindspot: boolean; indepCount: number }[] = []
  const usedTitles = new Set<string>()

  for (const dom of DOMAIN_META.value) {
    const inDom = props.allEvents.filter(
      (ev) => ev.category === dom.key && !isEventMuted(ev, props.mutedSet) && isVerifiedSourceEvent(ev),
    )
    const blindPool = inDom.filter((ev) => !matchedIdSet.has(ev.event_id))
    const pool = blindPool.length > 0 ? blindPool : inDom
    const ranked = [...pool].sort((a, b) => {
      const sa = (a.independent_publisher_count || a.sources?.length || 1) * 10 + (a.evidence_status === 'official_confirmed' ? 20 : 0) + (a.is_new_in_batch ? 8 : 0)
      const sb = (b.independent_publisher_count || b.sources?.length || 1) * 10 + (b.evidence_status === 'official_confirmed' ? 20 : 0) + (b.is_new_in_batch ? 8 : 0)
      return sb - sa || String(a.event_id).localeCompare(String(b.event_id))
    })
    const pick = ranked.find((ev) => !usedTitles.has(ev.title))
    if (pick) {
      usedTitles.add(pick.title)
      cards.push({
        ev: pick,
        domainLabel: dom.label,
        domainColor: dom.color,
        isBlindspot: !matchedIdSet.has(pick.event_id),
        indepCount: pick.independent_publisher_count || pick.sources?.length || 1,
      })
    }
  }
  return cards
})

function handleAddWatchlist() {
  const lbl = newLabel.value.trim()
  if (!lbl) return
  const matchedEnt = props.entities.find(
    (e) =>
      e.canonical_name.toLowerCase().includes(lbl.toLowerCase()) ||
      e.aliases.some((a) => a.toLowerCase() === lbl.toLowerCase()) ||
      e.tickers.some((t) => t.symbol.toLowerCase() === lbl.toLowerCase()),
  )
  const kws = newKeywords.value
    .split(/[,，\s]+/)
    .map((s) => s.trim())
    .filter(Boolean)
  if (!kws.includes(lbl)) kws.unshift(lbl)

  emit('add-watchlist', {
    id: `wl_${Date.now().toString(36)}`,
    kind: newKind.value,
    label: newMarket.value.trim() ? `${lbl} (${newMarket.value.trim()})` : lbl,
    entity_id: matchedEnt?.entity_id ?? null,
    market: newMarket.value.trim() || null,
    keywords: Array.from(new Set(kws)),
    created_at: new Date().toISOString(),
  })
  newLabel.value = ''
  newKeywords.value = ''
  newMarket.value = ''
}

function updateRule<K extends keyof AlertRuleSettings>(key: K, val: AlertRuleSettings[K]) {
  emit('update-alert-rules', {
    ...props.alertRules,
    [key]: val,
  })
}

function isCalClockTbd(cal: CatalystEvent): boolean {
  if (cal.is_clock_tbd || cal.certainty === 'tbd' || cal.certainty === 'reported_tbd') return true
  return /钟点待定|时间待定|待官方|TBD/i.test(cal.original_time_note || '')
}

const upcomingTomorrowTop3 = computed(() => {
  const list = props.calendarEvents || []
  const todayStr = formatShanghaiDateOnly(new Date(props.nowMs).toISOString())
  const cutoff = props.nowMs - 2 * 3_600_000
  return list
    .filter((ev) => {
      if (!ev.scheduled_at || ev.is_past) return false
      const evDate = formatShanghaiDateOnly(ev.scheduled_at)
      if (evDate < todayStr) return false
      const ms = parseTimestampMs(ev.scheduled_at)
      return ms !== null && (isCalClockTbd(ev) || ms >= cutoff)
    })
    .sort((a, b) => (a.scheduled_at || '').localeCompare(b.scheduled_at || ''))
    .slice(0, 3)
})

function formatShortCountdown(cal: CatalystEvent): string {
  if (isCalClockTbd(cal)) return t('当日待定', 'Day TBD')
  const ms = parseTimestampMs(cal.scheduled_at)
  if (ms === null) return t('待定', 'TBD')
  const diffH = Math.round((ms - props.nowMs) / 3_600_000)
  if (diffH <= 0) return t('即将发生', 'Imminent')
  if (diffH < 24) return t(`${diffH}h 后`, `in ${diffH}h`)
  const days = Math.floor(diffH / 24)
  return days === 1
    ? t(`明天 (${diffH % 24}h)`, `Tomorrow (${diffH % 24}h)`)
    : t(`${days} 天后`, `in ${days}d`)
}

function rotateLeadScoredList(list: ScoredItem[]): ScoredItem[] {
  if (
    list.length <= 1 ||
    sortBy.value !== 'relevance' ||
    onlyReadLater.value ||
    onlyNewSinceVisit.value ||
    Boolean((props.searchQuery || '').trim())
  ) {
    return list
  }
  const idx = selectLeadEventIndex(
    list.map((x) => x.event),
    new Set<string>(),
    new Set<string>(),
    batchAnchorMs.value,
  )
  if (idx <= 0 || idx >= list.length) return list
  const copy = [...list]
  const [lead] = copy.splice(idx, 1)
  copy.unshift(lead)
  return copy
}

const sortedMatchedList = computed(() => {
  if (sortBy.value === 'relevance') {
    return rotateLeadScoredList(scoredResults.value.matchedList)
  }
  const orderedEvents = sortEvents(
    scoredResults.value.matchedList.map((i) => i.event),
    sortBy.value,
    props.watchlist,
    props.mutedSet,
    props.downweightedSet,
    props.nowMs,
  )
  const byId = new Map(scoredResults.value.matchedList.map((i) => [i.event.event_id, i]))
  return orderedEvents.map((ev) => byId.get(ev.event_id)!).filter(Boolean)
})

const pagedMatched = computed(() => paginateItems(sortedMatchedList.value, visibleLimit.value))

const sortedFallbackList = computed(() => {
  if (sortBy.value === 'relevance') {
    return rotateLeadScoredList(scoredResults.value.fallbackList)
  }
  const orderedEvents = sortEvents(
    scoredResults.value.fallbackList.map((i) => i.event),
    sortBy.value,
    props.watchlist,
    props.mutedSet,
    props.downweightedSet,
    props.nowMs,
  )
  const byId = new Map(scoredResults.value.fallbackList.map((i) => [i.event.event_id, i]))
  return orderedEvents.map((ev) => byId.get(ev.event_id)!).filter(Boolean)
})

const pagedFallback = computed(() =>
  paginateItems(sortedFallbackList.value, props.searchQuery?.trim() ? visibleLimit.value : Math.max(12, visibleLimit.value)),
)

interface FeedRenderRow {
  item: ScoredItem
  crossDomainBadge?: string | null
  crossDomainHint?: string | null
}

function buildCrossDomainHint(ev: SmartEvent): string {
  const cat = ev.category || 'global'
  if (cat === 'global') {
    return t(
      '地缘/政策大事件常通过关税、汇率与供应链溢价跨界传导至科技与市场估值',
      'Macro & geopolitical shifts transmit into tech supply chains, FX, and risk premia',
    )
  }
  if (cat === 'finance') {
    return t(
      '流动性与通胀预期变化直接影响跨板块融资成本与资产风险偏好',
      'Rates & liquidity repricing directly alters sector valuation multiples and capex',
    )
  }
  if (cat === 'tech') {
    return t(
      '前沿技术与算力范式突破正在重塑上游能源、制造及资本开支分配',
      'Frontier AI & hardware shifts reshape capex allocation and downstream industries',
    )
  }
  return t(
    '高热社会与产业事件提供主线之外的增量风偏与政策敏感度参考',
    'High-velocity general events add cross-market context outside core watchlists',
  )
}

/** Weave 1-2 full blindspot EventCards naturally inside 精选 feed (retiring old 4-button stub tab) */
const interwovenFeedRows = computed<FeedRenderRow[]>(() => {
  const baseRows: FeedRenderRow[] = pagedMatched.value.visible.map((item) => ({ item }))
  if (
    onlyReadLater.value ||
    onlyHeavy.value ||
    antiEchoMode.value ||
    Boolean((props.searchQuery || '').trim()) ||
    props.freshBucket !== 'all' ||
    baseRows.length === 0
  ) {
    return baseRows
  }
  const alreadyIds = new Set(baseRows.map((r) => r.item.event.event_id))
  const blindPicks = blindspotDiscovery.value
    .filter((b) => b.isBlindspot && !alreadyIds.has(b.ev.event_id))
    .slice(0, 2)
  if (blindPicks.length === 0) return baseRows

  const out = [...baseRows]
  blindPicks.forEach((bp, idx) => {
    const row: FeedRenderRow = {
      item: {
        event: bp.ev,
        matched: false,
        score: 0,
        matchReasons: [t('跨界破茧 · 盲区高热', 'Cross-Domain Blindspot')],
        downweighted: false,
        isReadLater: props.readLaterSet.has(bp.ev.event_id),
      },
      crossDomainBadge: t(`跨界破茧 · ${bp.domainLabel}`, `Cross-Domain · ${bp.domainLabel}`),
      crossDomainHint: buildCrossDomainHint(bp.ev),
    }
    const insertAt = Math.min(out.length, idx === 0 ? 2 : 6)
    out.splice(insertAt, 0, row)
  })
  return out
})

const activeBreakingHighlights = computed<BreakingHighlightItem[]>(() => {
  if (
    onlyReadLater.value ||
    onlyNewSinceVisit.value ||
    Boolean((props.searchQuery || '').trim()) ||
    props.freshBucket !== 'all'
  ) {
    return []
  }
  const topEvents = interwovenFeedRows.value.map((r) => r.item.event)
  const filteredBh = (props.breakingHighlights || []).filter(
    (bh) => !props.mutedSet.has(bh.id) && !(bh.id && props.mutedSet.has(bh.id.replace(/^brk_/, ''))),
  )
  return filterActiveBreakingHighlights(filteredBh, topEvents, props.nowMs)
})
</script>


<template>
  <section class="space-y-2.5" :aria-label="t('今日要闻', 'Today Top Stories')">
    <!-- Responsive Smart-Sticky Sub-Bar (fits 360px/393px ZH & EN cleanly; sticks on <768px & Android) -->
    <div
      class="mobile-sticky-subbar flex flex-wrap items-center justify-between gap-y-1.5 gap-x-1.5 px-0.5"
      data-testid="today-sticky-subbar"
    >
      <div class="flex items-center gap-0.5 sm:gap-1 min-w-0">
        <button
          v-for="sec in ([
            { id: 'feed', label: t('精选', 'Top'), show: true },
            { id: 'pillars', label: t('分类', 'All'), show: true },
            { id: 'topics', label: t('专题', 'Topics'), show: true },
            { id: 'cocoon', label: t('破茧', 'Cocoon'), show: true },
          ] as const).filter((x) => x.show)"
          :key="sec.id"
          type="button"
          @click="todaySection = sec.id; if (sec.id === 'topics') markTopicsTabSeen()"
          class="mobile-pressable ios-tap inline-flex items-center gap-1 min-h-[34px] px-2 sm:px-2.5 rounded-xl text-[13px] font-semibold whitespace-nowrap shrink-0 transition-colors"
          :class="
            todaySection === sec.id
              ? 'bg-zinc-900 text-white dark:bg-white dark:text-zinc-950'
              : 'text-zinc-500 dark:text-zinc-400 hover:bg-black/[0.04] dark:hover:bg-white/[0.06]'
          "
        >
          <span>{{ sec.label }}</span>
          <span
            v-if="sec.id === 'topics' && topicsUnseenBadgeCount > 0 && todaySection !== 'topics'"
            class="px-1.5 py-0.2 rounded-full text-[10px] font-bold tabular-nums bg-[#007AFF]/15 text-[#007AFF] dark:bg-[#0A84FF]/25 dark:text-[#66B2FF]"
            data-testid="topics-unread-badge"
          >
            {{ topicsUnseenBadgeCount }}
          </span>
        </button>
      </div>

      <div
        v-if="todaySection === 'feed' && heavyTodayCount > 0"
        class="order-3 sm:order-2 basis-full sm:basis-auto sm:mr-auto flex items-center"
      >
        <button
          type="button"
          @click="onlyHeavy = !onlyHeavy"
          :aria-pressed="onlyHeavy"
          class="inline-flex items-center gap-1.5 min-h-[30px] px-2.5 rounded-full text-[11.5px] font-bold whitespace-nowrap shrink-0 transition-all"
          :class="
            onlyHeavy
              ? 'bg-[#DC2626] text-white shadow-xs jx-heavy-capsule'
              : 'bg-red-50 dark:bg-red-950/35 text-[#DC2626] dark:text-red-300 border border-red-200 dark:border-red-900/70 hover:bg-red-100'
          "
          data-testid="today-heavy-filter"
        >
          <span
            class="jx-sonar-dot"
            :class="onlyHeavy ? 'jx-sonar-white' : 'jx-sonar-red'"
          />
          <span>{{ t(`今日重磅 (${heavyTodayCount})`, `Top Stories (${heavyTodayCount})`) }}</span>
        </button>
      </div>

      <div class="order-2 sm:order-3 flex items-center gap-1 shrink-0">
        <!-- Mark all visible unread as read -->
        <button
          v-if="todaySection === 'feed' && visibleUnreadEvents.length > 0"
          type="button"
          @click="emit('mark-all-read', visibleUnreadEvents)"
          class="inline-flex items-center justify-center w-9 h-9 sm:w-auto sm:h-8 sm:px-2.5 sm:gap-1 rounded-xl text-xs font-medium text-zinc-600 dark:text-zinc-300 hover:bg-black/[0.05] dark:hover:bg-white/[0.08] transition-colors"
          :title="t('全部标为已读', 'Mark all read')"
          :aria-label="t('全部标为已读', 'Mark all read')"
        >
          <CheckCheck class="w-4 h-4 shrink-0" :stroke-width="1.5" />
          <span class="hidden sm:inline">{{ t('全已读', 'Read All') }}</span>
        </button>

        <!-- Compact / Standard Density Segmented Toggle (Desktop toolbar; on mobile lives inside Filter Sheet & Me) -->
        <div class="hidden sm:inline-flex ios-segmented" role="group" :aria-label="t('卡片密度', 'Card density')">
          <button
            type="button"
            @click="setFeedDensity('compact')"
            class="ios-segmented-btn min-h-[32px] px-2.5"
            :class="feedDensity === 'compact' ? 'ios-segmented-btn-active' : 'text-zinc-500 dark:text-zinc-400'"
          >
            {{ t('紧凑', 'Compact') }}
          </button>
          <button
            type="button"
            @click="setFeedDensity('standard')"
            class="ios-segmented-btn min-h-[32px] px-2.5"
            :class="feedDensity === 'standard' ? 'ios-segmented-btn-active' : 'text-zinc-500 dark:text-zinc-400'"
          >
            {{ t('标准', 'Standard') }}
          </button>
        </div>

        <!-- Low-frequency controls collapsed into Bottom Sheet Drawer -->
        <button
          v-if="todaySection === 'feed'"
          type="button"
          @click="filterDrawerOpen = true"
          class="relative inline-flex items-center justify-center gap-1 h-9 sm:h-8 px-2.5 rounded-xl text-xs font-semibold transition-colors whitespace-nowrap"
          :class="
            activeFilterCount > 0
              ? 'bg-[#007AFF] text-white'
              : 'bg-white dark:bg-[#1C1C1E] text-zinc-700 dark:text-zinc-200 shadow-[0_1px_2px_rgba(0,0,0,0.04)]'
          "
          :aria-label="t('打开筛选与关注管理', 'Open filters & watchlist')"
        >
          <SlidersHorizontal class="w-3.5 h-3.5 shrink-0" :stroke-width="1.5" />
          <span>{{ t('筛选', 'Filter') }}</span>
          <span
            v-if="activeFilterCount > 0"
            class="px-1.5 py-0.2 rounded-full bg-white/25 text-[10px] tabular-nums"
          >
            {{ activeFilterCount }}
          </span>
        </button>
      </div>
    </div>

    <!-- Compact Retention Strips inside 精选: Live Wire Pulse Strip + Return-Visit Delta Pill -->
    <div v-if="todaySection === 'feed' && !onlyReadLater" class="space-y-1.5">
      <div
        v-if="activeWirePulse"
        class="ios-card px-2.5 py-1.5 flex items-center justify-between gap-2 text-xs"
        data-testid="home-live-wire-pulse"
      >
        <button
          type="button"
          @click="wirePulseExpanded = !wirePulseExpanded"
          class="min-w-0 flex-1 flex items-center gap-1.5 text-left"
        >
          <span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-rose-500/12 text-rose-600 dark:text-rose-400 text-[10px] font-bold shrink-0 whitespace-nowrap">
            <span class="jx-sonar-dot jx-sonar-red" aria-hidden="true" />
            <Zap class="w-3 h-3" :stroke-width="2" />
            <span>{{ t('实时电报', 'Live') }}</span>
          </span>
          <span class="truncate font-medium text-zinc-800 dark:text-zinc-100">
            {{ activeWirePulse.title }}
          </span>
          <span class="hidden sm:inline text-[11px] text-zinc-400 tabular-nums shrink-0 whitespace-nowrap">
            · <SmartTime :iso="activeWirePulse.published_at" :now-ms="nowMs" />
          </span>
        </button>
        <div class="flex items-center gap-1 shrink-0">
          <button
            v-if="wirePulseItems.length > 1"
            type="button"
            @click="wirePulseIdx = (wirePulseIdx + 1) % wirePulseItems.length"
            class="px-1.5 min-h-[26px] rounded-lg bg-[#F2F2F7] dark:bg-[#2C2C2E] text-[10px] font-mono text-zinc-500 dark:text-zinc-300 tabular-nums whitespace-nowrap"
            :title="t('切换下一条快讯', 'Next flash wire')"
          >
            {{ (wirePulseIdx % wirePulseItems.length) + 1 }}/{{ wirePulseItems.length }}
          </button>
          <button
            type="button"
            @click="emit('switch-tab', 'wire')"
            class="inline-flex items-center gap-0.5 px-2 min-h-[26px] rounded-lg text-[11px] font-semibold text-[#007AFF] dark:text-[#0A84FF] hover:bg-[#007AFF]/10 whitespace-nowrap"
          >
            <span>{{ t('快讯流', 'Wire') }}</span>
            <ChevronRight class="w-3 h-3" />
          </button>
        </div>
      </div>

      <div
        v-if="wirePulseExpanded && activeWirePulse"
        class="rounded-xl bg-[#F5F5F7] dark:bg-[#2C2C2E] px-3 py-2 text-xs text-zinc-600 dark:text-zinc-300 space-y-1"
      >
        <div class="flex items-center justify-between gap-2 text-[11px] text-zinc-400">
          <span>{{ activeWirePulse.source_name }}</span>
          <SmartTime :iso="activeWirePulse.published_at" :now-ms="nowMs" />
        </div>
        <p class="leading-relaxed text-zinc-800 dark:text-zinc-100">
          {{ activeWirePulse.excerpt || activeWirePulse.title }}
        </p>
      </div>

      <!-- Mobile / Android Quick-Entry Chip Strip for Core Intelligence Modules -->
      <div
        class="mobile-quick-entry-strip items-center gap-1.5 overflow-x-auto no-scrollbar scroll-fade-x py-0.5"
        data-testid="mobile-quick-entry-strip"
      >
        <button
          type="button"
          @click="(e) => { centerPillIntoView(e); emit('switch-tab', 'calendar') }"
          class="mobile-pressable ios-tap inline-flex items-center gap-1.5 min-h-[34px] px-2.5 rounded-xl bg-white dark:bg-[#131823] border border-black/[0.06] dark:border-white/[0.08] text-[11.5px] font-semibold text-zinc-800 dark:text-zinc-100 whitespace-nowrap shrink-0 shadow-[0_1px_2px_rgba(0,0,0,0.03)]"
          data-testid="quick-entry-calendar"
        >
          <Calendar class="w-3.5 h-3.5 text-[#007AFF] shrink-0" :stroke-width="1.75" />
          <span>{{ t('催化日程 · 今日/本周重点', 'Calendar · Key Dates') }}</span>
        </button>
        <button
          type="button"
          @click="(e) => { centerPillIntoView(e); emit('switch-tab', 'tracking') }"
          class="mobile-pressable ios-tap inline-flex items-center gap-1.5 min-h-[34px] px-2.5 rounded-xl bg-white dark:bg-[#131823] border border-black/[0.06] dark:border-white/[0.08] text-[11.5px] font-semibold text-zinc-800 dark:text-zinc-100 whitespace-nowrap shrink-0 shadow-[0_1px_2px_rgba(0,0,0,0.03)]"
          data-testid="quick-entry-tracking"
        >
          <GitBranch class="w-3.5 h-3.5 text-violet-600 dark:text-violet-400 shrink-0" :stroke-width="1.75" />
          <span>{{ t('事件追踪 · 脉络档案', 'Tracking · Storylines') }}</span>
        </button>
        <button
          type="button"
          @click="(e) => { centerPillIntoView(e); emit('switch-tab', 'predictions') }"
          class="mobile-pressable ios-tap inline-flex items-center gap-1.5 min-h-[34px] px-2.5 rounded-xl bg-white dark:bg-[#131823] border border-black/[0.06] dark:border-white/[0.08] text-[11.5px] font-semibold text-zinc-800 dark:text-zinc-100 whitespace-nowrap shrink-0 shadow-[0_1px_2px_rgba(0,0,0,0.03)]"
          data-testid="quick-entry-predictions"
        >
          <Scale class="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400 shrink-0" :stroke-width="1.75" />
          <span>{{ t('前瞻验证', 'Predictions') }}</span>
        </button>
      </div>
    </div>

    <!-- Integrated 4-Pillar Briefings Sub-view -->
    <div v-if="todaySection === 'pillars'" class="ios-fade-in">
      <slot name="pillars" />
    </div>

    <!-- Quick-Switched Panels for 专题 -->
    <div v-else-if="todaySection === 'topics'" class="ios-fade-in">
      <LoadingSkeleton
        v-if="props.topicsLoading && ((props.topics?.length || 0) + (props.archivedTopics?.length || 0)) === 0"
        variant="cards"
        :count="3"
      />
      <TopicSpotlight
        v-else-if="((props.topics?.length || 0) + (props.archivedTopics?.length || 0)) > 0"
        :topics="props.topics || []"
        :archived-topics="props.archivedTopics || []"
        :initial-topic-id="props.selectedTopicId || null"
        :now-ms="props.nowMs"
        @open-qa-topic="emit('open-qa-topic', $event)"
        @jump-event-id="(evId, url) => emit('jump-event-id', evId, url)"
      />
      <div v-else class="ios-card p-6 text-center text-xs text-zinc-500">
        {{ t('当前暂无活跃专题，可稍后刷新查看。', 'No active topics at the moment.') }}
      </div>
    </div>

    <!-- Restored 破茧 (Cross-Domain Blindspot Discovery) View -->
    <div v-else-if="todaySection === 'cocoon'" class="ios-fade-in space-y-2.5" data-testid="today-cocoon-panel">
      <div class="ios-card px-3.5 py-2.5 flex items-center justify-between gap-2 text-xs">
        <div class="flex items-center gap-2 text-zinc-700 dark:text-zinc-200 font-medium">
          <Compass class="w-4 h-4 text-[#007AFF] shrink-0" :stroke-width="1.75" />
          <span>{{ t('破茧跨界视界：跳过关注词过滤，直接呈现在您关注领域之外的高独立信源事件', 'Cocoon Discovery: High-signal events outside your watchlist across macro, finance, tech & society') }}</span>
        </div>
      </div>
      <div v-if="blindspotDiscovery.length > 0" class="ios-card divide-y divide-black/[0.06] dark:divide-white/[0.08] overflow-hidden">
        <EventCard
          v-for="bp in blindspotDiscovery"
          :key="`cocoon-${bp.ev.event_id}`"
          :event="bp.ev"
          :now-ms="nowMs"
          :grouped="true"
          :controlled-expanded="expandedEventIds.has(bp.ev.event_id)"
          @set-expanded="setExpandedEvent(bp.ev.event_id, $event)"
          :is-read="isEventRead(bp.ev, readIds, legacyReadTitles)"
          :is-bookmarked="bookmarkedIds.has(bp.ev.event_id)"
          :is-new-since-visit="previousBatchId ? !previousSeenIds.has(bp.ev.event_id) : bp.ev.is_new_in_batch"
          :market-impact="eventImpactMap?.[bp.ev.event_id] || null"
          :thumbnail-url="bp.ev.thumbnail_url || null"
          :saved-note="savedNoteMap?.[bp.ev.event_id] || ''"
          :matching-note-count="matchingNotesForEvent(bp.ev)"
          :perspectives="commentsMap?.[bp.ev.category] || []"
          :is-read-later="readLaterSet.has(bp.ev.event_id)"
          :cross-domain-badge="t(`跨界破茧 · ${bp.domainLabel}`, `Cross-Domain · ${bp.domainLabel}`)"
          :cross-domain-hint="buildCrossDomainHint(bp.ev)"
          :show-moderation-actions="true"
          @toggle-read="emit('toggle-read', $event)"
          @mark-read="emit('mark-read', $event)"
          @open-notes="emit('open-notes')"
          @toggle-bookmark="emit('toggle-bookmark', $event)"
          @copy-link="emit('copy-link', $event)"
          @select-entity="emit('select-entity', $event)"
          @open-storyline="emit('open-storyline', $event)"
          @open-qa="emit('open-qa', $event)"
          @open-detail="emit('open-detail', $event)"
          @save-note="emit('save-note', $event)"
          @toggle-read-later="emit('toggle-read-later', $event)"
          @toggle-downweight="emit('toggle-downweight-event', $event)"
          @toggle-mute="emit('toggle-mute-event', $event)"
        />
      </div>
      <div v-else class="ios-card p-6 text-center text-xs text-zinc-500">
        {{ t('当前暂无额外盲区推荐事件', 'No cross-domain events available right now') }}
      </div>
    </div>

    <!-- Skeleton while loading -->
    <LoadingSkeleton v-else-if="loading && allEvents.length === 0" variant="cards" :count="4" />

    <!-- Empty / Fallback state -->
    <template v-else-if="sortedMatchedList.length === 0">
      <EmptySearchState
        v-if="scoredResults.fallbackList.length === 0"
        :query="props.searchQuery"
        :has-extra-filters="freshBucket !== 'all' || onlyReadLater || onlyNewSinceVisit"
        @clear-query="emit('clear-search')"
        @clear-filters-only="onlyReadLater = false; onlyNewSinceVisit = false; emit('update:freshBucket', 'all')"
        @reset="onlyReadLater = false; onlyNewSinceVisit = false; emit('update:freshBucket', 'all'); emit('clear-search')"
      />
      <div v-else class="space-y-2.5">
        <EventCard
          v-if="pagedFallback.visible[0]"
          :key="pagedFallback.visible[0].event.event_id"
          :event="pagedFallback.visible[0].event"
          :now-ms="nowMs"
          :featured="true"
          :controlled-expanded="expandedEventIds.has(pagedFallback.visible[0].event.event_id)"
          @set-expanded="setExpandedEvent(pagedFallback.visible[0].event.event_id, $event)"
          :is-read="isEventRead(pagedFallback.visible[0].event, readIds, legacyReadTitles)"
          :is-bookmarked="bookmarkedIds.has(pagedFallback.visible[0].event.event_id)"
          :is-new-since-visit="previousBatchId ? !previousSeenIds.has(pagedFallback.visible[0].event.event_id) : pagedFallback.visible[0].event.is_new_in_batch"
          :market-impact="eventImpactMap?.[pagedFallback.visible[0].event.event_id] || null"
          :thumbnail-url="pagedFallback.visible[0].event.thumbnail_url || null"
          :saved-note="savedNoteMap?.[pagedFallback.visible[0].event.event_id] || ''"
          :matching-note-count="matchingNotesForEvent(pagedFallback.visible[0].event)"
          :perspectives="commentsMap?.[pagedFallback.visible[0].event.category] || []"
          :is-read-later="readLaterSet.has(pagedFallback.visible[0].event.event_id)"
          :show-moderation-actions="true"
          @toggle-read="emit('toggle-read', $event)"
          @mark-read="emit('mark-read', $event)"
          @open-notes="emit('open-notes')"
          @toggle-bookmark="emit('toggle-bookmark', $event)"
          @copy-link="emit('copy-link', $event)"
          @select-entity="emit('select-entity', $event)"
          @open-storyline="emit('open-storyline', $event)"
          @open-qa="emit('open-qa', $event)"
          @open-detail="emit('open-detail', $event)"
          @save-note="emit('save-note', $event)"
          @toggle-read-later="emit('toggle-read-later', $event)"
          @toggle-downweight="emit('toggle-downweight-event', $event)"
          @toggle-mute="emit('toggle-mute-event', $event)"
        />
        <div
          v-if="pagedFallback.visible.length > 1"
          class="ios-card divide-y divide-black/[0.06] dark:divide-white/[0.08] overflow-hidden"
        >
          <EventCard
            v-for="item in pagedFallback.visible.slice(1)"
            :key="item.event.event_id"
            :event="item.event"
            :now-ms="nowMs"
            :grouped="true"
            :controlled-expanded="expandedEventIds.has(item.event.event_id)"
            @set-expanded="setExpandedEvent(item.event.event_id, $event)"
            :is-read="isEventRead(item.event, readIds, legacyReadTitles)"
            :is-bookmarked="bookmarkedIds.has(item.event.event_id)"
            :is-new-since-visit="previousBatchId ? !previousSeenIds.has(item.event.event_id) : item.event.is_new_in_batch"
            :market-impact="eventImpactMap?.[item.event.event_id] || null"
            :thumbnail-url="item.event.thumbnail_url || null"
            :saved-note="savedNoteMap?.[item.event.event_id] || ''"
            :matching-note-count="matchingNotesForEvent(item.event)"
            :perspectives="commentsMap?.[item.event.category] || []"
            :is-read-later="readLaterSet.has(item.event.event_id)"
            :show-moderation-actions="true"
            @toggle-read="emit('toggle-read', $event)"
            @mark-read="emit('mark-read', $event)"
            @open-notes="emit('open-notes')"
            @toggle-bookmark="emit('toggle-bookmark', $event)"
            @copy-link="emit('copy-link', $event)"
            @select-entity="emit('select-entity', $event)"
            @open-storyline="emit('open-storyline', $event)"
            @open-qa="emit('open-qa', $event)"
            @open-detail="emit('open-detail', $event)"
            @save-note="emit('save-note', $event)"
            @toggle-read-later="emit('toggle-read-later', $event)"
            @toggle-downweight="emit('toggle-downweight-event', $event)"
            @toggle-mute="emit('toggle-mute-event', $event)"
          />
        </div>
      </div>
    </template>

    <!-- Primary Top Feed: Fast-Track S-Tier Breaking + #1 Lead Story + iOS Inset Grouped List (#2+ incl. interwoven Cross-Domain Blindspot Cards) -->
    <div v-else class="space-y-2.5">
      <!-- Fast-Track S-Tier Breaking Promotion (surfaces major policy/regulatory wires within minutes without waiting for 3h AI batch) -->
      <div
        v-if="activeBreakingHighlights.length > 0"
        class="space-y-2"
        data-testid="fast-track-breaking-card"
      >
        <div
          v-for="bh in activeBreakingHighlights"
          :key="bh.id"
          class="ios-card border border-rose-500/25 bg-gradient-to-br from-rose-50/90 via-white to-white dark:from-rose-950/35 dark:via-[#1C1C1E] dark:to-[#1C1C1E] px-3.5 py-3 space-y-2"
        >
          <div class="flex items-center justify-between gap-2 text-[11px]">
            <div class="flex items-center gap-1.5 min-w-0">
              <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-[#DC2626] text-white font-bold tracking-tight shrink-0 whitespace-nowrap">
                <span class="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
                <span>{{ t(bh.breaking_label || '刚刚突发 · 重磅', 'BREAKING · HEAVY') }}</span>
              </span>
              <span class="font-medium text-rose-700 dark:text-rose-300 truncate">{{ bh.source_name }}</span>
              <span class="text-zinc-300 dark:text-zinc-600">·</span>
              <SmartTime :iso="bh.published_at" :now-ms="nowMs" class="text-zinc-500 dark:text-zinc-400 tabular-nums shrink-0" />
            </div>
            <button
              type="button"
              @click="emit('switch-tab', 'wire')"
              class="text-[11px] font-semibold text-rose-600 dark:text-rose-400 hover:underline shrink-0 whitespace-nowrap"
            >
              {{ t('7×24 快讯 →', 'Wire →') }}
            </button>
          </div>
          <a
            v-if="normalizeExternalUrl(bh.url)"
            :href="normalizeExternalUrl(bh.url)!"
            target="_blank"
            rel="noopener noreferrer"
            @click.stop
            class="block text-[16px] sm:text-[17px] font-bold text-zinc-950 dark:text-white leading-[1.35] hover:text-[#007AFF] dark:hover:text-[#0A84FF] transition-colors"
          >
            {{ bh.title }}
          </a>
          <h3 v-else class="text-[16px] sm:text-[17px] font-bold text-zinc-950 dark:text-white leading-[1.35]">
            {{ bh.title }}
          </h3>
          <p v-if="bh.excerpt && bh.excerpt !== bh.title" class="text-[13px] text-zinc-600 dark:text-zinc-300 line-clamp-2 leading-[1.45]">
            {{ bh.excerpt }}
          </p>
          <div v-if="(bh.related_titles?.length || 0) > 0" class="flex flex-wrap gap-1.5 pt-0.5">
            <span
              v-for="(rt, ridx) in bh.related_titles?.slice(0, 3)"
              :key="ridx"
              class="inline-flex items-center px-2 py-0.5 rounded-lg bg-rose-500/[0.08] text-rose-800 dark:text-rose-200 text-[11px] max-w-full truncate"
            >
              + {{ rt }}
            </span>
          </div>
        </div>
      </div>

      <EventCard
        v-if="interwovenFeedRows[0]"
        :key="`lead-${interwovenFeedRows[0].item.event.event_id}`"
        :event="interwovenFeedRows[0].item.event"
        :now-ms="nowMs"
        :featured="true"
        :controlled-expanded="expandedEventIds.has(interwovenFeedRows[0].item.event.event_id)"
        @set-expanded="setExpandedEvent(interwovenFeedRows[0].item.event.event_id, $event)"
        :is-read="isEventRead(interwovenFeedRows[0].item.event, readIds, legacyReadTitles)"
        :is-bookmarked="bookmarkedIds.has(interwovenFeedRows[0].item.event.event_id)"
        :is-new-since-visit="previousBatchId ? !previousSeenIds.has(interwovenFeedRows[0].item.event.event_id) : interwovenFeedRows[0].item.event.is_new_in_batch"
        :market-impact="eventImpactMap?.[interwovenFeedRows[0].item.event.event_id] || null"
        :thumbnail-url="interwovenFeedRows[0].item.event.thumbnail_url || null"
        :saved-note="savedNoteMap?.[interwovenFeedRows[0].item.event.event_id] || ''"
        :matching-note-count="matchingNotesForEvent(interwovenFeedRows[0].item.event)"
        :perspectives="commentsMap?.[interwovenFeedRows[0].item.event.category] || []"
        :is-read-later="interwovenFeedRows[0].item.isReadLater"
        :downweighted="interwovenFeedRows[0].item.downweighted"
        :cross-domain-badge="interwovenFeedRows[0].crossDomainBadge || null"
        :cross-domain-hint="interwovenFeedRows[0].crossDomainHint || null"
        :show-moderation-actions="true"
        @toggle-read="emit('toggle-read', $event)"
        @mark-read="emit('mark-read', $event)"
        @open-notes="emit('open-notes')"
        @toggle-bookmark="emit('toggle-bookmark', $event)"
        @copy-link="emit('copy-link', $event)"
        @select-entity="emit('select-entity', $event)"
        @open-storyline="emit('open-storyline', $event)"
        @open-qa="emit('open-qa', $event)"
        @open-detail="emit('open-detail', $event)"
        @save-note="emit('save-note', $event)"
        @toggle-read-later="emit('toggle-read-later', $event)"
        @toggle-downweight="emit('toggle-downweight-event', $event)"
        @toggle-mute="emit('toggle-mute-event', $event)"
      />

      <div
        v-if="interwovenFeedRows.length > 1"
        class="ios-card divide-y divide-black/[0.06] dark:divide-white/[0.08] overflow-hidden"
      >
        <EventCard
          v-for="row in interwovenFeedRows.slice(1)"
          :key="`${row.crossDomainBadge ? 'bs-' : ''}${row.item.event.event_id}`"
          :event="row.item.event"
          :now-ms="nowMs"
          :grouped="true"
          :controlled-expanded="expandedEventIds.has(row.item.event.event_id)"
          @set-expanded="setExpandedEvent(row.item.event.event_id, $event)"
          :is-read="isEventRead(row.item.event, readIds, legacyReadTitles)"
          :is-bookmarked="bookmarkedIds.has(row.item.event.event_id)"
          :is-new-since-visit="previousBatchId ? !previousSeenIds.has(row.item.event.event_id) : row.item.event.is_new_in_batch"
          :market-impact="eventImpactMap?.[row.item.event.event_id] || null"
          :thumbnail-url="row.item.event.thumbnail_url || null"
          :saved-note="savedNoteMap?.[row.item.event.event_id] || ''"
          :matching-note-count="matchingNotesForEvent(row.item.event)"
          :perspectives="commentsMap?.[row.item.event.category] || []"
          :is-read-later="row.item.isReadLater"
          :downweighted="row.item.downweighted"
          :cross-domain-badge="row.crossDomainBadge || null"
          :cross-domain-hint="row.crossDomainHint || null"
          :show-moderation-actions="true"
          @toggle-read="emit('toggle-read', $event)"
          @mark-read="emit('mark-read', $event)"
          @open-notes="emit('open-notes')"
          @toggle-bookmark="emit('toggle-bookmark', $event)"
          @copy-link="emit('copy-link', $event)"
          @select-entity="emit('select-entity', $event)"
          @open-storyline="emit('open-storyline', $event)"
          @open-qa="emit('open-qa', $event)"
          @open-detail="emit('open-detail', $event)"
          @save-note="emit('save-note', $event)"
          @toggle-read-later="emit('toggle-read-later', $event)"
          @toggle-downweight="emit('toggle-downweight-event', $event)"
          @toggle-mute="emit('toggle-mute-event', $event)"
        />
      </div>

      <div v-if="pagedMatched.hasMore" class="pt-1 text-center">
        <button
          type="button"
          @click="visibleLimit += DEFAULT_PAGE_SIZE"
          class="min-h-[44px] px-5 rounded-xl bg-white dark:bg-[#1C1C1E] shadow-[0_1px_2px_rgba(0,0,0,0.04)] text-xs font-semibold text-zinc-700 dark:text-zinc-200"
        >
          {{ t(`加载更多 (${pagedMatched.remaining})`, `Load More (${pagedMatched.remaining})`) }}
        </button>
      </div>
    </div>

    <!-- More Global Stories (Collapsed by Default on Feed) -->
    <div v-if="todaySection === 'feed' && sortedFallbackList.length > 0 && sortedMatchedList.length > 0" class="pt-1">
      <button
        type="button"
        @click="showAllNonMatched = !showAllNonMatched"
        class="w-full min-h-[44px] px-4 rounded-2xl bg-white dark:bg-[#1C1C1E] shadow-[0_1px_2px_rgba(0,0,0,0.04)] text-xs font-semibold text-zinc-700 dark:text-zinc-200 flex items-center justify-between"
      >
        <span class="inline-flex items-center gap-1.5">
          <GitBranch class="w-3.5 h-3.5 text-zinc-400" :stroke-width="1.5" />
          <span>{{ t(`更多全市场要闻 (${sortedFallbackList.length})`, `More Global Stories (${sortedFallbackList.length})`) }}</span>
        </span>
        <ChevronDown class="w-4 h-4 text-zinc-400 transition-transform" :class="{ 'rotate-180': showAllNonMatched }" />
      </button>

      <div v-if="showAllNonMatched || Boolean(props.searchQuery?.trim())" class="mt-2 ios-card divide-y divide-black/[0.06] dark:divide-white/[0.08] overflow-hidden">
        <EventCard
          v-for="item in pagedFallback.visible"
          :key="item.event.event_id"
          :event="item.event"
          :now-ms="nowMs"
          :grouped="true"
          :controlled-expanded="expandedEventIds.has(item.event.event_id)"
          @set-expanded="setExpandedEvent(item.event.event_id, $event)"
          :is-read="isEventRead(item.event, readIds, legacyReadTitles)"
          :is-bookmarked="bookmarkedIds.has(item.event.event_id)"
          :is-new-since-visit="previousBatchId ? !previousSeenIds.has(item.event.event_id) : item.event.is_new_in_batch"
          :market-impact="eventImpactMap?.[item.event.event_id] || null"
          :thumbnail-url="item.event.thumbnail_url || null"
          :saved-note="savedNoteMap?.[item.event.event_id] || ''"
          :perspectives="commentsMap?.[item.event.category] || []"
          :is-read-later="readLaterSet.has(item.event.event_id)"
          :show-moderation-actions="true"
          @toggle-read="emit('toggle-read', $event)"
          @toggle-bookmark="emit('toggle-bookmark', $event)"
          @copy-link="emit('copy-link', $event)"
          @select-entity="emit('select-entity', $event)"
          @open-storyline="emit('open-storyline', $event)"
          @open-qa="emit('open-qa', $event)"
          @open-detail="emit('open-detail', $event)"
          @save-note="emit('save-note', $event)"
          @toggle-read-later="emit('toggle-read-later', $event)"
          @toggle-downweight="emit('toggle-downweight-event', $event)"
          @toggle-mute="emit('toggle-mute-event', $event)"
        />
      </div>
    </div>

    <!-- Collapsible Quarantine Bucket for Zero-Source Leads -->
    <details
      v-if="todaySection === 'feed' && unverifiedTodayEvents.length > 0"
      class="ios-card px-3.5 py-2.5"
    >
      <summary class="cursor-pointer select-none min-h-[36px] flex items-center justify-between text-xs font-semibold text-amber-700 dark:text-amber-300 list-none">
        <span>{{ t(`待核实线索 (${unverifiedTodayEvents.length})`, `Pending Verification (${unverifiedTodayEvents.length})`) }}</span>
        <ChevronDown class="w-4 h-4" />
      </summary>
      <div class="mt-2.5 divide-y divide-black/[0.06] dark:divide-white/[0.08] overflow-hidden rounded-xl">
        <EventCard
          v-for="uEv in unverifiedTodayEvents"
          :key="`unv-today-${uEv.event_id}`"
          :event="uEv"
          :now-ms="nowMs"
          :grouped="true"
          :is-read="isEventRead(uEv, readIds, legacyReadTitles)"
          :is-bookmarked="bookmarkedIds.has(uEv.event_id)"
          :is-new-since-visit="previousBatchId ? !previousSeenIds.has(uEv.event_id) : uEv.is_new_in_batch"
          :market-impact="eventImpactMap?.[uEv.event_id] || null"
          :thumbnail-url="uEv.thumbnail_url || null"
          :saved-note="savedNoteMap?.[uEv.event_id] || ''"
          :perspectives="commentsMap?.[uEv.category] || []"
          @toggle-read="emit('toggle-read', $event)"
          @toggle-bookmark="emit('toggle-bookmark', $event)"
          @copy-link="emit('copy-link', $event)"
          @select-entity="emit('select-entity', $event)"
          @open-storyline="emit('open-storyline', $event)"
          @open-qa="emit('open-qa', $event)"
          @open-detail="emit('open-detail', $event)"
          @save-note="emit('save-note', $event)"
        />
      </div>
    </details>

    <!-- iOS Bottom Sheet Drawer: Watchlist + Freshness + Sort + Dedupe + Presets -->
    <Teleport to="body">
      <div
        v-if="filterDrawerOpen"
        class="ios-sheet-backdrop p-0 sm:p-4"
        role="dialog"
        aria-modal="true"
        @click.self="filterDrawerOpen = false"
      >
        <div class="ios-sheet-panel max-h-[85vh] flex flex-col">
          <!-- Sheet Drag Handle + Header -->
          <div class="px-4 pt-2.5 pb-3 bg-white dark:bg-zinc-900 border-b border-black/[0.06] dark:border-white/[0.08]">
            <div class="w-9 h-1 rounded-full bg-zinc-300 dark:bg-zinc-700 mx-auto mb-2 sm:hidden" />
            <div class="flex items-center justify-between">
              <h3 class="text-sm font-bold text-zinc-950 dark:text-white">
                {{ t('筛选与关注管理', 'Filters & Watchlist') }}
              </h3>
              <button
                type="button"
                @click="filterDrawerOpen = false"
                class="w-11 h-11 -mr-2 inline-flex items-center justify-center rounded-xl text-zinc-400 hover:text-zinc-700 dark:hover:text-white"
                :aria-label="t('关闭', 'Close')"
              >
                <X class="w-5 h-5" />
              </button>
            </div>
          </div>

          <!-- Sheet Body -->
          <div class="flex-1 overflow-y-auto p-4 space-y-4 text-xs pb-[max(1rem,env(safe-area-inset-bottom))]">
            <!-- Freshness & View Mode -->
            <div class="space-y-2">
              <div class="font-semibold text-zinc-500 dark:text-zinc-400">{{ t('新鲜度与视图', 'Freshness & View') }}</div>
              <div class="flex flex-wrap gap-1.5">
                <button
                  type="button"
                  @click="onlyReadLater = false; emit('update:freshBucket', 'all')"
                  class="min-h-[40px] px-3 rounded-xl font-medium"
                  :class="!onlyReadLater && freshBucket === 'all' ? 'bg-blue-600 text-white' : 'bg-white dark:bg-zinc-900 text-zinc-700 dark:text-zinc-200'"
                >
                  {{ t('全部', 'All') }} ({{ bucketCounts.all }})
                </button>
                <button
                  type="button"
                  @click="onlyReadLater = false; emit('update:freshBucket', 'unread')"
                  class="min-h-[40px] px-3 rounded-xl font-medium"
                  :class="!onlyReadLater && freshBucket === 'unread' ? 'bg-blue-600 text-white' : 'bg-white dark:bg-zinc-900 text-zinc-700 dark:text-zinc-200'"
                >
                  {{ t('仅未读', 'Unread') }} ({{ bucketCounts.unread }})
                </button>
                <button
                  type="button"
                  @click="onlyReadLater = false; emit('update:freshBucket', 'first_discovery')"
                  class="min-h-[40px] px-3 rounded-xl font-medium"
                  :class="!onlyReadLater && freshBucket === 'first_discovery' ? 'bg-emerald-600 text-white' : 'bg-white dark:bg-zinc-900 text-zinc-700 dark:text-zinc-200'"
                >
                  {{ t('首次发现', 'New') }} ({{ bucketCounts.first_discovery }})
                </button>
                <button
                  type="button"
                  @click="onlyReadLater = false; emit('update:freshBucket', 'old_progress')"
                  class="min-h-[40px] px-3 rounded-xl font-medium"
                  :class="!onlyReadLater && freshBucket === 'old_progress' ? 'bg-violet-600 text-white' : 'bg-white dark:bg-zinc-900 text-zinc-700 dark:text-zinc-200'"
                >
                  {{ t('旧事新进展', 'Follow-ups') }} ({{ bucketCounts.old_progress }})
                </button>
                <button
                  type="button"
                  @click="onlyReadLater = !onlyReadLater; if (onlyReadLater) antiEchoMode = false"
                  class="jx-pop-target ios-tap inline-flex items-center gap-1 min-h-[40px] px-3 rounded-xl font-medium transition-all"
                  :class="onlyReadLater ? 'bg-amber-600 text-white jx-pop-active jx-burst-ring' : 'bg-white dark:bg-zinc-900 text-zinc-700 dark:text-zinc-200'"
                >
                  <Bookmark class="w-3.5 h-3.5" :class="{ 'fill-current': onlyReadLater }" />
                  <span>{{ t('稍后深读', 'Read Later') }} ({{ readLaterCount }})</span>
                </button>
                <button
                  type="button"
                  @click="antiEchoMode = !antiEchoMode; if (antiEchoMode) onlyReadLater = false"
                  class="inline-flex items-center gap-1 min-h-[40px] px-3 rounded-xl font-medium"
                  :class="antiEchoMode ? 'bg-indigo-600 text-white' : 'bg-white dark:bg-zinc-900 text-indigo-700 dark:text-indigo-300'"
                >
                  <Compass class="w-3.5 h-3.5" />
                  <span>{{ t('破茧全视野', 'Panorama') }}</span>
                </button>
              </div>
            </div>

            <!-- Sort, Density & Dedupe -->
            <div class="ios-card p-3 space-y-3">
              <div class="flex items-center justify-between gap-2">
                <span class="font-semibold text-zinc-700 dark:text-zinc-200">{{ t('排序方式', 'Sort') }}</span>
                <div class="relative inline-flex items-center shrink-0 h-9 pl-3 pr-7 rounded-xl bg-zinc-100 dark:bg-zinc-800 text-xs text-zinc-900 dark:text-white focus-within:ring-2 focus-within:ring-[#007AFF]/40">
                  <span class="pointer-events-none whitespace-nowrap">
                    {{
                      sortBy === 'relevance'
                        ? t('关注相关', 'Relevance')
                        : sortBy === 'latest'
                          ? t('最新时间', 'Latest')
                          : t('可信度最高', 'Credibility')
                    }}
                  </span>
                  <ChevronDown class="w-3.5 h-3.5 text-zinc-400 pointer-events-none absolute right-2" />
                  <select
                    v-model="sortBy"
                    :aria-label="t('列表排序方式', 'Sort feed')"
                    class="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                  >
                    <option value="relevance">{{ t('关注相关', 'Relevance') }}</option>
                    <option value="latest">{{ t('最新时间', 'Latest') }}</option>
                    <option value="credibility">{{ t('可信度最高', 'Credibility') }}</option>
                  </select>
                </div>
              </div>
              <div class="flex items-center justify-between gap-2">
                <span class="font-semibold text-zinc-700 dark:text-zinc-200">{{ t('卡片密度', 'Density') }}</span>
                <div class="ios-segmented">
                  <button
                    type="button"
                    @click="setFeedDensity('compact')"
                    class="ios-segmented-btn min-h-[30px] px-3"
                    :class="feedDensity === 'compact' ? 'ios-segmented-btn-active' : 'text-zinc-500 dark:text-zinc-400'"
                  >
                    {{ t('紧凑', 'Compact') }}
                  </button>
                  <button
                    type="button"
                    @click="setFeedDensity('standard')"
                    class="ios-segmented-btn min-h-[30px] px-3"
                    :class="feedDensity === 'standard' ? 'ios-segmented-btn-active' : 'text-zinc-500 dark:text-zinc-400'"
                  >
                    {{ t('标准', 'Standard') }}
                  </button>
                </div>
              </div>
              <label class="flex items-center justify-between min-h-[40px] cursor-pointer text-zinc-700 dark:text-zinc-200">
                <span class="inline-flex items-center gap-1.5">
                  <Filter class="w-3.5 h-3.5 text-zinc-400" />
                  <span>{{ t('合并相似报道', 'Merge similar reports') }}</span>
                </span>
                <input
                  type="checkbox"
                  :checked="hideReprints"
                  @change="emit('toggle-hide-reprints', ($event.target as HTMLInputElement).checked)"
                  class="w-4 h-4 rounded border-zinc-300 text-blue-600"
                />
              </label>
              <label class="flex items-center justify-between min-h-[40px] cursor-pointer text-zinc-700 dark:text-zinc-200">
                <span>{{ t('仅看一手官方披露', 'First-party disclosures only') }}</span>
                <input
                  type="checkbox"
                  :checked="alertRules.firstPartyOnly"
                  @change="updateRule('firstPartyOnly', ($event.target as HTMLInputElement).checked)"
                  class="w-4 h-4 rounded border-zinc-300 text-blue-600"
                />
              </label>
            </div>

            <!-- Watchlist Management + Starter Packs -->
            <div class="ios-card p-3 space-y-3">
              <div class="flex items-center justify-between">
                <span class="font-semibold text-zinc-900 dark:text-white">
                  {{ t(`我的关注 (${watchlist.length})`, `Watchlist (${watchlist.length})`) }}
                </span>
                <span v-if="quietActive" class="text-[11px] text-zinc-400">
                  {{ t('免打扰中', 'Quiet') }} {{ alertRules.quietHoursStart }}-{{ alertRules.quietHoursEnd }}
                </span>
              </div>

              <!-- Quick Starter Packs -->
              <div class="flex flex-wrap gap-1.5">
                <button
                  v-for="preset in WATCHLIST_PRESETS"
                  :key="preset.id"
                  type="button"
                  @click="emit('apply-preset', preset)"
                  class="min-h-[36px] px-2.5 rounded-xl bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 font-medium"
                >
                  {{ preset.badge }} {{ appLang === 'en' ? preset.labelEn : preset.label }}
                </button>
              </div>

              <!-- Active Chips -->
              <div class="flex flex-wrap gap-1.5">
                <span
                  v-for="w in watchlist"
                  :key="w.id"
                  class="inline-flex items-center gap-1 pl-2.5 pr-1 min-h-[36px] rounded-xl bg-zinc-100 dark:bg-zinc-800 text-zinc-800 dark:text-zinc-200"
                >
                  <span class="text-[10px] text-blue-600 dark:text-blue-400 font-semibold">{{ KIND_LABELS[w.kind] }}</span>
                  <button
                    type="button"
                    @click="w.entity_id ? (filterDrawerOpen = false, emit('select-entity', w.label)) : null"
                    class="font-medium"
                  >
                    {{ w.label }}
                  </button>
                  <button
                    type="button"
                    @click="emit('remove-watchlist', w.id)"
                    class="w-8 h-8 inline-flex items-center justify-center rounded-lg text-zinc-400 hover:text-rose-500"
                    :aria-label="t(`取消关注 ${w.label}`, `Unfollow ${w.label}`)"
                  >
                    <Trash2 class="w-3.5 h-3.5" />
                  </button>
                </span>
              </div>

              <!-- Add Watchlist Form -->
              <form @submit.prevent="handleAddWatchlist" class="grid grid-cols-2 gap-2 pt-1">
                <div class="relative inline-flex items-center w-full h-10 pl-3 pr-7 rounded-xl bg-zinc-100 dark:bg-zinc-800 text-xs text-zinc-900 dark:text-white focus-within:ring-2 focus-within:ring-[#007AFF]/40">
                  <span class="pointer-events-none truncate">
                    {{
                      newKind === 'company'
                        ? t('公司', 'Company')
                        : newKind === 'ticker'
                          ? t('股票/代码', 'Ticker')
                          : newKind === 'industry'
                            ? t('行业', 'Industry')
                            : newKind === 'tech'
                              ? t('技术', 'Tech')
                              : t('事件', 'Event')
                    }}
                  </span>
                  <ChevronDown class="w-3.5 h-3.5 text-zinc-400 pointer-events-none absolute right-2" />
                  <select
                    v-model="newKind"
                    :aria-label="t('关注维度类型', 'Watchlist kind')"
                    class="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                  >
                    <option value="company">{{ t('公司', 'Company') }}</option>
                    <option value="ticker">{{ t('股票/代码', 'Ticker') }}</option>
                    <option value="industry">{{ t('行业', 'Industry') }}</option>
                    <option value="tech">{{ t('技术', 'Tech') }}</option>
                    <option value="event">{{ t('事件', 'Event') }}</option>
                  </select>
                </div>
                <input
                  v-model="newLabel"
                  type="text"
                  :placeholder="t('名称，如 NVDA / 台积电', 'Name, e.g. NVDA')"
                  class="h-10 px-3 rounded-xl border border-black/[0.08] dark:border-white/[0.1] bg-zinc-50 dark:bg-zinc-800 text-xs"
                />
                <input
                  v-model="newKeywords"
                  type="text"
                  :placeholder="t('同义词（选填）', 'Aliases (optional)')"
                  class="h-10 px-3 rounded-xl border border-black/[0.08] dark:border-white/[0.1] bg-zinc-50 dark:bg-zinc-800 text-xs"
                />
                <button
                  type="submit"
                  class="h-10 rounded-xl bg-blue-600 text-white font-semibold inline-flex items-center justify-center gap-1"
                >
                  <Plus class="w-3.5 h-3.5" />
                  <span>{{ t('加入关注', 'Follow') }}</span>
                </button>
              </form>
            </div>

            <!-- Muted Items Recovery -->
            <div v-if="mutedItemsDetail.length > 0" class="ios-card p-3 space-y-2">
              <div class="flex items-center justify-between">
                <span class="font-semibold text-amber-700 dark:text-amber-300">
                  {{ t(`已屏蔽 (${mutedItemsDetail.length})`, `Muted (${mutedItemsDetail.length})`) }}
                </span>
                <button
                  type="button"
                  @click="emit('unmute-all')"
                  class="inline-flex items-center gap-1 text-blue-600 dark:text-blue-400 font-semibold"
                >
                  <RotateCcw class="w-3 h-3" />
                  <span>{{ t('全部恢复', 'Unmute All') }}</span>
                </button>
              </div>
              <ul class="space-y-1">
                <li
                  v-for="m in mutedItemsDetail"
                  :key="m.key"
                  class="flex items-center justify-between gap-2 py-1"
                >
                  <span class="truncate text-zinc-600 dark:text-zinc-300">{{ m.label }}</span>
                  <button
                    type="button"
                    @click="emit('toggle-mute-event', m.key)"
                    class="shrink-0 text-blue-600 dark:text-blue-400 font-medium"
                  >
                    {{ t('恢复', 'Restore') }}
                  </button>
                </li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </section>
</template>
