<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import {
  Activity,
  BarChart3,
  Bookmark,
  Briefcase,
  Calendar,
  CheckCircle2,
  ChevronRight,
  ExternalLink,
  Sparkles,
  Target,
  X,
} from 'lucide-vue-next'
import OdometerNumber from '../OdometerNumber.vue'
import SmartTime from '../SmartTime.vue'
import {
  pickBiText,
  stripMarkdownArtifacts,
  t,
  translateEntityName,
  translateMarketTag,
  translateSourceName,
} from '../../core/i18n'
import { parseTimestampMs } from '../../core/time'
import { normalizeExternalUrl } from '../../core/legacyAdapter'
import { marketDownTextClass, marketUpTextClass } from '../../core/uiPrefs'
import {
  countUpcomingCatalystsWithinHours,
  matchEventAgainstWatchlist,
  matchImpactAgainstPortfolio,
} from '../../core/v3Logic'
import type {
  CatalystEvent,
  EntityProfile,
  EventMarketImpact,
  InlineEventImpact,
  MajorTopicSpotlight,
  MarketQuoteItem,
  PortfolioConfig,
  SmartEvent,
  WatchlistItem,
} from '../../core/types'

const props = defineProps<{
  selectedEvent: SmartEvent | null
  selectedImpact?: InlineEventImpact | null
  isSelectedRead?: boolean
  isSelectedBookmarked?: boolean
  indices: MarketQuoteItem[]
  quotesUpdatedLabel?: string
  flashingTickers?: Record<string, 'up' | 'down'>
  entities: EntityProfile[]
  watchlist: WatchlistItem[]
  allEvents?: SmartEvent[]
  topics?: MajorTopicSpotlight[]
  calendarEvents?: CatalystEvent[]
  financeImpacts?: EventMarketImpact[]
  portfolio?: PortfolioConfig
  previousVisitedAt?: string | null
  previousSeenIds?: Set<string>
  todayReadCount: number
  batchReadCount?: number
  batchTotalCount?: number
  historicalReadCount?: number
  nowMs: number
}>()

const emit = defineEmits<{
  (e: 'close-detail'): void
  (e: 'toggle-read', ev: SmartEvent): void
  (e: 'mark-read', ev: SmartEvent): void
  (e: 'toggle-bookmark', ev: SmartEvent): void
  (e: 'open-qa', ev?: SmartEvent): void
  (e: 'select-entity', name: string): void
  (e: 'switch-tab', tab: 'finance' | 'today' | 'calendar'): void
  (e: 'open-finance-portfolio'): void
  (e: 'open-weekly-report'): void
}>()

const sortedSources = computed(() => {
  const list = [...(props.selectedEvent?.sources || [])]
  return list.sort((a, b) => {
    const ag = (a.url || '').includes('news.google.com/rss/articles/') ? 1 : 0
    const bg = (b.url || '').includes('news.google.com/rss/articles/') ? 1 : 0
    return ag - bg
  })
})

const primarySourceUrl = computed(() => {
  for (const s of sortedSources.value) {
    const u = normalizeExternalUrl(s.url)
    if (u) return u
  }
  return ''
})

function safeSourceHref(raw?: string | null): string {
  return normalizeExternalUrl(raw) || ''
}

const cleanSummary = computed(() => {
  const raw = props.selectedEvent?.fact_summary || ''
  return stripMarkdownArtifacts(raw.replace(/^【据关联报道\/尚未见官方披露确认】\s*/g, ''))
})

function fmtPct(lo: number, hi: number): string {
  const a = lo > 0 ? `+${lo}%` : `${lo}%`
  const b = hi > 0 ? `+${hi}%` : `${hi}%`
  return `${a}~${b}`
}

