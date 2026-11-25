/**
 * B11 Daily Read Tracking + Echo-Chamber Diversity Analytics + Dismissible Sign-In Notice.
 * Resets daily read set automatically at midnight (00:00 Asia/Shanghai).
 */

import { formatShanghaiDateOnly } from './time'
import type { StorageLike } from './storage'
import type { CategoryKey, SmartEvent } from './types'

export interface DailyReadingState {
  date: string
  readEventIdsToday: string[]
}

const READING_PROGRESS_KEY = 'mirrorbrief_daily_reading_v1'
const LOGIN_BANNER_DISMISSED_KEY = 'mirrorbrief_login_banner_dismissed_v1'
const READING_HISTORY_KEY = 'mirrorbrief_reading_history_v1'

function resolveStorage(storage?: StorageLike): StorageLike | null {
  if (storage) return storage
  if (typeof window !== 'undefined' && window.localStorage) return window.localStorage
  return null
}

export function getTodayShanghaiDate(nowMs = Date.now()): string {
  return formatShanghaiDateOnly(new Date(nowMs).toISOString())
}

function normalizeIds(val: unknown): string[] {
  if (!Array.isArray(val)) return []
  return Array.from(new Set(val.filter((x): x is string => typeof x === 'string' && x.trim().length > 0)))
}

export function loadDailyReadingState(nowMs = Date.now(), storage?: StorageLike): DailyReadingState {
  const today = getTodayShanghaiDate(nowMs)
  const store = resolveStorage(storage)
  if (!store) {
    return { date: today, readEventIdsToday: [] }
  }
  try {
    const raw = store.getItem(READING_PROGRESS_KEY)
    if (!raw) return { date: today, readEventIdsToday: [] }
    const parsed = JSON.parse(raw) as Partial<DailyReadingState>
    if (parsed.date !== today) {
      const reset: DailyReadingState = { date: today, readEventIdsToday: [] }
      store.setItem(READING_PROGRESS_KEY, JSON.stringify(reset))
      return reset
    }
    return {
      date: today,
      readEventIdsToday: normalizeIds(parsed.readEventIdsToday),
    }
  } catch {
    return { date: today, readEventIdsToday: [] }
  }
}

export function saveDailyReadingState(state: DailyReadingState, storage?: StorageLike): void {
  const store = resolveStorage(storage)
  if (!store) return
  try {
    store.setItem(
      READING_PROGRESS_KEY,
      JSON.stringify({
        date: state.date,
        readEventIdsToday: normalizeIds(state.readEventIdsToday),
      }),
    )
  } catch {
    // ignore storage errors
  }
}

export function recordTodayReadEvents(
  state: DailyReadingState,
  eventIds: string[],
  isRead: boolean,
  nowMs = Date.now(),
  storage?: StorageLike,
): DailyReadingState {
  const base = state.date === getTodayShanghaiDate(nowMs) ? state : loadDailyReadingState(nowMs, storage)
  const nextSet = new Set(base.readEventIdsToday)
  for (const id of eventIds) {
    if (!id) continue
    if (isRead) nextSet.add(id)
    else nextSet.delete(id)
  }
  const next: DailyReadingState = {
    date: base.date,
    readEventIdsToday: Array.from(nextSet),
  }
  saveDailyReadingState(next, storage)
  return next
}

export function isLoginBannerDismissed(storage?: StorageLike): boolean {
  const store = resolveStorage(storage)
  if (!store) return false
  try {
    return store.getItem(LOGIN_BANNER_DISMISSED_KEY) === '1'
  } catch {
    return false
  }
}

export function dismissLoginBanner(storage?: StorageLike): void {
  const store = resolveStorage(storage)
  if (!store) return
  try {
    store.setItem(LOGIN_BANNER_DISMISSED_KEY, '1')
  } catch {
    // ignore
  }
}

export interface DailyHistoryBucket {
  date: string
  readCount: number
  readEventIds: string[]
  byCategory: Record<string, number>
  byEntity: Record<string, number>
}

export interface WeeklyReadingReport {
  totalReadCount: number
  activeDays: number
  streakDays: number
  dailyBreakdown: { date: string; readCount: number }[]
  categoryDistribution: { category: CategoryKey; count: number; pct: number }[]
}

export interface EchoChamberReport {
  diversityScore: number | null
  totalCategorizedReads: number
  dominantCategory: CategoryKey | null
  dominantPct: number
  blindspotCategories: CategoryKey[]
  topEntities: { name: string; count: number }[]
  status: 'balanced' | 'tilted' | 'echo_risk' | 'warming_up'
  statusLabel: string
  statusLabelEn: string
  recommendation: string
  recommendationEn: string
}

const TRACKED_CATEGORIES: CategoryKey[] = ['finance', 'global', 'tech', 'general']

