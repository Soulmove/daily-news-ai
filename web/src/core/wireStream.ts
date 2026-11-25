import { getApiBase } from './auth'
import { resolveDataUrl } from './dataBase'
import type { AiProgressDoc, LiveWireDoc } from './types'

export type WireTransportMode = 'sse' | 'polling' | 'paused'

export interface LiveWireStreamHandle {
  seedFromDoc: (doc: LiveWireDoc | null) => void
  seedAiFromDoc: (doc: AiProgressDoc | null) => void
  stop: () => void
  getMode: () => WireTransportMode
}

export interface LiveWireStreamOptions {
  onUpdate: (doc: LiveWireDoc, newIds: string[]) => void
  onAiUpdate?: (doc: AiProgressDoc, newIds: string[]) => void
  onTransportChange?: (mode: WireTransportMode) => void
  fetchStaticFallback?: () => Promise<LiveWireDoc | null>
  fetchAiFallback?: () => Promise<AiProgressDoc | null>
  getAuthToken?: () => string | null
  sseUrl?: string
  pollUrl?: string
  aiPollUrl?: string
  pollIntervalMs?: number
  enableSse?: boolean
}

export function createLiveWireController(opts: LiveWireStreamOptions): LiveWireStreamHandle {
  const apiBase = getApiBase()
  const sseUrl = opts.sseUrl ?? `${apiBase}/api/wire/stream`
  const pollUrl = opts.pollUrl ?? `${apiBase}/api/wire/latest`
  const aiPollUrl = opts.aiPollUrl ?? `${apiBase}/api/ai-progress/latest`
  const pollIntervalMs = Math.max(15_000, opts.pollIntervalMs ?? 45_000)
  const enableSse = opts.enableSse ?? false

  let stopped = false
  let mode: WireTransportMode = 'polling'
  let source: EventSource | null = null
  let pollTimer: ReturnType<typeof setInterval> | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null

  let hasSeededWire = false
  let lastWireSig = ''
  const knownWireIds = new Set<string>()

  let hasSeededAi = false
  let lastAiSig = ''
  const knownAiIds = new Set<string>()

  function setMode(next: WireTransportMode) {
    if (mode !== next) {
      mode = next
      opts.onTransportChange?.(next)
    }
  }

  function computeWireSig(doc: LiveWireDoc): string {
    const items = doc.items || []
    return `${doc.updated_at || ''}|${items
      .slice(0, 15)
      .map((i) => `${i.id}:${i.published_at}`)
      .join(',')}`
  }

  function computeAiSig(doc: AiProgressDoc): string {
    const tl = doc.timeline || []
    return `${doc.live_updated_at || doc.generated_at || ''}|${tl
      .slice(0, 20)
      .map((i) => `${i.id}:${i.date}:${i.is_first_hand ? '1' : '0'}`)
      .join(',')}`
  }

  function applyWireDoc(doc: LiveWireDoc | null | undefined, fromSeed = false) {
    if (!doc || !Array.isArray(doc.items)) return
    const incomingIds = doc.items.map((it) => it.id).filter(Boolean)
    const newIds: string[] = []
    if (!fromSeed && hasSeededWire) {
      for (const id of incomingIds) {
        if (!knownWireIds.has(id)) newIds.push(id)
      }
    }
    for (const id of incomingIds) knownWireIds.add(id)
    hasSeededWire = true

    const sig = computeWireSig(doc)
    if (!fromSeed && sig !== lastWireSig) {
      lastWireSig = sig
      opts.onUpdate(doc, newIds)
    } else if (fromSeed) {
      lastWireSig = sig
    }
  }

  function applyAiDoc(doc: AiProgressDoc | null | undefined, fromSeed = false) {
    if (!doc || !Array.isArray(doc.timeline)) return
    const incomingIds = doc.timeline.map((it) => it.id).filter(Boolean)
    const newIds: string[] = []
    if (!fromSeed && hasSeededAi) {
      for (const id of incomingIds) {
        if (!knownAiIds.has(id)) newIds.push(id)
      }
    }
    for (const id of incomingIds) knownAiIds.add(id)
    hasSeededAi = true

    const sig = computeAiSig(doc)
    if (!fromSeed && sig !== lastAiSig) {
      lastAiSig = sig
      opts.onAiUpdate?.(doc, newIds)
    } else if (fromSeed) {
      lastAiSig = sig
    }
  }

  async function fetchJsonNoStore<T>(url: string): Promise<T | null> {
    if (typeof fetch === 'undefined') return null
    try {
      const headers: Record<string, string> = { Accept: 'application/json' }
      const token = opts.getAuthToken?.()
      if (token) headers.Authorization = `Bearer ${token}`
      const resp = await fetch(`${url}${url.includes('?') ? '&' : '?'}_t=${Date.now()}`, {
        cache: 'no-store',
        headers,
      })
      if (!resp.ok) return null
      return (await resp.json()) as T
    } catch {
      return null
    }
  }

  async function pollOnce() {
    if (stopped) return
    if (typeof document !== 'undefined' && document.hidden) return

    let wireDoc = await fetchJsonNoStore<LiveWireDoc>(pollUrl)
    if ((!wireDoc || !Array.isArray(wireDoc.items)) && opts.fetchStaticFallback) {
      try {
        wireDoc = await opts.fetchStaticFallback()
      } catch {
        wireDoc = null
      }
    }
    if (!wireDoc || !Array.isArray(wireDoc.items)) {
      wireDoc = await fetchJsonNoStore<LiveWireDoc>(resolveDataUrl('data/live_wire.json', true))
    }
    if (!stopped && wireDoc) applyWireDoc(wireDoc, false)

    if (!stopped && opts.onAiUpdate) {
      let aiDoc = await fetchJsonNoStore<AiProgressDoc>(aiPollUrl)
      if ((!aiDoc || !Array.isArray(aiDoc.timeline)) && opts.fetchAiFallback) {
        try {
          aiDoc = await opts.fetchAiFallback()
        } catch {
          aiDoc = null
        }
      }
      if (!aiDoc || !Array.isArray(aiDoc.timeline)) {
        aiDoc = await fetchJsonNoStore<AiProgressDoc>(resolveDataUrl('data/ai_progress.json', true))
      }
      if (!stopped && aiDoc) applyAiDoc(aiDoc, false)
    }
  }

  function startPolling() {
    if (stopped || pollTimer) return
    setMode('polling')
    void pollOnce()
    pollTimer = setInterval(() => {
      void pollOnce()
    }, pollIntervalMs)
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  function closeSse() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (source) {
      source.close()
      source = null
    }
  }

  function connectSse() {
    if (stopped) return
    if (!enableSse || typeof window === 'undefined' || typeof EventSource === 'undefined') {
      startPolling()
      return
    }
    if (window.location.hostname.endsWith('github.io')) {
      startPolling()
      return
    }
    closeSse()
    try {
      const es = new EventSource(sseUrl)
      source = es
      es.addEventListener('open', () => {
        stopPolling()
        setMode('sse')
      })
      es.addEventListener('wire', (evt) => {
        try {
          const parsed = JSON.parse((evt as MessageEvent<string>).data) as LiveWireDoc
          applyWireDoc(parsed, false)
        } catch {
          // Ignore malformed SSE payload
        }
      })
      es.addEventListener('ai_progress', (evt) => {
        try {
          const parsed = JSON.parse((evt as MessageEvent<string>).data) as AiProgressDoc
          applyAiDoc(parsed, false)
        } catch {
          // Ignore malformed SSE payload
        }
      })
      es.addEventListener('error', () => {
        closeSse()
        if (stopped) return
        startPolling()
        reconnectTimer = setTimeout(() => {
          if (!stopped && !(typeof document !== 'undefined' && document.hidden)) {
            connectSse()
          }
        }, 20_000)
      })
    } catch {
      startPolling()
    }
  }

  function onVisibilityChange() {
    if (stopped || typeof document === 'undefined') return
    if (document.hidden) {
      closeSse()
      stopPolling()
      setMode('paused')
    } else {
      void pollOnce()
      connectSse()
    }
  }

  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', onVisibilityChange)
  }

  connectSse()

  return {
    seedFromDoc: (doc) => applyWireDoc(doc, true),
    seedAiFromDoc: (doc) => applyAiDoc(doc, true),
    getMode: () => mode,
    stop: () => {
      stopped = true
      closeSse()
      stopPolling()
      if (typeof document !== 'undefined') {
        document.removeEventListener('visibilitychange', onVisibilityChange)
      }
    },
  }
}
