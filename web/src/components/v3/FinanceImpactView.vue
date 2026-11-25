<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  Briefcase,
  ChevronDown,
  ChevronUp,
  Clock,
  ExternalLink,
  FileText,
  History,
  Info,
  Layers,
  Share2,
  Target,
  X,
} from 'lucide-vue-next'
import EmptySearchState from '../EmptySearchState.vue'
import LoadingSkeleton from '../LoadingSkeleton.vue'
import OdometerNumber from '../OdometerNumber.vue'
import SmartTime from '../SmartTime.vue'
import { getApiBase } from '../../core/auth'
import { extractHeadlineQualifiers, resolveEvidenceTierBadge } from '../../core/evidence'
import { pickBiText, t, translatePortfolioSector, translateSourceName } from '../../core/i18n'
import { normalizeExternalUrl } from '../../core/legacyAdapter'
import { getReactionSummary, loadReactionsBatch, toggleStructuredReaction } from '../../core/reactionsStore'
import { matchesSmartQuery } from '../../core/search'
import { globalQuotesStore, refreshGlobalQuotes } from '../../core/quotesStore'
import { extractShanghaiParts } from '../../core/time'
import { loadPortfolioConfig, savePortfolioConfig } from '../../core/storage'
import { countMatchingNotesForSubject, matchImpactAgainstPortfolio, type PortfolioMatchResult } from '../../core/v3Logic'
import {
  isRedUp,
  marketDownActiveBtnClass,
  marketDownBadgeClass,
  marketDownBarBgClass,
  marketDownTextClass,
  marketUpActiveBtnClass,
  marketUpBadgeClass,
  marketUpBarBgClass,
  marketUpTextClass,
} from '../../core/uiPrefs'
import type {
  EventMarketImpact,
  FinanceImpactBar,
  FinanceImpactDoc,
  MarketQuoteItem,
  PortfolioConfig,
  ResearchNote,
} from '../../core/types'

const props = defineProps<{
  doc: FinanceImpactDoc | null
  searchQuery?: string
  nowMs?: number
  loading?: boolean
  initialPortfolioOnly?: boolean
  openPortfolioNonce?: number
  researchNotes?: ResearchNote[]
  sharedPortfolioPreview?: { sectors: string[]; tickers: string[] } | null
}>()

const emit = defineEmits<{
  (e: 'jump-event-id', eventId: string): void
  (e: 'mark-read-event-id', eventId: string): void
  (e: 'open-notes'): void
  (e: 'clear-search'): void
  (e: 'clear-shared-portfolio'): void
  (e: 'portfolio-changed', cfg: PortfolioConfig, matchedCount?: number): void
  (e: 'open-portfolio-share-card', summary: {
    matchedCount: number
    bullishCount: number
    bearishCount: number
    neutralCount: number
    isRedUp: boolean
    sectors: string[]
    tickers: string[]
    symbolsLabel: string
    takeaways: { title: string; polarity: 'positive' | 'negative' | 'neutral'; summary: string; tags?: string[] }[]
  }): void
}>()

function countItemNotes(item: EventMarketImpact): number {
  const notes = props.researchNotes || []
  if (!notes.length) return 0
  const tickers = Object.keys(item.affected_tickers || {})
  for (const l of item.transmission_layers || []) {
    for (const s of l.stocks || []) {
      if (s.code) tickers.push(s.code)
    }
  }
  return countMatchingNotesForSubject(notes, {
    eventId: item.event_id,
    tickers,
    entities: [item.tag],
  })
}

function toggleInlineBrief(item: EventMarketImpact) {
  const opening = inlineBriefId.value !== item.id
  inlineBriefId.value = opening ? item.id : null
  if (opening && item.event_id) {
    emit('mark-read-event-id', item.event_id)
  }
}

function toggleDeepAnalysis(item: EventMarketImpact) {
  const opening = expandedId.value !== item.id
  expandedId.value = opening ? item.id : null
  if (opening && item.event_id) {
    emit('mark-read-event-id', item.event_id)
  }
}

const effectiveNowMs = computed(() => props.nowMs ?? Date.now())
const polarityFilter = ref<'all' | 'bullish' | 'bearish' | 'divergent'>('all')
const marketFilter = ref<'all' | 'A股' | '美股' | '港股'>('all')
const viewMode = ref<'cards' | 'compact'>('cards')
const compactExpandedId = ref<string | null>(null)
const expandedId = ref<string | null>(null)
const inlineBriefId = ref<string | null>(null)
const onlyPortfolioHits = ref(Boolean(props.initialPortfolioOnly))
const portfolioPanelOpen = ref(Boolean(props.initialPortfolioOnly))
watch(
  () => props.initialPortfolioOnly,
  (val) => {
    if (val) {
      portfolioPanelOpen.value = true
      onlyPortfolioHits.value = true
    }
  },
)
watch(
  () => props.openPortfolioNonce,
  (val) => {
    if (val && val > 0) {
      portfolioPanelOpen.value = true
    }
  },
)
function togglePortfolioPanel() {
  portfolioPanelOpen.value = !portfolioPanelOpen.value
  onlyPortfolioHits.value = portfolioPanelOpen.value
}
const disclaimerOpen = ref(false)
const portfolio = ref<PortfolioConfig>(loadPortfolioConfig())
const tickerInput = ref(portfolio.value.tickers.join(', '))

const liveIndices = globalQuotesStore.indices
const liveQuotesMap = globalQuotesStore.quotesMap
const liveQuotesUpdatedAt = globalQuotesStore.updatedAt
const flashingTickers = globalQuotesStore.flashingTickers

const syncTimeLabel = computed(() => {
  const explicit = globalQuotesStore.updatedTimeLabel.value
  if (explicit) return explicit
  const iso = liveQuotesUpdatedAt.value || props.doc?.quotes_updated_at || props.doc?.generated_at
  if (!iso) return ''
  const ms = Date.parse(iso)
  if (!Number.isFinite(ms)) return ''
  const pts = extractShanghaiParts(ms)
  return `${pts.hour}:${pts.minute}`
})

const marketClockLabel = computed(() => {
  const hm = syncTimeLabel.value
  return hm
    ? t(`实时行情自动同步 · ${hm}`, `Live Quotes Auto-Sync · ${hm}`)
    : t('实时行情自动同步', 'Live Quotes Auto-Sync')
})

function cardEvidenceBadge(item: EventMarketImpact) {
  return resolveEvidenceTierBadge({
    evidence_tier: item.evidence_tier,
    evidence_tier_label: item.evidence_tier_label,
    sources: item.sources,
    source_name: item.source_name,
    title: item.event_title,
    summary: item.event_summary,
  })
}

function cardQualifiers(item: EventMarketImpact) {
  const fb = extractHeadlineQualifiers(item.event_title, item.event_summary)
  return {
    effectiveDate: item.effective_date_label || fb.effectiveDateLabel,
    qualifier: item.qualifier_badge || fb.qualifierBadge,
  }
}

onMounted(() => {
  if (liveIndices.value.length === 0) {
    void refreshGlobalQuotes()
  }
})

const displayIndices = computed<MarketQuoteItem[]>(() =>
  liveIndices.value.length > 0 ? liveIndices.value : (props.doc?.index_quotes ?? []),
)

const PORTFOLIO_SECTOR_PRESETS = [
  'AI 算力 / 半导体',
  '美股核心科技',
  '港股互联网',
  'CPO / 通信光模块',
  '石油能源 / 油运',
  '黄金与贵金属',
  '银行 / 高股息红利',
  '出口链 / 消费电子',
  '网络安全 / 信创',
]

function togglePortfolioSector(sec: string) {
  const curr = new Set(portfolio.value.sectors)
  if (curr.has(sec)) curr.delete(sec)
  else curr.add(sec)
  portfolio.value = { ...portfolio.value, sectors: Array.from(curr) }
  savePortfolioConfig(portfolio.value)
  emit('portfolio-changed', portfolio.value)
}

