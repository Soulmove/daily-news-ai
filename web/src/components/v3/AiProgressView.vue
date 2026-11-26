<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import {
  AlertTriangle,
  Bot,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  GitBranch,
  Search,
  SlidersHorizontal,
  Sparkles,
  X,
} from 'lucide-vue-next'
import EmptySearchState from '../EmptySearchState.vue'
import SmartTime from '../SmartTime.vue'
import { appLang, pickBiText, t, translateSourceName } from '../../core/i18n'
import { centerPillIntoView } from '../../core/dom'
import { stripEmoji } from '../../core/icons'
import { normalizeExternalUrl, unwrapRawDictText } from '../../core/legacyAdapter'
import { matchesSmartQuery } from '../../core/search'
import { lockBodyScroll, triggerHaptic, unlockBodyScroll } from '../../core/uiPrefs'
import type { AiModelLineageNode, AiProgressDoc, AiProgressItem, ManifestV2 } from '../../core/types'
import type { WireTransportMode } from '../../core/wireStream'

const props = defineProps<{
  doc: AiProgressDoc | null
  manifest?: ManifestV2 | null
  searchQuery?: string
  nowMs?: number
  transportMode?: WireTransportMode
  justArrivedIds?: string[]
}>()

const emit = defineEmits<{
  (e: 'jump-event-id', eventId: string): void
  (e: 'mark-read-event-id', eventId: string): void
  (e: 'clear-search'): void
}>()

const regionFilter = ref<'all' | '一手' | '海外' | '国内' | '开源'>('all')
const dimFilter = ref<'all' | 'flagship_release' | 'research_breakthrough' | 'api_agent_eng' | 'open_source_eco' | 'commercial_governance'>('all')
const selectedCompanyId = ref<string>('all')
const selectedLineageIdx = ref<number>(0)
const lineageModelFilter = ref<string>('')
const companySheetOpen = ref(false)
const filterMenuOpen = ref(false)
const expandedRowIds = ref<Set<string>>(new Set())
const effectiveNowMs = computed(() => props.nowMs ?? Date.now())
const arrivedSet = computed(() => new Set(props.justArrivedIds ?? []))

const DIMENSION_TABS = [
  { id: 'all', zh: '全部维度', en: 'All Dims' },
  { id: 'flagship_release', zh: '旗舰模型', en: 'Flagships' },
  { id: 'research_breakthrough', zh: '科研突破', en: 'Research' },
  { id: 'api_agent_eng', zh: 'API 工程', en: 'API & Agents' },
  { id: 'open_source_eco', zh: '开源生态', en: 'Open Source' },
  { id: 'commercial_governance', zh: '商业治理', en: 'Governance' },
] as const

const activeDoc = computed<AiProgressDoc | null>(() => props.doc)

function isFirstHandItem(it: { is_first_hand?: boolean; source_tier?: string }): boolean {
  return Boolean(it.is_first_hand || it.source_tier === 'first_party')
}

function scrubDisplayText(text: string | null | undefined): string {
  return unwrapRawDictText(text)
    .replace(/\s*[-–—|｜]?\s*https?:\/\/\S+/gi, '')
    .replace(/\s*[-–—|｜]?\s*\bwww\.[A-Za-z0-9.-]+\.[a-z]{2,}\S*/gi, '')
    .replace(/\s+[-–—|｜]+\s*$/, '')
    .trim()
}

