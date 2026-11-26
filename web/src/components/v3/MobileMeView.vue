<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  BarChart3,
  Bell,
  Calendar,
  ChevronDown,
  ChevronRight,
  Cloud,
  Copy,
  Filter,
  GitBranch,
  HelpCircle,
  CalendarRange,
  Layers,
  LogOut,
  Moon,
  RefreshCw,
  Sun,
  Target,
  Trash2,
  TrendingUp,
  User,
} from 'lucide-vue-next'
import OdometerNumber from '../OdometerNumber.vue'
import SmartTime from '../SmartTime.vue'
import UserAvatar from '../UserAvatar.vue'
import type { AuthUser } from '../../core/auth'
import { appLang, t } from '../../core/i18n'
import {
  feedDensity,
  isRedUp,
  setFeedDensity,
  toggleMarketColorMode,
  triggerHaptic,
} from '../../core/uiPrefs'
import type { MorningBriefSummary } from '../../core/v3Logic'
import type { WorkbenchTab } from '../../core/types'

const props = defineProps<{
  authUser: AuthUser | null
  userAvatar?: string | null
  lastSyncedAt?: string | null
  cloudSyncBusy?: boolean
  isDark: boolean
  isAndroidApp: boolean
  mobilePushEnabled: boolean
  hideReprints: boolean
  watchlistCount: number
  bookmarkCount: number
  researchNotesCount: number
  readLaterCount: number
  todayReadCount: number
  batchReadCount?: number
  batchTotalCount?: number
  historicalReadCount?: number
  morningBrief?: MorningBriefSummary | null
  isHistoryMode: boolean
  historyDisplay?: string | null
  hasUnreadWeekly?: boolean
  storylinesCount: number
  calendarCount: number
  techToolsCount: number
  watchNewCount?: number
  portfolioHitCount?: number
  upcoming48hCount?: number
  nowMs: number
}>()

const emit = defineEmits<{
  (e: 'open-auth'): void
  (e: 'open-avatar-picker'): void
  (e: 'logout'): void
  (e: 'sync-now'): void
  (e: 'switch-tab', tab: WorkbenchTab): void
  (e: 'open-finance-portfolio'): void
  (e: 'open-bookmarks', subTab?: 'saved' | 'read_later' | 'notes'): void
  (e: 'open-qa'): void
  (e: 'open-weekly-report'): void
  (e: 'open-onboarding'): void
  (e: 'open-watchlist-manager'): void
  (e: 'open-feedback'): void
  (e: 'toggle-mobile-push'): void
  (e: 'toggle-hide-reprints', val: boolean): void
  (e: 'toggle-dark'): void
  (e: 'toggle-lang'): void
  (e: 'market-color-changed', isRedUpNow: boolean): void
  (e: 'copy-digest'): void
  (e: 'request-clear-local'): void
}>()

function cycleMarketColors() {
  triggerHaptic(10)
  const nextMode = toggleMarketColorMode()
  emit('market-color-changed', nextMode === 'cn')
}

const marketColorLabel = computed(() =>
  isRedUp() ? t('红涨绿跌', 'Red Up') : t('绿涨红跌', 'Green Up'),
)

const userDisplayName = computed(() => {
  if (!props.authUser) return t('未登录 · 本机模式', 'Guest · Local')
  return props.authUser.display_name || props.authUser.username
})
</script>

