<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ChevronDown,
  Clock,
  ExternalLink,
  GitBranch,
  Layers,
  Search,
  Sparkles,
  X,
} from 'lucide-vue-next'
import EmptySearchState from '../EmptySearchState.vue'
import LoadingSkeleton from '../LoadingSkeleton.vue'
import SmartTime from '../SmartTime.vue'
import { pickBiText, t, translateEntityName, translateSourceName, truncateAtSentence } from '../../core/i18n'
import { centerPillIntoView } from '../../core/dom'
import { resolveEvidenceTierBadge } from '../../core/evidence'
import { normalizeExternalUrl } from '../../core/legacyAdapter'
import { matchesSmartQuery } from '../../core/search'
import { parseTimestampMs } from '../../core/time'
import { DEFAULT_PAGE_SIZE, getConfidentEntities, paginateItems, sortStorylines, type EventSortMode } from '../../core/v3Logic'
import { CATEGORIES, type StorylineDossier, type WatchlistItem } from '../../core/types'

const props = defineProps<{
  storylines: Record<string, StorylineDossier>
  selectedStorylineId: string | null
  searchQuery?: string
  watchlist?: WatchlistItem[]
  mutedSet?: Set<string>
  nowMs?: number
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: 'select-storyline', id: string | null): void
  (e: 'select-entity', name: string): void
  (e: 'open-qa-storyline', dossier: StorylineDossier): void
  (e: 'back-to-today'): void
  (e: 'clear-search'): void
}>()

const filterCat = ref<string>('all')
const sortBy = ref<EventSortMode>('latest')
const localQuery = ref('')
const visibleLimit = ref(DEFAULT_PAGE_SIZE)
const effectiveNowMs = computed(() => props.nowMs ?? Date.now())
const effectiveQuery = computed(() => (localQuery.value || props.searchQuery || '').trim().toLowerCase())

