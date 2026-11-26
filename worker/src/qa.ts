import { recordWorkerAiUsageEvent } from './aiTelemetry'
import { sha256Hex } from './crypto'
import { getSiteSettings } from './db'
import { checkAndHitRateLimit } from './rateLimit'
import type { Env } from './types'

const ALIAS_GROUPS: string[][] = [
  ['nvda', 'nvidia', '英伟达', '黄仁勋'],
  ['tsm', 'tsmc', '台积电'],
  ['smic', '中芯国际', '00981'],
  ['amd', '超威'],
  ['intc', 'intel', '英特尔'],
  ['fomc', 'fed', '美联储', '鲍威尔', '加息', '降息', '利率'],
  ['gold', '黄金', '金价', '518880'],
  ['oil', '原油', '油价', '布伦特', '霍尔木兹'],
  ['iran', '伊朗', '美伊', '中东'],
  ['ukraine', '俄乌', '俄罗斯', '乌克兰', '和平协议', '波兰'],
  ['apec', 'trump', '特朗普', '中美', '关税'],
  ['anthropic', 'claude', 'ipo'],
  ['openai', 'gpt', 'chatgpt'],
  ['gemini', 'google', 'deepmind'],
  ['qwen', '阿里', '通义'],
  ['deepseek', 'kimi', '混元', 'workbuddy', 'tencent', '腾讯'],
]

function cleanQaText(val: unknown): string {
  let s = String(val || '').trim()
  if (!s) return ''
  s = s.replace(/[（(]\s*[、,，]?\s*(?:原始素材多?)?仅含?标题\s*[)）]/g, '')
  s = s.replace(/[、,，]?\s*(?:原始素材多?)?仅含?标题(?:[，,。；:\s]*(?:细节待查原文|具体[^。；;]*))?[。.]?/g, '')
  s = s.replace(/\[?R\d{2,4}\]?\s*[:：]?\s*/g, '')
  return s.replace(/\s{2,}/g, ' ').replace(/^[ 、,，]+|[ 、,，]+$/g, '')
}

async function readCompactR2Json<T>(env: Env, key: string): Promise<T | null> {
  try {
    const obj = await env.R2_DATA.get(key)
    if (!obj) return null
    return (await obj.json()) as T
  } catch {
    return null
  }
}

export interface QaRequestBody {
  question?: string
  target_type?: string | null
  target_id?: string | null
  lang?: string
  history?: Array<{ role?: string; content?: string }>
}

