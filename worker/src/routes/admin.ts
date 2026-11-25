import { Hono } from 'hono'
import { requireAdmin, requireSuperAdmin } from '../authMiddleware'
import { nowShanghaiIso, verifyPassword } from '../crypto'
import {
  adminUpdateUser,
  createInviteCodes,
  createUser,
  getAdminStats,
  getSiteSettings,
  getUserById,
  getUserByUsername,
  getUserPlainPassword,
  getUserState,
  listInviteCodes,
  listUsersWithStats,
  logAudit,
  revokeInviteCode,
  saveSiteSettings,
  toPublicUser,
} from '../db'
import {
  deleteEditorialOverride,
  deleteFeedback,
  getEditorialOverridesDoc,
  getPushConfig,
  listAuditLogs,
  listFeedback,
  listPushLogs,
  logPush,
  savePushConfig,
  titleFingerprint,
  updateFeedback,
  upsertEditorialOverride,
} from '../dbExtras'
import { QUOTES_CACHE_KEY, fetchAndBuildMarketQuotes, getDefaultEdgeCache } from '../quotes'
import type { Env, HonoVariables, UserRole } from '../types'
import { getWireLatestDoc, runWireCron } from '../wireCron'

const USERNAME_RE = /^[A-Za-z0-9_\u4e00-\u9fa5]{3,32}$/

export const adminRoutes = new Hono<{ Bindings: Env; Variables: HonoVariables }>()

adminRoutes.use('*', requireAdmin)

adminRoutes.get('/overview', async (c) => {
  const admin = c.get('user')!
  const stats = await getAdminStats(c.env.DB)
  let manifestSummary: Record<string, unknown> = {}
  try {
    const obj = await c.env.R2_DATA.get('data/manifest.json')
    if (obj) {
      const m = (await obj.json()) as Record<string, unknown>
      const smart = (m.smart as Record<string, unknown> | undefined) || {}
      const raw = (m.raw as Record<string, unknown> | undefined) || {}
      manifestSummary = {
        smart_batch_id: smart.latest_batch_id || smart.batch_id,
        smart_generated_at: smart.generated_at,
        raw_summary: raw.summary,
        v3: m.v3,
      }
    }
  } catch {
    manifestSummary = {}
  }

  return c.json({
    admin: toPublicUser(admin),
    stats,
    data_status: manifestSummary,
    server_time: nowShanghaiIso(),
  })
})

adminRoutes.get('/users', async (c) => {
  const users = await listUsersWithStats(c.env.DB)
  return c.json({ users })
})

adminRoutes.post('/users/:userId/reveal-password', requireSuperAdmin, async (c) => {
  const admin = c.get('user')!
  const userId = Number(c.req.param('userId'))
  const body = (await c.req.json().catch(() => ({}))) as { admin_password?: string }
  const freshAdmin = await getUserById(c.env.DB, admin.id)
  if (!freshAdmin || !(await verifyPassword(body.admin_password || '', freshAdmin.password_hash))) {
    return c.json({ detail: '管理员二次口令验证失败，无权查看用户密码' }, 403)
  }
  const target = await getUserById(c.env.DB, userId)
  if (!target) {
    return c.json({ detail: '用户不存在' }, 404)
  }
  const plain = await getUserPlainPassword(c.env, userId)
  await logAudit(c.env.DB, {
    action: 'admin_reveal_password',
    userId: admin.id,
    username: admin.username,
    detail: `Verified Level-1 identity to inspect password status for @${target.username}`,
    ip: c.get('clientIp'),
  })
  return c.json({ ok: true, password_plain: plain })
})

