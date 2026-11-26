<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BarChart3,
  Bell,
  CheckCircle2,
  Clock,
  Copy,
  Database,
  Eye,
  EyeOff,
  FileEdit,
  Globe,
  KeyRound,
  Lock,
  LogOut,
  Mail,
  MessageSquare,
  MonitorSmartphone,
  Pin,
  Plus,
  RefreshCw,
  RotateCcw,
  Search,
  Send,
  Shield,
  SlidersHorizontal,
  Smartphone,
  Ticket,
  Trash2,
  Users,
  X,
} from 'lucide-vue-next'
import AppShell from '../components/AppShell.vue'
import DialogDirtyGuard from '../components/DialogDirtyGuard.vue'
import UserAvatar from '../components/UserAvatar.vue'
import { useDialogBehavior } from '../core/dialog'
import { broadcastPresenceConfigChange, computeSimulatedOnlineCount } from '../core/presenceStore'
import {
  apiAdminApprovePredictionProposal,
  apiAdminApproveWaitlist,
  apiAdminAuditLogs,
  apiAdminContentList,
  apiAdminCreateInviteCodes,
  apiAdminCreateUser,
  apiAdminDeleteEditorialOverride,
  apiAdminDeleteFeedback,
  apiAdminFeedbackList,
  apiAdminGetPushConfig,
  apiAdminGetSiteSettings,
  apiAdminInviteCodes,
  apiAdminListDailyPredictions,
  apiAdminListPredictionProposals,
  apiAdminListWaitlist,
  apiAdminOverview,
  apiAdminPatchUser,
  apiAdminPushLogs,
  apiAdminPushTest,
  apiAdminRejectPredictionProposal,
  apiAdminRejectWaitlist,
  apiAdminRevealUserPassword,
  apiAdminRevokeInviteCode,
  apiAdminRunDailyPredictionCron,
  apiAdminSaveEditorialOverride,
  apiAdminSavePushConfig,
  apiAdminSaveSiteSettings,
  apiAdminSettleDailyPrediction,
  apiAdminSyncNow,
  apiAdminTraffic,
  apiAdminUpdateFeedback,
  apiAdminUserData,
  apiAdminUsers,
  apiLogin,
  clearAuthSession,
  isAdminRole,
  loadAuthSession,
  saveAuthSession,
  type AdminContentEventRow,
  type AdminContentWireRow,
  type AdminInviteCodeRow,
  type AdminOverviewResponse,
  type AdminPushConfig,
  type AdminTrafficResponse,
  type AdminUserRow,
  type AuthSession,
  type DailyPredictionRow,
  type FeedbackRecordItem,
  type GrowthStage,
  type PredictionProposalRow,
  type PublicSiteSettings,
  type SiteAccessMode,
  type UserRole,
  type WaitlistEntryRow,
} from '../core/auth'
import type { EditorialOverridesDoc } from '../core/overrides'
import { readDarkMode, writeDarkMode } from '../core/storage'
import { formatFriendlyBatchId } from '../core/time'

const isDark = ref(readDarkMode())
const session = ref<AuthSession | null>(loadAuthSession())
const activeTab = ref<'overview' | 'traffic' | 'feedback' | 'content' | 'users' | 'push' | 'audit'>('overview')

const loginUser = ref('admin')
const loginPass = ref('')
const authError = ref('')
const loading = ref(false)
const toast = ref('')

const overview = ref<AdminOverviewResponse | null>(null)
const users = ref<AdminUserRow[]>([])
const userSearch = ref('')
const auditLogs = ref<Record<string, unknown>[]>([])
const pushLogs = ref<Record<string, unknown>[]>([])
const pushConfig = ref<AdminPushConfig>({
  enabled: false,
  site_url: 'https://mirrorinfo.xyz',
  feishu_webhook: '',
  wecom_webhook: '',
  dingtalk_webhook: '',
  serverchan_sendkey: '',
  telegram_bot_token: '',
  telegram_chat_id: '',
  smtp_host: '',
  smtp_port: 465,
  smtp_user: '',
  smtp_pass: '',
  smtp_to: '',
  sms_webhook_url: '',
})

const siteSettingsForm = ref<PublicSiteSettings>({
  monitor_public: false,
  access_mode: 'invite_only',
  invite_required: true,
  login_required: false,
  feedback_enabled: true,
  feedback_notice: '欢迎反馈页面问题、数据纠错或功能建议，镜信编辑团队将尽快查阅并回复。',
  feedback_contact_wechat: '',
  feedback_contact_email: '',
  feedback_contact_group: '',
  feedback_contact_qr_url: '',
  feedback_daily_limit: 5,
  site_banner_enabled: false,
  site_banner_text: '',
  site_banner_tone: 'info',
  growth_stage: 'stage_1_cold_start',
  welcome_hero_enabled: true,
  soft_auth_prompts_enabled: true,
  guest_qa_daily_limit: 5,
  auth_qa_daily_limit: 30,
  crowd_vote_min_unlock: 3,
  user_referral_enabled: false,
  user_invite_quota: 3,
  referral_bonus_qa_quota: 15,
  invite_waitlist_enabled: false,
  prediction_daily_market_enabled: true,
  prediction_rewards_enabled: true,
  prediction_proposals_enabled: true,
  weekly_digest_enabled: true,
  weekly_digest_day: 0,
  weekly_digest_hour: 18,
  weekly_digest_minute: 0,
  online_counter_enabled: true,
  online_counter_mode: 'real',
  online_real_scope: 'all',
  online_sim_base: 68,
  online_sim_delta: 12,
  online_sim_interval_sec: 12,
  online_counter_label: '在线',
})

interface OnlineControlDraft {
  online_counter_enabled: boolean
  online_counter_mode: 'real' | 'simulated'
  online_real_scope: 'all' | 'logged_in' | 'guest'
  online_sim_base: number
  online_sim_delta: number
  online_sim_interval_sec: number
  online_counter_label: string
}

function buildOnlineDraftFromSettings(s: PublicSiteSettings): OnlineControlDraft {
  return {
    online_counter_enabled: s.online_counter_enabled !== false,
    online_counter_mode: s.online_counter_mode === 'simulated' ? 'simulated' : 'real',
    online_real_scope:
      s.online_real_scope === 'logged_in' || s.online_real_scope === 'guest' || s.online_real_scope === 'all'
        ? s.online_real_scope
        : 'all',
    online_sim_base: Number(s.online_sim_base ?? 68),
    online_sim_delta: Number(s.online_sim_delta ?? 12),
    online_sim_interval_sec: Number(s.online_sim_interval_sec ?? 12),
    online_counter_label: (s.online_counter_label || '在线').trim() || '在线',
  }
}

const onlineDraft = ref<OnlineControlDraft>({
  online_counter_enabled: true,
  online_counter_mode: 'real',
  online_real_scope: 'all',
  online_sim_base: 68,
  online_sim_delta: 12,
  online_sim_interval_sec: 12,
  online_counter_label: '在线',
})

const trafficReport = ref<AdminTrafficResponse | null>(null)
const trafficLoading = ref(false)
const trafficDay = ref('')
const trafficFilter = ref<'all' | 'auth' | 'guest' | 'online'>('all')
const trafficSort = ref<'visits' | 'recent'>('visits')
const trafficSearch = ref('')
const trafficSessionsExpanded = ref(true)
const hoveredHour = ref<number | null>(null)
const liveNowMs = ref(Date.now())
let trafficPollTimer: ReturnType<typeof setInterval> | null = null
let liveClockTimer: ReturnType<typeof setInterval> | null = null

interface GrowthControlDraft {
  growth_stage: GrowthStage
  access_mode: SiteAccessMode
  welcome_hero_enabled: boolean
  soft_auth_prompts_enabled: boolean
  guest_qa_daily_limit: number
  auth_qa_daily_limit: number
  crowd_vote_min_unlock: number
  user_referral_enabled: boolean
  user_invite_quota: number
  referral_bonus_qa_quota: number
  invite_waitlist_enabled: boolean
  prediction_daily_market_enabled: boolean
  prediction_rewards_enabled: boolean
  prediction_proposals_enabled: boolean
  weekly_digest_enabled: boolean
  weekly_digest_day: number
  weekly_digest_hour: number
  weekly_digest_minute: number
}

const growthDraft = ref<GrowthControlDraft>({
  growth_stage: 'stage_1_cold_start',
  access_mode: 'invite_only',
  welcome_hero_enabled: true,
  soft_auth_prompts_enabled: true,
  guest_qa_daily_limit: 5,
  auth_qa_daily_limit: 30,
  crowd_vote_min_unlock: 3,
  user_referral_enabled: false,
  user_invite_quota: 3,
  referral_bonus_qa_quota: 15,
  invite_waitlist_enabled: false,
  prediction_daily_market_enabled: true,
  prediction_rewards_enabled: true,
  prediction_proposals_enabled: true,
  weekly_digest_enabled: true,
  weekly_digest_day: 0,
  weekly_digest_hour: 18,
  weekly_digest_minute: 0,
})
const privateGateConfirmOpen = ref(false)
const waitlistItems = ref<WaitlistEntryRow[]>([])
const predictionProposals = ref<PredictionProposalRow[]>([])
const dailyPredictions = ref<DailyPredictionRow[]>([])
const settleValueDrafts = ref<Record<string, string>>({})

// Feedback inbox state
const feedbackStatusFilter = ref<string>('')
const feedbackItems = ref<FeedbackRecordItem[]>([])
const feedbackDrafts = ref<Record<number, { status: string; admin_reply: string }>>({})

// Content & Heavy override state
const contentEvents = ref<AdminContentEventRow[]>([])
const contentWire = ref<AdminContentWireRow[]>([])
const contentOverrides = ref<EditorialOverridesDoc | null>(null)
const contentSearch = ref('')
const contentScope = ref<'events' | 'wire'>('events')
const contentDrafts = ref<Record<string, { severity_override: string; heavy_reason_tag: string; pinned: boolean; hidden: boolean }>>({})

// Secondary verification modal for revealing user plaintext password
const revealTarget = ref<AdminUserRow | null>(null)
const revealAdminPassword = ref('')
const revealError = ref('')
const revealedPasswords = ref<Record<number, string>>({})

const inspectedUser = ref<{
  user: Record<string, unknown>
  has_state: boolean
  updated_at: string | null
  counts: Record<string, number> | null
  state: Record<string, unknown> | null
} | null>(null)
const resetTarget = ref<AdminUserRow | null>(null)
const resetNewPassword = ref('')
const createModalOpen = ref(false)
const createForm = ref<{
  username: string
  password: string
  display_name: string
  phone: string
  email: string
  role: UserRole
}>({
  username: '',
  password: '',
  display_name: '',
  phone: '',
  email: '',
  role: 'admin',
})

const busyAction = ref(false)
const monitorPublic = ref(false)

// One-time invite codes state
const inviteCodes = ref<AdminInviteCodeRow[]>([])
const inviteCount = ref(5)
const inviteNote = ref('')
const inviteExpiryDays = ref(30)

const createModalRef = ref<HTMLElement | null>(null)
const inspectedModalRef = ref<HTMLElement | null>(null)
const resetModalRef = ref<HTMLElement | null>(null)

const {
  dirtyConfirmOpen: createDirtyOpen,
  requestClose: requestCloseCreateModal,
  confirmDirtyDiscard: confirmCreateDiscard,
  cancelDirtyClose: cancelCreateDiscard,
} = useDialogBehavior({
  isOpen: createModalOpen,
  containerRef: createModalRef,
  onClose: () => {
    createModalOpen.value = false
  },
  isDirty: () => Boolean(createForm.value.username.trim() || createForm.value.password.trim()),
})

const { requestClose: requestCloseInspected } = useDialogBehavior({
  isOpen: computed(() => Boolean(inspectedUser.value)),
  containerRef: inspectedModalRef,
  onClose: () => {
    inspectedUser.value = null
  },
})

const {
  dirtyConfirmOpen: resetDirtyOpen,
  requestClose: requestCloseResetModal,
  confirmDirtyDiscard: confirmResetDiscard,
  cancelDirtyClose: cancelResetDiscard,
} = useDialogBehavior({
  isOpen: computed(() => Boolean(resetTarget.value && isSuperAdmin.value)),
  containerRef: resetModalRef,
  onClose: () => {
    resetTarget.value = null
  },
  isDirty: () => Boolean(resetNewPassword.value.trim()),
})

const isAdmin = computed(() => isAdminRole(session.value?.user.role))
const isSuperAdmin = computed(() => session.value?.user.role === 'super_admin')

const currentAccessMode = computed<SiteAccessMode>(() => {
  const m = siteSettingsForm.value.access_mode
  if (m === 'public' || m === 'invite_only' || m === 'private_gate') return m
  return 'invite_only'
})

function buildGrowthDraftFromSettings(s: PublicSiteSettings): GrowthControlDraft {
  return {
    growth_stage:
      s.growth_stage === 'stage_1_cold_start' ||
      s.growth_stage === 'stage_2_soft_invite' ||
      s.growth_stage === 'stage_3_scarcity_invite' ||
      s.growth_stage === 'stage_4_elite_circle'
        ? s.growth_stage
        : 'stage_1_cold_start',
    access_mode:
      s.access_mode === 'public' || s.access_mode === 'invite_only' || s.access_mode === 'private_gate'
        ? s.access_mode
        : 'invite_only',
    welcome_hero_enabled: s.welcome_hero_enabled !== false,
    soft_auth_prompts_enabled: s.soft_auth_prompts_enabled !== false,
    guest_qa_daily_limit: Number(s.guest_qa_daily_limit ?? 5),
    auth_qa_daily_limit: Number(s.auth_qa_daily_limit ?? 30),
    crowd_vote_min_unlock: Number(s.crowd_vote_min_unlock ?? 3),
    user_referral_enabled: Boolean(s.user_referral_enabled),
    user_invite_quota: Number(s.user_invite_quota ?? 3),
    referral_bonus_qa_quota: Number(s.referral_bonus_qa_quota ?? 15),
    invite_waitlist_enabled: Boolean(s.invite_waitlist_enabled),
    prediction_daily_market_enabled: s.prediction_daily_market_enabled !== false,
    prediction_rewards_enabled: s.prediction_rewards_enabled !== false,
    prediction_proposals_enabled: s.prediction_proposals_enabled !== false,
    weekly_digest_enabled: s.weekly_digest_enabled !== false,
    weekly_digest_day: Number(s.weekly_digest_day ?? 0),
    weekly_digest_hour: Number(s.weekly_digest_hour ?? 18),
    weekly_digest_minute: Number(s.weekly_digest_minute ?? 0),
  }
}

const GROWTH_STAGE_PRESETS: ReadonlyArray<{
  stage: GrowthStage
  title: string
  subtitle: string
  patch: Partial<GrowthControlDraft>
}> = [
  {
    stage: 'stage_1_cold_start',
    title: '阶段一：前期冷启动',
    subtitle: '开放免登录体验 + 首屏 3 胶囊 + 3 人投票即解锁共识',
    patch: {
      growth_stage: 'stage_1_cold_start',
      access_mode: 'public',
      welcome_hero_enabled: true,
      soft_auth_prompts_enabled: true,
      guest_qa_daily_limit: 5,
      auth_qa_daily_limit: 30,
      crowd_vote_min_unlock: 3,
      user_referral_enabled: false,
      user_invite_quota: 3,
      referral_bonus_qa_quota: 15,
      invite_waitlist_enabled: false,
    },
  },
  {
    stage: 'stage_2_soft_invite',
    title: '阶段二：中期软邀请裂变',
    subtitle: '仍免码注册，选填老用户邀请码双方每日 +15 次 AI 额度',
    patch: {
      growth_stage: 'stage_2_soft_invite',
      access_mode: 'public',
      welcome_hero_enabled: true,
      soft_auth_prompts_enabled: true,
      guest_qa_daily_limit: 5,
      crowd_vote_min_unlock: 5,
      user_referral_enabled: true,
      user_invite_quota: 3,
      referral_bonus_qa_quota: 15,
      invite_waitlist_enabled: false,
    },
  },
  {
    stage: 'stage_3_scarcity_invite',
    title: '阶段三：后期稀缺邀请制',
    subtitle: '凭码注册 + 开启无码访客候补申请 + 提高共识解锁门槛',
    patch: {
      growth_stage: 'stage_3_scarcity_invite',
      access_mode: 'invite_only',
      welcome_hero_enabled: true,
      soft_auth_prompts_enabled: true,
      guest_qa_daily_limit: 3,
      crowd_vote_min_unlock: 10,
      user_referral_enabled: true,
      user_invite_quota: 2,
      invite_waitlist_enabled: true,
    },
  },
  {
    stage: 'stage_4_elite_circle',
    title: '阶段四：大后期私有门禁',
    subtitle: '全站未登录拦截 + 仅凭邀请码或候补审批准入',
    patch: {
      growth_stage: 'stage_4_elite_circle',
      access_mode: 'private_gate',
      user_referral_enabled: true,
      invite_waitlist_enabled: true,
    },
  },
]

function applyStagePresetDraft(stage: GrowthStage) {
  const preset = GROWTH_STAGE_PRESETS.find((p) => p.stage === stage)
  if (!preset) return
  growthDraft.value = {
    ...growthDraft.value,
    ...preset.patch,
  }
  showToast(`已预填充「${preset.title}」参数草稿，请核对下方高亮变更项后点击「保存生效」`)
}

const currentLiveGrowth = computed(() => buildGrowthDraftFromSettings(siteSettingsForm.value))

const changedGrowthKeys = computed<Set<keyof GrowthControlDraft>>(() => {
  const out = new Set<keyof GrowthControlDraft>()
  const cur = currentLiveGrowth.value
  const d = growthDraft.value
  for (const k of Object.keys(d) as Array<keyof GrowthControlDraft>) {
    if (d[k] !== cur[k]) out.add(k)
  }
  return out
})

function stageShortLabel(st?: GrowthStage): string {
  const found = GROWTH_STAGE_PRESETS.find((p) => p.stage === st)
  return found ? found.title : '阶段一：前期冷启动'
}

const ACCESS_MODE_OPTIONS: ReadonlyArray<{
  value: SiteAccessMode
  title: string
  badge: string
  summary: string
}> = [
  {
    value: 'public',
    title: '完全开放（public）',
    badge: '自由浏览与注册',
    summary: '访客可直接浏览资讯，并自由注册账号（无需邀请码）。',
  },
  {
    value: 'invite_only',
    title: '邀请制注册（invite_only · 推荐）',
    badge: '推荐',
    summary: '访客可浏览公开资讯，但新账号注册必须凭管理员发放的一次性邀请码；已注册/迁移老账号可正常登录。',
  },
  {
    value: 'private_gate',
    title: '全站私有门禁（private_gate）',
    badge: '最高隔离',
    summary: '未登录访客无法查看内容与接口数据，必须先使用已有账号登录或凭邀请码注册后才能进入。',
  },
]

function accessModeMeta(mode: SiteAccessMode) {
  if (mode === 'public') {
    return {
      shortLabel: '完全开放（public）',
      badgeClass: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300',
      inviteHint: '当前全站处于「完全开放」模式：新用户可自由注册，无需填写邀请码（下列邀请码仅在切换为邀请制或私有门禁后生效）。',
    }
  }
  if (mode === 'private_gate') {
    return {
      shortLabel: '全站私有门禁（private_gate）',
      badgeClass: 'bg-rose-100 text-rose-700 dark:bg-rose-950/60 dark:text-rose-300',
      inviteHint: '当前全站处于「全站私有门禁」模式：未登录访客无法查看任何站内数据，必须凭现有账号登录或使用下列一次性邀请码注册后方可进入。',
    }
  }
  return {
    shortLabel: '邀请制注册（invite_only）',
    badgeClass: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300',
    inviteHint: '当前全站处于「邀请制注册」模式：访客可浏览公开资讯，但所有新用户注册必须消耗下方的 1 个有效一次性邀请码。',
  }
}

const filteredUsers = computed(() => {
  const q = userSearch.value.trim().toLowerCase()
  if (!q) return users.value
  return users.value.filter(
    (u) =>
      u.username.toLowerCase().includes(q) ||
      (u.display_name || '').toLowerCase().includes(q) ||
      (u.email || '').toLowerCase().includes(q) ||
      (u.phone || '').toLowerCase().includes(q) ||
      (u.last_login_ip || '').toLowerCase().includes(q),
  )
})

const filteredContentEvents = computed(() => {
  const q = contentSearch.value.trim().toLowerCase()
  const list = contentEvents.value
  if (!q) return list
  return list.filter((it) => `${it.title} ${it.category} ${it.heavy_reason_tag || ''}`.toLowerCase().includes(q))
})

const filteredContentWire = computed(() => {
  const q = contentSearch.value.trim().toLowerCase()
  const list = contentWire.value
  if (!q) return list
  return list.filter((it) => `${it.title} ${it.source_name} ${it.heavy_reason_tag || ''}`.toLowerCase().includes(q))
})

const HEAVY_TAG_OPTIONS = [
  '重磅',
  '地缘与军事突发',
  '元首/央行表态',
  '大宗与市场剧震',
  '监管与政策落地',
  '宏观与经济数据',
  '前沿模型与算力',
]

function roleLabel(role: UserRole): string {
  if (role === 'super_admin') return '超级管理员'
  if (role === 'admin') return '运营管理员'
  return '普通用户'
}

function roleBadgeClass(role: UserRole): string {
  if (role === 'super_admin') return 'bg-rose-100 text-rose-700 dark:bg-rose-950/60 dark:text-rose-300'
  if (role === 'admin') return 'bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300'
  return 'bg-blue-100 text-blue-700 dark:bg-blue-950/60 dark:text-blue-300'
}

function formatAuditAction(act: unknown): string {
  const s = String(act || '')
  if (s === 'cron_sync_github' || s === 'cron_cloud_sync') return '云端数据自动同步 (cron_cloud_sync)'
  if (s === 'admin_manual_sync') return '管理员手动同步 (admin_manual_sync)'
  if (s === 'admin_change_access_mode') return '修改全站访问门禁模式 (admin_change_access_mode)'
  return s
}

