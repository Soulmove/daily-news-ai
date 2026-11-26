import { isValidAvatarValue } from './avatars'
import type {
  AiClientConfig,
  AlertRuleSettings,
  CatalystEvent,
  CategoryKey,
  PortfolioConfig,
  PredictionRecord,
  ResearchNote,
  SmartEvent,
  WatchlistItem,
} from './types'

export interface StorageLike {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
  removeItem?(key: string): void
}

const _MEMORY_FALLBACK_STORAGE = new Map<string, string>()

function getSafeStorage(customStorage?: StorageLike): StorageLike {
  if (customStorage) return customStorage
  try {
    if (typeof window !== 'undefined' && window.localStorage) {
      return window.localStorage
    }
  } catch {
    // Fallback to module-level memory in restricted environments
  }
  return {
    getItem: (k) => _MEMORY_FALLBACK_STORAGE.get(k) ?? null,
    setItem: (k, v) => {
      _MEMORY_FALLBACK_STORAGE.set(k, v)
    },
    removeItem: (k) => {
      _MEMORY_FALLBACK_STORAGE.delete(k)
    },
  }
}

function safeStorageGet(key: string, storage?: StorageLike): string | null {
  try {
    return getSafeStorage(storage).getItem(key)
  } catch {
    return null
  }
}

function safeStorageSet(key: string, value: string, storage?: StorageLike): void {
  try {
    getSafeStorage(storage).setItem(key, value)
  } catch {
    // ignore storage write failures
  }
}

export interface ReadLaterMetaEntry {
  event_id: string
  title: string
  url: string
  category: CategoryKey
  source_name: string
  saved_at: string
}

export interface BookmarkedEvent {
  event_id: string
  title: string
  url: string
  category: CategoryKey
  source_name: string
  batch_id: string
  saved_at: string
  tags?: string[]
  note?: string
}

export interface VisitBaseline {
  last_batch_id: string | null
  last_visited_at: string | null
  seen_event_ids: string[]
}

export interface CatalystOverrideEntry {
  actualResult: string
  deviation: string
  updatedAt?: string
  eventSnapshot?: CatalystEvent
}

const KEYS = {
  DARK_MODE: 'darkMode',
  LEGACY_READ_ITEMS: 'readItems',
  LEGACY_FAVORITE_SOURCES: 'favorites',
  V2_READ_EVENTS: 'insight_v2_read_events',
  V2_BOOKMARKS: 'insight_v2_bookmarks',
  V2_VISIT_BASELINE: 'insight_v2_visit_baseline',
  V3_WATCHLIST: 'insight_v3_watchlist',
  V3_MUTED: 'insight_v3_muted',
  V3_DOWNWEIGHTED: 'insight_v3_downweighted',
  V3_READ_LATER: 'insight_v3_read_later',
  V3_HIDE_REPRINTS: 'insight_v3_hide_reprints',
  V3_ALERT_RULES: 'insight_v3_alert_rules',
  V3_PREDICTIONS: 'insight_v3_predictions',
  V3_TOOL_STATES: 'insight_v3_tool_states',
  V3_NOTES: 'insight_v3_notes',
  V3_CUSTOM_CATALYSTS: 'insight_v3_custom_catalysts',
  V3_CATALYST_OVERRIDES: 'insight_v3_catalyst_overrides',
  V3_AI_CLIENT_CONFIG: 'insight_v3_ai_client_config',
  V3_PORTFOLIO: 'insight_v3_portfolio',
  V3_READ_LATER_META: 'insight_v3_read_later_meta',
  V3_PREDICTION_STANCES: 'insight_v3_prediction_stances',
  V3_USER_AVATAR: 'insight_v3_user_avatar',
  V3_WEEKLY_HABIT: 'mirrorbrief_weekly_habit_v1',
} as const

export const LOCAL_STORAGE_NOTICE =
  '已读、收藏、关注清单、预测记录与研究笔记：未登录时保存在当前浏览器本地，登录后自动加密同步至云端（支持 JSON 导出备份）。'

export function readDarkMode(storage?: StorageLike): boolean {
  const s = getSafeStorage(storage)
  try {
    return s.getItem(KEYS.DARK_MODE) === 'true'
  } catch {
    return false
  }
}

export function writeDarkMode(isDark: boolean, storage?: StorageLike): void {
  const s = getSafeStorage(storage)
  try {
    s.setItem(KEYS.DARK_MODE, isDark ? 'true' : 'false')
  } catch {
    // Ignore quota errors
  }
}

export function loadReadState(storage?: StorageLike): {
  readIds: Set<string>
  legacyReadTitles: Set<string>
} {
  const s = getSafeStorage(storage)
  const readIds = new Set<string>()
  const legacyReadTitles = new Set<string>()

  try {
    const rawV2 = s.getItem(KEYS.V2_READ_EVENTS)
    if (rawV2) {
      const parsed = JSON.parse(rawV2)
      if (Array.isArray(parsed)) {
        for (const entry of parsed) {
          if (typeof entry === 'string') {
            readIds.add(entry)
          } else if (entry && typeof entry === 'object' && typeof entry.id === 'string') {
            readIds.add(entry.id)
          }
        }
      }
    }
  } catch {
    // Ignore corrupted JSON
  }

  try {
    const rawV1 = s.getItem(KEYS.LEGACY_READ_ITEMS)
    if (rawV1) {
      const parsed = JSON.parse(rawV1)
      if (Array.isArray(parsed)) {
        for (const title of parsed) {
          if (typeof title === 'string' && title.trim()) {
            legacyReadTitles.add(title.trim())
          }
        }
      }
    }
  } catch {
    // Ignore corrupted JSON
  }

  return { readIds, legacyReadTitles }
}

export function isEventRead(
  event: Pick<SmartEvent, 'event_id' | 'title'>,
  readIds: Set<string>,
  legacyReadTitles: Set<string>,
): boolean {
  return readIds.has(event.event_id) || legacyReadTitles.has(event.title.trim())
}

