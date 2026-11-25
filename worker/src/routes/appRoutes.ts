import { Hono } from 'hono'
import { requireUser } from '../authMiddleware'
import { nowShanghaiIso } from '../crypto'
import { getSiteSettings, getUserState, logAudit, sanitizeAvatarValue, saveUserState } from '../db'
import {
  ALLOWED_REACTION_KEYS,
  countRecentFeedback,
  createWaitlistEntry,
  getEditorialOverridesDoc,
  getPredictionCrowdStats,
  getReactionsBatch,
  isValidReactionKey,
  isValidReactionTargetType,
  listUserFeedback,
  saveFeedback,
  upsertContentReaction,
  upsertPredictionVote,
} from '../dbExtras'
import { handleQaAsk, type QaRequestBody } from '../qa'
import { QUOTES_CACHE_KEY, fetchAndBuildMarketQuotes, getDefaultEdgeCache } from '../quotes'
import { checkAndHitRateLimit } from '../rateLimit'
import type { Env, HonoVariables } from '../types'
import { AI_PROGRESS_CACHE_KEY, WIRE_CACHE_KEY, getWireLatestDoc } from '../wireCron'

export const publicAndCoreRoutes = new Hono<{ Bindings: Env; Variables: HonoVariables }>()

publicAndCoreRoutes.get('/health', (c) => {
  return c.json({
    status: 'ok',
    version: '6.0-cloudflare',
    access_mode: c.get('accessMode'),
    server_time: nowShanghaiIso(),
  })
})

publicAndCoreRoutes.get('/public/access-config', (c) => {
  const accessMode = c.get('accessMode')
  return c.json(
    {
      access_mode: accessMode,
      login_required: accessMode === 'private_gate',
      invite_required: accessMode !== 'public',
      site_url: c.env.SITE_PUBLIC_URL || 'https://mirrorinfo.xyz',
      data_base_url: c.env.DATA_PUBLIC_BASE_URL || 'https://data.mirrorinfo.xyz',
    },
    200,
    { 'Cache-Control': 'no-store' },
  )
})

publicAndCoreRoutes.get('/public/settings', async (c) => {
  const settings = await getSiteSettings(c.env.DB, c.env.SITE_ACCESS_MODE)
  return c.json(settings, 200, { 'Cache-Control': 'no-store' })
})

publicAndCoreRoutes.get('/public/overrides', async (c) => {
  const doc = await getEditorialOverridesDoc(c.env.DB)
  return c.json(doc, 200, { 'Cache-Control': 'no-store' })
})

// ---------------- Market Quotes (45s Edge Cache + R2 Fallback) ----------------

function httpCacheControl(
  c: { get: (k: 'accessMode') => 'private_gate' | 'invite_only' | 'public' },
  publicDirective: string,
): string {
  return c.get('accessMode') === 'private_gate' ? 'private, no-store' : publicDirective
}

publicAndCoreRoutes.get('/market/quotes', async (c) => {
  const cache = getDefaultEdgeCache()
  const cacheReq = new Request(QUOTES_CACHE_KEY)

  if (cache) {
    try {
      const hit = await cache.match(cacheReq)
      if (hit) {
        return new Response(hit.body, {
          status: 200,
          headers: {
            'Content-Type': 'application/json; charset=utf-8',
            'Cache-Control': httpCacheControl(c, 'public, max-age=45'),
            'X-MirrorBrief-Cache': 'HIT',
          },
        })
      }
    } catch {
      // Cache read failure ignored
    }
  }

  const doc = await fetchAndBuildMarketQuotes(c.env)
  const bodyStr = JSON.stringify(doc)

  if (cache && doc.status !== 'unavailable') {
    const cacheResp = new Response(bodyStr, {
      status: 200,
      headers: {
        'Content-Type': 'application/json; charset=utf-8',
        'Cache-Control': doc.status === 'ok' ? 'public, max-age=45' : 'public, max-age=15',
      },
    })
    const execCtx = c.executionCtx
    if (execCtx && typeof execCtx.waitUntil === 'function') {
      execCtx.waitUntil(cache.put(cacheReq, cacheResp.clone()))
    } else {
      await cache.put(cacheReq, cacheResp.clone())
    }
  }

  return new Response(bodyStr, {
    status: 200,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': httpCacheControl(c, 'public, max-age=45'),
      'X-MirrorBrief-Cache': 'MISS',
    },
  })
})

// ---------------- 7x24 Live Wire (30s Edge Cache replacing SSE) ----------------

