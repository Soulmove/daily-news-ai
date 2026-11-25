import type {
  AlertRuleSettings,
  BreakingHighlightItem,
  CatalystEvent,
  EventMarketImpact,
  PortfolioConfig,
  PredictionRecord,
  ResearchNote,
  SmartEvent,
  StorylineDossier,
  WatchlistItem,
} from './types'
import { isEventRead } from './storage'
import { pickBiText, t, translateMarketTag } from './i18n'
import { parseTimestampMs } from './time'
import type { FreshnessBucket } from './urlState'

export interface WatchlistMatchResult {
  matched: boolean
  score: number
  matchReasons: string[]
  muted: boolean
  downweighted: boolean
}

export function matchesWatchKeyword(hay: string, rawKw: string): boolean {
  const kw = rawKw.trim().toLowerCase()
  if (!kw) return false
  if (kw === '美元') {
    return /(?:美元指数|美元汇率|强美元|弱美元|美元兑|美元贬值|美元走强)/.test(hay)
  }
  if (/^[a-z0-9.\-_\s]+$/.test(kw) && kw.length <= 14) {
    const escaped = kw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\s+/g, '\\s+')
    return new RegExp(`(?:^|[^a-z0-9])${escaped}(?:$|[^a-z0-9])`, 'i').test(hay)
  }
  if (kw === '黄金') {
    if (/(?:黄金时段|黄金周|黄金期)/.test(hay) && !/(?:现货黄金|国际金价|金价|黄金etf|黄金期货|贵金属)/.test(hay)) {
      return false
    }
    return /(?:现货黄金|国际金价|金价|黄金etf|黄金期货|黄金暴跌|黄金大跌|买金|贵金属)/.test(hay)
  }
  if (kw === '特朗普' || kw === '川普') {
    return /(?:特朗普|川普)/.test(hay) && !/(?:霍尔木兹|克里米亚|油轮触雷|缅甸)/.test(hay)
  }
  return hay.includes(kw)
}

export function matchEventAgainstWatchlist(
  ev: SmartEvent,
  watchlist: WatchlistItem[],
  mutedSet: Set<string> = new Set(),
  downweightedSet: Set<string> = new Set(),
  nowMs: number = Date.now(),
): WatchlistMatchResult {
  const cleanTitleAndEntities = [
    ev.title,
    ev.title_en || '',
    ...ev.entities,
    (ev.fact_summary || '').slice(0, 140),
  ]
    .join(' ')
    .toLowerCase()

  const confidentEntityIds = new Set(
    (ev.entity_ids ?? []).filter((eid, idx) => {
      if (!ev.entity_confidences) return true
      const name = (ev.entities ?? [])[idx]
      if (!name || !Object.prototype.hasOwnProperty.call(ev.entity_confidences, name)) return true
      return Number(ev.entity_confidences[name]) >= ENTITY_CONFIDENCE_THRESHOLD
    }),
  )
  const evEntityIds = new Set(ev.entity_ids ?? [])

  if (
    mutedSet.has(ev.event_id) ||
    (ev.storyline_id && mutedSet.has(ev.storyline_id)) ||
    Array.from(evEntityIds).some((eid) => mutedSet.has(eid))
  ) {
    return {
      matched: false,
      score: -100,
      matchReasons: [t('已屏蔽该主体/事件', 'Muted entity/event')],
      muted: true,
      downweighted: false,
    }
  }

  const primarySrcId = ev.sources?.[0]?.source_id
  const downweighted =
    downweightedSet.has(ev.event_id) ||
    (ev.storyline_id ? downweightedSet.has(ev.storyline_id) : false) ||
    (primarySrcId ? downweightedSet.has(`src:${primarySrcId}`) : false) ||
    Array.from(evEntityIds).some((eid) => downweightedSet.has(eid))

  const reasons: string[] = []
  let score = 0

  for (const w of watchlist) {
    if (w.muted) continue
    let hit = false
    let hitReason = ''
    if (w.entity_id && confidentEntityIds.has(w.entity_id)) {
      hit = true
      hitReason = t(`命中实体 ${w.label}`, `Matched entity: ${w.label}`)
    } else {
      const matchedKw = w.keywords.find((kw) => matchesWatchKeyword(cleanTitleAndEntities, kw))
      if (matchedKw) {
        hit = true
        hitReason = t(`命中关注词 "${matchedKw}" (${w.label})`, `Matched "${matchedKw}" (${w.label})`)
      }
    }
    if (hit) {
      reasons.push(hitReason)
      score += 30
    }
  }

  if (typeof ev.radar_score === 'number' && !Number.isNaN(ev.radar_score)) {
    score += Math.round(ev.radar_score * 0.45)
  }

  if (ev.severity_tier === 'S') score += 20
  else if (ev.severity_tier === 'A') score += 8
  if (ev.evidence_status === 'official_confirmed') score += 16
  if (ev.update_kind === 'new_discovery') score += 12
  else if (ev.update_kind === 'new_fact_update') score += 10
  if (ev.importance === 'high') score += 10
  score += Math.min(18, (ev.independent_publisher_count ?? ev.platform_count ?? 1) * 6)
  if (ev.material_depth === 'body_lead_extracted' || ev.material_depth === 'first_party_and_body') {
    score += 8
  } else if (ev.material_depth === 'title_only') {
    score -= 8
  }

  // Freshness boost vs stale decay so breaking morning news outranks multi-day old filings/rumors
  const tsIso = ev.latest_reported_at || ev.first_reported_at || ev.published_at || ev.fetched_at
  if (tsIso) {
    const parsed = Date.parse(tsIso)
    if (!Number.isNaN(parsed)) {
      const ageHours = (nowMs - parsed) / 3_600_000
      if (ageHours <= 6) score += 26
      else if (ageHours <= 12) score += 18
      else if (ageHours <= 18) score += 10
      else if (ageHours <= 24) score += 4
      else if (ageHours <= 36) score -= 6
      else if (ageHours <= 48) score -= 12
      else if (ageHours <= 168) score -= 18
      else score -= 24
    }
  }

  if (ev.is_stale_rehash) score -= 20
  if (ev.attribution_warning) score -= 10
  if (downweighted) score -= 45

  return {
    matched: reasons.length > 0,
    score,
    matchReasons: reasons,
    muted: false,
    downweighted,
  }
}