export async function handleQaAsk(
  env: Env,
  body: QaRequestBody,
  opts: { clientIp: string; userId?: number | null; deviceId?: string; extraQaQuota?: number },
): Promise<{ status: number; payload: Record<string, unknown> }> {
  const qRaw = (body.question || '').trim()
  if (qRaw.length < 2) {
    return { status: 400, payload: { detail: '请至少输入 2 个字的检索或问答问题' } }
  }

  const settings = await getSiteSettings(env.DB, env.SITE_ACCESS_MODE)
  const guestLimit = Math.max(0, Math.min(100, Number(settings.guest_qa_daily_limit ?? 5)))
  const authBaseLimit = Math.max(1, Math.min(500, Number(settings.auth_qa_daily_limit ?? 30)))
  const extraBonus = Math.max(0, Math.round(Number(opts.extraQaQuota ?? 0)))
  const dailyLimit = opts.userId ? authBaseLimit + extraBonus : guestLimit

  if (!opts.userId && dailyLimit <= 0) {
    return {
      status: 429,
      payload: {
        detail: '当前未开放游客免费 AI 证据问答，请登录后使用',
        quota_exhausted: true,
        remaining_quota: 0,
        daily_limit: 0,
      },
    }
  }

  const cleanDev = (opts.deviceId || '').trim().slice(0, 80)
  const rlKey = opts.userId
    ? `uid:${opts.userId}`
    : cleanDev
      ? `dev:${cleanDev}`
      : `ip:${opts.clientIp}`
  const rl = await checkAndHitRateLimit(env.DB, {
    scope: 'qa_ask_daily',
    key: rlKey,
    limit: dailyLimit,
    windowSec: 86_400,
  })
  if (!rl.allowed) {
    return {
      status: 429,
      payload: {
        detail: opts.userId
          ? `今日 ${dailyLimit} 次 AI 证据问答额度已用完，请明日再试`
          : `游客每日免费 ${dailyLimit} 次 AI 证据问答额度已用完，登录立即扩容`,
        quota_exhausted: true,
        remaining_quota: 0,
        daily_limit: dailyLimit,
      },
    }
  }

  const lang = String(body.lang || '').toLowerCase().startsWith('en') ? 'en' : 'zh'
  const [manifestDoc, finCat, glbCat, techCat, genCat, impactsDoc, calDoc] = await Promise.all([
    readCompactR2Json<Record<string, unknown>>(env, 'data/manifest.json'),
    readCompactR2Json<Record<string, unknown>>(env, 'analysis_finance.json'),
    readCompactR2Json<Record<string, unknown>>(env, 'analysis_global.json'),
    readCompactR2Json<Record<string, unknown>>(env, 'analysis_tech.json'),
    readCompactR2Json<Record<string, unknown>>(env, 'analysis_general.json'),
    readCompactR2Json<Record<string, unknown>>(env, 'data/finance_impact.json'),
    readCompactR2Json<Record<string, unknown>>(env, 'data/calendar.json'),
  ])

  const smartInfo = (manifestDoc?.smart as Record<string, unknown> | undefined) || {}
  let cutoff = String(
    manifestDoc?.generated_at ||
      smartInfo.generated_at ||
      manifestDoc?.input_cutoff_at ||
      smartInfo.input_cutoff_at ||
      '',
  )

  const eventsPool: Array<Record<string, unknown>> = []
  for (const cdoc of [finCat, glbCat, techCat, genCat]) {
    if (!cdoc || typeof cdoc !== 'object') continue
    if (!cutoff) {
      cutoff = String(cdoc.input_cutoff_at || cdoc.generated_at || '')
    }
    const evs = Array.isArray(cdoc.events) ? cdoc.events : []
    for (const ev of evs) {
      if (ev && typeof ev === 'object') eventsPool.push(ev as Record<string, unknown>)
    }
  }

  const impactMap =
    (impactsDoc?.event_impact_map as Record<string, Record<string, unknown>> | undefined) || {}
  const calEvents = (Array.isArray(calDoc?.events) ? calDoc.events : []) as Array<Record<string, unknown>>

  const qLow = qRaw.toLowerCase()
  const expanded = new Set<string>(qLow.match(/[a-z0-9]{2,}|[\u4e00-\u9fff]{2,}/g) || [])
  for (let i = 0; i < qLow.length - 1; i++) {
    if (/[\u4e00-\u9fff]/.test(qLow[i]) && /[\u4e00-\u9fff]/.test(qLow[i + 1])) {
      expanded.add(qLow.slice(i, i + 2))
    }
  }
  for (const grp of ALIAS_GROUPS) {
    if (grp.some((g) => qLow.includes(g) || expanded.has(g))) {
      for (const g of grp) expanded.add(g)
    }
  }

  const scored: Array<{ score: number; ev: Record<string, unknown> }> = []
  for (const ev of eventsPool) {
    const sources = Array.isArray(ev.sources) ? ev.sources : []
    if (sources.length === 0) continue
    const eid = String(ev.event_id || '')
    const entities = Array.isArray(ev.entities) ? ev.entities.join(' ') : ''
    const hay = `${ev.title || ''} ${ev.title_en || ''} ${ev.fact_summary || ''} ${ev.ai_analysis || ''} ${entities}`.toLowerCase()
    let sc = 0
    if (body.target_id && eid === body.target_id) sc += 120
    if (body.target_id && String(ev.storyline_id || '') === body.target_id) sc += 65
    for (const tok of expanded) {
      if (tok.length >= 2 && hay.includes(tok)) sc += tok.length >= 3 ? 10 : 5
    }
    if (sc > 0) {
      sc += Math.min(15, Number(ev.independent_publisher_count || sources.length || 1))
      scored.push({ score: sc, ev })
    }
  }
  scored.sort((a, b) => b.score - a.score)
  let topEvs = scored.slice(0, 6).map((s) => s.ev)
  if (topEvs.length === 0) {
    topEvs = eventsPool.filter((e) => Array.isArray(e.sources) && e.sources.length > 0).slice(0, 4)
  }

  const matchedCal = calEvents
    .filter((c) => {
      const hay = `${c.title || ''} ${c.watch_variable || ''}`.toLowerCase()
      for (const tok of expanded) {
        if (hay.includes(tok)) return true
      }
      return false
    })
    .slice(0, 3)

  const evidenceUrls: Array<{ label: string; url: string }> = []
  const seenUrls = new Set<string>()
  for (const ev of topEvs) {
    const sources = Array.isArray(ev.sources) ? (ev.sources as Array<Record<string, unknown>>) : []
    for (const src of sources.slice(0, 2)) {
      const u = String(src.url || '').trim()
      if (u && !seenUrls.has(u)) {
        seenUrls.add(u)
        evidenceUrls.push({
          label: `${src.source_name || 'Source'} · ${String(ev.title || '').slice(0, 36)}`,
          url: u,
        })
      }
    }
  }

  // Server-controlled Gemini REST API synthesis when GEMINI_API_KEY is configured
  const geminiKey = (env.GEMINI_API_KEY || '').trim()
  const primaryModel = (env.GEMINI_MODEL || 'gemini-2.5-flash').trim() || 'gemini-2.5-flash'
  const keyFp = geminiKey ? (await sha256Hex(geminiKey)).slice(0, 8) : ''
  let geminiFallbackErrCode: string | null = null

  if (geminiKey && topEvs.length > 0) {
    const modelName = primaryModel
    const ctxLines = topEvs.map((ev, i) => {
      const srcs = (Array.isArray(ev.sources) ? (ev.sources as Array<Record<string, unknown>>) : [])
        .slice(0, 2)
        .map((s) => `${s.source_name || ''} (${s.published_at || ''})`)
        .join(', ')
      return `[${i + 1}] ${ev.title} (status=${ev.evidence_status}, sources=${srcs})\nFact: ${cleanQaText(ev.fact_summary)}\nAI: ${cleanQaText(ev.ai_analysis)}`
    })
    if (matchedCal.length > 0) {
      ctxLines.push(
        `Catalysts: ${matchedCal.map((c) => `${c.title} (${c.scheduled_at})`).join('; ')}`,
      )
    }
    const histTxt = (body.history || [])
      .slice(-4)
      .map((h) => `${h.role || 'user'}: ${h.content || ''}`)
      .join('\n')
    const sysLang = lang === 'en' ? 'English' : '简体中文'
    const prompt = `You are MirrorBrief's strict evidence-grounded research assistant. Answer in ${sysLang}.\nCRITICAL: Cite only facts/dates/numbers present in the Evidence below; state explicitly if something is missing.\nConversation context:\n${histTxt}\n\nQuestion: ${qRaw}\n\nEvidence:\n${ctxLines.join('\n\n')}`

    const t0 = Date.now()
    try {
      const controller = new AbortController()
      const timer = setTimeout(() => controller.abort(), 12_000)
      try {
        const resp = await fetch(
          `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(modelName)}:generateContent?key=${encodeURIComponent(geminiKey)}`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            signal: controller.signal,
            body: JSON.stringify({
              contents: [{ parts: [{ text: prompt }] }],
              generationConfig: { temperature: 0.25, maxOutputTokens: 1200 },
            }),
          },
        )
        const latencyMs = Math.max(0, Date.now() - t0)
        if (resp.ok) {
          const data = (await resp.json()) as {
            candidates?: Array<{ content?: { parts?: Array<{ text?: string }> } }>
            usageMetadata?: {
              promptTokenCount?: number
              candidatesTokenCount?: number
              thoughtsTokenCount?: number
              totalTokenCount?: number
            }
          }
          const ansTxt = cleanQaText(
            data.candidates?.[0]?.content?.parts?.map((p) => p.text || '').join('\n') || '',
          )
          if (ansTxt) {
            const um = data.usageMetadata
            const rawPromptTok = Number(um?.promptTokenCount || 0)
            const rawCandTok = Number(um?.candidatesTokenCount || 0) + Number(um?.thoughtsTokenCount || 0)
            const rawTotalTok = Number(um?.totalTokenCount || 0)
            const hasExact = rawTotalTok > 0 || rawPromptTok > 0 || rawCandTok > 0
            const promptTok = hasExact ? rawPromptTok : Math.max(1, Math.floor(prompt.length / 3))
            const outTok = hasExact
              ? rawCandTok > 0
                ? rawCandTok
                : Math.max(0, rawTotalTok - rawPromptTok)
              : Math.max(1, Math.floor(ansTxt.length / 3))
            const totalTok = hasExact ? (rawTotalTok > 0 ? rawTotalTok : promptTok + outTok) : promptTok + outTok
            try {
              await recordWorkerAiUsageEvent(env.DB, {
                id: `wk_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
                scope: 'worker_qa',
                tier: 'tier1',
                primaryModel: modelName,
                modelActual: modelName,
                isFallback: false,
                keySlot: 'WORKER_GEMINI_API_KEY',
                keyFingerprint: keyFp,
                ok: true,
                promptTokens: promptTok,
                outputTokens: outTok,
                totalTokens: totalTok,
                tokenSource: hasExact ? 'exact' : 'estimated',
                latencyMs,
              })
            } catch {
              // Telemetry failure must never break user QA response
            }
            return {
              status: 200,
              payload: {
                answerMarkdown: ansTxt,
                evidenceUrls: evidenceUrls.slice(0, 8),
                dataCutoffAt: cutoff,
                missingDisclosures: [
                  lang === 'zh'
                    ? '由服务端 AI 基于 R2 当前批次多源简报生成，已限定原文出典，请核对下方原始链接。'
                    : 'Synthesized by server-side AI strictly from current R2 multi-source evidence.',
                ],
                engineMode: 'server_llm',
                modelUsed: modelName,
                remaining_quota: rl.remaining,
                daily_limit: dailyLimit,
              },
            }
          }
          geminiFallbackErrCode = 'EMPTY_RESPONSE'
        } else {
          geminiFallbackErrCode = resp.status === 429 ? 'RATE_LIMIT_429' : `HTTP_${resp.status}`
        }
        try {
          await recordWorkerAiUsageEvent(env.DB, {
            id: `wk_err_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
            scope: 'worker_qa',
            tier: 'tier1',
            primaryModel: modelName,
            modelActual: modelName,
            isFallback: false,
            keySlot: 'WORKER_GEMINI_API_KEY',
            keyFingerprint: keyFp,
            ok: false,
            errorCode: geminiFallbackErrCode,
            promptTokens: 0,
            outputTokens: 0,
            totalTokens: 0,
            tokenSource: 'none',
            latencyMs,
          })
        } catch {
          // Non-fatal
        }
      } finally {
        clearTimeout(timer)
      }
    } catch {
      geminiFallbackErrCode = 'NETWORK_OR_TIMEOUT'
      try {
        await recordWorkerAiUsageEvent(env.DB, {
          id: `wk_err_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
          scope: 'worker_qa',
          tier: 'tier1',
          primaryModel: modelName,
          modelActual: modelName,
          isFallback: false,
          keySlot: 'WORKER_GEMINI_API_KEY',
          keyFingerprint: keyFp,
          ok: false,
          errorCode: geminiFallbackErrCode,
          promptTokens: 0,
          outputTokens: 0,
          totalTokens: 0,
          tokenSource: 'none',
          latencyMs: Math.max(0, Date.now() - t0),
        })
      } catch {
        // Non-fatal
      }
    }
  }

  // Deterministic grounded synthesis fallback (0 LLM dependency)
  const lines: string[] = []
  if (lang === 'en') {
    lines.push(`### Evidence-Grounded Brief: "${qRaw}"`)
    lines.push(`- **Coverage**: Matched ${topEvs.length} verified brief(s), ${matchedCal.length} catalysts.`)
    lines.push('\n**Key Facts & Provenance**')
    topEvs.slice(0, 5).forEach((ev, idx) => {
      const s0 = ((ev.sources as Array<Record<string, unknown>> | undefined) || [{}])[0]
      lines.push(
        `${idx + 1}. **${cleanQaText(ev.title_en || ev.title)}** (\`${s0.source_name || 'Source'}\`): ${cleanQaText(ev.summary_en || ev.fact_summary)}`,
      )
    })
  } else {
    lines.push(`### 多源证据研判：「${qRaw}」`)
    lines.push(`- **检索覆盖**：共关联 ${topEvs.length} 条已核验要闻与 ${matchedCal.length} 项催化节点。`)
    lines.push('\n**一、核心事实与一手依据**')
    topEvs.slice(0, 5).forEach((ev, idx) => {
      const s0 = ((ev.sources as Array<Record<string, unknown>> | undefined) || [{}])[0]
      const pubT = String(ev.latest_reported_at || ev.published_at || '').slice(0, 16).replace('T', ' ')
      lines.push(
        `${idx + 1}. **${cleanQaText(ev.title)}**（\`${cleanQaText(s0.source_name) || '原始信源'}\` · ${pubT || '本批次'}）：${cleanQaText(ev.fact_summary)}`,
      )
    })
    const impHit = topEvs.map((e) => impactMap[String(e.event_id || '')]).find(Boolean)
    if (impHit) {
      lines.push('\n**二、市场传导参考**')
      lines.push(`- 市场方向：\`${cleanQaText(impHit.polarity_label || impHit.polarity || '中性观察')}\` — ${cleanQaText(impHit.one_liner || impHit.reasoning)}`)
    }
  }

  try {
    await recordWorkerAiUsageEvent(env.DB, {
      id: `wk_rag_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      scope: 'worker_qa',
      tier: 'edge',
      primaryModel: geminiKey ? primaryModel : 'worker-grounded-rag',
      modelActual: 'worker-grounded-rag',
      isFallback: Boolean(geminiKey),
      keySlot: geminiKey ? 'WORKER_GEMINI_API_KEY' : 'EDGE_NO_KEY',
      keyFingerprint: keyFp,
      ok: true,
      errorCode: geminiFallbackErrCode,
      promptTokens: 0,
      outputTokens: 0,
      totalTokens: 0,
      tokenSource: 'none',
      latencyMs: 0,
    })
  } catch {
    // Non-fatal
  }

  return {
    status: 200,
    payload: {
      answerMarkdown: lines.join('\n'),
      evidenceUrls: evidenceUrls.slice(0, 8),
      dataCutoffAt: cutoff,
      missingDisclosures: [
        lang === 'zh'
          ? '回答由边缘检索与结构化证据引擎实时生成；最新盘中报价请结合“股市传导”实时行情交叉核对。'
          : 'Generated by edge grounded retrieval engine; cross-check intraday quotes in Market Impact.',
      ],
      engineMode: 'grounded_synthesis',
      modelUsed: 'worker-grounded-rag',
      remaining_quota: rl.remaining,
      daily_limit: dailyLimit,
    },
  }
}
