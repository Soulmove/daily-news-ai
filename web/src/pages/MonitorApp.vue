<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  Activity,
  AlertTriangle,
  Bell,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  Database,
  ExternalLink,
  GitBranch,
  History,
  LayoutGrid,
  List,
  Radio,
  RefreshCw,
  RotateCcw,
  Search,
  Star,
  X,
  XCircle,
} from 'lucide-vue-next'
import AppShell from '../components/AppShell.vue'
import SmartTime from '../components/SmartTime.vue'
import TimeMachineModal from '../components/TimeMachineModal.vue'
import { apiGetPublicSettings, isAdminRole, loadAuthSession } from '../core/auth'
import { clusterRawPlatforms, sanitizeExcerptText } from '../core/dedup'
import { normalizeExternalUrl } from '../core/legacyAdapter'
import {
  fetchConnectorsLatest,
  fetchHistoryIndex,
  fetchManifest,
  fetchRadarItems,
  fetchRawBatch,
} from '../core/fetcher'
import { filterRawClusters, filterRawPlatforms } from '../core/search'
import {
  loadFavoriteSourceIds,
  readDarkMode,
  saveFavoriteSourceIds,
  writeDarkMode,
} from '../core/storage'
import {
  evaluateRawHealth,
  formatFriendlyBatchId,
  formatShanghaiDateTime,
  parseTimestampMs,
} from '../core/time'
import {
  CATEGORIES,
  type CategoryKey,
  type ConnectorsLatestDoc,
  type HistoryIndexEntry,
  type ManifestV2,
  type RadarItem,
  type RawBatchMeta,
  type RawPlatform,
} from '../core/types'
import {
  buildMonitorUrl,
  type MonitorViewMode,
  parseMonitorUrlState,
  syncUrlToBrowser,
} from '../core/urlState'

const isDark = ref(readDarkMode())
const monitorAccessChecked = ref(false)
const monitorAccessAllowed = ref(false)
const nowMs = ref(Date.now())
let clockTimer: ReturnType<typeof setInterval> | null = null
let pollTimer: ReturnType<typeof setInterval> | null = null

function sanitizePublicNote(raw: string | null | undefined): string {
  const s = String(raw || '').trim()
  if (!s) return ''
  return s
    .replace(/Gemini Search/gi, '云端智能检索')
    .replace(/GitHub Actions?/gi, '云端自动化引擎')
    .replace(/ETag\s*条件请求/g, '增量缓存校验')
    .replace(/免费\s*API\s*配额/g, '系统调度策略')
}

function applyDarkClass(dark: boolean) {
  if (typeof document !== 'undefined') {
    document.documentElement.classList.toggle('dark', dark)
  }
}

function toggleDark() {
  isDark.value = !isDark.value
  applyDarkClass(isDark.value)
  writeDarkMode(isDark.value)
}

const initialUrl = parseMonitorUrlState()
const activeCategory = ref<CategoryKey | 'favorites'>(initialUrl.cat)
const historyPath = ref<string | null>(initialUrl.history)
const viewMode = ref<MonitorViewMode>(initialUrl.view)
const searchQuery = ref(initialUrl.q)
const sourceFilter = ref(initialUrl.source)
const healthFilter = ref<'all' | 'ok' | 'issue'>(initialUrl.health)

const manifest = ref<ManifestV2 | null>(null)
const pendingNewManifest = ref<ManifestV2 | null>(null)
const batchMeta = ref<RawBatchMeta | null>(null)
const platformsByCat = ref<Record<CategoryKey, RawPlatform[]>>({
  finance: [],
  global: [],
  tech: [],
  general: [],
})
const loading = ref(true)
const errorMsg = ref<string | null>(null)
const isRefreshing = ref(false)

const favoriteSourceIds = ref<Set<string>>(loadFavoriteSourceIds())
const expandedPlatforms = ref<Set<string>>(new Set())
const expandedClusters = ref<Set<string>>(new Set())

// Time Machine modal
const historyModalOpen = ref(false)
const historyEntries = ref<HistoryIndexEntry[]>([])
const historyLoading = ref(false)
const historyError = ref<string | null>(null)

const isHistoryMode = computed(() => Boolean(historyPath.value))

const connectorsDoc = ref<ConnectorsLatestDoc | null>(null)
const radarAllCategories = ref(true)
const radarDoc = ref<{
  generated_at: string
  baseline_window_note: string
  items: RadarItem[]
}>({
  generated_at: '',
  baseline_window_note: '',
  items: [],
})

const filteredRadarItems = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  return radarDoc.value.items.filter((item) => {
    if (!radarAllCategories.value && activeCategory.value !== 'favorites' && item.category !== activeCategory.value) {
      return false
    }
    if (q) {
      const hay = `${item.title} ${item.why_in_radar || ''} ${item.signal_type || ''} ${item.entity_ids.join(' ')}`.toLowerCase()
      if (!hay.includes(q)) return false
    }
    return true
  })
})

const historyDisplay = computed(() => {
  if (!historyPath.value) return null
  const found = historyEntries.value.find(
    (e) => e.path.replace(/\/+$/, '') === historyPath.value?.replace(/\/+$/, ''),
  )
  if (found?.display) return found.display
  if (batchMeta.value?.fetched_at) {
    return formatShanghaiDateTime(batchMeta.value.fetched_at, false)
  }
  return historyPath.value
})

const rawHealth = computed(() =>
  evaluateRawHealth(batchMeta.value?.fetched_at, nowMs.value, batchMeta.value?.target_cadence_minutes ?? 60, {
    isHistory: isHistoryMode.value,
    status: batchMeta.value?.crawl_status,
    errorSources: batchMeta.value?.summary.error_sources,
    staleSources: batchMeta.value?.summary.stale_sources,
  }),
)

const allPlatformsFlat = computed(() => [
  ...platformsByCat.value.finance,
  ...platformsByCat.value.global,
  ...platformsByCat.value.tech,
  ...platformsByCat.value.general,
])

const platformsForCategory = computed(() => {
  if (activeCategory.value === 'favorites') {
    return allPlatformsFlat.value.filter((p) => favoriteSourceIds.value.has(p.id))
  }
  return platformsByCat.value[activeCategory.value] ?? []
})

const filteredPlatforms = computed(() =>
  filterRawPlatforms(allPlatformsFlat.value, {
    category: activeCategory.value,
    query: searchQuery.value,
    sourceId: sourceFilter.value,
    healthFilter: healthFilter.value,
    favoriteSourceIds: favoriteSourceIds.value,
  }),
)