adminRoutes.post('/users', requireSuperAdmin, async (c) => {
  const admin = c.get('user')!
  const body = (await c.req.json().catch(() => ({}))) as {
    username?: string
    password?: string
    display_name?: string
    email?: string
    phone?: string
    role?: string
  }
  const uname = (body.username || '').trim()
  const pw = body.password || ''
  if (!USERNAME_RE.test(uname)) {
    return c.json({ detail: '用户名须为 3–32 位字母、数字、下划线或中文' }, 400)
  }
  if (pw.length < 6 || pw.length > 128) {
    return c.json({ detail: '密码长度须为 6–128 位' }, 400)
  }
  if (await getUserByUsername(c.env.DB, uname)) {
    return c.json({ detail: '该用户名已存在' }, 409)
  }
  const role: UserRole =
    body.role === 'user' || body.role === 'admin' || body.role === 'super_admin' ? body.role : 'admin'
  const created = await createUser(c.env, {
    username: uname,
    password: pw,
    displayName: (body.display_name || '').trim() || uname,
    email: (body.email || '').trim(),
    phone: (body.phone || '').trim(),
    role,
    ip: c.get('clientIp'),
  })
  await logAudit(c.env.DB, {
    action: 'admin_create_account',
    userId: admin.id,
    username: admin.username,
    detail: `Created account @${uname} role=${role}`,
    ip: c.get('clientIp'),
  })
  return c.json({ ok: true, user: toPublicUser(created) })
})

adminRoutes.get('/users/:userId/data', async (c) => {
  const admin = c.get('user')!
  const userId = Number(c.req.param('userId'))
  const target = await getUserById(c.env.DB, userId)
  if (!target) return c.json({ detail: '用户不存在' }, 404)
  const st = await getUserState(c.env, userId)
  await logAudit(c.env.DB, {
    action: 'admin_view_user_data',
    userId: admin.id,
    username: admin.username,
    detail: `Inspected encrypted state of user #${userId} (${target.username})`,
    ip: c.get('clientIp'),
  })
  return c.json({
    user: toPublicUser(target),
    has_state: st !== null,
    updated_at: st ? st.updated_at : null,
    counts: st ? st.counts : null,
    state: st ? st.state : null,
  })
})

adminRoutes.patch('/users/:userId', async (c) => {
  const admin = c.get('user')!
  const userId = Number(c.req.param('userId'))
  const body = (await c.req.json().catch(() => ({}))) as {
    is_active?: boolean
    new_password?: string
    display_name?: string
    email?: string
    phone?: string
    role?: string
  }

  const isSuper = admin.role === 'super_admin'
  if ((body.new_password || body.role) && !isSuper) {
    return c.json({ detail: '权限不足：二级管理员无法直接修改用户密码或变更管理员权限，请联系一级管理员' }, 403)
  }
  if (userId === admin.id) {
    if (body.is_active === false) {
      return c.json({ detail: '不能停用当前登录的管理员账号' }, 400)
    }
    if (body.role && body.role !== admin.role) {
      return c.json({ detail: '不能降级当前登录的一级管理员自身权限' }, 400)
    }
  }
  const target = await getUserById(c.env.DB, userId)
  if (!target) return c.json({ detail: '用户不存在' }, 404)
  if (!isSuper && (target.role === 'admin' || target.role === 'super_admin')) {
    return c.json({ detail: '权限不足：二级管理员无法操作其他管理员账号' }, 403)
  }

  const updated = await adminUpdateUser(c.env, {
    userId,
    isActive: body.is_active,
    newPassword: body.new_password,
    displayName: body.display_name,
    email: body.email,
    phone: body.phone,
    role: body.role,
    actorUsername: admin.username,
    ip: c.get('clientIp'),
  })
  if (!updated) return c.json({ detail: '用户不存在' }, 404)
  return c.json({ ok: true, user: toPublicUser(updated) })
})

// ---------------- One-Time Invite Code Management ----------------

adminRoutes.get('/invite-codes', async (c) => {
  const limit = Number(c.req.query('limit') || 100)
  const items = await listInviteCodes(c.env.DB, limit)
  return c.json({ items })
})

adminRoutes.post('/invite-codes', async (c) => {
  const admin = c.get('user')!
  const body = (await c.req.json().catch(() => ({}))) as {
    count?: number
    note?: string
    expires_days?: number | null
  }
  const created = await createInviteCodes(c.env.DB, {
    count: body.count ?? 1,
    note: body.note ?? '',
    expiresInDays: body.expires_days ?? null,
    createdBy: admin.username,
  })
  await logAudit(c.env.DB, {
    action: 'admin_create_invite_codes',
    userId: admin.id,
    username: admin.username,
    detail: `Generated ${created.length} invite code(s) note="${(body.note || '').slice(0, 40)}"`,
    ip: c.get('clientIp'),
  })
  return c.json({ ok: true, items: created })
})