const PUNCT_ONLY_RE = /^[\W_\s“”"'‘’•·.,!?;:()（）【】《》<>—\-]+$/

function cleanZhText(text?: string | null): string {
  if (!text) return ''
  return text.replace(/倍數/g, '倍数').trim()
}

function cleanBullets(list?: string[] | null): string[] {
  if (!Array.isArray(list)) return []
  return list
    .map((item) => cleanZhText(item))
    .filter((item) => item.length >= 2 && !PUNCT_ONLY_RE.test(item))
}

const storylineList = computed(() => {
  const q = effectiveQuery.value
  const muted = props.mutedSet
  const base = Object.values(props.storylines).filter((s) => {
    if (muted && (muted.has(s.storyline_id) || muted.has(s.current_event_id) || (s.entity_ids || []).some((id) => muted.has(id)))) {
      return false
    }
    if (filterCat.value !== 'all' && s.category !== filterCat.value) return false
    if (q) {
      const hay = `${s.title} ${s.title_en || ''} ${s.entities.join(' ')} ${s.current_stage}`
      if (!matchesSmartQuery(hay, q)) return false
    }
    return true
  })
  return sortStorylines(base, sortBy.value, props.watchlist || [])
})

const pagedStorylines = computed(() => paginateItems(storylineList.value, visibleLimit.value))

function dossierEntities(st: StorylineDossier) {
  return getConfidentEntities(st.entities || [], st.entity_confidences)
}

const activeDossier = computed<StorylineDossier | null>(() => {
  if (!props.selectedStorylineId) return null
  return props.storylines[props.selectedStorylineId] ?? null
})

const dossierEvidenceBadge = computed(() => {
  const d = activeDossier.value
  if (!d) return null
  return resolveEvidenceTierBadge({
    evidence_tier: d.evidence_tier,
    evidence_tier_label: d.evidence_tier_label,
    evidence_status: d.evidence_status,
    sources: d.sources,
    title: d.title,
  })
})

const isDossierUnverifiedOrResearch = computed(() => {
  const d = activeDossier.value
  if (!d) return false
  if (d.evidence_status === 'needs_verification') return true
  if (dossierEvidenceBadge.value) return dossierEvidenceBadge.value.isUnverifiedOrResearch
  return d.evidence_status === 'single_source'
})

const cleanedNewFacts = computed(() => cleanBullets(activeDossier.value?.fact_diff?.new_facts))
const cleanedCorrections = computed(() => {
  const d = activeDossier.value
  if (!d) return []
  const raw = d.contradictions.length ? d.contradictions : d.fact_diff.corrections
  return cleanBullets(raw)
})
const cleanedUnchanged = computed(() => cleanBullets(activeDossier.value?.fact_diff?.unchanged_background))
const cleanedOpVars = computed(() => cleanBullets(activeDossier.value?.investment_card?.operating_variables))
const cleanedValidationNodes = computed(() => cleanBullets(activeDossier.value?.investment_card?.validation_nodes))
const hasSupplyChain = computed(() => {
  const sc = activeDossier.value?.investment_card?.supply_chain_links
  if (!sc) return false
  return (sc.upstream?.length || 0) + (sc.downstream?.length || 0) > 0
})
const relatedAssetsList = computed(() => activeDossier.value?.investment_card?.related_assets || [])
const effectiveFirstDiscoveredAt = computed(() => {
  const d = activeDossier.value
  if (!d) return null
  const discIso = d.first_discovered_at
  const updIso = d.latest_fact_update_at
  const discMs = parseTimestampMs(discIso)
  const updMs = parseTimestampMs(updIso)
  if (discMs !== null && updMs !== null && discMs > updMs) {
    const repMs = parseTimestampMs(d.first_reported_at)
    if (repMs !== null && repMs <= updMs) return d.first_reported_at
    return updIso
  }
  return discIso || d.first_reported_at || updIso || null
})
const investmentStageGridClass = computed(() => {
  const cnt =
    1 +
    (cleanedOpVars.value.length > 0 ? 1 : 0) +
    (hasSupplyChain.value ? 1 : 0) +
    (relatedAssetsList.value.length > 0 ? 1 : 0) +
    (cleanedValidationNodes.value.length > 0 ? 1 : 0)
  if (cnt <= 2) return 'grid-cols-1 sm:grid-cols-2'
  if (cnt === 3) return 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3'
  if (cnt === 4) return 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-4'
  return 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-5'
})

function isPlaceholderOrEnglishText(raw?: string | null): boolean {
  const s = (raw || '').trim()
  if (!s) return true
  if (s.includes('该条为海外主流媒体英文原报') || s.includes('云端 AI 批次将自动')) return true
  const cjk = (s.match(/[\u4e00-\u9fff]/g) || []).length
  const lat = (s.match(/[A-Za-z]/g) || []).length
  return lat >= 16 && cjk <= 2
}

function getDossierFallbackPreview(st: StorylineDossier): { text: string; untranslated: boolean } {
  const hasCjk = (s: string) => /[\u4e00-\u9fff]/.test(s)
  const newFacts = cleanBullets(st.fact_diff?.new_facts)
  const bgFacts = cleanBullets(st.fact_diff?.unchanged_background)
  const timelineSummaries = (st.timeline || [])
    .map((n) => (n?.fact_summary || '').replace(/^【[^】]{2,14}】\s*/, '').trim())
    .filter((s) => Boolean(s) && !s.includes('该条为海外主流媒体英文原报') && !s.includes('云端 AI 批次将自动'))

  const zhCandidates = [
    ...newFacts,
    ...bgFacts,
    ...timelineSummaries,
    (st.ai_analysis?.core_fact || '').trim(),
    (st.next_catalyst || '').trim(),
  ]
  const zhHit = zhCandidates.find((c) => Boolean(c) && !isPlaceholderOrEnglishText(c) && hasCjk(c))
  if (zhHit) {
    return { text: truncateAtSentence(zhHit, 120), untranslated: false }
  }

  const fallbackPool = [
    newFacts[0],
    bgFacts[0],
    timelineSummaries[0],
    st.summary_en,
    st.sources?.[0]?.title,
    st.title_en,
    st.title,
  ]
  const firstNonPh = (
    fallbackPool.find((c) => Boolean(c) && !String(c).includes('该条为海外主流媒体英文原报') && !String(c).includes('云端 AI 批次将自动')) || ''
  )
    .replace(/^【[^】]{2,14}】\s*/, '')
    .trim()
  const truncated = truncateAtSentence(firstNonPh, 120)
  return { text: truncated, untranslated: Boolean(truncated) && isPlaceholderOrEnglishText(truncated) }
}

function resetAllFilters() {
  filterCat.value = 'all'
  localQuery.value = ''
  emit('clear-search')
}
</script>

<template>
  <section class="space-y-4" :aria-label="t('事件持续追踪与跨批次差异', 'Storyline Tracking & Cross-Batch Fact Diffs')">
    <!-- Detail View when a storyline is selected -->
    <div v-if="activeDossier" class="space-y-4">
      <!-- Return Navigation Breadcrumb -->
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div class="flex items-center gap-2">
          <button
            type="button"
            @click="emit('select-storyline', null)"
            class="inline-flex items-center gap-1.5 px-3 min-h-[38px] sm:min-h-[32px] rounded-xl sm:rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700"
          >
            <ArrowLeft class="w-3.5 h-3.5" />
            <span>{{ t('返回追踪列表', 'Back to Tracking') }}</span>
          </button>
          <button
            type="button"
            @click="emit('back-to-today')"
            class="inline-flex items-center gap-1 px-2.5 min-h-[38px] sm:min-h-[32px] rounded-xl sm:rounded-lg text-xs text-blue-600 dark:text-blue-400 hover:underline"
          >
            {{ t('返回今日', 'Today') }}
          </button>
        </div>

        <button
          type="button"
          @click="emit('open-qa-storyline', activeDossier)"
          class="inline-flex items-center gap-1.5 px-3 min-h-[38px] sm:min-h-[32px] rounded-xl sm:rounded-lg bg-blue-600 text-white text-xs font-semibold hover:bg-blue-700"
        >
          <Sparkles class="w-3.5 h-3.5" />
          <span>{{ t('基于此事件档案提问 / 记笔记', 'Ask Q&A & Notes on Dossier') }}</span>
        </button>
      </div>

      <!-- Dossier Header & Honest 4-timestamp breakdown -->
      <article class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 sm:p-6 space-y-4 shadow-xs">
        <div class="space-y-2">
          <div class="flex flex-wrap items-center gap-2 text-xs">
            <span class="px-2 py-0.5 rounded bg-violet-50 text-violet-800 border border-violet-200 dark:bg-violet-950/60 dark:text-violet-200 dark:border-violet-800 font-semibold">
              {{ activeDossier.current_stage }}
            </span>
            <span
              v-if="dossierEvidenceBadge"
              class="px-2 py-0.5 rounded border font-medium"
              :class="dossierEvidenceBadge.badgeClass"
            >
              {{ dossierEvidenceBadge.label }}
            </span>
          </div>
          <h2 class="text-lg sm:text-xl font-bold text-slate-900 dark:text-white leading-snug">
            {{ pickBiText(activeDossier.title_zh || activeDossier.title, activeDossier.title_en || activeDossier.title) }}
          </h2>
          <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs bg-slate-50 dark:bg-slate-800/60 rounded-xl p-3 border border-slate-200/80 dark:border-slate-700/80 tabular-nums">
            <div>
              <span class="block text-[11px] text-slate-500">{{ t('工作台首次发现', 'First Discovered') }}</span>
              <span class="font-semibold text-slate-800 dark:text-slate-100">
                <SmartTime :iso="effectiveFirstDiscoveredAt" :now-ms="effectiveNowMs" />
              </span>
            </div>
            <div>
              <span class="block text-[11px] text-slate-500">{{ t('最早外部披露', 'First Reported') }}</span>
              <span class="font-semibold text-slate-800 dark:text-slate-100">
                <SmartTime :iso="activeDossier.first_reported_at" :now-ms="effectiveNowMs" />
              </span>
            </div>
            <div>
              <span class="block text-[11px] text-slate-500">{{ t('最新事实更新', 'Latest Fact Update') }}</span>
              <span class="font-semibold text-slate-800 dark:text-slate-100">
                <SmartTime :iso="activeDossier.latest_fact_update_at" :now-ms="effectiveNowMs" />
              </span>
            </div>
            <div>
              <span class="block text-[11px] text-slate-500">{{ t('最新转述/报道', 'Latest Mention') }}</span>
              <span class="font-semibold text-slate-800 dark:text-slate-100">
                <SmartTime :iso="activeDossier.latest_reported_at" :now-ms="effectiveNowMs" />
              </span>
            </div>
          </div>
        </div>

        <!-- 1. Cross-Batch Fact Diff -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
          <div
            class="rounded-xl border p-3.5 space-y-1.5"
            :class="
              isDossierUnverifiedOrResearch
                ? 'border-amber-200 dark:border-amber-900 bg-amber-50/50 dark:bg-amber-950/20'
                : 'border-emerald-200 dark:border-emerald-900 bg-emerald-50/50 dark:bg-emerald-950/20'
            "
          >
            <h3
              class="font-bold flex items-center gap-1"
              :class="isDossierUnverifiedOrResearch ? 'text-amber-800 dark:text-amber-300' : 'text-emerald-800 dark:text-emerald-300'"
            >
              <AlertTriangle v-if="isDossierUnverifiedOrResearch" class="w-3.5 h-3.5" />
              <CheckCircle2 v-else class="w-3.5 h-3.5" />
              <span>{{ isDossierUnverifiedOrResearch ? t('待核实线索 / 调研声称', 'Unverified Leads / Research Claims') : t('新增实质事实', 'New Material Facts') }}</span>
            </h3>
            <ul class="space-y-1 text-slate-700 dark:text-slate-200">
              <li v-for="(f, i) in cleanedNewFacts" :key="i">• {{ f }}</li>
              <li v-if="cleanedNewFacts.length === 0" class="text-slate-500">
                {{ t('本批次暂无实质增量句子。', 'No new material sentences in this batch.') }}
              </li>
            </ul>
          </div>

          <div class="rounded-xl border border-amber-200 dark:border-amber-900 bg-amber-50/60 dark:bg-amber-950/20 p-3.5 space-y-1.5">
            <h3 class="font-bold text-amber-800 dark:text-amber-300 flex items-center gap-1">
              <AlertTriangle class="w-3.5 h-3.5" />
              <span>{{ t('修订 / 交叉矛盾', 'Corrections & Conflicts') }}</span>
            </h3>
            <ul class="space-y-1 text-slate-700 dark:text-slate-200">
              <li v-for="(c, i) in cleanedCorrections" :key="i">• {{ c }}</li>
              <li v-if="cleanedCorrections.length === 0" class="text-slate-500">
                {{ t('暂无交叉矛盾或口径修正。', 'No cross-source contradictions or revisions.') }}
              </li>
            </ul>
          </div>

          <div class="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/40 p-3.5 space-y-1.5">
            <h3 class="font-bold text-slate-700 dark:text-slate-300 flex items-center gap-1">
              <Layers class="w-3.5 h-3.5" />
              <span>{{ t('未变背景与下个节点', 'Background & Next Catalyst') }}</span>
            </h3>
            <p class="text-slate-600 dark:text-slate-300">
              <strong>{{ t('未变背景：', 'Background: ') }}</strong>{{ cleanedUnchanged.join('；') || t('首次建立档案', 'Initial dossier created') }}
            </p>
            <p class="text-blue-700 dark:text-blue-300">
              <strong>{{ t('下个验证节点：', 'Next Catalyst: ') }}</strong>{{ cleanZhText(activeDossier.next_catalyst) || t('待补充公开披露日期', 'Pending public disclosure') }}
            </p>
          </div>
        </div>

        <!-- 2. Structured Key Facts Table -->
        <div v-if="activeDossier.fact_atoms.length > 0" class="space-y-2">
          <h3 class="text-sm font-bold text-slate-900 dark:text-white">
            {{ t('核心事实与数据要点', 'Key Facts & Figures') }}
          </h3>
          <div class="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
            <table class="w-full text-left text-xs border-collapse">
              <thead class="bg-slate-50 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
                <tr>
                  <th class="px-3 py-2 font-semibold">{{ t('主体', 'Subject') }}</th>
                  <th class="px-3 py-2 font-semibold">{{ t('事件/指标', 'Metric / Action') }}</th>
                  <th class="px-3 py-2 font-semibold">{{ t('口径与周期', 'Scope & Period') }}</th>
                  <th class="px-3 py-2 font-semibold">{{ t('证据状态 & 出处', 'Attribution & Source') }}</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-100 dark:divide-slate-800">
                <tr v-for="atom in activeDossier.fact_atoms" :key="atom.atom_id">
                  <td class="px-3 py-2 font-medium text-slate-900 dark:text-white">{{ atom.subject }}</td>
                  <td class="px-3 py-2 text-slate-700 dark:text-slate-200">
                    {{ atom.metric_or_action }}
                    <span v-if="atom.value" class="ml-1 font-semibold text-blue-700 dark:text-blue-300">({{ atom.value }} {{ atom.unit || '' }})</span>
                  </td>
                  <td class="px-3 py-2 text-slate-500">{{ atom.scope }} · {{ atom.period }}</td>
                  <td class="px-3 py-2">
                    <span class="text-slate-700 dark:text-slate-300">{{ atom.attribution }}</span>
                    <a
                      v-if="normalizeExternalUrl(atom.source_url)"
                      :href="normalizeExternalUrl(atom.source_url)!"
                      target="_blank"
                      rel="noopener noreferrer"
                      @click.stop
                      class="ml-1.5 text-blue-600 hover:underline inline-flex items-center gap-0.5"
                    >
                      {{ t('原文', 'Source') }} <ExternalLink class="w-3 h-3" />
                    </a>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- 3. 5-Stage Research Card -->
        <div v-if="activeDossier.investment_card" class="rounded-xl border border-blue-200 dark:border-blue-900/70 bg-blue-50/40 dark:bg-blue-950/20 p-4 space-y-2.5">
          <h3 class="text-sm font-bold text-slate-900 dark:text-white">
            {{ t('五段式投研传导链（事实变化 → 经营变量 → 产业链 → 相关资产 → 验证节点）', '5-Stage Investment Chain (Fact → Variables → Supply Chain → Assets → Catalysts)') }}
          </h3>
          <div class="grid gap-2.5 text-xs" :class="investmentStageGridClass">
            <div class="bg-white dark:bg-slate-900 rounded-lg p-3 border border-emerald-200/80 dark:border-emerald-900/70">
              <div class="font-semibold text-emerald-700 dark:text-emerald-300 mb-1">{{ t('① 事实变化', '1. Fact Change') }}</div>
              <p class="text-slate-800 dark:text-slate-200 leading-relaxed line-clamp-4">
                {{ cleanedNewFacts[0] || cleanZhText(activeDossier.investment_card.fact_change) || activeDossier.title }}
              </p>
            </div>
            <div v-if="cleanedOpVars.length > 0" class="bg-white dark:bg-slate-900 rounded-lg p-3 border border-slate-200/80 dark:border-slate-800">
              <div class="font-semibold text-slate-500 mb-1">{{ t('② 经营变量', '2. Operating Vars') }}</div>
              <ul class="space-y-0.5 text-slate-800 dark:text-slate-200">
                <li v-for="v in cleanedOpVars" :key="v">• {{ v }}</li>
              </ul>
            </div>
            <div v-if="hasSupplyChain" class="bg-white dark:bg-slate-900 rounded-lg p-3 border border-slate-200/80 dark:border-slate-800">
              <div class="font-semibold text-slate-500 mb-1">{{ t('③ 产业链关系', '3. Supply Chain') }}</div>
              <p class="text-slate-700 dark:text-slate-300"><strong>{{ t('上游：', 'Upstream: ') }}</strong>{{ activeDossier.investment_card.supply_chain_links.upstream.join('、') || '-' }}</p>
              <p class="text-slate-700 dark:text-slate-300 mt-1"><strong>{{ t('下游：', 'Downstream: ') }}</strong>{{ activeDossier.investment_card.supply_chain_links.downstream.join('、') || '-' }}</p>
            </div>
            <div v-if="relatedAssetsList.length > 0" class="bg-white dark:bg-slate-900 rounded-lg p-3 border border-slate-200/80 dark:border-slate-800">
              <div class="font-semibold text-slate-500 mb-1">{{ t('④ 关联证券实体', '4. Related Assets') }}</div>
              <ul class="space-y-0.5 text-slate-800 dark:text-slate-200">
                <li v-for="a in relatedAssetsList" :key="a.ticker">{{ a.entity }} ({{ a.ticker }})</li>
              </ul>
            </div>
            <div v-if="cleanedValidationNodes.length > 0" class="bg-white dark:bg-slate-900 rounded-lg p-3 border border-slate-200/80 dark:border-slate-800">
              <div class="font-semibold text-slate-500 mb-1">{{ t('⑤ 验证节点', '5. Validation Nodes') }}</div>
              <ul class="space-y-0.5 text-blue-700 dark:text-blue-300">
                <li v-for="n in cleanedValidationNodes" :key="n">• {{ n }}</li>
              </ul>
            </div>
          </div>
          <p class="text-[11px] text-slate-500 dark:text-slate-400">
            {{ t('研究说明：', 'Research Note: ') }}{{
              String(activeDossier.investment_card.market_data_disclosure || '').includes('静态版本')
                ? t('本档案聚焦可溯源的公开监管文件（SEC/交易所披露）与多源交叉印证事实，客观呈现产业链传导脉络，不构成具体买卖建议。', 'This dossier focuses on traceable regulatory filings and multi-source verified facts along supply chains and is not investment advice.')
                : cleanZhText(activeDossier.investment_card.market_data_disclosure)
            }}
          </p>
        </div>

        <!-- 3.5 Multi-Side Stance Comparison (if enriched) -->
        <div
          v-if="(activeDossier.stance_comparison || []).length > 0"
          class="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-800/40 p-3.5 space-y-2 text-xs"
          data-testid="storyline-stance-comparison"
        >
          <h3 class="text-sm font-bold text-slate-900 dark:text-white">
            {{ t('多方立场与事实对照', 'Multi-Side Stance Comparison') }}
          </h3>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
            <div
              v-for="(sc, idx) in activeDossier.stance_comparison"
              :key="`sc-${idx}`"
              class="rounded-lg bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-700/80 p-2.5 space-y-1"
            >
              <div class="font-bold text-slate-900 dark:text-white">{{ sc.side || (sc as any).party }}</div>
              <p class="text-slate-600 dark:text-slate-300 leading-relaxed">{{ sc.summary || [(sc as any).stance, (sc as any).impact].filter(Boolean).join(' · ') }}</p>
              <div v-if="(sc.key_sources || []).length > 0" class="text-[10.5px] text-slate-400">
                {{ t('主要依据：', 'Sources: ') }}{{ sc.key_sources!.join(' · ') }}
              </div>
            </div>
          </div>
        </div>

        <!-- 4. Multi-batch Evolution Timeline -->
        <div class="space-y-2">
          <h3 class="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-1.5">
            <Clock class="w-4 h-4 text-violet-600" />
            <span>{{ t(`跨批次演化时间线 (${activeDossier.timeline.length} 个节点)`, `Multi-Batch Timeline (${activeDossier.timeline.length} nodes)`) }}</span>
          </h3>
          <ol class="border-l-2 border-slate-200 dark:border-slate-700 ml-2 pl-4 space-y-3">
            <li v-for="node in activeDossier.timeline" :key="`${node.batch_id}-${node.event_id}`" class="space-y-1 text-xs">
              <div class="flex flex-wrap items-center gap-2 text-slate-500 tabular-nums">
                <span class="font-semibold text-slate-800 dark:text-slate-200">
                  <SmartTime
                    v-if="node.timestamp || node.fetched_at"
                    :iso="node.timestamp || node.fetched_at"
                    :now-ms="effectiveNowMs"
                  />
                  <template v-else>{{ t('历史节点', 'Milestone') }}</template>
                </span>
                <span class="text-violet-700 dark:text-violet-300 font-medium">{{ node.delta_note }}</span>
              </div>
              <p class="text-sm font-medium text-slate-900 dark:text-white">{{ pickBiText(node.title, node.title_en) }}</p>
              <div class="flex flex-wrap gap-2">
                <template v-for="(s, sidx) in node.sources_preview" :key="sidx">
                  <a
                    v-if="normalizeExternalUrl(s.url)"
                    :href="normalizeExternalUrl(s.url)!"
                    target="_blank"
                    rel="noopener noreferrer"
                    @click.stop
                    class="text-blue-600 dark:text-blue-400 hover:underline inline-flex items-center gap-0.5"
                  >
                    {{ translateSourceName(s.source_name, node.title) }} <ExternalLink class="w-3 h-3" />
                  </a>
                  <span v-else class="text-slate-400 text-xs">
                    {{ translateSourceName(s.source_name, node.title) }}（{{ t('暂无直链', 'No Link') }}）
                  </span>
                </template>
              </div>
            </li>
          </ol>
        </div>
      </article>
    </div>

    <!-- Master Index List when no storyline selected -->
    <div v-else class="space-y-3">
      <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 space-y-3 shadow-xs">
        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <div>
            <h2 class="text-base sm:text-lg font-bold text-zinc-900 dark:text-white flex items-center gap-2">
              <GitBranch class="w-4 h-4 text-[#007AFF]" :stroke-width="1.5" />
              <span>
                {{
                  loading && Object.keys(storylines).length === 0
                    ? t('事件追踪', 'Tracking')
                    : t(`事件追踪 (${Object.keys(storylines).length})`, `Tracking (${Object.keys(storylines).length})`)
                }}
              </span>
            </h2>
          </div>
          <div class="flex flex-wrap items-center gap-2 w-full sm:w-auto">
            <div class="relative flex-1 sm:w-56">
              <Search class="w-3.5 h-3.5 text-zinc-400 pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2" />
              <input
                v-model="localQuery"
                type="search"
                :placeholder="t('搜追踪事件、实体…', 'Search storylines, entities…')"
                class="w-full h-9 pl-8 pr-7 rounded-xl bg-[#F5F5F7] dark:bg-[#2C2C2E] text-xs text-zinc-900 dark:text-white placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-[#007AFF]/40"
              />
              <button
                v-if="localQuery"
                type="button"
                @click="localQuery = ''"
                class="absolute right-1.5 top-1/2 -translate-y-1/2 w-6 h-6 inline-flex items-center justify-center rounded-md text-zinc-400 hover:text-zinc-700 dark:hover:text-white"
                :aria-label="t('清空搜索', 'Clear search')"
              >
                <X class="w-3.5 h-3.5" />
              </button>
            </div>
            <span
              v-if="effectiveQuery"
              class="inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-blue-50 dark:bg-blue-950/50 border border-blue-200 dark:border-blue-800 text-[11px] text-blue-700 dark:text-blue-300 tabular-nums shrink-0"
            >
              <span>{{ t(`命中 ${storylineList.length} 条`, `${storylineList.length} hits`) }}</span>
            </span>
          </div>
        </div>

        <div class="flex flex-col sm:flex-row sm:flex-wrap sm:items-center gap-2">
          <div class="relative inline-flex items-center self-start sm:self-auto shrink-0 h-9 pl-3 pr-7 rounded-xl bg-[#F5F5F7] dark:bg-[#2C2C2E] text-xs text-zinc-700 dark:text-zinc-200 focus-within:ring-2 focus-within:ring-[#007AFF]/40">
            <span class="pointer-events-none whitespace-nowrap">
              {{
                sortBy === 'latest'
                  ? t('排序：最新动态', 'Sort: Latest')
                  : sortBy === 'credibility'
                    ? t('排序：可信度最高', 'Sort: Credibility')
                    : t('排序：关注词相关', 'Sort: Watchlist')
              }}
            </span>
            <ChevronDown class="w-3.5 h-3.5 text-zinc-400 pointer-events-none absolute right-2" />
            <select
              v-model="sortBy"
              :aria-label="t('事件排序', 'Sort storylines')"
              class="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
            >
              <option value="latest">{{ t('排序：最新动态', 'Sort: Latest') }}</option>
              <option value="credibility">{{ t('排序：可信度最高', 'Sort: Credibility') }}</option>
              <option value="relevance">{{ t('排序：关注词相关', 'Sort: Watchlist') }}</option>
            </select>
          </div>
          <div class="flex sm:flex-wrap items-center gap-1.5 overflow-x-auto no-scrollbar scroll-fade-x sm:overflow-visible pb-0.5 sm:pb-0">
            <button
              type="button"
              @click="(e) => { filterCat = 'all'; centerPillIntoView(e) }"
              class="mobile-pressable min-h-[38px] sm:min-h-[30px] px-3 sm:px-2.5 rounded-xl sm:rounded-lg text-xs border font-medium whitespace-nowrap shrink-0"
              :class="filterCat === 'all' ? 'bg-slate-900 text-white border-slate-900 dark:bg-blue-600 dark:border-blue-600' : 'bg-white text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700'"
            >
              {{ t('全部板块', 'All Domains') }}
            </button>
            <button
              v-for="cat in CATEGORIES"
              :key="cat.id"
              type="button"
              @click="(e) => { filterCat = cat.id; centerPillIntoView(e) }"
              class="mobile-pressable min-h-[38px] sm:min-h-[30px] px-3 sm:px-2.5 rounded-xl sm:rounded-lg text-xs border font-medium whitespace-nowrap shrink-0"
              :class="filterCat === cat.id ? 'bg-slate-900 text-white border-slate-900 dark:bg-blue-600 dark:border-blue-600' : 'bg-white text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700'"
            >
              {{ t(cat.shortName, cat.shortNameEn) }}
            </button>
          </div>
        </div>
      </div>

      <LoadingSkeleton v-if="loading && Object.keys(storylines).length === 0" variant="grid" :count="6" />

      <EmptySearchState
        v-else-if="storylineList.length === 0"
        :query="props.searchQuery"
        :has-extra-filters="filterCat !== 'all'"
        @clear-query="emit('clear-search')"
        @clear-filters-only="filterCat = 'all'"
        @reset="resetAllFilters"
      />

      <div v-else class="space-y-3">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
          <article
            v-for="st in pagedStorylines.visible"
            :key="st.storyline_id"
          class="mobile-pressable rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 flex flex-col justify-between gap-3 hover:border-violet-400 dark:hover:border-violet-600 transition-colors"
        >
          <div class="space-y-2">
            <div class="flex flex-wrap items-center justify-between gap-1.5 text-[11px]">
              <span class="px-2 py-0.5 rounded bg-violet-50 text-violet-800 border border-violet-200 dark:bg-violet-950/60 dark:text-violet-200 dark:border-violet-800 font-medium">
                {{ st.current_stage }}
              </span>
              <span class="text-slate-500 tabular-nums">
                {{ t(`时间线 ${st.timeline.length} 节点 · ${st.sources.length} 出处`, `${st.timeline.length} timeline · ${st.sources.length} sources`) }}
              </span>
            </div>
            <h3 class="text-sm sm:text-base font-bold text-slate-900 dark:text-white leading-snug">
              {{ pickBiText(st.title_zh || st.title, st.title_en || st.title) }}
            </h3>
            <p class="text-xs text-slate-600 dark:text-slate-300 line-clamp-2">
              <span v-if="getDossierFallbackPreview(st).untranslated" lang="en">{{ getDossierFallbackPreview(st).text }}</span>
              <template v-else>
                {{ getDossierFallbackPreview(st).text }}
              </template>
            </p>
            <div v-if="dossierEntities(st).length > 0" class="flex flex-wrap gap-1.5">
              <button
                v-for="ent in dossierEntities(st).slice(0, 4)"
                :key="ent.name"
                type="button"
                @click="emit('select-entity', ent.name)"
                :title="ent.confidence != null ? `${t('置信度', 'Confidence')}: ${Math.round(ent.confidence * 100)}%` : undefined"
                class="min-h-[34px] sm:min-h-[24px] px-3 sm:px-2.5 rounded-full text-[11px] bg-slate-100 hover:bg-blue-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300"
              >
                # {{ translateEntityName(ent.name) }}
              </button>
            </div>
          </div>

          <div class="pt-2 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between gap-2 text-xs">
            <span class="text-slate-500 truncate max-w-[56%]" :title="st.next_catalyst || ''">
              {{ t('下个节点：', 'Next: ') }}{{ cleanZhText(st.next_catalyst) || t('待补充公开披露日期', 'Pending') }}
            </span>
            <button
              type="button"
              @click="emit('select-storyline', st.storyline_id)"
              class="px-3.5 min-h-[38px] sm:min-h-[30px] rounded-xl sm:rounded-lg bg-violet-600 text-white font-semibold hover:bg-violet-700 shrink-0"
            >
              {{ t('进入事件档案 →', 'Open Dossier →') }}
            </button>
          </div>
        </article>
        </div>
        <div v-if="pagedStorylines.hasMore" class="pt-1 text-center">
          <button
            type="button"
            @click="visibleLimit += DEFAULT_PAGE_SIZE"
            class="min-h-[42px] px-5 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-xs font-semibold text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800"
          >
            {{ t(`加载更多事件（剩余 ${pagedStorylines.remaining} 条）`, `Load More (${pagedStorylines.remaining} remaining)`) }}
          </button>
        </div>
      </div>
    </div>
  </section>
</template>