function formatAuditDetail(detail: unknown): string {
  return String(detail || '')
    .replace(/https?:\/\/github\.com\/\S+/gi, '云端数据仓库')
    .replace(/GitHub/gi, '云端引擎')
}

function showToast(msg: string) {
  toast.value = msg
  setTimeout(() => {
    if (toast.value === msg) toast.value = ''
  }, 4000)
}

function toggleDark() {
  isDark.value = !isDark.value
  if (typeof document !== 'undefined') {
    document.documentElement.classList.toggle('dark', isDark.value)
  }
  writeDarkMode(isDark.value)
}

function syncContentDrafts(
  events: AdminContentEventRow[],
  wire: AdminContentWireRow[],
  overrides: EditorialOverridesDoc | null,
) {
  const next: Record<string, { severity_override: string; heavy_reason_tag: string; pinned: boolean; hidden: boolean }> = {}
  const map = overrides?.items || {}
  for (const ev of events) {
    const key = `event:${ev.event_id}`
    const ov = map[key] || map[`title:${ev.title_fingerprint}`]
    next[key] = {
      severity_override: ov?.severity_override || ev.severity_tier || 'B',
      heavy_reason_tag: ov?.heavy_reason_tag || ev.heavy_reason_tag || '',
      pinned: Boolean(ov?.pinned),
      hidden: Boolean(ov?.hidden),
    }
  }
  for (const w of wire) {
    const key = `wire:${w.title_fingerprint}`
    const ov = map[key] || map[`title:${w.title_fingerprint}`]
    next[key] = {
      severity_override: ov?.severity_override || w.severity_tier || 'B',
      heavy_reason_tag: ov?.heavy_reason_tag || w.heavy_reason_tag || '',
      pinned: Boolean(ov?.pinned),
      hidden: Boolean(ov?.hidden),
    }
  }
  contentDrafts.value = next
}

async function loadFeedbackList() {
  if (!session.value) return
  try {
    const res = await apiAdminFeedbackList(session.value.token, feedbackStatusFilter.value)
    feedbackItems.value = res.items || []
    const drafts: Record<number, { status: string; admin_reply: string }> = {}
    for (const item of feedbackItems.value) {
      drafts[item.id] = {
        status: item.status || 'pending',
        admin_reply: item.admin_reply || '',
      }
    }
    feedbackDrafts.value = drafts
  } catch (err) {
    showToast(err instanceof Error ? err.message : '加载反馈列表失败')
  }
}

async function loadTrafficReport() {
  if (!session.value || !isAdmin.value) return
  trafficLoading.value = true
  try {
    const res = await apiAdminTraffic(session.value.token, {
      day: trafficDay.value || undefined,
      filter: trafficFilter.value,
      sort: trafficSort.value,
      q: trafficSearch.value.trim(),
      limit: 150,
    })
    trafficReport.value = res
    if (!trafficDay.value && res.day) {
      trafficDay.value = res.day
    }
  } catch (err) {
    showToast(err instanceof Error ? err.message : '加载在线与访问统计失败')
  } finally {
    trafficLoading.value = false
  }
}

async function loadAllAdminData() {
  if (!session.value || !isAdmin.value) return
  loading.value = true
  authError.value = ''
  try {
    const token = session.value.token
    const [ov, ul, pc, pl, al, ss, fb, ct, invRes, wlRes, propRes, dpRes, trRes] = await Promise.all([
      apiAdminOverview(token),
      apiAdminUsers(token),
      apiAdminGetPushConfig(token),
      apiAdminPushLogs(token),
      apiAdminAuditLogs(token, 100),
      apiAdminGetSiteSettings(token),
      apiAdminFeedbackList(token, feedbackStatusFilter.value),
      apiAdminContentList(token),
      apiAdminInviteCodes(token).catch(() => ({ items: [] })),
      apiAdminListWaitlist(token).catch(() => ({ items: [] })),
      apiAdminListPredictionProposals(token).catch(() => ({ items: [] })),
      apiAdminListDailyPredictions(token).catch(() => ({ items: [] })),
      apiAdminTraffic(token, {
        day: trafficDay.value || undefined,
        filter: trafficFilter.value,
        sort: trafficSort.value,
        q: trafficSearch.value.trim(),
        limit: 150,
      }).catch(() => null),
    ])
    inviteCodes.value = invRes.items || []
    waitlistItems.value = wlRes.items || []
    predictionProposals.value = propRes.items || []
    dailyPredictions.value = dpRes.items || []
    if (trRes) {
      trafficReport.value = trRes
      if (!trafficDay.value && trRes.day) {
        trafficDay.value = trRes.day
      }
    }
    overview.value = ov
    users.value = ul.users
    pushConfig.value = pc.config
    pushLogs.value = pl.logs
    auditLogs.value = al.logs
    monitorPublic.value = Boolean(ss.monitor_public)
    siteSettingsForm.value = {
      monitor_public: Boolean(ss.monitor_public),
      access_mode: ss.access_mode === 'public' || ss.access_mode === 'invite_only' || ss.access_mode === 'private_gate' ? ss.access_mode : 'invite_only',
      invite_required: ss.invite_required !== undefined ? Boolean(ss.invite_required) : ss.access_mode !== 'public',
      login_required: ss.login_required !== undefined ? Boolean(ss.login_required) : ss.access_mode === 'private_gate',
      feedback_enabled: ss.feedback_enabled !== false,
      feedback_notice: ss.feedback_notice || '',
      feedback_contact_wechat: ss.feedback_contact_wechat || '',
      feedback_contact_email: ss.feedback_contact_email || '',
      feedback_contact_group: ss.feedback_contact_group || '',
      feedback_contact_qr_url: ss.feedback_contact_qr_url || '',
      feedback_daily_limit: ss.feedback_daily_limit ?? 5,
      site_banner_enabled: Boolean(ss.site_banner_enabled),
      site_banner_text: ss.site_banner_text || '',
      site_banner_tone: ss.site_banner_tone || 'info',
      growth_stage: ss.growth_stage || 'stage_1_cold_start',
      welcome_hero_enabled: ss.welcome_hero_enabled !== false,
      soft_auth_prompts_enabled: ss.soft_auth_prompts_enabled !== false,
      guest_qa_daily_limit: ss.guest_qa_daily_limit ?? 5,
      auth_qa_daily_limit: ss.auth_qa_daily_limit ?? 30,
      crowd_vote_min_unlock: ss.crowd_vote_min_unlock ?? 3,
      user_referral_enabled: Boolean(ss.user_referral_enabled),
      user_invite_quota: ss.user_invite_quota ?? 3,
      referral_bonus_qa_quota: ss.referral_bonus_qa_quota ?? 15,
      invite_waitlist_enabled: Boolean(ss.invite_waitlist_enabled),
      prediction_daily_market_enabled: ss.prediction_daily_market_enabled !== false,
      prediction_rewards_enabled: ss.prediction_rewards_enabled !== false,
      prediction_proposals_enabled: ss.prediction_proposals_enabled !== false,
      weekly_digest_enabled: ss.weekly_digest_enabled !== false,
      weekly_digest_day: ss.weekly_digest_day ?? 0,
      weekly_digest_hour: ss.weekly_digest_hour ?? 18,
      weekly_digest_minute: ss.weekly_digest_minute ?? 0,
      online_counter_enabled: ss.online_counter_enabled !== false,
      online_counter_mode: ss.online_counter_mode === 'simulated' ? 'simulated' : 'real',
      online_real_scope:
        ss.online_real_scope === 'logged_in' || ss.online_real_scope === 'guest' || ss.online_real_scope === 'all'
          ? ss.online_real_scope
          : 'all',
      online_sim_base: ss.online_sim_base ?? 68,
      online_sim_delta: ss.online_sim_delta ?? 12,
      online_sim_interval_sec: ss.online_sim_interval_sec ?? 12,
      online_counter_label: ss.online_counter_label || '在线',
    }
    growthDraft.value = buildGrowthDraftFromSettings(siteSettingsForm.value)
    onlineDraft.value = buildOnlineDraftFromSettings(siteSettingsForm.value)
    feedbackItems.value = fb.items || []
    const drafts: Record<number, { status: string; admin_reply: string }> = {}
    for (const item of feedbackItems.value) {
      drafts[item.id] = { status: item.status || 'pending', admin_reply: item.admin_reply || '' }
    }
    feedbackDrafts.value = drafts
    contentEvents.value = ct.events || []
    contentWire.value = ct.wire || []
    contentOverrides.value = ct.overrides || null
    syncContentDrafts(contentEvents.value, contentWire.value, contentOverrides.value)
  } catch (err) {
    const msg = err instanceof Error ? err.message : '加载后台数据失败'
    authError.value = msg
    if (msg.includes('过期') || msg.includes('失效') || msg.includes('登录')) {
      clearAuthSession()
      session.value = null
    }
  } finally {
    loading.value = false
  }
}

async function handleAdminLogin() {
  authError.value = ''
  busyAction.value = true
  try {
    const res = await apiLogin(loginUser.value.trim(), loginPass.value)
    if (!isAdminRole(res.user.role)) {
      authError.value = '该账号不是管理员，无权进入后台控制台。'
      return
    }
    saveAuthSession(res)
    session.value = res
    loginPass.value = ''
    await loadAllAdminData()
  } catch (err) {
    authError.value = err instanceof Error ? err.message : '登录失败'
  } finally {
    busyAction.value = false
  }
}

function handleLogout() {
  clearAuthSession()
  session.value = null
  overview.value = null
  users.value = []
}

async function inspectUser(u: AdminUserRow) {
  if (!session.value) return
  busyAction.value = true
  try {
    const res = await apiAdminUserData(session.value.token, u.id)
    inspectedUser.value = {
      user: res.user as unknown as Record<string, unknown>,
      has_state: res.has_state,
      updated_at: res.updated_at,
      counts: res.counts as unknown as Record<string, number> | null,
      state: res.state,
    }
  } catch (err) {
    showToast(err instanceof Error ? err.message : '读取用户加密数据失败')
  } finally {
    busyAction.value = false
  }
}

function openRevealModal(u: AdminUserRow) {
  revealTarget.value = u
  revealAdminPassword.value = ''
  revealError.value = ''
}

async function submitRevealPassword() {
  if (!session.value || !revealTarget.value) return
  if (!revealAdminPassword.value.trim()) {
    revealError.value = '请输入您的超级管理员登录密码进行核验'
    return
  }
  busyAction.value = true
  revealError.value = ''
  try {
    const res = await apiAdminRevealUserPassword(
      session.value.token,
      revealTarget.value.id,
      revealAdminPassword.value,
    )
    if (res.password_plain) {
      revealedPasswords.value = {
        ...revealedPasswords.value,
        [revealTarget.value.id]: res.password_plain,
      }
      showToast(`已通过核验并解锁 @${revealTarget.value.username} 密码查看`)
    } else {
      showToast('该历史账号未记录明文备份，可通过改密重置')
    }
    revealTarget.value = null
    revealAdminPassword.value = ''
  } catch (err) {
    revealError.value = err instanceof Error ? err.message : '密码核验失败'
  } finally {
    busyAction.value = false
  }
}

function hideRevealedPassword(userId: number) {
  const next = { ...revealedPasswords.value }
  delete next[userId]
  revealedPasswords.value = next
}

async function toggleUserActive(u: AdminUserRow) {
  if (!session.value) return
  busyAction.value = true
  try {
    await apiAdminPatchUser(session.value.token, u.id, { is_active: !u.is_active })
    showToast(`已${u.is_active ? '停用' : '启用'}账号 @${u.username}`)
    await loadAllAdminData()
  } catch (err) {
    showToast(err instanceof Error ? err.message : '更新状态失败')
  } finally {
    busyAction.value = false
  }
}

async function handleChangeUserRole(u: AdminUserRow, nextRole: UserRole) {
  if (!session.value || !isSuperAdmin.value) return
  busyAction.value = true
  try {
    await apiAdminPatchUser(session.value.token, u.id, { role: nextRole })
    showToast(`已将 @${u.username} 权限设为：${roleLabel(nextRole)}`)
    await loadAllAdminData()
  } catch (err) {
    showToast(err instanceof Error ? err.message : '修改角色失败')
  } finally {
    busyAction.value = false
  }
}

async function submitCreateAccount() {
  if (!session.value || !isSuperAdmin.value) return
  if (!createForm.value.username.trim() || createForm.value.password.length < 6) {
    showToast('请填写用户名及至少 6 位密码')
    return
  }
  busyAction.value = true
  try {
    await apiAdminCreateUser(session.value.token, {
      username: createForm.value.username.trim(),
      password: createForm.value.password,
      display_name: createForm.value.display_name.trim(),
      phone: createForm.value.phone.trim(),
      email: createForm.value.email.trim(),
      role: createForm.value.role,
    })
    showToast(`已成功创建${roleLabel(createForm.value.role)} @${createForm.value.username}`)
    createModalOpen.value = false
    createForm.value = { username: '', password: '', display_name: '', phone: '', email: '', role: 'admin' }
    await loadAllAdminData()
  } catch (err) {
    showToast(err instanceof Error ? err.message : '创建账号失败')
  } finally {
    busyAction.value = false
  }
}

async function submitResetPassword() {
  if (!session.value || !resetTarget.value) return
  if (resetNewPassword.value.length < 6) {
    showToast('新密码至少 6 位')
    return
  }
  busyAction.value = true
  try {
    await apiAdminPatchUser(session.value.token, resetTarget.value.id, { new_password: resetNewPassword.value })
    showToast(`已重置 @${resetTarget.value.username} 密码`)
    resetTarget.value = null
    resetNewPassword.value = ''
    await loadAllAdminData()
  } catch (err) {
    showToast(err instanceof Error ? err.message : '重置密码失败')
  } finally {
    busyAction.value = false
  }
}

async function saveSiteSettingsPartial(patch: Partial<PublicSiteSettings>, successMsg: string) {
  if (!session.value) return
  busyAction.value = true
  try {
    const res = await apiAdminSaveSiteSettings(session.value.token, patch)
    monitorPublic.value = Boolean(res.monitor_public)
    siteSettingsForm.value = {
      ...siteSettingsForm.value,
      ...res,
    }
    growthDraft.value = buildGrowthDraftFromSettings(siteSettingsForm.value)
    onlineDraft.value = buildOnlineDraftFromSettings(siteSettingsForm.value)
    showToast(successMsg)
  } catch (err) {
    showToast(err instanceof Error ? err.message : '设置保存失败')
  } finally {
    busyAction.value = false
  }
}

const currentLiveOnline = computed(() => buildOnlineDraftFromSettings(siteSettingsForm.value))
const changedOnlineKeys = computed<Set<keyof OnlineControlDraft>>(() => {
  const out = new Set<keyof OnlineControlDraft>()
  const cur = currentLiveOnline.value
  const d = onlineDraft.value
  for (const k of Object.keys(d) as Array<keyof OnlineControlDraft>) {
    if (d[k] !== cur[k]) out.add(k)
  }
  return out
})

const simulatedPreviewRange = computed(() => {
  const base = Math.max(1, Math.round(Number(onlineDraft.value.online_sim_base || 1)))
  const delta = Math.max(0, Math.round(Number(onlineDraft.value.online_sim_delta || 0)))
  const interval = Math.max(3, Math.min(300, Math.round(Number(onlineDraft.value.online_sim_interval_sec || 12))))
  return {
    min: Math.max(1, base - delta),
    max: Math.max(1, base + delta),
    sample: computeSimulatedOnlineCount(base, delta, interval, liveNowMs.value),
  }
})

const liveRealOnline = computed(() => ({
  total: trafficReport.value?.online?.real_total ?? overview.value?.stats?.online_real_total ?? 0,
  logged_in: trafficReport.value?.online?.real_logged_in ?? overview.value?.stats?.online_real_logged_in ?? 0,
  guest: trafficReport.value?.online?.real_guest ?? overview.value?.stats?.online_real_guest ?? 0,
}))

const liveDisplayedOnlineCount = computed(() => {
  if (siteSettingsForm.value.online_counter_enabled === false) return 0
  if (siteSettingsForm.value.online_counter_mode === 'simulated') {
    return computeSimulatedOnlineCount(
      Number(siteSettingsForm.value.online_sim_base ?? 68),
      Number(siteSettingsForm.value.online_sim_delta ?? 12),
      Number(siteSettingsForm.value.online_sim_interval_sec ?? 12),
      liveNowMs.value,
    )
  }
  const scope = siteSettingsForm.value.online_real_scope || 'all'
  if (scope === 'logged_in') return liveRealOnline.value.logged_in
  if (scope === 'guest') return liveRealOnline.value.guest
  return liveRealOnline.value.total
})

async function refreshTrafficSilently() {
  if (!session.value || !isAdmin.value || trafficLoading.value) return
  try {
    const res = await apiAdminTraffic(session.value.token, {
      day: trafficDay.value || undefined,
      filter: trafficFilter.value,
      sort: trafficSort.value,
      q: trafficSearch.value.trim(),
      limit: 150,
    })
    trafficReport.value = res
    if (!trafficDay.value && res.day) {
      trafficDay.value = res.day
    }
  } catch {
    // Silent background poll
  }
}

const filteredTrafficRows = computed(() => {
  const rows = trafficReport.value?.ip_rows || []
  const q = trafficSearch.value.trim().toLowerCase()
  return rows.filter((row) => {
    if (trafficFilter.value === 'auth' && !row.has_auth) return false
    if (trafficFilter.value === 'guest' && row.has_auth) return false
    if (trafficFilter.value === 'online' && !row.is_online) return false
    if (q) {
      const hay = `${row.ip} ${row.country} ${row.last_username} ${row.usernames.join(' ')} ${row.last_tab}`.toLowerCase()
      if (!hay.includes(q)) return false
    }
    return true
  })
})

const hourlyMaxVisits = computed(() => {
  const list = trafficReport.value?.hourly || []
  return Math.max(1, ...list.map((h) => h.total_visits))
})

const hoveredHourlyRow = computed(() => {
  if (hoveredHour.value === null || !trafficReport.value) return null
  return trafficReport.value.hourly.find((h) => h.hour === hoveredHour.value) || null
})

async function handleSaveOnlineConfig() {
  const cleanBase = Math.max(1, Math.min(99999, Math.round(Number(onlineDraft.value.online_sim_base || 68))))
  const cleanDelta = Math.max(0, Math.min(50000, Math.round(Number(onlineDraft.value.online_sim_delta || 0))))
  const cleanInterval = Math.max(3, Math.min(300, Math.round(Number(onlineDraft.value.online_sim_interval_sec || 12))))
  const cleanLabel = (onlineDraft.value.online_counter_label || '').trim().slice(0, 16) || '在线'
  onlineDraft.value = {
    ...onlineDraft.value,
    online_sim_base: cleanBase,
    online_sim_delta: cleanDelta,
    online_sim_interval_sec: cleanInterval,
    online_counter_label: cleanLabel,
  }
  await saveSiteSettingsPartial(
    { ...onlineDraft.value },
    onlineDraft.value.online_counter_mode === 'simulated'
      ? `自定义在线人数已生效（基准 ${cleanBase} · 浮动 ±${cleanDelta} · 每 ${cleanInterval} 秒变动）`
      : '在线人数真实统计配置已保存并全站生效！',
  )
  broadcastPresenceConfigChange()
  await loadTrafficReport()
}

async function handleRevertRealOnline() {
  onlineDraft.value.online_counter_enabled = true
  onlineDraft.value.online_counter_mode = 'real'
  await saveSiteSettingsPartial(
    {
      online_counter_enabled: true,
      online_counter_mode: 'real',
      online_real_scope: onlineDraft.value.online_real_scope,
    },
    '已调回显示平台真实在线人数！',
  )
  broadcastPresenceConfigChange()
  await loadTrafficReport()
}

function resetOnlineDraft() {
  onlineDraft.value = buildOnlineDraftFromSettings(siteSettingsForm.value)
}

function platformLabel(p: string): string {
  if (p === 'android') return '安卓端'
  if (p === 'mobile') return '手机网页'
  return '桌面网页'
}

function tabLabel(tb: string): string {
  const map: Record<string, string> = {
    today: '精选要闻',
    wire: '7×24 快讯',
    finance: '股市传导',
    ai_progress: 'AI 前沿',
    calendar: '预测/日程',
    weekly: '每周盘点',
    tracking: '追踪',
    me: '我的',
  }
  return map[tb] || tb || '首页'
}

function formatCstTimeOnly(iso?: string | null): string {
  if (!iso) return '-'
  const m = String(iso).match(/T(\d{2}:\d{2}:\d{2})/)
  return m ? m[1] : String(iso).slice(0, 19).replace('T', ' ')
}

async function copyIpAddress(ip: string) {
  try {
    await navigator.clipboard.writeText(ip)
    showToast(`已复制 IP：${ip}`)
  } catch {
    showToast(`请手动复制 IP：${ip}`)
  }
}

function handleRequestSaveGrowthConsole() {
  if (!isSuperAdmin.value) {
    showToast('仅一级最高管理员可修改全站访问门禁与营销增长策略')
    return
  }
  if (growthDraft.value.access_mode === 'private_gate' && currentAccessMode.value !== 'private_gate') {
    privateGateConfirmOpen.value = true
    return
  }
  void executeSaveGrowthConsole()
}

async function executeSaveGrowthConsole() {
  privateGateConfirmOpen.value = false
  const payload = { ...growthDraft.value }
  await saveSiteSettingsPartial(
    payload,
    `阶段式营销与门禁策略已保存（${stageShortLabel(payload.growth_stage)} · ${accessModeMeta(payload.access_mode).shortLabel}），全站实时生效！`,
  )
  if (session.value) {
    apiAdminAuditLogs(session.value.token, 100)
      .then((res) => {
        auditLogs.value = res.logs
      })
      .catch(() => {})
  }
}

function resetGrowthDraft() {
  growthDraft.value = buildGrowthDraftFromSettings(siteSettingsForm.value)
}

