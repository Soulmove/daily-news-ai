import { reactive } from 'vue'
import { apiPresenceLeave, apiPresencePing, type PresencePingResponse } from './auth'
import { isAndroidAppShell } from './mobilePush'

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
let simDriftTimer: ReturnType<typeof setInterval> | null = null
let activeDriftSig = ''
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

function clearSimDriftTimer() {
  if (simDriftTimer) {
    clearInterval(simDriftTimer)
    simDriftTimer = null
  }
  activeDriftSig = ''
}

function applyPresenceResponse(res: PresencePingResponse) {
  presenceState.enabled = Boolean(res.enabled)
  presenceState.label = res.label || '在线'
  presenceState.mode = res.mode === 'simulated' ? 'simulated' : 'real'
  presenceState.loaded = true

  if (!res.enabled) {
    presenceState.count = 0
    clearSimDriftTimer()
    return
  }

  if (res.mode === 'simulated' && res.sim_drift) {
    const { base, delta, interval_sec } = res.sim_drift
    const sig = `${base}:${delta}:${interval_sec}`
    presenceState.count = computeSimulatedOnlineCount(base, delta, interval_sec, Date.now())
    if (sig !== activeDriftSig) {
      clearSimDriftTimer()
      activeDriftSig = sig
      const stepMs = Math.max(3000, Math.min(300_000, interval_sec * 1000))
      simDriftTimer = setInterval(() => {
        if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return
        presenceState.count = computeSimulatedOnlineCount(base, delta, interval_sec, Date.now())
      }, stepMs)
    }
  } else {
    clearSimDriftTimer()
    presenceState.count = Math.max(0, Math.round(Number(res.count ?? 0)))
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

function onVisibilityChange() {
  if (typeof document === 'undefined') return
  if (document.visibilityState === 'hidden') {
    lastHiddenAtMs = Date.now()
    return
  }
  const hiddenDuration = lastHiddenAtMs !== null ? Date.now() - lastHiddenAtMs : 0
  lastHiddenAtMs = null
  const countAsNewVisit = hiddenDuration >= 10 * 60_000
  void triggerPresenceHeartbeat(countAsNewVisit)
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
  const isFirstStart = !trackingStarted
  trackingStarted = true
  void triggerPresenceHeartbeat(isFirstStart)

  if (!heartbeatTimer) {
    heartbeatTimer = setInterval(() => {
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return
      void triggerPresenceHeartbeat(false)
    }, 45_000)
  }

  if (typeof window !== 'undefined' && !listenersBound) {
    listenersBound = true
    document.addEventListener('visibilitychange', onVisibilityChange)
    window.addEventListener('pagehide', onPageHide)
  }
}

export function stopPresenceTracking(): void {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer)
    heartbeatTimer = null
  }
  clearSimDriftTimer()
  trackingStarted = false
  if (typeof window !== 'undefined' && listenersBound) {
    listenersBound = false
    document.removeEventListener('visibilitychange', onVisibilityChange)
    window.removeEventListener('pagehide', onPageHide)
  }
}