/**
 * Strictly separates "Unread", "First Discovery", and "Old Story With New Progress"
 * so users never see old stories mislabeled as brand new events.
 */
export function matchesFreshnessBucket(
  ev: SmartEvent,
  bucket: FreshnessBucket,
  readIds: Set<string>,
  legacyReadTitles: Set<string>,
): boolean {
  if (bucket === 'all') return true
  if (bucket === 'unread') {
    return !isEventRead(ev, readIds, legacyReadTitles)
  }
  if (bucket === 'first_discovery') {
    return ev.update_kind === 'new_discovery' || (!ev.update_kind && ev.is_new_in_batch)
  }
  return (
    ev.update_kind === 'new_fact_update' ||
    ev.update_kind === 'continuing_coverage' ||
    Boolean(ev.followup?.is_continuing)
  )
}

export function passesAlertRule(ev: SmartEvent, rules: AlertRuleSettings): boolean {
  if (rules.firstPartyOnly && ev.evidence_status !== 'official_confirmed') {
    return false
  }
  const indep = ev.independent_publisher_count ?? ev.platform_count ?? ev.source_count
  if (indep < (rules.maxIndependentThreshold || 1)) {
    return false
  }
  return true
}

export function isInsideQuietHours(rules: AlertRuleSettings, nowDate = new Date()): boolean {
  if (!rules.quietHoursStart || !rules.quietHoursEnd) return false
  const [sh, sm] = rules.quietHoursStart.split(':').map(Number)
  const [eh, em] = rules.quietHoursEnd.split(':').map(Number)
  if ([sh, sm, eh, em].some((n) => Number.isNaN(n))) return false
  // Format local HH:MM in Asia/Shanghai when possible
  const shanghaiStr = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Shanghai',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(nowDate)
  const [ch, cm] = shanghaiStr.split(':').map(Number)
  const curMin = ch * 60 + cm
  const startMin = sh * 60 + sm
  const endMin = eh * 60 + em
  if (startMin === endMin) return false
  if (startMin < endMin) {
    return curMin >= startMin && curMin < endMin
  }
  // Overnight quiet window (e.g., 23:00 -> 07:00)
  return curMin >= startMin || curMin < endMin
}

export interface PredictionModeStats {
  total: number
  openCount: number
  correctCount: number
  incorrectCount: number
  indeterminateCount: number
  decisiveHitRatePct: number | null
  brierScore: number | null
}

