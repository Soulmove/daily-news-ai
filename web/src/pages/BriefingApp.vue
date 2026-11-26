<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  Bell,
  Bookmark,
  Bot,
  Building2,
  Calendar,
  CalendarRange,
  CheckCheck,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  CircleDot,
  Clock,
  Compass,
  Copy,
  Cpu,
  ExternalLink,
  Filter,
  Flame,
  GitBranch,
  Globe,
  HelpCircle,
  History,
  Info,
  Keyboard,
  Layers,
  Lightbulb,
  MapPin,
  MessageSquarePlus,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightOpen,
  Radio,
  RefreshCw,
  RotateCcw,
  Scale,
  Search,
  Shield,
  Sparkles,
  Target,
  Trash2,
  TrendingUp,
  User,
  X,
  Zap,
} from 'lucide-vue-next'
import AppShell from '../components/AppShell.vue'
import AuthModal from '../components/AuthModal.vue'
import AvatarPickerModal from '../components/AvatarPickerModal.vue'
import EmptySearchState from '../components/EmptySearchState.vue'
import LoadingSkeleton from '../components/LoadingSkeleton.vue'
import ShareCardModal, { type ShareCardPayload } from '../components/ShareCardModal.vue'
import SmartTime from '../components/SmartTime.vue'
import SoftAuthPromptModal, { type SoftAuthScenario } from '../components/SoftAuthPromptModal.vue'
import { appLang, pickBiText, syncHtmlLangAttr, t, toggleAppLang, translateEntityName } from '../core/i18n'
import { useDialogBehavior } from '../core/dialog'
import { lockBodyScroll, triggerHaptic, unlockBodyScroll } from '../core/uiPrefs'
import {
  globalQuotesStore,
  seedGlobalQuotesFromFinanceDoc,
  startGlobalQuotesPolling,
  stopGlobalQuotesPolling,
} from '../core/quotesStore'
import { normalizeExternalUrl } from '../core/legacyAdapter'
import {
  computeEchoChamberReport,
  computeWeeklyReadingReport,
  getTodayShanghaiDate,
  loadDailyReadingState,
  recordEventReadInHistory,
  recordTodayReadEvents,
  saveDailyReadingState,
  syncDailyStateToHistory,
} from '../core/readingProgress'
import { invalidateReactionsCache, loadReactionsBatch } from '../core/reactionsStore'
import {
  buildThreeColumnPerspectives,
  isOnboardingCompleted,
  setOnboardingCompleted,
  type WatchlistPresetTemplate,
} from '../core/thumbnails'
import {
  createLiveWireController,
  type LiveWireStreamHandle,
  type WireTransportMode,
} from '../core/wireStream'
import {
  dispatchImportantNewsNotification,
  isAndroidAppShell,
  isImportantPushEnabled,
  setImportantPushEnabledWithStatus,
  syncAndroidStatusBarTheme,
} from '../core/mobilePush'
import {
  apiFetchMe,
  apiFetchPredictionArena,
  apiFetchPredictionCrowd,
  apiFetchPublicOverrides,
  apiGetPublicSettings,
  apiPullCloudState,
  apiPushCloudState,
  apiSubmitPredictionProposal,
  apiSubmitPredictionVote,
  clearAuthSession,
  isAdminRole,
  loadAuthSession,
  saveAuthSession,
  type ArenaLeaderboardRow,
  type AuthSession,
  type DailyPredictionRow,
  type PublicSiteSettings,
  type UserPredictionProfile,
} from '../core/auth'
import {
  applyEditorialOverridesToEvents,
  applyEditorialOverridesToWire,
  type EditorialOverridesDoc,
} from '../core/overrides'
import { dedupeVisibleTodayEvents } from '../core/v3Logic'
import EventCard from '../components/EventCard.vue'
import SimulatedPerspectives from '../components/SimulatedPerspectives.vue'
import AiProgressView from '../components/v3/AiProgressView.vue'
import CalendarView from '../components/v3/CalendarView.vue'
import DesktopContextRail from '../components/v3/DesktopContextRail.vue'
import EntityDrawer from '../components/v3/EntityDrawer.vue'
import EvidenceQaModal from '../components/v3/EvidenceQaModal.vue'
import FinanceImpactView from '../components/v3/FinanceImpactView.vue'
import LiveWireView from '../components/v3/LiveWireView.vue'
import MobileMeView from '../components/v3/MobileMeView.vue'
import PredictionsView from '../components/v3/PredictionsView.vue'
import ReadingWeeklyReportModal from '../components/v3/ReadingWeeklyReportModal.vue'
import OnboardingGuideModal from '../components/v3/OnboardingGuideModal.vue'
import TechToolsView from '../components/v3/TechToolsView.vue'
import TodayView from '../components/v3/TodayView.vue'
import TrackingView from '../components/v3/TrackingView.vue'
import WeeklyDigestView from '../components/v3/WeeklyDigestView.vue'
import {
  fetchAiProgress,
  fetchCalendarEvents,
  fetchEntitiesIndex,
  fetchFinanceImpact,
  fetchHistoryIndex,
  fetchLiveWire,
  fetchMajorTopics,
  fetchManifest,
  fetchPredictionsPublic,
  fetchSimulatedComments,
  fetchSmartCategory,
  fetchStorylinesIndex,
  fetchTechTools,
  fetchWeeklyDigest,
  fetchWeeklyDigestsIndex,
} from '../core/fetcher'
import {
  extractSmartSourceOptions,
  extractTopEntities,
  filterSmartEvents,
  isEventMuted,
  matchesSmartQuery,
} from '../core/search'
import {
  type BookmarkedEvent,
  type CatalystOverrideEntry,
  type LocalToolState,
  type PredictionStance,
  type ReadLaterMetaEntry,
  clearLocalResearchState,
  exportAllResearchState,
  importResearchStateJson,
  mergeResearchStateJson,
  isEventRead,
  isNewSincePreviousVisit,
  loadAlertRules,
  loadBookmarkedEvents,
  loadCatalystOverrideMap,
  loadCustomCatalysts,
  loadHideReprints,
  loadLocalPredictions,
  loadPortfolioConfig,
  loadPredictionStances,
  loadReadLaterMetaMap,
  loadReadState,
  loadResearchNotes,
  loadStringSetKey,
  loadToolStates,
  loadUserAvatar,
  loadVisitBaseline,
  loadWatchlist,
  migrateCollidingEventStates,
  readDarkMode,
  resolveReadLaterEventsList,
  saveAlertRules,
  saveBookmarkedEvents,
  saveCatalystOverrideMap,
  saveCustomCatalysts,
  saveHideReprints,
  saveLocalPredictions,
  savePredictionStances,
  saveReadLaterMetaMap,
  saveReadState,
  saveResearchNotes,
  saveStringSetKey,
  saveToolStates,
  saveUserAvatar,
  saveVisitBaseline,
  saveWatchlist,
  writeDarkMode,
} from '../core/storage'
import {
  evaluateSmartHealth,
  formatFriendlyBatchId,
  formatShanghaiDateOnly,
  formatShanghaiDateTime,
  formatShanghaiHhMm,
  parseTimestampMs,
} from '../core/time'
import {
  type AiProgressDoc,
  type AlertRuleSettings,
  CATEGORIES,
  type CatalystEvent,
  type CategoryKey,
  type CrowdPredictionStat,
  type EntityProfile,
  type EvidenceStatus,
  type FinanceImpactDoc,
  type HistoryIndexEntry,
  type LiveWireDoc,
  type MajorTopicSpotlight,
  type ManifestV2,
  type PortfolioConfig,
  type PredictionRecord,
  type ResearchNote,
  type SimulatedCommentsDoc,
  type SimulatedPerspective,
  type SmartCategoryDoc,
  type SmartEvent,
  type StorylineDossier,
  type TechToolEntry,
  type WatchlistItem,
  type WeeklyDigestDoc,
  type WeeklyDigestItem,
  type WeeklyDigestsIndexDoc,
  type WeeklySectorId,
} from '../core/types'
import {
  buildBriefingUrl,
  type FreshnessBucket,
  hasInvalidBriefingUrlParams,
  parseBriefingUrlState,
  syncUrlToBrowser,
  type WorkbenchTab,
} from '../core/urlState'
import {
  buildMorningBriefSummary,
  countMatchingNotesForSubject,
  countUpcomingCatalystsWithinHours,
  DEFAULT_PAGE_SIZE,
  getEventRecommendationReasons,
  matchEventAgainstWatchlist,
  matchImpactAgainstPortfolio,
  mergePredictions,
  paginateItems,
  sortEvents,
  type EventSortMode,
} from '../core/v3Logic'

const ALL_CATS: CategoryKey[] = ['finance', 'global', 'tech', 'general']

// Theme & Clock
const isDark = ref(readDarkMode())
const nowMs = ref(Date.now())
let clockTimer: ReturnType<typeof setInterval> | null = null
let pollTimer: ReturnType<typeof setInterval> | null = null
let wireStreamHandle: LiveWireStreamHandle | null = null
const wireTransportMode = ref<WireTransportMode>('polling')
const justArrivedWireIds = ref<string[]>([])
const justArrivedAiIds = ref<string[]>([])
const isAndroidApp = isAndroidAppShell()
const mobilePushEnabled = ref<boolean>(isImportantPushEnabled())

async function handleToggleMobilePush() {
  const next = !mobilePushEnabled.value
  const res = await setImportantPushEnabledWithStatus(next)
  mobilePushEnabled.value = res.enabled
  if (res.enabled && res.permission === 'denied') {
    notifyToast(
      t(
        '已开启站内重磅提醒（系统弹窗通知需在浏览器设置中放行）',
        'In-app breaking alerts enabled (browser popups blocked by site settings)',
      ),
    )
  } else {
    notifyToast(
      res.enabled
        ? t('已开启重要快讯与一手 AI 推送通知', 'Important wire & first-hand AI alerts enabled')
        : t('已暂停重要消息推送通知', 'Mobile alert notifications paused'),
    )
  }
}

function applyDarkClass(dark: boolean) {
  if (typeof document !== 'undefined') {
    const root = document.documentElement
    root.classList.toggle('dark', dark)
    root.style.colorScheme = dark ? 'dark' : 'light'
    const metaTheme = document.querySelector('meta[name="theme-color"]')
    if (metaTheme) {
      metaTheme.setAttribute('content', dark ? '#000000' : '#F2F2F7')
    }
  }
  syncAndroidStatusBarTheme(dark)
}

function toggleDark() {
  const current =
    typeof document !== 'undefined'
      ? document.documentElement.classList.contains('dark')
      : isDark.value
  const next = !current
  isDark.value = next
  applyDarkClass(next)
  writeDarkMode(next)
}

// URL-synchronized state (consolidating briefing->today/pillars, tools->ai_progress/tools, predictions->calendar/predictions)
const initialUrl = parseBriefingUrlState()
const activeTab = ref<WorkbenchTab>(
  initialUrl.tab === 'briefing'
    ? 'today'
    : initialUrl.tab === 'tools'
      ? 'ai_progress'
      : initialUrl.tab === 'predictions'
        ? 'calendar'
        : initialUrl.tab,
)
const todaySection = ref<'feed' | 'pillars' | 'topics' | 'cocoon'>(
  initialUrl.tab === 'briefing' || Boolean(initialUrl.history) ? 'pillars' : 'feed',
)
const onlyBlindspot = ref<boolean>(false)
const aiSubView = ref<'tracker' | 'tools'>(initialUrl.tab === 'tools' ? 'tools' : 'tracker')
const scheduleSubView = ref<'calendar' | 'predictions'>(initialUrl.tab === 'calendar' && !initialUrl.pred ? 'calendar' : 'predictions')
const libraryTab = ref<'saved' | 'read_later' | 'notes'>('saved')
const menuCloseNonce = ref(0)
const activeCategory = ref<CategoryKey>(initialUrl.cat)
const historyPath = ref<string | null>(initialUrl.history)
const highlightedEventId = ref<string | null>(initialUrl.event)
const selectedStorylineId = ref<string | null>(initialUrl.story)
const selectedTopicId = ref<string | null>(null)
const drawerEntityKey = ref<string | null>(initialUrl.entity)
const freshBucket = ref<FreshnessBucket>(initialUrl.fresh)
const searchQuery = ref<string>(initialUrl.q)
const searchScope = ref<'current' | 'all'>(initialUrl.scope)
const sourceFilter = ref<string>(initialUrl.source)
const evidenceFilter = ref<'all' | EvidenceStatus>(initialUrl.evidence)
const onlyUnreadOrNew = ref<boolean>(initialUrl.unread)
const selectedEntity = ref<string>('')

// Data state
const manifest = ref<ManifestV2 | null>(null)
const pendingNewManifest = ref<ManifestV2 | null>(null)
const docsByCat = ref<Partial<Record<CategoryKey, SmartCategoryDoc>>>({})
const loadingCat = ref(false)
const loadingAllCats = ref(false)
const isRefreshing = ref(false)

// V3 Workbench Datasets (lazy-loaded on tab/drawer access)
const entities = ref<EntityProfile[]>([])
const entitiesLoaded = ref(false)
const storylinesMap = ref<Record<string, StorylineDossier>>({})
const storylinesLoaded = ref(false)
const storylinesLoading = ref(false)
const serverCalendarEvents = ref<CatalystEvent[]>([])
const calendarLoaded = ref(false)
const calendarLoading = ref(false)
const techTools = ref<TechToolEntry[]>([])
const toolsLoaded = ref(false)
const toolsLoading = ref(false)
const seedPredictions = ref<PredictionRecord[]>([])
const dailyArenaPredictions = ref<PredictionRecord[]>([])
const arenaProfile = ref<UserPredictionProfile | null>(null)
const arenaLeaderboard = ref<ArenaLeaderboardRow[]>([])
const arenaReasonTags = ref<string[]>(['流动性驱动', '业绩超预期', '市场已计价', '政策博弈', '逆向情绪'])
const arenaSeasonKey = ref('')
const predictionBonusQaQuota = ref(0)
const sharedPortfolioPreview = ref<{ sectors: string[]; tickers: string[] } | null>(null)
const focusedEventModalEvent = ref<SmartEvent | null>(null)
const predictionsNote = ref('')
const predictionsLoaded = ref(false)
const predictionsLoading = ref(false)
const majorTopics = ref<MajorTopicSpotlight[]>([])
const archivedTopics = ref<MajorTopicSpotlight[]>([])
const topicsLoaded = ref(false)
const topicsLoading = ref(false)
const pillarDateRange = ref<'today' | '3d' | '7d' | 'archive'>(initialUrl.history ? 'archive' : 'today')
const pillarCalendarOpen = ref(false)
const pillarSelectedDate = ref('')
const pillarRangeLoading = ref(false)
const archiveCatCache = ref<Record<string, SmartCategoryDoc>>({})
const pillarRangeEvents = ref<SmartEvent[]>([])
const aiProgressDoc = ref<AiProgressDoc | null>(null)
const aiProgressLoaded = ref(false)
const financeImpactDoc = ref<FinanceImpactDoc | null>(null)
const financeImpactLoaded = ref(false)
const liveWireDoc = ref<LiveWireDoc | null>(null)
const liveWireLoaded = ref(false)
const WEEKLY_LAST_SEEN_KEY = 'mirrorbrief_last_seen_week_v1'
const weeklyDigestDoc = ref<WeeklyDigestDoc | null>(null)
const weeklyDigestsIndexDoc = ref<WeeklyDigestsIndexDoc | null>(null)
const selectedWeekId = ref<string | null>(initialUrl.week || null)
const weeklyLoading = ref(false)
const weeklyLoaded = ref(false)
const lastSeenWeekId = ref<string | null>(
  typeof window !== 'undefined' ? window.localStorage.getItem(WEEKLY_LAST_SEEN_KEY) : null,
)
const hasUnreadWeekly = computed(() =>
  Boolean(weeklyDigestDoc.value?.week_id && weeklyDigestDoc.value.week_id !== lastSeenWeekId.value),
)
const siteSettings = ref<PublicSiteSettings>({
  monitor_public: false,
  site_banner_enabled: false,
  site_banner_text: '',
  site_banner_tone: 'info',
})
const siteSettingsLoaded = ref(false)
const siteBannerDismissed = ref(false)
const editorialOverrides = ref<EditorialOverridesDoc | null>(null)

const siteAccessMode = computed<'private_gate' | 'invite_only' | 'public'>(() => {
  const m = siteSettings.value.access_mode
  if (m === 'private_gate' || m === 'invite_only' || m === 'public') return m
  return 'invite_only'
})
const isPrivateGateLocked = computed(() => siteAccessMode.value === 'private_gate' && !authSession.value)

const showGlobalBanner = computed(() =>
  Boolean(!siteBannerDismissed.value && siteSettings.value.site_banner_enabled && (siteSettings.value.site_banner_text || '').trim()),
)

const effectiveLiveWireDoc = computed<LiveWireDoc | null>(() => {
  const doc = liveWireDoc.value
  if (!doc) return null
  const patchedItems = applyEditorialOverridesToWire(doc.items || [], editorialOverrides.value)
  return { ...doc, items: patchedItems, total: patchedItems.length }
})

async function refreshSiteSettingsAndOverrides() {
  try {
    const [settingsRes, overridesRes] = await Promise.all([
      apiGetPublicSettings(),
      apiFetchPublicOverrides(),
    ])
    siteSettings.value = settingsRes
    if (overridesRes) editorialOverrides.value = overridesRes
  } catch {
    // Keep defaults silently
  } finally {
    siteSettingsLoaded.value = true
  }
}

function openFeedbackFromRail() {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('infofocus-open-feedback'))
  }
}
const clearConfirmModalOpen = ref(false)
const onboardingModalOpen = ref(false)
const onboardingCompleted = ref(isOnboardingCompleted())
const weeklyReportOpen = ref(false)
const briefingSortBy = ref<EventSortMode>('latest')
const briefingVisibleLimit = ref(DEFAULT_PAGE_SIZE)
const bookmarkSearchQuery = ref('')
const bookmarkTagFilter = ref('all')
const editingBookmarkTagId = ref<string | null>(null)
const editingBookmarkTagText = ref('')

// V3 User-Local Research State (browser localStorage only)
const LEGACY_CATALYST_OVERRIDES_KEY = 'daily_news_ai_v3_catalyst_overrides_v1'
function loadUnifiedCatalystOverrides(): Record<string, CatalystOverrideEntry> {
  const unified = { ...loadCatalystOverrideMap() }
  try {
    if (typeof window !== 'undefined' && window.localStorage) {
      const legacyRaw = window.localStorage.getItem(LEGACY_CATALYST_OVERRIDES_KEY)
      if (legacyRaw) {
        const parsed = JSON.parse(legacyRaw) as Record<string, CatalystOverrideEntry>
        if (parsed && typeof parsed === 'object') {
          let mergedAny = false
          for (const [k, v] of Object.entries(parsed)) {
            if (v && !unified[k]) {
              unified[k] = v
              mergedAny = true
            }
          }
          if (mergedAny) {
            saveCatalystOverrideMap(unified)
          }
          window.localStorage.removeItem(LEGACY_CATALYST_OVERRIDES_KEY)
        }
      }
    }
  } catch {
    // Ignore storage migration errors
  }
  return unified
}

const watchlist = ref<WatchlistItem[]>(loadWatchlist())
const mutedSet = ref<Set<string>>(loadStringSetKey('muted'))
const downweightedSet = ref<Set<string>>(loadStringSetKey('downweighted'))
const readLaterSet = ref<Set<string>>(loadStringSetKey('read_later'))
const readLaterMetaMap = ref<Record<string, ReadLaterMetaEntry>>(loadReadLaterMetaMap())
const hideReprints = ref<boolean>(loadHideReprints())
const alertRules = ref<AlertRuleSettings>(loadAlertRules())
const localPredictions = ref<PredictionRecord[]>(loadLocalPredictions())
const toolStates = ref<Record<string, LocalToolState>>(loadToolStates())
const researchNotes = ref<ResearchNote[]>(loadResearchNotes())
const customCatalysts = ref<CatalystEvent[]>(loadCustomCatalysts())
const catalystOverrides = ref<Record<string, CatalystOverrideEntry>>(loadUnifiedCatalystOverrides())
const predictionStances = ref<Record<string, PredictionStance>>(loadPredictionStances())

// Inline Cross-Batch Fact Diff Modal ("对照前批" without losing current scroll/context)
const batchDiffModalOpen = ref(false)
const batchDiffLoading = ref(false)
const batchDiffTargetBatchId = ref('')
const batchDiffCurrentEvent = ref<SmartEvent | null>(null)
const batchDiffPrevEvent = ref<SmartEvent | null>(null)
const batchDiffStoryline = ref<StorylineDossier | null>(null)

// B5 Dialog Stack Accessibility Refs for inline modals
const bookmarksModalRef = ref<HTMLElement | null>(null)
const batchDiffModalRef = ref<HTMLElement | null>(null)
const clearConfirmModalRef = ref<HTMLElement | null>(null)

// Evidence Q&A Modal & Workbench Toast (supports actionable links per B12)
const qaModalOpen = ref(false)
const qaContextEvent = ref<SmartEvent | null>(null)
const qaContextStoryline = ref<StorylineDossier | null>(null)
const qaContextEntity = ref<EntityProfile | null>(null)
const qaContextTopic = ref<MajorTopicSpotlight | null>(null)
const qaContextPrompt = ref<string | null>(null)
interface ToastPayload {
  text: string
  actionLabel?: string
  onAction?: () => void
}
const workbenchToast = ref<ToastPayload | null>(null)
let toastTimer: ReturnType<typeof setTimeout> | null = null

function notifyToast(
  msg: string,
  opts?: { actionLabel?: string; onAction?: () => void },
) {
  workbenchToast.value = {
    text: msg,
    actionLabel: opts?.actionLabel,
    onAction: opts?.onAction,
  }
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => {
    workbenchToast.value = null
  }, 4200)
}

// Overview, Hero & Perspectives collapse controls
const showBatchMetaDetails = ref(false)
const overviewExpanded = ref(false)
const perspectivesOpen = ref(false)
const perspectivesLoading = ref(false)
const commentsByKey = ref<Record<string, SimulatedCommentsDoc>>({})

// Category history cache for 3D/7D range in Pillars view & diff modal
const historyEntries = ref<HistoryIndexEntry[]>([])
const historyLoading = ref(false)
const historyError = ref<string | null>(null)

// Bookmarks modal
const bookmarksModalOpen = ref(false)
const bookmarks = ref<BookmarkedEvent[]>(loadBookmarkedEvents())

const { requestClose: requestCloseBookmarks } = useDialogBehavior({
  isOpen: bookmarksModalOpen,
  containerRef: bookmarksModalRef,
  onClose: () => {
    bookmarksModalOpen.value = false
  },
})

const { requestClose: requestCloseBatchDiff } = useDialogBehavior({
  isOpen: batchDiffModalOpen,
  containerRef: batchDiffModalRef,
  onClose: () => {
    batchDiffModalOpen.value = false
  },
})

const { requestClose: requestCloseClearConfirm } = useDialogBehavior({
  isOpen: clearConfirmModalOpen,
  containerRef: clearConfirmModalRef,
  onClose: () => {
    clearConfirmModalOpen.value = false
  },
})

// Daily read state
const dailyReading = ref(loadDailyReadingState(nowMs.value))
const returnToFinanceTab = ref(false)

// Read & Visit baseline state
const readState = loadReadState()
const readIds = ref<Set<string>>(readState.readIds)
const legacyReadTitles = ref<Set<string>>(readState.legacyReadTitles)
const initialBaseline = loadVisitBaseline()
const previousBatchId = ref<string | null>(initialBaseline.last_batch_id)
const previousVisitedAt = ref<string | null>(initialBaseline.last_visited_at)
const previousSeenIds = ref<Set<string>>(new Set(initialBaseline.seen_event_ids))
const userPortfolio = ref<PortfolioConfig>(loadPortfolioConfig())
const financeInitialPortfolioOnly = ref(false)
function openFinancePortfolioHits() {
  financeInitialPortfolioOnly.value = true
  void switchTab('finance')
}

const returnVisitSummary = computed(() => {
  const prevMs = previousVisitedAt.value ? parseTimestampMs(previousVisitedAt.value) : null
  const watchHits = allLoadedEvents.value.filter((ev) => {
    const mr = matchEventAgainstWatchlist(ev, watchlist.value, mutedSet.value, downweightedSet.value, nowMs.value)
    if (!mr.matched) return false
    const evMs = parseTimestampMs(ev.latest_reported_at || ev.latest_fact_update_at || ev.first_reported_at || ev.fetched_at)
    if (prevMs !== null && evMs !== null) return evMs > prevMs
    if (previousBatchId.value) return !previousSeenIds.value.has(ev.event_id)
    return evMs !== null && nowMs.value - evMs <= 24 * 3_600_000
  }).length
  const portHits = (financeImpactDoc.value?.event_impacts || []).filter(
    (imp) => matchImpactAgainstPortfolio(imp, userPortfolio.value).matched,
  ).length
  const cal48h = countUpcomingCatalystsWithinHours(mergedServerCalendarEvents.value, nowMs.value, 48).length
  return { watchHits, portHits, cal48h }
})

const canonicalTodayEvents = computed<SmartEvent[]>(() =>
  allLoadedEvents.value.filter((ev) => !isEventMuted(ev, mutedSet.value)),
)

const categoryEventCounts = computed<Record<CategoryKey, number>>(() => {
  const counts: Record<CategoryKey, number> = { finance: 0, global: 0, tech: 0, general: 0 }
  for (const c of ALL_CATS) {
    const doc = docsByCat.value[c]
    if (doc && !doc.missing) {
      const overridden = applyEditorialOverridesToEvents(doc.events, editorialOverrides.value)
      counts[c] = overridden.filter((ev) => !isEventMuted(ev, mutedSet.value)).length
    }
  }
  return counts
})

const displayRailIndices = computed(() =>
  globalQuotesStore.indices.value.length > 0
    ? globalQuotesStore.indices.value
    : (financeImpactDoc.value?.index_quotes || []),
)

const batchTotalCount = computed(() => canonicalTodayEvents.value.length)
const batchReadCount = computed(() =>
  canonicalTodayEvents.value.filter((ev) => isEventRead(ev, readIds.value, legacyReadTitles.value)).length,
)
const historicalReadCount = computed(() =>
  Math.max(readIds.value.size, legacyReadTitles.value.size, dailyReading.value.readEventIdsToday.length),
)
const morningBriefSummary = computed(() =>
  buildMorningBriefSummary(
    financeImpactDoc.value?.event_impacts || [],
    userPortfolio.value,
    watchlist.value,
    mergedServerCalendarEvents.value,
    nowMs.value,
  ),
)

const activeDoc = computed<SmartCategoryDoc | null>(
  () => docsByCat.value[activeCategory.value] ?? null,
)

const isHistoryMode = computed(() => Boolean(historyPath.value))

const historyDisplay = computed(() => {
  if (!historyPath.value) return null
  const found = historyEntries.value.find(
    (e) => e.path.replace(/\/+$/, '') === historyPath.value?.replace(/\/+$/, ''),
  )
  if (found?.display) return found.display
  if (activeDoc.value?.generated_at) {
    return formatShanghaiDateTime(activeDoc.value.generated_at, false)
  }
  return historyPath.value
})

const fallbackCategoryLabels = computed<string[]>(() => {
  if (isHistoryMode.value || !manifest.value) return []
  return CATEGORIES.filter((cat) => manifest.value?.smart.categories?.[cat.id]?.is_fallback).map((cat) =>
    t(cat.name, cat.nameEn),
  )
})

const hasAnyFallbackCat = computed(() => fallbackCategoryLabels.value.length > 0)

const smartHealth = computed(() => {
  const genIso = activeDoc.value?.generated_at || (!isHistoryMode.value ? manifest.value?.smart.generated_at : null)
  const quota = !isHistoryMode.value ? manifest.value?.gemini_quota : undefined
  return evaluateSmartHealth(genIso, nowMs.value, {
    isHistory: isHistoryMode.value,
    status: !isHistoryMode.value ? manifest.value?.smart.status : undefined,
    hasFallbackCat: Boolean(activeDoc.value?.is_fallback || hasAnyFallbackCat.value),
    fallbackCategories: fallbackCategoryLabels.value,
    rawFetchedAtIso: !isHistoryMode.value ? manifest.value?.raw.fetched_at : null,
    rawStatus: !isHistoryMode.value ? manifest.value?.raw.status : undefined,
    errorSources: !isHistoryMode.value ? manifest.value?.raw.summary?.error_sources : undefined,
    quotaDegraded: Boolean(quota && quota.total_configured_keys > 0 && quota.healthy_keys === 0),
  })
})

const newerRawAvailable = computed(() => {
  if (isHistoryMode.value || !manifest.value) return false
  const rawMs = parseTimestampMs(manifest.value.raw.fetched_at)
  const cutoffMs = parseTimestampMs(activeDoc.value?.input_cutoff_at || manifest.value.smart.input_cutoff_at)
  if (rawMs === null || cutoffMs === null) return false
  return rawMs - cutoffMs > 5 * 60_000
})

const currentCommentsKey = computed(
  () => `${historyPath.value || 'latest'}::${activeCategory.value}::${activeDoc.value?.batch_id || ''}`,
)

const activeCommentsDoc = computed<SimulatedCommentsDoc | null>(
  () => commentsByKey.value[currentCommentsKey.value] ?? null,
)

const showSimulatedPerspectives = computed<boolean>(() => {
  const doc = activeCommentsDoc.value
  if (doc) {
    return (doc.comments?.length ?? 0) > 0 && doc.status !== 'not_generated' && doc.status !== 'missing'
  }
  if (isHistoryMode.value && historyPath.value) {
    const cur = historyPath.value.replace(/\/+$/, '')
    const entry = historyEntries.value.find((e) => e.path.replace(/\/+$/, '') === cur)
    return entry ? Boolean(entry.has_comments) : false
  }
  const catMeta = manifest.value?.smart?.categories?.[activeCategory.value]
  return Boolean(catMeta?.has_comments)
})

const allLoadedEvents = computed<SmartEvent[]>(() => {
  const combined: SmartEvent[] = []
  for (const c of ALL_CATS) {
    const doc = docsByCat.value[c]
    if (doc && !doc.missing) {
      combined.push(...doc.events)
    }
  }
  return applyEditorialOverridesToEvents(combined, editorialOverrides.value)
})

const allCatsReady = computed<boolean>(() =>
  ALL_CATS.every((c) => Boolean(docsByCat.value[c])),
)

const visibleTodayEvents = computed<SmartEvent[]>(() =>
  dedupeVisibleTodayEvents(allLoadedEvents.value, hideReprints.value, {
    alertRules: alertRules.value,
    mutedSet: mutedSet.value,
    watchlist: watchlist.value,
    downweightedSet: downweightedSet.value,
    nowMs: nowMs.value,
  }),
)

const bookmarkedIdSet = computed(() => new Set(bookmarks.value.map((b) => b.event_id)))

const mergedPredictions = computed(() => {
  const combinedSeeds: PredictionRecord[] = []
  const seen = new Set<string>()
  for (const dp of dailyArenaPredictions.value) {
    if (!seen.has(dp.prediction_id)) {
      seen.add(dp.prediction_id)
      combinedSeeds.push(dp)
    }
  }
  for (const sp of seedPredictions.value) {
    if (!seen.has(sp.prediction_id)) {
      seen.add(sp.prediction_id)
      combinedSeeds.push(sp)
    }
  }
  return mergePredictions(combinedSeeds, localPredictions.value)
})

const localPredictionIdSet = computed(
  () => new Set(localPredictions.value.map((p) => p.prediction_id)),
)

const mergedServerCalendarEvents = computed<CatalystEvent[]>(() => {
  const seenIds = new Set<string>()
  const activeMapped = serverCalendarEvents.value.map((ev) => {
    seenIds.add(ev.calendar_id)
    const over = catalystOverrides.value[ev.calendar_id]
    if (!over) return ev
    return {
      ...ev,
      actual_result: over.actualResult || ev.actual_result,
      post_deviation: over.deviation || ev.post_deviation,
    }
  })

  // Preserve user-recorded actuals across batch rotations using stored eventSnapshot
  const preservedFromPastBatches: CatalystEvent[] = []
  for (const [cid, over] of Object.entries(catalystOverrides.value)) {
    if (seenIds.has(cid)) continue
    if (!over || (!over.actualResult && !over.deviation)) continue
    const snap = over.eventSnapshot
    preservedFromPastBatches.push({
      calendar_id: cid,
      title: snap?.title || `历史批次催化事件 (${cid})`,
      scheduled_at: snap?.scheduled_at ?? over.updatedAt ?? null,
      original_time_note: snap?.original_time_note || '上批次排期 · 已记录实测结果（跨批次永久保留）',
      timezone: snap?.timezone || 'Asia/Shanghai',
      certainty: snap?.certainty || 'confirmed_official',
      certainty_label: '已记录复盘 · 跨批次保留',
      is_past: true,
      category: snap?.category || 'finance',
      entity_ids: snap?.entity_ids || [],
      storyline_id: snap?.storyline_id ?? null,
      watch_variable: snap?.watch_variable || '已录入实际兑现结果与预期偏差的跨批次留存事件',
      pre_expectation: snap?.pre_expectation || null,
      actual_result: over.actualResult || snap?.actual_result || null,
      post_deviation: over.deviation || snap?.post_deviation || null,
      source_name: snap?.source_name || '本地跨批次复盘留存',
      source_url: snap?.source_url ?? null,
    })
  }
  return [...activeMapped, ...preservedFromPastBatches]
})

const calendarTabTotalCount = computed<number>(() => {
  if (!calendarLoaded.value) {
    return manifest.value?.v3?.calendar_count || 0
  }
  const ids = new Set<string>()
  for (const c of customCatalysts.value) ids.add(c.calendar_id)
  for (const s of mergedServerCalendarEvents.value) ids.add(s.calendar_id)
  return ids.size
})

const activeDrawerEntity = computed<EntityProfile | null>(() => {
  const key = drawerEntityKey.value?.trim().toLowerCase()
  if (!key) return null
  return (
    entities.value.find(
      (e) =>
        e.entity_id.toLowerCase() === key ||
        e.canonical_name.toLowerCase() === key ||
        e.aliases.some((a) => a.toLowerCase() === key),
    ) ?? null
  )
})

const loadedEventsForScope = computed<SmartEvent[]>(() => {
  if (searchScope.value === 'all') {
    return allLoadedEvents.value
  }
  return activeDoc.value && !activeDoc.value.missing
    ? applyEditorialOverridesToEvents(activeDoc.value.events, editorialOverrides.value)
    : []
})

const pillarBaseEvents = computed<SmartEvent[]>(() => {
  if (!isHistoryMode.value && (pillarDateRange.value === '3d' || pillarDateRange.value === '7d')) {
    return pillarRangeEvents.value.length > 0
      ? applyEditorialOverridesToEvents(pillarRangeEvents.value, editorialOverrides.value)
      : loadedEventsForScope.value
  }
  return loadedEventsForScope.value
})

const sourceFilterOptions = computed(() =>
  extractSmartSourceOptions(pillarBaseEvents.value),
)

const evidenceFilterLabel = computed(() => {
  switch (evidenceFilter.value) {
    case 'official_confirmed':
      return t('一手官方证实', 'Official')
    case 'multi_source':
      return t('多源交叉印证', 'Multi-Source')
    case 'single_source':
      return t('单一来源', 'Single Source')
    case 'needs_verification':
      return t('待核实线索', 'Unverified')
    default:
      return t('全部可信度', 'All Evidence')
  }
})

const briefingSortLabel = computed(() => {
  if (briefingSortBy.value === 'credibility') return t('可信度最高', 'Credibility')
  if (briefingSortBy.value === 'relevance') return t('关注相关', 'Watchlist')
  return t('最新时间', 'Latest')
})

const sourceFilterLabel = computed(() => {
  if (sourceFilter.value === 'all') {
    return t(`全部媒体 (${sourceFilterOptions.value.length})`, `All Sources (${sourceFilterOptions.value.length})`)
  }
  const found = sourceFilterOptions.value.find((o) => o.id === sourceFilter.value)
  return found ? `${found.name} (${found.count})` : sourceFilter.value
})

