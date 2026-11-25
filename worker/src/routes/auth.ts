import { Hono } from 'hono'
import { requireUser, resolveAccessMode } from '../authMiddleware'
import { signJwt, verifyPassword } from '../crypto'
import {
  authenticateUser,
  bindUserContact,
  consumeInviteCode,
  createUser,
  createVerificationCode,
  getUserByContact,
  getUserById,
  getUserByUsername,
  getUserState,
  logAudit,
  toPublicUser,
  updatePassword,
  updateUserPreferences,
  validateInviteCode,
  verifyAndConsumeCode,
} from '../db'
import { getPushConfig } from '../dbExtras'
import { checkAndHitRateLimit, checkRegistrationGuards, recordRegistrationGuard } from '../rateLimit'
import type { Env, HonoVariables } from '../types'

const USERNAME_RE = /^[A-Za-z0-9_\u4e00-\u9fa5]{4,20}$/
const HAS_LETTER_RE = /[A-Za-z]/
const HAS_DIGIT_RE = /\d/
const PHONE_RE = /^\+?\d{7,16}$/

function validatePasswordStrength(pw: string, fieldName = 'new_password'): string | null {
  if (!pw || !pw.trim() || pw.length < 8 || pw.length > 64 || !HAS_LETTER_RE.test(pw) || !HAS_DIGIT_RE.test(pw)) {
    return fieldName
  }
  return null
}

async function deliverOtpCode(
  env: Env,
  target: string,
  channel: string,
  code: string,
): Promise<{ sent: boolean; channel: string; message: string; dev_code?: string }> {
  const textMsg = `【镜信】您的验证码为：${code}（10 分钟内有效，请勿泄露给他人）。`

  if (channel === 'email' && (env.RESEND_API_KEY || '').trim()) {
    try {
      const resp = await fetch('https://api.resend.com/emails', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${env.RESEND_API_KEY!.trim()}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          from: (env.RESEND_FROM || 'MirrorBrief <noreply@mirrorinfo.xyz>').trim(),
          to: [target],
          subject: `【镜信】账号安全验证码 ${code}`,
          text: textMsg,
        }),
      })
      if (resp.ok) {
        return { sent: true, channel: 'email', message: '验证码已发送至您的邮箱' }
      }
    } catch {
      // Fallback below
    }
  }

  const pushCfg = await getPushConfig(env, 'global')
  const smsWebhook = (env.SMS_WEBHOOK_URL || String(pushCfg.sms_webhook_url || '')).trim()
  if (channel === 'sms' && smsWebhook) {
    try {
      const resp = await fetch(smsWebhook, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone: target, code, text: textMsg }),
      })
      if (resp.ok) {
        return { sent: true, channel: 'sms', message: '验证码已发送至您的手机' }
      }
    } catch {
      // Fallback below
    }
  }

  return {
    sent: false,
    channel,
    dev_code: code,
    message: `验证码已生成：${code}（配置邮件/短信网关后将自动静默下发）`,
  }
}

export const authRoutes = new Hono<{ Bindings: Env; Variables: HonoVariables }>()

authRoutes.post('/send-code', async (c) => {
  const ip = c.get('clientIp')
  const rl = await checkAndHitRateLimit(c.env.DB, { scope: 'send_code', key: ip, limit: 12, windowSec: 600 })
  if (!rl.allowed) {
    return c.json({ detail: '发送验证码过于频繁，请稍后再试' }, 429)
  }

  const body = (await c.req.json().catch(() => ({}))) as { target?: string; purpose?: string }
  const target = (body.target || '').trim()
  const isEmail = target.includes('@') && target.includes('.')
  const isPhone = PHONE_RE.test(target)
  if (!isEmail && !isPhone) {
    return c.json({ detail: '请输入有效的手机号（如 13800138000）或电子邮箱' }, 400)
  }

  const purpose = (body.purpose || 'register').trim() || 'register'
  const existing = await getUserByContact(c.env.DB, target)
  if ((purpose === 'register' || purpose === 'bind') && existing) {
    return c.json({ detail: '该手机号或邮箱已被绑定' }, 409)
  }
  if (purpose === 'reset_password' && !existing) {
    return c.json({ detail: '未找到绑定该手机号或邮箱的账号' }, 404)
  }

  const channel = isEmail ? 'email' : 'sms'
  const code = await createVerificationCode(c.env.DB, { target, channel, purpose, ip })
  const delivery = await deliverOtpCode(c.env, target, channel, code)
  await logAudit(c.env.DB, {
    action: 'send_otp_code',
    username: target,
    detail: `purpose=${purpose} channel=${channel} sent=${delivery.sent}`,
    ip,
  })
  return c.json({ ok: true, ...delivery })
})

