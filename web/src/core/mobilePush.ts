function safeStorageGet(key: string): string | null {
  try {
    if (typeof window !== 'undefined' && window.localStorage) {
      return window.localStorage.getItem(key)
    }
  } catch {
    // Ignore storage access restrictions
  }
  return null
}

function safeStorageSet(key: string, value: string): void {
  try {
    if (typeof window !== 'undefined' && window.localStorage) {
      window.localStorage.setItem(key, value)
    }
  } catch {
    // Ignore storage access restrictions
  }
}

function safeStorageRemove(key: string): void {
  try {
    if (typeof window !== 'undefined') {
      window.localStorage?.removeItem(key)
      window.sessionStorage?.removeItem(key)
    }
  } catch {
    // Ignore storage access restrictions
  }
}

function safeSessionGet(key: string): string | null {
  try {
    if (typeof window !== 'undefined' && window.sessionStorage) {
      return window.sessionStorage.getItem(key)
    }
  } catch {
    // Ignore sessionStorage restrictions
  }
  return null
}

function safeSessionSet(key: string, value: string): void {
  try {
    if (typeof window !== 'undefined' && window.sessionStorage) {
      window.sessionStorage.setItem(key, value)
    }
  } catch {
    // Ignore sessionStorage restrictions
  }
}

function emitDevBridgeTelemetry(method: string, args: unknown[]): void {
  try {
    if (typeof window !== 'undefined' && window.parent && window.parent !== window) {
      window.parent.postMessage(
        {
          type: 'infofocus-android-bridge',
          method,
          args,
          timestamp: new Date().toISOString(),
        },
        window.location.origin,
      )
    }
  } catch {
    // Ignore cross-origin postMessage restrictions
  }
}

export interface InfoFocusAndroidBridge {
  notify(title: string, body: string, url?: string): void
  setPushEnabled?(enabled: boolean): void
  isPushEnabled?(): boolean
  requestPermission?(): void
  setTheme?(isDark: boolean): void
}

export function syncAndroidStatusBarTheme(isDark: boolean): void {
  emitDevBridgeTelemetry('setTheme', [isDark])
  const bridge = typeof window !== 'undefined' ? window.InfoFocusAndroid : undefined
  try {
    bridge?.setTheme?.(isDark)
  } catch {
    // Ignore when bridge doesn't expose setTheme
  }
}

declare global {
  interface Window {
    InfoFocusAndroid?: InfoFocusAndroidBridge
  }
}

const PUSH_PREF_KEY = 'infofocus_mobile_push_v1'

const _notifiedIds = new Set<string>()

export function clearAndroidAppShellFlag(): void {
  safeStorageRemove('infofocus_app_shell_flag')
  if (typeof document !== 'undefined') {
    document.documentElement.classList.remove('android-shell')
  }
}

function syncAndroidShellClass(active: boolean): boolean {
  if (typeof document !== 'undefined') {
    document.documentElement.classList.toggle('android-shell', active)
  }
  return active
}

export function buildAndroidDebugUrl(
  tab = 'today',
  mode: 'android' | 'web' = 'android',
  pathname = './index.html',
): string {
  const params = new URLSearchParams()
  if (tab && tab !== 'today') params.set('tab', tab)
  params.set('app', mode)
  return `${pathname}?${params.toString()}`
}

export function isAndroidAppShell(): boolean {
  if (typeof window === 'undefined') return false
  if (/InfoFocusAndroid/i.test(navigator.userAgent || '')) return syncAndroidShellClass(true)
  try {
    const params = new URLSearchParams(window.location.search)
    const appParam = params.get('app')
    if (appParam === 'web') {
      safeStorageRemove('infofocus_app_shell_flag')
      return syncAndroidShellClass(false)
    }
    const isInsideIframe = window.self !== window.top
    if (appParam === 'android') {
      if (isInsideIframe) {
        safeSessionSet('infofocus_app_shell_flag', 'android')
      } else {
        safeStorageSet('infofocus_app_shell_flag', 'android')
      }
      return syncAndroidShellClass(true)
    }
    // Never let a stale localStorage android flag leak mobile bottom nav onto desktop/tablet (>=768px)
    const isDesktopViewport = window.innerWidth >= 768 && !isInsideIframe
    if (isDesktopViewport) {
      return syncAndroidShellClass(false)
    }
    if (safeSessionGet('infofocus_app_shell_flag') === 'android') return syncAndroidShellClass(true)
    if (!isInsideIframe && safeStorageGet('infofocus_app_shell_flag') === 'android') return syncAndroidShellClass(true)
  } catch {
    // Ignore URL/storage edge errors
  }
  return syncAndroidShellClass(Boolean(window.InfoFocusAndroid))
}