async function handleApproveWaitlist(row: WaitlistEntryRow) {
  if (!session.value) return
  busyAction.value = true
  try {
    const res = await apiAdminApproveWaitlist(session.value.token, row.id)
    showToast(`已批准 #${row.id}（${row.contact}），签发邀请码：${res.code}`)
    const [wlRes, invRes] = await Promise.all([
      apiAdminListWaitlist(session.value.token),
      apiAdminInviteCodes(session.value.token),
    ])
    waitlistItems.value = wlRes.items || []
    inviteCodes.value = invRes.items || []
  } catch (err) {
    showToast(err instanceof Error ? err.message : '批准失败')
  } finally {
    busyAction.value = false
  }
}

async function handleRejectWaitlist(row: WaitlistEntryRow) {
  if (!session.value) return
  busyAction.value = true
  try {
    await apiAdminRejectWaitlist(session.value.token, row.id)
    showToast(`已拒绝候补申请 #${row.id}`)
    const wlRes = await apiAdminListWaitlist(session.value.token)
    waitlistItems.value = wlRes.items || []
  } catch (err) {
    showToast(err instanceof Error ? err.message : '操作失败')
  } finally {
    busyAction.value = false
  }
}

async function handleApproveProposal(row: PredictionProposalRow) {
  if (!session.value) return
  busyAction.value = true
  try {
    const res = await apiAdminApprovePredictionProposal(session.value.token, row.id)
    showToast(
      res.already_approved
        ? `提案 #${row.id} 此前已通过并上架`
        : `已通过提案 #${row.id} 并上架全站预测池，已向 ${row.username} 发放 +100 洞察分与 +1 邀请名额`,
    )
    const [propRes, dpRes] = await Promise.all([
      apiAdminListPredictionProposals(session.value.token),
      apiAdminListDailyPredictions(session.value.token),
    ])
    predictionProposals.value = propRes.items || []
    dailyPredictions.value = dpRes.items || []
  } catch (err) {
    showToast(err instanceof Error ? err.message : '审批提案失败')
  } finally {
    busyAction.value = false
  }
}

async function handleRejectProposal(row: PredictionProposalRow) {
  if (!session.value) return
  busyAction.value = true
  try {
    await apiAdminRejectPredictionProposal(session.value.token, row.id)
    showToast(`已拒绝提案 #${row.id}`)
    const propRes = await apiAdminListPredictionProposals(session.value.token)
    predictionProposals.value = propRes.items || []
  } catch (err) {
    showToast(err instanceof Error ? err.message : '操作失败')
  } finally {
    busyAction.value = false
  }
}

async function handleSettleDaily(row: DailyPredictionRow, outcome: 'yes' | 'no' | 'void') {
  if (!session.value) return
  busyAction.value = true
  try {
    const rawVal = (settleValueDrafts.value[row.id] || '').trim()
    const numVal = rawVal !== '' && Number.isFinite(Number(rawVal)) ? Number(rawVal) : null
    const res = await apiAdminSettleDailyPrediction(session.value.token, row.id, {
      outcome,
      settled_value: numVal,
    })
    showToast(`已完成结算（结果：${res.outcome.toUpperCase()} · 结算 ${res.settled_votes} 份投票）`)
    const dpRes = await apiAdminListDailyPredictions(session.value.token)
    dailyPredictions.value = dpRes.items || []
  } catch (err) {
    showToast(err instanceof Error ? err.message : '结算失败')
  } finally {
    busyAction.value = false
  }
}

async function handleTriggerDailyCron() {
  if (!session.value) return
  busyAction.value = true
  try {
    const res = await apiAdminRunDailyPredictionCron(session.value.token)
    showToast(`日赛调度完成：新生成 ${res.generated} 题 · 封盘 ${res.locked} 题 · 自动结算 ${res.settled} 题`)
    const dpRes = await apiAdminListDailyPredictions(session.value.token)
    dailyPredictions.value = dpRes.items || []
  } catch (err) {
    showToast(err instanceof Error ? err.message : '执行日赛调度失败')
  } finally {
    busyAction.value = false
  }
}

async function saveFeedbackReply(fb: FeedbackRecordItem) {
  if (!session.value) return
  const draft = feedbackDrafts.value[fb.id]
  if (!draft) return
  busyAction.value = true
  try {
    await apiAdminUpdateFeedback(session.value.token, fb.id, {
      status: draft.status,
      admin_reply: draft.admin_reply.trim(),
    })
    showToast(`已保存反馈 #${fb.id} 处理状态与回复`)
    await loadAllAdminData()
  } catch (err) {
    showToast(err instanceof Error ? err.message : '保存反馈处理失败')
  } finally {
    busyAction.value = false
  }
}

async function removeFeedbackItem(fb: FeedbackRecordItem) {
  if (!session.value) return
  busyAction.value = true
  try {
    await apiAdminDeleteFeedback(session.value.token, fb.id)
    showToast(`已删除反馈 #${fb.id}`)
    await loadAllAdminData()
  } catch (err) {
    showToast(err instanceof Error ? err.message : '删除反馈失败')
  } finally {
    busyAction.value = false
  }
}

async function applyEventOverride(ev: AdminContentEventRow) {
  if (!session.value) return
  const key = `event:${ev.event_id}`
  const draft = contentDrafts.value[key] || { severity_override: ev.severity_tier, heavy_reason_tag: ev.heavy_reason_tag || '', pinned: false, hidden: false }
  busyAction.value = true
  try {
    const res = await apiAdminSaveEditorialOverride(session.value.token, {
      key,
      target_type: 'event',
      event_id: ev.event_id,
      title: ev.title,
      title_fingerprint: ev.title_fingerprint,
      severity_override: draft.severity_override as 'S' | 'A' | 'B',
      heavy_reason_tag: draft.heavy_reason_tag || null,
      pinned: draft.pinned,
      hidden: draft.hidden,
    })
    contentOverrides.value = res.overrides
    syncContentDrafts(contentEvents.value, contentWire.value, contentOverrides.value)
    showToast(`已保存要闻人工干预（${ev.title.slice(0, 18)}…）`)
  } catch (err) {
    showToast(err instanceof Error ? err.message : '保存人工干预失败')
  } finally {
    busyAction.value = false
  }
}

async function applyWireOverride(w: AdminContentWireRow) {
  if (!session.value) return
  const key = `wire:${w.title_fingerprint}`
  const draft = contentDrafts.value[key] || { severity_override: w.severity_tier, heavy_reason_tag: w.heavy_reason_tag || '', pinned: false, hidden: false }
  busyAction.value = true
  try {
    const res = await apiAdminSaveEditorialOverride(session.value.token, {
      key,
      target_type: 'wire',
      title: w.title,
      title_fingerprint: w.title_fingerprint,
      severity_override: draft.severity_override as 'S' | 'A' | 'B',
      heavy_reason_tag: draft.heavy_reason_tag || null,
      pinned: draft.pinned,
      hidden: draft.hidden,
    })
    contentOverrides.value = res.overrides
    syncContentDrafts(contentEvents.value, contentWire.value, contentOverrides.value)
    showToast(`已保存快讯人工干预（${w.title.slice(0, 18)}…）`)
  } catch (err) {
    showToast(err instanceof Error ? err.message : '保存快讯干预失败')
  } finally {
    busyAction.value = false
  }
}

async function restoreOverride(key: string) {
  if (!session.value) return
  busyAction.value = true
  try {
    const res = await apiAdminDeleteEditorialOverride(session.value.token, key)
    contentOverrides.value = res.overrides
    syncContentDrafts(contentEvents.value, contentWire.value, contentOverrides.value)
    showToast('已撤回人工干预，恢复默认算法评分')
  } catch (err) {
    showToast(err instanceof Error ? err.message : '恢复失败')
  } finally {
    busyAction.value = false
  }
}

async function savePushSettings() {
  if (!session.value) return
  busyAction.value = true
  try {
    await apiAdminSavePushConfig(session.value.token, pushConfig.value)
    showToast('推送与验证码网关配置已保存！')
    await loadAllAdminData()
  } catch (err) {
    showToast(err instanceof Error ? err.message : '保存失败')
  } finally {
    busyAction.value = false
  }
}

async function runPushTest() {
  if (!session.value) return
  busyAction.value = true
  try {
    const res = await apiAdminPushTest(session.value.token)
    if (!res.results.length) {
      showToast('未检测到已填写的推送通道，请先填写 Webhook/邮箱并保存。')
    } else {
      const okN = res.results.filter((r) => r.status === 'ok').length
      showToast(`测试推送完成：${okN}/${res.results.length} 个通道成功`)
    }
    await loadAllAdminData()
  } catch (err) {
    showToast(err instanceof Error ? err.message : '测试推送失败')
  } finally {
    busyAction.value = false
  }
}

async function toggleMonitorPublic() {
  const next = !monitorPublic.value
  await saveSiteSettingsPartial(
    { monitor_public: next },
    next ? '已向普通用户公开「情报监控」页面' : '已隐藏「情报监控」页面（仅管理员可见）',
  )
}

async function runManualSync() {
  if (!session.value) return
  busyAction.value = true
  try {
    const res = await apiAdminSyncNow(session.value.token)
    const wireNote =
      typeof res.wire_total === 'number' || typeof res.quotes_count === 'number'
        ? `；快讯 ${res.wire_total ?? '-'} 条 / 行情 ${res.quotes_count ?? '-'} 项已更新`
        : ''
    if (res.skipped_same_batch && res.updated === 0) {
      showToast(`当前已是最新批次（${formatFriendlyBatchId(res.skipped_same_batch)}）${wireNote}`)
    } else {
      const batchNote = res.smart_batch_id ? `（批次：${formatFriendlyBatchId(res.smart_batch_id)}）` : ''
      showToast(`已同步云端最新批次 ${res.updated} 个数据文件${batchNote}${wireNote}！`)
    }
    await loadAllAdminData()
  } catch (err) {
    showToast(err instanceof Error ? err.message : '同步失败')
  } finally {
    busyAction.value = false
  }
}

async function handleGenerateInvites() {
  if (!session.value) return
  busyAction.value = true
  try {
    const res = await apiAdminCreateInviteCodes(session.value.token, {
      count: inviteCount.value,
      note: inviteNote.value.trim(),
      expires_days: inviteExpiryDays.value > 0 ? inviteExpiryDays.value : null,
    })
    inviteNote.value = ''
    showToast(`已生成 ${res.items.length} 个一次性邀请码！`)
    const listRes = await apiAdminInviteCodes(session.value.token)
    inviteCodes.value = listRes.items || []
  } catch (err) {
    showToast(err instanceof Error ? err.message : '生成邀请码失败')
  } finally {
    busyAction.value = false
  }
}

async function handleRevokeInvite(code: string) {
  if (!session.value) return
  busyAction.value = true
  try {
    await apiAdminRevokeInviteCode(session.value.token, code)
    showToast(`已作废邀请码 ${code}`)
    const listRes = await apiAdminInviteCodes(session.value.token)
    inviteCodes.value = listRes.items || []
  } catch (err) {
    showToast(err instanceof Error ? err.message : '作废失败')
  } finally {
    busyAction.value = false
  }
}

async function copyInviteText(code: string) {
  try {
    await navigator.clipboard.writeText(code)
    showToast(`已复制邀请码 ${code}`)
  } catch {
    showToast(`请手动复制：${code}`)
  }
}

function formatBytes(b: number | null | undefined): string {
  if (!b) return '0 B'
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  return `${(b / (1024 * 1024)).toFixed(2)} MB`
}

onMounted(() => {
  if (typeof document !== 'undefined') {
    document.documentElement.classList.toggle('dark', isDark.value)
  }
  if (isAdmin.value) {
    void loadAllAdminData()
  }
  liveClockTimer = setInterval(() => {
    if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return
    liveNowMs.value = Date.now()
  }, 1_000)
  trafficPollTimer = setInterval(() => {
    if (!isAdmin.value) return
    if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return
    void refreshTrafficSilently()
  }, 30_000)
})

onBeforeUnmount(() => {
  if (liveClockTimer) {
    clearInterval(liveClockTimer)
    liveClockTimer = null
  }
  if (trafficPollTimer) {
    clearInterval(trafficPollTimer)
    trafficPollTimer = null
  }
})
</script>

