<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import {
  AlertTriangle,
  Bookmark,
  Check,
  CheckCircle2,
  Columns3,
  ExternalLink,
  EyeOff,
  FileText,
  Flame,
  GitBranch,
  HelpCircle,
  Link2,
  MoreHorizontal,
  NotebookPen,
  Sparkles,
  ThumbsDown,
  X,
} from 'lucide-vue-next'
import SmartTime from './SmartTime.vue'
import {
  appLang,
  pickBiText,
  stripMarkdownArtifacts,
  t,
  translateEntityName,
  translateMarketTag,
  translateSourceName,
  truncateAtSentence,
} from '../core/i18n'
import { formatShanghaiDateTime } from '../core/time'
import { extractHeadlineQualifiers, resolveEvidenceTierBadge } from '../core/evidence'
import { normalizeExternalUrl } from '../core/legacyAdapter'
import { getReactionSummary, toggleStructuredReaction } from '../core/reactionsStore'
import { buildThreeColumnPerspectives } from '../core/thumbnails'
import { getConfidentEntities } from '../core/v3Logic'
import {
  feedDensity,
  lockBodyScroll,
  marketDownBadgeClass,
  marketDownTextClass,
  marketUpBadgeClass,
  marketUpTextClass,
  triggerHaptic,
  unlockBodyScroll,
  type FeedDensity,
} from '../core/uiPrefs'
import { CATEGORIES, type InlineEventImpact, type SimulatedPerspective, type SmartEvent } from '../core/types'

const props = defineProps<{
  event: SmartEvent
  nowMs: number
  isRead: boolean
  isBookmarked: boolean
  isNewSinceVisit: boolean
  isHighlighted?: boolean
  defaultExpanded?: boolean
  controlledExpanded?: boolean
  grouped?: boolean
  featured?: boolean
  marketImpact?: InlineEventImpact | null
  thumbnailUrl?: string | null
  whyRecommended?: string[]
  matchReasons?: string[]
  perspectives?: SimulatedPerspective[]
  savedNote?: string
  density?: FeedDensity
  isReadLater?: boolean
  downweighted?: boolean
  showModerationActions?: boolean
  isKeyboardFocused?: boolean
  crossDomainBadge?: string | null
  crossDomainHint?: string | null
  matchingNoteCount?: number
}>()

const emit = defineEmits<{
  (e: 'toggle-read', event: SmartEvent): void
  (e: 'mark-read', event: SmartEvent): void
  (e: 'toggle-bookmark', event: SmartEvent): void
  (e: 'copy-link', event: SmartEvent): void
  (e: 'select-entity', entity: string): void
  (e: 'open-prev-batch', prevBatchId: string): void
  (e: 'open-storyline', storylineId: string): void
  (e: 'open-qa', event: SmartEvent): void
  (e: 'open-detail', event: SmartEvent): void
  (e: 'open-notes'): void
  (e: 'toggle-read-later', eventId: string): void
  (e: 'toggle-downweight', key: string): void
  (e: 'toggle-mute', key: string): void
  (e: 'follow-event', event: SmartEvent): void
  (e: 'save-note', payload: { event: SmartEvent; content: string }): void
  (e: 'set-expanded', expanded: boolean): void
}>()

const isDesktopWide = typeof window !== 'undefined' && window.innerWidth >= 1280
const localExpanded = ref(Boolean(props.defaultExpanded || (props.isHighlighted && !isDesktopWide)))
const expanded = computed<boolean>({
  get: () => (props.controlledExpanded !== undefined ? props.controlledExpanded : localExpanded.value),
  set: (val: boolean) => {
    localExpanded.value = val
    if (props.controlledExpanded !== undefined) {
      emit('set-expanded', val)
    }
  },
})
const actionSheetOpen = ref(false)
const perspectivesOpen = ref(false)
const noteOpen = ref(false)
const openQaIdx = ref<number | null>(null)
const draftNote = ref(props.savedNote || '')
const copiedJustNow = ref(false)
const bookmarkBurst = ref(false)
let bookmarkBurstTimer: ReturnType<typeof setTimeout> | null = null

function handleBookmarkButtonClick() {
  triggerHaptic(10)
  bookmarkBurst.value = true
  if (bookmarkBurstTimer) clearTimeout(bookmarkBurstTimer)
  bookmarkBurstTimer = setTimeout(() => {
    bookmarkBurst.value = false
  }, 500)
  emit('toggle-bookmark', props.event)
}
const swipeFeedback = ref<'read' | 'bookmark' | null>(null)
const thumbLoadFailed = ref(false)
let readDwellTimer: ReturnType<typeof setTimeout> | null = null

function scheduleAutoReadIfExpanded(isOpen: boolean) {
  if (readDwellTimer) {
    clearTimeout(readDwellTimer)
    readDwellTimer = null
  }
  if (isOpen && !props.isRead) {
    readDwellTimer = setTimeout(() => {
      if (expanded.value && !props.isRead) {
        emit('mark-read', props.event)
      }
    }, 1500)
  }
}

watch(
  expanded,
  (val) => {
    scheduleAutoReadIfExpanded(val)
  },
  { immediate: Boolean(props.defaultExpanded) },
)

function triggerExternalSourceRead() {
  if (!props.isRead) emit('mark-read', props.event)
}

function getDownweightKey(): string {
  if (props.event.storyline_id) return props.event.storyline_id
  if (props.event.entity_ids && props.event.entity_ids.length > 0) return props.event.entity_ids[0]
  const srcId = primarySource.value?.source_id
  if (srcId) return `src:${srcId}`
  return props.event.event_id
}

watch(
  () => props.thumbnailUrl,
  () => {
    thumbLoadFailed.value = false
  },
)

// Touch swipe gesture: right = mark read, left = bookmark
const swipeOffsetX = ref(0)
let touchStartX = 0
let touchStartY = 0
let swipeTracking = false
let swipeLockedHorizontal = false

function onTouchStart(e: TouchEvent) {
  if (e.touches.length !== 1) return
  touchStartX = e.touches[0].clientX
  touchStartY = e.touches[0].clientY
  swipeTracking = true
  swipeLockedHorizontal = false
  swipeOffsetX.value = 0
}