function distinctSummary(item: {
  title?: string | null
  title_en?: string | null
  what_it_does?: string | null
  what_it_does_en?: string | null
}): string {
  const titleText = scrubDisplayText(pickBiText(item.title, item.title_en))
  const sumText = scrubDisplayText(pickBiText(item.what_it_does, item.what_it_does_en))
  if (!sumText) return ''
  const normTitle = titleText.replace(/[\s\-_·:：,，.。!！?？()（）\[\]【】'"“”‘’/]+/g, '').toLowerCase()
  const normSum = sumText.replace(/[\s\-_·:：,，.。!！?？()（）\[\]【】'"“”‘’/]+/g, '').toLowerCase()
  if (!normSum || normSum === normTitle) return ''
  if (normTitle.length >= 8 && normSum.startsWith(normTitle.slice(0, 14))) return ''
  return sumText
}

function onSheetKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && companySheetOpen.value) {
    e.preventDefault()
    e.stopPropagation()
    companySheetOpen.value = false
  }
}

watch(companySheetOpen, (open) => {
  if (open) {
    lockBodyScroll()
    if (typeof window !== 'undefined') window.addEventListener('keydown', onSheetKeydown, true)
  } else {
    unlockBodyScroll()
    if (typeof window !== 'undefined') window.removeEventListener('keydown', onSheetKeydown, true)
  }
})

watch(selectedCompanyId, () => {
  lineageModelFilter.value = ''
  const comp = activeCompany.value
  const lineageLen = comp?.model_lineage?.length || 0
  selectedLineageIdx.value = lineageLen > 0 ? lineageLen - 1 : 0
})

onUnmounted(() => {
  if (companySheetOpen.value) unlockBodyScroll()
  if (typeof window !== 'undefined') window.removeEventListener('keydown', onSheetKeydown, true)
})

function selectCompany(id: string) {
  triggerHaptic(10)
  if (id !== 'all' && getOrgCount(id) === 0) {
    regionFilter.value = 'all'
    dimFilter.value = 'all'
  }
  selectedCompanyId.value = id
  companySheetOpen.value = false
  lineageModelFilter.value = ''
  const comp =
    id === 'all' || !activeDoc.value
      ? null
      : activeDoc.value.companies.find((c) => c.company_id === id) || null
  const lineageLen = comp?.model_lineage?.length || 0
  selectedLineageIdx.value = lineageLen > 0 ? lineageLen - 1 : 0
}

function selectCompanyFromSheet(id: string) {
  selectCompany(id)
}

function toggleRow(id: string, eventId?: string | null) {
  const next = new Set(expandedRowIds.value)
  const opening = !next.has(id)
  if (opening) {
    next.add(id)
    if (eventId) emit('mark-read-event-id', eventId)
  } else {
    next.delete(id)
  }
  expandedRowIds.value = next
}

const baseFilteredTimeline = computed<AiProgressItem[]>(() => {
  const list = activeDoc.value?.timeline || []
  const q = (props.searchQuery || '').trim().toLowerCase()
  const filtered = list.filter((it) => {
    if (regionFilter.value === '海外' && it.region !== '海外') return false
    if (regionFilter.value === '国内' && it.region !== '国内') return false
    if (regionFilter.value === '开源' && !it.is_open_source) return false
    if (regionFilter.value === '一手' && !isFirstHandItem(it)) return false
    if (dimFilter.value !== 'all' && it.milestone_dim !== dimFilter.value) return false
    if (!q) return true
    return matchesSmartQuery(`${it.title} ${it.title_en || ''} ${it.what_it_does} ${it.company_name}`, q)
  })
  return [...filtered].sort((a, b) => {
    const da = (a.date || '').trim()
    const db = (b.date || '').trim()
    const dayCmp = db.slice(0, 10).localeCompare(da.slice(0, 10))
    if (dayCmp !== 0) return dayCmp
    const hasTimeA = da.length > 10 ? 1 : 0
    const hasTimeB = db.length > 10 ? 1 : 0
    if (hasTimeB !== hasTimeA) return hasTimeB - hasTimeA
    return db.localeCompare(da)
  })
})

const orgCountMap = computed(() => {
  const m = new Map<string, number>()
  for (const it of baseFilteredTimeline.value) {
    const cid = it.company_id
    if (!cid) continue
    m.set(cid, (m.get(cid) || 0) + 1)
  }
  return m
})

function getOrgCount(companyId: string): number {
  return orgCountMap.value.get(companyId) || 0
}

const filteredCompanies = computed(() => {
  const list = activeDoc.value?.companies || []
  const filtered = list.filter((c) => {
    const dynCnt = getOrgCount(c.company_id)
    if (dynCnt === 0 && selectedCompanyId.value !== c.company_id) {
      return false
    }
    return true
  })
  return [...filtered].sort(
    (a, b) => getOrgCount(b.company_id) - getOrgCount(a.company_id) || (b.recent_count || 0) - (a.recent_count || 0),
  )
})

watch([regionFilter, dimFilter], () => {
  if (selectedCompanyId.value !== 'all' && getOrgCount(selectedCompanyId.value) === 0) {
    selectedCompanyId.value = 'all'
  }
})

const activeCompany = computed(() => {
  if (selectedCompanyId.value === 'all' || !activeDoc.value) return null
  return activeDoc.value.companies.find((c) => c.company_id === selectedCompanyId.value) || null
})

const activeLineageNode = computed<AiModelLineageNode | null>(() => {
  const list = activeCompany.value?.model_lineage || []
  if (!list.length) return null
  return list[selectedLineageIdx.value] || list[list.length - 1]
})

const GIANT_LINEAGE_PATTERNS: { key: RegExp; labelZh: string; labelEn: string }[] = [
  { key: /openai|chatgpt/i, labelZh: 'OpenAI GPT 谱系', labelEn: 'OpenAI' },
  { key: /google|deepmind|gemini/i, labelZh: 'Google Gemini 谱系', labelEn: 'Google' },
  { key: /anthropic|claude/i, labelZh: 'Anthropic Claude 谱系', labelEn: 'Anthropic' },
  { key: /deepseek/i, labelZh: 'DeepSeek 谱系', labelEn: 'DeepSeek' },
  { key: /qwen|千问|alibaba|阿里/i, labelZh: '阿里千问 Qwen 谱系', labelEn: 'Qwen' },
  { key: /zhipu|glm|智谱/i, labelZh: '智谱 GLM 谱系', labelEn: 'Zhipu GLM' },
]

const quickLineageCompanies = computed(() => {
  const all = activeDoc.value?.companies || []
  const picked: typeof all = []
  const seenIds = new Set<string>()
  for (const pat of GIANT_LINEAGE_PATTERNS) {
    const match = all.find(
      (c) =>
        !seenIds.has(c.company_id) &&
        (c.model_lineage?.length || 0) > 0 &&
        (pat.key.test(c.company_id) || pat.key.test(c.company_name || '') || pat.key.test(c.company_name_en || '')),
    )
    if (match) {
      seenIds.add(match.company_id)
      picked.push(match)
    }
  }
  return picked
})

function quickLineageShortName(c: { company_id: string; company_name?: string; company_name_en?: string }): string {
  for (const pat of GIANT_LINEAGE_PATTERNS) {
    if (pat.key.test(c.company_id) || pat.key.test(c.company_name || '') || pat.key.test(c.company_name_en || '')) {
      return appLang.value === 'en' ? pat.labelEn : pat.labelZh
    }
  }
  return pickBiText(c.company_name || c.company_id, c.company_name_en)
}

const filteredTimeline = computed(() => {
  const base =
    selectedCompanyId.value === 'all'
      ? baseFilteredTimeline.value
      : baseFilteredTimeline.value.filter((it) => it.company_id === selectedCompanyId.value)
  const mf = lineageModelFilter.value.trim().toLowerCase()
  if (!mf) return base
  const tokens = mf.split(/[\s/]+/).filter((t) => t.length >= 2)
  return base.filter((it) => {
    const hay = `${it.title} ${it.title_en || ''} ${it.what_it_does} ${it.what_it_does_en || ''}`.toLowerCase()
    return hay.includes(mf) || tokens.some((tok) => hay.includes(tok))
  })
})

function toggleLineageModelFilter(node: AiModelLineageNode) {
  const kw = (node.filter_keyword || node.generation || '').trim()
  if (!kw) return
  lineageModelFilter.value = lineageModelFilter.value === kw ? '' : kw
}

function regionBadgeClass(region: string): string {
  if (region === '国内') return 'bg-rose-500/12 text-rose-700 dark:bg-rose-400/15 dark:text-rose-300'
  if (region === '海外') return 'bg-[#007AFF]/12 text-[#007AFF] dark:bg-[#0A84FF]/15 dark:text-[#0A84FF]'
  return 'bg-emerald-500/12 text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-300'
}

function resetLocalFilters() {
  regionFilter.value = 'all'
  dimFilter.value = 'all'
  selectedCompanyId.value = 'all'
  lineageModelFilter.value = ''
}
</script>

<template>
  <section class="space-y-3" :aria-label="t('全球 AI 模型与前沿进展追踪', 'Global AI Model & Open-Source Progress')">
    <div
      v-if="!props.doc"
      class="ios-card p-8 text-center text-sm text-zinc-500"
    >
      {{ t('正在加载国内外 AI 模型进展与一周大事...', 'Loading global AI model & open-source progress...') }}
    </div>

    <template v-else>
      <!-- Single-Row Header + Corner SlidersHorizontal Filter Popover (No dual filter strip, No archive toggle) -->
      <div class="flex flex-col gap-2">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="ios-segmented w-full sm:w-auto flex">
            <button
              v-for="tab in [
                { id: 'all', zh: '全部', en: 'All' },
                { id: '一手', zh: '一手', en: '1st' },
                { id: '海外', zh: '海外', en: 'Global' },
                { id: '国内', zh: '国内', en: 'China' },
                { id: '开源', zh: '开源', en: 'Open' },
              ]"
              :key="tab.id"
              type="button"
              @click="regionFilter = tab.id as any; selectedCompanyId = 'all'"
              class="ios-segmented-btn flex-1 sm:flex-initial min-h-[34px] px-2 sm:px-3 whitespace-nowrap"
              :class="regionFilter === tab.id ? 'ios-segmented-btn-active' : 'text-zinc-600 dark:text-zinc-400'"
            >
              {{ appLang === 'en' ? tab.en : tab.zh }}
            </button>
          </div>

          <div class="flex items-center gap-2 relative">
            <!-- Mobile/Tablet Lab Selector Button -->
            <button
              type="button"
              @click="companySheetOpen = true"
              class="lg:hidden ios-tap inline-flex items-center justify-between gap-1.5 min-h-[36px] px-3 rounded-xl bg-white dark:bg-[#1C1C1E] text-xs font-semibold text-zinc-800 dark:text-zinc-100 shadow-[0_1px_2px_rgba(0,0,0,0.04)] shrink-0"
              :aria-label="t('选择 AI 机构', 'Select AI Lab')"
            >
              <span class="truncate">
                {{
                  activeCompany
                    ? `${pickBiText(activeCompany.company_name, activeCompany.company_name_en)} (${getOrgCount(activeCompany.company_id)})`
                    : t(`机构：全部 (${baseFilteredTimeline.length})`, `Labs: All (${baseFilteredTimeline.length})`)
                }}
              </span>
              <ChevronDown class="w-3.5 h-3.5 text-zinc-400 shrink-0" :stroke-width="1.5" />
            </button>

            <!-- Compact Corner SlidersHorizontal Dimension Filter Popover -->
            <button
              type="button"
              @click="filterMenuOpen = !filterMenuOpen"
              class="ios-tap inline-flex items-center gap-1.5 min-h-[34px] px-3 rounded-xl border text-xs font-semibold transition-colors whitespace-nowrap"
              :class="
                dimFilter !== 'all' || filterMenuOpen
                  ? 'bg-[#007AFF] text-white border-[#007AFF]'
                  : 'bg-white dark:bg-[#1C1C1E] text-zinc-700 dark:text-zinc-200 border-black/[0.08] dark:border-white/[0.1]'
              "
              data-testid="ai-dimension-filter-btn"
            >
              <SlidersHorizontal class="w-3.5 h-3.5 shrink-0" :stroke-width="1.8" />
              <span>{{ dimFilter === 'all' ? t('维度筛选', 'Dimensions') : (DIMENSION_TABS.find((d) => d.id === dimFilter)?.[appLang === 'en' ? 'en' : 'zh'] || t('筛选', 'Filter')) }}</span>
            </button>

            <div
              v-if="filterMenuOpen"
              class="absolute right-0 top-10 z-30 w-56 rounded-2xl border border-black/[0.08] dark:border-white/[0.12] bg-white dark:bg-[#1C1C1E] shadow-xl p-2 space-y-1 text-xs"
              data-testid="ai-dimension-popover"
            >
              <div class="px-2 py-1 text-[10.5px] font-semibold text-zinc-400">{{ t('按技术维度筛选进展', 'Filter by Dimension') }}</div>
              <button
                v-for="dtab in DIMENSION_TABS"
                :key="dtab.id"
                type="button"
                @click="dimFilter = dtab.id as any; filterMenuOpen = false"
                class="w-full px-2.5 py-2 rounded-xl flex items-center justify-between text-left font-medium transition-colors"
                :class="dimFilter === dtab.id ? 'bg-[#007AFF]/12 text-[#007AFF] dark:text-[#66B2FF] font-semibold' : 'text-zinc-700 dark:text-zinc-200 hover:bg-black/[0.04] dark:hover:bg-white/[0.06]'"
              >
                <span>{{ appLang === 'en' ? dtab.en : dtab.zh }}</span>
                <span v-if="dimFilter === dtab.id" class="w-1.5 h-1.5 rounded-full bg-[#007AFF]" />
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Full-Width Responsive 2-Column Layout (248px comfortable lab sidebar + spacious content pane) -->
      <div class="grid grid-cols-1 lg:grid-cols-[248px_minmax(0,1fr)] gap-3 items-start">
        <!-- Desktop Vertical Lab List -->
        <aside class="hidden lg:block ios-card p-2">
          <div class="px-2 py-1 text-[11px] font-semibold text-zinc-400 tracking-wide flex items-center justify-between">
            <span>{{ t(`选择机构 (${filteredCompanies.length})`, `AI Labs (${filteredCompanies.length})`) }}</span>
            <span class="text-[10px] text-[#007AFF]">{{ t('全库', 'Archive') }}</span>
          </div>

          <div class="flex flex-col gap-0.5">
            <button
              type="button"
              @click="selectedCompanyId = 'all'"
              class="w-full text-left px-2.5 min-h-[34px] py-1.5 rounded-xl text-xs font-semibold flex items-center justify-between gap-2 transition-colors whitespace-nowrap"
              :class="
                selectedCompanyId === 'all'
                  ? 'bg-[#007AFF] text-white'
                  : 'text-zinc-700 dark:text-zinc-200 hover:bg-black/[0.04] dark:hover:bg-white/[0.06]'
              "
            >
              <span class="truncate">{{ t('全部机构', 'All Labs') }}</span>
              <span class="text-[11px] tabular-nums opacity-80">
                {{ baseFilteredTimeline.length }}
              </span>
            </button>

            <button
              v-for="comp in filteredCompanies"
              :key="comp.company_id"
              type="button"
              @click="selectedCompanyId = comp.company_id"
              class="w-full text-left px-2.5 min-h-[34px] py-1.5 rounded-xl text-xs flex items-center justify-between gap-2 transition-colors whitespace-nowrap"
              :class="
                selectedCompanyId === comp.company_id
                  ? 'bg-[#007AFF] text-white font-semibold'
                  : 'text-zinc-700 dark:text-zinc-200 hover:bg-black/[0.04] dark:hover:bg-white/[0.06]'
              "
            >
              <div class="min-w-0 flex items-center gap-1.5">
                <Bot class="w-3.5 h-3.5 shrink-0 opacity-75" :stroke-width="1.5" />
                <span class="truncate">{{ pickBiText(comp.company_name, comp.company_name_en) }}</span>
              </div>
              <span class="shrink-0 text-[11px] font-mono tabular-nums opacity-80">
                {{ getOrgCount(comp.company_id) }}
              </span>
            </button>
          </div>
        </aside>

        <!-- Mobile/Tablet Bottom Sheet Grid for All AI Labs -->
        <Teleport to="body">
          <div
            v-if="companySheetOpen"
            class="ios-sheet-backdrop p-0 sm:p-4"
            role="dialog"
            aria-modal="true"
            :aria-label="t('选择全部 AI 机构', 'Select AI Lab')"
            @click.self="companySheetOpen = false"
          >
            <div class="ios-sheet-panel max-h-[82vh] flex flex-col">
              <div class="px-4 pt-2.5 pb-3 bg-white dark:bg-[#1C1C1E] border-b border-black/[0.06] dark:border-white/[0.08]">
                <div class="w-9 h-1 rounded-full bg-zinc-300 dark:bg-zinc-600 mx-auto mb-2 sm:hidden" />
                <div class="flex items-center justify-between">
                  <h3 class="text-[16px] font-semibold text-zinc-950 dark:text-white">
                    {{ t(`选择机构 (${filteredCompanies.length})`, `Select AI Lab (${filteredCompanies.length})`) }}
                  </h3>
                  <button
                    type="button"
                    @click="companySheetOpen = false"
                    class="w-11 h-11 -mr-2 inline-flex items-center justify-center rounded-xl text-zinc-400"
                    :aria-label="t('关闭', 'Close')"
                  >
                    <X class="w-5 h-5" :stroke-width="1.5" />
                  </button>
                </div>
              </div>
              <div class="p-3.5 overflow-y-auto grid grid-cols-2 sm:grid-cols-3 gap-2 pb-[max(1rem,env(safe-area-inset-bottom))]">
                <button
                  type="button"
                  @click="selectCompanyFromSheet('all')"
                  class="ios-tap min-h-[46px] px-3 py-2 rounded-xl flex items-center justify-between gap-1.5 text-left text-xs font-semibold"
                  :class="selectedCompanyId === 'all' ? 'bg-[#007AFF] text-white' : 'bg-white dark:bg-[#2C2C2E] text-zinc-900 dark:text-zinc-100'"
                >
                  <span class="truncate">{{ t('全部机构', 'All Labs') }}</span>
                  <span class="tabular-nums opacity-80 shrink-0">{{ baseFilteredTimeline.length }}</span>
                </button>
                <button
                  v-for="comp in filteredCompanies"
                  :key="`sheet-${comp.company_id}`"
                  type="button"
                  @click="selectCompanyFromSheet(comp.company_id)"
                  class="ios-tap min-h-[46px] px-3 py-2 rounded-xl flex items-center justify-between gap-1.5 text-left text-xs font-medium"
                  :class="selectedCompanyId === comp.company_id ? 'bg-[#007AFF] text-white font-semibold' : 'bg-white dark:bg-[#2C2C2E] text-zinc-800 dark:text-zinc-100'"
                >
                  <span class="truncate">{{ pickBiText(comp.company_name, comp.company_name_en) }}</span>
                  <span class="tabular-nums font-mono text-[11px] opacity-75 shrink-0">{{ getOrgCount(comp.company_id) }}</span>
                </button>
              </div>
            </div>
          </div>
        </Teleport>

        <div class="min-w-0 ios-card overflow-hidden">
          <!-- Selected Lab Header + Model Lineage Evolution Tree -->
          <div
            v-if="activeCompany"
            class="px-4 py-3 bg-[#F5F5F7] dark:bg-[#2C2C2E] border-b border-black/[0.06] dark:border-white/[0.08] space-y-2.5 text-xs"
          >
            <div class="flex flex-wrap items-start justify-between gap-2">
              <div class="space-y-1 min-w-0">
                <div class="flex flex-wrap items-center gap-2">
                  <span class="font-bold text-sm text-zinc-950 dark:text-white">
                    {{ pickBiText(activeCompany.company_name, activeCompany.company_name_en) }}
                  </span>
                  <span class="px-2 py-0.5 rounded-md text-[10px] font-semibold whitespace-nowrap shrink-0" :class="regionBadgeClass(activeCompany.region)">
                    {{ pickBiText(activeCompany.region, activeCompany.region_en) }}
                  </span>
                  <span class="text-zinc-600 dark:text-zinc-300 font-medium break-words">
                    {{ t('当家旗舰：', 'Flagship: ') }}{{ activeCompany.flagship_model }}
                  </span>
                </div>
                <div class="text-[11px] text-amber-700 dark:text-amber-300 flex items-start gap-1">
                  <AlertTriangle class="w-3.5 h-3.5 shrink-0 mt-0.5" />
                  <span><strong>{{ t('限制与门槛：', 'Limits: ') }}</strong>{{ pickBiText(activeCompany.access_limits, activeCompany.access_limits_en) }}</span>
                </div>
              </div>
            </div>

            <!-- Model Lineage Generational Evolution Strip -->
            <div
              v-if="(activeCompany.model_lineage || []).length > 0"
              class="rounded-xl bg-white/90 dark:bg-[#1C1C1E] border border-black/[0.06] dark:border-white/[0.08] p-2.5 space-y-2"
              data-testid="model-lineage-strip"
            >
              <div class="flex items-center justify-between gap-2 text-[11px] font-semibold text-zinc-500 dark:text-zinc-400">
                <span class="inline-flex items-center gap-1">
                  <GitBranch class="w-3.5 h-3.5 text-[#007AFF]" />
                  {{ t('模型代际演进谱系（点击查看规格与突破）', 'Model Generational Lineage') }}
                </span>
                <span v-if="activeCompany.archive_count" class="tabular-nums text-zinc-400">
                  {{ t(`归档 ${activeCompany.archive_count} 条里程碑`, `${activeCompany.archive_count} archived`) }}
                </span>
              </div>

              <div class="flex flex-nowrap sm:flex-wrap items-center gap-1.5 overflow-x-auto sm:overflow-visible no-scrollbar scroll-fade-x pb-0.5 sm:pb-0">
                <template v-for="(node, idx) in activeCompany.model_lineage" :key="node.generation">
                  <button
                    type="button"
                    @click="(e) => { selectedLineageIdx = idx; centerPillIntoView(e) }"
                    class="mobile-pressable px-2.5 py-1 rounded-lg border text-[11px] font-medium transition-colors text-left whitespace-nowrap shrink-0"
                    :class="
                      selectedLineageIdx === idx
                        ? 'bg-[#007AFF] text-white border-[#007AFF]'
                        : 'bg-zinc-50 dark:bg-zinc-800/80 text-zinc-700 dark:text-zinc-200 border-zinc-200 dark:border-zinc-700 hover:border-[#007AFF]'
                    "
                  >
                    <span class="font-semibold">{{ node.generation }}</span>
                    <span class="ml-1 opacity-75 font-mono text-[10px]">{{ node.release_date }}</span>
                  </button>
                  <span
                    v-if="idx < (activeCompany.model_lineage?.length || 0) - 1"
                    class="text-zinc-400 text-[11px] select-none shrink-0"
                  >→</span>
                </template>
              </div>

              <div
                v-if="activeLineageNode"
                class="rounded-xl bg-zinc-50 dark:bg-zinc-800/70 border border-zinc-200/80 dark:border-zinc-700/80 p-2.5 space-y-2 text-[11.5px]"
                data-testid="model-lineage-5dim-panel"
              >
                <div class="flex flex-wrap items-center justify-between gap-2">
                  <div class="flex flex-wrap items-center gap-1.5">
                    <span class="font-bold text-zinc-950 dark:text-white text-xs">{{ activeLineageNode.generation }}</span>
                    <span class="px-1.5 py-0.5 rounded bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 font-mono text-[10px] text-zinc-600 dark:text-zinc-300">
                      {{ activeLineageNode.release_date }}
                    </span>
                    <span
                      v-if="activeLineageNode.status"
                      class="px-1.5 py-0.5 rounded bg-emerald-500/12 text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-300 text-[10px] font-semibold"
                    >
                      {{ activeLineageNode.status }}
                    </span>
                  </div>
                  <button
                    type="button"
                    @click="toggleLineageModelFilter(activeLineageNode)"
                    class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border text-[11px] font-semibold transition-colors whitespace-nowrap"
                    :class="lineageModelFilter === (activeLineageNode.filter_keyword || activeLineageNode.generation)
                      ? 'bg-[#007AFF] text-white border-[#007AFF]'
                      : 'bg-white dark:bg-zinc-900 text-[#007AFF] dark:text-[#66B2FF] border-[#007AFF]/40 hover:bg-[#007AFF]/10'"
                    data-testid="lineage-filter-btn"
                  >
                    <Search class="w-3 h-3 shrink-0" />
                    <span>
                      {{ lineageModelFilter === (activeLineageNode.filter_keyword || activeLineageNode.generation)
                        ? t('取消模型筛选', 'Clear Filter')
                        : t('一键筛选该模型相关动态', 'Filter Model News') }}
                    </span>
                  </button>
                </div>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-1.5 text-[11px]">
                  <div class="rounded-lg bg-white/80 dark:bg-zinc-900/70 px-2.5 py-1.5 border border-black/[0.04] dark:border-white/[0.06]">
                    <span class="font-semibold text-zinc-500 dark:text-zinc-400">{{ t('参数与上下文：', 'Specs & Context: ') }}</span>
                    <span class="font-mono text-zinc-800 dark:text-zinc-200">{{ activeLineageNode.specs }}</span>
                  </div>
                  <div
                    v-if="activeLineageNode.pricing_or_license"
                    class="rounded-lg bg-white/80 dark:bg-zinc-900/70 px-2.5 py-1.5 border border-black/[0.04] dark:border-white/[0.06]"
                  >
                    <span class="font-semibold text-zinc-500 dark:text-zinc-400">{{ t('定价 / 协议：', 'Pricing / License: ') }}</span>
                    <span class="text-zinc-800 dark:text-zinc-200">{{ activeLineageNode.pricing_or_license }}</span>
                  </div>
                </div>
                <div class="text-zinc-700 dark:text-zinc-200 leading-relaxed">
                  <strong class="text-zinc-500 dark:text-zinc-400 font-semibold">{{ t('核心突破与评测：', 'Breakthrough: ') }}</strong>{{ scrubDisplayText(activeLineageNode.highlight) }}
                </div>
              </div>
            </div>
          </div>

          <div v-else class="px-3.5 py-2 border-b border-black/[0.05] dark:border-white/[0.06] bg-gradient-to-r from-[#007AFF]/[0.05] via-transparent to-emerald-500/[0.04]">
            <div class="flex items-center gap-1.5 overflow-x-auto no-scrollbar scroll-fade-x whitespace-nowrap">
              <span class="text-[11px] font-semibold text-zinc-600 dark:text-zinc-300 inline-flex items-center gap-1 mr-0.5 shrink-0">
                <Sparkles class="w-3.5 h-3.5 text-[#007AFF]" :stroke-width="1.75" />
                <span>{{ t('热门巨头演进谱系：', 'Giant Lineages:') }}</span>
              </span>
              <button
                v-for="gc in quickLineageCompanies"
                :key="'ql_' + gc.company_id"
                type="button"
                @click="(e) => { selectCompany(gc.company_id); centerPillIntoView(e) }"
                class="ios-tap mobile-pressable px-2.5 min-h-[30px] rounded-full border border-[#007AFF]/25 bg-white/90 dark:bg-zinc-900/90 text-[11px] font-semibold text-[#007AFF] dark:text-[#66B2FF] hover:bg-[#007AFF] hover:text-white transition-colors shrink-0 whitespace-nowrap"
              >
                {{ quickLineageShortName(gc) }}
              </button>
            </div>
          </div>

          <div class="px-3.5 py-2 bg-zinc-50/80 dark:bg-zinc-900/60 border-b border-black/[0.05] dark:border-white/[0.06] flex flex-wrap items-center justify-between gap-2 text-xs text-zinc-500">
            <div class="flex flex-wrap items-center gap-2">
              <span class="font-semibold text-zinc-700 dark:text-zinc-200">
                {{ activeCompany ? pickBiText(activeCompany.company_name, activeCompany.company_name_en) : t('AI 前沿全机构演进动态（去重汇总）', 'All-Lab AI Milestones (Deduplicated)') }}
              </span>
              <button
                v-if="lineageModelFilter"
                type="button"
                @click="lineageModelFilter = ''"
                class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-[#007AFF]/12 text-[#007AFF] dark:text-[#66B2FF] text-[10.5px] font-semibold"
              >
                <span>{{ t(`已筛选模型: ${lineageModelFilter}`, `Model: ${lineageModelFilter}`) }}</span>
                <X class="w-3 h-3" />
              </button>
            </div>
            <span class="tabular-nums font-mono">{{ filteredTimeline.length }}</span>
          </div>

          <!-- Empty State -->
          <div v-if="filteredTimeline.length === 0" class="p-4">
            <EmptySearchState
              :query="props.searchQuery || lineageModelFilter"
              :has-extra-filters="regionFilter !== 'all' || dimFilter !== 'all' || selectedCompanyId !== 'all' || Boolean(lineageModelFilter)"
              @clear-query="emit('clear-search')"
              @clear-filters-only="resetLocalFilters"
              @reset="resetLocalFilters(); emit('clear-search')"
            />
          </div>

          <!-- Spacious Multi-Line Non-Truncating List -->
          <ul v-else class="divide-y divide-slate-100 dark:divide-slate-800/80 text-xs">
            <li
              v-for="item in filteredTimeline"
              :key="item.id"
              class="transition-colors"
              :class="
                arrivedSet.has(item.id)
                  ? 'bg-amber-50/75 dark:bg-amber-950/25 border-l-4 border-l-amber-500 hover:bg-amber-50'
                  : 'hover:bg-slate-50/90 dark:hover:bg-slate-800/50'
              "
            >
              <div
                @click="toggleRow(item.id, item.event_id)"
                class="px-3.5 py-3 flex flex-col gap-1.5 cursor-pointer"
              >
                <!-- Meta Row + Action Row (never squashes headline width!) -->
                <div class="flex items-start justify-between gap-2">
                  <div class="flex flex-wrap items-center gap-1.5 min-w-0">
                    <span class="shrink-0 font-mono text-[11px] text-slate-400 tabular-nums whitespace-nowrap">
                      <SmartTime :iso="item.date" :now-ms="effectiveNowMs" />
                    </span>
                    <span
                      v-if="arrivedSet.has(item.id)"
                      class="shrink-0 px-1.5 py-0.5 rounded bg-amber-500 text-white text-[10px] font-bold whitespace-nowrap"
                    >
                      NEW
                    </span>
                    <span
                      v-if="isFirstHandItem(item)"
                      class="shrink-0 px-1.5 py-0.5 rounded-md bg-emerald-500/12 text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-300 text-[10px] font-semibold whitespace-nowrap"
                    >
                      {{ t('一手官方', '1st-Hand') }}
                    </span>
                    <span
                      v-if="item.is_open_source"
                      class="shrink-0 px-1.5 py-0.5 rounded-md bg-violet-500/12 text-violet-700 dark:bg-violet-400/15 dark:text-violet-300 text-[10px] font-semibold whitespace-nowrap"
                    >
                      {{ t('开源', 'OSS') }}
                    </span>
                    <span
                      class="shrink-0 px-1.5 py-0.5 rounded-md text-[10px] font-semibold whitespace-nowrap"
                      :class="regionBadgeClass(item.region)"
                    >
                      {{ item.company_name }}
                    </span>
                    <span
                      v-if="item.milestone_dim_label"
                      class="shrink-0 px-1.5 py-0.5 rounded-md bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300 text-[10px] font-medium whitespace-nowrap"
                    >
                      {{ stripEmoji(pickBiText(item.milestone_dim_label, item.milestone_dim_label_en)) }}
                    </span>
                    <span
                      v-if="(item.related_sources?.length || 0) > 1"
                      class="shrink-0 px-1.5 py-0.5 rounded-md bg-blue-500/10 text-blue-700 dark:text-blue-300 text-[10px] font-medium whitespace-nowrap tabular-nums"
                    >
                      {{ t(`${item.related_sources!.length} 源合并`, `${item.related_sources!.length} sources`) }}
                    </span>
                  </div>

                  <div class="flex shrink-0 items-center gap-1.5" @click.stop>
                    <button
                      v-if="item.event_id"
                      type="button"
                      @click="emit('mark-read-event-id', item.event_id); emit('jump-event-id', item.event_id)"
                      class="text-[11px] text-blue-600 dark:text-blue-400 hover:underline font-medium whitespace-nowrap px-1"
                    >
                      {{ t('简报', 'Brief') }}
                    </button>
                    <a
                      v-if="normalizeExternalUrl(item.source_url)"
                      :href="normalizeExternalUrl(item.source_url)!"
                      target="_blank"
                      rel="noopener noreferrer"
                      @click.stop="item.event_id && emit('mark-read-event-id', item.event_id)"
                      class="inline-flex items-center gap-0.5 px-1.5 min-h-[28px] rounded-lg text-[11px] text-violet-600 dark:text-violet-400 hover:underline font-medium whitespace-nowrap"
                    >
                      <span>{{ t('原文', 'Link') }}</span>
                      <ExternalLink class="w-3 h-3" />
                    </a>
                    <button
                      type="button"
                      @click="toggleRow(item.id, item.event_id)"
                      class="w-7 h-7 inline-flex items-center justify-center rounded-md text-slate-400 hover:text-slate-700 dark:hover:text-white"
                      :aria-label="t('展开详情', 'Toggle detail')"
                    >
                      <ChevronUp v-if="expandedRowIds.has(item.id)" class="w-4 h-4" />
                      <ChevronDown v-else class="w-4 h-4" />
                    </button>
                  </div>
                </div>

                <!-- Full Unclipped Headline & Summary -->
                <div class="min-w-0 space-y-1">
                  <div class="font-semibold text-[14px] text-zinc-900 dark:text-white leading-[1.4] break-words">
                    {{ scrubDisplayText(pickBiText(item.title, item.title_en)) }}
                  </div>
                  <p
                    v-if="distinctSummary(item) && !expandedRowIds.has(item.id)"
                    class="text-[12.5px] text-zinc-500 dark:text-zinc-400 leading-[1.5] line-clamp-2"
                  >
                    {{ distinctSummary(item) }}
                  </p>
                </div>
              </div>

              <!-- Expanded Full Text + Multi-Source Comparison -->
              <div
                v-if="expandedRowIds.has(item.id)"
                class="px-4 pb-3.5 pt-2 bg-zinc-50/70 dark:bg-zinc-800/30 text-xs space-y-2 text-zinc-600 dark:text-zinc-300 border-t border-black/[0.05] dark:border-white/[0.06]"
              >
                <p v-if="distinctSummary(item)" class="leading-relaxed text-zinc-700 dark:text-zinc-200">
                  {{ distinctSummary(item) }}
                </p>
                <p v-if="item.who_cares" class="text-[11px] text-zinc-500">
                  <strong>{{ t('适用人群：', 'Audience: ') }}</strong>{{ item.who_cares }}
                </p>
                <p v-if="item.limitations" class="text-amber-700 dark:text-amber-300">
                  <strong>{{ t('限制与门槛：', 'Limits: ') }}</strong>{{ pickBiText(item.limitations, item.limitations_en) }}
                </p>
                <div v-if="(item.related_sources?.length || 0) > 0" class="flex flex-wrap items-center gap-1.5 pt-0.5">
                  <span class="text-[11px] font-medium text-zinc-400">{{ t('多源对照：', 'Sources:') }}</span>
                  <template v-for="(rs, rIdx) in item.related_sources" :key="rIdx">
                    <a
                      v-if="normalizeExternalUrl(rs.url)"
                      :href="normalizeExternalUrl(rs.url)!"
                      target="_blank"
                      rel="noopener noreferrer"
                      @click.stop="item.event_id && emit('mark-read-event-id', item.event_id)"
                      class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-white dark:bg-zinc-900 border border-black/[0.08] dark:border-white/[0.1] text-[11px] hover:underline whitespace-nowrap"
                      :class="rs.is_first_hand ? 'text-emerald-700 dark:text-emerald-300 font-semibold' : 'text-zinc-600 dark:text-zinc-300'"
                    >
                      <span>{{ translateSourceName(rs.source_name, item.title) }}</span>
                      <span v-if="rs.is_first_hand" class="text-[9px]">(一手)</span>
                      <ExternalLink class="w-2.5 h-2.5" />
                    </a>
                    <span
                      v-else
                      class="px-2 py-0.5 rounded-md bg-white dark:bg-zinc-900 border border-black/[0.08] dark:border-white/[0.1] text-[11px]"
                    >
                      {{ translateSourceName(rs.source_name, item.title) }}
                    </span>
                  </template>
                </div>
                <div class="text-[11px] text-zinc-400">
                  {{ translateSourceName(item.source_name, item.title) }} · <SmartTime :iso="item.date" :now-ms="effectiveNowMs" />
                </div>
              </div>
            </li>
          </ul>
        </div>
      </div>
    </template>
  </section>
</template>