export function computePredictionStats(records: PredictionRecord[]): {
  live: PredictionModeStats
  replay: PredictionModeStats
} {
  const calc = (subset: PredictionRecord[]): PredictionModeStats => {
    let openCount = 0
    let correctCount = 0
    let incorrectCount = 0
    let indeterminateCount = 0
    let brierSum = 0
    let brierN = 0

    for (const r of subset) {
      if (r.status === 'open' || !r.settlement) {
        openCount += 1
        continue
      }
      if (r.settlement.outcome === 'correct') {
        correctCount += 1
        const p = Math.min(1, Math.max(0, r.probability_pct / 100))
        brierSum += (p - 1) ** 2
        brierN += 1
      } else if (r.settlement.outcome === 'incorrect') {
        incorrectCount += 1
        const p = Math.min(1, Math.max(0, r.probability_pct / 100))
        brierSum += (p - 0) ** 2
        brierN += 1
      } else {
        indeterminateCount += 1
      }
    }

    const decided = correctCount + incorrectCount
    return {
      total: subset.length,
      openCount,
      correctCount,
      incorrectCount,
      indeterminateCount,
      decisiveHitRatePct: decided > 0 ? Math.round((correctCount / decided) * 1000) / 10 : null,
      brierScore: brierN > 0 ? Math.round((brierSum / brierN) * 1000) / 1000 : null,
    }
  }

  return {
    live: calc(records.filter((r) => r.mode === 'live')),
    replay: calc(records.filter((r) => r.mode === 'replay')),
  }
}

export function mergePredictions(
  seedRecords: PredictionRecord[],
  localRecords: PredictionRecord[],
): PredictionRecord[] {
  const byId = new Map<string, PredictionRecord>()
  for (const s of seedRecords) {
    byId.set(s.prediction_id, s)
  }
  // Local records (user-created or user-edited/settled versions of seeds) override by prediction_id
  for (const l of localRecords) {
    byId.set(l.prediction_id, l)
  }
  return Array.from(byId.values()).sort((a, b) => b.created_at.localeCompare(a.created_at))
}

/**
 * Single source of truth for Today workbench visible events after alert rules, mute filter,
 * and optional reprint/storyline deduplication so the header Tab pill and TodayView always agree.
 */
export function dedupeVisibleTodayEvents(
  allEvents: SmartEvent[],
  hideReprints: boolean,
  options?: {
    alertRules?: AlertRuleSettings
    mutedSet?: Set<string>
    watchlist?: WatchlistItem[]
    downweightedSet?: Set<string>
    nowMs?: number
  },
): SmartEvent[] {
  const seenStory = new Set<string>()
  const seenTitlePrefix = new Set<string>()
  const out: SmartEvent[] = []
  for (const ev of allEvents) {
    if (options?.alertRules && !passesAlertRule(ev, options.alertRules)) {
      continue
    }
    if (hideReprints) {
      const stKey = ev.storyline_id?.trim()
      const titleKey = ev.title
        .replace(/^(?:报道称|传闻称|消息称)[：:]\s*/, '')
        .replace(/[\s\p{P}]+/gu, '')
        .toLowerCase()
        .slice(0, 14)
      if (stKey && seenStory.has(stKey)) continue
      if (titleKey && seenTitlePrefix.has(titleKey)) continue
      if (stKey) seenStory.add(stKey)
      if (titleKey) seenTitlePrefix.add(titleKey)
    }
    if (options?.mutedSet && options.watchlist) {
      const res = matchEventAgainstWatchlist(
        ev,
        options.watchlist,
        options.mutedSet,
        options.downweightedSet ?? new Set(),
        options.nowMs,
      )
      if (res.muted) continue
    }
    out.push(ev)
  }
  return out
}

export type EventSortMode = 'latest' | 'credibility' | 'relevance'
export const DEFAULT_PAGE_SIZE = 20
export const ENTITY_CONFIDENCE_THRESHOLD = 0.65

export function getEventTimestampMs(
  ev: Pick<SmartEvent, 'latest_fact_update_at' | 'published_at' | 'latest_reported_at' | 'fetched_at'>,
): number {
  const iso = ev.latest_fact_update_at || ev.published_at || ev.latest_reported_at || ev.fetched_at
  if (!iso) return 0
  const ms = Date.parse(iso)
  return Number.isNaN(ms) ? 0 : ms
}