function onTouchMove(e: TouchEvent) {
  if (!swipeTracking || e.touches.length !== 1) return
  const dx = e.touches[0].clientX - touchStartX
  const dy = e.touches[0].clientY - touchStartY
  if (!swipeLockedHorizontal) {
    if (Math.abs(dy) > 14 && Math.abs(dy) > Math.abs(dx)) {
      swipeTracking = false
      swipeOffsetX.value = 0
      return
    }
    if (Math.abs(dx) > 16 && Math.abs(dx) > Math.abs(dy) * 1.35) {
      swipeLockedHorizontal = true
    } else {
      return
    }
  }
  const clamped = Math.max(-88, Math.min(88, dx * 0.65))
  swipeOffsetX.value = clamped
}

function onTouchEnd() {
  if (!swipeTracking) return
  const dx = swipeOffsetX.value
  swipeTracking = false
  swipeLockedHorizontal = false
  swipeOffsetX.value = 0

  if (dx >= 48) {
    triggerHaptic(10)
    emit('toggle-read', props.event)
    swipeFeedback.value = 'read'
    setTimeout(() => {
      if (swipeFeedback.value === 'read') swipeFeedback.value = null
    }, 1100)
  } else if (dx <= -48) {
    triggerHaptic(10)
    emit('toggle-bookmark', props.event)
    swipeFeedback.value = 'bookmark'
    setTimeout(() => {
      if (swipeFeedback.value === 'bookmark') swipeFeedback.value = null
    }, 1100)
  }
}

function onSheetKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && actionSheetOpen.value) {
    e.preventDefault()
    e.stopPropagation()
    actionSheetOpen.value = false
  }
}

watch(actionSheetOpen, (open) => {
  if (open) {
    lockBodyScroll()
    if (typeof window !== 'undefined') window.addEventListener('keydown', onSheetKeydown, true)
  } else {
    unlockBodyScroll()
    if (typeof window !== 'undefined') window.removeEventListener('keydown', onSheetKeydown, true)
  }
})

onUnmounted(() => {
  if (readDwellTimer) {
    clearTimeout(readDwellTimer)
    readDwellTimer = null
  }
  if (bookmarkBurstTimer) {
    clearTimeout(bookmarkBurstTimer)
    bookmarkBurstTimer = null
  }
  if (actionSheetOpen.value) unlockBodyScroll()
  if (typeof window !== 'undefined') window.removeEventListener('keydown', onSheetKeydown, true)
})

watch(
  () => props.savedNote,
  (val) => {
    draftNote.value = val || ''
  },
)

const effectiveDensity = computed<FeedDensity>(() => props.density ?? feedDensity.value)
const isCompact = computed(() => effectiveDensity.value === 'compact')

const perspectiveCols = computed(() =>
  buildThreeColumnPerspectives(props.event, props.perspectives || []),
)

function saveCardNote() {
  emit('save-note', { event: props.event, content: draftNote.value.trim() })
  noteOpen.value = false
}

function fmtPctRange(lo: number, hi: number): string {
  const a = lo > 0 ? `+${lo}%` : `${lo}%`
  const b = hi > 0 ? `+${hi}%` : `${hi}%`
  return `${a}~${b}`
}

const categoryInfo = computed(
  () => CATEGORIES.find((c) => c.id === props.event.category) ?? CATEGORIES[0],
)

const sortedSources = computed(() =>
  [...(props.event.sources || [])].sort((a, b) => {
    const ag = (a.url || '').includes('news.google.com/rss/articles/') ? 1 : 0
    const bg = (b.url || '').includes('news.google.com/rss/articles/') ? 1 : 0
    return ag - bg
  }),
)
const primarySource = computed(() => sortedSources.value[0] ?? null)

const originIso = computed(() => props.event.first_reported_at || props.event.published_at || null)
const ingestedIso = computed(() => props.event.first_discovered_at || props.event.fetched_at || null)

const unifiedEvidence = computed(() =>
  resolveEvidenceTierBadge({
    evidence_status: props.event.evidence_status,
    sources: props.event.sources,
    title: props.event.title,
    summary: props.event.fact_summary,
    independent_publisher_count: props.event.independent_publisher_count,
  }),
)

const headlineQualifiers = computed(() =>
  extractHeadlineQualifiers(props.event.title_zh || props.event.title, props.event.fact_summary),
)

const cleanFactSummary = computed(() => {
  const raw = props.event.fact_summary || ''
  const trimmed = stripMarkdownArtifacts(
    raw.replace(/^【据关联报道\/尚未见官方披露确认】\s*/g, ''),
  )
  return truncateAtSentence(trimmed || raw, 220)
})

const isPlaceholderOrUntranslatedSummary = computed(() => {
  const s = cleanFactSummary.value
  if (!s) return true
  if (s.includes('该条为海外主流媒体英文原报') || s.includes('云端 AI 批次将自动')) return true
  const cjk = (s.match(/[\u4e00-\u9fff]/g) || []).length
  const lat = (s.match(/[A-Za-z]/g) || []).length
  return lat >= 16 && cjk <= 2
})

const englishFallbackSummary = computed(() => {
  const src0 = props.event.sources?.[0]
  const rawEn = (
    props.event.summary_en ||
    src0?.excerpt ||
    (!cleanFactSummary.value.includes('该条为海外主流媒体英文原报') ? cleanFactSummary.value : '') ||
    props.event.title_en ||
    src0?.title ||
    props.event.title ||
    ''
  )
    .replace(/^【[^】]{2,14}】\s*/, '')
    .trim()
  return truncateAtSentence(stripMarkdownArtifacts(rawEn), 150)
})

const displayEntities = computed(() => {
  const text = `${props.event.title} ${props.event.fact_summary || ''}`
  const hasUsdHeadOfState = /美元首/.test(text) && !/(?:美联储|fomc|加息|降息|鲍威尔|美元指数|美元汇率)/i.test(text)
  return getConfidentEntities(props.event.entities || [], props.event.entity_confidences).filter((item) => {
    if (hasUsdHeadOfState && item.name.includes('美联储')) return false
    return true
  })
})