export function saveReadState(
  readIds: Set<string>,
  legacyReadTitles: Set<string>,
  storage?: StorageLike,
): void {
  const s = getSafeStorage(storage)
  try {
    const boundedIds = Array.from(readIds).slice(-2000)
    s.setItem(KEYS.V2_READ_EVENTS, JSON.stringify(boundedIds))
    const boundedTitles = Array.from(legacyReadTitles).slice(-1000)
    s.setItem(KEYS.LEGACY_READ_ITEMS, JSON.stringify(boundedTitles))
  } catch {
    // Ignore storage errors
  }
}

export function loadBookmarkedEvents(storage?: StorageLike): BookmarkedEvent[] {
  const s = getSafeStorage(storage)
  try {
    const raw = s.getItem(KEYS.V2_BOOKMARKS)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter(
      (b): b is BookmarkedEvent =>
        Boolean(b && typeof b === 'object' && typeof b.event_id === 'string' && typeof b.title === 'string'),
    )
  } catch {
    return []
  }
}

export function saveBookmarkedEvents(
  bookmarks: BookmarkedEvent[],
  storage?: StorageLike,
): void {
  const s = getSafeStorage(storage)
  try {
    s.setItem(KEYS.V2_BOOKMARKS, JSON.stringify(bookmarks.slice(-500)))
  } catch {
    // Ignore
  }
}

export function loadFavoriteSourceIds(storage?: StorageLike): Set<string> {
  const s = getSafeStorage(storage)
  try {
    const raw = s.getItem(KEYS.LEGACY_FAVORITE_SOURCES)
    if (!raw) return new Set()
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return new Set()
    return new Set(parsed.filter((x): x is string => typeof x === 'string' && x.length > 0))
  } catch {
    return new Set()
  }
}

export function saveFavoriteSourceIds(
  sourceIds: Set<string>,
  storage?: StorageLike,
): void {
  const s = getSafeStorage(storage)
  try {
    s.setItem(KEYS.LEGACY_FAVORITE_SOURCES, JSON.stringify(Array.from(sourceIds)))
  } catch {
    // Ignore
  }
}

export function loadVisitBaseline(storage?: StorageLike): VisitBaseline {
  const s = getSafeStorage(storage)
  try {
    const raw = s.getItem(KEYS.V2_VISIT_BASELINE)
    if (!raw) {
      return { last_batch_id: null, last_visited_at: null, seen_event_ids: [] }
    }
    const parsed = JSON.parse(raw)
    return {
      last_batch_id: typeof parsed?.last_batch_id === 'string' ? parsed.last_batch_id : null,
      last_visited_at: typeof parsed?.last_visited_at === 'string' ? parsed.last_visited_at : null,
      seen_event_ids: Array.isArray(parsed?.seen_event_ids)
        ? parsed.seen_event_ids.filter((x: unknown): x is string => typeof x === 'string')
        : [],
    }
  } catch {
    return { last_batch_id: null, last_visited_at: null, seen_event_ids: [] }
  }
}

export function saveVisitBaseline(
  baseline: VisitBaseline,
  storage?: StorageLike,
): void {
  const s = getSafeStorage(storage)
  try {
    s.setItem(
      KEYS.V2_VISIT_BASELINE,
      JSON.stringify({
        last_batch_id: baseline.last_batch_id,
        last_visited_at: baseline.last_visited_at,
        seen_event_ids: baseline.seen_event_ids.slice(-1500),
      }),
    )
  } catch {
    // Ignore
  }
}

export function isNewSincePreviousVisit(
  event: Pick<SmartEvent, 'event_id' | 'is_new_in_batch'>,
  previousSeenIds: Set<string>,
  previousBatchId: string | null,
): boolean {
  if (!previousBatchId) {
    // First-ever visit on this browser: fall back to batch novelty flag
    return event.is_new_in_batch
  }
  return !previousSeenIds.has(event.event_id)
}

/**
 * Migrate any legacy colliding event IDs (e.g. V2 bug `evt_a9d2aca38270` shared by two different events
 * split from the same omnibus article) deterministically using exact title verification so marking Event A
 * never leaks to Event B.
 */
export function migrateCollidingEventStates(
  events: Pick<SmartEvent, 'event_id' | 'title' | 'legacy_event_ids'>[],
  readIds: Set<string>,
  bookmarks: BookmarkedEvent[],
  storage?: StorageLike,
): { readIds: Set<string>; bookmarks: BookmarkedEvent[]; migrated: boolean } {
  let migrated = false
  const nextRead = new Set(readIds)
  const nextBookmarks = bookmarks.map((b) => ({ ...b }))

  for (const ev of events) {
    const legList = ev.legacy_event_ids ?? []
    if (legList.length === 0) continue
    for (const oldId of legList) {
      if (nextRead.has(oldId)) {
        // Legacy ID could have been stored by another colliding event; only claim it if title also exists in bookmarks or no collision ambiguity
        const matchingBm = nextBookmarks.find((b) => b.event_id === oldId && b.title.trim() === ev.title.trim())
        if (matchingBm) {
          nextRead.add(ev.event_id)
        }
        nextRead.delete(oldId)
        migrated = true
      }
      for (const bm of nextBookmarks) {
        if (bm.event_id === oldId && bm.title.trim() === ev.title.trim()) {
          bm.event_id = ev.event_id
          migrated = true
        }
      }
    }
  }

  if (migrated) {
    saveBookmarkedEvents(nextBookmarks, storage)
    const { legacyReadTitles } = loadReadState(storage)
    saveReadState(nextRead, legacyReadTitles, storage)
  }
  return { readIds: nextRead, bookmarks: nextBookmarks, migrated }
}

