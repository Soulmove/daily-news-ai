import { reactive } from 'vue'
import { apiPresenceLeave, apiPresencePing, apiPresenceStatus, type PresencePingResponse } from './auth'
import { isAndroidAppShell } from './mobilePush'

export const PRESENCE_CONFIG_SYNC_KEY = 'mirrorbrief_presence_sync_ts'
export const PRESENCE_CACHE_KEY = 'mirrorbrief_presence_cache_v1'

const HEARTBEAT_INTERVAL_MS = 50_000
const STATUS_POLL_INTERVAL_MS = 25_000
const IDLE_SLEEP_MS = 10 * 60_000

export interface PresenceClientState {
  enabled: boolean
  count: number
  label: string
  loaded: boolean
  mode: 'real' | 'simulated'
}

export const presenceState = reactive<PresenceClientState>({
  enabled: true,
  count: 0,
  label: '在线',
  loaded: false,
  mode: 'real',
})

function hashSlot(n: number): number {
  let x = (n | 0) + 0x9e3779b9
  x = Math.imul(x ^ (x >>> 16), 0x85ebca6b)
  x = Math.imul(x ^ (x >>> 13), 0xc2b2ae35)
  x = (x ^ (x >>> 16)) >>> 0
  return x / 4294967296
}

/**
 * Deterministic smooth mean-reverting random walk matching worker/src/presence.ts.
 */
export function computeSimulatedOnlineCount(
  base: number,
  delta: number,
  intervalSec: number,
  nowMs = Date.now(),
): number {
  const cleanBase = Math.max(1, Math.round(Number.isFinite(base) ? base : 68))
  const cleanDelta = Math.max(0, Math.round(Number.isFinite(delta) ? delta : 12))
  const cleanInterval = Math.max(3, Math.min(300, Math.round(Number.isFinite(intervalSec) ? intervalSec : 12)))
  if (cleanDelta === 0) return cleanBase
  const lo = Math.max(1, cleanBase - cleanDelta)
  const hi = Math.max(lo, cleanBase + cleanDelta)
  const slot = Math.floor(nowMs / (cleanInterval * 1000))
  let val = cleanBase
  const maxStep = Math.max(1, Math.min(cleanDelta, Math.ceil(cleanDelta * 0.25)))
  for (let s = slot - 24; s <= slot; s++) {
    const pull = (cleanBase - val) / Math.max(1, cleanDelta)
    const r = hashSlot(s) * 2 - 1 + pull * 0.45
    let step = Math.round(r * maxStep)
    if (step === 0) {
      step = r >= 0 ? 1 : -1
    }
    val = Math.max(lo, Math.min(hi, val + step))
  }
  return val
}

let heartbeatTimer: ReturnType<typeof setInterval> | null = null
let statusPollTimer: ReturnType<typeof setInterval> | null = null
let simDriftTimer: ReturnType<typeof setInterval> | null = null
let activeDriftSig = ''
let serverClockOffsetMs = 0
let lastSyncAtMs = 0
let lastActivityAtMs = Date.now()
let currentTokenGetter: () => string | null = () => null
let currentTabGetter: () => string = () => 'today'
let lastHiddenAtMs: number | null = null
let trackingStarted = false
let listenersBound = false

function detectClientPlatform(): 'desktop' | 'mobile' | 'android' {
  if (isAndroidAppShell()) return 'android'
  if (typeof window !== 'undefined' && window.innerWidth < 768) return 'mobile'
  return 'desktop'
}

function isClientActive(): boolean {
  if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return false
  return Date.now() - lastActivityAtMs < IDLE_SLEEP_MS
}

function clearSimDriftTimer() {
  if (simDriftTimer) {
    clearInterval(simDriftTimer)
    simDriftTimer = null
  }
  activeDriftSig = ''
}

function applyPresenceResponse(res: PresencePingResponse, fromBroadcast = false) {
  lastSyncAtMs = Date.now()
  if (typeof res.server_time_ms === 'number' && Number.isFinite(res.server_time_ms)) {
    serverClockOffsetMs = res.server_time_ms - Date.now()
  }
  presenceState.enabled = Boolean(res.enabled)
  presenceState.label = res.label || '在线'
  presenceState.mode = res.mode === 'simulated' ? 'simulated' : 'real'
  presenceState.loaded = true

  if (!fromBroadcast) {
    try {
      if (typeof window !== 'undefined' && window.localStorage) {
        window.localStorage.setItem(PRESENCE_CACHE_KEY, JSON.stringify({ ts: lastSyncAtMs, res }))
      }
    } catch {
      // Ignore storage errors
    }
  }

  if (!res.enabled) {
    presenceState.count = 0
    clearSimDriftTimer()
    return
  }

  if (res.mode === 'simulated' && res.sim_drift) {
    const { base, delta, interval_sec } = res.sim_drift
    const sig = `${base}:${delta}:${interval_sec}`
    presenceState.count = computeSimulatedOnlineCount(
      base,
      delta,
      interval_sec,
      Date.now() + serverClockOffsetMs,
    )
    if (sig !== activeDriftSig) {
      clearSimDriftTimer()
      activeDriftSig = sig
      // Check every 1s with zero network requests so transitions happen cleanly on the exact interval_sec slot
      simDriftTimer = setInterval(() => {
        if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return
        const nextCount = computeSimulatedOnlineCount(
          base,
          delta,
          interval_sec,
          Date.now() + serverClockOffsetMs,
        )
        if (nextCount !== presenceState.count) {
          presenceState.count = nextCount
        }
      }, 1_000)
    }
  } else {
    clearSimDriftTimer()
    presenceState.count = Math.max(0, Math.round(Number(res.count ?? 0)))
  }
}

