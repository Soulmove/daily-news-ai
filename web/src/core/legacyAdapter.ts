import type {
  CategoryKey,
  OverviewSection,
  RawBatchMeta,
  RawItem,
  RawPlatform,
  RawSourceReport,
  SimulatedCommentsDoc,
  SmartCategoryDoc,
  SmartEvent,
  SmartSourceRef,
} from './types'
import { parseArchiveTimeFromPath, parseTimestampMs } from './time'
import { truncateAtSentence } from './i18n'

export const CATEGORY_LABEL_MAP: Record<CategoryKey, string> = {
  finance: '财经/市场',
  global: '国际/宏观',
  tech: '科技/AI',
  general: '社会/热点',
}

function isModernSchemaVersion(version: unknown): boolean {
  const num = Number.parseFloat(String(version ?? '').trim())
  return Number.isFinite(num) && num >= 2
}

export const PLATFORM_NAME_MAP: Record<string, string> = {
  'wallstreetcn-hot': '华尔街见闻 · 最热',
  'wallstreetcn-news': '华尔街见闻 · 资讯',
  'wallstreetcn-quick': '华尔街见闻 · 快讯',
  'cls-hot': '财联社 · 热门',
  'cls-depth': '财联社 · 深度',
  'cls-telegraph': '财联社 · 电报',
  'xueqiu-hotstock': '雪球 · 热门股票',
  gelonghui: '格隆汇',
  jin10: '金十数据',
  'mktnews-flash': 'MKTNews 快讯',
  'fastbull-express': '法布财经 · 快讯',
  'fastbull-news': '法布财经 · 头条',
  aihot: 'AIHOT 前沿',
  ithome: 'IT之家',
  sspai: '少数派',
  juejin: '稀土掘金',
  coolapk: '酷安',
  hackernews: 'Hacker News',
  'github-trending-today': 'GitHub Trending',
  producthunt: 'Product Hunt',
  'v2ex-share': 'V2EX 分享',
  freebuf: 'FreeBuf 安全',
  solidot: 'Solidot 奇客',
  'pcbeta-windows11': '远景论坛 Win11',
  zaobao: '联合早报',
  sputniknewscn: '卫星通讯社',
  cankaoxiaoxi: '参考消息',
  kaopu: '靠谱新闻',
  thepaper: '澎湃新闻',
  ifeng: '凤凰网热点',
  'tencent-hot': '腾讯新闻综合早报',
  toutiao: '今日头条',
  baidu: '百度热搜',
  zhihu: '知乎热榜',
  weibo: '微博热搜',
  douyin: '抖音热点',
  'bilibili-hot-search': 'B站热搜',
  tieba: '百度贴吧热议',
  douban: '豆瓣热门电影',
  hupu: '虎扑主干道',
  'chongbuluo-hot': '虫部落 · 最热',
  'chongbuluo-latest': '虫部落 · 最新',
  nowcoder: '牛客热榜',
  // Retired V1 sources that may appear in historical raw archives
  '36kr-quick': '36氪快讯 (历史)',
  '36kr-renqi': '36氪人气 (历史)',
  huxiu: '虎嗅 (历史)',
  geekpark: '极客公园 (历史)',
  qbitai: '量子位 (历史)',
}

export function normalizeExternalUrl(raw: unknown): string | null {
  if (typeof raw !== 'string') return null
  const text = raw.trim()
  if (!text || text === '#' || text === 'null' || text === 'undefined') return null
  try {
    const parsed = new URL(text)
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return null
    if (/^https?:\/\/(?:www\.)?xueqiu\.com\/s\/[^/]+\/?$/i.test(text)) return null
    return parsed.toString()
  } catch {
    return null
  }
}

export function sanitizeExternalUrl(raw: unknown): string | null {
  const safe = normalizeExternalUrl(raw)
  if (!safe) return null
  try {
    const parsed = new URL(safe)
    // Reject bare site homepages without path or query for news article cards
    if ((parsed.pathname === '/' || !parsed.pathname) && !parsed.search) return null
    return safe
  } catch {
    return null
  }
}

function stableHash(input: string): string {
  let h = 0x811c9dc5
  for (let i = 0; i < input.length; i++) {
    h ^= input.charCodeAt(i)
    h = Math.imul(h, 0x01000193)
  }
  return (h >>> 0).toString(16).padStart(8, '0')
}