const DEFAULT_WATCHLIST_SEEDS: WatchlistItem[] = [
  {
    id: 'wl_seed_diplomacy_apec',
    kind: 'event',
    label: '中美外交与 APEC 峰会',
    entity_id: 'ent_us_china_diplomacy',
    keywords: ['特朗普', '川普', 'trump', 'apec', '习近平', '中美', '中美俄', '访华', '白宫', '外交部', '深圳峰会'],
    created_at: '2026-11-19T00:00:00+08:00',
  },
  {
    id: 'wl_seed_macro_fed',
    kind: 'industry',
    label: '美联储、关税与大宗商品',
    entity_id: 'ent_macro_fomc',
    keywords: ['美联储', 'fomc', '降息', '加息', '关税', '黄金', '金价', '美元指数', '美元汇率', '原油', '央行'],
    created_at: '2026-11-19T00:00:00+08:00',
  },
  {
    id: 'wl_seed_ai_chips',
    kind: 'tech',
    label: 'AI 大模型与算力芯片',
    entity_id: 'ent_nvidia',
    market: 'US/HK',
    keywords: ['英伟达', 'nvidia', 'nvda', 'qwen', '千问', 'deepseek', 'anthropic', 'openai', '混元', '存储芯片', 'hbm'],
    created_at: '2026-11-19T00:00:00+08:00',
  },
  {
    id: 'wl_seed_spacex',
    kind: 'company',
    label: 'SpaceX / 特斯拉 / 商业航天',
    entity_id: 'ent_spacex_tesla',
    market: 'US',
    keywords: ['spacex', '星舰', 'starship', '筷子夹', '马斯克', '特斯拉', 'tesla', 'grok', 'optimus'],
    created_at: '2026-11-19T00:00:00+08:00',
  },
]

function readJsonKey<T>(key: string, fallback: T, storage?: StorageLike): T {
  const s = getSafeStorage(storage)
  try {
    const raw = s.getItem(key)
    if (!raw) return fallback
    return JSON.parse(raw) as T
  } catch {
    return fallback
  }
}

function writeJsonKey(key: string, value: unknown, storage?: StorageLike): void {
  const s = getSafeStorage(storage)
  try {
    s.setItem(key, JSON.stringify(value))
  } catch {
    // Ignore storage quota errors
  }
}

export function loadWatchlist(storage?: StorageLike): WatchlistItem[] {
  const s = getSafeStorage(storage)
  const raw = s.getItem(KEYS.V3_WATCHLIST)
  if (raw === null) {
    // First-ever load: seed defaults and persist so subsequent deletes stay persistent
    saveWatchlist(DEFAULT_WATCHLIST_SEEDS, storage)
    return DEFAULT_WATCHLIST_SEEDS.map((x) => ({ ...x, keywords: [...x.keywords] }))
  }
  const parsed = readJsonKey<WatchlistItem[]>(KEYS.V3_WATCHLIST, [], storage)
  return Array.isArray(parsed) ? parsed : []
}

export function saveWatchlist(items: WatchlistItem[], storage?: StorageLike): void {
  writeJsonKey(KEYS.V3_WATCHLIST, items.slice(0, 100), storage)
}

export function loadStringSetKey(
  kind: 'muted' | 'downweighted' | 'read_later',
  storage?: StorageLike,
): Set<string> {
  const key =
    kind === 'muted'
      ? KEYS.V3_MUTED
      : kind === 'downweighted'
        ? KEYS.V3_DOWNWEIGHTED
        : KEYS.V3_READ_LATER
  const list = readJsonKey<unknown>(key, [], storage)
  if (!Array.isArray(list)) return new Set()
  return new Set(list.filter((x): x is string => typeof x === 'string' && x.length > 0))
}

export function saveStringSetKey(
  kind: 'muted' | 'downweighted' | 'read_later',
  set: Set<string>,
  storage?: StorageLike,
): void {
  const key =
    kind === 'muted'
      ? KEYS.V3_MUTED
      : kind === 'downweighted'
        ? KEYS.V3_DOWNWEIGHTED
        : KEYS.V3_READ_LATER
  writeJsonKey(key, Array.from(set).slice(-1000), storage)
}

export function loadReadLaterMetaMap(storage?: StorageLike): Record<string, ReadLaterMetaEntry> {
  const raw = readJsonKey<unknown>(KEYS.V3_READ_LATER_META, {}, storage)
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {}
  return raw as Record<string, ReadLaterMetaEntry>
}

export function saveReadLaterMetaMap(map: Record<string, ReadLaterMetaEntry>, storage?: StorageLike): void {
  const entries = Object.entries(map).slice(-300)
  writeJsonKey(KEYS.V3_READ_LATER_META, Object.fromEntries(entries), storage)
}

export function resolveReadLaterEventsList(
  readLaterSet: Set<string>,
  loadedEvents: SmartEvent[],
  metaMap: Record<string, ReadLaterMetaEntry>,
): { validEvents: SmartEvent[]; orphanIds: string[] } {
  const loadedById = new Map<string, SmartEvent>()
  for (const ev of loadedEvents) {
    loadedById.set(ev.event_id, ev)
    for (const leg of ev.legacy_event_ids || []) {
      loadedById.set(leg, ev)
    }
  }
  const validEvents: SmartEvent[] = []
  const orphanIds: string[] = []
  for (const id of readLaterSet) {
    const live = loadedById.get(id)
    if (live) {
      validEvents.push(live)
      continue
    }
    const meta = metaMap[id]
    if (meta && meta.title) {
      validEvents.push({
        event_id: meta.event_id || id,
        title: meta.title,
        category: meta.category || 'general',
        entities: [],
        importance: 'normal',
        sentiment: null,
        special_note: null,
        evidence_status: 'single_source',
        evidence_label: '已保存待深读',
        evidence_status_reason: '跨批次保留快照',
        material_depth: 'title_only',
        source_count: meta.url ? 1 : 0,
        platform_count: meta.url ? 1 : 0,
        published_at: meta.saved_at || null,
        fetched_at: meta.saved_at || new Date().toISOString(),
        input_batch_id: 'saved-snapshot',
        fact_summary: '',
        ai_analysis: '',
        unverified_claims: [],
        speculation_or_outlook: null,
        sources: meta.url
          ? [
              {
                item_id: `rl_${id}`,
                source_id: 'saved',
                source_name: meta.source_name || '已保存报道',
                source_kind: 'news',
                title: meta.title,
                url: meta.url,
                published_at: meta.saved_at || null,
                fetched_at: meta.saved_at || new Date().toISOString(),
              },
            ]
          : [],
        followup: null,
        is_new_in_batch: false,
      })
    } else {
      orphanIds.push(id)
    }
  }
  return { validEvents, orphanIds }
}