function pruneHistoryKeys(
  map: Record<string, DailyHistoryBucket>,
  keepDays = 30,
  nowMs = Date.now(),
): Record<string, DailyHistoryBucket> {
  const cutoffMs = nowMs - keepDays * 86_400_000
  const cutoffDate = getTodayShanghaiDate(cutoffMs)
  const out: Record<string, DailyHistoryBucket> = {}
  for (const [k, v] of Object.entries(map)) {
    if (k >= cutoffDate && v && typeof v === 'object') {
      out[k] = v
    }
  }
  return out
}

export function loadReadingHistory(
  storage?: StorageLike,
  nowMs = Date.now(),
): Record<string, DailyHistoryBucket> {
  const store = resolveStorage(storage)
  if (!store) return {}
  try {
    const raw = store.getItem(READING_HISTORY_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw) as Record<string, DailyHistoryBucket>
    if (!parsed || typeof parsed !== 'object') return {}
    return pruneHistoryKeys(parsed, 30, nowMs)
  } catch {
    return {}
  }
}

function saveReadingHistory(
  history: Record<string, DailyHistoryBucket>,
  storage?: StorageLike,
  nowMs = Date.now(),
): void {
  const store = resolveStorage(storage)
  if (!store) return
  try {
    store.setItem(READING_HISTORY_KEY, JSON.stringify(pruneHistoryKeys(history, 30, nowMs)))
  } catch {
    // ignore storage quota errors
  }
}

function ensureBucket(history: Record<string, DailyHistoryBucket>, dateStr: string): DailyHistoryBucket {
  const existing = history[dateStr]
  if (existing) {
    return {
      date: dateStr,
      readCount: Number(existing.readCount) || 0,
      readEventIds: Array.isArray(existing.readEventIds) ? existing.readEventIds : [],
      byCategory: existing.byCategory && typeof existing.byCategory === 'object' ? { ...existing.byCategory } : {},
      byEntity: existing.byEntity && typeof existing.byEntity === 'object' ? { ...existing.byEntity } : {},
    }
  }
  return {
    date: dateStr,
    readCount: 0,
    readEventIds: [],
    byCategory: {},
    byEntity: {},
  }
}

export function recordEventReadInHistory(
  ev: Pick<SmartEvent, 'event_id' | 'category' | 'entities'>,
  nowMs = Date.now(),
  storage?: StorageLike,
): void {
  const today = getTodayShanghaiDate(nowMs)
  const history = loadReadingHistory(storage, nowMs)
  const bucket = ensureBucket(history, today)
  if (!bucket.readEventIds.includes(ev.event_id)) {
    bucket.readEventIds.push(ev.event_id)
    bucket.readCount = Math.max(bucket.readCount, bucket.readEventIds.length)
    const cat = TRACKED_CATEGORIES.includes(ev.category) ? ev.category : 'general'
    bucket.byCategory[cat] = (bucket.byCategory[cat] || 0) + 1
    for (const ent of (ev.entities || []).slice(0, 3)) {
      if (ent) bucket.byEntity[ent] = (bucket.byEntity[ent] || 0) + 1
    }
  }
  history[today] = bucket
  saveReadingHistory(history, storage, nowMs)
}

export function syncDailyStateToHistory(
  state: DailyReadingState,
  nowMs = Date.now(),
  storage?: StorageLike,
): void {
  const history = loadReadingHistory(storage, nowMs)
  const bucket = ensureBucket(history, state.date)
  bucket.readCount = Math.max(bucket.readCount, state.readEventIdsToday.length)
  for (const id of state.readEventIdsToday) {
    if (!bucket.readEventIds.includes(id)) bucket.readEventIds.push(id)
  }
  history[state.date] = bucket
  saveReadingHistory(history, storage, nowMs)
}

export function computeWeeklyReadingReport(nowMs = Date.now(), storage?: StorageLike): WeeklyReadingReport {
  const dailyState = loadDailyReadingState(nowMs, storage)
  const history = loadReadingHistory(storage, nowMs)
  const todayBucket = ensureBucket(history, dailyState.date)
  todayBucket.readCount = Math.max(todayBucket.readCount, dailyState.readEventIdsToday.length)
  history[dailyState.date] = todayBucket

  const dailyBreakdown: { date: string; readCount: number }[] = []
  const catTotals: Record<CategoryKey, number> = { finance: 0, global: 0, tech: 0, general: 0 }
  let totalReadCount = 0
  let activeDays = 0

  for (let offset = 6; offset >= 0; offset -= 1) {
    const dStr = getTodayShanghaiDate(nowMs - offset * 86_400_000)
    const b = history[dStr]
    const rc = b ? Number(b.readCount) || 0 : 0
    totalReadCount += rc
    if (rc > 0) activeDays += 1
    dailyBreakdown.push({
      date: dStr,
      readCount: rc,
    })
    if (b?.byCategory) {
      for (const cat of TRACKED_CATEGORIES) {
        catTotals[cat] += Number(b.byCategory[cat]) || 0
      }
    }
  }

  let streakDays = 0
  for (let offset = 0; offset < 30; offset += 1) {
    const dStr = getTodayShanghaiDate(nowMs - offset * 86_400_000)
    const b = history[dStr]
    if (b && b.readCount > 0) {
      streakDays += 1
    } else if (offset > 0) {
      break
    }
  }

  const totalCatReads = TRACKED_CATEGORIES.reduce((acc, c) => acc + catTotals[c], 0)
  const categoryDistribution = TRACKED_CATEGORIES.map((category) => ({
    category,
    count: catTotals[category],
    pct: totalCatReads > 0 ? Math.round((catTotals[category] / totalCatReads) * 100) : 0,
  }))

  return {
    totalReadCount,
    activeDays,
    streakDays,
    dailyBreakdown,
    categoryDistribution,
  }
}