export function getEventCredibilityScore(ev: SmartEvent): number {
  const baseMap: Record<SmartEvent['evidence_status'], number> = {
    official_confirmed: 400,
    multi_source: 280,
    single_source: 160,
    needs_verification: 60,
  }
  let score = baseMap[ev.evidence_status] ?? 100
  const indep = ev.independent_publisher_count ?? ev.source_count ?? 1
  score += Math.min(8, Math.max(1, indep)) * 12
  const hasFirstParty = (ev.sources || []).some((s) => s.source_tier === 'first_party')
  if (hasFirstParty) score += 40
  if (ev.contradictions && ev.contradictions.length > 0) score -= 35
  return score
}

export function sortEvents(
  events: SmartEvent[],
  sortBy: EventSortMode,
  watchlist: WatchlistItem[] = [],
  mutedSet: Set<string> = new Set(),
  downweightedSet: Set<string> = new Set(),
  nowMs: number = Date.now(),
): SmartEvent[] {
  const copy = [...events]
  const cmpId = (a: SmartEvent, b: SmartEvent) => String(a.event_id || '').localeCompare(String(b.event_id || ''))
  if (sortBy === 'latest') {
    return copy.sort((a, b) => {
      const td = getEventTimestampMs(b) - getEventTimestampMs(a)
      return td !== 0 ? td : cmpId(a, b)
    })
  }
  if (sortBy === 'credibility') {
    return copy.sort((a, b) => {
      const diff = getEventCredibilityScore(b) - getEventCredibilityScore(a)
      if (diff !== 0) return diff
      const td = getEventTimestampMs(b) - getEventTimestampMs(a)
      return td !== 0 ? td : cmpId(a, b)
    })
  }
  return copy.sort((a, b) => {
    const sa = matchEventAgainstWatchlist(a, watchlist, mutedSet, downweightedSet, nowMs).score
    const sb = matchEventAgainstWatchlist(b, watchlist, mutedSet, downweightedSet, nowMs).score
    if (sb !== sa) return sb - sa
    const td = getEventTimestampMs(b) - getEventTimestampMs(a)
    return td !== 0 ? td : cmpId(a, b)
  })
}

export function sortStorylines(
  dossiers: StorylineDossier[],
  sortBy: EventSortMode,
  watchlist: WatchlistItem[] = [],
): StorylineDossier[] {
  const copy = [...dossiers]
  const ts = (d: StorylineDossier) =>
    Date.parse(d.latest_fact_update_at || d.latest_reported_at || d.first_reported_at || '') || 0
  const cred = (d: StorylineDossier) => {
    const map: Record<string, number> = {
      official_confirmed: 400,
      multi_source: 280,
      single_source: 160,
      needs_verification: 60,
    }
    return (map[d.evidence_status] ?? 100) + Math.min(8, (d.sources || []).length) * 10
  }
  const rel = (d: StorylineDossier) => {
    if (!watchlist.length) return 0
    const blob = `${d.title} ${(d.entities || []).join(' ')}`.toLowerCase()
    let hits = 0
    for (const w of watchlist) {
      if (blob.includes(w.label.toLowerCase()) || w.keywords.some((a) => a && blob.includes(a.toLowerCase()))) {
        hits += 10
      }
    }
    return hits
  }
  if (sortBy === 'credibility') {
    return copy.sort((a, b) => cred(b) - cred(a) || ts(b) - ts(a))
  }
  if (sortBy === 'relevance') {
    return copy.sort((a, b) => rel(b) - rel(a) || ts(b) - ts(a))
  }
  return copy.sort((a, b) => ts(b) - ts(a))
}

export function paginateItems<T>(
  items: T[],
  visibleLimit: number = DEFAULT_PAGE_SIZE,
): { visible: T[]; hasMore: boolean; remaining: number; total: number } {
  const total = items.length
  const safeLimit = Math.max(1, visibleLimit)
  const visible = items.slice(0, safeLimit)
  const remaining = Math.max(0, total - visible.length)
  return {
    visible,
    hasMore: remaining > 0,
    remaining,
    total,
  }
}