const topEntities = computed(() =>
  extractTopEntities(pillarBaseEvents.value, 10),
)

function checkIsRead(ev: SmartEvent): boolean {
  return isEventRead(ev, readIds.value, legacyReadTitles.value)
}

function checkIsNew(ev: SmartEvent): boolean {
  return isNewSincePreviousVisit(ev, previousSeenIds.value, previousBatchId.value)
}

function checkIsBookmarked(ev: SmartEvent): boolean {
  return bookmarks.value.some((b) => b.event_id === ev.event_id)
}

const filteredEvents = computed(() => {
  const unmuted = pillarBaseEvents.value.filter((ev) => !isEventMuted(ev, mutedSet.value))
  const base = filterSmartEvents(unmuted, {
    query: searchQuery.value,
    evidence: evidenceFilter.value,
    sourceId: sourceFilter.value,
    entity: selectedEntity.value,
    onlyUnreadOrNew: onlyUnreadOrNew.value,
    unreadChecker: (ev) => !checkIsRead(ev) || checkIsNew(ev),
  })
  if (!onlyBlindspot.value) return base
  return base.filter(
    (ev) =>
      !checkIsRead(ev) &&
      (ev.sources?.length ?? 0) > 0 &&
      ev.evidence_status !== 'needs_verification' &&
      !matchEventAgainstWatchlist(ev, watchlist.value, mutedSet.value, downweightedSet.value, nowMs.value).matched,
  )
})

const sortedBriefingEvents = computed(() =>
  sortEvents(
    filteredEvents.value,
    briefingSortBy.value,
    watchlist.value,
    mutedSet.value,
    downweightedSet.value,
    nowMs.value,
  ),
)

const isVerifiedProvenanceEvent = (ev: SmartEvent) =>
  (ev.sources?.length ?? 0) > 0 && ev.evidence_status !== 'needs_verification'

const verifiedBriefingEvents = computed(() => {
  if (evidenceFilter.value === 'needs_verification') return sortedBriefingEvents.value
  return sortedBriefingEvents.value.filter(isVerifiedProvenanceEvent)
})

const unverifiedBriefingEvents = computed(() => {
  if (evidenceFilter.value === 'needs_verification') return []
  return sortedBriefingEvents.value.filter((ev) => !isVerifiedProvenanceEvent(ev))
})

const pagedBriefingEvents = computed(() =>
  paginateItems(verifiedBriefingEvents.value, briefingVisibleLimit.value),
)

const savedNoteMap = computed<Record<string, string>>(() => {
  const m: Record<string, string> = {}
  for (const n of researchNotes.value) {
    if (n.target_type === 'event' && n.target_id && !(n.target_id in m)) {
      m[n.target_id] = n.answer_markdown
    }
  }
  return m
})

const commentsByCatForCards = computed<Record<string, import('../core/types').SimulatedPerspective[]>>(() => {
  const m: Record<string, import('../core/types').SimulatedPerspective[]> = {}
  for (const [key, doc] of Object.entries(commentsByKey.value)) {
    const cat = key.split(':')[0]
    if (doc?.comments?.length && !m[cat]) {
      m[cat] = doc.comments
    }
  }
  return m
})

const allBookmarkTags = computed(() => {
  const tags = new Set<string>()
  for (const b of bookmarks.value) {
    for (const tg of b.tags || []) {
      if (tg.trim()) tags.add(tg.trim())
    }
  }
  return Array.from(tags).sort()
})

const filteredBookmarks = computed(() => {
  const q = bookmarkSearchQuery.value.trim()
  return bookmarks.value.filter((b) => {
    if (bookmarkTagFilter.value !== 'all' && !(b.tags || []).includes(bookmarkTagFilter.value)) {
      return false
    }
    if (q) {
      const hay = `${b.title} ${b.source_name} ${(b.tags || []).join(' ')} ${b.note || ''}`
      if (!matchesSmartQuery(hay, q)) return false
    }
    return true
  })
})

const newOrUnreadCountInActive = computed(() => {
  const events = (activeDoc.value?.events ?? []).filter((ev) => !isEventMuted(ev, mutedSet.value))
  return events.filter((ev) => !checkIsRead(ev) || checkIsNew(ev)).length
})

const isBriefingFiltered = computed(
  () =>
    evidenceFilter.value !== 'all' ||
    sourceFilter.value !== 'all' ||
    Boolean(selectedEntity.value) ||
    onlyUnreadOrNew.value,
)

const filteredKeyChanges = computed(() => {
  if (!activeDoc.value || activeDoc.value.missing) return []
  const keyItems = activeDoc.value.key_changes ?? []
  const pool = isBriefingFiltered.value
    ? filteredEvents.value
    : activeDoc.value.events.filter((ev) => !isEventMuted(ev, mutedSet.value))
  if (pool.length === 0) return []
  const poolById = new Map(pool.map((e) => [e.event_id, e]))
  const matchedKeys = isBriefingFiltered.value
    ? keyItems.filter((k) => Boolean(k.event_id && poolById.has(k.event_id)))
    : [...keyItems]
  const usedIds = new Set(matchedKeys.map((k) => k.event_id).filter(Boolean))
  for (const ev of pool) {
    if (matchedKeys.length >= 3) break
    if (usedIds.has(ev.event_id)) continue
    usedIds.add(ev.event_id)
    const primarySrc = ev.sources[0]
    matchedKeys.push({
      headline: ev.title,
      detail: ev.fact_summary || ev.summary || '',
      event_id: ev.event_id,
      primary_url: primarySrc?.url ?? null,
      source_name: primarySrc?.source_name ?? null,
      source_count: ev.sources.length,
    })
  }
  return matchedKeys.slice(0, 3)
})

function syncUrl(replace = false) {
  const url = buildBriefingUrl({
    tab: activeTab.value,
    cat: activeCategory.value,
    history: historyPath.value,
    event: highlightedEventId.value,
    story: selectedStorylineId.value,
    entity: drawerEntityKey.value,
    week: activeTab.value === 'weekly' ? selectedWeekId.value : null,
    fresh: freshBucket.value,
    q: searchQuery.value,
    scope: searchScope.value,
    source: sourceFilter.value,
    evidence: evidenceFilter.value,
    unread: onlyUnreadOrNew.value,
    pred: incomingPkChallenge.value?.predId || null,
    p: incomingPkChallenge.value ? String(incomingPkChallenge.value.prob) : null,
    ref: incomingPkChallenge.value?.ref || null,
    ref_sectors: sharedPortfolioPreview.value?.sectors.length ? sharedPortfolioPreview.value.sectors.join(',') : null,
    ref_tickers: sharedPortfolioPreview.value?.tickers.length ? sharedPortfolioPreview.value.tickers.join(',') : null,
  })
  syncUrlToBrowser(url, replace)
}

function recordCurrentBatchSeen(doc: SmartCategoryDoc) {
  if (isHistoryMode.value || doc.missing || !doc.batch_id) return
  const baseline = loadVisitBaseline()
  const merged = new Set(baseline.seen_event_ids)
  for (const ev of doc.events) {
    merged.add(ev.event_id)
  }
  saveVisitBaseline({
    last_batch_id: manifest.value?.smart.latest_batch_id || doc.batch_id,
    last_visited_at: new Date().toISOString(),
    seen_event_ids: Array.from(merged),
  })
}

async function loadEntities(forceFresh = false) {
  if (!forceFresh && entitiesLoaded.value) return
  const res = await fetchEntitiesIndex(manifest.value, forceFresh)
  entities.value = res.entities
  entitiesLoaded.value = true
}

async function loadStorylines(forceFresh = false) {
  if (!forceFresh && storylinesLoaded.value) return
  storylinesLoading.value = true
  try {
    const res = await fetchStorylinesIndex(manifest.value, forceFresh)
    storylinesMap.value = res.storylines
    storylinesLoaded.value = true
  } finally {
    storylinesLoading.value = false
  }
}

async function loadCalendar(forceFresh = false) {
  if (!forceFresh && calendarLoaded.value) return
  calendarLoading.value = true
  try {
    const res = await fetchCalendarEvents(manifest.value, forceFresh)
    serverCalendarEvents.value = res.events
    // Backfill missing snapshots for previously saved overrides so batch rotation never loses them
    let patched = false
    const nextOverrides = { ...catalystOverrides.value }
    for (const ev of res.events) {
      const existing = nextOverrides[ev.calendar_id]
      if (existing && !existing.eventSnapshot) {
        nextOverrides[ev.calendar_id] = { ...existing, eventSnapshot: ev }
        patched = true
      }
    }
    if (patched) {
      catalystOverrides.value = nextOverrides
      saveCatalystOverrideMap(nextOverrides)
    }
    calendarLoaded.value = true
  } finally {
    calendarLoading.value = false
  }
}

async function loadTools(forceFresh = false) {
  if (!forceFresh && toolsLoaded.value) return
  toolsLoading.value = true
  try {
    const res = await fetchTechTools(manifest.value, forceFresh)
    techTools.value = res.tools
    toolsLoaded.value = true
  } finally {
    toolsLoading.value = false
  }
}

const crowdStatsMap = ref<Record<string, CrowdPredictionStat>>({})
const GUEST_STAGED_VOTES_KEY = 'mirrorbrief_guest_staged_votes_v1'
const WELCOME_HERO_DISMISSED_KEY = 'mirrorbrief_welcome_hero_dismissed_v1'
const PENDING_REF_STORAGE_KEY = 'mirrorbrief_pending_ref_v1'

function loadGuestStagedVotes(): Record<string, number> {
  if (typeof window === 'undefined') return {}
  try {
    const raw = window.localStorage.getItem(GUEST_STAGED_VOTES_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw) as Record<string, number>
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

function saveGuestStagedVotes(map: Record<string, number>) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(GUEST_STAGED_VOTES_KEY, JSON.stringify(map))
  } catch {
    // ignore
  }
}

const guestStagedVotes = ref<Record<string, number>>(loadGuestStagedVotes())
const welcomeHeroDismissed = ref<boolean>(
  typeof window !== 'undefined' && window.localStorage.getItem(WELCOME_HERO_DISMISSED_KEY) === '1',
)
const pendingRefCode = ref<string>(
  typeof window !== 'undefined' ? (window.localStorage.getItem(PENDING_REF_STORAGE_KEY) || '') : '',
)
const incomingPkChallenge = ref<{ predId: string; prob: number; ref?: string } | null>(null)
const financeOpenPortfolioNonce = ref(0)
const softAuthPromptOpen = ref(false)
const softAuthScenario = ref<SoftAuthScenario>('portfolio_saved')
const shareCardOpen = ref(false)
const shareCardPayload = ref<ShareCardPayload | null>(null)
let portfolioSoftPromptShown = false

function dismissWelcomeHero() {
  welcomeHeroDismissed.value = true
  if (typeof window !== 'undefined') {
    try {
      window.localStorage.setItem(WELCOME_HERO_DISMISSED_KEY, '1')
    } catch {
      // ignore
    }
  }
}

function triggerSoftAuth(scenario: SoftAuthScenario) {
  if (authSession.value) return
  if (siteSettings.value.soft_auth_prompts_enabled === false) return
  softAuthScenario.value = scenario
  softAuthPromptOpen.value = true
}

function mapDailyRowToPredictionRecord(row: DailyPredictionRow): PredictionRecord {
  return {
    prediction_id: row.id,
    mode: 'live',
    status: row.status === 'settled' ? 'settled' : 'open',
    category: (row.category || 'market') as PredictionRecord['category'],
    title: row.title,
    target_entity_id: null,
    target_entity: row.ticker || null,
    question: row.question,
    created_at: row.created_at,
    due_at: row.due_at,
    lock_at: row.lock_at,
    win_rule: row.win_rule || '',
    lose_rule: row.lose_rule || '',
    supporting_evidence: [],
    opposing_evidence: [],
    core_assumption: '',
    invalidation_trigger: '',
    probability_pct: Number(row.ai_prob_pct ?? 50),
    current_judgment: row.win_rule || row.question,
    versions: [],
    settlement:
      row.status === 'settled'
        ? {
            settled_at: row.settled_at || row.due_at,
            outcome: row.outcome === 'yes' ? 'correct' : row.outcome === 'no' ? 'incorrect' : 'indeterminate',
            evidence_url: '',
            note: row.settled_value !== null && row.settled_value !== undefined
              ? `结算观测值：${row.settled_value}`
              : '系统客观结算',
          }
        : null,
    is_seed: true,
    source_type: row.source_type,
    ticker: row.ticker,
    base_price: row.base_price,
    target_price: row.target_price,
    proposer_username: row.proposer_username,
    arena_status: row.status,
    arena_outcome: row.outcome,
    settled_value: row.settled_value,
  }
}

function clearSharedPortfolioPreview() {
  sharedPortfolioPreview.value = null
  syncUrl(true)
}

function openPredictionPkShareCard(payload: { rec: PredictionRecord; probPct: number }) {
  const pid = payload.rec.prediction_id
  const origin = typeof window !== 'undefined' ? window.location.origin : 'https://mirrorinfo.xyz'
  const u = new URL(`${origin}/s/pred/${encodeURIComponent(pid)}`)
  u.searchParams.set('p', String(Math.round(payload.probPct)))
  if (authSession.value?.user?.username) {
    u.searchParams.set('ref', authSession.value.user.username)
  } else if (pendingRefCode.value) {
    u.searchParams.set('ref', pendingRefCode.value)
  }
  const stat = crowdStatsMap.value[pid]
  const minVotes = Math.max(1, Number(stat?.min_votes ?? siteSettings.value.crowd_vote_min_unlock ?? 3))
  shareCardPayload.value = {
    kind: 'prediction_pk',
    predictionId: pid,
    title: payload.rec.title,
    question: pickBiText(payload.rec.question, (payload.rec as unknown as { question_en?: string }).question_en) || payload.rec.title,
    userProbPct: payload.probPct,
    aiProbPct: Number(payload.rec.probability_pct ?? 50),
    winRule: payload.rec.win_rule || '',
    deadlineLabel: formatShanghaiDateTime(payload.rec.due_at, false),
    voteCount: Number(stat?.vote_count ?? (guestStagedVotes.value[pid] !== undefined ? 1 : 0)),
    minVotes,
    crowdAvgPct: stat?.unlocked && typeof stat.crowd_avg_pct === 'number' ? stat.crowd_avg_pct : null,
    rankTier: arenaProfile.value?.rank_tier || null,
    hitRatePct: arenaProfile.value?.hit_rate_pct ?? null,
    shareUrl: u.toString(),
  }
  shareCardOpen.value = true
}

function openPortfolioShareCard(summary: {
  matchedCount: number
  bullishCount: number
  bearishCount: number
  neutralCount: number
  isRedUp: boolean
  sectors: string[]
  tickers: string[]
  symbolsLabel: string
  takeaways: { title: string; polarity: 'positive' | 'negative' | 'neutral'; summary: string; tags?: string[] }[]
}) {
  const origin = typeof window !== 'undefined' ? window.location.origin : 'https://mirrorinfo.xyz'
  const u = new URL(origin)
  u.searchParams.set('tab', 'finance')
  if (summary.sectors.length > 0) {
    u.searchParams.set('ref_sectors', summary.sectors.slice(0, 10).join(','))
  }
  if (summary.tickers.length > 0) {
    u.searchParams.set('ref_tickers', summary.tickers.slice(0, 10).join(','))
  }
  shareCardPayload.value = {
    kind: 'portfolio_radar',
    ...summary,
    shareUrl: u.toString(),
  }
  shareCardOpen.value = true
}

function openEchoChamberShareCard() {
  const echo = computeEchoChamberReport(nowMs.value)
  const weekly = computeWeeklyReadingReport(nowMs.value)
  const colorHex: Record<CategoryKey, string> = {
    finance: '#F43F5E',
    global: '#F59E0B',
    tech: '#3B82F6',
    general: '#10B981',
  }
  const catLabelMap: Record<CategoryKey, string> = {
    finance: t('财经金融', 'Finance'),
    global: t('国际政治', 'Global'),
    tech: t('科技AI', 'Tech & AI'),
    general: t('综合要闻', 'General'),
  }
  const sortedCats = [...weekly.categoryDistribution].sort((a, b) => a.pct - b.pct)
  const blindCat = sortedCats[0]
  let blindspotTeaserTitle = ''
  if (blindCat) {
    const candidates = allLoadedEvents.value.filter((ev) => ev.category === blindCat.category)
    const topEv =
      candidates.find((ev) => ev.severity_tier === 'S' || ev.importance === 'high') ||
      candidates[0]
    if (topEv) {
      blindspotTeaserTitle = pickBiText(topEv.title_zh || topEv.title, topEv.title_en || topEv.title)
    }
  }
  const score = echo.diversityScore ?? 0
  const personaLabel =
    score >= 75
      ? t('全景穿透型视野', 'Panoramic Lens')
      : score >= 50
        ? t('均衡观察型视野', 'Balanced Observer')
        : t('单频聚焦型视野', 'Single-Band Focus')

  const origin = typeof window !== 'undefined' ? window.location.origin : 'https://mirrorinfo.xyz'
  shareCardPayload.value = {
    kind: 'echo_chamber',
    diversityScore: score,
    statusLabel: t(echo.statusLabel, echo.statusLabelEn),
    personaLabel,
    totalReads: echo.totalCategorizedReads,
    distribution: weekly.categoryDistribution.map((c) => ({
      label: catLabelMap[c.category],
      pct: c.pct,
      color: colorHex[c.category],
    })),
    blindspotLabel: blindCat ? catLabelMap[blindCat.category] : '',
    blindspotPct: blindCat ? blindCat.pct : 0,
    blindspotTeaserTitle,
    recommendation: t(echo.recommendation, echo.recommendationEn),
    shareUrl: origin,
  }
  shareCardOpen.value = true
}

function getCategoryLabel(cat: CategoryKey | string): string {
  const meta = CATEGORIES.find((c) => c.id === cat)
  return appLang.value === 'en' ? (meta?.nameEn || String(cat)) : (meta?.name || String(cat))
}

function openEventBriefShareCard(ev: SmartEvent) {
  const origin = typeof window !== 'undefined' ? window.location.origin : 'https://mirrorinfo.xyz'
  const cols = buildThreeColumnPerspectives(ev, commentsByCatForCards.value[ev.category] || [])
  const sources = Array.isArray(ev.sources) ? ev.sources : []
  const primarySrc = sources[0]
  shareCardPayload.value = {
    kind: 'event_brief',
    eventId: ev.event_id,
    title: pickBiText(ev.title_zh || ev.title, ev.title_en || ev.title),
    categoryLabel: getCategoryLabel(ev.category),
    sourceName: primarySrc?.publisher_name || primarySrc?.source_name || t('多源交叉核验', 'Cross-Checked'),
    sourceCount: sources.length,
    officialPoints: cols.find((c) => c.lane === 'official')?.points.slice(0, 2) || [],
    bullishPoints: cols.find((c) => c.lane === 'bullish')?.points.slice(0, 2) || [],
    bearishPoints: cols.find((c) => c.lane === 'bearish')?.points.slice(0, 2) || [],
    shareUrl: `${origin}/s/event/${encodeURIComponent(ev.event_id)}`,
  }
  shareCardOpen.value = true
}

function mapWeeklySectorToCategory(sectorId: WeeklySectorId | string): CategoryKey {
  if (sectorId === 'macro_finance') return 'finance'
  if (sectorId === 'geopolitics') return 'global'
  if (sectorId === 'tech_ai') return 'tech'
  return 'general'
}

function openWeeklyPoster(stats: { streakWeeks: number; readCount: number }) {
  const doc = weeklyDigestDoc.value
  if (!doc) return
  const origin = typeof window !== 'undefined' ? window.location.origin : 'https://mirrorinfo.xyz'
  const accentMap: Record<WeeklySectorId, string> = {
    macro_finance: '#F59E0B',
    geopolitics: '#3B82F6',
    tech_ai: '#8B5CF6',
    industry_society: '#10B981',
  }
  shareCardPayload.value = {
    kind: 'weekly_digest',
    weekId: doc.week_id,
    dateRangeLabel: doc.date_range_label,
    weekTheme: doc.week_theme,
    totalItems: doc.stats.selected_items,
    p0Count: doc.stats.p0_count,
    streakWeeks: stats.streakWeeks,
    readCount: stats.readCount,
    sectorHighlights: doc.sectors.map((s) => ({
      sectorLabel: `${appLang.value === 'en' ? s.title_en : s.title} (${s.item_count})`,
      accentHex: accentMap[s.sector_id] || '#60A5FA',
      headline: s.items[0]?.title || s.sector_takeaway || s.subtitle,
    })),
    shareUrl: `${origin}/?tab=weekly&week=${encodeURIComponent(doc.week_id)}`,
  }
  shareCardOpen.value = true
}

function handleToggleWeeklyBookmark(item: WeeklyDigestItem) {
  const exists = bookmarks.value.some((b) => b.event_id === item.id)
  if (exists) {
    removeBookmark(item.id)
    return
  }
  const primary = item.sources?.[0]
  bookmarks.value = [
    {
      event_id: item.id,
      title: item.title,
      url: primary?.url || '',
      category: mapWeeklySectorToCategory(item.sector_id),
      source_name: primary?.source_name || t('每周盘点', 'Weekly Digest'),
      batch_id: weeklyDigestDoc.value?.week_id || 'weekly',
      saved_at: new Date().toISOString(),
    },
    ...bookmarks.value,
  ]
  saveBookmarkedEvents(bookmarks.value)
  notifyToast(t('已收入个人阅读库', 'Saved to Personal Library'))
  scheduleAutoCloudSync()
}

function openQaForWeeklyItem(item: WeeklyDigestItem) {
  void Promise.all([ensureAllCategoriesLoaded(), loadFinanceImpact(), loadCalendar()])
  qaContextEvent.value = null
  qaContextStoryline.value = null
  qaContextEntity.value = null
  qaContextTopic.value = null
  qaContextPrompt.value = t(
    `请帮我深度复盘本周大事「${item.title}」：事实摘要为「${item.fact_summary}」。请结合站内近期新闻与市场影响，拆解它为何关键以及下周需重点盯防的风险与催化指标。`,
    `Review the weekly major event "${item.title}" (${item.fact_summary}). Explain why it matters and key catalysts/risks to monitor next week.`,
  )
  qaModalOpen.value = true
}

function markWeeklyDigestVisited(weekId: string) {
  if (!weekId) return
  lastSeenWeekId.value = weekId
  try {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(WEEKLY_LAST_SEEN_KEY, weekId)
    }
  } catch {
    // ignore storage errors
  }
}

async function loadCrowdStats() {
  try {
    const res = await apiFetchPredictionCrowd(authSession.value?.token)
    crowdStatsMap.value = res.items || {}
  } catch {
    // Public view still works with local baseline if crowd endpoint is temporarily unreachable
  }
}

async function handleVotePredictionCrowd(payload: { predictionId: string; probPct: number; reasonTag?: string }) {
  if (!authSession.value?.token) {
    // Guest UX unified (P0-4): stage vote locally first, then prompt soft registration without hard-blocking slider
    const nextStaged = { ...guestStagedVotes.value, [payload.predictionId]: payload.probPct }
    guestStagedVotes.value = nextStaged
    saveGuestStagedVotes(nextStaged)
    notifyToast(
      t(
        `已暂存你的 ${payload.probPct}% 预判，登录后正式锁定战绩`,
        `Staged ${payload.probPct}% forecast locally — sign in to lock record`,
      ),
    )
    triggerSoftAuth('prediction_vote')
    return
  }
  try {
    const challengerRef =
      incomingPkChallenge.value?.predId === payload.predictionId ? incomingPkChallenge.value.ref : undefined
    const res = await apiSubmitPredictionVote(authSession.value.token, payload.predictionId, payload.probPct, {
      reason_tag: payload.reasonTag,
      challenger_ref: challengerRef,
    })
    if (res.items) {
      crowdStatsMap.value = res.items
    }
    const stat = res.item || crowdStatsMap.value[payload.predictionId]
    const cnt = stat?.vote_count || 1
    const minNeed = Math.max(1, Number(stat?.min_votes ?? res.min_votes ?? siteSettings.value.crowd_vote_min_unlock ?? 3))
    const mult = Number(res.early_multiplier ?? stat?.user_early_multiplier ?? 1)
    const multTag = mult > 1 ? ` · 早鸟 ${mult.toFixed(1)}x` : ''
    const msg = stat?.unlocked
      ? t(
          `已记录 ${payload.probPct}%${multTag}（共 ${cnt} 人参与，群众均值 ${stat.crowd_avg_pct}%）`,
          `Vote ${payload.probPct}% saved (${cnt} voters · avg ${stat.crowd_avg_pct}%)`,
        )
      : t(
          `已记录 ${payload.probPct}%${multTag}（已收 ${cnt}/${minNeed} 份，邀好友立即解锁均值）`,
          `Vote ${payload.probPct}% saved (${cnt}/${minNeed} to unlock crowd avg)`,
        )
    const rec = mergedPredictions.value.find((p) => p.prediction_id === payload.predictionId)
    notifyToast(
      msg,
      rec
        ? {
            actionLabel: t('生成 PK 卡', 'Share PK Card'),
            onAction: () => openPredictionPkShareCard({ rec, probPct: payload.probPct }),
          }
        : undefined,
    )
  } catch (err) {
    notifyToast(err instanceof Error ? err.message : t('投票提交失败，请稍后重试', 'Vote submission failed'))
  }
}

async function handleSubmitPredictionProposal(body: {
  category: string
  title: string
  question: string
  win_rule: string
  lose_rule: string
  due_at: string
}) {
  if (!authSession.value?.token) {
    triggerSoftAuth('prediction_vote')
    return
  }
  try {
    await apiSubmitPredictionProposal(authSession.value.token, body)
    notifyToast(
      t(
        '预测提案已提交审核，通过后将上架全站日赛并奖励 +100 洞察分与 +1 邀请名额',
        'Proposal submitted — rewards +100 pts and +1 invite upon approval',
      ),
    )
  } catch (err) {
    notifyToast(err instanceof Error ? err.message : t('提案提交失败，请稍后重试', 'Proposal submission failed'))
  }
}

async function loadPredictions(forceFresh = false) {
  if (!forceFresh && predictionsLoaded.value) return
  predictionsLoading.value = true
  try {
    const [res, arenaRes] = await Promise.all([
      fetchPredictionsPublic(manifest.value, forceFresh),
      apiFetchPredictionArena(authSession.value?.token).catch(() => null),
    ])
    seedPredictions.value = res.predictions
    predictionsNote.value = res.note
    if (arenaRes) {
      dailyArenaPredictions.value = (arenaRes.daily_predictions || []).map(mapDailyRowToPredictionRecord)
      crowdStatsMap.value = arenaRes.crowd_stats || {}
      arenaProfile.value = arenaRes.my_profile || null
      arenaLeaderboard.value = arenaRes.leaderboard || []
      if (arenaRes.allowed_reason_tags?.length) {
        arenaReasonTags.value = arenaRes.allowed_reason_tags
      }
      arenaSeasonKey.value = arenaRes.season_key || ''
      if (arenaRes.my_profile) {
        const expMs = Date.parse(arenaRes.my_profile.bonus_qa_expires_at || '')
        predictionBonusQaQuota.value =
          arenaRes.my_profile.bonus_qa_quota > 0 && (Number.isNaN(expMs) || expMs > Date.now())
            ? Number(arenaRes.my_profile.bonus_qa_quota)
            : 0
      }
    } else {
      await loadCrowdStats()
    }
    predictionsLoaded.value = true
  } finally {
    predictionsLoading.value = false
  }
}

async function ensureCategoryLoaded(cat: CategoryKey, forceFresh = false) {
  if (!forceFresh && docsByCat.value[cat]) return
  const doc = await fetchSmartCategory(cat, {
    archivePath: historyPath.value,
    manifest: manifest.value,
    forceFresh,
  })
  docsByCat.value = {
    ...docsByCat.value,
    [cat]: doc,
  }
  const mig = migrateCollidingEventStates(doc.events, readIds.value, bookmarks.value)
  if (mig.migrated) {
    readIds.value = mig.readIds
    bookmarks.value = mig.bookmarks
  }
  recordCurrentBatchSeen(doc)
}

async function ensureAllCategoriesLoaded(forceFresh = false) {
  loadingAllCats.value = true
  try {
    const fetched = await Promise.all(
      ALL_CATS.map(async (cat) => {
        if (!forceFresh && docsByCat.value[cat]) {
          return [cat, docsByCat.value[cat]!] as const
        }
        const doc = await fetchSmartCategory(cat, {
          archivePath: historyPath.value,
          manifest: manifest.value,
          forceFresh,
        })
        return [cat, doc] as const
      }),
    )
    // Atomic single commit prevents Today tab badge flickering sequentially through intermediate sums
    const nextMap = { ...docsByCat.value }
    for (const [cat, doc] of fetched) {
      nextMap[cat] = doc
      const mig = migrateCollidingEventStates(doc.events, readIds.value, bookmarks.value)
      if (mig.migrated) {
        readIds.value = mig.readIds
        bookmarks.value = mig.bookmarks
      }
      recordCurrentBatchSeen(doc)
    }
    docsByCat.value = nextMap
  } finally {
    loadingAllCats.value = false
  }
}

async function loadTopics(forceFresh = false) {
  if (!forceFresh && topicsLoaded.value) return
  topicsLoading.value = true
  try {
    const res = await fetchMajorTopics(manifest.value, forceFresh)
    majorTopics.value = res.topics
    archivedTopics.value = res.archived_topics || []
    topicsLoaded.value = true
  } finally {
    topicsLoading.value = false
  }
}

async function loadAiProgress(forceFresh = false) {
  if (!forceFresh && aiProgressLoaded.value) return
  aiProgressDoc.value = await fetchAiProgress(manifest.value, forceFresh)
  wireStreamHandle?.seedAiFromDoc(aiProgressDoc.value)
  aiProgressLoaded.value = true
}

async function loadFinanceImpact(forceFresh = false) {
  if (!forceFresh && financeImpactLoaded.value) return
  financeImpactDoc.value = await fetchFinanceImpact(manifest.value, forceFresh)
  if (financeImpactDoc.value) {
    seedGlobalQuotesFromFinanceDoc(financeImpactDoc.value)
  }
  financeImpactLoaded.value = true
}

async function loadLiveWire(forceFresh = false) {
  if (!forceFresh && liveWireLoaded.value) return
  liveWireDoc.value = await fetchLiveWire(manifest.value, forceFresh)
  wireStreamHandle?.seedFromDoc(liveWireDoc.value)
  liveWireLoaded.value = true
}

async function loadWeeklyDigest(weekId?: string | null, forceFresh = false) {
  const targetWeek = weekId ?? selectedWeekId.value ?? null
  weeklyLoading.value = true
  try {
    const [docRes, idxRes] = await Promise.all([
      fetchWeeklyDigest(targetWeek, forceFresh),
      fetchWeeklyDigestsIndex(forceFresh),
    ])
    if (docRes) {
      weeklyDigestDoc.value = docRes
      if (!selectedWeekId.value && docRes.week_id) {
        selectedWeekId.value = docRes.week_id
      }
    }
    if (idxRes) {
      weeklyDigestsIndexDoc.value = idxRes
    }
    weeklyLoaded.value = true
  } finally {
    weeklyLoading.value = false
  }
}

async function handleSelectWeeklyIssue(weekId: string) {
  selectedWeekId.value = weekId || null
  syncUrl(false)
  await loadWeeklyDigest(selectedWeekId.value, false)
}

async function ensureDataForTab(tab: WorkbenchTab, forceFresh = false) {
  if (tab === 'today' || tab === 'briefing') {
    await Promise.all([
      ensureAllCategoriesLoaded(forceFresh),
      loadEntities(forceFresh),
      loadCalendar(forceFresh),
      loadTopics(forceFresh),
      loadFinanceImpact(forceFresh),
      loadLiveWire(forceFresh),
    ])
  } else if (tab === 'wire') {
    await loadLiveWire(forceFresh)
  } else if (tab === 'weekly') {
    await loadWeeklyDigest(selectedWeekId.value, forceFresh)
  } else if (tab === 'ai_progress' || tab === 'tools') {
    await Promise.all([loadAiProgress(forceFresh), loadTools(forceFresh), ensureAllCategoriesLoaded(forceFresh)])
  } else if (tab === 'finance') {
    await Promise.all([loadFinanceImpact(forceFresh), ensureAllCategoriesLoaded(forceFresh)])
  } else if (tab === 'tracking') {
    await Promise.all([loadStorylines(forceFresh), loadEntities(forceFresh)])
  } else if (tab === 'calendar' || tab === 'predictions') {
    await Promise.all([
      loadPredictions(forceFresh),
      loadCalendar(forceFresh),
      ensureAllCategoriesLoaded(forceFresh),
      loadFinanceImpact(forceFresh),
      loadLiveWire(forceFresh),
    ])
  } else {
    await Promise.all([
      ensureAllCategoriesLoaded(forceFresh),
      loadCalendar(forceFresh),
      loadEntities(forceFresh),
      loadFinanceImpact(forceFresh),
    ])
  }
}

async function loadInitial(forceFresh = false) {
  loadingCat.value = true
  try {
    if (!historyPath.value) {
      manifest.value = await fetchManifest(forceFresh)
      pendingNewManifest.value = null
    }
    docsByCat.value = {}
    await ensureCategoryLoaded(activeCategory.value, forceFresh)
    if (searchScope.value === 'all' || searchQuery.value.trim() || highlightedEventId.value) {
      await ensureAllCategoriesLoaded(forceFresh)
    }
    if (forceFresh || highlightedEventId.value || incomingPkChallenge.value || sharedPortfolioPreview.value) {
      await Promise.all([ensureDataForTab(activeTab.value, forceFresh), refreshSiteSettingsAndOverrides()])
    } else {
      void ensureDataForTab(activeTab.value, forceFresh)
    }
    if (!historyPath.value && !weeklyLoaded.value) {
      void loadWeeklyDigest(selectedWeekId.value, false)
    }
    if (drawerEntityKey.value) {
      void loadEntities(forceFresh)
    }
    if (highlightedEventId.value) {
      void focusHighlightedEventLanding()
    } else {
      scrollToHighlightedEvent()
    }
  } finally {
    loadingCat.value = false
  }
}

async function switchCategory(cat: CategoryKey) {
  if (activeCategory.value === cat) return
  activeCategory.value = cat
  sourceFilter.value = 'all'
  selectedEntity.value = ''
  highlightedEventId.value = null
  perspectivesOpen.value = false
  syncUrl(false)

  if (!docsByCat.value[cat]) {
    loadingCat.value = true
    try {
      await ensureCategoryLoaded(cat)
    } finally {
      loadingCat.value = false
    }
  }
  if (!isHistoryMode.value && (pillarDateRange.value === '3d' || pillarDateRange.value === '7d')) {
    void loadPillarMultiDayRange(pillarDateRange.value === '3d' ? 3 : 7)
  }
}

async function loadPerspectivesIfNeeded() {
  const key = currentCommentsKey.value
  if (commentsByKey.value[key] || !activeDoc.value) return
  perspectivesLoading.value = true
  try {
    const doc = await fetchSimulatedComments(activeCategory.value, {
      archivePath: historyPath.value,
      manifest: manifest.value,
      expectedBatchId: activeDoc.value.batch_id,
      expectedGeneratedAt: activeDoc.value.generated_at,
    })
    commentsByKey.value = {
      ...commentsByKey.value,
      [key]: doc,
    }
  } finally {
    perspectivesLoading.value = false
  }
}

function togglePerspectives() {
  perspectivesOpen.value = !perspectivesOpen.value
  if (perspectivesOpen.value) {
    void loadPerspectivesIfNeeded()
  }
}

function scrollToHighlightedEvent() {
  if (!highlightedEventId.value || typeof document === 'undefined') return
  setTimeout(() => {
    const el = document.getElementById(`event-${highlightedEventId.value}`)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }, 120)
}

async function focusHighlightedEventLanding() {
  const targetId = highlightedEventId.value
  if (!targetId) return
  const matched = allLoadedEvents.value.find((e) => e.event_id === targetId)
  if (!matched) {
    notifyToast(t('该事件已归档沉淀，可前往「每周盘点」查看本周大事精选或用搜索框检索', 'Event may have moved to Weekly Digest or archive'))
    return
  }
  await nextTick()
  setTimeout(() => {
    const el = typeof document !== 'undefined' ? document.getElementById(`event-${targetId}`) : null
    if (el && el.offsetParent !== null) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    } else {
      focusedEventModalEvent.value = matched
    }
  }, 180)
}

