<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { CheckCheck, ExternalLink } from 'lucide-vue-next'
import EmptySearchState from '../EmptySearchState.vue'
import LoadingSkeleton from '../LoadingSkeleton.vue'
import SmartTime from '../SmartTime.vue'
import type { LiveWireDoc, LiveWireItem, WatchlistItem } from '../../core/types'
import type { WireTransportMode } from '../../core/wireStream'
import { extractHeadlineQualifiers, resolveEvidenceTierBadge } from '../../core/evidence'
import { centerPillIntoView } from '../../core/dom'
import { formatWireHeadline, pickBiText, stripMarkdownArtifacts, t, translateSourceName, truncateAtSentence } from '../../core/i18n'
import { normalizeExternalUrl } from '../../core/legacyAdapter'
import { matchesSmartQuery } from '../../core/search'
import { formatShanghaiDateOnly, parseTimestampMs } from '../../core/time'
import { markAllWireRead, markWireRead, wireReadIdSet } from '../../core/uiPrefs'

const props = defineProps<{
  doc: LiveWireDoc | null
  searchQuery?: string
  watchlist?: WatchlistItem[]
  nowMs?: number
  loading?: boolean
  transportMode?: WireTransportMode
  justArrivedIds?: string[]
}>()

const emit = defineEmits<{
  (e: 'clear-search'): void
}>()

type WireCat = 'all' | 'high' | 'major' | 'watchlist' | 'macro' | 'ai' | 'semi' | 'biz'
const WIRE_CATS: WireCat[] = ['all', 'high', 'major', 'watchlist', 'macro', 'ai', 'semi', 'biz']

const catFilter = ref<WireCat>('all')
const expandedId = ref<string | null>(null)
const effectiveNowMs = computed(() => props.nowMs ?? Date.now())

const items = computed<LiveWireItem[]>(() => props.doc?.items ?? [])
const arrivedSet = computed(() => new Set(props.justArrivedIds ?? []))
const effectiveQuery = computed(() => (props.searchQuery || '').trim())

const WIRE_CONSUMER_NOISE_RE = /优惠券|买赠|促销|折扣|9\.9元|黑五|black friday|手游|主机游戏|steam|演唱会|剧场版|车机|购车|输入法内测|调查问卷/i

function matchesWireTopic(it: LiveWireItem, topic: WireCat): boolean {
  const hay = `${it.title} ${it.title_en || ''} ${it.excerpt || ''}`.toLowerCase()
  if (topic === 'high') {
    return !WIRE_CONSUMER_NOISE_RE.test(hay) && it.importance === 'high'
  }
  if (topic === 'major') {
    if (WIRE_CONSUMER_NOISE_RE.test(hay)) return false
    return (
      it.importance === 'high' ||
      /央行|证监会|沪深|两融|降准|降息|美联储|fomc|cpi|gdp|关税|白宫|特朗普|openai|gemini|claude|anthropic|英伟达|nvidia|tsmc|台积电|hbm|tpu|芯片|光模块|科创板|回购|涨价/i.test(
        hay,
      )
    )
  }
  if (topic === 'watchlist') {
    const wl = (props.watchlist || []).filter((w) => !w.muted)
    if (wl.length === 0) return false
    return wl.some((w) =>
      [w.label, ...(w.keywords || [])].some((kw) => kw && kw.trim().length >= 2 && hay.includes(kw.trim().toLowerCase())),
    )
  }
  if (topic === 'macro') {
    return it.category === 'global' || it.category === 'finance' || /央行|证监会|沪深|美联储|fomc|关税|通胀|gdp|cpi|汇率|两融|国债|降息/i.test(hay)
  }
  if (topic === 'ai') {
    return /ai|大模型|llm|openai|gpt|claude|anthropic|gemini|deepseek|千问|qwen|智谱|glm|agent|算力|模型/i.test(hay)
  }
  if (topic === 'semi') {
    return /芯片|半导体|英伟达|nvidia|台积电|tsmc|海力士|三星|hbm|tpu|asic|光模块|cpo|pcb|存储|服务器/i.test(hay)
  }
  if (topic === 'biz') {
    return /ipo|并购|回购|财报|营收|出海|跨境|电商|汽车|火箭|电信|运营商|涨价/i.test(hay)
  }
  return true
}