const realThumbUrl = computed(() => {
  const u = (props.thumbnailUrl || props.event.thumbnail_url || '').trim()
  if (!u || !/^https?:\/\//i.test(u)) return null
  if (/(\/default\/|\/_static\/|\/static\/share|share\.(?:png|jpe?g|webp)|(?:^|[/_-])(?:play|video[-_]?icon|placeholder|default[-_]?thumb|logo|favicon|sprite|avatar)(?:[/_.-]|$)|\.svg(?:\?|$))/i.test(u)) {
    return null
  }
  return u
})

function onThumbLoad(e: Event) {
  const el = e.target as HTMLImageElement | null
  if (!el) return
  const w = el.naturalWidth || 0
  const h = el.naturalHeight || 0
  if (w < 160 || h < 90 || (Math.abs(w - h) <= 4 && w <= 400)) {
    thumbLoadFailed.value = true
  }
}

const polarityChip = computed(() => {
  if (!props.marketImpact) return null
  if (props.marketImpact.polarity === 'bullish') {
    return {
      label: t('利好', 'Bullish'),
      cls: marketUpBadgeClass(),
    }
  }
  if (props.marketImpact.polarity === 'bearish') {
    return {
      label: t('利空', 'Bearish'),
      cls: marketDownBadgeClass(),
    }
  }
  return {
    label: t('分化', 'Mixed'),
    cls: 'bg-amber-500/12 text-amber-700 dark:bg-amber-400/15 dark:text-amber-300',
  }
})

function handleCopyLink() {
  emit('copy-link', props.event)
  copiedJustNow.value = true
  setTimeout(() => {
    copiedJustNow.value = false
  }, 1600)
}

function handleCardPrimaryClick() {
  if (typeof window !== 'undefined' && window.innerWidth >= 1280) {
    expanded.value = false
    emit('open-detail', props.event)
    return
  }
  expanded.value = !expanded.value
}

function runSheetAction(fn: () => void) {
  actionSheetOpen.value = false
  fn()
}
</script>

<template>
  <div class="relative overflow-hidden" :class="grouped ? '' : 'rounded-2xl'">
    <!-- Swipe action background indicators -->
    <div
      v-if="swipeOffsetX !== 0"
      class="absolute inset-0 flex items-center justify-between px-4 text-xs font-semibold pointer-events-none"
      :class="[grouped ? '' : 'rounded-2xl', swipeOffsetX > 0 ? 'bg-emerald-500 text-white' : 'bg-amber-500 text-white']"
    >
      <span class="inline-flex items-center gap-1" :class="swipeOffsetX > 0 ? 'opacity-100' : 'opacity-0'">
        <CheckCircle2 class="w-4 h-4" />
        {{ isRead ? t('标为未读', 'Unread') : t('标为已读', 'Mark Read') }}
      </span>
      <span class="inline-flex items-center gap-1" :class="swipeOffsetX < 0 ? 'opacity-100' : 'opacity-0'">
        <Bookmark class="w-4 h-4" />
        {{ isBookmarked ? t('取消收藏', 'Unsave') : t('收藏', 'Save') }}
      </span>
    </div>

    <article
      :id="`event-${event.event_id}`"
      :data-read="isRead ? 'true' : 'false'"
      :data-density="effectiveDensity"
      @touchstart.passive="onTouchStart"
      @touchmove.passive="onTouchMove"
      @touchend="onTouchEnd"
      @touchcancel="onTouchEnd"
      :style="swipeOffsetX !== 0 ? { transform: `translateX(${swipeOffsetX}px)` } : undefined"
      class="group relative transition-all duration-150"
      :class="[
        grouped
          ? 'bg-white dark:bg-[#1C1C1E] hover:bg-black/[0.015] dark:hover:bg-[#242426]'
          : 'ios-card hover:shadow-[0_4px_14px_rgba(0,0,0,0.06)] dark:hover:bg-[#242426]',
        isHighlighted || isKeyboardFocused ? 'ring-2 ring-inset ring-[#007AFF]/50' : '',
        (event.severity_tier === 'S' || event.severity_tier === 'A' || event.importance === 'high') && !isRead ? 'border-l-[3px] border-l-[#DC2626]' : '',
        isRead && !expanded ? 'opacity-70' : '',
      ]"
    >
      <!-- Swipe Toast Pill -->
      <div
        v-if="swipeFeedback"
        class="absolute top-2 right-2 z-10 px-2.5 py-1 rounded-full text-[11px] font-semibold text-white shadow-sm"
        :class="swipeFeedback === 'read' ? 'bg-emerald-600' : 'bg-amber-500'"
      >
        {{
          swipeFeedback === 'read'
            ? (isRead ? t('已标为已读', 'Marked Read') : t('已标为未读', 'Marked Unread'))
            : (isBookmarked ? t('已加入收藏', 'Saved') : t('已取消收藏', 'Removed'))
        }}
      </div>

      <div :class="featured ? 'p-4 sm:p-5' : isCompact ? 'px-3.5 py-3' : 'p-4 sm:p-5'">
        <!-- Lead Eyebrow (only on Lead Story #1) or Cross-Domain Blindspot Eyebrow -->
        <div v-if="crossDomainBadge" class="mb-1.5 flex flex-wrap items-center gap-2 text-[11px]">
          <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-indigo-500/12 text-indigo-700 dark:bg-indigo-400/15 dark:text-indigo-300 font-semibold">
            {{ crossDomainBadge }}
          </span>
          <span v-if="crossDomainHint" class="text-zinc-500 dark:text-zinc-400 truncate">
            {{ crossDomainHint }}
          </span>
        </div>
        <div v-else-if="featured" class="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold text-[#007AFF] dark:text-[#0A84FF] uppercase tracking-wide">
          <span class="w-1.5 h-1.5 rounded-full bg-[#007AFF] dark:bg-[#0A84FF]" />
          <span>{{ t('头条焦点', 'Lead Story') }}</span>
          <span
            v-if="event.severity_tier === 'S' || event.severity_tier === 'A' || event.importance === 'high'"
            class="jx-heavy-capsule ml-1 inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-[#DC2626] text-white text-[10px] font-bold tracking-tight whitespace-nowrap"
            data-testid="card-heavy-badge"
          >
            <span class="jx-sonar-dot jx-sonar-white" />
            <Flame class="w-3 h-3 shrink-0" :stroke-width="2" />
            <span>{{ event.severity_tier === 'S' ? t('S级重磅', 'S-TIER') : t('重磅', 'HEAVY') }}{{ event.heavy_reason_tag ? ` · ${event.heavy_reason_tag}` : '' }}</span>
          </span>
        </div>
        <div
          v-else-if="event.severity_tier === 'S' || event.severity_tier === 'A' || event.importance === 'high'"
          class="mb-1 flex items-center gap-1.5"
        >
          <span
            class="jx-heavy-capsule inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-[#DC2626] text-white text-[10px] font-bold tracking-tight whitespace-nowrap"
            data-testid="card-heavy-badge"
          >
            <span class="jx-sonar-dot jx-sonar-white" />
            <Flame class="w-3 h-3 shrink-0" :stroke-width="2" />
            <span>{{ event.severity_tier === 'S' ? t('S级重磅', 'S-TIER') : t('重磅', 'HEAVY') }}{{ event.heavy_reason_tag ? ` · ${event.heavy_reason_tag}` : '' }}</span>
          </span>
        </div>

        <!-- Main Row (Desktop >=1280px opens Split-View Reader; mobile expands in-place) -->
        <div
          @click="handleCardPrimaryClick"
          class="mobile-pressable flex items-start gap-3 cursor-pointer select-none"
        >
          <div class="min-w-0 flex-1 space-y-1.5">
            <!-- Flush-left aligned Headline (NO inline status pills pushing title indent) -->
            <h3
              class="font-semibold text-zinc-950 dark:text-[#F2F2F7] leading-[1.35] tracking-[-0.015em]"
              :class="[
                featured
                  ? 'text-[19px] sm:text-[20px] font-bold leading-[1.3]'
                  : isCompact
                    ? 'text-[16px] sm:text-[17px] line-clamp-2'
                    : 'text-[17px]',
                isRead && !expanded ? 'font-medium text-zinc-500 dark:text-zinc-400' : '',
              ]"
            >
              {{ pickBiText(event.title_zh || event.title, event.title_en || event.title) }}
            </h3>

            <!-- Lead Story & Standard mode show summary inline; Compact mode fills 1-line snippet when thumbnail present to avoid vertical whitespace -->
            <p
              v-if="featured || !isCompact || expanded || (realThumbUrl && !thumbLoadFailed && cleanFactSummary)"
              class="text-zinc-600 dark:text-zinc-300 leading-[1.45]"
              :class="[
                isCompact && !featured && !expanded ? 'text-[13px] line-clamp-1' : 'text-[14px] sm:text-[15px]',
                !expanded && !(isCompact && !featured) ? 'line-clamp-2' : '',
              ]"
            >
              <template v-if="isPlaceholderOrUntranslatedSummary">
                <span lang="en">{{ englishFallbackSummary }}</span>
              </template>
              <template v-else>
                {{ pickBiText(cleanFactSummary, event.summary_en || cleanFactSummary) }}
              </template>
            </p>

            <!-- Inline Grounded Deep-Q&A Micro-Pills -->
            <div v-if="event.deep_qa && event.deep_qa.length > 0" class="pt-1 space-y-1.5" @click.stop>
              <div class="flex flex-wrap items-center gap-1.5">
                <button
                  v-for="(qa, qIdx) in event.deep_qa.slice(0, 3)"
                  :key="`qa-${qIdx}`"
                  type="button"
                  @click="openQaIdx = openQaIdx === qIdx ? null : qIdx"
                  class="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-[11px] font-medium border transition-colors"
                  :class="openQaIdx === qIdx ? 'bg-zinc-900 text-white border-zinc-900 dark:bg-white dark:text-zinc-950' : 'bg-zinc-100/80 dark:bg-zinc-800/80 text-zinc-700 dark:text-zinc-300 border-zinc-200/80 dark:border-zinc-700/80 hover:border-[#007AFF]'"
                  data-testid="deep-qa-pill"
                >
                  <HelpCircle class="w-3 h-3 shrink-0 text-[#007AFF]" :stroke-width="1.8" />
                  <span class="truncate max-w-[230px]">{{ qa.question }}</span>
                </button>
              </div>
              <div
                v-if="openQaIdx !== null && event.deep_qa[openQaIdx]"
                class="jx-collapse-reveal rounded-xl bg-zinc-50 dark:bg-zinc-800/80 border border-zinc-200/80 dark:border-zinc-700/80 px-3 py-2 text-xs text-zinc-700 dark:text-zinc-200 space-y-1 leading-relaxed"
                data-testid="event-deep-qa-answer"
              >
                <p>{{ event.deep_qa[openQaIdx].answer }}</p>
                <p v-if="event.deep_qa[openQaIdx].historical_parallel" class="text-[11px] text-[#007AFF] dark:text-[#66B2FF]">
                  {{ t('历史镜像参考：', 'Historical Parallel: ') }}{{ event.deep_qa[openQaIdx].historical_parallel }}
                </p>
              </div>
            </div>
          </div>

          <!-- Optional Real Article Image (never fake 3D neon illustrations) -->
          <img
            v-if="realThumbUrl && !thumbLoadFailed"
            :src="realThumbUrl"
            :alt="pickBiText(event.title_zh || event.title, event.title_en || event.title)"
            loading="lazy"
            referrerpolicy="no-referrer"
            @load="onThumbLoad"
            @error="thumbLoadFailed = true"
            class="rounded-xl object-cover shrink-0 bg-zinc-100 dark:bg-zinc-800"
            :class="isCompact && !featured ? 'w-[72px] h-[52px]' : 'w-[84px] h-[63px]'"
          />
        </div>

        <!-- Unified Responsive Meta + Subtle Action Icons (wraps cleanly on narrow mobile viewports) -->
        <div class="mt-2 flex items-start sm:items-center justify-between gap-2">
          <div class="flex items-center flex-wrap gap-x-1.5 gap-y-1 min-w-0 flex-1 text-[11px] text-zinc-500 dark:text-zinc-400">
            <span
              v-if="!isRead"
              class="w-1.5 h-1.5 rounded-full bg-[#007AFF] dark:bg-[#0A84FF] shrink-0"
              :aria-label="t('未读', 'Unread')"
            />
            <span class="font-medium text-zinc-700 dark:text-zinc-200 truncate min-w-0 max-w-[132px] sm:max-w-[200px]">
              {{ translateSourceName(primarySource?.publisher_name || primarySource?.source_name, primarySource?.title || event.title) || (appLang === 'en' ? categoryInfo.shortNameEn : categoryInfo.shortName) }}
            </span>
            <span class="text-zinc-300 dark:text-zinc-600 shrink-0">·</span>
            <span class="tabular-nums shrink-0 whitespace-nowrap">
              <SmartTime v-if="originIso" :iso="originIso" :ingested-iso="ingestedIso" :now-ms="nowMs" :compact-mobile="true" />
              <SmartTime v-else-if="ingestedIso" :iso="ingestedIso" :now-ms="nowMs" :compact-mobile="true" />
            </span>
            <span
              class="px-1.5 py-0.5 rounded-md border text-[10px] font-semibold shrink-0 whitespace-nowrap"
              :class="unifiedEvidence.badgeClass"
              :title="unifiedEvidence.label"
            >
              {{ unifiedEvidence.shortLabel }}
            </span>
            <span
              v-if="headlineQualifiers.effectiveDateLabel"
              class="px-1.5 py-0.5 rounded-md bg-blue-500/10 text-blue-700 dark:text-blue-300 text-[10px] font-semibold shrink-0 whitespace-nowrap"
            >
              {{ headlineQualifiers.effectiveDateLabel }}
            </span>
            <span
              v-if="polarityChip"
              class="px-1.5 py-0.5 rounded-md text-[10px] font-semibold shrink-0 whitespace-nowrap"
              :class="polarityChip.cls"
            >
              {{ polarityChip.label }}
            </span>
            <span
              v-if="event.followup?.is_continuing"
              class="px-1.5 py-0.5 rounded-md text-[10px] font-semibold bg-[#007AFF]/10 text-[#007AFF] dark:text-[#0A84FF] shrink-0 whitespace-nowrap"
            >
              {{ t('更新', 'Updated') }}
            </span>
            <span
              v-else-if="isNewSinceVisit && !isRead"
              class="text-[10px] font-semibold text-[#007AFF] dark:text-[#0A84FF] shrink-0 whitespace-nowrap"
            >
              {{ t('新', 'NEW') }}
            </span>
            <button
              v-if="matchingNoteCount && matchingNoteCount > 0"
              type="button"
              @click.stop="emit('open-notes')"
              class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-amber-500/12 text-amber-800 dark:bg-amber-400/15 dark:text-amber-200 text-[10px] font-semibold shrink-0 whitespace-nowrap hover:underline"
            >
              <FileText class="w-3 h-3 shrink-0" :stroke-width="1.75" />
              <span>{{ t(`${matchingNoteCount} 条相关笔记`, `${matchingNoteCount} notes`) }}</span>
            </button>
          </div>

          <div class="flex items-center -mr-1.5 shrink-0 transition-opacity duration-150 lg:opacity-65 lg:group-hover:opacity-100 lg:focus-within:opacity-100">
            <button
              v-if="showModerationActions && !featured && !downweighted"
              type="button"
              @click.stop="triggerHaptic(8); emit('toggle-downweight', getDownweightKey())"
              class="hidden sm:inline-flex items-center px-1.5 h-6 mr-0.5 rounded-md text-[10px] text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 hover:bg-black/[0.04] dark:hover:bg-white/[0.06] whitespace-nowrap shrink-0"
              :title="t('降低此类话题或信源权重', 'Show less like this')"
            >
              × <span>{{ t('少看此类', 'Less') }}</span>
            </button>
            <button
              type="button"
              @click.stop="handleBookmarkButtonClick"
              class="jx-pop-target inline-flex items-center justify-center w-8 h-8 rounded-lg ios-tap transition-colors"
              :class="[
                isBookmarked ? 'text-amber-500' : 'text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200',
                bookmarkBurst ? 'jx-burst-ring text-amber-500' : '',
              ]"
              :aria-pressed="isBookmarked"
              :aria-label="isBookmarked ? t('取消收藏', 'Remove from saved') : t('收藏', 'Save')"
            >
              <Bookmark
                class="w-4 h-4 transition-transform"
                :stroke-width="1.5"
                :class="[{ 'fill-current': isBookmarked }, bookmarkBurst ? 'jx-pop-active' : '']"
              />
            </button>

            <button
              type="button"
              @click.stop="triggerHaptic(10); handleCopyLink()"
              class="inline-flex items-center justify-center w-8 h-8 rounded-lg ios-tap text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 transition-colors"
              :aria-label="t('分享链接', 'Share link')"
            >
              <Check v-if="copiedJustNow" class="w-4 h-4 text-emerald-500" :stroke-width="1.75" />
              <Link2 v-else class="w-4 h-4" :stroke-width="1.5" />
            </button>

            <button
              type="button"
              @click.stop="triggerHaptic(10); actionSheetOpen = true"
              class="inline-flex items-center justify-center w-8 h-8 rounded-lg ios-tap text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 transition-colors"
              :aria-label="t('更多操作', 'More actions')"
            >
              <MoreHorizontal class="w-4 h-4" :stroke-width="1.5" />
            </button>
          </div>
        </div>

        <!-- Inline Expanded Section (Summary, Market Impact, AI Analysis, Sources, Entities) -->
        <div
          v-if="expanded"
          class="jx-collapse-reveal mt-3 pt-3 border-t border-black/[0.06] dark:border-white/[0.08] space-y-3"
        >
          <!-- Market Impact Details -->
          <div
            v-if="marketImpact"
            class="ios-surface-2 p-3 space-y-2 text-xs"
          >
            <div class="flex items-center justify-between gap-2">
              <span class="font-semibold text-zinc-800 dark:text-zinc-100">{{ t('股市传导', 'Market Impact') }}</span>
              <span v-if="polarityChip" class="px-1.5 py-0.5 rounded-md text-[10px] font-semibold" :class="polarityChip.cls">
                {{ polarityChip.label }}
              </span>
            </div>
            <p v-if="marketImpact.one_liner" class="text-zinc-600 dark:text-zinc-300 leading-relaxed">
              {{ marketImpact.one_liner }}
            </p>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
              <div
                v-for="b in marketImpact.bars"
                :key="b.market + b.sector"
                class="flex items-center justify-between gap-2 rounded-lg bg-white dark:bg-[#1C1C1E] px-2.5 py-1.5 text-[11px]"
              >
                <span class="truncate text-zinc-700 dark:text-zinc-300">{{ translateMarketTag(b.market) }} · {{ pickBiText(b.sector, b.sector_en) }}</span>
                <span
                  class="shrink-0 font-mono font-semibold tabular-nums"
                  :class="(b.pct_low + b.pct_high) >= 0 ? marketUpTextClass() : marketDownTextClass()"
                >
                  {{ fmtPctRange(b.pct_low, b.pct_high) }}
                </span>
              </div>
            </div>
          </div>

          <!-- AI Analysis -->
          <div
            v-if="event.ai_analysis"
            class="ios-surface-2 px-3 py-2.5 space-y-1"
          >
            <div class="flex items-center gap-1.5 text-xs font-semibold text-[#007AFF] dark:text-[#0A84FF]">
              <Sparkles class="w-3.5 h-3.5" :stroke-width="1.5" />
              <span>{{ t('AI 解读', 'AI Analysis') }}</span>
            </div>
            <p class="text-[13px] text-zinc-800 dark:text-zinc-200 leading-relaxed">
              {{ pickBiText(event.ai_analysis, event.ai_analysis_en) }}
            </p>
          </div>

          <!-- Regulatory Note (if any, reader-facing only; no engineering downweight/signal telemetry) -->
          <div
            v-if="event.regulatory_note"
            class="ios-surface-2 px-3 py-2 text-[11px] text-zinc-600 dark:text-zinc-300"
          >
            {{ event.regulatory_note }}
          </div>

          <div
            v-if="event.unverified_claims.length > 0"
            class="rounded-xl bg-amber-500/10 px-3 py-2 text-xs text-amber-800 dark:text-amber-200 space-y-1"
          >
            <div class="font-semibold flex items-center gap-1">
              <AlertTriangle class="w-3.5 h-3.5" />
              <span>{{ t('待证实边界', 'Unverified Scope') }}</span>
            </div>
            <ul class="list-disc list-inside space-y-0.5">
              <li v-for="(claim, idx) in event.unverified_claims" :key="idx">{{ claim }}</li>
            </ul>
          </div>

          <!-- Primary Source CTA & Linked Sources (entire row clickable with @click.stop & valid http/https URL guard) -->
          <div class="space-y-2">
            <div class="flex flex-wrap items-center gap-2">
              <a
                v-if="primarySource && normalizeExternalUrl(primarySource.url)"
                :href="normalizeExternalUrl(primarySource.url)!"
                target="_blank"
                rel="noopener noreferrer"
                @click.stop="triggerExternalSourceRead()"
                class="ios-tap inline-flex items-center gap-1.5 px-3.5 min-h-[38px] rounded-xl text-xs font-semibold bg-[#007AFF] text-white hover:bg-[#0066D6] transition-colors"
              >
                <span>{{ translateSourceName(primarySource.publisher_name || primarySource.source_name, primarySource.title || event.title) }}</span>
                <ExternalLink class="w-3.5 h-3.5 shrink-0" :stroke-width="1.5" />
              </a>
              <span
                v-else
                class="inline-flex items-center gap-1.5 px-3 min-h-[38px] rounded-xl text-xs font-medium bg-black/[0.04] dark:bg-white/[0.06] text-zinc-400 cursor-not-allowed"
              >
                {{ t('暂无原文直链', 'No Direct Link') }}
              </span>
              <button
                type="button"
                @click="emit('open-qa', event)"
                class="ios-tap inline-flex items-center gap-1 px-3 min-h-[38px] rounded-xl text-xs font-medium bg-[#F2F2F7] dark:bg-[#2C2C2E] text-zinc-700 dark:text-zinc-200"
              >
                <Sparkles class="w-3.5 h-3.5 text-[#007AFF] dark:text-[#0A84FF]" :stroke-width="1.5" />
                <span>{{ t('证据问答', 'Q&A') }}</span>
              </button>
            </div>

            <ul
              v-if="event.sources.length > 1"
              class="divide-y divide-black/[0.05] dark:divide-white/[0.06] rounded-xl bg-[#F5F5F7] dark:bg-[#2C2C2E] overflow-hidden text-xs"
            >
              <li
                v-for="src in sortedSources"
                :key="src.item_id"
              >
                <a
                  v-if="normalizeExternalUrl(src.url)"
                  :href="normalizeExternalUrl(src.url)!"
                  target="_blank"
                  rel="noopener noreferrer"
                  @click.stop="triggerExternalSourceRead()"
                  class="px-3 py-2 flex items-center justify-between gap-2 hover:bg-black/[0.04] dark:hover:bg-white/[0.06] transition-colors group"
                  :aria-label="t('打开原文', 'Open source')"
                >
                  <div class="min-w-0">
                    <div class="text-[11px] text-zinc-500 dark:text-zinc-400 flex items-center gap-1.5">
                      <span class="font-medium text-zinc-700 dark:text-zinc-200">{{ translateSourceName(src.publisher_name || src.source_name, src.title) }}</span>
                      <SmartTime v-if="src.published_at" :iso="src.published_at" :now-ms="nowMs" />
                    </div>
                    <p class="text-zinc-800 dark:text-zinc-100 truncate mt-0.5 group-hover:text-[#007AFF]">{{ pickBiText(src.title_zh || src.title, src.title) }}</p>
                  </div>
                  <ExternalLink class="w-4 h-4 text-[#007AFF] dark:text-[#0A84FF] shrink-0" :stroke-width="1.5" />
                </a>
                <div v-else class="px-3 py-2 flex items-center justify-between gap-2 opacity-60">
                  <div class="min-w-0">
                    <div class="text-[11px] text-zinc-500 dark:text-zinc-400 flex items-center gap-1.5">
                      <span class="font-medium text-zinc-700 dark:text-zinc-200">{{ translateSourceName(src.publisher_name || src.source_name, src.title) }}</span>
                      <SmartTime v-if="src.published_at" :iso="src.published_at" :now-ms="nowMs" />
                    </div>
                    <p class="text-zinc-500 dark:text-zinc-400 truncate mt-0.5">{{ pickBiText(src.title_zh || src.title, src.title) }}</p>
                  </div>
                  <span class="text-[10px] text-zinc-400 shrink-0">{{ t('暂无直链', 'No Link') }}</span>
                </div>
              </li>
            </ul>
          </div>

          <!-- Related Entities -->
          <div v-if="displayEntities.length > 0" class="flex flex-wrap items-center gap-1.5">
            <button
              v-for="ent in displayEntities"
              :key="ent.name"
              type="button"
              @click="emit('select-entity', ent.name)"
              class="min-h-[34px] px-2.5 rounded-full text-xs bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 hover:text-blue-600"
            >
              # {{ translateEntityName(ent.name) }}
            </button>
          </div>

          <!-- Zero-UGC Structured 1-Click Signal Reaction Bar -->
          <div class="pt-2 border-t border-black/[0.05] dark:border-white/[0.06] space-y-1.5">
            <div class="flex flex-wrap items-center justify-between gap-2 text-[11px]">
              <span class="text-zinc-400 font-medium shrink-0">{{ t('信源含金量判断：', 'Signal Rating:') }}</span>
              <div class="flex flex-wrap items-center gap-1.5">
                <button
                  v-for="opt in ([
                    { key: 'heavy', label: t('真重磅', 'Heavy'), activeCls: 'bg-rose-600 text-white border-rose-600' },
                    { key: 'track', label: t('持续跟踪', 'Track'), activeCls: 'bg-[#007AFF] text-white border-[#007AFF]' },
                    { key: 'noise', label: t('噪音', 'Noise'), activeCls: 'bg-zinc-700 text-white border-zinc-700 dark:bg-zinc-600' },
                  ] as const)"
                  :key="opt.key"
                  type="button"
                  @click.stop="triggerHaptic(8); void toggleStructuredReaction('event', event.event_id, opt.key)"
                  class="ios-tap inline-flex items-center gap-1 px-2.5 min-h-[28px] rounded-full border text-[11px] font-medium transition-colors"
                  :class="
                    getReactionSummary('event', event.event_id).my_reaction === opt.key
                      ? opt.activeCls
                      : 'border-black/[0.08] dark:border-white/[0.1] bg-white dark:bg-[#2C2C2E] text-zinc-600 dark:text-zinc-300 hover:border-[#007AFF]/40'
                  "
                >
                  <span>{{ opt.label }}</span>
                  <span
                    v-if="(getReactionSummary('event', event.event_id).counts[opt.key] || 0) > 0"
                    class="font-mono text-[10px] opacity-85 tabular-nums"
                  >
                    {{ getReactionSummary('event', event.event_id).counts[opt.key] }}
                  </span>
                </button>
              </div>
            </div>
            <div
              v-if="getReactionSummary('event', event.event_id).total > 0"
              class="h-1 rounded-full overflow-hidden flex bg-black/[0.05] dark:bg-white/[0.08]"
            >
              <div
                class="bg-rose-500 transition-all"
                :style="{ width: `${Math.round(((getReactionSummary('event', event.event_id).counts.heavy || 0) / getReactionSummary('event', event.event_id).total) * 100)}%` }"
              />
              <div
                class="bg-[#007AFF] transition-all"
                :style="{ width: `${Math.round(((getReactionSummary('event', event.event_id).counts.track || 0) / getReactionSummary('event', event.event_id).total) * 100)}%` }"
              />
              <div
                class="bg-zinc-400 transition-all"
                :style="{ width: `${Math.round(((getReactionSummary('event', event.event_id).counts.noise || 0) / getReactionSummary('event', event.event_id).total) * 100)}%` }"
              />
            </div>
          </div>
        </div>

        <!-- Perspectives Comparison Panel -->
        <div
          v-if="perspectivesOpen"
          class="mt-3 pt-3 border-t border-black/[0.06] dark:border-white/[0.08] grid grid-cols-1 md:grid-cols-3 gap-2"
        >
          <div
            v-for="col in perspectiveCols"
            :key="col.lane"
            class="rounded-xl p-2.5 space-y-1 text-xs bg-zinc-50 dark:bg-zinc-800/60"
          >
            <div class="font-semibold text-zinc-900 dark:text-white">
              {{ appLang === 'en' ? col.labelEn : col.label }}
            </div>
            <ul class="space-y-1 text-zinc-600 dark:text-zinc-300 list-disc list-inside leading-relaxed">
              <li v-for="(pt, idx) in col.points" :key="idx">{{ pt }}</li>
            </ul>
          </div>
        </div>

        <!-- Inline Note Drawer -->
        <div
          v-if="noteOpen"
          class="mt-3 pt-3 border-t border-black/[0.06] dark:border-white/[0.08] space-y-2"
        >
          <textarea
            v-model="draftNote"
            rows="2"
            :placeholder="t('记录核心判断或跟踪问题...', 'Write your thesis or open question...')"
            class="w-full rounded-xl border border-black/[0.08] dark:border-white/[0.1] bg-zinc-50 dark:bg-zinc-800 px-3 py-2 text-xs text-zinc-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <div class="flex items-center justify-end gap-2">
            <button
              type="button"
              @click="noteOpen = false"
              class="min-h-[36px] px-3 rounded-xl text-xs text-zinc-600 dark:text-zinc-300 bg-zinc-100 dark:bg-zinc-800"
            >
              {{ t('取消', 'Cancel') }}
            </button>
            <button
              type="button"
              @click="saveCardNote"
              class="min-h-[36px] px-3.5 rounded-xl text-xs font-semibold bg-blue-600 text-white"
            >
              {{ t('保存', 'Save') }}
            </button>
          </div>
        </div>
      </div>
    </article>

    <!-- iOS ActionSheet for Secondary Card Actions -->
    <Teleport to="body">
      <div
        v-if="actionSheetOpen"
        class="ios-sheet-backdrop p-2 sm:p-4"
        role="dialog"
        aria-modal="true"
        @click.self="actionSheetOpen = false"
      >
        <div class="w-full sm:max-w-md space-y-2 pb-[env(safe-area-inset-bottom)]">
          <div class="rounded-2xl bg-white/95 dark:bg-zinc-900/95 backdrop-blur-xl overflow-hidden divide-y divide-black/[0.06] dark:divide-white/[0.08] shadow-2xl">
            <div class="px-4 py-3 text-center">
              <p class="text-xs font-semibold text-zinc-900 dark:text-white line-clamp-1">
                {{ pickBiText(event.title_zh || event.title, event.title_en || event.title) }}
              </p>
              <p class="text-[11px] text-zinc-400 mt-0.5">
                {{ translateSourceName(primarySource?.publisher_name || primarySource?.source_name, primarySource?.title || event.title) }} · {{ formatShanghaiDateTime(originIso) }}
              </p>
            </div>

            <button
              type="button"
              @click="runSheetAction(() => { handleCardPrimaryClick() })"
              class="w-full min-h-[48px] px-4 flex items-center justify-between text-sm font-medium text-zinc-900 dark:text-white active:bg-black/[0.04] dark:active:bg-white/[0.06]"
            >
              <span class="inline-flex items-center gap-2.5">
                <Sparkles class="w-4 h-4 text-blue-600 dark:text-blue-400" />
                <span>{{ expanded ? t('收起 AI 解读与出处', 'Collapse AI & Sources') : t(`查看 AI 解读 (${event.sources.length} 出处)`, `View AI & ${event.sources.length} Sources`) }}</span>
              </span>
            </button>

            <a
              v-if="primarySource && normalizeExternalUrl(primarySource.url)"
              :href="normalizeExternalUrl(primarySource.url)!"
              target="_blank"
              rel="noopener noreferrer"
              @click.stop="triggerExternalSourceRead(); actionSheetOpen = false"
              class="w-full min-h-[48px] px-4 flex items-center justify-between text-sm font-medium text-zinc-900 dark:text-white active:bg-black/[0.04] dark:active:bg-white/[0.06]"
            >
              <span class="inline-flex items-center gap-2.5">
                <ExternalLink class="w-4 h-4 text-zinc-500" />
                <span>{{ t('打开原文', 'Open Source') }}</span>
              </span>
            </a>

            <button
              v-if="event.storyline_id"
              type="button"
              @click="runSheetAction(() => emit('open-storyline', event.storyline_id!))"
              class="w-full min-h-[48px] px-4 flex items-center justify-between text-sm font-medium text-zinc-900 dark:text-white active:bg-black/[0.04] dark:active:bg-white/[0.06]"
            >
              <span class="inline-flex items-center gap-2.5">
                <GitBranch class="w-4 h-4 text-violet-600 dark:text-violet-400" />
                <span>{{ t('事件档案', 'Event Dossier') }}</span>
              </span>
            </button>

            <button
              type="button"
              @click="runSheetAction(() => emit('open-qa', event))"
              class="w-full min-h-[48px] px-4 flex items-center justify-between text-sm font-medium text-zinc-900 dark:text-white active:bg-black/[0.04] dark:active:bg-white/[0.06]"
            >
              <span class="inline-flex items-center gap-2.5">
                <Sparkles class="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
                <span>{{ t('证据问答', 'Evidence Q&A') }}</span>
              </span>
            </button>

            <button
              type="button"
              @click="runSheetAction(() => { perspectivesOpen = !perspectivesOpen })"
              class="w-full min-h-[48px] px-4 flex items-center justify-between text-sm font-medium text-zinc-900 dark:text-white active:bg-black/[0.04] dark:active:bg-white/[0.06]"
            >
              <span class="inline-flex items-center gap-2.5">
                <Columns3 class="w-4 h-4 text-zinc-500" />
                <span>{{ perspectivesOpen ? t('收起观点对照', 'Hide Perspectives') : t('观点对照', 'Perspectives') }}</span>
              </span>
            </button>

            <button
              type="button"
              @click="runSheetAction(() => { noteOpen = !noteOpen })"
              class="w-full min-h-[48px] px-4 flex items-center justify-between text-sm font-medium text-zinc-900 dark:text-white active:bg-black/[0.04] dark:active:bg-white/[0.06]"
            >
              <span class="inline-flex items-center gap-2.5">
                <NotebookPen class="w-4 h-4 text-amber-600 dark:text-amber-400" />
                <span>{{ savedNote ? t('编辑笔记', 'Edit Note') : t('记笔记', 'Add Note') }}</span>
              </span>
            </button>

            <button
              type="button"
              @click="runSheetAction(() => emit('toggle-read', event))"
              class="w-full min-h-[48px] px-4 flex items-center justify-between text-sm font-medium text-zinc-900 dark:text-white active:bg-black/[0.04] dark:active:bg-white/[0.06]"
            >
              <span class="inline-flex items-center gap-2.5">
                <CheckCircle2 class="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                <span>{{ isRead ? t('标为未读', 'Mark Unread') : t('标为已读', 'Mark Read') }}</span>
              </span>
            </button>

            <template v-if="showModerationActions">
              <button
                type="button"
                @click="runSheetAction(() => emit('toggle-read-later', event.event_id))"
                class="w-full min-h-[48px] px-4 flex items-center justify-between text-sm font-medium text-zinc-900 dark:text-white active:bg-black/[0.04] dark:active:bg-white/[0.06]"
              >
                <span class="inline-flex items-center gap-2.5">
                  <Bookmark class="w-4 h-4 text-blue-600 dark:text-blue-400" />
                  <span>{{ isReadLater ? t('移出稍后深读', 'Remove Read Later') : t('加入稍后深读', 'Read Later') }}</span>
                </span>
              </button>
              <button
                type="button"
                @click="runSheetAction(() => emit('toggle-downweight', event.storyline_id || event.event_id))"
                class="w-full min-h-[48px] px-4 flex items-center justify-between text-sm font-medium text-zinc-900 dark:text-white active:bg-black/[0.04] dark:active:bg-white/[0.06]"
              >
                <span class="inline-flex items-center gap-2.5">
                  <ThumbsDown class="w-4 h-4 text-zinc-500" />
                  <span>{{ downweighted ? t('恢复推荐权重', 'Restore Weight') : t('减少此类推荐', 'Show Less Like This') }}</span>
                </span>
              </button>
              <button
                type="button"
                @click="runSheetAction(() => emit('toggle-mute', event.storyline_id || event.event_id))"
                class="w-full min-h-[48px] px-4 flex items-center justify-between text-sm font-medium text-rose-600 dark:text-rose-400 active:bg-black/[0.04] dark:active:bg-white/[0.06]"
              >
                <span class="inline-flex items-center gap-2.5">
                  <EyeOff class="w-4 h-4" />
                  <span>{{ t('屏蔽该事件主线', 'Mute Thread') }}</span>
                </span>
              </button>
            </template>
          </div>

          <button
            type="button"
            @click="actionSheetOpen = false"
            class="w-full min-h-[50px] rounded-2xl bg-white dark:bg-zinc-900 text-sm font-bold text-blue-600 dark:text-blue-400 shadow-lg flex items-center justify-center gap-1.5"
          >
            <X class="w-4 h-4" />
            <span>{{ t('取消', 'Cancel') }}</span>
          </button>
        </div>
      </div>
    </Teleport>
  </div>
</template>
