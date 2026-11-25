<script setup lang="ts">
import { computed, ref, toRef, watch } from 'vue'
import { Calendar, Cloud, KeyRound, LogOut, Mail, Phone, Shield, Sun, User, X } from 'lucide-vue-next'
import DialogDirtyGuard from './DialogDirtyGuard.vue'
import UserAvatar from './UserAvatar.vue'
import {
  ApiValidationError,
  apiBindContact,
  apiChangePassword,
  apiLogin,
  apiRegister,
  apiResetPassword,
  apiSendCode,
  apiUpdatePreferences,
  isAdminRole,
  type AuthSession,
  type SiteAccessMode,
} from '../core/auth'
import { useDialogBehavior } from '../core/dialog'
import { t } from '../core/i18n'
import type { MorningBriefSummary } from '../core/v3Logic'

const props = withDefaults(
  defineProps<{
    isOpen: boolean
    session: AuthSession | null
    userAvatar?: string | null
    lastSyncedAt: string | null
    syncBusy: boolean
    morningBrief?: MorningBriefSummary | null
    initialSection?: 'profile' | 'security' | null
    accessMode?: SiteAccessMode
    allowClose?: boolean
  }>(),
  {
    accessMode: 'invite_only',
    allowClose: true,
  },
)

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'authenticated', session: AuthSession): void
  (e: 'logout'): void
  (e: 'sync-now'): void
  (e: 'open-avatar-picker'): void
}>()

const dialogEl = ref<HTMLElement | null>(null)
const mode = ref<'login' | 'register' | 'forgot'>('login')
const username = ref('')
const password = ref('')
const displayName = ref('')
const regContact = ref('')
const inviteCode = ref('')

const forgotTarget = ref('')
const forgotCode = ref('')
const forgotNewPassword = ref('')

const bindTarget = ref('')
const bindCode = ref('')
const showBindForm = ref(false)

const currentPassword = ref('')
const newPassword = ref('')
const showPwForm = ref(false)

const busy = ref(false)
const sendingCode = ref(false)
const errorMsg = ref('')
const okMsg = ref('')
const fieldErrors = ref<{ username?: string; password?: string; contact?: string; invite_code?: string }>({})

const requiresInviteCode = computed(() => props.accessMode === 'invite_only' || props.accessMode === 'private_gate')

const hasDirtyForm = computed(() => {
  if (props.session) {
    return Boolean(
      (showBindForm.value && (bindTarget.value.trim() || bindCode.value.trim())) ||
      (showPwForm.value && (currentPassword.value || newPassword.value)),
    )
  }
  if (mode.value === 'forgot') {
    return Boolean(forgotTarget.value.trim() || forgotCode.value.trim() || forgotNewPassword.value)
  }
  return Boolean(username.value.trim() || password.value || displayName.value.trim() || regContact.value.trim())
})

const { dirtyConfirmOpen, onBackdropClick, onCloseButton, confirmDirtyDiscard, cancelDirtyClose } =
  useDialogBehavior({
    isOpen: toRef(props, 'isOpen'),
    containerRef: dialogEl,
    onClose: () => {
      if (props.allowClose !== false) emit('close')
    },
    isDirty: () => hasDirtyForm.value,
  })

const USERNAME_RE = /^[A-Za-z0-9_\u4e00-\u9fa5]{4,20}$/

function isValidRegisterPassword(pw: string): boolean {
  return pw.length >= 8 && pw.length <= 64 && /[A-Za-z]/.test(pw) && /\d/.test(pw)
}

function clearFieldErrors() {
  fieldErrors.value = {}
}

watch(
  () => props.isOpen,
  (open) => {
    if (open) {
      errorMsg.value = ''
      okMsg.value = ''
      clearFieldErrors()
      password.value = ''
      regContact.value = ''
      inviteCode.value = ''
      forgotCode.value = ''
      forgotNewPassword.value = ''
      bindCode.value = ''
      currentPassword.value = ''
      newPassword.value = ''
      showPwForm.value = props.initialSection === 'security'
      showBindForm.value = props.initialSection === 'security' && Boolean(props.session && !props.session.user.email && !props.session.user.phone)
    }
  },
)

