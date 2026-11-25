<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  Bell,
  Bug,
  CheckCircle2,
  Copy,
  Database,
  ExternalLink,
  MonitorSmartphone,
  Moon,
  RefreshCw,
  RotateCw,
  Send,
  Smartphone,
  Sun,
  Terminal,
  Trash2,
  Wifi,
} from 'lucide-vue-next'
import AppShell from '../components/AppShell.vue'
import {
  apiLogin,
  clearAuthSession,
  getApiBase,
  isAdminRole,
  loadAuthSession,
  saveAuthSession,
  type AuthSession,
} from '../core/auth'
import { setAppLang } from '../core/i18n'
import {
  buildAndroidDebugUrl,
  clearAndroidAppShellFlag,
  getApkDownloadUrl,
  setImportantPushEnabled,
} from '../core/mobilePush'
import { readDarkMode, writeDarkMode } from '../core/storage'
import type { WorkbenchTab } from '../core/types'

interface DevicePreset {
  id: string
  label: string
  width: number
  height: number
}

interface BridgeLogEntry {
  id: number
  time: string
  method: string
  argsText: string
  source: 'postMessage' | 'mockBridge' | 'devTrigger'
}

interface RuntimeLogEntry {
  id: number
  time: string
  level: 'error' | 'warn' | 'info'
  message: string
}

interface ProbeResult {
  name: string
  path: string
  status: number | string
  latencyMs: number
  ok: boolean
  detail: string
}

interface OverflowNode {
  tag: string
  text: string
  rightEdge: number
  viewportWidth: number
}

const DEVICE_PRESETS: DevicePreset[] = [
  { id: 'android_std', label: '标准安卓 393×851', width: 393, height: 851 },
  { id: 'compact_375', label: '紧凑屏 375×812', width: 375, height: 812 },
  { id: 'mini_360', label: '小屏极限 360×740', width: 360, height: 740 },
  { id: 'large_430', label: '大屏安卓 430×932', width: 430, height: 932 },
  { id: 'tablet_768', label: '折叠内屏 768×1024', width: 768, height: 1024 },
]

const ANDROID_TABS: Array<{ id: WorkbenchTab; label: string }> = [
  { id: 'today', label: '今日要闻' },
  { id: 'wire', label: '7×24 快讯' },
  { id: 'ai_progress', label: 'AI 前沿' },
  { id: 'finance', label: '股市传导' },
  { id: 'briefing', label: '新闻简报' },
  { id: 'tracking', label: '事件追踪' },
  { id: 'calendar', label: '催化日历' },
  { id: 'predictions', label: '前瞻验证' },
  { id: 'tools', label: '科技工具库' },
  { id: 'me', label: '我的 (Me)' },
]

const INSPECTED_STORAGE_KEYS = [
  'infofocus_app_shell_flag',
  'infofocus_mobile_push_v1',
  'mirrorbrief_lang_v1',
  'darkMode',
  'infofocus_v3_watchlist_v1',
  'infofocus_bookmarks_v1',
  'infofocus_read_v1',
  'insight_pro_auth_session_v1',
]

const DEV_CONSOLE_SESSION_KEY = 'infofocus_android_dev_admin_v1'

