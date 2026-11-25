<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  Bookmark,
  CheckCircle2,
  Cloud,
  Copy,
  HelpCircle,
  History,
  Info,
  KeyRound,
  Keyboard,
  LogOut,
  Menu,
  MessageSquare,
  Moon,
  MoreHorizontal,
  Newspaper,
  Radio,
  RefreshCw,
  Search,
  Settings,
  Shield,
  Smartphone,
  Sparkles,
  Sun,
  Trash2,
  User,
  X,
} from 'lucide-vue-next'
import SmartTime from './SmartTime.vue'
import UserAvatar from './UserAvatar.vue'
import {
  apiFetchMyFeedback,
  apiGetPublicSettings,
  apiSubmitFeedback,
  isAdminRole,
  loadAuthSession,
  type AuthUser,
  type FeedbackRecordItem,
  type PublicSiteSettings,
} from '../core/auth'
import { appLang, syncHtmlLangAttr, t } from '../core/i18n'
import { isAndroidAppShell } from '../core/mobilePush'
import { formatShanghaiDateTime, parseTimestampMs } from '../core/time'
import { lockBodyScroll, isRedUp, toggleMarketColorMode, unlockBodyScroll } from '../core/uiPrefs'

const props = defineProps<{
  activePage: 'briefing' | 'monitor' | 'about' | 'help'
  activeTab?: string
  menuCloseNonce?: number
  isDark: boolean
  isHistoryMode?: boolean
  historyDisplay?: string | null
  bookmarkCount?: number
  isRefreshing?: boolean
  showHistoryButton?: boolean
  showBookmarksButton?: boolean
  showRefreshButton?: boolean
  showAuthButton?: boolean
  showSearchButton?: boolean
  showQaButton?: boolean
  searchActive?: boolean
  updatedAtIso?: string | null
  batchStatusTone?: 'ok' | 'warn' | 'err'
  nowMs?: number
  authUser?: AuthUser | null
  userAvatar?: string | null
  cloudSyncBusy?: boolean
  hideMobileFooter?: boolean
  wideWorkspace?: boolean
}>()

const emit = defineEmits<{
  (e: 'toggle-dark'): void
  (e: 'open-history'): void
  (e: 'open-bookmarks'): void
  (e: 'refresh'): void
  (e: 'open-auth', section?: 'profile' | 'security'): void
  (e: 'request-logout'): void
  (e: 'market-color-changed', isRedUpNow: boolean): void
  (e: 'open-search'): void
  (e: 'open-qa'): void
  (e: 'open-batch-info'): void
  (e: 'open-shortcuts'): void
  (e: 'copy-digest'): void
  (e: 'request-clear-local'): void
  (e: 'scroll-top'): void
}>()

const monitorPublic = ref(false)
const siteSettings = ref<PublicSiteSettings>({
  monitor_public: false,
  feedback_enabled: true,
  feedback_notice: '欢迎反馈页面问题、数据纠错或功能建议，镜信编辑团队将尽快查阅并回复。',
  feedback_daily_limit: 5,
})
const mobileMenuOpen = ref(false)
const userMenuOpen = ref(false)
const dangerSubmenuOpen = ref(false)
const feedbackOpen = ref(false)
const feedbackTab = ref<'submit' | 'history'>('submit')
const feedbackCat = ref<'bug' | 'data' | 'suggestion'>('bug')
const feedbackContact = ref('')
const feedbackContent = ref('')
const feedbackBusy = ref(false)
const feedbackStatus = ref<{ ok: boolean; text: string } | null>(null)
const myFeedbackList = ref<FeedbackRecordItem[]>([])
const loadingMyFeedback = ref(false)
const localSessionUser = ref<AuthUser | null>(loadAuthSession()?.user ?? null)

// Auto-hide mobile/tablet header on scroll down, reveal on scroll up
const headerHidden = ref(false)
let lastScrollY = 0

function syncStickyTopOffset(hidden: boolean) {
  if (typeof document !== 'undefined') {
    document.documentElement.style.setProperty('--mobile-sticky-top', hidden ? '0px' : '48px')
  }
}

watch(headerHidden, (hidden) => {
  syncStickyTopOffset(hidden)
})

function handleWindowScroll() {
  if (typeof window === 'undefined') return
  const y = window.scrollY || 0
  if (mobileMenuOpen.value || userMenuOpen.value || y <= 48) {
    headerHidden.value = false
    lastScrollY = y
    return
  }
  const delta = y - lastScrollY
  if (delta > 10 && y > 72) {
    headerHidden.value = true
  } else if (delta < -8) {
    headerHidden.value = false
  }
  lastScrollY = y
}

function handleHeaderTap(e: MouseEvent) {
  const target = e.target as HTMLElement | null
  if (target?.closest('a, button, input, select')) return
  emit('scroll-top')
  if (typeof window !== 'undefined') {
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }
}

function handleBrandClick() {
  if (props.activePage === 'briefing') {
    emit('scroll-top')
    if (typeof window !== 'undefined') {
      window.scrollTo({ top: 0, behavior: 'smooth' })
    }
  } else if (typeof window !== 'undefined') {
    window.location.href = './index.html'
  }
}

async function refreshFeedbackModalData() {
  const token = loadAuthSession()?.token || ''
  loadingMyFeedback.value = true
  try {
    const [settingsRes, mineRes] = await Promise.all([
      apiGetPublicSettings(),
      apiFetchMyFeedback(token),
    ])
    siteSettings.value = settingsRes
    monitorPublic.value = Boolean(settingsRes.monitor_public)
    myFeedbackList.value = mineRes.items || []
  } catch {
    // Keep existing cached values
  } finally {
    loadingMyFeedback.value = false
  }
}

watch(feedbackOpen, (open) => {
  if (open) {
    lockBodyScroll()
    feedbackStatus.value = null
    void refreshFeedbackModalData()
  } else {
    unlockBodyScroll()
  }
})

