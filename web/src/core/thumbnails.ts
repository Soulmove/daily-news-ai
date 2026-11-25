import type {
  CategoryKey,
  SimulatedPerspective,
  SmartEvent,
  StorylineDossier,
  WatchlistItem,
} from './types'
import type { StorageLike } from './storage'
import { truncateAtSentence } from './i18n'

/**
 * Resolve curated 16:9 thumbnail asset ONLY for Top-3 Must-Read cards in Today view (C9).
 * Cards beyond rank 2 (index >= 3) strictly return null to keep minimalism intact.
 */
export function resolveMustReadThumbnail(
  ev: Pick<SmartEvent, 'title' | 'title_zh' | 'title_en' | 'fact_summary' | 'category' | 'thumbnail_url'>,
  rankIndex: number,
  usedUrls?: Set<string>,
): string | null {
  if (rankIndex < 0 || rankIndex > 2) return null
  if (ev.thumbnail_url && typeof ev.thumbnail_url === 'string') return ev.thumbnail_url

  const blob = `${ev.title_zh || ''} ${ev.title_en || ''} ${ev.title || ''} ${ev.fact_summary || ''}`.toLowerCase()
  const candidates: string[] = []

  if (/(apec|summit|trilateral|diplom|putin|xi |trump|会晤|峰会|访华|元首|白宫|外交)/i.test(blob)) {
    candidates.push('./thumbs/top1-apec-summit.webp')
  }
  if (/(gemini|claude|openai|qwen|deepseek|grok|大模型|模型发布|nvidia|jensen|黄仁勋|blackwell|gpu|芯片|chip|tsmc|半导体|算力)/i.test(blob)) {
    candidates.push('./thumbs/top3-chip-transition.webp')
  }
  if (/(ipo|listing|募资|上市|发行价|破发|fomc|利率|美联储|fed\b|黄金)/i.test(blob)) {
    candidates.push('./thumbs/top2-ai-ipo.webp')
  }

  const catMap: Record<CategoryKey, string> = {
    finance: './thumbs/cat-finance.webp',
    tech: './thumbs/cat-tech.webp',
    global: './thumbs/cat-global.webp',
    general: './thumbs/cat-general.webp',
  }
  candidates.push(catMap[ev.category] || './thumbs/cat-general.webp')

  const fallbackPool = [
    './thumbs/top1-apec-summit.webp',
    './thumbs/top2-ai-ipo.webp',
    './thumbs/top3-chip-transition.webp',
    './thumbs/cat-tech.webp',
    './thumbs/cat-finance.webp',
    './thumbs/cat-global.webp',
    './thumbs/cat-general.webp',
  ]
  for (const url of [...candidates, ...fallbackPool]) {
    if (!usedUrls || !usedUrls.has(url)) {
      usedUrls?.add(url)
      return url
    }
  }
  return candidates[0]
}

export interface WatchlistPresetTemplate {
  id: 'stock' | 'ai_tech' | 'self_growth'
  label: string
  labelEn: string
  desc: string
  descEn: string
  badge: string
  items: Omit<WatchlistItem, 'created_at'>[]
}

export const WATCHLIST_PRESETS: WatchlistPresetTemplate[] = [
  {
    id: 'stock',
    label: '炒股 / 市场主线',
    labelEn: 'Markets & Equities',
    desc: '盯紧英伟达、美联储 FOMC、AI 芯片链、港美科技龙头与宏观利率',
    descEn: 'Track Nvidia, Fed FOMC, AI supply chain, HK/US mega-caps & rates',
    badge: '投资研判',
    items: [
      { id: 'preset_nvda', label: '英伟达 (NVIDIA)', kind: 'company', keywords: ['nvidia', 'nvda', '黄仁勋', 'blackwell'] },
      { id: 'preset_fomc', label: '美联储 FOMC 与利率', kind: 'event', keywords: ['美联储', 'fomc', 'fed', '降息', '加息', '美债'] },
      { id: 'preset_tsmc', label: '台积电 / 半导体链', kind: 'industry', keywords: ['台积电', 'tsmc', '半导体', '光刻机', 'hbm'] },
      { id: 'preset_tencent', label: '腾讯 (00700)', kind: 'ticker', keywords: ['腾讯', '00700', 'tencent'] },
      { id: 'preset_anthropic_ipo', label: 'AI 资本化与 IPO', kind: 'event', keywords: ['anthropic', 'ipo', '募资', '估值'] },
    ],
  },
  {
    id: 'ai_tech',
    label: 'AI 与前沿科技',
    labelEn: 'AI & Frontier Tech',
    desc: '追踪大模型迭代、开源权重、Agent 工具链与前沿硬件突破',
    descEn: 'Follow foundation models, open weights, coding agents & AI hardware',
    badge: '科技前线',
    items: [
      { id: 'preset_models', label: '大模型与多模态', kind: 'tech', keywords: ['gemini', 'claude', 'gpt', 'deepseek', 'longcat', 'openpangu'] },
      { id: 'preset_infra', label: 'vLLM / AI 推理基础设施', kind: 'tech', keywords: ['vllm', 'llama.cpp', 'sglang', 'mcp', 'agent'] },
      { id: 'preset_musk', label: 'SpaceX / Tesla / xAI', kind: 'company', keywords: ['spacex', 'tesla', 'musk', '马斯克', 'cybercab', 'xai', 'grok'] },
      { id: 'preset_huawei', label: '华为昇腾 / 盘古', kind: 'company', keywords: ['华为', '昇腾', '盘古', 'ascend'] },
    ],
  },
  {
    id: 'self_growth',
    label: '自我提升与认知视野',
    labelEn: 'Self-Growth & Synthesis',
    desc: '过滤短期杂音，聚合生产力工具、产业变迁与宏观认知主线',
    descEn: 'Filter market noise; curate AI workflows, industry shifts & macro synthesis',
    badge: '认知跃迁',
    items: [
      { id: 'preset_efficiency', label: 'AI 工作流与研发效率', kind: 'tech', keywords: ['claude code', 'agent', 'copilot', '开源', 'workflow'] },
      { id: 'preset_macro', label: '全球外交与地缘变局', kind: 'event', keywords: ['apec', '中美', '峰会', '能源', '关税'] },
      { id: 'preset_science', label: '具身智能与新能源', kind: 'industry', keywords: ['机器人', '储能', '固态电池', '自动驾驶'] },
    ],
  },
]