export function loadHideReprints(storage?: StorageLike): boolean {
  const s = getSafeStorage(storage)
  const val = s.getItem(KEYS.V3_HIDE_REPRINTS)
  return val === null ? true : val === 'true'
}

export function saveHideReprints(hide: boolean, storage?: StorageLike): void {
  const s = getSafeStorage(storage)
  try {
    s.setItem(KEYS.V3_HIDE_REPRINTS, hide ? 'true' : 'false')
  } catch {
    // Ignore
  }
}

export function loadAlertRules(storage?: StorageLike): AlertRuleSettings {
  return readJsonKey<AlertRuleSettings>(
    KEYS.V3_ALERT_RULES,
    {
      firstPartyOnly: false,
      maxIndependentThreshold: 1,
      quietHoursStart: '23:00',
      quietHoursEnd: '07:00',
    },
    storage,
  )
}

export function saveAlertRules(rules: AlertRuleSettings, storage?: StorageLike): void {
  writeJsonKey(KEYS.V3_ALERT_RULES, rules, storage)
}

export function loadLocalPredictions(storage?: StorageLike): PredictionRecord[] {
  const list = readJsonKey<PredictionRecord[]>(KEYS.V3_PREDICTIONS, [], storage)
  return Array.isArray(list) ? list : []
}

export function saveLocalPredictions(records: PredictionRecord[], storage?: StorageLike): void {
  writeJsonKey(KEYS.V3_PREDICTIONS, records.slice(0, 300), storage)
}

export interface LocalToolState {
  wantTry: boolean
  note: string
  updatedAt: string
}

export function loadToolStates(storage?: StorageLike): Record<string, LocalToolState> {
  const raw = readJsonKey<Record<string, LocalToolState>>(KEYS.V3_TOOL_STATES, {}, storage)
  return raw && typeof raw === 'object' ? raw : {}
}

export function saveToolStates(states: Record<string, LocalToolState>, storage?: StorageLike): void {
  writeJsonKey(KEYS.V3_TOOL_STATES, states, storage)
}

export function loadResearchNotes(storage?: StorageLike): ResearchNote[] {
  const list = readJsonKey<ResearchNote[]>(KEYS.V3_NOTES, [], storage)
  return Array.isArray(list) ? list : []
}

export function saveResearchNotes(notes: ResearchNote[], storage?: StorageLike): void {
  writeJsonKey(KEYS.V3_NOTES, notes.slice(0, 300), storage)
}

export function loadCustomCatalysts(storage?: StorageLike): CatalystEvent[] {
  const list = readJsonKey<CatalystEvent[]>(KEYS.V3_CUSTOM_CATALYSTS, [], storage)
  return Array.isArray(list) ? list : []
}

export function saveCustomCatalysts(list: CatalystEvent[], storage?: StorageLike): void {
  writeJsonKey(KEYS.V3_CUSTOM_CATALYSTS, list.slice(0, 200), storage)
}

export function loadCatalystOverrideMap(storage?: StorageLike): Record<string, CatalystOverrideEntry> {
  const raw = readJsonKey<Record<string, CatalystOverrideEntry>>(KEYS.V3_CATALYST_OVERRIDES, {}, storage)
  return raw && typeof raw === 'object' ? raw : {}
}

export function saveCatalystOverrideMap(
  map: Record<string, CatalystOverrideEntry>,
  storage?: StorageLike,
): void {
  writeJsonKey(KEYS.V3_CATALYST_OVERRIDES, map, storage)
}

export function loadAiClientConfig(storage?: StorageLike): AiClientConfig {
  const def: AiClientConfig = {
    provider: 'gemini',
    apiKey: '',
    model: '',
    baseUrl: 'https://api.openai.com/v1',
  }
  const raw = readJsonKey<Partial<AiClientConfig>>(KEYS.V3_AI_CLIENT_CONFIG, def, storage)
  return {
    provider: raw.provider === 'openai_compat' ? 'openai_compat' : 'gemini',
    apiKey: typeof raw.apiKey === 'string' ? raw.apiKey : '',
    model: typeof raw.model === 'string' && raw.model.trim() ? raw.model.trim() : def.model,
    baseUrl: typeof raw.baseUrl === 'string' && raw.baseUrl.trim() ? raw.baseUrl.trim() : def.baseUrl,
  }
}

export function saveAiClientConfig(cfg: AiClientConfig, storage?: StorageLike): void {
  writeJsonKey(KEYS.V3_AI_CLIENT_CONFIG, cfg, storage)
}

export type PredictionStance = 'agree' | 'disagree' | 'neutral'

export function loadPredictionStances(storage?: StorageLike): Record<string, PredictionStance> {
  const raw = readJsonKey<Record<string, unknown>>(KEYS.V3_PREDICTION_STANCES, {}, storage)
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {}
  const out: Record<string, PredictionStance> = {}
  for (const [k, v] of Object.entries(raw)) {
    if (v === 'agree' || v === 'disagree' || v === 'neutral') out[k] = v
  }
  return out
}

export function savePredictionStances(stances: Record<string, PredictionStance>, storage?: StorageLike): void {
  writeJsonKey(KEYS.V3_PREDICTION_STANCES, stances, storage)
}

export function loadPortfolioConfig(storage?: StorageLike): PortfolioConfig {
  const def: PortfolioConfig = {
    sectors: ['AI 算力 / 半导体', '美股核心科技'],
    tickers: ['NVDA'],
    riskProfile: 'balanced',
  }
  const raw = readJsonKey<Partial<PortfolioConfig>>(KEYS.V3_PORTFOLIO, def, storage)
  return {
    sectors: Array.isArray(raw.sectors) ? raw.sectors.filter((x): x is string => typeof x === 'string') : def.sectors,
    tickers: Array.isArray(raw.tickers) ? raw.tickers.filter((x): x is string => typeof x === 'string') : def.tickers,
    riskProfile:
      raw.riskProfile === 'conservative' || raw.riskProfile === 'aggressive' ? raw.riskProfile : 'balanced',
  }
}