function jumpToEvent(eventId: string | undefined) {
  if (!eventId) return
  highlightedEventId.value = eventId
  syncUrl(false)
  scrollToHighlightedEvent()
}

function handleMarkSingleRead(target: SmartEvent | string) {
  if (!target) return
  const resolvedEv =
    typeof target === 'string'
      ? allLoadedEvents.value.find((e) => e.event_id === target)
      : target
  const id = typeof target === 'string' ? target : target.event_id
  if (!id) return
  const already =
    readIds.value.has(id) ||
    Boolean(resolvedEv && legacyReadTitles.value.has(resolvedEv.title.trim()))
  if (already) return

  const nextIds = new Set(readIds.value)
  const nextTitles = new Set(legacyReadTitles.value)
  nextIds.add(id)
  if (resolvedEv?.title?.trim()) nextTitles.add(resolvedEv.title.trim())
  readIds.value = nextIds
  legacyReadTitles.value = nextTitles
  saveReadState(nextIds, nextTitles)
  dailyReading.value = recordTodayReadEvents(dailyReading.value, [id], true, nowMs.value)
  if (resolvedEv) recordEventReadInHistory(resolvedEv, nowMs.value)
}

function handleToggleRead(ev: SmartEvent) {
  const nextIds = new Set(readIds.value)
  const nextTitles = new Set(legacyReadTitles.value)
  const wasRead = isEventRead(ev, nextIds, nextTitles)
  if (wasRead) {
    nextIds.delete(ev.event_id)
    nextTitles.delete(ev.title.trim())
  } else {
    nextIds.add(ev.event_id)
    nextTitles.add(ev.title.trim())
  }
  readIds.value = nextIds
  legacyReadTitles.value = nextTitles
  saveReadState(nextIds, nextTitles)
  dailyReading.value = recordTodayReadEvents(dailyReading.value, [ev.event_id], !wasRead, nowMs.value)
  if (!wasRead) {
    recordEventReadInHistory(ev, nowMs.value)
  }
}

function markVisibleAsRead() {
  handleMarkEventsRead(filteredEvents.value)
}

function handleMarkEventsRead(events: SmartEvent[]) {
  if (!events.length) return
  const nextIds = new Set(readIds.value)
  const nextTitles = new Set(legacyReadTitles.value)
  const ids: string[] = []
  for (const ev of events) {
    nextIds.add(ev.event_id)
    nextTitles.add(ev.title.trim())
    ids.push(ev.event_id)
  }
  readIds.value = nextIds
  legacyReadTitles.value = nextTitles
  saveReadState(nextIds, nextTitles)
  dailyReading.value = recordTodayReadEvents(dailyReading.value, ids, true, nowMs.value)
  notifyToast(t(`已将 ${ids.length} 条标为已读`, `Marked ${ids.length} items as read`))
}

// --- Mobile UX: Full-screen Search Overlay, Batch Info Sheet, Pull-to-Refresh, Floating Nav, Channel Swipe ---
const searchOverlayOpen = ref(false)
const searchInputEl = ref<HTMLInputElement | null>(null)
const batchInfoModalOpen = ref(false)
const showFloatingNav = ref(false)
const pullDistance = ref(0)
let pullStartY = 0
let pullTracking = false
let pullHapticTriggered = false

watch(searchOverlayOpen, (open) => {
  if (open) {
    lockBodyScroll()
    void nextTick(() => searchInputEl.value?.focus())
  } else {
    unlockBodyScroll()
  }
})

watch(batchInfoModalOpen, (open) => {
  if (open) lockBodyScroll()
  else unlockBodyScroll()
})

const searchCurrentTabOnly = ref(false)

function openSearchOverlay() {
  awaitingGChord = false
  if (gChordTimer) {
    clearTimeout(gChordTimer)
    gChordTimer = null
  }
  searchOverlayOpen.value = true
  void Promise.all([
    ensureAllCategoriesLoaded(),
    loadEntities(),
    loadFinanceImpact(),
    loadLiveWire(),
    loadAiProgress(),
    loadTools(),
    loadStorylines(),
    loadTopics(),
    loadCalendar(),
    loadPredictions(),
  ])
}

function closeSearchOverlay(clearTemp = false) {
  awaitingGChord = false
  if (gChordTimer) {
    clearTimeout(gChordTimer)
    gChordTimer = null
  }
  searchOverlayOpen.value = false
  if (clearTemp && searchQuery.value.trim()) {
    searchQuery.value = ''
    syncUrl(true)
  }
}

function scrollToTop() {
  if (typeof window !== 'undefined') {
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }
}

function handleBottomTabClick(tab: WorkbenchTab) {
  triggerHaptic(10)
  menuCloseNonce.value += 1
  if (tab === 'predictions') {
    if (activeTab.value === 'calendar' && scheduleSubView.value === 'predictions') {
      scrollToTop()
      return
    }
    void switchTab('predictions')
    return
  }
  if (activeTab.value === tab) {
    scrollToTop()
    return
  }
  void switchTab(tab)
}

function jumpToNextUnread() {
  if (typeof document === 'undefined' || typeof window === 'undefined') return
  const unreadEls = Array.from(document.querySelectorAll<HTMLElement>('[data-read="false"]'))
  if (!unreadEls.length) {
    notifyToast(t('当前页面暂无未读内容', 'No unread items on this view'))
    return
  }
  const threshold = window.scrollY + 120
  const nextEl =
    unreadEls.find((el) => el.getBoundingClientRect().top + window.scrollY > threshold) || unreadEls[0]
  nextEl.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

function onGlobalScrollTrack() {
  if (typeof window === 'undefined') return
  showFloatingNav.value = (window.scrollY || 0) > 420
}

function onPullTouchStart(e: TouchEvent) {
  if (typeof window === 'undefined' || (window.scrollY || 0) > 4 || e.touches.length !== 1) return
  pullStartY = e.touches[0].clientY
  pullTracking = true
  pullHapticTriggered = false
  pullDistance.value = 0
}

function onPullTouchMove(e: TouchEvent) {
  if (!pullTracking || e.touches.length !== 1) return
  if ((window.scrollY || 0) > 4) {
    pullTracking = false
    pullHapticTriggered = false
    pullDistance.value = 0
    return
  }
  const dy = e.touches[0].clientY - pullStartY
  if (dy > 8) {
    pullDistance.value = Math.min(84, dy * 0.5)
    if (pullDistance.value >= 54 && !pullHapticTriggered) {
      pullHapticTriggered = true
      if (typeof navigator !== 'undefined' && typeof navigator.vibrate === 'function') {
        navigator.vibrate(10)
      }
    }
  } else {
    pullDistance.value = 0
  }
}

function onPullTouchEnd() {
  if (!pullTracking) return
  const pulled = pullDistance.value
  pullTracking = false
  pullHapticTriggered = false
  pullDistance.value = 0
  if (pulled >= 54 && !isRefreshing.value) {
    void handleManualRefresh()
  }
}

// Horizontal swipe between 4 categories on Briefings tab
let briefSwipeX0 = 0
let briefSwipeY0 = 0
function onBriefingTouchStart(e: TouchEvent) {
  if (e.touches.length !== 1) return
  briefSwipeX0 = e.touches[0].clientX
  briefSwipeY0 = e.touches[0].clientY
}
function onBriefingTouchEnd(e: TouchEvent) {
  if (!e.changedTouches.length) return
  const dx = e.changedTouches[0].clientX - briefSwipeX0
  const dy = e.changedTouches[0].clientY - briefSwipeY0
  if (Math.abs(dx) < 72 || Math.abs(dx) < Math.abs(dy) * 1.65) return
  const catIds = CATEGORIES.map((c) => c.id)
  const idx = catIds.indexOf(activeCategory.value)
  if (dx < 0 && idx < catIds.length - 1) {
    void switchCategory(catIds[idx + 1])
  } else if (dx > 0 && idx > 0) {
    void switchCategory(catIds[idx - 1])
  }
}

const searchOverlayMatches = computed(() => {
  const q = searchQuery.value.trim()
  if (!q) {
    return {
      entities: [] as EntityProfile[],
      financeImpacts: [] as NonNullable<typeof financeImpactDoc.value>['event_impacts'],
      events: [] as SmartEvent[],
      wire: [] as NonNullable<typeof liveWireDoc.value>['items'],
      ai: [] as NonNullable<typeof aiProgressDoc.value>['timeline'],
      tools: [] as TechToolEntry[],
      topics: [] as MajorTopicSpotlight[],
      storylines: [] as StorylineDossier[],
      calendar: [] as CatalystEvent[],
      predictions: [] as PredictionRecord[],
    }
  }
  const onlyCurrent = searchCurrentTabOnly.value
  const allow = (tab: WorkbenchTab | 'tools' | 'predictions' | 'entities') => {
    if (!onlyCurrent) return true
    if (tab === 'entities') return true
    if (tab === 'tools') return activeTab.value === 'ai_progress'
    if (tab === 'predictions') return activeTab.value === 'calendar'
    return activeTab.value === tab
  }

  const matchedEntities = allow('entities')
    ? entities.value
        .filter((ent) => {
          const tickerText = (ent.tickers || [])
            .map((tk) => (typeof tk === 'string' ? tk : `${tk.symbol || ''} ${tk.label || ''}`))
            .join(' ')
          return matchesSmartQuery(
            `${ent.canonical_name} ${(ent.aliases || []).join(' ')} ${tickerText} ${ent.sector || ''}`,
            q,
          )
        })
        .slice(0, 6)
    : []

  const matchedFinance = allow('finance')
    ? (financeImpactDoc.value?.event_impacts || [])
        .filter((imp) => {
          const barsHay = (imp.bars || []).map((b) => `${b.market} ${b.sector} ${b.proxy_ticker || ''}`).join(' ')
          const layerHay = (imp.transmission_layers || [])
            .map((l) => `${l.tier_label} ${(l.stocks || []).map((s) => `${s.name} ${s.code}`).join(' ')}`)
            .join(' ')
          const tickersHay = Object.keys(imp.affected_tickers || {}).join(' ')
          return matchesSmartQuery(`${imp.event_title} ${imp.tag} ${imp.one_liner} ${barsHay} ${layerHay} ${tickersHay}`, q)
        })
        .slice(0, 5)
    : []

  const evs = allow('today')
    ? canonicalTodayEvents.value
        .filter((ev) => matchesSmartQuery(`${ev.title_zh || ''} ${ev.title} ${ev.fact_summary || ''} ${(ev.entities || []).join(' ')}`, q))
        .slice(0, 6)
    : []

  const wires = allow('wire')
    ? (effectiveLiveWireDoc.value?.items || [])
        .filter((it) => !mutedSet.value.has(it.id) && matchesSmartQuery(`${it.title} ${it.title_en || ''} ${it.excerpt || ''} ${it.source_name || ''}`, q))
        .slice(0, 5)
    : []

  const aiItems = allow('ai_progress')
    ? (aiProgressDoc.value?.timeline || [])
        .filter((it) => matchesSmartQuery(`${it.title} ${it.what_it_does || ''} ${it.summary || ''} ${it.company_name || ''} ${it.source_name || ''}`, q))
        .slice(0, 5)
    : []

  const matchedTools = allow('tools')
    ? techTools.value
        .filter((tool) => matchesSmartQuery(`${tool.name} ${tool.repo || ''} ${tool.summary || ''} ${tool.sector || ''}`, q))
        .slice(0, 4)
    : []

  const topicItems = allow('today')
    ? [...majorTopics.value, ...archivedTopics.value]
        .filter((tp) => matchesSmartQuery(`${tp.title} ${tp.title_en || ''} ${tp.subtitle || ''} ${tp.region_label || ''} ${(tp.primary_orgs || []).join(' ')} ${(tp.timeline || []).map((n) => n.title).join(' ')}`, q))
        .slice(0, 4)
    : []

  const stItems = allow('tracking') || allow('today')
    ? Object.values(storylinesMap.value)
        .filter((st) => !mutedSet.value.has(st.storyline_id) && matchesSmartQuery(`${st.title_zh || ''} ${st.title} ${st.current_stage || ''} ${(st.entities || []).join(' ')}`, q))
        .slice(0, 5)
    : []

  const calItems = allow('calendar')
    ? mergedServerCalendarEvents.value
        .filter((cal) => matchesSmartQuery(`${cal.title} ${cal.title_en || ''} ${cal.location_display || ''} ${cal.event_type_label || ''} ${cal.watch_variable || ''}`, q))
        .slice(0, 4)
    : []

  const predItems = allow('predictions')
    ? mergedPredictions.value
        .filter((pr) => matchesSmartQuery(`${pr.title} ${pr.question} ${pr.target_entity || ''} ${pr.current_judgment}`, q))
        .slice(0, 4)
    : []

  return {
    entities: matchedEntities,
    financeImpacts: matchedFinance,
    events: evs,
    wire: wires,
    ai: aiItems,
    tools: matchedTools,
    topics: topicItems,
    storylines: stItems,
    calendar: calItems,
    predictions: predItems,
  }
})

const batchStatusTone = computed<'ok' | 'warn' | 'err'>(() => {
  const cls = smartHealth.value.pillClass || ''
  if (cls.includes('red') || cls.includes('rose')) return 'err'
  if (cls.includes('amber')) return 'warn'
  return 'ok'
})

// --- Desktop 3-Column Workbench State, Scroll Memory & Keyboard Shortcuts ---
const sidebarCollapsed = ref(false)
const rightDrawerOpen = ref(false)
const shortcutsModalOpen = ref(false)
const selectedDetailEvent = ref<SmartEvent | null>(null)
const tabScrollMemory = new Map<string, number>()
let keyboardFocusIdx = -1
let gChordTimer: ReturnType<typeof setTimeout> | null = null
let awaitingGChord = false

watch(rightDrawerOpen, (open) => {
  if (open) lockBodyScroll()
  else unlockBodyScroll()
})

watch(shortcutsModalOpen, (open) => {
  if (open) lockBodyScroll()
  else unlockBodyScroll()
})

let detailDwellTimer: ReturnType<typeof setTimeout> | null = null

function openEventInDetailReader(ev: SmartEvent) {
  selectedDetailEvent.value = ev
  highlightedEventId.value = ev.event_id
  syncUrl(false)
  if (typeof window !== 'undefined' && window.innerWidth >= 1024 && window.innerWidth < 1280) {
    rightDrawerOpen.value = true
  }
  if (detailDwellTimer) clearTimeout(detailDwellTimer)
  detailDwellTimer = setTimeout(() => {
    if (selectedDetailEvent.value?.event_id === ev.event_id) {
      handleMarkSingleRead(ev)
    }
  }, 1500)
}

function closeDetailReader() {
  if (detailDwellTimer) {
    clearTimeout(detailDwellTimer)
    detailDwellTimer = null
  }
  selectedDetailEvent.value = null
  highlightedEventId.value = null
  syncUrl(false)
}

const upcomingCatalystsForRail = computed(() => {
  const list = mergedServerCalendarEvents.value || []
  const todayStr = formatShanghaiDateOnly(new Date(nowMs.value).toISOString())
  return list
    .filter((ev) => ev.scheduled_at && !ev.is_past && formatShanghaiDateOnly(ev.scheduled_at) >= todayStr)
    .sort((a, b) => (a.scheduled_at || '').localeCompare(b.scheduled_at || ''))
    .slice(0, 3)
})

const readLaterResolved = computed(() =>
  resolveReadLaterEventsList(readLaterSet.value, allLoadedEvents.value, readLaterMetaMap.value),
)
const readLaterEvents = computed(() => readLaterResolved.value.validEvents)
const readLaterCount = computed(() => readLaterEvents.value.length)
const libraryCount = computed(() => bookmarks.value.length + readLaterCount.value + researchNotes.value.length)

function handleReadLaterItemClick(ev: SmartEvent) {
  bookmarksModalOpen.value = false
  if (ev.input_batch_id === 'saved-snapshot') {
    const srcUrl = normalizeExternalUrl(ev.sources?.[0]?.url)
    if (srcUrl && typeof window !== 'undefined') {
      window.open(srcUrl, '_blank', 'noopener,noreferrer')
    } else {
      notifyToast(t('该跨批次深读条目已移出当前最新简报，且暂无可用原文直链', 'Snapshot story is outside latest batch and has no direct link'))
    }
    return
  }
  void handleJumpToTodayEvent(ev)
}

watch([allCatsReady, allLoadedEvents, isHistoryMode], ([ready, evs, hist]) => {
  if (hist || !ready || evs.length === 0) return
  const orphans = readLaterResolved.value.orphanIds
  if (!orphans.length) return
  const next = new Set(readLaterSet.value)
  for (const id of orphans) next.delete(id)
  readLaterSet.value = next
  saveStringSetKey('read_later', next)
})

function openLibraryModal(subTab: 'saved' | 'read_later' | 'notes' = 'saved') {
  libraryTab.value = subTab
  bookmarksModalOpen.value = true
}

const desktopNavItems = computed(() => [
  { id: 'today' as WorkbenchTab, label: t('今日要闻', 'Today'), shortLabel: t('要闻', 'Today'), icon: Compass, count: !loadingAllCats.value && allCatsReady.value ? canonicalTodayEvents.value.length : 0 },
  { id: 'wire' as WorkbenchTab, label: t('7×24 快讯', 'Live Wire'), shortLabel: t('快讯', 'Live'), icon: Radio, count: effectiveLiveWireDoc.value?.total || 0 },
  { id: 'finance' as WorkbenchTab, label: t('股市传导', 'Markets'), shortLabel: t('股市', 'Markets'), icon: TrendingUp, count: financeImpactDoc.value?.event_impacts?.length || 0 },
  { id: 'ai_progress' as WorkbenchTab, label: t('AI 前沿', 'AI Frontier'), shortLabel: t('AI前沿', 'AI'), icon: Bot, count: aiProgressDoc.value?.timeline.length || manifest.value?.v3?.ai_progress_count || 0 },
  { id: 'predictions' as WorkbenchTab, label: t('预测日程', 'Forecasts'), shortLabel: t('预测', 'Pred'), icon: Target, count: mergedPredictions.value.length || calendarTabTotalCount.value || 0 },
  { id: 'tracking' as WorkbenchTab, label: t('事件追踪', 'Tracking'), shortLabel: t('追踪', 'Track'), icon: GitBranch, count: Object.keys(storylinesMap.value).length || manifest.value?.v3?.storylines_count || 0 },
])

watch(
  () => allLoadedEvents.value.slice(0, 80).map((e) => e.event_id).join(','),
  (csv) => {
    if (!csv) return
    void loadReactionsBatch('event', csv.split(','), { token: authSession.value?.token ?? null })
  },
)

interface CommandItem {
  id: string
  label: string
  keywords: string
  run: () => void
}

const commandPaletteItems = computed<CommandItem[]>(() => {
  const base: CommandItem[] = [
    ...desktopNavItems.value.map((m) => ({
      id: `tab-${m.id}`,
      label: m.label,
      keywords: `${m.label} ${m.shortLabel} ${m.id}`.toLowerCase(),
      run: () => {
        searchOverlayOpen.value = false
        void switchTab(m.id)
      },
    })),
    {
      id: 'tool-qa',
      label: t('AI 证据问答 / 笔记', 'AI Evidence Q&A / Notes'),
      keywords: 'ai 问答 笔记 qa notes evidence',
      run: () => {
        searchOverlayOpen.value = false
        openQaGlobal()
      },
    },
    {
      id: 'tool-bookmarks',
      label: t(`阅读库 (${libraryCount.value})`, `Library (${libraryCount.value})`),
      keywords: '阅读库 收藏 笔记 深读 bookmarks library saved notes',
      run: () => {
        searchOverlayOpen.value = false
        openLibraryModal('saved')
      },
    },
    {
      id: 'tool-weekly',
      label: t('每周盘点 · 一周大事', 'Weekly Digest'),
      keywords: '每周 盘点 一周大事 周刊 weekly digest',
      run: () => {
        searchOverlayOpen.value = false
        void switchTab('weekly')
      },
    },
    {
      id: 'tool-diversity',
      label: t('视野分布与信息茧房体检', 'Diversity Check'),
      keywords: '信息茧房 视野 周报 diversity report',
      run: () => {
        searchOverlayOpen.value = false
        weeklyReportOpen.value = true
      },
    },
    {
      id: 'tool-theme',
      label: isDark.value ? t('切换为浅色主题', 'Switch to Light Mode') : t('切换为深色主题', 'Switch to Dark Mode'),
      keywords: '主题 深色 浅色 dark light theme',
      run: () => {
        searchOverlayOpen.value = false
        toggleDark()
      },
    },
  ]
  const q = searchQuery.value.trim()
  if (!q) return base
  return base.filter((x) => matchesSmartQuery(`${x.keywords} ${x.label}`, q))
})

function isEditableElement(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false
  const tag = el.tagName.toLowerCase()
  return tag === 'input' || tag === 'textarea' || tag === 'select' || el.isContentEditable
}

function moveKeyboardFeedFocus(delta: number) {
  if (typeof document === 'undefined') return
  const cards = Array.from(document.querySelectorAll<HTMLElement>('article[id^="event-"]'))
  if (!cards.length) return
  keyboardFocusIdx = Math.max(0, Math.min(cards.length - 1, keyboardFocusIdx + delta))
  const target = cards[keyboardFocusIdx]
  if (!target) return
  const evId = target.id.replace(/^event-/, '')
  highlightedEventId.value = evId
  target.scrollIntoView({ behavior: 'smooth', block: 'center' })
  const matchedEv = allLoadedEvents.value.find((x) => x.event_id === evId)
  if (matchedEv && typeof window !== 'undefined' && window.innerWidth >= 1280) {
    selectedDetailEvent.value = matchedEv
  }
}

function handleDesktopKeyboardShortcuts(e: KeyboardEvent) {
  // ⌘K / Ctrl+K opens search command palette anywhere
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    openSearchOverlay()
    return
  }

  if (e.key === 'Escape') {
    if (shortcutsModalOpen.value) {
      shortcutsModalOpen.value = false
      return
    }
    if (searchOverlayOpen.value) {
      e.preventDefault()
      e.stopPropagation()
      closeSearchOverlay(true)
      return
    }
    if (batchInfoModalOpen.value) {
      batchInfoModalOpen.value = false
      return
    }
    if (drawerEntityKey.value) {
      closeEntityDrawer()
      return
    }
    if (rightDrawerOpen.value) {
      rightDrawerOpen.value = false
      return
    }
    if (selectedDetailEvent.value) {
      closeDetailReader()
      return
    }
  }

  if (searchOverlayOpen.value) return

  if (isEditableElement(e.target) || e.metaKey || e.ctrlKey || e.altKey) return

  if (e.key === '/') {
    e.preventDefault()
    openSearchOverlay()
    return
  }

  if (e.key === '?') {
    e.preventDefault()
    shortcutsModalOpen.value = !shortcutsModalOpen.value
    return
  }

  if (awaitingGChord) {
    awaitingGChord = false
    if (gChordTimer) clearTimeout(gChordTimer)
    const k = e.key.toLowerCase()
    const map: Record<string, WorkbenchTab> = {
      t: 'today',
      w: 'wire',
      a: 'ai_progress',
      f: 'finance',
      b: 'briefing',
      r: 'tracking',
      c: 'calendar',
      p: 'predictions',
      o: 'tools',
    }
    if (map[k]) {
      e.preventDefault()
      void switchTab(map[k])
    }
    return
  }

  if (e.key.toLowerCase() === 'g') {
    awaitingGChord = true
    if (gChordTimer) clearTimeout(gChordTimer)
    gChordTimer = setTimeout(() => {
      awaitingGChord = false
    }, 900)
    return
  }

  if (e.key === 'j') {
    e.preventDefault()
    moveKeyboardFeedFocus(1)
    return
  }

  if (e.key === 'k') {
    e.preventDefault()
    moveKeyboardFeedFocus(-1)
    return
  }

  if (e.key === 'Enter' && highlightedEventId.value) {
    const ev = allLoadedEvents.value.find((x) => x.event_id === highlightedEventId.value)
    if (ev) {
      e.preventDefault()
      openEventInDetailReader(ev)
    }
  }
}

onMounted(() => {
  if (typeof window !== 'undefined') {
    window.addEventListener('scroll', onGlobalScrollTrack, { passive: true })
    window.addEventListener('keydown', handleDesktopKeyboardShortcuts)
  }
})

onBeforeUnmount(() => {
  if (searchOverlayOpen.value) unlockBodyScroll()
  if (batchInfoModalOpen.value) unlockBodyScroll()
  if (rightDrawerOpen.value) unlockBodyScroll()
  if (shortcutsModalOpen.value) unlockBodyScroll()
  if (gChordTimer) clearTimeout(gChordTimer)
  if (typeof window !== 'undefined') {
    window.removeEventListener('scroll', onGlobalScrollTrack)
    window.removeEventListener('keydown', handleDesktopKeyboardShortcuts)
  }
})

function executeRemoveBookmark(eventId: string) {
  bookmarks.value = bookmarks.value.filter((b) => b.event_id !== eventId)
  saveBookmarkedEvents(bookmarks.value)
  notifyToast(t('已取消收藏', 'Removed bookmark'))
}

function handleToggleBookmark(ev: SmartEvent) {
  const exists = bookmarks.value.some((b) => b.event_id === ev.event_id)
  if (exists) {
    removeBookmark(ev.event_id)
  } else {
    const primary = ev.sources[0]
    bookmarks.value = [
      {
        event_id: ev.event_id,
        title: ev.title,
        url: primary?.url || '',
        category: ev.category,
        source_name: primary?.source_name || t('未知来源', 'Unknown source'),
        batch_id: activeDoc.value?.batch_id || '',
        saved_at: new Date().toISOString(),
      },
      ...bookmarks.value,
    ]
    saveBookmarkedEvents(bookmarks.value)
    if (!authSession.value) {
      notifyToast(
        t('已收藏到本地浏览器，登录后可跨设备同步', 'Saved locally — sign in to sync across devices'),
        {
          actionLabel: t('去登录同步', 'Sign in to sync'),
          onAction: () => {
            openAuthModal()
          },
        },
      )
    } else {
      notifyToast(t('已收藏并准备同步至云端', 'Saved & synced to cloud'))
    }
  }
}

function removeBookmark(eventId: string) {
  const target = bookmarks.value.find((b) => b.event_id === eventId)
  openConfirmAction({
    kind: 'remove_bookmark',
    targetId: eventId,
    title: t('确认取消收藏？', 'Remove Bookmark?'),
    message: target
      ? t(`确定将《${target.title}》移出我的收藏吗？`, `Remove "${target.title}" from your saved bookmarks?`)
      : t('确定要取消收藏这条简报吗？', 'Remove this briefing from your bookmarks?'),
    confirmLabel: t('确认取消收藏', 'Remove'),
  })
}

function startEditBookmarkTags(b: BookmarkedEvent) {
  editingBookmarkTagId.value = b.event_id
  editingBookmarkTagText.value = (b.tags || []).join(', ')
}

function saveBookmarkTags(eventId: string) {
  const tags = editingBookmarkTagText.value
    .split(/[,，\s]+/)
    .map((s) => s.trim())
    .filter(Boolean)
    .slice(0, 6)
  bookmarks.value = bookmarks.value.map((b) =>
    b.event_id === eventId ? { ...b, tags } : b,
  )
  saveBookmarkedEvents(bookmarks.value)
  editingBookmarkTagId.value = null
  notifyToast(t('已更新收藏标签', 'Updated bookmark tags'))
}

function handleCopyLink(ev: SmartEvent) {
  highlightedEventId.value = ev.event_id
  syncUrl(false)
  if (typeof window !== 'undefined' && navigator.clipboard) {
    const abs = `${window.location.origin}/s/event/${encodeURIComponent(ev.event_id)}`
    void navigator.clipboard.writeText(abs).catch(() => {})
  }
  notifyToast(t('已复制该事件直达链接（含精确事件 ID）', 'Copied permalink with exact event ID'))
}

function handleSelectEntity(ent: string) {
  if (selectedEntity.value === ent) {
    selectedEntity.value = ''
  } else {
    selectedEntity.value = ent
  }
}

const SECONDARY_TABS = new Set<WorkbenchTab>(['tracking', 'weekly'])
const isSecondaryTabActive = computed(() => SECONDARY_TABS.has(activeTab.value))
const previousTab = ref<WorkbenchTab>('today')

function handleSecondaryBack() {
  const dest: WorkbenchTab = !SECONDARY_TABS.has(previousTab.value) ? previousTab.value : 'today'
  void switchTab(dest)
}

async function switchTab(nextTab: WorkbenchTab) {
  menuCloseNonce.value += 1
  if (typeof window !== 'undefined') {
    tabScrollMemory.set(activeTab.value, window.scrollY || 0)
  }
  let targetTab: WorkbenchTab = nextTab
  if (nextTab === 'briefing') {
    todaySection.value = 'pillars'
    targetTab = 'today'
  } else if (nextTab === 'today') {
    todaySection.value = 'feed'
    returnToFinanceTab.value = false
  } else {
    returnToFinanceTab.value = false
  }
  if (nextTab === 'tools') {
    aiSubView.value = 'tools'
    targetTab = 'ai_progress'
  } else if (nextTab === 'ai_progress') {
    aiSubView.value = 'tracker'
  }
  if (nextTab === 'predictions') {
    scheduleSubView.value = 'predictions'
    targetTab = 'calendar'
  } else if (nextTab === 'calendar') {
    scheduleSubView.value = 'calendar'
  }

  if (!SECONDARY_TABS.has(activeTab.value) && targetTab !== activeTab.value) {
    previousTab.value = activeTab.value
  }
  if (targetTab === 'tracking' && searchQuery.value.trim() && searchScope.value === 'current') {
    searchQuery.value = ''
  }

  keyboardFocusIdx = -1
  activeTab.value = targetTab
  syncUrl(false)
  await ensureDataForTab(nextTab)
  void nextTick().then(() => {
    if (typeof window !== 'undefined') {
      const savedY = tabScrollMemory.get(targetTab) ?? 0
      window.scrollTo({ top: savedY, behavior: 'auto' })
    }
  })
}

async function handleOpenStoryline(storylineId: string) {
  if (!SECONDARY_TABS.has(activeTab.value)) {
    previousTab.value = activeTab.value
  }
  selectedStorylineId.value = storylineId
  activeTab.value = 'tracking'
  syncUrl(false)
  await loadStorylines()
  if (typeof window !== 'undefined') {
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }
}

function handleSelectStoryline(id: string | null) {
  selectedStorylineId.value = id
  if (id === null) {
    highlightedEventId.value = null
  }
  syncUrl(false)
}

async function handleOpenEntityByName(nameOrId: string) {
  await loadEntities()
  const key = nameOrId.trim().toLowerCase()
  const found = entities.value.find(
    (e) =>
      e.entity_id.toLowerCase() === key ||
      e.canonical_name.toLowerCase() === key ||
      e.aliases.some((a) => a.toLowerCase() === key),
  )
  if (found) {
    drawerEntityKey.value = found.entity_id
    syncUrl(false)
  } else {
    // Fallback to cross-category event search when no deep EntityProfile exists
    activeTab.value = 'today'
    todaySection.value = 'pillars'
    searchScope.value = 'all'
    searchQuery.value = nameOrId
    syncUrl(false)
    void ensureAllCategoriesLoaded()
    notifyToast(t(`暂未建档「${nameOrId}」，已为您切换至全分类相关报道检索`, `No profile yet for "${nameOrId}"; switched to cross-pillar search`))
  }
}

function closeEntityDrawer() {
  drawerEntityKey.value = null
  syncUrl(false)
}

function handleAddWatchlist(item: WatchlistItem) {
  const dup = watchlist.value.some((w) => w.label.toLowerCase() === item.label.toLowerCase())
  if (dup) {
    notifyToast(t(`关注项「${item.label}」已在列表中`, `"${item.label}" is already on your watchlist`))
    return
  }
  watchlist.value = [item, ...watchlist.value]
  saveWatchlist(watchlist.value)
  notifyToast(t(`已加入关注：${item.label}`, `Added to watchlist: ${item.label}`))
}

function handleRemoveWatchlist(id: string) {
  watchlist.value = watchlist.value.filter((w) => w.id !== id)
  saveWatchlist(watchlist.value)
}

function handleApplyWatchlistPreset(preset: WatchlistPresetTemplate) {
  const existingLabels = new Set(watchlist.value.map((w) => w.label.toLowerCase()))
  const added: WatchlistItem[] = []
  const nowIso = new Date().toISOString()
  for (const item of preset.items) {
    if (!existingLabels.has(item.label.toLowerCase())) {
      added.push({ ...item, id: `${item.id}_${Date.now().toString(36)}`, created_at: nowIso })
      existingLabels.add(item.label.toLowerCase())
    }
  }
  if (added.length > 0) {
    watchlist.value = [...added, ...watchlist.value]
    saveWatchlist(watchlist.value)
  }
  onboardingCompleted.value = true
  setOnboardingCompleted(true)
  notifyToast(
    added.length > 0
      ? t(`已套用「${preset.label}」模板（新增 ${added.length} 个关注词）`, `Applied "${preset.labelEn}" pack (+${added.length} items)`)
      : t(`「${preset.label}」关注词已在列表中`, `All items from "${preset.labelEn}" already active`),
  )
}

function handleDismissOnboardingStrip() {
  onboardingCompleted.value = true
  setOnboardingCompleted(true)
}

function handleSaveCardNote(payload: { event: SmartEvent; content: string }) {
  const trimmed = payload.content.trim()
  const existingIdx = researchNotes.value.findIndex(
    (n) => n.target_type === 'event' && n.target_id === payload.event.event_id,
  )
  if (!trimmed) {
    if (existingIdx >= 0) {
      researchNotes.value = researchNotes.value.filter((_, idx) => idx !== existingIdx)
      saveResearchNotes(researchNotes.value)
      notifyToast(t('已清空该事件笔记', 'Cleared event note'))
    }
    return
  }
  const primary = payload.event.sources?.[0]?.url
  const tickerMatches = `${payload.event.title} ${payload.event.fact_summary || ''} ${trimmed}`.match(/\b[A-Z]{2,5}(?:\.[A-Z]{1,2})?\b|\b\d{6}\.(?:SZ|SH|BJ)\b|\b\d{4,5}\.HK\b/g) || []
  const noteObj: ResearchNote = {
    note_id: existingIdx >= 0 ? researchNotes.value[existingIdx].note_id : `note_${Date.now().toString(36)}`,
    target_type: 'event',
    target_id: payload.event.event_id,
    title: payload.event.title,
    entity_ids: Array.from(new Set(payload.event.entity_ids || [])),
    tickers: Array.from(new Set(tickerMatches)).slice(0, 6),
    answer_markdown: trimmed,
    evidence_urls: primary ? [primary] : [],
    data_cutoff_at: activeDoc.value?.input_cutoff_at || manifest.value?.smart.input_cutoff_at || null,
    created_at: new Date().toISOString(),
  }
  if (existingIdx >= 0) {
    researchNotes.value = researchNotes.value.map((n, idx) => (idx === existingIdx ? noteObj : n))
  } else {
    researchNotes.value = [noteObj, ...researchNotes.value]
  }
  saveResearchNotes(researchNotes.value)
  notifyToast(
    authSession.value
      ? t('事件笔记已保存并同步云端', 'Event note saved & synced')
      : t('事件笔记已保存至本地', 'Event note saved locally'),
  )
  if (!authSession.value && researchNotes.value.length >= 2) {
    triggerSoftAuth('second_note')
  }
}

