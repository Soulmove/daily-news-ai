import type { CategoryKey, EvidenceStatus, WorkbenchTab } from './types'

const VALID_CATEGORIES = new Set<CategoryKey>(['finance', 'global', 'tech', 'general'])
const VALID_EVIDENCE = new Set<string>(['all', 'official_confirmed', 'multi_source', 'single_source', 'needs_verification'])
const VALID_TABS = new Set<WorkbenchTab>(['today', 'wire', 'briefing', 'ai_progress', 'finance', 'tracking', 'calendar', 'predictions', 'tools', 'me'])
const VALID_FRESH = new Set<string>(['all', 'unread', 'first_discovery', 'old_progress'])

export type FreshnessBucket = 'all' | 'unread' | 'first_discovery' | 'old_progress'

export interface BriefingUrlState {
  tab: WorkbenchTab
  cat: CategoryKey
  history: string | null
  event: string | null
  story: string | null
  entity: string | null
  q: string
  scope: 'current' | 'all'
  source: string
  evidence: 'all' | EvidenceStatus
  unread: boolean
  fresh: FreshnessBucket
}

export type MonitorViewMode = 'stream' | 'matrix' | 'health' | 'connectors' | 'radar'

export interface MonitorUrlState {
  cat: CategoryKey | 'favorites'
  history: string | null
  view: MonitorViewMode
  q: string
  source: string
  health: 'all' | 'ok' | 'issue'
}

export function hasInvalidBriefingUrlParams(search = typeof window !== 'undefined' ? window.location.search : ''): boolean {
  const params = new URLSearchParams(search)
  const rawTab = params.get('tab')
  if (rawTab !== null && !VALID_TABS.has(rawTab as WorkbenchTab)) return true
  if (rawTab === 'today') return true
  const rawCat = params.get('cat')
  if (rawCat !== null && !VALID_CATEGORIES.has(rawCat as CategoryKey)) return true
  const rawEvidence = params.get('evidence')
  if (rawEvidence !== null && !VALID_EVIDENCE.has(rawEvidence)) return true
  const rawFresh = params.get('fresh')
  if (rawFresh !== null && !VALID_FRESH.has(rawFresh)) return true
  return false
}

export function sanitizeHistoryParam(raw: string | null): string | null {
  if (!raw) return null
  const trimmed = raw.trim().replace(/^\/+/, '')
  if (!trimmed.startsWith('archives/')) return null
  if (trimmed.includes('..')) return null
  return trimmed.endsWith('/') ? trimmed : `${trimmed}/`
}

export function parseBriefingUrlState(search = typeof window !== 'undefined' ? window.location.search : ''): BriefingUrlState {
  const params = new URLSearchParams(search)
  const rawTabParam = params.get('tab')
  const rawTab = (rawTabParam === 'impact' ? 'finance' : rawTabParam) as WorkbenchTab | null
  const tab: WorkbenchTab = rawTab && VALID_TABS.has(rawTab) ? rawTab : 'today'
  const rawCat = params.get('cat') as CategoryKey | null
  const cat: CategoryKey = rawCat && VALID_CATEGORIES.has(rawCat) ? rawCat : 'finance'
  const rawEvidence = params.get('evidence') || 'all'
  const evidence = (VALID_EVIDENCE.has(rawEvidence) ? rawEvidence : 'all') as 'all' | EvidenceStatus
  const scope = params.get('scope') === 'all' ? 'all' : 'current'
  const rawFresh = params.get('fresh') || (params.get('unread') === '1' ? 'unread' : 'all')
  const fresh = (VALID_FRESH.has(rawFresh) ? rawFresh : 'all') as FreshnessBucket

  return {
    tab,
    cat,
    history: sanitizeHistoryParam(params.get('history')),
    event: params.get('event')?.trim() || null,
    story: params.get('story')?.trim() || null,
    entity: params.get('entity')?.trim() || null,
    q: params.get('q') || '',
    scope,
    source: params.get('source') || 'all',
    evidence,
    unread: params.get('unread') === '1',
    fresh,
  }
}

export function buildBriefingUrl(
  state: BriefingUrlState,
  pathname = typeof window !== 'undefined' ? window.location.pathname : 'index.html',
): string {
  const params = new URLSearchParams()
  if (state.tab !== 'today') params.set('tab', state.tab)
  if (state.cat !== 'finance') params.set('cat', state.cat)
  if (state.history) params.set('history', state.history)
  if (state.event) params.set('event', state.event)
  if (state.story) params.set('story', state.story)
  if (state.entity) params.set('entity', state.entity)
  if (state.q.trim()) params.set('q', state.q.trim())
  if (state.scope === 'all') params.set('scope', 'all')
  if (state.source && state.source !== 'all') params.set('source', state.source)
  if (state.evidence !== 'all') params.set('evidence', state.evidence)
  if (state.unread) params.set('unread', '1')
  if (state.fresh && state.fresh !== 'all') params.set('fresh', state.fresh)

  const qs = params.toString()
  if (typeof window !== 'undefined') {
    const curParams = new URLSearchParams(window.location.search)
    const appFlag = curParams.get('app')
    if (appFlag === 'android') {
      params.set('app', 'android')
    }
  }
  const finalQs = params.toString()
  return finalQs ? `${pathname}?${finalQs}` : pathname
}

export function parseMonitorUrlState(search = typeof window !== 'undefined' ? window.location.search : ''): MonitorUrlState {
  const params = new URLSearchParams(search)
  const rawCat = params.get('cat')
  let cat: CategoryKey | 'favorites' = 'finance'
  if (rawCat === 'favorites') {
    cat = 'favorites'
  } else if (rawCat && VALID_CATEGORIES.has(rawCat as CategoryKey)) {
    cat = rawCat as CategoryKey
  }

  const rawView = params.get('view')
  const view: MonitorViewMode =
    rawView === 'matrix' || rawView === 'health' || rawView === 'connectors' || rawView === 'radar'
      ? rawView
      : 'stream'

  const rawHealth = params.get('health')
  const health = rawHealth === 'ok' || rawHealth === 'issue' ? rawHealth : 'all'

  return {
    cat,
    history: sanitizeHistoryParam(params.get('history')),
    view,
    q: params.get('q') || '',
    source: params.get('source') || 'all',
    health,
  }
}

export function buildMonitorUrl(
  state: MonitorUrlState,
  pathname = typeof window !== 'undefined' ? window.location.pathname : 'monitor.html',
): string {
  const params = new URLSearchParams()
  if (state.cat !== 'finance') params.set('cat', state.cat)
  if (state.history) params.set('history', state.history)
  if (state.view !== 'stream') params.set('view', state.view)
  if (state.q.trim()) params.set('q', state.q.trim())
  if (state.source && state.source !== 'all') params.set('source', state.source)
  if (state.health !== 'all') params.set('health', state.health)

  const qs = params.toString()
  if (typeof window !== 'undefined') {
    const curParams = new URLSearchParams(window.location.search)
    const appFlag = curParams.get('app')
    if (appFlag === 'android') {
      params.set('app', 'android')
    }
  }
  const finalQs = params.toString()
  return finalQs ? `${pathname}?${finalQs}` : pathname
}

export function syncUrlToBrowser(url: string, replace = false): void {
  if (typeof window === 'undefined' || !window.history) return
  const current = `${window.location.pathname}${window.location.search}`
  if (current === url) return
  if (replace) {
    window.history.replaceState(null, '', url)
  } else {
    window.history.pushState(null, '', url)
  }
}