function roleLabel(role?: string): string {
  if (role === 'super_admin') return t('超级管理员', 'Super Admin')
  if (role === 'admin') return t('管理员', 'Admin')
  return t('标准用户', 'Member')
}

async function handleSendOtp(targetRaw: string, purpose: 'register' | 'bind' | 'reset_password') {
  errorMsg.value = ''
  okMsg.value = ''
  const target = targetRaw.trim()
  if (!target) {
    errorMsg.value = t('请先输入手机号或邮箱地址', 'Please enter a phone number or email address first')
    return
  }
  sendingCode.value = true
  try {
    const res = await apiSendCode(target, purpose)
    okMsg.value = res.message
    if (res.dev_code) {
      if (purpose === 'bind') bindCode.value = res.dev_code
      if (purpose === 'reset_password') forgotCode.value = res.dev_code
    }
  } catch (err) {
    errorMsg.value = err instanceof Error ? err.message : t('发送验证码失败', 'Failed to send code')
  } finally {
    sendingCode.value = false
  }
}

async function submitAuth() {
  if (busy.value) return
  errorMsg.value = ''
  okMsg.value = ''
  clearFieldErrors()

  if (mode.value === 'forgot') {
    if (!forgotTarget.value.trim() || !forgotCode.value.trim() || !isValidRegisterPassword(forgotNewPassword.value)) {
      errorMsg.value = t(
        '请填写手机号/邮箱、6位验证码及 8~64 位包含字母和数字的新密码',
        'Enter contact, 6-digit code, and 8–64 char password with letters & digits',
      )
      return
    }
    busy.value = true
    try {
      const res = await apiResetPassword(forgotTarget.value.trim(), forgotCode.value.trim(), forgotNewPassword.value)
      emit('authenticated', { token: res.token, user: res.user })
      emit('close')
    } catch (err) {
      errorMsg.value = err instanceof Error ? err.message : t('重置密码失败', 'Password reset failed')
    } finally {
      busy.value = false
    }
    return
  }

  const u = username.value.trim()
  if (!u || !password.value.trim()) {
    errorMsg.value = t('请输入账号和密码', 'Please enter username and password')
    return
  }

  if (mode.value === 'register') {
    let hasErr = false
    if (requiresInviteCode.value && !inviteCode.value.trim()) {
      fieldErrors.value.invite_code = t(
        '请输入管理员发放的一次性邀请码',
        'Please enter a one-time invite code',
      )
      hasErr = true
    }
    if (!USERNAME_RE.test(u)) {
      fieldErrors.value.username = t(
        '用户名需 4~20 位，只能用字母、数字、下划线或中文',
        'Username must be 4–20 chars (letters, digits, underscore, or Chinese)',
      )
      hasErr = true
    }
    if (!isValidRegisterPassword(password.value)) {
      fieldErrors.value.password = t(
        '密码至少 8 位（最长 64 位），需同时包含字母和数字',
        'Password must be 8–64 chars with both letters and digits',
      )
      hasErr = true
    }
    const c = regContact.value.trim()
    if (c) {
      const isEmail = c.includes('@') && c.includes('.')
      const isPhone = /^\+?\d{7,16}$/.test(c)
      if (!isEmail && !isPhone) {
        fieldErrors.value.contact = t('请输入有效的手机号或电子邮箱', 'Enter a valid phone number or email')
        hasErr = true
      }
    }
    if (hasErr) return
  }

  busy.value = true
  try {
    if (mode.value === 'login') {
      const sess = await apiLogin(u, password.value)
      emit('authenticated', sess)
      emit('close')
    } else {
      const c = regContact.value.trim()
      const isEmail = c.includes('@')
      const sess = await apiRegister(u, password.value, displayName.value.trim(), {
        email: isEmail ? c : '',
        phone: c && !isEmail ? c : '',
        invite_code: inviteCode.value.trim(),
      })
      emit('authenticated', sess)
      emit('close')
    }
  } catch (err) {
    if (err instanceof ApiValidationError) {
      fieldErrors.value = {
        username: err.fieldErrors.username,
        password: err.fieldErrors.password,
        contact: err.fieldErrors.contact || err.fieldErrors.email || err.fieldErrors.phone,
        invite_code: err.fieldErrors.invite_code,
      }
      if (!fieldErrors.value.username && !fieldErrors.value.password && !fieldErrors.value.contact && !fieldErrors.value.invite_code) {
        errorMsg.value = err.message
      }
    } else {
      errorMsg.value = err instanceof Error ? err.message : t('操作失败', 'Request failed')
    }
  } finally {
    busy.value = false
  }
}

