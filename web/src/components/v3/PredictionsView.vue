<script setup lang="ts">
import { computed, ref } from 'vue'
import { CheckCircle2, ChevronDown, ChevronRight, HelpCircle, History, Plus, RotateCcw, Scale, Share2, ThumbsDown, ThumbsUp, Trash2, Trophy, Users } from 'lucide-vue-next'
import EmptySearchState from '../EmptySearchState.vue'
import OdometerNumber from '../OdometerNumber.vue'
import SmartTime from '../SmartTime.vue'
import { pickBiText, t } from '../../core/i18n'
import { normalizeExternalUrl } from '../../core/legacyAdapter'
import { matchesSmartQuery } from '../../core/search'
import type { PredictionStance } from '../../core/storage'
import { computeLiveDomainLeaderboard, computePredictionStats, inferPredictionCategory, type PredictionCategory } from '../../core/v3Logic'
import type { CrowdPredictionStat, PredictionRecord } from '../../core/types'

const props = defineProps<{
  predictions: PredictionRecord[]
  publicNote?: string
  searchQuery?: string
  localPredictionIds?: Set<string>
  stances?: Record<string, PredictionStance>
  crowdStats?: Record<string, CrowdPredictionStat>
  isAdmin?: boolean
  nowMs?: number
}>()

const emit = defineEmits<{
  (e: 'create-prediction', record: PredictionRecord): void
  (e: 'revise-prediction', payload: { predictionId: string; newJudgment: string; newProbPct: number; reason: string }): void
  (e: 'settle-prediction', payload: { predictionId: string; outcome: 'correct' | 'incorrect' | 'indeterminate'; evidenceUrl: string; note: string }): void
  (e: 'set-prediction-stance', payload: { predictionId: string; stance: PredictionStance }): void
  (e: 'vote-crowd', payload: { predictionId: string; probPct: number }): void
  (e: 'delete-prediction', predictionId: string): void
  (e: 'reset-local-predictions'): void
  (e: 'clear-search'): void
}>()

const categoryFilter = ref<'all' | PredictionCategory | 'settled'>('all')
const showLeaderboard = ref(true)
const summaryOpenMobile = ref(false)
const brierHelpOpen = ref(false)
const expandedVersionIds = ref<Set<string>>(new Set())
const leaderboardCopied = ref(false)
const showNewForm = ref(false)
const revisingId = ref<string | null>(null)
const settlingId = ref<string | null>(null)
const effectiveNowMs = computed(() => props.nowMs ?? Date.now())

const fTitle = ref('')
const fEntity = ref('')
const fQuestion = ref('')
const fDueAt = ref('2026-12-01T18:00')
const fMode = ref<'live' | 'replay'>('live')
const fProb = ref(60)
const fWin = ref('')
const fLose = ref('')
const fAssume = ref('')
const fInvalid = ref('')
const fJudg = ref('')

const revJudg = ref('')
const revProb = ref(50)
const voteDrafts = ref<Record<string, number>>({})
const stanceBurstKey = ref('')
const voteBurstPid = ref('')
let burstTimer: ReturnType<typeof setTimeout> | null = null

function triggerStanceClick(predictionId: string, stance: PredictionStance) {
  stanceBurstKey.value = `${predictionId}:${stance}`
  if (burstTimer) clearTimeout(burstTimer)
  burstTimer = setTimeout(() => {
    stanceBurstKey.value = ''
    voteBurstPid.value = ''
  }, 500)
  emit('set-prediction-stance', { predictionId, stance })
}

function triggerVoteClick(rec: PredictionRecord) {
  voteBurstPid.value = rec.prediction_id
  if (burstTimer) clearTimeout(burstTimer)
  burstTimer = setTimeout(() => {
    stanceBurstKey.value = ''
    voteBurstPid.value = ''
  }, 500)
  emit('vote-crowd', { predictionId: rec.prediction_id, probPct: getVoteDraft(rec) })
}

function getVoteDraft(rec: PredictionRecord): number {
  const pid = rec.prediction_id
  if (typeof voteDrafts.value[pid] === 'number') return voteDrafts.value[pid]
  const uProb = props.crowdStats?.[pid]?.user_prob_pct
  if (typeof uProb === 'number') return Math.round(uProb)
  return Math.max(5, Math.min(95, Math.round(rec.probability_pct / 5) * 5))
}

function setVoteDraft(pid: string, val: number) {
  voteDrafts.value = { ...voteDrafts.value, [pid]: Math.max(5, Math.min(95, val)) }
}

function cleanPredText(raw?: string | null): string {
  if (!raw) return ''
  return String(raw)
    .replace(/^Replay:\s*/i, '')
    .replace(/（单独计入\s*Replay\s*区[^）]*）/g, '')
    .replace(/V3\s*SEC\s*EDGAR\s*连接器/gi, 'SEC 官方披露')
    .replace(/Hugging\s*Face\s*\/\s*官方文档连接器/gi, 'Hugging Face 与官方文档')
    .replace(/HF\s*连接器/gi, 'Hugging Face 官方发布')
    .replace(/连接器/g, '官方追踪')
    .trim()
}
const revReason = ref('')

const setOutcome = ref<'correct' | 'incorrect' | 'indeterminate'>('correct')
const setUrl = ref('')
const setNote = ref('')

const stats = computed(() => computePredictionStats(props.predictions))
const liveBoard = computed(() => computeLiveDomainLeaderboard(props.predictions, 5))