export function getConfidentEntities(
  entities: string[] = [],
  confidences?: Record<string, number>,
  threshold: number = ENTITY_CONFIDENCE_THRESHOLD,
): { name: string; confidence: number | null }[] {
  const out: { name: string; confidence: number | null }[] = []
  for (const name of entities) {
    if (!name) continue
    if (confidences && Object.prototype.hasOwnProperty.call(confidences, name)) {
      const conf = Number(confidences[name])
      if (!Number.isNaN(conf) && conf < threshold) continue
      out.push({ name, confidence: Number.isNaN(conf) ? null : conf })
    } else {
      out.push({ name, confidence: null })
    }
  }
  return out
}

export function getEventRecommendationReasons(
  ev: SmartEvent,
  watchlist: WatchlistItem[] = [],
  mutedSet: Set<string> = new Set(),
  downweightedSet: Set<string> = new Set(),
  lang: 'zh' | 'en' = 'zh',
): string[] {
  const reasons: string[] = []
  const match = matchEventAgainstWatchlist(ev, watchlist, mutedSet, downweightedSet)
  for (const r of match.matchReasons.slice(0, 2)) {
    reasons.push(lang === 'en' ? `Watchlist: ${r}` : `关注词命中：${r}`)
  }
  if (ev.evidence_status === 'official_confirmed') {
    reasons.push(lang === 'en' ? '1st-party confirmed' : '一手官方证实')
  } else if (ev.evidence_status === 'multi_source' && (ev.independent_publisher_count ?? ev.source_count ?? 1) >= 2) {
    reasons.push(
      lang === 'en'
        ? `${ev.independent_publisher_count ?? ev.source_count} independent sources`
        : `${ev.independent_publisher_count ?? ev.source_count} 家独立交叉`,
    )
  }
  if (ev.importance === 'high') {
    reasons.push(lang === 'en' ? 'High impact priority' : '高重要度主线')
  }
  if (ev.update_kind === 'new_fact_update') {
    reasons.push(lang === 'en' ? 'New substantive delta' : '存在实质新事实增量')
  }
  if (ev.regulatory_note) {
    reasons.push(ev.regulatory_note)
  } else if (ev.downweight_reasons && ev.downweight_reasons.length > 0) {
    reasons.push(ev.downweight_reasons[0])
  }
  if (reasons.length === 0) {
    const catZh: Record<string, string> = {
      finance: '财经与市场',
      global: '全球地缘',
      tech: 'AI 与科技',
      general: '综合热点',
    }
    const catEn: Record<string, string> = {
      finance: 'Finance & Markets',
      global: 'Global Affairs',
      tech: 'AI & Tech',
      general: 'General Digest',
    }
    reasons.push(lang === 'en' ? `Track: ${catEn[ev.category] || ev.category}` : `核心赛道：${catZh[ev.category] || ev.category}`)
  }
  return reasons.slice(0, 3)
}

/**
 * Dynamically rotates the #1 Hero Lead card on Today -> 精选 so already-read,
 * B-tier routine, or >24h stale events (without <6h fresh updates) step aside
 * for fresh <=24h authoritative S/A-tier multi-source stories.
 */
export function selectLeadEventIndex(
  events: SmartEvent[],
  readIds: Set<string>,
  legacyReadTitles: Set<string>,
  nowMs: number = Date.now(),
): number {
  if (events.length <= 1) return 0
  const first = events[0]
  const firstRead = isEventRead(first, readIds, legacyReadTitles)
  const firstPubIso = first.first_reported_at || first.published_at || first.fetched_at
  const firstPubMs = parseTimestampMs(firstPubIso)
  const firstUpdateMs = parseTimestampMs(first.latest_reported_at || first.latest_fact_update_at || firstPubIso)
  const firstAgeH = firstPubMs !== null ? (nowMs - firstPubMs) / 3_600_000 : 0
  const firstUpdateAgeH = firstUpdateMs !== null ? (nowMs - firstUpdateMs) / 3_600_000 : firstAgeH
  const firstIsStale = firstAgeH > 24 && firstUpdateAgeH > 6
  const firstIsWeak = first.severity_tier === 'B' || Boolean(first.is_stale_rehash)
  if (!firstRead && !firstIsStale && !firstIsWeak) return 0

  const windows = [12, 24, 36, 9999]
  for (const maxH of windows) {
    let bestIdx = -1
    let bestScore = -Infinity
    for (let i = 0; i < events.length; i += 1) {
      const ev = events[i]
      if (isEventRead(ev, readIds, legacyReadTitles)) continue
      const tsMs = parseTimestampMs(ev.latest_reported_at || ev.latest_fact_update_at || ev.first_reported_at || ev.published_at || ev.fetched_at)
      const ageH = tsMs !== null ? Math.max(0, (nowMs - tsMs) / 3_600_000) : 48
      if (ageH > maxH) continue
      const indep = ev.independent_publisher_count ?? ev.source_count ?? 1
      const tierBonus = ev.severity_tier === 'S' ? 35 : ev.severity_tier === 'A' ? 15 : 0
      const sc =
        tierBonus +
        indep * 15 +
        (ev.evidence_status === 'official_confirmed' ? 20 : 0) +
        (ev.importance === 'high' ? 12 : 0) +
        (ageH <= 6 ? 16 : ageH <= 12 ? 10 : ageH <= 24 ? 4 : 0) -
        (ev.is_stale_rehash ? 30 : 0)
      if (sc > bestScore) {
        bestScore = sc
        bestIdx = i
      }
    }
    if (bestIdx >= 0) return bestIdx
  }
  return 0
}