adminRoutes.delete('/invite-codes/:code', async (c) => {
  const admin = c.get('user')!
  const code = decodeURIComponent(c.req.param('code'))
  const revoked = await revokeInviteCode(c.env.DB, code)
  if (!revoked) {
    return c.json({ detail: '邀请码不存在或已被使用，无法作废' }, 404)
  }
  await logAudit(c.env.DB, {
    action: 'admin_revoke_invite_code',
    userId: admin.id,
    username: admin.username,
    detail: `Revoked invite code ${code}`,
    ip: c.get('clientIp'),
  })
  return c.json({ ok: true })
})

// ---------------- Audit Logs, Push Config & Site Settings ----------------

adminRoutes.get('/audit-logs', async (c) => {
  const limit = Number(c.req.query('limit') || 100)
  return c.json({ logs: await listAuditLogs(c.env.DB, limit) })
})

adminRoutes.get('/push-config', async (c) => {
  return c.json({ config: await getPushConfig(c.env, 'global') })
})

adminRoutes.put('/push-config', async (c) => {
  const admin = c.get('user')!
  const body = (await c.req.json().catch(() => ({}))) as Record<string, unknown>
  const ts = await savePushConfig(c.env, body, 'global')
  await logAudit(c.env.DB, {
    action: 'admin_save_push_config',
    userId: admin.id,
    username: admin.username,
    detail: `Updated global push config (enabled=${Boolean(body.enabled)})`,
    ip: c.get('clientIp'),
  })
  return c.json({ ok: true, updated_at: ts })
})