publicAndCoreRoutes.get('/wire/latest', async (c) => {
  const cache = getDefaultEdgeCache()
  const cacheReq = new Request(WIRE_CACHE_KEY)

  if (cache) {
    try {
      const hit = await cache.match(cacheReq)
      if (hit) {
        return new Response(hit.body, {
          status: 200,
          headers: {
            'Content-Type': 'application/json; charset=utf-8',
            'Cache-Control': httpCacheControl(c, 'public, max-age=30'),
            'X-MirrorBrief-Cache': 'HIT',
          },
        })
      }
    } catch {
      // Ignore cache miss error
    }
  }

  const doc = await getWireLatestDoc(c.env)
  const bodyStr = JSON.stringify(doc)

  if (cache && doc.status === 'ok') {
    const cacheResp = new Response(bodyStr, {
      status: 200,
      headers: {
        'Content-Type': 'application/json; charset=utf-8',
        'Cache-Control': 'public, max-age=30',
      },
    })
    const execCtx = c.executionCtx
    if (execCtx && typeof execCtx.waitUntil === 'function') {
      execCtx.waitUntil(cache.put(cacheReq, cacheResp.clone()))
    } else {
      await cache.put(cacheReq, cacheResp.clone())
    }
  }

  return new Response(bodyStr, {
    status: 200,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': httpCacheControl(c, 'public, max-age=30'),
      'X-MirrorBrief-Cache': 'MISS',
    },
  })
})

publicAndCoreRoutes.get('/ai-progress/latest', async (c) => {
  const cache = getDefaultEdgeCache()
  const cacheReq = new Request(AI_PROGRESS_CACHE_KEY)

  if (cache) {
    try {
      const hit = await cache.match(cacheReq)
      if (hit) {
        return new Response(hit.body, {
          status: 200,
          headers: {
            'Content-Type': 'application/json; charset=utf-8',
            'Cache-Control': httpCacheControl(c, 'public, max-age=60'),
            'X-MirrorBrief-Cache': 'HIT',
          },
        })
      }
    } catch {
      // Ignore
    }
  }

  const r2Obj = await c.env.R2_DATA.get('data/ai_progress.json')
  if (!r2Obj) {
    return c.json({
      schema_version: '4.0',
      generated_at: '',
      batch_id: '',
      weekly_digest: { period_label: '', summary: '', highlights: [] },
      companies: [],
      timeline: [],
    })
  }

  const rawText = await r2Obj.text()
  if (cache) {
    const cacheResp = new Response(rawText, {
      status: 200,
      headers: {
        'Content-Type': 'application/json; charset=utf-8',
        'Cache-Control': 'public, max-age=60',
      },
    })
    const execCtx = c.executionCtx
    if (execCtx && typeof execCtx.waitUntil === 'function') {
      execCtx.waitUntil(cache.put(cacheReq, cacheResp.clone()))
    } else {
      await cache.put(cacheReq, cacheResp.clone())
    }
  }

  return new Response(rawText, {
    status: 200,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': httpCacheControl(c, 'public, max-age=60'),
      'X-MirrorBrief-Cache': 'MISS',
    },
  })
})

// ---------------- User Encrypted Cloud Sync State ----------------

publicAndCoreRoutes.get('/user/state', requireUser, async (c) => {
  const user = c.get('user')!
  const st = await getUserState(c.env, user.id)
  if (!st) {
    return c.json({ has_state: false, state: null, updated_at: null, counts: null })
  }
  return c.json({ has_state: true, ...st })
})

publicAndCoreRoutes.put('/user/state', requireUser, async (c) => {
  const user = c.get('user')!
  const body = (await c.req.json().catch(() => null)) as { state?: Record<string, unknown> } | null
  if (!body || !body.state || typeof body.state !== 'object') {
    return c.json({ detail: '无效的云端同步载荷' }, 400)
  }

  const rawBytes = new TextEncoder().encode(JSON.stringify(body.state)).length
  if (rawBytes > 2 * 1024 * 1024) {
    return c.json({ detail: '同步数据包超过 2 MB 上限' }, 413)
  }

  const sanitized: Record<string, unknown> = { ...body.state }
  delete sanitized.ai_client_config
  if ('avatar' in sanitized) {
    sanitized.avatar = sanitizeAvatarValue(sanitized.avatar)
  }

  const res = await saveUserState(c.env, { userId: user.id, payload: sanitized })
  await logAudit(c.env.DB, {
    action: 'sync_push',
    userId: user.id,
    username: user.username,
    detail: `Synced ${rawBytes}B AES-256-GCM state`,
    ip: c.get('clientIp'),
  })
  return c.json({
    ok: true,
    ...res,
    avatar: 'avatar' in sanitized ? sanitized.avatar : user.avatar || '',
  })
})