const allDedupedClusters = computed(() => {
  const clusters = clusterRawPlatforms(filteredPlatforms.value, true)
  return filterRawClusters(clusters, {
    query: searchQuery.value,
    sourceId: sourceFilter.value,
    onlyFavorites: activeCategory.value === 'favorites',
    favoriteSourceIds: favoriteSourceIds.value,
  })
})

const hideDiscussionAndStale = ref(true)

const hiddenNoiseCount = computed(() => {
  if (!hideDiscussionAndStale.value) return 0
  return Math.max(0, allDedupedClusters.value.length - dedupedClusters.value.length)
})

const dedupedClusters = computed(() => {
  if (!hideDiscussionAndStale.value) return allDedupedClusters.value
  const cutoffMs = parseTimestampMs(batchMeta.value?.fetched_at) ?? nowMs.value
  const staleWindowMs = 72 * 3600 * 1000
  return allDedupedClusters.value.filter((cl) => {
    if (cl.source_kind === 'discussion') return false
    const pubMs = parseTimestampMs(cl.published_at)
    if (pubMs !== null && cutoffMs - pubMs > staleWindowMs) return false
    return true
  })
})

const zeroCoverageOkCount = computed(() =>
  batchMeta.value?.sources.filter((s) => s.status === 'ok' && (s.pub_date_coverage ?? 1) === 0).length ?? 0,
)

function formatShanghaiWithSeconds(iso: string | null | undefined): string {
  const ms = parseTimestampMs(iso)
  if (ms === null) return '时间未知'
  const parts = new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).formatToParts(new Date(ms))
  const m: Record<string, string> = {}
  for (const p of parts) m[p.type] = p.value
  return `${m.month}-${m.day} ${m.hour}:${m.minute}:${m.second}`
}

const healthReports = computed(() => {
  if (!batchMeta.value) return []
  return batchMeta.value.sources.filter((s) => {
    if (activeCategory.value !== 'favorites' && s.category !== activeCategory.value) return false
    if (activeCategory.value === 'favorites' && !favoriteSourceIds.value.has(s.id)) return false
    if (healthFilter.value === 'ok' && s.status !== 'ok') return false
    if (healthFilter.value === 'issue' && s.status === 'ok') return false
    if (searchQuery.value.trim()) {
      const q = searchQuery.value.trim().toLowerCase()
      return s.name.toLowerCase().includes(q) || s.id.toLowerCase().includes(q)
    }
    return true
  })
})

function syncUrl(replace = false) {
  const url = buildMonitorUrl({
    cat: activeCategory.value,
    history: historyPath.value,
    view: viewMode.value,
    q: searchQuery.value,
    source: sourceFilter.value,
    health: healthFilter.value,
  })
  syncUrlToBrowser(url, replace)
}

async function loadData(forceFresh = false) {
  loading.value = true
  errorMsg.value = null
  try {
    if (!historyPath.value) {
      manifest.value = await fetchManifest(forceFresh)
      pendingNewManifest.value = null
    }
    const res = await fetchRawBatch({
      archivePath: historyPath.value,
      manifest: manifest.value,
      forceFresh,
    })
    batchMeta.value = res.meta
    platformsByCat.value = res.platformsByCategory

    if (!historyPath.value) {
      const [cDoc, rDoc] = await Promise.all([
        fetchConnectorsLatest(manifest.value, forceFresh),
        fetchRadarItems(manifest.value, forceFresh),
      ])
      connectorsDoc.value = cDoc
      radarDoc.value = rDoc
    }
  } catch (err) {
    errorMsg.value = err instanceof Error ? err.message : '加载监控数据失败'
  } finally {
    loading.value = false
  }
}

function toggleFavoriteSource(sourceId: string) {
  const next = new Set(favoriteSourceIds.value)
  if (next.has(sourceId)) next.delete(sourceId)
  else next.add(sourceId)
  favoriteSourceIds.value = next
  saveFavoriteSourceIds(next)
}

function togglePlatformExpand(sourceId: string) {
  const next = new Set(expandedPlatforms.value)
  if (next.has(sourceId)) next.delete(sourceId)
  else next.add(sourceId)
  expandedPlatforms.value = next
}

function toggleClusterExpand(clusterId: string) {
  const next = new Set(expandedClusters.value)
  if (next.has(clusterId)) next.delete(clusterId)
  else next.add(clusterId)
  expandedClusters.value = next
}

function statusPillInfo(status: string) {
  switch (status) {
    case 'ok':
      return {
        label: '正常',
        cls: 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-800',
      }
    case 'empty':
      return {
        label: '无新内容',
        cls: 'bg-slate-100 text-slate-700 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700',
      }
    case 'stale':
      return {
        label: '长期滞后',
        cls: 'bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-950/60 dark:text-amber-300 dark:border-amber-800',
      }
    case 'retired':
      return {
        label: '上游已下线',
        cls: 'bg-slate-100 text-slate-600 border-slate-300 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700',
      }
    default:
      return {
        label: '请求失败',
        cls: 'bg-red-50 text-red-700 border-red-200 dark:bg-red-950/60 dark:text-red-300 dark:border-red-800',
      }
  }
}

async function openHistoryModal() {
  historyModalOpen.value = true
  if (historyEntries.value.length === 0) {
    await loadHistoryList()
  }
}

async function loadHistoryList(forceFresh = false) {
  historyLoading.value = true
  historyError.value = null
  try {
    historyEntries.value = await fetchHistoryIndex('raw', forceFresh)
  } catch (err) {
    historyError.value = err instanceof Error ? err.message : '加载历史快照索引失败'
  } finally {
    historyLoading.value = false
  }
}

async function selectHistoryEntry(entry: HistoryIndexEntry) {
  historyPath.value = entry.path.endsWith('/') ? entry.path : `${entry.path}/`
  historyModalOpen.value = false
  syncUrl(false)
  await loadData(false)
}

async function returnToLatest() {
  historyPath.value = null
  historyModalOpen.value = false
  syncUrl(false)
  await loadData(true)
}

async function handleManualRefresh() {
  isRefreshing.value = true
  try {
    await loadData(!isHistoryMode.value)
  } finally {
    isRefreshing.value = false
  }
}

