import { computed, ref } from 'vue'
import { getApiBase } from './auth'
import { resolveDataUrl } from './dataBase'
import { formatShanghaiHhMm, parseTimestampMs } from './time'
import type { FinanceImpactDoc, MarketQuoteItem } from './types'

export interface GlobalQuotesResponse {
  schema_version?: string
  updated_at?: string
  quote_time_hhmm?: string
  session_status?: string
  status?: string
  source_note?: string
  source_note_en?: string
  indices?: MarketQuoteItem[]
  quotes?: Record<string, MarketQuoteItem>
}

const indicesRef = ref<MarketQuoteItem[]>([])
const quotesMapRef = ref<Record<string, MarketQuoteItem>>({})
const updatedAtRef = ref<string | null>(null)
const quoteTimeHhmmRef = ref<string>('')
const sessionStatusRef = ref<string>('closed')
const flashingTickersRef = ref<Record<string, 'up' | 'down'>>({})
const loadingRef = ref(false)
const lastFetchSourceRef = ref<'api' | 'static' | 'finance_doc' | 'none'>('none')

let pollTimer: ReturnType<typeof setInterval> | null = null
let activePolling = false
let inFlightPromise: Promise<void> | null = null
let visibilityListenerBound = false
let refreshListenerBound = false

function formatHhmmFromIso(iso: string | null | undefined, explicitHhmm?: string | null): string {
  const cleanHhmm = String(explicitHhmm || '').trim()
  if (/^\d{2}:\d{2}$/.test(cleanHhmm)) return cleanHhmm
  if (!iso) return ''
  const ms = parseTimestampMs(iso)
  if (ms === null) return ''
  try {
    const dt = new Date(ms)
    const parts = new Intl.DateTimeFormat('zh-CN', {
      timeZone: 'Asia/Shanghai',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).formatToParts(dt)
    const hh = parts.find((p) => p.type === 'hour')?.value ?? '00'
    const mm = parts.find((p) => p.type === 'minute')?.value ?? '00'
    return `${hh}:${mm}`
  } catch {
    return formatShanghaiHhMm(iso)
  }
}

function isTradingSessionNow(): boolean {
  try {
    const now = new Date()
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: 'Asia/Shanghai',
      weekday: 'short',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).formatToParts(now)
    const wd = parts.find((p) => p.type === 'weekday')?.value ?? 'Mon'
    if (wd === 'Sat' || wd === 'Sun') return false
    const hh = Number(parts.find((p) => p.type === 'hour')?.value ?? '0')
    const mm = Number(parts.find((p) => p.type === 'minute')?.value ?? '0')
    const hm = hh * 60 + mm
    return (hm >= 9 * 60 + 15 && hm <= 11 * 60 + 35) || (hm >= 13 * 60 && hm <= 16 * 60 + 15) || hm >= 21 * 60 || hm <= 5 * 60 + 15
  } catch {
    return false
  }
}

function recordFlashes(prevMap: Record<string, MarketQuoteItem>, nextIndices: MarketQuoteItem[], nextMap: Record<string, MarketQuoteItem>): void {
  const nextFlashes: Record<string, 'up' | 'down'> = {}
  const prevIndices = new Map<string, MarketQuoteItem>()
  for (const idx of indicesRef.value) prevIndices.set(idx.ticker, idx)

  for (const item of nextIndices) {
    const prev = prevIndices.get(item.ticker) ?? prevMap[item.ticker]
    if (prev && (prev.price !== item.price || prev.pct_change !== item.pct_change)) {
      nextFlashes[item.ticker] = item.price >= prev.price ? 'up' : 'down'
    }
  }
  for (const [tkr, item] of Object.entries(nextMap)) {
    const prev = prevMap[tkr]
    if (prev && (prev.price !== item.price || prev.pct_change !== item.pct_change)) {
      nextFlashes[tkr] = item.price >= prev.price ? 'up' : 'down'
    }
  }
  if (Object.keys(nextFlashes).length > 0) {
    flashingTickersRef.value = nextFlashes
    setTimeout(() => {
      flashingTickersRef.value = {}
    }, 1500)
  }
}

function applyQuotesPayload(doc: GlobalQuotesResponse, sourceKind: 'api' | 'static' | 'finance_doc'): void {
  const incomingIndices = Array.isArray(doc.indices) ? doc.indices : []
  const incomingMap = doc.quotes && typeof doc.quotes === 'object' ? doc.quotes : {}
  const hasAnyData = incomingIndices.length > 0 || Object.keys(incomingMap).length > 0
  if (!hasAnyData) return

  const curUpdated = updatedAtRef.value || ''
  const nextUpdated = String(doc.updated_at || '')
  // Never let an older static snapshot overwrite a newer live API snapshot unless current store is empty
  if (indicesRef.value.length > 0 && curUpdated && nextUpdated && nextUpdated < curUpdated && sourceKind !== 'api') {
    return
  }

  recordFlashes(quotesMapRef.value, incomingIndices, incomingMap)

  if (incomingIndices.length > 0) {
    indicesRef.value = incomingIndices
  }
  if (Object.keys(incomingMap).length > 0) {
    quotesMapRef.value = { ...quotesMapRef.value, ...incomingMap }
  }
  if (nextUpdated) {
    updatedAtRef.value = nextUpdated
  }
  const hhmm = formatHhmmFromIso(nextUpdated || updatedAtRef.value, doc.quote_time_hhmm)
  if (hhmm) quoteTimeHhmmRef.value = hhmm
  if (doc.session_status) sessionStatusRef.value = doc.session_status
  lastFetchSourceRef.value = sourceKind
}