function commitPortfolioTickers() {
  const tickers = tickerInput.value
    .split(/[,，\s]+/)
    .map((s) => s.trim().toUpperCase())
    .filter(Boolean)
    .slice(0, 15)
  portfolio.value = { ...portfolio.value, tickers }
  savePortfolioConfig(portfolio.value)
  const hitCount = impacts.value.filter((item) => matchImpactAgainstPortfolio(item, portfolio.value).matched).length
  portfolioPanelOpen.value = false
  emit('portfolio-changed', portfolio.value, hitCount)
}

const impacts = computed<EventMarketImpact[]>(() =>
  (props.doc?.event_impacts ?? []).filter(
    (item) => item.validation_status !== 'insufficient_evidence' && Array.isArray(item.bars) && item.bars.length > 0,
  ),
)

const effectivePortfolio = computed<PortfolioConfig>(() =>
  props.sharedPortfolioPreview &&
  (props.sharedPortfolioPreview.sectors.length > 0 || props.sharedPortfolioPreview.tickers.length > 0)
    ? {
        sectors: props.sharedPortfolioPreview.sectors,
        tickers: props.sharedPortfolioPreview.tickers,
        riskProfile: 'balanced',
      }
    : portfolio.value,
)

const portfolioMatchMap = computed<Record<string, PortfolioMatchResult>>(() => {
  const out: Record<string, PortfolioMatchResult> = {}
  for (const item of impacts.value) {
    out[item.id] = matchImpactAgainstPortfolio(item, effectivePortfolio.value)
  }
  return out
})

const sharedPreviewStats = computed(() => {
  if (!props.sharedPortfolioPreview) return null
  const matched = impacts.value.filter((it) => portfolioMatchMap.value[it.id]?.matched)
  let bullish = 0
  let bearish = 0
  let neutral = 0
  for (const it of matched) {
    const m = portfolioMatchMap.value[it.id]
    if (m && m.avgDelta > 0.2) bullish += 1
    else if (m && m.avgDelta < -0.2) bearish += 1
    else neutral += 1
  }
  return { total: matched.length, bullish, bearish, neutral }
})

function switchToMyOwnPortfolio() {
  emit('clear-shared-portfolio')
  portfolioPanelOpen.value = true
  onlyPortfolioHits.value = false
}

const baseFilteredWithoutPortfolio = computed(() => {
  const q = (props.searchQuery || '').trim().toLowerCase()
  return impacts.value.filter((item) => {
    if (polarityFilter.value !== 'all' && item.polarity !== polarityFilter.value) return false
    if (marketFilter.value !== 'all' && !item.bars.some((b) => b.market === marketFilter.value)) {
      return false
    }
    if (q) {
      const hay = `${item.event_title} ${item.event_title_en || ''} ${item.one_liner} ${item.tag} ${item.bars.map((b) => `${b.sector} ${b.sector_en || ''} ${b.logic}`).join(' ')}`
      if (!matchesSmartQuery(hay, q)) return false
    }
    return true
  })
})

const portfolioMatchedCount = computed(() =>
  baseFilteredWithoutPortfolio.value.filter((it) => portfolioMatchMap.value[it.id]?.matched).length,
)

function marketRelevanceScore(item: EventMarketImpact, mkt: 'A股' | '美股' | '港股'): number {
  let score = 0
  item.bars.forEach((b, idx) => {
    if (b.market === mkt) {
      const mag = Math.max(Math.abs(b.pct_low), Math.abs(b.pct_high))
      score += mag + (idx === 0 ? 3 : idx === 1 ? 1.5 : 0.5)
    }
  })
  const tier1 = item.transmission_layers?.[0]?.stocks || []
  score += tier1.filter((s) => s.market === mkt).length * 2.5
  return score
}

const filteredImpacts = computed(() => {
  const base = onlyPortfolioHits.value
    ? baseFilteredWithoutPortfolio.value.filter((item) => portfolioMatchMap.value[item.id]?.matched)
    : baseFilteredWithoutPortfolio.value
  if (marketFilter.value === 'all') return base
  const targetMkt = marketFilter.value
  return [...base].sort((a, b) => marketRelevanceScore(b, targetMkt) - marketRelevanceScore(a, targetMkt))
})

function sortedBars(item: EventMarketImpact): FinanceImpactBar[] {
  const bars = item.bars || []
  if (marketFilter.value === 'all') return bars
  const mkt = marketFilter.value
  return [...bars].sort((a, b) => (a.market === mkt ? 0 : 1) - (b.market === mkt ? 0 : 1))
}

function sortedTier1Stocks(item: EventMarketImpact) {
  const stocks = item.transmission_layers?.[0]?.stocks || []
  if (marketFilter.value === 'all') return stocks
  const mkt = marketFilter.value
  return [...stocks].sort((a, b) => (a.market === mkt ? 0 : 1) - (b.market === mkt ? 0 : 1))
}

function cleanSectorTitle(market: string, sectorName: string): string {
  const s = String(sectorName || '').trim()
  const prefixRe = new RegExp(`^(?:${market}|A股|港股|美股|台股|A-Share|HKEX|US)\\s*[·/\\s-]*`, 'i')
  return s.replace(prefixRe, '').trim() || s
}

function pricedInBadgeClass(code?: string): string {
  if (code === 'unpriced') return 'bg-[#007AFF]/12 text-[#007AFF] dark:bg-[#0A84FF]/18 dark:text-[#64D2FF]'
  if (code === 'overseas_priced_in') return 'bg-rose-500/12 text-rose-700 dark:bg-rose-400/15 dark:text-rose-300'
  if (code === 'fully_priced') return 'bg-zinc-500/12 text-zinc-700 dark:bg-zinc-400/15 dark:text-zinc-300'
  return 'bg-amber-500/12 text-amber-700 dark:bg-amber-400/15 dark:text-amber-300'
}

const counts = computed(() => ({
  all: impacts.value.length,
  bullish: impacts.value.filter((i) => i.polarity === 'bullish').length,
  bearish: impacts.value.filter((i) => i.polarity === 'bearish').length,
  divergent: impacts.value.filter((i) => i.polarity === 'divergent').length,
  hk: impacts.value.filter((i) => i.bars.some((b) => b.market === '港股')).length,
}))

function polarityLabel(item: EventMarketImpact): string {
  if (item.validation_status === 'insufficient_evidence') return t('暂无可靠推演', 'Insufficient Model')
  if (item.polarity === 'bullish') return t('股市偏利好', 'Bullish Bias')
  if (item.polarity === 'bearish') return t('股市承压', 'Bearish Risk')
  return t('结构分化 / 对冲', 'Divergent')
}

function polarityBadgeClass(item: EventMarketImpact): string {
  if (item.validation_status === 'insufficient_evidence') {
    return 'bg-zinc-500/12 text-zinc-600 dark:bg-zinc-400/15 dark:text-zinc-300'
  }
  if (item.polarity === 'bullish') return marketUpBadgeClass()
  if (item.polarity === 'bearish') return marketDownBadgeClass()
  return 'bg-amber-500/12 text-amber-700 dark:bg-amber-400/15 dark:text-amber-300'
}

function formatRange(bar: FinanceImpactBar): string {
  const lo = bar.pct_low > 0 ? `+${bar.pct_low}%` : `${bar.pct_low}%`
  const hi = bar.pct_high > 0 ? `+${bar.pct_high}%` : `${bar.pct_high}%`
  return `${lo} ~ ${hi}`
}

function barGeometry(bar: FinanceImpactBar): { left: string; width: string; isPositive: boolean } {
  const maxAbs = 7.0
  const mid = (bar.pct_low + bar.pct_high) / 2
  const isPositive = mid >= 0
  const mag = Math.min(maxAbs, Math.max(Math.abs(bar.pct_low), Math.abs(bar.pct_high)))
  const widthPct = Math.max(8, (mag / maxAbs) * 50)
  return isPositive
    ? { left: '50%', width: `${widthPct}%`, isPositive: true }
    : { left: `${50 - widthPct}%`, width: `${widthPct}%`, isPositive: false }
}

