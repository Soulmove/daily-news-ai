<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { Building2, ExternalLink, FileText, GitBranch, Sparkles, X } from 'lucide-vue-next'
import SmartTime from '../SmartTime.vue'
import { useDialogBehavior } from '../../core/dialog'
import { pickBiText, t, translateEntityName, translateEntityType, translateEvidenceStatus } from '../../core/i18n'
import { normalizeExternalUrl } from '../../core/legacyAdapter'
import type { EntityProfile } from '../../core/types'

const props = defineProps<{
  entity: EntityProfile | null
  nowMs?: number
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'open-storyline', storylineId: string): void
  (e: 'open-qa-entity', entity: EntityProfile): void
}>()

const drawerEl = ref<HTMLElement | null>(null)
const isOpen = computed(() => Boolean(props.entity))
const effectiveNowMs = computed(() => props.nowMs ?? Date.now())

const { onBackdropClick, onCloseButton } = useDialogBehavior({
  isOpen,
  containerRef: drawerEl,
  onClose: () => emit('close'),
})

function onEntityEscape(e: KeyboardEvent) {
  if (e.key === 'Escape' && isOpen.value) {
    e.preventDefault()
    e.stopPropagation()
    emit('close')
  }
}

watch(isOpen, (open) => {
  if (typeof window === 'undefined') return
  if (open) window.addEventListener('keydown', onEntityEscape, true)
  else window.removeEventListener('keydown', onEntityEscape, true)
}, { immediate: true })

onUnmounted(() => {
  if (typeof window !== 'undefined') window.removeEventListener('keydown', onEntityEscape, true)
})
</script>