authRoutes.post('/register', async (c) => {
  const ip = c.get('clientIp')
  const deviceId = c.get('deviceId')
  const accessMode = resolveAccessMode(c.env.SITE_ACCESS_MODE)

  const body = (await c.req.json().catch(() => ({}))) as {
    username?: string
    password?: string
    display_name?: string
    email?: string
    phone?: string
    code?: string
    invite_code?: string
    inviteCode?: string
  }

  const uname = (body.username || '').trim()
  const pw = body.password || ''

  const rlErr = await checkRegistrationGuards(c.env.DB, ip, deviceId)
  if (rlErr) {
    await logAudit(c.env.DB, {
      action: 'register_rate_limited',
      username: uname.slice(0, 32),
      detail: `${rlErr} (${deviceId.slice(0, 24)})`,
      ip,
    })
    return c.json({ detail: rlErr }, 429)
  }

  let matchedInviteId: number | null = null
  if (accessMode === 'invite_only' || accessMode === 'private_gate') {
    const rawInvite = (body.invite_code || body.inviteCode || '').trim()
    if (!rawInvite) {
      return c.json(
        {
          detail: [
            {
              loc: ['body', 'invite_code'],
              msg: '当前系统处于邀请注册模式，请填写管理员发放的一次性邀请码',
              type: 'value_error',
            },
          ],
        },
        422,
      )
    }
    const validInv = await validateInviteCode(c.env.DB, rawInvite)
    if (!validInv) {
      await logAudit(c.env.DB, {
        action: 'register_invalid_invite',
        username: uname.slice(0, 32),
        detail: `Invalid/used invite code: ${rawInvite.slice(0, 24)}`,
        ip,
      })
      return c.json({ detail: '邀请码无效、已被使用或已过期，请联系管理员获取新邀请码' }, 403)
    }
    matchedInviteId = validInv.id
  }

  if (!uname || !pw || !pw.trim()) {
    return c.json({ detail: '请输入账号和密码' }, 400)
  }
  if (!USERNAME_RE.test(uname)) {
    return c.json(
      { detail: [{ loc: ['body', 'username'], msg: '用户名需 4~20 位，只能用字母、数字、下划线或中文' }] },
      422,
    )
  }
  if (validatePasswordStrength(pw, 'password')) {
    return c.json(
      { detail: [{ loc: ['body', 'password'], msg: '密码至少 8 位（最长 64 位），需同时包含字母和数字' }] },
      422,
    )
  }
  if (await getUserByUsername(c.env.DB, uname)) {
    return c.json({ detail: '该用户名已被注册' }, 409)
  }

  const email = (body.email || '').trim()
  const phone = (body.phone || '').trim()
  const contactTarget = email || phone
  if (contactTarget) {
    const isEmail = contactTarget.includes('@') && contactTarget.includes('.')
    const isPhone = PHONE_RE.test(contactTarget)
    if (!isEmail && !isPhone) {
      return c.json({ detail: [{ loc: ['body', 'contact'], msg: '请输入有效的手机号或电子邮箱' }] }, 422)
    }
    if (await getUserByContact(c.env.DB, contactTarget)) {
      return c.json({ detail: [{ loc: ['body', 'contact'], msg: '该手机号或邮箱已被其他账号绑定' }] }, 422)
    }
    if ((body.code || '').trim()) {
      const okCode = await verifyAndConsumeCode(c.env.DB, {
        target: contactTarget,
        purpose: 'register',
        code: body.code!,
      })
      if (!okCode) {
        return c.json({ detail: '验证码错误或已过期' }, 400)
      }
    }
  }

  const user = await createUser(c.env, {
    username: uname,
    password: pw,
    displayName: (body.display_name || '').trim() || uname,
    email,
    phone,
    role: 'user',
    ip,
  })

  if (matchedInviteId !== null) {
    const consumed = await consumeInviteCode(c.env.DB, {
      codeId: matchedInviteId,
      userId: user.id,
      username: user.username,
    })
    if (!consumed) {
      // Concurrent race on one-time invite code: roll back created user
      await c.env.DB.prepare('DELETE FROM users WHERE id = ?1').bind(user.id).run()
      return c.json({ detail: '该邀请码已被抢先使用，请联系管理员获取新邀请码' }, 409)
    }
  }

  await recordRegistrationGuard(c.env.DB, ip, deviceId)
  const token = await signJwt(
    { sub: user.id, username: user.username, role: user.role, ver: user.token_version },
    c.env.JWT_SECRET,
  )
  return c.json({ token, user: toPublicUser(user) })
})

authRoutes.post('/login', async (c) => {
  const ip = c.get('clientIp')
  const body = (await c.req.json().catch(() => ({}))) as { username?: string; password?: string }
  const uname = (body.username || '').trim()
  const pw = body.password || ''

  const rl = await checkAndHitRateLimit(c.env.DB, {
    scope: 'login',
    key: `${ip}:${uname.toLowerCase()}`,
    limit: 15,
    windowSec: 300,
  })
  if (!rl.allowed) {
    return c.json({ detail: '登录尝试过于频繁，请 5 分钟后再试' }, 429)
  }

  if (!uname || !pw) {
    return c.json({ detail: '请输入用户名和密码' }, 400)
  }

  const user = await authenticateUser(c.env, { username: uname, password: pw, ip })
  if (!user) {
    return c.json({ detail: '用户名或密码错误（或账号已被停用）' }, 401)
  }

  const token = await signJwt(
    { sub: user.id, username: user.username, role: user.role, ver: user.token_version },
    c.env.JWT_SECRET,
  )
  return c.json({ token, user: toPublicUser(user) })
})