watch(
  () => [props.activeTab, props.menuCloseNonce],
  () => {
    mobileMenuOpen.value = false
  },
)

function cycleMarketColorMode() {
  const nextMode = toggleMarketColorMode()
  emit('market-color-changed', nextMode === 'cn')
}

const marketColorLabel = computed(() =>
  isRedUp() ? t('红涨绿跌', 'Red Up') : t('绿涨红跌', 'Green Up'),
)

const shortUpdateLabel = computed(() => {
  if (!props.updatedAtIso) return ''
  const ms = parseTimestampMs(props.updatedAtIso)
  if (ms === null) return ''
  const diffMin = Math.max(0, Math.floor(((props.nowMs ?? Date.now()) - ms) / 60_000))
  if (diffMin < 1) return t('刚刚', 'now')
  if (diffMin < 60) return `${diffMin}m`
  const h = Math.floor(diffMin / 60)
  if (h < 24) return `${h}h`
  return `${Math.floor(h / 24)}d`
})

function feedbackStatusBadge(st: string): { label: string; cls: string } {
  if (st === 'resolved') return { label: t('已解决', 'Resolved'), cls: 'bg-emerald-500/12 text-emerald-700 dark:text-emerald-300' }
  if (st === 'replied') return { label: t('已回复', 'Replied'), cls: 'bg-blue-500/12 text-blue-700 dark:text-blue-300' }
  if (st === 'in_progress') return { label: t('处理中', 'In Progress'), cls: 'bg-amber-500/12 text-amber-700 dark:text-amber-300' }
  return { label: t('待受理', 'Pending'), cls: 'bg-zinc-500/12 text-zinc-600 dark:text-zinc-300' }
}

function feedbackCatLabel(cat: string): string {
  if (cat === 'data') return t('数据纠错', 'Data')
  if (cat === 'suggestion') return t('功能建议', 'Idea')
  return t('页面问题', 'Bug')
}

async function submitFeedbackForm() {
  if (siteSettings.value.feedback_enabled === false) {
    feedbackStatus.value = { ok: false, text: t('反馈通道当前维护中，请通过下方官方联系渠道沟通。', 'Feedback channel is temporarily paused.') }
    return
  }
  const txt = feedbackContent.value.trim()
  if (txt.length < 4) {
    feedbackStatus.value = { ok: false, text: t('请至少输入 4 个字的反馈内容', 'Please enter at least 4 characters') }
    return
  }
  feedbackBusy.value = true
  feedbackStatus.value = null
  try {
    const token = loadAuthSession()?.token || ''
    await apiSubmitFeedback(
      {
        category: feedbackCat.value,
        contact: feedbackContact.value.trim() || effectiveUser.value?.username || '',
        content: txt,
        page_url: typeof window !== 'undefined' ? window.location.href : '',
      },
      token,
    )
    feedbackContent.value = ''
    feedbackStatus.value = {
      ok: true,
      text: t('已成功提交！可在「我的反馈记录」查看受理状态与官方回复。', 'Submitted! Track status and replies under My Feedback.'),
    }
    await refreshFeedbackModalData()
  } catch (err) {
    feedbackStatus.value = {
      ok: false,
      text: err instanceof Error ? err.message : t('提交失败，请稍后重试', 'Submission failed, please retry'),
    }
  } finally {
    feedbackBusy.value = false
  }
}

const effectiveUser = computed(() => (props.authUser !== undefined ? props.authUser : localSessionUser.value))

watch(
  () => props.authUser,
  (nextUser) => {
    localSessionUser.value = nextUser ?? null
  },
)

const statusDotClass = computed(() => {
  if (props.batchStatusTone === 'err') return 'jx-sonar-red'
  if (props.batchStatusTone === 'warn') return 'jx-sonar-amber'
  return 'jx-sonar-emerald'
})

const containerWidthClass = computed(() =>
  props.wideWorkspace ? 'max-w-[1440px] min-[1800px]:max-w-[1600px]' : 'max-w-6xl',
)

function onGlobalKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    if (feedbackOpen.value) feedbackOpen.value = false
    if (mobileMenuOpen.value) mobileMenuOpen.value = false
    if (userMenuOpen.value) {
      userMenuOpen.value = false
      dangerSubmenuOpen.value = false
    }
  }
}

function onGlobalClickOutside(e: MouseEvent) {
  const target = e.target as HTMLElement | null
  if (userMenuOpen.value && !target?.closest('[data-user-menu-root]')) {
    userMenuOpen.value = false
    dangerSubmenuOpen.value = false
  }
}

function handleExternalOpenFeedback() {
  feedbackTab.value = 'submit'
  feedbackOpen.value = true
}

function closeUserMenu() {
  userMenuOpen.value = false
  dangerSubmenuOpen.value = false
}

onMounted(() => {
  syncHtmlLangAttr()
  syncStickyTopOffset(headerHidden.value)
  localSessionUser.value = loadAuthSession()?.user ?? null
  void apiGetPublicSettings().then((s) => {
    siteSettings.value = s
    monitorPublic.value = Boolean(s.monitor_public)
  })
  if (typeof window !== 'undefined') {
    window.addEventListener('keydown', onGlobalKeydown)
    window.addEventListener('click', onGlobalClickOutside)
    window.addEventListener('scroll', handleWindowScroll, { passive: true })
    window.addEventListener('infofocus-open-feedback', handleExternalOpenFeedback)
  }
})

onUnmounted(() => {
  syncStickyTopOffset(false)
  if (feedbackOpen.value) unlockBodyScroll()
  if (typeof window !== 'undefined') {
    window.removeEventListener('keydown', onGlobalKeydown)
    window.removeEventListener('click', onGlobalClickOutside)
    window.removeEventListener('scroll', handleWindowScroll)
    window.removeEventListener('infofocus-open-feedback', handleExternalOpenFeedback)
  }
})
</script>