// ---------------- Predictions Crowd Consensus ----------------

publicAndCoreRoutes.get('/predictions/crowd', async (c) => {
  const user = c.get('user')
  const settings = await getSiteSettings(c.env.DB, c.env.SITE_ACCESS_MODE)
  const minUnlock = Math.max(1, Math.min(50, Number(settings.crowd_vote_min_unlock ?? 3)))
  const stats = await getPredictionCrowdStats(c.env.DB, {
    userId: user ? user.id : null,
    minVotes: minUnlock,
  })
  return c.json(stats, 200, { 'Cache-Control': 'no-store' })
})

publicAndCoreRoutes.put('/predictions/:predictionId/vote', requireUser, async (c) => {
  const user = c.get('user')!
  const pid = decodeURIComponent(c.req.param('predictionId') || '').trim()
  if (!pid || pid.length > 120) {
    return c.json({ detail: '无效的预测条目 ID' }, 400)
  }
  const body = (await c.req.json().catch(() => ({}))) as { prob_pct?: number }
  const prob = Number(body.prob_pct)
  if (!Number.isFinite(prob) || prob < 5 || prob > 95) {
    return c.json({ detail: '概率值须在 5 至 95 之间' }, 422)
  }
  const settings = await getSiteSettings(c.env.DB, c.env.SITE_ACCESS_MODE)
  const minUnlock = Math.max(1, Math.min(50, Number(settings.crowd_vote_min_unlock ?? 3)))
  await upsertPredictionVote(c.env.DB, { predictionId: pid, userId: user.id, probPct: prob })
  const stats = await getPredictionCrowdStats(c.env.DB, { userId: user.id, minVotes: minUnlock })
  return c.json(
    {
      ok: true,
      min_votes: stats.min_votes,
      item: stats.items[pid] ?? null,
      items: stats.items,
    },
    200,
    { 'Cache-Control': 'no-store' },
  )
})

// ---------------- Feedback ----------------

publicAndCoreRoutes.post('/feedback', async (c) => {
  const settings = await getSiteSettings(c.env.DB, c.env.SITE_ACCESS_MODE)
  if (!settings.feedback_enabled) {
    return c.json({ detail: '意见反馈通道当前维护中，请通过页面公布的联系方式直接联系团队' }, 403)
  }
  const body = (await c.req.json().catch(() => ({}))) as {
    content?: string
    contact?: string
    category?: string
    page_url?: string
  }
  const text = (body.content || '').trim()
  if (text.length < 4) {
    return c.json({ detail: '请至少填写 4 个字的反馈或问题描述' }, 400)
  }

  const user = c.get('user')
  const ip = c.get('clientIp')
  const devRaw = (c.req.header('x-device-id') || '').trim().slice(0, 80)
  const limitN = Number(settings.feedback_daily_limit ?? 5)
  const recentN = await countRecentFeedback(c.env.DB, {
    ip,
    userId: user ? user.id : null,
    deviceId: devRaw,
    hours: 24,
  })
  if (recentN >= limitN) {
    return c.json({ detail: `24 小时内最多提交 ${limitN} 条反馈，感谢您的理解与支持` }, 429)
  }

  const saved = await saveFeedback(c.env.DB, {
    content: text,
    contact: (body.contact || '').trim(),
    category: (body.category || 'suggestion').trim() || 'suggestion',
    pageUrl: (body.page_url || '').trim(),
    ip,
    userId: user ? user.id : null,
    username: user ? user.username : '',
    deviceId: devRaw,
  })
  await logAudit(c.env.DB, {
    action: 'user_feedback',
    userId: user ? user.id : null,
    username: (user?.username || body.contact || 'guest').slice(0, 32),
    detail: text.slice(0, 120),
    ip,
  })
  return c.json({ ok: true, ...saved })
})

publicAndCoreRoutes.get('/feedback/mine', async (c) => {
  const user = c.get('user')
  const devRaw = (c.req.header('x-device-id') || '').trim().slice(0, 80)
  const items = await listUserFeedback(c.env.DB, {
    userId: user ? user.id : null,
    deviceId: devRaw,
  })
  return c.json({ items })
})

// ---------------- Waitlist Application (Stage 3/4) ----------------

