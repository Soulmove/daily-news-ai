import type {
  AiClientConfig,
  CatalystEvent,
  EntityProfile,
  MajorTopicSpotlight,
  SmartEvent,
  StorylineDossier,
} from './types'
import { formatShanghaiDateTime } from './time'
import { getApiBase } from './auth'
import { appLang, truncateAtSentence } from './i18n'
import { normalizeExternalUrl } from './legacyAdapter'

export interface EvidenceQaResponse {
  answerMarkdown: string
  evidenceUrls: { label: string; url: string }[]
  dataCutoffAt: string
  missingDisclosures: string[]
  engineMode?: 'local_retrieval' | 'live_llm' | 'server_llm' | 'grounded_synthesis'
  modelUsed?: string
}

export interface QaContextBundle {
  event?: SmartEvent | null
  storyline?: StorylineDossier | null
  entity?: EntityProfile | null
  topic?: MajorTopicSpotlight | null
  allEvents?: SmartEvent[]
  topics?: MajorTopicSpotlight[]
  calendarEvents?: CatalystEvent[]
  dataCutoffAt?: string | null
}

/**
 * Strictly bounded Evidence Q&A engine: answers questions exclusively from loaded events,
 * topics/itineraries, calendar schedules, storylines, SEC/HKEX filings, and financial actuals.
 */