export function computeEchoChamberReport(nowMs = Date.now(), storage?: StorageLike): EchoChamberReport {
  const history = loadReadingHistory(storage, nowMs)
  const catTotals: Record<CategoryKey, number> = { finance: 0, global: 0, tech: 0, general: 0 }
  const entityTotals = new Map<string, number>()

  for (let offset = 6; offset >= 0; offset -= 1) {
    const dStr = getTodayShanghaiDate(nowMs - offset * 86_400_000)
    const b = history[dStr]
    if (!b) continue
    for (const cat of TRACKED_CATEGORIES) {
      catTotals[cat] += Number(b.byCategory?.[cat]) || 0
    }
    for (const [ent, cnt] of Object.entries(b.byEntity || {})) {
      entityTotals.set(ent, (entityTotals.get(ent) || 0) + (Number(cnt) || 0))
    }
  }

  const totalCategorizedReads = TRACKED_CATEGORIES.reduce((acc, c) => acc + catTotals[c], 0)
  const topEntities = Array.from(entityTotals.entries())
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 5)

  const blindspotCategories = TRACKED_CATEGORIES.filter((c) => catTotals[c] === 0)

  if (totalCategorizedReads < 2) {
    return {
      diversityScore: null,
      totalCategorizedReads,
      dominantCategory: null,
      dominantPct: 0,
      blindspotCategories,
      topEntities,
      status: 'warming_up',
      statusLabel: '待评估',
      statusLabelEn: 'Not Yet Rated',
      recommendation: '已读满 2 条以上新闻后将自动生成跨领域视野评分。',
      recommendationEn: 'Read at least 2 categorized briefs to generate your domain diversity score.',
    }
  }

  let dominantCategory: CategoryKey = 'finance'
  let maxCount = -1
  for (const cat of TRACKED_CATEGORIES) {
    if (catTotals[cat] > maxCount) {
      maxCount = catTotals[cat]
      dominantCategory = cat
    }
  }
  const dominantPct = Math.round((maxCount / totalCategorizedReads) * 100)

  let entropy = 0
  for (const cat of TRACKED_CATEGORIES) {
    const p = catTotals[cat] / totalCategorizedReads
    if (p > 0) entropy -= p * Math.log(p)
  }
  const diversityScore = Math.round((entropy / Math.log(TRACKED_CATEGORIES.length)) * 100)

  let status: EchoChamberReport['status'] = 'balanced'
  let statusLabel = '视野均衡'
  let statusLabelEn = 'Well Balanced'
  let recommendation = '您的近 7 日阅读覆盖多个宏观与产业赛道，认知结构健康，请继续保持适度交叉验证。'
  let recommendationEn = 'Your 7-day reading spans multiple sectors cleanly, keeping blind spots low.'

  if (diversityScore < 35 || dominantPct >= 75) {
    status = 'echo_risk'
    statusLabel = '单一赛道偏重（茧房预警）'
    statusLabelEn = 'Narrow Focus Alert'
    recommendation = `近 7 日 ${dominantPct}% 阅读集中在同一领域，建议切到「破茧盲区视角」补充盲区维度。`
    recommendationEn = `${dominantPct}% of your reads came from one domain; explore blindspot tabs for macro balance.`
  } else if (diversityScore < 65) {
    status = 'tilted'
    statusLabel = '略偏主线，可适度拓宽'
    statusLabelEn = 'Moderately Focused'
    recommendation = '主线聚焦度较高，浏览其余赛道有助于捕捉跨界传导信号。'
    recommendationEn = 'Good focus on your primary theme; scanning uncovered tabs adds cross-sector context.'
  }

  return {
    diversityScore,
    totalCategorizedReads,
    dominantCategory,
    dominantPct,
    blindspotCategories,
    topEntities,
    status,
    statusLabel,
    statusLabelEn,
    recommendation,
    recommendationEn,
  }
}