function parseLegacySummary(rawSummary: string): OverviewSection[] {
  if (!rawSummary) return []
  const parts = rawSummary.split(/(?=【)/).filter((s) => s.trim())
  return parts.map((section) => {
    const titleMatch = /【(.*?)】/.exec(section)
    const title = titleMatch ? titleMatch[1].trim() : '核心综述'
    const content = section.replace(/【.*?】/, '').trim()
    let items = content
      .split(/(?=\(\d+\)\.?)/)
      .map((s) => s.trim())
      .filter((s) => s.length > 2)
    if (items.length === 0 && content) {
      items = content
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean)
    }
    return {
      title,
      points: items.map((text) => ({ text })),
    }
  })
}

export function adaptSmartCategoryDoc(
  rawJson: any,
  category: CategoryKey,
  archivePath?: string | null
): SmartCategoryDoc {
  if (!rawJson || rawJson.missing || rawJson.error) {
    return {
      schema_version: '2.0',
      batch_id: '',
      input_batch_id: '',
      input_cutoff_at: '',
      generated_at: parseArchiveTimeFromPath(archivePath) || '',
      published_at: null,
      category,
      category_label: CATEGORY_LABEL_MAP[category],
      generation_mode: 'missing',
      key_changes: [],
      overview_sections: [],
      events: [],
      missing: true,
      error: rawJson?.error || '该历史批次未包含此分类数据',
    }
  }

  // V2+ native payload (2.0, 3.0, 4.1, ...)
  if (Array.isArray(rawJson.events) && (isModernSchemaVersion(rawJson.schema_version) || !Array.isArray(rawJson.items))) {
    const usedIds = new Set<string>()
    const cleanEvents: SmartEvent[] = rawJson.events.map((ev: any, idx: number) => {
      const validSources: SmartSourceRef[] = (Array.isArray(ev.sources) ? ev.sources : [])
        .map((s: any) => {
          const safeUrl = sanitizeExternalUrl(s?.url)
          if (!safeUrl) return null
          return {
            item_id: String(s.item_id || ''),
            article_id: s.article_id ? String(s.article_id) : undefined,
            source_id: String(s.source_id || 'unknown'),
            source_name: String(s.source_name || PLATFORM_NAME_MAP[s.source_id] || s.source_id || '未知来源'),
            publisher_name: s.publisher_name ? String(s.publisher_name) : undefined,
            source_kind: String(s.source_kind || 'news'),
            source_tier: s.source_tier ? String(s.source_tier) : undefined,
            publisher_family: s.publisher_family ? String(s.publisher_family) : undefined,
            is_reprint_copy: Boolean(s.is_reprint_copy),
            title: String(s.title || ev.title),
            title_zh: s.title_zh ? String(s.title_zh) : undefined,
            url: safeUrl,
            published_at: s.published_at || null,
            published_at_source: s.published_at_source || null,
            fetched_at: s.fetched_at || rawJson.input_cutoff_at || rawJson.generated_at,
            excerpt: s.excerpt || null,
            deep_fetch_status: s.deep_fetch_status || null,
          } as SmartSourceRef
        })
        .filter(Boolean) as SmartSourceRef[]

      const rawId = String(ev.event_id || '').trim() || `evt_${category}_${stableHash(`${ev.title}|${idx}`)}`
      let resolvedId = rawId
      let legacyIds: string[] = Array.isArray(ev.legacy_event_ids) ? [...ev.legacy_event_ids] : []
      if (usedIds.has(rawId)) {
        resolvedId = `${rawId}__${stableHash(`${category}|${ev.title}|${idx}`)}`
        if (!legacyIds.includes(rawId)) legacyIds.push(rawId)
      }
      usedIds.add(resolvedId)

      const status =
        validSources.length === 0
          ? 'needs_verification'
          : ev.evidence_status || (validSources.length >= 2 ? 'multi_source' : 'single_source')

      const defaultLabel =
        status === 'needs_verification'
          ? '待核实'
          : status === 'official_confirmed'
            ? '一手官方/披露已证实'
            : status === 'multi_source'
              ? '多独立源提及（待核正文）'
              : '单源提及'

      const fetchedAt = String(ev.fetched_at || rawJson.input_cutoff_at || rawJson.generated_at || '')
      return {
        ...ev,
        event_id: resolvedId,
        legacy_event_ids: legacyIds,
        category,
        evidence_status: status,
        evidence_label: ev.evidence_label || defaultLabel,
        sources: validSources,
        source_count: validSources.length,
        first_discovered_at: ev.first_discovered_at || fetchedAt || null,
        first_reported_at: ev.first_reported_at || ev.published_at || null,
        latest_fact_update_at: ev.latest_fact_update_at || ev.published_at || null,
        latest_reported_at: ev.latest_reported_at || ev.published_at || null,
        unverified_claims: Array.isArray(ev.unverified_claims) ? ev.unverified_claims : [],
        contradictions: Array.isArray(ev.contradictions) ? ev.contradictions : [],
        fact_atoms: Array.isArray(ev.fact_atoms) ? ev.fact_atoms : [],
        entities: Array.isArray(ev.entities) ? ev.entities : [],
        entity_ids: Array.isArray(ev.entity_ids) ? ev.entity_ids : [],
      }
    })

    return {
      ...rawJson,
      category,
      category_label: rawJson.category_label || CATEGORY_LABEL_MAP[category],
      events: cleanEvents,
    }
  }

  // Legacy V1 historical archive adapter
  const pathTime = parseArchiveTimeFromPath(archivePath)
  const dateRaw = typeof rawJson.date === 'string' ? rawJson.date : ''
  const parsedDateMs = parseTimestampMs(dateRaw)
  const generatedIso =
    pathTime || (parsedDateMs !== null ? new Date(parsedDateMs).toISOString() : '')
  const batchId = `v1-${(generatedIso || 'legacy').slice(0, 16).replace(/[:T]/g, '-')}`

  let rawItems: any[] = []
  if (Array.isArray(rawJson.items)) {
    rawItems = rawJson.items
  } else if (rawJson.categories && typeof rawJson.categories === 'object') {
    for (const k of Object.keys(rawJson.categories)) {
      if (Array.isArray(rawJson.categories[k])) {
        rawItems = rawJson.categories[k]
        break
      }
    }
  }

  const events: SmartEvent[] = rawItems.map((it, idx) => {
    const title = String(it.title || `未命名事件 ${idx + 1}`).trim()
    const safeUrl = sanitizeExternalUrl(it.url)
    const sources: SmartSourceRef[] = safeUrl
      ? [
          {
            item_id: `v1_${stableHash(`${category}|${safeUrl}`)}`,
            source_id: 'legacy-source',
            source_name: (() => {
              try {
                return new URL(safeUrl).hostname.replace(/^www\./, '')
              } catch {
                return '原始链接'
              }
            })(),
            source_kind: 'news',
            title,
            url: safeUrl,
            published_at: null,
            fetched_at: generatedIso,
            excerpt: null,
          },
        ]
      : []

    return {
      event_id: `evt_v1_${stableHash(`${category}|${title}`)}`,
      title,
      category,
      entities: [],
      importance: idx < 3 ? 'high' : 'normal',
      sentiment: it.sentiment || null,
      special_note: it.special_note || null,
      evidence_status: sources.length > 0 ? 'single_source' : 'needs_verification',
      evidence_label: sources.length > 0 ? '单源提及 (V1归档)' : '待核实 (V1无出处)',
      evidence_status_reason:
        sources.length > 0
          ? 'V1 历史归档记录了单一来源链接（原始更新时间未细分）'
          : 'V1 历史归档未匹配到可靠新闻 URL（原链接为空、# 或行情页），已转为待核实',
      material_depth: 'title_only',
      source_count: sources.length,
      platform_count: sources.length,
      published_at: null,
      fetched_at: generatedIso,
      input_batch_id: batchId,
      fact_summary: String(it.summary || it.comment || it.reason || '').trim(),
      ai_analysis: String(it.impact || '旧版 V1 归档未单独拆分事实摘要与 AI 解读，阅读时请留意区分。').trim(),
      unverified_claims: [],
      speculation_or_outlook: it.prediction ? String(it.prediction).trim() : null,
      sources,
      followup: null,
      is_new_in_batch: false,
      legacy_v1_origin: true,
    }
  })

  const summaryStr = String(rawJson.economy_summary || rawJson.summary || '')
  return {
    schema_version: '1.0-adapted',
    batch_id: batchId,
    input_batch_id: batchId,
    input_cutoff_at: generatedIso,
    generated_at: generatedIso,
    published_at: generatedIso,
    category,
    category_label: CATEGORY_LABEL_MAP[category],
    generation_mode: 'legacy_v1',
    legacy_v1_notice:
      '当前正在浏览早期历史归档批次：旧版仅基于标题生成且部分条目缺少原文直链。',
    key_changes: events.slice(0, 3).map((ev) => ({
      event_id: ev.event_id,
      headline: ev.title,
      detail: truncateAtSentence(ev.fact_summary, 90),
      evidence_status: ev.evidence_status,
      source_count: ev.source_count,
      primary_url: ev.sources[0]?.url || null,
      source_name: ev.sources[0]?.source_name || null,
    })),
    overview_sections: parseLegacySummary(summaryStr),
    events,
  }
}