export async function refreshPresenceStatusNow(): Promise<void> {
  try {
    const res = await apiPresenceStatus()
    if (res && typeof res.count === 'number') {
      applyPresenceResponse(res)
    }
  } catch {
    // Silent fallback
  }
}

export async function triggerPresenceHeartbeat(isVisit = false): Promise<void> {
  try {
    const res = await apiPresencePing(
      {
        is_visit: isVisit,
        platform: detectClientPlatform(),
        tab: currentTabGetter(),
      },
      currentTokenGetter(),
    )
    if (res && typeof res.count === 'number') {
      applyPresenceResponse(res)
    }
  } catch {
    // Silent fallback — never block UI if telemetry fails
  }
}

export function broadcastPresenceConfigChange(): void {
  try {
    if (typeof window !== 'undefined' && window.localStorage) {
      window.localStorage.setItem(PRESENCE_CONFIG_SYNC_KEY, String(Date.now()))
    }
  } catch {
    // Ignore storage quota/sandbox errors
  }
}

function recordUserActivity() {
  const now = Date.now()
  if (now - lastActivityAtMs < 15_000) return
  const wasIdle = now - lastActivityAtMs >= IDLE_SLEEP_MS
  lastActivityAtMs = now
  if (wasIdle) {
    void triggerPresenceHeartbeat(false)
  }
}

function onVisibilityChange() {
  if (typeof document === 'undefined') return
  if (document.visibilityState === 'hidden') {
    lastHiddenAtMs = Date.now()
    return
  }
  lastActivityAtMs = Date.now()
  const hiddenDuration = lastHiddenAtMs !== null ? Date.now() - lastHiddenAtMs : 0
  lastHiddenAtMs = null
  const countAsNewVisit = hiddenDuration >= 10 * 60_000
  void triggerPresenceHeartbeat(countAsNewVisit)
}

function onWindowFocus() {
  lastActivityAtMs = Date.now()
  if (Date.now() - lastSyncAtMs < 5_000) return
  void refreshPresenceStatusNow()
}

function onStorageSync(e: StorageEvent) {
  if (e.key === PRESENCE_CONFIG_SYNC_KEY) {
    void refreshPresenceStatusNow()
    return
  }
  if (e.key === PRESENCE_CACHE_KEY && e.newValue) {
    try {
      const parsed = JSON.parse(e.newValue) as { ts?: number; res?: PresencePingResponse }
      if (parsed?.res && typeof parsed.res.count === 'number') {
        applyPresenceResponse(parsed.res, true)
      }
    } catch {
      // Ignore malformed cache payload
    }
  }
}

function onPageHide() {
  apiPresenceLeave()
}

export function startPresenceTracking(opts: {
  getToken: () => string | null
  getTab: () => string
}): void {
  currentTokenGetter = opts.getToken
  currentTabGetter = opts.getTab
  lastActivityAtMs = Date.now()

  // Seed instant UI display from shared tab cache before initial ping completes
  try {
    if (typeof window !== 'undefined' && window.localStorage) {
      const raw = window.localStorage.getItem(PRESENCE_CACHE_KEY)
      if (raw) {
        const parsed = JSON.parse(raw) as { ts?: number; res?: PresencePingResponse }
        if (parsed?.res && typeof parsed.ts === 'number' && Date.now() - parsed.ts < 60_000) {
          applyPresenceResponse(parsed.res, true)
        }
      }
    }
  } catch {
    // Ignore
  }

  const isFirstStart = !trackingStarted
  trackingStarted = true
  void triggerPresenceHeartbeat(isFirstStart)

  if (!heartbeatTimer) {
    heartbeatTimer = setInterval(() => {
      if (!isClientActive()) return
      void triggerPresenceHeartbeat(false)
    }, HEARTBEAT_INTERVAL_MS)
  }

  if (!statusPollTimer) {
    statusPollTimer = setInterval(() => {
      if (!isClientActive()) return
      if (Date.now() - lastSyncAtMs < 20_000) return
      void refreshPresenceStatusNow()
    }, STATUS_POLL_INTERVAL_MS)
  }

  if (typeof window !== 'undefined' && !listenersBound) {
    listenersBound = true
    document.addEventListener('visibilitychange', onVisibilityChange)
    window.addEventListener('focus', onWindowFocus)
    window.addEventListener('storage', onStorageSync)
    window.addEventListener('pagehide', onPageHide)
    window.addEventListener('pointerdown', recordUserActivity, { passive: true })
    window.addEventListener('keydown', recordUserActivity, { passive: true })
    window.addEventListener('scroll', recordUserActivity, { passive: true })
  }
}

export function stopPresenceTracking(): void {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer)
    heartbeatTimer = null
  }
  if (statusPollTimer) {
    clearInterval(statusPollTimer)
    statusPollTimer = null
  }
  clearSimDriftTimer()
  trackingStarted = false
  if (typeof window !== 'undefined' && listenersBound) {
    listenersBound = false
    document.removeEventListener('visibilitychange', onVisibilityChange)
    window.removeEventListener('focus', onWindowFocus)
    window.removeEventListener('storage', onStorageSync)
    window.removeEventListener('pagehide', onPageHide)
    window.removeEventListener('pointerdown', recordUserActivity)
    window.removeEventListener('keydown', recordUserActivity)
    window.removeEventListener('scroll', recordUserActivity)
  }
}