export function savePortfolioConfig(cfg: PortfolioConfig, storage?: StorageLike): void {
  writeJsonKey(KEYS.V3_PORTFOLIO, cfg, storage)
}

export function exportBookmarksMarkdown(bookmarks: BookmarkedEvent[]): string {
  const lines = ['# 镜信 MirrorBrief 我的收藏导出', '', `导出时间：${new Date().toISOString()}`, `总计：${bookmarks.length} 条`, '']
  for (const b of bookmarks) {
    const tagStr = b.tags && b.tags.length > 0 ? ` [${b.tags.join(', ')}]` : ''
    lines.push(`- **${b.title}**${tagStr}`)
    lines.push(`  - 来源：${b.source_name || '默认信源'} | 领域：${b.category} | 收藏于：${b.saved_at.slice(0, 16).replace('T', ' ')}`)
    if (b.url && b.url !== '#') lines.push(`  - 原文：${b.url}`)
    if (b.note) lines.push(`  - 个人备注：${b.note}`)
  }
  return lines.join('\n')
}

export function exportBookmarksJson(bookmarks: BookmarkedEvent[]): string {
  return JSON.stringify(
    {
      schema_version: '3.1',
      exported_at: new Date().toISOString(),
      total: bookmarks.length,
      bookmarks,
    },
    null,
    2,
  )
}

export function loadUserAvatar(storage?: StorageLike): string {
  const s = getSafeStorage(storage)
  try {
    const raw = (s.getItem(KEYS.V3_USER_AVATAR) || '').trim()
    return isValidAvatarValue(raw) ? raw : ''
  } catch {
    return ''
  }
}

export function saveUserAvatar(avatar: string, storage?: StorageLike): string {
  const clean = isValidAvatarValue(avatar) ? avatar.trim() : ''
  const s = getSafeStorage(storage)
  try {
    if (!clean && typeof s.removeItem === 'function') {
      s.removeItem(KEYS.V3_USER_AVATAR)
    } else {
      s.setItem(KEYS.V3_USER_AVATAR, clean)
    }
  } catch {
    // Ignore storage errors
  }
  return clean
}

export type WeeklyItemStanceChoice = 'bull' | 'bear' | 'neutral'
export type WeeklyOutlookIntuitionChoice = 'up' | 'volatile' | 'down'

export interface WeeklyHabitState {
  readByWeek: Record<string, string[]>
  completedWeeks: string[]
  reactionsByItem: Record<string, WeeklyItemStanceChoice>
  outlookStancesById: Record<string, WeeklyOutlookIntuitionChoice>
  lastVisitedWeekId: string | null
}

function emptyWeeklyHabitState(): WeeklyHabitState {
  return {
    readByWeek: {},
    completedWeeks: [],
    reactionsByItem: {},
    outlookStancesById: {},
    lastVisitedWeekId: null,
  }
}

export function normalizeWeeklyHabitState(raw: unknown): WeeklyHabitState {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return emptyWeeklyHabitState()
  }
  const src = raw as Partial<WeeklyHabitState>
  const readByWeek: Record<string, string[]> = {}
  if (src.readByWeek && typeof src.readByWeek === 'object' && !Array.isArray(src.readByWeek)) {
    for (const [wid, arr] of Object.entries(src.readByWeek)) {
      if (typeof wid === 'string' && wid && Array.isArray(arr)) {
        readByWeek[wid] = Array.from(new Set(arr.filter((x): x is string => typeof x === 'string' && x.length > 0)))
      }
    }
  }
  const completedWeeks = Array.isArray(src.completedWeeks)
    ? Array.from(new Set(src.completedWeeks.filter((w): w is string => typeof w === 'string' && w.length > 0))).sort()
    : []
  const reactionsByItem: Record<string, WeeklyItemStanceChoice> = {}
  if (src.reactionsByItem && typeof src.reactionsByItem === 'object' && !Array.isArray(src.reactionsByItem)) {
    for (const [k, v] of Object.entries(src.reactionsByItem)) {
      if (v === 'bull' || v === 'bear' || v === 'neutral') reactionsByItem[k] = v
    }
  }
  const outlookStancesById: Record<string, WeeklyOutlookIntuitionChoice> = {}
  if (src.outlookStancesById && typeof src.outlookStancesById === 'object' && !Array.isArray(src.outlookStancesById)) {
    for (const [k, v] of Object.entries(src.outlookStancesById)) {
      if (v === 'up' || v === 'volatile' || v === 'down') outlookStancesById[k] = v
    }
  }
  return {
    readByWeek,
    completedWeeks,
    reactionsByItem,
    outlookStancesById,
    lastVisitedWeekId: typeof src.lastVisitedWeekId === 'string' && src.lastVisitedWeekId ? src.lastVisitedWeekId : null,
  }
}

export function loadWeeklyHabitState(storage?: StorageLike): WeeklyHabitState {
  const s = getSafeStorage(storage)
  try {
    const raw = s.getItem(KEYS.V3_WEEKLY_HABIT)
    if (!raw) return emptyWeeklyHabitState()
    return normalizeWeeklyHabitState(JSON.parse(raw))
  } catch {
    return emptyWeeklyHabitState()
  }
}

export function saveWeeklyHabitState(state: WeeklyHabitState, storage?: StorageLike): WeeklyHabitState {
  const normalized = normalizeWeeklyHabitState(state)
  safeStorageSet(KEYS.V3_WEEKLY_HABIT, JSON.stringify(normalized), storage)
  return normalized
}