publicAndCoreRoutes.post('/public/waitlist', async (c) => {
  const settings = await getSiteSettings(c.env.DB, c.env.SITE_ACCESS_MODE)
  if (!settings.invite_waitlist_enabled) {
    return c.json({ detail: '当前未开放候补席位申请，请联系邀请人或管理员' }, 403)
  }
  const ip = c.get('clientIp')
  const rl = await checkAndHitRateLimit(c.env.DB, {
    scope: 'waitlist_submit',
    key: ip,
    limit: 5,
    windowSec: 3600,
  })
  if (!rl.allowed) {
    return c.json({ detail: '提交过于频繁，请 1 小时后再试' }, 429)
  }
  const body = (await c.req.json().catch(() => ({}))) as {
    contact?: string
    focus_areas?: string | string[]
    note?: string
  }
  const contact = (body.contact || '').trim()
  if (contact.length < 3 || contact.length > 160) {
    return c.json({ detail: '请填写有效的联系方式（邮箱、手机号或微信号，至少 3 个字符）' }, 400)
  }
  const focusAreas = Array.isArray(body.focus_areas)
    ? body.focus_areas.map((s) => String(s || '').trim()).filter(Boolean).join('、')
    : String(body.focus_areas || '').trim()
  const row = await createWaitlistEntry(c.env.DB, {
    contact,
    focusAreas,
    note: String(body.note || '').trim(),
    ip,
  })
  await logAudit(c.env.DB, {
    action: 'public_waitlist_submit',
    username: contact.slice(0, 48),
    detail: `Waitlist #${row.id} focus=${focusAreas.slice(0, 80)}`,
    ip,
  })
  return c.json({ ok: true, id: row.id, status: row.status })
})

// ---------------- Structured 1-Click Reactions (Zero Open-Text UGC) ----------------

function resolveReactionVoterKey(c: {
  get: ((k: 'user') => { id: number } | null) & ((k: 'deviceId') => string) & ((k: 'clientIp') => string)
}): string {
  const user = c.get('user')
  if (user) return `u:${user.id}`
  const dev = (c.get('deviceId') || '').trim()
  if (dev && dev !== 'anonymous') return `dev:${dev.slice(0, 80)}`
  return `ip:${(c.get('clientIp') || 'unknown').slice(0, 64)}`
}

publicAndCoreRoutes.get('/reactions/batch', async (c) => {
  const rawType = (c.req.query('target_type') || '').trim()
  if (!isValidReactionTargetType(rawType)) {
    return c.json({ detail: '无效的 target_type，仅支持 event / finance / prediction' }, 400)
  }
  const idsRaw = (c.req.query('ids') || '').trim()
  const ids = idsRaw
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
  const voterKey = resolveReactionVoterKey(c)
  const items = await getReactionsBatch(c.env.DB, {
    targetType: rawType,
    ids,
    voterKey,
  })
  return c.json(
    {
      target_type: rawType,
      allowed_keys: ALLOWED_REACTION_KEYS[rawType],
      items,
    },
    200,
    { 'Cache-Control': 'no-store' },
  )
})

publicAndCoreRoutes.post('/reactions', async (c) => {
  const body = (await c.req.json().catch(() => ({}))) as {
    target_type?: string
    target_id?: string
    reaction_key?: string
  }
  const rawType = (body.target_type || '').trim()
  const targetId = (body.target_id || '').trim()
  const reactionKey = (body.reaction_key || '').trim()
  if (!isValidReactionTargetType(rawType)) {
    return c.json({ detail: '无效的 target_type，仅支持 event / finance / prediction' }, 400)
  }
  if (!targetId || targetId.length > 120) {
    return c.json({ detail: '无效的 target_id' }, 400)
  }
  if (!isValidReactionKey(rawType, reactionKey)) {
    return c.json({ detail: `无效的表态键值 ${reactionKey}` }, 400)
  }
  const voterKey = resolveReactionVoterKey(c)
  const item = await upsertContentReaction(c.env.DB, {
    targetType: rawType,
    targetId,
    voterKey,
    reactionKey,
  })
  return c.json({ ok: true, item }, 200, { 'Cache-Control': 'no-store' })
})

// ---------------- Evidence Q&A ----------------

publicAndCoreRoutes.post('/qa/ask', async (c) => {
  const user = c.get('user')
  const body = (await c.req.json().catch(() => ({}))) as QaRequestBody
  const result = await handleQaAsk(c.env, body, {
    clientIp: c.get('clientIp'),
    userId: user ? user.id : null,
    deviceId: c.get('deviceId'),
    extraQaQuota: user ? Number(user.extra_qa_quota ?? 0) : 0,
  })
  return c.json(result.payload, result.status as 200 | 400 | 429)
})