const ONBOARDING_SEEN_KEY = 'infofocus_onboarding_seen_v1'

export function isOnboardingCompleted(storage?: StorageLike): boolean {
  try {
    const s = storage || (typeof window !== 'undefined' ? window.localStorage : undefined)
    return s?.getItem(ONBOARDING_SEEN_KEY) === 'true'
  } catch {
    return false
  }
}

export function setOnboardingCompleted(done: boolean, storage?: StorageLike): void {
  try {
    const s = storage || (typeof window !== 'undefined' ? window.localStorage : undefined)
    s?.setItem(ONBOARDING_SEEN_KEY, done ? 'true' : 'false')
  } catch {
    // Ignore storage quota issues
  }
}

export interface PerspectiveColumn {
  lane: 'official' | 'bullish' | 'bearish'
  label: string
  labelEn: string
  tone: 'blue' | 'emerald' | 'rose'
  points: string[]
}

/**
 * Build C8 3-column Perspective Comparison card ("官方/一手" vs "顺风/乐观" vs "风险/质疑")
 * cleanly from existing verified event facts, cross-checks, uncertainties and perspectives.
 */
export function buildThreeColumnPerspectives(
  ev: SmartEvent,
  comments: SimulatedPerspective[] = [],
  dossier?: StorylineDossier | null,
): PerspectiveColumn[] {
  const officialPoints: string[] = []
  if (ev.evidence_status_reason) officialPoints.push(ev.evidence_status_reason)
  for (const a of (ev.fact_atoms || []).slice(0, 2)) {
    const body = [a.subject, a.metric_or_action, a.value, a.unit].filter(Boolean).join(' ')
    if (body) officialPoints.push(`${body}${a.attribution ? `（${a.attribution}）` : ''}`)
  }
  if (officialPoints.length === 0 && ev.fact_summary) {
    officialPoints.push(truncateAtSentence(ev.fact_summary, 140))
  }

  const bullishPoints: string[] = []
  for (const c of comments) {
    if (c.pro_argument) bullishPoints.push(c.pro_argument)
    else if (c.stance?.includes('支持') || c.stance?.includes('乐观') || c.perspective_tag?.includes('多')) {
      bullishPoints.push(c.content)
    }
  }
  if (ev.ai_analysis && bullishPoints.length === 0) {
    const parts = ev.ai_analysis
      .split(/[。；\n]+/)
      .map((s) => s.trim())
      .filter((s) => s.length >= 8)
    for (const p of parts) {
      if (/(利好|增长|突破|加速|扩展|落地|机会|领先|超预期)/.test(p)) bullishPoints.push(p)
    }
    if (bullishPoints.length === 0 && parts[0]) bullishPoints.push(parts[0])
  }

  const bearishPoints: string[] = []
  for (const w of ev.contradictions || []) {
    if (w) bearishPoints.push(w)
  }
  for (const u of ev.unverified_claims || []) {
    if (u) bearishPoints.push(`待证实：${u}`)
  }
  if (ev.speculation_or_outlook) {
    bearishPoints.push(`外推/不确定性：${ev.speculation_or_outlook}`)
  }
  for (const c of comments) {
    if (c.con_argument) bearishPoints.push(c.con_argument)
    if (c.key_unknown) bearishPoints.push(`关键未知：${c.key_unknown}`)
  }
  if (dossier) {
    for (const q of (dossier.open_questions || []).slice(0, 2)) {
      if (q && !bearishPoints.includes(q)) bearishPoints.push(q)
    }
  }
  if (bearishPoints.length === 0) {
    bearishPoints.push(
      ev.attribution_warning || '暂未出现直接证伪信号，仍需结合后续一手财报/监管文件跟踪验证。',
    )
  }

  return [
    {
      lane: 'official',
      label: '官方 / 一手定调',
      labelEn: 'Primary / Official Fact',
      tone: 'blue',
      points: officialPoints.slice(0, 3),
    },
    {
      lane: 'bullish',
      label: '顺风 / 乐观解读',
      labelEn: 'Constructive / Tailwind',
      tone: 'emerald',
      points: bullishPoints.slice(0, 3),
    },
    {
      lane: 'bearish',
      label: '风险 / 看空质疑',
      labelEn: 'Risk / Skeptical Check',
      tone: 'rose',
      points: bearishPoints.slice(0, 3),
    },
  ]
}
