import { stripEmoji, type IconName } from './icons'

export type UnifiedEvidenceTier = 'official' | 'research' | 'corroborated' | 'single_source'

export interface EvidenceBadgeMeta {
  tier: UnifiedEvidenceTier
  iconKey: IconName
  label: string
  shortLabel: string
  badgeClass: string
  isUnverifiedOrResearch: boolean
}

const OFFICIAL_SOURCE_RE =
  /证监会|沪深交易所|沪深北交易所|上交所|深交所|北交所|央行|中国人民银行|财政部|商务部|工信部|国家统计局|国家发改委|国务院|外交部|美联储|federal\s*reserve|sec|中国结算|新华网|新华社|人民日报/i

const RESEARCH_TEXT_RE =
  /研报|策略报告|招商证券|中信证券|中金公司|华泰证券|国泰君安|高盛|摩根士丹利|大摩|小摩|瑞银|天风|郭明錤|供应链调研|渠道路演|分析师(?:披露|指出|预测|测算)/i

const TIER_MAP: Record<UnifiedEvidenceTier, Omit<EvidenceBadgeMeta, 'isUnverifiedOrResearch'>> = {
  official: {
    tier: 'official',
    iconKey: 'official',
    label: '官方公告 / 监管披露',
    shortLabel: '官方披露',
    badgeClass:
      'bg-emerald-500/12 text-emerald-700 dark:text-emerald-300 border-emerald-500/25',
  },
  research: {
    tier: 'research',
    iconKey: 'research',
    label: '机构研报 / 渠道调研',
    shortLabel: '研报/调研',
    badgeClass:
      'bg-indigo-500/12 text-indigo-700 dark:text-indigo-300 border-indigo-500/25',
  },
  corroborated: {
    tier: 'corroborated',
    iconKey: 'media',
    label: '多源媒体证实',
    shortLabel: '多源证实',
    badgeClass:
      'bg-sky-500/12 text-sky-700 dark:text-sky-300 border-sky-500/25',
  },
  single_source: {
    tier: 'single_source',
    iconKey: 'clue',
    label: '单一信源线索',
    shortLabel: '单一信源',
    badgeClass:
      'bg-amber-500/12 text-amber-700 dark:text-amber-300 border-amber-500/30',
  },
}

export interface EvidenceInput {
  evidence_tier?: string | null
  evidence_tier_label?: string | null
  evidence_status?: string | null
  sources?: Array<{ source_name?: string | null; is_reprint_copy?: boolean }> | null
  source_name?: string | null
  title?: string | null
  summary?: string | null
  independent_publisher_count?: number | null
}

export function resolveEvidenceTierBadge(input: EvidenceInput | null | undefined): EvidenceBadgeMeta {
  const obj = input || {}
  const explicit = String(obj.evidence_tier || '').trim() as UnifiedEvidenceTier
  let tier: UnifiedEvidenceTier | null =
    explicit === 'official' || explicit === 'research' || explicit === 'corroborated' || explicit === 'single_source'
      ? explicit
      : null

  if (!tier) {
    const srcNames = [
      obj.source_name || '',
      ...(obj.sources || []).map((s) => s?.source_name || ''),
    ].join(' ')
    const text = `${srcNames} ${obj.title || ''} ${obj.summary || ''}`
    const indepCount =
      Number(obj.independent_publisher_count || 0) ||
      new Set((obj.sources || []).map((s) => (s?.source_name || '').trim()).filter(Boolean)).size

    if (
      obj.evidence_status === 'official_confirmed' ||
      OFFICIAL_SOURCE_RE.test(srcNames) ||
      /(?:中国证监会|沪深北交易所|沪深交易所|中国结算|央行|财政部|商务部|美联储).*(?:公告|通知|批准|施行|生效|减免|决议|规定)/.test(
        text,
      )
    ) {
      tier = 'official'
    } else if (RESEARCH_TEXT_RE.test(text)) {
      tier = 'research'
    } else if (obj.evidence_status === 'multi_source' || indepCount >= 2 || (obj.sources?.length || 0) >= 2) {
      tier = 'corroborated'
    } else {
      tier = 'single_source'
    }
  }

  const base = TIER_MAP[tier]
  return {
    ...base,
    label: stripEmoji(obj.evidence_tier_label) || base.label,
    isUnverifiedOrResearch: tier === 'single_source' || tier === 'research',
  }
}

export function extractHeadlineQualifiers(
  title: string | null | undefined,
  summary?: string | null,
): { effectiveDateLabel: string | null; qualifierBadge: string | null } {
  const blob = `${title || ''} ${summary || ''}`.trim()
  if (!blob) return { effectiveDateLabel: null, qualifierBadge: null }

  let effectiveDateLabel: string | null = null
  const m1 = blob.match(/自\s*(?:(202[6-9])年)?\s*(\d{1,2})月(\d{1,2})日起(?:正式)?(?:施行|生效|实施|减免|执行)/)
  if (m1) {
    const yr = m1[1] && m1[1] !== '2026' ? `${m1[1]}年` : ''
    effectiveDateLabel = `${yr}${m1[2]}月${m1[3]}日起正式生效`
  } else {
    const m2 = blob.match(/(?:(202[6-9])年)?(\d{1,2})月(\d{1,2})日(?:起|起正式|正式)(?:生效|施行|实施|启用|减免|免收|执行)/)
    if (m2) {
      const yr = m2[1] && m2[1] !== '2026' ? `${m2[1]}年` : ''
      effectiveDateLabel = `${yr}${m2[2]}月${m2[3]}日生效`
    } else if (blob.includes('下周一') && /(保证金|两融|施行|实施)/.test(blob)) {
      effectiveDateLabel = '下周一起正式实施'
    }
  }

  let qualifierBadge: string | null = null
  const mUp = blob.match(/(?:最高(?:提价|涨价|涨幅|调价|上调)|(?:涨幅|提价|涨价|报价|调价)最高(?:达|至|为)?)\s*(\d+(?:\.\d+)?)\s*%/)
  if (mUp) {
    qualifierBadge = `要价上限 ${mUp[1]}% · 关注客户实际接受率`
  } else if (/(?:削减|减少).*?(?:100万|20%).*?(?:联发科|TPU\s*8t)/i.test(blob)) {
    qualifierBadge = '供应商切换：减博通 8i / 增联发科 8t'
  } else if (/(遴选|接班|外部.*?CEO)/i.test(blob) && !blob.includes('8-K')) {
    qualifierBadge = '未获董事会正式确认'
  } else if (/(传闻|据传|洽购|磋商|意向)/.test(blob)) {
    qualifierBadge = '尚在磋商阶段 · 关注正式签约'
  }

  return { effectiveDateLabel, qualifierBadge }
}