<template>
  <section
    class="max-w-xl mx-auto space-y-3"
    :aria-label="t('我的', 'Me')"
    data-testid="mobile-me-page"
  >
    <!-- 1. Compact Account & One-Line Stats Card (<= 145px) -->
    <div class="ios-card p-3.5 space-y-3">
      <div class="flex items-center justify-between gap-3">
        <div class="flex items-center gap-3 min-w-0">
          <button
            type="button"
            @click="authUser ? emit('open-avatar-picker') : emit('open-auth')"
            class="ios-tap rounded-full shrink-0"
            :aria-label="authUser ? t('更换头像', 'Change avatar') : t('登录账号', 'Sign in')"
            data-testid="mobile-me-avatar-btn"
          >
            <UserAvatar
              :avatar="userAvatar || authUser?.avatar"
              :username="authUser?.username"
              :role="authUser?.role"
              size="lg"
              :editable="Boolean(authUser)"
            />
          </button>
          <div class="min-w-0">
            <div class="flex items-center gap-1.5">
              <h1 class="text-[16px] font-semibold text-zinc-950 dark:text-white truncate">
                {{ userDisplayName }}
              </h1>
              <Cloud v-if="authUser" class="w-3.5 h-3.5 text-emerald-500 shrink-0" :stroke-width="1.5" />
            </div>
            <p class="text-[12px] text-zinc-500 dark:text-zinc-400 truncate tabular-nums">
              <template v-if="authUser && lastSyncedAt">
                {{ t('已同步 · ', 'Synced · ') }}<SmartTime :iso="lastSyncedAt" :now-ms="nowMs" />
              </template>
              <template v-else-if="authUser">
                {{ t('云端加密已开启', 'Encrypted Cloud Sync') }}
              </template>
              <template v-else>
                {{ t('登录开启多端同步', 'Sign in to sync across devices') }}
              </template>
            </p>
          </div>
        </div>

        <div class="flex items-center gap-1.5 shrink-0">
          <template v-if="authUser">
            <button
              type="button"
              @click="triggerHaptic(10); emit('sync-now')"
              :disabled="cloudSyncBusy"
              class="ios-tap inline-flex items-center justify-center w-10 h-10 rounded-xl bg-[#F2F2F7] dark:bg-[#2C2C2E] text-zinc-700 dark:text-zinc-200 disabled:opacity-50"
              :aria-label="t('立即同步', 'Sync now')"
            >
              <RefreshCw class="w-4 h-4" :stroke-width="1.5" :class="{ 'animate-spin': cloudSyncBusy }" />
            </button>
            <button
              type="button"
              @click="emit('logout')"
              class="ios-tap inline-flex items-center justify-center w-10 h-10 rounded-xl bg-[#F2F2F7] dark:bg-[#2C2C2E] text-zinc-500 hover:text-rose-500"
              :aria-label="t('退出登录', 'Sign out')"
            >
              <LogOut class="w-4 h-4" :stroke-width="1.5" />
            </button>
          </template>
          <button
            v-else
            type="button"
            @click="emit('open-auth')"
            class="ios-tap px-3.5 min-h-[38px] rounded-xl bg-[#007AFF] text-white text-xs font-semibold whitespace-nowrap"
          >
            {{ t('登录', 'Sign In') }}
          </button>
        </div>
      </div>

      <!-- Compact Single-Row Personal Stats -> Opens Unified Library / Watchlist -->
      <div class="grid grid-cols-4 pt-2.5 border-t border-black/[0.06] dark:border-white/[0.08] text-center">
        <button type="button" @click="emit('open-bookmarks', 'saved')" class="ios-tap py-1 flex flex-col items-center">
          <span class="text-[15px] font-bold text-zinc-950 dark:text-white tabular-nums"><OdometerNumber :value="bookmarkCount" /></span>
          <span class="text-[11px] text-zinc-500">{{ t('收藏', 'Saved') }}</span>
        </button>
        <button type="button" @click="emit('open-watchlist-manager')" class="ios-tap py-1 flex flex-col items-center">
          <span class="text-[15px] font-bold text-zinc-950 dark:text-white tabular-nums"><OdometerNumber :value="watchlistCount" /></span>
          <span class="text-[11px] text-zinc-500">{{ t('关注', 'Watch') }}</span>
        </button>
        <button type="button" @click="emit('open-bookmarks', 'notes')" class="ios-tap py-1 flex flex-col items-center">
          <span class="text-[15px] font-bold text-zinc-950 dark:text-white tabular-nums"><OdometerNumber :value="researchNotesCount" /></span>
          <span class="text-[11px] text-zinc-500">{{ t('笔记', 'Notes') }}</span>
        </button>
        <button type="button" @click="emit('open-bookmarks', 'read_later')" class="ios-tap py-1 flex flex-col items-center">
          <span class="text-[15px] font-bold text-zinc-950 dark:text-white tabular-nums"><OdometerNumber :value="readLaterCount" /></span>
          <span class="text-[11px] text-zinc-500">{{ t('深读', 'Later') }}</span>
        </button>
      </div>
    </div>

    <!-- 1.2 Return-Visit Tracking Pulse Card + Morning Brief -->
    <div class="ios-card p-3 space-y-2.5" data-testid="mobile-tracking-pulse">
      <div class="flex flex-wrap items-center justify-between gap-1 text-xs">
        <span class="inline-flex items-center gap-1.5 font-semibold text-zinc-900 dark:text-white">
          <Target class="w-3.5 h-3.5 text-[#007AFF] shrink-0" :stroke-width="1.75" />
          <span>{{ t('我的追踪动态', 'My Tracking Pulse') }}</span>
        </span>
        <span class="text-[11px] text-zinc-500 dark:text-zinc-400 tabular-nums">
          {{ t(`本批 ${batchReadCount ?? todayReadCount}/${batchTotalCount ?? '—'} · 累计深读 ${historicalReadCount ?? todayReadCount} 篇`, `Batch ${batchReadCount ?? todayReadCount}/${batchTotalCount ?? '—'} · Total ${historicalReadCount ?? todayReadCount}`) }}
        </span>
      </div>
      <div class="grid grid-cols-3 gap-1.5 text-center text-xs">
        <button
          type="button"
          @click="emit('switch-tab', 'today')"
          class="ios-surface-2 py-2 px-1 rounded-xl flex flex-col items-center gap-0.5 active:opacity-80"
        >
          <span class="text-[15px] font-bold text-[#007AFF] tabular-nums">{{ watchNewCount ?? 0 }}</span>
          <span class="text-[10px] text-zinc-500 truncate max-w-full">{{ t('关注新进展', 'Watch Hits') }}</span>
        </button>
        <button
          type="button"
          @click="emit('open-finance-portfolio')"
          class="ios-surface-2 py-2 px-1 rounded-xl flex flex-col items-center gap-0.5 active:opacity-80"
        >
          <span class="text-[15px] font-bold text-indigo-600 dark:text-indigo-400 tabular-nums">{{ portfolioHitCount ?? 0 }}</span>
          <span class="text-[10px] text-zinc-500 truncate max-w-full">{{ t('持仓传导', 'Portfolio') }}</span>
        </button>
        <button
          type="button"
          @click="emit('switch-tab', 'calendar')"
          class="ios-surface-2 py-2 px-1 rounded-xl flex flex-col items-center gap-0.5 active:opacity-80"
        >
          <span class="text-[15px] font-bold text-amber-600 dark:text-amber-400 tabular-nums">{{ upcoming48hCount ?? 0 }}</span>
          <span class="text-[10px] text-zinc-500 truncate max-w-full">{{ t('48h 催化', '48h Alerts') }}</span>
        </button>
      </div>

      <!-- Personalized Pre-Market Morning Brief Card -->
      <div
        v-if="morningBrief && (morningBrief.portfolioHits.length > 0 || morningBrief.upcomingCatalysts.length > 0)"
        class="rounded-xl bg-amber-50/70 dark:bg-amber-950/25 border border-amber-200/80 dark:border-amber-900/60 p-2.5 space-y-1.5 text-[11px]"
      >
        <div class="flex items-center justify-between gap-2">
          <span class="inline-flex items-center gap-1 font-bold text-amber-900 dark:text-amber-200">
            <Sun class="w-3.5 h-3.5 shrink-0" :stroke-width="1.75" />
            <span>{{ t('盘前个人早报', 'Personal Pre-Market Brief') }}</span>
          </span>
          <button
            type="button"
            @click="emit('open-auth')"
            class="text-[#007AFF] dark:text-[#0A84FF] font-semibold hover:underline"
          >
            {{ authUser?.email ? t('每日 08:00 推送已绑定', '08:00 Digest Ready') : t('绑定邮箱接收推送 →', 'Bind Email →') }}
          </button>
        </div>
        <div v-for="ph in morningBrief.portfolioHits" :key="ph.id" class="text-zinc-700 dark:text-zinc-200 truncate">
          • <span class="font-semibold">{{ String(ph.tags[0] || '').replace(/^[\s·•:：]+|[\s·•:：]+$/g, '') }}</span>：{{ ph.title }}
        </div>
        <div v-for="cal in morningBrief.upcomingCatalysts" :key="cal.id" class="inline-flex items-center gap-1 text-amber-800 dark:text-amber-300 truncate max-w-full">
          <Calendar class="w-3 h-3 shrink-0" :stroke-width="1.75" />
          <span class="truncate">{{ cal.title }}</span>
        </div>
      </div>
    </div>

    <!-- 1.5 Secondary Research Modules Quick Entry (1 tap from Me, zero topbar clutter) -->
    <div class="ios-card px-2 py-1.5 grid grid-cols-3 gap-1 text-[12px] font-medium">
      <button
        type="button"
        @click="emit('switch-tab', 'calendar')"
        class="ios-tap min-h-[44px] px-2 rounded-xl flex items-center justify-center gap-1.5 text-zinc-800 dark:text-zinc-100 active:bg-black/[0.04]"
      >
        <Calendar class="w-4 h-4 text-[#007AFF]" :stroke-width="1.5" />
        <span class="truncate">{{ t('日程前瞻', 'Outlook') }}</span>
      </button>
      <button
        type="button"
        @click="emit('switch-tab', 'tracking')"
        class="ios-tap min-h-[44px] px-2 rounded-xl flex items-center justify-center gap-1.5 text-zinc-800 dark:text-zinc-100 active:bg-black/[0.04]"
      >
        <GitBranch class="w-4 h-4 text-[#007AFF]" :stroke-width="1.5" />
        <span class="truncate">{{ t('事件追踪', 'Tracking') }}</span>
      </button>
      <button
        type="button"
        @click="emit('switch-tab', 'weekly')"
        class="ios-tap relative min-h-[44px] px-2 rounded-xl flex items-center justify-center gap-1.5 text-zinc-800 dark:text-zinc-100 active:bg-black/[0.04]"
        data-testid="me-weekly-digest-btn"
      >
        <CalendarRange class="w-4 h-4 text-[#007AFF]" :stroke-width="1.5" />
        <span class="truncate">{{ t('每周盘点', 'Weekly') }}</span>
        <span
          v-if="hasUnreadWeekly"
          class="w-1.5 h-1.5 rounded-full bg-rose-500 shrink-0"
          :aria-label="t('新刊未读', 'New weekly issue')"
        />
      </button>
    </div>

    <!-- 2. iOS Grouped Settings List (Single clean rounded list with hairline dividers, no card-in-card) -->
    <div class="ios-card divide-y divide-black/[0.06] dark:divide-white/[0.08] overflow-hidden">
      <button
        type="button"
        @click="emit('open-weekly-report')"
        class="w-full min-h-[48px] px-4 flex items-center justify-between gap-3 active:bg-black/[0.03] dark:active:bg-white/[0.04]"
      >
        <span class="inline-flex items-center gap-3 text-[15px] font-medium text-zinc-900 dark:text-white">
          <BarChart3 class="w-[18px] h-[18px] text-[#007AFF] shrink-0" :stroke-width="1.5" />
          <span>{{ t('视野分布与信息茧房体检', 'Diversity Check') }}</span>
        </span>
        <span class="inline-flex items-center gap-1 text-[12px] text-zinc-400 tabular-nums shrink-0">
          <span>{{ t(`已读 ${batchReadCount ?? todayReadCount}`, `${batchReadCount ?? todayReadCount} read`) }}</span>
          <ChevronRight class="w-4 h-4" :stroke-width="1.5" />
        </span>
      </button>

      <button
        type="button"
        @click="emit('open-watchlist-manager')"
        class="w-full min-h-[48px] px-4 flex items-center justify-between gap-3 active:bg-black/[0.03] dark:active:bg-white/[0.04]"
      >
        <span class="inline-flex items-center gap-3 text-[15px] font-medium text-zinc-900 dark:text-white">
          <HelpCircle class="w-[18px] h-[18px] text-[#007AFF] shrink-0" :stroke-width="1.5" />
          <span>{{ t('关注主题包与管理', 'Watchlist & Packs') }}</span>
        </span>
        <ChevronRight class="w-4 h-4 text-zinc-400 shrink-0" :stroke-width="1.5" />
      </button>

      <div class="w-full min-h-[48px] px-4 flex items-center justify-between gap-3">
        <span class="inline-flex items-center gap-3 text-[15px] font-medium text-zinc-900 dark:text-white">
          <Layers class="w-[18px] h-[18px] text-[#007AFF] shrink-0" :stroke-width="1.5" />
          <span>{{ t('信息流密度', 'Card Density') }}</span>
        </span>
        <div class="ios-segmented shrink-0">
          <button
            type="button"
            @click="triggerHaptic(10); setFeedDensity('compact')"
            class="ios-segmented-btn min-h-[30px] px-2.5"
            :class="feedDensity === 'compact' ? 'ios-segmented-btn-active' : 'text-zinc-500 dark:text-zinc-400'"
          >
            {{ t('紧凑', 'Compact') }}
          </button>
          <button
            type="button"
            @click="triggerHaptic(10); setFeedDensity('standard')"
            class="ios-segmented-btn min-h-[30px] px-2.5"
            :class="feedDensity === 'standard' ? 'ios-segmented-btn-active' : 'text-zinc-500 dark:text-zinc-400'"
          >
            {{ t('标准', 'Standard') }}
          </button>
        </div>
      </div>

      <button
        type="button"
        @click="triggerHaptic(10); emit('toggle-mobile-push')"
        class="w-full min-h-[48px] px-4 flex items-center justify-between gap-3 active:bg-black/[0.03] dark:active:bg-white/[0.04]"
      >
        <span class="inline-flex items-center gap-3 text-[15px] font-medium text-zinc-900 dark:text-white">
          <Bell class="w-[18px] h-[18px] text-[#007AFF] shrink-0" :stroke-width="1.5" />
          <span>{{ t('重要快讯推送', 'Breaking Push') }}</span>
        </span>
        <span
          class="text-[13px] font-medium shrink-0"
          :class="mobilePushEnabled ? 'text-emerald-600 dark:text-emerald-400' : 'text-zinc-400'"
        >
          {{ mobilePushEnabled ? t('已开启', 'On') : t('已关闭', 'Off') }}
        </span>
      </button>

      <button
        type="button"
        @click="triggerHaptic(10); emit('toggle-hide-reprints', !hideReprints)"
        class="w-full min-h-[48px] px-4 flex items-center justify-between gap-3 active:bg-black/[0.03] dark:active:bg-white/[0.04]"
      >
        <span class="inline-flex items-center gap-3 text-[15px] font-medium text-zinc-900 dark:text-white">
          <Filter class="w-[18px] h-[18px] text-zinc-500 shrink-0" :stroke-width="1.5" />
          <span>{{ t('合并相似报道', 'Merge Similar Reports') }}</span>
        </span>
        <span class="text-[13px] text-zinc-500 shrink-0">
          {{ hideReprints ? t('开启', 'On') : t('关闭', 'Off') }}
        </span>
      </button>

      <button
        type="button"
        @click="cycleMarketColors()"
        class="w-full min-h-[48px] px-4 flex items-center justify-between gap-3 active:bg-black/[0.03] dark:active:bg-white/[0.04]"
      >
        <span class="inline-flex items-center gap-3 text-[15px] font-medium text-zinc-900 dark:text-white">
          <TrendingUp class="w-[18px] h-[18px] text-zinc-500 shrink-0" :stroke-width="1.5" />
          <span>{{ t('涨跌配色', 'Market Colors') }}</span>
        </span>
        <span class="text-[13px] text-zinc-500 shrink-0">{{ marketColorLabel }}</span>
      </button>

      <button
        type="button"
        @click="triggerHaptic(10); emit('toggle-dark')"
        class="w-full min-h-[48px] px-4 flex items-center justify-between gap-3 active:bg-black/[0.03] dark:active:bg-white/[0.04]"
      >
        <span class="inline-flex items-center gap-3 text-[15px] font-medium text-zinc-900 dark:text-white">
          <Sun v-if="isDark" class="w-[18px] h-[18px] text-amber-400 shrink-0" :stroke-width="1.5" />
          <Moon v-else class="w-[18px] h-[18px] text-zinc-500 shrink-0" :stroke-width="1.5" />
          <span>{{ t('外观', 'Appearance') }}</span>
        </span>
        <span class="text-[13px] text-zinc-500 shrink-0">{{ isDark ? t('深色', 'Dark') : t('浅色', 'Light') }}</span>
      </button>
    </div>

    <!-- 3. Local Tools & Cache Actions (Zero export/import clutter) -->
    <div class="ios-card divide-y divide-black/[0.05] dark:divide-white/[0.06] overflow-hidden text-[14px]">
      <button
        type="button"
        @click="emit('copy-digest')"
        class="w-full min-h-[44px] px-4 flex items-center gap-3 text-zinc-700 dark:text-zinc-200 active:bg-black/[0.03]"
      >
        <Copy class="w-4 h-4 text-[#007AFF]" :stroke-width="1.5" />
        <span>{{ t('复制 30 秒速览日报', 'Copy 30s Digest') }}</span>
      </button>
      <button
        type="button"
        @click="emit('request-clear-local')"
        class="w-full min-h-[44px] px-4 flex items-center gap-3 text-rose-600 dark:text-rose-400 active:bg-rose-500/10"
      >
        <Trash2 class="w-4 h-4" :stroke-width="1.5" />
        <span>{{ t('清空本机数据…', 'Clear Local Data…') }}</span>
      </button>
    </div>

    <!-- 4. Low-Frequency Footer Links: Single 12px Gray Line (No cards, no icons, no borders) -->
    <div class="pt-1 pb-2 text-center text-[12px] text-zinc-400 dark:text-zinc-500 leading-relaxed">
      <a href="./about.html" class="hover:text-zinc-700 dark:hover:text-zinc-300">{{ t('关于', 'About') }}</a>
      <span class="mx-1.5">·</span>
      <a href="./help.html" class="hover:text-zinc-700 dark:hover:text-zinc-300">{{ t('使用帮助', 'Help') }}</a>
      <span class="mx-1.5">·</span>
      <a href="./privacy.html" class="hover:text-zinc-700 dark:hover:text-zinc-300">{{ t('隐私政策', 'Privacy') }}</a>
      <span class="mx-1.5">·</span>
      <a href="./terms.html" class="hover:text-zinc-700 dark:hover:text-zinc-300">{{ t('用户协议', 'Terms') }}</a>
      <span class="mx-1.5">·</span>
      <button type="button" @click="emit('open-feedback')" class="hover:text-zinc-700 dark:hover:text-zinc-300">
        {{ t('意见反馈', 'Feedback') }}
      </button>
    </div>
  </section>
</template>