function toggleSetKey(kind: 'muted' | 'downweighted' | 'read_later', key: string) {
  const refTarget = kind === 'muted' ? mutedSet : kind === 'downweighted' ? downweightedSet : readLaterSet
  const next = new Set(refTarget.value)
  const wasPresent = next.has(key)
  if (wasPresent) next.delete(key)
  else next.add(key)
  refTarget.value = next
  saveStringSetKey(kind, next)

  if (kind === 'muted') {
    notifyToast(
      wasPresent
        ? t('已取消屏蔽，条目将在信息流恢复显示', 'Unmuted — item restored to feeds')
        : t('已屏蔽该内容（全站自动隐藏），设置已同步', 'Muted — hidden across feeds'),
    )
    if (authSession.value) {
      void pushCurrentStateToCloud(true)
    }
    return
  }

  if (kind === 'read_later') {
    const nextMeta = { ...readLaterMetaMap.value }
    if (!wasPresent) {
      const ev = allLoadedEvents.value.find((e) => e.event_id === key)
      if (ev) {
        nextMeta[key] = {
          event_id: ev.event_id,
          title: ev.title_zh || ev.title,
          url: ev.sources?.[0]?.url || '',
          category: ev.category,
          source_name: ev.sources?.[0]?.source_name || '',
          saved_at: ev.published_at || ev.fetched_at || new Date().toISOString(),
        }
      }
      readLaterMetaMap.value = nextMeta
      saveReadLaterMetaMap(nextMeta)
      if (!authSession.value) {
        notifyToast(
          t('已加入稍后深读，可在【稍后深读】中查看', 'Added to Read Later'),
          {
            actionLabel: t('登录后可跨设备同步', 'Sign in to sync'),
            onAction: () => {
              authModalOpen.value = true
            },
          },
        )
      } else {
        notifyToast(t('已加入稍后深读，可在【稍后深读】中查看', 'Added to Read Later (cloud synced)'))
      }
    } else {
      delete nextMeta[key]
      readLaterMetaMap.value = nextMeta
      saveReadLaterMetaMap(nextMeta)
      notifyToast(t('已移出稍后深读', 'Removed from Read Later'))
    }
  }
}

function handleToggleHideReprints(val: boolean) {
  hideReprints.value = val
  saveHideReprints(val)
}

function handleUpdateAlertRules(rules: AlertRuleSettings) {
  alertRules.value = rules
  saveAlertRules(rules)
}

function handleAddCustomCatalyst(ev: CatalystEvent) {
  customCatalysts.value = [ev, ...customCatalysts.value]
  saveCustomCatalysts(customCatalysts.value)
  notifyToast(t(`已添加自定义催化日历：${ev.title}`, `Added custom catalyst: ${ev.title}`))
}

function handleUpdateCustomCatalyst(ev: CatalystEvent) {
  customCatalysts.value = customCatalysts.value.map((c) =>
    c.calendar_id === ev.calendar_id ? ev : c,
  )
  saveCustomCatalysts(customCatalysts.value)
  notifyToast(t(`已更新自定义催化节点：${ev.title}`, `Updated catalyst: ${ev.title}`))
}

function handleDeleteCustomCatalyst(calendarId: string) {
  customCatalysts.value = customCatalysts.value.filter((c) => c.calendar_id !== calendarId)
  saveCustomCatalysts(customCatalysts.value)
  notifyToast(t('已删除自定义催化节点', 'Deleted custom catalyst'))
}

function handleSaveCatalystActual(payload: { calendarId: string; actualResult: string; deviation: string }) {
  const customIdx = customCatalysts.value.findIndex((c) => c.calendar_id === payload.calendarId)
  if (customIdx >= 0) {
    customCatalysts.value = customCatalysts.value.map((c) =>
      c.calendar_id === payload.calendarId
        ? { ...c, actual_result: payload.actualResult, post_deviation: payload.deviation }
        : c,
    )
    saveCustomCatalysts(customCatalysts.value)
  } else {
    const matchedServer = serverCalendarEvents.value.find((e) => e.calendar_id === payload.calendarId)
    const prevOver = catalystOverrides.value[payload.calendarId]
    const next = {
      ...catalystOverrides.value,
      [payload.calendarId]: {
        actualResult: payload.actualResult,
        deviation: payload.deviation,
        updatedAt: new Date().toISOString(),
        eventSnapshot: matchedServer || prevOver?.eventSnapshot,
      },
    }
    catalystOverrides.value = next
    saveCatalystOverrideMap(next)
  }
  notifyToast(t('已保存实际兑现与预期偏差记录（本地）', 'Saved actual outcome & deviation log (local)'))
}

function handleClearCatalystActual(calendarId: string) {
  const customIdx = customCatalysts.value.findIndex((c) => c.calendar_id === calendarId)
  if (customIdx >= 0) {
    customCatalysts.value = customCatalysts.value.map((c) =>
      c.calendar_id === calendarId ? { ...c, actual_result: null, post_deviation: null } : c,
    )
    saveCustomCatalysts(customCatalysts.value)
  } else {
    const next = { ...catalystOverrides.value }
    delete next[calendarId]
    catalystOverrides.value = next
    saveCatalystOverrideMap(next)
  }
  notifyToast(t('已清除该催化事件的本地实录与偏差记录', 'Cleared local catalyst outcome log'))
}

function handleSetPredictionStance(payload: { predictionId: string; stance: PredictionStance }) {
  const cur = predictionStances.value[payload.predictionId]
  const next = { ...predictionStances.value }
  if (cur === payload.stance) {
    delete next[payload.predictionId]
    notifyToast(t('已取消本次立场标记', 'Prediction stance cleared'))
  } else {
    next[payload.predictionId] = payload.stance
    notifyToast(t('投票已记录 · 共识概率已更新', 'Vote recorded · consensus updated'))
  }
  predictionStances.value = next
  savePredictionStances(next)
}

function handleCreatePrediction(record: PredictionRecord) {
  localPredictions.value = [record, ...localPredictions.value]
  saveLocalPredictions(localPredictions.value)
  notifyToast(t(`已立项可验证假设：${record.title}`, `Created prediction: ${record.title}`))
}

function handleDeletePrediction(predictionId: string) {
  localPredictions.value = localPredictions.value.filter((p) => p.prediction_id !== predictionId)
  saveLocalPredictions(localPredictions.value)
  notifyToast(
    predictionId.startsWith('pred_user_')
      ? t('已删除该本地自建前瞻假设', 'Deleted local prediction')
      : t('已清除本地修订/测试结算，恢复默认公开题状态', 'Reset local edits to baseline prediction'),
  )
}

function handleResetLocalPredictions() {
  localPredictions.value = []
  saveLocalPredictions([])
  notifyToast(t('已清空所有本地自建假设与测试结算记录', 'Cleared all local predictions & settlements'))
}

function handleRevisePrediction(payload: {
  predictionId: string
  newJudgment: string
  newProbPct: number
  reason: string
}) {
  const existing = mergedPredictions.value.find((p) => p.prediction_id === payload.predictionId)
  if (!existing) return
  const nextVerNum = existing.versions.length + 1
  const updated: PredictionRecord = {
    ...existing,
    versions: [
      ...existing.versions.map((v) => ({ ...v })),
      {
        version: nextVerNum,
        updated_at: new Date().toISOString(),
        judgment: payload.newJudgment,
        probability_pct: payload.newProbPct,
        reason: payload.reason,
      },
    ],
    current_judgment: payload.newJudgment,
    probability_pct: payload.newProbPct,
  }
  const rest = localPredictions.value.filter((p) => p.prediction_id !== payload.predictionId)
  localPredictions.value = [updated, ...rest]
  saveLocalPredictions(localPredictions.value)
  notifyToast(t(`已保存 v${nextVerNum} 修订（v1 底稿已完整保留）`, `Saved revision v${nextVerNum} (v1 preserved)`))
}

function handleSettlePrediction(payload: {
  predictionId: string
  outcome: 'correct' | 'incorrect' | 'indeterminate'
  evidenceUrl: string
  note: string
}) {
  const existing = mergedPredictions.value.find((p) => p.prediction_id === payload.predictionId)
  if (!existing) return
  const updated: PredictionRecord = {
    ...existing,
    status: 'settled',
    settlement: {
      outcome: payload.outcome,
      settled_at: new Date().toISOString(),
      evidence_url: payload.evidenceUrl || null,
      note: payload.note,
    },
  }
  const rest = localPredictions.value.filter((p) => p.prediction_id !== payload.predictionId)
  localPredictions.value = [updated, ...rest]
  saveLocalPredictions(localPredictions.value)
  notifyToast(t('已完成假设客观结算', 'Settled prediction'))
}

function handleExportAllResearch() {
  if (typeof window === 'undefined') return
  const jsonText = exportAllResearchState()
  const blob = new Blob([jsonText], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `insight-pro-v3-research-${new Date().toISOString().slice(0, 10)}.json`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  setTimeout(() => URL.revokeObjectURL(url), 1000)
  notifyToast(t('已导出全站研究状态 JSON（含关注/屏蔽/预测/笔记/工具清单）', 'Exported research state JSON backup'))
}

function handleImportAllResearch(fileText: string) {
  const res = importResearchStateJson(fileText)
  if (!res.ok) {
    notifyToast(t(`导入失败：${res.error || '格式无效'}`, `Import failed: ${res.error || 'Invalid format'}`))
    return
  }
  watchlist.value = loadWatchlist()
  mutedSet.value = loadStringSetKey('muted')
  downweightedSet.value = loadStringSetKey('downweighted')
  readLaterSet.value = loadStringSetKey('read_later')
  readLaterMetaMap.value = loadReadLaterMetaMap()
  hideReprints.value = loadHideReprints()
  alertRules.value = loadAlertRules()
  localPredictions.value = loadLocalPredictions()
  toolStates.value = loadToolStates()
  researchNotes.value = loadResearchNotes()
  customCatalysts.value = loadCustomCatalysts()
  catalystOverrides.value = loadCatalystOverrideMap()
  bookmarks.value = loadBookmarkedEvents()
  const refreshedRead = loadReadState()
  readIds.value = refreshedRead.readIds
  legacyReadTitles.value = refreshedRead.legacyReadTitles
  notifyToast(t(`成功从 JSON 备份恢复 ${res.importedCount} 项研究状态`, `Restored ${res.importedCount} research groups from JSON backup`))
}

function handleTopbarFileImport(ev: Event) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  void file.text().then((txt) => handleImportAllResearch(txt))
  input.value = ''
}

function handleClearAllLocalState() {
  clearLocalResearchState()
  watchlist.value = loadWatchlist()
  mutedSet.value = new Set()
  downweightedSet.value = new Set()
  readLaterSet.value = new Set()
  readLaterMetaMap.value = {}
  saveReadLaterMetaMap({})
  hideReprints.value = loadHideReprints()
  alertRules.value = loadAlertRules()
  localPredictions.value = []
  toolStates.value = {}
  researchNotes.value = []
  customCatalysts.value = []
  catalystOverrides.value = {}
  bookmarks.value = []
  readIds.value = new Set()
  legacyReadTitles.value = new Set()
  predictionStances.value = {}
  clearConfirmModalOpen.value = false
  notifyToast(t('已清空本浏览器内的本地自建数据与测试记录（公共内容与 API 密钥保持不变）', 'Reset local browser data (public briefs & API keys kept)'))
}

function isKeyChangeRead(eventId: string | null | undefined): boolean {
  if (!eventId || !activeDoc.value) return false
  const ev = activeDoc.value.events.find((e) => e.event_id === eventId)
  return ev ? checkIsRead(ev) : false
}

function handleUpdateToolState(payload: { toolId: string; wantTry: boolean; note: string }) {
  const prev = toolStates.value[payload.toolId]
  toolStates.value = {
    ...toolStates.value,
    [payload.toolId]: {
      wantTry: payload.wantTry,
      note: payload.note,
      updatedAt: new Date().toISOString(),
    },
  }
  saveToolStates(toolStates.value)
  if (prev?.wantTry !== payload.wantTry) {
    notifyToast(
      payload.wantTry
        ? t('已加入个人试用清单', 'Added to personal tryout list')
        : t('已移出试用清单', 'Removed from tryout list'),
    )
  }
}

function openQaGlobal() {
  void Promise.all([ensureAllCategoriesLoaded(), loadTopics(), loadCalendar()])
  qaContextEvent.value = null
  qaContextStoryline.value = null
  qaContextEntity.value = null
  qaContextTopic.value = null
  qaContextPrompt.value = null
  qaModalOpen.value = true
}

function openQaForEvent(ev: SmartEvent) {
  void ensureAllCategoriesLoaded()
  qaContextEvent.value = ev
  qaContextStoryline.value = null
  qaContextEntity.value = null
  qaContextTopic.value = null
  qaContextPrompt.value = null
  qaModalOpen.value = true
}

function openQaForStoryline(dossier: StorylineDossier) {
  void ensureAllCategoriesLoaded()
  qaContextEvent.value = null
  qaContextStoryline.value = dossier
  qaContextEntity.value = null
  qaContextTopic.value = null
  qaContextPrompt.value = null
  qaModalOpen.value = true
}

function openQaForEntity(entity: EntityProfile) {
  void ensureAllCategoriesLoaded()
  qaContextEvent.value = null
  qaContextStoryline.value = null
  qaContextEntity.value = entity
  qaContextTopic.value = null
  qaContextPrompt.value = null
  qaModalOpen.value = true
}

function openQaForTopic(topic: MajorTopicSpotlight) {
  void ensureAllCategoriesLoaded()
  qaContextEvent.value = null
  qaContextStoryline.value = null
  qaContextEntity.value = null
  qaContextTopic.value = topic
  qaContextPrompt.value = null
  qaModalOpen.value = true
}

function openQaForPrediction(rec: PredictionRecord) {
  void Promise.all([ensureAllCategoriesLoaded(), loadFinanceImpact(), loadLiveWire()])
  qaContextEvent.value = null
  qaContextStoryline.value = null
  qaContextEntity.value = null
  qaContextTopic.value = null
  qaContextPrompt.value = t(
    `请结合站内最新一手报道、快讯与市场传导数据，帮我研判预测题「${rec.title}」（判定条件：${rec.win_rule || rec.question}），分别总结正反两方核心依据。`,
    `Using the latest verified news, wires, and market impacts on this site, analyze "${rec.title}" (Win criteria: ${rec.win_rule || rec.question}) with bullish and bearish arguments.`,
  )
  qaModalOpen.value = true
}

function handleUnmuteAll() {
  mutedSet.value = new Set()
  saveStringSetKey('muted', mutedSet.value)
  notifyToast(t('已恢复全部被屏蔽事件显示', 'Restored all muted items'))
}

async function handleJumpToTodayEvent(ev: SmartEvent) {
  activeTab.value = 'today'
  todaySection.value = 'pillars'
  activeCategory.value = ev.category
  highlightedEventId.value = ev.event_id
  await ensureCategoryLoaded(ev.category)
  syncUrl(false)
  scrollToHighlightedEvent()
}

async function handleJumpToEventId(eventId: string, fallbackUrl?: string | null) {
  const fromFinance = activeTab.value === 'finance'
  await ensureAllCategoriesLoaded()
  const found = allLoadedEvents.value.find((e) => e.event_id === eventId)
  if (found) {
    searchQuery.value = ''
    sourceFilter.value = 'all'
    evidenceFilter.value = 'all'
    onlyUnreadOrNew.value = false
    selectedEntity.value = ''
    briefingVisibleLimit.value = Math.max(briefingVisibleLimit.value, 100)
    if (typeof window !== 'undefined' && window.innerWidth >= 1280) {
      selectedDetailEvent.value = found
    }
    returnToFinanceTab.value = fromFinance
    await handleJumpToTodayEvent(found)
    return
  }
  const hasUrl = Boolean(fallbackUrl && /^https?:\/\//i.test(fallbackUrl))
  notifyToast(
    t('该条新闻已不在当前最新简报批次中', 'This story is no longer in the latest briefing batch'),
    hasUrl
      ? {
          actionLabel: t('打开原文', 'Open Source'),
          onAction: () => {
            if (typeof window !== 'undefined' && fallbackUrl) {
              window.open(fallbackUrl, '_blank', 'noopener,noreferrer')
            }
          },
        }
      : undefined,
  )
}

function handleCopyDailyBriefing() {
  const lines: string[] = [
    `【镜信 MirrorBrief 每日速览 · ${activeDoc.value?.batch_id || manifest.value?.smart.latest_batch_id || ''}】`,
  ]
  if (majorTopics.value.length > 0) {
    lines.push('\n【全网超级专题】')
    for (const tp of majorTopics.value.slice(0, 2)) {
      const latestNode = tp.timeline[tp.timeline.length - 1]
      lines.push(`• ${tp.title}：${latestNode ? latestNode.title : tp.subtitle}`)
    }
  }
  const catNames: Record<CategoryKey, string> = {
    global: '国际/宏观',
    finance: '财经/市场',
    tech: '科技/AI',
    general: '社会/热点',
  }
  for (const cat of ['global', 'finance', 'tech', 'general'] as CategoryKey[]) {
    const evs = (docsByCat.value[cat]?.events || []).slice(0, 2)
    if (evs.length > 0) {
      lines.push(`\n[${catNames[cat]}]`)
      for (const ev of evs) {
        lines.push(`• ${ev.title}`)
      }
    }
  }
  if (typeof window !== 'undefined') {
    lines.push(`\n完整工作台：${window.location.origin}${window.location.pathname}`)
    if (navigator.clipboard) {
      void navigator.clipboard.writeText(lines.join('\n')).catch(() => {})
    }
  }
  notifyToast('已复制 30 秒速览日报（可直接粘贴发微信/飞书）')
}

function handleSaveResearchNote(note: ResearchNote) {
  researchNotes.value = [note, ...researchNotes.value]
  saveResearchNotes(researchNotes.value)
  notifyToast(
    authSession.value
      ? t('研究笔记已保存并将同步至云端', 'Research note saved & synced to cloud')
      : t('研究笔记已保存至本机浏览器（登录后可跨设备同步）', 'Research note saved locally (sign in to sync)'),
  )
  if (!authSession.value && researchNotes.value.length >= 2) {
    triggerSoftAuth('second_note')
  }
}

function executeDeleteResearchNote(noteId: string) {
  researchNotes.value = researchNotes.value.filter((n) => n.note_id !== noteId)
  saveResearchNotes(researchNotes.value)
  notifyToast(t('已删除研报笔记', 'Research note deleted'))
}

function handleDeleteResearchNote(noteId: string) {
  const note = researchNotes.value.find((n) => n.note_id === noteId)
  openConfirmAction({
    kind: 'delete_note',
    targetId: noteId,
    title: t('确认删除研报笔记？', 'Delete Research Note?'),
    message: note
      ? t(`确定永久删除笔记《${note.title}》吗？删除后将无法恢复。`, `Permanently delete note "${note.title}"? This cannot be undone.`)
      : t('确定要永久删除这条研报笔记吗？', 'Permanently delete this research note?'),
    confirmLabel: t('确认删除', 'Delete'),
  })
}

function triggerFeedbackDialog() {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('infofocus-open-feedback'))
  }
}

async function loadHistoryList(forceFresh = false) {
  historyLoading.value = true
  historyError.value = null
  try {
    historyEntries.value = await fetchHistoryIndex('smart', forceFresh)
  } catch (err) {
    historyError.value = err instanceof Error ? err.message : '加载历史索引失败'
  } finally {
    historyLoading.value = false
  }
}

function getHistoryEntryDateStr(entry: HistoryIndexEntry): string {
  const raw = entry.generated_at || entry.published_at || entry.fetched_at
  if (raw) {
    const d = formatShanghaiDateOnly(raw)
    if (d && d !== '-') return d
  }
  const m = `${entry.path || ''} ${entry.display || ''}`.match(/(20\d{2}-\d{2}-\d{2})/)
  return m ? m[1] : ''
}

const availableHistoryDates = computed<string[]>(() => {
  const s = new Set<string>()
  for (const e of historyEntries.value) {
    const d = getHistoryEntryDateStr(e)
    if (d) s.add(d)
  }
  return Array.from(s).sort((a, b) => b.localeCompare(a))
})

const entriesForSelectedPillarDate = computed<HistoryIndexEntry[]>(() => {
  if (!pillarSelectedDate.value) return []
  return historyEntries.value.filter((e) => getHistoryEntryDateStr(e) === pillarSelectedDate.value)
})

async function togglePillarCalendar() {
  pillarCalendarOpen.value = !pillarCalendarOpen.value
  if (pillarCalendarOpen.value && historyEntries.value.length === 0) {
    await loadHistoryList()
    if (!pillarSelectedDate.value && availableHistoryDates.value.length > 0) {
      pillarSelectedDate.value = availableHistoryDates.value[0]
    }
  }
}

async function loadPillarMultiDayRange(days: 3 | 7) {
  pillarRangeLoading.value = true
  try {
    if (historyEntries.value.length === 0) {
      await loadHistoryList()
    }
    const todayStr = formatShanghaiDateOnly(new Date(nowMs.value).toISOString())
    const cutoffStr = formatShanghaiDateOnly(new Date(nowMs.value - (days - 1) * 86_400_000).toISOString())
    const latestPerDate = new Map<string, HistoryIndexEntry>()
    for (const entry of historyEntries.value) {
      const d = getHistoryEntryDateStr(entry)
      if (!d || d === todayStr || d < cutoffStr) continue
      const prev = latestPerDate.get(d)
      const curMs = parseTimestampMs(entry.generated_at || entry.published_at || entry.fetched_at) ?? 0
      const prevMs = prev ? parseTimestampMs(prev.generated_at || prev.published_at || prev.fetched_at) ?? 0 : -1
      if (!prev || curMs > prevMs) {
        latestPerDate.set(d, entry)
      }
    }
    const catsToFetch: CategoryKey[] = searchScope.value === 'all' ? ALL_CATS : [activeCategory.value]
    if (searchScope.value === 'all') {
      await ensureAllCategoriesLoaded()
    } else {
      await ensureCategoryLoaded(activeCategory.value)
    }
    const sortedEntries = Array.from(latestPerDate.entries())
      .sort((a, b) => b[0].localeCompare(a[0]))
      .slice(0, days - 1)
    const fetchJobs: Promise<SmartCategoryDoc>[] = []
    for (const [, entry] of sortedEntries) {
      const normPath = entry.path.endsWith('/') ? entry.path : `${entry.path}/`
      for (const cat of catsToFetch) {
        const cacheKey = `${normPath}::${cat}`
        if (archiveCatCache.value[cacheKey]) {
          fetchJobs.push(Promise.resolve(archiveCatCache.value[cacheKey]))
        } else {
          fetchJobs.push(
            fetchSmartCategory(cat, { archivePath: normPath }).then((doc) => {
              if (!doc.missing) {
                archiveCatCache.value = { ...archiveCatCache.value, [cacheKey]: doc }
              }
              return doc
            }),
          )
        }
      }
    }
    const archiveDocs = await Promise.all(fetchJobs)
    const seenIds = new Set<string>()
    const seenTitles = new Set<string>()
    const merged: SmartEvent[] = []
    for (const ev of loadedEventsForScope.value) {
      const tKey = (ev.title_zh || ev.title || '').trim().toLowerCase()
      seenIds.add(ev.event_id)
      if (tKey) seenTitles.add(tKey)
      merged.push(ev)
    }
    for (const doc of archiveDocs) {
      if (doc.missing) continue
      for (const ev of doc.events) {
        const tKey = (ev.title_zh || ev.title || '').trim().toLowerCase()
        if (seenIds.has(ev.event_id) || (tKey && seenTitles.has(tKey))) continue
        seenIds.add(ev.event_id)
        if (tKey) seenTitles.add(tKey)
        merged.push(ev)
      }
    }
    pillarRangeEvents.value = merged
  } finally {
    pillarRangeLoading.value = false
  }
}

async function setPillarDateRange(range: 'today' | '3d' | '7d') {
  if (isHistoryMode.value && range === 'today') {
    await returnToLatest()
    return
  }
  if (isHistoryMode.value) {
    historyPath.value = null
    perspectivesOpen.value = false
    highlightedEventId.value = null
    syncUrl(false)
    await loadInitial(false)
  }
  pillarDateRange.value = range
  pillarCalendarOpen.value = false
  if (range === 'today') {
    pillarRangeEvents.value = []
    return
  }
  await loadPillarMultiDayRange(range === '3d' ? 3 : 7)
}

async function selectHistoryEntry(entry: HistoryIndexEntry) {
  historyPath.value = entry.path.endsWith('/') ? entry.path : `${entry.path}/`
  activeTab.value = 'today'
  todaySection.value = 'pillars'
  pillarDateRange.value = 'archive'
  pillarCalendarOpen.value = false
  perspectivesOpen.value = false
  highlightedEventId.value = null
  syncUrl(false)
  await loadInitial(false)
}

async function returnToLatest() {
  historyPath.value = null
  pillarDateRange.value = 'today'
  pillarCalendarOpen.value = false
  pillarSelectedDate.value = ''
  pillarRangeEvents.value = []
  perspectivesOpen.value = false
  highlightedEventId.value = null
  syncUrl(false)
  await loadInitial(true)
}

async function openBatchDiffModal(prevBatchId: string, currentEvent: SmartEvent) {
  batchDiffTargetBatchId.value = prevBatchId
  batchDiffCurrentEvent.value = currentEvent
  batchDiffPrevEvent.value = null
  batchDiffStoryline.value = null
  batchDiffModalOpen.value = true
  batchDiffLoading.value = true
  try {
    await Promise.all([
      historyEntries.value.length === 0 ? loadHistoryList() : Promise.resolve(),
      !storylinesLoaded.value ? loadStorylines() : Promise.resolve(),
    ])
    if (currentEvent.storyline_id && storylinesMap.value[currentEvent.storyline_id]) {
      batchDiffStoryline.value = storylinesMap.value[currentEvent.storyline_id]
    }
    const match = historyEntries.value.find((e) => e.batch_id === prevBatchId)
    if (match) {
      const prevDoc = await fetchSmartCategory(currentEvent.category, {
        archivePath: match.path,
        manifest: manifest.value,
      })
      batchDiffPrevEvent.value =
        prevDoc.events.find(
          (pe) =>
            pe.event_id === currentEvent.event_id ||
            (currentEvent.storyline_id && pe.storyline_id === currentEvent.storyline_id) ||
            pe.title === currentEvent.title,
        ) ?? null
    }
  } finally {
    batchDiffLoading.value = false
  }
}

async function openPreviousBatch(prevBatchId: string) {
  if (historyEntries.value.length === 0) {
    await loadHistoryList()
  }
  const match = historyEntries.value.find((e) => e.batch_id === prevBatchId)
  if (match) {
    await selectHistoryEntry(match)
  } else {
    notifyToast(t('该历史快照暂不可用', 'Historical snapshot unavailable'))
  }
}

async function handleManualRefresh() {
  if (isRefreshing.value) return
  isRefreshing.value = true
  const prevIds = new Set(allLoadedEvents.value.map((e) => e.event_id))
  try {
    if (isHistoryMode.value) {
      await loadInitial(false)
      notifyToast(t('已刷新当前历史归档视图', 'Archive snapshot reloaded'))
    } else {
      await loadInitial(true)
      await ensureDataForTab(activeTab.value, true)
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('jingxin:refresh-quotes'))
      }
      const freshIds = new Set<string>()
      for (const c of ALL_CATS) {
        for (const ev of docsByCat.value[c]?.events ?? []) {
          freshIds.add(ev.event_id)
        }
      }
      let newCount = 0
      for (const id of freshIds) {
        if (!prevIds.has(id)) newCount += 1
      }
      notifyToast(
        newCount > 0
          ? t(`已更新 ${newCount} 条最新事件与行情`, `Updated ${newCount} new events & quotes`)
          : t('已是最新 · 行情与批次已同步', 'Up to date · batch & quotes synced'),
      )
    }
  } catch (err) {
    notifyToast(
      t(
        `检查更新失败：${err instanceof Error ? err.message : '网络异常，请稍后重试'}`,
        `Refresh failed: ${err instanceof Error ? err.message : 'Network error'}`,
      ),
    )
  } finally {
    isRefreshing.value = false
  }
}

async function checkForNewBatch() {
  if (isHistoryMode.value || !manifest.value) return
  const fresh = await fetchManifest(true)
  if (!fresh) return
  if (fresh.smart.latest_batch_id && fresh.smart.latest_batch_id !== manifest.value.smart.latest_batch_id) {
    pendingNewManifest.value = fresh
    await loadPendingNewBatch()
  }
}

async function loadPendingNewBatch() {
  if (!pendingNewManifest.value) return
  // Keep previous batch as baseline so newly added items get marked as "新增"
  if (manifest.value?.smart.latest_batch_id) {
    previousBatchId.value = manifest.value.smart.latest_batch_id
    const curSeen = new Set<string>()
    for (const c of ALL_CATS) {
      for (const ev of docsByCat.value[c]?.events ?? []) {
        curSeen.add(ev.event_id)
      }
    }
    previousSeenIds.value = curSeen
  }
  await loadInitial(true)
}

function clearFilters() {
  searchQuery.value = ''
  searchScope.value = 'current'
  sourceFilter.value = 'all'
  evidenceFilter.value = 'all'
  onlyUnreadOrNew.value = false
  onlyBlindspot.value = false
  selectedEntity.value = ''
  syncUrl(true)
}

async function handleBookmarkNavigate(b: BookmarkedEvent) {
  bookmarksModalOpen.value = false
  activeTab.value = 'today'
  todaySection.value = 'pillars'
  if (activeCategory.value !== b.category) {
    activeCategory.value = b.category
  }
  highlightedEventId.value = b.event_id
  clearFilters()
  await ensureCategoryLoaded(b.category)
  syncUrl(false)
  scrollToHighlightedEvent()
}

// Auto-switch to cross-4-category search when typing a query on Pillars view so global search never misses!
watch(searchQuery, (q) => {
  if (q.trim().length > 0 && activeTab.value === 'today' && todaySection.value === 'pillars' && searchScope.value === 'current') {
    searchScope.value = 'all'
    void ensureAllCategoriesLoaded()
  }
})

// Keep search/freshness synced gently with replaceState and lazy-load other categories when needed
watch([searchQuery, searchScope, sourceFilter, evidenceFilter, onlyUnreadOrNew, freshBucket], () => {
  syncUrl(true)
  if (searchScope.value === 'all' || searchQuery.value.trim().length > 0) {
    void ensureAllCategoriesLoaded()
  }
})

watch(searchScope, () => {
  if (!isHistoryMode.value && (pillarDateRange.value === '3d' || pillarDateRange.value === '7d')) {
    void loadPillarMultiDayRange(pillarDateRange.value === '3d' ? 3 : 7)
  }
})

function handlePopState() {
  const next = parseBriefingUrlState()
  const mappedTab: WorkbenchTab =
    next.tab === 'briefing'
      ? 'today'
      : next.tab === 'tools'
        ? 'ai_progress'
        : next.tab === 'predictions'
          ? 'calendar'
          : next.tab
  const tabChanged = mappedTab !== activeTab.value
  const catChanged = next.cat !== activeCategory.value
  const historyChanged = next.history !== historyPath.value

  activeTab.value = mappedTab
  if (next.tab === 'briefing') todaySection.value = 'pillars'
  if (next.tab === 'tools') aiSubView.value = 'tools'
  if (next.tab === 'predictions') scheduleSubView.value = 'predictions'
  activeCategory.value = next.cat
  historyPath.value = next.history
  selectedWeekId.value = next.week || null
  highlightedEventId.value = next.event
  selectedStorylineId.value = next.story
  drawerEntityKey.value = next.entity
  freshBucket.value = next.fresh
  searchQuery.value = next.q
  searchScope.value = next.scope
  sourceFilter.value = next.source
  evidenceFilter.value = next.evidence
  onlyUnreadOrNew.value = next.unread
  if (typeof window !== 'undefined' && hasInvalidBriefingUrlParams(window.location.search)) {
    syncUrl(true)
  }

  if (historyChanged) {
    void loadInitial(false)
  } else {
    if (tabChanged) {
      void ensureDataForTab(next.tab)
    }
    if (next.entity) {
      void loadEntities()
    }
    if (catChanged) {
      void ensureCategoryLoaded(next.cat)
    } else {
      scrollToHighlightedEvent()
    }
  }
}

watch(manifest, (m) => {
  if (m) {
    void ensureAllCategoriesLoaded()
    void loadEntities()
  }
})

// Cloud Account & Encrypted Auto-Sync State
const authSession = ref<AuthSession | null>(loadAuthSession())
const authModalOpen = ref(false)
const authModalSection = ref<'profile' | 'security' | undefined>(undefined)
const authModalMode = ref<'login' | 'register' | null>(null)
const openWatchlistNonce = ref(0)
const avatarPickerOpen = ref(false)

type ConfirmActionKind = 'logout' | 'delete_note' | 'remove_bookmark'
interface PendingConfirmAction {
  kind: ConfirmActionKind
  targetId?: string
  title: string
  message: string
  confirmLabel: string
}
const pendingConfirmAction = ref<PendingConfirmAction | null>(null)

function openConfirmAction(action: PendingConfirmAction) {
  pendingConfirmAction.value = action
}

function closeConfirmAction() {
  pendingConfirmAction.value = null
}

function runConfirmedAction() {
  const action = pendingConfirmAction.value
  pendingConfirmAction.value = null
  if (!action) return
  if (action.kind === 'logout') {
    executeLogoutNow()
  } else if (action.kind === 'delete_note' && action.targetId) {
    executeDeleteResearchNote(action.targetId)
  } else if (action.kind === 'remove_bookmark' && action.targetId) {
    executeRemoveBookmark(action.targetId)
  }
}

function openAuthModal(section?: 'profile' | 'security' | 'login' | 'register') {
  if (section === 'login' || section === 'register') {
    authModalSection.value = undefined
    authModalMode.value = section
  } else {
    authModalMode.value = null
    authModalSection.value = section
  }
  authModalOpen.value = true
}

function requestLogoutWithConfirm() {
  openConfirmAction({
    kind: 'logout',
    title: t('确认退出登录？', 'Sign Out?'),
    message: t('退出后当前设备将清除头像显示，已加密同步至云端的个人数据仍安全保留在您的账号中。', 'Your avatar will be cleared from this device. Your synced data remains safely stored in your cloud account.'),
    confirmLabel: t('确认退出', 'Sign Out'),
  })
}

async function openWatchlistManagerFromMe() {
  await switchTab('today')
  openWatchlistNonce.value += 1
}

function handlePortfolioChanged(cfg: PortfolioConfig, hitCount?: number) {
  userPortfolio.value = cfg
  if (typeof hitCount === 'number') {
    notifyToast(
      t(
        `自选股配置已保存 · 命中 ${hitCount} 条市场传导`,
        `Watchlist tickers saved · ${hitCount} transmission hits`,
      ),
    )
  }
  if (!authSession.value && !portfolioSoftPromptShown) {
    portfolioSoftPromptShown = true
    triggerSoftAuth('portfolio_saved')
  }
}

function handleMarketColorChanged(redUp: boolean) {
  notifyToast(
    redUp
      ? t('行情涨跌色已切换为「红涨绿跌」', 'Market colors set to Red-Up / Green-Down')
      : t('行情涨跌色已切换为「绿涨红跌」', 'Market colors set to Green-Up / Red-Down'),
  )
  scheduleCloudPush()
}
const userAvatar = ref<string>(loadUserAvatar() || authSession.value?.user?.avatar || '')
const cloudSyncBusy = ref(false)
const lastSyncedAt = ref<string | null>(null)
let cloudSyncTimer: ReturnType<typeof setTimeout> | null = null
let suppressAutoSync = false

function reloadAllLocalStateRefs() {
  watchlist.value = loadWatchlist()
  mutedSet.value = loadStringSetKey('muted')
  downweightedSet.value = loadStringSetKey('downweighted')
  readLaterSet.value = loadStringSetKey('read_later')
  readLaterMetaMap.value = loadReadLaterMetaMap()
  hideReprints.value = loadHideReprints()
  alertRules.value = loadAlertRules()
  localPredictions.value = loadLocalPredictions()
  toolStates.value = loadToolStates()
  researchNotes.value = loadResearchNotes()
  customCatalysts.value = loadCustomCatalysts()
  catalystOverrides.value = loadCatalystOverrideMap()
  bookmarks.value = loadBookmarkedEvents()
  userPortfolio.value = loadPortfolioConfig()
  predictionStances.value = loadPredictionStances()
  userAvatar.value = loadUserAvatar() || authSession.value?.user?.avatar || ''
  const refreshedRead = loadReadState()
  readIds.value = refreshedRead.readIds
  legacyReadTitles.value = refreshedRead.legacyReadTitles
}