export function filterActiveBreakingHighlights(
  highlights: BreakingHighlightItem[],
  topEvents: SmartEvent[],
  nowMs: number = Date.now(),
): BreakingHighlightItem[] {
  if (!highlights.length) return []
  const topTitleTokens = topEvents.slice(0, 6).map((e) => (e.title || '').toLowerCase())
  return highlights
    .filter((bh) => {
      const ms = parseTimestampMs(bh.published_at)
      if (ms !== null && (nowMs - ms) / 3_600_000 > 12) return false
      const normBh = (bh.title || '').toLowerCase().replace(/[\s，,。：:【】\[\]()（）]/g, '')
      if (!normBh) return false
      // Suppress fast-track card once ai_analyst has promoted the same story into the top SmartEvent cards
      const isAlreadyInTop = topTitleTokens.some((t) => {
        const nt = t.replace(/[\s，,。：:【】\[\]()（）]/g, '')
        if (!nt) return false
        if (nt.includes(normBh.slice(0, 12)) || normBh.includes(nt.slice(0, 12))) return true
        return (bh.title.includes('保证金') && t.includes('保证金')) || (bh.title.includes('4000亿') && t.includes('4000亿'))
      })
      return !isAlreadyInTop
    })
    .slice(0, 3)
}

export interface PortfolioMatchResult {
  matched: boolean
  tags: string[]
  avgDelta: number
}

export function matchImpactAgainstPortfolio(
  item: EventMarketImpact,
  portfolio: PortfolioConfig,
): PortfolioMatchResult {
  if (item.validation_status === 'insufficient_evidence' || item.bars.length === 0) {
    return { matched: false, tags: [], avgDelta: 0 }
  }
  const tags: string[] = []
  const deltas: number[] = []
  const hay = `${item.event_title} ${item.one_liner} ${item.tag} ${item.bars.map((b) => `${b.market} ${b.sector}`).join(' ')}`.toLowerCase()

  const tickerWeights = item.affected_tickers || {}
  for (const rawTk of portfolio.tickers || []) {
    const tk = rawTk.trim().toUpperCase()
    if (!tk) continue
    const matchedEntry = Object.entries(tickerWeights).find(
      ([k]) => k.toUpperCase() === tk || k.toUpperCase().startsWith(`${tk}.`),
    )
    if (matchedEntry) {
      const [sym, weight] = matchedEntry
      tags.push(`${sym} (${weight >= 0 ? t('正相关', 'Positive Beta') : t('承压', 'Bearish Exposure')})`)
      const sameSignBar = item.bars.find((b) => {
        const m = (b.pct_low + b.pct_high) / 2
        return weight >= 0 ? m >= 0 : m <= 0
      })
      const baseMag = sameSignBar
        ? Math.abs((sameSignBar.pct_low + sameSignBar.pct_high) / 2)
        : Math.abs((item.bars[0].pct_low + item.bars[0].pct_high) / 2)
      deltas.push(weight * Math.max(1.0, baseMag))
      continue
    }
    if (hay.includes(tk.toLowerCase())) {
      tags.push(tk)
      const matchingBar = item.bars.find((b) => `${b.sector} ${b.logic}`.toLowerCase().includes(tk.toLowerCase()))
      if (matchingBar) {
        deltas.push((matchingBar.pct_low + matchingBar.pct_high) / 2)
      }
    }
  }

  const secTokens = (portfolio.sectors || [])
    .flatMap((s) => s.split(/[\s/]+/).map((k) => k.trim().toLowerCase()))
    .filter((k) => k.length >= 2)
  for (const b of item.bars) {
    const bLow = `${b.market} ${b.sector} ${b.logic}`.toLowerCase()
    if (secTokens.some((tok) => bLow.includes(tok))) {
      const mktTag = translateMarketTag(b.market)
      const secShort = pickBiText(b.sector, b.sector_en).split(' ')[0]
      const cleanTag = secShort.toLowerCase().startsWith(mktTag.toLowerCase()) ? secShort : `${mktTag}·${secShort}`
      tags.push(cleanTag)
      deltas.push((b.pct_low + b.pct_high) / 2)
    }
  }

  const uniqueTags = Array.from(new Set(tags)).slice(0, 3)
  if (uniqueTags.length === 0) return { matched: false, tags: [], avgDelta: 0 }
  const avg = deltas.length > 0 ? Math.round((deltas.reduce((a, b) => a + b, 0) / deltas.length) * 10) / 10 : 0
  return { matched: true, tags: uniqueTags, avgDelta: avg }
}