async function checkForNewBatch() {
  if (isHistoryMode.value || !manifest.value) return
  const fresh = await fetchManifest(true)
  if (!fresh) return
  if (fresh.raw.latest_batch_id && fresh.raw.latest_batch_id !== manifest.value.raw.latest_batch_id) {
    await loadData(true)
  }
}

function clearFilters() {
  searchQuery.value = ''
  sourceFilter.value = 'all'
  healthFilter.value = 'all'
  syncUrl(true)
}

watch([activeCategory, viewMode], () => {
  if (sourceFilter.value !== 'all') sourceFilter.value = 'all'
  syncUrl(false)
})

watch([searchQuery, sourceFilter, healthFilter], () => {
  syncUrl(true)
})

function handlePopState() {
  const next = parseMonitorUrlState()
  const historyChanged = next.history !== historyPath.value
  activeCategory.value = next.cat
  historyPath.value = next.history
  viewMode.value = next.view
  searchQuery.value = next.q
  sourceFilter.value = next.source
  healthFilter.value = next.health
  if (historyChanged) {
    void loadData(false)
  }
}

onMounted(() => {
  applyDarkClass(isDark.value)
  const sess = loadAuthSession()
  const isAdm = isAdminRole(sess?.user.role)
  void apiGetPublicSettings().then((s) => {
    monitorAccessAllowed.value = Boolean(s.monitor_public || isAdm)
    monitorAccessChecked.value = true
    if (monitorAccessAllowed.value) {
      void loadData(false)
    }
  })
  clockTimer = setInterval(() => {
    nowMs.value = Date.now()
  }, 30_000)
  pollTimer = setInterval(() => {
    if (monitorAccessAllowed.value) {
      void checkForNewBatch()
    }
  }, 90_000)
  window.addEventListener('popstate', handlePopState)
})

onBeforeUnmount(() => {
  if (clockTimer) clearInterval(clockTimer)
  if (pollTimer) clearInterval(pollTimer)
  window.removeEventListener('popstate', handlePopState)
})
</script>