export function answerQuestionBounded(
  question: string,
  context: QaContextBundle,
): EvidenceQaResponse {
  const q = question.trim().toLowerCase()
  const cutoff = context.dataCutoffAt ? formatShanghaiDateTime(context.dataCutoffAt, false) : '当前已加载批次'
  const urls: { label: string; url: string }[] = []
  const seenUrls = new Set<string>()
  const addUrl = (label: string, url?: string | null) => {
    const safeUrl = normalizeExternalUrl(url)
    if (!safeUrl || seenUrls.has(safeUrl)) return
    seenUrls.add(safeUrl)
    urls.push({ label, url: safeUrl })
  }

  const missing: string[] = []
  const lines: string[] = []

  if (context.topic) {
    const tp = context.topic
    lines.push(`### 专题「${tp.title}」时间线与脉络梳理（数据截止 ${cutoff}）`)
    lines.push(`- **专题概要**：${tp.subtitle}（汇总 ${tp.source_count} 家信源 · 共 ${tp.total_mentions} 条相关报道）`)
    for (const node of tp.timeline.slice(-8)) {
      const ts = node.time ? formatShanghaiDateTime(node.time, false) : '近期'
      lines.push(`- **[${node.stage_tag} · ${ts}] ${node.title}**${node.summary ? ` — ${truncateAtSentence(node.summary, 110)}` : ''}`)
      if (node.url) addUrl(`${node.source_name}: ${truncateAtSentence(node.title, 32)}`, node.url)
    }
  } else if (context.storyline) {
    const st = context.storyline
    st.sources.forEach((s) => addUrl(`${s.source_name}: ${s.title.slice(0, 28)}`, s.url))

    if (q.includes('变化') || q.includes('7天') || q.includes('新增') || q.includes('进展')) {
      lines.push(`### 主线「${st.title}」进展拆解（数据截止 ${cutoff}）`)
      lines.push(`- **当前阶段**：${st.current_stage} · 可信等级：${st.evidence_label}`)
      lines.push(`- **新增事实**：${st.fact_diff.new_facts.length ? st.fact_diff.new_facts.join('；') : '本批次暂无相对上批的新增实质事实句子。'}`)
      if (st.fact_diff.unchanged_background.length) {
        lines.push(`- **未变背景**：${st.fact_diff.unchanged_background.join('；')}`)
      }
    } else if (q.includes('分歧') || q.includes('正反') || q.includes('质疑') || q.includes('可靠') || q.includes('证实')) {
      lines.push(`### 主线「${st.title}」正反依据与冲突核查`)
      lines.push(`- **支撑/事实依据**：${st.fact_atoms.map((a) => `${a.subject}: ${a.metric_or_action} (${a.attribution})`).join('；') || st.fact_diff.new_facts.join('；')}`)
      if (st.contradictions.length) {
        lines.push(`- **矛盾/反向核查**：${st.contradictions.join('；')}`)
      }
      if (st.unverified_claims?.length) {
        lines.push(`- **待证传闻声明**：${st.unverified_claims.join('；')}`)
      }
      if (!st.contradictions.length && st.evidence_status !== 'official_confirmed') {
        missing.push('尚未检索到公司官方/监管公告正文对全部细节作出书面回应。')
      }
    } else if (q.includes('证伪') || q.includes('催化') || q.includes('节点') || q.includes('下一步')) {
      lines.push(`### 主线「${st.title}」证伪条件与下个验证节点`)
      lines.push(`- **下个验证节点**：${st.next_catalyst || '关注下一次财报或官方监管披露'}`)
      lines.push(`- **当前悬而未决问题**：${st.open_questions.join('；') || '暂无未决争议点记录'}`)
      if (st.investment_card) {
        lines.push(`- **核心经营变量**：${st.investment_card.operating_variables.join('、')}`)
      }
    } else {
      lines.push(`### 基于已加载主线「${st.title}」的证据回答`)
      lines.push(`- **事实摘要**：${st.fact_diff.new_facts.concat(st.fact_diff.unchanged_background).join('；') || st.title}`)
      if (st.ai_analysis) lines.push(`- **背景解读**：${st.ai_analysis}`)
      lines.push(`- **证据状态**：${st.evidence_label}`)
    }
  } else if (context.entity) {
    const ent = context.entity
    ent.recent_filings.slice(0, 4).forEach((f) => addUrl(`${f.form} (${f.filing_date})`, f.url))
    ent.recent_events.slice(0, 4).forEach((e) => addUrl(e.title.slice(0, 32), e.primary_url))

    lines.push(`### 实体档案「${ent.canonical_name}」证据回答（数据截止 ${cutoff}）`)
    lines.push(`- **近期事件动态（${ent.change_count_30d} 条）**：${ent.recent_events.slice(0, 4).map((e) => e.title).join('；') || '本批次暂无直接关联事件。'}`)
    if (ent.financial_actuals.length) {
      lines.push(`- **SEC XBRL 历史实际营收**：${ent.financial_actuals.slice(0, 3).map((a) => `${a.period_end} ${a.value}`).join(' | ')}`)
    } else {
      missing.push('当前实体档案中暂未写入 SEC XBRL 季度财务数字（非美股上市公司或本轮连接器未覆盖）。')
    }
    lines.push(`- **核心关注变量**：${ent.operating_variables.join('、')}`)
    lines.push(`- **未来验证里程碑**：${ent.validation_milestones.join('；')}`)
  } else if (context.event) {
    const ev = context.event
    ev.sources.forEach((s) => addUrl(`${s.source_name}`, s.url))
    lines.push(`### 单条事件「${ev.title}」证据核查（数据截止 ${cutoff}）`)
    lines.push(`- **可核验事实**：${ev.fact_summary || ev.title}`)
    lines.push(`- **可信度说明**：${ev.evidence_label} — ${ev.evidence_status_reason}`)
    if (ev.attribution_warning) lines.push(`- **归因警告**：${ev.attribution_warning}`)
    if (ev.contradictions?.length) lines.push(`- **交叉矛盾**：${ev.contradictions.join('；')}`)
    if (ev.material_depth === 'title_only') {
      missing.push('当前事件核心素材仅含热榜标题或短摘要，系统未编造正文数字，请点击下方出处链接查看原文。')
    }
  } else {
    const allEvs = context.allEvents ?? []
    const allTopics = context.topics ?? []
    const allCals = context.calendarEvents ?? []
    const cleanedQuery = q
      .replace(/[？?！!。，,、：:""''（）()]/g, ' ')
      .replace(/(近\d+天|有哪些|主要|在哪里|是什么|什么|怎么|如何|为什么|哪些|发生|情况|关于|当前|现在|目前|这次|来中国|和|与|及|的|了|吗|呢)/g, ' ')
      .trim()
    const queryTerms = cleanedQuery
      .split(/\s+/)
      .map((t) => t.trim())
      .filter((t) => t.length >= 2)

    const isChangesOverview = /核心变化|主要变化|要点|汇总|发生.*什么|近\d+天/.test(q)
    const isConflictOverview = /正反|分歧|争议|多空|相反|传闻/.test(q)
    const isValidationOverview = /证伪|验证|节点|催化|后续|风险/.test(q)

    // Check Major Topic Spotlights & Itineraries first when user asks a topical/itinerary query
    const matchedTopics = !isChangesOverview && !isConflictOverview && !isValidationOverview
      ? allTopics.filter((tp) => {
          const tHay = `${tp.title} ${tp.subtitle} ${tp.timeline.map((n) => `${n.title} ${n.summary}`).join(' ')}`.toLowerCase()
          if (queryTerms.some((t) => tHay.includes(t))) return true
          if (cleanedQuery.length >= 2) {
            let hits = 0
            for (let i = 0; i <= cleanedQuery.length - 2; i += 1) {
              const bg = cleanedQuery.slice(i, i + 2)
              if (!/\s/.test(bg) && tHay.includes(bg)) hits += 1
            }
            return hits >= 2
          }
          return false
        })
      : []

    const ranked = allEvs
      .map((ev) => {
        const hay = `${ev.title} ${ev.fact_summary} ${ev.ai_analysis || ''} ${ev.entities.join(' ')} ${(ev.unverified_claims || []).join(' ')} ${(ev.contradictions || []).join(' ')} ${ev.sources.map((s) => `${s.source_name} ${s.title}`).join(' ')}`.toLowerCase()
        let score = 0
        if (q && hay.includes(q)) score += 10
        for (const term of queryTerms) {
          if (hay.includes(term)) score += term.length >= 3 ? 4 : 2
        }
        // Fallback bigram/entity token overlap for Chinese phrases without spaces
        if (score === 0 && cleanedQuery.length >= 2) {
          for (let i = 0; i <= cleanedQuery.length - 2; i += 1) {
            const bg = cleanedQuery.slice(i, i + 2)
            if (!/\s/.test(bg) && hay.includes(bg)) score += 1
          }
        }
        return { ev, score }
      })
      .filter((item) => item.score >= (queryTerms.length > 0 ? 2 : 1))
      .sort((a, b) => b.score - a.score)

    if ((matchedTopics.length > 0 || ranked.length > 0) && !(isChangesOverview || isConflictOverview || isValidationOverview)) {
      if (matchedTopics.length > 0) {
        const tp = matchedTopics[0]
        lines.push(`### 命中专题「${tp.title}」最新时间线（数据截止 ${cutoff}）`)
        tp.timeline.slice(-6).forEach((node) => {
          const ts = node.time ? formatShanghaiDateTime(node.time, false) : '近期'
          lines.push(`- **[${node.stage_tag} · ${ts}] ${node.title}**（${node.source_name}）`)
          if (node.url) addUrl(`${node.source_name}: ${node.title.slice(0, 24)}`, node.url)
        })
      }
      if (ranked.length > 0) {
        const hits = ranked.slice(0, matchedTopics.length > 0 ? 3 : 5).map((r) => r.ev)
        lines.push(`### 相关已核验简报（共 ${ranked.length} 条 · 数据截止 ${cutoff}）`)
        hits.forEach((ev) => {
          const firstUrl = ev.sources.find((s) => s.url)?.url
          lines.push(`- **${ev.title}**（${ev.evidence_label}）：${truncateAtSentence(ev.fact_summary, 130)}`)
          if (ev.attribution_warning) {
            lines.push(`  核查提示：${ev.attribution_warning}`)
          }
          if (firstUrl) addUrl(truncateAtSentence(ev.title, 36), firstUrl)
        })
      }
      const calHits = allCals.filter((c) => {
        const ch = `${c.title} ${c.watch_variable}`.toLowerCase()
        return queryTerms.some((t) => ch.includes(t))
      })
      if (calHits.length > 0) {
        lines.push(`### 关联日程节点`)
        calHits.slice(0, 3).forEach((c) => {
          lines.push(`- **${c.title}**（${c.scheduled_at ? formatShanghaiDateTime(c.scheduled_at, false) : '待定'} · 观察：${c.watch_variable}）`)
          if (c.source_url) addUrl(c.source_name, c.source_url)
        })
      }
    } else if (isConflictOverview && allEvs.length > 0) {
      const contested = allEvs.filter(
        (ev) =>
          (ev.contradictions && ev.contradictions.length > 0) ||
          (ev.unverified_claims && ev.unverified_claims.length > 0) ||
          Boolean(ev.attribution_warning),
      )
      const pick = (contested.length > 0 ? contested : allEvs).slice(0, 5)
      lines.push(`### 本批次正反依据与核心分歧汇总（数据截止 ${cutoff}）`)
      pick.forEach((ev) => {
        const diffNote =
          ev.contradictions?.[0] ||
          ev.attribution_warning ||
          ev.unverified_claims?.[0] ||
          ev.evidence_status_reason
        lines.push(`- **${ev.title}**（${ev.evidence_label}）：${truncateAtSentence(ev.fact_summary, 100)}；待核分歧：${diffNote}`)
        const firstUrl = ev.sources.find((s) => s.url)?.url
        if (firstUrl) addUrl(truncateAtSentence(ev.title, 36), firstUrl)
      })
      missing.push('涉及市场传闻或未决监管口径的事件仅反映现有公开线索，未见正式公告前不视为既成事实。')
    } else if (isValidationOverview && allEvs.length > 0) {
      const pick = allEvs
        .filter((ev) => ev.speculation_or_outlook || ev.attribution_warning || (ev.unverified_claims?.length ?? 0) > 0 || ev.importance === 'high')
        .slice(0, 5)
      const list = pick.length > 0 ? pick : allEvs.slice(0, 5)
      lines.push(`### 本批次重点证伪条件与关键验证节点（数据截止 ${cutoff}）`)
      list.forEach((ev) => {
        const node = ev.speculation_or_outlook || ev.attribution_warning || ev.evidence_status_reason
        lines.push(`- **${ev.title}**：关注验证点 — ${node}`)
        const firstUrl = ev.sources.find((s) => s.url)?.url
        if (firstUrl) addUrl(ev.title.slice(0, 28), firstUrl)
      })
    } else if (allEvs.length > 0 && (isChangesOverview || ranked.length === 0)) {
      if (isChangesOverview) {
        const priorityEvs = [...allEvs]
          .sort((a, b) => {
            const rank = { official_confirmed: 3, multi_source: 2, single_source: 1, needs_verification: 0 }
            return (rank[b.evidence_status] ?? 0) - (rank[a.evidence_status] ?? 0) || b.source_count - a.source_count
          })
          .slice(0, 5)
        lines.push(`### 当前已加载批次核心变化速览（共 ${allEvs.length} 条 · 数据截止 ${cutoff}）`)
        priorityEvs.forEach((ev) => {
          lines.push(`- **${ev.title}**（${ev.evidence_label} · ${ev.independent_publisher_count || ev.source_count} 源）：${ev.fact_summary.slice(0, 95)}`)
          const firstUrl = ev.sources.find((s) => s.url)?.url
          if (firstUrl) addUrl(ev.title.slice(0, 28), firstUrl)
        })
      } else {
        lines.push(`### 未在当前已加载素材中检索到直接对应「${question.trim()}」的证据（数据截止 ${cutoff}）`)
        const sampleTopics = allEvs.slice(0, 3).map((e) => e.entities[0] || e.title.slice(0, 16)).join('、')
        missing.push(`当前已加载 ${allEvs.length} 条事件（热门主体含：${sampleTopics}），依据严谨性规则拒绝臆测未匹配问题。`)
      }
    } else {
      lines.push(`### 未在当前已加载素材中检索到直接对应证据（数据截止 ${cutoff}）`)
      missing.push('现有本地与批次缓存中无匹配的官方披露或新闻原文，依据严谨性规则拒绝臆测回答。')
    }
  }

  if (urls.length === 0) {
    missing.push('当前条目前无合格原文链接，仅供核查提示。')
  }
  missing.push('本系统当前为静态站点，不含付费实时盘中行情估值与华尔街一致预期接口。')

  return {
    answerMarkdown: lines.join('\n'),
    evidenceUrls: urls.slice(0, 6),
    dataCutoffAt: cutoff,
    missingDisclosures: missing,
    engineMode: 'local_retrieval',
  }
}