async function handleSelectAvatar(nextAvatar: string) {
  const clean = saveUserAvatar(nextAvatar)
  userAvatar.value = clean
  if (authSession.value) {
    authSession.value = {
      token: authSession.value.token,
      user: { ...authSession.value.user, avatar: clean },
    }
    saveAuthSession(authSession.value)
    await pushCurrentStateToCloud(true)
    notifyToast(t('头像已更新并同步至云端', 'Avatar updated & synced to cloud'))
  } else {
    notifyToast(t('头像已更换并保存在本机', 'Avatar updated locally'))
  }
}

async function pushCurrentStateToCloud(silent = true) {
  if (!authSession.value || suppressAutoSync) return
  cloudSyncBusy.value = true
  try {
    const snapshot = JSON.parse(exportAllResearchState()) as Record<string, unknown>
    const res = await apiPushCloudState(authSession.value.token, snapshot)
    lastSyncedAt.value = res.updated_at
    if (!silent) notifyToast(t('已将个人研究数据加密同步至云端', 'Encrypted research state synced to cloud'))
  } catch (err) {
    if (!silent) {
      notifyToast(t(`云端同步失败：${err instanceof Error ? err.message : '网络异常'}`, `Cloud sync failed: ${err instanceof Error ? err.message : 'Network error'}`))
    }
  } finally {
    cloudSyncBusy.value = false
  }
}

async function pullOrInitCloudState(silent = true) {
  if (!authSession.value) return
  cloudSyncBusy.value = true
  try {
    const pulled = await apiPullCloudState(authSession.value.token)
    if (pulled.has_state && pulled.state) {
      let mergedRes = { ok: true, mergedCount: 0, needsPush: false }
      suppressAutoSync = true
      try {
        mergedRes = mergeResearchStateJson(JSON.stringify(pulled.state))
        reloadAllLocalStateRefs()
      } finally {
        suppressAutoSync = false
      }
      lastSyncedAt.value = pulled.updated_at
      if (mergedRes.needsPush) {
        await pushCurrentStateToCloud(true)
      }
      if (!silent) notifyToast(t('已将本地与云端研究数据双向合并同步', 'Merged & synced local and cloud research state'))
    } else {
      await pushCurrentStateToCloud(silent)
    }
  } catch (err) {
    const msg = err instanceof Error ? err.message : ''
    if (msg.includes('过期') || msg.includes('失效')) {
      clearAuthSession()
      authSession.value = null
    } else if (!silent) {
      notifyToast(`云端同步失败：${msg || '网络异常'}`)
    }
  } finally {
    cloudSyncBusy.value = false
  }
}

function scheduleCloudPush() {
  if (!authSession.value || suppressAutoSync) return
  if (cloudSyncTimer) clearTimeout(cloudSyncTimer)
  cloudSyncTimer = setTimeout(() => {
    void pushCurrentStateToCloud(true)
  }, 1500)
}

async function handleAuthenticated(sess: AuthSession) {
  authSession.value = sess
  saveAuthSession(sess)
  if (sess.user.avatar) {
    userAvatar.value = saveUserAvatar(sess.user.avatar)
  }
  invalidateReactionsCache()
  const stagedEntries = Object.entries(guestStagedVotes.value)
  if (stagedEntries.length > 0) {
    for (const [pid, prob] of stagedEntries) {
      try {
        await apiSubmitPredictionVote(sess.token, pid, prob)
      } catch {
        // ignore single prediction flush failure
      }
    }
    guestStagedVotes.value = {}
    saveGuestStagedVotes({})
  }
  if (predictionsLoaded.value || activeTab.value === 'calendar') {
    void loadPredictions(true)
  } else {
    void apiFetchMe(sess.token)
      .then((me) => {
        predictionBonusQaQuota.value = Math.max(0, Number(me.prediction_bonus_qa_quota ?? 0))
      })
      .catch(() => {})
  }
  if (sess.referral_bonus_granted && sess.referral_bonus_granted > 0) {
    notifyToast(
      t(
        `欢迎加入！已兑现邀请码，您与邀请人同时获赠每日 +${sess.referral_bonus_granted} 次 AI 问答额度`,
        `Welcome! Invite redeemed — both accounts received +${sess.referral_bonus_granted} daily AI Q&As`,
      ),
    )
  } else {
    notifyToast(
      t(
        `欢迎回来，${sess.user.display_name || sess.user.username}！正在同步加密云端数据...`,
        `Welcome back, ${sess.user.display_name || sess.user.username}! Syncing cloud data...`,
      ),
    )
  }
  await pullOrInitCloudState(false)
  if (!workbenchStarted) {
    startLiveWorkbench()
  }
}

function executeLogoutNow() {
  clearAuthSession()
  authSession.value = null
  arenaProfile.value = null
  predictionBonusQaQuota.value = 0
  lastSyncedAt.value = null
  authModalOpen.value = false
  userAvatar.value = saveUserAvatar('')
  if (siteAccessMode.value === 'private_gate') {
    wireStreamHandle?.stop()
    wireStreamHandle = null
    stopGlobalQuotesPolling()
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
    workbenchStarted = false
  }
  notifyToast(t('已安全退出账号', 'Signed out cleanly'))
}

function handleLogout() {
  requestLogoutWithConfirm()
}

watch(
  [
    watchlist,
    mutedSet,
    downweightedSet,
    readLaterSet,
    hideReprints,
    alertRules,
    localPredictions,
    toolStates,
    researchNotes,
    customCatalysts,
    catalystOverrides,
    bookmarks,
    userPortfolio,
    readLaterMetaMap,
    predictionStances,
    userAvatar,
    readIds,
    legacyReadTitles,
  ],
  () => {
    scheduleCloudPush()
  },
  { deep: true },
)

function handleVisibilityChange() {
  if (typeof document !== 'undefined' && document.visibilityState !== 'visible') {
    saveDailyReadingState(dailyReading.value)
  }
}

function handleDarkStorageSync(e: StorageEvent) {
  if (e.key && e.key !== 'insight_pro_dark_mode') return
  const synced = readDarkMode()
  if (synced !== isDark.value) {
    isDark.value = synced
  }
  applyDarkClass(synced)
}

let workbenchStarted = false

function startLiveWorkbench() {
  if (workbenchStarted) return
  workbenchStarted = true
  void loadInitial(false)
  if (!isHistoryMode.value) {
    startGlobalQuotesPolling()
    wireStreamHandle = createLiveWireController({
      fetchStaticFallback: () => fetchLiveWire(manifest.value, true),
      fetchAiFallback: () => fetchAiProgress(manifest.value, true),
      getAuthToken: () => authSession.value?.token ?? null,
      pollIntervalMs: 45_000,
      enableSse: false,
      onTransportChange: (mode) => {
        wireTransportMode.value = mode
      },
      onUpdate: (doc, newIds) => {
        liveWireDoc.value = doc
        liveWireLoaded.value = true
        nowMs.value = Date.now()
        if (newIds.length > 0) {
          justArrivedWireIds.value = Array.from(new Set([...newIds, ...justArrivedWireIds.value])).slice(0, 24)
          setTimeout(() => {
            const drop = new Set(newIds)
            justArrivedWireIds.value = justArrivedWireIds.value.filter((id) => !drop.has(id))
          }, 25_000)
          const wlKeywords = watchlist.value.map((w) => w.label.toLowerCase()).filter(Boolean)
          const hot = doc.items.find(
            (it) =>
              newIds.includes(it.id) &&
              (it.importance === 'high' || wlKeywords.some((k) => it.title.toLowerCase().includes(k))),
          )
          if (hot) {
            dispatchImportantNewsNotification({
              id: `wire_${hot.id}`,
              title: t('镜信重磅电报', 'MirrorBrief Breaking Wire'),
              body: hot.title,
              tab: 'wire',
            })
          }
        }
      },
      onAiUpdate: (doc, newIds) => {
        aiProgressDoc.value = doc
        aiProgressLoaded.value = true
        nowMs.value = Date.now()
        if (newIds.length > 0) {
          justArrivedAiIds.value = Array.from(new Set([...newIds, ...justArrivedAiIds.value])).slice(0, 24)
          setTimeout(() => {
            const drop = new Set(newIds)
            justArrivedAiIds.value = justArrivedAiIds.value.filter((id) => !drop.has(id))
          }, 25_000)
          const wlKeywords = watchlist.value.map((w) => w.label.toLowerCase()).filter(Boolean)
          const hotAi = doc.timeline.find(
            (it) =>
              newIds.includes(it.id) &&
              (it.is_first_hand ||
                it.category_en === 'Funding & Strategy' ||
                wlKeywords.some((k) => it.title.toLowerCase().includes(k))),
          )
          if (hotAi) {
            dispatchImportantNewsNotification({
              id: `ai_${hotAi.id}`,
              title: `${hotAi.company_name} · ${hotAi.is_first_hand ? t('一手发布', '1st-Hand') : t('重要进展', 'AI Drop')}`,
              body: hotAi.title,
              tab: 'ai_progress',
            })
          }
        }
      },
    })
    if (liveWireDoc.value) wireStreamHandle.seedFromDoc(liveWireDoc.value)
    if (aiProgressDoc.value) wireStreamHandle.seedAiFromDoc(aiProgressDoc.value)
  }
  pollTimer = setInterval(() => {
    void checkForNewBatch()
  }, 120_000)
}

watch([siteSettingsLoaded, isPrivateGateLocked], ([loaded, locked]) => {
  if (loaded && !locked && !workbenchStarted) {
    startLiveWorkbench()
  }
})

onMounted(async () => {
  syncHtmlLangAttr()
  applyDarkClass(isDark.value)
  if (typeof window !== 'undefined') {
    const urlParams = new URLSearchParams(window.location.search)
    const refParam = (urlParams.get('ref') || '').trim().toUpperCase()
    if (refParam) {
      pendingRefCode.value = refParam
      try {
        window.localStorage.setItem(PENDING_REF_STORAGE_KEY, refParam)
      } catch {
        // ignore
      }
    }
    const pkPred = (urlParams.get('pred') || '').trim()
    const rawProb = urlParams.get('p')
    const pkProb = rawProb ? Number(rawProb) : 50
    if (pkPred) {
      const clampedProb = Number.isFinite(pkProb) && pkProb >= 5 && pkProb <= 95 ? Math.round(pkProb) : 50
      incomingPkChallenge.value = { predId: pkPred, prob: clampedProb, ref: refParam || undefined }
      activeTab.value = 'calendar'
      scheduleSubView.value = 'predictions'
    }
    const refSectorsRaw = (urlParams.get('ref_sectors') || '').trim()
    const refTickersRaw = (urlParams.get('ref_tickers') || '').trim()
    if (refSectorsRaw || refTickersRaw) {
      const sectors = refSectorsRaw.split(',').map((s) => s.trim()).filter(Boolean).slice(0, 12)
      const tickers = refTickersRaw.split(',').map((s) => s.trim()).filter(Boolean).slice(0, 12)
      if (sectors.length > 0 || tickers.length > 0) {
        sharedPortfolioPreview.value = { sectors, tickers }
        activeTab.value = 'finance'
      }
    }
    if (hasInvalidBriefingUrlParams(window.location.search)) {
      syncUrl(true)
    }
  }
  if (authSession.value) {
    try {
      const res = await apiFetchMe(authSession.value.token)
      if (authSession.value) {
        authSession.value = { token: authSession.value.token, user: res.user }
        saveAuthSession(authSession.value)
        predictionBonusQaQuota.value = Math.max(0, Number(res.prediction_bonus_qa_quota ?? 0))
        if (res.user.avatar) {
          userAvatar.value = saveUserAvatar(res.user.avatar)
        }
        lastSyncedAt.value = res.sync_summary.updated_at
        if (res.sync_summary.has_cloud_state) {
          void pullOrInitCloudState(true)
        }
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : ''
      if (msg.includes('401') || msg.includes('过期') || msg.includes('失效')) {
        clearAuthSession()
        authSession.value = null
        lastSyncedAt.value = null
      }
    }
  }
  await refreshSiteSettingsAndOverrides()
  if (!isPrivateGateLocked.value) {
    startLiveWorkbench()
  }
  clockTimer = setInterval(() => {
    nowMs.value = Date.now()
    const today = getTodayShanghaiDate(nowMs.value)
    if (dailyReading.value.date !== today) {
      dailyReading.value = loadDailyReadingState(nowMs.value)
    }
  }, 10_000)
  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', handleVisibilityChange)
  }
  window.addEventListener('beforeunload', handleVisibilityChange)
  window.addEventListener('popstate', handlePopState)
  window.addEventListener('storage', handleDarkStorageSync)
})

onBeforeUnmount(() => {
  saveDailyReadingState(dailyReading.value)
  syncDailyStateToHistory(dailyReading.value, Date.now())
  wireStreamHandle?.stop()
  stopGlobalQuotesPolling()
  if (clockTimer) clearInterval(clockTimer)
  if (pollTimer) clearInterval(pollTimer)
  if (toastTimer) clearTimeout(toastTimer)
  if (cloudSyncTimer) clearTimeout(cloudSyncTimer)
  if (detailDwellTimer) clearTimeout(detailDwellTimer)
  if (typeof document !== 'undefined') {
    document.removeEventListener('visibilitychange', handleVisibilityChange)
  }
  window.removeEventListener('beforeunload', handleVisibilityChange)
  window.removeEventListener('popstate', handlePopState)
  window.removeEventListener('storage', handleDarkStorageSync)
})
</script>