async function submitBindContact() {
  if (!props.session) return
  errorMsg.value = ''
  okMsg.value = ''
  if (!bindTarget.value.trim() || !bindCode.value.trim()) {
    errorMsg.value = t('请输入手机号/邮箱及验证码', 'Enter phone/email and verification code')
    return
  }
  busy.value = true
  try {
    const res = await apiBindContact(props.session.token, bindTarget.value.trim(), bindCode.value.trim())
    emit('authenticated', { token: props.session.token, user: res.user })
    okMsg.value = t('绑定成功！今后可直接用该手机号/邮箱登录或找回密码。', 'Bound! You can now sign in or recover passwords using it.')
    bindTarget.value = ''
    bindCode.value = ''
    showBindForm.value = false
  } catch (err) {
    errorMsg.value = err instanceof Error ? err.message : t('绑定失败', 'Binding failed')
  } finally {
    busy.value = false
  }
}

async function submitChangePassword() {
  if (!props.session) return
  errorMsg.value = ''
  okMsg.value = ''
  if (!isValidRegisterPassword(newPassword.value)) {
    errorMsg.value = t('新密码需为 8~64 位，且同时包含字母和数字', 'New password must be 8–64 chars with both letters and digits')
    return
  }
  busy.value = true
  try {
    const res = await apiChangePassword(props.session.token, currentPassword.value, newPassword.value)
    emit('authenticated', { token: res.token, user: res.user })
    okMsg.value = t('密码已更新。', 'Password updated.')
    currentPassword.value = ''
    newPassword.value = ''
    showPwForm.value = false
  } catch (err) {
    errorMsg.value = err instanceof Error ? err.message : t('修改密码失败', 'Failed to update password')
  } finally {
    busy.value = false
  }
}

const digestBusy = ref(false)
async function toggleEmailDigest() {
  if (!props.session || digestBusy.value) return
  const nextVal = !(props.session.user.email_digest_enabled ?? true)
  digestBusy.value = true
  errorMsg.value = ''
  okMsg.value = ''
  try {
    const res = await apiUpdatePreferences(props.session.token, { email_digest_enabled: nextVal })
    emit('authenticated', { token: props.session.token, user: res.user })
    okMsg.value = nextVal
      ? t('已开启每日 08:00 邮件摘要推送', 'Daily 08:00 email digest enabled')
      : t('已暂停每日邮件摘要推送', 'Daily email digest paused')
  } catch (err) {
    errorMsg.value = err instanceof Error ? err.message : t('更新邮件偏好失败', 'Failed to update preference')
  } finally {
    digestBusy.value = false
  }
}
</script>

