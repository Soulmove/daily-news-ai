import { translateSourceName } from './i18n'
import type {
  CategoryKey,
  EvidenceStatus,
  RawClusterEvent,
  RawPlatform,
  SmartEvent,
} from './types'

export interface SmartSearchFilters {
  query: string
  evidence?: 'all' | EvidenceStatus
  sourceId?: string
  onlyUnreadOrNew?: boolean
  unreadChecker?: (event: SmartEvent) => boolean
  entity?: string
}

export interface RawSearchFilters {
  query: string
  sourceId?: string
  healthFilter?: 'all' | 'ok' | 'issue'
  onlyFavorites?: boolean
  favoriteSourceIds?: Set<string>
}

export function normalizeSearchText(input: string | null | undefined): string {
  if (!input) return ''
  return input
    .normalize('NFKC')
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim()
}

const ZH_COMPOUND_TOKENS = [
  '神舟二十四', '人工智能', '人工智能', '黎曼猜想', '平准基金', '保证金', '做市商', '逆回购', '流动性',
  '美联储', '英伟达', '特斯拉', '阿里巴巴', 'DeepSeek', 'Anthropic', '创业板', '科创板', '纳斯达克',
  '半导体', '机器人', '新能源', '比特币', '交易所', '发布会', '大模型', '商业化', '房地产', '人民币',
  '比亚迪', '华尔街', '中概股', '恒生科技', '港股通', '央行', '黄金', '原油', '降息', '加息', '通胀',
  '非农', '复职', '开源', '上市', '破发', '财报', '芯片', '算力', '回购', '关税', '空头', '暴跌',
  '飙升', '做空', '指数', '恒生', '上证', '深证', '美股', '港股', 'a股', '华为', '小米', '苹果',
  '微软', '谷歌', '字节', '腾讯', '百度', '阿里', '智谱', '豆包', '核电', '航天', '火箭', '卫星',
  '俄乌', '中东', '伊朗', '以色列', '俄罗斯', '乌克兰', '韩国', '日本', '欧盟', '特朗普', '鲍威尔',
  '黄仁勋', '车祸', '爆炸', '气候', '地震',
].sort((a, b) => b.length - a.length)

function splitCjkTerm(term: string): string[] {
  const clean = term.trim()
  if (!clean || !/[\u4e00-\u9fff]/.test(clean) || clean.length < 4) return []
  const out: string[] = []
  let rest = clean.toLowerCase()
  while (rest.length > 0) {
    const matchedTok = ZH_COMPOUND_TOKENS.find((tok) => rest.startsWith(tok.toLowerCase()))
    if (matchedTok) {
      out.push(matchedTok.toLowerCase())
      rest = rest.slice(matchedTok.length)
    } else if (rest.length >= 2) {
      // Check if any known token sits inside rest (e.g. prefix 2 chars + known 3-char token)
      let earliestIdx = -1
      for (const tok of ZH_COMPOUND_TOKENS) {
        const idx = rest.indexOf(tok.toLowerCase())
        if (idx > 0 && (earliestIdx === -1 || idx < earliestIdx)) {
          earliestIdx = idx
        }
      }
      if (earliestIdx > 0) {
        out.push(rest.slice(0, earliestIdx))
        rest = rest.slice(earliestIdx)
      } else {
        out.push(rest.slice(0, 2))
        rest = rest.slice(2)
      }
    } else {
      if (out.length > 0) out[out.length - 1] += rest
      else out.push(rest)
      rest = ''
    }
  }
  return Array.from(new Set(out.filter((x) => x.length >= 2 || /^[a-z0-9]+$/i.test(x))))
}

export function splitQueryTerms(query: string): string[] {
  const norm = normalizeSearchText(query)
  if (!norm) return []
  return norm.split(/[\s,，、;；|]+/).filter(Boolean)
}

export function matchesAllTerms(haystack: string, terms: string[]): boolean {
  if (terms.length === 0) return true
  const norm = normalizeSearchText(haystack)
  return terms.every((term) => norm.includes(term))
}