export function countUpcomingCatalystsWithinHours(
  events: CatalystEvent[],
  nowMs: number = Date.now(),
  hours: number = 48,
): CatalystEvent[] {
  const cutoff = nowMs - 2 * 3_600_000
  const maxMs = nowMs + hours * 3_600_000
  return events
    .filter((ev) => {
      if (!ev.scheduled_at || ev.is_past) return false
      const ms = parseTimestampMs(ev.scheduled_at)
      return ms !== null && ms >= cutoff && ms <= maxMs
    })
    .sort((a, b) => (a.scheduled_at || '').localeCompare(b.scheduled_at || ''))
}

export interface LiveLeaderboardRow {
  entity: string
  totalLive: number
  settledDecisive: number
  correct: number
  hitPct: number | null
  brier: number | null
}

export interface LiveLeaderboardSummary {
  liveSettledDecisive: number
  replaySettledDecisive: number
  unlocked: boolean
  rows: LiveLeaderboardRow[]
}

/**
 * Computes the public win-rate leaderboard STRICTLY from `mode === 'live'` records.
 * Historical `replay` samples MUST never unlock or inflate the public leaderboard.
 */
export function computeLiveDomainLeaderboard(
  predictions: PredictionRecord[],
  minSettledThreshold: number = 5,
): LiveLeaderboardSummary {
  const liveRecords = predictions.filter((r) => r.mode === 'live')
  const replayDecisive = predictions.filter(
    (r) =>
      r.mode === 'replay' &&
      r.status === 'settled' &&
      (r.settlement?.outcome === 'correct' || r.settlement?.outcome === 'incorrect'),
  ).length

  const isDecisiveLive = (r: PredictionRecord) =>
    r.status === 'settled' && (r.settlement?.outcome === 'correct' || r.settlement?.outcome === 'incorrect')

  const liveSettledDecisive = liveRecords.filter(isDecisiveLive).length
  const unlocked = liveSettledDecisive >= minSettledThreshold

  const groups = new Map<string, PredictionRecord[]>()
  for (const rec of liveRecords) {
    const raw = (rec.target_entity || '').trim()
    const key = /^(?:英伟达|nvidia)\b/i.test(raw) || /NVDA\.US/i.test(raw) ? '英伟达 (NVIDIA)' : raw || '宏观与综合'
    const arr = groups.get(key) || []
    arr.push(rec)
    groups.set(key, arr)
  }

  const rows: LiveLeaderboardRow[] = Array.from(groups.entries())
    .map(([entity, list]) => {
      const s = computePredictionStats(list)
      const decisive = list.filter(isDecisiveLive)
      const correct = decisive.filter((x) => x.settlement?.outcome === 'correct').length
      const hitPct = unlocked && decisive.length > 0 ? Math.round((correct / decisive.length) * 100) : null
      return {
        entity,
        totalLive: list.length,
        settledDecisive: decisive.length,
        correct,
        hitPct,
        brier: unlocked ? s.live.brierScore : null,
      }
    })
    .sort((a, b) => (b.hitPct ?? -1) - (a.hitPct ?? -1) || b.settledDecisive - a.settledDecisive || b.totalLive - a.totalLive)
    .slice(0, 6)

  return {
    liveSettledDecisive,
    replaySettledDecisive: replayDecisive,
    unlocked,
    rows,
  }
}