const heavyWireCount = computed(() => items.value.filter((it) => matchesWireTopic(it, 'high')).length)

const filtered = computed(() => {
  const q = effectiveQuery.value.trim()
  return items.value.filter((it) => {
    if (catFilter.value !== 'all' && !matchesWireTopic(it, catFilter.value)) return false
    if (q && !matchesSmartQuery(`${it.title} ${it.title_en || ''} ${it.excerpt} ${it.source_name}`, q)) return false
    return true
  })
})

const unreadIds = computed(() =>
  filtered.value.filter((it) => !wireReadIdSet.value.has(it.id)).map((it) => it.id),
)

// Time grouping (Asia/Shanghai): 今天下午 / 今天上午 / 昨天 / 更早
interface WireGroup {
  id: string
  label: string
  shortLabel: string
  items: LiveWireItem[]
}

function getTimeBucket(iso: string | undefined, nowMsVal: number): { id: string; label: string; shortLabel: string } {
  const ms = parseTimestampMs(iso)
  if (ms === null) {
    return { id: 'earlier', label: t('更早', 'Earlier'), shortLabel: t('早', 'Old') }
  }
  const todayStr = formatShanghaiDateOnly(new Date(nowMsVal).toISOString())
  const yesterdayStr = formatShanghaiDateOnly(new Date(nowMsVal - 86_400_000).toISOString())
  const itemDate = formatShanghaiDateOnly(new Date(ms).toISOString())

  if (itemDate === todayStr) {
    // Shanghai hour = UTC hour + 8 mod 24
    const shHour = (new Date(ms).getUTCHours() + 8) % 24
    if (shHour >= 12) {
      return { id: 'today_pm', label: t('今天下午', 'Today PM'), shortLabel: t('午', 'PM') }
    }
    return { id: 'today_am', label: t('今天上午', 'Today AM'), shortLabel: t('早', 'AM') }
  }
  if (itemDate === yesterdayStr) {
    return { id: 'yesterday', label: t('昨天', 'Yesterday'), shortLabel: t('昨', 'Yst') }
  }
  return { id: 'earlier', label: t('更早', 'Earlier'), shortLabel: t('前', 'Old') }
}

// Lightweight virtual windowing for long wire streams (renders visible slice + generous overscan)
const ROW_ESTIMATE_PX = 86
const scrollY = ref(0)
const viewportH = ref(typeof window !== 'undefined' ? window.innerHeight : 800)

function onWindowScroll() {
  scrollY.value = window.scrollY || 0
  viewportH.value = window.innerHeight || 800
}

onMounted(() => {
  if (typeof window !== 'undefined') {
    window.addEventListener('scroll', onWindowScroll, { passive: true })
    window.addEventListener('resize', onWindowScroll, { passive: true })
  }
})

onUnmounted(() => {
  if (typeof window !== 'undefined') {
    window.removeEventListener('scroll', onWindowScroll)
    window.removeEventListener('resize', onWindowScroll)
  }
})

// Flatten groups into virtualizable rows (headers + items)
type VirtualRow =
  | { kind: 'header'; key: string; groupId: string; label: string; count: number }
  | { kind: 'item'; key: string; item: LiveWireItem }

const grouped = computed<WireGroup[]>(() => {
  const map = new Map<string, WireGroup>()
  const order = ['today_pm', 'today_am', 'yesterday', 'earlier']
  for (const it of filtered.value) {
    const b = getTimeBucket(it.published_at, effectiveNowMs.value)
    let g = map.get(b.id)
    if (!g) {
      g = { id: b.id, label: b.label, shortLabel: b.shortLabel, items: [] }
      map.set(b.id, g)
    }
    g.items.push(it)
  }
  return order.map((id) => map.get(id)).filter((g): g is WireGroup => Boolean(g && g.items.length > 0))
})