export function matchesSmartQuery(haystack: string, query: string): boolean {
  const normQuery = normalizeSearchText(query)
  if (!normQuery) return true
  const normHay = normalizeSearchText(haystack)
  if (!normHay) return false
  if (normHay.includes(normQuery)) return true
  const terms = splitQueryTerms(normQuery)
  if (terms.length === 0) return true
  if (terms.every((t) => normHay.includes(t))) return true
  // Expand contiguous >=4-char Chinese phrases into sub-terms so e.g. "央行逆回购" matches "央行开展 5160 亿元 7 天期逆回购"
  const expanded: string[] = []
  for (const t of terms) {
    if (normHay.includes(t)) {
      expanded.push(t)
    } else {
      const sub = splitCjkTerm(t)
      if (sub.length >= 2) {
        expanded.push(...sub)
      } else {
        expanded.push(t)
      }
    }
  }
  return expanded.length > 0 && expanded.every((t) => normHay.includes(t))
}

export function isEventMuted(
  ev: Pick<SmartEvent, 'event_id' | 'storyline_id' | 'entity_ids'>,
  mutedSet: Set<string>,
): boolean {
  if (!mutedSet || mutedSet.size === 0) return false
  if (mutedSet.has(ev.event_id)) return true
  if (ev.storyline_id && mutedSet.has(ev.storyline_id)) return true
  return (ev.entity_ids || []).some((eid) => mutedSet.has(eid))
}

export function buildSmartEventSearchableText(event: SmartEvent): string {
  const parts: string[] = [
    event.title,
    event.title_en ?? '',
    event.fact_summary,
    event.ai_analysis,
    event.special_note ?? '',
    event.speculation_or_outlook ?? '',
    ...event.entities,
    ...event.unverified_claims,
  ]
  for (const s of event.sources) {
    parts.push(s.source_name, s.publisher_name ?? '', s.source_id, s.title, s.title_zh ?? '', s.excerpt ?? '')
  }
  return parts.filter(Boolean).join(' ')
}

export function filterSmartEvents(
  events: SmartEvent[],
  filters: SmartSearchFilters & { mutedSet?: Set<string> },
): SmartEvent[] {
  const entityNorm = normalizeSearchText(filters.entity)

  return events.filter((ev) => {
    if (filters.mutedSet && isEventMuted(ev, filters.mutedSet)) {
      return false
    }
    if (filters.evidence && filters.evidence !== 'all' && ev.evidence_status !== filters.evidence) {
      return false
    }
    if (filters.sourceId && filters.sourceId !== 'all') {
      const targetSid = filters.sourceId
      const hasSource = targetSid.startsWith('pub:')
        ? ev.sources.some(
            (s) =>
              `pub:${translateSourceName(s.publisher_name || s.source_name || s.source_id, s.title || ev.title).toLowerCase()}` ===
              targetSid.toLowerCase(),
          )
        : ev.sources.some((s) => s.source_id === targetSid)
      if (!hasSource) return false
    }
    if (entityNorm) {
      const hasEntity =
        ev.entities.some((e) => normalizeSearchText(e) === entityNorm) ||
        normalizeSearchText(ev.title).includes(entityNorm)
      if (!hasEntity) return false
    }
    if (filters.onlyUnreadOrNew && filters.unreadChecker && !filters.unreadChecker(ev)) {
      return false
    }
    if (filters.query && filters.query.trim()) {
      const hay = buildSmartEventSearchableText(ev)
      if (!matchesSmartQuery(hay, filters.query)) return false
    }
    return true
  })
}

export function extractSmartSourceOptions(
  events: SmartEvent[],
): { id: string; name: string; count: number }[] {
  const byDisplay = new Map<string, { display: string; ids: Set<string>; count: number }>()
  for (const ev of events) {
    const seenDisplayInEvent = new Set<string>()
    for (const src of ev.sources) {
      const display = translateSourceName(src.publisher_name || src.source_name || src.source_id, src.title || ev.title).trim()
      if (!display) continue
      const dispKey = display.toLowerCase()
      const optId = src.source_id.startsWith('rss-gnews-') && display !== '权威报道' && display !== '国际媒体' && display !== '新闻电讯'
        ? `pub:${display}`
        : src.source_id
      if (!optId) continue
      let rec = byDisplay.get(dispKey)
      if (!rec) {
        rec = { display, ids: new Set([optId]), count: 0 }
        byDisplay.set(dispKey, rec)
      } else {
        rec.ids.add(optId)
      }
      if (!seenDisplayInEvent.has(dispKey)) {
        seenDisplayInEvent.add(dispKey)
        rec.count += 1
      }
    }
  }
  return Array.from(byDisplay.values())
    .map((rec) => ({
      id: rec.ids.size === 1 ? Array.from(rec.ids)[0] : `pub:${rec.display}`,
      name: rec.display,
      count: rec.count,
    }))
    .sort((a, b) => b.count - a.count)
}