function buildGroundedPromptContext(question: string, context: QaContextBundle): {
  prompt: string
  evidenceUrls: { label: string; url: string }[]
  cutoff: string
} {
  const cutoff = context.dataCutoffAt ? formatShanghaiDateTime(context.dataCutoffAt, false) : '当前批次'
  const localSnap = answerQuestionBounded(question, context)
  const chunks: string[] = []

  if (context.topic) {
    chunks.push(
      `【当前专题】${context.topic.title}\n` +
        context.topic.timeline
          .map((n) => `- [${n.time || '近期'} | ${n.stage_tag}] ${n.title} (${n.source_name}) ${n.summary}`)
          .join('\n'),
    )
  } else if (context.storyline) {
    chunks.push(
      `【当前事件档案】${context.storyline.title}\n阶段：${context.storyline.current_stage}\n新增事实：${context.storyline.fact_diff.new_facts.join('；')}\n历史背景：${context.storyline.fact_diff.unchanged_background.join('；')}\n未决问题：${context.storyline.open_questions.join('；')}`,
    )
  } else if (context.entity) {
    chunks.push(
      `【当前实体档案】${context.entity.canonical_name}\n变量：${context.entity.operating_variables.join('、')}\n近期事件：${context.entity.recent_events.slice(0, 6).map((e) => e.title).join('；')}`,
    )
  } else if (context.event) {
    chunks.push(
      `【当前单条事件】${context.event.title}\n事实：${context.event.fact_summary}\n解读：${context.event.ai_analysis}\n来源：${context.event.sources.map((s) => `${s.source_name}:${s.title}`).join('；')}`,
    )
  } else {
    if (context.topics?.length) {
      chunks.push(
        '【活跃超级专题时间线】\n' +
          context.topics
            .slice(0, 3)
            .map(
              (tp) =>
                `专题「${tp.title}」:\n` +
                tp.timeline
                  .slice(-6)
                  .map((n) => `  - ${n.time || '近期'} [${n.stage_tag}] ${n.title} (${n.source_name})`)
                  .join('\n'),
            )
            .join('\n'),
      )
    }
    const evList = (context.allEvents ?? []).slice(0, 28)
    if (evList.length) {
      chunks.push(
        '【当前批次重点简报】\n' +
          evList
            .map((e, i) => `${i + 1}. [${e.category}] ${e.title}｜${(e.fact_summary || '').slice(0, 110)}`)
            .join('\n'),
      )
    }
    if (context.calendarEvents?.length) {
      chunks.push(
        '【近期日程日历】\n' +
          context.calendarEvents
            .slice(0, 8)
            .map((c) => `- ${c.scheduled_at || '待定'} ${c.title}（观察：${c.watch_variable}）`)
            .join('\n'),
      )
    }
  }

  const prompt = [
    `你是 镜信 MirrorBrief 严肃新闻与投研助理。数据截止时间：${cutoff}。`,
    '请严格基于下方已入库素材回答用户问题：',
    '1. 用清晰结构（### 小标题 + - **要点**：说明）直接回答，重点给出时间线、核心事实与潜在市场/行业影响。',
    '2. 严禁编造下方素材未提及的数字或行程细节；若素材确有缺失，请在末尾明确列出“当前素材缺口”。',
    '',
    chunks.join('\n\n'),
    '',
    `用户问题：${question.trim()}`,
  ].join('\n')

  return { prompt, evidenceUrls: localSnap.evidenceUrls, cutoff }
}