<template>
  <div
    v-if="entity"
    class="fixed inset-0 z-50 flex justify-end bg-slate-900/50 backdrop-blur-xs"
    role="dialog"
    aria-modal="true"
    aria-labelledby="entity-drawer-title"
    @click.self="onBackdropClick"
  >
    <div
      ref="drawerEl"
      tabindex="-1"
      class="w-full max-w-2xl bg-white dark:bg-slate-900 h-full overflow-y-auto shadow-2xl border-l border-slate-200 dark:border-slate-800 flex flex-col focus:outline-none"
    >
      <header class="sticky top-0 z-10 bg-white/95 dark:bg-slate-900/95 backdrop-blur px-5 py-4 border-b border-slate-200 dark:border-slate-800 flex items-start justify-between gap-3">
        <div class="space-y-1">
          <div class="flex flex-wrap items-center gap-2">
            <Building2 class="w-5 h-5 text-blue-600 dark:text-blue-400 shrink-0" />
            <h2 id="entity-drawer-title" class="text-lg font-bold text-slate-900 dark:text-white">{{ translateEntityName(entity.canonical_name) }}</h2>
            <span class="text-xs px-2 py-0.5 rounded bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300">
              {{ translateEntityType(entity.entity_type) }}
            </span>
          </div>
          <div class="flex flex-wrap items-center gap-1.5 text-xs">
            <span
              v-for="tk in entity.tickers"
              :key="tk.label"
              class="px-2 py-0.5 rounded bg-blue-50 text-blue-800 border border-blue-200 dark:bg-blue-950/60 dark:text-blue-200 dark:border-blue-800 font-mono"
            >
              {{ tk.label }}
            </span>
            <span v-if="entity.cik" class="text-slate-500 font-mono">CIK {{ entity.cik }}</span>
          </div>
        </div>

        <button
          type="button"
          @click="onCloseButton"
          class="w-8 h-8 rounded-lg border border-slate-200 dark:border-slate-700 inline-flex items-center justify-center text-slate-500 hover:text-slate-900 dark:hover:text-white"
          :aria-label="t('关闭实体档案', 'Close entity dossier')"
        >
          <X class="w-4 h-4" />
        </button>
      </header>

      <div class="p-5 space-y-5 text-xs sm:text-sm">
        <div class="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-blue-50/70 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800 px-3.5 py-2.5">
          <div class="text-xs text-blue-900 dark:text-blue-200">
            <strong>{{ t('最近事件数：', 'Recent Events: ') }}</strong>{{ entity.recent_events?.length ?? entity.change_count_30d }}
            <template v-if="entity.recent_filings?.length">
              · <strong>{{ t('监管披露：', 'Filings: ') }}</strong>{{ entity.recent_filings.length }}
            </template>
            · <strong>{{ t('行业：', 'Sector: ') }}</strong>{{ entity.sector || entity.category || entity.entity_type }}
            · <strong>{{ t('档案基调：', 'Basis: ') }}</strong>{{ entity.model_state?.status || (entity.cik ? t('SEC 监管/新闻客观索引', 'SEC Filings & News Index') : t('跨源追踪索引', 'Cross-Source Index')) }}
          </div>
          <button
            type="button"
            @click="emit('open-qa-entity', entity)"
            class="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-blue-600 text-white text-xs font-medium hover:bg-blue-700"
          >
            <Sparkles class="w-3.5 h-3.5" />
            <span>{{ t('基于证据提问', 'Ask Evidence Q&A') }}</span>
          </button>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div class="rounded-xl border border-slate-200 dark:border-slate-800 p-3.5 space-y-1.5">
            <h3 class="text-xs font-bold text-slate-700 dark:text-slate-300">{{ t('核心经营变量', 'Operating Variables') }}</h3>
            <ul class="space-y-1 text-xs text-slate-600 dark:text-slate-300">
              <li v-for="v in entity.operating_variables" :key="v">• {{ v }}</li>
            </ul>
          </div>
          <div class="rounded-xl border border-slate-200 dark:border-slate-800 p-3.5 space-y-1.5">
            <h3 class="text-xs font-bold text-slate-700 dark:text-slate-300">{{ t('验证里程碑与上下游', 'Milestones & Supply Chain') }}</h3>
            <p class="text-xs text-slate-600 dark:text-slate-300">
              <strong>{{ t('上游：', 'Upstream: ') }}</strong>{{ entity.supply_chain_upstream.join('、') || t('无补充', 'None') }}
            </p>
            <p class="text-xs text-slate-600 dark:text-slate-300">
              <strong>{{ t('下游：', 'Downstream: ') }}</strong>{{ entity.supply_chain_downstream.join('、') || t('无补充', 'None') }}
            </p>
            <p class="text-xs text-blue-700 dark:text-blue-300">
              <strong>{{ t('近期节点：', 'Near Milestones: ') }}</strong>{{ entity.validation_milestones.join('；') }}
            </p>
          </div>
        </div>

        <div class="space-y-2">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <h3 class="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-1.5">
              <FileText class="w-4 h-4 text-emerald-600" />
              <span>{{ t('官方历史财务披露 (SEC XBRL CompanyFacts)', 'Official Financial Actuals (SEC XBRL)') }}</span>
            </h3>
            <span
              v-if="entity.financial_actuals.length > 0"
              class="text-[11px] px-2 py-0.5 rounded bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800"
            >
              {{ t('统计币种：', 'Currency: ') }}{{ Array.from(new Set(entity.financial_actuals.map((a) => a.unit || 'N/A'))).join(' / ') }}
            </span>
          </div>
          <div v-if="entity.financial_actuals.length === 0" class="rounded-lg bg-slate-50 dark:bg-slate-800/60 p-3 text-xs text-slate-500">
            {{
              entity.cik
                ? t(`已绑定美股 CIK (${entity.cik})，正等待 XBRL CompanyFacts 数据同步；您可优先核对下方最新一手监管申报原文。`, `SEC CIK (${entity.cik}) bound; awaiting XBRL sync. See direct filings below.`)
                : t('该主体主要在港交所 / A 股或非美国交易所披露（未纳入 SEC EDGAR 10-Q 申报口径），请通过下方 HKEX/巨潮链接核对业绩。', 'Entity primarily files outside US SEC EDGAR (HKEX / A-Share); refer to local exchange links below.')
            }}
          </div>
          <div v-else class="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <div
              v-for="act in entity.financial_actuals"
              :key="`${act.period_end}-${act.form}-${act.unit || 'u'}`"
              class="rounded-lg border border-slate-200 dark:border-slate-800 p-2.5 bg-slate-50/70 dark:bg-slate-800/40"
            >
              <div class="text-[11px] text-slate-500">{{ act.period_end }} · {{ act.frame || act.form }}</div>
              <div class="text-sm font-bold text-slate-900 dark:text-white tabular-nums mt-0.5">
                {{ act.value }} <span class="text-xs font-medium text-emerald-700 dark:text-emerald-300">{{ act.unit || '' }}</span>
              </div>
              <div class="text-[10px] text-slate-400">{{ act.metric }} · {{ t('披露：', 'Filed: ') }}{{ act.filed }}</div>
            </div>
          </div>
        </div>

        <div v-if="entity.recent_filings.length > 0" class="space-y-2">
          <h3 class="text-sm font-bold text-slate-900 dark:text-white">
            {{ t(`最新一手监管文件 (${entity.recent_filings.length})`, `Latest Regulatory Filings (${entity.recent_filings.length})`) }}
          </h3>
          <ul class="divide-y divide-slate-100 dark:divide-slate-800 rounded-xl border border-slate-200 dark:border-slate-800">
            <li
              v-for="f in entity.recent_filings"
              :key="f.url"
              class="p-3 flex items-center justify-between gap-2 text-xs"
            >
              <div class="min-w-0">
                <span class="font-mono font-semibold text-blue-700 dark:text-blue-300">{{ f.form }}</span>
                <span class="ml-2 text-slate-500">{{ f.filing_date }}</span>
                <p class="text-slate-800 dark:text-slate-200 truncate mt-0.5">{{ f.description || f.form }}</p>
              </div>
              <a
                v-if="normalizeExternalUrl(f.url)"
                :href="normalizeExternalUrl(f.url)!"
                target="_blank"
                rel="noopener noreferrer"
                @click.stop
                class="inline-flex items-center gap-1 px-2.5 py-1 rounded border border-slate-200 dark:border-slate-700 text-blue-600 dark:text-blue-400 hover:bg-blue-50 shrink-0"
              >
                <span>{{ t('原文', 'Source') }}</span>
                <ExternalLink class="w-3 h-3" />
              </a>
              <span v-else class="text-[11px] text-slate-400 shrink-0">{{ t('暂无直链', 'No Link') }}</span>
            </li>
          </ul>
        </div>

        <div class="space-y-2">
          <h3 class="text-sm font-bold text-slate-900 dark:text-white">
            {{ t(`本轮关联事件 (${entity.recent_events.length})`, `Related Events (${entity.recent_events.length})`) }}
          </h3>
          <p v-if="entity.recent_events.length === 0" class="text-xs text-slate-500">
            {{ t('本批次暂无与该主体关联的事件。', 'No linked events in this batch.') }}
          </p>
          <ul v-else class="space-y-2">
            <li
              v-for="ev in entity.recent_events"
              :key="ev.event_id"
              class="rounded-xl border border-slate-200 dark:border-slate-800 p-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2"
            >
              <div class="min-w-0 space-y-1">
                <div class="text-xs font-semibold text-slate-900 dark:text-white">{{ pickBiText(ev.title, ev.title_en) }}</div>
                <div class="text-[11px] text-slate-500">
                  <SmartTime :iso="ev.latest_reported_at || ev.first_discovered_at" :now-ms="effectiveNowMs" /> · {{ translateEvidenceStatus(ev.evidence_status) }}
                </div>
              </div>
              <button
                type="button"
                @click="emit('open-storyline', ev.storyline_id); emit('close')"
                class="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-violet-50 text-violet-800 border border-violet-200 dark:bg-violet-950/50 dark:text-violet-200 dark:border-violet-800 text-xs font-medium shrink-0 self-start sm:self-auto"
              >
                <GitBranch class="w-3.5 h-3.5" />
                <span>{{ t('进入主线档案', 'Open Dossier') }}</span>
              </button>
            </li>
          </ul>
        </div>
      </div>
    </div>
  </div>
</template>