export function exportAllResearchState(storage?: StorageLike): string {
  const { readIds, legacyReadTitles } = loadReadState(storage)
  const payload = {
    schema_version: '3.0',
    exported_at: new Date().toISOString(),
    avatar: loadUserAvatar(storage),
    watchlist: loadWatchlist(storage),
    muted: Array.from(loadStringSetKey('muted', storage)),
    downweighted: Array.from(loadStringSetKey('downweighted', storage)),
    read_later: Array.from(loadStringSetKey('read_later', storage)),
    hide_reprints: loadHideReprints(storage),
    market_color_mode: safeStorageGet('infofocus_market_color_v1', storage) || 'auto',
    important_push_enabled: safeStorageGet('infofocus_mobile_important_push_v1', storage),
    alert_rules: loadAlertRules(storage),
    predictions: loadLocalPredictions(storage),
    tool_states: loadToolStates(storage),
    notes: loadResearchNotes(storage),
    custom_catalysts: loadCustomCatalysts(storage),
    catalyst_overrides: loadCatalystOverrideMap(storage),
    bookmarks: loadBookmarkedEvents(storage),
    portfolio: loadPortfolioConfig(storage),
    read_later_meta: loadReadLaterMetaMap(storage),
    prediction_stances: loadPredictionStances(storage),
    weekly_habit: loadWeeklyHabitState(storage),
    read_ids: Array.from(readIds),
    legacy_read_titles: Array.from(legacyReadTitles),
    favorite_sources: Array.from(loadFavoriteSourceIds(storage)),
  }
  return JSON.stringify(payload, null, 2)
}

export function importResearchStateJson(
  rawJsonText: string,
  storage?: StorageLike,
): { ok: boolean; importedCount: number; error?: string } {
  try {
    const data = JSON.parse(rawJsonText)
    if (!data || typeof data !== 'object') {
      return { ok: false, importedCount: 0, error: 'JSON 根节点必须是对象' }
    }
    let count = 0
    if (Array.isArray(data.watchlist)) {
      saveWatchlist(data.watchlist, storage)
      count += data.watchlist.length
    }
    if (Array.isArray(data.predictions)) {
      saveLocalPredictions(data.predictions, storage)
      count += data.predictions.length
    }
    if (Array.isArray(data.notes)) {
      saveResearchNotes(data.notes, storage)
      count += data.notes.length
    }
    if (Array.isArray(data.custom_catalysts)) {
      saveCustomCatalysts(data.custom_catalysts, storage)
      count += data.custom_catalysts.length
    }
    if (data.catalyst_overrides && typeof data.catalyst_overrides === 'object') {
      saveCatalystOverrideMap(data.catalyst_overrides as Record<string, CatalystOverrideEntry>, storage)
      count += Object.keys(data.catalyst_overrides).length
    }
    if (data.tool_states && typeof data.tool_states === 'object') {
      saveToolStates(data.tool_states, storage)
      count += Object.keys(data.tool_states).length
    }
    if (Array.isArray(data.bookmarks)) {
      saveBookmarkedEvents(data.bookmarks, storage)
      count += data.bookmarks.length
    }
    if (data.portfolio && typeof data.portfolio === 'object') {
      const p = data.portfolio as Partial<PortfolioConfig>
      savePortfolioConfig(
        {
          sectors: Array.isArray(p.sectors) ? p.sectors : [],
          tickers: Array.isArray(p.tickers) ? p.tickers : [],
          riskProfile:
            p.riskProfile === 'conservative' || p.riskProfile === 'aggressive' ? p.riskProfile : 'balanced',
        },
        storage,
      )
      count += 1
    }
    if (data.read_later_meta && typeof data.read_later_meta === 'object' && !Array.isArray(data.read_later_meta)) {
      saveReadLaterMetaMap(data.read_later_meta as Record<string, ReadLaterMetaEntry>, storage)
      count += Object.keys(data.read_later_meta).length
    }
    if (data.prediction_stances && typeof data.prediction_stances === 'object' && !Array.isArray(data.prediction_stances)) {
      savePredictionStances(data.prediction_stances as Record<string, PredictionStance>, storage)
      count += Object.keys(data.prediction_stances).length
    }
    if (data.weekly_habit && typeof data.weekly_habit === 'object' && !Array.isArray(data.weekly_habit)) {
      const normalizedHabit = saveWeeklyHabitState(data.weekly_habit as WeeklyHabitState, storage)
      count +=
        normalizedHabit.completedWeeks.length +
        Object.keys(normalizedHabit.reactionsByItem).length +
        Object.keys(normalizedHabit.outlookStancesById).length
    }
    if (Array.isArray(data.muted)) {
      saveStringSetKey('muted', new Set(data.muted), storage)
    }
    if (Array.isArray(data.downweighted)) {
      saveStringSetKey('downweighted', new Set(data.downweighted), storage)
    }
    if (Array.isArray(data.read_later)) {
      saveStringSetKey('read_later', new Set(data.read_later), storage)
    }
    if (typeof data.hide_reprints === 'boolean') {
      saveHideReprints(data.hide_reprints, storage)
      count += 1
    }
    if (data.alert_rules && typeof data.alert_rules === 'object') {
      saveAlertRules(data.alert_rules as AlertRuleSettings, storage)
      count += 1
    }
    if (Array.isArray(data.read_ids) || Array.isArray(data.legacy_read_titles)) {
      const nextRead = new Set(Array.isArray(data.read_ids) ? (data.read_ids as string[]) : [])
      const nextTitles = new Set(
        Array.isArray(data.legacy_read_titles) ? (data.legacy_read_titles as string[]) : [],
      )
      saveReadState(nextRead, nextTitles, storage)
      count += nextRead.size
    }
    if (Array.isArray(data.favorite_sources)) {
      saveFavoriteSourceIds(new Set(data.favorite_sources as string[]), storage)
      count += data.favorite_sources.length
    }
    if (typeof data.avatar === 'string' && isValidAvatarValue(data.avatar)) {
      saveUserAvatar(data.avatar, storage)
      count += 1
    }
    if (data.market_color_mode === 'cn' || data.market_color_mode === 'intl' || data.market_color_mode === 'auto') {
      safeStorageSet('infofocus_market_color_v1', data.market_color_mode, storage)
      count += 1
    }
    if (data.important_push_enabled === '1' || data.important_push_enabled === '0') {
      safeStorageSet('infofocus_mobile_important_push_v1', data.important_push_enabled, storage)
      count += 1
    }
    return { ok: true, importedCount: count }
  } catch (err) {
    return { ok: false, importedCount: 0, error: err instanceof Error ? err.message : '解析 JSON 失败' }
  }
}

