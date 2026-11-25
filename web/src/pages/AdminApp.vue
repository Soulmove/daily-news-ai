<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Bell,
  CheckCircle2,
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
  Send,
  Shield,
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
import {
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
  apiAdminListWaitlist,
  apiAdminOverview,
  apiAdminPatchUser,
  apiAdminPushLogs,
  apiAdminPushTest,
  apiAdminRejectWaitlist,
  apiAdminRevealUserPassword,
  apiAdminRevokeInviteCode,
  apiAdminSaveEditorialOverride,
  apiAdminSavePushConfig,
  apiAdminSaveSiteSettings,
  apiAdminSyncNow,
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
  type AdminUserRow,
  type AuthSession,
  type FeedbackRecordItem,
  type GrowthStage,
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
const activeTab = ref<'overview' | 'feedback' | 'content' | 'users' | 'push' | 'audit'>('overview')

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
})

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
})
const privateGateConfirmOpen = ref(false)
const waitlistItems = ref<WaitlistEntryRow[]>([])

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
      crowd_vote_min_unlock: 3,
      user_referral_enabled: false,
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

async function loadAllAdminData() {
  if (!session.value || !isAdmin.value) return
  loading.value = true
  authError.value = ''
  try {
    const token = session.value.token
    const [ov, ul, pc, pl, al, ss, fb, ct, invRes, wlRes] = await Promise.all([
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
    ])
    inviteCodes.value = invRes.items || []
    waitlistItems.value = wlRes.items || []
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
    }
    growthDraft.value = buildGrowthDraftFromSettings(siteSettingsForm.value)
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
    showToast(successMsg)
  } catch (err) {
    showToast(err instanceof Error ? err.message : '设置保存失败')
  } finally {
    busyAction.value = false
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
              <h1 class="text-base sm:text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
                <span>私有云管理控制台</span>
                <span
                  class="px-2 py-0.5 rounded-full text-[11px] font-semibold"
                  :class="isSuperAdmin ? 'bg-rose-100 text-rose-700 dark:bg-rose-950/60 dark:text-rose-300' : 'bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300'"
                >
                  {{ isSuperAdmin ? '超级管理员（全权限）' : '运营管理员（受限权限）' }}
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