function marketLabel(mk: string): string {
  if (mk === 'A股') return t('A股', 'A-Shares')
  if (mk === '美股') return t('美股', 'US')
  if (mk === '港股') return t('港股', 'HKEX')
  return mk
}

function resetLocalFilters() {
  polarityFilter.value = 'all'
  marketFilter.value = 'all'
  onlyPortfolioHits.value = false
}

function mergedQuoteList(item: EventMarketImpact): MarketQuoteItem[] {
  const list = item.realized_quotes || []
  return list.map((q) => liveQuotesMap.value[q.ticker] || q)
}

function openPortfolioRadarShareCard() {
  const matchedItems = baseFilteredWithoutPortfolio.value.filter((it) => portfolioMatchMap.value[it.id]?.matched)
  const pool = matchedItems.length > 0 ? matchedItems : baseFilteredWithoutPortfolio.value.slice(0, 6)
  let bullishCount = 0
  let bearishCount = 0
  let neutralCount = 0
  const classifyItem = (it: EventMarketImpact): 'positive' | 'negative' | 'neutral' => {
    const m = portfolioMatchMap.value[it.id]
    if (m?.matched) {
      if (m.avgDelta > 0.2) return 'positive'
      if (m.avgDelta < -0.2) return 'negative'
      return 'neutral'
    }
    if (it.polarity === 'bullish') return 'positive'
    if (it.polarity === 'bearish') return 'negative'
    return 'neutral'
  }

  for (const it of pool) {
    const pol = classifyItem(it)
    if (pol === 'positive') bullishCount += 1
    else if (pol === 'negative') bearishCount += 1
    else neutralCount += 1
  }

  const takeaways = pool.slice(0, 3).map((it) => {
    const pol = classifyItem(it)
    const m = portfolioMatchMap.value[it.id]
    const barTags = (it.bars || []).slice(0, 2).map((b) => cleanSectorTitle(b.market, b.sector))
    return {
      title: pickBiText(it.event_title, it.event_title_en),
      polarity: pol,
      summary: pickBiText(it.one_liner, it.one_liner_en),
      tags: m?.tags?.length ? m.tags.slice(0, 2) : barTags,
    }
  })

  const sectors = effectivePortfolio.value.sectors
  const tickers = effectivePortfolio.value.tickers
  const labels = [...sectors, ...tickers].slice(0, 6)
  emit('open-portfolio-share-card', {
    matchedCount: bullishCount + bearishCount + neutralCount,
    bullishCount,
    bearishCount,
    neutralCount,
    isRedUp: isRedUp(),
    sectors,
    tickers,
    symbolsLabel: labels.length > 0 ? labels.join(' · ') : t('全市场重点板块雷达', 'Cross-Market Sector Radar'),
    takeaways,
  })
}

watch(
  () => baseFilteredWithoutPortfolio.value.map((x) => x.id).join(','),
  (csv) => {
    if (!csv) return
    void loadReactionsBatch('finance', csv.split(','))
  },
  { immediate: true },
)
</script>