const flatRows = computed<VirtualRow[]>(() => {
  const rows: VirtualRow[] = []
  for (const g of grouped.value) {
    rows.push({ kind: 'header', key: `hdr-${g.id}`, groupId: g.id, label: g.label, count: g.items.length })
    for (const it of g.items) {
      rows.push({ kind: 'item', key: it.id, item: it })
    }
  }
  return rows
})

const shouldVirtualize = computed(() => flatRows.value.length > 40)

const virtualWindow = computed(() => {
  const total = flatRows.value.length
  if (!shouldVirtualize.value) {
    return { start: 0, end: total, topPad: 0, bottomPad: 0 }
  }
  const approxStart = Math.floor(Math.max(0, scrollY.value - 120) / ROW_ESTIMATE_PX)
  const visibleCount = Math.ceil(viewportH.value / ROW_ESTIMATE_PX) + 14
  const start = Math.max(0, approxStart - 8)
  const end = Math.min(total, start + visibleCount + 10)
  return {
    start,
    end,
    topPad: start * ROW_ESTIMATE_PX,
    bottomPad: Math.max(0, (total - end) * ROW_ESTIMATE_PX),
  }
})

const visibleRows = computed(() => flatRows.value.slice(virtualWindow.value.start, virtualWindow.value.end))