const watchMatchesSummary = computed(() => {
  const prevMs = props.previousVisitedAt ? parseTimestampMs(props.previousVisitedAt) : null
  const evList = props.allEvents || []
  const newWatchEvents = evList.filter((ev) => {
    const mr = matchEventAgainstWatchlist(ev, props.watchlist)
    if (!mr.matched) return false
    const ms = parseTimestampMs(ev.latest_reported_at || ev.latest_fact_update_at || ev.first_reported_at || ev.fetched_at)
    if (prevMs !== null && ms !== null) return ms > prevMs
    if (props.previousSeenIds && props.previousSeenIds.size > 0) return !props.previousSeenIds.has(ev.event_id)
    return ms !== null && props.nowMs - ms <= 24 * 3_600_000
  })
  const watchKws = props.watchlist.flatMap((w) => [w.label, ...(w.keywords || [])]).map((s) => s.trim().toLowerCase()).filter((s) => s.length >= 2)
  const hitTopics = (props.topics || []).filter((tp) => {
    const hay = `${tp.title} ${(tp.primary_orgs || []).join(' ')}`.toLowerCase()
    const kwHit = watchKws.some((kw) => hay.includes(kw))
    const entHit = (tp.entity_ids || []).some((eid) => props.watchlist.some((w) => w.entity_id === eid))
    return kwHit || entHit
  })
  return { events: newWatchEvents.length, topics: hitTopics.length }
})

const portfolioHitCount = computed(() => {
  if (!props.portfolio) return 0
  return (props.financeImpacts || []).filter((imp) => matchImpactAgainstPortfolio(imp, props.portfolio!).matched).length
})

const upcoming48hCatalysts = computed(() =>
  countUpcomingCatalystsWithinHours(props.calendarEvents || [], props.nowMs, 48),
)

// Dynamically rank hot entity profiles by today's event heat + 30d activity so active daily subjects rotate to top
const hotEntities = computed(() => {
  const countsByEid = new Map<string, number>()
  const countsByName = new Map<string, number>()
  for (const ev of props.allEvents || []) {
    for (const eid of ev.entity_ids || []) {
      countsByEid.set(eid, (countsByEid.get(eid) || 0) + 1)
    }
    for (const name of ev.entities || []) {
      const k = String(name).trim().toLowerCase()
      if (k) countsByName.set(k, (countsByName.get(k) || 0) + 1)
    }
  }
  return [...props.entities].sort((a, b) => {
    const scoreA =
      (countsByEid.get(a.entity_id) || 0) * 4 +
      (countsByName.get(a.canonical_name.toLowerCase()) || 0) * 3 +
      (a.recent_event_count ?? a.recent_events?.length ?? 0) * 2 +
      (a.change_count_30d || 0)
    const scoreB =
      (countsByEid.get(b.entity_id) || 0) * 4 +
      (countsByName.get(b.canonical_name.toLowerCase()) || 0) * 3 +
      (b.recent_event_count ?? b.recent_events?.length ?? 0) * 2 +
      (b.change_count_30d || 0)
    if (scoreB !== scoreA) return scoreB - scoreA
    return String(b.last_event_at || '').localeCompare(String(a.last_event_at || ''))
  })
})

const tickFlashByTicker = ref<Record<string, 'up' | 'down'>>({})
const lastPriceByTicker = new Map<string, number>()
let railFlashTimer: ReturnType<typeof setTimeout> | null = null

watch(
  () => props.indices,
  (nextList) => {
    const flashed: Record<string, 'up' | 'down'> = {}
    for (const idx of nextList || []) {
      const numP = Number(idx.price)
      if (!Number.isFinite(numP)) continue
      const prev = lastPriceByTicker.get(idx.ticker)
      if (prev !== undefined && prev !== numP) {
        flashed[idx.ticker] = numP > prev ? 'up' : 'down'
      }
      lastPriceByTicker.set(idx.ticker, numP)
    }
    if (Object.keys(flashed).length > 0) {
      tickFlashByTicker.value = flashed
      if (railFlashTimer) clearTimeout(railFlashTimer)
      railFlashTimer = setTimeout(() => {
        tickFlashByTicker.value = {}
      }, 700)
    }
  },
  { deep: true, immediate: true },
)

onUnmounted(() => {
  if (railFlashTimer) clearTimeout(railFlashTimer)
})
</script>