function toggleVersionExpand(id: string) {
  const next = new Set(expandedVersionIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedVersionIds.value = next
}

function versionTrailSummary(rec: PredictionRecord): string {
  const vers = rec.versions || []
  if (vers.length <= 1) {
    const v0 = vers[0]
    return v0 ? `v1 (${v0.probability_pct}%) · ${t('点击展开初始底稿', 'Tap to view baseline v1')}` : ''
  }
  const first = vers[0]
  const last = vers[vers.length - 1]
  return `v1 (${first.probability_pct}%) → v${last.version} (${last.probability_pct}%) · ${t(`点击展开 ${vers.length} 次观点演变`, `Tap for ${vers.length} revisions`)}`
}

function formatDueCountdown(dueIso: string): string {
  const dueMs = Date.parse(dueIso)
  if (Number.isNaN(dueMs)) return ''
  const diffDays = Math.ceil((dueMs - effectiveNowMs.value) / 86_400_000)
  if (diffDays < 0) return t('已到期', 'Past due')
  if (diffDays === 0) return t('今日到期', 'Due today')
  return t(`剩 ${diffDays} 天`, `${diffDays}d left`)
}

function copyLeaderboardUrl() {
  if (typeof window === 'undefined') return
  const u = new URL(window.location.href)
  u.searchParams.set('tab', 'predictions')
  u.searchParams.set('view', 'leaderboard')
  navigator.clipboard?.writeText(u.toString()).catch(() => {})
  leaderboardCopied.value = true
  setTimeout(() => {
    leaderboardCopied.value = false
  }, 1800)
}

const categoryCounts = computed(() => {
  const live = props.predictions.filter((p) => p.mode === 'live')
  return {
    all: props.predictions.length,
    tech_ai: live.filter((p) => inferPredictionCategory(p) === 'tech_ai').length,
    market: live.filter((p) => inferPredictionCategory(p) === 'market').length,
    macro: live.filter((p) => inferPredictionCategory(p) === 'macro').length,
    global_space: live.filter((p) => inferPredictionCategory(p) === 'global_space').length,
    settled: props.predictions.filter((p) => p.status === 'settled' || Boolean(p.settlement)).length,
  }
})

const filteredRecords = computed(() => {
  const q = (props.searchQuery || '').trim().toLowerCase()
  const matched = props.predictions.filter((p) => {
    const isSettled = p.status === 'settled' || Boolean(p.settlement)
    if (categoryFilter.value === 'settled') {
      if (!isSettled) return false
    } else if (categoryFilter.value !== 'all') {
      if (p.mode !== 'live') return false
      if (inferPredictionCategory(p) !== categoryFilter.value) return false
    }
    if (q) {
      const hay = `${p.title} ${p.question} ${p.target_entity || ''} ${p.current_judgment} ${p.win_rule} ${p.lose_rule}`
      if (!matchesSmartQuery(hay, q)) return false
    }
    return true
  })
  return matched.slice().sort((a, b) => {
    // 1. Live mode before historical replay; 2. Early/live settled highlighted cleanly right on top; 3. Earliest due date first
    const modeRankA = a.mode === 'live' ? 0 : 1
    const modeRankB = b.mode === 'live' ? 0 : 1
    if (modeRankA !== modeRankB) return modeRankA - modeRankB
    const settledA = a.status === 'settled' || Boolean(a.settlement) ? 0 : 1
    const settledB = b.status === 'settled' || Boolean(b.settlement) ? 0 : 1
    if (settledA !== settledB) return settledA - settledB
    return String(a.due_at || '').localeCompare(String(b.due_at || ''))
  })
})

function submitNew() {
  if (!fTitle.value.trim() || !fQuestion.value.trim()) return
  const nowIso = new Date().toISOString()
  const dueIso = fDueAt.value ? `${fDueAt.value}:00+08:00` : nowIso
  const initJudg = fJudg.value.trim() || fTitle.value.trim()
  emit('create-prediction', {
    prediction_id: `pred_user_${Date.now().toString(36)}`,
    mode: fMode.value,
    status: 'open',
    title: fTitle.value.trim(),
    target_entity: fEntity.value.trim() || t('自定义标的', 'Custom Entity'),
    question: fQuestion.value.trim(),
    created_at: nowIso,
    due_at: dueIso,
    win_rule: fWin.value.trim() || t('出现公开官方证实公告或可验证指标达标', 'Official confirmation or measurable milestone met'),
    lose_rule: fLose.value.trim() || t('到期前未达成目标或被官方辟谣', 'Not achieved by deadline or officially refuted'),
    indeterminate_rule: t('截至到期双方未公布足够客观证据', 'Insufficient objective public evidence by deadline'),
    supporting_evidence: [],
    opposing_evidence: [],
    core_assumption: fAssume.value.trim() || t('基于当前公开供应链/监管轨迹推演', 'Derived from current public filings & supply chain'),
    invalidation_trigger: fInvalid.value.trim() || t('官方文件否决或核心条件逆转', 'Official reversal or invalidating filing'),
    probability_pct: Math.min(99, Math.max(1, Number(fProb.value) || 50)),
    probability_note: fMode.value === 'replay' ? t('历史回测题 · 与实时验证分开统计', 'Historical replay · scored separately') : t('实时验证题 · 主观基准估算', 'Live prediction · subjective baseline'),
    current_judgment: initJudg,
    versions: [
      {
        version: 1,
        updated_at: nowIso,
        judgment: initJudg,
        probability_pct: Math.min(99, Math.max(1, Number(fProb.value) || 50)),
        reason: t('初始立项设定（自动保留 v1 不可篡改底稿）', 'Initial v1 baseline'),
      },
    ],
    settlement: null,
  })
  fTitle.value = ''
  fQuestion.value = ''
  fJudg.value = ''
  showNewForm.value = false
}

function openRevise(rec: PredictionRecord) {
  revisingId.value = rec.prediction_id
  settlingId.value = null
  revJudg.value = rec.current_judgment
  revProb.value = rec.probability_pct
  revReason.value = ''
}

function submitRevise(id: string) {
  emit('revise-prediction', {
    predictionId: id,
    newJudgment: revJudg.value.trim(),
    newProbPct: Math.min(99, Math.max(1, Number(revProb.value) || 50)),
    reason: revReason.value.trim() || t('根据最新公开证据调整判断', 'Updated based on latest public evidence'),
  })
  revisingId.value = null
}

function openSettle(rec: PredictionRecord) {
  settlingId.value = rec.prediction_id
  revisingId.value = null
  setOutcome.value = 'correct'
  setUrl.value = ''
  setNote.value = ''
}

function submitSettle(id: string) {
  emit('settle-prediction', {
    predictionId: id,
    outcome: setOutcome.value,
    evidenceUrl: setUrl.value.trim(),
    note: setNote.value.trim() || t('按公开结算规则完成核验判定', 'Resolved under public verification criteria'),
  })
  settlingId.value = null
}
</script>

<template>
  <section class="space-y-3" :aria-label="t('前瞻判断与历史验证工作台', 'Predictions & Verification Workbench')">
    <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-3 sm:p-4 space-y-3 shadow-xs">
      <!-- Slim Top Header + ? Explainer -->
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div class="min-w-0">
          <h2 class="text-[15px] sm:text-lg font-bold text-slate-900 dark:text-white flex items-center gap-1.5">
            <Scale class="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
            <span>{{ t('前瞻预测与客观验证', 'Predictions & Verification') }}</span>
            <button
              type="button"
              @click="brierHelpOpen = !brierHelpOpen"
              class="w-5 h-5 rounded-full inline-flex items-center justify-center text-slate-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-950/50"
              :aria-label="t('查看验证闭环与 Brier 精度说明', 'Verification & Brier explainer')"
            >
              <HelpCircle class="w-3.5 h-3.5" />
            </button>
          </h2>
          <p class="hidden sm:block text-xs text-slate-500 dark:text-slate-400">
            {{ cleanPredText(publicNote) || t('实时追踪与历史复盘严格分开计分，每次修订均不可篡改地保留历史快照。', 'Live tracking and historical reviews are scored strictly separately.') }}
          </p>
        </div>

        <div class="flex flex-wrap items-center gap-1.5 text-xs">
          <button
            type="button"
            @click="showNewForm = !showNewForm"
            class="inline-flex items-center gap-1 px-3 min-h-[32px] rounded-xl sm:rounded-lg bg-blue-600 text-white font-semibold hover:bg-blue-700 whitespace-nowrap"
          >
            <Plus class="w-3.5 h-3.5" />
            <span>{{ t('新建', 'New') }}<span class="hidden sm:inline">{{ t('可验证假设', ' Hypothesis') }}</span></span>
          </button>
          <button
            v-if="props.localPredictionIds && props.localPredictionIds.size > 0"
            type="button"
            @click="emit('reset-local-predictions')"
            class="inline-flex items-center gap-1 px-2.5 min-h-[32px] rounded-xl sm:rounded-lg border border-red-200 dark:border-red-900 bg-red-50/70 dark:bg-red-950/30 text-red-700 dark:text-red-300 hover:bg-red-100 whitespace-nowrap"
            :title="t('清除本地自建假设与测试结算记录', 'Reset local edits')"
          >
            <RotateCcw class="w-3.5 h-3.5" />
            <span class="hidden sm:inline">{{ t('清除本地修订', 'Reset Local') }}</span>
          </button>
        </div>
      </div>

      <!-- Plain-Language 3-Step Verification + Brier Calibration Explainer Popover -->
      <div
        v-if="brierHelpOpen"
        class="rounded-xl border border-blue-200 dark:border-blue-800/80 bg-blue-50/60 dark:bg-blue-950/30 p-3 text-xs space-y-1.5 text-slate-700 dark:text-slate-200"
      >
        <div class="font-bold text-blue-900 dark:text-blue-200">
          {{ t('镜信前瞻验证：3 步透明闭环与校准精度 (Brier 误差)', 'How Verification & Brier Calibration Works') }}
        </div>
        <p class="leading-relaxed">
          {{ t('① 公开立 Flag：绑定具体事实问题、倾向概率（0~100%）与唯一官方判定依据；② 过程修订留痕：每次根据新证据调整概率均保留 v1 底稿与演化链，绝不事后改口；③ 到期官方核验：依据 SEC 公告/央行声明/交易所收盘价自动结算。Brier 误差越接近 0 代表概率判断越精准（0.25 相当于随机猜）。', '1) Set falsifiable target & official win rule; 2) Track every probability revision without deleting v1; 3) Settle against official filings/rates. Lower Brier score (near 0) means better probability calibration.') }}
        </p>
      </div>

      <!-- Mobile Collapsible Overview Bar (< sm): Keeps prediction cards 1 & 2 right above the fold on 393x851! -->
      <button
        type="button"
        @click="summaryOpenMobile = !summaryOpenMobile"
        class="sm:hidden w-full rounded-xl border border-slate-200 dark:border-slate-700 bg-[#F5F5F7] dark:bg-slate-800/80 px-3 py-2 flex items-center justify-between gap-2 text-xs text-left"
      >
        <span class="font-semibold text-slate-800 dark:text-slate-100 truncate tabular-nums">
          {{
            liveBoard.liveSettledDecisive > 0
              ? t(`验证战绩（进行中 ${stats.live.openCount} · 实时已结 ${liveBoard.liveSettledDecisive} 命中 ${stats.live.correctCount}）`, `Summary (${stats.live.openCount} Open · ${liveBoard.liveSettledDecisive} Won ${stats.live.correctCount})`)
              : t(`验证战绩总览（实时进行中 ${stats.live.openCount} · 待核验 · 胜率榜）`, `Summary (${stats.live.openCount} Live Open · Stats)`)
          }}
        </span>
        <ChevronDown class="w-4 h-4 text-slate-500 shrink-0 transition-transform" :class="{ 'rotate-180': summaryOpenMobile }" />
      </button>

      <!-- Dual Calibration Cards + Live-Only Leaderboard (Collapsible on Mobile, Visible on Desktop >= sm) -->
      <div :class="summaryOpenMobile ? 'block space-y-3' : 'hidden sm:block space-y-3'">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
          <div class="rounded-xl bg-emerald-500/8 dark:bg-emerald-400/10 p-3 space-y-1">
            <div class="flex items-start justify-between gap-2">
              <span class="font-bold text-emerald-800 dark:text-emerald-200 min-w-0">{{ t('实时公开追踪验证', 'Live Public Tracking') }}</span>
              <span v-if="liveBoard.unlocked && stats.live.decisiveHitRatePct !== null" class="font-mono text-emerald-700 dark:text-emerald-300 font-semibold shrink-0 whitespace-nowrap">
                {{ t(`真实胜率 ${stats.live.decisiveHitRatePct}%`, `Win Rate ${stats.live.decisiveHitRatePct}%`) }}
              </span>
              <span v-else-if="liveBoard.liveSettledDecisive > 0" class="font-mono text-emerald-700 dark:text-emerald-300 font-semibold shrink-0 whitespace-nowrap">
                {{ t(`实时已结 ${liveBoard.liveSettledDecisive} 题（命中 ${stats.live.correctCount}）`, `${liveBoard.liveSettledDecisive} Settled (${stats.live.correctCount} Won)`) }}
              </span>
              <span v-else class="text-[11px] text-zinc-500 dark:text-zinc-400 shrink-0 whitespace-nowrap">
                {{ t(`待到期核验 (${stats.live.openCount} 题)`, `Awaiting Due Date (${stats.live.openCount} open)`) }}
              </span>
            </div>
            <div class="flex flex-wrap gap-x-4 gap-y-1 text-zinc-700 dark:text-zinc-300 tabular-nums">
              <span>{{ t('总题', 'Total') }} <OdometerNumber :value="stats.live.total" /></span>
              <span class="inline-flex items-center gap-1.5">
                <span class="jx-sonar-dot jx-sonar-emerald" aria-hidden="true" />
                <span>{{ t('进行中', 'Open') }} <OdometerNumber :value="stats.live.openCount" /></span>
              </span>
              <template v-if="liveBoard.unlocked">
                <span>{{ t('命中', 'Won') }} {{ stats.live.correctCount }}</span>
                <span>{{ t('未中', 'Lost') }} {{ stats.live.incorrectCount }}</span>
                <span>{{ t(`校准精度（Brier 误差 ${stats.live.brierScore} · 越接近 0 越精准）`, `Brier Error ${stats.live.brierScore}`) }}</span>
              </template>
              <span v-else-if="liveBoard.liveSettledDecisive > 0" class="text-emerald-700 dark:text-emerald-300 font-medium">
                {{ t(`实时已结 ${liveBoard.liveSettledDecisive} 题（命中 ${stats.live.correctCount}${stats.live.brierScore !== null ? ` · Brier ${stats.live.brierScore}` : ''}）· 满 5 题解锁完整榜单`, `Live settled ${liveBoard.liveSettledDecisive} (${stats.live.correctCount} won) · 5 settled unlocks full board`) }}
              </span>
              <span v-else class="text-zinc-500 dark:text-zinc-400">
                {{ t(`统计积累中 (${liveBoard.liveSettledDecisive}/5，待到期官方核验解锁真实胜率)`, `Building live sample (${liveBoard.liveSettledDecisive}/5 to unlock win rate)`) }}
              </span>
            </div>
          </div>

          <div class="ios-surface-2 p-3 space-y-1">
            <div class="flex items-start justify-between gap-2">
              <span class="font-bold text-zinc-800 dark:text-zinc-200 min-w-0">{{ t('历史复盘对照（独立存档，不计入公开胜率）', 'Historical Replay (Excluded from Public Win Rate)') }}</span>
              <span class="text-[11px] text-zinc-500 dark:text-zinc-400 shrink-0 whitespace-nowrap">
                {{ t(`${stats.replay.total} 题对照样题`, `${stats.replay.total} Replay Cases`) }}
              </span>
            </div>
            <div class="text-zinc-600 dark:text-zinc-400">
              {{ t(`已核验 ${liveBoard.replaySettledDecisive} 题历史事件回放；仅用于复盘波动幅度与锚定基准，绝不拉高实时胜率榜。`, `${liveBoard.replaySettledDecisive} historical replays archived separately; excluded from live leaderboard KPIs.`) }}
            </div>
          </div>
        </div>

        <!-- Public Prediction Accuracy Leaderboard (STRICTLY Live-only & >= 5 threshold) -->
        <div
          v-if="showLeaderboard"
          class="rounded-xl border border-indigo-200/80 dark:border-indigo-800/70 bg-indigo-50/40 dark:bg-indigo-950/20 p-3 space-y-2 text-xs"
          data-testid="prediction-leaderboard"
        >
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="flex items-center gap-1.5 font-bold text-slate-900 dark:text-white">
              <Trophy class="w-4 h-4 text-amber-500" />
              <span>{{ t('前瞻预测实时公开胜率榜（仅计入到期核验 Live 题）', 'Live Public Accuracy Leaderboard (Live Mode Only)') }}</span>
            </div>
            <button
              v-if="liveBoard.unlocked"
              type="button"
              @click="copyLeaderboardUrl"
              class="inline-flex items-center gap-1 px-2.5 min-h-[28px] rounded-lg border border-indigo-200 dark:border-indigo-700 bg-white dark:bg-slate-900 text-[11px] font-medium text-indigo-700 dark:text-indigo-300 hover:bg-indigo-50"
            >
              <Share2 class="w-3 h-3" />
              <span>{{ leaderboardCopied ? t('已复制公开榜链接', 'Leaderboard URL Copied') : t('分享公开胜率榜', 'Share Leaderboard') }}</span>
            </button>
          </div>

          <div
            v-if="!liveBoard.unlocked"
            class="rounded-lg bg-white/85 dark:bg-slate-900/80 border border-indigo-200/70 dark:border-indigo-900/60 px-3 py-2 text-slate-600 dark:text-slate-300"
          >
            {{
              liveBoard.liveSettledDecisive > 0
                ? t(`实时已结 ${liveBoard.liveSettledDecisive} 题（命中 ${stats.live.correctCount}）· 累计满 5 题解锁分领域公开胜率榜（另含 ${liveBoard.replaySettledDecisive} 题历史复盘样题独立计分，不计入榜单）。`, `Live settled ${liveBoard.liveSettledDecisive} (${stats.live.correctCount} won) · 5 settled unlocks domain leaderboard (${liveBoard.replaySettledDecisive} historical replays excluded).`)
                : t(`实时胜率统计积累中 (${liveBoard.liveSettledDecisive}/5，待到期官方核验解锁真实胜率) · 当前仅展示进行中/待核验跟踪题目（另含 ${liveBoard.replaySettledDecisive} 题历史复盘样题不计入榜单）。`, `Accumulating live sample (${liveBoard.liveSettledDecisive}/5 live settled needed to unlock public win rates; ${liveBoard.replaySettledDecisive} historical replays excluded).`)
            }}
          </div>

          <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
            <div
              v-for="(row, idx) in liveBoard.rows"
              :key="row.entity"
              class="rounded-lg bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 px-3 py-2 flex items-center justify-between gap-2"
            >
              <div class="min-w-0">
                <div class="font-semibold text-slate-800 dark:text-slate-100 truncate">
                  #{{ idx + 1 }} {{ row.entity }}
                </div>
                <div class="text-[11px] text-slate-500 tabular-nums">
                  {{ t(`实时样本 ${row.totalLive} · 已决 ${row.settledDecisive} · 命中 ${row.correct}`, `${row.totalLive} live · ${row.settledDecisive} settled · ${row.correct} won`) }}
                </div>
              </div>
              <div class="text-right shrink-0">
                <div class="font-mono font-bold text-sm" :class="row.hitPct !== null && row.hitPct >= 60 ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-700 dark:text-slate-200'">
                  {{ row.hitPct !== null ? `${row.hitPct}%` : t('待核验', 'Pending') }}
                </div>
                <div v-if="row.brier !== null" class="text-[10px] font-mono text-slate-400">
                  {{ t('Brier 误差', 'Brier') }} {{ row.brier }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Create Form -->
      <form
        v-if="showNewForm"
        @submit.prevent="submitNew"
        class="pt-3 border-t border-slate-200 dark:border-slate-800 space-y-2.5 text-xs"
      >
        <div class="grid grid-cols-1 sm:grid-cols-12 gap-2">
          <input v-model="fTitle" type="text" :placeholder="t('假设标题，如 某公司是否按期披露 8-K 公告', 'Hypothesis title, e.g. Will Company X file 8-K on schedule?')" class="sm:col-span-5 h-9 px-3 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-white" />
          <input v-model="fEntity" type="text" :placeholder="t('目标主体 (如 NVDA / Qwen)', 'Entity (e.g. NVDA / Qwen)')" class="sm:col-span-3 h-9 px-2.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-white" />
          <div class="relative inline-flex items-center sm:col-span-2 w-full h-9 pl-2.5 pr-7 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-white focus-within:ring-2 focus-within:ring-[#007AFF]/40">
            <span class="pointer-events-none truncate">{{ fMode === 'live' ? t('实时追踪', 'Live') : t('历史复盘', 'Review') }}</span>
            <ChevronDown class="w-3.5 h-3.5 text-zinc-400 pointer-events-none absolute right-2" />
            <select v-model="fMode" :aria-label="t('预测模式', 'Prediction mode')" class="absolute inset-0 w-full h-full opacity-0 cursor-pointer">
              <option value="live">{{ t('实时追踪', 'Live') }}</option>
              <option value="replay">{{ t('历史复盘', 'Review') }}</option>
            </select>
          </div>
          <input v-model.number="fProb" type="number" min="1" max="99" :aria-label="t('初始概率百分比', 'Initial probability (%)')" class="sm:col-span-2 h-9 px-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-white" />
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-12 gap-2">
          <input v-model="fQuestion" type="text" :placeholder="t('具体可检验问题（谁/什么指标/何时前）', 'Falsifiable question (who/metric/deadline)')" class="sm:col-span-5 h-9 px-3 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-white" />
          <input v-model="fDueAt" type="datetime-local" :aria-label="t('到期时间', 'Due date')" class="sm:col-span-3 h-9 px-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-white" />
          <input v-model="fJudg" type="text" :placeholder="t('v1 初始判断结论', 'Initial v1 judgment')" class="sm:col-span-4 h-9 px-2.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-white" />
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <input v-model="fWin" type="text" :placeholder="t('判赢客观规则 (可选)', 'Win criteria (optional)')" class="h-9 px-2.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-white" />
          <input v-model="fLose" type="text" :placeholder="t('判输/证伪触发条件 (可选)', 'Falsification criteria (optional)')" class="h-9 px-2.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-white" />
        </div>
        <button type="submit" class="px-4 py-2 rounded-lg bg-emerald-600 text-white font-semibold hover:bg-emerald-700">
          {{ t('提交建立预测 (保存 v1 初始版本)', 'Create Hypothesis (Save v1)') }}
        </button>
      </form>

      <!-- Domain Category Filter Pills -->
      <div class="flex flex-wrap items-center justify-between gap-2 text-xs pt-1">
        <div class="flex sm:flex-wrap gap-1.5 overflow-x-auto no-scrollbar sm:overflow-visible w-full sm:w-auto pb-0.5 sm:pb-0">
          <button type="button" @click="categoryFilter = 'all'" class="min-h-[36px] sm:min-h-[30px] px-3 sm:px-2.5 rounded-xl sm:rounded-lg border font-medium whitespace-nowrap shrink-0" :class="categoryFilter === 'all' ? 'bg-slate-900 text-white border-slate-900 dark:bg-blue-600 dark:border-blue-600' : 'bg-white text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700'">
            {{ t(`全部 (${categoryCounts.all})`, `All (${categoryCounts.all})`) }}
          </button>
          <button type="button" @click="categoryFilter = 'tech_ai'" class="min-h-[36px] sm:min-h-[30px] px-3 sm:px-2.5 rounded-xl sm:rounded-lg border font-medium whitespace-nowrap shrink-0" :class="categoryFilter === 'tech_ai' ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700'">
            {{ t(`科技与 AI (${categoryCounts.tech_ai})`, `Tech & AI (${categoryCounts.tech_ai})`) }}
          </button>
          <button type="button" @click="categoryFilter = 'market'" class="min-h-[36px] sm:min-h-[30px] px-3 sm:px-2.5 rounded-xl sm:rounded-lg border font-medium whitespace-nowrap shrink-0" :class="categoryFilter === 'market' ? 'bg-amber-600 text-white border-amber-600' : 'bg-white text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700'">
            {{ t(`股市与大宗 (${categoryCounts.market})`, `Markets (${categoryCounts.market})`) }}
          </button>
          <button type="button" @click="categoryFilter = 'macro'" class="min-h-[36px] sm:min-h-[30px] px-3 sm:px-2.5 rounded-xl sm:rounded-lg border font-medium whitespace-nowrap shrink-0" :class="categoryFilter === 'macro' ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-white text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700'">
            {{ t(`宏观与央行 (${categoryCounts.macro})`, `Macro & Fed (${categoryCounts.macro})`) }}
          </button>
          <button type="button" @click="categoryFilter = 'global_space'" class="min-h-[36px] sm:min-h-[30px] px-3 sm:px-2.5 rounded-xl sm:rounded-lg border font-medium whitespace-nowrap shrink-0" :class="categoryFilter === 'global_space' ? 'bg-slate-800 text-white border-slate-800 dark:bg-cyan-600 dark:border-cyan-600' : 'bg-white text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700'">
            {{ t(`国际与航天 (${categoryCounts.global_space})`, `Global & Space (${categoryCounts.global_space})`) }}
          </button>
          <button type="button" @click="categoryFilter = 'settled'" class="min-h-[36px] sm:min-h-[30px] px-3 sm:px-2.5 rounded-xl sm:rounded-lg border font-medium whitespace-nowrap shrink-0" :class="categoryFilter === 'settled' ? 'bg-emerald-600 text-white border-emerald-600' : 'bg-white text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700'">
            {{ t(`已核验实绩 (${categoryCounts.settled})`, `Settled (${categoryCounts.settled})`) }}
          </button>
        </div>
        <span v-if="props.searchQuery?.trim()" class="text-blue-600 dark:text-blue-400 font-medium">
          {{ t(`全局关键词检索命中 ${filteredRecords.length} / ${predictions.length} 项`, `Matched ${filteredRecords.length} / ${predictions.length}`) }}
        </span>
      </div>
    </div>

    <EmptySearchState
      v-if="filteredRecords.length === 0"
      :query="props.searchQuery"
      :has-extra-filters="categoryFilter !== 'all'"
      @clear-query="emit('clear-search')"
      @clear-filters-only="categoryFilter = 'all'"
      @reset="categoryFilter = 'all'; emit('clear-search')"
    />

    <div v-else class="grid grid-cols-1 xl:grid-cols-2 gap-3">
      <article
        v-for="rec in filteredRecords"
        :key="rec.prediction_id"
        class="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-3.5 sm:p-4 flex flex-col justify-between gap-3"
      >
        <div class="space-y-3">
          <!-- Section 1: Question Header + Countdown + Benchmark Badge -->
          <div class="flex flex-wrap items-center justify-between gap-2 text-xs">
            <div class="flex flex-wrap items-center gap-1.5">
              <span
                class="px-2 py-0.5 rounded-md font-semibold"
                :class="rec.mode === 'live' ? 'bg-emerald-500/12 text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-300' : 'bg-zinc-500/12 text-zinc-700 dark:bg-zinc-400/15 dark:text-zinc-300'"
              >
                {{ rec.mode === 'live' ? t('实时追踪', 'Live') : t('历史复盘', 'Review') }}
              </span>
              <span
                class="px-2 py-0.5 rounded font-semibold"
                :class="rec.settlement?.outcome === 'correct'
                  ? 'bg-emerald-600 text-white'
                  : rec.settlement?.outcome === 'incorrect'
                    ? 'bg-red-600 text-white'
                    : rec.settlement?.outcome === 'indeterminate'
                      ? 'bg-amber-600 text-white'
                      : 'bg-blue-50 text-blue-800 dark:bg-blue-950/60 dark:text-blue-200'"
              >
                {{
                  rec.settlement
                    ? rec.settlement.outcome === 'correct'
                      ? t('已核验：达成', 'Settled: Correct')
                      : rec.settlement.outcome === 'incorrect'
                        ? t('已核验：未达', 'Settled: Missed')
                        : t('已核验：延期未决', 'Settled: Indeterminate')
                    : t('进行中 · 待核验', 'Open · Tracking')
                }}
              </span>
              <span class="px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 text-[11px] font-medium">
                {{ rec.prediction_id.startsWith('pred_user_') ? t('我的自建判断', 'My Hypothesis') : t('镜信 AI 公开基准', 'MirrorBrief Benchmark') }}
              </span>
            </div>
            <span class="text-slate-500 tabular-nums text-[11px]">
              {{ t('到期 ', 'Due ') }}<SmartTime :iso="rec.due_at" :now-ms="effectiveNowMs" />
              <span v-if="!rec.settlement && formatDueCountdown(rec.due_at)" class="ml-1 font-semibold text-blue-600 dark:text-blue-400">
                ({{ formatDueCountdown(rec.due_at) }})
              </span>
            </span>
          </div>

          <div>
            <h3 class="text-sm sm:text-base font-bold text-slate-900 dark:text-white leading-snug">{{ cleanPredText(pickBiText(rec.title, (rec as any).title_en)) }}</h3>
            <p class="text-xs text-slate-600 dark:text-slate-300 mt-1 leading-relaxed">{{ cleanPredText(pickBiText(rec.question, (rec as any).question_en)) }}</p>
          </div>

          <!-- Section 2: Visual Tendency Probability Progress Bar & Official Settlement Criterion -->
          <div class="rounded-lg bg-slate-50 dark:bg-slate-800/60 p-2.5 border border-slate-200/80 dark:border-slate-700/80 space-y-2 text-xs">
            <div class="flex items-center justify-between gap-2">
              <span class="font-semibold text-slate-700 dark:text-slate-200">
                <template v-if="rec.settlement">
                  {{
                    t(
                      `结算前预测概率：${rec.probability_pct}%（${rec.settlement.outcome === 'correct' ? '已命中 · 100% 兑现' : rec.settlement.outcome === 'incorrect' ? '未命中 · 0% 落空' : '延期结案'}）`,
                      `Pre-Resolution Prob: ${rec.probability_pct}% (${rec.settlement.outcome === 'correct' ? 'Hit · 100%' : rec.settlement.outcome === 'incorrect' ? 'Missed · 0%' : 'Deferred'})`,
                    )
                  }}
                </template>
                <template v-else>
                  {{ t(`当前倾向概率：${rec.probability_pct}%`, `Current Probability: ${rec.probability_pct}%`) }}
                </template>
                <span class="text-[11px] font-normal text-slate-500">· {{ rec.prediction_id.startsWith('pred_user_') ? t('我的自建判断', 'My Judgment') : t('镜信 AI 公开基准', 'AI Public Benchmark') }}</span>
              </span>
              <span class="font-mono font-bold tabular-nums text-blue-700 dark:text-blue-300">
                {{ rec.settlement?.outcome === 'correct' ? '100%' : rec.settlement?.outcome === 'incorrect' ? '0%' : `${rec.probability_pct}%` }}
              </span>
            </div>
            <div class="relative h-2 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden">
              <div
                class="h-full rounded-full transition-all"
                :class="
                  rec.settlement?.outcome === 'correct'
                    ? 'bg-emerald-500'
                    : rec.settlement?.outcome === 'incorrect'
                      ? 'bg-rose-500'
                      : rec.probability_pct >= 60
                        ? 'bg-emerald-500'
                        : rec.probability_pct <= 40
                          ? 'bg-amber-500'
                          : 'bg-[#007AFF]'
                "
                :style="{
                  width: `${
                    rec.settlement?.outcome === 'correct'
                      ? 100
                      : rec.settlement?.outcome === 'incorrect'
                        ? 8
                        : Math.min(100, Math.max(4, rec.probability_pct))
                  }%`,
                }"
              />
            </div>

            <!-- Crowd Consensus Probability (strictly >= 10 users gate) & User Interactive Slider -->
            <div
              v-if="rec.mode === 'live' && !rec.settlement"
              class="pt-2 mt-1 border-t border-slate-200/70 dark:border-slate-700/70 space-y-1.5"
              data-testid="crowd-consensus-panel"
            >
              <div class="flex flex-wrap items-center justify-between gap-2 text-[11.5px]">
                <span class="inline-flex items-center gap-1.5 font-semibold text-slate-700 dark:text-slate-200">
                  <Users class="w-3.5 h-3.5 text-slate-500 shrink-0" :stroke-width="1.75" />
                  <span>{{ t('群众共识概率', 'Crowd Consensus') }}</span>
                </span>
                <span v-if="props.crowdStats?.[rec.prediction_id]?.unlocked" class="font-mono font-bold text-indigo-600 dark:text-indigo-400">
                  {{ t(`群众均值 ${props.crowdStats[rec.prediction_id].crowd_avg_pct}%（${props.crowdStats[rec.prediction_id].vote_count} 人参与）`, `Avg ${props.crowdStats[rec.prediction_id].crowd_avg_pct}% (${props.crowdStats[rec.prediction_id].vote_count} voters)`) }}
                </span>
                <span v-else class="font-medium text-amber-700 dark:text-amber-300">
                  {{ t(`群众概率收集阶段（${props.crowdStats?.[rec.prediction_id]?.vote_count || 0}/10 人已投票 · 满 10 人后解锁均值）`, `Collecting votes (${props.crowdStats?.[rec.prediction_id]?.vote_count || 0}/10 to unlock mean)`) }}
                </span>
              </div>
              <div class="relative h-1.5 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden">
                <div
                  v-if="props.crowdStats?.[rec.prediction_id]?.unlocked && props.crowdStats?.[rec.prediction_id]?.crowd_avg_pct != null"
                  class="h-full rounded-full bg-indigo-500 transition-all"
                  :style="{ width: `${Math.min(100, Math.max(4, props.crowdStats[rec.prediction_id].crowd_avg_pct || 0))}%` }"
                />
                <div
                  v-else
                  class="h-full rounded-full bg-amber-400 transition-all"
                  :style="{ width: `${Math.min(100, (props.crowdStats?.[rec.prediction_id]?.vote_count || 0) * 10)}%` }"
                />
              </div>
              <div class="flex flex-wrap items-center gap-2 pt-0.5">
                <input
                  type="range"
                  min="5"
                  max="95"
                  step="5"
                  :value="getVoteDraft(rec)"
                  @input="setVoteDraft(rec.prediction_id, Number(($event.target as HTMLInputElement).value))"
                  :aria-label="t('我的概率预判滑块', 'My probability slider')"
                  class="flex-1 min-w-[120px] accent-[#007AFF] cursor-pointer"
                />
                <span class="font-mono text-[11px] font-bold text-slate-700 dark:text-slate-200 w-9 text-right tabular-nums">
                  {{ getVoteDraft(rec) }}%
                </span>
                <button
                  type="button"
                  @click="triggerVoteClick(rec)"
                  class="jx-pop-target px-2.5 min-h-[28px] rounded-lg bg-[#007AFF] text-white text-[11px] font-semibold hover:bg-blue-600 whitespace-nowrap transition-transform"
                  :class="voteBurstPid === rec.prediction_id ? 'jx-pop-active jx-burst-ring' : ''"
                >
                  {{ props.crowdStats?.[rec.prediction_id]?.user_prob_pct != null ? t('更新我的投票', 'Update Vote') : t('提交我的概率预判', 'Submit Vote') }}
                </button>
              </div>
            </div>

            <div class="space-y-1 text-[12px] leading-relaxed pt-0.5">
              <div class="text-emerald-800 dark:text-emerald-300">
                <strong>{{ t('达成条件（是）：', 'Win Rule (Yes): ') }}</strong>{{ cleanPredText(rec.win_rule) }}
              </div>
              <div class="text-rose-700 dark:text-rose-300">
                <strong>{{ t('落空条件（猜错）：', 'Lose Rule (No): ') }}</strong>{{ cleanPredText(rec.lose_rule) }}
              </div>
              <div class="text-slate-700 dark:text-slate-200">
                <strong>{{ t('当前最新进展：', 'Latest Update: ') }}</strong>{{ cleanPredText(pickBiText(rec.current_judgment, (rec as any).current_judgment_en)) }}
              </div>
            </div>
          </div>

          <!-- Section 4: Collapsed 1-Line Version Evolution History (ZERO Nested Scroll Container!) -->
          <div class="rounded-lg bg-slate-50 dark:bg-slate-800/50 border border-slate-200/80 dark:border-slate-700/80 text-xs overflow-hidden">
            <button
              type="button"
              @click="toggleVersionExpand(rec.prediction_id)"
              class="w-full px-2.5 py-2 flex items-center justify-between gap-2 text-left hover:bg-slate-100/70 dark:hover:bg-slate-800"
              :aria-expanded="expandedVersionIds.has(rec.prediction_id)"
            >
              <span class="inline-flex items-center gap-1.5 min-w-0">
                <History class="w-3.5 h-3.5 text-slate-500 shrink-0" />
                <span class="font-semibold text-slate-700 dark:text-slate-200 shrink-0">{{ t(`版本修订轨迹 (${rec.versions.length} 版)`, `Revisions (${rec.versions.length})`) }}</span>
                <span class="text-[11px] text-slate-500 dark:text-slate-400 truncate">{{ versionTrailSummary(rec) }}</span>
              </span>
              <component :is="expandedVersionIds.has(rec.prediction_id) ? ChevronDown : ChevronRight" class="w-3.5 h-3.5 text-slate-400 shrink-0" />
            </button>
            <ul
              v-if="expandedVersionIds.has(rec.prediction_id)"
              class="px-2.5 pb-2.5 pt-1 border-t border-slate-200/70 dark:border-slate-700/70 space-y-1.5"
            >
              <li v-for="v in rec.versions" :key="v.version" class="text-[11px] text-slate-600 dark:text-slate-300 leading-relaxed">
                <strong class="font-mono text-slate-900 dark:text-white">v{{ v.version }}</strong>
                ({{ v.probability_pct }}% · <SmartTime :iso="v.updated_at" :now-ms="effectiveNowMs" />):
                {{ cleanPredText(v.judgment) }} — <span class="text-slate-500">{{ cleanPredText(v.reason) }}</span>
              </li>
            </ul>
          </div>

          <div v-if="rec.settlement" class="rounded-lg bg-emerald-50/70 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-900 p-2.5 text-xs space-y-1">
            <div>
              <CheckCircle2 class="w-3.5 h-3.5 inline mr-1 text-emerald-700 dark:text-emerald-400" />
              <strong>{{ t('核验结论：', 'Resolution: ') }}</strong>{{ rec.settlement.note }}
            </div>
            <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-600 dark:text-slate-300">
              <span v-if="rec.settlement.evidence_title">{{ rec.settlement.evidence_title }}</span>
              <a
                v-if="normalizeExternalUrl(rec.settlement.evidence_url)"
                :href="normalizeExternalUrl(rec.settlement.evidence_url)!"
                target="_blank"
                rel="noopener noreferrer"
                @click.stop
                class="text-blue-600 dark:text-blue-400 underline font-medium"
              >
                {{ t('查看核验出处', 'Verify Source') }}
              </a>
              <span v-if="rec.settlement.brier_score !== null && rec.settlement.brier_score !== undefined" class="font-mono text-emerald-700 dark:text-emerald-300">
                {{ t(`Brier 误差 ${rec.settlement.brier_score}`, `Brier ${rec.settlement.brier_score}`) }}
              </span>
            </div>
          </div>

          <div v-if="revisingId === rec.prediction_id" class="p-3 rounded-xl border border-blue-200 bg-blue-50/50 dark:bg-blue-950/30 space-y-2 text-xs">
            <div class="grid grid-cols-1 sm:grid-cols-4 gap-2">
              <input v-model="revJudg" type="text" :placeholder="t('新判断陈述', 'Revised judgment')" class="sm:col-span-3 px-2.5 py-1.5 rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900" />
              <input v-model.number="revProb" type="number" min="1" max="99" class="px-2.5 py-1.5 rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900" />
            </div>
            <input v-model="revReason" type="text" :placeholder="t('修改依据 (如 新增 SEC 披露或指标变化)', 'Reason for revision')" class="w-full px-2.5 py-1.5 rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900" />
            <div class="flex gap-2">
              <button type="button" @click="submitRevise(rec.prediction_id)" class="px-3 py-1 rounded bg-blue-600 text-white font-semibold">{{ t('保留旧版并写入新版本', 'Append New Version') }}</button>
              <button type="button" @click="revisingId = null" class="px-3 py-1 rounded border border-slate-300">{{ t('取消', 'Cancel') }}</button>
            </div>
          </div>

          <div v-if="settlingId === rec.prediction_id" class="p-3 rounded-xl border border-emerald-200 bg-emerald-50/50 dark:bg-emerald-950/30 space-y-2 text-xs">
            <div class="flex flex-wrap gap-2">
              <label class="inline-flex items-center gap-1"><input v-model="setOutcome" type="radio" value="correct" />{{ t('正确 (Correct)', 'Correct') }}</label>
              <label class="inline-flex items-center gap-1"><input v-model="setOutcome" type="radio" value="incorrect" />{{ t('错误 (Incorrect)', 'Incorrect') }}</label>
              <label class="inline-flex items-center gap-1"><input v-model="setOutcome" type="radio" value="indeterminate" />{{ t('不可判定 (Indeterminate)', 'Indeterminate') }}</label>
            </div>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <input v-model="setUrl" type="url" :placeholder="t('结算证据 URL (可选)', 'Evidence URL (optional)')" class="px-2.5 py-1.5 rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900" />
              <input v-model="setNote" type="text" :placeholder="t('结算依据说明', 'Resolution rationale')" class="px-2.5 py-1.5 rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900" />
            </div>
            <div class="flex gap-2">
              <button type="button" @click="submitSettle(rec.prediction_id)" class="px-3 py-1 rounded bg-emerald-600 text-white font-semibold">{{ t('确认客观结算', 'Confirm Resolution') }}</button>
              <button type="button" @click="settlingId = null" class="px-3 py-1 rounded border border-slate-300">{{ t('取消', 'Cancel') }}</button>
            </div>
          </div>
        </div>

        <div class="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-100 dark:border-slate-800 text-xs">
          <!-- 1-Click Stance Vote (Cloud Synced) -->
          <div v-if="rec.mode === 'live' && !rec.settlement" class="flex items-center gap-1">
            <button
              type="button"
              @click="triggerStanceClick(rec.prediction_id, 'agree')"
              class="jx-pop-target inline-flex items-center gap-1 px-2 min-h-[28px] rounded-lg border text-[11px] font-medium transition-all"
              :class="[
                props.stances?.[rec.prediction_id] === 'agree' ? 'bg-emerald-600 text-white border-emerald-600' : 'border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800',
                stanceBurstKey === `${rec.prediction_id}:agree` ? 'jx-pop-active jx-burst-ring text-emerald-500' : '',
              ]"
            >
              <ThumbsUp class="w-3 h-3 shrink-0" :stroke-width="1.75" :class="{ 'fill-current': props.stances?.[rec.prediction_id] === 'agree' }" />
              <span>{{ t('赞同', 'Agree') }}</span>
            </button>
            <button
              type="button"
              @click="triggerStanceClick(rec.prediction_id, 'disagree')"
              class="jx-pop-target inline-flex items-center gap-1 px-2 min-h-[28px] rounded-lg border text-[11px] font-medium transition-all"
              :class="[
                props.stances?.[rec.prediction_id] === 'disagree' ? 'bg-rose-600 text-white border-rose-600' : 'border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800',
                stanceBurstKey === `${rec.prediction_id}:disagree` ? 'jx-pop-active jx-burst-ring text-rose-500' : '',
              ]"
            >
              <ThumbsDown class="w-3 h-3 shrink-0" :stroke-width="1.75" :class="{ 'fill-current': props.stances?.[rec.prediction_id] === 'disagree' }" />
              <span>{{ t('反对', 'Disagree') }}</span>
            </button>
            <button
              type="button"
              @click="triggerStanceClick(rec.prediction_id, 'neutral')"
              class="jx-pop-target inline-flex items-center gap-1 px-2 min-h-[28px] rounded-lg border text-[11px] font-medium transition-all"
              :class="[
                props.stances?.[rec.prediction_id] === 'neutral' ? 'bg-slate-800 text-white border-slate-800 dark:bg-blue-600 dark:border-blue-600' : 'border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800',
                stanceBurstKey === `${rec.prediction_id}:neutral` ? 'jx-pop-active jx-burst-ring text-blue-500' : '',
              ]"
            >
              <Scale class="w-3 h-3 shrink-0" :stroke-width="1.75" />
              <span>{{ t('观望', 'Hold') }}</span>
            </button>
          </div>

          <div
            v-if="isAdmin || rec.prediction_id.startsWith('pred_user_')"
            class="flex flex-wrap items-center gap-1.5 ml-auto"
          >
            <button
              type="button"
              @click="openRevise(rec)"
              class="px-2.5 min-h-[30px] rounded-lg border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800"
            >
              {{ t('修订 (留v1)', 'Revise') }}
            </button>
            <button
              type="button"
              @click="openSettle(rec)"
              class="px-2.5 min-h-[30px] rounded-lg border border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-50 dark:hover:bg-emerald-950/50"
            >
              {{ rec.settlement ? t('重算', 'Re-resolve') : t('结算', 'Resolve') }}
            </button>
            <button
              v-if="props.localPredictionIds?.has(rec.prediction_id)"
              type="button"
              @click="emit('delete-prediction', rec.prediction_id)"
              class="inline-flex items-center gap-1 px-2.5 min-h-[30px] rounded-lg border border-red-200 dark:border-red-900 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/40"
              :aria-label="rec.prediction_id.startsWith('pred_user_') ? t('删除自建假设', 'Delete Custom') : t('还原默认状态', 'Restore Default')"
            >
              <Trash2 class="w-3.5 h-3.5" />
            </button>
          </div>
          <span
            v-else
            class="ml-auto text-[11px] text-slate-400"
          >
            {{ rec.settlement ? t('已由系统客观核验结案', 'Verified & settled automatically') : t('支持上方一键投票记录立场', 'Click Agree / Disagree / Hold to record stance') }}
          </span>
        </div>
      </article>
    </div>
  </section>
</template>