<template>
  <section class="space-y-2.5" :aria-label="t('股市传导推演', 'Market Transmission Forecasts')">
    <!-- Mobile/Tablet Only Horizontal Benchmark Quotes Strip (hidden on xl desktop where right rail shows indices without duplication) -->
    <div
      v-if="displayIndices.length > 0"
      class="xl:hidden grid grid-cols-2 sm:flex sm:flex-wrap items-center gap-1.5 pb-0.5"
    >
      <div
        v-for="idx in displayIndices"
        :key="idx.ticker"
        class="ios-card px-2.5 py-1.5 flex items-center justify-between sm:justify-start gap-1.5 sm:gap-2 text-xs min-w-0 transition-all duration-300"
        :class="
          flashingTickers[idx.ticker] === 'up'
            ? (isRedUp() ? 'jx-tick-up ring-1 ring-rose-500/40' : 'jx-tick-up ring-1 ring-emerald-500/40')
            : flashingTickers[idx.ticker] === 'down'
              ? (isRedUp() ? 'jx-tick-down ring-1 ring-emerald-500/40' : 'jx-tick-down ring-1 ring-rose-500/40')
              : ''
        "
      >
        <span class="font-semibold text-zinc-700 dark:text-zinc-200 truncate">
          {{ pickBiText(idx.name, idx.name_en) }}
        </span>
        <span class="inline-flex items-center gap-1 shrink-0">
          <span class="font-mono font-bold text-zinc-950 dark:text-white tabular-nums">
            <OdometerNumber :value="idx.price" />
          </span>
          <span
            v-if="idx.pct_change != null"
            class="font-mono text-[11px] font-semibold tabular-nums"
            :class="idx.pct_change >= 0 ? marketUpTextClass() : marketDownTextClass()"
          >
            {{ idx.pct_change >= 0 ? `+${idx.pct_change}%` : `${idx.pct_change}%` }}
          </span>
        </span>
      </div>
    </div>

    <LoadingSkeleton v-if="loading && !doc" variant="cards" :count="4" />

    <div
      v-else-if="!doc || impacts.length === 0"
      class="ios-card p-8 text-center text-sm text-zinc-500"
    >
      {{ t('暂无股市传导数据', 'No market impact data available.') }}
    </div>

    <template v-else>
      <!-- Two-part Slim Filter Bar that NEVER clips on 360px (Smart Sticky on <768px) -->
      <div class="mobile-sticky-subbar flex flex-wrap items-center justify-between gap-1.5 text-xs" data-testid="finance-sticky-subbar">
        <div class="ios-segmented flex-1 sm:flex-initial flex">
          <button
            type="button"
            @click="polarityFilter = 'all'"
            class="ios-segmented-btn flex-1 sm:flex-initial min-h-[32px] px-2"
            :class="polarityFilter === 'all' ? 'ios-segmented-btn-active' : 'text-zinc-600 dark:text-zinc-400'"
          >
            {{ t('全部', 'All') }}
          </button>
          <button
            type="button"
            @click="polarityFilter = 'bullish'"
            class="ios-segmented-btn flex-1 sm:flex-initial min-h-[32px] px-2"
            :class="polarityFilter === 'bullish' ? marketUpActiveBtnClass() : marketUpTextClass()"
          >
            {{ t('利好', 'Bull') }}
          </button>
          <button
            type="button"
            @click="polarityFilter = 'bearish'"
            class="ios-segmented-btn flex-1 sm:flex-initial min-h-[32px] px-2"
            :class="polarityFilter === 'bearish' ? marketDownActiveBtnClass() : marketDownTextClass()"
          >
            {{ t('承压', 'Bear') }}
          </button>
          <button
            type="button"
            @click="polarityFilter = 'divergent'"
            class="ios-segmented-btn flex-1 sm:flex-initial min-h-[32px] px-2"
            :class="polarityFilter === 'divergent' ? 'bg-amber-600 text-white' : 'text-amber-700 dark:text-amber-300'"
          >
            {{ t('分化', 'Mix') }}
          </button>
        </div>

        <div class="flex flex-wrap sm:flex-nowrap items-center gap-1 min-w-0 max-w-full sm:shrink-0">
          <button
            type="button"
            @click="togglePortfolioPanel"
            class="ios-tap inline-flex items-center gap-1 min-h-[34px] px-2 sm:px-2.5 rounded-xl font-medium whitespace-nowrap"
            :class="(portfolioPanelOpen || onlyPortfolioHits) ? 'bg-[#007AFF] text-white' : 'bg-white dark:bg-[#1C1C1E] text-[#007AFF] dark:text-[#0A84FF]'"
          >
            <Briefcase class="w-3.5 h-3.5" :stroke-width="1.5" />
            <span>{{ t('持仓', 'Port') }}</span>
            <span v-if="onlyPortfolioHits" class="text-[10px] opacity-90 tabular-nums">({{ filteredImpacts.length }})</span>
          </button>

          <div class="relative inline-flex items-center shrink-0 h-8 sm:h-9 pl-2 pr-6 sm:pl-2.5 sm:pr-7 rounded-xl bg-white dark:bg-[#1C1C1E] text-xs font-medium text-zinc-700 dark:text-zinc-200 shadow-[0_1px_2px_rgba(0,0,0,0.04)] focus-within:ring-2 focus-within:ring-[#007AFF]/40">
            <span class="pointer-events-none whitespace-nowrap">
              {{ marketFilter === 'all' ? t('全市场', 'All Markets') : marketLabel(marketFilter) }}
            </span>
            <ChevronDown class="w-3.5 h-3.5 text-zinc-400 pointer-events-none absolute right-1.5 sm:right-2" />
            <select
              v-model="marketFilter"
              :aria-label="t('市场筛选', 'Market filter')"
              class="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
            >
              <option value="all">{{ t('全市场', 'All') }}</option>
              <option value="A股">{{ marketLabel('A股') }}</option>
              <option value="美股">{{ marketLabel('美股') }}</option>
              <option value="港股">{{ marketLabel('港股') }}</option>
            </select>
          </div>

          <div class="ios-segmented shrink-0 flex">
            <button
              type="button"
              @click="viewMode = 'cards'"
              class="ios-segmented-btn min-h-[32px] px-1.5 sm:px-2 text-[11px]"
              :class="viewMode === 'cards' ? 'ios-segmented-btn-active' : 'text-zinc-600 dark:text-zinc-400'"
            >
              {{ t('标准卡片', 'Cards') }}
            </button>
            <button
              type="button"
              @click="viewMode = 'compact'"
              class="ios-segmented-btn min-h-[32px] px-1.5 sm:px-2 text-[11px]"
              :class="viewMode === 'compact' ? 'ios-segmented-btn-active' : 'text-zinc-600 dark:text-zinc-400'"
            >
              {{ t('紧凑看盘', 'Compact') }}
            </button>
          </div>

          <button
            type="button"
            @click="disclaimerOpen = !disclaimerOpen"
            class="ios-tap inline-flex items-center justify-center w-8 h-8 sm:w-9 sm:h-9 rounded-xl bg-white dark:bg-[#1C1C1E] text-zinc-500 hover:text-[#007AFF] shrink-0"
            :aria-label="t('口径与免责声明', 'Methodology & Disclaimer')"
            :title="t('口径与免责声明', 'Methodology & Disclaimer')"
          >
            <Info class="w-4 h-4" :stroke-width="1.5" />
          </button>
        </div>
      </div>

      <!-- Auto-Sync Market Clock Status -->
      <div class="flex flex-wrap items-center justify-between gap-2 text-[11px] px-0.5">
        <span
          data-testid="finance-auto-sync-status"
          class="inline-flex items-center gap-1.5 tabular-nums font-medium text-emerald-700 dark:text-emerald-300"
        >
          <span
            class="jx-sonar-dot jx-sonar-emerald"
            aria-hidden="true"
          />
          <span>{{ marketClockLabel }}</span>
        </span>
      </div>

      <!-- Collapsible Info Popover for Disclaimer (zero default screen bloat) -->
      <div
        v-if="disclaimerOpen"
        class="ios-card px-3.5 py-2.5 text-xs text-zinc-600 dark:text-zinc-300 flex items-start justify-between gap-2"
      >
        <p class="leading-relaxed">
          {{ pickBiText(doc?.disclaimer || '涨跌敏感区间根据事件方向、领域逻辑与历史波动率校准，仅供参考，不构成投资建议。', doc?.disclaimer_en || 'Sensitivity ranges are calibrated by event polarity & historical volatility. Analytical reference only; not investment advice.') }}
        </p>
        <button
          type="button"
          @click="disclaimerOpen = false"
          class="w-8 h-8 inline-flex items-center justify-center rounded-lg text-zinc-400 shrink-0"
          :aria-label="t('关闭', 'Close')"
        >
          <X class="w-4 h-4" />
        </button>
      </div>

      <!-- Shared Friend Portfolio Preview Banner (?tab=finance&ref_sectors=...&ref_tickers=...) -->
      <div
        v-if="sharedPortfolioPreview && sharedPreviewStats"
        class="rounded-2xl border border-[#007AFF]/35 bg-gradient-to-r from-[#007AFF]/10 via-white to-white dark:from-[#0A84FF]/15 dark:via-[#1C1C1E] dark:to-[#1C1C1E] p-3.5 sm:p-4 space-y-2.5 text-xs"
        data-testid="shared-portfolio-preview-banner"
      >
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="space-y-0.5 min-w-0">
            <div class="font-bold text-zinc-950 dark:text-white flex items-center gap-1.5">
              <Briefcase class="w-4 h-4 text-[#007AFF] shrink-0" :stroke-width="1.75" />
              <span>{{ t('好友脱敏持仓传导预览（只读）', 'Shared Desensitized Portfolio Radar Preview') }}</span>
            </div>
            <p class="text-[11.5px] text-zinc-600 dark:text-zinc-300">
              {{ [...sharedPortfolioPreview.sectors, ...sharedPortfolioPreview.tickers].join(' · ') }}
              · {{ t(`命中 ${sharedPreviewStats.total} 条传导线（利好 ${sharedPreviewStats.bullish} / 承压 ${sharedPreviewStats.bearish} / 分化 ${sharedPreviewStats.neutral}）`, `${sharedPreviewStats.total} matched (${sharedPreviewStats.bullish} bull / ${sharedPreviewStats.bearish} bear / ${sharedPreviewStats.neutral} mix)`) }}
            </p>
          </div>
          <button
            type="button"
            @click="switchToMyOwnPortfolio"
            class="ios-tap px-3.5 py-2 rounded-xl bg-[#007AFF] hover:bg-[#0066D6] text-white font-semibold shrink-0 whitespace-nowrap"
            data-testid="switch-to-my-portfolio-btn"
          >
            {{ t('换成我的自选股测一测', 'Test With My Watchlist') }}
          </button>
        </div>
      </div>

      <!-- Portfolio Scenario Simulator Panel -->
      <div
        v-if="portfolioPanelOpen"
        class="rounded-xl border border-indigo-200 dark:border-indigo-800/80 bg-indigo-50/40 dark:bg-indigo-950/20 p-3.5 sm:p-4 space-y-3 text-xs"
        data-testid="portfolio-scenario-panel"
      >
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="font-bold text-slate-900 dark:text-white flex items-center gap-1.5">
            <Briefcase class="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
            <span>{{ t('持仓关联情景模拟（按个股与直接板块方向精准计算敏感偏置）', 'Portfolio Exposure Simulator (Ticker & Sector Sensitivity)') }}</span>
          </div>
          <div class="flex flex-wrap items-center gap-2.5">
            <label class="inline-flex items-center gap-1 cursor-pointer text-[11px] text-indigo-800 dark:text-indigo-200 font-medium">
              <input v-model="onlyPortfolioHits" type="checkbox" class="rounded border-indigo-300 text-indigo-600" />
              <span>{{ t('仅看命中', 'Hits Only') }}</span>
            </label>
            <span class="text-[11px] text-indigo-700 dark:text-indigo-300 font-semibold tabular-nums">
              {{ t(`命中 ${portfolioMatchedCount} 条传导链`, `${portfolioMatchedCount} correlated chains`) }}
            </span>
          </div>
        </div>

        <div class="flex flex-wrap gap-1.5">
          <button
            v-for="sec in PORTFOLIO_SECTOR_PRESETS"
            :key="sec"
            type="button"
            @click="togglePortfolioSector(sec)"
            class="px-2.5 py-1 rounded-full text-[11px] font-medium border transition-colors"
            :class="
              portfolio.sectors.includes(sec)
                ? 'bg-indigo-600 text-white border-indigo-600'
                : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:border-indigo-400'
            "
          >
            {{ portfolio.sectors.includes(sec) ? '已选 ' : '+ ' }}{{ translatePortfolioSector(sec) }}
          </button>
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <input
            v-model="tickerInput"
            @blur="commitPortfolioTickers"
            @keydown.enter.prevent="commitPortfolioTickers"
            type="text"
            :placeholder="t('关注个股/ETF 代码（逗号分隔，如 NVDA, TSM, 00700, GLD, USO）', 'Tickers (comma-separated, e.g. NVDA, TSM, 00700, GLD)')"
            class="flex-1 min-w-[200px] h-9 px-3 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white"
          />
          <button
            type="button"
            @click="commitPortfolioTickers"
            class="px-3 h-9 rounded-lg bg-slate-900 dark:bg-indigo-600 text-white font-semibold"
          >
            {{ t('保存标的', 'Save Tickers') }}
          </button>
          <button
            type="button"
            @click="openPortfolioRadarShareCard"
            class="inline-flex items-center gap-1.5 px-3 h-9 rounded-lg border border-indigo-300 dark:border-indigo-700 bg-white dark:bg-slate-900 text-indigo-700 dark:text-indigo-300 font-semibold hover:bg-indigo-50 dark:hover:bg-indigo-950/50 whitespace-nowrap"
            data-testid="generate-portfolio-radar-btn"
          >
            <Share2 class="w-3.5 h-3.5" :stroke-width="1.75" />
            <span>{{ t('生成今日持仓体检图', 'Generate Radar Poster') }}</span>
          </button>
        </div>
      </div>

      <!-- Unified Empty State -->
      <EmptySearchState
        v-if="filteredImpacts.length === 0"
        :query="props.searchQuery"
        :has-extra-filters="polarityFilter !== 'all' || marketFilter !== 'all' || onlyPortfolioHits"
        @clear-query="emit('clear-search')"
        @clear-filters-only="resetLocalFilters"
        @reset="resetLocalFilters(); emit('clear-search')"
      />

      <!-- Compact Ticker-Tape View -->
      <div v-else-if="viewMode === 'compact'" class="ios-card divide-y divide-black/[0.05] dark:divide-white/[0.06] overflow-hidden">
        <div
          v-for="item in filteredImpacts"
          :key="'cmp_' + item.id"
          class="mobile-pressable p-3 sm:px-4 hover:bg-black/[0.02] dark:hover:bg-white/[0.03] transition-colors"
        >
          <div class="flex flex-wrap items-center justify-between gap-2.5">
            <div class="min-w-0 w-full sm:w-auto sm:min-w-[260px] flex-1 space-y-1">
              <div class="flex flex-wrap items-center gap-1.5 text-[11px]">
                <span class="px-1.5 py-0.5 rounded-md font-semibold" :class="polarityBadgeClass(item)">
                  {{ polarityLabel(item) }}
                </span>
                <span class="px-1.5 py-0.5 rounded-md border font-medium" :class="cardEvidenceBadge(item).badgeClass">
                  {{ cardEvidenceBadge(item).shortLabel }}
                </span>
                <span
                  v-if="cardQualifiers(item).effectiveDate"
                  class="px-1.5 py-0.5 rounded-md bg-blue-500/10 text-blue-700 dark:text-blue-300 font-semibold"
                >
                  {{ cardQualifiers(item).effectiveDate }}
                </span>
                <span class="text-zinc-500 truncate">{{ pickBiText(item.tag, item.tag_en) }}</span>
              </div>
              <div class="text-sm font-semibold text-zinc-900 dark:text-white leading-snug">
                {{ pickBiText(item.event_title, item.event_title_en) }}
              </div>
            </div>
            <div class="flex flex-wrap items-center gap-1.5 min-w-0 max-w-full sm:shrink-0">
              <span
                v-for="bar in sortedBars(item).slice(0, 3)"
                :key="'cb_' + bar.market + bar.sector"
                class="px-2 py-0.5 rounded-lg text-[11px] font-mono font-bold tabular-nums max-w-full whitespace-nowrap"
                :class="((bar.pct_low + bar.pct_high) / 2) >= 0 ? marketUpBadgeClass() : marketDownBadgeClass()"
              >
                {{ bar.proxy_ticker || marketLabel(bar.market) }} {{ formatRange(bar) }}
              </span>
              <button
                type="button"
                @click="compactExpandedId = compactExpandedId === item.id ? null : item.id"
                class="px-2 min-h-[28px] rounded-lg border border-black/[0.08] dark:border-white/[0.1] text-[11px] font-medium text-[#007AFF] dark:text-[#0A84FF]"
              >
                {{ compactExpandedId === item.id ? t('收起', 'Hide') : t('详情 ▾', 'Details ▾') }}
              </button>
            </div>
          </div>

          <div v-if="compactExpandedId === item.id" class="mt-2.5 pt-2.5 border-t border-black/[0.05] dark:border-white/[0.06] space-y-2 text-xs">
            <p class="text-zinc-600 dark:text-zinc-300 leading-relaxed">{{ pickBiText(item.one_liner, item.one_liner_en) }}</p>
            <div v-if="item.priced_in_analysis?.expectation_gap" class="rounded-xl bg-[#F5F7FA] dark:bg-[#252528] px-2.5 py-2 text-zinc-700 dark:text-zinc-200">
              <strong>{{ t('预期差：', 'Expectation Gap: ') }}</strong>{{ item.priced_in_analysis.expectation_gap }}
            </div>
            <button
              type="button"
              @click="viewMode = 'cards'; expandedId = item.id"
              class="text-[11px] font-semibold text-[#007AFF] hover:underline"
            >
              {{ t('在标准卡片视图中打开四维深研面板 →', 'Open 4-Dimension Panel in Cards View →') }}
            </button>
          </div>
        </div>
      </div>

      <!-- 2-Column Per-Event Market Transmission Cards -->
      <div v-else class="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <article
          v-for="item in filteredImpacts"
          :key="item.id"
          class="ios-card p-3.5 sm:p-4 flex flex-col justify-between gap-2.5 transition-all"
          :class="portfolioMatchMap[item.id]?.matched ? 'ring-1 ring-[#007AFF]/30' : ''"
        >
          <div class="space-y-2">
            <!-- Portfolio Exposure Strip -->
            <div
              v-if="portfolioMatchMap[item.id]?.matched"
              class="rounded-xl bg-[#F2F2F7] dark:bg-[#2C2C2E] px-2.5 py-1 text-[11px] flex items-center justify-between gap-2"
            >
              <span class="font-medium text-zinc-700 dark:text-zinc-200 inline-flex items-center gap-1 min-w-0 flex-1">
                <Briefcase class="w-3 h-3 shrink-0 text-[#007AFF]" :stroke-width="1.5" />
                <span class="truncate">{{ portfolioMatchMap[item.id].tags.join(' · ') }}</span>
              </span>
              <span
                class="font-mono font-bold tabular-nums whitespace-nowrap shrink-0"
                :class="portfolioMatchMap[item.id].avgDelta >= 0 ? marketUpTextClass() : marketDownTextClass()"
              >
                {{ portfolioMatchMap[item.id].avgDelta >= 0 ? `+${portfolioMatchMap[item.id].avgDelta}%` : `${portfolioMatchMap[item.id].avgDelta}%` }}
              </span>
            </div>

            <!-- Clean Header (no collision between rule tag & timestamp) -->
            <div class="space-y-1 text-xs">
              <div class="flex flex-wrap items-center gap-1.5 min-w-0">
                <span class="px-1.5 py-0.5 rounded-md font-semibold shrink-0 whitespace-nowrap" :class="polarityBadgeClass(item)">
                  {{ polarityLabel(item) }}
                </span>
                <span
                  class="px-1.5 py-0.5 rounded-md border text-[11px] font-semibold shrink-0 whitespace-nowrap"
                  :class="cardEvidenceBadge(item).badgeClass"
                  :title="cardEvidenceBadge(item).label"
                >
                  {{ cardEvidenceBadge(item).label }}
                </span>
                <span
                  v-if="cardQualifiers(item).effectiveDate"
                  class="px-1.5 py-0.5 rounded-md bg-blue-500/12 text-blue-700 dark:text-blue-300 text-[11px] font-bold shrink-0 whitespace-nowrap"
                >
                  {{ cardQualifiers(item).effectiveDate }}
                </span>
                <span
                  v-if="cardQualifiers(item).qualifier"
                  class="px-1.5 py-0.5 rounded-md bg-amber-500/12 text-amber-800 dark:text-amber-300 text-[11px] font-semibold shrink-0 whitespace-nowrap"
                >
                  {{ cardQualifiers(item).qualifier }}
                </span>
                <span
                  v-if="item.priced_in_analysis?.status_label"
                  class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md text-[11px] font-semibold shrink-0 whitespace-nowrap"
                  :class="pricedInBadgeClass(item.priced_in_analysis.status_code)"
                >
                  <Clock class="w-3 h-3" />
                  {{ pickBiText(item.priced_in_analysis.status_label, item.priced_in_analysis.status_label_en) }}
                </span>
                <span class="text-zinc-600 dark:text-zinc-300 font-medium break-words">
                  {{ pickBiText(item.tag, item.tag_en) }}
                </span>
              </div>
              <div class="text-[11px] text-zinc-400 tabular-nums flex flex-wrap items-center gap-1.5">
                <SmartTime :iso="item.published_at" :now-ms="effectiveNowMs" />
                <span>·</span>
                <span>{{ translateSourceName(item.source_name, item.event_title) }}</span>
              </div>
            </div>

            <!-- Event Headline & Full Unclipped Logic One-Liner -->
            <div class="space-y-1">
              <h3 class="text-[16px] sm:text-[17px] font-semibold text-zinc-950 dark:text-[#F2F2F7] leading-[1.35]">
                {{ pickBiText(item.event_title, item.event_title_en) }}
              </h3>
              <p class="text-[13px] text-zinc-600 dark:text-zinc-300 leading-[1.5]">
                {{ pickBiText(item.one_liner, item.one_liner_en) }}
              </p>
            </div>

            <!-- ① Expectation-Gap & Session Pricing Callout -->
            <div
              v-if="item.priced_in_analysis?.expectation_gap"
              class="rounded-xl bg-[#F5F7FA] dark:bg-[#252528] border border-black/[0.05] dark:border-white/[0.07] px-2.5 py-2 text-[12px] text-zinc-700 dark:text-zinc-200 leading-relaxed"
            >
              <span class="font-semibold text-[#007AFF] dark:text-[#64D2FF]">{{ t('预期差拆解：', 'Expectation Gap: ') }}</span>
              <span>{{ item.priced_in_analysis.expectation_gap }}</span>
            </div>

            <!-- ② Tier-1 Direct Stock Exposure Chips (prioritizing active market filter) -->
            <div v-if="sortedTier1Stocks(item).length > 0" class="flex flex-wrap items-center gap-1.5 text-[11px]">
              <span class="text-zinc-400 font-medium shrink-0">{{ t('核心映射：', 'Key Plays:') }}</span>
              <span
                v-for="stk in sortedTier1Stocks(item).slice(0, 4)"
                :key="stk.code"
                class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md border font-medium whitespace-nowrap"
                :class="
                  stk.direction === 'negative'
                    ? (isRedUp()
                      ? 'border-emerald-200 dark:border-emerald-900/60 bg-emerald-50/70 dark:bg-emerald-950/30 text-emerald-700 dark:text-emerald-300'
                      : 'border-rose-200 dark:border-rose-900/60 bg-rose-50/70 dark:bg-rose-950/30 text-rose-700 dark:text-rose-300')
                    : 'border-black/[0.08] dark:border-white/[0.1] bg-white dark:bg-[#2C2C2E] text-zinc-800 dark:text-zinc-100'
                "
              >
                <span>{{ stk.name }}</span>
                <span class="font-mono text-[10px] opacity-75">{{ stk.code }}</span>
              </span>
            </div>

            <!-- Realized Quotes -->
            <div v-if="mergedQuoteList(item).length > 0" class="flex flex-wrap items-center gap-1.5 text-[11px] text-zinc-500 dark:text-zinc-400 tabular-nums">
              <span
                v-for="rq in mergedQuoteList(item)"
                :key="rq.ticker"
                class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-[#F2F2F7] dark:bg-[#2C2C2E] font-mono transition-all duration-300"
                :class="
                  flashingTickers[rq.ticker] === 'up'
                    ? (isRedUp() ? 'ring-1 ring-rose-500/50 bg-rose-50/70 dark:bg-rose-950/30' : 'ring-1 ring-emerald-500/50 bg-emerald-50/70 dark:bg-emerald-950/30')
                    : flashingTickers[rq.ticker] === 'down'
                      ? (isRedUp() ? 'ring-1 ring-emerald-500/50 bg-emerald-50/70 dark:bg-emerald-950/30' : 'ring-1 ring-rose-500/50 bg-rose-50/70 dark:bg-rose-950/30')
                      : ''
                "
              >
                <span class="text-zinc-600 dark:text-zinc-300 font-sans">{{ pickBiText(rq.name, rq.name_en) }}</span>
                <span class="text-zinc-900 dark:text-white font-semibold">{{ rq.price }}</span>
                <span
                  v-if="rq.pct_change != null"
                  :class="rq.pct_change >= 0 ? marketUpTextClass() : marketDownTextClass()"
                >
                  {{ rq.pct_change >= 0 ? `+${rq.pct_change}%` : `${rq.pct_change}%` }}
                </span>
              </span>
            </div>

            <!-- Diverging Horizontal Sensitivity Bars (Market-filter sorted so matching market bars sit at the top) -->
            <div v-if="item.bars.length > 0" class="pt-1 space-y-2">
              <div
                v-for="bar in (expandedId === item.id ? sortedBars(item) : sortedBars(item).slice(0, 3))"
                :key="bar.market + bar.sector"
                class="space-y-1 rounded-lg transition-colors"
                :class="marketFilter !== 'all' && bar.market === marketFilter ? 'bg-blue-50/50 dark:bg-blue-950/20 px-1.5 py-1 -mx-1.5' : ''"
              >
                <div class="flex items-start justify-between gap-2 text-xs">
                  <div class="flex items-baseline gap-1.5 min-w-0 flex-1">
                    <span
                      class="text-[11px] font-semibold shrink-0 whitespace-nowrap"
                      :class="marketFilter !== 'all' && bar.market === marketFilter ? 'text-[#007AFF] dark:text-[#64D2FF]' : 'text-zinc-400'"
                    >
                      {{ marketLabel(bar.market) }}
                    </span>
                    <span class="font-medium text-zinc-800 dark:text-zinc-200 leading-snug break-words">
                      {{ cleanSectorTitle(bar.market, pickBiText(bar.sector, bar.sector_en)) }}
                    </span>
                  </div>
                  <span
                    class="font-mono font-semibold text-xs tabular-nums whitespace-nowrap shrink-0 inline-flex items-center gap-0.5 pt-0.5"
                    :class="barGeometry(bar).isPositive ? marketUpTextClass() : marketDownTextClass()"
                  >
                    <ArrowUpRight v-if="barGeometry(bar).isPositive" class="w-3 h-3" :stroke-width="1.75" />
                    <ArrowDownRight v-else class="w-3 h-3" :stroke-width="1.75" />
                    {{ formatRange(bar) }}
                  </span>
                </div>

                <div class="relative h-1.5 rounded-full bg-black/[0.06] dark:bg-white/[0.08] overflow-hidden">
                  <div class="absolute left-1/2 top-0 bottom-0 w-px bg-zinc-400/70 z-10" />
                  <div
                    class="absolute top-0 bottom-0 rounded-full transition-all"
                    :class="barGeometry(bar).isPositive ? marketUpBarBgClass() : marketDownBarBgClass()"
                    :style="{ left: barGeometry(bar).left, width: barGeometry(bar).width }"
                  />
                </div>
              </div>
            </div>

            <!-- Inline Collapsible Source Briefing Panel (Preserves Scroll & Context!) -->
            <div
              v-if="inlineBriefId === item.id"
              class="rounded-xl border border-blue-200 dark:border-blue-800/80 bg-blue-50/50 dark:bg-blue-950/25 p-3 space-y-2 text-xs"
            >
              <div class="font-semibold text-blue-900 dark:text-blue-200 flex items-center justify-between gap-2">
                <span class="inline-flex items-center gap-1">
                  <FileText class="w-3.5 h-3.5" />
                  {{ t('原简报依据详情', 'Underlying Brief Evidence') }}
                </span>
                <button
                  type="button"
                  @click="emit('mark-read-event-id', item.event_id); emit('jump-event-id', item.event_id)"
                  class="text-[11px] font-semibold text-blue-700 dark:text-blue-300 hover:underline"
                >
                  {{ t('在今日要闻全文定位 →', 'Open in Full Briefings →') }}
                </button>
              </div>
              <p class="text-slate-700 dark:text-slate-200 leading-relaxed">
                {{ pickBiText(item.event_summary || item.one_liner, item.event_summary_en || item.one_liner_en) }}
              </p>
              <div v-if="(item.sources || []).length > 0" class="flex flex-wrap gap-2 pt-0.5">
                <template v-for="(src, sidx) in item.sources" :key="src.url || sidx">
                  <a
                    v-if="normalizeExternalUrl(src.url)"
                    :href="normalizeExternalUrl(src.url)!"
                    target="_blank"
                    rel="noopener noreferrer"
                    @click.stop="item.event_id && emit('mark-read-event-id', item.event_id)"
                    class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-white dark:bg-slate-900 border border-blue-200 dark:border-blue-800 text-[11px] text-blue-700 dark:text-blue-300 hover:underline"
                  >
                    <span>{{ translateSourceName(src.source_name, item.event_title) }}</span>
                    <ExternalLink class="w-3 h-3" />
                  </a>
                  <span
                    v-else
                    class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800/70 text-[11px] text-slate-400"
                  >
                    {{ translateSourceName(src.source_name, item.event_title) }}（{{ t('暂无直链', 'No Link') }}）
                  </span>
                </template>
              </div>
            </div>
          </div>

          <!-- Footer Controls -->
          <div class="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-100 dark:border-slate-800 text-xs">
            <div class="flex flex-wrap items-center gap-1.5">
              <button
                type="button"
                @click="toggleInlineBrief(item)"
                class="inline-flex items-center gap-1 px-2.5 min-h-[34px] sm:min-h-[26px] rounded-lg border border-blue-200 dark:border-blue-800 bg-blue-50/70 dark:bg-blue-950/30 font-medium text-blue-700 dark:text-blue-300 hover:bg-blue-100"
              >
                <FileText class="w-3 h-3" />
                <span>{{ inlineBriefId === item.id ? t('收起原简报', 'Hide Brief') : t('原简报', 'Brief') }}</span>
              </button>
              <a
                v-if="normalizeExternalUrl(item.source_url)"
                :href="normalizeExternalUrl(item.source_url)!"
                target="_blank"
                rel="noopener noreferrer"
                @click.stop="item.event_id && emit('mark-read-event-id', item.event_id)"
                class="inline-flex items-center gap-1 px-2 min-h-[34px] sm:min-h-[26px] rounded-lg text-slate-600 dark:text-slate-300 hover:text-blue-600"
              >
                <span>{{ t('原文', 'Source') }}</span>
                <ExternalLink class="w-3 h-3" />
              </a>
              <span
                v-else
                class="inline-flex items-center px-2 min-h-[34px] sm:min-h-[26px] rounded-lg text-[11px] text-slate-400 cursor-not-allowed"
              >
                {{ t('暂无原文直链', 'No Direct Link') }}
              </span>
              <button
                v-if="countItemNotes(item) > 0"
                type="button"
                @click="emit('open-notes')"
                class="inline-flex items-center gap-1 px-2 min-h-[28px] sm:min-h-[26px] rounded-lg bg-amber-500/12 text-amber-800 dark:bg-amber-400/15 dark:text-amber-200 text-[11px] font-semibold hover:underline"
              >
                <FileText class="w-3 h-3 shrink-0" :stroke-width="1.75" />
                <span>{{ t(`你曾在此标的记录过 ${countItemNotes(item)} 条笔记`, `${countItemNotes(item)} notes`) }}</span>
              </button>
            </div>
            <button
              v-if="item.bars.length > 0"
              type="button"
              @click="toggleDeepAnalysis(item)"
              class="inline-flex items-center gap-1 px-2.5 min-h-[34px] sm:min-h-[26px] rounded-lg bg-slate-50 sm:bg-transparent dark:bg-slate-800/70 sm:dark:bg-transparent font-medium text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white"
            >
              <span>{{ expandedId === item.id ? t('收起深度拆解', 'Hide Analysis') : t('三阶标的 · 历史回放 · 水位线', 'Deep Research & Precedents') }}</span>
              <ChevronUp v-if="expandedId === item.id" class="w-3.5 h-3.5" />
              <ChevronDown v-else class="w-3.5 h-3.5" />
            </button>
          </div>

          <!-- Zero-UGC 1-Click Market Sentiment Reaction Bar -->
          <div class="pt-1.5 space-y-1">
            <div class="flex flex-wrap items-center justify-between gap-1.5 text-[11px]">
              <span class="text-zinc-400 font-medium shrink-0">{{ t('市场共识判断：', 'Market View:') }}</span>
              <div class="flex flex-wrap items-center gap-1.5">
                <button
                  v-for="opt in ([
                    { key: 'bullish_cat', label: t('看多催化', 'Bullish'), activeCls: 'bg-rose-600 text-white border-rose-600' },
                    { key: 'bearish_hedge', label: t('利空避险', 'Bearish'), activeCls: 'bg-emerald-600 text-white border-emerald-600' },
                    { key: 'priced_in', label: t('已计价', 'Priced In'), activeCls: 'bg-zinc-700 text-white border-zinc-700 dark:bg-zinc-600' },
                  ] as const)"
                  :key="opt.key"
                  type="button"
                  @click.stop="void toggleStructuredReaction('finance', item.id, opt.key)"
                  class="ios-tap inline-flex items-center gap-1 px-2 min-h-[26px] rounded-full border text-[11px] font-medium transition-colors"
                  :class="
                    getReactionSummary('finance', item.id).my_reaction === opt.key
                      ? opt.activeCls
                      : 'border-black/[0.08] dark:border-white/[0.1] bg-[#F5F5F7] dark:bg-[#2C2C2E] text-zinc-600 dark:text-zinc-300 hover:border-[#007AFF]/40'
                  "
                >
                  <span>{{ opt.label }}</span>
                  <span
                    v-if="(getReactionSummary('finance', item.id).counts[opt.key] || 0) > 0"
                    class="font-mono text-[10px] opacity-85 tabular-nums"
                  >
                    {{ getReactionSummary('finance', item.id).counts[opt.key] }}
                  </span>
                </button>
              </div>
            </div>
            <div
              v-if="getReactionSummary('finance', item.id).total > 0"
              class="h-1 rounded-full overflow-hidden flex bg-black/[0.05] dark:bg-white/[0.08]"
            >
              <div
                class="bg-rose-500 transition-all"
                :style="{ width: `${Math.round(((getReactionSummary('finance', item.id).counts.bullish_cat || 0) / getReactionSummary('finance', item.id).total) * 100)}%` }"
              />
              <div
                class="bg-emerald-500 transition-all"
                :style="{ width: `${Math.round(((getReactionSummary('finance', item.id).counts.bearish_hedge || 0) / getReactionSummary('finance', item.id).total) * 100)}%` }"
              />
              <div
                class="bg-zinc-400 transition-all"
                :style="{ width: `${Math.round(((getReactionSummary('finance', item.id).counts.priced_in || 0) / getReactionSummary('finance', item.id).total) * 100)}%` }"
              />
            </div>
          </div>

          <!-- Expanded 4-Dimension V9 Deep Research Drawer -->
          <div v-if="expandedId === item.id && item.bars.length > 0" class="pt-2.5 border-t border-dashed border-slate-200 dark:border-slate-700 space-y-3 text-xs">
            <!-- ② 3-Tier Supply Chain & Core Stock Exposure -->
            <div v-if="(item.transmission_layers || []).length > 0" class="space-y-1.5" data-testid="transmission-layers-panel">
              <div class="font-semibold text-slate-800 dark:text-slate-100 flex items-center gap-1.5">
                <Layers class="w-3.5 h-3.5 text-[#007AFF]" />
                <span>{{ t('三阶产业链穿透与核心标的暴露：', '3-Tier Supply-Chain & Stock Exposure:') }}</span>
              </div>
              <div class="space-y-2">
                <div
                  v-for="layer in item.transmission_layers"
                  :key="layer.tier"
                  class="rounded-xl border border-black/[0.06] dark:border-white/[0.08] bg-[#F8F9FB] dark:bg-[#242426] p-2.5 space-y-1.5"
                >
                  <div class="font-semibold text-zinc-900 dark:text-white">{{ layer.tier_label }}</div>
                  <p class="text-[11.5px] text-zinc-600 dark:text-zinc-300 leading-relaxed">{{ layer.summary }}</p>
                  <ul v-if="(layer.stocks || []).length > 0" class="space-y-1 pt-0.5">
                    <li v-for="stk in layer.stocks" :key="stk.code" class="text-[11.5px] leading-snug text-zinc-700 dark:text-zinc-200">
                      <span
                        class="inline-block px-1.5 py-0.5 rounded font-mono text-[10.5px] font-semibold mr-1.5"
                        :class="
                          stk.direction === 'negative'
                            ? marketDownBadgeClass()
                            : stk.direction === 'positive'
                              ? marketUpBadgeClass()
                              : 'bg-zinc-200 dark:bg-zinc-700 text-zinc-700 dark:text-zinc-200'
                        "
                      >{{ stk.name }} {{ stk.code }}</span>
                      <span>{{ stk.exposure_logic }}</span>
                    </li>
                  </ul>
                </div>
              </div>
            </div>

            <!-- ③ Historical Precedents Replay Table -->
            <div v-if="(item.historical_precedents || []).length > 0" class="space-y-1.5" data-testid="historical-precedents-panel">
              <div class="font-semibold text-slate-800 dark:text-slate-100 flex items-center gap-1.5">
                <History class="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" />
                <span>{{ t('历史同类真实事件回放对照：', 'Historical Benchmark Precedents:') }}</span>
              </div>
              <div class="space-y-1.5">
                <div
                  v-for="(prec, pIdx) in item.historical_precedents"
                  :key="pIdx"
                  class="rounded-xl border border-black/[0.06] dark:border-white/[0.08] bg-white dark:bg-[#1E1E20] p-2.5 space-y-1"
                >
                  <div class="flex flex-wrap items-baseline gap-1.5">
                    <span class="px-1.5 py-0.5 rounded bg-zinc-100 dark:bg-zinc-800 font-mono text-[10.5px] font-bold text-zinc-700 dark:text-zinc-200">{{ prec.date }}</span>
                    <span class="font-semibold text-zinc-900 dark:text-white">{{ prec.event_title }}</span>
                  </div>
                  <div class="text-[11.5px] text-zinc-600 dark:text-zinc-300 space-y-0.5">
                    <div><strong>T+1：</strong>{{ prec.t1_reaction }}</div>
                    <div><strong>T+5：</strong>{{ prec.t5_reaction }}</div>
                    <div v-if="prec.lesson" class="text-[#007AFF] dark:text-[#64D2FF]"><strong>{{ t('复盘启示：', 'Takeaway: ') }}</strong>{{ prec.lesson }}</div>
                  </div>
                </div>
              </div>
            </div>

            <!-- ④ Quantitative Numeric Threshold Conditions -->
            <div v-if="(item.quant_if_then || []).length > 0" class="space-y-1.5" data-testid="quant-if-then-panel">
              <div class="font-semibold text-slate-800 dark:text-slate-100 flex items-center gap-1.5">
                <Target class="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                <span>{{ t('量化盘面水位线（带硬阈值触发）：', 'Quantitative Market Triggers:') }}</span>
              </div>
              <div class="space-y-1.5">
                <div
                  v-for="(qcond, qIdx) in item.quant_if_then"
                  :key="qIdx"
                  class="rounded-xl px-2.5 py-2 space-y-0.5"
                  :class="
                    qcond.case === 'bull'
                      ? marketUpBadgeClass()
                      : qcond.case === 'bear'
                        ? marketDownBadgeClass()
                        : 'bg-[#F5F5F7] dark:bg-[#2C2C2E] text-zinc-700 dark:text-zinc-300'
                  "
                >
                  <div class="font-semibold">{{ qcond.label }} · {{ qcond.trigger_metric }}</div>
                  <div class="font-mono text-[11px] opacity-95">{{ qcond.threshold }}</div>
                  <div class="opacity-90">→ {{ qcond.action_implication }}</div>
                </div>
              </div>
            </div>
            <div v-else-if="item.if_then.length > 0" class="space-y-1.5">
              <div class="font-semibold text-slate-700 dark:text-slate-200">{{ t('若 / 则条件推演：', 'If / Then Scenarios:') }}</div>
              <div
                v-for="(cond, idx) in item.if_then"
                :key="idx"
                class="rounded-xl px-2.5 py-1.5"
                :class="
                  cond.tone === 'bullish'
                    ? marketUpBadgeClass()
                    : cond.tone === 'bearish'
                      ? marketDownBadgeClass()
                      : 'bg-[#F5F5F7] dark:bg-[#2C2C2E] text-zinc-700 dark:text-zinc-300'
                "
              >
                <span class="font-semibold">{{ cond.cond }}</span> → {{ cond.result }}
              </div>
            </div>

            <div class="space-y-1">
              <div class="font-semibold text-slate-700 dark:text-slate-200">{{ t('各板块传导逻辑：', 'Sector Transmission Logic:') }}</div>
              <ul class="space-y-1 text-slate-600 dark:text-slate-300">
                <li v-for="bar in sortedBars(item)" :key="'lg_' + bar.market + bar.sector">
                  <strong class="text-slate-700 dark:text-slate-200">{{ marketLabel(bar.market) }} · {{ cleanSectorTitle(bar.market, pickBiText(bar.sector, bar.sector_en)) }}：</strong>
                  {{ pickBiText(bar.logic, bar.logic_en) }}
                </li>
              </ul>
            </div>

            <div v-if="item.milestones.length > 0" class="space-y-1">
              <div class="font-semibold text-slate-700 dark:text-slate-200">{{ t('后续关键观察节点：', 'Key Verification Milestones:') }}</div>
              <div class="flex flex-wrap gap-1.5">
                <span
                  v-for="(ms, mIdx) in item.milestones"
                  :key="mIdx"
                  class="px-2 py-0.5 rounded-full border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-[11px]"
                >
                  {{ ms.date }} · {{ ms.label }}
                </span>
              </div>
            </div>
          </div>
        </article>
      </div>
    </template>
  </section>
</template>
