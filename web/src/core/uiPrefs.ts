import { ref, watch } from 'vue'
import { appLang, type AppLang } from './i18n'

export type FeedDensity = 'compact' | 'standard'
export type MarketColorMode = 'auto' | 'cn' | 'intl'

const DENSITY_KEY = 'infofocus_feed_density_v1'
const WIRE_READ_KEY = 'infofocus_wire_read_ids_v1'
const MARKET_COLOR_KEY = 'infofocus_market_color_v1'

function readStoredMarketColorMode(): MarketColorMode {
  if (typeof window === 'undefined') return 'auto'
  try {
    const raw = window.localStorage.getItem(MARKET_COLOR_KEY)
    if (raw === 'cn' || raw === 'intl') return raw
  } catch {
    // Ignore storage errors
  }
  return 'auto'
}

export function isRedUp(lang: AppLang = appLang.value): boolean {
  if (marketColorMode.value === 'cn') return true
  if (marketColorMode.value === 'intl') return false
  return lang === 'zh'
}

export function syncMarketColorDomAttr(lang: AppLang = appLang.value): void {
  if (typeof document !== 'undefined') {
    document.documentElement.dataset.marketColor = isRedUp(lang) ? 'cn' : 'intl'
  }
}

export const marketColorMode = ref<MarketColorMode>(readStoredMarketColorMode())

export function setMarketColorMode(mode: MarketColorMode): void {
  marketColorMode.value = mode
  if (typeof window !== 'undefined') {
    try {
      window.localStorage.setItem(MARKET_COLOR_KEY, mode)
    } catch {
      // Ignore storage quota errors
    }
  }
  syncMarketColorDomAttr()

watch(appLang, (nextLang) => {
  syncMarketColorDomAttr(nextLang)
})
}

export function toggleMarketColorMode(): MarketColorMode {
  const next: MarketColorMode = isRedUp() ? 'intl' : 'cn'
  setMarketColorMode(next)
  return next
}

syncMarketColorDomAttr()

watch(appLang, (nextLang) => {
  syncMarketColorDomAttr(nextLang)
})

export function marketUpTextClass(): string {
  return isRedUp() ? 'text-rose-600 dark:text-rose-400' : 'text-emerald-600 dark:text-emerald-400'
}

export function marketDownTextClass(): string {
  return isRedUp() ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'
}

export function marketUpBadgeClass(): string {
  return isRedUp()
    ? 'bg-rose-500/12 text-rose-600 dark:bg-rose-400/15 dark:text-rose-300'
    : 'bg-emerald-500/12 text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-300'
}

export function marketDownBadgeClass(): string {
  return isRedUp()
    ? 'bg-emerald-500/12 text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-300'
    : 'bg-rose-500/12 text-rose-600 dark:bg-rose-400/15 dark:text-rose-300'
}

export function marketUpBarBgClass(): string {
  return isRedUp() ? 'bg-rose-500' : 'bg-emerald-500'
}

export function marketDownBarBgClass(): string {
  return isRedUp() ? 'bg-emerald-500' : 'bg-rose-500'
}

export function marketUpActiveBtnClass(): string {
  return isRedUp() ? 'bg-rose-600 text-white' : 'bg-emerald-600 text-white'
}

export function marketDownActiveBtnClass(): string {
  return isRedUp() ? 'bg-emerald-600 text-white' : 'bg-rose-600 text-white'
}

function readStoredDensity(): FeedDensity {
  if (typeof window === 'undefined') return 'compact'
  try {
    const raw = window.localStorage.getItem(DENSITY_KEY)
    return raw === 'standard' ? 'standard' : 'compact'
  } catch {
    return 'compact'
  }
}

export const feedDensity = ref<FeedDensity>(readStoredDensity())

export function setFeedDensity(next: FeedDensity): void {
  feedDensity.value = next
  if (typeof window !== 'undefined') {
    try {
      window.localStorage.setItem(DENSITY_KEY, next)
    } catch {
      // Ignore storage quota errors
    }
  }
}

export function toggleFeedDensity(): void {
  setFeedDensity(feedDensity.value === 'compact' ? 'standard' : 'compact')
}

function readStoredWireReadIds(): Set<string> {
  if (typeof window === 'undefined') return new Set()
  try {
    const raw = window.localStorage.getItem(WIRE_READ_KEY)
    if (!raw) return new Set()
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed)) {
      return new Set(parsed.filter((x): x is string => typeof x === 'string').slice(-600))
    }
  } catch {
    // Ignore corrupt JSON
  }
  return new Set()
}

export const wireReadIdSet = ref<Set<string>>(readStoredWireReadIds())

function persistWireReadIds(): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(WIRE_READ_KEY, JSON.stringify([...wireReadIdSet.value].slice(-600)))
  } catch {
    // Ignore storage quota errors
  }
}

export function markWireRead(id: string): void {
  if (!id || wireReadIdSet.value.has(id)) return
  const next = new Set(wireReadIdSet.value)
  next.add(id)
  wireReadIdSet.value = next
  persistWireReadIds()
}

export function markAllWireRead(ids: string[]): void {
  const next = new Set(wireReadIdSet.value)
  let changed = false
  for (const id of ids) {
    if (id && !next.has(id)) {
      next.add(id)
      changed = true
    }
  }
  if (changed) {
    wireReadIdSet.value = next
    persistWireReadIds()
  }
}

// Reference-counted body scroll lock to prevent background scroll bleed when drawers/modals open
let _scrollLockCount = 0
let _prevOverflow = ''

export function lockBodyScroll(): void {
  if (typeof document === 'undefined') return
  if (_scrollLockCount === 0) {
    _prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
  }
  _scrollLockCount += 1
}

export function unlockBodyScroll(): void {
  if (typeof document === 'undefined') return
  if (_scrollLockCount <= 0) return
  _scrollLockCount -= 1
  if (_scrollLockCount === 0) {
    document.body.style.overflow = _prevOverflow
  }
}

export function triggerHaptic(durationMs = 10): void {
  if (typeof navigator === 'undefined') return
  try {
    if (typeof navigator.vibrate === 'function') {
      navigator.vibrate(durationMs)
    }
  } catch {
    // Ignore unsupported or blocked haptics
  }
}