<template>
  <AppShell
    active-page="about"
    :is-dark="isDark"
    :auth-user="session?.user ?? null"
    :user-avatar="session?.user?.avatar || ''"
    :show-history-button="false"
    :show-bookmarks-button="false"
    :show-refresh-button="false"
    @toggle-dark="toggleDark"
  >
    <div class="max-w-6xl mx-auto space-y-5">
      <div
        v-if="toast"
        class="rounded-xl border border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-950/40 px-4 py-2.5 text-sm font-medium text-emerald-900 dark:text-emerald-200 flex items-center justify-between"
      >
        <span>{{ toast }}</span>
        <button type="button" @click="toast = ''" class="text-emerald-600"><X class="w-4 h-4" /></button>
      </div>

      <!-- Admin Login Gate -->
      <section
        v-if="!isAdmin"
        class="max-w-md mx-auto mt-8 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 space-y-4 shadow-sm"
      >
        <div class="flex items-center gap-2.5">
          <div class="w-10 h-10 rounded-xl bg-rose-600 text-white flex items-center justify-center">
            <Shield class="w-5 h-5" />
          </div>
          <div>
            <h1 class="text-lg font-bold text-slate-900 dark:text-white">镜信 · 管理员后台</h1>
            <p class="text-xs text-slate-500">支持超级管理员与运营管理员分级权限登录</p>
          </div>
        </div>

        <div
          v-if="session && !isAdminRole(session.user.role)"
          class="rounded-xl bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 p-3 text-xs text-amber-900 dark:text-amber-200 flex items-center justify-between gap-2"
        >
          <span>当前登录账号 @{{ session.user.username }} 为普通用户，无后台权限。</span>
          <button type="button" @click="handleLogout" class="font-semibold underline shrink-0">切换管理员</button>
        </div>

        <form @submit.prevent="handleAdminLogin" class="space-y-3">
          <div>
            <label class="block text-xs font-medium text-slate-600 dark:text-slate-300 mb-1">管理员账号</label>
            <input
              v-model="loginUser"
              type="text"
              required
              class="w-full h-10 px-3 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm"
            />
          </div>
          <div>
            <label class="block text-xs font-medium text-slate-600 dark:text-slate-300 mb-1">管理员密码</label>
            <input
              v-model="loginPass"
              type="password"
              required
              class="w-full h-10 px-3 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm"
            />
          </div>
          <p v-if="authError" class="text-xs text-red-600 dark:text-red-400 font-medium">{{ authError }}</p>
          <button
            type="submit"
            :disabled="busyAction"
            class="w-full h-10 rounded-xl bg-slate-900 dark:bg-blue-600 text-white text-sm font-semibold hover:opacity-95 disabled:opacity-60"
          >
            {{ busyAction ? '验证中...' : '进入管理员控制台' }}
          </button>
        </form>
      </section>

      <!-- Authenticated Admin Dashboard -->
      <template v-else>
        <header class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 sm:p-5 flex flex-wrap items-center justify-between gap-3">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-xl bg-indigo-600 text-white flex items-center justify-center">
              <Shield class="w-5 h-5" />
            </div>
            <div>
              <h1 class="text-base sm:text-lg font-bold text-slate-900 dark:text-white flex flex-wrap items-center gap-2">
                <span>私有云管理控制台</span>
                <span
                  class="px-2 py-0.5 rounded-full text-[11px] font-semibold"
                  :class="isSuperAdmin ? 'bg-rose-100 text-rose-700 dark:bg-rose-950/60 dark:text-rose-300' : 'bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300'"
                >
                  {{ isSuperAdmin ? '超级管理员（全权限）' : '运营管理员（受限权限）' }}
                </span>
                <button
                  type="button"
                  @click="activeTab = 'traffic'; loadTrafficReport()"
                  data-testid="admin-header-real-online-pill"
                  class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-500/12 text-emerald-700 dark:text-emerald-300 border border-emerald-500/25 hover:bg-emerald-500/20 transition-colors tabular-nums"
                  title="点击查看实时在线与 IP 访问详情（真实在线不受假人数影响）"
                >
                  <span class="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                  <span>真实在线 {{ liveRealOnline.total }} 人（登 {{ liveRealOnline.logged_in }} / 客 {{ liveRealOnline.guest }}）</span>
                </button>
                <span
                  v-if="siteSettingsForm.online_counter_mode === 'simulated'"
                  class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300 tabular-nums"
                >
                  <span>前台假人数展示中：{{ siteSettingsForm.online_counter_enabled === false ? '已隐藏' : `${liveDisplayedOnlineCount} 人` }}</span>
                </span>
              </h1>
              <p class="text-xs text-slate-500">
                当前登录：{{ session?.user.display_name }} (@{{ session?.user.username }}) ·
                {{ isSuperAdmin ? '拥有系统设置、内容调度、反馈回复及账号密码核验查看权限' : '支持用户研究数据审计、反馈受理与内容重磅调度' }}
              </p>
            </div>
          </div>

          <div class="flex flex-wrap items-center gap-2 text-xs">
            <a
              href="./android-dev.html"
              class="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-emerald-600 text-white font-semibold hover:bg-emerald-700"
            >
              <MonitorSmartphone class="w-3.5 h-3.5" />
              <span>安卓页面调试后台</span>
            </a>
            <button
              v-if="isSuperAdmin"
              type="button"
              @click="createModalOpen = true"
              class="inline-flex items-center gap-1 px-3 py-2 rounded-xl bg-rose-600 text-white font-semibold hover:bg-rose-700"
            >
              <Plus class="w-3.5 h-3.5" />
              <span>新增管理员 / 账号</span>
            </button>
            <button
              type="button"
              :disabled="busyAction || loading"
              @click="runManualSync"
              class="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-blue-600 text-white font-semibold hover:bg-blue-700 disabled:opacity-60"
            >
              <RefreshCw class="w-3.5 h-3.5" :class="{ 'animate-spin': busyAction }" />
              <span>立即同步云端最新批次</span>
            </button>
            <button
              type="button"
              @click="loadAllAdminData"
              class="px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 font-medium"
            >
              刷新面板
            </button>
            <button
              type="button"
              @click="handleLogout"
              class="inline-flex items-center gap-1 px-3 py-2 rounded-xl border border-red-200 dark:border-red-900 text-red-600 font-medium hover:bg-red-50"
            >
              <LogOut class="w-3.5 h-3.5" />
              <span>退出</span>
            </button>
          </div>
        </header>

        <!-- Admin Navigation Tabs -->
        <div class="flex flex-wrap gap-2 text-xs sm:text-sm font-semibold">
          <button
            type="button"
            @click="activeTab = 'overview'"
            class="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl border transition-colors"
            :class="activeTab === 'overview' ? 'bg-slate-900 text-white border-slate-900 dark:bg-blue-600 dark:border-blue-600' : 'bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-300'"
          >
            <Database class="w-4 h-4" />
            <span>运营总览</span>
          </button>
          <button
            type="button"
            @click="activeTab = 'traffic'; loadTrafficReport()"
            data-testid="admin-tab-traffic"
            class="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl border transition-colors"
            :class="activeTab === 'traffic' ? 'bg-slate-900 text-white border-slate-900 dark:bg-blue-600 dark:border-blue-600' : 'bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-300'"
          >
            <BarChart3 class="w-4 h-4" />
            <span>在线与访问统计</span>
            <span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 tabular-nums">
              <span class="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              {{ trafficReport?.online?.real_total ?? overview?.stats?.online_real_total ?? 0 }}
            </span>
          </button>
          <button
            type="button"
            @click="activeTab = 'feedback'"
            class="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl border transition-colors"
            :class="activeTab === 'feedback' ? 'bg-slate-900 text-white border-slate-900 dark:bg-blue-600 dark:border-blue-600' : 'bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-300'"
          >
            <MessageSquare class="w-4 h-4" />
            <span>意见反馈与渠道设置</span>
            <span
              v-if="(overview?.stats?.pending_feedback_count ?? 0) > 0"
              class="px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-rose-500 text-white tabular-nums"
            >
              {{ overview?.stats?.pending_feedback_count }}
            </span>
          </button>
          <button
            type="button"
            @click="activeTab = 'content'"
            class="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl border transition-colors"
            :class="activeTab === 'content' ? 'bg-slate-900 text-white border-slate-900 dark:bg-blue-600 dark:border-blue-600' : 'bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-300'"
          >
            <FileEdit class="w-4 h-4" />
            <span>内容运营与重磅调度</span>
          </button>
          <button
            type="button"
            @click="activeTab = 'users'"
            class="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl border transition-colors"
            :class="activeTab === 'users' ? 'bg-slate-900 text-white border-slate-900 dark:bg-blue-600 dark:border-blue-600' : 'bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-300'"
          >
            <Users class="w-4 h-4" />
            <span>用户与管理员权限 ({{ users.length }})</span>
          </button>
          <button
            type="button"
            @click="activeTab = 'push'"
            class="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl border transition-colors"
            :class="activeTab === 'push' ? 'bg-slate-900 text-white border-slate-900 dark:bg-blue-600 dark:border-blue-600' : 'bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-300'"
          >
            <Bell class="w-4 h-4" />
            <span>推送与验证码网关</span>
          </button>
          <button
            type="button"
            @click="activeTab = 'audit'"
            class="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl border transition-colors"
            :class="activeTab === 'audit' ? 'bg-slate-900 text-white border-slate-900 dark:bg-blue-600 dark:border-blue-600' : 'bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-300'"
          >
            <Activity class="w-4 h-4" />
            <span>安全审计日志</span>
          </button>
        </div>

        <!-- Tab 1: Overview -->
        <section v-if="activeTab === 'overview' && overview" class="space-y-4">
          <div class="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4">
              <div class="text-xs text-slate-500">账号总数（含管理员）</div>
              <div class="text-2xl font-bold text-slate-900 dark:text-white mt-1 tabular-nums">{{ overview.stats.total_users }}</div>
              <div class="text-[11px] text-emerald-600 mt-1">
                超管 {{ overview.stats.super_admin_count ?? 1 }} · 运营管理 {{ overview.stats.sub_admin_count ?? 0 }}
              </div>
            </div>
            <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4">
              <div class="text-xs text-slate-500">已开启云同步账号数</div>
              <div class="text-2xl font-bold text-blue-600 dark:text-blue-400 mt-1 tabular-nums">{{ overview.stats.synced_users }}</div>
              <div class="text-[11px] text-slate-500 mt-1">
                云端有效快照 {{ overview.stats.sync_snapshots_total ?? overview.stats.synced_users }} 份 · 关注 {{ overview.stats.total_watchlist_items }} · 收藏 {{ overview.stats.total_bookmarks }} · 笔记 {{ overview.stats.total_notes }}
              </div>
            </div>
            <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4">
              <div class="text-xs text-slate-500">待处理用户反馈</div>
              <div class="text-2xl font-bold text-amber-600 dark:text-amber-400 mt-1 tabular-nums">{{ overview.stats.pending_feedback_count ?? 0 }}</div>
              <div class="text-[11px] text-slate-500 mt-1">
                累计反馈 {{ overview.stats.total_feedback_count ?? feedbackItems.length }} 条 · 库体积 {{ formatBytes(overview.stats.db_file_bytes) }}
              </div>
            </div>
            <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4">
              <div class="text-xs text-slate-500">推送触达统计</div>
              <div class="text-2xl font-bold text-emerald-600 dark:text-emerald-400 mt-1 tabular-nums">{{ overview.stats.push_ok_count }}</div>
              <div class="text-[11px] text-slate-500 mt-1">失败 {{ overview.stats.push_error_count }} 次 · 加密载荷 {{ formatBytes(overview.stats.encrypted_storage_bytes) }}</div>
            </div>
          </div>

          <!-- Real-Time Online & Daily IP Frequency Quick Strip -->
          <div class="rounded-2xl border border-emerald-200/80 dark:border-emerald-900/60 bg-white dark:bg-slate-900 p-4 sm:p-5 flex flex-wrap items-center justify-between gap-3 text-xs sm:text-sm">
            <div class="flex flex-wrap items-center gap-4">
              <div>
                <div class="text-[11px] text-slate-500 flex items-center gap-1.5">
                  <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                  <span>当前真实在线（2 分钟心跳 · 同 IP 去重）</span>
                </div>
                <div class="font-bold text-slate-900 dark:text-white mt-0.5 tabular-nums">
                  <span class="text-lg text-emerald-600 dark:text-emerald-400">{{ liveRealOnline.total }}</span>
                  <span class="text-xs font-medium text-slate-500 ml-2">
                    已登录 {{ liveRealOnline.logged_in }} · 未登录 {{ liveRealOnline.guest }}
                  </span>
                </div>
              </div>
              <div class="h-8 w-px bg-slate-200 dark:bg-slate-800 hidden sm:block" />
              <div>
                <div class="text-[11px] text-slate-500">前台顶栏当前展示</div>
                <div class="font-bold text-slate-900 dark:text-white mt-0.5 tabular-nums">
                  <span>{{ siteSettingsForm.online_counter_enabled === false ? '已隐藏' : `${liveDisplayedOnlineCount} ${siteSettingsForm.online_counter_label || '在线'}` }}</span>
                  <span
                    class="ml-1.5 px-1.5 py-0.5 rounded text-[10px] font-semibold"
                    :class="siteSettingsForm.online_counter_mode === 'simulated' ? 'bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300' : 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300'"
                  >
                    {{ siteSettingsForm.online_counter_mode === 'simulated' ? '自定义浮动假人数' : '真实在线' }}
                  </span>
                </div>
              </div>
              <div class="h-8 w-px bg-slate-200 dark:bg-slate-800 hidden sm:block" />
              <div>
                <div class="text-[11px] text-slate-500">今日全站访问 / 独立 IP</div>
                <div class="font-bold text-slate-900 dark:text-white mt-0.5 tabular-nums">
                  <span>{{ overview.stats.today_total_visits ?? trafficReport?.summary?.total_visits ?? 0 }} 次</span>
                  <span class="text-xs font-medium text-slate-500 ml-1.5">/ {{ overview.stats.today_unique_ips ?? trafficReport?.summary?.unique_ips ?? 0 }} IP</span>
                </div>
              </div>
            </div>
            <button
              type="button"
              @click="activeTab = 'traffic'; loadTrafficReport()"
              class="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold transition-colors shrink-0"
            >
              <span>管理在线人数 / 看 24h IP 明细</span>
              <ArrowRight class="w-3.5 h-3.5" />
            </button>
          </div>

          <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 space-y-2 text-xs sm:text-sm">
            <h2 class="font-bold text-slate-900 dark:text-white">最新同步新闻批次状态</h2>
            <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-1">
              <div class="rounded-xl bg-slate-50 dark:bg-slate-800/60 p-3">
                <div class="text-slate-500 text-xs">当前简报批次</div>
                <div class="font-mono font-semibold text-slate-900 dark:text-white mt-0.5">
                  {{ formatFriendlyBatchId(overview.data_status.smart_batch_id) || '未同步' }}
                </div>
              </div>
              <div class="rounded-xl bg-slate-50 dark:bg-slate-800/60 p-3">
                <div class="text-slate-500 text-xs">更新时间</div>
                <div class="font-mono font-semibold text-slate-900 dark:text-white mt-0.5">{{ overview.data_status.smart_generated_at || '-' }}</div>
              </div>
              <div class="rounded-xl bg-slate-50 dark:bg-slate-800/60 p-3">
                <div class="text-slate-500 text-xs">在线信源数</div>
                <div class="font-semibold text-emerald-600 dark:text-emerald-400 mt-0.5">
                  {{ (overview.data_status.raw_summary as any)?.ok_sources ?? '-' }} / {{ (overview.data_status.raw_summary as any)?.configured_sources ?? '-' }} 在线
                </div>
              </div>
            </div>
          </div>

          <!-- Staged Marketing & Global Access Mode Console -->
          <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 space-y-5 text-xs sm:text-sm" data-testid="growth-console-card">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div class="space-y-1">
                <div class="flex flex-wrap items-center gap-2">
                  <Shield class="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
                  <h2 class="font-bold text-slate-900 dark:text-white">阶段式营销与门禁总控台</h2>
                  <span
                    class="px-2 py-0.5 rounded-full text-[11px] font-semibold"
                    :class="accessModeMeta(currentAccessMode).badgeClass"
                  >
                    {{ stageShortLabel(siteSettingsForm.growth_stage) }} · {{ accessModeMeta(currentAccessMode).shortLabel }}
                  </span>
                </div>
                <p class="text-xs text-slate-500">
                  支持一键预填四阶段营销预设或微调任意单点参数（仅预填充草稿并高亮差异，需确认保存后全站热生效，自动部署不会覆盖）。
                </p>
              </div>
              <span
                v-if="changedGrowthKeys.size > 0"
                class="px-2.5 py-1 rounded-full bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300 text-xs font-semibold shrink-0"
              >
                有 {{ changedGrowthKeys.size }} 项草稿待保存
              </span>
            </div>

            <!-- 4-Stage One-Click Draft Presets -->
            <div class="space-y-2">
              <div class="text-xs font-bold text-slate-700 dark:text-slate-200">一键预填运营阶段预设（先预填草稿，再由管理员确认保存）</div>
              <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5 text-xs">
                <button
                  v-for="preset in GROWTH_STAGE_PRESETS"
                  :key="preset.stage"
                  type="button"
                  :disabled="!isSuperAdmin || busyAction"
                  @click="applyStagePresetDraft(preset.stage)"
                  class="text-left rounded-xl border p-3 space-y-1 transition-all disabled:opacity-60"
                  :class="
                    growthDraft.growth_stage === preset.stage
                      ? 'border-indigo-500 bg-indigo-50/70 dark:bg-indigo-950/30 ring-1 ring-indigo-500'
                      : 'border-slate-200 dark:border-slate-800 hover:border-indigo-300 dark:hover:border-indigo-700'
                  "
                >
                  <div class="font-bold text-slate-900 dark:text-white flex items-center justify-between gap-1">
                    <span>{{ preset.title }}</span>
                    <span
                      v-if="siteSettingsForm.growth_stage === preset.stage"
                      class="px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300 text-[10px]"
                    >线上运行</span>
                  </div>
                  <p class="text-[11px] text-slate-500 dark:text-slate-400 leading-relaxed">{{ preset.subtitle }}</p>
                </button>
              </div>
            </div>

            <!-- Site Access Mode 3-Way Selector -->
            <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
              <label
                v-for="opt in ACCESS_MODE_OPTIONS"
                :key="opt.value"
                class="relative rounded-xl border p-3.5 transition-all flex flex-col justify-between gap-2"
                :class="[
                  growthDraft.access_mode === opt.value
                    ? opt.value === 'private_gate'
                      ? 'border-rose-500 bg-rose-50/50 dark:bg-rose-950/20 ring-1 ring-rose-500'
                      : opt.value === 'public'
                        ? 'border-emerald-500 bg-emerald-50/50 dark:bg-emerald-950/20 ring-1 ring-emerald-500'
                        : 'border-indigo-500 bg-indigo-50/50 dark:bg-indigo-950/20 ring-1 ring-indigo-500'
                    : 'border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700',
                  changedGrowthKeys.has('access_mode') && growthDraft.access_mode === opt.value ? 'ring-2 ring-amber-500' : '',
                  !isSuperAdmin ? 'opacity-70 cursor-not-allowed' : 'cursor-pointer',
                ]"
              >
                <div class="flex items-start justify-between gap-2">
                  <div class="flex items-center gap-2">
                    <input
                      v-model="growthDraft.access_mode"
                      type="radio"
                      name="site_access_mode"
                      :value="opt.value"
                      :disabled="!isSuperAdmin || busyAction"
                      class="mt-0.5 text-indigo-600 focus:ring-indigo-500"
                    />
                    <Globe v-if="opt.value === 'public'" class="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
                    <Ticket v-else-if="opt.value === 'invite_only'" class="w-4 h-4 text-indigo-600 dark:text-indigo-400 shrink-0" />
                    <Lock v-else class="w-4 h-4 text-rose-600 dark:text-rose-400 shrink-0" />
                    <span class="font-bold text-slate-900 dark:text-white text-xs sm:text-sm">{{ opt.title }}</span>
                  </div>
                  <span
                    class="px-1.5 py-0.5 rounded text-[10px] font-semibold shrink-0"
                    :class="accessModeMeta(opt.value).badgeClass"
                  >
                    {{ opt.badge }}
                  </span>
                </div>
                <p class="text-xs text-slate-600 dark:text-slate-300 leading-relaxed pl-6">
                  {{ opt.summary }}
                </p>
                <div
                  v-if="currentAccessMode === opt.value"
                  class="pl-6 inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700 dark:text-emerald-300"
                >
                  <CheckCircle2 class="w-3.5 h-3.5" />
                  <span>正在运行</span>
                </div>
              </label>
            </div>

            <!-- Granular Growth Toggles & Numeric Limits -->
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 text-xs pt-1 border-t border-slate-100 dark:border-slate-800">
              <label
                class="rounded-xl border p-3 flex items-start justify-between gap-2 cursor-pointer"
                :class="changedGrowthKeys.has('welcome_hero_enabled') ? 'border-amber-400 bg-amber-50/60 dark:bg-amber-950/20' : 'border-slate-200 dark:border-slate-800'"
              >
                <div>
                  <div class="font-bold text-slate-900 dark:text-white">新访客 3 秒价值条</div>
                  <div class="text-[11px] text-slate-500">对未登录新访客展示首屏 3 个体验胶囊</div>
                </div>
                <input v-model="growthDraft.welcome_hero_enabled" :disabled="!isSuperAdmin" type="checkbox" class="rounded w-4 h-4 text-indigo-600 mt-0.5" />
              </label>

              <label
                class="rounded-xl border p-3 flex items-start justify-between gap-2 cursor-pointer"
                :class="changedGrowthKeys.has('soft_auth_prompts_enabled') ? 'border-amber-400 bg-amber-50/60 dark:bg-amber-950/20' : 'border-slate-200 dark:border-slate-800'"
              >
                <div>
                  <div class="font-bold text-slate-900 dark:text-white">场景化软注册引导</div>
                  <div class="text-[11px] text-slate-500">保存持仓 / 投票 / 额度用尽时温和引导登录</div>
                </div>
                <input v-model="growthDraft.soft_auth_prompts_enabled" :disabled="!isSuperAdmin" type="checkbox" class="rounded w-4 h-4 text-indigo-600 mt-0.5" />
              </label>

              <label
                class="rounded-xl border p-3 flex items-start justify-between gap-2 cursor-pointer"
                :class="changedGrowthKeys.has('user_referral_enabled') ? 'border-amber-400 bg-amber-50/60 dark:bg-amber-950/20' : 'border-slate-200 dark:border-slate-800'"
              >
                <div>
                  <div class="font-bold text-slate-900 dark:text-white">用户裂变发码功能</div>
                  <div class="text-[11px] text-slate-500">开启后登录用户可在账号中心生成专属邀请链接</div>
                </div>
                <input v-model="growthDraft.user_referral_enabled" :disabled="!isSuperAdmin" type="checkbox" class="rounded w-4 h-4 text-indigo-600 mt-0.5" />
              </label>

              <label
                class="rounded-xl border p-3 flex items-start justify-between gap-2 cursor-pointer"
                :class="changedGrowthKeys.has('invite_waitlist_enabled') ? 'border-amber-400 bg-amber-50/60 dark:bg-amber-950/20' : 'border-slate-200 dark:border-slate-800'"
              >
                <div>
                  <div class="font-bold text-slate-900 dark:text-white">开启无码候补申请</div>
                  <div class="text-[11px] text-slate-500">邀请制下允许无码访客提交候补席位申请</div>
                </div>
                <input v-model="growthDraft.invite_waitlist_enabled" :disabled="!isSuperAdmin" type="checkbox" class="rounded w-4 h-4 text-indigo-600 mt-0.5" />
              </label>

              <label
                class="rounded-xl border p-3 flex items-start justify-between gap-2 cursor-pointer"
                :class="changedGrowthKeys.has('prediction_daily_market_enabled') ? 'border-amber-400 bg-amber-50/60 dark:bg-amber-950/20' : 'border-slate-200 dark:border-slate-800'"
              >
                <div>
                  <div class="font-bold text-slate-900 dark:text-white">自动每日行情日赛</div>
                  <div class="text-[11px] text-slate-500">每日自动生成标普/黄金/A股 T+1 预测题目并客观结算</div>
                </div>
                <input v-model="growthDraft.prediction_daily_market_enabled" :disabled="!isSuperAdmin" type="checkbox" class="rounded w-4 h-4 text-indigo-600 mt-0.5" />
              </label>

              <label
                class="rounded-xl border p-3 flex items-start justify-between gap-2 cursor-pointer"
                :class="changedGrowthKeys.has('prediction_rewards_enabled') ? 'border-amber-400 bg-amber-50/60 dark:bg-amber-950/20' : 'border-slate-200 dark:border-slate-800'"
              >
                <div>
                  <div class="font-bold text-slate-900 dark:text-white">洞察分与连胜权益奖励</div>
                  <div class="text-[11px] text-slate-500">启用 Brier 洞察分、段位勋章、连胜 AI 加赠及邀请加额</div>
                </div>
                <input v-model="growthDraft.prediction_rewards_enabled" :disabled="!isSuperAdmin" type="checkbox" class="rounded w-4 h-4 text-indigo-600 mt-0.5" />
              </label>

              <label
                class="rounded-xl border p-3 flex items-start justify-between gap-2 cursor-pointer"
                :class="changedGrowthKeys.has('prediction_proposals_enabled') ? 'border-amber-400 bg-amber-50/60 dark:bg-amber-950/20' : 'border-slate-200 dark:border-slate-800'"
              >
                <div>
                  <div class="font-bold text-slate-900 dark:text-white">用户预测题共创投稿</div>
                  <div class="text-[11px] text-slate-500">允许登录用户提交可核验预测题提案供管理员采纳</div>
                </div>
                <input v-model="growthDraft.prediction_proposals_enabled" :disabled="!isSuperAdmin" type="checkbox" class="rounded w-4 h-4 text-indigo-600 mt-0.5" />
              </label>

              <div
                class="rounded-xl border p-3 space-y-1"
                :class="changedGrowthKeys.has('guest_qa_daily_limit') ? 'border-amber-400 bg-amber-50/60 dark:bg-amber-950/20' : 'border-slate-200 dark:border-slate-800'"
              >
                <label class="block font-bold text-slate-900 dark:text-white">游客每日 AI 问答限额（0~100）</label>
                <input v-model.number="growthDraft.guest_qa_daily_limit" :disabled="!isSuperAdmin" type="number" min="0" max="100" class="w-full h-8 px-2.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 font-mono" />
              </div>

              <div
                class="rounded-xl border p-3 space-y-1"
                :class="changedGrowthKeys.has('auth_qa_daily_limit') ? 'border-amber-400 bg-amber-50/60 dark:bg-amber-950/20' : 'border-slate-200 dark:border-slate-800'"
              >
                <label class="block font-bold text-slate-900 dark:text-white">登录用户每日 AI 基础额度（1~500）</label>
                <input v-model.number="growthDraft.auth_qa_daily_limit" :disabled="!isSuperAdmin" type="number" min="1" max="500" class="w-full h-8 px-2.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 font-mono" />
              </div>

              <div
                class="rounded-xl border p-3 space-y-1"
                :class="changedGrowthKeys.has('crowd_vote_min_unlock') ? 'border-amber-400 bg-amber-50/60 dark:bg-amber-950/20' : 'border-slate-200 dark:border-slate-800'"
              >
                <label class="block font-bold text-slate-900 dark:text-white">前瞻共识解锁人数门槛（1~50）</label>
                <input v-model.number="growthDraft.crowd_vote_min_unlock" :disabled="!isSuperAdmin" type="number" min="1" max="50" class="w-full h-8 px-2.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 font-mono" />
              </div>

              <div
                class="rounded-xl border p-3 space-y-1"
                :class="changedGrowthKeys.has('user_invite_quota') ? 'border-amber-400 bg-amber-50/60 dark:bg-amber-950/20' : 'border-slate-200 dark:border-slate-800'"
              >
                <label class="block font-bold text-slate-900 dark:text-white">单用户可生成邀请码上限（0~50）</label>
                <input v-model.number="growthDraft.user_invite_quota" :disabled="!isSuperAdmin" type="number" min="0" max="50" class="w-full h-8 px-2.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 font-mono" />
              </div>

              <div
                class="rounded-xl border p-3 space-y-1"
                :class="changedGrowthKeys.has('referral_bonus_qa_quota') ? 'border-amber-400 bg-amber-50/60 dark:bg-amber-950/20' : 'border-slate-200 dark:border-slate-800'"
              >
                <label class="block font-bold text-slate-900 dark:text-white">邀请双方 AI 额度加成（0~100）</label>
                <input v-model.number="growthDraft.referral_bonus_qa_quota" :disabled="!isSuperAdmin" type="number" min="0" max="100" class="w-full h-8 px-2.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 font-mono" />
              </div>
            </div>

            <!-- Weekly Major Events Digest Auto-Publish Schedule -->
            <div
              class="rounded-xl border p-3.5 space-y-2.5 text-xs"
              :class="
                changedGrowthKeys.has('weekly_digest_enabled') ||
                changedGrowthKeys.has('weekly_digest_day') ||
                changedGrowthKeys.has('weekly_digest_hour') ||
                changedGrowthKeys.has('weekly_digest_minute')
                  ? 'border-amber-400 bg-amber-50/50 dark:bg-amber-950/20'
                  : 'border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-800/30'
              "
              data-testid="admin-weekly-schedule-panel"
            >
              <div class="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div class="font-bold text-slate-900 dark:text-white">每周盘点 · 一周大事自动出刊排班（北京时间 Mon-Sun）</div>
                  <div class="text-[11px] text-slate-500 dark:text-slate-400">
                    默认每周日 18:00 汇总本周一至周日去重提纯大事；云端工作流每小时检测本配置并在目标时段自动出刊同步 R2。
                  </div>
                </div>
                <label class="inline-flex items-center gap-2 font-semibold text-slate-800 dark:text-slate-100 cursor-pointer shrink-0">
                  <input v-model="growthDraft.weekly_digest_enabled" :disabled="!isSuperAdmin" type="checkbox" class="rounded w-4 h-4 text-indigo-600" />
                  <span>{{ growthDraft.weekly_digest_enabled ? '已开启自动出刊' : '已暂停自动出刊' }}</span>
                </label>
              </div>

              <div class="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                <div class="space-y-1">
                  <label class="block text-[11px] font-semibold text-slate-600 dark:text-slate-300">每周更新星期</label>
                  <select
                    v-model.number="growthDraft.weekly_digest_day"
                    :disabled="!isSuperAdmin"
                    class="w-full h-8 px-2.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs font-medium"
                  >
                    <option :value="0">每周日（默认）</option>
                    <option :value="1">每周一</option>
                    <option :value="2">每周二</option>
                    <option :value="3">每周三</option>
                    <option :value="4">每周四</option>
                    <option :value="5">每周五</option>
                    <option :value="6">每周六</option>
                  </select>
                </div>

                <div class="space-y-1">
                  <label class="block text-[11px] font-semibold text-slate-600 dark:text-slate-300">更新小时（00-23 CST）</label>
                  <select
                    v-model.number="growthDraft.weekly_digest_hour"
                    :disabled="!isSuperAdmin"
                    class="w-full h-8 px-2.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs font-mono"
                  >
                    <option v-for="h in 24" :key="h - 1" :value="h - 1">
                      {{ String(h - 1).padStart(2, '0') }} 点
                    </option>
                  </select>
                </div>

                <div class="space-y-1">
                  <label class="block text-[11px] font-semibold text-slate-600 dark:text-slate-300">展示分钟（00-59）</label>
                  <input
                    v-model.number="growthDraft.weekly_digest_minute"
                    :disabled="!isSuperAdmin"
                    type="number"
                    min="0"
                    max="59"
                    class="w-full h-8 px-2.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 font-mono"
                  />
                </div>
              </div>
            </div>

            <div class="flex flex-wrap items-center justify-between gap-3 pt-1 text-xs">
              <div v-if="!isSuperAdmin" class="inline-flex items-center gap-1.5 text-amber-700 dark:text-amber-300 font-medium">
                <AlertTriangle class="w-3.5 h-3.5 shrink-0" />
                <span>仅一级最高管理员可修改全站访问门禁与营销增长策略（当前为只读预览）</span>
              </div>
              <div v-else class="text-slate-500">
                <span v-if="changedGrowthKeys.size > 0" class="text-amber-700 dark:text-amber-300 font-semibold">
                  已标亮 {{ changedGrowthKeys.size }} 项待保存变更（{{ Array.from(changedGrowthKeys).join(', ') }}）
                </span>
                <span v-else>所有阶段营销与门禁配置与线上保持一致。</span>
              </div>
              <div class="flex items-center gap-2">
                <button
                  v-if="isSuperAdmin && changedGrowthKeys.size > 0"
                  type="button"
                  @click="resetGrowthDraft"
                  class="px-3.5 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 font-medium hover:bg-slate-50 dark:hover:bg-slate-800"
                >
                  放弃草稿
                </button>
                <button
                  type="button"
                  :disabled="busyAction || !isSuperAdmin || changedGrowthKeys.size === 0"
                  @click="handleRequestSaveGrowthConsole"
                  class="px-4 py-2 rounded-xl font-semibold text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  :class="growthDraft.access_mode === 'private_gate' ? 'bg-rose-600 hover:bg-rose-700' : 'bg-indigo-600 hover:bg-indigo-700'"
                >
                  {{ busyAction ? '保存中...' : '保存阶段与门禁配置' }}
                </button>
              </div>
            </div>
          </div>

          <!-- Admin Visibility Switch for Monitor Page -->
          <div class="rounded-2xl border border-indigo-200/80 dark:border-indigo-900/70 bg-white dark:bg-slate-900 p-5 flex flex-wrap items-center justify-between gap-3 text-xs sm:text-sm">
            <div class="space-y-1">
              <h2 class="font-bold text-slate-900 dark:text-white">「情报监控」页面访问权限控制</h2>
              <p class="text-xs text-slate-500">
                当前状态：<strong>{{ monitorPublic ? '已对所有用户公开显示' : '已对普通用户隐藏（仅管理员可见）' }}</strong>。无论开关状态如何，管理员始终可直接进入查看。
              </p>
            </div>
            <div class="flex flex-wrap items-center gap-2">
              <a
                href="./monitor.html"
                class="px-3.5 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 font-semibold hover:bg-slate-50 dark:hover:bg-slate-800"
              >
                管理员直达情报监控 ↗
              </a>
              <button
                type="button"
                :disabled="busyAction"
                @click="toggleMonitorPublic"
                class="px-3.5 py-2 rounded-xl font-semibold text-white transition-colors"
                :class="monitorPublic ? 'bg-amber-600 hover:bg-amber-700' : 'bg-indigo-600 hover:bg-indigo-700'"
              >
                {{ monitorPublic ? '改为仅管理员可见' : '开放给普通用户查看' }}
              </button>
            </div>
          </div>
        </section>

        <!-- Tab 1.5: Live Online Counter Console & Daily IP Visit Frequency Analytics -->
        <section v-if="activeTab === 'traffic'" class="space-y-4">
          <!-- Card A: Front-end Online Counter Control Panel -->
          <div
            class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 space-y-4 text-xs sm:text-sm"
            data-testid="admin-online-config-card"
          >
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div class="space-y-1">
                <div class="flex flex-wrap items-center gap-2">
                  <SlidersHorizontal class="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                  <h2 class="text-sm sm:text-base font-bold text-slate-900 dark:text-white">
                    平台同时在线人数控制（网页端 &amp; 安卓端同步生效）
                  </h2>
                  <span
                    class="px-2 py-0.5 rounded-full text-[11px] font-semibold"
                    :class="siteSettingsForm.online_counter_mode === 'simulated' ? 'bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300' : 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300'"
                  >
                    {{ siteSettingsForm.online_counter_mode === 'simulated' ? '当前线上：自定义浮动假人数' : '当前线上：真实统计在线人数' }}
                  </span>
                </div>
                <p class="text-xs text-slate-500">
                  后台每 30 秒自动刷新真实数据，即使前台开启假人数，管理员仍可实时掌握真实活跃人数与登录构成。
                </p>
              </div>
              <div class="flex flex-wrap items-center gap-2">
                <button
                  v-if="siteSettingsForm.online_counter_mode === 'simulated' || onlineDraft.online_counter_mode === 'simulated'"
                  type="button"
                  :disabled="busyAction"
                  @click="handleRevertRealOnline"
                  data-testid="admin-revert-real-online-btn"
                  class="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold transition-colors"
                >
                  <RotateCcw class="w-3.5 h-3.5" />
                  <span>一键调回真实在线人数</span>
                </button>
                <span
                  v-if="changedOnlineKeys.size > 0"
                  class="px-2.5 py-1 rounded-full bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300 text-xs font-semibold"
                >
                  {{ changedOnlineKeys.size }} 项待保存
                </span>
              </div>
            </div>

            <!-- Prominent Dual Real vs Displayed Comparison Cards (Real stays visible even under Simulated Mode) -->
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs" data-testid="admin-online-real-vs-display">
              <div class="rounded-xl border border-emerald-200 dark:border-emerald-900/70 bg-emerald-50/50 dark:bg-emerald-950/20 p-3.5 space-y-1.5">
                <div class="flex items-center justify-between gap-2">
                  <span class="font-bold text-emerald-900 dark:text-emerald-200 flex items-center gap-1.5">
                    <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                    <span>真实同时在线人数（按 IP 去重 · 仅后台可见）</span>
                  </span>
                  <button
                    type="button"
                    @click="loadTrafficReport"
                    class="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700 dark:text-emerald-300 hover:underline"
                    title="立即刷新真实在线数据"
                  >
                    <RefreshCw class="w-3 h-3" :class="{ 'animate-spin': trafficLoading }" />
                    <span>30s 自动刷新</span>
                  </button>
                </div>
                <div class="flex items-baseline gap-2.5">
                  <span class="text-2xl font-bold text-emerald-700 dark:text-emerald-300 tabular-nums">{{ liveRealOnline.total }} 人</span>
                  <span class="text-slate-600 dark:text-slate-300 tabular-nums">
                    已登录 <strong class="text-slate-900 dark:text-white">{{ liveRealOnline.logged_in }}</strong> ·
                    未登录 <strong class="text-slate-900 dark:text-white">{{ liveRealOnline.guest }}</strong> ·
                    活跃窗口 2 分钟（{{ trafficReport?.active_sessions?.length ?? 0 }} 会话）
                  </span>
                </div>
              </div>

              <div
                class="rounded-xl border p-3.5 space-y-1.5"
                :class="siteSettingsForm.online_counter_mode === 'simulated' ? 'border-amber-200 dark:border-amber-900/70 bg-amber-50/50 dark:bg-amber-950/20' : 'border-indigo-200 dark:border-indigo-900/70 bg-indigo-50/40 dark:bg-indigo-950/20'"
              >
                <div class="flex items-center justify-between gap-2">
                  <span class="font-bold text-slate-900 dark:text-white">前台顶栏对外实时展示</span>
                  <span
                    class="px-2 py-0.5 rounded-full text-[10.5px] font-semibold"
                    :class="siteSettingsForm.online_counter_mode === 'simulated' ? 'bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300' : 'bg-indigo-100 text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300'"
                  >
                    {{ siteSettingsForm.online_counter_mode === 'simulated' ? '模拟假人数模式' : '同步真实在线' }}
                  </span>
                </div>
                <div class="flex items-baseline gap-2.5">
                  <span
                    class="text-2xl font-bold tabular-nums"
                    :class="siteSettingsForm.online_counter_mode === 'simulated' ? 'text-amber-700 dark:text-amber-300' : 'text-indigo-700 dark:text-indigo-300'"
                  >
                    {{ siteSettingsForm.online_counter_enabled === false ? '已隐藏' : `${liveDisplayedOnlineCount} ${siteSettingsForm.online_counter_label || '在线'}` }}
                  </span>
                  <span class="text-slate-600 dark:text-slate-300 tabular-nums">
                    <template v-if="siteSettingsForm.online_counter_mode === 'simulated'">
                      基准 {{ siteSettingsForm.online_sim_base ?? 68 }} · 浮动 ±{{ siteSettingsForm.online_sim_delta ?? 12 }} · 每 {{ siteSettingsForm.online_sim_interval_sec ?? 12 }}s 变动（真实统计仍独立运行）
                    </template>
                    <template v-else>
                      当前展示口径：{{ siteSettingsForm.online_real_scope === 'logged_in' ? '仅已登录用户' : siteSettingsForm.online_real_scope === 'guest' ? '仅未登录访客' : '全部在线（登录 + 未登录）' }}
                    </template>
                  </span>
                </div>
              </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs pt-1 border-t border-slate-100 dark:border-slate-800">
              <label class="rounded-xl border border-slate-200 dark:border-slate-800 p-3 flex items-center justify-between gap-2 cursor-pointer">
                <div>
                  <div class="font-bold text-slate-900 dark:text-white">前台顶栏显示在线人数</div>
                  <div class="text-[11px] text-slate-500">开启后 PC / 手机 / 安卓端顶部均显示在线胶囊</div>
                </div>
                <input v-model="onlineDraft.online_counter_enabled" type="checkbox" class="rounded w-4 h-4 text-emerald-600" />
              </label>

              <div class="rounded-xl border border-slate-200 dark:border-slate-800 p-3 space-y-1">
                <label class="block font-bold text-slate-900 dark:text-white">在线文案后缀（默认：在线）</label>
                <input
                  v-model="onlineDraft.online_counter_label"
                  type="text"
                  maxlength="16"
                  placeholder="在线"
                  class="w-full h-8 px-2.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs"
                />
              </div>

              <div class="rounded-xl border border-slate-200 dark:border-slate-800 p-3 space-y-1.5">
                <div class="font-bold text-slate-900 dark:text-white">在线统计口径模式</div>
                <div class="grid grid-cols-2 gap-1.5">
                  <button
                    type="button"
                    @click="onlineDraft.online_counter_mode = 'real'"
                    data-testid="online-mode-real"
                    class="h-8 px-2 rounded-lg text-xs font-semibold border transition-colors"
                    :class="onlineDraft.online_counter_mode === 'real' ? 'bg-emerald-600 text-white border-emerald-600' : 'border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-300'"
                  >
                    真实在线人数
                  </button>
                  <button
                    type="button"
                    @click="onlineDraft.online_counter_mode = 'simulated'"
                    data-testid="online-mode-simulated"
                    class="h-8 px-2 rounded-lg text-xs font-semibold border transition-colors"
                    :class="onlineDraft.online_counter_mode === 'simulated' ? 'bg-amber-600 text-white border-amber-600' : 'border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-300'"
                  >
                    自定义/伪造人数
                  </button>
                </div>
              </div>
            </div>

            <!-- Real Scope Selector -->
            <div
              v-if="onlineDraft.online_counter_mode === 'real'"
              class="rounded-xl border border-emerald-200/80 dark:border-emerald-900/60 bg-emerald-50/40 dark:bg-emerald-950/15 p-3.5 space-y-2 text-xs"
            >
              <div class="font-bold text-slate-900 dark:text-white">选择真实在线人群展示范围</div>
              <div class="grid grid-cols-1 sm:grid-cols-3 gap-2">
                <label
                  v-for="opt in [
                    { id: 'all', title: '全部在线（登录 + 未登录）', desc: '同时统计已登录与未登录访客（同一 IP 多浏览器合并计为 1 人）' },
                    { id: 'logged_in', title: '仅显示已登录用户', desc: '只展示当前有已登录会话的活跃 IP 人数' },
                    { id: 'guest', title: '仅显示未登录访客', desc: '只展示纯未登录访客的活跃 IP 人数' },
                  ] as const"
                  :key="opt.id"
                  class="rounded-xl border p-2.5 flex items-start gap-2 cursor-pointer transition-colors"
                  :class="onlineDraft.online_real_scope === opt.id ? 'border-emerald-500 bg-white dark:bg-slate-900 ring-1 ring-emerald-500' : 'border-slate-200 dark:border-slate-800 bg-white/60 dark:bg-slate-900/50'"
                >
                  <input v-model="onlineDraft.online_real_scope" type="radio" :value="opt.id" class="mt-0.5 text-emerald-600" />
                  <div>
                    <div class="font-bold text-slate-900 dark:text-white">{{ opt.title }}</div>
                    <div class="text-[11px] text-slate-500 leading-relaxed">{{ opt.desc }}</div>
                  </div>
                </label>
              </div>
            </div>

            <!-- Simulated Online Config -->
            <div
              v-else
              class="rounded-xl border border-amber-200 dark:border-amber-900/70 bg-amber-50/50 dark:bg-amber-950/20 p-3.5 space-y-3 text-xs"
            >
              <div class="flex flex-wrap items-center justify-between gap-2">
                <div class="font-bold text-slate-900 dark:text-white">自定义（伪造）在线人数与波动参数</div>
                <span class="text-[11px] font-semibold text-amber-800 dark:text-amber-300 tabular-nums">
                  波动范围预览：{{ simulatedPreviewRange.min }} ~ {{ simulatedPreviewRange.max }} 人（当前时刻计算值：{{ simulatedPreviewRange.sample }}）
                </span>
              </div>
              <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div class="space-y-1">
                  <label class="block font-semibold text-slate-700 dark:text-slate-300">基准在线人数（1 ~ 99999）</label>
                  <input
                    v-model.number="onlineDraft.online_sim_base"
                    type="number"
                    min="1"
                    max="99999"
                    class="w-full h-9 px-3 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 font-mono"
                  />
                </div>
                <div class="space-y-1">
                  <label class="block font-semibold text-slate-700 dark:text-slate-300">上下浮动幅度（±N，0 ~ 50000）</label>
                  <input
                    v-model.number="onlineDraft.online_sim_delta"
                    type="number"
                    min="0"
                    max="50000"
                    class="w-full h-9 px-3 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 font-mono"
                  />
                </div>
                <div class="space-y-1">
                  <label class="block font-semibold text-slate-700 dark:text-slate-300">人数变动频率（秒，3 ~ 300）</label>
                  <input
                    v-model.number="onlineDraft.online_sim_interval_sec"
                    type="number"
                    min="3"
                    max="300"
                    class="w-full h-9 px-3 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 font-mono"
                  />
                  <div class="flex flex-wrap gap-1 pt-0.5">
                    <button
                      v-for="sec in [5, 10, 15, 30, 60]"
                      :key="sec"
                      type="button"
                      @click="onlineDraft.online_sim_interval_sec = sec"
                      class="px-2 py-0.5 rounded border text-[11px] font-mono"
                      :class="onlineDraft.online_sim_interval_sec === sec ? 'bg-amber-600 text-white border-amber-600' : 'border-slate-300 dark:border-slate-700 text-slate-600 dark:text-slate-300'"
                    >
                      {{ sec }}s
                    </button>
                  </div>
                </div>
              </div>
              <p class="text-[11px] text-slate-500">
                提示：所有在线访客看到的人数将按相同时间槽平滑游走、在您设定的基准值上下自然跳动，不会每次刷新乱跳；任何时候点击「一键调回真实在线人数」即可立即切回真实心跳统计。
              </p>
            </div>

            <div class="flex flex-wrap items-center justify-end gap-2">
              <button
                v-if="changedOnlineKeys.size > 0"
                type="button"
                @click="resetOnlineDraft"
                class="px-3.5 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 text-xs font-medium"
              >
                还原未保存修改
              </button>
              <button
                type="button"
                :disabled="busyAction"
                @click="handleSaveOnlineConfig"
                data-testid="save-online-config-btn"
                class="px-4 py-2 rounded-xl bg-slate-900 dark:bg-blue-600 text-white text-xs font-semibold hover:opacity-95 disabled:opacity-50"
              >
                {{ busyAction ? '保存中...' : '保存在线人数配置' }}
              </button>
            </div>
          </div>

          <!-- Card B: Daily Web Traffic Frequency & 24-Hour Distribution -->
          <div
            class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 space-y-4 text-xs sm:text-sm"
            data-testid="admin-traffic-overview-card"
          >
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 class="text-sm sm:text-base font-bold text-slate-900 dark:text-white">单日网页访问频率分析（登录 + 未登录 · 北京时间）</h2>
                <p class="text-xs text-slate-500">每次页面进入、关闭切回超过 10 分钟计为 1 次独立访问，50 秒保活心跳（静置 10 分钟自动休眠节省免费额度）。</p>
              </div>
              <div class="flex flex-wrap items-center gap-2 text-xs">
                <select
                  v-model="trafficDay"
                  @change="loadTrafficReport"
                  class="h-8 px-2.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 font-mono"
                >
                  <option v-for="d in trafficReport?.available_days || (trafficDay ? [trafficDay] : [])" :key="d" :value="d">
                    {{ d }}{{ d === trafficReport?.today_cst ? '（今日）' : '' }}
                  </option>
                </select>
                <button
                  type="button"
                  :disabled="trafficLoading"
                  @click="loadTrafficReport"
                  class="inline-flex items-center gap-1 h-8 px-3 rounded-lg border border-slate-300 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 font-medium"
                >
                  <RefreshCw class="w-3.5 h-3.5" :class="{ 'animate-spin': trafficLoading }" />
                  <span>刷新统计</span>
                </button>
              </div>
            </div>

            <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 text-xs">
              <div class="rounded-xl bg-slate-50 dark:bg-slate-800/60 p-3.5">
                <div class="text-slate-500">当日总访问次数</div>
                <div class="text-xl font-bold text-slate-900 dark:text-white mt-1 tabular-nums">
                  {{ trafficReport?.summary?.total_visits ?? 0 }}
                </div>
                <div class="text-[11px] text-slate-500 mt-1 tabular-nums">
                  已登录 {{ trafficReport?.summary?.auth_visits ?? 0 }} · 未登录 {{ trafficReport?.summary?.guest_visits ?? 0 }}
                </div>
              </div>
              <div class="rounded-xl bg-slate-50 dark:bg-slate-800/60 p-3.5">
                <div class="text-slate-500">当日独立 IP 数</div>
                <div class="text-xl font-bold text-indigo-600 dark:text-indigo-400 mt-1 tabular-nums">
                  {{ trafficReport?.summary?.unique_ips ?? 0 }}
                </div>
                <div class="text-[11px] text-slate-500 mt-1 tabular-nums">
                  含登录 IP {{ trafficReport?.summary?.auth_ips ?? 0 }} · 纯访客 IP {{ trafficReport?.summary?.guest_only_ips ?? 0 }}
                </div>
              </div>
              <div class="rounded-xl bg-slate-50 dark:bg-slate-800/60 p-3.5">
                <div class="text-slate-500">平均每 IP 访问频次</div>
                <div class="text-xl font-bold text-emerald-600 dark:text-emerald-400 mt-1 tabular-nums">
                  {{ (trafficReport?.summary?.avg_visits_per_ip ?? 0).toFixed(2) }}x
                </div>
                <div class="text-[11px] text-slate-500 mt-1 tabular-nums">
                  回头高频 IP（&ge;2 次）{{ trafficReport?.summary?.repeat_ips ?? 0 }} 个
                </div>
              </div>
              <div class="rounded-xl bg-slate-50 dark:bg-slate-800/60 p-3.5">
                <div class="text-slate-500">访问高峰时段（CST）</div>
                <div class="text-xl font-bold text-amber-600 dark:text-amber-400 mt-1 font-mono tabular-nums">
                  {{ trafficReport?.summary?.peak_hour ? trafficReport.summary.peak_hour.label : '--:--' }}
                </div>
                <div class="text-[11px] text-slate-500 mt-1 tabular-nums">
                  高峰 {{ trafficReport?.summary?.peak_hour?.total_visits ?? 0 }} 次 · 总心跳 {{ trafficReport?.summary?.total_heartbeats ?? 0 }}
                </div>
              </div>
            </div>

            <!-- 24h Hourly Stacked Bar Chart -->
            <div class="space-y-2 pt-1">
              <div class="flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-500">
                <div class="flex items-center gap-3">
                  <span class="inline-flex items-center gap-1"><span class="w-2.5 h-2.5 rounded-xs bg-indigo-500" /> 已登录访问</span>
                  <span class="inline-flex items-center gap-1"><span class="w-2.5 h-2.5 rounded-xs bg-sky-400" /> 未登录访问</span>
                </div>
                <div v-if="hoveredHourlyRow" class="font-mono text-slate-700 dark:text-slate-200 font-semibold">
                  {{ hoveredHourlyRow.label }}：共 {{ hoveredHourlyRow.total_visits }} 次（登录 {{ hoveredHourlyRow.auth_visits }} · 访客 {{ hoveredHourlyRow.guest_visits }} · 独立 IP {{ hoveredHourlyRow.unique_ips }}）
                </div>
                <div v-else>悬停或点击柱状条查看各小时频次详情</div>
              </div>

              <div class="grid grid-cols-[repeat(24,minmax(0,1fr))] gap-1 items-end h-28 pt-3 px-2 pb-1 rounded-xl bg-slate-50 dark:bg-slate-800/40 border border-slate-200/70 dark:border-slate-800">
                <button
                  v-for="h in trafficReport?.hourly || []"
                  :key="h.hour"
                  type="button"
                  @mouseenter="hoveredHour = h.hour"
                  @focus="hoveredHour = h.hour"
                  @click="hoveredHour = h.hour"
                  class="group relative flex flex-col justify-end items-stretch h-full rounded-t focus:outline-none"
                  :title="`${h.label} · 总 ${h.total_visits} 次（登录 ${h.auth_visits} / 访客 ${h.guest_visits} / 独立IP ${h.unique_ips}）`"
                >
                  <div
                    class="w-full flex flex-col justify-end overflow-hidden rounded-t-sm transition-all"
                    :style="{ height: `${h.total_visits > 0 ? Math.max(8, Math.round((h.total_visits / hourlyMaxVisits) * 100)) : 2}%` }"
                    :class="hoveredHour === h.hour ? 'ring-1 ring-slate-900 dark:ring-white' : ''"
                  >
                    <div
                      v-if="h.guest_visits > 0"
                      class="w-full bg-sky-400 dark:bg-sky-500"
                      :style="{ height: `${Math.round((h.guest_visits / Math.max(1, h.total_visits)) * 100)}%` }"
                    />
                    <div
                      v-if="h.auth_visits > 0"
                      class="w-full bg-indigo-500 dark:bg-indigo-400"
                      :style="{ height: `${Math.round((h.auth_visits / Math.max(1, h.total_visits)) * 100)}%` }"
                    />
                    <div
                      v-if="h.total_visits === 0"
                      class="w-full h-full bg-slate-200 dark:bg-slate-700/60"
                    />
                  </div>
                </button>
              </div>
              <div class="flex justify-between text-[10px] font-mono text-slate-400 px-1">
                <span>00:00</span>
                <span>06:00</span>
                <span>12:00</span>
                <span>18:00</span>
                <span>23:00</span>
              </div>
            </div>
          </div>

          <!-- Card C: IP Visit Frequency Breakdown Table -->
          <div
            class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 space-y-3 text-xs"
            data-testid="admin-traffic-ip-table"
          >
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h3 class="text-sm sm:text-base font-bold text-slate-900 dark:text-white">
                  按 IP 统计的当日访问明细（共 {{ filteredTrafficRows.length }} / {{ trafficReport?.filtered_total ?? filteredTrafficRows.length }} 个 IP）
                </h3>
                <p class="text-[11px] text-slate-500">精确记录每个 IP 当日访问总次数、登录 vs 未登录拆分、关联账号、访问端及活跃时间。</p>
              </div>
              <div class="flex flex-wrap items-center gap-1.5">
                <button
                  v-for="f in [
                    { id: 'all', label: '全部 IP' },
                    { id: 'auth', label: '含已登录' },
                    { id: 'guest', label: '仅未登录' },
                    { id: 'online', label: '当前在线' },
                  ] as const"
                  :key="f.id"
                  type="button"
                  @click="trafficFilter = f.id"
                  class="px-2.5 py-1 rounded-lg border font-medium transition-colors"
                  :class="trafficFilter === f.id ? 'bg-slate-900 text-white border-slate-900 dark:bg-blue-600 dark:border-blue-600' : 'border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300'"
                >
                  {{ f.label }}
                </button>
              </div>
            </div>

            <div class="flex flex-wrap items-center justify-between gap-2">
              <div class="relative flex-1 min-w-[200px] max-w-sm">
                <Search class="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
                <input
                  v-model="trafficSearch"
                  type="text"
                  placeholder="搜索 IP、关联用户名、国家/地区或停留板块..."
                  class="w-full h-8 pl-8 pr-3 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs"
                />
              </div>
              <div class="flex items-center gap-1.5">
                <button
                  type="button"
                  @click="trafficSort = 'visits'; loadTrafficReport()"
                  class="px-2.5 py-1 rounded-lg border font-medium"
                  :class="trafficSort === 'visits' ? 'bg-indigo-600 text-white border-indigo-600' : 'border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300'"
                >
                  按当日访问次数
                </button>
                <button
                  type="button"
                  @click="trafficSort = 'recent'; loadTrafficReport()"
                  class="px-2.5 py-1 rounded-lg border font-medium"
                  :class="trafficSort === 'recent' ? 'bg-indigo-600 text-white border-indigo-600' : 'border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300'"
                >
                  按最近活跃时间
                </button>
              </div>
            </div>

            <div v-if="!filteredTrafficRows.length" class="py-8 text-center text-slate-400">
              当日暂无匹配的 IP 访问记录
            </div>
            <div v-else class="overflow-x-auto">
              <table class="w-full text-left border-collapse text-xs">
                <thead>
                  <tr class="border-b border-slate-200 dark:border-slate-800 text-slate-500">
                    <th class="py-2 pr-3 font-semibold">IP 地址 / 地区</th>
                    <th class="py-2 px-3 font-semibold">当日访问次数</th>
                    <th class="py-2 px-3 font-semibold">身份与关联账号</th>
                    <th class="py-2 px-3 font-semibold">终端与最近板块</th>
                    <th class="py-2 pl-3 font-semibold">首访 / 最近活跃 (CST)</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-100 dark:divide-slate-800/70">
                  <tr
                    v-for="row in filteredTrafficRows"
                    :key="`${row.day_cst}:${row.ip}`"
                    class="hover:bg-slate-50/80 dark:hover:bg-slate-800/30"
                  >
                    <td class="py-2.5 pr-3 whitespace-nowrap">
                      <div class="flex items-center gap-1.5">
                        <span
                          class="w-2 h-2 rounded-full shrink-0"
                          :class="row.is_online ? 'bg-emerald-500' : 'bg-slate-300 dark:bg-slate-700'"
                          :title="row.is_online ? '当前在线' : '离线'"
                        />
                        <span class="font-mono font-semibold text-slate-900 dark:text-white">{{ row.ip }}</span>
                        <button
                          type="button"
                          @click="copyIpAddress(row.ip)"
                          class="text-slate-400 hover:text-slate-700 dark:hover:text-white p-0.5"
                          title="复制 IP"
                        >
                          <Copy class="w-3 h-3" />
                        </button>
                        <span
                          v-if="row.country"
                          class="px-1.5 py-0.2 rounded bg-slate-100 dark:bg-slate-800 text-[10px] font-mono text-slate-500"
                        >
                          {{ row.country }}
                        </span>
                      </div>
                    </td>
                    <td class="py-2.5 px-3 whitespace-nowrap tabular-nums">
                      <div class="font-bold text-slate-900 dark:text-white text-[13px]">{{ row.visit_count }} 次</div>
                      <div class="text-[11px] text-slate-500">
                        登录 {{ row.auth_visit_count }} · 访客 {{ row.guest_visit_count }} · 心跳 {{ row.heartbeat_count }}
                      </div>
                    </td>
                    <td class="py-2.5 px-3">
                      <div v-if="row.usernames.length > 0" class="flex flex-wrap gap-1">
                        <span
                          v-for="uname in row.usernames"
                          :key="uname"
                          class="px-1.5 py-0.5 rounded bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 font-semibold"
                        >
                          @{{ uname }}
                        </span>
                      </div>
                      <span v-else class="px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-500">
                        未登录访客
                      </span>
                    </td>
                    <td class="py-2.5 px-3 whitespace-nowrap">
                      <div class="flex flex-wrap items-center gap-1">
                        <span
                          v-for="pl in row.platforms"
                          :key="pl"
                          class="px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 text-[10px]"
                        >
                          {{ platformLabel(pl) }}
                        </span>
                        <span class="text-[11px] text-slate-500">· {{ tabLabel(row.last_tab) }}</span>
                      </div>
                    </td>
                    <td class="py-2.5 pl-3 whitespace-nowrap font-mono text-[11px] text-slate-500 tabular-nums">
                      <div>末 {{ formatCstTimeOnly(row.last_seen_at) }}</div>
                      <div class="text-slate-400">首 {{ formatCstTimeOnly(row.first_seen_at) }}</div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- Card D: Live Active Sessions Drawer -->
          <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 space-y-3 text-xs">
            <div class="flex items-center justify-between gap-2">
              <h3 class="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-2">
                <Clock class="w-4 h-4 text-emerald-500" />
                <span>当前活跃在线会话列表（去重后 {{ liveRealOnline.total }} 人在线 · {{ trafficReport?.active_sessions?.length ?? 0 }} 个浏览器会话，最近 2 分钟心跳）</span>
              </h3>
              <button
                type="button"
                @click="trafficSessionsExpanded = !trafficSessionsExpanded"
                class="text-xs text-blue-600 dark:text-blue-400 font-semibold"
              >
                {{ trafficSessionsExpanded ? '收起' : '展开' }}
              </button>
            </div>
            <div v-if="trafficSessionsExpanded">
              <div v-if="!trafficReport?.active_sessions?.length" class="py-4 text-center text-slate-400">
                当前 2 分钟窗口内暂无活跃会话心跳
              </div>
              <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                <div
                  v-for="s in trafficReport.active_sessions"
                  :key="s.session_key"
                  class="rounded-xl border border-slate-200/80 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-800/40 p-3 flex items-center justify-between gap-2"
                >
                  <div class="min-w-0 space-y-0.5">
                    <div class="flex items-center gap-1.5">
                      <span class="w-2 h-2 rounded-full bg-emerald-500 shrink-0" />
                      <span class="font-semibold text-slate-900 dark:text-white truncate">
                        {{ s.is_logged_in ? `@${s.username}` : '未登录访客' }}
                      </span>
                      <span class="px-1.5 py-0.2 rounded bg-white dark:bg-slate-900 text-[10px] text-slate-500 shrink-0">
                        {{ platformLabel(s.platform) }}
                      </span>
                    </div>
                    <div class="font-mono text-[11px] text-slate-500 truncate">
                      {{ s.ip }}{{ s.country ? ` · ${s.country}` : '' }} · {{ tabLabel(s.current_tab) }}
                    </div>
                  </div>
                  <span class="font-mono text-[10.5px] text-slate-400 shrink-0">{{ formatCstTimeOnly(s.last_seen_at) }}</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- Tab 2: Feedback & Channel Config -->
        <section v-if="activeTab === 'feedback'" class="space-y-4">
          <form
            @submit.prevent="
              saveSiteSettingsPartial(
                {
                  feedback_enabled: siteSettingsForm.feedback_enabled,
                  feedback_notice: siteSettingsForm.feedback_notice,
                  feedback_contact_wechat: siteSettingsForm.feedback_contact_wechat,
                  feedback_contact_email: siteSettingsForm.feedback_contact_email,
                  feedback_contact_group: siteSettingsForm.feedback_contact_group,
                  feedback_contact_qr_url: siteSettingsForm.feedback_contact_qr_url,
                  feedback_daily_limit: siteSettingsForm.feedback_daily_limit,
                },
                '意见反馈渠道配置已保存并全站生效！',
              )
            "
            class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 space-y-3.5 text-xs"
          >
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 class="text-sm sm:text-base font-bold text-slate-900 dark:text-white">用户反馈渠道与频控配置</h2>
                <p class="text-slate-500">保存后将即时同步到全站「意见反馈」弹窗顶部提示与官方联系入口。</p>
              </div>
              <label class="inline-flex items-center gap-2 font-semibold cursor-pointer">
                <input v-model="siteSettingsForm.feedback_enabled" type="checkbox" class="rounded w-4 h-4 text-blue-600" />
                <span>开启在线提交反馈</span>
              </label>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div class="md:col-span-2">
                <label class="block text-slate-500 mb-1">反馈弹窗顶部公告 / 引导文案</label>
                <input
                  v-model="siteSettingsForm.feedback_notice"
                  type="text"
                  maxlength="400"
                  placeholder="例如：欢迎反馈页面问题或数据纠错..."
                  class="w-full h-9 px-3 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800"
                />
              </div>
              <div>
                <label class="block text-slate-500 mb-1">官方联系微信（选填）</label>
                <input
                  v-model="siteSettingsForm.feedback_contact_wechat"
                  type="text"
                  placeholder="微信号"
                  class="w-full h-9 px-3 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800"
                />
              </div>
              <div>
                <label class="block text-slate-500 mb-1">官方联系邮箱（选填）</label>
                <input
                  v-model="siteSettingsForm.feedback_contact_email"
                  type="text"
                  placeholder="support@example.com"
                  class="w-full h-9 px-3 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800"
                />
              </div>
              <div>
                <label class="block text-slate-500 mb-1">社群 / 交流群号（选填）</label>
                <input
                  v-model="siteSettingsForm.feedback_contact_group"
                  type="text"
                  placeholder="QQ 群 / 微信群口令"
                  class="w-full h-9 px-3 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800"
                />
              </div>
              <div class="grid grid-cols-3 gap-2">
                <div class="col-span-2">
                  <label class="block text-slate-500 mb-1">二维码图片链接（选填）</label>
                  <input
                    v-model="siteSettingsForm.feedback_contact_qr_url"
                    type="text"
                    placeholder="https://..."
                    class="w-full h-9 px-3 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800"
                  />
                </div>
                <div>
                  <label class="block text-slate-500 mb-1">单用户日限额</label>
                  <input
                    v-model.number="siteSettingsForm.feedback_daily_limit"
                    type="number"
                    min="1"
                    max="50"
                    class="w-full h-9 px-3 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800"
                  />
                </div>
              </div>
            </div>

            <div class="flex justify-end">
              <button
                type="submit"
                :disabled="busyAction"
                class="px-4 py-2 rounded-xl bg-blue-600 text-white font-semibold hover:bg-blue-700 disabled:opacity-60"
              >
                保存渠道设置
              </button>
            </div>
          </form>

          <!-- Feedback Inbox -->
          <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 space-y-3 text-xs">
            <div class="flex flex-wrap items-center justify-between gap-2">
              <h3 class="text-sm font-bold text-slate-900 dark:text-white">用户反馈工单列表 ({{ feedbackItems.length }})</h3>
              <div class="flex flex-wrap gap-1.5">
                <button
                  v-for="opt in [
                    { id: '', label: '全部' },
                    { id: 'pending', label: '待受理' },
                    { id: 'in_progress', label: '处理中' },
                    { id: 'replied', label: '已回复' },
                    { id: 'resolved', label: '已解决' },
                  ]"
                  :key="opt.id"
                  type="button"
                  @click="feedbackStatusFilter = opt.id; loadFeedbackList()"
                  class="px-2.5 py-1 rounded-lg border font-medium transition-colors"
                  :class="feedbackStatusFilter === opt.id ? 'bg-slate-900 text-white border-slate-900 dark:bg-blue-600 dark:border-blue-600' : 'border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300'"
                >
                  {{ opt.label }}
                </button>
              </div>
            </div>

            <div v-if="!feedbackItems.length" class="py-8 text-center text-slate-400">暂无匹配的反馈记录</div>

            <div v-else class="space-y-3">
              <article
                v-for="fb in feedbackItems"
                :key="fb.id"
                class="rounded-xl border border-slate-200/80 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-800/40 p-3.5 space-y-2.5"
              >
                <div class="flex flex-wrap items-center justify-between gap-2">
                  <div class="flex flex-wrap items-center gap-2">
                    <span class="font-mono font-bold text-slate-700 dark:text-slate-200">#{{ fb.id }}</span>
                    <span class="px-2 py-0.5 rounded bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 font-semibold">
                      {{ fb.category }}
                    </span>
                    <span class="text-slate-600 dark:text-slate-300 font-medium">
                      {{ fb.username ? `@${fb.username}` : '访客' }} · {{ fb.contact || '无联系方式' }}
                    </span>
                  </div>
                  <span class="font-mono text-slate-400">{{ String(fb.created_at || '').slice(0, 19).replace('T', ' ') }}</span>
                </div>

                <p class="text-slate-800 dark:text-slate-100 leading-relaxed whitespace-pre-wrap">{{ fb.content }}</p>

                <div v-if="fb.page_url" class="text-[11px] text-slate-400 truncate">页面来源：{{ fb.page_url }}</div>

                <div v-if="feedbackDrafts[fb.id]" class="grid grid-cols-1 md:grid-cols-12 gap-2 pt-1">
                  <select
                    v-model="feedbackDrafts[fb.id].status"
                    class="md:col-span-2 h-9 px-2.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
                  >
                    <option value="pending">待受理</option>
                    <option value="in_progress">处理中</option>
                    <option value="replied">已回复</option>
                    <option value="resolved">已解决</option>
                  </select>
                  <input
                    v-model="feedbackDrafts[fb.id].admin_reply"
                    type="text"
                    placeholder="填写官方回复（用户将在「我的反馈记录」中实时看见）..."
                    class="md:col-span-7 h-9 px-3 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
                  />
                  <div class="md:col-span-3 flex items-center justify-end gap-1.5">
                    <button
                      type="button"
                      :disabled="busyAction"
                      @click="saveFeedbackReply(fb)"
                      class="h-9 px-3 rounded-lg bg-blue-600 text-white font-semibold hover:bg-blue-700"
                    >
                      保存回复
                    </button>
                    <button
                      type="button"
                      :disabled="busyAction"
                      @click="removeFeedbackItem(fb)"
                      class="h-9 px-2.5 rounded-lg border border-rose-200 dark:border-rose-800 text-rose-600 hover:bg-rose-50"
                      title="删除反馈"
                    >
                      <Trash2 class="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              </article>
            </div>
          </div>
        </section>

        <!-- Tab 3: Content Operations & Heavy Overrides -->
        <section v-if="activeTab === 'content'" class="space-y-4">
          <!-- Global Site Announcement Banner -->
          <form
            @submit.prevent="
              saveSiteSettingsPartial(
                {
                  site_banner_enabled: siteSettingsForm.site_banner_enabled,
                  site_banner_tone: siteSettingsForm.site_banner_tone,
                  site_banner_text: siteSettingsForm.site_banner_text,
                },
                '全站顶部通知横幅已更新！',
              )
            "
            class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 space-y-3 text-xs"
          >
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 class="text-sm sm:text-base font-bold text-slate-900 dark:text-white">全站顶部公告横幅管理</h2>
                <p class="text-slate-500">用于临时推送维护提醒、版本更新或重要市场闭市/调度通知。</p>
              </div>
              <label class="inline-flex items-center gap-2 font-semibold cursor-pointer">
                <input v-model="siteSettingsForm.site_banner_enabled" type="checkbox" class="rounded w-4 h-4 text-blue-600" />
                <span>在工作台顶部展示横幅</span>
              </label>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-12 gap-2.5">
              <select
                v-model="siteSettingsForm.site_banner_tone"
                class="md:col-span-3 h-9 px-2.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800"
              >
                <option value="info">蓝紫提示（Info）</option>
                <option value="warning">琥珀提醒（Warning）</option>
                <option value="important">绯红重磅（Important）</option>
              </select>
              <input
                v-model="siteSettingsForm.site_banner_text"
                type="text"
                maxlength="300"
                placeholder="输入横幅文案（如：突发公告：美伊停火临时声明窗口追踪已开启）..."
                class="md:col-span-7 h-9 px-3 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800"
              />
              <button
                type="submit"
                :disabled="busyAction"
                class="md:col-span-2 h-9 px-4 rounded-lg bg-blue-600 text-white font-semibold hover:bg-blue-700"
              >
                保存横幅
              </button>
            </div>
          </form>

          <!-- Editorial Overrides Table -->
          <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 space-y-3 text-xs">
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h3 class="text-sm font-bold text-slate-900 dark:text-white">重磅评级、置顶与屏蔽人工调度（跨批次持续生效）</h3>
                <p class="text-slate-500">支持将突发新闻提级为 S/A 级重磅、取消误判重磅（降为 B 级）、置顶或屏蔽隐藏。</p>
              </div>
              <div class="flex flex-wrap items-center gap-2">
                <div class="inline-flex rounded-lg border border-slate-200 dark:border-slate-700 p-0.5">
                  <button
                    type="button"
                    @click="contentScope = 'events'"
                    class="px-3 py-1 rounded-md font-semibold"
                    :class="contentScope === 'events' ? 'bg-slate-900 text-white dark:bg-blue-600' : 'text-slate-600 dark:text-slate-300'"
                  >
                    今日要闻 ({{ contentEvents.length }})
                  </button>
                  <button
                    type="button"
                    @click="contentScope = 'wire'"
                    class="px-3 py-1 rounded-md font-semibold"
                    :class="contentScope === 'wire' ? 'bg-slate-900 text-white dark:bg-blue-600' : 'text-slate-600 dark:text-slate-300'"
                  >
                    7×24 快讯 ({{ contentWire.length }})
                  </button>
                </div>
                <input
                  v-model="contentSearch"
                  type="search"
                  placeholder="搜索标题或分类..."
                  class="h-8 px-3 rounded-lg border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 w-48"
                />
              </div>
            </div>

            <!-- Events Table -->
            <div v-if="contentScope === 'events'" class="space-y-2">
              <div
                v-for="ev in filteredContentEvents.slice(0, 50)"
                :key="ev.event_id"
                class="rounded-xl border border-slate-200/80 dark:border-slate-800 p-3 space-y-2"
                :class="contentOverrides?.items?.[`event:${ev.event_id}`] ? 'bg-indigo-50/40 dark:bg-indigo-950/20 border-indigo-200 dark:border-indigo-800' : 'bg-slate-50/50 dark:bg-slate-800/30'"
              >
                <div class="flex flex-wrap items-start justify-between gap-2">
                  <div class="space-y-0.5 min-w-0 flex-1">
                    <div class="font-semibold text-slate-900 dark:text-white leading-snug">{{ ev.title }}</div>
                    <div class="text-[11px] text-slate-500">
                      分类: {{ ev.category }} · 算法默认: <strong>{{ ev.severity_tier }}</strong>
                      <span v-if="ev.heavy_reason_tag"> ({{ ev.heavy_reason_tag }})</span>
                      · {{ ev.source_count }} 源
                    </div>
                  </div>
                  <span
                    v-if="contentOverrides?.items?.[`event:${ev.event_id}`]"
                    class="px-2 py-0.5 rounded-full bg-indigo-600 text-white text-[10px] font-semibold shrink-0"
                  >
                    已人工干预
                  </span>
                </div>

                <div v-if="contentDrafts[`event:${ev.event_id}`]" class="flex flex-wrap items-center gap-2 pt-1">
                  <select
                    v-model="contentDrafts[`event:${ev.event_id}`].severity_override"
                    class="h-8 px-2 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
                  >
                    <option value="S">S级重磅</option>
                    <option value="A">A级要闻</option>
                    <option value="B">B级常规 (取消重磅)</option>
                  </select>
                  <select
                    v-model="contentDrafts[`event:${ev.event_id}`].heavy_reason_tag"
                    class="h-8 px-2 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
                  >
                    <option value="">自动后缀</option>
                    <option v-for="tag in HEAVY_TAG_OPTIONS" :key="tag" :value="tag">{{ tag }}</option>
                  </select>
                  <label class="inline-flex items-center gap-1 cursor-pointer px-2 py-1 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700">
                    <input v-model="contentDrafts[`event:${ev.event_id}`].pinned" type="checkbox" class="rounded" />
                    <Pin class="w-3 h-3 text-indigo-500" />
                    <span>置顶</span>
                  </label>
                  <label class="inline-flex items-center gap-1 cursor-pointer px-2 py-1 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700">
                    <input v-model="contentDrafts[`event:${ev.event_id}`].hidden" type="checkbox" class="rounded" />
                    <EyeOff class="w-3 h-3 text-rose-500" />
                    <span>屏蔽隐藏</span>
                  </label>
                  <button
                    type="button"
                    :disabled="busyAction"
                    @click="applyEventOverride(ev)"
                    class="h-8 px-3 rounded-lg bg-blue-600 text-white font-semibold hover:bg-blue-700"
                  >
                    保存干预
                  </button>
                  <button
                    v-if="contentOverrides?.items?.[`event:${ev.event_id}`]"
                    type="button"
                    :disabled="busyAction"
                    @click="restoreOverride(`event:${ev.event_id}`)"
                    class="inline-flex items-center gap-1 h-8 px-2.5 rounded-lg border border-slate-300 dark:border-slate-700 hover:bg-slate-100"
                  >
                    <RotateCcw class="w-3 h-3" />
                    <span>恢复默认</span>
                  </button>
                </div>
              </div>
            </div>

            <!-- Wire Table -->
            <div v-else class="space-y-2">
              <div
                v-for="w in filteredContentWire.slice(0, 60)"
                :key="w.id"
                class="rounded-xl border border-slate-200/80 dark:border-slate-800 p-3 space-y-2"
                :class="contentOverrides?.items?.[`wire:${w.title_fingerprint}`] ? 'bg-indigo-50/40 dark:bg-indigo-950/20 border-indigo-200 dark:border-indigo-800' : 'bg-slate-50/50 dark:bg-slate-800/30'"
              >
                <div class="flex flex-wrap items-start justify-between gap-2">
                  <div class="space-y-0.5 min-w-0 flex-1">
                    <div class="font-semibold text-slate-900 dark:text-white leading-snug">{{ w.title }}</div>
                    <div class="text-[11px] text-slate-500">
                      来源: {{ w.source_name }} · 算法默认: <strong>{{ w.severity_tier }}</strong>
                      <span v-if="w.heavy_reason_tag"> ({{ w.heavy_reason_tag }})</span>
                    </div>
                  </div>
                  <span
                    v-if="contentOverrides?.items?.[`wire:${w.title_fingerprint}`]"
                    class="px-2 py-0.5 rounded-full bg-indigo-600 text-white text-[10px] font-semibold shrink-0"
                  >
                    已人工干预
                  </span>
                </div>

                <div v-if="contentDrafts[`wire:${w.title_fingerprint}`]" class="flex flex-wrap items-center gap-2 pt-1">
                  <select
                    v-model="contentDrafts[`wire:${w.title_fingerprint}`].severity_override"
                    class="h-8 px-2 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
                  >
                    <option value="S">S级重磅</option>
                    <option value="A">A级要闻</option>
                    <option value="B">B级常规 (取消重磅)</option>
                  </select>
                  <select
                    v-model="contentDrafts[`wire:${w.title_fingerprint}`].heavy_reason_tag"
                    class="h-8 px-2 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
                  >
                    <option value="">自动后缀</option>
                    <option v-for="tag in HEAVY_TAG_OPTIONS" :key="tag" :value="tag">{{ tag }}</option>
                  </select>
                  <label class="inline-flex items-center gap-1 cursor-pointer px-2 py-1 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700">
                    <input v-model="contentDrafts[`wire:${w.title_fingerprint}`].pinned" type="checkbox" class="rounded" />
                    <Pin class="w-3 h-3 text-indigo-500" />
                    <span>置顶</span>
                  </label>
                  <label class="inline-flex items-center gap-1 cursor-pointer px-2 py-1 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700">
                    <input v-model="contentDrafts[`wire:${w.title_fingerprint}`].hidden" type="checkbox" class="rounded" />
                    <EyeOff class="w-3 h-3 text-rose-500" />
                    <span>屏蔽隐藏</span>
                  </label>
                  <button
                    type="button"
                    :disabled="busyAction"
                    @click="applyWireOverride(w)"
                    class="h-8 px-3 rounded-lg bg-blue-600 text-white font-semibold hover:bg-blue-700"
                  >
                    保存干预
                  </button>
                  <button
                    v-if="contentOverrides?.items?.[`wire:${w.title_fingerprint}`]"
                    type="button"
                    :disabled="busyAction"
                    @click="restoreOverride(`wire:${w.title_fingerprint}`)"
                    class="inline-flex items-center gap-1 h-8 px-2.5 rounded-lg border border-slate-300 dark:border-slate-700 hover:bg-slate-100"
                  >
                    <RotateCcw class="w-3 h-3" />
                    <span>恢复默认</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- Tab 4: Users, Invite Codes & Tiered Admin Management -->
        <section v-if="activeTab === 'users'" class="space-y-4">
          <!-- Current Site Access Mode Status Banner -->
          <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 flex flex-wrap items-center justify-between gap-3 text-xs">
            <div class="flex items-start gap-2.5">
              <Shield class="w-4 h-4 text-indigo-600 dark:text-indigo-400 mt-0.5 shrink-0" />
              <div class="space-y-1">
                <div class="flex flex-wrap items-center gap-2">
                  <span class="font-bold text-slate-900 dark:text-white">全站访问门禁状态</span>
                  <span
                    class="px-2 py-0.5 rounded-full text-[11px] font-semibold"
                    :class="accessModeMeta(currentAccessMode).badgeClass"
                  >
                    {{ accessModeMeta(currentAccessMode).shortLabel }}
                  </span>
                </div>
                <p class="text-slate-500 dark:text-slate-400">
                  {{ accessModeMeta(currentAccessMode).inviteHint }}
                </p>
              </div>
            </div>
            <button
              type="button"
              @click="activeTab = 'overview'"
              class="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 font-semibold hover:bg-slate-50 dark:hover:bg-slate-800 shrink-0"
            >
              <span>前往运营总览切换门禁模式</span>
              <ArrowRight class="w-3.5 h-3.5" />
            </button>
          </div>

          <!-- One-Time Invite Code Generator Card -->
          <div class="rounded-2xl border border-indigo-200/80 dark:border-indigo-900/70 bg-white dark:bg-slate-900 p-4 sm:p-5 space-y-3 text-xs">
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div class="flex items-center gap-2">
                <Ticket class="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
                <div>
                  <h2 class="text-sm sm:text-base font-bold text-slate-900 dark:text-white">一次性注册邀请码管理（Invite-Only / Private-Gate）</h2>
                  <p class="text-slate-500">每个邀请码仅限绑定 1 位新用户激活使用，可随时作废未使用的邀请码。</p>
                </div>
              </div>
              <span class="font-mono text-[11px] px-2.5 py-1 rounded-full bg-indigo-50 dark:bg-indigo-950/50 text-indigo-700 dark:text-indigo-300 font-semibold">
                可用 {{ inviteCodes.filter((c) => !c.revoked && c.used_by_user_id === null).length }} / 共 {{ inviteCodes.length }}
              </span>
            </div>

            <form @submit.prevent="handleGenerateInvites" class="grid grid-cols-1 sm:grid-cols-12 gap-2 items-end">
              <div class="sm:col-span-2">
                <label class="block text-slate-500 mb-1">生成数量</label>
                <input v-model.number="inviteCount" type="number" min="1" max="50" class="w-full h-9 px-3 rounded-xl border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-800" />
              </div>
              <div class="sm:col-span-2">
                <label class="block text-slate-500 mb-1">有效天数</label>
                <input v-model.number="inviteExpiryDays" type="number" min="1" max="365" class="w-full h-9 px-3 rounded-xl border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-800" />
              </div>
              <div class="sm:col-span-5">
                <label class="block text-slate-500 mb-1">备注用途（如：内测好友 / 同事）</label>
                <input v-model="inviteNote" type="text" maxlength="80" placeholder="选填用途备注..." class="w-full h-9 px-3 rounded-xl border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-800" />
              </div>
              <div class="sm:col-span-3">
                <button type="submit" :disabled="busyAction" class="w-full h-9 px-3 rounded-xl bg-indigo-600 text-white font-semibold hover:bg-indigo-700 disabled:opacity-60 inline-flex items-center justify-center gap-1.5">
                  <Plus class="w-3.5 h-3.5" />
                  <span>生成邀请码</span>
                </button>
              </div>
            </form>

            <div v-if="inviteCodes.length > 0" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2 pt-1 max-h-60 overflow-y-auto">
              <div
                v-for="inv in inviteCodes.slice(0, 30)"
                :key="inv.code"
                class="rounded-xl border px-3 py-2 flex items-center justify-between gap-2"
                :class="inv.revoked ? 'border-slate-200 dark:border-slate-800 opacity-50 bg-slate-50 dark:bg-slate-800/30' : inv.used_by_user_id !== null ? 'border-emerald-200 dark:border-emerald-900 bg-emerald-50/40 dark:bg-emerald-950/20' : 'border-indigo-200 dark:border-indigo-800 bg-indigo-50/30 dark:bg-indigo-950/20'"
              >
                <div class="min-w-0">
                  <div class="font-mono font-bold text-slate-900 dark:text-white truncate">{{ inv.code }}</div>
                  <div class="text-[10.5px] text-slate-500 truncate">
                    <template v-if="inv.revoked">已作废</template>
                    <template v-else-if="inv.used_by_user_id !== null">已使用 · @{{ inv.used_by_username }}</template>
                    <template v-else>未使用{{ inv.note ? ` · ${inv.note}` : '' }}</template>
                  </div>
                </div>
                <div class="flex items-center gap-1 shrink-0">
                  <button
                    v-if="!inv.revoked && inv.used_by_user_id === null"
                    type="button"
                    @click="copyInviteText(inv.code)"
                    class="p-1.5 rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-white dark:hover:bg-slate-800"
                    title="复制邀请码"
                  >
                    <Copy class="w-3 h-3" />
                  </button>
                  <button
                    v-if="!inv.revoked && inv.used_by_user_id === null"
                    type="button"
                    :disabled="busyAction"
                    @click="handleRevokeInvite(inv.code)"
                    class="p-1.5 rounded-lg border border-rose-200 dark:border-rose-900 text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/30"
                    title="作废"
                  >
                    <Trash2 class="w-3 h-3" />
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- Waitlist Applications Panel -->
          <div
            v-if="siteSettingsForm.invite_waitlist_enabled || waitlistItems.length > 0"
            class="rounded-2xl border border-amber-200/80 dark:border-amber-900/70 bg-white dark:bg-slate-900 p-4 sm:p-5 space-y-3 text-xs"
            data-testid="admin-waitlist-panel"
          >
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 class="text-sm sm:text-base font-bold text-slate-900 dark:text-white">
                  候补席位申请列表 ({{ waitlistItems.filter((w) => w.status === 'pending').length }} 待审批 / 共 {{ waitlistItems.length }})
                </h2>
                <p class="text-slate-500">阶段三/四无邀请码访客提交的候补席位申请，点击「通过并自动发码」一键生成并绑定一次性邀请码。</p>
              </div>
            </div>
            <div v-if="waitlistItems.length === 0" class="py-4 text-center text-slate-400">暂无候补席位申请记录</div>
            <div v-else class="space-y-2 max-h-72 overflow-y-auto">
              <div
                v-for="wl in waitlistItems"
                :key="wl.id"
                class="rounded-xl border border-slate-200 dark:border-slate-800 p-3 flex flex-wrap items-center justify-between gap-3"
              >
                <div class="min-w-0 space-y-1">
                  <div class="flex flex-wrap items-center gap-2">
                    <span class="font-mono font-bold text-slate-800 dark:text-white">#{{ wl.id }}</span>
                    <span class="font-semibold text-slate-900 dark:text-white">{{ wl.contact }}</span>
                    <span
                      class="px-2 py-0.5 rounded-full text-[10.5px] font-semibold"
                      :class="
                        wl.status === 'approved'
                          ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300'
                          : wl.status === 'rejected'
                            ? 'bg-slate-200 text-slate-600 dark:bg-slate-800 dark:text-slate-400'
                            : 'bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300'
                      "
                    >
                      {{ wl.status === 'approved' ? '已签发邀请码' : wl.status === 'rejected' ? '已拒绝' : '待审批' }}
                    </span>
                    <span v-if="wl.focus_areas" class="text-[11px] text-indigo-600 dark:text-indigo-400">{{ wl.focus_areas }}</span>
                  </div>
                  <p v-if="wl.note" class="text-[11px] text-slate-500">{{ wl.note }}</p>
                </div>
                <div class="flex items-center gap-2 shrink-0">
                  <template v-if="wl.status === 'approved' && wl.assigned_code">
                    <span class="font-mono font-bold px-2.5 py-1 rounded-lg bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800">
                      {{ wl.assigned_code }}
                    </span>
                    <button
                      type="button"
                      @click="copyInviteText(wl.assigned_code)"
                      class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800"
                    >
                      <Copy class="w-3 h-3" />
                      <span>复制</span>
                    </button>
                  </template>
                  <template v-else-if="wl.status === 'pending'">
                    <button
                      type="button"
                      :disabled="busyAction"
                      @click="handleApproveWaitlist(wl)"
                      class="px-3 py-1.5 rounded-lg bg-emerald-600 text-white font-semibold hover:bg-emerald-700"
                    >
                      通过并自动发码
                    </button>
                    <button
                      type="button"
                      :disabled="busyAction"
                      @click="handleRejectWaitlist(wl)"
                      class="px-2.5 py-1.5 rounded-lg border border-rose-200 dark:border-rose-800 text-rose-600 hover:bg-rose-50"
                    >
                      拒绝
                    </button>
                  </template>
                </div>
              </div>
            </div>
          </div>

          <!-- User Prediction Proposals Review Queue -->
          <div
            class="rounded-2xl border border-indigo-200/80 dark:border-indigo-900/70 bg-white dark:bg-slate-900 p-4 sm:p-5 space-y-3 text-xs"
            data-testid="admin-proposals-panel"
          >
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 class="text-sm sm:text-base font-bold text-slate-900 dark:text-white">
                  用户预测提案审核队列 ({{ predictionProposals.filter((p) => p.status === 'pending').length }} 待审 / 共 {{ predictionProposals.length }})
                </h2>
                <p class="text-slate-500">
                  采纳用户提交的可验证预测题后，题目立即进入全站竞技场并向提案者发放 +100 洞察分与 +1 邀请码额度。
                </p>
              </div>
            </div>
            <div v-if="predictionProposals.length === 0" class="py-4 text-center text-slate-400">
              暂无用户预测提案记录
            </div>
            <div v-else class="space-y-2 max-h-80 overflow-y-auto">
              <div
                v-for="prop in predictionProposals"
                :key="prop.id"
                class="rounded-xl border border-slate-200 dark:border-slate-800 p-3 space-y-2"
              >
                <div class="flex flex-wrap items-center justify-between gap-2">
                  <div class="flex flex-wrap items-center gap-2">
                    <span class="font-mono font-bold text-slate-800 dark:text-white">#{{ prop.id }}</span>
                    <span class="font-semibold text-indigo-600 dark:text-indigo-400">{{ prop.username }}</span>
                    <span class="px-2 py-0.5 rounded-full text-[10.5px] font-semibold bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
                      {{ prop.category }}
                    </span>
                    <span
                      class="px-2 py-0.5 rounded-full text-[10.5px] font-semibold"
                      :class="
                        prop.status === 'approved'
                          ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300'
                          : prop.status === 'rejected'
                            ? 'bg-slate-200 text-slate-600 dark:bg-slate-800 dark:text-slate-400'
                            : 'bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300'
                      "
                    >
                      {{ prop.status === 'approved' ? '已采纳上架' : prop.status === 'rejected' ? '已拒绝' : '待审核' }}
                    </span>
                  </div>
                  <span class="font-mono text-[11px] text-slate-400">截止 {{ prop.due_at }}</span>
                </div>
                <div class="font-bold text-slate-900 dark:text-white">{{ prop.title }}</div>
                <div class="text-slate-600 dark:text-slate-300">{{ prop.question }}</div>
                <div class="text-[11px] text-slate-500">
                  达成标准：{{ prop.win_rule || '按截止时刻公开数据核验' }} · 未达成标准：{{ prop.lose_rule || '未达到上述阈值' }}
                </div>
                <div v-if="prop.status === 'pending'" class="flex items-center gap-2 pt-1">
                  <button
                    type="button"
                    :disabled="busyAction"
                    @click="handleApproveProposal(prop)"
                    class="px-3 py-1.5 rounded-lg bg-emerald-600 text-white font-semibold hover:bg-emerald-700"
                  >
                    通过上架（+100分/+1邀）
                  </button>
                  <button
                    type="button"
                    :disabled="busyAction"
                    @click="handleRejectProposal(prop)"
                    class="px-2.5 py-1.5 rounded-lg border border-rose-200 dark:border-rose-800 text-rose-600 hover:bg-rose-50"
                  >
                    拒绝
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- Daily Market Predictions & Manual Settlement Console -->
          <div
            class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 sm:p-5 space-y-3 text-xs"
            data-testid="admin-daily-predictions-panel"
          >
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 class="text-sm sm:text-base font-bold text-slate-900 dark:text-white">
                  每日自动行情日赛与手动结算台 ({{ dailyPredictions.filter((d) => d.status !== 'settled').length }} 进行中 / 共 {{ dailyPredictions.length }})
                </h2>
                <p class="text-slate-500">
                  支持一键触发当日自动行情出题与客观结算，也可在极端行情或用户共创题到期时执行人工兜底裁定。
                </p>
              </div>
              <button
                type="button"
                :disabled="busyAction"
                @click="handleTriggerDailyCron"
                class="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-indigo-600 text-white font-semibold hover:bg-indigo-700 disabled:opacity-50"
              >
                <RefreshCw class="w-3.5 h-3.5" />
                <span>立即运行自动出题与结算</span>
              </button>
            </div>
            <div v-if="dailyPredictions.length === 0" class="py-4 text-center text-slate-400">
              暂无日赛或共创预测题目，可点击右上角按钮立即生成今日行情预测题
            </div>
            <div v-else class="space-y-2 max-h-96 overflow-y-auto">
              <div
                v-for="dp in dailyPredictions"
                :key="dp.id"
                class="rounded-xl border border-slate-200 dark:border-slate-800 p-3 space-y-2"
              >
                <div class="flex flex-wrap items-center justify-between gap-2">
                  <div class="flex flex-wrap items-center gap-2">
                    <span class="font-mono text-[11px] font-bold text-slate-700 dark:text-slate-200">{{ dp.id }}</span>
                    <span
                      class="px-2 py-0.5 rounded-full text-[10.5px] font-semibold"
                      :class="
                        dp.status === 'settled'
                          ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300'
                          : dp.status === 'locked'
                            ? 'bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300'
                            : 'bg-blue-100 text-blue-700 dark:bg-blue-950/60 dark:text-blue-300'
                      "
                    >
                      {{ dp.status === 'settled' ? `已结算 (${String(dp.outcome || '').toUpperCase()})` : dp.status === 'locked' ? '已封盘待结算' : '开放投票中' }}
                    </span>
                    <span v-if="dp.ticker" class="font-mono text-[11px] text-indigo-600 dark:text-indigo-400">
                      {{ dp.ticker }} (基准 {{ dp.base_price ?? '-' }})
                    </span>
                    <span v-if="dp.proposer_username" class="text-[11px] text-slate-500">
                      提案人：{{ dp.proposer_username }}
                    </span>
                  </div>
                  <span class="font-mono text-[11px] text-slate-400">截止 {{ dp.due_at }}</span>
                </div>
                <div class="font-bold text-slate-900 dark:text-white">{{ dp.title }}</div>
                <div class="text-slate-600 dark:text-slate-300">{{ dp.question }}</div>
                <div v-if="dp.status !== 'settled'" class="flex flex-wrap items-center gap-2 pt-1">
                  <input
                    v-model="settleValueDrafts[dp.id]"
                    type="text"
                    placeholder="可选：结算观测值"
                    class="w-36 h-8 px-2.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 font-mono text-[11px]"
                  />
                  <button
                    type="button"
                    :disabled="busyAction"
                    @click="handleSettleDaily(dp, 'yes')"
                    class="px-3 py-1.5 rounded-lg bg-emerald-600 text-white font-semibold hover:bg-emerald-700"
                  >
                    判为达成 (YES)
                  </button>
                  <button
                    type="button"
                    :disabled="busyAction"
                    @click="handleSettleDaily(dp, 'no')"
                    class="px-3 py-1.5 rounded-lg bg-rose-600 text-white font-semibold hover:bg-rose-700"
                  >
                    判为未达成 (NO)
                  </button>
                  <button
                    type="button"
                    :disabled="busyAction"
                    @click="handleSettleDaily(dp, 'void')"
                    class="px-2.5 py-1.5 rounded-lg border border-slate-300 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800"
                  >
                    作废 (VOID)
                  </button>
                </div>
                <div v-else class="text-[11px] text-emerald-700 dark:text-emerald-300 font-medium">
                  已于 {{ dp.settled_at }} 结算为 {{ String(dp.outcome || '').toUpperCase() }}
                  <span v-if="dp.settled_value !== null && dp.settled_value !== undefined">（观测值：{{ dp.settled_value }}）</span>
                </div>
              </div>
            </div>
          </div>

          <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 sm:p-5 space-y-3">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 class="text-sm sm:text-base font-bold text-slate-900 dark:text-white">用户绑定信息、密码与管理员分级管理</h2>
              <p class="text-xs text-slate-500">
                所有用户密码默认打码脱敏展示；超级管理员需通过密码二次核验后方可查看单条账号密码，运营管理员仅可查看绑定手机/邮箱与云同步数据。
              </p>
            </div>
            <div class="flex items-center gap-2 w-full sm:w-auto">
              <input
                v-model="userSearch"
                type="search"
                placeholder="搜索用户名 / 手机 / 邮箱 / IP..."
                class="h-9 px-3 rounded-xl border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-xs flex-1 sm:w-64"
              />
              <button
                v-if="isSuperAdmin"
                type="button"
                @click="createModalOpen = true"
                class="h-9 px-3 rounded-xl bg-rose-600 text-white text-xs font-semibold hover:bg-rose-700 shrink-0"
              >
                + 新增管理员
              </button>
            </div>
          </div>

          <div class="overflow-x-auto">
            <table class="w-full text-left text-xs border-collapse">
              <thead>
                <tr class="border-b border-slate-200 dark:border-slate-800 text-slate-500">
                  <th class="py-2 pr-3">ID / 账号</th>
                  <th class="py-2 pr-3">权限级别 / 状态</th>
                  <th class="py-2 pr-3">绑定手机 & 邮箱</th>
                  <th class="py-2 pr-3">登录密码（默认脱敏 · 需二次核验）</th>
                  <th class="py-2 pr-3">云同步数据摘要</th>
                  <th class="py-2 text-right">管理操作</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-100 dark:divide-slate-800">
                <tr v-for="u in filteredUsers" :key="u.id" class="hover:bg-slate-50/70 dark:hover:bg-slate-800/40">
                  <td class="py-2.5 pr-3">
                    <div class="flex items-center gap-2.5">
                      <UserAvatar :avatar="u.avatar" :username="u.username" :role="u.role" size="sm" />
                      <div>
                        <div class="font-bold text-slate-900 dark:text-white">#{{ u.id }} {{ u.username }}</div>
                        <div class="text-[11px] text-slate-500">{{ u.display_name }} · 登录 {{ u.login_count }} 次</div>
                      </div>
                    </div>
                  </td>
                  <td class="py-2.5 pr-3 whitespace-nowrap">
                    <span class="px-1.5 py-0.5 rounded text-[10px] font-semibold mr-1" :class="roleBadgeClass(u.role)">
                      {{ roleLabel(u.role) }}
                    </span>
                    <span
                      class="px-1.5 py-0.5 rounded text-[10px] font-semibold"
                      :class="u.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-200 text-slate-600'"
                    >
                      {{ u.is_active ? '正常' : '已停用' }}
                    </span>
                  </td>
                  <td class="py-2.5 pr-3 font-mono text-[11px] space-y-0.5">
                    <div class="inline-flex items-center gap-1"><Smartphone class="w-3 h-3 text-slate-400 shrink-0" /><span>{{ u.phone || '未绑定手机' }}</span></div>
                    <div class="inline-flex items-center gap-1 text-slate-500"><Mail class="w-3 h-3 text-slate-400 shrink-0" /><span>{{ u.email || '未绑定邮箱' }}</span></div>
                  </td>
                  <td class="py-2.5 pr-3 font-mono text-xs">
                    <template v-if="isSuperAdmin">
                      <div v-if="revealedPasswords[u.id]" class="inline-flex items-center gap-1.5">
                        <span class="px-2 py-0.5 rounded bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 border border-rose-200 dark:border-rose-800">
                          {{ revealedPasswords[u.id] }}
                        </span>
                        <button
                          type="button"
                          @click="hideRevealedPassword(u.id)"
                          class="p-1 rounded border border-slate-200 dark:border-slate-700 text-slate-500 hover:text-slate-800"
                          title="重新隐藏"
                        >
                          <EyeOff class="w-3 h-3" />
                        </button>
                      </div>
                      <div v-else class="inline-flex items-center gap-1.5">
                        <span class="px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-500">••••••••</span>
                        <button
                          v-if="u.has_saved_password !== false"
                          type="button"
                          @click="openRevealModal(u)"
                          class="inline-flex items-center gap-1 px-2 py-0.5 rounded border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-100"
                        >
                          <Eye class="w-3 h-3" />
                          <span>查看</span>
                        </button>
                      </div>
                    </template>
                    <span v-else class="text-slate-400 italic">••••••••</span>
                  </td>
                  <td class="py-2.5 pr-3 tabular-nums">
                    <div v-if="u.state_updated_at">
                      关注 {{ u.watchlist_count ?? 0 }} · 收藏 {{ u.bookmarks_count ?? 0 }} · 深读 {{ u.read_later_count ?? 0 }} · 笔记 {{ u.notes_count ?? 0 }}
                    </div>
                    <div v-else class="text-slate-400">暂无云端快照</div>
                  </td>
                  <td class="py-2.5 text-right space-x-1.5 whitespace-nowrap">
                    <button
                      type="button"
                      @click="inspectUser(u)"
                      class="inline-flex items-center gap-1 px-2 py-1 rounded-lg border border-blue-200 dark:border-blue-800 text-blue-700 dark:text-blue-300 hover:bg-blue-50"
                    >
                      <Eye class="w-3 h-3" />
                      <span>查看数据</span>
                    </button>

                    <!-- Role Switcher & Password Reset: strictly Super Admin only! -->
                    <template v-if="isSuperAdmin">
                      <select
                        v-if="u.id !== session?.user.id"
                        :value="u.role"
                        @change="handleChangeUserRole(u, ($event.target as HTMLSelectElement).value as UserRole)"
                        class="h-7 px-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-[11px]"
                        title="增减/调整管理员权限级别"
                      >
                        <option value="user">普通用户</option>
                        <option value="admin">运营管理员</option>
                        <option value="super_admin">超级管理员</option>
                      </select>

                      <button
                        type="button"
                        @click="resetTarget = u; resetNewPassword = ''"
                        class="inline-flex items-center gap-1 px-2 py-1 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-100"
                      >
                        <KeyRound class="w-3 h-3" />
                        <span>改密</span>
                      </button>
                    </template>

                    <button
                      v-if="u.id !== session?.user.id && (isSuperAdmin || u.role === 'user')"
                      type="button"
                      @click="toggleUserActive(u)"
                      class="px-2 py-1 rounded-lg border text-xs font-medium"
                      :class="u.is_active ? 'border-red-200 text-red-600 hover:bg-red-50' : 'border-emerald-200 text-emerald-700 hover:bg-emerald-50'"
                    >
                      {{ u.is_active ? '停用' : '启用' }}
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          </div>
        </section>

        <!-- Tab 5: Push Channels & OTP Gateway Configuration -->
        <section v-if="activeTab === 'push'" class="space-y-4">
          <form
            @submit.prevent="savePushSettings"
            class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 space-y-4 text-xs sm:text-sm"
          >
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 class="font-bold text-slate-900 dark:text-white">定时简报推送 & 手机/邮箱验证码网关配置</h2>
                <p class="text-xs text-slate-500">配置邮箱 SMTP 或短信 Webhook 后，用户注册绑定与找回密码验证码也会通过该通道自动下发。</p>
              </div>
              <label class="inline-flex items-center gap-2 font-semibold cursor-pointer">
                <input v-model="pushConfig.enabled" type="checkbox" class="rounded text-blue-600 w-4 h-4" />
                <span>启用定时简报推送</span>
              </label>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
              <div>
                <label class="block text-slate-500 mb-1">站点头链 URL</label>
                <input v-model="pushConfig.site_url" type="url" class="w-full h-9 px-3 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800" />
              </div>
              <div>
                <label class="block text-slate-500 mb-1">手机短信验证码 Webhook URL（可选）</label>
                <input v-model="pushConfig.sms_webhook_url" type="text" placeholder="自定义短信网关接口 URL" class="w-full h-9 px-3 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800" />
              </div>
              <div>
                <label class="block text-slate-500 mb-1">飞书群机器人 Webhook URL</label>
                <input v-model="pushConfig.feishu_webhook" type="text" placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..." class="w-full h-9 px-3 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800" />
              </div>
              <div>
                <label class="block text-slate-500 mb-1">企业微信机器人 Webhook URL</label>
                <input v-model="pushConfig.wecom_webhook" type="text" placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..." class="w-full h-9 px-3 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800" />
              </div>
              <div>
                <label class="block text-slate-500 mb-1">钉钉机器人 Webhook URL</label>
                <input v-model="pushConfig.dingtalk_webhook" type="text" placeholder="https://oapi.dingtalk.com/robot/send?access_token=..." class="w-full h-9 px-3 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800" />
              </div>
              <div>
                <label class="block text-slate-500 mb-1">Server酱（微信个人推送）SendKey</label>
                <input v-model="pushConfig.serverchan_sendkey" type="password" placeholder="SCT..." class="w-full h-9 px-3 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800" />
              </div>
              <div class="grid grid-cols-2 gap-2">
                <div>
                  <label class="block text-slate-500 mb-1">邮箱 SMTP 服务器（兼发邮箱验证码）</label>
                  <input v-model="pushConfig.smtp_host" type="text" placeholder="smtp.qq.com" class="w-full h-9 px-3 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800" />
                </div>
                <div>
                  <label class="block text-slate-500 mb-1">SSL 端口</label>
                  <input v-model.number="pushConfig.smtp_port" type="number" class="w-full h-9 px-3 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800" />
                </div>
              </div>
              <div>
                <label class="block text-slate-500 mb-1">发件邮箱账号 & 授权码</label>
                <div class="grid grid-cols-2 gap-2">
                  <input v-model="pushConfig.smtp_user" type="text" placeholder="sender@qq.com" class="h-9 px-3 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800" />
                  <input v-model="pushConfig.smtp_pass" type="password" placeholder="SMTP 授权码" class="h-9 px-3 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800" />
                </div>
              </div>
              <div>
                <label class="block text-slate-500 mb-1">简报收件人邮箱（多个用逗号分隔）</label>
                <input v-model="pushConfig.smtp_to" type="text" placeholder="you@qq.com" class="w-full h-9 px-3 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800" />
              </div>
            </div>

            <div class="flex flex-wrap gap-2 pt-2">
              <button
                type="submit"
                :disabled="busyAction"
                class="px-4 py-2 rounded-xl bg-blue-600 text-white text-xs font-semibold hover:bg-blue-700"
              >
                保存配置
              </button>
              <button
                type="button"
                :disabled="busyAction"
                @click="runPushTest"
                class="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl border border-emerald-300 dark:border-emerald-700 text-emerald-700 dark:text-emerald-300 text-xs font-semibold hover:bg-emerald-50"
              >
                <Send class="w-3.5 h-3.5" />
                <span>立即发送测试简报</span>
              </button>
            </div>
          </form>

          <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 space-y-2 text-xs">
            <h3 class="font-bold text-slate-900 dark:text-white">近期推送记录</h3>
            <p v-if="!pushLogs.length" class="text-slate-400">暂无推送记录</p>
            <ul v-else class="space-y-1.5">
              <li
                v-for="(lg, idx) in pushLogs"
                :key="idx"
                class="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-slate-50 dark:bg-slate-800/50 px-3 py-2"
              >
                <span>
                  <strong class="uppercase">{{ lg.channel }}</strong> · {{ lg.summary }}
                  <span v-if="lg.error_msg" class="text-red-500 ml-1">({{ lg.error_msg }})</span>
                </span>
                <span class="font-mono text-slate-500">{{ String(lg.created_at || '').slice(0, 19).replace('T', ' ') }} · {{ lg.status }}</span>
              </li>
            </ul>
          </div>
        </section>

        <!-- Tab 6: Audit Logs -->
        <section v-if="activeTab === 'audit'" class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 space-y-2 text-xs">
          <h2 class="font-bold text-slate-900 dark:text-white text-sm">安全审计与同步日志（最近 100 条）</h2>
          <div class="overflow-x-auto">
            <table class="w-full text-left border-collapse">
              <thead>
                <tr class="border-b border-slate-200 dark:border-slate-800 text-slate-500">
                  <th class="py-2 pr-3">时间</th>
                  <th class="py-2 pr-3">用户</th>
                  <th class="py-2 pr-3">动作</th>
                  <th class="py-2 pr-3">详情</th>
                  <th class="py-2">来源 IP</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-100 dark:divide-slate-800">
                <tr v-for="(lg, idx) in auditLogs" :key="idx">
                  <td class="py-2 pr-3 font-mono text-slate-500 whitespace-nowrap">{{ String(lg.created_at || '').slice(0, 19).replace('T', ' ') }}</td>
                  <td class="py-2 pr-3 font-semibold">{{ lg.username || '-' }}</td>
                  <td class="py-2 pr-3 font-mono text-blue-600 dark:text-blue-400">{{ formatAuditAction(lg.action) }}</td>
                  <td class="py-2 pr-3 text-slate-600 dark:text-slate-300">{{ formatAuditDetail(lg.detail) }}</td>
                  <td class="py-2 font-mono text-slate-500">{{ lg.ip }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </template>

      <!-- Reveal Plaintext Password Secondary Verification Modal -->
      <div
        v-if="revealTarget && isSuperAdmin"
        class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/60 backdrop-blur-xs"
        @click.self="revealTarget = null"
      >
        <form
          role="dialog"
          aria-modal="true"
          @submit.prevent="submitRevealPassword"
          class="w-full max-w-sm rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-5 space-y-3 shadow-2xl text-sm"
        >
          <h3 class="font-bold text-slate-900 dark:text-white flex items-center gap-1.5">
            <Lock class="w-4 h-4 text-rose-500" />
            <span>二次身份核验：查看 @{{ revealTarget.username }} 密码</span>
          </h3>
          <p class="text-xs text-slate-500">敏感审计操作，请输入您的超级管理员当前登录密码进行确认。</p>
          <input
            v-model="revealAdminPassword"
            type="password"
            required
            placeholder="输入超级管理员登录密码"
            class="w-full h-10 px-3 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm"
          />
          <p v-if="revealError" class="text-xs text-rose-600 font-medium">{{ revealError }}</p>
          <div class="flex justify-end gap-2 text-xs">
            <button type="button" @click="revealTarget = null" class="px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700">取消</button>
            <button type="submit" :disabled="busyAction" class="px-3.5 py-2 rounded-lg bg-rose-600 text-white font-semibold">
              {{ busyAction ? '核验中...' : '验证并查看' }}
            </button>
          </div>
        </form>
      </div>

      <!-- Create Admin / User Modal (Super Admin Only) -->
      <div
        v-if="createModalOpen"
        class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/60 backdrop-blur-xs"
        @click.self="requestCloseCreateModal('backdrop')"
      >
        <form
          ref="createModalRef"
          role="dialog"
          aria-modal="true"
          aria-labelledby="admin-create-modal-title"
          tabindex="-1"
          @submit.prevent="submitCreateAccount"
          class="relative w-full max-w-md rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-5 space-y-3 shadow-2xl text-xs sm:text-sm outline-none"
        >
          <div class="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-2.5">
            <h3 id="admin-create-modal-title" class="font-bold text-slate-900 dark:text-white">新增管理员或用户账号</h3>
            <button type="button" @click="requestCloseCreateModal('button')" class="text-slate-400" aria-label="关闭"><X class="w-4 h-4" /></button>
          </div>
          <div class="space-y-2.5">
            <div>
              <label class="block text-xs text-slate-500 mb-1">权限级别</label>
              <select v-model="createForm.role" class="w-full h-9 px-3 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs">
                <option value="admin">运营管理员（仅看绑定信息与数据，不可看/改用户密码）</option>
                <option value="super_admin">超级管理员（拥有所有权限，可二次核验查看密码）</option>
                <option value="user">普通用户</option>
              </select>
            </div>
            <div>
              <label class="block text-xs text-slate-500 mb-1">登录用户名</label>
              <input v-model="createForm.username" type="text" required placeholder="3–32 位字母/数字/下划线" class="w-full h-9 px-3 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs" />
            </div>
            <div>
              <label class="block text-xs text-slate-500 mb-1">初始密码（至少 6 位）</label>
              <input v-model="createForm.password" type="text" required placeholder="输入初始密码" class="w-full h-9 px-3 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs font-mono" />
            </div>
            <div class="grid grid-cols-2 gap-2">
              <div>
                <label class="block text-xs text-slate-500 mb-1">绑定手机号（可选）</label>
                <input v-model="createForm.phone" type="text" placeholder="138..." class="w-full h-9 px-3 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs" />
              </div>
              <div>
                <label class="block text-xs text-slate-500 mb-1">绑定邮箱（可选）</label>
                <input v-model="createForm.email" type="email" placeholder="user@..." class="w-full h-9 px-3 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs" />
              </div>
            </div>
          </div>
          <div class="flex justify-end gap-2 pt-2 text-xs">
            <button type="button" @click="requestCloseCreateModal('button')" class="px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700">取消</button>
            <button type="submit" :disabled="busyAction" class="px-4 py-2 rounded-lg bg-rose-600 text-white font-semibold">确认创建</button>
          </div>
          <DialogDirtyGuard
            :open="createDirtyOpen"
            @confirm="confirmCreateDiscard"
            @cancel="cancelCreateDiscard"
          />
        </form>
      </div>

      <!-- Admin-Only Decrypted User Data Modal -->
      <div
        v-if="inspectedUser"
        class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/60 backdrop-blur-xs"
        @click.self="requestCloseInspected('backdrop')"
      >
        <div
          ref="inspectedModalRef"
          role="dialog"
          aria-modal="true"
          aria-labelledby="admin-inspect-modal-title"
          tabindex="-1"
          class="w-full max-w-2xl max-h-[85vh] overflow-y-auto rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-5 space-y-3 shadow-2xl text-xs outline-none"
        >
          <div class="flex items-center justify-between gap-2 border-b border-slate-200 dark:border-slate-800 pb-3">
            <div id="admin-inspect-modal-title" class="flex items-center gap-2 font-bold text-sm text-slate-900 dark:text-white">
              <Lock class="w-4 h-4 text-emerald-600" />
              <span>用户云端研究数据：@{{ (inspectedUser.user as any).username }}</span>
            </div>
            <button type="button" @click="requestCloseInspected('button')" class="p-1 text-slate-500 hover:text-slate-900" aria-label="关闭"><X class="w-4 h-4" /></button>
          </div>
          <p v-if="!inspectedUser.has_state" class="text-slate-500 py-4 text-center">该用户尚未向云端同步任何研究数据。</p>
          <pre v-else class="rounded-xl bg-slate-950 text-emerald-300 p-3.5 overflow-x-auto text-[11px] leading-relaxed font-mono">{{ JSON.stringify(inspectedUser.state, null, 2) }}</pre>
        </div>
      </div>

      <!-- Super Admin Reset Password Modal -->
      <div
        v-if="resetTarget && isSuperAdmin"
        class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/60 backdrop-blur-xs"
        @click.self="requestCloseResetModal('backdrop')"
      >
        <div
          ref="resetModalRef"
          role="dialog"
          aria-modal="true"
          aria-labelledby="admin-reset-modal-title"
          tabindex="-1"
          class="relative w-full max-w-sm rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-5 space-y-3 shadow-2xl text-sm outline-none"
        >
          <h3 id="admin-reset-modal-title" class="font-bold text-slate-900 dark:text-white">重置用户密码：@{{ resetTarget.username }}</h3>
          <input
            v-model="resetNewPassword"
            type="text"
            placeholder="输入新密码（至少 6 位）"
            class="w-full h-10 px-3 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm font-mono"
          />
          <div class="flex justify-end gap-2 text-xs">
            <button type="button" @click="requestCloseResetModal('button')" class="px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700">取消</button>
            <button type="button" :disabled="busyAction" @click="submitResetPassword" class="px-3.5 py-2 rounded-lg bg-blue-600 text-white font-semibold">确认重置</button>
          </div>
          <DialogDirtyGuard
            :open="resetDirtyOpen"
            @confirm="confirmResetDiscard"
            @cancel="cancelResetDiscard"
          />
        </div>
      </div>

      <!-- Private Gate Secondary Confirmation Modal -->
      <div
        v-if="privateGateConfirmOpen && isSuperAdmin"
        class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/60 backdrop-blur-xs"
        @click.self="privateGateConfirmOpen = false"
      >
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="admin-private-gate-confirm-title"
          class="w-full max-w-md rounded-2xl bg-white dark:bg-slate-900 border border-rose-200 dark:border-rose-900 p-5 space-y-3 shadow-2xl text-sm"
        >
          <div class="flex items-center gap-2 text-rose-600 dark:text-rose-400 font-bold">
            <AlertTriangle class="w-5 h-5 shrink-0" />
            <h3 id="admin-private-gate-confirm-title">确认切换为「全站私有门禁」模式？</h3>
          </div>
          <p class="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
            保存后将<strong>立即全站生效（无需重新部署）</strong>：所有未登录访客将无法查看资讯主页、情报监控与 API 接口数据，必须使用已有账号登录或凭一次性邀请码注册后方可访问。
          </p>
          <div class="flex justify-end gap-2 pt-1 text-xs">
            <button
              type="button"
              @click="privateGateConfirmOpen = false; growthDraft.access_mode = currentAccessMode"
              class="px-3.5 py-2 rounded-lg border border-slate-200 dark:border-slate-700 font-medium"
            >
              取消
            </button>
            <button
              type="button"
              :disabled="busyAction"
              @click="executeSaveGrowthConsole"
              class="px-4 py-2 rounded-lg bg-rose-600 text-white font-semibold hover:bg-rose-700 disabled:opacity-60"
            >
              {{ busyAction ? '切换中...' : '确认切换为全站私有门禁' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </AppShell>
</template>