<template>
  <AppShell
    active-page="monitor"
    :is-dark="isDark"
    :is-history-mode="isHistoryMode"
    :history-display="historyDisplay"
    :is-refreshing="isRefreshing"
    :show-history-button="true"
    :show-bookmarks-button="false"
    :show-refresh-button="true"
    @toggle-dark="toggleDark"
    @open-history="openHistoryModal"
    @refresh="handleManualRefresh"
  >
    <template #top-banner>
      <div
        v-if="pendingNewManifest"
        class="bg-blue-600 text-white px-4 py-2 text-xs sm:text-sm"
      >
        <div class="max-w-6xl mx-auto flex flex-wrap items-center justify-between gap-2">
          <div class="flex items-center gap-2">
            <Bell class="w-4 h-4 shrink-0" />
            <span>
              有新更新批次 <strong>{{ formatFriendlyBatchId(pendingNewManifest.raw.latest_batch_id) }}</strong>
              （<SmartTime :iso="pendingNewManifest.raw.fetched_at" :now-ms="nowMs" />）
            </span>
          </div>
          <button
            type="button"
            @click="loadData(true)"
            class="px-3 py-1 rounded-md bg-white text-blue-700 font-semibold hover:bg-blue-50 transition-colors"
          >
            加载新快照
          </button>
        </div>
      </div>

      <div
        v-if="isHistoryMode"
        class="bg-indigo-600 text-white px-4 py-2 text-xs sm:text-sm"
      >
        <div class="max-w-6xl mx-auto flex flex-wrap items-center justify-between gap-2">
          <div class="flex items-center gap-2">
            <History class="w-4 h-4 shrink-0" />
            <span>历史时间快照：<strong>{{ historyDisplay }}</strong>（展示该历史时刻快照状态）</span>
          </div>
          <button
            type="button"
            @click="returnToLatest"
            class="inline-flex items-center gap-1 px-3 py-1 rounded-md bg-white text-indigo-700 font-semibold hover:bg-indigo-50"
          >
            <RotateCcw class="w-3.5 h-3.5" />
            <span>返回实时监控</span>
          </button>
        </div>
      </div>
    </template>

    <!-- Admin Visibility Gate -->
    <div
      v-if="monitorAccessChecked && !monitorAccessAllowed"
      class="max-w-lg mx-auto mt-10 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 text-center space-y-3 shadow-sm"
    >
      <h1 class="text-lg font-bold text-slate-900 dark:text-white">情报监控页当前仅对管理员开放</h1>
      <p class="text-xs sm:text-sm text-slate-500 dark:text-slate-400">
        管理员可在私有后台一键切换是否向普通用户公开此监控页面；如果您是管理员，请先登录管理员账号。
      </p>
      <div class="flex items-center justify-center gap-2.5 pt-2 text-xs font-semibold">
        <a href="./index.html" class="px-4 py-2 rounded-xl bg-indigo-600 text-white hover:bg-indigo-700">返回镜信首页</a>
        <a href="./admin.html" class="px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800">管理员登录</a>
      </div>
    </div>

    <div v-else-if="monitorAccessChecked" class="space-y-4 sm:space-y-5">
      <!-- Real Update Health & Timestamps Header -->
      <section
        class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 sm:p-5 shadow-xs space-y-3"
        aria-label="更新时间与信源健康状态"
      >
        <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
          <div class="space-y-1">
            <div class="flex flex-wrap items-center gap-2">
              <h1 class="text-lg sm:text-xl font-bold text-slate-900 dark:text-white tracking-tight">
                多源实时热点与信源监控
              </h1>
              <span
                v-if="loading && !batchMeta"
                class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border bg-slate-100 text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700"
              >
                加载实时元数据...
              </span>
              <span
                v-else
                class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold border"
                :class="rawHealth.pillClass"
              >
                {{ rawHealth.label }}
              </span>
            </div>
            <p class="text-xs text-slate-500 dark:text-slate-400">
              {{ loading && !batchMeta ? '正在加载最新更新批次、数据连接状态与分类热榜...' : `${rawHealth.detail} · 真实入库时间，刷新页面不会伪造“刚刚更新”。` }}
            </p>
          </div>

          <div
            v-if="batchMeta"
            class="grid grid-cols-2 sm:flex sm:flex-wrap gap-3 text-xs bg-slate-50 dark:bg-slate-800/70 rounded-xl px-3.5 py-2.5 border border-slate-200/80 dark:border-slate-700/80 tabular-nums"
          >
            <div>
              <span class="block text-[11px] text-slate-500 dark:text-slate-400">最近更新时间</span>
              <span class="font-semibold text-slate-900 dark:text-white">
                <SmartTime :iso="batchMeta.fetched_at" :now-ms="nowMs" />
              </span>
            </div>
            <div>
              <span class="block text-[11px] text-slate-500 dark:text-slate-400">信源在线率</span>
              <span class="font-semibold text-slate-900 dark:text-white">
                {{ batchMeta.summary.ok_sources }} / {{ batchMeta.summary.configured_sources }} 在线
              </span>
              <span
                v-if="batchMeta.summary.error_sources > 0"
                class="ml-1 text-red-600 dark:text-red-400 font-medium"
              >
                · {{ batchMeta.summary.error_sources }} 异常
              </span>
              <span
                v-if="batchMeta.summary.stale_sources > 0"
                class="ml-1 text-amber-600 dark:text-amber-400 font-medium"
              >
                · {{ batchMeta.summary.stale_sources }} 滞后
              </span>
              <span
                v-if="zeroCoverageOkCount > 0"
                class="ml-1 text-slate-500 dark:text-slate-400"
              >
                · {{ zeroCoverageOkCount }} 榜单无原文时间
              </span>
            </div>
            <div>
              <span class="block text-[11px] text-slate-500 dark:text-slate-400">收录 / 去重数</span>
              <span class="font-semibold text-slate-900 dark:text-white">
                {{ batchMeta.summary.total_raw_items }} 条 → {{ batchMeta.summary.deduped_events }} 簇
              </span>
            </div>
            <div v-if="batchMeta.summary.retired_sources > 0">
              <span class="block text-[11px] text-slate-500 dark:text-slate-400">已下线清理源</span>
              <span class="font-semibold text-slate-700 dark:text-slate-300">
                {{ batchMeta.summary.retired_sources }} 个
              </span>
            </div>
          </div>
        </div>
      </section>

      <!-- Tabs, View Switcher, Search & Source Filter -->
      <section class="space-y-3">
        <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-2.5">
          <!-- Category Tabs -->
          <div class="flex flex-wrap items-center gap-1.5" role="tablist" aria-label="监控分类">
            <button
              v-for="cat in CATEGORIES"
              :key="cat.id"
              type="button"
              role="tab"
              :aria-selected="activeCategory === cat.id"
              @click="activeCategory = cat.id"
              class="inline-flex items-center gap-2 px-3 min-h-[38px] rounded-xl text-sm font-medium border transition-colors"
              :class="
                activeCategory === cat.id
                  ? 'bg-slate-900 text-white border-slate-900 dark:bg-blue-600 dark:border-blue-600'
                  : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50 dark:bg-slate-900 dark:text-slate-300 dark:border-slate-800 dark:hover:bg-slate-800'
              "
            >
              <span class="w-2 h-2 rounded-full" :class="cat.accentDotClass" />
              <span>{{ cat.shortName }}</span>
              <span class="text-xs opacity-75 tabular-nums">{{ platformsByCat[cat.id].length }} 源</span>
            </button>

            <button
              type="button"
              role="tab"
              :aria-selected="activeCategory === 'favorites'"
              @click="activeCategory = 'favorites'"
              class="inline-flex items-center gap-1.5 px-3 min-h-[38px] rounded-xl text-sm font-medium border transition-colors"
              :class="
                activeCategory === 'favorites'
                  ? 'bg-amber-600 text-white border-amber-600'
                  : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50 dark:bg-slate-900 dark:text-slate-300 dark:border-slate-800 dark:hover:bg-slate-800'
              "
            >
              <Star class="w-3.5 h-3.5" :class="{ 'fill-current': activeCategory === 'favorites' }" />
              <span>关注源 ({{ favoriteSourceIds.size }})</span>
            </button>
          </div>

          <!-- View Switcher (Default: Readable Stream, Optional: Source Matrix, Health Panel, Connectors & Radar) -->
          <div
            class="flex flex-wrap rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-1 gap-1 self-start"
            role="group"
            aria-label="切换监控视图"
          >
            <button
              type="button"
              @click="viewMode = 'stream'"
              class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium"
              :class="
                viewMode === 'stream'
                  ? 'bg-blue-600 text-white shadow-xs'
                  : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'
              "
            >
              <List class="w-3.5 h-3.5" />
              <span>聚合阅读流</span>
            </button>
            <button
              type="button"
              @click="viewMode = 'radar'"
              class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium"
              :class="
                viewMode === 'radar'
                  ? 'bg-blue-600 text-white shadow-xs'
                  : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'
              "
            >
              <Radio class="w-3.5 h-3.5" />
              <span>全网异动雷达 ({{ radarDoc.items.length }})</span>
            </button>
            <button
              type="button"
              @click="viewMode = 'connectors'"
              class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium"
              :class="
                viewMode === 'connectors'
                  ? 'bg-blue-600 text-white shadow-xs'
                  : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'
              "
            >
              <Database class="w-3.5 h-3.5" />
              <span>一手连接器 ({{ connectorsDoc?.summary.total_connectors ?? 0 }})</span>
            </button>
            <button
              type="button"
              @click="viewMode = 'matrix'"
              class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium"
              :class="
                viewMode === 'matrix'
                  ? 'bg-blue-600 text-white shadow-xs'
                  : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'
              "
            >
              <LayoutGrid class="w-3.5 h-3.5" />
              <span>来源矩阵</span>
            </button>
            <button
              type="button"
              @click="viewMode = 'health'"
              class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium"
              :class="
                viewMode === 'health'
                  ? 'bg-blue-600 text-white shadow-xs'
                  : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'
              "
            >
              <Activity class="w-3.5 h-3.5" />
              <span>信源健康 ({{ batchMeta?.summary.error_sources || 0 }} 异常)</span>
            </button>
          </div>
        </div>

        <!-- Search + Explicit Source / Health Filters -->
        <div class="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-3 flex flex-col sm:flex-row gap-2">
          <div class="relative flex-1">
            <Search class="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input
              v-model="searchQuery"
              type="search"
              placeholder="搜索热点标题、摘要、平台名..."
              aria-label="搜索实时热点"
              class="w-full pl-9 pr-9 h-10 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-sm text-slate-900 dark:text-white placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              v-if="searchQuery"
              type="button"
              @click="searchQuery = ''"
              class="absolute right-2 top-1/2 -translate-y-1/2 w-6 h-6 inline-flex items-center justify-center rounded text-slate-400 hover:text-slate-700 dark:hover:text-white"
              aria-label="清空搜索词"
            >
              <X class="w-4 h-4" />
            </button>
          </div>

          <select
            v-model="sourceFilter"
            aria-label="按单一来源过滤"
            class="h-10 px-2.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-xs sm:text-sm text-slate-700 dark:text-slate-200 sm:max-w-[200px]"
          >
            <option value="all">全部来源 ({{ platformsForCategory.length }})</option>
            <option v-for="p in platformsForCategory" :key="p.id" :value="p.id">
              {{ p.name }} ({{ p.items.length || p.fallback_items?.length || 0 }})
            </option>
          </select>

          <select
            v-model="healthFilter"
            aria-label="按信源状态过滤"
            class="h-10 px-2.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-xs sm:text-sm text-slate-700 dark:text-slate-200"
          >
            <option value="all">全部状态</option>
            <option value="ok">仅正常信源</option>
            <option value="issue">仅异常/滞后信源</option>
          </select>
        </div>
      </section>

      <!-- Loading & Error -->
      <div
        v-if="loading"
        class="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-10 text-center space-y-2"
      >
        <RefreshCw class="w-6 h-6 animate-spin text-blue-600 mx-auto" />
        <p class="text-sm text-slate-600 dark:text-slate-300">正在加载实时信源与聚类事件...</p>
      </div>

      <div
        v-else-if="errorMsg"
        class="rounded-xl border border-red-200 dark:border-red-900 bg-red-50/70 dark:bg-red-950/30 p-6 text-center space-y-3"
      >
        <AlertTriangle class="w-7 h-7 text-red-600 mx-auto" />
        <p class="text-sm text-red-800 dark:text-red-200">{{ errorMsg }}</p>
        <button
          type="button"
          @click="handleManualRefresh"
          class="px-4 py-2 rounded-lg bg-red-600 text-white text-sm font-medium hover:bg-red-700"
        >
          重试加载
        </button>
      </div>

      <!-- View 1: Default Continuous Readable Stream (Deduped Events) -->
      <section v-else-if="viewMode === 'stream'" class="space-y-3" aria-label="去重聚合新闻流">
        <div class="flex flex-wrap items-center justify-between gap-2 px-1 text-xs text-slate-600 dark:text-slate-400">
          <div class="flex flex-wrap items-center gap-2">
            <span>
              已聚合去重为 <strong class="text-slate-900 dark:text-white tabular-nums">{{ dedupedClusters.length }}</strong> 条独立事件
              （合并重复 URL 与相似标题）
            </span>
            <button
              type="button"
              @click="hideDiscussionAndStale = !hideDiscussionAndStale"
              class="px-2 py-0.5 rounded border text-[11px] font-medium transition-colors"
              :class="
                hideDiscussionAndStale
                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800'
                  : 'bg-slate-100 text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700'
              "
            >
              {{
                hideDiscussionAndStale
                  ? `已过滤 ${hiddenNoiseCount} 条讨论贴/72h前旧闻 · 点此查看全量`
                  : '当前含讨论贴与全部旧闻 · 点此仅看72h新闻与一手'
              }}
            </button>
          </div>
          <button
            v-if="searchQuery || sourceFilter !== 'all' || healthFilter !== 'all'"
            type="button"
            @click="clearFilters"
            class="text-blue-600 dark:text-blue-400 hover:underline font-medium"
          >
            重置筛选
          </button>
        </div>

        <div
          v-if="dedupedClusters.length === 0"
          class="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 text-center text-sm text-slate-500 dark:text-slate-400 space-y-2"
        >
          <p v-if="activeCategory === 'favorites' && favoriteSourceIds.size === 0">
            你还没有收藏任何信息源。可以切换到任意分类，在「来源矩阵」或「信源健康」中点击星标添加关注源。
          </p>
          <p v-else>当前筛选条件下没有匹配的监控内容。</p>
        </div>

        <div v-else class="space-y-2.5">
          <article
            v-for="cluster in dedupedClusters"
            :key="cluster.cluster_id"
            class="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 space-y-2 hover:border-slate-300 dark:hover:border-slate-700 transition-colors"
          >
            <div class="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500 dark:text-slate-400">
              <div class="flex flex-wrap items-center gap-1.5">
                <span class="font-semibold text-slate-800 dark:text-slate-200">
                  {{ cluster.appearances[0]?.source_name }}
                </span>
                <span
                  v-if="cluster.appearances.length > 1"
                  class="px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 dark:bg-blue-950/60 dark:text-blue-300 font-medium"
                >
                  共 {{ cluster.appearances.length }} 个来源报道
                </span>
                <span
                  v-if="cluster.appearances.some((a) => a.is_fallback)"
                  class="px-2 py-0.5 rounded bg-amber-50 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300"
                >
                  含降级缓存条目
                </span>
                <span
                  v-if="cluster.metric_label"
                  class="px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300 tabular-nums"
                >
                  {{ cluster.metric_label }}
                </span>
              </div>

              <div class="flex items-center gap-2 tabular-nums">
                <span class="inline-flex items-center gap-1">
                  <Clock class="w-3.5 h-3.5" />
                  {{
                    cluster.published_at
                      ? `原文 ${formatShanghaiDateTime(cluster.published_at, false)}`
                      : `采集 ${formatShanghaiDateTime(cluster.fetched_at, false)}`
                  }}
                </span>
              </div>
            </div>

            <div class="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2">
              <div class="space-y-1 min-w-0">
                <h2 class="text-sm sm:text-base font-bold text-slate-900 dark:text-white leading-snug">
                  <a
                    v-if="normalizeExternalUrl(cluster.primary_url)"
                    :href="normalizeExternalUrl(cluster.primary_url)!"
                    target="_blank"
                    rel="noopener noreferrer"
                    @click.stop
                    class="hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
                  >
                    {{ cluster.primary_title }}
                  </a>
                  <span v-else>{{ cluster.primary_title }}</span>
                </h2>
                <p v-if="sanitizeExcerptText(cluster.excerpt)" class="text-xs sm:text-sm text-slate-600 dark:text-slate-400 leading-relaxed">
                  {{ sanitizeExcerptText(cluster.excerpt) }}
                </p>
              </div>

              <div class="flex items-center gap-2 shrink-0">
                <a
                  v-if="normalizeExternalUrl(cluster.primary_url)"
                  :href="normalizeExternalUrl(cluster.primary_url)!"
                  target="_blank"
                  rel="noopener noreferrer"
                  @click.stop
                  class="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium bg-slate-100 hover:bg-blue-50 text-slate-700 hover:text-blue-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-blue-950/60"
                >
                  <span>原文</span>
                  <ExternalLink class="w-3 h-3" />
                </a>
                <span
                  v-else
                  class="inline-flex items-center px-2.5 py-1.5 rounded-lg text-xs text-slate-400 dark:text-slate-500 bg-slate-50 dark:bg-slate-800/50 cursor-not-allowed"
                >
                  暂无原文直链
                </span>
                <button
                  v-if="cluster.appearances.length > 1"
                  type="button"
                  @click="toggleClusterExpand(cluster.cluster_id)"
                  class="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800"
                >
                  <span>{{ expandedClusters.has(cluster.cluster_id) ? '收起' : `查看 ${cluster.appearances.length} 源` }}</span>
                  <ChevronUp v-if="expandedClusters.has(cluster.cluster_id)" class="w-3.5 h-3.5" />
                  <ChevronDown v-else class="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            <!-- Multi-source appearances list -->
            <ul
              v-if="expandedClusters.has(cluster.cluster_id)"
              class="pt-2 border-t border-slate-100 dark:border-slate-800 space-y-1.5 text-xs"
            >
              <li
                v-for="app in cluster.appearances"
                :key="app.item_id"
                class="flex flex-wrap items-center justify-between gap-2 text-slate-600 dark:text-slate-300"
              >
                <div class="flex items-center gap-2 min-w-0">
                  <span class="font-medium text-slate-800 dark:text-slate-200 shrink-0">
                    {{ app.source_name }}
                  </span>
                  <span class="truncate">{{ app.title }}</span>
                </div>
                <a
                  v-if="normalizeExternalUrl(app.url)"
                  :href="normalizeExternalUrl(app.url)!"
                  target="_blank"
                  rel="noopener noreferrer"
                  @click.stop
                  class="inline-flex items-center gap-1 text-blue-600 dark:text-blue-400 hover:underline shrink-0"
                >
                  <span>打开</span>
                  <ExternalLink class="w-3 h-3" />
                </a>
                <span v-else class="text-slate-400 dark:text-slate-500 shrink-0">暂无直链</span>
              </li>
            </ul>
          </article>
        </div>
      </section>

      <!-- View V3-A: Whole-Web Change Radar -->
      <section v-else-if="viewMode === 'radar'" class="space-y-3" aria-label="全网异动信号雷达">
        <div class="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 space-y-2 text-xs">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <h2 class="text-sm sm:text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
              <Radio class="w-4 h-4 text-rose-600 dark:text-rose-400" />
              <span>
                全网异动雷达 · {{ radarAllCategories || activeCategory === 'favorites' ? '全站' : '当前分类' }}命中 {{ filteredRadarItems.length }} / 全站 {{ radarDoc.items.length }} 条
              </span>
            </h2>
            <div class="flex items-center gap-2">
              <button
                type="button"
                @click="radarAllCategories = !radarAllCategories"
                class="px-2.5 py-1 rounded-lg border text-xs font-medium"
                :class="radarAllCategories ? 'bg-rose-600 text-white border-rose-600' : 'bg-slate-50 text-slate-700 border-slate-200 dark:bg-slate-800 dark:text-slate-200 dark:border-slate-700'"
              >
                {{ radarAllCategories ? '仅看当前分类' : `看全站全部 (${radarDoc.items.length})` }}
              </button>
              <span v-if="radarDoc.generated_at" class="text-slate-500 dark:text-slate-400 tabular-nums">
                计算于 <SmartTime :iso="radarDoc.generated_at" :now-ms="nowMs" />
              </span>
            </div>
          </div>
          <p v-if="radarDoc.baseline_window_note" class="text-slate-600 dark:text-slate-300">
            {{ radarDoc.baseline_window_note }}
          </p>
        </div>

        <div
          v-if="filteredRadarItems.length === 0"
          class="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 text-center text-sm text-slate-500 dark:text-slate-400"
        >
          当前分类/关键词筛选下暂无异动信号（请切换顶部分类或清空关键词）。
        </div>

        <div v-else class="space-y-2.5">
          <article
            v-for="item in filteredRadarItems"
            :key="item.event_id"
            class="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 space-y-2"
          >
            <div class="flex flex-wrap items-center justify-between gap-2 text-xs">
              <div class="flex flex-wrap items-center gap-1.5">
                <span class="px-2 py-0.5 rounded-full bg-rose-50 text-rose-800 border border-rose-200 dark:bg-rose-950/60 dark:text-rose-200 dark:border-rose-800 font-bold tabular-nums">
                  异动评分 {{ item.radar_score }}
                </span>
                <span v-if="item.signal_type" class="px-2 py-0.5 rounded bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300 font-medium">
                  {{ item.signal_type }}
                </span>
                <span class="px-2 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200 dark:bg-blue-950/50 dark:text-blue-300 dark:border-blue-800">
                  {{ item.independent_publisher_count }} 家独立媒体 · 转载 {{ item.reprint_count }} 次
                </span>
              </div>

              <span v-if="item.first_discovered_at" class="text-slate-500 dark:text-slate-400 tabular-nums">
                首见 {{ formatShanghaiDateTime(item.first_discovered_at, false) }}
              </span>
            </div>

            <h3 class="text-sm sm:text-base font-bold text-slate-900 dark:text-white leading-snug">
              {{ item.title }}
            </h3>

            <p v-if="item.why_in_radar" class="text-xs text-slate-600 dark:text-slate-300">
              <strong>触发缘由：</strong>{{ item.why_in_radar }}
            </p>

            <div class="flex flex-wrap items-center gap-2 pt-1 text-xs">
              <a
                v-if="item.storyline_id"
                :href="`./index.html?tab=tracking&story=${encodeURIComponent(item.storyline_id)}`"
                class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700"
              >
                <GitBranch class="w-3.5 h-3.5" />
                <span>进入事件档案 & 跨批次 Diff</span>
              </a>
              <a
                v-if="normalizeExternalUrl(item.primary_url)"
                :href="normalizeExternalUrl(item.primary_url)!"
                target="_blank"
                rel="noopener noreferrer"
                @click.stop
                class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800"
              >
                <span>查看原文</span>
                <ExternalLink class="w-3 h-3" />
              </a>
              <span
                v-else
                class="inline-flex items-center px-2.5 py-1 rounded-lg border border-slate-100 dark:border-slate-800 text-slate-400 dark:text-slate-500 cursor-not-allowed"
              >
                暂无原文直链
              </span>
            </div>
          </article>
        </div>
      </section>

      <!-- View V3-B: First-Party Connectors Telemetry -->
      <section v-else-if="viewMode === 'connectors'" class="space-y-4" aria-label="一手官方数据源连接器状态">
        <div
          v-if="!connectorsDoc"
          class="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 text-center text-sm text-slate-500 dark:text-slate-400"
        >
          {{ isHistoryMode ? '历史归档快照未附带连接器遥测文件，请切回最新批次查看连接器状态。' : '未读取到一手连接器遥测数据（data/connectors_latest.json）。' }}
        </div>

        <template v-else>
          <div class="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 flex flex-wrap items-center justify-between gap-3 text-xs">
            <div class="space-y-1">
              <h2 class="text-sm sm:text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
                <Database class="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                <span>V3 一手官方数据源连接器实时遥测</span>
              </h2>
              <p class="text-slate-500 dark:text-slate-400">
                正常运行 {{ connectorsDoc.summary.healthy_connectors }} / {{ connectorsDoc.summary.total_connectors }} 路 · 一手条目 {{ connectorsDoc.summary.total_first_party_items }} 条 · 工具台账 {{ connectorsDoc.summary.tech_tools_count }} 款 · 日历排期 {{ connectorsDoc.summary.calendar_events_count }} 项
              </p>
            </div>
            <span class="text-slate-500 dark:text-slate-400 tabular-nums">
              最近探测 {{ formatShanghaiDateTime(connectorsDoc.fetched_at, false) }}
            </span>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
            <article
              v-for="conn in connectorsDoc.connectors"
              :key="conn.connector_id"
              class="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 space-y-2 text-xs"
            >
              <div class="flex items-start justify-between gap-2">
                <div>
                  <h3 class="text-sm font-bold text-slate-900 dark:text-white">
                    {{ sanitizePublicNote(conn.connector_name) }}
                  </h3>
                  <p class="text-[11px] text-slate-500 dark:text-slate-400 font-mono">
                    {{ conn.connector_id }} · {{ conn.source_tier }}
                  </p>
                </div>
                <span
                  class="px-2 py-0.5 rounded-full text-[11px] font-semibold border shrink-0"
                  :class="
                    conn.status === 'ok' || conn.status === 'cached_304'
                      ? 'bg-emerald-50 text-emerald-800 border-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-200 dark:border-emerald-800'
                      : conn.status === 'partial' || conn.status === 'empty'
                        ? 'bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-950/60 dark:text-amber-200 dark:border-amber-800'
                        : 'bg-red-50 text-red-700 border-red-200 dark:bg-red-950/60 dark:text-red-300 dark:border-red-800'
                  "
                >
                  {{ conn.status }}
                </span>
              </div>

              <div class="flex flex-wrap gap-3 text-slate-600 dark:text-slate-300 tabular-nums">
                <span>一手条目：<strong>{{ conn.item_count }}</strong></span>
                <span v-if="conn.calendar_count">日历事件：<strong>{{ conn.calendar_count }}</strong></span>
                <span>耗时：<strong>{{ conn.latency_ms }} ms</strong></span>
                <span>探测：{{ formatShanghaiDateTime(conn.fetched_at, false) }}</span>
              </div>

              <p v-if="conn.tos_note" class="rounded-lg bg-slate-50 dark:bg-slate-800/70 border border-slate-200/80 dark:border-slate-700 px-2.5 py-1.5 text-[11px] text-slate-600 dark:text-slate-300 leading-relaxed">
                服务说明：{{ sanitizePublicNote(conn.tos_note) }}
              </p>
              <p v-if="conn.error_message" class="rounded-lg bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 px-2.5 py-1.5 text-[11px] text-red-700 dark:text-red-300">
                异常信息：{{ conn.error_message }}
              </p>
            </article>
          </div>
        </template>
      </section>

      <!-- View 2: Source Matrix (Clean responsive cards, NO fixed inner card scrollbars!) -->
      <section v-else-if="viewMode === 'matrix'" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4" aria-label="来源矩阵视图">
        <div
          v-if="filteredPlatforms.length === 0"
          class="col-span-full rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 text-center text-sm text-slate-500 dark:text-slate-400"
        >
          没有符合条件的信源卡片。
        </div>

        <article
          v-for="platform in filteredPlatforms"
          :key="platform.id"
          class="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 flex flex-col justify-between gap-3"
        >
          <div class="space-y-3">
            <div class="flex items-start justify-between gap-2 border-b border-slate-100 dark:border-slate-800 pb-2.5">
              <div class="min-w-0">
                <div class="flex items-center gap-2 flex-wrap">
                  <h2 class="text-sm font-bold text-slate-900 dark:text-white truncate">
                    {{ platform.name }}
                  </h2>
                  <span
                    class="text-[11px] px-1.5 py-0.5 rounded border font-medium"
                    :class="statusPillInfo(platform.status).cls"
                  >
                    {{ statusPillInfo(platform.status).label }}
                  </span>
                </div>
                <p class="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5 tabular-nums">
                  采集：{{ formatShanghaiDateTime(platform.fetched_at, false) }}
                  <template v-if="platform.last_success_at && platform.status !== 'ok'">
                    · 上次成功：{{ formatShanghaiDateTime(platform.last_success_at, false) }}
                  </template>
                </p>
              </div>

              <button
                type="button"
                @click="toggleFavoriteSource(platform.id)"
                class="w-8 h-8 inline-flex items-center justify-center rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 shrink-0"
                :aria-label="favoriteSourceIds.has(platform.id) ? `取消关注 ${platform.name}` : `关注 ${platform.name}`"
                :aria-pressed="favoriteSourceIds.has(platform.id)"
              >
                <Star
                  class="w-4 h-4"
                  :class="favoriteSourceIds.has(platform.id) ? 'text-amber-500 fill-current' : 'text-slate-400'"
                />
              </button>
            </div>

            <div
              v-if="platform.error_message && platform.status !== 'ok'"
              class="rounded-lg bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900 p-2.5 text-xs text-red-700 dark:text-red-300"
            >
              异常说明：{{ platform.error_message }}
              <span v-if="platform.fallback_used && platform.fallback_items?.length" class="block mt-1 font-medium">
                当前临时展示上次成功缓存（{{ platform.fallback_items.length }} 条）。
              </span>
            </div>

            <!-- Item list (natural height, expandable instead of inner card scrollbar) -->
            <ul class="space-y-2 text-xs sm:text-sm">
              <li
                v-for="(item, idx) in (expandedPlatforms.has(platform.id)
                  ? (platform.items.length ? platform.items : platform.fallback_items || [])
                  : (platform.items.length ? platform.items : platform.fallback_items || []).slice(0, 8))"
                :key="item.item_id || idx"
                class="flex items-start gap-2 leading-snug"
              >
                <span class="text-xs font-mono text-slate-400 w-5 shrink-0 tabular-nums">{{ idx + 1 }}.</span>
                <div class="min-w-0 flex-1">
                  <a
                    v-if="normalizeExternalUrl(item.url)"
                    :href="normalizeExternalUrl(item.url)!"
                    target="_blank"
                    rel="noopener noreferrer"
                    @click.stop
                    class="text-slate-800 dark:text-slate-200 hover:text-blue-600 dark:hover:text-blue-400 break-words"
                  >
                    {{ item.title }}
                  </a>
                  <span v-else class="text-slate-800 dark:text-slate-200">{{ item.title }}</span>
                  <span v-if="item.metric_label" class="ml-1.5 text-[11px] text-slate-400">
                    {{ item.metric_label }}
                  </span>
                </div>
              </li>
            </ul>
          </div>

          <button
            v-if="(platform.items.length || platform.fallback_items?.length || 0) > 8"
            type="button"
            @click="togglePlatformExpand(platform.id)"
            class="w-full py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 text-xs font-medium text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800"
          >
            {{
              expandedPlatforms.has(platform.id)
                ? '收起部分条目'
                : `展开全部 ${platform.items.length || platform.fallback_items?.length || 0} 条`
            }}
          </button>
        </article>
      </section>

      <!-- View 3: Source Health Diagnostics -->
      <section v-else class="space-y-4" aria-label="信源健康诊断面板">
        <div class="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden">
          <div class="px-4 py-3 border-b border-slate-200 dark:border-slate-800 flex flex-wrap items-center justify-between gap-2">
            <h2 class="text-sm font-bold text-slate-900 dark:text-white">
              信源采集健康台账 ({{ healthReports.length }} 个信源)
            </h2>
            <span class="text-xs text-slate-500 dark:text-slate-400">
              区分「正常 / 无新内容 / 请求失败 / 长期滞后 / 已下线清理」
            </span>
          </div>

          <div class="divide-y divide-slate-100 dark:divide-slate-800">
            <div
              v-for="rep in healthReports"
              :key="rep.id"
              class="px-4 py-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 text-xs sm:text-sm"
            >
              <div class="space-y-1">
                <div class="flex items-center gap-2 flex-wrap">
                  <CheckCircle2 v-if="rep.status === 'ok'" class="w-4 h-4 text-emerald-600 shrink-0" />
                  <XCircle v-else class="w-4 h-4 text-red-600 shrink-0" />
                  <span class="font-semibold text-slate-900 dark:text-white">{{ rep.name }}</span>
                  <code class="text-[11px] text-slate-500 font-mono">{{ rep.id }}</code>
                  <span
                    class="text-[11px] px-1.5 py-0.5 rounded border font-medium"
                    :class="
                      rep.status === 'ok' && (rep.pub_date_coverage ?? 1) === 0 && rep.item_count > 0
                        ? 'bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-950/50 dark:text-amber-300 dark:border-amber-800'
                        : statusPillInfo(rep.status).cls
                    "
                  >
                    {{
                      rep.status === 'ok' && (rep.pub_date_coverage ?? 1) === 0 && rep.item_count > 0
                        ? '在线 · 榜单无原文时间'
                        : statusPillInfo(rep.status).label
                    }}
                  </span>
                </div>
                <p v-if="rep.error_message" class="text-xs text-red-600 dark:text-red-400">
                  原因：{{ rep.error_message }}
                </p>
              </div>

              <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500 dark:text-slate-400 tabular-nums">
                <span>条目：{{ rep.item_count }}</span>
                <span v-if="rep.pub_date_coverage !== undefined">
                  时间覆盖：{{ rep.pub_date_coverage === 0 ? '0%（热点榜按采集时间入库）' : `${Math.round(rep.pub_date_coverage * 100)}%` }}
                </span>
                <span>最后成功：{{ formatShanghaiWithSeconds(rep.last_success_at) }}</span>
                <button
                  type="button"
                  @click="toggleFavoriteSource(rep.id)"
                  class="inline-flex items-center gap-1 text-xs font-medium text-slate-600 dark:text-slate-300 hover:text-amber-600"
                >
                  <Star class="w-3.5 h-3.5" :class="{ 'text-amber-500 fill-current': favoriteSourceIds.has(rep.id) }" />
                  <span>{{ favoriteSourceIds.has(rep.id) ? '已关注' : '关注' }}</span>
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- Retired V1 sources transparency notice -->
        <div
          v-if="batchMeta?.retired_sources?.length"
          class="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-100/70 dark:bg-slate-900/60 p-4 space-y-2"
        >
          <h3 class="text-xs sm:text-sm font-bold text-slate-800 dark:text-slate-200">
            V2.0 清理的长期失效上游接口 ({{ batchMeta.retired_sources.length }})
          </h3>
          <ul class="space-y-1 text-xs text-slate-600 dark:text-slate-400">
            <li v-for="ret in batchMeta.retired_sources" :key="ret.id">
              • <strong>{{ ret.name }}</strong> (<code class="font-mono">{{ ret.id }}</code>)：{{ ret.reason }}
            </li>
          </ul>
        </div>
      </section>
    </div>

    <TimeMachineModal
      :is-open="historyModalOpen"
      mode="raw"
      :entries="historyEntries"
      :loading="historyLoading"
      :error="historyError"
      :current-history-path="historyPath"
      @close="historyModalOpen = false"
      @select="selectHistoryEntry"
      @return-latest="returnToLatest"
      @retry="loadHistoryList(true)"
    />
  </AppShell>
</template>