export function extractTopEntities(
  events: SmartEvent[],
  limit = 10,
): { entity: string; count: number }[] {
  const counts = new Map<string, { entity: string; count: number }>()
  for (const ev of events) {
    const seen = new Set<string>()
    for (const rawEntity of ev.entities) {
      const ent = rawEntity.trim()
      if (!ent || ent.length > 24) continue
      const key = normalizeSearchText(ent)
      if (seen.has(key)) continue
      seen.add(key)
      const prev = counts.get(key)
      if (prev) {
        prev.count += 1
      } else {
        counts.set(key, { entity: ent, count: 1 })
      }
    }
  }
  return Array.from(counts.values())
    .filter((x) => x.count >= 1)
    .sort((a, b) => b.count - a.count || a.entity.localeCompare(b.entity, 'zh-CN'))
    .slice(0, limit)
}

export function filterRawClusters(
  clusters: RawClusterEvent[],
  filters: RawSearchFilters,
): RawClusterEvent[] {
  const terms = splitQueryTerms(filters.query)
  return clusters.filter((c) => {
    if (filters.onlyFavorites && filters.favoriteSourceIds) {
      const anyFav = c.appearances.some((a) => filters.favoriteSourceIds!.has(a.source_id))
      if (!anyFav) return false
    }
    if (filters.sourceId && filters.sourceId !== 'all') {
      const hasSource = c.appearances.some((a) => a.source_id === filters.sourceId)
      if (!hasSource) return false
    }
    if (terms.length > 0) {
      const hay = [
        c.primary_title,
        c.excerpt ?? '',
        ...c.appearances.map((a) => `${a.source_name} ${a.source_id} ${a.title} ${a.excerpt ?? ''}`),
      ].join(' ')
      if (!matchesAllTerms(hay, terms)) return false
    }
    return true
  })
}

export function filterRawPlatforms(
  platforms: RawPlatform[],
  filters: RawSearchFilters & { category?: CategoryKey | 'favorites' | 'all' },
): RawPlatform[] {
  const terms = splitQueryTerms(filters.query)
  return platforms
    .filter((p) => {
      if (filters.category === 'favorites') {
        if (!filters.favoriteSourceIds?.has(p.id)) return false
      } else if (filters.category && filters.category !== 'all' && p.category !== filters.category) {
        return false
      }
      if (filters.sourceId && filters.sourceId !== 'all' && p.id !== filters.sourceId) {
        return false
      }
      if (filters.healthFilter === 'ok' && p.status !== 'ok') return false
      if (filters.healthFilter === 'issue' && p.status === 'ok') return false
      return true
    })
    .map((p) => {
      const items = p.items.length > 0 ? p.items : p.fallback_items ?? []
      if (terms.length === 0) return p
      const matchingItems = items.filter((item) =>
        matchesAllTerms(
          `${p.name} ${p.id} ${item.title} ${item.excerpt ?? ''} ${item.metric_label ?? ''}`,
          terms,
        ),
      )
      return {
        ...p,
        items: p.items.length > 0 ? matchingItems : [],
        fallback_items: p.items.length === 0 ? matchingItems : p.fallback_items,
      }
    })
    .filter((p) => {
      if (terms.length === 0) return true
      const effectiveItems = p.items.length > 0 ? p.items : p.fallback_items ?? []
      return (
        effectiveItems.length > 0 ||
        matchesAllTerms(`${p.name} ${p.id}`, terms)
      )
    })
}