export type PredictionCategory = 'tech_ai' | 'market' | 'macro' | 'global_space'

export function inferPredictionCategory(rec: Pick<PredictionRecord, 'category' | 'target_entity_id' | 'target_entity' | 'title'>): PredictionCategory {
  const c = String(rec.category || '').trim()
  if (c === 'tech_ai' || c === 'market' || c === 'macro' || c === 'global_space') {
    return c
  }
  const blob = `${rec.title || ''} ${rec.target_entity_id || ''} ${rec.target_entity || ''}`.toLowerCase()
  if (/aerospace|神舟|cop31|气候|关税|特朗普|外交|航天|空间站|海外建/.test(blob)) {
    return 'global_space'
  }
  if (/fomc|macro|美联储|pmi|非农|pce|cpi|央行|经济工作会议|赤字率|降息|加息/.test(blob)) {
    return 'macro'
  }
  if (/gold|broker|opec|黄金|金价|a股|成交额|保证金|平准基金|收盘价|涨幅|市值|原油/.test(blob)) {
    return 'market'
  }
  return 'tech_ai'
}

export function countMatchingNotesForSubject(
  notes: ResearchNote[],
  subject: {
    eventId?: string | null
    storylineId?: string | null
    entityIds?: string[]
    entities?: string[]
    tickers?: string[]
  },
): number {
  if (!notes.length) return 0
  const subjEids = new Set((subject.entityIds || []).map((s) => s.toLowerCase()).filter(Boolean))
  const subjTickers = new Set((subject.tickers || []).map((s) => s.toUpperCase().replace(/\.[A-Z]+$/, '')).filter(Boolean))
  const subjNames = (subject.entities || []).map((s) => s.toLowerCase()).filter((s) => s.length >= 2)
  let hits = 0
  for (const n of notes) {
    if (subject.eventId && n.target_id === subject.eventId) {
      hits += 1
      continue
    }
    if (subject.storylineId && n.target_id === subject.storylineId) {
      hits += 1
      continue
    }
    if ((n.entity_ids || []).some((eid) => subjEids.has(eid.toLowerCase()))) {
      hits += 1
      continue
    }
    if (
      (n.tickers || []).some((tk) => subjTickers.has(tk.toUpperCase().replace(/\.[A-Z]+$/, '')))
    ) {
      hits += 1
      continue
    }
    const hay = `${n.title} ${n.answer_markdown}`.toLowerCase()
    if (
      subjNames.some((nm) => hay.includes(nm)) ||
      Array.from(subjTickers).some((tk) => tk.length >= 3 && hay.includes(tk.toLowerCase()))
    ) {
      hits += 1
    }
  }
  return hits
}

export interface MorningBriefSummary {
  portfolioHits: { id: string; eventId: string; title: string; polarity: string; tags: string[] }[]
  upcomingCatalysts: { id: string; title: string; scheduledAt: string | null }[]
}

export function buildMorningBriefSummary(
  impacts: EventMarketImpact[],
  portfolio: PortfolioConfig,
  watchlist: WatchlistItem[],
  calendarEvents: CatalystEvent[],
  nowMs: number = Date.now(),
): MorningBriefSummary {
  const portHits: MorningBriefSummary['portfolioHits'] = []
  const watchKws = watchlist
    .flatMap((w) => [w.label, ...(w.keywords || [])])
    .map((s) => s.trim().toLowerCase())
    .filter((s) => s.length >= 2)

  for (const imp of impacts) {
    if (imp.validation_status === 'insufficient_evidence') continue
    const pm = matchImpactAgainstPortfolio(imp, portfolio)
    const watchHit = watchKws.some((k) => `${imp.event_title} ${imp.one_liner}`.toLowerCase().includes(k))
    if (pm.matched || watchHit) {
      portHits.push({
        id: imp.id,
        eventId: imp.event_id,
        title: imp.event_title,
        polarity: imp.polarity,
        tags: pm.tags.length > 0 ? pm.tags : ['关注词命中'],
      })
    }
    if (portHits.length >= 2) break
  }

  const next48 = countUpcomingCatalystsWithinHours(calendarEvents, nowMs, 48).slice(0, 2)
  return {
    portfolioHits: portHits,
    upcomingCatalysts: next48.map((c) => ({
      id: c.calendar_id,
      title: c.title,
      scheduledAt: c.scheduled_at,
    })),
  }
}
