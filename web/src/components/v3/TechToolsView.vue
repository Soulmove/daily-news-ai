<script setup lang="ts">
import { computed, ref } from 'vue'
import { Bookmark, Cpu, Download, ExternalLink, Search, Star, Terminal } from 'lucide-vue-next'
import EmptySearchState from '../EmptySearchState.vue'
import SmartTime from '../SmartTime.vue'
import { stripMarkdownArtifacts, t, truncateAtSentence } from '../../core/i18n'
import { normalizeExternalUrl } from '../../core/legacyAdapter'
import { matchesSmartQuery } from '../../core/search'
import type { LocalToolState } from '../../core/storage'
import type { TechToolEntry } from '../../core/types'

const RAW_COMMIT_NOISE_RE =
  /^(?:What's Changed|Highlights|TL;DR|Bug Fixes|Release Notes|New Features|Full Changelog|Website|Attestations|Checksums|Backwards Incompatible Changes|Deprecations|Features|New models|Model\s*·\s*Type.*|(?:v\d+(?:\.\d+)*\s*[：:]\s*)?\d[\d,]*\s+(?:commits?|PRs?)\s+from.*|.*\bby\s+@\S+\s+in\s+https?:\/\/\S*|(?:sycl|cuda|metal|vulkan|rpc|ggml|model|feat|fix|chore|refactor|ci|docs|test|api|llm|cmd)\b[^:：]{0,20}[:：]\s*.*|[A-Za-z][A-Za-z0-9 _/-]{1,24}\s*[:：]\s*$|\S+\s+https?:\/\/github\.com\/.*|\.{0,3}?\s*\(#?\d{3,6}\))$/i

function isHfWeightTool(tool: TechToolEntry): boolean {
  const id = (tool.tool_id || '').toLowerCase()
  const src = (tool.source_name || '').toLowerCase()
  const url = (tool.official_url || '').toLowerCase()
  return id.startsWith('tool_hf_') || src.includes('hugging face') || url.includes('huggingface.co/')
}

function extractParamBadge(tool: TechToolEntry): string | null {
  const hay = `${tool.name || ''} ${tool.repo || ''}`
  const m = hay.match(/(?:^|[-_/ ])(\d+(?:\.\d+)?[BM](?:-[A-Z]\d+(?:\.\d+)?[BM])?)(?=$|[-_/ ])/i)
  return m ? m[1].toUpperCase() : null
}

function formatDownloadsLabel(tool: TechToolEntry): string | null {
  const dl = Number((tool as unknown as { downloads?: number | null }).downloads || 0)
  if (dl >= 10000) return t(`${(dl / 10000).toFixed(1)} 万下载`, `${(dl / 1000).toFixed(0)}k DLs`)
  if (dl > 0) return t(`${dl} 下载`, `${dl} DLs`)
  const m = String(tool.summary || '').match(/近期下载\s*([\d.]+\s*万次?|\d+\s*次?)/)
  return m ? `${m[1].replace(/次$/, '')}下载` : null
}

function formatLicenseLabel(tool: TechToolEntry): string | null {
  const lic = String(tool.license || '').trim()
  if (!lic || lic.toUpperCase() === 'NOASSERTION') return null
  if (lic.includes('多许可证')) return t('多许可证', 'Multi-License')
  return lic.toLowerCase() === 'apache-2.0' ? 'Apache-2.0' : lic.toLowerCase() === 'mit' ? 'MIT' : lic
}

function getDistinctToolLinks(tool: TechToolEntry): { href: string; label: string }[] {
  const candidates: { href?: string | null; label: string }[] = isHfWeightTool(tool)
    ? [
        { href: tool.official_url, label: t('模型主页 / 权重卡', 'Model Card') },
        { href: tool.release_url, label: t('发布版本', 'Release') },
        { href: tool.docs_url, label: t('文档', 'Docs') },
      ]
    : [
        { href: tool.official_url, label: t('仓库主页', 'Repo') },
        { href: tool.release_url, label: t('发布说明', 'Release Notes') },
        { href: tool.docs_url, label: t('文档', 'Docs') },
      ]
  const seen = new Set<string>()
  const out: { href: string; label: string }[] = []
  for (const item of candidates) {
    const safeUrl = normalizeExternalUrl(item.href)
    if (!safeUrl) continue
    const norm = safeUrl.replace(/#readme$/i, '').replace(/\/+$/, '').toLowerCase()
    if (seen.has(norm)) continue
    seen.add(norm)
    out.push({ href: safeUrl, label: item.label })
  }
  return out
}

function isReadableToolSegment(seg: string): boolean {
  if (!seg || seg.length < 6) return false
  if (RAW_COMMIT_NOISE_RE.test(seg)) return false
  if (/\(#?\d{3,6}\)\s*$/.test(seg) && /^(?:sycl|cuda|metal|model|feat|fix|chore|api|eval|ggml|llm|cmd)\b/i.test(seg)) return false
  if (/github\.com\/\S+\/(?:pull|commit|compare)\//i.test(seg)) return false
  if (/\d[\d,]*\s+(?:commits?|PRs?|contributors?)\b/i.test(seg)) return false
  return true
}

function formatToolSummary(raw: string | null | undefined): string {
  let clean = stripMarkdownArtifacts(raw)
    .replace(/^Hugging Face\s*官方模型卡\s*（([^）]*)）[。.\s]*/i, '$1')
    .replace(/^Hugging Face\s*官方模型卡[^：:]*[：:]\s*/i, '')
    .replace(/(?:（|\()\s*近期下载\s*[\d.]+\s*万?次?\s*(?:）|\))/g, '')
    .replace(/(?:Website|Attestations|Full Changelog|Checksums)\s*[:：]\s*(?=[；;\n]|$)/gi, '')
    .replace(/^[；;:：\s]+/, '')
    .trim()
  if ((clean.match(/）/g) || []).length > (clean.match(/（/g) || []).length) {
    clean = clean.replace(/[）。.]+$/, '').trim()
  }
  return clean
}

function getToolSummarySegments(raw: string | null | undefined): string[] {
  const clean = formatToolSummary(raw)
  if (!clean) return []
  return clean
    .split(/[；\n]+/)
    .map((s) => s.replace(/^[；;:：\s]+/, '').trim())
    .filter(isReadableToolSegment)
    .map((s) => truncateAtSentence(s, 96))
    .slice(0, 3)
}

function formatStarsLabel(stars: number | null | undefined): string | null {
  const n = Number(stars || 0)
  if (!Number.isFinite(n) || n <= 0) return null
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}

function cleanPricingLabel(raw: string | null | undefined): string {
  const s = String(raw || '').trim()
  if (!s || s.includes('受限于对应开源许可证')) return t('开源免费', 'Open Source')
  return s
}

const props = defineProps<{
  tools: TechToolEntry[]
  toolStates: Record<string, LocalToolState>
  globalSearchQuery?: string
  nowMs?: number
}>()

const emit = defineEmits<{
  (e: 'update-tool-state', payload: { toolId: string; wantTry: boolean; note: string }): void
  (e: 'clear-search'): void
}>()

const categoryTab = ref<'all' | 'sdk' | 'weights'>('all')
const stageFilter = ref<'all' | 'ga' | 'beta' | 'waitlist' | 'announced'>('all')
const sortBy = ref<'stars' | 'recent'>('stars')
const onlyWantTry = ref(false)
const editingNoteId = ref<string | null>(null)
const draftNote = ref('')
const effectiveNowMs = computed(() => props.nowMs ?? Date.now())

const STAGE_STYLES: Record<string, string> = {
  ga: 'bg-emerald-500/12 text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-300',
  beta: 'bg-[#007AFF]/12 text-[#007AFF] dark:bg-[#0A84FF]/15 dark:text-[#0A84FF]',
  waitlist: 'bg-amber-500/12 text-amber-700 dark:bg-amber-400/15 dark:text-amber-300',
  announced: 'bg-zinc-500/12 text-zinc-700 dark:bg-zinc-400/15 dark:text-zinc-300',
}

function shortStageLabel(tool: TechToolEntry): string {
  if (tool.availability_stage === 'ga') {
    return isHfWeightTool(tool) ? t('开源 GA', 'Open GA') : t('正式可用', 'GA')
  }
  return tool.availability_label
}

const categoryCounts = computed(() => {
  const sdk = props.tools.filter((x) => !isHfWeightTool(x)).length
  const weights = props.tools.filter((x) => isHfWeightTool(x)).length
  return { all: props.tools.length, sdk, weights }
})

const filteredTools = computed(() => {
  const globalQ = (props.globalSearchQuery || '').trim().toLowerCase()
  const list = props.tools.filter((tool) => {
    if (categoryTab.value === 'sdk' && isHfWeightTool(tool)) return false
    if (categoryTab.value === 'weights' && !isHfWeightTool(tool)) return false
    if (stageFilter.value !== 'all' && tool.availability_stage !== stageFilter.value) return false
    if (onlyWantTry.value && !props.toolStates[tool.tool_id]?.wantTry) return false
    if (globalQ) {
      const hay = `${tool.name} ${tool.repo || ''} ${tool.tool_type} ${tool.summary} ${tool.license || ''} ${tool.pain_point || ''} ${tool.comparison_note || ''}`
      if (!matchesSmartQuery(hay, globalQ)) return false
    }
    return true
  })
  return [...list].sort((a, b) => {
    if (sortBy.value === 'stars') {
      const sa = Number(a.stars || 0)
      const sb = Number(b.stars || 0)
      if (sa !== sb) return sb - sa
    }
    const ta = String(a.version_published_at || a.checked_at || '')
    const tb = String(b.version_published_at || b.checked_at || '')
    return tb.localeCompare(ta)
  })
})

const tryBurstId = ref<string | null>(null)
let tryBurstTimer: ReturnType<typeof setTimeout> | null = null

function toggleWantTry(tool: TechToolEntry) {
  const cur = props.toolStates[tool.tool_id]
  tryBurstId.value = tool.tool_id
  if (tryBurstTimer) clearTimeout(tryBurstTimer)
  tryBurstTimer = setTimeout(() => {
    tryBurstId.value = null
  }, 500)
  emit('update-tool-state', {
    toolId: tool.tool_id,
    wantTry: !cur?.wantTry,
    note: cur?.note || '',
  })
}

function startNote(tool: TechToolEntry) {
  editingNoteId.value = tool.tool_id
  draftNote.value = props.toolStates[tool.tool_id]?.note || ''
}

function saveNote(tool: TechToolEntry) {
  const cur = props.toolStates[tool.tool_id]
  emit('update-tool-state', {
    toolId: tool.tool_id,
    wantTry: cur?.wantTry ?? true,
    note: draftNote.value.trim(),
  })
  editingNoteId.value = null
}

function resetLocalFilters() {
  categoryTab.value = 'all'
  stageFilter.value = 'all'
  onlyWantTry.value = false
}
</script>

<template>
  <section class="space-y-4" :aria-label="t('AI 模型、API 与开源工具库', 'AI Models, APIs & Open-Source Tools')">
    <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 sm:p-5 space-y-3 shadow-xs">
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2.5">
        <div class="flex flex-wrap items-center gap-3">
          <h2 class="text-base sm:text-lg font-bold text-zinc-900 dark:text-white flex items-center gap-2">
            <Cpu class="w-4 h-4 text-[#007AFF]" :stroke-width="1.5" />
            <span>{{ t(`开源工具与模型权重库 (${filteredTools.length})`, `AI Tools & Open Weights (${filteredTools.length})`) }}</span>
          </h2>

          <!-- Category Tabs: All / Frameworks & Agent SDK / Open Weights (wraps cleanly inside narrow 360-393px cards) -->
          <div class="ios-segmented flex flex-wrap max-w-full gap-1 text-[11.5px] sm:text-xs">
            <button
              type="button"
              @click="categoryTab = 'all'"
              class="ios-segmented-btn min-h-[30px] px-2 sm:px-2.5 whitespace-nowrap"
              :class="categoryTab === 'all' ? 'ios-segmented-btn-active' : 'text-zinc-600 dark:text-zinc-400'"
            >
              {{ t(`全部 (${categoryCounts.all})`, `All (${categoryCounts.all})`) }}
            </button>
            <button
              type="button"
              @click="categoryTab = 'sdk'"
              class="ios-segmented-btn min-h-[30px] px-2 sm:px-2.5 whitespace-nowrap"
              :class="categoryTab === 'sdk' ? 'ios-segmented-btn-active' : 'text-zinc-600 dark:text-zinc-400'"
            >
              {{ t(`框架与 Agent SDK (${categoryCounts.sdk})`, `Frameworks & SDKs (${categoryCounts.sdk})`) }}
            </button>
            <button
              type="button"
              @click="categoryTab = 'weights'"
              class="ios-segmented-btn min-h-[30px] px-2 sm:px-2.5 whitespace-nowrap"
              :class="categoryTab === 'weights' ? 'ios-segmented-btn-active' : 'text-zinc-600 dark:text-zinc-400'"
            >
              {{ t(`开源模型权重 (${categoryCounts.weights})`, `Open Weights (${categoryCounts.weights})`) }}
            </button>
          </div>
        </div>

        <span
          v-if="props.globalSearchQuery?.trim()"
          class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-blue-50 dark:bg-blue-950/50 border border-blue-200 dark:border-blue-800 text-xs text-blue-700 dark:text-blue-300"
        >
          <Search class="w-3.5 h-3.5" />
          <span>{{ t(`顶部搜索过滤中：「${props.globalSearchQuery}」`, `Search filter: "${props.globalSearchQuery}"`) }}</span>
        </span>
      </div>

      <div class="flex flex-col sm:flex-row sm:flex-wrap sm:items-center sm:justify-between gap-2 text-xs pt-1">
        <div class="flex flex-wrap gap-1.5">
          <button type="button" @click="stageFilter = 'all'" class="min-h-[32px] px-2.5 rounded-lg border font-medium whitespace-nowrap text-[12px]" :class="stageFilter === 'all' ? 'bg-slate-900 text-white border-slate-900 dark:bg-blue-600 dark:border-blue-600' : 'bg-white text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700'">
            {{ t('全部阶段', 'All Stages') }}
          </button>
          <button type="button" @click="stageFilter = 'ga'" class="min-h-[32px] px-2.5 rounded-lg border font-medium whitespace-nowrap text-[12px]" :class="stageFilter === 'ga' ? 'bg-emerald-600 text-white border-emerald-600' : 'bg-white text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700'">
            {{ t('正式可用 GA', 'GA Available') }}
          </button>
          <button type="button" @click="stageFilter = 'beta'" class="min-h-[32px] px-2.5 rounded-lg border font-medium whitespace-nowrap text-[12px]" :class="stageFilter === 'beta' ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700'">
            {{ t('测试/预览 Beta', 'Beta / Preview') }}
          </button>
          <button type="button" @click="stageFilter = 'announced'" class="min-h-[32px] px-2.5 rounded-lg border font-medium whitespace-nowrap text-[12px]" :class="stageFilter === 'announced' ? 'bg-slate-700 text-white border-slate-700' : 'bg-white text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700'">
            {{ t('仅宣布待开源', 'Announced') }}
          </button>
        </div>

        <div class="flex flex-wrap items-center gap-3">
          <div class="ios-segmented inline-flex text-[11px]">
            <button
              type="button"
              @click="sortBy = 'stars'"
              class="ios-segmented-btn min-h-[28px] px-2.5 inline-flex items-center gap-1 whitespace-nowrap"
              :class="sortBy === 'stars' ? 'ios-segmented-btn-active' : 'text-zinc-600 dark:text-zinc-400'"
            >
              <Star class="w-3 h-3" :stroke-width="1.75" />
              <span>{{ t('按星标最高', 'Top Stars') }}</span>
            </button>
            <button
              type="button"
              @click="sortBy = 'recent'"
              class="ios-segmented-btn min-h-[28px] px-2.5 whitespace-nowrap"
              :class="sortBy === 'recent' ? 'ios-segmented-btn-active' : 'text-zinc-600 dark:text-zinc-400'"
            >
              {{ t('按最新更新', 'Most Recent') }}
            </button>
          </div>
          <label class="inline-flex items-center gap-1.5 min-h-[32px] cursor-pointer text-slate-600 dark:text-slate-300">
            <input v-model="onlyWantTry" type="checkbox" class="rounded border-slate-300 text-blue-600" />
            <span>{{ t('仅看「准备试用」清单', 'Want to Try Only') }}</span>
          </label>
        </div>
      </div>
    </div>

    <EmptySearchState
      v-if="filteredTools.length === 0"
      :query="props.globalSearchQuery"
      :has-extra-filters="categoryTab !== 'all' || stageFilter !== 'all' || onlyWantTry"
      @clear-query="emit('clear-search')"
      @clear-filters-only="resetLocalFilters"
      @reset="resetLocalFilters(); emit('clear-search')"
    />

    <div v-else class="grid grid-cols-1 md:grid-cols-2 gap-3">
      <article
        v-for="tool in filteredTools"
        :key="tool.tool_id"
        class="ios-card p-4 flex flex-col justify-between gap-2.5 min-w-0"
      >
        <div class="space-y-2 min-w-0">
          <!-- Top Structured Meta Row: Green Stage Badge (whitespace-nowrap) + Param + License + Downloads -->
          <div class="flex flex-wrap items-center justify-between gap-1.5 text-xs">
            <div class="flex flex-wrap items-center gap-1.5 min-w-0">
              <span
                class="px-2 py-0.5 rounded-md font-semibold whitespace-nowrap shrink-0"
                :class="STAGE_STYLES[tool.availability_stage] || STAGE_STYLES.announced"
              >
                {{ shortStageLabel(tool) }}
              </span>
              <span
                v-if="extractParamBadge(tool)"
                class="px-2 py-0.5 rounded-md bg-violet-500/12 text-violet-700 dark:bg-violet-400/15 dark:text-violet-300 text-[11px] font-mono font-semibold whitespace-nowrap shrink-0"
              >
                {{ extractParamBadge(tool) }}
              </span>
              <span
                v-if="formatLicenseLabel(tool)"
                class="px-2 py-0.5 rounded-md bg-[#F2F2F7] dark:bg-[#2C2C2E] text-zinc-700 dark:text-zinc-200 text-[11px] font-medium whitespace-nowrap shrink-0"
              >
                {{ formatLicenseLabel(tool) }}
              </span>
              <span
                v-else
                class="px-2 py-0.5 rounded-md bg-[#F2F2F7] dark:bg-[#2C2C2E] text-zinc-600 dark:text-zinc-300 text-[11px] font-medium whitespace-nowrap shrink-0"
              >
                {{ cleanPricingLabel(tool.pricing_or_cost) }}
              </span>
              <span
                v-if="formatDownloadsLabel(tool)"
                class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-blue-500/10 text-blue-700 dark:text-blue-300 text-[11px] font-medium whitespace-nowrap shrink-0 tabular-nums"
              >
                <Download class="w-3 h-3" />
                {{ formatDownloadsLabel(tool) }}
              </span>
            </div>
            <div class="flex items-center gap-2 shrink-0">
              <span
                v-if="formatStarsLabel(tool.stars)"
                class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-500/12 text-amber-800 dark:bg-amber-400/15 dark:text-amber-200 text-[11px] font-bold font-mono tabular-nums whitespace-nowrap"
                data-testid="tool-stars-badge"
              >
                <Star class="w-3 h-3 fill-amber-400 text-amber-500 shrink-0" :stroke-width="1.75" />
                <span>{{ formatStarsLabel(tool.stars) }}</span>
              </span>
              <span class="text-zinc-400 font-mono text-[11px] tabular-nums whitespace-nowrap">
                <template v-if="tool.latest_version && !String(tool.latest_version).startsWith('更新于')">{{ tool.latest_version }} · </template>
                <SmartTime :iso="tool.version_published_at || tool.checked_at" :now-ms="effectiveNowMs" />
              </span>
            </div>
          </div>

          <div class="flex items-start justify-between gap-2 min-w-0">
            <div class="min-w-0 flex-1">
              <h3 class="text-[16px] font-semibold text-zinc-950 dark:text-white break-words">{{ tool.name }}</h3>
              <p class="text-[12px] text-zinc-500 truncate">
                {{ tool.tool_type }}
                <template v-if="tool.repo && tool.repo !== tool.name"> · {{ tool.repo }}</template>
              </p>
            </div>
            <button
              type="button"
              @click="toggleWantTry(tool)"
              class="jx-pop-target ios-tap inline-flex items-center gap-1 px-3 min-h-[36px] sm:min-h-[32px] rounded-xl text-xs font-semibold shrink-0 transition-colors"
              :class="[
                toolStates[tool.tool_id]?.wantTry
                  ? 'bg-[#007AFF] text-white'
                  : 'bg-[#F2F2F7] text-zinc-700 dark:bg-[#2C2C2E] dark:text-zinc-200',
                tryBurstId === tool.tool_id ? 'jx-burst-ring text-[#007AFF]' : '',
              ]"
            >
              <Bookmark
                class="w-3.5 h-3.5 transition-transform"
                :stroke-width="1.5"
                :class="[{ 'fill-current': toolStates[tool.tool_id]?.wantTry }, tryBurstId === tool.tool_id ? 'jx-pop-active' : '']"
              />
              <span>{{ toolStates[tool.tool_id]?.wantTry ? t('已加入', 'Saved') : t('试用', 'Try') }}</span>
            </button>
          </div>

          <div class="text-[13.5px] text-zinc-600 dark:text-zinc-300 leading-[1.45] space-y-1">
            <ul
              v-if="getToolSummarySegments(tool.summary).length > 0"
              class="list-disc list-inside space-y-0.5"
            >
              <li
                v-for="(seg, idx) in getToolSummarySegments(tool.summary)"
                :key="idx"
                class="line-clamp-2"
              >
                {{ seg }}
              </li>
            </ul>
            <p v-else class="line-clamp-2 text-zinc-500 dark:text-zinc-400">
              {{
                tool.latest_version
                  ? t(`${tool.name} 最新版本已发布，点击下方查看官方模型卡或发布说明。`, `${tool.name} released. See official details below.`)
                  : t('详见官方仓库与发布说明。', 'See official repository and release notes below.')
              }}
            </p>
          </div>

          <div
            v-if="tool.pain_point || tool.best_for || tool.comparison_note"
            class="rounded-xl bg-[#F5F5F7] dark:bg-[#2C2C2E] px-3 py-2 text-[12px] space-y-1 text-zinc-700 dark:text-zinc-200 leading-relaxed"
            data-testid="tool-ai-comparison"
          >
            <p v-if="tool.pain_point">
              <strong class="text-zinc-900 dark:text-white">{{ t('核心痛点：', 'Solves: ') }}</strong>{{ tool.pain_point }}
            </p>
            <p v-if="tool.best_for">
              <strong class="text-zinc-900 dark:text-white">{{ t('最适用：', 'Best For: ') }}</strong>{{ tool.best_for }}
            </p>
            <p v-if="tool.comparison_note" class="text-[#005BBF] dark:text-[#66B2FF]">
              <strong>{{ t('竞品差异：', 'Comparison: ') }}</strong>{{ tool.comparison_note }}
            </p>
          </div>

          <div v-if="toolStates[tool.tool_id]?.note" class="rounded-xl bg-[#F2F2F7] dark:bg-[#2C2C2E] px-2.5 py-1.5 text-xs text-zinc-700 dark:text-zinc-200">
            <Terminal class="w-3 h-3 inline mr-1 text-[#007AFF]" :stroke-width="1.5" />
            {{ toolStates[tool.tool_id].note }}
          </div>

          <div v-if="editingNoteId === tool.tool_id" class="flex gap-1.5 text-xs">
            <input v-model="draftNote" type="text" :placeholder="t('写下兼容性测试/实测反馈...', 'Write compatibility notes...')" class="flex-1 h-10 sm:h-8 px-2.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900" />
            <button type="button" @click="saveNote(tool)" class="px-3 min-h-[38px] sm:min-h-[32px] rounded-lg bg-teal-600 text-white font-semibold">{{ t('存笔记', 'Save') }}</button>
            <button type="button" @click="editingNoteId = null" class="px-2.5 min-h-[38px] sm:min-h-[32px] rounded-lg border border-slate-300 dark:border-slate-600">{{ t('取消', 'Cancel') }}</button>
          </div>
        </div>

        <!-- Deduplicated Distinct Links Footer -->
        <div class="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-100 dark:border-slate-800 text-xs">
          <div class="flex flex-wrap gap-3">
            <a
              v-for="lnk in getDistinctToolLinks(tool)"
              :key="lnk.href"
              :href="lnk.href"
              target="_blank"
              rel="noopener noreferrer"
              @click.stop
              class="min-h-[32px] sm:min-h-[24px] text-blue-600 dark:text-blue-400 hover:underline inline-flex items-center gap-1 whitespace-nowrap"
            >
              <span>{{ lnk.label }}</span>
              <ExternalLink class="w-3 h-3" />
            </a>
            <span v-if="getDistinctToolLinks(tool).length === 0" class="text-[11px] text-slate-400">
              {{ t('暂无官方外链', 'No External Link') }}
            </span>
          </div>
          <button type="button" @click="startNote(tool)" class="min-h-[34px] sm:min-h-[26px] px-2.5 rounded-lg bg-slate-50 sm:bg-transparent dark:bg-slate-800/70 sm:dark:bg-transparent text-slate-600 dark:text-slate-300 hover:text-blue-600 font-medium whitespace-nowrap">
            {{ toolStates[tool.tool_id]?.note ? t('编辑试用备注', 'Edit Note') : t('+ 记录试用备注', '+ Add Note') }}
          </button>
        </div>
      </article>
    </div>
  </section>
</template>