<template>
  <div
    v-if="isOpen"
    class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/60 backdrop-blur-xs"
    role="dialog"
    aria-modal="true"
    aria-labelledby="auth-modal-title"
    :aria-label="t('账号登录与云端同步', 'Account Sign In & Cloud Sync')"
    @click.self="props.allowClose !== false && onBackdropClick()"
  >
    <div
      ref="dialogEl"
      tabindex="-1"
      class="w-full max-w-md rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-2xl overflow-hidden focus:outline-none"
    >
      <header class="px-5 py-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between gap-2">
        <div class="flex items-center gap-2 font-bold text-slate-900 dark:text-white text-base">
          <Cloud class="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
          <h2 id="auth-modal-title">
            {{
              session
                ? t('我的镜信账号', 'My Account')
                : mode === 'login'
                  ? t('登录镜信账号', 'Sign In to MirrorBrief')
                  : mode === 'register'
                    ? t('注册镜信新账号', 'Create MirrorBrief Account')
                    : t('找回 / 重置登录密码', 'Reset Password')
            }}
          </h2>
        </div>
        <button
          v-if="props.allowClose !== false"
          type="button"
          @click="onCloseButton"
          class="w-8 h-8 rounded-lg inline-flex items-center justify-center text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
          :aria-label="t('关闭账号弹窗', 'Close account dialog')"
        >
          <X class="w-4 h-4" />
        </button>
      </header>

      <DialogDirtyGuard
        :open="dirtyConfirmOpen"
        @confirm="confirmDirtyDiscard"
        @cancel="cancelDirtyClose"
      />

      <!-- Logged-in Account View -->
      <div v-if="session" class="p-5 space-y-4 text-sm">
        <div class="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 p-3.5 space-y-2.5">
          <div class="flex items-center justify-between gap-3">
            <div class="flex items-center gap-3 min-w-0">
              <button
                type="button"
                @click="emit('open-avatar-picker')"
                class="ios-tap rounded-full shrink-0 focus-visible:outline-2 focus-visible:outline-[#007AFF]"
                :title="t('点击更换高定头像或上传照片', 'Change or upload avatar')"
                :aria-label="t('更换头像', 'Change avatar')"
                data-testid="auth-modal-avatar-btn"
              >
                <UserAvatar
                  :avatar="userAvatar || session.user.avatar"
                  :username="session.user.username"
                  :role="session.user.role"
                  size="lg"
                  :editable="true"
                />
              </button>
              <div class="min-w-0">
                <div class="font-bold text-slate-900 dark:text-white truncate">
                  {{ session.user.display_name || session.user.username }}
                </div>
                <div class="flex items-center gap-2 mt-0.5">
                  <span class="text-xs font-mono text-slate-500 truncate">@{{ session.user.username }}</span>
                  <button
                    type="button"
                    @click="emit('open-avatar-picker')"
                    class="text-[11px] font-semibold text-[#007AFF] dark:text-[#0A84FF] hover:underline shrink-0"
                  >
                    {{ t('更换头像', 'Edit Avatar') }}
                  </button>
                </div>
              </div>
            </div>
            <span
              class="px-2 py-0.5 rounded-full text-[11px] font-semibold shrink-0"
              :class="isAdminRole(session.user.role) ? 'bg-rose-100 text-rose-700 dark:bg-rose-950/60 dark:text-rose-300' : 'bg-blue-100 text-blue-700 dark:bg-blue-950/60 dark:text-blue-300'"
            >
              {{ roleLabel(session.user.role) }}
            </span>
          </div>

          <div class="grid grid-cols-1 gap-1 text-xs text-slate-600 dark:text-slate-300 pt-1 border-t border-slate-200/70 dark:border-slate-700/70">
            <div class="flex items-center justify-between">
              <span class="inline-flex items-center gap-1 text-slate-500"><Phone class="w-3.5 h-3.5" /> {{ t('绑定手机：', 'Phone: ') }}</span>
              <span class="font-mono">{{ session.user.phone || t('未绑定', 'Unbound') }}</span>
            </div>
            <div class="flex items-center justify-between">
              <span class="inline-flex items-center gap-1 text-slate-500"><Mail class="w-3.5 h-3.5" /> {{ t('绑定邮箱：', 'Email: ') }}</span>
              <span class="font-mono">{{ session.user.email || t('未绑定', 'Unbound') }}</span>
            </div>
            <div class="flex items-center justify-between gap-2 pt-1">
              <span class="text-slate-600 dark:text-slate-300">
                {{ t('每日 08:00 重点邮件摘要', 'Daily 08:00 Email Digest') }}
                <span v-if="!session.user.email" class="text-[11px] text-amber-600 dark:text-amber-400">
                  ({{ t('需先绑定邮箱', 'Bind email first') }})
                </span>
              </span>
              <button
                type="button"
                role="switch"
                :aria-checked="Boolean(session.user.email_digest_enabled ?? true)"
                :disabled="!session.user.email || digestBusy"
                @click="toggleEmailDigest"
                class="px-2.5 py-0.5 rounded-full text-[11px] font-semibold border transition-colors disabled:opacity-50"
                :class="
                  session.user.email && (session.user.email_digest_enabled ?? true)
                    ? 'bg-emerald-100 text-emerald-800 border-emerald-300 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-700'
                    : 'bg-slate-100 text-slate-600 border-slate-300 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700'
                "
              >
                {{
                  digestBusy
                    ? '...'
                    : session.user.email && (session.user.email_digest_enabled ?? true)
                      ? t('已开启', 'On')
                      : t('已关闭', 'Off')
                }}
              </button>
            </div>
          </div>

          <p class="text-xs text-emerald-700 dark:text-emerald-300">
            {{ t('最近云端同步：', 'Last Cloud Sync: ') }}{{ lastSyncedAt ? lastSyncedAt.slice(0, 19).replace('T', ' ') : t('已连接云端', 'Connected') }}
          </p>
        </div>

        <!-- Personal Pre-Market Brief Summary -->
        <div
          v-if="morningBrief && (morningBrief.portfolioHits.length > 0 || morningBrief.upcomingCatalysts.length > 0)"
          class="rounded-xl border border-amber-200/80 dark:border-amber-900/60 bg-amber-50/70 dark:bg-amber-950/25 p-3 space-y-1.5 text-xs"
          data-testid="account-morning-brief"
        >
          <div class="flex items-center justify-between gap-2">
            <span class="inline-flex items-center gap-1.5 font-bold text-amber-900 dark:text-amber-200">
              <Sun class="w-3.5 h-3.5 shrink-0" :stroke-width="1.75" />
              <span>{{ t('盘前个人早报 · 命中持仓与临近催化', 'Personal Pre-Market Brief') }}</span>
            </span>
            <button
              v-if="!session.user.email"
              type="button"
              @click="showBindForm = true; showPwForm = false"
              class="text-[11px] font-semibold text-indigo-600 dark:text-indigo-400 hover:underline shrink-0"
            >
              {{ t('立即绑定邮箱 →', 'Bind Email →') }}
            </button>
          </div>
          <div v-for="ph in morningBrief.portfolioHits" :key="ph.id" class="text-slate-700 dark:text-slate-200 truncate">
            • <span class="font-semibold">{{ String(ph.tags[0] || '').replace(/^[\s·•:：]+|[\s·•:：]+$/g, '') }}</span>：{{ ph.title }}
          </div>
          <div v-for="cal in morningBrief.upcomingCatalysts" :key="cal.id" class="inline-flex items-center gap-1 text-amber-800 dark:text-amber-300 truncate max-w-full">
            <Calendar class="w-3 h-3 shrink-0" :stroke-width="1.75" />
            <span class="truncate">{{ cal.title }}</span>
          </div>
        </div>

        <div class="flex flex-wrap gap-2">
          <button
            type="button"
            :disabled="syncBusy"
            @click="emit('sync-now')"
            class="flex-1 px-3 py-2 rounded-xl bg-indigo-600 text-white text-xs font-semibold hover:bg-indigo-700 disabled:opacity-60"
          >
            {{ syncBusy ? t('正在同步...', 'Syncing...') : t('立即同步云端数据', 'Sync to Cloud Now') }}
          </button>
          <a
            v-if="isAdminRole(session.user.role)"
            href="./admin.html"
            class="inline-flex items-center gap-1 px-3 py-2 rounded-xl bg-slate-900 dark:bg-rose-600 text-white text-xs font-semibold hover:opacity-90"
          >
            <Shield class="w-3.5 h-3.5" />
            <span>{{ t('管理员后台', 'Admin Console') }}</span>
          </a>
        </div>

        <div class="pt-1 border-t border-slate-200 dark:border-slate-800 space-y-2.5">
          <div class="flex items-center gap-4 text-xs font-medium">
            <button
              type="button"
              @click="showBindForm = !showBindForm; showPwForm = false"
              class="text-indigo-600 dark:text-indigo-400 hover:underline"
            >
              {{ showBindForm ? t('收起绑定', 'Hide Bind') : t('绑定 / 换绑手机或邮箱', 'Bind Phone or Email') }}
            </button>
            <button
              type="button"
              @click="showPwForm = !showPwForm; showBindForm = false"
              class="inline-flex items-center gap-1 text-blue-600 dark:text-blue-400 hover:underline"
            >
              <KeyRound class="w-3.5 h-3.5" />
              <span>{{ showPwForm ? t('收起改密', 'Hide Password') : t('修改密码', 'Change Password') }}</span>
            </button>
          </div>

          <form v-if="showBindForm" @submit.prevent="submitBindContact" class="space-y-2">
            <div class="flex gap-1.5">
              <input
                v-model="bindTarget"
                type="text"
                :placeholder="t('输入要绑定的手机号或邮箱', 'Enter phone or email to bind')"
                required
                class="flex-1 h-9 px-3 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs"
              />
              <button
                type="button"
                :disabled="sendingCode"
                @click="handleSendOtp(bindTarget, 'bind')"
                class="px-2.5 h-9 rounded-lg border border-indigo-200 dark:border-indigo-800 bg-indigo-50 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300 text-xs font-semibold shrink-0"
              >
                {{ sendingCode ? t('发送中...', 'Sending...') : t('获取验证码', 'Send Code') }}
              </button>
            </div>
            <input
              v-model="bindCode"
              type="text"
              :placeholder="t('输入 6 位验证码', 'Enter 6-digit code')"
              required
              class="w-full h-9 px-3 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs"
            />
            <button
              type="submit"
              :disabled="busy"
              class="w-full h-9 rounded-lg bg-indigo-600 text-white text-xs font-semibold"
            >
              {{ t('确认绑定', 'Confirm Binding') }}
            </button>
          </form>

          <form v-if="showPwForm" @submit.prevent="submitChangePassword" class="space-y-2">
            <input
              v-model="currentPassword"
              type="password"
              :placeholder="t('输入当前密码', 'Current password')"
              required
              class="w-full h-9 px-3 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs"
            />
            <input
              v-model="newPassword"
              type="password"
              :placeholder="t('输入新密码（8~64 位，须含字母和数字）', 'New password (8–64 chars, letters & digits)')"
              required
              class="w-full h-9 px-3 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs"
            />
            <button
              type="submit"
              :disabled="busy"
              class="w-full h-9 rounded-lg bg-slate-900 dark:bg-blue-600 text-white text-xs font-semibold"
            >
              {{ t('确认修改密码', 'Update Password') }}
            </button>
          </form>

          <p v-if="errorMsg" class="text-xs text-red-600 dark:text-red-400">{{ errorMsg }}</p>
          <p v-if="okMsg" class="text-xs text-emerald-600 dark:text-emerald-400">{{ okMsg }}</p>

          <button
            type="button"
            @click="emit('logout')"
            class="w-full inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl border border-red-200 dark:border-red-900 text-red-600 dark:text-red-400 text-xs font-semibold hover:bg-red-50 dark:hover:bg-red-950/30"
          >
            <LogOut class="w-3.5 h-3.5" />
            <span>{{ t('退出当前账号', 'Sign Out') }}</span>
          </button>
        </div>
      </div>

      <!-- Login / Register / Forgot Password Form -->
      <form v-else novalidate @submit.prevent="submitAuth" class="p-5 space-y-3.5 text-sm">
        <div class="grid grid-cols-3 rounded-xl bg-slate-100 dark:bg-slate-800 p-1 text-xs font-semibold">
          <button
            type="button"
            @click="mode = 'login'; errorMsg = ''; okMsg = ''; clearFieldErrors()"
            class="py-1.5 rounded-lg transition-colors"
            :class="mode === 'login' ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-xs' : 'text-slate-500'"
          >
            {{ t('账号登录', 'Sign In') }}
          </button>
          <button
            type="button"
            @click="mode = 'register'; errorMsg = ''; okMsg = ''; clearFieldErrors()"
            class="py-1.5 rounded-lg transition-colors"
            :class="mode === 'register' ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-xs' : 'text-slate-500'"
          >
            {{ t('注册新账号', 'Register') }}
          </button>
          <button
            type="button"
            @click="mode = 'forgot'; errorMsg = ''; okMsg = ''; clearFieldErrors()"
            class="py-1.5 rounded-lg transition-colors"
            :class="mode === 'forgot' ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-xs' : 'text-slate-500'"
          >
            {{ t('忘记密码', 'Forgot Password') }}
          </button>
        </div>

        <div v-if="mode === 'forgot'" class="space-y-2.5">
          <div>
            <label class="block text-xs font-medium text-slate-600 dark:text-slate-300 mb-1">
              {{ t('已绑定的手机号或邮箱', 'Bound Phone or Email') }}
            </label>
            <div class="flex gap-1.5">
              <input
                v-model="forgotTarget"
                type="text"
                :placeholder="t('输入手机号或邮箱', 'Enter phone or email')"
                required
                class="flex-1 h-10 px-3 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm text-slate-900 dark:text-white"
              />
              <button
                type="button"
                :disabled="sendingCode"
                @click="handleSendOtp(forgotTarget, 'reset_password')"
                class="px-3 h-10 rounded-xl border border-indigo-200 dark:border-indigo-800 bg-indigo-50 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300 text-xs font-semibold shrink-0"
              >
                {{ sendingCode ? t('发送中...', 'Sending...') : t('获取验证码', 'Send Code') }}
              </button>
            </div>
          </div>
          <div>
            <label class="block text-xs font-medium text-slate-600 dark:text-slate-300 mb-1">
              {{ t('6 位验证码', '6-Digit Code') }}
            </label>
            <input
              v-model="forgotCode"
              type="text"
              :placeholder="t('输入收到的 6 位验证码', 'Enter 6-digit code')"
              required
              class="w-full h-10 px-3 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm text-slate-900 dark:text-white"
            />
          </div>
          <div>
            <label class="block text-xs font-medium text-slate-600 dark:text-slate-300 mb-1">
              {{ t('设置新密码', 'New Password') }}
            </label>
            <input
              v-model="forgotNewPassword"
              type="password"
              :placeholder="t('输入新密码（8~64 位，须含字母和数字）', 'New password (8–64 chars, letters & digits)')"
              required
              class="w-full h-10 px-3 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm text-slate-900 dark:text-white"
            />
          </div>
        </div>

        <div v-else class="space-y-2.5">
          <div>
            <label class="block text-xs font-medium text-slate-600 dark:text-slate-300 mb-1">
              {{ mode === 'login' ? t('用户名 / 已绑定手机号 / 邮箱', 'Username, Phone, or Email') : t('用户名', 'Username') }}
            </label>
            <input
              v-model="username"
              type="text"
              autocomplete="username"
              :placeholder="mode === 'login' ? t('输入用户名、手机号或邮箱', 'Username, phone, or email') : t('4~20 位字母、数字、下划线或中文', '4–20 letters, digits, underscore, or Chinese')"
              @input="fieldErrors.username = undefined"
              class="w-full h-10 px-3 rounded-xl border bg-white dark:bg-slate-800 text-sm text-slate-900 dark:text-white"
              :class="fieldErrors.username ? 'border-red-500 dark:border-red-500' : 'border-slate-300 dark:border-slate-700'"
            />
            <p v-if="fieldErrors.username" class="mt-1 text-xs text-red-600 dark:text-red-400">
              {{ fieldErrors.username }}
            </p>
          </div>
          <div v-if="mode === 'register' && requiresInviteCode">
            <label class="block text-xs font-medium text-slate-600 dark:text-slate-300 mb-1">
              {{ t('一次性邀请码（必填）', 'One-Time Invite Code (Required)') }}
            </label>
            <input
              v-model="inviteCode"
              type="text"
              autocomplete="off"
              :placeholder="t('请输入管理员发放的邀请码，如 MB-XXXX-XXXX', 'Enter invite code (e.g. MB-XXXX-XXXX)')"
              @input="fieldErrors.invite_code = undefined"
              class="w-full h-10 px-3 rounded-xl border bg-white dark:bg-slate-800 font-mono text-sm text-slate-900 dark:text-white uppercase"
              :class="fieldErrors.invite_code ? 'border-red-500 dark:border-red-500' : 'border-slate-300 dark:border-slate-700'"
            />
            <p v-if="fieldErrors.invite_code" class="mt-1 text-xs text-red-600 dark:text-red-400">
              {{ fieldErrors.invite_code }}
            </p>
          </div>
          <div v-if="mode === 'register'">
            <label class="block text-xs font-medium text-slate-600 dark:text-slate-300 mb-1">
              {{ t('昵称（可选）', 'Display Name (Optional)') }}
            </label>
            <input
              v-model="displayName"
              type="text"
              :placeholder="t('例如：阿滨', 'e.g. Alex')"
              class="w-full h-10 px-3 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm text-slate-900 dark:text-white"
            />
          </div>
          <div v-if="mode === 'register'">
            <div class="flex flex-wrap items-center justify-between gap-1 mb-1">
              <label class="text-xs font-medium text-slate-600 dark:text-slate-300">
                {{ t('绑定手机号或邮箱（可选）', 'Phone or Email (Optional)') }}
              </label>
              <span class="text-[11px] text-slate-400">
                {{ t('建议绑定：未绑定将无法找回密码和云端数据', 'Recommended: required for password & cloud data recovery') }}
              </span>
            </div>
            <input
              v-model="regContact"
              type="text"
              :placeholder="t('选填手机号或邮箱地址（免验证码直接绑定）', 'Optional phone or email (no OTP needed)')"
              @input="fieldErrors.contact = undefined"
              class="w-full h-10 px-3 rounded-xl border bg-white dark:bg-slate-800 text-sm text-slate-900 dark:text-white"
              :class="fieldErrors.contact ? 'border-red-500 dark:border-red-500' : 'border-slate-300 dark:border-slate-700'"
            />
            <p v-if="fieldErrors.contact" class="mt-1 text-xs text-red-600 dark:text-red-400">
              {{ fieldErrors.contact }}
            </p>
          </div>
          <div>
            <div class="flex items-center justify-between mb-1">
              <label class="block text-xs font-medium text-slate-600 dark:text-slate-300">{{ t('密码', 'Password') }}</label>
              <button
                v-if="mode === 'login'"
                type="button"
                @click="mode = 'forgot'; errorMsg = ''; clearFieldErrors()"
                class="text-xs text-indigo-600 dark:text-indigo-400 hover:underline"
              >
                {{ t('忘记密码？', 'Forgot password?') }}
              </button>
            </div>
            <input
              v-model="password"
              type="password"
              :autocomplete="mode === 'login' ? 'current-password' : 'new-password'"
              :placeholder="mode === 'login' ? t('输入登录密码', 'Enter password') : t('至少 8 位，需同时含字母和数字', 'Min 8 chars with letters & digits')"
              @input="fieldErrors.password = undefined"
              class="w-full h-10 px-3 rounded-xl border bg-white dark:bg-slate-800 text-sm text-slate-900 dark:text-white"
              :class="fieldErrors.password ? 'border-red-500 dark:border-red-500' : 'border-slate-300 dark:border-slate-700'"
            />
            <p v-if="fieldErrors.password" class="mt-1 text-xs text-red-600 dark:text-red-400">
              {{ fieldErrors.password }}
            </p>
          </div>
        </div>

        <p v-if="errorMsg" class="text-xs text-red-600 dark:text-red-400 font-medium">{{ errorMsg }}</p>
        <p v-if="okMsg" class="text-xs text-emerald-600 dark:text-emerald-400 font-medium">{{ okMsg }}</p>

        <button
          type="submit"
          :disabled="busy"
          class="w-full h-10 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-sm disabled:opacity-60 transition-colors"
        >
          {{
            busy
              ? t('提交中…', 'Submitting…')
              : mode === 'login'
                ? t('立即登录', 'Sign In')
                : mode === 'register'
                  ? t('创建账号并开启云同步', 'Create Account & Sync')
                  : t('确认重置密码并登录', 'Reset Password & Sign In')
          }}
        </button>

        <p v-if="mode === 'register'" class="text-[11px] text-center text-slate-400 dark:text-slate-500 pt-0.5">
          {{ t('注册即表示同意', 'By registering you agree to') }}
          <a href="./terms.html" target="_blank" rel="noopener noreferrer" class="text-slate-600 dark:text-slate-300 underline underline-offset-2 hover:text-indigo-600">{{ t('《用户协议》', 'Terms') }}</a>
          {{ t('和', 'and') }}
          <a href="./privacy.html" target="_blank" rel="noopener noreferrer" class="text-slate-600 dark:text-slate-300 underline underline-offset-2 hover:text-indigo-600">{{ t('《隐私政策》', 'Privacy Policy') }}</a>
        </p>
      </form>
    </div>
  </div>
</template>