export function adaptSimulatedComments(
  rawJson: any,
  category: CategoryKey,
  expectedBatchId?: string | null,
  expectedGeneratedAt?: string | null
): SimulatedCommentsDoc {
  if (!rawJson || rawJson.missing || rawJson.error) {
    return {
      schema_version: '2.0',
      batch_id: expectedBatchId || null,
      generated_at: null,
      category,
      is_ai_simulated: true,
      status: 'missing',
      disclaimer: '该批次未包含 AI 模拟观点文件（旧版归档或未开启同批生成）。',
      comments: [],
    }
  }

  if (isModernSchemaVersion(rawJson.schema_version)) {
    if (expectedBatchId && rawJson.batch_id && rawJson.batch_id !== expectedBatchId) {
      return {
        schema_version: String(rawJson.schema_version),
        batch_id: rawJson.batch_id,
        input_batch_id: rawJson.input_batch_id,
        generated_at: rawJson.generated_at,
        category,
        is_ai_simulated: true,
        status: 'batch_mismatch',
        disclaimer: `该历史批次 (${expectedBatchId}) 暂无同批生成的多维观点记录。`,
        comments: [],
      }
    }
    return {
      schema_version: String(rawJson.schema_version),
      batch_id: rawJson.batch_id || null,
      input_batch_id: rawJson.input_batch_id || null,
      generated_at: rawJson.generated_at || null,
      category,
      is_ai_simulated: true,
      status: rawJson.status || (rawJson.comments?.length ? 'ok' : 'not_generated'),
      disclaimer:
        rawJson.disclaimer ||
        '以下内容由 AI 角色辩证推演生成，仅提供正反证据参考，不代表真实用户、公众舆论或所模拟人物本人立场。',
      comments: Array.isArray(rawJson.comments) ? rawJson.comments : [],
    }
  }

  // Legacy V1 comments check: verify batch timestamp consistency!
  const commentMs = parseTimestampMs(rawJson.date)
  const expectedMs = parseTimestampMs(expectedGeneratedAt)
  if (commentMs !== null && expectedMs !== null && Math.abs(commentMs - expectedMs) > 45 * 60_000) {
    return {
      schema_version: '1.0-adapted',
      batch_id: null,
      generated_at: rawJson.date || null,
      category,
      is_ai_simulated: true,
      status: 'batch_mismatch',
      disclaimer: `该历史批次暂无同批生成的多维观点记录。`,
      comments: [],
    }
  }

  const list = Array.isArray(rawJson.comments) ? rawJson.comments : []
  return {
    schema_version: '1.0-adapted',
    batch_id: expectedBatchId || null,
    generated_at: rawJson.date || null,
    category,
    is_ai_simulated: true,
    status: list.length ? 'ok' : 'not_generated',
    disclaimer:
      '以下内容由 AI 人设模拟生成（旧版归档兼容），不代表真实网友评论、公众舆论或真实个人发言。',
    comments: list.map((c: any, i: number) => ({
      id: `v1_c_${i}`,
      role: String(c.role || 'AI 观察角色'),
      perspective_tag: String(c.emotion || c.name || '模拟观察'),
      content: String(c.content || ''),
      stance: String(c.emotion || '模拟视角'),
    })),
  }
}