export function seedGlobalQuotesFromFinanceDoc(doc: FinanceImpactDoc | null | undefined): void {
  if (!doc) return
  const docIndices = Array.isArray(doc.index_quotes) ? doc.index_quotes : []
  if (docIndices.length === 0) return
  // Seed immediately on cold start so desktop right rail and Finance tab are synchronized before API returns
  const mapFromDoc: Record<string, MarketQuoteItem> = {}
  for (const idx of docIndices) {
    if (idx?.ticker) mapFromDoc[idx.ticker] = idx
  }
  for (const card of doc.event_impacts || []) {
    for (const rq of card.realized_quotes || []) {
      if (rq?.ticker && !mapFromDoc[rq.ticker]) {
        mapFromDoc[rq.ticker] = rq
      }
    }
  }
  applyQuotesPayload(
    {
      updated_at: doc.quotes_updated_at || doc.generated_at,
      indices: docIndices,
      quotes: mapFromDoc,
    },
    'finance_doc',
  )
}

export async function refreshGlobalQuotes(): Promise<void> {
  if (inFlightPromise) return inFlightPromise
  inFlightPromise = (async () => {
    loadingRef.value = true
    try {
      const apiBase = getApiBase()
      try {
        const resp = await fetch(`${apiBase}/api/market/quotes`, { cache: 'no-store' })
        if (resp.ok) {
          const data = (await resp.json()) as GlobalQuotesResponse
          if (data && (Array.isArray(data.indices) && data.indices.length > 0 || (data.quotes && Object.keys(data.quotes).length > 0))) {
            applyQuotesPayload(data, 'api')
            return
          }
        }
      } catch {
        // Fall through to static data file on offline/static hosts
      }
      try {
        const staticResp = await fetch(resolveDataUrl('data/market_quotes.json', true), { cache: 'no-store' })
        if (staticResp.ok) {
          const staticData = (await staticResp.json()) as GlobalQuotesResponse
          applyQuotesPayload(staticData, 'static')
        }
      } catch {
        // Keep existing quotes safely
      }
    } finally {
      loadingRef.value = false
      inFlightPromise = null
    }
  })()
  return inFlightPromise
}

function scheduleNextInterval(): void {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
  if (!activePolling || typeof window === 'undefined') return
  const intervalMs = isTradingSessionNow() ? 35_000 : 60_000
  pollTimer = setInterval(() => {
    if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return
    void refreshGlobalQuotes()
  }, intervalMs)
}

function handleVisibilityChange(): void {
  if (typeof document !== 'undefined' && document.visibilityState === 'visible') {
    void refreshGlobalQuotes()
  }
}

function handleForceRefreshEvent(): void {
  void refreshGlobalQuotes()
}

export function startGlobalQuotesPolling(): void {
  if (typeof window === 'undefined') return
  activePolling = true
  void refreshGlobalQuotes()
  scheduleNextInterval()
  if (!visibilityListenerBound && typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', handleVisibilityChange)
    visibilityListenerBound = true
  }
  if (!refreshListenerBound) {
    window.addEventListener('jingxin:refresh-quotes', handleForceRefreshEvent)
    refreshListenerBound = true
  }
}

export function stopGlobalQuotesPolling(): void {
  activePolling = false
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
  if (visibilityListenerBound && typeof document !== 'undefined') {
    document.removeEventListener('visibilitychange', handleVisibilityChange)
    visibilityListenerBound = false
  }
  if (refreshListenerBound && typeof window !== 'undefined') {
    window.removeEventListener('jingxin:refresh-quotes', handleForceRefreshEvent)
    refreshListenerBound = false
  }
}

export function resolveLiveQuote(quote: MarketQuoteItem): MarketQuoteItem {
  if (!quote?.ticker) return quote
  return quotesMapRef.value[quote.ticker] ?? quotesMapRef.value[quote.ticker.toUpperCase()] ?? quote
}

export function resetGlobalQuotesForTests(): void {
  indicesRef.value = []
  quotesMapRef.value = {}
  updatedAtRef.value = null
  quoteTimeHhmmRef.value = ''
  flashingTickersRef.value = {}
  lastFetchSourceRef.value = 'none'
}

export const globalQuotesStore = {
  indices: computed(() => indicesRef.value),
  quotesMap: computed(() => quotesMapRef.value),
  updatedAt: computed(() => updatedAtRef.value),
  updatedTimeLabel: computed(() => quoteTimeHhmmRef.value || formatHhmmFromIso(updatedAtRef.value)),
  sessionStatus: computed(() => sessionStatusRef.value),
  flashingTickers: computed(() => flashingTickersRef.value),
  loading: computed(() => loadingRef.value),
  lastFetchSource: computed(() => lastFetchSourceRef.value),
}
