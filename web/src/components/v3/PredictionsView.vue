<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  Award,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Copy,
  Flame,
  HelpCircle,
  LineChart,
  Lock,
  MessageSquareText,
  Newspaper,
  Plus,
  RotateCcw,
  Scale,
  Send,
  Share2,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  Trash2,
  TrendingUp,
  Trophy,
  Users,
  Zap,
} from 'lucide-vue-next'
import EmptySearchState from '../EmptySearchState.vue'
import OdometerNumber from '../OdometerNumber.vue'
import SmartTime from '../SmartTime.vue'
import UserAvatar from '../UserAvatar.vue'
import type { ArenaLeaderboardRow, UserPredictionProfile } from '../../core/auth'
import { pickBiText, t } from '../../core/i18n'
import { normalizeExternalUrl } from '../../core/legacyAdapter'
import { globalQuotesStore } from '../../core/quotesStore'
import { getReactionSummary, loadReactionsBatch, toggleStructuredReaction } from '../../core/reactionsStore'
import { matchesSmartQuery } from '../../core/search'
import type { PredictionStance } from '../../core/storage'
import { computeLiveDomainLeaderboard, computePredictionStats, inferPredictionCategory, type PredictionCategory } from '../../core/v3Logic'
import type {
  CrowdPredictionStat,
  EventMarketImpact,
  LiveWireItem,
  MarketQuoteItem,
  PredictionRecord,
  SmartEvent,
} from '../../core/types'

const DEFAULT_REASON_TAGS = ['流动性驱动', '业绩超预期', '市场已计价', '政策博弈', '逆向情绪']

const props = defineProps<{
  predictions: PredictionRecord[]
  publicNote?: string
  searchQuery?: string
  localPredictionIds?: Set<string>
  stances?: Record<string, PredictionStance>
  crowdStats?: Record<string, CrowdPredictionStat>
  crowdMinUnlock?: number
  guestStagedVotes?: Record<string, number>
  incomingPkChallenge?: { predId: string; prob: number; ref?: string } | null
  arenaProfile?: UserPredictionProfile | null
  arenaLeaderboard?: ArenaLeaderboardRow[]
  allowedReasonTags?: string[]
  predictionProposalsEnabled?: boolean
  seasonKey?: string
  allEvents?: SmartEvent[]
  liveWireItems?: LiveWireItem[]
  financeImpacts?: EventMarketImpact[]
  isLoggedIn?: boolean
  isAdmin?: boolean
  nowMs?: number
}>()

const emit = defineEmits<{
  (e: 'create-prediction', record: PredictionRecord): void
  (e: 'submit-proposal', body: { category: string; title: string; question: string; win_rule: string; lose_rule: string; due_at: string }): void
  (e: 'settle-prediction', payload: { predictionId: string; outcome: 'correct' | 'incorrect' | 'indeterminate'; evidenceUrl: string; note: string }): void
  (e: 'set-prediction-stance', payload: { predictionId: string; stance: PredictionStance }): void
  (e: 'vote-crowd', payload: { predictionId: string; probPct: number; reasonTag?: string }): void
  (e: 'open-share-pk', payload: { rec: PredictionRecord; probPct: number }): void
  (e: 'open-qa-prediction', rec: PredictionRecord): void
  (e: 'jump-event', ev: SmartEvent): void
  (e: 'open-finance-search', keyword: string): void
  (e: 'dismiss-pk-banner'): void
  (e: 'open-auth'): void
  (e: 'delete-prediction', predictionId: string): void
  (e: 'reset-local-predictions'): void
  (e: 'clear-search'): void
}>()

const categoryFilter = ref<'all' | PredictionCategory | 'settled'>('all')
const showLeaderboard = ref(true)
const arenaBoardOpen = ref(true)
const summaryOpenMobile = ref(false)
const brierHelpOpen = ref(false)
const expandedResearchIds = ref<Set<string>>(new Set())
const leaderboardCopied = ref(false)
const showNewForm = ref(false)
const settlingId = ref<string | null>(null)
const sprintIdx = ref(0)
const effectiveNowMs = computed(() => props.nowMs ?? Date.now())

const fTitle = ref('')
const fEntity = ref('')
const fCategory = ref<'market' | 'tech_ai' | 'macro' | 'global_space'>('market')
const fQuestion = ref('')
const fDueAt = ref('2026-12-01T18:00')
const fMode = ref<'live' | 'replay'>('live')
const fProb = ref(60)
const fWin = ref('')
const fLose = ref('')
const fAssume = ref('')
const fInvalid = ref('')
const fJudg = ref('')
const submitToArenaPool = ref(true)

const voteDrafts = ref<Record<string, number>>({})
const reasonDrafts = ref<Record<string, string>>({})
const stanceBurstKey = ref('')
const voteBurstPid = ref('')
const pkCopiedPid = ref('')
let burstTimer: ReturnType<typeof setTimeout> | null = null

const setOutcome = ref<'correct' | 'incorrect' | 'indeterminate'>('correct')
const setUrl = ref('')
const setNote = ref('')

const reasonTagsList = computed(() =>
  props.allowedReasonTags && props.allowedReasonTags.length > 0 ? props.allowedReasonTags : DEFAULT_REASON_TAGS,
)

const effectiveMinUnlock = computed(() => Math.max(1, Number(props.crowdMinUnlock ?? 3)))

function minVotesForRec(pid: string): number {
  return Math.max(1, Number(props.crowdStats?.[pid]?.min_votes ?? effectiveMinUnlock.value))
}

function resolveLockAtMs(rec: PredictionRecord): number | null {
  if (rec.lock_at) {
    const lm = Date.parse(rec.lock_at)
    if (!Number.isNaN(lm)) return lm
  }
  const dueMs = Date.parse(rec.due_at || '')
  if (!Number.isNaN(dueMs)) return dueMs - 30 * 60_000
  return null
}

function isRecLocked(rec: PredictionRecord): boolean {
  if (rec.settlement || rec.status === 'settled' || rec.arena_status === 'settled' || rec.arena_status === 'locked') {
    return true
  }
  const lockMs = resolveLockAtMs(rec)
  if (lockMs !== null && effectiveNowMs.value >= lockMs) return true
  const dueMs = Date.parse(rec.due_at || '')
  if (!Number.isNaN(dueMs) && effectiveNowMs.value >= dueMs) return true
  return false
}

function formatLockCountdown(rec: PredictionRecord): string {
  if (rec.settlement || rec.arena_status === 'settled') return t('已核验结算', 'Settled')
  if (isRecLocked(rec)) return t('已封盘 · 等待客观结算', 'Locked · Awaiting Settlement')
  const lockMs = resolveLockAtMs(rec)
  if (lockMs === null) return ''
  const diffMin = Math.max(1, Math.floor((lockMs - effectiveNowMs.value) / 60_000))
  if (diffMin < 60) return t(`距封盘 ${diffMin} 分`, `Locks in ${diffMin}m`)
  const hours = Math.floor(diffMin / 60)
  if (hours < 24) {
    const mins = diffMin % 60
    return t(`距封盘 ${hours}h${mins > 0 ? `${mins}m` : ''}`, `Locks in ${hours}h`)
  }
  const days = Math.floor(hours / 24)
  return t(`距封盘 ${days} 天`, `Locks in ${days}d`)
}

function getEarlyMultiplier(rec: PredictionRecord): number {
  const cMs = Date.parse(rec.created_at || '')
  const lMs = resolveLockAtMs(rec)
  if (Number.isNaN(cMs) || lMs === null || lMs <= cMs) return 1.0
  const frac = Math.max(0, (effectiveNowMs.value - cMs) / (lMs - cMs))
  if (frac <= 0.25) return 1.5
  if (frac <= 0.6) return 1.2
  return 1.0
}

function buildPkShareUrl(pid: string, probPct: number): string {
  if (typeof window === 'undefined') return ''
  const origin = window.location.origin || 'https://mirrorinfo.xyz'
  return `${origin}/s/pred/${encodeURIComponent(pid)}?p=${Math.round(probPct)}`
}

function copyPkLink(rec: PredictionRecord) {
  const url = buildPkShareUrl(rec.prediction_id, getVoteDraft(rec))
  if (url) navigator.clipboard?.writeText(url).catch(() => {})
  pkCopiedPid.value = rec.prediction_id
  setTimeout(() => {
    if (pkCopiedPid.value === rec.prediction_id) pkCopiedPid.value = ''
  }, 2000)
}