adminRoutes.post('/push-test', async (c) => {
  const admin = c.get('user')!
  const cfg = await getPushConfig(c.env, 'global')
  const siteUrl = String(cfg.site_url || c.env.SITE_PUBLIC_URL || 'https://mirrorinfo.xyz').replace(/\/+$/, '')
  const text = `【镜信 MirrorBrief 测试推送】\n来自 Cloudflare Workers 边缘后端的连通性测试。\n访问工作台：${siteUrl}/`
  const results: Array<{ channel: string; status: string; error?: string }> = []

  const postWebhook = async (channel: string, url: string, payload: unknown) => {
    try {
      const r = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (r.ok) {
        await logPush(c.env.DB, { channel, status: 'ok', batchId: 'test', summary: 'Push test ok' })
        results.push({ channel, status: 'ok' })
      } else {
        const msg = `HTTP ${r.status}`
        await logPush(c.env.DB, { channel, status: 'error', batchId: 'test', errorMsg: msg })
        results.push({ channel, status: 'error', error: msg })
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      await logPush(c.env.DB, { channel, status: 'error', batchId: 'test', errorMsg: msg })
      results.push({ channel, status: 'error', error: msg })
    }
  }

  if (String(cfg.feishu_webhook || '').trim()) {
    await postWebhook('feishu', String(cfg.feishu_webhook).trim(), {
      msg_type: 'text',
      content: { text },
    })
  }
  if (String(cfg.wecom_webhook || '').trim()) {
    await postWebhook('wecom', String(cfg.wecom_webhook).trim(), {
      msgtype: 'text',
      text: { content: text },
    })
  }
  if (String(cfg.dingtalk_webhook || '').trim()) {
    await postWebhook('dingtalk', String(cfg.dingtalk_webhook).trim(), {
      msgtype: 'text',
      text: { content: text },
    })
  }
  if (String(cfg.telegram_bot_token || '').trim() && String(cfg.telegram_chat_id || '').trim()) {
    await postWebhook(
      'telegram',
      `https://api.telegram.org/bot${String(cfg.telegram_bot_token).trim()}/sendMessage`,
      {
        chat_id: String(cfg.telegram_chat_id).trim(),
        text,
        disable_web_page_preview: true,
      },
    )
  }

  await logAudit(c.env.DB, {
    action: 'admin_push_test',
    userId: admin.id,
    username: admin.username,
    detail: `Dispatched test push to ${results.length} channels`,
    ip: c.get('clientIp'),
  })
  return c.json({ ok: true, results })
})

adminRoutes.get('/push-logs', async (c) => {
  const limit = Number(c.req.query('limit') || 50)
  return c.json({ logs: await listPushLogs(c.env.DB, limit) })
})

adminRoutes.get('/site-settings', async (c) => {
  return c.json(await getSiteSettings(c.env.DB))
})

adminRoutes.put('/site-settings', async (c) => {
  const admin = c.get('user')!
  const body = (await c.req.json().catch(() => ({}))) as Record<string, unknown>
  const res = await saveSiteSettings(c.env.DB, body)
  await logAudit(c.env.DB, {
    action: 'admin_update_site_settings',
    userId: admin.id,
    username: admin.username,
    detail: `Updated settings keys=${Object.keys(body).sort().join(',')}`,
    ip: c.get('clientIp'),
  })
  return c.json({ ok: true, ...res })
})

// ---------------- Feedback Admin ----------------

adminRoutes.get('/feedback', async (c) => {
  const statusFilter = (c.req.query('status') || '').trim()
  const limit = Number(c.req.query('limit') || 150)
  return c.json({ items: await listFeedback(c.env.DB, { limit, statusFilter }) })
})

adminRoutes.patch('/feedback/:feedbackId', async (c) => {
  const admin = c.get('user')!
  const feedbackId = Number(c.req.param('feedbackId'))
  const body = (await c.req.json().catch(() => ({}))) as { status?: string; admin_reply?: string }
  const updated = await updateFeedback(c.env.DB, {
    feedbackId,
    status: body.status,
    adminReply: body.admin_reply,
    actorUsername: admin.username,
  })
  if (!updated) return c.json({ detail: '反馈记录不存在' }, 404)
  await logAudit(c.env.DB, {
    action: 'admin_reply_feedback',
    userId: admin.id,
    username: admin.username,
    detail: `Feedback #${feedbackId} status=${updated.status}`,
    ip: c.get('clientIp'),
  })
  return c.json({ ok: true, item: updated })
})

adminRoutes.delete('/feedback/:feedbackId', async (c) => {
  const admin = c.get('user')!
  const feedbackId = Number(c.req.param('feedbackId'))
  const deleted = await deleteFeedback(c.env.DB, feedbackId)
  if (!deleted) return c.json({ detail: '反馈记录不存在' }, 404)
  await logAudit(c.env.DB, {
    action: 'admin_delete_feedback',
    userId: admin.id,
    username: admin.username,
    detail: `Deleted feedback #${feedbackId}`,
    ip: c.get('clientIp'),
  })
  return c.json({ ok: true })
})

// ---------------- Editorial Content & Heavy Scheduling ----------------

adminRoutes.get('/content', async (c) => {
  const eventsOut: Array<Record<string, unknown>> = []
  for (const cat of ['finance', 'global', 'tech', 'general']) {
    try {
      const obj = await c.env.R2_DATA.get(`analysis_${cat}.json`)
      if (!obj) continue
      const doc = (await obj.json()) as { events?: Array<Record<string, unknown>> }
      for (const ev of doc.events || []) {
        if (!ev || typeof ev !== 'object') continue
        const title = String(ev.title || '')
        eventsOut.push({
          event_id: ev.event_id,
          title,
          title_fingerprint: titleFingerprint(title),
          category: ev.category || cat,
          severity_tier: ev.severity_tier || 'B',
          heavy_reason_tag: ev.heavy_reason_tag ?? null,
          importance: ev.importance || 'normal',
          published_at: ev.latest_reported_at || ev.first_reported_at || ev.published_at || null,
          source_count: Array.isArray(ev.sources) ? ev.sources.length : 0,
        })
      }
    } catch {
      continue
    }
  }

  const wireDoc = await getWireLatestDoc(c.env)
  const wireItems = Array.isArray(wireDoc.items) ? (wireDoc.items as Array<Record<string, unknown>>) : []
  const wireOut = wireItems.slice(0, 80).map((w) => {
    const title = String(w.title || '')
    return {
      id: w.id,
      title,
      title_fingerprint: titleFingerprint(title),
      category: w.category || 'general',
      severity_tier: w.severity_tier || 'B',
      heavy_reason_tag: w.heavy_reason_tag ?? null,
      importance: w.importance || 'normal',
      source_name: w.source_name || '',
      published_at: w.published_at || null,
    }
  })

  const overrides = await getEditorialOverridesDoc(c.env.DB)
  return c.json({ events: eventsOut, wire: wireOut, overrides })
})

adminRoutes.put('/editorial-overrides', async (c) => {
  const admin = c.get('user')!
  const body = (await c.req.json().catch(() => ({}))) as {
    key?: string
    target_type?: string
    event_id?: string
    title?: string
    title_fingerprint?: string
    severity_override?: string | null
    heavy_reason_tag?: string | null
    pinned?: boolean
    hidden?: boolean
  }
  if (!body.key || !body.key.trim()) {
    return c.json({ detail: '无效的置顶/标注主键' }, 400)
  }
  const saved = await upsertEditorialOverride(c.env.DB, {
    key: body.key,
    targetType: body.target_type || 'event',
    eventId: body.event_id || '',
    title: body.title || '',
    titleFingerprint: body.title_fingerprint,
    severityOverride: body.severity_override,
    heavyReasonTag: body.heavy_reason_tag,
    pinned: body.pinned,
    hidden: body.hidden,
    updatedBy: admin.username,
  })
  await logAudit(c.env.DB, {
    action: 'admin_editorial_override',
    userId: admin.id,
    username: admin.username,
    detail: `Override key=${body.key} sev=${body.severity_override || '-'} pinned=${Boolean(body.pinned)} hidden=${Boolean(body.hidden)}`,
    ip: c.get('clientIp'),
  })
  return c.json({ ok: true, overrides: saved })
})

adminRoutes.delete('/editorial-overrides/:key', async (c) => {
  const admin = c.get('user')!
  const key = decodeURIComponent(c.req.param('key'))
  const { removed, doc } = await deleteEditorialOverride(c.env.DB, key)
  if (removed) {
    await logAudit(c.env.DB, {
      action: 'admin_delete_editorial_override',
      userId: admin.id,
      username: admin.username,
      detail: `Cleared editorial override key=${key}`,
      ip: c.get('clientIp'),
    })
  }
  return c.json({ ok: true, overrides: doc })
})

adminRoutes.post('/sync-now', async (c) => {
  const admin = c.get('user')!
  const [wireRes, quotesDoc] = await Promise.all([
    runWireCron(c.env),
    fetchAndBuildMarketQuotes(c.env),
  ])

  const cache = getDefaultEdgeCache()
  if (cache) {
    try {
      await cache.delete(new Request(QUOTES_CACHE_KEY))
    } catch {
      // Ignore
    }
  }

  let smartBatchId = ''
  let rawBatchId = ''
  try {
    const manObj = await c.env.R2_DATA.get('data/manifest.json')
    if (manObj) {
      const m = (await manObj.json()) as Record<string, unknown>
      smartBatchId = String((m.smart as Record<string, unknown> | undefined)?.latest_batch_id || '')
      rawBatchId = String((m.raw as Record<string, unknown> | undefined)?.latest_batch_id || '')
    }
  } catch {
    // Keep empty
  }

  const wireDoc = await getWireLatestDoc(c.env)
  const wireTotal = Array.isArray(wireDoc.items) ? wireDoc.items.length : 0
  const quotesCount = quotesDoc.quotes ? Object.keys(quotesDoc.quotes).length : 0

  await logAudit(c.env.DB, {
    action: 'admin_manual_sync',
    userId: admin.id,
    username: admin.username,
    detail: `边缘同步完成：快讯新增/刷新 ${wireRes.inserted} 条（当前 ${wireTotal} 条），行情 ${quotesCount} 项`,
    ip: c.get('clientIp'),
  })

  return c.json({
    ok: true,
    base: c.env.DATA_PUBLIC_BASE_URL || 'https://data.mirrorinfo.xyz',
    updated: wireRes.inserted,
    failed: [],
    forced: true,
    smart_batch_id: smartBatchId,
    raw_batch_id: rawBatchId,
    wire_updated_at: wireRes.updated_at,
    wire_total: wireTotal,
    quotes_count: quotesCount,
  })
})