function jumpToGroup(groupId: string) {
  const idx = flatRows.value.findIndex((r) => r.kind === 'header' && r.groupId === groupId)
  if (idx < 0) return
  if (shouldVirtualize.value) {
    window.scrollTo({ top: Math.max(0, idx * ROW_ESTIMATE_PX + 56), behavior: 'smooth' })
  } else {
    document.getElementById(`wire-group-${groupId}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}

// Horizontal swipe between wire category tabs
let swipeX0 = 0
let swipeY0 = 0
function onWireTouchStart(e: TouchEvent) {
  if (e.touches.length !== 1) return
  swipeX0 = e.touches[0].clientX
  swipeY0 = e.touches[0].clientY
}
function onWireTouchEnd(e: TouchEvent) {
  if (!e.changedTouches.length) return
  const dx = e.changedTouches[0].clientX - swipeX0
  const dy = e.changedTouches[0].clientY - swipeY0
  if (Math.abs(dx) < 68 || Math.abs(dx) < Math.abs(dy) * 1.6) return
  const idx = WIRE_CATS.indexOf(catFilter.value)
  if (dx < 0 && idx < WIRE_CATS.length - 1) {
    catFilter.value = WIRE_CATS[idx + 1]
  } else if (dx > 0 && idx > 0) {
    catFilter.value = WIRE_CATS[idx - 1]
  }
}

watch(catFilter, () => {
  if (typeof window !== 'undefined' && window.scrollY > 120) {
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }
})

function handleToggleExpand(it: LiveWireItem) {
  markWireRead(it.id)
  expandedId.value = expandedId.value === it.id ? null : it.id
}

function catLabel(cat: string): string {
  if (cat === 'finance') return t('财经', 'Markets')
  if (cat === 'tech') return t('科技', 'Tech')
  if (cat === 'global') return t('国际', 'Global')
  return t('综合', 'General')
}

function clearAll() {
  catFilter.value = 'all'
  emit('clear-search')
}
</script>

<template>
  <section
    class="space-y-2 relative"
    :aria-label="t('7×24 全球电报', '7×24 Live Wire')"
    @touchstart.passive="onWireTouchStart"
    @touchend.passive="onWireTouchEnd"
  >
    <!-- Ultra-Slim Single-Row iOS Segmented Filter Bar (Smart Sticky on <768px) -->
    <div class="mobile-sticky-subbar flex items-center justify-between gap-2" data-testid="wire-sticky-subbar">
      <div class="ios-segmented flex-1 sm:flex-initial overflow-x-auto no-scrollbar scroll-fade-x">
        <button
          v-for="tab in ([
            { k: 'all', label: t('全部', 'All') },
            { k: 'high', label: t(`突发急电 (${heavyWireCount})`, `Flash Alerts (${heavyWireCount})`) },
            { k: 'major', label: t('精选干货', 'Key Wire') },
            { k: 'watchlist', label: t('命中关注', 'Watch') },
            { k: 'macro', label: t('宏观与政策', 'Macro') },
            { k: 'ai', label: t('AI 与大模型', 'AI') },
            { k: 'semi', label: t('半导体与算力链', 'Compute') },
            { k: 'biz', label: t('商业与出海', 'Biz') },
          ] as const)"
          :key="tab.k"
          type="button"
          @click="(e) => { catFilter = tab.k; centerPillIntoView(e) }"
          class="mobile-pressable ios-segmented-btn flex-1 sm:flex-initial min-h-[34px] px-2.5 sm:px-3 whitespace-nowrap inline-flex items-center justify-center gap-1.5 shrink-0"
          :class="
            catFilter === tab.k
              ? tab.k === 'high' || tab.k === 'major'
                ? 'bg-[#DC2626] text-white shadow-xs font-bold jx-heavy-capsule'
                : 'ios-segmented-btn-active'
              : tab.k === 'high'
                ? 'text-[#DC2626] dark:text-red-400 font-bold bg-red-50/80 dark:bg-red-950/30'
                : 'text-zinc-600 dark:text-zinc-400'
          "
        >
          <span
            v-if="tab.k === 'high'"
            class="jx-sonar-dot"
            :class="catFilter === 'high' ? 'jx-sonar-white' : 'jx-sonar-red'"
          />
          <span>{{ tab.label }}</span>
        </button>
      </div>

      <button
        v-if="unreadIds.length > 0"
        type="button"
        @click="markAllWireRead(unreadIds)"
        class="inline-flex items-center justify-center w-11 h-11 sm:w-auto sm:h-9 sm:px-2.5 sm:gap-1 rounded-xl text-xs font-medium text-zinc-600 dark:text-zinc-300 bg-white dark:bg-zinc-900 border border-black/[0.06] dark:border-white/[0.08] shrink-0"
        :title="t('全部标为已读', 'Mark all read')"
        :aria-label="t('全部标为已读', 'Mark all read')"
      >
        <CheckCheck class="w-4 h-4 shrink-0" />
        <span class="hidden sm:inline">{{ t('全已读', 'Read All') }}</span>
      </button>
    </div>

    <LoadingSkeleton v-if="loading && !items.length" variant="list" :count="8" />

    <EmptySearchState
      v-else-if="!filtered.length"
      :query="effectiveQuery"
      :has-extra-filters="catFilter !== 'all'"
      @clear-query="emit('clear-search')"
      @clear-filters-only="catFilter = 'all'"
      @reset="clearAll"
    />

    <!-- Grouped & Virtualized 7x24 Wire Stream (NO overflow-hidden on ancestor so sticky headers work!) -->
    <div v-else class="space-y-2">
      <!-- Compact Time-Group Quick Jump Strip (never overlaps article links) -->
      <div
        v-if="grouped.length >= 2"
        class="flex items-center gap-1.5 overflow-x-auto no-scrollbar scroll-fade-x text-[11px]"
        :aria-label="t('快讯时间快速跳转', 'Quick time index')"
      >
        <button
          v-for="g in grouped"
          :key="g.id"
          type="button"
          @click="(e) => { jumpToGroup(g.id); centerPillIntoView(e) }"
          class="mobile-pressable ios-tap min-h-[30px] px-2.5 rounded-full bg-white dark:bg-[#1C1C1E] text-zinc-600 dark:text-zinc-300 font-semibold whitespace-nowrap shrink-0"
        >
          {{ g.label }} · {{ g.items.length }}
        </button>
      </div>

      <div class="ios-card">
        <div :style="virtualWindow.topPad > 0 ? { height: `${virtualWindow.topPad}px` } : undefined" />

        <template v-for="row in visibleRows" :key="row.key">
          <!-- Sticky Time Group Header -->
          <div
            v-if="row.kind === 'header'"
            :id="`wire-group-${row.groupId}`"
            class="sticky top-0 z-20 px-3.5 py-2 bg-[#F2F2F7]/95 dark:bg-black/95 backdrop-blur-md border-b border-black/[0.05] dark:border-white/[0.08] flex items-center justify-between text-[12px] font-semibold text-zinc-500 dark:text-zinc-400 first:rounded-t-[16px]"
          >
            <span>{{ row.label }}</span>
            <span class="tabular-nums">{{ row.count }}</span>
          </div>

          <!-- Compact Wire Item Row -->
          <article
            v-else
            @click="handleToggleExpand(row.item)"
            class="mobile-pressable px-3.5 py-2.5 lg:py-2.5 border-b border-black/[0.05] dark:border-white/[0.06] last:border-b-0 flex flex-col sm:flex-row sm:items-start gap-1.5 sm:gap-4 hover:bg-black/[0.02] dark:hover:bg-white/[0.03] active:bg-black/[0.04] cursor-pointer transition-colors"
            :class="[
              arrivedSet.has(row.item.id) ? 'bg-amber-50/70 dark:bg-amber-950/20' : '',
              row.item.importance === 'high' ? 'border-l-[3px] border-l-[#DC2626] bg-red-50/25 dark:bg-red-950/10' : '',
              wireReadIdSet.has(row.item.id) && expandedId !== row.item.id ? 'opacity-65' : '',
            ]"
          >
            <!-- Fixed-Width Desktop Timestamp Column (>=164px + 16px gap, never overlaps headline; mobile wraps source badge cleanly without 1-char truncation) -->
            <div class="flex items-start justify-between gap-2 sm:flex-col sm:items-start sm:justify-start sm:gap-0.5 sm:w-[164px] sm:min-w-[164px] sm:shrink-0 sm:pr-2 text-[11px]">
              <div class="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 min-w-0 flex-1">
                <span
                  v-if="row.item.id === filtered[0]?.id"
                  class="jx-sonar-dot shrink-0"
                  :class="row.item.importance === 'high' ? 'jx-sonar-red' : 'jx-sonar-blue'"
                />
                <span
                  v-else-if="!wireReadIdSet.has(row.item.id)"
                  class="w-1.5 h-1.5 rounded-full shrink-0"
                  :class="row.item.importance === 'high' ? 'bg-[#DC2626] animate-pulse' : 'bg-blue-500'"
                />
                <span
                  class="font-mono tabular-nums whitespace-nowrap shrink-0"
                  :class="row.item.importance === 'high' ? 'text-[#DC2626] dark:text-red-400 font-bold' : 'text-zinc-500 dark:text-zinc-400'"
                >
                  <SmartTime :iso="row.item.published_at" :ingested-iso="row.item.fetched_at" :now-ms="effectiveNowMs" />
                </span>
                <span class="sm:hidden text-zinc-400 shrink-0 whitespace-nowrap">
                  {{ catLabel(row.item.category) }}
                </span>
                <span class="sm:hidden px-1.5 py-0.5 rounded bg-black/[0.04] dark:bg-white/[0.08] text-zinc-600 dark:text-zinc-300 font-medium shrink-0 whitespace-nowrap">
                  {{ translateSourceName(row.item.source_name, row.item.title) }}
                </span>
              </div>
              <span class="hidden sm:block text-[10.5px] text-zinc-400 dark:text-zinc-500 truncate max-w-full">
                {{ translateSourceName(row.item.source_name, row.item.title) || catLabel(row.item.category) }}
              </span>
              <a
                v-if="normalizeExternalUrl(row.item.url)"
                :href="normalizeExternalUrl(row.item.url)!"
                target="_blank"
                rel="noopener noreferrer"
                @click.stop="markWireRead(row.item.id)"
                class="sm:hidden w-10 h-10 -my-2 -mr-2 inline-flex items-center justify-center rounded-xl text-zinc-400 hover:text-blue-600 shrink-0"
                :aria-label="t('查看原文', 'Open source')"
              >
                <ExternalLink class="w-3.5 h-3.5" />
              </a>
            </div>

            <!-- Headline & Optional Expanded Excerpt -->
            <div class="min-w-0 flex-1 space-y-1">
              <div class="flex items-start justify-between gap-2">
                <p
                  class="text-[14px] leading-snug"
                  :class="
                    row.item.importance === 'high'
                      ? 'font-bold text-zinc-950 dark:text-white'
                      : 'font-medium text-zinc-900 dark:text-zinc-100'
                  "
                >
                  <span
                    v-if="row.item.importance === 'high'"
                    class="jx-heavy-capsule inline-flex items-center gap-1 px-1.5 py-0.5 mr-1.5 rounded bg-[#DC2626] text-white text-[10px] font-bold align-middle tracking-tight whitespace-nowrap"
                    data-testid="wire-heavy-badge"
                  >
                    <span class="jx-sonar-dot jx-sonar-white" />
                    <span>{{ t('突发急电', 'FLASH') }}{{ row.item.heavy_reason_tag ? ` · ${row.item.heavy_reason_tag}` : '' }}</span>
                  </span>
                  {{ pickBiText(formatWireHeadline(row.item.title), row.item.title_en || formatWireHeadline(row.item.title)) }}
                </p>
                <a
                  v-if="normalizeExternalUrl(row.item.url)"
                  :href="normalizeExternalUrl(row.item.url)!"
                  target="_blank"
                  rel="noopener noreferrer"
                  @click.stop="markWireRead(row.item.id)"
                  class="hidden sm:inline-flex shrink-0 text-zinc-400 hover:text-blue-600 p-1"
                  :aria-label="t('查看原文', 'Open source')"
                >
                  <ExternalLink class="w-3.5 h-3.5" />
                </a>
              </div>

              <p
                v-if="expandedId === row.item.id && row.item.excerpt && row.item.excerpt !== row.item.title"
                class="text-xs text-zinc-600 dark:text-zinc-400 leading-relaxed bg-zinc-50 dark:bg-zinc-800/60 rounded-xl px-2.5 py-2"
              >
                {{ truncateAtSentence(stripMarkdownArtifacts(row.item.excerpt), 220) }}
              </p>

              <div class="hidden sm:flex flex-wrap items-center gap-1.5 text-[11px] text-zinc-400">
                <span
                  class="px-1.5 py-0.2 rounded border text-[10px] font-semibold"
                  :class="resolveEvidenceTierBadge({ source_name: row.item.source_name, title: row.item.title, summary: row.item.excerpt }).badgeClass"
                >
                  {{ resolveEvidenceTierBadge({ source_name: row.item.source_name, title: row.item.title, summary: row.item.excerpt }).shortLabel }}
                </span>
                <span
                  v-if="extractHeadlineQualifiers(row.item.title, row.item.excerpt).effectiveDateLabel"
                  class="px-1.5 py-0.2 rounded bg-blue-500/10 text-blue-700 dark:text-blue-300 text-[10px] font-semibold"
                >
                  {{ extractHeadlineQualifiers(row.item.title, row.item.excerpt).effectiveDateLabel }}
                </span>
                <span
                  v-if="extractHeadlineQualifiers(row.item.title, row.item.excerpt).qualifierBadge"
                  class="px-1.5 py-0.2 rounded bg-amber-500/10 text-amber-700 dark:text-amber-300 text-[10px] font-semibold"
                >
                  {{ extractHeadlineQualifiers(row.item.title, row.item.excerpt).qualifierBadge }}
                </span>
                <span>{{ catLabel(row.item.category) }}</span>
                <span>·</span>
                <span>{{ translateSourceName(row.item.source_name, row.item.title) }}</span>
              </div>
            </div>
          </article>
        </template>

        <div :style="virtualWindow.bottomPad > 0 ? { height: `${virtualWindow.bottomPad}px` } : undefined" />
      </div>
    </div>
  </section>
</template>