function scrollToPrediction(pid: string) {
  if (typeof document === 'undefined') return
  const el = document.getElementById(`pred-card-${pid}`)
  el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

watch(
  () => props.predictions.map((p) => p.prediction_id).join(','),
  (csv) => {
    if (!csv) return
    void loadReactionsBatch('prediction', csv.split(','))
  },
  { immediate: true },
)

function triggerStanceClick(predictionId: string, stance: PredictionStance) {
  stanceBurstKey.value = `${predictionId}:${stance}`
  if (burstTimer) clearTimeout(burstTimer)
  burstTimer = setTimeout(() => {
    stanceBurstKey.value = ''
    voteBurstPid.value = ''
  }, 500)
  void toggleStructuredReaction('prediction', predictionId, stance)
  emit('set-prediction-stance', { predictionId, stance })
}

function getReasonDraft(rec: PredictionRecord): string {
  const pid = rec.prediction_id
  if (pid in reasonDrafts.value) return reasonDrafts.value[pid]
  return props.crowdStats?.[pid]?.user_reason_tag || ''
}

function toggleReasonDraft(pid: string, tag: string) {
  const cur = reasonDrafts.value[pid] ?? props.crowdStats?.[pid]?.user_reason_tag ?? ''
  reasonDrafts.value = { ...reasonDrafts.value, [pid]: cur === tag ? '' : tag }
}

function triggerVoteClick(rec: PredictionRecord) {
  if (isRecLocked(rec)) return
  voteBurstPid.value = rec.prediction_id
  if (burstTimer) clearTimeout(burstTimer)
  burstTimer = setTimeout(() => {
    stanceBurstKey.value = ''
    voteBurstPid.value = ''
  }, 500)
  emit('vote-crowd', {
    predictionId: rec.prediction_id,
    probPct: getVoteDraft(rec),
    reasonTag: getReasonDraft(rec) || undefined,
  })
}

function getVoteDraft(rec: PredictionRecord): number {
  const pid = rec.prediction_id
  if (typeof voteDrafts.value[pid] === 'number') return voteDrafts.value[pid]
  const uProb = props.crowdStats?.[pid]?.user_prob_pct
  if (typeof uProb === 'number') return Math.round(uProb)
  const staged = props.guestStagedVotes?.[pid]
  if (typeof staged === 'number') return Math.round(staged)
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

const stats = computed(() => computePredictionStats(props.predictions))
const liveBoard = computed(() => computeLiveDomainLeaderboard(props.predictions, 5))

const pkChallengeRecord = computed<PredictionRecord | null>(() => {
  if (!props.incomingPkChallenge) return null
  return props.predictions.find((p) => p.prediction_id === props.incomingPkChallenge?.predId) ?? null
})

// Daily 3-Question Speed Prediction Sprint: prioritize open daily/proposal questions first, then open live questions
const sprintQuestions = computed<PredictionRecord[]>(() => {
  const openOnes = props.predictions.filter((p) => p.mode === 'live' && !isRecLocked(p))
  const dailyOrProposal = openOnes.filter((p) => p.source_type === 'auto_market' || p.source_type === 'user_proposal')
  const rest = openOnes.filter((p) => p.source_type !== 'auto_market' && p.source_type !== 'user_proposal')
  return [...dailyOrProposal, ...rest].slice(0, 3)
})

function hasUserForecasted(pid: string): boolean {
  return (
    props.crowdStats?.[pid]?.user_prob_pct != null ||
    props.guestStagedVotes?.[pid] !== undefined
  )
}

const sprintDoneCount = computed(() => sprintQuestions.value.filter((q) => hasUserForecasted(q.prediction_id)).length)
const currentSprintRec = computed<PredictionRecord | null>(() => {
  const list = sprintQuestions.value
  if (list.length === 0) return null
  const idx = sprintIdx.value % list.length
  return list[idx]
})

function submitSprintAndAdvance() {
  const rec = currentSprintRec.value
  if (!rec || isRecLocked(rec)) return
  const alreadyDoneAll = sprintDoneCount.value >= sprintQuestions.value.length
  triggerVoteClick(rec)
  if (!alreadyDoneAll && sprintQuestions.value.length > 1) {
    sprintIdx.value = (sprintIdx.value + 1) % sprintQuestions.value.length
  }
}

function toggleResearchExpand(id: string) {
  const next = new Set(expandedResearchIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedResearchIds.value = next
}

function openSprintResearch(rec: PredictionRecord) {
  const next = new Set(expandedResearchIds.value)
  next.add(rec.prediction_id)
  expandedResearchIds.value = next
  scrollToPrediction(rec.prediction_id)
}

const DOMAIN_TERM_GROUPS: Array<{ kw: string[]; label: string }> = [
  { kw: ['上证', '000001', 'a股', '沪指', '中国股市', '央行', '降准'], label: '上证指数' },
  { kw: ['英伟达', 'nvda', '芯片', '算力', 'gpu', '半导体'], label: '英伟达' },
  { kw: ['纳指', '纳斯达克', 'ixic', '美股', '标普'], label: '美股' },
  { kw: ['黄金', 'xau', 'xauusd', 'gc=f', '金价', '避险'], label: '黄金' },
  { kw: ['美联储', 'fomc', '降息', '加息', '通胀', 'cpi', '利率'], label: '美联储' },
  { kw: ['claude', 'anthropic', 'openai', 'gpt', 'gemini', '大模型', 'ai'], label: 'AI' },
  { kw: ['原油', '油价', '霍尔木兹', 'opec', '地缘', '中东'], label: '原油' },
]

function extractPredictionKeywords(rec: PredictionRecord): string[] {
  const tokens: string[] = []
  const hay = `${rec.title} ${rec.question} ${rec.target_entity || ''} ${rec.ticker || ''}`.toLowerCase()
  if (rec.ticker) tokens.push(rec.ticker.toLowerCase())
  if (rec.target_entity) tokens.push(rec.target_entity.toLowerCase())
  for (const grp of DOMAIN_TERM_GROUPS) {
    if (grp.kw.some((k) => hay.includes(k))) {
      for (const k of grp.kw) tokens.push(k)
    }
  }
  const enWords = hay.match(/[a-z]{3,}/g) || []
  for (const w of enWords) {
    if (!['the', 'and', 'for', 'will', 'this', 'with', 'from', 'live', 'replay', 'open'].includes(w)) {
      tokens.push(w)
    }
  }
  return Array.from(new Set(tokens)).slice(0, 12)
}

function extractPrimaryKeyword(rec: PredictionRecord): string {
  const hay = `${rec.title} ${rec.question} ${rec.target_entity || ''} ${rec.ticker || ''}`.toLowerCase()
  for (const grp of DOMAIN_TERM_GROUPS) {
    if (grp.kw.some((k) => hay.includes(k))) return grp.label
  }
  if (rec.target_entity && !rec.target_entity.includes('自定义')) return rec.target_entity
  return rec.ticker || ''
}

function resolveQuoteForPrediction(rec: PredictionRecord): MarketQuoteItem | null {
  const map = globalQuotesStore.quotesMap.value
  const list = globalQuotesStore.indices.value
  const candidates: string[] = []
  if (rec.ticker) candidates.push(rec.ticker, rec.ticker.toUpperCase())
  const hay = `${rec.title} ${rec.question}`.toLowerCase()
  if (hay.includes('上证') || hay.includes('000001')) candidates.push('000001.SH')
  if (hay.includes('英伟达') || hay.includes('nvda')) candidates.push('NVDA')
  if (hay.includes('纳指') || hay.includes('纳斯达克') || hay.includes('ixic')) candidates.push('IXIC')
  if (hay.includes('黄金') || hay.includes('xau') || hay.includes('gc=f')) candidates.push('XAUUSD', 'GC=F', '518880.SH')
  for (const key of candidates) {
    const hit = map[key] || list.find((it) => it.ticker.toUpperCase() === key.toUpperCase())
    if (hit && Number.isFinite(Number(hit.price)) && Number(hit.price) > 0) return hit
  }
  return null
}

function buildPredictionResearchPack(rec: PredictionRecord) {
  const kws = extractPredictionKeywords(rec)
  const primaryKeyword = extractPrimaryKeyword(rec)
  const liveQuote = resolveQuoteForPrediction(rec)
  const refTarget = Number(rec.target_price ?? rec.base_price ?? 0)
  const targetGapPct =
    liveQuote && refTarget > 0
      ? Number((((Number(liveQuote.price) - refTarget) / refTarget) * 100).toFixed(2))
      : null

  const catPref = inferPredictionCategory(rec)
  const preferredCat =
    catPref === 'tech_ai' ? 'tech' : catPref === 'global_space' ? 'global' : 'finance'

  const scoredEvents = (props.allEvents || [])
    .map((ev) => {
      const hay = `${ev.title_zh || ev.title} ${ev.fact_summary || ev.summary || ''} ${(ev.entities || []).join(' ')}`.toLowerCase()
      let score = 0
      for (const kw of kws) {
        if (hay.includes(kw)) score += 3
      }
      if (ev.category === preferredCat) score += 1
      if (ev.severity_tier === 'S' || ev.importance === 'high') score += 1
      return { ev, score }
    })
    .filter((x) => x.score >= 3 || (kws.length === 0 && x.ev.category === preferredCat))
    .sort((a, b) => b.score - a.score)
  const matchedEvents =
    scoredEvents.length > 0
      ? scoredEvents.slice(0, 3).map((x) => x.ev)
      : (props.allEvents || []).filter((e) => e.category === preferredCat).slice(0, 2)

  const matchedImpacts = (props.financeImpacts || [])
    .filter((imp) => {
      const hay = `${imp.event_title} ${imp.tag} ${imp.one_liner} ${imp.category}`.toLowerCase()
      return kws.some((kw) => hay.includes(kw))
    })
    .slice(0, 2)

  const matchedWire = (props.liveWireItems || [])
    .filter((w) => {
      const hay = `${w.title} ${w.excerpt} ${w.tag}`.toLowerCase()
      return kws.some((kw) => hay.includes(kw))
    })
    .slice(0, 2)

  return {
    liveQuote,
    refTarget: refTarget > 0 ? refTarget : null,
    targetGapPct,
    matchedEvents,
    matchedImpacts,
    matchedWire,
    primaryKeyword,
    supporting: (rec.supporting_evidence || []).slice(0, 3),
    opposing: (rec.opposing_evidence || []).slice(0, 3),
  }
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

function humanVsAiOutcome(rec: PredictionRecord): 'human_win' | 'ai_win' | 'tie' | null {
  if (!rec.settlement || rec.settlement.outcome === 'indeterminate') return null
  const stat = props.crowdStats?.[rec.prediction_id]
  if (!stat || !stat.unlocked || stat.crowd_avg_pct == null) return null
  const actual = rec.settlement.outcome === 'correct' ? (rec.probability_pct >= 50 ? 1 : 0) : null
  const arenaActual = rec.arena_outcome === 'yes' ? 1 : rec.arena_outcome === 'no' ? 0 : actual
  if (arenaActual === null) return null
  const hErr = Math.abs(stat.crowd_avg_pct / 100 - arenaActual)
  const aiErr = Math.abs(rec.probability_pct / 100 - arenaActual)
  if (hErr + 0.01 < aiErr) return 'human_win'
  if (aiErr + 0.01 < hErr) return 'ai_win'
  return 'tie'
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
    // 1. Open daily/co-created & live predictions first; 2. Locked open waiting settlement; 3. Settled; 4. Replay
    const rankWeight = (p: PredictionRecord) => {
      if (p.mode === 'replay') return 4
      if (p.status === 'settled' || Boolean(p.settlement)) return 3
      if (isRecLocked(p)) return 2
      if (p.source_type === 'auto_market' || p.source_type === 'user_proposal') return 0
      return 1
    }
    const rA = rankWeight(a)
    const rB = rankWeight(b)
    if (rA !== rB) return rA - rB
    return String(a.due_at || '').localeCompare(String(b.due_at || ''))
  })
})

function submitNew() {
  if (!fTitle.value.trim() || !fQuestion.value.trim()) return
  const nowIso = new Date().toISOString()
  const dueIso = fDueAt.value ? `${fDueAt.value}:00+08:00` : nowIso
  const initJudg = fJudg.value.trim() || fTitle.value.trim()
  const titleTrim = fTitle.value.trim()
  const qTrim = fQuestion.value.trim()
  const winTrim = fWin.value.trim() || t('出现公开官方证实公告或可验证指标达标', 'Official confirmation or measurable milestone met')
  const loseTrim = fLose.value.trim() || t('到期前未达成目标或被官方辟谣', 'Not achieved by deadline or officially refuted')

  emit('create-prediction', {
    prediction_id: `pred_user_${Date.now().toString(36)}`,
    mode: fMode.value,
    status: 'open',
    category: fCategory.value,
    title: titleTrim,
    target_entity: fEntity.value.trim() || t('自定义标的', 'Custom Entity'),
    question: qTrim,
    created_at: nowIso,
    due_at: dueIso,
    win_rule: winTrim,
    lose_rule: loseTrim,
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

  if (submitToArenaPool.value && fMode.value === 'live' && props.predictionProposalsEnabled !== false) {
    emit('submit-proposal', {
      category: fCategory.value,
      title: titleTrim,
      question: qTrim,
      win_rule: winTrim,
      lose_rule: loseTrim,
      due_at: dueIso,
    })
  }

  fTitle.value = ''
  fQuestion.value = ''
  fJudg.value = ''
  showNewForm.value = false
}

function openSettle(rec: PredictionRecord) {
  settlingId.value = rec.prediction_id
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
    <!-- Pinned Top Friend PK Focusing Card (?tab=calendar&pred=<id>&p=<prob>&ref=<name>) -->
    <div
      v-if="incomingPkChallenge"
      class="rounded-2xl border-2 border-[#007AFF] bg-gradient-to-br from-[#007AFF]/[0.08] via-white to-white dark:from-[#0A84FF]/[0.16] dark:via-slate-900 dark:to-slate-900 p-4 space-y-3 shadow-sm text-xs"
      data-testid="pk-challenge-banner"
    >
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div class="flex items-center gap-2 min-w-0">
          <span class="px-2 py-0.5 rounded-full bg-[#007AFF] text-white text-[11px] font-bold shrink-0">
            {{ t('好友预测 PK 聚焦对战', 'Friend Prediction PK') }}
          </span>
          <span class="font-bold text-slate-900 dark:text-white truncate">
            {{ pkChallengeRecord ? cleanPredText(pkChallengeRecord.title) : incomingPkChallenge.predId }}
          </span>
        </div>
        <div class="flex items-center gap-1.5 shrink-0">
          <button
            type="button"
            @click="categoryFilter = 'all'; scrollToPrediction(incomingPkChallenge.predId)"
            class="px-2.5 py-1 rounded-lg bg-[#F2F2F7] dark:bg-slate-800 text-slate-700 dark:text-slate-200 font-semibold hover:text-[#007AFF]"
          >
            {{ t('定位原卡片', 'Scroll to Card') }}
          </button>
          <button
            type="button"
            @click="emit('dismiss-pk-banner')"
            class="px-2 py-1 rounded-lg text-zinc-500 hover:bg-black/[0.05] dark:hover:bg-white/[0.08]"
          >
            {{ t('收起', 'Dismiss') }}
          </button>
        </div>
      </div>

      <p v-if="pkChallengeRecord" class="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
        {{ cleanPredText(pkChallengeRecord.question) }}
      </p>

      <div class="grid grid-cols-1 md:grid-cols-12 gap-2.5 items-stretch">
        <div class="md:col-span-3 rounded-xl bg-amber-500/10 border border-amber-500/25 p-3 flex flex-col justify-center">
          <div class="text-[11px] font-semibold text-amber-800 dark:text-amber-300">
            {{ incomingPkChallenge.ref ? `@${incomingPkChallenge.ref} 的预判` : t('好友预判概率', 'Friend Forecast') }}
          </div>
          <div class="text-2xl font-bold font-mono tabular-nums text-amber-700 dark:text-amber-300 mt-0.5">
            {{ incomingPkChallenge.prob }}%
          </div>
        </div>

        <div class="md:col-span-3 rounded-xl bg-slate-100 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700 p-3 flex flex-col justify-center">
          <div class="text-[11px] font-semibold text-slate-500 dark:text-slate-400">
            {{ t('镜信 AI 基准概率', 'MirrorBrief AI Baseline') }}
          </div>
          <div class="text-2xl font-bold font-mono tabular-nums text-slate-900 dark:text-white mt-0.5">
            {{ pkChallengeRecord ? Math.round(pkChallengeRecord.probability_pct) : 50 }}%
          </div>
        </div>

        <div class="md:col-span-6 rounded-xl bg-white dark:bg-slate-950/60 border border-[#007AFF]/25 p-3 space-y-2">
          <template v-if="pkChallengeRecord && isRecLocked(pkChallengeRecord)">
            <div class="flex items-center gap-1.5 text-amber-700 dark:text-amber-300 font-semibold">
              <Lock class="w-3.5 h-3.5 shrink-0" />
              <span>{{ t('本题已封盘 · 等待客观结算，禁止继续提交新预测', 'Locked — Awaiting Objective Settlement') }}</span>
            </div>
          </template>
          <template v-else-if="pkChallengeRecord">
            <div class="flex items-center justify-between gap-2">
              <span class="font-semibold text-slate-800 dark:text-slate-100">{{ t('我的接招概率：', 'My Forecast:') }}</span>
              <div class="flex items-center gap-1">
                <button
                  v-for="presetVal in [20, 50, 80]"
                  :key="presetVal"
                  type="button"
                  @click="setVoteDraft(pkChallengeRecord.prediction_id, presetVal)"
                  class="px-2 py-0.5 rounded-md font-mono font-bold text-[11px] border"
                  :class="getVoteDraft(pkChallengeRecord) === presetVal ? 'bg-[#007AFF] text-white border-[#007AFF]' : 'border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300'"
                >
                  {{ presetVal }}%
                </button>
              </div>
            </div>
            <div class="flex items-center gap-2">
              <input
                type="range"
                min="5"
                max="95"
                step="5"
                :value="getVoteDraft(pkChallengeRecord)"
                @input="setVoteDraft(pkChallengeRecord.prediction_id, Number(($event.target as HTMLInputElement).value))"
                class="flex-1 accent-[#007AFF] cursor-pointer"
              />
              <span class="font-mono text-sm font-bold text-[#007AFF] w-10 text-right tabular-nums">
                {{ getVoteDraft(pkChallengeRecord) }}%
              </span>
              <button
                type="button"
                @click="triggerVoteClick(pkChallengeRecord)"
                class="px-3 py-1.5 rounded-xl bg-[#007AFF] hover:bg-[#0066D6] text-white font-semibold shrink-0"
              >
                {{ t('提交应战', 'Accept PK') }}
              </button>
              <button
                type="button"
                @click="emit('open-share-pk', { rec: pkChallengeRecord, probPct: getVoteDraft(pkChallengeRecord) })"
                class="px-2.5 py-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-semibold shrink-0"
              >
                {{ t('海报', 'Card') }}
              </button>
            </div>
          </template>
        </div>
      </div>
    </div>

    <!-- Top Arena Bar: Calibration Profile + Daily 3-Question Sprint + Season Leaderboard -->
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-3 text-xs">
      <!-- Left: Daily 3-Question Speed Sprint -->
      <div
        v-if="sprintQuestions.length > 0"
        class="lg:col-span-7 rounded-2xl border border-emerald-500/25 bg-gradient-to-br from-emerald-500/[0.06] via-white to-white dark:from-emerald-400/[0.08] dark:via-slate-900 dark:to-slate-900 p-3.5 sm:p-4 space-y-2.5 shadow-xs"
        data-testid="daily-sprint-card"
      >
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="flex items-center gap-1.5 font-bold text-slate-900 dark:text-white text-[13.5px]">
            <Zap class="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" :stroke-width="2" />
            <span>{{ t('每日 3 题极速预测打卡', 'Daily 3-Question Prediction Sprint') }}</span>
            <span class="px-2 py-0.5 rounded-full bg-emerald-600/12 text-emerald-700 dark:text-emerald-300 text-[11px] font-mono tabular-nums">
              {{ sprintDoneCount }}/{{ sprintQuestions.length }}
            </span>
          </div>
          <div class="flex items-center gap-1">
            <button
              v-for="(sq, idx) in sprintQuestions"
              :key="`sp-dot-${sq.prediction_id}`"
              type="button"
              @click="sprintIdx = idx"
              class="px-2 py-0.5 rounded-md font-mono text-[11px] font-semibold border transition-colors"
              :class="
                idx === sprintIdx % sprintQuestions.length
                  ? 'bg-emerald-600 text-white border-emerald-600'
                  : hasUserForecasted(sq.prediction_id)
                    ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/30'
                    : 'bg-white dark:bg-slate-800 text-slate-500 border-slate-200 dark:border-slate-700'
              "
            >
              #{{ idx + 1 }}
            </button>
          </div>
        </div>

        <template v-if="currentSprintRec">
          <div class="space-y-1">
            <div class="flex flex-wrap items-center gap-1.5 text-[11px]">
              <span
                class="px-1.5 py-0.5 rounded bg-blue-500/12 text-blue-700 dark:text-blue-300 font-semibold"
              >
                {{
                  currentSprintRec.source_type === 'auto_market'
                    ? t('今日行情日赛', 'Daily Market')
                    : currentSprintRec.source_type === 'user_proposal'
                      ? t('用户共创', 'Community')
                      : t('主线追踪', 'Live Track')
                }}
              </span>
              <span class="px-1.5 py-0.5 rounded bg-amber-500/12 text-amber-700 dark:text-amber-300 font-mono font-bold">
                {{ t(`早鸟 ${getEarlyMultiplier(currentSprintRec)}×`, `${getEarlyMultiplier(currentSprintRec)}x Early`) }}
              </span>
              <span class="text-slate-500 dark:text-slate-400 font-medium">
                {{ formatLockCountdown(currentSprintRec) }}
              </span>
            </div>
            <div class="font-bold text-sm text-slate-950 dark:text-white leading-snug">
              {{ cleanPredText(currentSprintRec.title) }}
            </div>
          </div>

          <div class="flex flex-wrap items-center gap-1.5">
            <button
              v-for="pctBtn in [20, 50, 80]"
              :key="`sp-pct-${pctBtn}`"
              type="button"
              @click="setVoteDraft(currentSprintRec.prediction_id, pctBtn)"
              class="px-2.5 min-h-[30px] rounded-lg font-mono font-bold border transition-colors"
              :class="
                getVoteDraft(currentSprintRec) === pctBtn
                  ? 'bg-[#007AFF] text-white border-[#007AFF]'
                  : 'bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:border-[#007AFF]'
              "
            >
              {{ pctBtn }}%
            </button>
            <input
              type="range"
              min="5"
              max="95"
              step="5"
              :value="getVoteDraft(currentSprintRec)"
              @input="setVoteDraft(currentSprintRec.prediction_id, Number(($event.target as HTMLInputElement).value))"
              class="flex-1 min-w-[110px] accent-[#007AFF] cursor-pointer"
            />
            <span class="font-mono font-bold text-slate-800 dark:text-slate-100 w-9 text-right tabular-nums">
              {{ getVoteDraft(currentSprintRec) }}%
            </span>
          </div>

          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="flex flex-wrap items-center gap-1">
              <button
                v-for="tag in reasonTagsList"
                :key="`sp-tag-${tag}`"
                type="button"
                @click="toggleReasonDraft(currentSprintRec.prediction_id, tag)"
                class="px-2 py-0.5 rounded-full text-[11px] border transition-colors"
                :class="
                  getReasonDraft(currentSprintRec) === tag
                    ? 'bg-slate-900 text-white border-slate-900 dark:bg-blue-600 dark:border-blue-600'
                    : 'bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700'
                "
              >
                {{ tag }}
              </button>
            </div>
            <div class="flex flex-wrap items-center gap-1.5 ml-auto">
              <button
                type="button"
                @click="emit('open-qa-prediction', currentSprintRec)"
                class="inline-flex items-center gap-1 px-2.5 min-h-[32px] rounded-xl border border-blue-200 dark:border-blue-800 text-[#007AFF] dark:text-[#64D2FF] font-semibold hover:bg-blue-50 dark:hover:bg-blue-950/30"
              >
                <MessageSquareText class="w-3.5 h-3.5" />
                <span>{{ t('AI 查证据', 'Ask AI') }}</span>
              </button>
              <button
                type="button"
                @click="openSprintResearch(currentSprintRec)"
                class="inline-flex items-center gap-1 px-2.5 min-h-[32px] rounded-xl border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 font-semibold hover:bg-slate-50 dark:hover:bg-slate-800"
              >
                <BookOpen class="w-3.5 h-3.5" />
                <span>{{ t('看关联数据', 'Data') }}</span>
              </button>
              <button
                type="button"
                @click="submitSprintAndAdvance"
                class="px-3 min-h-[32px] rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-semibold"
                data-testid="sprint-submit-btn"
              >
                {{
                  sprintDoneCount >= sprintQuestions.length
                    ? t('修改预测', 'Edit Forecast')
                    : hasUserForecasted(currentSprintRec.prediction_id)
                      ? t('修改并下一题', 'Update & Next')
                      : t('提交并下一题', 'Submit & Next')
                }}
              </button>
              <button
                v-if="sprintDoneCount >= sprintQuestions.length"
                type="button"
                @click="emit('open-share-pk', { rec: currentSprintRec, probPct: getVoteDraft(currentSprintRec) })"
                class="inline-flex items-center gap-1 px-3 min-h-[32px] rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-semibold"
              >
                <Share2 class="w-3.5 h-3.5" />
                <span>{{ t('今日打卡完成 · 晒 PK 卡', 'Done · Share PK') }}</span>
              </button>
            </div>
          </div>
        </template>
      </div>

      <!-- Right: Personal Calibration Rank & Rewards -->
      <div
        class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-3.5 sm:p-4 space-y-2.5 shadow-xs flex flex-col justify-between"
        :class="sprintQuestions.length > 0 ? 'lg:col-span-5' : 'lg:col-span-12'"
        data-testid="personal-arena-profile"
      >
        <div class="flex items-center justify-between gap-2">
          <div class="flex items-center gap-1.5 font-bold text-slate-900 dark:text-white text-[13.5px]">
            <Award class="w-4 h-4 text-amber-500 shrink-0" :stroke-width="2" />
            <span>{{ t('我的校准战绩与站内特权', 'My Calibration Rank & Perks') }}</span>
          </div>
          <span v-if="seasonKey" class="px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-800 font-mono text-[10.5px] text-slate-500">
            {{ seasonKey }} 赛季
          </span>
        </div>

        <template v-if="isLoggedIn && arenaProfile">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div>
              <span class="px-2.5 py-0.5 rounded-full bg-amber-500/15 text-amber-700 dark:text-amber-300 font-bold text-xs">
                {{ arenaProfile.rank_tier || '见习观察员' }}
              </span>
              <span class="ml-2 text-slate-500 tabular-nums">
                {{ t(`洞察分 ${arenaProfile.insight_points}`, `${arenaProfile.insight_points} Pts`) }}
              </span>
            </div>
            <div class="font-mono text-slate-700 dark:text-slate-200 tabular-nums">
              {{
                arenaProfile.settled_count > 0
                  ? t(`胜率 ${arenaProfile.hit_rate_pct ?? 0}% · 连胜 ${arenaProfile.current_streak}`, `Win ${arenaProfile.hit_rate_pct ?? 0}% · Streak ${arenaProfile.current_streak}`)
                  : t('首场结算后解锁胜率', 'Win rate unlocks after 1st settle')
              }}
            </div>
          </div>
          <div class="grid grid-cols-2 gap-2 text-[11px]">
            <div class="rounded-xl bg-[#F5F5F7] dark:bg-slate-800/80 px-2.5 py-2">
              <div class="text-slate-500">{{ t('连胜 / 前30% AI额度奖励', 'Streak / Top 30% AI Bonus') }}</div>
              <div class="font-bold text-[#007AFF] dark:text-[#0A84FF] mt-0.5">
                {{ arenaProfile.bonus_qa_quota > 0 ? `+${arenaProfile.bonus_qa_quota} 次/日（7天有效）` : t('3 连胜或月榜前 30% 解锁 +10', '3-streak unlocks +10/day') }}
              </div>
            </div>
            <div class="rounded-xl bg-[#F5F5F7] dark:bg-slate-800/80 px-2.5 py-2">
              <div class="text-slate-500">{{ t('荣誉邀请码配额加成', 'Invite Quota Unlocked') }}</div>
              <div class="font-bold text-emerald-600 dark:text-emerald-400 mt-0.5">
                {{ arenaProfile.unlocked_referral_bonus > 0 ? `+${arenaProfile.unlocked_referral_bonus} 枚额外邀请码` : t('升至趋势捕手解锁 +2 枚', 'Tier 2 unlocks +2 invites') }}
              </div>
            </div>
          </div>
        </template>
        <template v-else>
          <p class="text-slate-600 dark:text-slate-300 leading-relaxed">
            {{ t('登录后自动累积每月洞察分、连胜记录与 Brier 校准段位：3 连胜或进月榜前 30% 解锁 +10 次/日 AI 问答额度，出题采纳奖 +100 分与 +1 邀请码。', 'Sign in to earn monthly insight points & calibration tiers: 3-streak or Top 30% unlocks +10 daily AI Q&As and bonus invite codes.') }}
          </p>
          <button
            type="button"
            @click="emit('open-auth')"
            class="self-start px-3.5 py-1.5 rounded-xl bg-[#007AFF] hover:bg-[#0066D6] text-white font-semibold"
          >
            {{ t('登录绑定个人战绩', 'Sign In to Save Stats') }}
          </button>
        </template>
      </div>
    </div>

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
            {{ cleanPredText(publicNote) || t('纯智识荣誉激励，零资金充值或水评；每次预判均严格锁定到期前 30 分钟封盘与不可篡改核验。', 'Zero cash, zero open comments. Strict 30-min lock before settlement & objective calibration.') }}
          </p>
        </div>

        <div class="flex flex-wrap items-center gap-1.5 text-xs">
          <button
            type="button"
            @click="showNewForm = !showNewForm"
            class="inline-flex items-center gap-1 px-3 min-h-[32px] rounded-xl sm:rounded-lg bg-blue-600 text-white font-semibold hover:bg-blue-700 whitespace-nowrap"
          >
            <Plus class="w-3.5 h-3.5" />
            <span>{{ t('新建', 'New') }}<span class="hidden sm:inline">{{ t('可验证假设 / 共创投稿', ' Hypothesis') }}</span></span>
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
          {{ t('① 越早预判倍率越高（1.5× / 1.2× / 1.0×），并在到期前 30 分钟自动封盘防作弊；② 到期由行情或一手官宣客观结算，Brier 误差越近 0 洞察分越高、击败镜信 AI 再加 +20 分；③ 零现金玩法，连胜与高段位解锁 AI 证据问答扩容及共创荣誉署名。', '1) Early forecasts earn 1.5x/1.2x multipliers and lock 30m before due; 2) Resolved objectively via market quotes or primary filings; 3) Non-monetary insight points unlock AI Q&A quota bonuses.') }}
        </p>
      </div>

      <!-- Mobile Collapsible Overview Bar (< sm) -->
      <button
        type="button"
        @click="summaryOpenMobile = !summaryOpenMobile"
        class="sm:hidden w-full rounded-xl border border-slate-200 dark:border-slate-700 bg-[#F5F5F7] dark:bg-slate-800/80 px-3 py-2 flex items-center justify-between gap-2 text-xs text-left"
      >
        <span class="font-semibold text-slate-800 dark:text-slate-100 truncate tabular-nums">
          {{
            liveBoard.liveSettledDecisive > 0
              ? t(`验证战绩（进行中 ${stats.live.openCount} · 已结 ${liveBoard.liveSettledDecisive}）`, `Summary (${stats.live.openCount} Open · ${liveBoard.liveSettledDecisive} Settled)`)
              : t(`月度赛季榜单 & 战绩总览（进行中 ${stats.live.openCount}）`, `Leaderboard & Stats (${stats.live.openCount} Open)`)
          }}
        </span>
        <ChevronDown class="w-4 h-4 text-slate-500 shrink-0 transition-transform" :class="{ 'rotate-180': summaryOpenMobile }" />
      </button>

      <!-- Dual Calibration Cards + Monthly Season Leaderboard -->
      <div :class="summaryOpenMobile ? 'block space-y-3' : 'hidden sm:block space-y-3'">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
          <div class="rounded-xl bg-emerald-500/8 dark:bg-emerald-400/10 p-3 space-y-1">
            <div class="flex items-start justify-between gap-2">
              <span class="font-bold text-emerald-800 dark:text-emerald-200 min-w-0">{{ t('实时公开追踪验证', 'Live Public Tracking') }}</span>
              <span v-if="liveBoard.unlocked && stats.live.decisiveHitRatePct !== null" class="font-mono text-emerald-700 dark:text-emerald-300 font-semibold shrink-0 whitespace-nowrap">
                {{ t(`真实胜率 ${stats.live.decisiveHitRatePct}%`, `Win Rate ${stats.live.decisiveHitRatePct}%`) }}
              </span>
              <span v-else class="text-[11px] text-zinc-500 dark:text-zinc-400 shrink-0 whitespace-nowrap">
                {{ t(`进行中 (${stats.live.openCount} 题)`, `Tracking (${stats.live.openCount} open)`) }}
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
                <span>{{ t(`Brier 误差 ${stats.live.brierScore}`, `Brier ${stats.live.brierScore}`) }}</span>
              </template>
            </div>
          </div>

          <div class="ios-surface-2 p-3 space-y-1">
            <div class="flex items-start justify-between gap-2">
              <span class="font-bold text-zinc-800 dark:text-zinc-200 min-w-0">{{ t('历史复盘对照（独立存档，不计入榜单）', 'Historical Replay (Excluded from Ranking)') }}</span>
              <span class="text-[11px] text-zinc-500 dark:text-zinc-400 shrink-0 whitespace-nowrap">
                {{ t(`${stats.replay.total} 题样题`, `${stats.replay.total} Cases`) }}
              </span>
            </div>
            <div class="text-zinc-600 dark:text-zinc-400">
              {{ t(`已核验 ${liveBoard.replaySettledDecisive} 题历史事件回放；仅用于复盘波动基准。`, `${liveBoard.replaySettledDecisive} historical replays archived separately.`) }}
            </div>
          </div>
        </div>

        <!-- Monthly User Calibration Leaderboard (Top 20) -->
        <div
          v-if="(arenaLeaderboard?.length || 0) > 0"
          class="rounded-xl border border-amber-200/80 dark:border-amber-800/70 bg-amber-50/40 dark:bg-amber-950/15 p-3 space-y-2 text-xs"
          data-testid="season-user-leaderboard"
        >
          <div class="flex items-center justify-between gap-2">
            <div class="flex items-center gap-1.5 font-bold text-slate-900 dark:text-white">
              <Trophy class="w-4 h-4 text-amber-500" />
              <span>{{ t(`${seasonKey || ''} 月度先知榜（Top 30% 获 +10 次 AI 问答加成）`, 'Monthly Calibration Leaderboard') }}</span>
            </div>
            <button
              type="button"
              @click="arenaBoardOpen = !arenaBoardOpen"
              class="text-[11px] text-slate-500 hover:text-slate-800 dark:hover:text-white"
            >
              {{ arenaBoardOpen ? t('收起', 'Hide') : t('展开', 'Show') }}
            </button>
          </div>
          <div v-if="arenaBoardOpen" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
            <div
              v-for="row in (arenaLeaderboard || []).slice(0, 9)"
              :key="`lb-u-${row.user_id}`"
              class="rounded-lg bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 px-2.5 py-2 flex items-center justify-between gap-2"
            >
              <div class="flex items-center gap-2 min-w-0">
                <span class="font-mono font-bold text-slate-400 w-4 text-center shrink-0">#{{ row.rank }}</span>
                <UserAvatar :avatar="row.avatar" :username="row.username" size="xs" />
                <div class="min-w-0">
                  <div class="font-semibold text-slate-800 dark:text-slate-100 truncate">
                    {{ row.display_name || row.username }}
                  </div>
                  <div class="text-[10.5px] text-slate-500 truncate">
                    {{ row.rank_tier }} · {{ row.hit_rate_pct != null ? `胜率 ${row.hit_rate_pct}%` : '追踪中' }}
                  </div>
                </div>
              </div>
              <div class="text-right shrink-0">
                <div class="font-mono font-bold text-amber-600 dark:text-amber-400">{{ row.insight_points }}分</div>
                <div v-if="row.current_streak > 0" class="text-[10px] text-emerald-600 dark:text-emerald-400 font-semibold">
                  {{ row.current_streak }} 连胜
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Public Prediction Accuracy Leaderboard (Domain Live-only & >= 5 threshold) -->
        <div
          v-if="showLeaderboard"
          class="rounded-xl border border-indigo-200/80 dark:border-indigo-800/70 bg-indigo-50/40 dark:bg-indigo-950/20 p-3 space-y-2 text-xs"
          data-testid="prediction-leaderboard"
        >
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="flex items-center gap-1.5 font-bold text-slate-900 dark:text-white">
              <Flame class="w-4 h-4 text-indigo-500" />
              <span>{{ t('领域基准公开校准率榜（Live 模式）', 'Live Domain Accuracy Leaderboard') }}</span>
            </div>
            <button
              v-if="liveBoard.unlocked"
              type="button"
              @click="copyLeaderboardUrl"
              class="inline-flex items-center gap-1 px-2.5 min-h-[28px] rounded-lg border border-indigo-200 dark:border-indigo-700 bg-white dark:bg-slate-900 text-[11px] font-medium text-indigo-700 dark:text-indigo-300 hover:bg-indigo-50"
            >
              <Share2 class="w-3 h-3" />
              <span>{{ leaderboardCopied ? t('已复制公开榜链接', 'Copied') : t('分享公开胜率榜', 'Share Leaderboard') }}</span>
            </button>
          </div>

          <div
            v-if="!liveBoard.unlocked"
            class="rounded-lg bg-white/85 dark:bg-slate-900/80 border border-indigo-200/70 dark:border-indigo-900/60 px-3 py-2 text-slate-600 dark:text-slate-300"
          >
            {{
              t(
                `实时胜率统计积累中 (${liveBoard.liveSettledDecisive}/5，待到期官方核验解锁分领域榜单)。`,
                `Accumulating live sample (${liveBoard.liveSettledDecisive}/5 live settled needed to unlock domain leaderboard).`,
              )
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
                  {{ t(`样本 ${row.totalLive} · 已决 ${row.settledDecisive} · 命中 ${row.correct}`, `${row.totalLive} live · ${row.settledDecisive} settled · ${row.correct} won`) }}
                </div>
              </div>
              <div class="text-right shrink-0">
                <div class="font-mono font-bold text-sm" :class="row.hitPct !== null && row.hitPct >= 60 ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-700 dark:text-slate-200'">
                  {{ row.hitPct !== null ? `${row.hitPct}%` : t('待核验', 'Pending') }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Create / Community Proposal Form -->
      <form
        v-if="showNewForm"
        @submit.prevent="submitNew"
        class="pt-3 border-t border-slate-200 dark:border-slate-800 space-y-2.5 text-xs"
      >
        <div class="grid grid-cols-1 sm:grid-cols-12 gap-2">
          <input v-model="fTitle" type="text" required :placeholder="t('假设标题，如 本周内是否公布新关税豁免清单', 'Hypothesis title')" class="sm:col-span-4 h-9 px-3 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-white" />
          <input v-model="fEntity" type="text" :placeholder="t('目标主体 (如 NVDA / A股)', 'Entity (e.g. NVDA)')" class="sm:col-span-2 h-9 px-2.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-white" />
          <select v-model="fCategory" :aria-label="t('赛道分类', 'Category')" class="sm:col-span-2 h-9 px-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-white">
            <option value="market">{{ t('股市与大宗', 'Markets') }}</option>
            <option value="tech_ai">{{ t('科技与 AI', 'Tech & AI') }}</option>
            <option value="macro">{{ t('宏观与央行', 'Macro & Fed') }}</option>
            <option value="global_space">{{ t('国际与航天', 'Global') }}</option>
          </select>
          <select v-model="fMode" :aria-label="t('预测模式', 'Prediction mode')" class="sm:col-span-2 h-9 px-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-white">
            <option value="live">{{ t('实时追踪', 'Live') }}</option>
            <option value="replay">{{ t('历史复盘', 'Review') }}</option>
          </select>
          <input v-model.number="fProb" type="number" min="5" max="95" :aria-label="t('初始概率百分比', 'Initial probability (%)')" class="sm:col-span-2 h-9 px-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-white" />
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-12 gap-2">
          <input v-model="fQuestion" type="text" required :placeholder="t('具体可检验问题（谁/什么指标/何时前）', 'Falsifiable question (who/metric/deadline)')" class="sm:col-span-5 h-9 px-3 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-white" />
          <input v-model="fDueAt" type="datetime-local" :aria-label="t('到期时间', 'Due date')" class="sm:col-span-3 h-9 px-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-white" />
          <input v-model="fJudg" type="text" :placeholder="t('v1 初始判断结论', 'Initial v1 judgment')" class="sm:col-span-4 h-9 px-2.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-white" />
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <input v-model="fWin" type="text" :placeholder="t('判赢客观规则 (可选)', 'Win criteria (optional)')" class="h-9 px-2.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-white" />
          <input v-model="fLose" type="text" :placeholder="t('判输/证伪触发条件 (可选)', 'Falsification criteria (optional)')" class="h-9 px-2.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-white" />
        </div>

        <label
          v-if="fMode === 'live' && props.predictionProposalsEnabled !== false"
          class="inline-flex items-center gap-2 text-xs text-indigo-700 dark:text-indigo-300 font-medium cursor-pointer"
          data-testid="submit-to-arena-checkbox"
        >
          <input v-model="submitToArenaPool" type="checkbox" class="rounded text-indigo-600" />
          <span>{{ t('同时投稿至全站预测池（审核上架奖 +100 洞察分与出题官徽章，并赠 +1 邀请码）', 'Also propose to Global Arena Pool (+100 pts, author badge & +1 invite if approved)') }}</span>
        </label>

        <div class="flex flex-wrap items-center gap-2">
          <button type="submit" class="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-emerald-600 text-white font-semibold hover:bg-emerald-700">
            <Send class="w-3.5 h-3.5" />
            <span>{{ t('提交建立预测', 'Submit Prediction') }}</span>
          </button>
        </div>
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
        :id="`pred-card-${rec.prediction_id}`"
        class="rounded-xl border bg-white dark:bg-slate-900 p-3.5 sm:p-4 flex flex-col justify-between gap-3"
        :class="incomingPkChallenge?.predId === rec.prediction_id ? 'border-[#007AFF] ring-2 ring-[#007AFF]/25' : 'border-slate-200 dark:border-slate-800'"
      >
        <div class="space-y-3">
          <!-- Section 1: Question Header + Source Type + Lock Countdown + Early Multiplier -->
          <div class="flex flex-wrap items-center justify-between gap-2 text-xs">
            <div class="flex flex-wrap items-center gap-1.5">
              <span
                class="px-2 py-0.5 rounded-md font-semibold"
                :class="
                  rec.source_type === 'auto_market'
                    ? 'bg-blue-500/12 text-blue-700 dark:text-blue-300'
                    : rec.source_type === 'user_proposal'
                      ? 'bg-violet-500/12 text-violet-700 dark:text-violet-300'
                      : rec.mode === 'live'
                        ? 'bg-emerald-500/12 text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-300'
                        : 'bg-zinc-500/12 text-zinc-700 dark:bg-zinc-400/15 dark:text-zinc-300'
                "
              >
                {{
                  rec.source_type === 'auto_market'
                    ? t('每日行情日赛', 'Daily Market')
                    : rec.source_type === 'user_proposal'
                      ? t('用户共创', 'Community')
                      : rec.mode === 'live'
                        ? t('实时追踪', 'Live')
                        : t('历史复盘', 'Review')
                }}
              </span>
              <span
                class="px-2 py-0.5 rounded font-semibold inline-flex items-center gap-1"
                :class="rec.settlement?.outcome === 'correct'
                  ? 'bg-emerald-600 text-white'
                  : rec.settlement?.outcome === 'incorrect'
                    ? 'bg-red-600 text-white'
                    : rec.settlement?.outcome === 'indeterminate'
                      ? 'bg-amber-600 text-white'
                      : isRecLocked(rec)
                        ? 'bg-amber-500/15 text-amber-800 dark:text-amber-300'
                        : 'bg-blue-50 text-blue-800 dark:bg-blue-950/60 dark:text-blue-200'"
              >
                <Lock v-if="isRecLocked(rec) && !rec.settlement" class="w-3 h-3" />
                <span>
                  {{
                    rec.settlement
                      ? rec.settlement.outcome === 'correct'
                        ? t('已核验：达成', 'Settled: Yes')
                        : rec.settlement.outcome === 'incorrect'
                          ? t('已核验：未达', 'Settled: No')
                          : t('已核验：延期/作废', 'Settled: Void')
                      : isRecLocked(rec)
                        ? t('已封盘 · 等待客观结算', 'Locked · Awaiting Settlement')
                        : t('进行中 · 可投票', 'Open')
                  }}
                </span>
              </span>
              <span
                v-if="!isRecLocked(rec) && rec.mode === 'live'"
                class="px-1.5 py-0.5 rounded bg-amber-500/12 text-amber-700 dark:text-amber-300 font-mono text-[11px] font-bold"
              >
                {{ t(`早鸟 ${getEarlyMultiplier(rec)}×`, `${getEarlyMultiplier(rec)}x`) }}
              </span>
              <span
                v-if="rec.proposer_username"
                class="px-2 py-0.5 rounded bg-violet-500/10 text-violet-700 dark:text-violet-300 text-[11px] font-semibold"
              >
                本题由 @{{ rec.proposer_username }} 提出
              </span>
            </div>
            <span class="text-slate-500 tabular-nums text-[11px] inline-flex items-center gap-1">
              <Clock class="w-3 h-3" />
              <span>{{ formatLockCountdown(rec) || formatDueCountdown(rec.due_at) }}</span>
              <span class="opacity-65">(<SmartTime :iso="rec.due_at" :now-ms="effectiveNowMs" />)</span>
            </span>
          </div>

          <div>
            <h3 class="text-sm sm:text-base font-bold text-slate-900 dark:text-white leading-snug">{{ cleanPredText(pickBiText(rec.title, (rec as any).title_en)) }}</h3>
            <p class="text-xs text-slate-600 dark:text-slate-300 mt-1 leading-relaxed">{{ cleanPredText(pickBiText(rec.question, (rec as any).question_en)) }}</p>
          </div>

          <!-- Section 2: Human Crowd VS MirrorBrief AI Confrontation Bar -->
          <div class="rounded-lg bg-slate-50 dark:bg-slate-800/60 p-2.5 border border-slate-200/80 dark:border-slate-700/80 space-y-2 text-xs">
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div class="flex items-center gap-2 font-semibold text-slate-800 dark:text-slate-100">
                <Users class="w-3.5 h-3.5 text-[#007AFF] shrink-0" />
                <span>{{ t('人类众筹 VS 镜信 AI', 'Human Crowd VS MirrorBrief AI') }}</span>
                <span
                  v-if="humanVsAiOutcome(rec) === 'human_win'"
                  class="px-2 py-0.5 rounded-full bg-emerald-600 text-white text-[10px] font-bold"
                >
                  {{ t('战报：人类共识击败 AI', 'Humans Beat AI') }}
                </span>
                <span
                  v-else-if="humanVsAiOutcome(rec) === 'ai_win'"
                  class="px-2 py-0.5 rounded-full bg-amber-600 text-white text-[10px] font-bold"
                >
                  {{ t('战报：镜信 AI 获胜', 'AI Won') }}
                </span>
              </div>
              <div class="flex items-center gap-2 font-mono text-[11.5px] tabular-nums">
                <span class="text-[#007AFF] dark:text-[#64D2FF] font-bold">
                  {{
                    props.crowdStats?.[rec.prediction_id]?.unlocked && props.crowdStats?.[rec.prediction_id]?.crowd_avg_pct != null
                      ? `人类 ${props.crowdStats[rec.prediction_id].crowd_avg_pct}%`
                      : `人类 ${props.crowdStats?.[rec.prediction_id]?.vote_count || 0}/${minVotesForRec(rec.prediction_id)}票解锁`
                  }}
                </span>
                <span class="text-slate-400">VS</span>
                <span class="text-amber-600 dark:text-amber-400 font-bold">
                  AI {{ Math.round(rec.probability_pct) }}%
                </span>
              </div>
            </div>

            <!-- Confrontation Visual Progress Track -->
            <div class="relative h-2.5 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden">
              <div
                v-if="props.crowdStats?.[rec.prediction_id]?.unlocked && props.crowdStats?.[rec.prediction_id]?.crowd_avg_pct != null"
                class="h-full rounded-full bg-[#007AFF] transition-all"
                :style="{ width: `${Math.min(100, Math.max(4, props.crowdStats[rec.prediction_id].crowd_avg_pct || 50))}%` }"
              />
              <div
                v-else
                class="h-full rounded-full bg-amber-400/75 transition-all"
                :style="{ width: `${Math.min(100, Math.round(((props.crowdStats?.[rec.prediction_id]?.vote_count || 0) / minVotesForRec(rec.prediction_id)) * 100))}%` }"
              />
              <div
                class="absolute top-0 bottom-0 w-1 bg-amber-600 dark:bg-amber-400"
                :style="{ left: `${Math.min(98, Math.max(2, rec.probability_pct))}%` }"
                :title="`AI ${rec.probability_pct}%`"
              />
            </div>

            <!-- Crowd Consensus Interactive Submission Panel (Enforces Lock!) -->
            <div
              v-if="rec.mode === 'live' && !rec.settlement"
              class="pt-2 mt-1 border-t border-slate-200/70 dark:border-slate-700/70 space-y-2"
              data-testid="crowd-consensus-panel"
            >
              <div
                v-if="isRecLocked(rec)"
                class="rounded-lg bg-amber-500/12 border border-amber-500/30 px-2.5 py-2 flex items-center justify-between gap-2 text-[11.5px] font-semibold text-amber-800 dark:text-amber-200"
                data-testid="prediction-locked-notice"
              >
                <span class="inline-flex items-center gap-1.5">
                  <Lock class="w-3.5 h-3.5 shrink-0" />
                  <span>{{ t('已封盘 · 等待客观结算（禁止继续新投票）', 'Locked — Awaiting Objective Settlement') }}</span>
                </span>
                <span v-if="props.crowdStats?.[rec.prediction_id]?.user_prob_pct != null" class="font-mono">
                  {{ t(`我的锁定押注 ${props.crowdStats[rec.prediction_id].user_prob_pct}%`, `Locked ${props.crowdStats[rec.prediction_id].user_prob_pct}%`) }}
                </span>
              </div>

              <template v-else>
                <div class="flex flex-wrap items-center gap-2 pt-0.5">
                  <div class="flex items-center gap-1">
                    <button
                      v-for="pctBtn in [20, 50, 80]"
                      :key="`c-pct-${rec.prediction_id}-${pctBtn}`"
                      type="button"
                      @click="setVoteDraft(rec.prediction_id, pctBtn)"
                      class="px-1.5 py-0.5 rounded font-mono text-[10.5px] font-bold border"
                      :class="getVoteDraft(rec) === pctBtn ? 'bg-[#007AFF] text-white border-[#007AFF]' : 'bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300'"
                    >
                      {{ pctBtn }}%
                    </button>
                  </div>
                  <input
                    type="range"
                    min="5"
                    max="95"
                    step="5"
                    :disabled="isRecLocked(rec)"
                    :value="getVoteDraft(rec)"
                    @input="setVoteDraft(rec.prediction_id, Number(($event.target as HTMLInputElement).value))"
                    :aria-label="t('我的概率预判滑块', 'My probability slider')"
                    class="flex-1 min-w-[100px] accent-[#007AFF] cursor-pointer disabled:opacity-50"
                  />
                  <span class="font-mono text-[11px] font-bold text-slate-700 dark:text-slate-200 w-9 text-right tabular-nums">
                    {{ getVoteDraft(rec) }}%
                  </span>
                  <button
                    type="button"
                    :disabled="isRecLocked(rec)"
                    @click="triggerVoteClick(rec)"
                    class="jx-pop-target px-2.5 min-h-[28px] rounded-lg bg-[#007AFF] text-white text-[11px] font-semibold hover:bg-blue-600 whitespace-nowrap transition-transform disabled:opacity-50 disabled:cursor-not-allowed"
                    :class="voteBurstPid === rec.prediction_id ? 'jx-pop-active jx-burst-ring' : ''"
                  >
                    {{ props.crowdStats?.[rec.prediction_id]?.user_prob_pct != null ? t('更新押注', 'Update') : t('提交预判', 'Submit') }}
                  </button>
                </div>

                <!-- Structured Reason Tag Selector (0 UGC moderation risk) -->
                <div class="flex flex-wrap items-center gap-1 text-[10.5px]">
                  <span class="text-slate-500 mr-0.5">{{ t('判断依据(选点)：', 'Reason:') }}</span>
                  <button
                    v-for="tag in reasonTagsList"
                    :key="`rtag-${rec.prediction_id}-${tag}`"
                    type="button"
                    @click="toggleReasonDraft(rec.prediction_id, tag)"
                    class="px-2 py-0.5 rounded-full border transition-colors"
                    :class="
                      getReasonDraft(rec) === tag
                        ? 'bg-slate-900 text-white border-slate-900 dark:bg-blue-600 dark:border-blue-600'
                        : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:border-blue-400'
                    "
                  >
                    {{ tag }}
                  </button>
                </div>
              </template>

              <!-- Bull vs Bear Top Reason Tags Distribution -->
              <div
                v-if="
                  (props.crowdStats?.[rec.prediction_id]?.reason_breakdown?.bull_top?.length || 0) > 0 ||
                  (props.crowdStats?.[rec.prediction_id]?.reason_breakdown?.bear_top?.length || 0) > 0
                "
                class="flex flex-wrap items-center gap-2 text-[10.5px] text-slate-600 dark:text-slate-300"
              >
                <span v-if="(props.crowdStats?.[rec.prediction_id]?.reason_breakdown?.bull_top?.length || 0) > 0" class="text-rose-600 dark:text-rose-400">
                  看多逻辑：{{ props.crowdStats![rec.prediction_id].reason_breakdown!.bull_top.slice(0, 2).map((x) => `${x.tag}(${x.count})`).join(' · ') }}
                </span>
                <span v-if="(props.crowdStats?.[rec.prediction_id]?.reason_breakdown?.bear_top?.length || 0) > 0" class="text-emerald-600 dark:text-emerald-400">
                  看空逻辑：{{ props.crowdStats![rec.prediction_id].reason_breakdown!.bear_top.slice(0, 2).map((x) => `${x.tag}(${x.count})`).join(' · ') }}
                </span>
              </div>

              <div class="flex flex-wrap items-center justify-between gap-2 pt-0.5 text-[11px]">
                <span
                  v-if="!isLoggedIn && props.guestStagedVotes?.[rec.prediction_id] !== undefined"
                  class="px-2 py-0.5 rounded-md bg-blue-500/12 text-[#007AFF] dark:text-[#0A84FF] font-semibold tabular-nums"
                  data-testid="guest-staged-vote-pill"
                >
                  {{ t(`已暂存你的预判：${props.guestStagedVotes[rec.prediction_id]}% · 登录后计入胜率战绩`, `Staged: ${props.guestStagedVotes[rec.prediction_id]}% · Sign in to lock record`) }}
                </span>
                <span v-else-if="props.crowdStats?.[rec.prediction_id]?.user_prob_pct != null" class="text-emerald-600 dark:text-emerald-400 font-semibold tabular-nums">
                  {{
                    t(
                      `已锁定 ${props.crowdStats[rec.prediction_id].user_prob_pct}%${props.crowdStats[rec.prediction_id].user_early_multiplier ? ` (${props.crowdStats[rec.prediction_id].user_early_multiplier}×倍率)` : ''}`,
                      `Locked: ${props.crowdStats[rec.prediction_id].user_prob_pct}%`,
                    )
                  }}
                </span>
                <span v-else class="text-slate-400">{{ t('拖动滑块参与预判对赌', 'Slide to forecast') }}</span>

                <div class="flex items-center gap-1.5">
                  <button
                    type="button"
                    @click="copyPkLink(rec)"
                    class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:border-[#007AFF]/40 whitespace-nowrap"
                  >
                    <Check v-if="pkCopiedPid === rec.prediction_id" class="w-3 h-3 text-emerald-500" />
                    <Copy v-else class="w-3 h-3" />
                    <span>{{ pkCopiedPid === rec.prediction_id ? t('已复制 PK 链接', 'Copied') : t('复制 PK 链接', 'Copy PK Link') }}</span>
                  </button>
                  <button
                    type="button"
                    @click="emit('open-share-pk', { rec, probPct: getVoteDraft(rec) })"
                    class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-indigo-600 text-white font-semibold hover:bg-indigo-700 whitespace-nowrap"
                  >
                    <Share2 class="w-3 h-3" />
                    <span>{{ t('生成 PK 卡', 'PK Poster') }}</span>
                  </button>
                </div>
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

          <!-- Prediction Research Assistant: Live Quote + Matched News + Transmission + AI Q&A -->
          <div class="rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-200/80 dark:border-slate-700/80 text-xs overflow-hidden">
            <div class="px-2.5 py-2 flex flex-wrap items-center justify-between gap-2">
              <button
                type="button"
                @click="toggleResearchExpand(rec.prediction_id)"
                class="inline-flex items-center gap-1.5 min-w-0 text-left hover:text-[#007AFF] dark:hover:text-[#64D2FF]"
                :aria-expanded="expandedResearchIds.has(rec.prediction_id)"
              >
                <LineChart class="w-3.5 h-3.5 text-[#007AFF] shrink-0" />
                <span class="font-semibold text-slate-800 dark:text-slate-100 shrink-0">
                  {{ t('辅助研判 · 关联情报与行情数据', 'Research Context · News & Quotes') }}
                </span>
                <span
                  v-if="buildPredictionResearchPack(rec).liveQuote"
                  class="px-1.5 py-0.5 rounded bg-blue-500/12 text-[#007AFF] dark:text-[#64D2FF] font-mono text-[10.5px] tabular-nums"
                >
                  {{ buildPredictionResearchPack(rec).liveQuote!.ticker }}
                  {{ buildPredictionResearchPack(rec).liveQuote!.price }}
                  <template v-if="buildPredictionResearchPack(rec).targetGapPct !== null">
                    ({{ buildPredictionResearchPack(rec).targetGapPct! >= 0 ? '+' : '' }}{{ buildPredictionResearchPack(rec).targetGapPct }}%)
                  </template>
                </span>
                <span v-else class="text-[11px] text-slate-500 dark:text-slate-400">
                  {{
                    t(
                      `关联 ${buildPredictionResearchPack(rec).matchedEvents.length} 要闻 · ${buildPredictionResearchPack(rec).matchedImpacts.length} 传导`,
                      `${buildPredictionResearchPack(rec).matchedEvents.length} news · ${buildPredictionResearchPack(rec).matchedImpacts.length} markets`,
                    )
                  }}
                </span>
                <component :is="expandedResearchIds.has(rec.prediction_id) ? ChevronDown : ChevronRight" class="w-3.5 h-3.5 text-slate-400 shrink-0" />
              </button>

              <div class="flex flex-wrap items-center gap-1.5 ml-auto">
                <button
                  type="button"
                  @click="emit('open-qa-prediction', rec)"
                  class="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-white dark:bg-slate-900 border border-blue-200 dark:border-blue-800 text-[#007AFF] dark:text-[#64D2FF] font-semibold hover:bg-blue-50 dark:hover:bg-blue-950/30 whitespace-nowrap"
                >
                  <MessageSquareText class="w-3 h-3" />
                  <span>{{ t('问 AI 证据', 'Ask AI') }}</span>
                </button>
                <button
                  type="button"
                  @click="emit('open-finance-search', buildPredictionResearchPack(rec).primaryKeyword)"
                  class="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 font-medium hover:border-[#007AFF]/40 whitespace-nowrap"
                >
                  <TrendingUp class="w-3 h-3 text-amber-500" />
                  <span>{{ t('去股市传导分析', 'Markets Map') }}</span>
                </button>
                <button
                  type="button"
                  @click="toggleResearchExpand(rec.prediction_id)"
                  class="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-slate-200/70 dark:bg-slate-700/70 text-slate-700 dark:text-slate-200 font-semibold hover:opacity-90 whitespace-nowrap"
                >
                  <BookOpen class="w-3 h-3" />
                  <span>{{ expandedResearchIds.has(rec.prediction_id) ? t('收起研判', 'Collapse') : t('展开数据', 'Expand') }}</span>
                </button>
              </div>
            </div>

            <div
              v-if="expandedResearchIds.has(rec.prediction_id)"
              class="px-3 pb-3 pt-2 border-t border-slate-200/70 dark:border-slate-700/70 space-y-2.5 bg-white/60 dark:bg-slate-900/40"
              data-testid="prediction-research-panel"
            >
              <!-- 1. Real-time Market Reference vs Threshold -->
              <div
                v-if="buildPredictionResearchPack(rec).liveQuote"
                class="rounded-lg bg-blue-50/70 dark:bg-blue-950/30 border border-blue-200/80 dark:border-blue-900/70 px-2.5 py-2 flex flex-wrap items-center justify-between gap-2 text-[11.5px]"
              >
                <div class="font-semibold text-slate-800 dark:text-slate-100">
                  {{ buildPredictionResearchPack(rec).liveQuote!.name || buildPredictionResearchPack(rec).liveQuote!.ticker }}
                  <span class="font-mono text-[#007AFF] dark:text-[#64D2FF] ml-1">
                    {{ buildPredictionResearchPack(rec).liveQuote!.price }}
                  </span>
                  <span
                    class="font-mono ml-1.5"
                    :class="Number(buildPredictionResearchPack(rec).liveQuote!.pct_change ?? 0) >= 0 ? 'text-rose-600 dark:text-rose-400' : 'text-emerald-600 dark:text-emerald-400'"
                  >
                    {{ Number(buildPredictionResearchPack(rec).liveQuote!.pct_change ?? 0) >= 0 ? '+' : '' }}{{ Number(buildPredictionResearchPack(rec).liveQuote!.pct_change ?? 0).toFixed(2) }}%
                  </span>
                </div>
                <div v-if="buildPredictionResearchPack(rec).refTarget !== null" class="text-slate-600 dark:text-slate-300 font-mono tabular-nums">
                  {{ t(`目标参考线：${buildPredictionResearchPack(rec).refTarget}`, `Threshold: ${buildPredictionResearchPack(rec).refTarget}`) }}
                  <span v-if="buildPredictionResearchPack(rec).targetGapPct !== null" class="ml-1 font-bold">
                    ({{ buildPredictionResearchPack(rec).targetGapPct! >= 0 ? t('已高于基准', 'Above') : t('仍低于基准', 'Below') }} {{ Math.abs(buildPredictionResearchPack(rec).targetGapPct!) }}%)
                  </span>
                </div>
              </div>

              <!-- 2. Core Assumption & Supporting / Opposing Bullets -->
              <div
                v-if="rec.core_assumption || buildPredictionResearchPack(rec).supporting.length > 0 || buildPredictionResearchPack(rec).opposing.length > 0"
                class="grid grid-cols-1 md:grid-cols-2 gap-2 text-[11.5px]"
              >
                <div v-if="buildPredictionResearchPack(rec).supporting.length > 0 || rec.core_assumption" class="rounded-lg bg-emerald-50/60 dark:bg-emerald-950/20 border border-emerald-200/70 dark:border-emerald-900/60 p-2 space-y-1">
                  <div class="font-bold text-emerald-800 dark:text-emerald-300">{{ t('正方核心依据与假设', 'Bullish Evidence & Thesis') }}</div>
                  <p v-if="rec.core_assumption" class="text-slate-700 dark:text-slate-200">{{ cleanPredText(rec.core_assumption) }}</p>
                  <ul v-if="buildPredictionResearchPack(rec).supporting.length > 0" class="list-disc pl-4 space-y-0.5 text-slate-600 dark:text-slate-300">
                    <li v-for="(s, sIdx) in buildPredictionResearchPack(rec).supporting" :key="sIdx">{{ cleanPredText(s) }}</li>
                  </ul>
                </div>
                <div v-if="buildPredictionResearchPack(rec).opposing.length > 0 || rec.invalidation_trigger" class="rounded-lg bg-rose-50/60 dark:bg-rose-950/20 border border-rose-200/70 dark:border-rose-900/60 p-2 space-y-1">
                  <div class="font-bold text-rose-800 dark:text-rose-300">{{ t('反方疑点与证伪条件', 'Bearish Risks & Invalidation') }}</div>
                  <p v-if="rec.invalidation_trigger" class="text-slate-700 dark:text-slate-200">{{ cleanPredText(rec.invalidation_trigger) }}</p>
                  <ul v-if="buildPredictionResearchPack(rec).opposing.length > 0" class="list-disc pl-4 space-y-0.5 text-slate-600 dark:text-slate-300">
                    <li v-for="(o, oIdx) in buildPredictionResearchPack(rec).opposing" :key="oIdx">{{ cleanPredText(o) }}</li>
                  </ul>
                </div>
              </div>

              <!-- 3. Matched In-Site Verified News Briefings -->
              <div v-if="buildPredictionResearchPack(rec).matchedEvents.length > 0" class="space-y-1.5">
                <div class="inline-flex items-center gap-1 font-bold text-slate-700 dark:text-slate-200 text-[11px]">
                  <Newspaper class="w-3.5 h-3.5 text-[#007AFF]" />
                  <span>{{ t('站内关联已核验要闻（点击弹窗精读后即可回来下注）', 'Related Verified News (Tap to read in overlay)') }}</span>
                </div>
                <div class="space-y-1.5">
                  <div
                    v-for="ev in buildPredictionResearchPack(rec).matchedEvents"
                    :key="`pr-ev-${rec.prediction_id}-${ev.event_id}`"
                    class="rounded-lg border border-slate-200/80 dark:border-slate-700/80 bg-white dark:bg-slate-900 p-2 flex items-start justify-between gap-2"
                  >
                    <div class="min-w-0 space-y-0.5">
                      <div class="font-semibold text-slate-900 dark:text-white leading-snug">
                        {{ pickBiText(ev.title_zh || ev.title, ev.title_en || ev.title) }}
                      </div>
                      <p class="text-[11px] text-slate-500 dark:text-slate-400 line-clamp-2">
                        {{ ev.fact_summary || ev.summary }}
                      </p>
                    </div>
                    <button
                      type="button"
                      @click="emit('jump-event', ev)"
                      class="px-2 py-1 rounded-md bg-[#007AFF]/10 text-[#007AFF] dark:text-[#64D2FF] text-[11px] font-semibold hover:bg-[#007AFF]/15 shrink-0 whitespace-nowrap"
                    >
                      {{ t('精读全文', 'Read') }}
                    </button>
                  </div>
                </div>
              </div>

              <!-- 4. Matched Market Transmission & Live Wire -->
              <div
                v-if="buildPredictionResearchPack(rec).matchedImpacts.length > 0 || buildPredictionResearchPack(rec).matchedWire.length > 0"
                class="grid grid-cols-1 md:grid-cols-2 gap-2"
              >
                <div
                  v-for="imp in buildPredictionResearchPack(rec).matchedImpacts"
                  :key="`pr-imp-${rec.prediction_id}-${imp.id}`"
                  class="rounded-lg border border-amber-200/70 dark:border-amber-900/60 bg-amber-50/40 dark:bg-amber-950/20 p-2 space-y-1 text-[11px]"
                >
                  <div class="flex items-center justify-between gap-1">
                    <span class="font-bold text-amber-800 dark:text-amber-300 truncate">{{ imp.tag }} · {{ imp.event_title }}</span>
                    <button
                      type="button"
                      @click="emit('open-finance-search', imp.tag || buildPredictionResearchPack(rec).primaryKeyword)"
                      class="text-[#007AFF] font-semibold shrink-0 hover:underline"
                    >
                      {{ t('查看传导', 'Impact') }}
                    </button>
                  </div>
                  <p class="text-slate-600 dark:text-slate-300 line-clamp-2">{{ imp.one_liner }}</p>
                </div>
                <div
                  v-for="wire in buildPredictionResearchPack(rec).matchedWire"
                  :key="`pr-w-${rec.prediction_id}-${wire.id}`"
                  class="rounded-lg border border-slate-200/80 dark:border-slate-700/80 bg-white dark:bg-slate-900 p-2 space-y-0.5 text-[11px]"
                >
                  <div class="font-semibold text-slate-800 dark:text-slate-100 line-clamp-1">{{ wire.title }}</div>
                  <div class="text-slate-500 dark:text-slate-400 flex items-center justify-between gap-2">
                    <span>{{ wire.source_name }}</span>
                    <SmartTime :iso="wire.published_at" :now-ms="effectiveNowMs" />
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div v-if="rec.settlement" class="rounded-lg bg-emerald-50/70 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-900 p-2.5 text-xs space-y-1">
            <div>
              <CheckCircle2 class="w-3.5 h-3.5 inline mr-1 text-emerald-700 dark:text-emerald-400" />
              <strong>{{ t('核验结论：', 'Resolution: ') }}</strong>{{ rec.settlement.note }}
            </div>
            <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-600 dark:text-slate-300">
              <span v-if="props.crowdStats?.[rec.prediction_id]?.user_points_awarded">
                {{ t(`本题获得 +${props.crowdStats[rec.prediction_id].user_points_awarded} 洞察分`, `+${props.crowdStats[rec.prediction_id].user_points_awarded} Insight Pts`) }}
              </span>
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
            </div>
          </div>

          <div v-if="settlingId === rec.prediction_id" class="p-3 rounded-xl border border-emerald-200 bg-emerald-50/50 dark:bg-emerald-950/30 space-y-2 text-xs">
            <div class="flex flex-wrap gap-2">
              <label class="inline-flex items-center gap-1"><input v-model="setOutcome" type="radio" value="correct" />{{ t('正确', 'Correct') }}</label>
              <label class="inline-flex items-center gap-1"><input v-model="setOutcome" type="radio" value="incorrect" />{{ t('错误', 'Incorrect') }}</label>
              <label class="inline-flex items-center gap-1"><input v-model="setOutcome" type="radio" value="indeterminate" />{{ t('不可判定', 'Indeterminate') }}</label>
            </div>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <input v-model="setUrl" type="url" :placeholder="t('结算证据 URL (可选)', 'Evidence URL')" class="px-2.5 py-1.5 rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900" />
              <input v-model="setNote" type="text" :placeholder="t('结算依据说明', 'Resolution rationale')" class="px-2.5 py-1.5 rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900" />
            </div>
            <div class="flex gap-2">
              <button type="button" @click="submitSettle(rec.prediction_id)" class="px-3 py-1 rounded bg-emerald-600 text-white font-semibold">{{ t('确认结算', 'Resolve') }}</button>
              <button type="button" @click="settlingId = null" class="px-3 py-1 rounded border border-slate-300">{{ t('取消', 'Cancel') }}</button>
            </div>
          </div>
        </div>

        <div class="pt-2 border-t border-slate-100 dark:border-slate-800 space-y-2 text-xs">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <!-- 1-Click Stance Vote -->
            <div v-if="rec.mode === 'live' && !rec.settlement" class="flex items-center gap-1">
              <button
                type="button"
                @click="triggerStanceClick(rec.prediction_id, 'agree')"
                class="jx-pop-target inline-flex items-center gap-1 px-2 min-h-[28px] rounded-lg border text-[11px] font-medium transition-all"
                :class="[
                  (getReactionSummary('prediction', rec.prediction_id).my_reaction || props.stances?.[rec.prediction_id]) === 'agree' ? 'bg-emerald-600 text-white border-emerald-600' : 'border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800',
                  stanceBurstKey === `${rec.prediction_id}:agree` ? 'jx-pop-active jx-burst-ring text-emerald-500' : '',
                ]"
              >
                <ThumbsUp class="w-3 h-3 shrink-0" :stroke-width="1.75" />
                <span>{{ t('赞同', 'Agree') }}</span>
                <span v-if="(getReactionSummary('prediction', rec.prediction_id).counts.agree || 0) > 0" class="font-mono text-[10px] opacity-85 tabular-nums">
                  {{ getReactionSummary('prediction', rec.prediction_id).counts.agree }}
                </span>
              </button>
              <button
                type="button"
                @click="triggerStanceClick(rec.prediction_id, 'disagree')"
                class="jx-pop-target inline-flex items-center gap-1 px-2 min-h-[28px] rounded-lg border text-[11px] font-medium transition-all"
                :class="[
                  (getReactionSummary('prediction', rec.prediction_id).my_reaction || props.stances?.[rec.prediction_id]) === 'disagree' ? 'bg-rose-600 text-white border-rose-600' : 'border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800',
                  stanceBurstKey === `${rec.prediction_id}:disagree` ? 'jx-pop-active jx-burst-ring text-rose-500' : '',
                ]"
              >
                <ThumbsDown class="w-3 h-3 shrink-0" :stroke-width="1.75" />
                <span>{{ t('反对', 'Disagree') }}</span>
                <span v-if="(getReactionSummary('prediction', rec.prediction_id).counts.disagree || 0) > 0" class="font-mono text-[10px] opacity-85 tabular-nums">
                  {{ getReactionSummary('prediction', rec.prediction_id).counts.disagree }}
                </span>
              </button>
              <button
                type="button"
                @click="triggerStanceClick(rec.prediction_id, 'neutral')"
                class="jx-pop-target inline-flex items-center gap-1 px-2 min-h-[28px] rounded-lg border text-[11px] font-medium transition-all"
                :class="[
                  (getReactionSummary('prediction', rec.prediction_id).my_reaction || props.stances?.[rec.prediction_id]) === 'neutral' ? 'bg-slate-800 text-white border-slate-800 dark:bg-blue-600 dark:border-blue-600' : 'border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800',
                  stanceBurstKey === `${rec.prediction_id}:neutral` ? 'jx-pop-active jx-burst-ring text-blue-500' : '',
                ]"
              >
                <Scale class="w-3 h-3 shrink-0" :stroke-width="1.75" />
                <span>{{ t('观望', 'Hold') }}</span>
                <span v-if="(getReactionSummary('prediction', rec.prediction_id).counts.neutral || 0) > 0" class="font-mono text-[10px] opacity-85 tabular-nums">
                  {{ getReactionSummary('prediction', rec.prediction_id).counts.neutral }}
                </span>
              </button>
            </div>

            <div
              v-if="isAdmin || rec.prediction_id.startsWith('pred_user_')"
              class="flex flex-wrap items-center gap-1.5 ml-auto"
            >
              <button
                v-if="rec.prediction_id.startsWith('pred_user_') || !rec.source_type || rec.source_type === 'seed'"
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
            <span v-else class="ml-auto text-[11px] text-slate-400">
              {{ rec.settlement ? t('已由系统客观核验结案', 'Settled objectively') : t('上方选择依据并提交概率', 'Pick reason & submit prob') }}
            </span>
          </div>

          <div
            v-if="getReactionSummary('prediction', rec.prediction_id).total > 0"
            class="h-1 rounded-full overflow-hidden flex bg-slate-100 dark:bg-slate-800"
          >
            <div
              class="bg-emerald-500 transition-all"
              :style="{ width: `${Math.round(((getReactionSummary('prediction', rec.prediction_id).counts.agree || 0) / getReactionSummary('prediction', rec.prediction_id).total) * 100)}%` }"
            />
            <div
              class="bg-rose-500 transition-all"
              :style="{ width: `${Math.round(((getReactionSummary('prediction', rec.prediction_id).counts.disagree || 0) / getReactionSummary('prediction', rec.prediction_id).total) * 100)}%` }"
            />
            <div
              class="bg-blue-500 transition-all"
              :style="{ width: `${Math.round(((getReactionSummary('prediction', rec.prediction_id).counts.neutral || 0) / getReactionSummary('prediction', rec.prediction_id).total) * 100)}%` }"
            />
          </div>
        </div>
      </article>
    </div>
  </section>
</template>