authRoutes.get('/me', requireUser, async (c) => {
  const user = c.get('user')!
  const st = await getUserState(c.env, user.id)
  return c.json({
    user: toPublicUser(user),
    sync_summary: {
      has_cloud_state: st !== null,
      updated_at: st ? st.updated_at : null,
      counts: st ? st.counts : null,
    },
  })
})

authRoutes.patch('/preferences', requireUser, async (c) => {
  const user = c.get('user')!
  const body = (await c.req.json().catch(() => ({}))) as { email_digest_enabled?: boolean }
  const updated = await updateUserPreferences(c.env.DB, {
    userId: user.id,
    emailDigestEnabled: Boolean(body.email_digest_enabled),
    ip: c.get('clientIp'),
  })
  return c.json({ ok: true, user: toPublicUser(updated) })
})

authRoutes.post('/password', requireUser, async (c) => {
  const user = c.get('user')!
  const body = (await c.req.json().catch(() => ({}))) as {
    current_password?: string
    new_password?: string
  }
  const curPw = body.current_password || ''
  const newPw = body.new_password || ''

  if (validatePasswordStrength(newPw, 'new_password')) {
    return c.json(
      { detail: [{ loc: ['body', 'new_password'], msg: '密码至少 8 位（最长 64 位），需同时包含字母和数字' }] },
      422,
    )
  }

  const freshUser = await getUserById(c.env.DB, user.id)
  if (!freshUser || !(await verifyPassword(curPw, freshUser.password_hash))) {
    return c.json({ detail: '当前密码不正确' }, 400)
  }

  const updated = await updatePassword(c.env, {
    userId: user.id,
    newPassword: newPw,
    actorUsername: user.username,
    ip: c.get('clientIp'),
  })
  const token = await signJwt(
    { sub: updated.id, username: updated.username, role: updated.role, ver: updated.token_version },
    c.env.JWT_SECRET,
  )
  return c.json({ ok: true, token, user: toPublicUser(updated) })
})

authRoutes.post('/bind-contact', requireUser, async (c) => {
  const user = c.get('user')!
  const body = (await c.req.json().catch(() => ({}))) as { target?: string; code?: string }
  const target = (body.target || '').trim()
  const isEmail = target.includes('@') && target.includes('.')
  const isPhone = PHONE_RE.test(target)
  if (!isEmail && !isPhone) {
    return c.json({ detail: '请输入有效的手机号或电子邮箱' }, 400)
  }
  const okCode = await verifyAndConsumeCode(c.env.DB, {
    target,
    purpose: 'bind',
    code: body.code || '',
  })
  if (!okCode) {
    return c.json({ detail: '验证码错误或已过期' }, 400)
  }
  try {
    const updated = await bindUserContact(c.env.DB, {
      userId: user.id,
      email: isEmail ? target : undefined,
      phone: isPhone ? target : undefined,
      ip: c.get('clientIp'),
    })
    return c.json({ ok: true, user: toPublicUser(updated) })
  } catch (err) {
    return c.json({ detail: err instanceof Error ? err.message : '绑定失败' }, 409)
  }
})

authRoutes.post('/reset-password', async (c) => {
  const ip = c.get('clientIp')
  const rl = await checkAndHitRateLimit(c.env.DB, { scope: 'reset_pw', key: ip, limit: 10, windowSec: 600 })
  if (!rl.allowed) {
    return c.json({ detail: '操作过于频繁，请稍后再试' }, 429)
  }
  const body = (await c.req.json().catch(() => ({}))) as {
    target?: string
    code?: string
    new_password?: string
  }
  const newPw = body.new_password || ''
  if (validatePasswordStrength(newPw, 'new_password')) {
    return c.json(
      { detail: [{ loc: ['body', 'new_password'], msg: '密码至少 8 位（最长 64 位），需同时包含字母和数字' }] },
      422,
    )
  }
  const target = (body.target || '').trim()
  const user = await getUserByContact(c.env.DB, target)
  if (!user) {
    return c.json({ detail: '未找到绑定该手机号或邮箱的账号' }, 404)
  }
  const okCode = await verifyAndConsumeCode(c.env.DB, {
    target,
    purpose: 'reset_password',
    code: body.code || '',
  })
  if (!okCode) {
    return c.json({ detail: '验证码错误或已过期' }, 400)
  }
  const updated = await updatePassword(c.env, {
    userId: user.id,
    newPassword: newPw,
    actorUsername: `${user.username}(找回密码)`,
    ip,
  })
  const token = await signJwt(
    { sub: updated.id, username: updated.username, role: updated.role, ver: updated.token_version },
    c.env.JWT_SECRET,
  )
  return c.json({ ok: true, token, user: toPublicUser(updated) })
})