export function mergeResearchStateJson(
  rawJsonText: string,
  storage?: StorageLike,
): { ok: boolean; mergedCount: number; needsPush: boolean; error?: string } {
  try {
    const cloud = JSON.parse(rawJsonText)
    if (!cloud || typeof cloud !== 'object') {
      return { ok: false, mergedCount: 0, needsPush: false, error: '云端状态格式无效' }
    }
    let mergedCount = 0
    let needsPush = false

    const localBookmarks = loadBookmarkedEvents(storage)
    const cloudBookmarks = Array.isArray(cloud.bookmarks) ? (cloud.bookmarks as BookmarkedEvent[]) : []
    const bmMap = new Map<string, BookmarkedEvent>()
    for (const b of cloudBookmarks) if (b?.event_id) bmMap.set(b.event_id, b)
    for (const b of localBookmarks) {
      if (b?.event_id && !bmMap.has(b.event_id)) {
        bmMap.set(b.event_id, b)
        needsPush = true
      }
    }
    if (bmMap.size > 0) {
      saveBookmarkedEvents(Array.from(bmMap.values()), storage)
      mergedCount += bmMap.size
    }

    const localNotes = loadResearchNotes(storage)
    const cloudNotes = Array.isArray(cloud.notes) ? (cloud.notes as ResearchNote[]) : []
    const noteMap = new Map<string, ResearchNote>()
    for (const n of cloudNotes) if (n?.note_id) noteMap.set(n.note_id, n)
    for (const n of localNotes) {
      if (n?.note_id && !noteMap.has(n.note_id)) {
        noteMap.set(n.note_id, n)
        needsPush = true
      }
    }
    if (noteMap.size > 0) {
      saveResearchNotes(Array.from(noteMap.values()), storage)
      mergedCount += noteMap.size
    }

    const localPreds = loadLocalPredictions(storage)
    const cloudPreds = Array.isArray(cloud.predictions) ? (cloud.predictions as PredictionRecord[]) : []
    const predMap = new Map<string, PredictionRecord>()
    for (const p of cloudPreds) if (p?.prediction_id) predMap.set(p.prediction_id, p)
    for (const p of localPreds) {
      if (p?.prediction_id && !predMap.has(p.prediction_id)) {
        predMap.set(p.prediction_id, p)
        needsPush = true
      }
    }
    if (predMap.size > 0) {
      saveLocalPredictions(Array.from(predMap.values()), storage)
      mergedCount += predMap.size
    }

    const localCals = loadCustomCatalysts(storage)
    const cloudCals = Array.isArray(cloud.custom_catalysts) ? (cloud.custom_catalysts as CatalystEvent[]) : []
    const calMap = new Map<string, CatalystEvent>()
    for (const c of cloudCals) if (c?.calendar_id) calMap.set(c.calendar_id, c)
    for (const c of localCals) {
      if (c?.calendar_id && !calMap.has(c.calendar_id)) {
        calMap.set(c.calendar_id, c)
        needsPush = true
      }
    }
    if (calMap.size > 0) {
      saveCustomCatalysts(Array.from(calMap.values()), storage)
      mergedCount += calMap.size
    }

    const mergedCatOv = { ...(cloud.catalyst_overrides || {}), ...loadCatalystOverrideMap(storage) }
    if (Object.keys(mergedCatOv).length > 0) {
      saveCatalystOverrideMap(mergedCatOv, storage)
      mergedCount += Object.keys(mergedCatOv).length
    }

    const mergedTools = { ...(cloud.tool_states || {}), ...loadToolStates(storage) }
    if (Object.keys(mergedTools).length > 0) {
      saveToolStates(mergedTools, storage)
      mergedCount += Object.keys(mergedTools).length
    }

    const localWatch = loadWatchlist(storage)
    const cloudWatch = Array.isArray(cloud.watchlist) ? (cloud.watchlist as WatchlistItem[]) : []
    const watchMap = new Map<string, WatchlistItem>()
    for (const w of cloudWatch) if (w?.label) watchMap.set(w.label, w)
    for (const w of localWatch) {
      if (w?.label && !watchMap.has(w.label)) {
        watchMap.set(w.label, w)
      }
    }
    if (watchMap.size > 0) {
      saveWatchlist(Array.from(watchMap.values()), storage)
    }

    const localPortfolio = loadPortfolioConfig(storage)
    const cp = (cloud.portfolio && typeof cloud.portfolio === 'object' ? cloud.portfolio : {}) as Partial<PortfolioConfig>
    savePortfolioConfig(
      {
        sectors: Array.from(new Set([...(Array.isArray(cp.sectors) ? cp.sectors : []), ...localPortfolio.sectors])),
        tickers: Array.from(new Set([...(Array.isArray(cp.tickers) ? cp.tickers : []), ...localPortfolio.tickers])),
        riskProfile: cp.riskProfile || localPortfolio.riskProfile,
      },
      storage,
    )

    for (const setKey of ['muted', 'downweighted', 'read_later'] as const) {
      const localSet = loadStringSetKey(setKey, storage)
      const cloudArr = Array.isArray(cloud[setKey]) ? (cloud[setKey] as string[]) : []
      const mergedSet = new Set([
        ...cloudArr,
        ...Array.from(localSet),
      ])
      saveStringSetKey(setKey, mergedSet, storage)
      if (localSet.size > cloudArr.length || Array.from(localSet).some((v) => !cloudArr.includes(v))) {
        needsPush = true
      }
    }

    const { readIds: curReads, legacyReadTitles: curLegacy } = loadReadState(storage)
    const nextRead = new Set([
      ...(Array.isArray(cloud.read_ids) ? (cloud.read_ids as string[]) : []),
      ...Array.from(curReads),
    ])
    const nextLegacy = new Set([
      ...(Array.isArray(cloud.legacy_read_titles) ? (cloud.legacy_read_titles as string[]) : []),
      ...Array.from(curLegacy),
    ])
    if (curReads.size > (Array.isArray(cloud.read_ids) ? cloud.read_ids.length : 0)) {
      needsPush = true
    }
    saveReadState(nextRead, nextLegacy, storage)

    const mergedFavs = new Set([
      ...(Array.isArray(cloud.favorite_sources) ? (cloud.favorite_sources as string[]) : []),
      ...Array.from(loadFavoriteSourceIds(storage)),
    ])
    saveFavoriteSourceIds(mergedFavs, storage)

    const localMeta = loadReadLaterMetaMap(storage)
    const cloudMeta = (cloud.read_later_meta && typeof cloud.read_later_meta === 'object' ? cloud.read_later_meta : {}) as Record<string, ReadLaterMetaEntry>
    const mergedMeta = { ...cloudMeta, ...localMeta }
    if (Object.keys(mergedMeta).length > 0) {
      saveReadLaterMetaMap(mergedMeta, storage)
      if (Object.keys(localMeta).length > Object.keys(cloudMeta).length) needsPush = true
    }

    const localStances = loadPredictionStances(storage)
    const cloudStances = (cloud.prediction_stances && typeof cloud.prediction_stances === 'object' ? cloud.prediction_stances : {}) as Record<string, PredictionStance>
    const mergedStances = { ...cloudStances, ...localStances }
    if (Object.keys(mergedStances).length > 0) {
      savePredictionStances(mergedStances, storage)
      if (Object.keys(localStances).length > Object.keys(cloudStances).length) needsPush = true
    }

    const localHabit = loadWeeklyHabitState(storage)
    const cloudHabit = normalizeWeeklyHabitState(cloud.weekly_habit)
    const mergedReadByWeek: Record<string, string[]> = { ...cloudHabit.readByWeek }
    for (const [wid, localArr] of Object.entries(localHabit.readByWeek)) {
      const cloudArr = mergedReadByWeek[wid] || []
      const union = Array.from(new Set([...cloudArr, ...localArr]))
      if (union.length > cloudArr.length) needsPush = true
      mergedReadByWeek[wid] = union
    }
    const mergedCompleted = Array.from(new Set([...cloudHabit.completedWeeks, ...localHabit.completedWeeks])).sort()
    if (mergedCompleted.length > cloudHabit.completedWeeks.length) needsPush = true
    const mergedReactions = { ...cloudHabit.reactionsByItem, ...localHabit.reactionsByItem }
    if (
      Object.keys(localHabit.reactionsByItem).some(
        (k) => localHabit.reactionsByItem[k] !== cloudHabit.reactionsByItem[k],
      )
    ) {
      needsPush = true
    }
    const mergedOutlook = { ...cloudHabit.outlookStancesById, ...localHabit.outlookStancesById }
    if (
      Object.keys(localHabit.outlookStancesById).some(
        (k) => localHabit.outlookStancesById[k] !== cloudHabit.outlookStancesById[k],
      )
    ) {
      needsPush = true
    }
    const mergedHabit: WeeklyHabitState = {
      readByWeek: mergedReadByWeek,
      completedWeeks: mergedCompleted,
      reactionsByItem: mergedReactions,
      outlookStancesById: mergedOutlook,
      lastVisitedWeekId: localHabit.lastVisitedWeekId || cloudHabit.lastVisitedWeekId,
    }
    if (
      Object.keys(mergedReadByWeek).length > 0 ||
      mergedCompleted.length > 0 ||
      Object.keys(mergedReactions).length > 0 ||
      Object.keys(mergedOutlook).length > 0 ||
      mergedHabit.lastVisitedWeekId
    ) {
      saveWeeklyHabitState(mergedHabit, storage)
      mergedCount += 1
    }

    const localAvatar = loadUserAvatar(storage)
    const cloudAvatar = typeof cloud.avatar === 'string' && isValidAvatarValue(cloud.avatar) ? cloud.avatar.trim() : ''
    if (cloudAvatar && !localAvatar) {
      saveUserAvatar(cloudAvatar, storage)
      mergedCount += 1
    } else if (localAvatar && localAvatar !== cloudAvatar) {
      needsPush = true
    }

    const localMarketColor = safeStorageGet('infofocus_market_color_v1', storage)
    const cloudMarketColor =
      cloud.market_color_mode === 'cn' || cloud.market_color_mode === 'intl' ? cloud.market_color_mode : ''
    if (cloudMarketColor && !localMarketColor) {
      safeStorageSet('infofocus_market_color_v1', cloudMarketColor, storage)
      mergedCount += 1
    } else if (localMarketColor && localMarketColor !== cloudMarketColor) {
      needsPush = true
    }

    const localPush = safeStorageGet('infofocus_mobile_important_push_v1', storage)
    const cloudPush =
      cloud.important_push_enabled === '1' || cloud.important_push_enabled === '0' ? cloud.important_push_enabled : ''
    if (cloudPush && localPush === null) {
      safeStorageSet('infofocus_mobile_important_push_v1', cloudPush, storage)
      mergedCount += 1
    } else if (localPush !== null && localPush !== cloudPush) {
      needsPush = true
    }

    return { ok: true, mergedCount, needsPush }
  } catch (err) {
    return { ok: false, mergedCount: 0, needsPush: false, error: err instanceof Error ? err.message : '合并云端状态失败' }
  }
}

export function clearLocalResearchState(storage?: StorageLike): void {
  const s = getSafeStorage(storage)
  const keysToClear = [
    ...Object.entries(KEYS)
      .filter(([name]) => name !== 'DARK_MODE' && name !== 'V3_AI_CLIENT_CONFIG')
      .map(([, key]) => key),
    'daily_news_ai_v3_catalyst_overrides_v1',
  ]
  for (const key of keysToClear) {
    try {
      if (typeof s.removeItem === 'function') {
        s.removeItem(key)
      } else {
        s.setItem(key, '')
      }
    } catch {
      // Ignore storage access errors
    }
  }
}