export function adaptRawCategoryPlatforms(
  rawArray: any,
  category: CategoryKey,
  batchFetchedAt: string
): RawPlatform[] {
  if (!Array.isArray(rawArray)) return []
  return rawArray.map((plat: any) => {
    const sid = String(plat.id || 'unknown')
    const sname = String(plat.name || PLATFORM_NAME_MAP[sid] || sid)
    const kind = String(plat.kind || (sid === 'xueqiu-hotstock' ? 'market_ticker' : 'news'))
    const fetchedAt = String(plat.fetched_at || batchFetchedAt)
    const normItems = (Array.isArray(plat.items) ? plat.items : [])
      .map((it: any, idx: number): RawItem | null => {
        const title = String(it?.title || '').trim()
        const url = sanitizeExternalUrl(it?.canonical_url || it?.url) || String(it?.url || '').trim()
        if (!title || !url || url === '#') return null
        return {
          item_id: String(it.item_id || `${sid}_${stableHash(`${sid}|${url}|${title}`)}`),
          source_id: sid,
          source_name: sname,
          source_kind: kind,
          citable_as_news: it.citable_as_news ?? sid !== 'xueqiu-hotstock',
          category,
          title,
          url,
          canonical_url: String(it.canonical_url || url),
          published_at: it.published_at || null,
          published_at_source: it.published_at_source || null,
          fetched_at: String(it.fetched_at || fetchedAt),
          excerpt: it.excerpt || null,
          metric_label: it.metric_label || null,
          rank: it.rank || idx + 1,
        }
      })
      .filter(Boolean) as RawItem[]

    const fallbackItems = (Array.isArray(plat.fallback_items) ? plat.fallback_items : []).map((it: any) => ({
      ...it,
      source_id: sid,
      source_name: sname,
      category,
      is_fallback: true,
    }))

    return {
      id: sid,
      name: sname,
      kind,
      category,
      status: plat.status || (normItems.length > 0 ? 'ok' : 'empty'),
      upstream_status: plat.upstream_status || null,
      upstream_updated_at: plat.upstream_updated_at || null,
      fetched_at: fetchedAt,
      last_success_at: plat.last_success_at || (normItems.length > 0 ? fetchedAt : null),
      error_message: plat.error_message || null,
      fallback_used: Boolean(plat.fallback_used),
      fallback_items: fallbackItems,
      items: normItems,
    }
  })
}