<template>
  <div
    v-if="!authSession && !siteSettingsLoaded"
    class="min-h-screen flex flex-col items-center justify-center p-4 bg-slate-100 dark:bg-slate-950"
    data-testid="site-gate-loading"
  >
    <div class="flex flex-col items-center gap-3 text-center">
      <div class="w-8 h-8 rounded-full border-2 border-slate-300 dark:border-slate-700 border-t-blue-600 dark:border-t-blue-400 animate-spin" />
      <div class="text-xs font-medium text-slate-500 dark:text-slate-400">
        {{ t('正在校验站点访问状态...', 'Checking workspace access...') }}
      </div>
    </div>
  </div>

  <div
    v-else-if="isPrivateGateLocked"
    class="min-h-screen flex flex-col items-center justify-center p-4 bg-slate-100 dark:bg-slate-950"
    data-testid="private-gate-screen"
  >
    <div class="text-center mb-4 space-y-1">
      <div class="text-lg font-bold text-slate-900 dark:text-white">{{ t('镜信 MirrorBrief · 受控私有空间', 'MirrorBrief · Private Access') }}</div>
      <div class="text-xs text-slate-500 dark:text-slate-400">{{ t('请使用已授权账号登录，或凭管理员发放的一次性邀请码注册进入', 'Sign in with an authorized account or one-time invite code') }}</div>
    </div>
    <AuthModal
      :is-open="true"
      :allow-close="false"
      :access-mode="siteAccessMode"
      :site-settings="siteSettings"
      :initial-ref-code="pendingRefCode"
      :initial-mode="authModalMode"
      :session="null"
      :last-synced-at="null"
      :sync-busy="false"
      @authenticated="handleAuthenticated"
    />
  </div>

  <AppShell
    v-else
    active-page="briefing"
    :active-tab="activeTab"
    :menu-close-nonce="menuCloseNonce"
    :is-dark="isDark"
    :is-history-mode="isHistoryMode"
    :history-display="historyDisplay"
    :bookmark-count="libraryCount"
    :is-refreshing="isRefreshing"
    :show-history-button="false"
    :show-weekly-button="true"
    :show-bookmarks-button="true"
    :show-refresh-button="true"
    :show-auth-button="true"
    :show-search-button="true"
    :show-qa-button="true"
    :search-active="Boolean(searchQuery.trim())"
    :updated-at-iso="activeDoc?.generated_at || liveWireDoc?.updated_at || null"
    :batch-status-tone="batchStatusTone"
    :now-ms="nowMs"
    :auth-user="authSession?.user ?? null"
    :user-avatar="userAvatar"
    :cloud-sync-busy="cloudSyncBusy"
    :hide-mobile-footer="activeTab === 'me'"
    :wide-workspace="true"
    @toggle-dark="toggleDark"
    @open-weekly="switchTab('weekly')"
    @open-bookmarks="openLibraryModal('saved')"
    @refresh="handleManualRefresh"
    @open-auth="openAuthModal"
    @request-logout="requestLogoutWithConfirm"
    @market-color-changed="handleMarketColorChanged"
    @open-search="openSearchOverlay"
    @open-qa="openQaGlobal"
    @open-batch-info="batchInfoModalOpen = true"
    @open-shortcuts="shortcutsModalOpen = true"
    @copy-digest="handleCopyDailyBriefing"
    @request-clear-local="clearConfirmModalOpen = true"
    @scroll-top="scrollToTop"
  >
    <template #mobile-menu-extra="{ close }">
      <div class="flex flex-wrap gap-1.5">
        <button
          type="button"
          @click="close(); switchTab('calendar')"
          class="inline-flex items-center gap-1.5 min-h-[38px] px-3 rounded-xl text-xs font-semibold bg-[#007AFF]/10 text-[#007AFF] dark:text-[#0A84FF]"
        >
          <Calendar class="w-3.5 h-3.5" :stroke-width="1.5" />
          <span>{{ t('日程与前瞻', 'Outlook') }}</span>
        </button>
        <button
          type="button"
          @click="close(); switchTab('tracking')"
          class="inline-flex items-center gap-1.5 min-h-[38px] px-3 rounded-xl text-xs font-semibold bg-[#007AFF]/10 text-[#007AFF] dark:text-[#0A84FF]"
        >
          <GitBranch class="w-3.5 h-3.5" :stroke-width="1.5" />
          <span>{{ t('事件追踪', 'Tracking') }}</span>
        </button>
      </div>
    </template>

    <template #top-banner>
      <!-- Admin-configured global announcement banner -->
      <div
        v-if="showGlobalBanner"
        data-testid="global-site-banner"
        class="text-white px-4 py-2 text-xs sm:text-sm"
        :class="
          siteSettings.site_banner_tone === 'important'
            ? 'bg-[#DC2626]'
            : siteSettings.site_banner_tone === 'warning'
              ? 'bg-amber-600'
              : 'bg-indigo-600'
        "
      >
        <div class="max-w-6xl mx-auto flex items-center justify-between gap-2">
          <div class="flex items-center gap-2 min-w-0">
            <Bell class="w-4 h-4 shrink-0" />
            <span class="font-medium leading-snug">{{ siteSettings.site_banner_text }}</span>
          </div>
          <button
            type="button"
            @click="siteBannerDismissed = true"
            class="w-7 h-7 inline-flex items-center justify-center rounded-md hover:bg-white/15 shrink-0"
            :aria-label="t('关闭通知', 'Dismiss banner')"
          >
            <X class="w-4 h-4" />
          </button>
        </div>
      </div>

      <!-- Live new-batch banner (doesn't auto-scroll user away) -->
      <div
        v-if="pendingNewManifest"
        class="bg-blue-600 text-white px-4 py-2 text-xs sm:text-sm"
      >
        <div class="max-w-6xl mx-auto flex flex-wrap items-center justify-between gap-2">
          <div class="flex items-center gap-2">
            <Bell class="w-4 h-4 shrink-0" />
            <span>
              {{ t('发现新简报批次', 'New briefing batch available:') }} <strong>{{ formatFriendlyBatchId(pendingNewManifest.smart.latest_batch_id) }}</strong>
              （<SmartTime :iso="pendingNewManifest.smart.generated_at" :now-ms="nowMs" />）
            </span>
          </div>
          <button
            type="button"
            @click="loadPendingNewBatch"
            class="px-3 py-1 rounded-md bg-white text-blue-700 font-semibold hover:bg-blue-50 transition-colors"
          >
            {{ t('立即切换并查看新增', 'Load Latest Batch') }}
          </button>
        </div>
      </div>

      <!-- History mode persistent banner -->
      <div
        v-if="isHistoryMode"
        class="bg-indigo-600 text-white px-4 py-2 text-xs sm:text-sm"
      >
        <div class="max-w-6xl mx-auto flex flex-wrap items-center justify-between gap-2">
          <div class="flex items-center gap-2">
            <History class="w-4 h-4 shrink-0" />
            <span>
              {{ t('历史归档快照：', 'Archive Snapshot: ') }}<strong>{{ historyDisplay }}</strong>
              {{ t('（时间与内容均已锁定为该历史批次发布状态）', '(locked to published snapshot)') }}
            </span>
          </div>
          <button
            type="button"
            @click="returnToLatest"
            class="inline-flex items-center gap-1 px-3 py-1 rounded-md bg-white text-indigo-700 font-semibold hover:bg-indigo-50 transition-colors"
          >
            <RotateCcw class="w-3.5 h-3.5" />
            <span>{{ t('返回最新批次', 'Return to Latest') }}</span>
          </button>
        </div>
      </div>
    </template>

    <div
      class="space-y-2.5 sm:space-y-4"
      @touchstart.passive="onPullTouchStart"
      @touchmove.passive="onPullTouchMove"
      @touchend="onPullTouchEnd"
    >
      <!-- Pull-to-refresh subtle iOS/Android indicator (0px height when idle) -->
      <div
        v-if="pullDistance > 8 || isRefreshing"
        class="mobile-pull-indicator items-center justify-center gap-1.5 text-xs text-zinc-500 dark:text-zinc-400 transition-all overflow-hidden"
        :style="{ height: isRefreshing ? '36px' : `${Math.round(pullDistance * 0.58)}px` }"
      >
        <RefreshCw
          class="w-3.5 h-3.5 transition-transform duration-100"
          :class="isRefreshing ? 'animate-spin text-blue-600' : pullDistance >= 54 ? 'text-blue-600' : ''"
          :style="!isRefreshing ? { transform: `rotate(${Math.round(pullDistance * 4)}deg)` } : undefined"
        />
        <span>
          {{
            isRefreshing
              ? t('正在刷新最新批次与行情…', 'Refreshing batch & quotes…')
              : pullDistance >= 54
                ? t('松手立即刷新', 'Release to refresh')
                : t('下拉刷新', 'Pull to refresh')
          }}
        </span>
      </div>
      <!-- Desktop 3-Column / Tablet 2-Column / Mobile 1-Column Responsive Workbench -->
      <div class="md:flex md:items-start md:gap-4 lg:gap-5 xl:gap-6">
        <!-- LEFT RAIL: Fixed Sticky macOS Frosted Navigation (>=768px; expands at >=1024px) -->
        <aside
          class="hidden md:flex desktop-shell-only flex-col justify-between sticky top-[58px] h-[calc(100vh-4.25rem)] shrink-0 rounded-2xl ios-glass p-2 transition-all duration-200"
          :class="sidebarCollapsed ? 'w-16' : 'w-16 lg:w-[208px] xl:w-[216px]'"
          :aria-label="t('工作台导航栏', 'Workbench Sidebar')"
        >
          <div class="space-y-1 overflow-y-auto no-scrollbar">
            <button
              v-for="item in desktopNavItems"
              :key="item.id"
              type="button"
              @click="switchTab(item.id)"
              :aria-current="(activeTab === item.id || (item.id === 'predictions' && activeTab === 'calendar')) ? 'page' : undefined"
              :title="item.label"
              class="ios-tap w-full min-h-[38px] px-2.5 rounded-xl flex items-center gap-2.5 text-[13px] transition-colors"
              :class="[
                sidebarCollapsed ? 'justify-center' : 'justify-center lg:justify-between',
                (activeTab === item.id || (item.id === 'predictions' && activeTab === 'calendar'))
                  ? 'bg-[#007AFF] text-white font-semibold shadow-xs'
                  : 'text-zinc-700 dark:text-zinc-300 hover:bg-black/[0.05] dark:hover:bg-white/[0.07] font-medium',
              ]"
            >
              <span class="inline-flex items-center gap-2.5 min-w-0">
                <component :is="item.icon" class="w-[18px] h-[18px] shrink-0" :stroke-width="1.5" />
                <span v-if="!sidebarCollapsed" class="hidden lg:inline truncate">{{ item.label }}</span>
              </span>
              <span
                v-if="!sidebarCollapsed && item.count > 0"
                class="hidden lg:inline-flex text-[11px] tabular-nums px-1.5 py-0.2 rounded-md"
                :class="(activeTab === item.id || (item.id === 'predictions' && activeTab === 'calendar')) ? 'bg-white/20 text-white' : 'text-zinc-400'"
              >
                {{ item.count }}
              </span>
            </button>

            <div class="my-2 border-t border-black/[0.06] dark:border-white/[0.08]" />

            <button
              type="button"
              @click="switchTab('weekly')"
              :aria-current="activeTab === 'weekly' ? 'page' : undefined"
              :title="t('每周盘点 · 一周大事', 'Weekly Digest')"
              class="ios-tap w-full min-h-[38px] px-2.5 rounded-xl flex items-center gap-2.5 text-[13px] transition-colors"
              :class="[
                sidebarCollapsed ? 'justify-center' : 'justify-center lg:justify-between',
                activeTab === 'weekly'
                  ? 'bg-[#007AFF] text-white font-semibold shadow-xs'
                  : 'text-zinc-700 dark:text-zinc-300 hover:bg-black/[0.05] dark:hover:bg-white/[0.07] font-medium',
              ]"
              data-testid="sidebar-weekly-btn"
            >
              <span class="inline-flex items-center gap-2.5 min-w-0">
                <CalendarRange class="w-[18px] h-[18px] shrink-0" :stroke-width="1.5" />
                <span v-if="!sidebarCollapsed" class="hidden lg:inline truncate">{{ t('每周盘点', 'Weekly') }}</span>
              </span>
              <span
                v-if="!sidebarCollapsed && hasUnreadWeekly && activeTab !== 'weekly'"
                class="hidden lg:inline-flex items-center px-1.5 py-0.2 rounded-full bg-rose-500 text-white text-[10px] font-bold"
              >
                {{ t('新', 'New') }}
              </span>
            </button>

            <button
              type="button"
              @click="openLibraryModal('saved')"
              :title="t('个人阅读库', 'Library')"
              class="ios-tap w-full min-h-[38px] px-2.5 rounded-xl flex items-center gap-2.5 text-[13px] font-medium text-zinc-600 dark:text-zinc-400 hover:bg-black/[0.05] dark:hover:bg-white/[0.07] transition-colors"
              :class="sidebarCollapsed ? 'justify-center' : 'justify-center lg:justify-between'"
            >
              <span class="inline-flex items-center gap-2.5 min-w-0">
                <Bookmark class="w-[18px] h-[18px] shrink-0" :stroke-width="1.5" />
                <span v-if="!sidebarCollapsed" class="hidden lg:inline truncate">{{ t('阅读库', 'Library') }}</span>
              </span>
              <span
                v-if="!sidebarCollapsed && libraryCount > 0"
                class="hidden lg:inline-flex text-[11px] tabular-nums text-zinc-400"
              >
                {{ libraryCount }}
              </span>
            </button>
          </div>

          <!-- Sidebar Utility Links: Help, Feedback, About, Admin -->
          <div
            class="pt-2 border-t border-black/[0.06] dark:border-white/[0.08] flex flex-col gap-0.5 text-[12px]"
            :class="sidebarCollapsed ? 'items-center' : ''"
          >
            <a
              href="./help.html"
              class="flex items-center gap-2 px-2 py-1.5 rounded-lg text-zinc-500 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-white hover:bg-black/[0.05] dark:hover:bg-white/[0.08] transition-colors"
              :title="t('使用帮助', 'Help & Guide')"
            >
              <HelpCircle class="w-3.5 h-3.5 shrink-0" :stroke-width="1.5" />
              <span v-if="!sidebarCollapsed" class="hidden lg:inline truncate">{{ t('使用帮助', 'Help') }}</span>
            </a>
            <button
              type="button"
              @click="openFeedbackFromRail"
              class="flex items-center gap-2 px-2 py-1.5 rounded-lg text-zinc-500 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-white hover:bg-black/[0.05] dark:hover:bg-white/[0.08] transition-colors text-left"
              :title="t('意见反馈', 'Send Feedback')"
            >
              <MessageSquarePlus class="w-3.5 h-3.5 shrink-0" :stroke-width="1.5" />
              <span v-if="!sidebarCollapsed" class="hidden lg:inline truncate">{{ t('意见反馈', 'Feedback') }}</span>
            </button>
            <a
              href="./about.html"
              class="flex items-center gap-2 px-2 py-1.5 rounded-lg text-zinc-500 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-white hover:bg-black/[0.05] dark:hover:bg-white/[0.08] transition-colors"
              :title="t('关于镜信', 'About MirrorBrief')"
            >
              <Info class="w-3.5 h-3.5 shrink-0" :stroke-width="1.5" />
              <span v-if="!sidebarCollapsed" class="hidden lg:inline truncate">{{ t('关于镜信', 'About') }}</span>
            </a>
            <a
              v-if="isAdminRole(authSession?.user?.role)"
              href="./admin.html"
              class="flex items-center gap-2 px-2 py-1.5 rounded-lg text-rose-600 dark:text-rose-400 hover:bg-rose-500/10 transition-colors"
              :title="t('管理员后台', 'Admin Console')"
            >
              <Shield class="w-3.5 h-3.5 shrink-0" :stroke-width="1.5" />
              <span v-if="!sidebarCollapsed" class="hidden lg:inline truncate">{{ t('管理员后台', 'Admin') }}</span>
            </a>
          </div>

          <!-- Sidebar Footer: Collapse Toggle & Shortcuts -->
          <div
            class="pt-1.5 border-t border-black/[0.06] dark:border-white/[0.08] flex items-center gap-1"
            :class="sidebarCollapsed ? 'flex-col justify-center' : 'justify-center lg:justify-between'"
          >
            <button
              type="button"
              @click="sidebarCollapsed = !sidebarCollapsed"
              class="hidden lg:inline-flex items-center justify-center w-9 h-9 rounded-xl text-zinc-400 hover:text-zinc-800 dark:hover:text-white hover:bg-black/[0.05] dark:hover:bg-white/[0.08]"
              :title="sidebarCollapsed ? t('展开侧边栏', 'Expand sidebar') : t('收起侧边栏', 'Collapse sidebar')"
              :aria-label="sidebarCollapsed ? t('展开侧边栏', 'Expand sidebar') : t('收起侧边栏', 'Collapse sidebar')"
            >
              <PanelLeftOpen v-if="sidebarCollapsed" class="w-4 h-4" :stroke-width="1.5" />
              <PanelLeftClose v-else class="w-4 h-4" :stroke-width="1.5" />
            </button>
            <button
              type="button"
              @click="shortcutsModalOpen = true"
              class="hidden md:inline-flex items-center justify-center gap-1 px-2 h-8 rounded-lg text-[11px] text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 hover:bg-black/[0.05] dark:hover:bg-white/[0.08]"
              :title="t('键盘快捷键 (?)', 'Keyboard shortcuts (?)')"
              :aria-label="t('键盘快捷键 (?)', 'Keyboard shortcuts (?)')"
            >
              <Keyboard class="w-3.5 h-3.5" :stroke-width="1.5" />
              <kbd v-if="!sidebarCollapsed" class="hidden lg:inline font-mono">?</kbd>
            </button>
          </div>
        </aside>

        <!-- MIDDLE RAIL: Primary Feed (680~760px optimal reading width on list views) -->
        <div
          class="min-w-0 flex-1 space-y-2.5 ios-fade-in"
          :class="(activeTab === 'today' || activeTab === 'briefing') ? 'xl:max-w-[760px] xl:mx-auto' : ''"
        >
          <!-- 768~1279px Compact Context Drawer Trigger -->
          <div class="hidden md:flex xl:hidden desktop-shell-only items-center justify-end">
            <button
              type="button"
              @click="rightDrawerOpen = true"
              class="ios-tap inline-flex items-center gap-1.5 h-8 px-3 rounded-xl bg-white dark:bg-[#1C1C1E] text-[12px] font-medium text-zinc-600 dark:text-zinc-300 shadow-[0_1px_2px_rgba(0,0,0,0.04)]"
            >
              <PanelRightOpen class="w-3.5 h-3.5 text-[#007AFF]" :stroke-width="1.5" />
              <span>{{ t('行情与上下文', 'Context Rail') }}</span>
            </button>
          </div>

          <!-- Active Search Chip (shown only when a search query is active; full search opens via topbar ⌘K icon) -->
          <div
            v-if="searchQuery.trim() && activeTab !== 'me'"
            class="flex items-center justify-between gap-2 px-3 py-1.5 rounded-xl bg-[#007AFF]/10 text-xs text-[#007AFF] dark:text-[#0A84FF]"
          >
            <button
              type="button"
              @click="openSearchOverlay"
              class="inline-flex items-center gap-1.5 min-w-0 flex-1 text-left truncate font-medium"
            >
              <Search class="w-3.5 h-3.5 shrink-0" :stroke-width="1.5" />
              <span class="truncate">{{ t(`搜索：「${searchQuery}」`, `Search: "${searchQuery}"`) }}</span>
            </button>
            <button
              type="button"
              @click="searchQuery = ''"
              class="w-8 h-8 inline-flex items-center justify-center rounded-lg hover:bg-[#007AFF]/15 shrink-0"
              :aria-label="t('清空搜索', 'Clear search')"
            >
              <X class="w-3.5 h-3.5" :stroke-width="1.5" />
            </button>
          </div>

          <!-- History isolation notice if user enters live modules while browsing a historical snapshot -->
      <div
        v-if="isHistoryMode && !(activeTab === 'today' && todaySection === 'pillars') && activeTab !== 'me'"
        class="rounded-xl bg-indigo-500/10 px-3.5 py-2.5 text-xs text-indigo-800 dark:text-indigo-200 flex flex-wrap items-center justify-between gap-2"
      >
        <span>
          {{
            t(
              `提示：当前处于历史归档模式（${historyDisplay}）。仅「分类简报」显示该历史快照。`,
              `Note: Browsing historical snapshot (${historyDisplay}). Switch to Pillars view to inspect this snapshot.`,
            )
          }}
        </span>
        <div class="flex items-center gap-2 shrink-0">
          <button type="button" @click="switchTab('briefing')" class="px-2.5 py-1 rounded-lg bg-white dark:bg-[#1C1C1E] font-semibold">
            {{ t('查看历史简报', 'View Snapshot') }}
          </button>
          <button type="button" @click="returnToLatest" class="px-2.5 py-1 rounded-lg bg-indigo-600 text-white font-semibold">
            {{ t('返回最新', 'Latest') }}
          </button>
        </div>
      </div>

      <!-- TAB 1: Personalized My Today Workbench -->
      <template v-if="activeTab === 'today'">
        <!-- Cold-Start 30-Second Value Hero (guest-only, compact & permanently dismissible) -->
        <section
          v-if="siteSettings.welcome_hero_enabled !== false && !authSession && !welcomeHeroDismissed"
          class="ios-card border border-[#007AFF]/20 bg-gradient-to-br from-[#007AFF]/[0.06] via-white to-white dark:from-[#0A84FF]/[0.12] dark:via-[#1C1C1E] dark:to-[#1C1C1E] px-3.5 py-3 space-y-2 relative"
          data-testid="welcome-value-hero"
        >
          <button
            type="button"
            @click="dismissWelcomeHero"
            class="absolute top-2.5 right-2.5 w-7 h-7 inline-flex items-center justify-center rounded-full text-zinc-400 hover:bg-black/[0.06] dark:hover:bg-white/[0.08] hover:text-zinc-700 dark:hover:text-zinc-200 transition-colors"
            :aria-label="t('关闭欢迎指引', 'Dismiss welcome banner')"
          >
            <X class="w-4 h-4" :stroke-width="1.5" />
          </button>
          <div class="pr-8 space-y-0.5">
            <h2 class="text-[14px] sm:text-[15px] font-bold text-zinc-950 dark:text-white leading-snug">
              {{ t('3 分钟看透全球大事，直接算清对 A股 / 美股的影响', 'Understand global news in 3 mins — quantify direct A-Share & US equity impact') }}
            </h2>
            <p class="text-[11.5px] text-zinc-500 dark:text-zinc-400">
              {{ t('75+ 路一手信源交叉核验 · 免费 AI 证据问答 · 持仓宏观传导推演', '75+ verified first-hand feeds · Free AI evidence Q&A · Portfolio macro radar') }}
            </p>
          </div>
          <div class="flex flex-wrap items-center gap-1.5 text-[11.5px]">
            <button
              type="button"
              @click="financeInitialPortfolioOnly = false; financeOpenPortfolioNonce += 1; void switchTab('finance')"
              class="ios-tap inline-flex items-center gap-1 px-2.5 min-h-[30px] rounded-full bg-[#007AFF] hover:bg-[#0066D6] text-white font-semibold whitespace-nowrap transition-colors"
              data-testid="hero-pill-portfolio"
            >
              <TrendingUp class="w-3.5 h-3.5 shrink-0" :stroke-width="1.75" />
              <span>{{ t('测测今日大事对我的持仓影响 →', 'Test Portfolio Impact →') }}</span>
            </button>
            <button
              type="button"
              @click="openQaGlobal"
              class="ios-tap inline-flex items-center gap-1 px-2.5 min-h-[30px] rounded-full bg-white dark:bg-[#2C2C2E] border border-[#007AFF]/25 text-[#007AFF] dark:text-[#0A84FF] font-semibold hover:bg-[#007AFF]/10 whitespace-nowrap transition-colors"
              data-testid="hero-pill-qa"
            >
              <Sparkles class="w-3.5 h-3.5 shrink-0" :stroke-width="1.75" />
              <span>{{ t('免费向 AI 证据库提问', 'Ask AI Evidence DB Free') }}</span>
            </button>
            <button
              type="button"
              @click="scheduleSubView = 'predictions'; void loadPredictions(); void switchTab('calendar')"
              class="ios-tap inline-flex items-center gap-1 px-2.5 min-h-[30px] rounded-full bg-[#F2F2F7] dark:bg-[#2C2C2E] text-zinc-700 dark:text-zinc-200 font-semibold hover:bg-black/[0.06] dark:hover:bg-white/[0.1] whitespace-nowrap transition-colors"
              data-testid="hero-pill-predict"
            >
              <Scale class="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400 shrink-0" :stroke-width="1.75" />
              <span>{{ t('押一题本周大事概率', 'Forecast This Week') }}</span>
            </button>
          </div>
        </section>

        <LoadingSkeleton
          v-if="(loadingCat || loadingAllCats) && allLoadedEvents.length === 0"
          variant="cards"
          :count="4"
        />
        <TodayView
          v-else
          v-model:active-section="todaySection"
          :all-events="allLoadedEvents"
          :open-watchlist-nonce="openWatchlistNonce"
          :entities="entities"
          :topics="majorTopics"
          :archived-topics="archivedTopics"
          :selected-topic-id="selectedTopicId"
          :calendar-events="mergedServerCalendarEvents"
          :watchlist="watchlist"
          :muted-set="mutedSet"
          :downweighted-set="downweightedSet"
          :read-later-set="readLaterSet"
          :read-later-events="readLaterEvents"
          :read-later-display-count="readLaterCount"
          :hide-reprints="hideReprints"
          :alert-rules="alertRules"
          :read-ids="readIds"
          :legacy-read-titles="legacyReadTitles"
          :bookmarked-ids="bookmarkedIdSet"
          :previous-seen-ids="previousSeenIds"
          :previous-visited-at="previousVisitedAt"
          :previous-batch-id="previousBatchId"
          :live-wire-items="effectiveLiveWireDoc?.items || []"
          :breaking-highlights="effectiveLiveWireDoc?.breaking_highlights || []"
          :now-ms="nowMs"
          :fresh-bucket="freshBucket"
          :search-query="searchQuery"
          :event-impact-map="financeImpactDoc?.event_impact_map"
          :is-logged-in="Boolean(authSession)"
          :today-read-count="dailyReading.readEventIdsToday.length"
          :saved-note-map="savedNoteMap"
          :research-notes="researchNotes"
          :comments-map="commentsByCatForCards"
          :highlighted-event-id="highlightedEventId"
          :loading="loadingCat || loadingAllCats"
          :topics-loading="topicsLoading || !topicsLoaded"
          @add-watchlist="handleAddWatchlist"
          @remove-watchlist="handleRemoveWatchlist"
          @apply-preset="handleApplyWatchlistPreset"
          @open-onboarding="onboardingModalOpen = true"
          @open-weekly-report="weeklyReportOpen = true"
          @open-notes="openLibraryModal('notes')"
          @save-note="handleSaveCardNote"
          @toggle-mute-event="toggleSetKey('muted', $event)"
          @unmute-all="handleUnmuteAll"
          @toggle-downweight-event="toggleSetKey('downweighted', $event)"
          @toggle-read-later="toggleSetKey('read_later', $event)"
          @toggle-hide-reprints="handleToggleHideReprints"
          @update-alert-rules="handleUpdateAlertRules"
          @update:fresh-bucket="freshBucket = $event"
          @toggle-read="handleToggleRead"
          @mark-read="handleMarkSingleRead"
          @mark-all-read="handleMarkEventsRead"
          @toggle-bookmark="handleToggleBookmark"
          @copy-link="handleCopyLink"
          @select-entity="handleOpenEntityByName"
          @open-storyline="handleOpenStoryline"
          @open-qa="openQaForEvent"
          @open-detail="openEventInDetailReader"
          @open-qa-topic="openQaForTopic"
          @jump-to-event="handleJumpToTodayEvent"
          @jump-event-id="handleJumpToEventId"
          @switch-tab="switchTab"
          @clear-search="clearFilters"
          @open-auth="openAuthModal()"
          @open-echo-share-card="openEchoChamberShareCard"
          @share-poster="openEventBriefShareCard"
        >
          <template #pillars>
            <div class="space-y-3">
              <div
                v-if="returnToFinanceTab"
                class="rounded-xl bg-[#007AFF]/10 px-3.5 py-2 flex items-center justify-between gap-2 text-xs"
              >
                <span class="text-[#007AFF] dark:text-[#0A84FF] font-medium">
                  {{ t('已定位到对应原简报', 'Jumped to matching briefing') }}
                </span>
                <button
                  type="button"
                  @click="returnToFinanceTab = false; switchTab('finance')"
                  class="px-3 py-1 rounded-lg bg-[#007AFF] text-white font-semibold shrink-0"
                >
                  {{ t('← 返回股市', '← Markets') }}
                </button>
              </div>

              <!-- 4 Category Tabs + Unread & Filter Bar -->
              <section
                class="space-y-2.5"
                :aria-label="t('分类与检索控制', 'Category and Filter Controls')"
                @touchstart.passive="onBriefingTouchStart"
                @touchend.passive="onBriefingTouchEnd"
              >
                <div class="flex flex-wrap items-center justify-between gap-2">
                  <div class="ios-segmented overflow-x-auto no-scrollbar max-w-full" role="tablist" :aria-label="t('新闻分类', 'News Categories')">
                    <button
                      v-for="cat in CATEGORIES"
                      :key="cat.id"
                      type="button"
                      role="tab"
                      :aria-selected="activeCategory === cat.id"
                      @click="switchCategory(cat.id)"
                      class="ios-segmented-btn min-h-[34px] px-3 gap-1.5"
                      :class="
                        activeCategory === cat.id
                          ? 'ios-segmented-btn-active'
                          : 'text-zinc-600 dark:text-zinc-400'
                      "
                    >
                      <span class="w-1.5 h-1.5 rounded-full shrink-0" :class="cat.accentDotClass" />
                      <span>{{ appLang === 'en' ? cat.shortNameEn : cat.shortName }}</span>
                      <span
                        v-if="docsByCat[cat.id] || (!isHistoryMode && manifest?.smart.categories[cat.id])"
                        class="text-[11px] opacity-65 tabular-nums"
                      >
                        {{ docsByCat[cat.id] ? categoryEventCounts[cat.id] : manifest?.smart.categories[cat.id]?.item_count }}
                      </span>
                    </button>
                  </div>

                  <div class="flex items-center gap-1.5 text-xs">
                    <button
                      type="button"
                      @click="onlyBlindspot = !onlyBlindspot; if (onlyBlindspot) { searchScope = 'all'; void ensureAllCategoriesLoaded() }"
                      :aria-pressed="onlyBlindspot"
                      class="inline-flex items-center gap-1 px-2.5 h-9 rounded-xl font-medium whitespace-nowrap shrink-0 transition-colors"
                      :class="
                        onlyBlindspot
                          ? 'bg-indigo-600 text-white'
                          : 'bg-white dark:bg-[#1C1C1E] text-indigo-700 dark:text-indigo-300'
                      "
                    >
                      <Lightbulb class="w-3.5 h-3.5 shrink-0" :stroke-width="1.75" />
                      <span>{{ t('盲区高热未读', 'Blindspot Unread') }}</span>
                    </button>

                    <button
                      type="button"
                      @click="onlyUnreadOrNew = !onlyUnreadOrNew"
                      :aria-pressed="onlyUnreadOrNew"
                      class="inline-flex items-center gap-1 px-2.5 h-9 rounded-xl font-medium whitespace-nowrap shrink-0 transition-colors"
                      :class="
                        onlyUnreadOrNew
                          ? 'bg-[#007AFF] text-white'
                          : 'bg-white dark:bg-[#1C1C1E] text-zinc-700 dark:text-zinc-200'
                      "
                    >
                      <Sparkles class="w-3.5 h-3.5 shrink-0" :stroke-width="1.5" />
                      <span>{{ t(`未读 (${newOrUnreadCountInActive})`, `Unread (${newOrUnreadCountInActive})`) }}</span>
                    </button>

                    <button
                      v-if="filteredEvents.length > 0"
                      type="button"
                      @click="markVisibleAsRead"
                      class="inline-flex items-center gap-1 px-2.5 h-9 rounded-xl bg-white dark:bg-[#1C1C1E] text-zinc-600 dark:text-zinc-300 whitespace-nowrap shrink-0 transition-colors"
                      :title="t('全标已读', 'Mark all read')"
                    >
                      <CheckCheck class="w-3.5 h-3.5 shrink-0" :stroke-width="1.5" />
                      <span>{{ t('全已读', 'Read All') }}</span>
                    </button>
                  </div>
                </div>

                <!-- Slim Select Controls (Fixed appearance-none height on mobile WebView) -->
                <div class="ios-card p-2.5 space-y-2">
                  <div class="flex flex-wrap items-center gap-2">
                    <div class="ios-segmented shrink-0">
                      <button
                        type="button"
                        @click="setPillarDateRange('today')"
                        class="ios-segmented-btn min-h-[30px] px-2.5 text-xs"
                        :class="pillarDateRange === 'today' && !isHistoryMode ? 'ios-segmented-btn-active' : 'text-zinc-600 dark:text-zinc-400'"
                      >
                        {{ t('今天', 'Today') }}
                      </button>
                      <button
                        type="button"
                        @click="setPillarDateRange('3d')"
                        class="ios-segmented-btn min-h-[30px] px-2.5 text-xs"
                        :class="pillarDateRange === '3d' ? 'ios-segmented-btn-active' : 'text-zinc-600 dark:text-zinc-400'"
                      >
                        {{ t('近3天', '3D') }}{{ pillarRangeLoading && pillarDateRange === '3d' ? '...' : '' }}
                      </button>
                      <button
                        type="button"
                        @click="setPillarDateRange('7d')"
                        class="ios-segmented-btn min-h-[30px] px-2.5 text-xs"
                        :class="pillarDateRange === '7d' ? 'ios-segmented-btn-active' : 'text-zinc-600 dark:text-zinc-400'"
                      >
                        {{ t('近7天', '7D') }}{{ pillarRangeLoading && pillarDateRange === '7d' ? '...' : '' }}
                      </button>
                    </div>

                    <button
                      type="button"
                      @click="togglePillarCalendar"
                      class="inline-flex items-center gap-1 px-2.5 h-[32px] rounded-xl text-xs font-medium shrink-0 transition-colors"
                      :class="
                        pillarCalendarOpen || isHistoryMode
                          ? 'bg-[#007AFF]/12 text-[#007AFF] dark:text-[#0A84FF]'
                          : 'bg-[#F5F5F7] dark:bg-[#2C2C2E] text-zinc-700 dark:text-zinc-200'
                      "
                      :aria-expanded="pillarCalendarOpen"
                    >
                      <Calendar class="w-3.5 h-3.5 shrink-0" :stroke-width="1.5" />
                      <span>{{ isHistoryMode ? historyDisplay : t('按日期', 'By Date') }}</span>
                    </button>

                    <button
                      v-if="isHistoryMode"
                      type="button"
                      @click="returnToLatest"
                      class="inline-flex items-center gap-1 px-2.5 h-[32px] rounded-xl bg-indigo-600 text-white text-xs font-semibold shrink-0"
                    >
                      {{ t('返回今日', 'Back to Today') }}
                    </button>

                    <div class="ios-segmented shrink-0">
                      <button
                        type="button"
                        @click="searchScope = 'current'"
                        class="ios-segmented-btn min-h-[30px] px-2.5 text-xs"
                        :class="searchScope === 'current' ? 'ios-segmented-btn-active' : 'text-zinc-600 dark:text-zinc-400'"
                      >
                        {{ t('当前板块', 'Current') }}
                      </button>
                      <button
                        type="button"
                        @click="searchScope = 'all'"
                        class="ios-segmented-btn min-h-[30px] px-2.5 text-xs"
                        :class="searchScope === 'all' ? 'ios-segmented-btn-active' : 'text-zinc-600 dark:text-zinc-400'"
                      >
                        {{ t('全板块', 'All 4') }}{{ loadingAllCats ? '...' : '' }}
                      </button>
                    </div>

                    <div class="relative inline-flex items-center shrink-0 h-9 pl-2.5 pr-7 rounded-xl bg-[#F5F5F7] dark:bg-[#2C2C2E] text-xs text-zinc-700 dark:text-zinc-200 focus-within:ring-2 focus-within:ring-[#007AFF]/40">
                      <span class="pointer-events-none whitespace-nowrap">{{ evidenceFilterLabel }}</span>
                      <ChevronDown class="w-3.5 h-3.5 text-zinc-400 pointer-events-none absolute right-2" />
                      <select
                        v-model="evidenceFilter"
                        :aria-label="t('按依据状态筛选', 'Filter by evidence status')"
                        class="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                      >
                        <option value="all">{{ t('全部可信度', 'All Evidence') }}</option>
                        <option value="official_confirmed">{{ t('一手官方证实', 'Official') }}</option>
                        <option value="multi_source">{{ t('多源交叉印证', 'Multi-Source') }}</option>
                        <option value="single_source">{{ t('单一来源', 'Single Source') }}</option>
                        <option value="needs_verification">{{ t('待核实线索', 'Unverified') }}</option>
                      </select>
                    </div>

                    <div class="relative inline-flex items-center shrink-0 h-9 pl-2.5 pr-7 rounded-xl bg-[#F5F5F7] dark:bg-[#2C2C2E] text-xs text-zinc-700 dark:text-zinc-200 focus-within:ring-2 focus-within:ring-[#007AFF]/40">
                      <span class="pointer-events-none whitespace-nowrap">{{ briefingSortLabel }}</span>
                      <ChevronDown class="w-3.5 h-3.5 text-zinc-400 pointer-events-none absolute right-2" />
                      <select
                        v-model="briefingSortBy"
                        :aria-label="t('简报排序方式', 'Sort briefings')"
                        class="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                      >
                        <option value="latest">{{ t('最新时间', 'Latest') }}</option>
                        <option value="credibility">{{ t('可信度最高', 'Credibility') }}</option>
                        <option value="relevance">{{ t('关注相关', 'Watchlist') }}</option>
                      </select>
                    </div>

                    <div class="relative inline-flex items-center shrink-0 max-w-[165px] h-9 pl-2.5 pr-7 rounded-xl bg-[#F5F5F7] dark:bg-[#2C2C2E] text-xs text-zinc-700 dark:text-zinc-200 focus-within:ring-2 focus-within:ring-[#007AFF]/40">
                      <span class="pointer-events-none truncate">{{ sourceFilterLabel }}</span>
                      <ChevronDown class="w-3.5 h-3.5 text-zinc-400 pointer-events-none absolute right-2" />
                      <select
                        v-model="sourceFilter"
                        :aria-label="t('按来源平台筛选', 'Filter by publisher')"
                        class="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                      >
                        <option value="all">{{ t(`全部媒体 (${sourceFilterOptions.length})`, `All Sources (${sourceFilterOptions.length})`) }}</option>
                        <option
                          v-for="opt in sourceFilterOptions"
                          :key="opt.id"
                          :value="opt.id"
                        >
                          {{ opt.name }} ({{ opt.count }})
                        </option>
                      </select>
                    </div>
                  </div>

                  <div
                    v-if="pillarCalendarOpen"
                    class="rounded-xl bg-[#F5F5F7] dark:bg-[#2C2C2E] p-2.5 space-y-2 text-xs border border-black/[0.05] dark:border-white/[0.07]"
                  >
                    <div class="flex flex-wrap items-center justify-between gap-2">
                      <span class="font-semibold text-zinc-700 dark:text-zinc-200">
                        {{ t('按历史日期切换快照', 'Browse Historical Snapshot by Date') }}
                      </span>
                      <div class="flex items-center gap-1.5">
                        <input
                          v-model="pillarSelectedDate"
                          type="date"
                          :min="availableHistoryDates[availableHistoryDates.length - 1] || ''"
                          :max="availableHistoryDates[0] || ''"
                          :aria-label="t('选择日期', 'Pick date')"
                          class="h-8 px-2 rounded-lg bg-white dark:bg-zinc-900 border border-black/[0.08] dark:border-white/[0.1] text-xs text-zinc-900 dark:text-white"
                        />
                        <button
                          v-if="isHistoryMode"
                          type="button"
                          @click="returnToLatest"
                          class="h-8 px-2.5 rounded-lg bg-[#007AFF] text-white font-semibold"
                        >
                          {{ t('回到最新', 'Latest') }}
                        </button>
                      </div>
                    </div>

                    <div v-if="historyLoading" class="text-[11px] text-zinc-500">
                      {{ t('加载可用日期索引中…', 'Loading available archive dates…') }}
                    </div>
                    <template v-else-if="availableHistoryDates.length > 0">
                      <div class="flex flex-wrap gap-1.5">
                        <button
                          v-for="dt in availableHistoryDates.slice(0, 10)"
                          :key="dt"
                          type="button"
                          @click="pillarSelectedDate = dt"
                          class="px-2 py-1 rounded-lg text-[11px] font-medium tabular-nums transition-colors"
                          :class="
                            pillarSelectedDate === dt
                              ? 'bg-[#007AFF] text-white'
                              : 'bg-white dark:bg-zinc-900 text-zinc-700 dark:text-zinc-200 hover:bg-black/[0.04]'
                          "
                        >
                          {{ dt }}
                        </button>
                      </div>
                      <div v-if="entriesForSelectedPillarDate.length > 0" class="flex flex-wrap items-center gap-1.5 pt-1 border-t border-black/[0.06] dark:border-white/[0.08]">
                        <span class="text-[11px] text-zinc-500">{{ t('当日批次：', 'Batches:') }}</span>
                        <button
                          v-for="entry in entriesForSelectedPillarDate.slice(0, 12)"
                          :key="entry.path"
                          type="button"
                          @click="selectHistoryEntry(entry)"
                          class="px-2 py-1 rounded-lg text-[11px] font-mono transition-colors"
                          :class="
                            historyPath?.replace(/\/+$/, '') === entry.path.replace(/\/+$/, '')
                              ? 'bg-indigo-600 text-white font-semibold'
                              : 'bg-white dark:bg-zinc-900 text-zinc-700 dark:text-zinc-200 hover:bg-indigo-50 dark:hover:bg-indigo-950/40'
                          "
                        >
                          {{ formatShanghaiHhMm(entry.generated_at || entry.published_at || entry.fetched_at) || entry.display }}
                        </button>
                      </div>
                      <div v-else-if="pillarSelectedDate" class="text-[11px] text-zinc-400">
                        {{ t(`日期 ${pillarSelectedDate} 暂无历史快照`, `No snapshot archived on ${pillarSelectedDate}`) }}
                      </div>
                    </template>
                  </div>

                  <div
                    v-if="topEntities.length > 0 || searchQuery || sourceFilter !== 'all' || evidenceFilter !== 'all' || onlyUnreadOrNew || selectedEntity"
                    class="flex flex-nowrap sm:flex-wrap items-center gap-1.5 overflow-x-auto no-scrollbar text-xs"
                  >
                    <button
                      v-for="item in topEntities"
                      :key="item.entity"
                      type="button"
                      @click="handleSelectEntity(item.entity)"
                      class="px-2.5 min-h-[30px] rounded-lg whitespace-nowrap shrink-0 transition-colors"
                      :class="
                        selectedEntity === item.entity
                          ? 'bg-[#007AFF] text-white'
                          : 'bg-[#F5F5F7] text-zinc-700 dark:bg-[#2C2C2E] dark:text-zinc-300'
                      "
                    >
                      {{ translateEntityName(item.entity) }}
                    </button>

                    <button
                      v-if="selectedEntity"
                      type="button"
                      @click="handleOpenEntityByName(selectedEntity)"
                      class="px-2.5 min-h-[30px] rounded-lg bg-[#007AFF]/10 text-[#007AFF] dark:text-[#0A84FF] font-medium whitespace-nowrap shrink-0"
                    >
                      {{ t(`查看「${selectedEntity}」档案 →`, `Inspect "${translateEntityName(selectedEntity)}" →`) }}
                    </button>

                    <button
                      v-if="searchQuery || sourceFilter !== 'all' || evidenceFilter !== 'all' || onlyUnreadOrNew || onlyBlindspot || selectedEntity"
                      type="button"
                      @click="clearFilters"
                      class="ml-auto px-2 min-h-[30px] text-[#007AFF] dark:text-[#0A84FF] font-medium whitespace-nowrap shrink-0"
                    >
                      {{ t('重置', 'Reset') }}
                    </button>
                  </div>
                </div>
              </section>

              <LoadingSkeleton v-if="loadingCat && !activeDoc" variant="cards" :count="4" />

              <div
                v-else-if="activeDoc?.missing"
                class="ios-card p-6 text-center space-y-3"
              >
                <AlertCircle class="w-7 h-7 text-rose-500 mx-auto" />
                <div class="text-sm font-semibold text-zinc-900 dark:text-white">
                  {{ t('该分类在本批次暂不可用', 'Category Unavailable in This Batch') }}
                </div>
                <button
                  type="button"
                  @click="handleManualRefresh"
                  class="px-4 py-2 rounded-xl bg-[#007AFF] text-white text-xs font-semibold"
                >
                  {{ t('重试加载', 'Retry') }}
                </button>
              </div>

              <template v-else-if="activeDoc">
                <EmptySearchState
                  v-if="verifiedBriefingEvents.length === 0 && unverifiedBriefingEvents.length === 0"
                  :query="searchQuery"
                  :has-extra-filters="sourceFilter !== 'all' || evidenceFilter !== 'all' || onlyUnreadOrNew || onlyBlindspot || Boolean(selectedEntity)"
                  @clear-query="searchQuery = ''"
                  @clear-filters-only="clearFilters"
                  @reset="clearFilters"
                />

                <section v-if="verifiedBriefingEvents.length > 0" class="space-y-2.5" :aria-label="t('重点新闻列表', 'Briefing Events Feed')">
                  <div class="ios-card divide-y divide-black/[0.06] dark:divide-white/[0.08] overflow-hidden">
                    <EventCard
                      v-for="ev in pagedBriefingEvents.visible"
                      :key="ev.event_id"
                      :event="ev"
                      :now-ms="nowMs"
                      :grouped="true"
                      :is-read="checkIsRead(ev)"
                      :market-impact="financeImpactDoc?.event_impact_map?.[ev.event_id] || null"
                      :is-bookmarked="checkIsBookmarked(ev)"
                      :is-new-since-visit="checkIsNew(ev)"
                      :is-highlighted="highlightedEventId === ev.event_id"
                      :force-expand-perspectives="highlightedEventId === ev.event_id"
                      :saved-note="savedNoteMap[ev.event_id] || ''"
                      :matching-note-count="countMatchingNotesForSubject(researchNotes, { eventId: ev.event_id, storylineId: ev.storyline_id, entityIds: ev.entity_ids, entities: ev.entities })"
                      :perspectives="commentsByCatForCards[ev.category] || []"
                      :is-read-later="readLaterSet.has(ev.event_id)"
                      :downweighted="downweightedSet.has(ev.event_id)"
                      :show-moderation-actions="true"
                      @toggle-read="handleToggleRead"
                      @mark-read="handleMarkSingleRead"
                      @open-notes="openLibraryModal('notes')"
                      @toggle-bookmark="handleToggleBookmark"
                      @copy-link="handleCopyLink"
                      @select-entity="handleOpenEntityByName"
                      @open-prev-batch="(pbId) => openBatchDiffModal(pbId, ev)"
                      @open-storyline="handleOpenStoryline"
                      @open-qa="openQaForEvent"
                      @open-detail="openEventInDetailReader"
                      @save-note="handleSaveCardNote"
                      @toggle-read-later="toggleSetKey('read_later', $event)"
                      @toggle-downweight="toggleSetKey('downweighted', $event)"
                      @toggle-mute="toggleSetKey('muted', $event)"
                      @share-poster="openEventBriefShareCard"
                    />
                  </div>
                  <div v-if="pagedBriefingEvents.hasMore" class="pt-1 text-center">
                    <button
                      type="button"
                      @click="briefingVisibleLimit += DEFAULT_PAGE_SIZE"
                      class="min-h-[42px] px-5 rounded-xl bg-white dark:bg-[#1C1C1E] text-xs font-semibold text-zinc-700 dark:text-zinc-200 shadow-[0_1px_2px_rgba(0,0,0,0.04)]"
                    >
                      {{ t(`加载更多 (${pagedBriefingEvents.remaining})`, `Load More (${pagedBriefingEvents.remaining})`) }}
                    </button>
                  </div>
                </section>

                <details
                  v-if="unverifiedBriefingEvents.length > 0"
                  class="ios-card px-3.5 py-2.5"
                >
                  <summary class="cursor-pointer select-none flex items-center justify-between text-xs font-semibold text-amber-700 dark:text-amber-300">
                    <span>{{ t(`待核实线索 (${unverifiedBriefingEvents.length})`, `Pending Verification (${unverifiedBriefingEvents.length})`) }}</span>
                    <ChevronDown class="w-4 h-4" />
                  </summary>
                  <div class="mt-2.5 divide-y divide-black/[0.06] dark:divide-white/[0.08] overflow-hidden rounded-xl">
                    <EventCard
                      v-for="ev in unverifiedBriefingEvents"
                      :key="`unv-${ev.event_id}`"
                      :event="ev"
                      :now-ms="nowMs"
                      :grouped="true"
                      :is-read="checkIsRead(ev)"
                      :market-impact="financeImpactDoc?.event_impact_map?.[ev.event_id] || null"
                      :is-bookmarked="checkIsBookmarked(ev)"
                      :is-new-since-visit="checkIsNew(ev)"
                      :is-highlighted="highlightedEventId === ev.event_id"
                      :force-expand-perspectives="highlightedEventId === ev.event_id"
                      :saved-note="savedNoteMap[ev.event_id] || ''"
                      :matching-note-count="countMatchingNotesForSubject(researchNotes, { eventId: ev.event_id, storylineId: ev.storyline_id, entityIds: ev.entity_ids, entities: ev.entities })"
                      :perspectives="commentsByCatForCards[ev.category] || []"
                      :is-read-later="readLaterSet.has(ev.event_id)"
                      :downweighted="downweightedSet.has(ev.event_id)"
                      :show-moderation-actions="true"
                      @toggle-read="handleToggleRead"
                      @mark-read="handleMarkSingleRead"
                      @open-notes="openLibraryModal('notes')"
                      @toggle-bookmark="handleToggleBookmark"
                      @copy-link="handleCopyLink"
                      @select-entity="handleOpenEntityByName"
                      @open-prev-batch="(pbId) => openBatchDiffModal(pbId, ev)"
                      @open-storyline="handleOpenStoryline"
                      @open-qa="openQaForEvent"
                      @open-detail="openEventInDetailReader"
                      @save-note="handleSaveCardNote"
                      @toggle-read-later="toggleSetKey('read_later', $event)"
                      @toggle-downweight="toggleSetKey('downweighted', $event)"
                      @toggle-mute="toggleSetKey('muted', $event)"
                      @share-poster="openEventBriefShareCard"
                    />
                  </div>
                </details>

                <SimulatedPerspectives
                  v-if="showSimulatedPerspectives"
                  :is-open="perspectivesOpen"
                  :loading="perspectivesLoading"
                  :doc="activeCommentsDoc"
                  :expected-batch-id="activeDoc.batch_id"
                  @toggle="togglePerspectives"
                />
              </template>
            </div>
          </template>
        </TodayView>
      </template>

      <!-- TAB LIVE WIRE: 7x24 Real-Time Flash Stream -->
      <template v-else-if="activeTab === 'wire'">
        <LiveWireView
          :doc="effectiveLiveWireDoc"
          :search-query="searchQuery"
          :watchlist="watchlist"
          :now-ms="nowMs"
          :loading="!liveWireLoaded"
          :transport-mode="wireTransportMode"
          :just-arrived-ids="justArrivedWireIds"
          @clear-search="clearFilters"
        />
      </template>

      <!-- TAB AI FRONTIER: Consolidated AI Tracker + Tech Tools Library -->
      <template v-else-if="activeTab === 'ai_progress'">
        <div class="space-y-3">
          <div class="ios-segmented overflow-x-auto no-scrollbar">
            <button
              type="button"
              @click="aiSubView = 'tracker'"
              class="ios-segmented-btn min-h-[34px] px-3 whitespace-nowrap"
              :class="aiSubView === 'tracker' ? 'ios-segmented-btn-active' : 'text-zinc-600 dark:text-zinc-400'"
            >
              {{ t('机构动态与演进谱系', 'Labs & Lineage') }}
            </button>
            <button
              type="button"
              @click="aiSubView = 'tools'; void loadTools()"
              class="ios-segmented-btn min-h-[34px] px-3 whitespace-nowrap"
              :class="aiSubView === 'tools' ? 'ios-segmented-btn-active' : 'text-zinc-600 dark:text-zinc-400'"
            >
              {{ t(`高星开源工具库 (${techTools.length || manifest?.v3?.tech_tools_count || 0})`, `Tools (${techTools.length || manifest?.v3?.tech_tools_count || 0})`) }}
            </button>
          </div>

          <template v-if="aiSubView === 'tracker'">
            <LoadingSkeleton v-if="!aiProgressLoaded && !aiProgressDoc" variant="grid" :count="6" />
            <AiProgressView
              v-else
              :doc="aiProgressDoc"
              :manifest="manifest"
              :search-query="searchQuery"
              :now-ms="nowMs"
              :transport-mode="wireTransportMode"
              :just-arrived-ids="justArrivedAiIds"
              @jump-event-id="handleJumpToEventId"
              @mark-read-event-id="handleMarkSingleRead"
              @clear-search="clearFilters"
            />
          </template>
          <template v-else>
            <LoadingSkeleton v-if="toolsLoading && techTools.length === 0" variant="grid" :count="6" />
            <TechToolsView
              v-else
              :tools="techTools"
              :tool-states="toolStates"
              :global-search-query="searchQuery"
              :now-ms="nowMs"
              @update-tool-state="handleUpdateToolState"
              @clear-search="clearFilters"
            />
          </template>
        </div>
      </template>

      <!-- TAB FINANCE IMPACT: A-Share / US-Share Transmission & Scenario Simulator -->
      <template v-else-if="activeTab === 'finance'">
        <FinanceImpactView
          :doc="financeImpactDoc"
          :search-query="searchQuery"
          :now-ms="nowMs"
          :loading="!financeImpactLoaded"
          :initial-portfolio-only="financeInitialPortfolioOnly"
          :open-portfolio-nonce="financeOpenPortfolioNonce"
          :research-notes="researchNotes"
          :shared-portfolio-preview="sharedPortfolioPreview"
          @jump-event-id="handleJumpToEventId"
          @mark-read-event-id="handleMarkSingleRead"
          @open-notes="openLibraryModal('notes')"
          @clear-search="clearFilters"
          @clear-shared-portfolio="clearSharedPortfolioPreview"
          @portfolio-changed="handlePortfolioChanged"
          @open-portfolio-share-card="openPortfolioShareCard"
        />
      </template>

      <!-- TAB TRACKING: Storyline Tracking & Cross-Batch Fact Diffs -->
      <template v-else-if="activeTab === 'tracking'">
        <div class="space-y-3">
          <div class="mobile-quick-entry-strip items-center justify-between gap-2">
            <button
              type="button"
              @click="handleSecondaryBack()"
              class="mobile-pressable ios-tap inline-flex items-center gap-1.5 min-h-[38px] px-3 rounded-xl bg-white dark:bg-[#1C1C1E] text-xs font-semibold text-zinc-700 dark:text-zinc-200 shadow-[0_1px_2px_rgba(0,0,0,0.04)]"
            >
              <ArrowLeft class="w-3.5 h-3.5" :stroke-width="1.5" />
              <span>{{ t('返回', 'Back') }}</span>
            </button>
          </div>
          <TrackingView
            :storylines="storylinesMap"
            :selected-storyline-id="selectedStorylineId"
            :search-query="searchQuery"
            :watchlist="watchlist"
            :muted-set="mutedSet"
            :now-ms="nowMs"
            :loading="storylinesLoading || !storylinesLoaded"
            @select-storyline="handleSelectStoryline"
            @select-entity="handleOpenEntityByName"
            @open-qa-storyline="openQaForStoryline"
            @back-to-today="switchTab('today')"
            @clear-search="clearFilters"
          />
        </div>
      </template>

      <!-- TAB SCHEDULE & OUTLOOK: Consolidated Calendar + Predictions -->
      <template v-else-if="activeTab === 'calendar'">
        <div class="space-y-3">
          <div class="mobile-quick-entry-strip items-center justify-between gap-2">
            <button
              type="button"
              @click="handleSecondaryBack()"
              class="mobile-pressable ios-tap inline-flex items-center gap-1.5 min-h-[38px] px-3 rounded-xl bg-white dark:bg-[#1C1C1E] text-xs font-semibold text-zinc-700 dark:text-zinc-200 shadow-[0_1px_2px_rgba(0,0,0,0.04)]"
            >
              <ArrowLeft class="w-3.5 h-3.5" :stroke-width="1.5" />
              <span>{{ t('返回', 'Back') }}</span>
            </button>
          </div>
          <div class="ios-segmented">
            <button
              type="button"
              @click="scheduleSubView = 'predictions'; void loadPredictions()"
              class="ios-segmented-btn min-h-[34px] px-3.5"
              :class="scheduleSubView === 'predictions' ? 'ios-segmented-btn-active' : 'text-zinc-600 dark:text-zinc-400'"
            >
              {{ t(`前瞻验证 (${mergedPredictions.length})`, `Predictions (${mergedPredictions.length})`) }}
            </button>
            <button
              type="button"
              @click="scheduleSubView = 'calendar'"
              class="ios-segmented-btn min-h-[34px] px-3.5"
              :class="scheduleSubView === 'calendar' ? 'ios-segmented-btn-active' : 'text-zinc-600 dark:text-zinc-400'"
            >
              {{ t(`催化日程 (${calendarTabTotalCount})`, `Calendar (${calendarTabTotalCount})`) }}
            </button>
          </div>

          <template v-if="scheduleSubView === 'calendar'">
            <LoadingSkeleton v-if="calendarLoading && serverCalendarEvents.length === 0" variant="list" :count="6" />
            <CalendarView
              v-else
              :events="mergedServerCalendarEvents"
              :custom-events="customCatalysts"
              :watchlist="watchlist"
              :search-query="searchQuery"
              :now-ms="nowMs"
              @add-custom-catalyst="handleAddCustomCatalyst"
              @update-custom-catalyst="handleUpdateCustomCatalyst"
              @delete-custom-catalyst="handleDeleteCustomCatalyst"
              @save-catalyst-actual="handleSaveCatalystActual"
              @clear-catalyst-actual="handleClearCatalystActual"
              @open-storyline="handleOpenStoryline"
              @jump-event-id="handleJumpToEventId"
              @clear-search="clearFilters"
            />
          </template>
          <template v-else>
            <LoadingSkeleton v-if="predictionsLoading && seedPredictions.length === 0" variant="cards" :count="4" />
            <PredictionsView
              v-else
              :predictions="mergedPredictions"
              :public-note="predictionsNote"
              :search-query="searchQuery"
              :local-prediction-ids="localPredictionIdSet"
              :stances="predictionStances"
              :crowd-stats="crowdStatsMap"
              :crowd-min-unlock="siteSettings.crowd_vote_min_unlock ?? 3"
              :guest-staged-votes="guestStagedVotes"
              :incoming-pk-challenge="incomingPkChallenge"
              :arena-profile="arenaProfile"
              :arena-leaderboard="arenaLeaderboard"
              :allowed-reason-tags="arenaReasonTags"
              :prediction-proposals-enabled="siteSettings.prediction_proposals_enabled !== false"
              :season-key="arenaSeasonKey"
              :all-events="allLoadedEvents"
              :live-wire-items="effectiveLiveWireDoc?.items || []"
              :finance-impacts="financeImpactDoc?.event_impacts || []"
              :is-logged-in="Boolean(authSession)"
              :is-admin="isAdminRole(authSession?.user?.role)"
              :now-ms="nowMs"
              @create-prediction="handleCreatePrediction"
              @submit-proposal="handleSubmitPredictionProposal"
              @settle-prediction="handleSettlePrediction"
              @set-prediction-stance="handleSetPredictionStance"
              @vote-crowd="handleVotePredictionCrowd"
              @open-share-pk="openPredictionPkShareCard"
              @open-qa-prediction="openQaForPrediction"
              @jump-event="(ev) => { focusedEventModalEvent = ev }"
              @open-finance-search="(kw) => { if (kw) searchQuery = kw; void switchTab('finance') }"
              @dismiss-pk-banner="incomingPkChallenge = null; syncUrl(true)"
              @open-auth="openAuthModal('login')"
              @delete-prediction="handleDeletePrediction"
              @reset-local-predictions="handleResetLocalPredictions"
              @clear-search="clearFilters"
            />
          </template>
        </div>
      </template>

      <!-- TAB WEEKLY: Weekly Major Events Digest -->
      <template v-else-if="activeTab === 'weekly'">
        <WeeklyDigestView
          :doc="weeklyDigestDoc"
          :index-doc="weeklyDigestsIndexDoc"
          :selected-week-id="selectedWeekId"
          :loading="weeklyLoading"
          :site-settings="siteSettings"
          :watchlist="watchlist"
          :portfolio="userPortfolio"
          :bookmarked-ids="bookmarkedIdSet"
          :now-ms="nowMs"
          @select-week="handleSelectWeeklyIssue"
          @refresh="loadWeeklyDigest(selectedWeekId, true)"
          @toggle-bookmark-item="handleToggleWeeklyBookmark"
          @open-qa-item="openQaForWeeklyItem"
          @open-finance-keyword="(kw) => { searchQuery = kw || ''; void switchTab('finance') }"
          @open-weekly-poster="openWeeklyPoster"
          @switch-tab="switchTab"
          @mark-week-visited="markWeeklyDigestVisited"
        />
      </template>

      <!-- TAB ME: Dedicated Mobile / Android "我的 (Me)" Profile & Workbench Hub Page -->
      <template v-else-if="activeTab === 'me'">
        <MobileMeView
          :auth-user="authSession?.user ?? null"
          :user-avatar="userAvatar"
          :last-synced-at="lastSyncedAt"
          :cloud-sync-busy="cloudSyncBusy"
          :is-dark="isDark"
          :is-android-app="isAndroidApp"
          :mobile-push-enabled="mobilePushEnabled"
          :hide-reprints="hideReprints"
          :watchlist-count="watchlist.length"
          :bookmark-count="bookmarks.length"
          :research-notes-count="researchNotes.length"
          :read-later-count="readLaterCount"
          :today-read-count="dailyReading.readEventIdsToday.length"
          :batch-read-count="batchReadCount"
          :batch-total-count="batchTotalCount"
          :historical-read-count="historicalReadCount"
          :morning-brief="morningBriefSummary"
          :is-history-mode="isHistoryMode"
          :history-display="historyDisplay"
          :has-unread-weekly="hasUnreadWeekly"
          :storylines-count="Object.keys(storylinesMap).length || manifest?.v3?.storylines_count || 0"
          :calendar-count="calendarTabTotalCount"
          :tech-tools-count="techTools.length || manifest?.v3?.tech_tools_count || 0"
          :watch-new-count="returnVisitSummary.watchHits"
          :portfolio-hit-count="returnVisitSummary.portHits"
          :upcoming-48h-count="returnVisitSummary.cal48h"
          :now-ms="nowMs"
          @open-finance-portfolio="openFinancePortfolioHits"
          @open-auth="openAuthModal()"
          @open-avatar-picker="avatarPickerOpen = true"
          @open-watchlist-manager="openWatchlistManagerFromMe"
          @market-color-changed="handleMarketColorChanged"
          @logout="handleLogout"
          @sync-now="pushCurrentStateToCloud(false)"
          @switch-tab="switchTab"
          @open-bookmarks="(sub) => openLibraryModal(sub || 'saved')"
          @open-qa="openQaGlobal"
          @open-weekly-report="weeklyReportOpen = true"
          @open-onboarding="onboardingModalOpen = true"
          @open-feedback="triggerFeedbackDialog"
          @toggle-mobile-push="handleToggleMobilePush"
          @toggle-hide-reprints="handleToggleHideReprints"
          @toggle-dark="toggleDark"
          @toggle-lang="toggleAppLang"
          @copy-digest="handleCopyDailyBriefing"
          @request-clear-local="clearConfirmModalOpen = true"
        />
      </template>
        </div>

        <!-- RIGHT RAIL: Sticky Context Sidebar & Split-View Detail Reader (>=1280px; hidden on AI Frontier, Calendar/Predictions & Weekly Digest for full-width readability) -->
        <div
          v-if="(activeTab !== 'ai_progress' && activeTab !== 'calendar' && activeTab !== 'weekly') || Boolean(selectedDetailEvent)"
          class="hidden xl:block desktop-shell-only w-[336px] shrink-0 sticky top-[58px] max-h-[calc(100vh-4.25rem)] overflow-y-auto no-scrollbar pb-4"
        >
          <DesktopContextRail
            :selected-event="selectedDetailEvent"
            :selected-impact="selectedDetailEvent ? financeImpactDoc?.event_impact_map?.[selectedDetailEvent.event_id] || null : null"
            :is-selected-read="selectedDetailEvent ? isEventRead(selectedDetailEvent, readIds, legacyReadTitles) : false"
            :is-selected-bookmarked="selectedDetailEvent ? bookmarkedIdSet.has(selectedDetailEvent.event_id) : false"
            :indices="displayRailIndices"
            :quotes-updated-label="globalQuotesStore.updatedTimeLabel.value"
            :flashing-tickers="globalQuotesStore.flashingTickers.value"
            :entities="entities"
            :watchlist="watchlist"
            :all-events="allLoadedEvents"
            :topics="majorTopics"
            :calendar-events="mergedServerCalendarEvents"
            :finance-impacts="financeImpactDoc?.event_impacts || []"
            :portfolio="userPortfolio"
            :previous-visited-at="previousVisitedAt"
            :previous-seen-ids="previousSeenIds"
            :today-read-count="dailyReading.readEventIdsToday.length"
            :batch-read-count="batchReadCount"
            :batch-total-count="batchTotalCount"
            :historical-read-count="historicalReadCount"
            :now-ms="nowMs"
            @close-detail="closeDetailReader"
            @toggle-read="handleToggleRead"
            @mark-read="handleMarkSingleRead"
            @toggle-bookmark="handleToggleBookmark"
            @open-qa="(ev) => ev ? openQaForEvent(ev) : openQaGlobal()"
            @select-entity="handleOpenEntityByName"
            @switch-tab="switchTab"
            @open-finance-portfolio="openFinancePortfolioHits"
            @open-weekly-report="weeklyReportOpen = true"
          />
        </div>
      </div>
    </div>

    <!-- V3 Entity Research Drawer -->
    <EntityDrawer
      :entity="activeDrawerEntity"
      @close="closeEntityDrawer"
      @open-storyline="handleOpenStoryline"
      @open-qa-entity="openQaForEntity"
    />

    <!-- V3 Bounded Evidence QA & Notes Modal (supports local retrieval + BYOK Live LLM) -->
    <EvidenceQaModal
      :is-open="qaModalOpen"
      :context-event="qaContextEvent"
      :context-storyline="qaContextStoryline"
      :context-entity="qaContextEntity"
      :context-topic="qaContextTopic"
      :context-prompt="qaContextPrompt"
      :all-events="allLoadedEvents"
      :topics="majorTopics"
      :calendar-events="mergedServerCalendarEvents"
      :data-cutoff-at="activeDoc?.input_cutoff_at || manifest?.smart.input_cutoff_at"
      :saved-notes="researchNotes"
      :is-logged-in="Boolean(authSession)"
      :auth-token="authSession?.token ?? null"
      :guest-daily-limit="siteSettings.guest_qa_daily_limit ?? 5"
      :auth-daily-limit="siteSettings.auth_qa_daily_limit ?? 30"
      :extra-qa-quota="(authSession?.user?.extra_qa_quota ?? 0) + predictionBonusQaQuota"
      :now-ms="nowMs"
      @close="qaModalOpen = false"
      @save-note="handleSaveResearchNote"
      @delete-note="handleDeleteResearchNote"
      @quota-exhausted="triggerSoftAuth('qa_quota')"
    />

    <!-- Workbench Toast Feedback (Apple Frosted Glass Micro-Toast) -->
    <div
      v-if="workbenchToast"
      class="jx-collapse-reveal fixed bottom-20 md:bottom-5 left-3 right-3 md:left-auto md:right-5 z-50 md:max-w-sm rounded-2xl bg-zinc-900/90 dark:bg-[#1C1C1E]/92 backdrop-blur-xl text-white px-4 py-2.5 text-xs font-medium shadow-[0_12px_32px_rgba(0,0,0,0.28)] border border-white/15 flex items-center justify-between md:justify-start gap-2.5"
      role="status"
      aria-live="polite"
      data-testid="workbench-toast"
    >
      <span class="inline-flex items-center gap-2 min-w-0">
        <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0" aria-hidden="true" />
        <span>{{ workbenchToast.text }}</span>
      </span>
      <button
        v-if="workbenchToast.actionLabel && workbenchToast.onAction"
        type="button"
        @click="workbenchToast.onAction(); workbenchToast = null"
        class="px-3 min-h-[30px] rounded-xl bg-white/95 text-zinc-900 font-semibold hover:bg-white shrink-0"
      >
        {{ workbenchToast.actionLabel }}
      </button>
    </div>

    <!-- Unified Personal Library Modal (Saved + Read Later + Notes) -->
    <div
      v-if="bookmarksModalOpen"
      class="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-black/45 backdrop-blur-[2px]"
      @click.self="requestCloseBookmarks('backdrop')"
    >
      <div
        ref="bookmarksModalRef"
        role="dialog"
        aria-modal="true"
        aria-labelledby="bookmarks-modal-title"
        tabindex="-1"
        class="w-full max-w-xl max-h-[82vh] flex flex-col rounded-2xl bg-white dark:bg-[#1C1C1E] shadow-2xl overflow-hidden outline-none"
      >
        <div class="px-4 sm:px-5 pt-3.5 pb-3 border-b border-black/[0.06] dark:border-white/[0.08] space-y-2.5">
          <div class="flex items-center justify-between gap-3">
            <div>
              <h2 id="bookmarks-modal-title" class="text-base font-bold text-zinc-950 dark:text-white flex items-center gap-2">
                <Bookmark class="w-4 h-4 text-[#007AFF]" :stroke-width="1.5" />
                <span>{{ t(`个人阅读库 (${libraryCount})`, `Library (${libraryCount})`) }}</span>
              </h2>
              <p class="text-[11px] text-zinc-500 dark:text-zinc-400 mt-0.5 flex flex-wrap items-center gap-1.5">
                <template v-if="authSession">
                  <span class="text-emerald-600 dark:text-emerald-400 font-medium">
                    {{
                      t(
                        `云端加密同步 · ${formatShanghaiHhMm(lastSyncedAt) || '--:--'}`,
                        `Cloud synced · ${formatShanghaiHhMm(lastSyncedAt) || '--:--'}`,
                      )
                    }}
                  </span>
                </template>
                <template v-else>
                  <span>{{ t('保存在本设备。登录后可跨端同步。', 'Stored on this device. Sign in to sync.') }}</span>
                  <button
                    type="button"
                    @click="bookmarksModalOpen = false; openAuthModal()"
                    class="text-[#007AFF] dark:text-[#0A84FF] font-semibold hover:underline"
                  >
                    {{ t('去登录', 'Sign in') }}
                  </button>
                </template>
              </p>
            </div>
            <button
              type="button"
              @click="requestCloseBookmarks('button')"
              class="w-9 h-9 inline-flex items-center justify-center rounded-xl text-zinc-400 hover:bg-black/[0.05] dark:hover:bg-white/[0.08]"
              :aria-label="t('关闭阅读库', 'Close library')"
            >
              <X class="w-5 h-5" :stroke-width="1.5" />
            </button>
          </div>

          <div class="ios-segmented w-full flex">
            <button
              type="button"
              @click="libraryTab = 'saved'"
              class="ios-segmented-btn flex-1 min-h-[32px] px-2.5"
              :class="libraryTab === 'saved' ? 'ios-segmented-btn-active' : 'text-zinc-600 dark:text-zinc-400'"
            >
              {{ t(`收藏 (${bookmarks.length})`, `Saved (${bookmarks.length})`) }}
            </button>
            <button
              type="button"
              @click="libraryTab = 'read_later'"
              class="ios-segmented-btn flex-1 min-h-[32px] px-2.5"
              :class="libraryTab === 'read_later' ? 'ios-segmented-btn-active' : 'text-zinc-600 dark:text-zinc-400'"
            >
              {{ t(`稍后深读 (${readLaterCount})`, `Later (${readLaterCount})`) }}
            </button>
            <button
              type="button"
              @click="libraryTab = 'notes'"
              class="ios-segmented-btn flex-1 min-h-[32px] px-2.5"
              :class="libraryTab === 'notes' ? 'ios-segmented-btn-active' : 'text-zinc-600 dark:text-zinc-400'"
            >
              {{ t(`研报笔记 (${researchNotes.length})`, `Notes (${researchNotes.length})`) }}
            </button>
          </div>
        </div>

        <div class="flex-1 overflow-y-auto p-4 sm:p-5 space-y-3">
          <template v-if="libraryTab === 'saved'">
          <!-- C7 Bookmarks Search, Tag Pills & Export (Markdown/JSON) -->
          <div v-if="bookmarks.length > 0" class="space-y-2">
            <div class="flex flex-wrap items-center gap-2">
              <div class="relative flex-1 min-w-[180px]">
                <Search class="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
                <input
                  v-model="bookmarkSearchQuery"
                  type="search"
                  :placeholder="t('搜索收藏标题、来源或标签...', 'Search saved titles, sources, or tags...')"
                  class="w-full h-8 pl-8 pr-2.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-xs text-slate-900 dark:text-white"
                />
              </div>
            </div>
            <div v-if="allBookmarkTags.length > 0" class="flex flex-wrap items-center gap-1 text-[11px]">
              <button
                type="button"
                @click="bookmarkTagFilter = 'all'"
                class="px-2 py-0.5 rounded-full border"
                :class="bookmarkTagFilter === 'all' ? 'bg-slate-900 text-white border-slate-900 dark:bg-white dark:text-slate-900' : 'border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300'"
              >
                {{ t('全部标签', 'All Tags') }}
              </button>
              <button
                v-for="tg in allBookmarkTags"
                :key="tg"
                type="button"
                @click="bookmarkTagFilter = tg"
                class="px-2 py-0.5 rounded-full border"
                :class="bookmarkTagFilter === tg ? 'bg-blue-600 text-white border-blue-600' : 'border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300'"
              >
                #{{ tg }}
              </button>
            </div>
          </div>

          <div v-if="filteredBookmarks.length === 0" class="py-10 text-center text-sm text-slate-500 dark:text-slate-400">
            {{ bookmarks.length === 0 ? t('暂无收藏事件。点击新闻卡片下方「收藏」即可保存在我的收藏。', 'No saved briefings yet. Click "Save" on any event card to bookmark it.') : t('没有匹配当前关键词或标签的收藏。', 'No saved briefings match that filter.') }}
          </div>

          <ul v-else class="space-y-2.5">
            <li
              v-for="item in filteredBookmarks"
              :key="item.event_id"
              class="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-800/40 p-3 flex items-start justify-between gap-3"
            >
              <div class="min-w-0 flex-1 space-y-1.5">
                <button
                  type="button"
                  @click="handleBookmarkNavigate(item)"
                  class="text-left text-sm font-semibold text-slate-900 dark:text-white hover:text-blue-600 dark:hover:text-blue-400"
                >
                  {{ item.title }}
                </button>
                <div class="text-xs text-slate-500 dark:text-slate-400 flex flex-wrap gap-2">
                  <span>{{ item.source_name }}</span>
                  <span v-if="item.saved_at" class="inline-flex items-center gap-1">
                    <span>{{ t('收藏于', 'Saved') }}</span>
                    <SmartTime :iso="item.saved_at" :now-ms="nowMs" />
                  </span>
                </div>
                <div class="flex flex-wrap items-center gap-1.5">
                  <span
                    v-for="tg in (item.tags || [])"
                    :key="tg"
                    class="px-1.5 py-0.2 rounded bg-blue-50 dark:bg-blue-950/50 text-blue-700 dark:text-blue-300 text-[10px] border border-blue-200/70 dark:border-blue-800"
                  >
                    #{{ tg }}
                  </span>
                  <button
                    type="button"
                    @click="startEditBookmarkTags(item)"
                    class="text-[11px] text-slate-500 hover:text-blue-600 underline"
                  >
                    {{ (item.tags && item.tags.length > 0) ? t('改标签', 'Edit tags') : t('+ 加标签', '+ Add tags') }}
                  </button>
                </div>
                <form
                  v-if="editingBookmarkTagId === item.event_id"
                  @submit.prevent="saveBookmarkTags(item.event_id)"
                  class="flex items-center gap-1.5 pt-1"
                >
                  <input
                    v-model="editingBookmarkTagText"
                    type="text"
                    :placeholder="t('输入标签，逗号分隔，如 AI, 美股', 'Comma-separated tags, e.g. AI, Markets')"
                    class="flex-1 h-7 px-2 rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-xs text-slate-900 dark:text-white"
                  />
                  <button type="submit" class="px-2 h-7 rounded bg-blue-600 text-white text-[11px] font-medium">
                    {{ t('保存', 'Save') }}
                  </button>
                </form>
                <a
                  v-if="normalizeExternalUrl(item.url)"
                  :href="normalizeExternalUrl(item.url)!"
                  target="_blank"
                  rel="noopener noreferrer"
                  @click.stop
                  class="inline-flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 hover:underline"
                >
                  <span>{{ t('打开原文', 'Open Source') }}</span>
                  <ExternalLink class="w-3 h-3" />
                </a>
                <span v-else class="inline-flex items-center text-[11px] text-zinc-400">
                  {{ t('暂无原文直链', 'No direct link') }}
                </span>
              </div>

              <button
                type="button"
                @click="removeBookmark(item.event_id)"
                class="w-8 h-8 inline-flex items-center justify-center rounded-lg text-slate-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950/40 shrink-0"
                :aria-label="t('取消收藏', 'Remove bookmark')"
              >
                <Trash2 class="w-4 h-4" />
              </button>
            </li>
          </ul>
          </template>

          <template v-else-if="libraryTab === 'read_later'">
            <div v-if="readLaterEvents.length === 0" class="py-10 text-center text-sm text-zinc-500 dark:text-zinc-400">
              {{ t('暂无稍后深读事件。可在卡片「···」菜单中添加。', 'No Read Later items yet. Use the card menu to add stories.') }}
            </div>
            <ul v-else class="divide-y divide-black/[0.06] dark:divide-white/[0.08]">
              <li
                v-for="ev in readLaterEvents"
                :key="`rl-${ev.event_id}`"
                class="py-2.5 flex items-start justify-between gap-3"
              >
                <button
                  type="button"
                  @click="handleReadLaterItemClick(ev)"
                  class="min-w-0 flex-1 text-left space-y-1"
                >
                  <div class="text-sm font-semibold text-zinc-900 dark:text-white hover:text-[#007AFF] line-clamp-2">
                    {{ pickBiText(ev.title_zh || ev.title, ev.title_en || ev.title) }}
                  </div>
                  <div class="text-[11px] text-zinc-400 tabular-nums">
                    {{ ev.sources[0]?.source_name || '' }}
                  </div>
                </button>
                <button
                  type="button"
                  @click="toggleSetKey('read_later', ev.event_id)"
                  class="w-8 h-8 inline-flex items-center justify-center rounded-lg text-zinc-400 hover:text-rose-500 shrink-0"
                  :aria-label="t('移出稍后深读', 'Remove from Read Later')"
                >
                  <Trash2 class="w-4 h-4" :stroke-width="1.5" />
                </button>
              </li>
            </ul>
          </template>

          <template v-else>
            <div v-if="researchNotes.length === 0" class="py-10 text-center text-sm text-zinc-500 dark:text-zinc-400">
              {{ t('暂无研报笔记。可在卡片或证据问答中保存笔记。', 'No research notes yet. Save notes on cards or in Evidence Q&A.') }}
            </div>
            <ul v-else class="space-y-2.5">
              <li
                v-for="n in researchNotes"
                :key="n.note_id"
                class="ios-surface-2 p-3 flex items-start justify-between gap-2.5"
              >
                <div class="min-w-0 flex-1 space-y-1">
                  <div class="text-xs font-semibold text-zinc-900 dark:text-white">{{ n.title }}</div>
                  <p class="text-xs text-zinc-600 dark:text-zinc-300 leading-relaxed whitespace-pre-line">{{ n.answer_markdown }}</p>
                </div>
                <button
                  type="button"
                  @click="handleDeleteResearchNote(n.note_id)"
                  class="w-8 h-8 inline-flex items-center justify-center rounded-lg text-zinc-400 hover:text-rose-500 shrink-0"
                  :aria-label="t('删除笔记', 'Delete note')"
                >
                  <Trash2 class="w-4 h-4" :stroke-width="1.5" />
                </button>
              </li>
            </ul>
          </template>
        </div>
      </div>
    </div>

    <!-- Cross-Batch Fact Diff Comparison Modal ("对照前批" without losing current scroll/context) -->
    <div
      v-if="batchDiffModalOpen && batchDiffCurrentEvent"
      class="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-slate-950/60 backdrop-blur-xs"
      @click.self="requestCloseBatchDiff('backdrop')"
    >
      <div
        ref="batchDiffModalRef"
        role="dialog"
        aria-modal="true"
        aria-labelledby="batch-diff-modal-title"
        tabindex="-1"
        class="w-full max-w-2xl max-h-[85vh] flex flex-col rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-2xl overflow-hidden outline-none"
      >
        <div class="flex items-center justify-between gap-3 px-4 sm:px-5 py-3.5 border-b border-slate-200 dark:border-slate-800">
          <div>
            <h2 id="batch-diff-modal-title" class="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
              <GitBranch class="w-4 h-4 text-blue-600 dark:text-blue-400" />
              <span>{{ t('跨批次事实增量对照', 'Cross-Batch Fact Comparison') }}</span>
            </h2>
            <p class="text-xs text-slate-500 dark:text-slate-400 mt-0.5 tabular-nums">
              {{ t('当前批次', 'Current Batch') }} <code class="font-mono">{{ formatFriendlyBatchId(activeDoc?.batch_id) }}</code> vs {{ t('前批', 'Previous') }} <code class="font-mono">{{ formatFriendlyBatchId(batchDiffTargetBatchId) }}</code>
            </p>
          </div>
          <button
            type="button"
            @click="requestCloseBatchDiff('button')"
            class="w-9 h-9 inline-flex items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
            :aria-label="t('关闭对照弹窗', 'Close diff dialog')"
          >
            <X class="w-5 h-5" />
          </button>
        </div>

        <div class="flex-1 overflow-y-auto p-4 sm:p-5 space-y-3 text-xs sm:text-sm">
          <h3 class="font-bold text-slate-900 dark:text-white text-sm sm:text-base leading-snug">
            {{ batchDiffCurrentEvent.title }}
          </h3>

          <div v-if="batchDiffLoading" class="py-6 text-center text-xs text-slate-500 flex items-center justify-center gap-2">
            <RefreshCw class="w-4 h-4 animate-spin text-blue-600" />
            <span>{{ t('正在比对前批次归档正文与脉络 Diff...', 'Comparing against previous snapshot archive...') }}</span>
          </div>

          <template v-else>
            <div
              v-if="batchDiffStoryline?.fact_diff"
              class="rounded-xl border border-emerald-200 dark:border-emerald-900 bg-emerald-50/40 dark:bg-emerald-950/20 p-3.5 space-y-2 text-xs"
            >
              <div class="font-bold text-emerald-900 dark:text-emerald-200">
                {{ t('变动类型：', 'Change Type: ') }}{{ batchDiffStoryline.fact_diff.change_type_label }}
              </div>
              <div v-if="batchDiffStoryline.fact_diff.new_facts.length > 0">
                <div class="font-semibold text-emerald-800 dark:text-emerald-300 mb-0.5">{{ t('新增事实：', 'New Facts:') }}</div>
                <ul class="space-y-0.5 text-slate-700 dark:text-slate-200">
                  <li v-for="(nf, i) in batchDiffStoryline.fact_diff.new_facts" :key="i">• {{ nf }}</li>
                </ul>
              </div>
              <div v-if="batchDiffStoryline.fact_diff.corrections.length > 0">
                <div class="font-semibold text-amber-800 dark:text-amber-300 mb-0.5">{{ t('状态修订/冲突：', 'Revisions / Conflicts:') }}</div>
                <ul class="space-y-0.5 text-amber-900 dark:text-amber-200">
                  <li v-for="(cf, i) in batchDiffStoryline.fact_diff.corrections" :key="i">• {{ cf }}</li>
                </ul>
              </div>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
              <div class="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/60 p-3 space-y-1">
                <div class="font-bold text-slate-500 dark:text-slate-400">{{ t('前批次', 'Previous Batch') }} ({{ formatFriendlyBatchId(batchDiffTargetBatchId) }})</div>
                <div v-if="batchDiffPrevEvent" class="text-slate-700 dark:text-slate-200 leading-relaxed space-y-1">
                  <div class="font-semibold">{{ batchDiffPrevEvent.title }}</div>
                  <p>{{ batchDiffPrevEvent.fact_summary || batchDiffPrevEvent.summary }}</p>
                  <div class="text-[11px] text-slate-500">{{ t(`引用 ${batchDiffPrevEvent.sources.length} 源`, `${batchDiffPrevEvent.sources.length} sources`) }} · {{ batchDiffPrevEvent.evidence_label }}</div>
                </div>
                <div v-else class="text-slate-500">{{ t('前批次存档摘要已轮转或无法定位单条事件，请参考上方脉络增量。', 'Previous archive summary was rotated or unavailable; see storyline diff above.') }}</div>
              </div>
              <div class="rounded-xl border border-blue-200 dark:border-blue-900 bg-blue-50/40 dark:bg-blue-950/20 p-3 space-y-1">
                <div class="font-bold text-blue-700 dark:text-blue-300">{{ t('当前批次', 'Current Batch') }} ({{ formatFriendlyBatchId(activeDoc?.batch_id) }})</div>
                <p class="text-slate-800 dark:text-slate-100 leading-relaxed">
                  {{ batchDiffCurrentEvent.fact_summary || batchDiffCurrentEvent.summary }}
                </p>
                <div class="text-[11px] text-blue-700 dark:text-blue-300">
                  {{ t(`引用 ${batchDiffCurrentEvent.sources.length} 源`, `${batchDiffCurrentEvent.sources.length} sources`) }} · {{ batchDiffCurrentEvent.evidence_label }}
                </div>
              </div>
            </div>
          </template>
        </div>

        <div class="flex flex-wrap items-center justify-between gap-2 px-4 sm:px-5 py-3 border-t border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-800/40 text-xs">
          <button
            type="button"
            @click="requestCloseBatchDiff('button'); openPreviousBatch(batchDiffTargetBatchId)"
            class="inline-flex items-center gap-1 text-indigo-600 dark:text-indigo-400 hover:underline font-medium"
          >
            <History class="w-3.5 h-3.5" />
            <span>{{ t('在时间机器中整页打开该前批快照', 'Open Full Previous Snapshot in Archive') }}</span>
          </button>
          <button
            type="button"
            @click="requestCloseBatchDiff('button')"
            class="px-3.5 py-1.5 rounded-lg bg-slate-900 dark:bg-blue-600 text-white font-semibold"
          >
            {{ t('关闭对照（保留当前页位置）', 'Close Comparison') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Safe Two-Step Confirmation Modal for Clearing Local Research Data -->
    <div
      v-if="clearConfirmModalOpen"
      class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/60 backdrop-blur-xs"
      @click.self="requestCloseClearConfirm('backdrop')"
    >
      <div
        ref="clearConfirmModalRef"
        role="dialog"
        aria-modal="true"
        aria-labelledby="clear-confirm-title"
        tabindex="-1"
        class="w-full max-w-md rounded-2xl bg-white dark:bg-slate-900 border border-red-200 dark:border-red-900 shadow-2xl p-5 space-y-4 outline-none"
      >
        <div class="flex items-start justify-between gap-2">
          <div class="flex items-center gap-2 text-red-600 dark:text-red-400 font-bold text-base">
            <AlertCircle class="w-5 h-5 shrink-0" />
            <h2 id="clear-confirm-title">{{ t('确认清空本浏览器个人数据？', 'Reset Local Browser Data?') }}</h2>
          </div>
          <button
            type="button"
            @click="requestCloseClearConfirm('button')"
            class="w-8 h-8 inline-flex items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
            :aria-label="t('取消清空', 'Cancel reset')"
          >
            <X class="w-4 h-4" />
          </button>
        </div>

        <div class="text-xs sm:text-sm text-slate-600 dark:text-slate-300 space-y-2 leading-relaxed">
          <p>{{ t('此操作将清空当前浏览器本地保存的个人记录（不可撤销，公共新闻与您配置的 AI 密钥不受影响）：', 'This permanently clears local browser state (public news and BYOK API keys remain intact):') }}</p>
          <ul class="rounded-xl bg-slate-50 dark:bg-slate-800/70 border border-slate-200 dark:border-slate-700 p-3 space-y-1 text-xs tabular-nums">
            <li>• {{ t('收藏：', 'Saved: ') }}<strong>{{ bookmarks.length }}</strong> · {{ t('稍后深读：', 'Read Later: ') }}<strong>{{ readLaterCount }}</strong></li>
            <li>• {{ t('研究笔记：', 'Notes: ') }}<strong>{{ researchNotes.length }}</strong> · {{ t('已屏蔽：', 'Muted: ') }}<strong>{{ mutedSet.size }}</strong></li>
            <li>• {{ t('自建催化：', 'Custom Catalysts: ') }}<strong>{{ customCatalysts.length }}</strong> · {{ t('本地预测：', 'Local Predictions: ') }}<strong>{{ localPredictions.length }}</strong></li>
            <li>• {{ t('关注词列表将重置为默认均衡配置', 'Watchlist will reset to default balanced topics') }}</li>
          </ul>
        </div>

        <div class="flex flex-wrap items-center justify-end gap-2 pt-1 text-xs">
          <button
            type="button"
            @click="requestCloseClearConfirm('button')"
            class="px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800"
          >
            {{ t('取消', 'Cancel') }}
          </button>
          <button
            type="button"
            @click="handleClearAllLocalState"
            class="px-3.5 py-2 rounded-lg bg-red-600 text-white font-semibold hover:bg-red-700"
          >
            {{ t('确认清空', 'Confirm Reset') }}
          </button>
        </div>
      </div>
    </div>

    <AuthModal
      :is-open="authModalOpen"
      :session="authSession"
      :access-mode="siteAccessMode"
      :site-settings="siteSettings"
      :initial-ref-code="pendingRefCode"
      :initial-mode="authModalMode"
      :user-avatar="userAvatar"
      :last-synced-at="lastSyncedAt"
      :sync-busy="cloudSyncBusy"
      :morning-brief="morningBriefSummary"
      :initial-section="authModalSection"
      @close="authModalOpen = false; authModalSection = undefined; authModalMode = null"
      @authenticated="handleAuthenticated"
      @logout="handleLogout"
      @sync-now="pushCurrentStateToCloud(false)"
      @open-avatar-picker="avatarPickerOpen = true"
    />

    <SoftAuthPromptModal
      :is-open="softAuthPromptOpen"
      :scenario="softAuthScenario"
      @close="softAuthPromptOpen = false"
      @open-auth="(m) => { softAuthPromptOpen = false; openAuthModal(m) }"
    />

    <ShareCardModal
      :is-open="shareCardOpen"
      :payload="shareCardPayload"
      @close="shareCardOpen = false"
    />

    <!-- Single-Event Focus Reader Modal (for ?event=<id> shared deep-links not in active visible list) -->
    <Teleport to="body">
      <div
        v-if="focusedEventModalEvent"
        class="fixed inset-0 z-[58] flex items-center justify-center p-3 sm:p-5 bg-slate-950/60 backdrop-blur-xs"
        @click.self="focusedEventModalEvent = null"
        @keydown.esc.prevent="focusedEventModalEvent = null"
      >
        <div
          role="dialog"
          aria-modal="true"
          :aria-label="t('分享事件精读聚焦', 'Focused Shared Event')"
          class="w-full max-w-2xl max-h-[88vh] overflow-y-auto rounded-2xl bg-white dark:bg-[#1C1C1E] border border-black/[0.08] dark:border-white/[0.12] shadow-2xl p-4 sm:p-5 space-y-3"
        >
          <div class="flex items-center justify-between gap-2 pb-2 border-b border-black/[0.06] dark:border-white/[0.08]">
            <div class="inline-flex items-center gap-2 min-w-0">
              <span class="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-[#007AFF]/12 text-[#007AFF] dark:text-[#0A84FF]">
                {{ getCategoryLabel(focusedEventModalEvent.category) }}
              </span>
              <span class="text-xs font-semibold text-zinc-700 dark:text-zinc-200 truncate">
                {{ t('精读直达聚焦视图', 'Shared Event Focus') }}
              </span>
            </div>
            <div class="flex items-center gap-1.5 shrink-0">
              <button
                type="button"
                @click="const cat = focusedEventModalEvent.category; focusedEventModalEvent = null; activeTab = 'briefing'; void switchCategory(cat)"
                class="px-2.5 min-h-[30px] rounded-lg bg-[#007AFF]/10 text-[#007AFF] dark:text-[#0A84FF] text-[11px] font-semibold hover:bg-[#007AFF]/15"
              >
                {{ t('进入频道完整流', 'Open Channel') }}
              </button>
              <button
                type="button"
                @click="focusedEventModalEvent = null"
                class="w-8 h-8 inline-flex items-center justify-center rounded-lg text-zinc-400 hover:bg-black/[0.05] dark:hover:bg-white/[0.08]"
                :aria-label="t('关闭', 'Close')"
              >
                <X class="w-4 h-4" />
              </button>
            </div>
          </div>
          <EventCard
            :event="focusedEventModalEvent"
            :now-ms="nowMs"
            :is-read="checkIsRead(focusedEventModalEvent)"
            :market-impact="financeImpactDoc?.event_impact_map?.[focusedEventModalEvent.event_id] || null"
            :is-bookmarked="checkIsBookmarked(focusedEventModalEvent)"
            :is-new-since-visit="checkIsNew(focusedEventModalEvent)"
            :is-highlighted="true"
            :force-expand-perspectives="true"
            :default-expanded="true"
            :saved-note="savedNoteMap[focusedEventModalEvent.event_id] || ''"
            :matching-note-count="countMatchingNotesForSubject(researchNotes, { eventId: focusedEventModalEvent.event_id, storylineId: focusedEventModalEvent.storyline_id, entityIds: focusedEventModalEvent.entity_ids, entities: focusedEventModalEvent.entities })"
            :perspectives="commentsByCatForCards[focusedEventModalEvent.category] || []"
            :is-read-later="readLaterSet.has(focusedEventModalEvent.event_id)"
            :downweighted="downweightedSet.has(focusedEventModalEvent.event_id)"
            :show-moderation-actions="false"
            @toggle-read="handleToggleRead"
            @mark-read="handleMarkSingleRead"
            @open-notes="openLibraryModal('notes')"
            @toggle-bookmark="handleToggleBookmark"
            @copy-link="handleCopyLink"
            @select-entity="handleOpenEntityByName"
            @open-storyline="handleOpenStoryline"
            @open-qa="(ev) => { focusedEventModalEvent = null; openQaForEvent(ev) }"
            @open-detail="(ev) => { focusedEventModalEvent = null; openEventInDetailReader(ev) }"
            @save-note="handleSaveCardNote"
            @toggle-read-later="toggleSetKey('read_later', $event)"
            @toggle-downweight="toggleSetKey('downweighted', $event)"
            @toggle-mute="toggleSetKey('muted', $event)"
            @share-poster="openEventBriefShareCard"
          />
        </div>
      </div>
    </Teleport>

    <!-- Secondary Action Confirmation Modal (Sign Out / Delete Note / Remove Bookmark) -->
    <Teleport to="body">
      <div
        v-if="pendingConfirmAction"
        class="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-slate-950/60 backdrop-blur-xs"
        @click.self="closeConfirmAction"
        @keydown.esc.prevent="closeConfirmAction"
      >
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="action-confirm-title"
          tabindex="-1"
          class="w-full max-w-sm rounded-2xl bg-white dark:bg-[#1C1C1E] border border-black/[0.08] dark:border-white/[0.12] shadow-2xl p-5 space-y-3.5 outline-none"
        >
          <div class="flex items-start justify-between gap-2">
            <h2 id="action-confirm-title" class="text-base font-bold text-zinc-950 dark:text-white">
              {{ pendingConfirmAction.title }}
            </h2>
            <button
              type="button"
              @click="closeConfirmAction"
              class="w-8 h-8 inline-flex items-center justify-center rounded-lg text-zinc-400 hover:bg-black/[0.05] dark:hover:bg-white/[0.08]"
              :aria-label="t('取消', 'Cancel')"
            >
              <X class="w-4 h-4" />
            </button>
          </div>
          <p class="text-xs sm:text-sm text-zinc-600 dark:text-zinc-300 leading-relaxed">
            {{ pendingConfirmAction.message }}
          </p>
          <div class="flex items-center justify-end gap-2 pt-1 text-xs">
            <button
              type="button"
              @click="closeConfirmAction"
              class="px-3.5 py-2 rounded-xl border border-zinc-200 dark:border-zinc-700 text-zinc-700 dark:text-zinc-200 hover:bg-zinc-50 dark:hover:bg-zinc-800"
            >
              {{ t('取消', 'Cancel') }}
            </button>
            <button
              type="button"
              @click="runConfirmedAction"
              data-testid="confirm-destructive-action-btn"
              class="px-3.5 py-2 rounded-xl bg-red-600 text-white font-semibold hover:bg-red-700"
            >
              {{ pendingConfirmAction.confirmLabel }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <AvatarPickerModal
      :is-open="avatarPickerOpen"
      :current-avatar="userAvatar || authSession?.user?.avatar || ''"
      :username="authSession?.user?.username || ''"
      :role="authSession?.user?.role || 'user'"
      @close="avatarPickerOpen = false"
      @select="handleSelectAvatar"
    />

    <OnboardingGuideModal
      :is-open="onboardingModalOpen"
      @close="onboardingModalOpen = false; handleDismissOnboardingStrip()"
      @apply-preset="handleApplyWatchlistPreset"
      @jump-tab="(tab) => switchTab(tab)"
    />

    <ReadingWeeklyReportModal
      :is-open="weeklyReportOpen"
      :now-ms="nowMs"
      @close="weeklyReportOpen = false"
      @jump-panorama="activeTab = 'today'; todaySection = 'pillars'; searchScope = 'all'; onlyBlindspot = true; void ensureAllCategoriesLoaded(); weeklyReportOpen = false; syncUrl(false)"
    />

    <!-- Floating Quick Navigation Buttons: Jump to Unread + Back to Top (tucked low above tab bar so card titles never get covered) -->
    <div
      v-if="showFloatingNav"
      class="fixed right-2 bottom-[66px] md:right-5 md:bottom-6 z-20 flex flex-col gap-1.5 opacity-90 hover:opacity-100 transition-opacity"
    >
      <button
        v-if="activeTab === 'today' || activeTab === 'briefing'"
        type="button"
        @click="jumpToNextUnread"
        class="w-10 h-10 md:w-11 md:h-11 rounded-full ios-glass border border-black/[0.08] dark:border-white/[0.12] shadow-md flex items-center justify-center text-blue-600 dark:text-blue-400 active:scale-95 transition-transform"
        :title="t('跳到下一条未读', 'Jump to next unread')"
        :aria-label="t('跳到下一条未读', 'Jump to next unread')"
      >
        <CircleDot class="w-4 h-4 md:w-5 md:h-5" />
      </button>
      <button
        type="button"
        @click="scrollToTop"
        class="w-9 h-9 md:w-11 md:h-11 rounded-full ios-glass border border-black/[0.08] dark:border-white/[0.12] shadow-md flex items-center justify-center text-zinc-700 dark:text-zinc-200 active:scale-95 transition-transform"
        :title="t('回到顶部', 'Back to top')"
        :aria-label="t('回到顶部', 'Back to top')"
      >
        <ArrowUp class="w-4 h-4 md:w-5 md:h-5" />
      </button>
    </div>

    <!-- Full-Screen Unified Search Overlay (News + 7x24 Live Wire + Archive) -->
    <Teleport to="body">
      <div
        v-if="searchOverlayOpen"
        class="fixed inset-0 z-50 bg-[#F2F2F7] dark:bg-black flex flex-col"
        role="dialog"
        aria-modal="true"
        :aria-label="t('全站搜索', 'Global Search')"
        @click.self="closeSearchOverlay(true)"
      >
        <div class="ios-glass border-b border-black/[0.06] dark:border-white/[0.08] px-3 py-2 flex items-center gap-2">
          <div class="relative flex-1 min-w-0">
            <Search class="w-4 h-4 text-zinc-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input
              ref="searchInputEl"
              v-model="searchQuery"
              type="search"
              :placeholder="t('搜索新闻、7×24快讯、实体、工具…', 'Search news, live wire, entities…')"
              class="w-full h-11 pl-9 pr-9 rounded-xl bg-black/[0.05] dark:bg-white/[0.09] text-sm text-zinc-950 dark:text-white placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
              @keydown.enter="searchOverlayOpen = false"
              @keydown.esc.prevent.stop="closeSearchOverlay(true)"
            />
            <button
              v-if="searchQuery"
              type="button"
              @click="searchQuery = ''"
              class="absolute right-1 top-1/2 -translate-y-1/2 w-9 h-9 inline-flex items-center justify-center rounded-lg text-zinc-400"
              :aria-label="t('清空', 'Clear')"
            >
              <X class="w-4 h-4" />
            </button>
          </div>
          <button
            type="button"
            @click="closeSearchOverlay(true)"
            class="min-h-[44px] px-2 text-sm font-semibold text-blue-600 dark:text-blue-400 shrink-0"
          >
            {{ searchQuery.trim() ? t('取消', 'Cancel') : t('关闭', 'Close') }}
          </button>
        </div>

        <div class="flex-1 overflow-y-auto p-3.5 max-w-2xl w-full mx-auto space-y-4">
          <!-- Command Palette: Jump to ANY Module or Tool (filterable by typing) -->
          <div v-if="commandPaletteItems.length > 0" class="space-y-1.5">
            <div class="text-xs font-semibold text-zinc-500">{{ t('模块与工具直达', 'Jump to Module & Tools') }}</div>
            <div class="grid grid-cols-2 sm:grid-cols-3 gap-1.5">
              <button
                v-for="cmd in commandPaletteItems"
                :key="cmd.id"
                type="button"
                @click="cmd.run()"
                class="ios-tap min-h-[42px] px-3 rounded-xl bg-white dark:bg-[#1C1C1E] text-left text-xs font-medium text-zinc-800 dark:text-zinc-100 hover:text-[#007AFF] truncate shadow-[0_1px_2px_rgba(0,0,0,0.04)]"
              >
                {{ cmd.label }}
              </button>
            </div>
          </div>

          <template v-if="!searchQuery.trim()">
            <div v-if="entities.length > 0" class="space-y-2">
              <div class="text-xs font-semibold text-zinc-500">{{ t('热门实体', 'Trending Entities') }}</div>
              <div class="flex flex-wrap gap-2">
                <button
                  v-for="ent in entities.slice(0, 12)"
                  :key="ent.entity_id"
                  type="button"
                  @click="searchQuery = ent.canonical_name"
                  class="ios-tap min-h-[38px] px-3 rounded-xl bg-white dark:bg-[#1C1C1E] text-xs font-medium text-zinc-800 dark:text-zinc-200"
                >
                  {{ translateEntityName(ent.canonical_name) }}
                </button>
              </div>
            </div>
          </template>

          <template v-else>
            <div class="flex items-center justify-between gap-2 pb-1">
              <span class="text-[11px] font-semibold text-zinc-500">
                {{ searchCurrentTabOnly ? t('已开启：仅在当前标签页筛选', 'Scope: Current Tab Only') : t('全站 6 模块跨区检索（实体 · 股市 · 要闻 · AI · 快讯 · 日历）', 'Cross-Module Global Search (6 Modules)') }}
              </span>
              <button
                type="button"
                @click="searchCurrentTabOnly = !searchCurrentTabOnly"
                class="ios-tap inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-medium border transition-colors"
                :class="searchCurrentTabOnly ? 'bg-[#007AFF] text-white border-[#007AFF]' : 'bg-white dark:bg-[#1C1C1E] text-zinc-600 dark:text-zinc-300 border-black/[0.08] dark:border-white/[0.1]'"
              >
                <component :is="searchCurrentTabOnly ? MapPin : Globe" class="w-3 h-3 shrink-0" />
                <span>{{ searchCurrentTabOnly ? t('仅当前标签页筛选', 'Current Tab') : t('全站 6 模块搜索', 'All 6 Modules') }}</span>
              </button>
            </div>

            <!-- Group 1: Entities & Supply Chain Profiles -->
            <div v-if="searchOverlayMatches.entities.length > 0" class="space-y-1.5">
              <div class="flex items-center gap-1.5 text-xs font-semibold text-zinc-500">
                <Building2 class="w-3.5 h-3.5 shrink-0" />
                <span>{{ t('实体与产业链档案', 'Entities & Supply Chain') }}</span>
              </div>
              <div class="ios-card divide-y divide-black/[0.05] dark:divide-white/[0.06] overflow-hidden">
                <button
                  v-for="ent in searchOverlayMatches.entities"
                  :key="ent.entity_id"
                  type="button"
                  @click="searchOverlayOpen = false; void handleOpenEntityByName(ent.canonical_name)"
                  class="w-full text-left px-3.5 py-3 text-xs font-medium text-zinc-800 dark:text-zinc-200 active:bg-black/[0.04]"
                >
                  <div class="flex items-center justify-between gap-2">
                    <span class="text-sm font-semibold text-zinc-900 dark:text-white">{{ translateEntityName(ent.canonical_name) }}</span>
                    <span v-if="ent.tickers && ent.tickers.length" class="font-mono text-[11px] text-[#007AFF] dark:text-[#0A84FF]">
                      {{ ent.tickers.map((tk) => (typeof tk === 'string' ? tk : tk.symbol || tk.label || '')).filter(Boolean).slice(0, 3).join(' · ') }}
                    </span>
                  </div>
                  <div class="mt-0.5 text-[11px] text-zinc-500 line-clamp-1">
                    {{ ent.sector }} · {{ t(`近30日 ${ent.change_count_30d} 次催化`, `${ent.change_count_30d} events (30d)`) }}
                  </div>
                </button>
              </div>
            </div>

            <!-- Group 2: Finance Impact Transmission -->
            <div v-if="searchOverlayMatches.financeImpacts.length > 0" class="space-y-1.5">
              <div class="flex items-center gap-1.5 text-xs font-semibold text-zinc-500">
                <TrendingUp class="w-3.5 h-3.5 shrink-0" />
                <span>{{ t('股市传导推演', 'Market Transmission') }}</span>
              </div>
              <div class="ios-card divide-y divide-black/[0.05] dark:divide-white/[0.06] overflow-hidden">
                <button
                  v-for="imp in searchOverlayMatches.financeImpacts"
                  :key="imp.id"
                  type="button"
                  @click="searchOverlayOpen = false; void switchTab('finance')"
                  class="w-full text-left px-3.5 py-3 text-xs font-medium text-zinc-800 dark:text-zinc-200 active:bg-black/[0.04]"
                >
                  <div class="flex items-center justify-between gap-2 mb-0.5 text-[11px]">
                    <span class="font-semibold text-[#007AFF] dark:text-[#0A84FF]">{{ imp.tag }}</span>
                    <span v-if="imp.effective_date_label" class="text-[#007AFF] dark:text-[#0A84FF]">{{ imp.effective_date_label }}</span>
                  </div>
                  <div class="text-sm font-medium text-zinc-900 dark:text-zinc-100 line-clamp-2">{{ pickBiText(imp.event_title, imp.event_title_en || imp.event_title) }}</div>
                </button>
              </div>
            </div>

            <!-- Group 3: Today Stories, Topics & Storyline Tracking -->
            <div v-if="searchOverlayMatches.events.length > 0 || searchOverlayMatches.topics.length > 0 || searchOverlayMatches.storylines.length > 0" class="space-y-1.5">
              <div class="flex items-center gap-1.5 text-xs font-semibold text-zinc-500">
                <Flame class="w-3.5 h-3.5 shrink-0" />
                <span>{{ t('今日要闻 & 事件追踪', 'Today Stories & Tracking') }}</span>
              </div>
              <div class="ios-card divide-y divide-black/[0.05] dark:divide-white/[0.06] overflow-hidden">
                <button
                  v-for="ev in searchOverlayMatches.events"
                  :key="ev.event_id"
                  type="button"
                  @click="searchOverlayOpen = false; handleJumpToEventId(ev.event_id)"
                  class="w-full text-left px-3.5 py-3 text-sm font-medium text-zinc-900 dark:text-zinc-100 active:bg-black/[0.04]"
                >
                  <div class="text-[11px] text-zinc-400 mb-0.5">{{ t('今日要闻', 'Top Story') }}</div>
                  <div class="line-clamp-2">{{ pickBiText(ev.title_zh || ev.title, ev.title_en || ev.title) }}</div>
                </button>
                <button
                  v-for="tp in searchOverlayMatches.topics"
                  :key="tp.topic_id"
                  type="button"
                  @click="searchOverlayOpen = false; selectedTopicId = tp.topic_id; activeTab = 'today'; todaySection = 'topics'"
                  class="w-full text-left px-3.5 py-3 text-xs font-medium text-zinc-800 dark:text-zinc-200 active:bg-black/[0.04]"
                >
                  <div class="flex items-center justify-between gap-2 mb-0.5 text-[11px] text-[#007AFF] dark:text-[#0A84FF]">
                    <span>{{ t('焦点专题', 'Topic') }} · {{ tp.lifecycle_label || t('专题', 'Topic') }}</span>
                    <span>{{ tp.timeline?.length || 0 }} {{ t('节点', 'nodes') }}</span>
                  </div>
                  <div class="line-clamp-2">{{ pickBiText(tp.title, tp.title_en || tp.title) }}</div>
                </button>
                <button
                  v-for="st in searchOverlayMatches.storylines"
                  :key="st.storyline_id"
                  type="button"
                  @click="searchOverlayOpen = false; handleOpenStoryline(st.storyline_id)"
                  class="w-full text-left px-3.5 py-3 text-xs font-medium text-zinc-800 dark:text-zinc-200 active:bg-black/[0.04]"
                >
                  <div class="text-[11px] text-violet-600 dark:text-violet-400 mb-0.5">{{ t('事件追踪档案', 'Dossier') }} · {{ st.current_stage }}</div>
                  <div class="line-clamp-2">{{ pickBiText(st.title_zh || st.title, st.title_en || st.title) }}</div>
                </button>
              </div>
            </div>

            <!-- Group 4: AI Frontier & Open-Source Tools -->
            <div v-if="searchOverlayMatches.ai.length > 0 || searchOverlayMatches.tools.length > 0" class="space-y-1.5">
              <div class="flex items-center gap-1.5 text-xs font-semibold text-zinc-500">
                <Bot class="w-3.5 h-3.5 shrink-0" />
                <span>{{ t('AI 前沿 & 工具库', 'AI Frontier & Tools') }}</span>
              </div>
              <div class="ios-card divide-y divide-black/[0.05] dark:divide-white/[0.06] overflow-hidden">
                <button
                  v-for="ai in searchOverlayMatches.ai"
                  :key="ai.id"
                  type="button"
                  @click="searchOverlayOpen = false; aiSubView = 'tracker'; switchTab('ai_progress')"
                  class="w-full text-left px-3.5 py-3 text-xs font-medium text-zinc-800 dark:text-zinc-200 active:bg-black/[0.04]"
                >
                  <div class="flex items-center justify-between gap-2 mb-0.5 text-[11px] text-zinc-400">
                    <span>{{ ai.company_name }}</span>
                    <span>{{ ai.source_name }}</span>
                  </div>
                  <div class="line-clamp-2">{{ ai.title }}</div>
                </button>
                <button
                  v-for="tl in searchOverlayMatches.tools"
                  :key="tl.tool_id"
                  type="button"
                  @click="searchOverlayOpen = false; aiSubView = 'tools'; void loadTools(); void switchTab('ai_progress')"
                  class="w-full text-left px-3.5 py-3 text-xs font-medium text-zinc-800 dark:text-zinc-200 active:bg-black/[0.04]"
                >
                  <div class="flex items-center justify-between gap-2 mb-0.5 text-[11px] text-teal-600 dark:text-teal-400">
                    <span>{{ t('开源工具 / 权重', 'Tool') }} · {{ tl.tool_type }}</span>
                    <span>{{ tl.latest_version || tl.license || '' }}</span>
                  </div>
                  <div class="line-clamp-2">{{ tl.name }} — {{ tl.summary }}</div>
                </button>
              </div>
            </div>

            <!-- Group 5: 7x24 Live Wire -->
            <div v-if="searchOverlayMatches.wire.length > 0" class="space-y-1.5">
              <div class="flex items-center gap-1.5 text-xs font-semibold text-zinc-500">
                <Zap class="w-3.5 h-3.5 shrink-0" />
                <span>{{ t('7×24 快讯', 'Live Wire') }}</span>
              </div>
              <div class="ios-card divide-y divide-black/[0.05] dark:divide-white/[0.06] overflow-hidden">
                <button
                  v-for="w in searchOverlayMatches.wire"
                  :key="w.id"
                  type="button"
                  @click="searchOverlayOpen = false; switchTab('wire')"
                  class="w-full text-left px-3.5 py-3 text-xs font-medium text-zinc-800 dark:text-zinc-200 active:bg-black/[0.04]"
                >
                  <div class="line-clamp-2">{{ pickBiText(w.title, w.title_en || w.title) }}</div>
                </button>
              </div>
            </div>

            <!-- Group 6: Catalyst Calendar & Predictions -->
            <div v-if="searchOverlayMatches.calendar.length > 0 || searchOverlayMatches.predictions.length > 0" class="space-y-1.5">
              <div class="flex items-center gap-1.5 text-xs font-semibold text-zinc-500">
                <Calendar class="w-3.5 h-3.5 shrink-0" />
                <span>{{ t('催化日程 & 前瞻验证', 'Calendar & Predictions') }}</span>
              </div>
              <div class="ios-card divide-y divide-black/[0.05] dark:divide-white/[0.06] overflow-hidden">
                <button
                  v-for="cal in searchOverlayMatches.calendar"
                  :key="cal.calendar_id"
                  type="button"
                  @click="searchOverlayOpen = false; scheduleSubView = 'calendar'; switchTab('calendar')"
                  class="w-full text-left px-3.5 py-3 text-xs font-medium text-zinc-800 dark:text-zinc-200 active:bg-black/[0.04]"
                >
                  <div class="flex items-center justify-between gap-2 mb-0.5 text-[11px] text-indigo-600 dark:text-indigo-400">
                    <span>{{ cal.location_display || cal.region_label || '全球' }} · {{ cal.event_type_label || '日程' }}</span>
                    <span>{{ cal.scheduled_at ? cal.scheduled_at.slice(0, 10) : 'TBD' }}</span>
                  </div>
                  <div class="line-clamp-2">{{ pickBiText(cal.title, cal.title_en || cal.title) }}</div>
                </button>
                <button
                  v-for="pr in searchOverlayMatches.predictions"
                  :key="pr.prediction_id"
                  type="button"
                  @click="searchOverlayOpen = false; scheduleSubView = 'predictions'; void loadPredictions(); void switchTab('calendar')"
                  class="w-full text-left px-3.5 py-3 text-xs font-medium text-zinc-800 dark:text-zinc-200 active:bg-black/[0.04]"
                >
                  <div class="flex items-center justify-between gap-2 mb-0.5 text-[11px] text-amber-600 dark:text-amber-400">
                    <span>{{ t('前瞻推演', 'Prediction') }} · {{ pr.target_entity || t('行业事件', 'Sector') }}</span>
                    <span>{{ pr.probability_pct }}%</span>
                  </div>
                  <div class="line-clamp-2">{{ pr.title }}</div>
                </button>
              </div>
            </div>

            <div
              v-if="
                searchOverlayMatches.entities.length === 0 &&
                searchOverlayMatches.financeImpacts.length === 0 &&
                searchOverlayMatches.events.length === 0 &&
                searchOverlayMatches.wire.length === 0 &&
                searchOverlayMatches.ai.length === 0 &&
                searchOverlayMatches.tools.length === 0 &&
                searchOverlayMatches.topics.length === 0 &&
                searchOverlayMatches.storylines.length === 0 &&
                searchOverlayMatches.calendar.length === 0 &&
                searchOverlayMatches.predictions.length === 0
              "
              class="text-center py-10 text-xs text-zinc-400"
            >
              {{ t('未找到匹配内容 · 按「完成」返回当前视图', 'No matches found · Tap Done to return') }}
            </div>
          </template>
        </div>
      </div>
    </Teleport>

    <!-- Batch Status & Disclaimers Detail Sheet (opened from Topbar Status Dot) -->
    <Teleport to="body">
      <div
        v-if="batchInfoModalOpen"
        class="ios-sheet-backdrop p-0 sm:p-4"
        role="dialog"
        aria-modal="true"
        @click.self="batchInfoModalOpen = false"
      >
        <div class="ios-sheet-panel bg-white dark:bg-zinc-900 p-5 space-y-3 text-xs pb-[max(1.25rem,env(safe-area-inset-bottom))]">
          <div class="flex items-center justify-between">
            <h3 class="text-sm font-bold text-zinc-950 dark:text-white">{{ t('批次更新明细', 'Batch Status') }}</h3>
            <button
              type="button"
              @click="batchInfoModalOpen = false"
              class="w-11 h-11 -mr-2 inline-flex items-center justify-center rounded-xl text-zinc-400"
              :aria-label="t('关闭', 'Close')"
            >
              <X class="w-5 h-5" />
            </button>
          </div>
          <div class="rounded-xl bg-zinc-50 dark:bg-zinc-800/70 p-3 space-y-1.5 text-zinc-600 dark:text-zinc-300 tabular-nums">
            <div class="flex justify-between gap-2">
              <span class="text-zinc-400">{{ t('状态', 'Status') }}</span>
              <span class="font-semibold text-zinc-900 dark:text-white">{{ smartHealth.label }}</span>
            </div>
            <div v-if="activeDoc?.batch_id" class="flex justify-between gap-2">
              <span class="text-zinc-400">{{ t('批次', 'Batch') }}</span>
              <span class="font-mono">{{ formatFriendlyBatchId(activeDoc.batch_id) }}</span>
            </div>
            <div v-if="activeDoc?.generated_at" class="flex justify-between gap-2">
              <span class="text-zinc-400">{{ t('生成时间', 'Generated') }}</span>
              <span>{{ formatShanghaiDateTime(activeDoc.generated_at, false) }}</span>
            </div>
            <div v-if="activeDoc?.input_cutoff_at" class="flex justify-between gap-2">
              <span class="text-zinc-400">{{ t('素材截止', 'Cutoff') }}</span>
              <span>{{ formatShanghaiDateTime(activeDoc.input_cutoff_at, false) }}</span>
            </div>
          </div>
          <p class="text-[11px] text-zinc-400 leading-relaxed">
            {{ t('本服务聚合公开媒体与官方披露，所有分析与股市敏感区间仅供参考，不构成投资建议。', 'Aggregated from public reports & official filings. All AI analysis and sensitivity ranges are for reference only and not investment advice.') }}
          </p>
          <div class="flex items-center justify-between pt-1">
            <a href="./about.html" class="text-blue-600 dark:text-blue-400 font-semibold">
              {{ t('关于与完整免责声明 →', 'About & Full Disclaimers →') }}
            </a>
            <button
              type="button"
              @click="batchInfoModalOpen = false; handleManualRefresh()"
              class="min-h-[40px] px-4 rounded-xl bg-blue-600 text-white font-semibold"
            >
              {{ t('立即刷新', 'Refresh Now') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- 1024~1279px Slide-Over Right Context & Detail Reader Drawer -->
    <Teleport to="body">
      <div
        v-if="rightDrawerOpen"
        class="mac-drawer-backdrop"
        role="dialog"
        aria-modal="true"
        :aria-label="t('上下文与详情抽屉', 'Context & Detail Drawer')"
        @click.self="rightDrawerOpen = false"
      >
        <div class="mac-drawer-panel p-4 overflow-y-auto space-y-3">
          <div class="flex items-center justify-between pb-2 border-b border-black/[0.06] dark:border-white/[0.08]">
            <span class="text-sm font-bold text-zinc-900 dark:text-white">{{ t('投研上下文与详情', 'Context & Reader') }}</span>
            <button
              type="button"
              @click="rightDrawerOpen = false"
              class="w-9 h-9 inline-flex items-center justify-center rounded-xl text-zinc-400 hover:text-zinc-900 dark:hover:text-white"
              :aria-label="t('关闭', 'Close')"
            >
              <X class="w-4 h-4" :stroke-width="1.5" />
            </button>
          </div>
          <DesktopContextRail
            :selected-event="selectedDetailEvent"
            :selected-impact="selectedDetailEvent ? financeImpactDoc?.event_impact_map?.[selectedDetailEvent.event_id] || null : null"
            :is-selected-read="selectedDetailEvent ? isEventRead(selectedDetailEvent, readIds, legacyReadTitles) : false"
            :is-selected-bookmarked="selectedDetailEvent ? bookmarkedIdSet.has(selectedDetailEvent.event_id) : false"
            :indices="displayRailIndices"
            :quotes-updated-label="globalQuotesStore.updatedTimeLabel.value"
            :flashing-tickers="globalQuotesStore.flashingTickers.value"
            :entities="entities"
            :watchlist="watchlist"
            :all-events="allLoadedEvents"
            :topics="majorTopics"
            :calendar-events="mergedServerCalendarEvents"
            :finance-impacts="financeImpactDoc?.event_impacts || []"
            :portfolio="userPortfolio"
            :previous-visited-at="previousVisitedAt"
            :previous-seen-ids="previousSeenIds"
            :today-read-count="dailyReading.readEventIdsToday.length"
            :batch-read-count="batchReadCount"
            :batch-total-count="batchTotalCount"
            :historical-read-count="historicalReadCount"
            :now-ms="nowMs"
            @close-detail="closeDetailReader"
            @toggle-read="handleToggleRead"
            @mark-read="handleMarkSingleRead"
            @toggle-bookmark="handleToggleBookmark"
            @open-qa="(ev) => { rightDrawerOpen = false; ev ? openQaForEvent(ev) : openQaGlobal() }"
            @select-entity="(name) => { rightDrawerOpen = false; handleOpenEntityByName(name) }"
            @switch-tab="(tab) => { rightDrawerOpen = false; switchTab(tab) }"
            @open-finance-portfolio="rightDrawerOpen = false; openFinancePortfolioHits()"
            @open-weekly-report="rightDrawerOpen = false; weeklyReportOpen = true"
          />
        </div>
      </div>
    </Teleport>

    <!-- Keyboard Shortcuts Cheat Sheet Modal (?) -->
    <Teleport to="body">
      <div
        v-if="shortcutsModalOpen"
        class="ios-sheet-backdrop p-4"
        role="dialog"
        aria-modal="true"
        :aria-label="t('键盘快捷键', 'Keyboard Shortcuts')"
        @click.self="shortcutsModalOpen = false"
      >
        <div class="ios-sheet-panel bg-white dark:bg-[#1C1C1E] p-5 space-y-3.5 text-xs">
          <div class="flex items-center justify-between">
            <h3 class="text-[16px] font-semibold text-zinc-950 dark:text-white inline-flex items-center gap-2">
              <Keyboard class="w-4 h-4 text-[#007AFF]" :stroke-width="1.5" />
              <span>{{ t('键盘快捷键', 'Keyboard Shortcuts') }}</span>
            </h3>
            <button
              type="button"
              @click="shortcutsModalOpen = false"
              class="w-9 h-9 inline-flex items-center justify-center rounded-xl text-zinc-400 hover:text-zinc-900 dark:hover:text-white"
              :aria-label="t('关闭', 'Close')"
            >
              <X class="w-4 h-4" :stroke-width="1.5" />
            </button>
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[13px]">
            <div class="flex items-center justify-between py-1.5 px-2.5 rounded-lg bg-[#F5F5F7] dark:bg-[#2C2C2E]">
              <span>{{ t('全局搜索', 'Global Search') }}</span>
              <kbd class="font-mono text-[11px] text-zinc-500">⌘K / /</kbd>
            </div>
            <div class="flex items-center justify-between py-1.5 px-2.5 rounded-lg bg-[#F5F5F7] dark:bg-[#2C2C2E]">
              <span>{{ t('上下切换条目', 'Next / Prev Item') }}</span>
              <kbd class="font-mono text-[11px] text-zinc-500">j / k</kbd>
            </div>
            <div class="flex items-center justify-between py-1.5 px-2.5 rounded-lg bg-[#F5F5F7] dark:bg-[#2C2C2E]">
              <span>{{ t('右栏打开详情', 'Open Reader') }}</span>
              <kbd class="font-mono text-[11px] text-zinc-500">Enter</kbd>
            </div>
            <div class="flex items-center justify-between py-1.5 px-2.5 rounded-lg bg-[#F5F5F7] dark:bg-[#2C2C2E]">
              <span>{{ t('关闭抽屉 / 弹窗', 'Dismiss') }}</span>
              <kbd class="font-mono text-[11px] text-zinc-500">Esc</kbd>
            </div>
            <div class="flex items-center justify-between py-1.5 px-2.5 rounded-lg bg-[#F5F5F7] dark:bg-[#2C2C2E]">
              <span>{{ t('跳至今日 / 快讯 / 股市', 'Today / Wire / Markets') }}</span>
              <kbd class="font-mono text-[11px] text-zinc-500">g t · g w · g f</kbd>
            </div>
            <div class="flex items-center justify-between py-1.5 px-2.5 rounded-lg bg-[#F5F5F7] dark:bg-[#2C2C2E]">
              <span>{{ t('跳至 AI / 日程 / 追踪', 'AI / Outlook / Track') }}</span>
              <kbd class="font-mono text-[11px] text-zinc-500">g a · g c · g r</kbd>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- iOS-Grade Frosted 6-Tab Bottom Navigation Bar (<768px mobile, plus Android shell / phone landscape) -->
    <nav
      class="md:hidden mobile-shell-nav fixed bottom-0 inset-x-0 z-40 ios-glass border-t border-black/[0.07] dark:border-white/[0.1] px-1 pt-1 pb-[max(0.35rem,env(safe-area-inset-bottom))]"
      aria-label="移动端底部导航"
    >
      <div class="grid grid-cols-6 items-center text-[10px] font-semibold">
        <button
          type="button"
          @click="handleBottomTabClick('today')"
          :aria-current="activeTab === 'today' ? 'page' : undefined"
          class="ios-tap flex flex-col items-center justify-center gap-0.5 min-h-[48px] py-1 rounded-xl transition-colors"
          :class="activeTab === 'today' ? 'text-[#007AFF] dark:text-[#0A84FF]' : 'text-zinc-500 dark:text-zinc-400'"
        >
          <Compass class="w-[20px] h-[20px]" :stroke-width="1.5" />
          <span>{{ t('要闻', 'Today') }}</span>
        </button>
        <button
          type="button"
          @click="handleBottomTabClick('wire')"
          :aria-current="activeTab === 'wire' ? 'page' : undefined"
          class="ios-tap relative flex flex-col items-center justify-center gap-0.5 min-h-[48px] py-1 rounded-xl transition-colors"
          :class="activeTab === 'wire' ? 'text-[#007AFF] dark:text-[#0A84FF]' : 'text-zinc-500 dark:text-zinc-400'"
        >
          <Radio class="w-[20px] h-[20px]" :stroke-width="1.5" />
          <span>{{ t('快讯', 'Live') }}</span>
        </button>
        <button
          type="button"
          @click="handleBottomTabClick('finance')"
          :aria-current="activeTab === 'finance' ? 'page' : undefined"
          class="ios-tap flex flex-col items-center justify-center gap-0.5 min-h-[48px] py-1 rounded-xl transition-colors"
          :class="activeTab === 'finance' ? 'text-[#007AFF] dark:text-[#0A84FF]' : 'text-zinc-500 dark:text-zinc-400'"
        >
          <TrendingUp class="w-[20px] h-[20px]" :stroke-width="1.5" />
          <span>{{ t('股市', 'Markets') }}</span>
        </button>
        <button
          type="button"
          @click="handleBottomTabClick('predictions')"
          :aria-current="activeTab === 'calendar' ? 'page' : undefined"
          class="ios-tap flex flex-col items-center justify-center gap-0.5 min-h-[48px] py-1 rounded-xl transition-colors"
          :class="activeTab === 'calendar' ? 'text-[#007AFF] dark:text-[#0A84FF]' : 'text-zinc-500 dark:text-zinc-400'"
        >
          <Target class="w-[20px] h-[20px]" :stroke-width="1.5" />
          <span>{{ t('预测', 'Arena') }}</span>
        </button>
        <button
          type="button"
          @click="handleBottomTabClick('ai_progress')"
          :aria-current="activeTab === 'ai_progress' ? 'page' : undefined"
          class="ios-tap flex flex-col items-center justify-center gap-0.5 min-h-[48px] py-1 rounded-xl transition-colors"
          :class="activeTab === 'ai_progress' ? 'text-[#007AFF] dark:text-[#0A84FF]' : 'text-zinc-500 dark:text-zinc-400'"
        >
          <Bot class="w-[20px] h-[20px]" :stroke-width="1.5" />
          <span>{{ t('AI 前沿', 'AI') }}</span>
        </button>
        <button
          type="button"
          @click="handleBottomTabClick('me')"
          :aria-current="activeTab === 'me' ? 'page' : undefined"
          class="ios-tap relative flex flex-col items-center justify-center gap-0.5 min-h-[48px] py-1 rounded-xl transition-colors"
          :class="activeTab === 'me' || isSecondaryTabActive ? 'text-[#007AFF] dark:text-[#0A84FF]' : 'text-zinc-500 dark:text-zinc-400'"
        >
          <span v-if="isSecondaryTabActive" class="w-1.5 h-1.5 rounded-full bg-[#007AFF] absolute top-1.5 right-3" />
          <User class="w-[20px] h-[20px]" :stroke-width="1.5" />
          <span>{{ t('我的', 'Me') }}</span>
        </button>
      </div>
    </nav>
  </AppShell>
</template>