export function getApkDownloadUrl(): string {
  return ''
}

export function isImportantPushEnabled(): boolean {
  const bridge = typeof window !== 'undefined' ? window.InfoFocusAndroid : undefined
  if (bridge && typeof bridge.isPushEnabled === 'function') {
    try {
      return Boolean(bridge.isPushEnabled())
    } catch {
      // Fallback to storage
    }
  }
  const raw = safeStorageGet(PUSH_PREF_KEY)
  if (raw === null) {
    // Native Android app defaults push alerts ON
    return isAndroidAppShell()
  }
  return raw === '1'
}

export async function setImportantPushEnabledWithStatus(
  enabled: boolean,
): Promise<{ enabled: boolean; permission: NotificationPermission | 'unsupported' }> {
  safeStorageSet(PUSH_PREF_KEY, enabled ? '1' : '0')
  emitDevBridgeTelemetry('setPushEnabled', [enabled])
  const bridge = typeof window !== 'undefined' ? window.InfoFocusAndroid : undefined
  if (bridge) {
    try {
      if (enabled && typeof bridge.requestPermission === 'function') {
        emitDevBridgeTelemetry('requestPermission', [])
        bridge.requestPermission()
      }
      bridge.setPushEnabled?.(enabled)
    } catch {
      // Ignore bridge runtime issues
    }
    return { enabled, permission: 'granted' }
  }
  let permission: NotificationPermission | 'unsupported' = 'unsupported'
  if (typeof window !== 'undefined' && 'Notification' in window) {
    permission = Notification.permission
    if (enabled && permission === 'default') {
      try {
        permission = await Notification.requestPermission()
      } catch {
        // Decoupled: never roll back saved in-app push preference when browser blocks prompt
      }
    }
  }
  return { enabled, permission }
}

export async function setImportantPushEnabled(enabled: boolean): Promise<boolean> {
  const res = await setImportantPushEnabledWithStatus(enabled)
  return res.enabled
}

export interface PushAlertPayload {
  id: string
  title: string
  body: string
  tab?: 'wire' | 'ai_progress' | 'today'
}

export function shouldDispatchAlertForId(id: string): boolean {
  if (!id || _notifiedIds.has(id)) return false
  _notifiedIds.add(id)
  if (_notifiedIds.size > 400) {
    const oldest = _notifiedIds.values().next().value
    if (oldest) _notifiedIds.delete(oldest)
  }
  return true
}

export function dispatchImportantNewsNotification(payload: PushAlertPayload): boolean {
  if (!isImportantPushEnabled()) return false
  if (!shouldDispatchAlertForId(payload.id)) return false

  const targetTab = payload.tab || 'wire'
  const originBase =
    typeof window !== 'undefined' && window.location?.origin && window.location.origin.startsWith('http')
      ? window.location.origin
      : 'https://mirrorinfo.xyz'
  const deepUrl = `${originBase}/index.html?app=android&tab=${targetTab}`
  emitDevBridgeTelemetry('notify', [payload.title, payload.body, deepUrl])
  const bridge = typeof window !== 'undefined' ? window.InfoFocusAndroid : undefined
  if (bridge && typeof bridge.notify === 'function') {
    try {
      bridge.notify(payload.title, payload.body, deepUrl)
      return true
    } catch {
      // Fall through to Web Notification
    }
  }

  if (typeof window !== 'undefined' && 'Notification' in window && Notification.permission === 'granted') {
    try {
      new Notification(payload.title, {
        body: payload.body,
        icon: './icon-192.png',
        tag: payload.id,
      })
      return true
    } catch {
      return false
    }
  }
  return false
}
