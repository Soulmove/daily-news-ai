import { Hono } from 'hono'
import { getEffectiveAccessMode } from './db'
import { findPredictionDeadline } from './predictionArena'
import type { Env, HonoVariables } from './types'

export const shareMetaRoutes = new Hono<{ Bindings: Env; Variables: HonoVariables }>()

const CRAWLER_UA_RE =
  /(twitterbot|facebookexternalhit|facebot|telegrambot|slackbot|whatsapp|linkedinbot|discordbot|lark|feishu|micromessenger|dingtalk|qq\/|bingbot|googlebot|baiduspider|curl\/|wget\/)/i

function escapeHtml(raw: string): string {
  return String(raw || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function getSiteOrigin(env: Env): string {
  return String(env.SITE_PUBLIC_URL || 'https://mirrorinfo.xyz').replace(/\/+$/, '')
}

async function findEventSummaryForShare(
  env: Env,
  eventId: string,
): Promise<{ title: string; summary: string; sourceCount: number } | null> {
  for (const cat of ['finance', 'global', 'tech', 'general']) {
    try {
      const obj = await env.R2_DATA.get(`analysis_${cat}.json`)
      if (!obj) continue
      const doc = (await obj.json()) as { events?: Array<Record<string, unknown>> }
      for (const ev of doc.events || []) {
        if (String(ev.event_id || '') === eventId) {
          const sources = Array.isArray(ev.sources) ? ev.sources : []
          const summaryRaw = String(ev.fact_summary || ev.ai_analysis || ev.summary || '').trim()
          return {
            title: String(ev.title_zh || ev.title || '镜信核验事件简报'),
            summary: summaryRaw.slice(0, 140),
            sourceCount: sources.length,
          }
        }
      }
    } catch {
      continue
    }
  }
  return null
}

export async function resolveShareMeta(
  env: Env,
  opts: {
    type: 'pred' | 'event'
    id: string
    p?: string
    ref?: string
  },
): Promise<{ title: string; description: string; target_url: string; found: boolean }> {
  const siteUrl = getSiteOrigin(env)
  const accessMode = await getEffectiveAccessMode(env.DB, env.SITE_ACCESS_MODE)
  const id = opts.id.trim().slice(0, 120)

  if (opts.type === 'pred') {
    const dest = new URL(`${siteUrl}/`)
    dest.searchParams.set('tab', 'calendar')
    dest.searchParams.set('pred', id)
    if (opts.p && Number.isFinite(Number(opts.p))) {
      dest.searchParams.set('p', String(Math.round(Number(opts.p))))
    }
    if (opts.ref) {
      dest.searchParams.set('ref', opts.ref.slice(0, 48))
    }

    if (accessMode === 'private_gate') {
      return {
        title: '镜信 MirrorBrief · 好友发起前瞻预测 PK',
        description: '登录镜信工作台参与可验证概率预判，查看实时人类共识与 AI 校准对比。',
        target_url: dest.toString(),
        found: false,
      }
    }

    const info = await findPredictionDeadline(env, id)
    if (info.found && info.title) {
      const pVal = opts.p && Number.isFinite(Number(opts.p)) ? Math.round(Number(opts.p)) : null
      const prefix = pVal !== null ? `我押 ${pVal}% | ` : ''
      const title = `${prefix}${info.title} · 镜信前瞻预测 PK`
      const desc = `${info.question || info.title}（镜信 AI 基准 ${Math.round(info.ai_prob_pct)}%${info.win_rule ? ` · 判定：${info.win_rule.slice(0, 60)}` : ''}）`
      return {
        title,
        description: desc,
        target_url: dest.toString(),
        found: true,
      }
    }

    return {
      title: '镜信 MirrorBrief · 前瞻预测对赌 PK',
      description: '点击参与概率推演并生成你的专属校验战绩。',
      target_url: dest.toString(),
      found: false,
    }
  }

  const dest = new URL(`${siteUrl}/`)
  dest.searchParams.set('event', id)

  if (accessMode === 'private_gate') {
    return {
      title: '镜信 MirrorBrief · 多源核验重大事件简报',
      description: '登录镜信查看多源交叉核验事实、三视角拆解与市场传导推演。',
      target_url: dest.toString(),
      found: false,
    }
  }

  const ev = await findEventSummaryForShare(env, id)
  if (ev) {
    return {
      title: `${ev.title} · 镜信多源核验简报`,
      description: `${ev.sourceCount} 路信源核验 · ${ev.summary || '点击查看官方定调 / 顺风逻辑 / 风险质疑三视角拆解。'}`,
      target_url: dest.toString(),
      found: true,
    }
  }

  return {
    title: '镜信 MirrorBrief · 一镜照见全球真实大事',
    description: '75+ 一手信源交叉核验 · 免费 AI 证据问答 · 持仓宏观传导推演',
    target_url: dest.toString(),
    found: false,
  }
}

function renderOgHtml(meta: { title: string; description: string; target_url: string; share_url: string }): string {
  const safeTitle = escapeHtml(meta.title)
  const safeDesc = escapeHtml(meta.description)
  const safeTarget = escapeHtml(meta.target_url)
  const safeShareUrl = escapeHtml(meta.share_url)
  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>${safeTitle}</title>
  <meta name="description" content="${safeDesc}" />
  <meta property="og:site_name" content="镜信 MirrorBrief" />
  <meta property="og:type" content="article" />
  <meta property="og:title" content="${safeTitle}" />
  <meta property="og:description" content="${safeDesc}" />
  <meta property="og:url" content="${safeShareUrl}" />
  <meta name="twitter:card" content="summary" />
  <meta name="twitter:title" content="${safeTitle}" />
  <meta name="twitter:description" content="${safeDesc}" />
  <meta http-equiv="refresh" content="0;url=${safeTarget}" />
</head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'PingFang SC',sans-serif;background:#0B1220;color:#F8FAFC;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;padding:24px;">
  <main style="max-width:520px;width:100%;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.12);border-radius:18px;padding:24px;">
    <div style="font-size:12px;font-weight:700;color:#60A5FA;letter-spacing:0.06em;">镜信 MIRRORBRIEF</div>
    <h1 style="font-size:18px;line-height:1.45;margin:10px 0 8px;">${safeTitle}</h1>
    <p style="font-size:14px;line-height:1.6;color:#CBD5E1;margin:0 0 18px;">${safeDesc}</p>
    <a href="${safeTarget}" style="display:inline-block;padding:10px 18px;border-radius:12px;background:#007AFF;color:#FFFFFF;text-decoration:none;font-weight:600;font-size:14px;">立即前往查看详情</a>
  </main>
  <script>try{window.location.replace(${JSON.stringify(meta.target_url)});}catch(e){}</script>
</body>
</html>`
}

async function handleShareRedirect(
  c: {
    req: {
      param: (name: string) => string
      query: (name: string) => string | undefined
      header: (name: string) => string | undefined
      url: string
    }
    env: Env
  },
  type: 'pred' | 'event',
) {
  const id = decodeURIComponent(c.req.param('id') || '').trim()
  if (!id) {
    return Response.redirect(`${getSiteOrigin(c.env)}/`, 302)
  }
  const p = c.req.query('p')
  const ref = c.req.query('ref')
  const meta = await resolveShareMeta(c.env, { type, id, p, ref })
  const ua = c.req.header('user-agent') || ''
  const previewFlag = c.req.query('preview') === '1'
  if (previewFlag || CRAWLER_UA_RE.test(ua)) {
    const html = renderOgHtml({
      ...meta,
      share_url: c.req.url,
    })
    return new Response(html, {
      status: 200,
      headers: {
        'Content-Type': 'text/html; charset=utf-8',
        'Cache-Control': 'public, max-age=120',
      },
    })
  }
  return Response.redirect(meta.target_url, 302)
}

shareMetaRoutes.get('/pred/:id', (c) => handleShareRedirect(c, 'pred'))
shareMetaRoutes.get('/event/:id', (c) => handleShareRedirect(c, 'event'))