/**
 * Real LLM Q&A via user's locally-configured Gemini or OpenAI-compatible API key (BYOK).
 */
export async function callLiveLlmQa(
  question: string,
  config: AiClientConfig,
  context: QaContextBundle,
): Promise<EvidenceQaResponse> {
  const apiKey = config.apiKey.trim()
  if (!apiKey) {
    return answerQuestionBounded(question, context)
  }

  const { prompt, evidenceUrls, cutoff } = buildGroundedPromptContext(question, context)

  if (config.provider === 'gemini') {
    const modelsToTry = Array.from(new Set([config.model.trim() || 'gemini-2.5-flash']))
    let lastErr = ''
    for (const mdl of modelsToTry) {
      try {
        const resp = await fetch(
          `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(mdl)}:generateContent?key=${encodeURIComponent(apiKey)}`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              contents: [{ parts: [{ text: prompt }] }],
              generationConfig: { temperature: 0.25, maxOutputTokens: 1200 },
            }),
          },
        )
        if (!resp.ok) {
          lastErr = `HTTP ${resp.status} (${mdl})`
          continue
        }
        const data = (await resp.json()) as {
          candidates?: { content?: { parts?: { text?: string }[] } }[]
        }
        const text = data.candidates?.[0]?.content?.parts?.map((p) => p.text || '').join('\n').trim()
        if (text) {
          return {
            answerMarkdown: text,
            evidenceUrls,
            dataCutoffAt: cutoff,
            missingDisclosures: ['回答由浏览器直连您配置的 Gemini API 生成，已限定引用本批次入库素材；请核对下方原文出处。'],
            engineMode: 'live_llm',
            modelUsed: mdl,
          }
        }
      } catch (err) {
        lastErr = err instanceof Error ? err.message : String(err)
      }
    }
    throw new Error(`Gemini API 调用失败：${lastErr || '未知错误'}`)
  }

  const base = (config.baseUrl || 'https://api.openai.com/v1').replace(/\/+$/, '')
  const mdl = config.model.trim() || 'gpt-4o-mini'
  const resp = await fetch(`${base}/chat/completions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({
      model: mdl,
      temperature: 0.25,
      messages: [
        { role: 'system', content: '你是严谨的新闻与投研分析助手，只基于提供素材作答并标明缺失信息。' },
        { role: 'user', content: prompt },
      ],
    }),
  })
  if (!resp.ok) {
    throw new Error(`OpenAI 兼容接口返回 HTTP ${resp.status}`)
  }
  const data = (await resp.json()) as {
    choices?: { message?: { content?: string } }[]
  }
  const text = data.choices?.[0]?.message?.content?.trim()
  if (!text) {
    throw new Error('模型未返回有效文本内容')
  }
  return {
    answerMarkdown: text,
    evidenceUrls,
    dataCutoffAt: cutoff,
    missingDisclosures: [`回答由浏览器直连您配置的接口 (${mdl}) 生成，基于本批次入库素材。`],
    engineMode: 'live_llm',
    modelUsed: mdl,
  }
}

export async function askEvidenceQa(
  question: string,
  config: AiClientConfig,
  context: QaContextBundle,
  options?: { forceLocal?: boolean; history?: { role: string; content: string }[] },
): Promise<EvidenceQaResponse> {
  if (!options?.forceLocal && config.apiKey.trim()) {
    return callLiveLlmQa(question, config, context)
  }
  if (!options?.forceLocal) {
    try {
      const targetType = context.storyline
        ? 'storyline'
        : context.entity
          ? 'entity'
          : context.event
            ? 'event'
            : 'global'
      const targetId =
        context.storyline?.storyline_id ||
        context.entity?.entity_id ||
        context.event?.event_id ||
        null
      const resp = await fetch(`${getApiBase()}/api/qa/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question,
          target_type: targetType,
          target_id: targetId,
          lang: appLang.value,
          history: options?.history || [],
        }),
      })
      if (resp.ok) {
        const data = (await resp.json()) as EvidenceQaResponse
        if (data?.answerMarkdown) {
          if (Array.isArray(data.evidenceUrls)) {
            data.evidenceUrls = data.evidenceUrls
              .map((u) => {
                const safeUrl = normalizeExternalUrl(u?.url)
                return safeUrl ? { label: u.label, url: safeUrl } : null
              })
              .filter((u): u is { label: string; url: string } => Boolean(u))
          }
          return data
        }
      }
    } catch {
      // Offline / dev fallback cleanly to bounded local synthesis below
    }
  }
  return answerQuestionBounded(question, context)
}