<template>
  <aside class="space-y-3" :aria-label="t('上下文与详情阅读器', 'Context & Split Reader')">
    <!-- MODE A: Split-View Article Detail Reader (preserves middle feed scroll position) -->
    <div v-if="selectedEvent" class="ios-card p-4 space-y-3.5 ios-fade-in">
      <div class="flex items-center justify-between gap-2 pb-2 border-b border-black/[0.06] dark:border-white/[0.08]">
        <span class="text-[12px] font-semibold text-[#007AFF] dark:text-[#0A84FF]">
          {{ t('详情阅读', 'Article Reader') }}
        </span>
        <div class="flex items-center gap-1">
          <button
            type="button"
            @click="emit('toggle-read', selectedEvent)"
            class="ios-tap w-8 h-8 rounded-lg inline-flex items-center justify-center hover:bg-black/[0.05] dark:hover:bg-white/[0.08]"
            :class="isSelectedRead ? 'text-emerald-500' : 'text-zinc-400'"
            :title="isSelectedRead ? t('标为未读', 'Mark Unread') : t('标为已读', 'Mark Read')"
          >
            <CheckCircle2 class="w-4 h-4" :stroke-width="1.5" />
          </button>
          <button
            type="button"
            @click="emit('toggle-bookmark', selectedEvent)"
            class="ios-tap w-8 h-8 rounded-lg inline-flex items-center justify-center hover:bg-black/[0.05] dark:hover:bg-white/[0.08]"
            :class="isSelectedBookmarked ? 'text-amber-500' : 'text-zinc-400'"
            :title="isSelectedBookmarked ? t('取消收藏', 'Unsave') : t('收藏', 'Save')"
          >
            <Bookmark class="w-4 h-4" :stroke-width="1.5" :class="{ 'fill-current': isSelectedBookmarked }" />
          </button>
          <button
            type="button"
            @click="emit('close-detail')"
            class="ios-tap w-8 h-8 rounded-lg inline-flex items-center justify-center text-zinc-400 hover:text-zinc-800 dark:hover:text-white hover:bg-black/[0.05] dark:hover:bg-white/[0.08]"
            :aria-label="t('关闭详情', 'Close reader')"
          >
            <X class="w-4 h-4" :stroke-width="1.5" />
          </button>
        </div>
      </div>

      <h3 class="text-[18px] font-semibold text-zinc-950 dark:text-white leading-[1.38] tracking-[-0.015em]">
        {{ pickBiText(selectedEvent.title_zh || selectedEvent.title, selectedEvent.title_en || selectedEvent.title) }}
      </h3>

      <div class="flex flex-wrap items-center gap-2 text-[12px] text-zinc-500 dark:text-zinc-400 tabular-nums">
        <span>{{ translateSourceName(selectedEvent.sources[0]?.publisher_name || selectedEvent.sources[0]?.source_name, selectedEvent.sources[0]?.title || selectedEvent.title) }}</span>
        <span>·</span>
        <SmartTime v-if="selectedEvent.first_reported_at || selectedEvent.published_at" :iso="selectedEvent.first_reported_at || selectedEvent.published_at" :now-ms="nowMs" />
      </div>

      <p v-if="cleanSummary" class="text-[15px] text-zinc-700 dark:text-zinc-200 leading-[1.5]">
        {{ pickBiText(cleanSummary, selectedEvent.summary_en || cleanSummary) }}
      </p>

      <!-- AI Analysis -->
      <div v-if="selectedEvent.ai_analysis" class="ios-surface-2 p-3 space-y-1.5">
        <div class="flex items-center gap-1.5 text-[12px] font-semibold text-[#007AFF] dark:text-[#0A84FF]">
          <Sparkles class="w-3.5 h-3.5" :stroke-width="1.5" />
          <span>{{ t('AI 解读', 'AI Analysis') }}</span>
        </div>
        <p class="text-[14px] text-zinc-700 dark:text-zinc-200 leading-[1.5]">
          {{ pickBiText(selectedEvent.ai_analysis, selectedEvent.ai_analysis_en) }}
        </p>
      </div>

      <!-- Market Impact -->
      <div v-if="selectedImpact" class="ios-surface-2 p-3 space-y-2 text-[12px]">
        <div class="font-semibold text-zinc-800 dark:text-zinc-100">{{ t('股市传导', 'Market Impact') }}</div>
        <div class="space-y-1.5">
          <div
            v-for="b in selectedImpact.bars.slice(0, 4)"
            :key="b.market + b.sector"
            class="flex items-center justify-between gap-2"
          >
            <span class="text-zinc-600 dark:text-zinc-300 truncate">{{ translateMarketTag(b.market) }} · {{ pickBiText(b.sector, b.sector_en) }}</span>
            <span
              class="font-mono font-semibold tabular-nums shrink-0"
              :class="(b.pct_low + b.pct_high) >= 0 ? marketUpTextClass() : marketDownTextClass()"
            >
              {{ fmtPct(b.pct_low, b.pct_high) }}
            </span>
          </div>
        </div>
      </div>

      <!-- Action CTAs -->
      <div class="flex items-center gap-2">
        <a
          v-if="primarySourceUrl"
          :href="primarySourceUrl"
          target="_blank"
          rel="noopener noreferrer"
          @click.stop="emit('mark-read', selectedEvent)"
          class="ios-tap flex-1 min-h-[38px] px-3 rounded-xl bg-[#007AFF] text-white text-[13px] font-semibold inline-flex items-center justify-center gap-1.5 hover:bg-[#0066D6]"
        >
          <span>{{ t('查看原文', 'Read Source') }}</span>
          <ExternalLink class="w-3.5 h-3.5" :stroke-width="1.5" />
        </a>
        <span
          v-else
          class="flex-1 min-h-[38px] px-3 rounded-xl bg-black/[0.04] dark:bg-white/[0.06] text-zinc-400 text-[12px] font-medium inline-flex items-center justify-center cursor-not-allowed"
        >
          {{ t('暂无原文直链', 'No Direct Link') }}
        </span>
        <button
          type="button"
          @click="emit('open-qa', selectedEvent)"
          class="ios-tap min-h-[38px] px-3 rounded-xl bg-[#F5F5F7] dark:bg-[#2C2C2E] text-zinc-800 dark:text-zinc-100 text-[13px] font-medium inline-flex items-center gap-1"
        >
          <Sparkles class="w-3.5 h-3.5 text-[#007AFF]" :stroke-width="1.5" />
          <span>{{ t('问答', 'Q&A') }}</span>
        </button>
      </div>

      <!-- Related Entities -->
      <div v-if="(selectedEvent.entities || []).length > 0" class="flex flex-wrap gap-1.5 pt-0.5">
        <button
          v-for="entName in (selectedEvent.entities || []).slice(0, 5)"
          :key="entName"
          type="button"
          @click="emit('select-entity', entName)"
          class="ios-tap px-2 py-0.5 rounded-lg bg-[#F5F5F7] dark:bg-[#2C2C2E] text-[11px] font-medium text-zinc-600 dark:text-zinc-300 hover:text-[#007AFF]"
        >
          # {{ translateEntityName(entName) }}
        </button>
      </div>

      <!-- Linked Sources (every row clickable native anchor with @click.stop, showing full list!) -->
      <div v-if="sortedSources.length > 0" class="space-y-1.5 pt-1">
        <div class="text-[12px] font-semibold text-zinc-400">{{ t(`出处 (${sortedSources.length})`, `Sources (${sortedSources.length})`) }}</div>
        <ul class="divide-y divide-black/[0.05] dark:divide-white/[0.06] text-[12px]">
          <li
            v-for="src in sortedSources"
            :key="src.item_id"
            class="py-0.5"
          >
            <a
              v-if="safeSourceHref(src.url)"
              :href="safeSourceHref(src.url)"
              target="_blank"
              rel="noopener noreferrer"
              @click.stop="emit('mark-read', selectedEvent)"
              class="py-1.5 px-1 -mx-1 rounded-lg flex items-center justify-between gap-2 hover:bg-black/[0.04] dark:hover:bg-white/[0.06] transition-colors group"
            >
              <div class="min-w-0">
                <div class="text-zinc-400 text-[11px]">{{ translateSourceName(src.publisher_name || src.source_name, src.title) }}</div>
                <div class="text-zinc-800 dark:text-zinc-200 truncate group-hover:text-[#007AFF]">{{ pickBiText(src.title_zh || src.title, src.title) }}</div>
              </div>
              <ExternalLink class="w-3.5 h-3.5 text-[#007AFF] shrink-0" :stroke-width="1.5" />
            </a>
            <div v-else class="py-1.5 flex items-center justify-between gap-2 opacity-60">
              <div class="min-w-0">
                <div class="text-zinc-400 text-[11px]">{{ translateSourceName(src.publisher_name || src.source_name, src.title) }}</div>
                <div class="text-zinc-500 dark:text-zinc-400 truncate">{{ pickBiText(src.title_zh || src.title, src.title) }}</div>
              </div>
              <span class="text-[10px] text-zinc-400 shrink-0">{{ t('暂无直链', 'No Link') }}</span>
            </div>
          </li>
        </ul>
      </div>
    </div>

    <!-- MODE B: Default Non-Duplicative Context Overview (Benchmarks + Entities + Reading Overview) -->
    <template v-else>
      <!-- 1. Market Indices Mini Strip -->
      <div v-if="indices.length > 0" class="ios-card p-3.5 space-y-2.5">
        <div class="flex items-center justify-between">
          <span class="text-[13px] font-semibold text-zinc-900 dark:text-white inline-flex items-center gap-1.5">
            <Activity class="w-3.5 h-3.5 text-[#007AFF]" :stroke-width="1.5" />
            <span>{{ t('核心指数', 'Benchmarks') }}</span>
            <span v-if="quotesUpdatedLabel" class="text-[10px] font-mono font-normal text-zinc-400 tabular-nums">
              {{ quotesUpdatedLabel }}
            </span>
          </span>
          <button
            type="button"
            @click="emit('switch-tab', 'finance')"
            class="text-[12px] text-[#007AFF] dark:text-[#0A84FF] font-medium hover:underline"
          >
            {{ t('股市传导', 'Markets') }}
          </button>
        </div>
        <div class="grid grid-cols-2 gap-2">
          <div
            v-for="idx in indices.slice(0, 6)"
            :key="idx.ticker"
            class="ios-surface-2 px-2.5 py-2 space-y-0.5 transition-colors"
            :class="
              (flashingTickers?.[idx.ticker] || tickFlashByTicker[idx.ticker]) === 'up'
                ? 'jx-tick-up'
                : (flashingTickers?.[idx.ticker] || tickFlashByTicker[idx.ticker]) === 'down'
                  ? 'jx-tick-down'
                  : ''
            "
          >
            <div class="text-[11px] text-zinc-500 dark:text-zinc-400 truncate">
              {{ pickBiText(idx.name, idx.name_en) }}
            </div>
            <div class="flex items-baseline justify-between gap-1 font-mono tabular-nums">
              <span class="text-[12px] font-semibold text-zinc-900 dark:text-white">
                <OdometerNumber :value="idx.price" />
              </span>
              <span
                v-if="idx.pct_change != null"
                class="text-[11px] font-semibold"
                :class="idx.pct_change >= 0 ? marketUpTextClass() : marketDownTextClass()"
              >
                {{ idx.pct_change >= 0 ? `+${idx.pct_change}%` : `${idx.pct_change}%` }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- 2. Hot Entities Drawer Entry -->
      <div v-if="hotEntities.length > 0" class="ios-card p-3.5 space-y-2.5" data-testid="hot-entities-rail">
        <div class="text-[13px] font-semibold text-zinc-900 dark:text-white">
          {{ t('热门实体档案', 'Entity Profiles') }}
        </div>
        <div class="flex flex-wrap gap-1.5">
          <button
            v-for="ent in hotEntities.slice(0, 10)"
            :key="ent.entity_id"
            type="button"
            @click="emit('select-entity', ent.canonical_name)"
            class="ios-tap px-2.5 py-1 rounded-lg bg-[#F5F5F7] dark:bg-[#2C2C2E] text-[12px] font-medium text-zinc-700 dark:text-zinc-200 hover:text-[#007AFF]"
          >
            {{ translateEntityName(ent.canonical_name) }}
          </button>
        </div>
      </div>

      <!-- 3. Personalized Tracking Return-Visit Dashboard + Diversity Check -->
      <div class="ios-card p-3.5 space-y-2.5" data-testid="desktop-tracking-dashboard">
        <div class="flex items-center justify-between text-[12px]">
          <span class="font-semibold text-zinc-900 dark:text-white inline-flex items-center gap-1.5">
            <Target class="w-3.5 h-3.5 text-[#007AFF]" :stroke-width="1.5" />
            <span>{{ t('我的追踪动态', 'My Tracking Pulse') }}</span>
          </span>
          <div class="flex items-center gap-2 text-[11px]">
            <button
              type="button"
              @click="emit('open-weekly-report')"
              class="inline-flex items-center gap-1 text-[#007AFF] dark:text-[#0A84FF] font-medium hover:underline"
            >
              <BarChart3 class="w-3.5 h-3.5" :stroke-width="1.5" />
              <span>{{ t('视野分布', 'Diversity') }}</span>
            </button>
          </div>
        </div>

        <div class="flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-xl bg-[#F5F5F7] dark:bg-[#2C2C2E] text-[11px] text-zinc-600 dark:text-zinc-300 tabular-nums">
          <span>
            {{ t('本批进度：已读', 'Batch Read:') }} <OdometerNumber :value="batchReadCount ?? todayReadCount" />/{{ batchTotalCount ?? '—' }}
          </span>
          <span class="font-semibold text-zinc-800 dark:text-zinc-100">
            {{ t('历史累计：', 'Total:') }} <OdometerNumber :value="historicalReadCount ?? todayReadCount" /> {{ t('篇', '') }}
          </span>
        </div>

        <div class="space-y-1.5 text-[12px]">
          <button
            type="button"
            @click="emit('switch-tab', 'today')"
            class="w-full px-2.5 py-1.5 rounded-xl bg-[#F5F5F7] dark:bg-[#2C2C2E] flex items-center justify-between gap-2 text-left hover:bg-zinc-200/70 dark:hover:bg-zinc-700/70 transition-colors"
          >
            <span class="text-zinc-700 dark:text-zinc-200 truncate">
              {{ t('关注词新事件 / 专题', 'Watchlist New Stories') }}
            </span>
            <span class="inline-flex items-center gap-1 font-semibold text-[#007AFF] dark:text-[#0A84FF] tabular-nums shrink-0">
              <span>{{ watchMatchesSummary.events }} 条 · {{ watchMatchesSummary.topics }} 专题</span>
              <ChevronRight class="w-3.5 h-3.5 text-zinc-400" />
            </span>
          </button>

          <button
            type="button"
            @click="emit('open-finance-portfolio')"
            class="w-full px-2.5 py-1.5 rounded-xl bg-[#F5F5F7] dark:bg-[#2C2C2E] flex items-center justify-between gap-2 text-left hover:bg-zinc-200/70 dark:hover:bg-zinc-700/70 transition-colors"
          >
            <span class="inline-flex items-center gap-1 text-zinc-700 dark:text-zinc-200 truncate">
              <Briefcase class="w-3.5 h-3.5 text-indigo-500 shrink-0" :stroke-width="1.5" />
              <span class="truncate">{{ t('命中持仓股市传导', 'Portfolio Impact Hits') }}</span>
            </span>
            <span class="inline-flex items-center gap-1 font-semibold text-indigo-600 dark:text-indigo-400 tabular-nums shrink-0">
              <span>{{ portfolioHitCount }} 条</span>
              <ChevronRight class="w-3.5 h-3.5 text-zinc-400" />
            </span>
          </button>

          <button
            type="button"
            @click="emit('switch-tab', 'calendar')"
            class="w-full px-2.5 py-1.5 rounded-xl bg-[#F5F5F7] dark:bg-[#2C2C2E] space-y-1 text-left hover:bg-zinc-200/70 dark:hover:bg-zinc-700/70 transition-colors"
          >
            <div class="flex items-center justify-between gap-2">
              <span class="inline-flex items-center gap-1 text-zinc-700 dark:text-zinc-200">
                <Calendar class="w-3.5 h-3.5 text-amber-500 shrink-0" :stroke-width="1.5" />
                <span>{{ t('未来 48h 催化提醒', 'Next 48h Catalysts') }}</span>
              </span>
              <span class="inline-flex items-center gap-1 font-semibold text-amber-600 dark:text-amber-400 tabular-nums shrink-0">
                <span>{{ upcoming48hCatalysts.length }} 项</span>
                <ChevronRight class="w-3.5 h-3.5 text-zinc-400" />
              </span>
            </div>
            <div v-if="upcoming48hCatalysts.length > 0" class="text-[11px] text-zinc-500 dark:text-zinc-400 truncate">
              {{ upcoming48hCatalysts.slice(0, 2).map((c) => c.title).join(' · ') }}
            </div>
          </button>
        </div>
      </div>
    </template>
  </aside>
</template>