export function buildLegacyRawMeta(platforms: RawPlatform[], archivePath: string | null): RawBatchMeta {
  const fetchedAt = parseArchiveTimeFromPath(archivePath) || ''
  const sources: RawSourceReport[] = platforms.map((p) => ({
    id: p.id,
    name: p.name,
    category: p.category,
    kind: p.kind,
    status: p.status,
    fetched_at: fetchedAt,
    last_success_at: p.items.length > 0 ? fetchedAt : null,
    item_count: p.items.length,
    error_message: p.error_message || null,
  }))
  const totalItems = platforms.reduce((acc, p) => acc + p.items.length, 0)
  return {
    schema_version: '1.0-adapted',
    batch_id: `raw-legacy-${(fetchedAt || 'archive').slice(0, 16)}`,
    fetched_at: fetchedAt,
    published_at: fetchedAt,
    target_cadence_minutes: 60,
    crawl_status: 'legacy',
    summary: {
      configured_sources: platforms.length,
      ok_sources: platforms.filter((p) => p.items.length > 0).length,
      empty_sources: platforms.filter((p) => p.items.length === 0).length,
      error_sources: 0,
      stale_sources: 0,
      retired_sources: 0,
      total_raw_items: totalItems,
      deduped_events: totalItems,
    },
    sources,
  }
}

export function unwrapRawDictText(raw: unknown): string {
  const txt = String(raw ?? '').trim()
  if (!txt) return ''
  if (/^\{[\s\n]*['"](?:name|version|notes|summary|title|text)['"]\s*:/.test(txt)) {
    try {
      const parsed = JSON.parse(txt) as Record<string, unknown>
      if (parsed && typeof parsed === 'object') {
        for (const key of ['notes', 'summary', 'text', 'highlights', 'desc', 'description'] as const) {
          const val = String(parsed[key] ?? '').trim()
          if (val && !val.startsWith('{') && !val.startsWith('[')) {
            return val
          }
        }
      }
    } catch {
      // Fall through to Python repr / truncated dict extraction
    }
    const m = txt.match(/['"](?:notes|summary|text|highlights|desc|description)['"]\s*:\s*['"]([\s\S]*)/)
    if (m && m[1]) {
      return m[1]
        .replace(/['"]\s*,\s*['"][A-Za-z0-9_]+['"]\s*:[\s\S]*$/, '')
        .replace(/['"]?\s*\}\s*$/, '')
        .trim()
    }
  }
  return txt
}