function loadDevConsoleSession(): AuthSession | null {
  try {
    const raw = window.sessionStorage.getItem(DEV_CONSOLE_SESSION_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as AuthSession
    return parsed?.user ? parsed : null
  } catch {
    return null
  }
}

function saveDevConsoleSession(s: AuthSession): void {
  try {
    window.sessionStorage.setItem(DEV_CONSOLE_SESSION_KEY, JSON.stringify(s))
  } catch {
    // Ignore storage errors
  }
}

const isDark = ref(readDarkMode())
const session = ref<AuthSession | null>(loadDevConsoleSession())
const isAdmin = computed(() => isAdminRole(session.value?.user.role))

const loginUser = ref('admin')
const loginPass = ref('')
const authError = ref('')
const loginBusy = ref(false)
const toast = ref('')

// Emulator state
const phoneFrameRef = ref<HTMLIFrameElement | null>(null)
const activePresetId = ref<string>('android_std')
const landscape = ref(false)
const scaleFactor = ref<number>(0.85)
const shellMode = ref<'android' | 'web'>('android')
const currentTab = ref<WorkbenchTab>('today')
const frameDarkTheme = ref<boolean>(readDarkMode())
const frameLang = ref<'zh' | 'en'>(readStoredLang())
const frameVersion = ref(0)
const frameLoading = ref(true)
const mockPushEnabled = ref(true)

// Simulated native heads-up notification toast inside the device screen
const activePushBanner = ref<{ title: string; body: string; url: string } | null>(null)
const testNotifTitle = ref('突发快讯 · 腾讯 WorkBuddy 上线电脑操控')
const testNotifBody = ref('点击通知即可直接跳转至对应移动标签页，支持从电脑端测试推送深链跳转。')
const testNotifTab = ref<'wire' | 'ai_progress' | 'today'>('wire')

// Right-column dev tools tabs
const devPanel = ref<'bridge' | 'network' | 'runtime' | 'storage'>('bridge')
const bridgeLogs = ref<BridgeLogEntry[]>([])
const runtimeLogs = ref<RuntimeLogEntry[]>([])
const probeResults = ref<ProbeResult[]>([])
const probeBusy = ref(false)
const swStatusText = ref('未检测')
const overflowReport = ref<{ checkedAt: string; scrollWidth: number; innerWidth: number; offenders: OverflowNode[] } | null>(null)
const storageSnapshot = ref<Array<{ key: string; scope: 'local' | 'session'; valuePreview: string; bytes: number }>>([])

let _logSeq = 0
let _cleanupIframeTraps: (() => void) | null = null

function readStoredLang(): 'zh' | 'en' {
  try {
    return window.localStorage.getItem('mirrorbrief_lang_v1') === 'en' ? 'en' : 'zh'
  } catch {
    return 'zh'
  }
}

function nowTimeStr(): string {
  const d = new Date()
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
}

function showToast(msg: string) {
  toast.value = msg
  setTimeout(() => {
    if (toast.value === msg) toast.value = ''
  }, 3200)
}

function pushBridgeLog(method: string, args: unknown[], source: BridgeLogEntry['source']) {
  bridgeLogs.value = [
    {
      id: ++_logSeq,
      time: nowTimeStr(),
      method,
      argsText: args.map((a) => (typeof a === 'string' ? a : JSON.stringify(a))).join(', '),
      source,
    },
    ...bridgeLogs.value,
  ].slice(0, 60)
}

function pushRuntimeLog(level: RuntimeLogEntry['level'], message: string) {
  runtimeLogs.value = [
    {
      id: ++_logSeq,
      time: nowTimeStr(),
      level,
      message,
    },
    ...runtimeLogs.value,
  ].slice(0, 80)
}

const activePreset = computed(
  () => DEVICE_PRESETS.find((p) => p.id === activePresetId.value) ?? DEVICE_PRESETS[0],
)

const screenDims = computed(() => {
  const w = landscape.value ? activePreset.value.height : activePreset.value.width
  const h = landscape.value ? activePreset.value.width : activePreset.value.height
  return { width: w, height: h }
})

const relativeDebugUrl = computed(() => buildAndroidDebugUrl(currentTab.value, shellMode.value))
const iframeSrc = computed(() => {
  const base = relativeDebugUrl.value
  const sep = base.includes('?') ? '&' : '?'
  return `${base}${sep}_dev=${frameVersion.value}`
})

async function handleAdminLogin() {
  authError.value = ''
  loginBusy.value = true
  try {
    const res = await apiLogin(loginUser.value.trim(), loginPass.value)
    if (!isAdminRole(res.user.role)) {
      authError.value = '当前账号非管理员角色，无法进入安卓开发者调试台。'
      return
    }
    // Store admin session strictly in isolated sessionStorage so preview iframe never inherits admin login
    saveDevConsoleSession(res)
    session.value = res
    loginPass.value = ''
    void runNetworkProbes()
    refreshStorageSnapshot()
  } catch (err) {
    authError.value = err instanceof Error ? err.message : '登录失败'
  } finally {
    loginBusy.value = false
  }
}

function toggleConsoleDark() {
  isDark.value = !isDark.value
  document.documentElement.classList.toggle('dark', isDark.value)
  writeDarkMode(isDark.value)
}

function navigatePhoneTab(tab: WorkbenchTab) {
  currentTab.value = tab
  frameLoading.value = true
  frameVersion.value += 1
}

function reloadPhoneFrame(hard = false) {
  frameLoading.value = true
  if (hard) {
    pushRuntimeLog('info', `强制重载安卓调试视图 (${relativeDebugUrl.value})`)
  }
  frameVersion.value += 1
}

function togglePhoneDark() {
  frameDarkTheme.value = !frameDarkTheme.value
  writeDarkMode(frameDarkTheme.value)
  reloadPhoneFrame()
}

function togglePhoneLang() {
  const next = frameLang.value === 'zh' ? 'en' : 'zh'
  frameLang.value = next
  setAppLang(next)
  reloadPhoneFrame()
}

function switchShellMode(mode: 'android' | 'web') {
  shellMode.value = mode
  if (mode === 'web') {
    clearAndroidAppShellFlag()
  }
  reloadPhoneFrame()
}

function copyDeepLink() {
  const absUrl =
    typeof window !== 'undefined'
      ? new URL(relativeDebugUrl.value, window.location.href).toString()
      : relativeDebugUrl.value
  navigator.clipboard?.writeText(absUrl).catch(() => {})
  showToast(`已复制深链：${absUrl}`)
}

function openStandalonePreview() {
  window.open(relativeDebugUrl.value, '_blank', 'noopener,noreferrer')
}

function attachIframeDevHooks() {
  _cleanupIframeTraps?.()
  _cleanupIframeTraps = null
  frameLoading.value = false

  const frame = phoneFrameRef.value
  const win = frame?.contentWindow as (Window & {
    InfoFocusAndroid?: Record<string, unknown>
    console?: Console
  }) | null
  if (!win) return

  // Inject mock window.InfoFocusAndroid matching MainActivity.java InfoFocusJsBridge
  win.InfoFocusAndroid = {
    setTheme(dark: boolean) {
      frameDarkTheme.value = Boolean(dark)
      pushBridgeLog('setTheme', [Boolean(dark)], 'mockBridge')
    },
    notify(title: string, body: string, url?: string) {
      const targetUrl = String(url || `https://mirrorinfo.xyz/${relativeDebugUrl.value}`)
      pushBridgeLog('notify', [title, body, targetUrl], 'mockBridge')
      activePushBanner.value = { title: String(title), body: String(body), url: targetUrl }
    },
    isPushEnabled() {
      pushBridgeLog('isPushEnabled', [mockPushEnabled.value], 'mockBridge')
      return mockPushEnabled.value
    },
    setPushEnabled(enabled: boolean) {
      mockPushEnabled.value = Boolean(enabled)
      pushBridgeLog('setPushEnabled', [mockPushEnabled.value], 'mockBridge')
    },
    requestPermission() {
      pushBridgeLog('requestPermission', ['granted (mock)'], 'mockBridge')
    },
  }

  const onErr = (ev: ErrorEvent) => {
    pushRuntimeLog('error', `[window.error] ${ev.message || 'Unknown error'} (${ev.filename || ''}:${ev.lineno || 0})`)
  }
  const onRej = (ev: PromiseRejectionEvent) => {
    pushRuntimeLog('error', `[unhandledrejection] ${String(ev.reason || 'Promise rejected')}`)
  }
  win.addEventListener('error', onErr)
  win.addEventListener('unhandledrejection', onRej)

  const origError = win.console?.error
  const origWarn = win.console?.warn
  if (win.console && origError && origWarn) {
    win.console.error = (...args: unknown[]) => {
      pushRuntimeLog('error', `[console.error] ${args.map((x) => String(x)).join(' ')}`)
      origError.apply(win.console, args)
    }
    win.console.warn = (...args: unknown[]) => {
      pushRuntimeLog('warn', `[console.warn] ${args.map((x) => String(x)).join(' ')}`)
      origWarn.apply(win.console, args)
    }
  }

  pushRuntimeLog('info', `已挂载沙盒调试视图：${relativeDebugUrl.value}`)
  refreshStorageSnapshot()

  _cleanupIframeTraps = () => {
    try {
      win.removeEventListener('error', onErr)
      win.removeEventListener('unhandledrejection', onRej)
      if (win.console && origError && origWarn) {
        win.console.error = origError
        win.console.warn = origWarn
      }
    } catch {
      // Ignore torn-down iframe references
    }
  }
}

function triggerSimulatedPush() {
  const deepUrl = `./index.html?app=android&tab=${testNotifTab.value}`
  activePushBanner.value = {
    title: testNotifTitle.value.trim() || '镜信重磅快讯测试',
    body: testNotifBody.value.trim() || '模拟推送正文内容',
    url: deepUrl,
  }
  pushBridgeLog('notify', [activePushBanner.value.title, activePushBanner.value.body, deepUrl], 'devTrigger')
}

function handleTapPushBanner() {
  if (!activePushBanner.value) return
  try {
    const u = new URL(activePushBanner.value.url, window.location.href)
    const tabParam = u.searchParams.get('tab') as WorkbenchTab | null
    if (tabParam && ANDROID_TABS.some((t) => t.id === tabParam)) {
      currentTab.value = tabParam
    }
    shellMode.value = 'android'
    reloadPhoneFrame()
    pushBridgeLog('handleNotificationIntent', [u.toString()], 'devTrigger')
  } catch {
    reloadPhoneFrame()
  }
  activePushBanner.value = null
}

function toggleMockNativePush() {
  const next = !mockPushEnabled.value
  mockPushEnabled.value = next
  void setImportantPushEnabled(next)
  pushBridgeLog('setPushEnabled', [next], 'devTrigger')
  refreshStorageSnapshot()
}

function inspectMobileViewportOverflow() {
  const frame = phoneFrameRef.value
  const doc = frame?.contentDocument
  const win = frame?.contentWindow
  if (!doc || !win) {
    showToast('无法读取设备页面 DOM，请确认页面已完成加载')
    return
  }
  const vw = win.innerWidth
  const sw = doc.documentElement.scrollWidth
  const offenders: OverflowNode[] = []
  let expectedScrollableCount = 0

  function isInsideHorizontalScroller(el: HTMLElement): boolean {
    let p: HTMLElement | null = el.parentElement
    while (p && p !== doc.body && p !== doc.documentElement) {
      const style = win.getComputedStyle(p)
      if (
        (style.overflowX === 'auto' || style.overflowX === 'scroll') &&
        p.scrollWidth > p.clientWidth + 1
      ) {
        return true
      }
      p = p.parentElement
    }
    return false
  }

  const els = doc.body?.querySelectorAll('*') || []
  for (let i = 0; i < els.length; i++) {
    const el = els[i] as HTMLElement
    const style = win.getComputedStyle(el)
    if (
      (style.overflowX === 'auto' || style.overflowX === 'scroll') &&
      el.scrollWidth > el.clientWidth + 1
    ) {
      expectedScrollableCount += 1
      continue
    }
    const rect = el.getBoundingClientRect()
    if (rect.width > 0 && rect.right > vw + 1.5) {
      if (isInsideHorizontalScroller(el)) continue
      offenders.push({
        tag: `${el.tagName.toLowerCase()}${el.className ? '.' + String(el.className).split(/\s+/).slice(0, 2).join('.') : ''}`,
        text: (el.innerText || '').trim().slice(0, 32),
        rightEdge: Math.round(rect.right),
        viewportWidth: vw,
      })
      if (offenders.length >= 12) break
    }
  }
  overflowReport.value = {
    checkedAt: nowTimeStr(),
    scrollWidth: sw,
    innerWidth: vw,
    offenders,
  }
  if (sw > vw + 1 || offenders.length > 0) {
    pushRuntimeLog(
      'warn',
      `检测到横向溢出：scrollWidth=${sw}px > viewport=${vw}px（${offenders.length} 个越界节点）`,
    )
  } else {
    pushRuntimeLog(
      'info',
      `视口宽度体检通过：${vw}px 下无横向溢出${expectedScrollableCount > 0 ? `（含 ${expectedScrollableCount} 处预期横向滚动条）` : ''}`,
    )
  }
}

async function runNetworkProbes() {
  probeBusy.value = true
  const apiBase = getApiBase()
  const targets = [
    { name: '7×24 实时快讯', path: `${apiBase}/api/wire/latest`, method: 'GET' },
    { name: 'AI 前沿接口', path: `${apiBase}/api/ai-progress/latest`, method: 'GET' },
    { name: '市场延迟行情', path: `${apiBase}/api/market/quotes`, method: 'GET' },
    { name: '安卓安装包 APK', path: getApkDownloadUrl(), method: 'HEAD' },
    { name: 'RSS 订阅源', path: './feed.xml', method: 'HEAD' },
  ]
  const out: ProbeResult[] = []
  for (const tgt of targets) {
    const t0 = performance.now()
    try {
      const res = await fetch(tgt.path, { method: tgt.method, cache: 'no-store' })
      const ms = Math.round(performance.now() - t0)
      let detail = `Content-Type: ${res.headers.get('content-type') || 'unknown'}`
      if (tgt.method === 'GET' && res.ok) {
        const j = await res.json().catch(() => null)
        if (j?.items) detail = `items=${j.items.length}, updated=${String(j.updated_at || '').slice(11, 19)}`
        else if (j?.timeline) detail = `timeline=${j.timeline.length}`
        else if (j?.indices) detail = `indices=${j.indices.length}`
      }
      out.push({ name: tgt.name, path: tgt.path, status: res.status, latencyMs: ms, ok: res.ok, detail })
    } catch (err) {
      out.push({
        name: tgt.name,
        path: tgt.path,
        status: 'ERR',
        latencyMs: Math.round(performance.now() - t0),
        ok: false,
        detail: err instanceof Error ? err.message : 'Network error',
      })
    }
  }
  probeResults.value = out

  if ('serviceWorker' in navigator) {
    try {
      const regs = await navigator.serviceWorker.getRegistrations()
      const cacheKeys = typeof caches !== 'undefined' ? await caches.keys() : []
      swStatusText.value = `已注册 ${regs.length} 个 SW；缓存桶：[${cacheKeys.join(', ') || '无'}]`
    } catch {
      swStatusText.value = '无法读取 Service Worker 状态'
    }
  } else {
    swStatusText.value = '当前环境不支持 Service Worker'
  }
  probeBusy.value = false
}

async function resetServiceWorkerAndCaches() {
  try {
    if ('serviceWorker' in navigator) {
      const regs = await navigator.serviceWorker.getRegistrations()
      await Promise.all(regs.map((r) => r.unregister()))
    }
    if (typeof caches !== 'undefined') {
      const keys = await caches.keys()
      await Promise.all(keys.map((k) => caches.delete(k)))
    }
    showToast('已注销 Service Worker 并清空所有离线缓存，正在重刷设备页面…')
    await runNetworkProbes()
    reloadPhoneFrame(true)
  } catch (err) {
    showToast(err instanceof Error ? err.message : '清理失败')
  }
}

function refreshStorageSnapshot() {
  const rows: typeof storageSnapshot.value = []
  const frameWin = phoneFrameRef.value?.contentWindow
  const stores: Array<{ scope: 'local' | 'session'; store: Storage | undefined }> = [
    { scope: 'local', store: window.localStorage },
    { scope: 'session', store: frameWin?.sessionStorage ?? window.sessionStorage },
  ]
  for (const { scope, store } of stores) {
    if (!store) continue
    for (const k of INSPECTED_STORAGE_KEYS) {
      const v = store.getItem(k)
      if (v !== null) {
        const preview = k === 'insight_pro_auth_session_v1' ? '<redacted JWT session>' : v.slice(0, 90)
        rows.push({ key: k, scope, valuePreview: preview, bytes: v.length })
      }
    }
  }
  storageSnapshot.value = rows
}

function handleClearAndroidFlagFromStorage() {
  clearAndroidAppShellFlag()
  try {
    phoneFrameRef.value?.contentWindow?.sessionStorage?.removeItem('infofocus_app_shell_flag')
  } catch {
    // Ignore
  }
  refreshStorageSnapshot()
  showToast('已清理 app=android 缓存标记，桌面浏览器不会再被锁死在安卓模式')
}

function handleWindowMessage(ev: MessageEvent) {
  if (ev.origin !== window.location.origin) return
  const data = ev.data as { type?: string; method?: string; args?: unknown[] } | null
  if (!data || data.type !== 'infofocus-android-bridge' || !data.method) return
  pushBridgeLog(data.method, Array.isArray(data.args) ? data.args : [], 'postMessage')
  if (data.method === 'setTheme' && Array.isArray(data.args)) {
    frameDarkTheme.value = Boolean(data.args[0])
  } else if (data.method === 'notify' && Array.isArray(data.args)) {
    activePushBanner.value = {
      title: String(data.args[0] || ''),
      body: String(data.args[1] || ''),
      url: String(data.args[2] || relativeDebugUrl.value),
    }
  }
}

onMounted(() => {
  document.documentElement.classList.toggle('dark', isDark.value)
  window.addEventListener('message', handleWindowMessage)
  if (isAdmin.value) {
    void runNetworkProbes()
    refreshStorageSnapshot()
  }
})

onUnmounted(() => {
  _cleanupIframeTraps?.()
  window.removeEventListener('message', handleWindowMessage)
})
</script>

<template>
  <AppShell
    active-page="about"
    :is-dark="isDark"
    :show-history-button="false"
    :show-bookmarks-button="false"
    :show-refresh-button="false"
    @toggle-dark="toggleConsoleDark"
  >
    <div class="max-w-[1440px] mx-auto space-y-4">
      <div
        v-if="toast"
        class="rounded-xl border border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-950/40 px-4 py-2.5 text-xs sm:text-sm font-medium text-emerald-900 dark:text-emerald-200 flex items-center justify-between"
      >
        <span>{{ toast }}</span>
        <button type="button" @click="toast = ''" class="underline text-xs">关闭</button>
      </div>

      <!-- Admin Auth Gate -->
      <section
        v-if="!isAdmin"
        class="max-w-md mx-auto mt-8 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 space-y-4 shadow-sm"
      >
        <div class="flex items-center gap-2.5">
          <div class="w-10 h-10 rounded-xl bg-emerald-600 text-white flex items-center justify-center">
            <MonitorSmartphone class="w-5 h-5" />
          </div>
          <div>
            <h1 class="text-lg font-bold text-slate-900 dark:text-white">镜信 · 安卓开发者调试后台</h1>
            <p class="text-xs text-slate-500">请使用管理员账号登录以开启 PC 端手机模拟器与 Bridge 调试台</p>
          </div>
        </div>

        <form @submit.prevent="handleAdminLogin" class="space-y-3">
          <div>
            <label class="block text-xs font-medium text-slate-600 dark:text-slate-300 mb-1">管理员账号</label>
            <input
              v-model="loginUser"
              type="text"
              required
              class="w-full h-10 px-3 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm"
            />
          </div>
          <div>
            <label class="block text-xs font-medium text-slate-600 dark:text-slate-300 mb-1">管理员密码</label>
            <input
              v-model="loginPass"
              type="password"
              required
              class="w-full h-10 px-3 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm"
            />
          </div>
          <p v-if="authError" class="text-xs text-red-600 dark:text-red-400 font-medium">{{ authError }}</p>
          <button
            type="submit"
            :disabled="loginBusy"
            class="w-full h-10 rounded-xl bg-slate-900 dark:bg-blue-600 text-white text-sm font-semibold hover:opacity-95 disabled:opacity-60"
          >
            {{ loginBusy ? '验证中...' : '进入安卓调试后台' }}
          </button>
        </form>
      </section>

      <!-- Authenticated Android Developer Console -->
      <template v-else>
        <!-- Top Header Toolbar -->
        <header class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 flex flex-wrap items-center justify-between gap-3">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-xl bg-emerald-600 text-white flex items-center justify-center shrink-0">
              <MonitorSmartphone class="w-5 h-5" />
            </div>
            <div>
              <h1 class="text-base sm:text-lg font-bold text-slate-900 dark:text-white flex flex-wrap items-center gap-2">
                <span>安卓页面开发者调试后台</span>
                <span class="px-2 py-0.5 rounded-full text-[11px] font-mono bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300">
                  InfoFocusAndroid / WebView Bridge Lab
                </span>
              </h1>
              <p class="text-xs text-slate-500 dark:text-slate-400">
                直接在电脑实时调试真实安卓壳页面（{{ screenDims.width }}×{{ screenDims.height }}）、模拟推送深链跳转与检测横向溢出
              </p>
            </div>
          </div>

          <div class="flex flex-wrap items-center gap-2 text-xs">
            <a
              href="./admin.html"
              class="inline-flex items-center gap-1 px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 font-medium"
            >
              <ArrowLeft class="w-3.5 h-3.5" />
              <span>返回管理后台</span>
            </a>
            <button
              type="button"
              @click="openStandalonePreview"
              class="inline-flex items-center gap-1 px-3 py-2 rounded-xl border border-blue-200 dark:border-blue-800 bg-blue-50/70 dark:bg-blue-950/30 text-blue-700 dark:text-blue-300 font-semibold hover:bg-blue-100"
            >
              <ExternalLink class="w-3.5 h-3.5" />
              <span>新标签独立打开</span>
            </button>
            <button
              type="button"
              @click="copyDeepLink"
              class="inline-flex items-center gap-1 px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 font-medium"
            >
              <Copy class="w-3.5 h-3.5" />
              <span>复制当前深链</span>
            </button>
          </div>
        </header>

        <!-- Device Controls Strip -->
        <section class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-3 space-y-2.5 text-xs">
          <div class="flex flex-wrap items-center gap-2">
            <!-- Shell Mode -->
            <div class="inline-flex rounded-xl border border-slate-200 dark:border-slate-700 p-0.5 bg-slate-50 dark:bg-slate-800/60">
              <button
                type="button"
                @click="switchShellMode('android')"
                class="px-2.5 py-1.5 rounded-lg font-semibold transition-colors"
                :class="shellMode === 'android' ? 'bg-emerald-600 text-white' : 'text-slate-600 dark:text-slate-300'"
              >
                Android App 壳 (?app=android)
              </button>
              <button
                type="button"
                @click="switchShellMode('web')"
                class="px-2.5 py-1.5 rounded-lg font-semibold transition-colors"
                :class="shellMode === 'web' ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-900' : 'text-slate-600 dark:text-slate-300'"
              >
                手机浏览器 (?app=web)
              </button>
            </div>

            <!-- Device Presets -->
            <select
              v-model="activePresetId"
              class="h-8 px-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 font-medium"
            >
              <option v-for="p in DEVICE_PRESETS" :key="p.id" :value="p.id">{{ p.label }}</option>
            </select>

            <button
              type="button"
              @click="landscape = !landscape"
              class="inline-flex items-center gap-1 h-8 px-2.5 rounded-xl border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 font-medium"
            >
              <RotateCw class="w-3.5 h-3.5" />
              <span>{{ landscape ? '横屏' : '竖屏' }}</span>
            </button>

            <select
              v-model.number="scaleFactor"
              class="h-8 px-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 font-mono"
            >
              <option :value="1">100%</option>
              <option :value="0.85">85%</option>
              <option :value="0.75">75%</option>
            </select>

            <button
              type="button"
              @click="togglePhoneDark"
              class="inline-flex items-center gap-1 h-8 px-2.5 rounded-xl border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 font-medium"
            >
              <Moon v-if="!frameDarkTheme" class="w-3.5 h-3.5" />
              <Sun v-else class="w-3.5 h-3.5 text-amber-400" />
              <span>{{ frameDarkTheme ? '暗色主题' : '浅色主题' }}</span>
            </button>

            <button
              type="button"
              @click="togglePhoneLang"
              class="h-8 px-2.5 rounded-xl border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 font-mono font-semibold"
            >
              语言：{{ frameLang.toUpperCase() }}
            </button>

            <button
              type="button"
              @click="inspectMobileViewportOverflow"
              class="inline-flex items-center gap-1 h-8 px-3 rounded-xl bg-amber-50 dark:bg-amber-950/40 text-amber-800 dark:text-amber-300 border border-amber-200 dark:border-amber-800 font-semibold hover:bg-amber-100"
            >
              <Bug class="w-3.5 h-3.5" />
              <span>检测宽度溢出</span>
            </button>

            <button
              type="button"
              @click="reloadPhoneFrame(true)"
              class="inline-flex items-center gap-1 h-8 px-3 rounded-xl bg-slate-900 dark:bg-blue-600 text-white font-semibold hover:opacity-90"
            >
              <RefreshCw class="w-3.5 h-3.5" :class="{ 'animate-spin': frameLoading }" />
              <span>重载手机页</span>
            </button>
          </div>

          <!-- Quick Route Tab Pills -->
          <div class="flex flex-wrap items-center gap-1.5 pt-1 border-t border-slate-100 dark:border-slate-800">
            <span class="text-[11px] text-slate-400 mr-1">快捷跳转标签：</span>
            <button
              v-for="tab in ANDROID_TABS"
              :key="tab.id"
              type="button"
              @click="navigatePhoneTab(tab.id)"
              class="px-2.5 py-1 rounded-lg font-medium transition-colors"
              :class="
                currentTab === tab.id
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700'
              "
            >
              {{ tab.label }}
            </button>
          </div>
        </section>

        <!-- Main Workspace Grid: Interactive Android Frame (Left) + Diagnostics Tools (Right) -->
        <div class="grid grid-cols-1 xl:grid-cols-12 gap-4 items-start">
          <!-- Left Pane: Phone Simulator -->
          <section class="xl:col-span-6 rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-100/80 dark:bg-slate-950 p-4 flex flex-col items-center gap-3 overflow-auto">
            <div class="w-full flex items-center justify-between text-[11px] text-slate-500 font-mono">
              <span>URL: {{ relativeDebugUrl }}</span>
              <span>{{ screenDims.width }}×{{ screenDims.height }}px ({{ Math.round(scaleFactor * 100) }}%)</span>
            </div>

            <!-- Scaled Phone Chassis -->
            <div
              class="origin-top transition-all duration-200"
              :style="{
                width: `${screenDims.width}px`,
                height: `${screenDims.height + 54}px`,
                transform: `scale(${scaleFactor})`,
                marginBottom: `${Math.round((screenDims.height + 54) * (scaleFactor - 1))}px`,
              }"
            >
              <div class="w-full h-full rounded-[32px] border-[6px] border-slate-800 dark:border-slate-700 shadow-2xl overflow-hidden flex flex-col bg-white dark:bg-slate-950 relative">
                <!-- Simulated Android System Status Bar (reflects syncAndroidStatusBarTheme) -->
                <div
                  class="h-7 px-5 flex items-center justify-between text-[11px] font-semibold shrink-0 transition-colors"
                  :class="frameDarkTheme ? 'bg-[#020617] text-slate-200 border-b border-slate-800/70' : 'bg-white text-slate-800 border-b border-slate-100'"
                >
                  <span>18:10</span>
                  <div class="w-16 h-3.5 rounded-full bg-slate-900/90 dark:bg-black/80 mx-auto" />
                  <span class="flex items-center gap-1.5 font-mono text-[10px]">
                    <Wifi class="w-3 h-3" />
                    <span>5G</span>
                    <span>98%</span>
                  </span>
                </div>

                <!-- Simulated Android Push Notification Heads-Up Toast -->
                <div
                  v-if="activePushBanner"
                  class="absolute top-9 left-3 right-3 z-30 rounded-2xl bg-slate-900/95 text-white border border-slate-700 shadow-2xl p-3 space-y-1 cursor-pointer"
                  @click="handleTapPushBanner"
                >
                  <div class="flex items-center justify-between text-[10px] text-emerald-400 font-semibold">
                    <span class="flex items-center gap-1">
                      <Bell class="w-3 h-3" />
                      <span>MirrorBrief 原生通知模拟（点击跳转深链）</span>
                    </span>
                    <button type="button" @click.stop="activePushBanner = null" class="text-slate-400 hover:text-white px-1"><X class="w-3.5 h-3.5" /></button>
                  </div>
                  <div class="text-xs font-bold leading-snug">{{ activePushBanner.title }}</div>
                  <div class="text-[11px] text-slate-300 line-clamp-2">{{ activePushBanner.body }}</div>
                </div>

                <!-- Real App Viewport Iframe -->
                <iframe
                  ref="phoneFrameRef"
                  :src="iframeSrc"
                  title="Android App Preview"
                  class="w-full flex-1 border-0 bg-white dark:bg-slate-950"
                  @load="attachIframeDevHooks"
                />

                <!-- Simulated Android Gesture Bar -->
                <div
                  class="h-6 flex items-center justify-center shrink-0 transition-colors"
                  :class="frameDarkTheme ? 'bg-[#0f172a] border-t border-slate-800' : 'bg-white border-t border-slate-100'"
                >
                  <div class="w-24 h-1 rounded-full bg-slate-400/70 dark:bg-slate-500/70" />
                </div>
              </div>
            </div>
          </section>

          <!-- Right Pane: Diagnostics & JS Bridge Studio -->
          <section class="xl:col-span-6 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 space-y-4">
            <!-- Panel Sub-Tabs -->
            <div class="flex flex-wrap gap-1.5 text-xs font-semibold border-b border-slate-100 dark:border-slate-800 pb-3">
              <button
                type="button"
                @click="devPanel = 'bridge'"
                class="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl transition-colors"
                :class="devPanel === 'bridge' ? 'bg-emerald-600 text-white' : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300'"
              >
                <Smartphone class="w-3.5 h-3.5" />
                <span>Bridge 桥接与推送 ({{ bridgeLogs.length }})</span>
              </button>
              <button
                type="button"
                @click="devPanel = 'network'"
                class="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl transition-colors"
                :class="devPanel === 'network' ? 'bg-blue-600 text-white' : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300'"
              >
                <Activity class="w-3.5 h-3.5" />
                <span>接口与离线缓存</span>
              </button>
              <button
                type="button"
                @click="devPanel = 'runtime'"
                class="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl transition-colors"
                :class="devPanel === 'runtime' ? 'bg-amber-600 text-white' : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300'"
              >
                <Terminal class="w-3.5 h-3.5" />
                <span>日志与排版溢出 ({{ runtimeLogs.length }})</span>
              </button>
              <button
                type="button"
                @click="devPanel = 'storage'; refreshStorageSnapshot()"
                class="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl transition-colors"
                :class="devPanel === 'storage' ? 'bg-indigo-600 text-white' : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300'"
              >
                <Database class="w-3.5 h-3.5" />
                <span>本地状态存储</span>
              </button>
            </div>

            <!-- Dev Tab 1: InfoFocusAndroid Bridge & Push Simulator -->
            <div v-if="devPanel === 'bridge'" class="space-y-4 text-xs">
              <div class="rounded-xl border border-emerald-200/80 dark:border-emerald-900 bg-emerald-50/40 dark:bg-emerald-950/20 p-3.5 space-y-2.5">
                <div class="flex flex-wrap items-center justify-between gap-2">
                  <span class="font-bold text-slate-900 dark:text-white">触发模拟原生重磅推送（测试 Deep-Link 跳转）</span>
                  <button
                    type="button"
                    @click="toggleMockNativePush"
                    class="px-2.5 py-1 rounded-lg font-semibold border"
                    :class="mockPushEnabled ? 'bg-emerald-600 text-white border-emerald-600' : 'bg-white dark:bg-slate-800 border-slate-300 text-slate-600'"
                  >
                    Mock Push 开关：{{ mockPushEnabled ? '开启' : '关闭' }}
                  </button>
                </div>
                <div class="grid grid-cols-1 sm:grid-cols-3 gap-2">
                  <input
                    v-model="testNotifTitle"
                    type="text"
                    placeholder="推送标题"
                    class="sm:col-span-2 h-9 px-2.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800"
                  />
                  <select
                    v-model="testNotifTab"
                    class="h-9 px-2.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800"
                  >
                    <option value="wire">跳至：7×24 快讯</option>
                    <option value="ai_progress">跳至：AI 前沿</option>
                    <option value="today">跳至：今日要闻</option>
                  </select>
                </div>
                <div class="flex flex-col sm:flex-row gap-2">
                  <input
                    v-model="testNotifBody"
                    type="text"
                    placeholder="推送正文"
                    class="flex-1 h-9 px-2.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800"
                  />
                  <button
                    type="button"
                    @click="triggerSimulatedPush"
                    class="inline-flex items-center justify-center gap-1.5 h-9 px-4 rounded-lg bg-emerald-600 text-white font-semibold hover:bg-emerald-700 shrink-0"
                  >
                    <Send class="w-3.5 h-3.5" />
                    <span>弹出设备通知</span>
                  </button>
                </div>
              </div>

              <div class="space-y-2">
                <div class="flex items-center justify-between">
                  <h3 class="font-bold text-slate-800 dark:text-slate-200">InfoFocusAndroid JSBridge 实时调用日志</h3>
                  <button type="button" @click="bridgeLogs = []" class="text-[11px] text-slate-400 hover:text-slate-700">清空记录</button>
                </div>
                <div v-if="bridgeLogs.length === 0" class="rounded-xl border border-dashed border-slate-200 dark:border-slate-700 p-4 text-center text-slate-400">
                  暂无调用记录。在左侧切换暗色主题、开启推送或点击「弹出设备通知」即可实时抓包。
                </div>
                <ul v-else class="max-h-72 overflow-y-auto divide-y divide-slate-100 dark:divide-slate-800 rounded-xl border border-slate-200 dark:border-slate-800 font-mono text-[11px]">
                  <li v-for="log in bridgeLogs" :key="log.id" class="p-2.5 flex items-start justify-between gap-2">
                    <div class="min-w-0">
                      <span class="text-slate-400 mr-2">{{ log.time }}</span>
                      <span class="px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300 font-semibold mr-2">
                        {{ log.method }}
                      </span>
                      <span class="text-slate-700 dark:text-slate-300 break-all">{{ log.argsText || '()' }}</span>
                    </div>
                    <span class="text-[10px] text-slate-400 shrink-0">{{ log.source }}</span>
                  </li>
                </ul>
              </div>
            </div>

            <!-- Dev Tab 2: API Health, APK & Service Worker -->
            <div v-else-if="devPanel === 'network'" class="space-y-3 text-xs">
              <div class="flex flex-wrap items-center justify-between gap-2">
                <span class="font-bold text-slate-800 dark:text-slate-200">安卓依赖接口与资源状态探测</span>
                <div class="flex items-center gap-2">
                  <button
                    type="button"
                    :disabled="probeBusy"
                    @click="runNetworkProbes"
                    class="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-blue-600 text-white font-semibold hover:bg-blue-700 disabled:opacity-60"
                  >
                    <RefreshCw class="w-3.5 h-3.5" :class="{ 'animate-spin': probeBusy }" />
                    <span>重新探测</span>
                  </button>
                  <button
                    type="button"
                    @click="resetServiceWorkerAndCaches"
                    class="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-red-200 dark:border-red-900 text-red-600 font-semibold hover:bg-red-50 dark:hover:bg-red-950/30"
                  >
                    <Trash2 class="w-3.5 h-3.5" />
                    <span>清理 SW 缓存</span>
                  </button>
                </div>
              </div>

              <div class="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/40 px-3 py-2 text-[11px] font-mono text-slate-600 dark:text-slate-300">
                Service Worker 状态：{{ swStatusText }}
              </div>

              <div class="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
                <table class="w-full text-left border-collapse text-[11px]">
                  <thead class="bg-slate-50 dark:bg-slate-800/60 text-slate-500">
                    <tr>
                      <th class="py-2 px-3">探测项</th>
                      <th class="py-2 px-2">状态</th>
                      <th class="py-2 px-2">耗时</th>
                      <th class="py-2 px-3">载荷摘要</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-slate-100 dark:divide-slate-800">
                    <tr v-for="p in probeResults" :key="p.path">
                      <td class="py-2 px-3 font-medium">{{ p.name }}</td>
                      <td class="py-2 px-2 font-mono font-bold" :class="p.ok ? 'text-emerald-600' : 'text-red-600'">{{ p.status }}</td>
                      <td class="py-2 px-2 font-mono text-slate-500">{{ p.latencyMs }}ms</td>
                      <td class="py-2 px-3 font-mono text-slate-500 break-all">{{ p.detail }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <!-- Dev Tab 3: Runtime Error Trap & Overflow Audit -->
            <div v-else-if="devPanel === 'runtime'" class="space-y-3 text-xs">
              <div
                v-if="overflowReport"
                class="rounded-xl border p-3 space-y-1.5"
                :class="
                  overflowReport.offenders.length > 0
                    ? 'border-amber-300 bg-amber-50/70 dark:border-amber-800 dark:bg-amber-950/30'
                    : 'border-emerald-200 bg-emerald-50/60 dark:border-emerald-800 dark:bg-emerald-950/20'
                "
              >
                <div class="flex items-center justify-between font-semibold">
                  <span class="flex items-center gap-1.5">
                    <AlertTriangle v-if="overflowReport.offenders.length > 0" class="w-4 h-4 text-amber-600" />
                    <CheckCircle2 v-else class="w-4 h-4 text-emerald-600" />
                    <span>
                      视口布局检测 ({{ overflowReport.checkedAt }}) · scrollWidth={{ overflowReport.scrollWidth }}px / viewport={{ overflowReport.innerWidth }}px
                    </span>
                  </span>
                </div>
                <ul v-if="overflowReport.offenders.length > 0" class="space-y-1 text-[11px] font-mono text-amber-900 dark:text-amber-200">
                  <li v-for="(ov, idx) in overflowReport.offenders" :key="idx">
                    • {{ ov.tag }} (right={{ ov.rightEdge }}px &gt; {{ ov.viewportWidth }}px) {{ ov.text ? `«${ov.text}»` : '' }}
                  </li>
                </ul>
              </div>

              <div class="flex items-center justify-between">
                <h3 class="font-bold text-slate-800 dark:text-slate-200">模拟器 Console 与异常捕获</h3>
                <button type="button" @click="runtimeLogs = []" class="text-[11px] text-slate-400 hover:text-slate-700">清空</button>
              </div>
              <ul class="max-h-80 overflow-y-auto divide-y divide-slate-100 dark:divide-slate-800 rounded-xl border border-slate-200 dark:border-slate-800 font-mono text-[11px]">
                <li v-for="rl in runtimeLogs" :key="rl.id" class="p-2.5 flex items-start gap-2">
                  <span class="text-slate-400 shrink-0">{{ rl.time }}</span>
                  <span
                    class="px-1.5 py-0.2 rounded font-bold shrink-0 uppercase"
                    :class="
                      rl.level === 'error'
                        ? 'bg-red-100 text-red-700'
                        : rl.level === 'warn'
                          ? 'bg-amber-100 text-amber-800'
                          : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'
                    "
                  >
                    {{ rl.level }}
                  </span>
                  <span class="break-all text-slate-700 dark:text-slate-200">{{ rl.message }}</span>
                </li>
              </ul>
            </div>

            <!-- Dev Tab 4: Storage Inspector -->
            <div v-else-if="devPanel === 'storage'" class="space-y-3 text-xs">
              <div class="flex flex-wrap items-center justify-between gap-2">
                <span class="font-bold text-slate-800 dark:text-slate-200">移动端持久化状态检查 (Storage Snapshot)</span>
                <div class="flex items-center gap-2">
                  <button
                    type="button"
                    @click="refreshStorageSnapshot"
                    class="px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 font-medium"
                  >
                    刷新快照
                  </button>
                  <button
                    type="button"
                    @click="handleClearAndroidFlagFromStorage"
                    class="px-3 py-1.5 rounded-lg border border-amber-200 dark:border-amber-800 bg-amber-50/70 dark:bg-amber-950/30 text-amber-800 dark:text-amber-300 font-semibold"
                  >
                    清除安卓壳锁定标记
                  </button>
                </div>
              </div>
              <div class="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
                <table class="w-full text-left border-collapse text-[11px] font-mono">
                  <thead class="bg-slate-50 dark:bg-slate-800/60 text-slate-500">
                    <tr>
                      <th class="py-2 px-3">键名</th>
                      <th class="py-2 px-2">作用域</th>
                      <th class="py-2 px-2">体积</th>
                      <th class="py-2 px-3">当前值预览</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-slate-100 dark:divide-slate-800">
                    <tr v-for="row in storageSnapshot" :key="`${row.scope}:${row.key}`">
                      <td class="py-2 px-3 text-slate-900 dark:text-white">{{ row.key }}</td>
                      <td class="py-2 px-2 text-slate-500">{{ row.scope }}</td>
                      <td class="py-2 px-2 text-slate-500">{{ row.bytes }}B</td>
                      <td class="py-2 px-3 text-slate-600 dark:text-slate-300 break-all">{{ row.valuePreview }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        </div>
      </template>
    </div>
  </AppShell>
</template>