<template>
  <div class="min-h-screen flex flex-col bg-[#F5F5F7] text-[#1D1D1F] dark:bg-black dark:text-[#F5F5F7] overflow-x-clip">
    <a
      href="#main-content"
      class="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:px-3 focus:py-2 focus:rounded-lg focus:bg-zinc-900 focus:text-white focus:text-sm focus:font-medium"
    >
      {{ t('跳至主要内容', 'Skip to main content') }}
    </a>

    <!-- Invisible status-bar tap zone on mobile/tablet to scroll smoothly to top -->
    <button
      type="button"
      @click="emit('scroll-top')"
      class="md:hidden fixed top-0 inset-x-0 h-2.5 z-50 bg-transparent cursor-pointer"
      :aria-label="t('点击状态栏区域回到顶部', 'Tap top bar to scroll to top')"
    />

    <slot name="top-banner" />

    <!-- macOS / iOS Frosted Minimal Topbar: Brand + Primary Nav + Search (⌘K) + Theme + Avatar/More Menu (ZERO overlap at any width) -->
    <header
      @click="handleHeaderTap"
      class="sticky top-0 z-40 ios-glass border-b border-black/[0.06] dark:border-white/[0.08] transition-transform duration-200 will-change-transform"
      :class="headerHidden ? '-translate-y-full md:translate-y-0' : 'translate-y-0'"
    >
      <div class="mx-auto px-2.5 sm:px-5" :class="containerWidthClass">
        <div class="flex items-center justify-between gap-2 h-12">
          <!-- Left: Brand + Compact Status Dot + Ultra-Short Relative Age -->
          <div class="flex items-center gap-1.5 min-w-0">
            <a
              href="./index.html"
              @click.prevent="handleBrandClick"
              class="flex items-center gap-1.5 sm:gap-2 min-h-[44px] py-1 pr-0.5 rounded-xl shrink-0 whitespace-nowrap"
              :aria-label="t('镜信首页', 'MirrorBrief Home')"
            >
              <img
                :src="'./icon.svg'"
                alt="镜信 MirrorBrief"
                class="w-6 h-6 sm:w-7 sm:h-7 rounded-lg bg-[#FAFAFA] object-cover shrink-0 shadow-[0_1px_2px_rgba(0,0,0,0.08)]"
              />
              <span class="font-bold text-[15px] tracking-tight text-zinc-950 dark:text-white whitespace-nowrap">
                {{ t('镜信', 'MirrorBrief') }}
              </span>
            </a>

            <button
              v-if="updatedAtIso"
              type="button"
              @click="emit('open-batch-info')"
              class="inline-flex items-center gap-1 min-h-[44px] md:min-h-[34px] px-1 sm:px-1.5 rounded-lg text-[11px] sm:text-[12px] text-zinc-500 dark:text-zinc-400 hover:bg-black/[0.04] dark:hover:bg-white/[0.06] transition-colors shrink-0 whitespace-nowrap"
              :aria-label="t('查看批次更新明细', 'View batch update details')"
            >
              <span class="jx-sonar-dot" :class="statusDotClass" />
              <span class="tabular-nums font-medium">{{ shortUpdateLabel }}</span>
            </button>
          </div>

          <!-- Right: Mobile keeps ONLY Search + AI Q&A + Menu (zero overlap at 360px/393px); Desktop adds Theme + Avatar Menu -->
          <div class="flex items-center gap-0.5 sm:gap-1 shrink-0">
            <!-- Search Icon / ⌘K Command Palette Trigger -->
            <button
              v-if="showSearchButton"
              type="button"
              @click="emit('open-search')"
              class="ios-tap inline-flex items-center justify-center gap-1.5 w-10 h-10 sm:w-11 sm:h-11 md:w-auto md:h-8 md:px-2.5 rounded-xl md:rounded-lg transition-colors"
              :class="
                searchActive
                  ? 'text-[#007AFF] dark:text-[#0A84FF] bg-[#007AFF]/10'
                  : 'text-zinc-600 dark:text-zinc-300 md:bg-black/[0.05] md:dark:bg-white/[0.08] hover:bg-black/[0.08] dark:hover:bg-white/[0.12]'
              "
              :aria-label="t('全局搜索', 'Search')"
              :title="t('搜索与命令面板 (⌘K 或 /)', 'Search & Command Palette (⌘K or /)')"
            >
              <Search class="w-[18px] h-[18px] md:w-3.5 md:h-3.5 shrink-0" :stroke-width="1.5" />
              <span class="hidden md:inline text-[12px] font-medium text-zinc-500 dark:text-zinc-400">
                {{ t('搜索', 'Search') }}
              </span>
              <kbd class="hidden xl:inline-flex items-center px-1 py-0.2 rounded bg-white/80 dark:bg-black/40 text-[10px] font-mono text-zinc-400">
                ⌘K
              </kbd>
            </button>

            <button
              v-if="showQaButton"
              type="button"
              @click="emit('open-qa')"
              class="ios-tap inline-flex items-center justify-center w-10 h-10 sm:w-11 sm:h-11 md:w-8 md:h-8 rounded-xl md:rounded-lg text-[#007AFF] dark:text-[#0A84FF] hover:bg-[#007AFF]/10 transition-colors"
              :title="t('AI 证据问答', 'AI Evidence Q&A')"
              :aria-label="t('AI 证据问答', 'AI Evidence Q&A')"
            >
              <Sparkles class="w-[18px] h-[18px] md:w-4 md:h-4" :stroke-width="1.5" />
            </button>

            <!-- Dark / Light Toggle (desktop topbar only; on mobile lives inside Menu / Me tab) -->
            <button
              type="button"
              @click.stop="emit('toggle-dark')"
              class="hidden md:inline-flex desktop-shell-only ios-tap items-center justify-center w-8 h-8 rounded-lg text-zinc-600 dark:text-zinc-300 hover:bg-black/[0.05] dark:hover:bg-white/[0.08] transition-colors shrink-0"
              :aria-label="isDark ? t('切换浅色', 'Light mode') : t('切换深色', 'Dark mode')"
            >
              <Sun v-if="isDark" class="w-4 h-4 text-amber-400 pointer-events-none" :stroke-width="1.5" />
              <Moon v-else class="w-4 h-4 pointer-events-none" :stroke-width="1.5" />
            </button>

            <!-- Desktop Unified Avatar / More Menu (>=768px): houses Auth, Refresh, Batch Info, Digest, Export/Import, Admin, Android Dev, About, Danger Clear -->
            <div class="hidden md:block desktop-shell-only relative" data-user-menu-root>
              <button
                type="button"
                @click.stop="userMenuOpen = !userMenuOpen"
                class="ios-tap inline-flex items-center justify-center gap-1.5 h-8 px-2 rounded-lg hover:bg-black/[0.05] dark:hover:bg-white/[0.08] transition-colors"
                :aria-expanded="userMenuOpen"
                :aria-label="t('账号与更多工具菜单', 'Account & Tools Menu')"
              >
                <UserAvatar
                  v-if="effectiveUser"
                  :avatar="userAvatar || effectiveUser.avatar"
                  :username="effectiveUser.username"
                  :role="effectiveUser.role"
                  size="sm"
                />
                <span
                  v-else
                  class="inline-flex items-center justify-center w-7 h-7 rounded-full bg-[#007AFF]/12 text-[#007AFF] dark:text-[#0A84FF]"
                >
                  <User class="w-4 h-4" :stroke-width="1.75" />
                </span>
                <MoreHorizontal class="w-4 h-4 text-zinc-500" :stroke-width="1.5" />
              </button>

              <!-- macOS Popover Menu -->
              <div
                v-if="userMenuOpen"
                class="absolute right-0 mt-1.5 w-60 rounded-2xl bg-white/95 dark:bg-[#1C1C1E]/95 backdrop-blur-xl shadow-2xl border border-black/[0.08] dark:border-white/[0.1] p-1.5 text-[13px] z-50 ios-fade-in"
              >
                <!-- Account Section -->
                <template v-if="showAuthButton && effectiveUser">
                  <div class="px-3 py-1.5 flex items-center justify-between gap-2 text-[11px] text-zinc-500">
                    <span class="font-semibold text-zinc-900 dark:text-white truncate">
                      {{ effectiveUser.display_name || effectiveUser.username }}
                    </span>
                    <span class="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400 shrink-0">
                      <Cloud class="w-3.5 h-3.5" :stroke-width="1.5" :class="{ 'animate-pulse': cloudSyncBusy }" />
                      <span>{{ t('已同步', 'Synced') }}</span>
                    </span>
                  </div>
                  <button
                    type="button"
                    @click="closeUserMenu(); emit('open-auth', 'profile')"
                    class="w-full px-3 py-1.5 rounded-xl flex items-center gap-2 text-zinc-700 dark:text-zinc-200 hover:bg-black/[0.05] dark:hover:bg-white/[0.08]"
                  >
                    <Settings class="w-4 h-4 text-[#007AFF]" :stroke-width="1.5" />
                    <span>{{ t('个人设置 / 头像', 'Profile & Avatar') }}</span>
                  </button>
                  <button
                    type="button"
                    @click="closeUserMenu(); emit('open-auth', 'security')"
                    class="w-full px-3 py-1.5 rounded-xl flex items-center gap-2 text-zinc-700 dark:text-zinc-200 hover:bg-black/[0.05] dark:hover:bg-white/[0.08]"
                  >
                    <KeyRound class="w-4 h-4 text-zinc-400" :stroke-width="1.5" />
                    <span>{{ t('绑定邮箱 / 修改密码', 'Email & Password') }}</span>
                  </button>
                  <button
                    type="button"
                    @click="closeUserMenu(); emit('request-logout')"
                    class="w-full px-3 py-1.5 rounded-xl flex items-center gap-2 text-rose-600 dark:text-rose-400 hover:bg-rose-500/10"
                  >
                    <LogOut class="w-4 h-4" :stroke-width="1.5" />
                    <span>{{ t('退出登录', 'Sign Out') }}</span>
                  </button>
                </template>
                <button
                  v-else-if="showAuthButton"
                  type="button"
                  @click="closeUserMenu(); emit('open-auth')"
                  class="w-full px-3 py-2 rounded-xl flex items-center justify-between gap-2 text-left hover:bg-black/[0.05] dark:hover:bg-white/[0.08]"
                >
                  <span class="inline-flex items-center gap-2 min-w-0">
                    <User class="w-4 h-4 text-[#007AFF] shrink-0" :stroke-width="1.5" />
                    <span class="font-semibold text-zinc-900 dark:text-white truncate">
                      {{ t('登录 / 开启云同步', 'Sign In / Sync') }}
                    </span>
                  </span>
                </button>

                <div class="my-1 border-t border-black/[0.06] dark:border-white/[0.08]" />

                <button
                  v-if="showRefreshButton"
                  type="button"
                  @click="closeUserMenu(); emit('refresh')"
                  class="w-full px-3 py-2 rounded-xl flex items-center gap-2 text-zinc-700 dark:text-zinc-200 hover:bg-black/[0.05] dark:hover:bg-white/[0.08]"
                >
                  <RefreshCw class="w-4 h-4 text-zinc-400" :stroke-width="1.5" :class="{ 'animate-spin': isRefreshing }" />
                  <span>{{ t('立即检查更新', 'Refresh Now') }}</span>
                </button>
                <button
                  v-if="updatedAtIso"
                  type="button"
                  @click="closeUserMenu(); emit('open-batch-info')"
                  class="w-full px-3 py-2 rounded-xl flex items-center gap-2 text-zinc-700 dark:text-zinc-200 hover:bg-black/[0.05] dark:hover:bg-white/[0.08]"
                >
                  <Info class="w-4 h-4 text-zinc-400" :stroke-width="1.5" />
                  <span>{{ t('批次明细与免责声明', 'Batch Info & Disclaimers') }}</span>
                </button>
                <button
                  v-if="activePage === 'briefing'"
                  type="button"
                  @click="closeUserMenu(); emit('copy-digest')"
                  class="w-full px-3 py-2 rounded-xl flex items-center gap-2 text-zinc-700 dark:text-zinc-200 hover:bg-black/[0.05] dark:hover:bg-white/[0.08]"
                >
                  <Copy class="w-4 h-4 text-zinc-400" :stroke-width="1.5" />
                  <span>{{ t('复制 30 秒速览日报', 'Copy 30s Digest') }}</span>
                </button>
                <button
                  v-if="activePage === 'briefing'"
                  type="button"
                  @click="cycleMarketColorMode()"
                  class="w-full px-3 py-2 rounded-xl flex items-center justify-between gap-2 text-zinc-700 dark:text-zinc-200 hover:bg-black/[0.05] dark:hover:bg-white/[0.08]"
                >
                  <span>{{ t('涨跌配色', 'Market Colors') }}</span>
                  <span class="text-[11px] text-zinc-400">{{ marketColorLabel }}</span>
                </button>
                <button
                  v-if="activePage === 'briefing'"
                  type="button"
                  @click="closeUserMenu(); emit('open-shortcuts')"
                  class="w-full px-3 py-2 rounded-xl flex items-center justify-between gap-2 text-zinc-700 dark:text-zinc-200 hover:bg-black/[0.05] dark:hover:bg-white/[0.08]"
                >
                  <span class="inline-flex items-center gap-2">
                    <Keyboard class="w-4 h-4 text-zinc-400" :stroke-width="1.5" />
                    <span>{{ t('键盘快捷键', 'Shortcuts') }}</span>
                  </span>
                  <kbd class="text-[11px] font-mono text-zinc-400">?</kbd>
                </button>

                <div class="my-1 border-t border-black/[0.06] dark:border-white/[0.08]" />

                <a
                  v-if="isAdminRole(effectiveUser?.role)"
                  href="./admin.html"
                  class="w-full px-3 py-2 rounded-xl flex items-center gap-2 text-zinc-700 dark:text-zinc-200 hover:bg-black/[0.05] dark:hover:bg-white/[0.08]"
                >
                  <Shield class="w-4 h-4 text-rose-500" :stroke-width="1.5" />
                  <span>{{ t('管理员后台', 'Admin Console') }}</span>
                </a>
                <a
                  v-if="isAdminRole(effectiveUser?.role) && !isAndroidAppShell()"
                  href="./android-dev.html"
                  class="w-full px-3 py-2 rounded-xl flex items-center gap-2 text-zinc-700 dark:text-zinc-200 hover:bg-black/[0.05] dark:hover:bg-white/[0.08]"
                >
                  <Smartphone class="w-4 h-4 text-emerald-500" :stroke-width="1.5" />
                  <span>{{ t('安卓页面调试台', 'Android Dev Console') }}</span>
                </a>
                <a
                  href="./help.html"
                  class="w-full px-3 py-2 rounded-xl flex items-center gap-2 text-zinc-700 dark:text-zinc-200 hover:bg-black/[0.05] dark:hover:bg-white/[0.08]"
                >
                  <HelpCircle class="w-4 h-4 text-zinc-400" :stroke-width="1.5" />
                  <span>{{ t('使用帮助', 'Help & Guide') }}</span>
                </a>
                <a
                  href="./about.html"
                  class="w-full px-3 py-2 rounded-xl flex items-center gap-2 text-zinc-700 dark:text-zinc-200 hover:bg-black/[0.05] dark:hover:bg-white/[0.08]"
                >
                  <Info class="w-4 h-4 text-zinc-400" :stroke-width="1.5" />
                  <span>{{ t('关于镜信', 'About MirrorBrief') }}</span>
                </a>
                <button
                  type="button"
                  @click="closeUserMenu(); feedbackTab = 'submit'; feedbackOpen = true"
                  class="w-full px-3 py-2 rounded-xl flex items-center gap-2 text-zinc-700 dark:text-zinc-200 hover:bg-black/[0.05] dark:hover:bg-white/[0.08]"
                >
                  <MessageSquare class="w-4 h-4 text-zinc-400" :stroke-width="1.5" />
                  <span>{{ t('意见反馈', 'Send Feedback') }}</span>
                </button>

                <!-- Secondary collapsible submenu for destructive Clear Local Data -->
                <template v-if="activePage === 'briefing'">
                  <div class="my-1 border-t border-black/[0.06] dark:border-white/[0.08]" />
                  <button
                    type="button"
                    @click.stop="dangerSubmenuOpen = !dangerSubmenuOpen"
                    class="w-full px-3 py-1.5 rounded-xl flex items-center justify-between text-[12px] text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200"
                  >
                    <span>{{ t('更多数据操作', 'Advanced Data') }}</span>
                    <span>{{ dangerSubmenuOpen ? '−' : '+' }}</span>
                  </button>
                  <button
                    v-if="dangerSubmenuOpen"
                    type="button"
                    @click="closeUserMenu(); emit('request-clear-local')"
                    class="w-full mt-0.5 px-3 py-2 rounded-xl flex items-center gap-2 text-rose-600 dark:text-rose-400 hover:bg-rose-500/10"
                  >
                    <Trash2 class="w-4 h-4" :stroke-width="1.5" />
                    <span>{{ t('清空本机数据…', 'Clear Local Data…') }}</span>
                  </button>
                </template>
              </div>
            </div>

            <!-- Mobile / Tablet Menu Toggle (< 768px) -->
            <button
              type="button"
              @click="mobileMenuOpen = !mobileMenuOpen"
              class="md:hidden ios-tap inline-flex items-center justify-center w-10 h-10 sm:w-11 sm:h-11 rounded-xl text-zinc-700 dark:text-zinc-200 hover:bg-black/[0.05] dark:hover:bg-white/[0.08]"
              :aria-expanded="mobileMenuOpen"
              :aria-label="mobileMenuOpen ? t('收起菜单', 'Close menu') : t('打开菜单', 'Open menu')"
            >
              <X v-if="mobileMenuOpen" class="w-[18px] h-[18px]" :stroke-width="1.5" />
              <Menu v-else class="w-[18px] h-[18px]" :stroke-width="1.5" />
            </button>
          </div>
        </div>

        <!-- Mobile / Tablet Backdrop & Menu (< 768px; auto-closes on backdrop tap or tab switch) -->
        <div
          v-if="mobileMenuOpen"
          @click="mobileMenuOpen = false"
          class="md:hidden fixed inset-0 top-12 z-30 bg-black/25 backdrop-blur-[1px]"
        />
        <nav
          v-if="mobileMenuOpen"
          class="md:hidden relative z-40 pb-3 pt-2.5 border-t border-black/[0.06] dark:border-white/[0.08] space-y-2.5"
          :aria-label="t('移动端主导航', 'Mobile Navigation')"
        >
          <slot name="mobile-menu-extra" :close="() => (mobileMenuOpen = false)" />
          <div class="flex flex-wrap gap-2">
            <button
              v-if="showRefreshButton"
              type="button"
              @click="mobileMenuOpen = false; emit('refresh')"
              class="inline-flex items-center gap-1.5 min-h-[40px] px-3 rounded-xl text-xs font-semibold whitespace-nowrap bg-black/[0.05] dark:bg-white/[0.08] text-zinc-800 dark:text-zinc-100"
            >
              <RefreshCw class="w-3.5 h-3.5" :stroke-width="1.5" :class="{ 'animate-spin': isRefreshing }" />
              <span>{{ t('刷新', 'Refresh') }}</span>
            </button>
            <button
              v-if="showBookmarksButton"
              type="button"
              @click="mobileMenuOpen = false; emit('open-bookmarks')"
              class="inline-flex items-center gap-1.5 min-h-[40px] px-3 rounded-xl text-xs font-semibold whitespace-nowrap bg-black/[0.05] dark:bg-white/[0.08] text-zinc-800 dark:text-zinc-100"
            >
              <Bookmark class="w-3.5 h-3.5" :stroke-width="1.5" />
              <span>{{ t('阅读库', 'Library') }} ({{ bookmarkCount ?? 0 }})</span>
            </button>
            <button
              v-if="showHistoryButton"
              type="button"
              @click="mobileMenuOpen = false; emit('open-history')"
              class="inline-flex items-center gap-1.5 min-h-[40px] px-3 rounded-xl text-xs font-semibold whitespace-nowrap bg-black/[0.05] dark:bg-white/[0.08] text-zinc-800 dark:text-zinc-100"
            >
              <History class="w-3.5 h-3.5" :stroke-width="1.5" />
              <span>{{ t('归档', 'Archive') }}</span>
            </button>
            <button
              type="button"
              @click="emit('toggle-dark')"
              class="inline-flex items-center gap-1.5 min-h-[40px] px-3 rounded-xl text-xs font-semibold whitespace-nowrap bg-black/[0.05] dark:bg-white/[0.08] text-zinc-800 dark:text-zinc-100"
            >
              <Sun v-if="isDark" class="w-3.5 h-3.5 text-amber-400" :stroke-width="1.5" />
              <Moon v-else class="w-3.5 h-3.5" :stroke-width="1.5" />
              <span>{{ isDark ? t('浅色', 'Light') : t('深色', 'Dark') }}</span>
            </button>
            <button
              v-if="activePage === 'briefing'"
              type="button"
              @click="cycleMarketColorMode()"
              class="inline-flex items-center gap-1.5 min-h-[40px] px-3 rounded-xl text-xs font-semibold whitespace-nowrap bg-black/[0.05] dark:bg-white/[0.08] text-zinc-800 dark:text-zinc-100"
            >
              <span>{{ marketColorLabel }}</span>
            </button>
            <button
              v-if="showAuthButton"
              type="button"
              @click="mobileMenuOpen = false; emit('open-auth')"
              class="inline-flex items-center gap-1.5 min-h-[40px] px-3 rounded-xl text-xs font-semibold whitespace-nowrap"
              :class="effectiveUser ? 'bg-emerald-500/12 text-emerald-700 dark:text-emerald-300' : 'bg-[#007AFF] text-white'"
            >
              <User class="w-3.5 h-3.5" :stroke-width="1.5" />
              <span>{{ effectiveUser ? (effectiveUser.display_name || effectiveUser.username) : t('登录', 'Sign In') }}</span>
            </button>
          </div>

          <!-- Low-frequency items collapsed to clean small text links at bottom of menu -->
          <div class="pt-2 border-t border-black/[0.05] dark:border-white/[0.07] flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-zinc-500 dark:text-zinc-400">
            <a href="./help.html" @click="mobileMenuOpen = false" class="hover:text-zinc-900 dark:hover:text-white">{{ t('使用帮助', 'Help') }}</a>
            <button type="button" @click="mobileMenuOpen = false; feedbackTab = 'submit'; feedbackOpen = true" class="hover:text-zinc-900 dark:hover:text-white">{{ t('意见反馈', 'Feedback') }}</button>
            <a href="./about.html" @click="mobileMenuOpen = false" class="hover:text-zinc-900 dark:hover:text-white">{{ t('关于镜信', 'About') }}</a>
            <a v-if="isAdminRole(effectiveUser?.role)" href="./admin.html" @click="mobileMenuOpen = false" class="hover:text-zinc-900 dark:hover:text-white">{{ t('管理后台', 'Admin Console') }}</a>
            <a v-if="isAdminRole(effectiveUser?.role) && !isAndroidAppShell()" href="./android-dev.html" @click="mobileMenuOpen = false" class="hover:text-zinc-900 dark:hover:text-white">{{ t('安卓调试', 'Android Dev') }}</a>
          </div>
        </nav>
      </div>
    </header>

    <main
      id="main-content"
      class="flex-1 w-full mx-auto px-2.5 sm:px-5 pt-2 sm:pt-3 pb-24 md:pb-8"
      :class="containerWidthClass"
    >
      <slot />
    </main>

    <!-- Single-line minimal desktop footer (hidden on mobile & briefing feed pages to stay clutter-free) -->
    <footer
      v-if="activePage !== 'briefing'"
      class="hidden md:block border-t border-black/[0.06] dark:border-white/[0.08] bg-white/80 dark:bg-[#1C1C1E]/80 mt-8"
    >
      <div class="mx-auto px-5 py-3 text-xs text-zinc-500 dark:text-zinc-400 flex items-center justify-between gap-2" :class="containerWidthClass">
        <span>{{ t('镜信 · 北京时间展示', 'MirrorBrief · Asia/Shanghai') }}</span>
        <nav class="flex items-center gap-4 shrink-0" :aria-label="t('页脚链接', 'Footer Links')">
          <a href="./about.html" class="hover:text-zinc-900 dark:hover:text-white">{{ t('关于镜信', 'About') }}</a>
          <a href="./privacy.html" class="hover:text-zinc-900 dark:hover:text-white">{{ t('隐私', 'Privacy') }}</a>
          <a href="./terms.html" class="hover:text-zinc-900 dark:hover:text-white">{{ t('协议', 'Terms') }}</a>
          <a href="./help.html" class="hover:text-zinc-900 dark:hover:text-white">{{ t('使用帮助', 'Help') }}</a>
          <button type="button" @click="feedbackTab = 'submit'; feedbackOpen = true" class="hover:text-zinc-900 dark:hover:text-white">
            {{ t('意见反馈', 'Feedback') }}
          </button>
        </nav>
      </div>
    </footer>

    <!-- Built-in Feedback Drawer / Sheet -->
    <div
      v-if="feedbackOpen"
      tabindex="-1"
      class="ios-sheet-backdrop p-0 sm:p-4"
      role="dialog"
      aria-modal="true"
      @click.self="feedbackOpen = false"
      @keydown.esc="feedbackOpen = false"
    >
      <div class="ios-sheet-panel bg-white dark:bg-[#1C1C1E] p-5 space-y-3.5 text-xs sm:text-sm max-h-[88vh] overflow-y-auto">
        <div class="w-9 h-1 rounded-full bg-zinc-300 dark:bg-zinc-600 mx-auto sm:hidden" />
        <div class="flex items-center justify-between">
          <h3 class="font-bold text-zinc-900 dark:text-white flex items-center gap-1.5">
            <MessageSquare class="w-4 h-4 text-[#007AFF]" :stroke-width="1.5" />
            <span>{{ t('意见反馈与服务台', 'Feedback Center') }}</span>
          </h3>
          <button
            type="button"
            @click="feedbackOpen = false"
            class="w-11 h-11 -mr-2 rounded-xl inline-flex items-center justify-center text-zinc-400 hover:text-zinc-700 dark:hover:text-white"
            :aria-label="t('关闭', 'Close')"
          >
            <X class="w-5 h-5" :stroke-width="1.5" />
          </button>
        </div>

        <!-- Official Notice & Channels configured by Admin -->
        <div
          v-if="siteSettings.feedback_notice || siteSettings.feedback_contact_wechat || siteSettings.feedback_contact_email || siteSettings.feedback_contact_group"
          class="rounded-xl border border-blue-200/70 dark:border-blue-800/70 bg-blue-50/50 dark:bg-blue-950/25 p-3 space-y-1.5 text-xs"
        >
          <p v-if="siteSettings.feedback_notice" class="text-zinc-700 dark:text-zinc-200 leading-relaxed">
            {{ siteSettings.feedback_notice }}
          </p>
          <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-zinc-600 dark:text-zinc-300">
            <span v-if="siteSettings.feedback_contact_wechat">{{ t('客服微信：', 'WeChat: ') }}<strong class="select-all">{{ siteSettings.feedback_contact_wechat }}</strong></span>
            <span v-if="siteSettings.feedback_contact_email">{{ t('官方邮箱：', 'Email: ') }}<strong class="select-all">{{ siteSettings.feedback_contact_email }}</strong></span>
            <span v-if="siteSettings.feedback_contact_group">{{ t('交流社群：', 'Community: ') }}<strong class="select-all">{{ siteSettings.feedback_contact_group }}</strong></span>
          </div>
          <img
            v-if="siteSettings.feedback_contact_qr_url && /^(https?:\/\/|\/|\.\.?\/)/.test(siteSettings.feedback_contact_qr_url)"
            :src="siteSettings.feedback_contact_qr_url"
            alt="Contact QR"
            class="mt-1.5 w-24 h-24 rounded-lg border border-black/10 object-contain bg-white"
          />
        </div>

        <!-- Tabs: Submit vs My History -->
        <div class="ios-segmented w-full flex">
          <button
            type="button"
            @click="feedbackTab = 'submit'"
            class="flex-1 min-h-[36px] ios-segmented-btn"
            :class="feedbackTab === 'submit' ? 'ios-segmented-btn-active' : 'text-zinc-600 dark:text-zinc-400'"
          >
            {{ t('提交反馈', 'Submit') }}
          </button>
          <button
            type="button"
            @click="feedbackTab = 'history'; refreshFeedbackModalData()"
            class="flex-1 min-h-[36px] ios-segmented-btn"
            :class="feedbackTab === 'history' ? 'ios-segmented-btn-active' : 'text-zinc-600 dark:text-zinc-400'"
          >
            {{ t('我的反馈记录', 'My Feedback') }} ({{ myFeedbackList.length }})
          </button>
        </div>

        <template v-if="feedbackTab === 'submit'">
          <div
            v-if="siteSettings.feedback_enabled === false"
            class="rounded-xl border border-amber-200 dark:border-amber-800 bg-amber-50/70 dark:bg-amber-950/30 p-3.5 text-xs text-amber-800 dark:text-amber-200 leading-relaxed"
          >
            {{ t('在线表单维护中，请通过上方微信、邮箱或交流社群联系编辑团队，或在「我的反馈记录」查看历史处理进展。', 'Online submissions are paused temporarily. Please use our direct contacts above or view past tickets.') }}
          </div>

          <form v-else @submit.prevent="submitFeedbackForm" class="space-y-2.5">
            <div class="ios-segmented w-full flex">
              <button
                v-for="opt in ([
                  { id: 'bug', label: t('页面问题', 'Bug') },
                  { id: 'data', label: t('数据纠错', 'Data') },
                  { id: 'suggestion', label: t('功能建议', 'Idea') },
                ] as const)"
                :key="opt.id"
                type="button"
                @click="feedbackCat = opt.id"
                class="flex-1 min-h-[36px] ios-segmented-btn"
                :class="feedbackCat === opt.id ? 'ios-segmented-btn-active' : 'text-zinc-600 dark:text-zinc-400'"
              >
                {{ opt.label }}
              </button>
            </div>

            <input
              v-model="feedbackContact"
              type="text"
              :placeholder="t('联系方式（选填）', 'Contact (optional)')"
              class="w-full h-11 px-3 rounded-xl bg-[#F5F5F7] dark:bg-[#2C2C2E] text-xs text-zinc-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-[#007AFF]"
            />

            <textarea
              v-model="feedbackContent"
              rows="4"
              :placeholder="t('描述问题或建议...', 'Describe the issue or suggestion...')"
              class="w-full p-3 rounded-xl bg-[#F5F5F7] dark:bg-[#2C2C2E] text-xs text-zinc-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-[#007AFF]"
            />

            <div
              v-if="feedbackStatus"
              class="rounded-xl px-3 py-2 text-xs flex items-center justify-between gap-2"
              :class="feedbackStatus.ok ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300' : 'bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-300'"
            >
              <span>{{ feedbackStatus.text }}</span>
              <button
                v-if="feedbackStatus.ok"
                type="button"
                @click="feedbackTab = 'history'"
                class="font-semibold underline shrink-0"
              >
                {{ t('查看记录', 'View') }}
              </button>
            </div>

            <div class="flex justify-end gap-2 pt-1 pb-[env(safe-area-inset-bottom)]">
              <button
                type="button"
                @click="feedbackOpen = false"
                class="min-h-[44px] px-4 rounded-xl bg-[#F5F5F7] dark:bg-[#2C2C2E] text-xs font-medium text-zinc-600 dark:text-zinc-300"
              >
                {{ t('取消', 'Cancel') }}
              </button>
              <button
                type="submit"
                :disabled="feedbackBusy"
                class="min-h-[44px] px-5 rounded-xl bg-[#007AFF] text-white text-xs font-semibold hover:bg-[#0066D6] disabled:opacity-60"
              >
                {{ feedbackBusy ? t('提交中...', 'Submitting...') : t('提交', 'Submit') }}
              </button>
            </div>
          </form>
        </template>

        <template v-else>
          <div class="space-y-2.5 max-h-[52vh] overflow-y-auto pb-[env(safe-area-inset-bottom)]">
            <div v-if="loadingMyFeedback" class="py-6 text-center text-xs text-zinc-400">
              {{ t('正在同步我的反馈记录...', 'Loading feedback history...') }}
            </div>
            <div v-else-if="myFeedbackList.length === 0" class="py-8 text-center text-xs text-zinc-400 space-y-1">
              <CheckCircle2 class="w-5 h-5 mx-auto text-zinc-300 dark:text-zinc-600" />
              <p>{{ t('暂未提交过反馈记录', 'No feedback records yet') }}</p>
            </div>
            <article
              v-else
              v-for="item in myFeedbackList"
              :key="item.id"
              class="rounded-xl border border-black/[0.06] dark:border-white/[0.08] bg-[#F5F5F7]/70 dark:bg-[#2C2C2E]/70 p-3 space-y-1.5 text-xs"
            >
              <div class="flex items-center justify-between gap-2">
                <div class="flex items-center gap-1.5">
                  <span class="px-1.5 py-0.5 rounded bg-black/[0.06] dark:bg-white/[0.08] font-medium text-zinc-700 dark:text-zinc-200">
                    {{ feedbackCatLabel(item.category) }}
                  </span>
                  <span class="px-1.5 py-0.5 rounded font-semibold" :class="feedbackStatusBadge(item.status).cls">
                    {{ feedbackStatusBadge(item.status).label }}
                  </span>
                </div>
                <span class="text-[11px] font-mono text-zinc-400">{{ formatShanghaiDateTime(item.created_at, false) }}</span>
              </div>
              <p class="text-zinc-800 dark:text-zinc-100 leading-relaxed whitespace-pre-wrap">{{ item.content }}</p>
              <div
                v-if="item.admin_reply"
                class="rounded-lg border border-emerald-200 dark:border-emerald-800/80 bg-emerald-50/70 dark:bg-emerald-950/30 px-2.5 py-2 space-y-0.5"
              >
                <div class="text-[11px] font-semibold text-emerald-700 dark:text-emerald-300 flex items-center justify-between">
                  <span>{{ t('官方回复', 'Official Reply') }}</span>
                  <span v-if="item.replied_at" class="font-mono font-normal opacity-80">{{ formatShanghaiDateTime(item.replied_at, false) }}</span>
                </div>
                <p class="text-zinc-700 dark:text-zinc-200 leading-relaxed">{{ item.admin_reply }}</p>
              </div>
            </article>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>
