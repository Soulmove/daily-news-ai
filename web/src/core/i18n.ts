/**
 * Unified reactive bilingual (zh / en) dictionary and helpers for MirrorBrief (镜信).
 * Keeps UI chrome completely translated while leaving news body copy in its own language.
 */

import { ref } from 'vue'

export type AppLang = 'zh' | 'en'

const LANG_KEY = 'mirrorbrief_lang_v1'

export const I18N_DICTIONARY = {
  brand: {
    logoChar: { zh: '镜', en: 'M' },
    name: { zh: '镜信', en: 'MirrorBrief' },
    subtitle: {
      zh: '一镜照见全球真实大事 · 7×24 零延迟',
      en: 'Global Real-Time Intelligence · 7×24',
    },
  },
  nav: {
    briefing: { zh: '全球情报', en: 'Briefings' },
    monitor: { zh: '情报监控', en: 'Monitor' },
    about: { zh: '关于镜信', en: 'About' },
    home: { zh: '返回首页', en: 'Home' },
  },
  tabs: {
    today: { zh: '今日要闻', en: 'Today' },
    wire: { zh: '7×24 快讯', en: 'Live Wire' },
    ai_progress: { zh: 'AI 前沿', en: 'AI Frontier' },
    finance: { zh: '股市传导', en: 'Markets' },
    briefing: { zh: '新闻简报', en: 'Briefings' },
    tracking: { zh: '事件追踪', en: 'Tracking' },
    calendar: { zh: '催化日历', en: 'Calendar' },
    predictions: { zh: '前瞻验证', en: 'Predictions' },
    tools: { zh: '科技工具库', en: 'Tools' },
  },
  categories: {
    finance: { name: '财经/市场', nameEn: 'Markets / Finance', short: '财经', shortEn: 'Markets' },
    global: { name: '国际/宏观', nameEn: 'Global / Macro', short: '国际', shortEn: 'Global' },
    tech: { name: '科技/AI', nameEn: 'Tech / AI', short: '科技', shortEn: 'Tech' },
    general: { name: '社会/热点', nameEn: 'Society / Headlines', short: '热点', shortEn: 'Headlines' },
  },
  search: {
    placeholder: { zh: '搜索新闻、实体、日历、工具', en: 'Search news, entities, calendar, tools' },
    emptyTitleWithQuery: {
      zh: '没找到「{q}」相关事件。试试：清空筛选 / 换个关键词 / 查看全部事件',
      en: 'No results found for "{q}". Try clearing filters, changing keywords, or viewing all items.',
    },
    emptyTitleFilterOnly: {
      zh: '当前筛选条件下暂无匹配内容',
      en: 'No matching items under current filters',
    },
    clearAll: { zh: '清空筛选', en: 'Clear Filters' },
    viewAll: { zh: '查看全部事件', en: 'View All Items' },
  },
  actions: {
    archive: { zh: '历史归档', en: 'Archive' },
    archiveShort: { zh: '归档', en: 'Past' },
    saved: { zh: '收藏', en: 'Saved' },
    signIn: { zh: '登录 / 同步', en: 'Sign In' },
    signInShort: { zh: '登录', en: 'Login' },
    syncedShort: { zh: '已同步', en: 'Sync' },
    checkUpdates: { zh: '检查最新更新', en: 'Check for updates' },
    checkingUpdates: { zh: '检查中…', en: 'Checking…' },
    alreadyLatest: { zh: '已是最新', en: 'Already up to date' },
    updatedCount: { zh: '已更新 {n} 条最新事件', en: 'Updated {n} new events' },
  },
  footer: {
    privacy: { zh: '隐私政策', en: 'Privacy' },
    terms: { zh: '用户协议', en: 'Terms' },
    help: { zh: '使用帮助', en: 'Help' },
    feedback: { zh: '意见反馈', en: 'Feedback' },
  },
} as const

function readInitialLang(): AppLang {
  if (typeof window === 'undefined') return 'zh'
  try {
    if (window.location?.search?.includes('lang=en')) return 'en'
  } catch {
    // ignore
  }
  return 'zh'
}

export const appLang = ref<AppLang>(readInitialLang())

export function setAppLang(next: AppLang): void {
  appLang.value = next
  if (typeof window !== 'undefined') {
    try {
      window.localStorage.setItem(LANG_KEY, next)
      document.documentElement.lang = next === 'en' ? 'en' : 'zh-CN'
    } catch {
      // ignore
    }
  }
}

export function syncHtmlLangAttr(): void {
  if (typeof document !== 'undefined') {
    document.documentElement.lang = appLang.value === 'en' ? 'en' : 'zh-CN'
  }
}

export function toggleAppLang(): void {
  setAppLang(appLang.value === 'zh' ? 'en' : 'zh')
}

export function t(zhText: string, enText: string, params?: Record<string, string | number>): string {
  let raw = appLang.value === 'en' ? enText : zhText
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      raw = raw.replaceAll(`{${k}}`, String(v))
    }
  }
  return raw
}

const BROKEN_GLOSS_TOKEN_RE =
  /(?:strikes mine in|as officials turn hawkish|slides in day-two|erases YTD|officials signal hawkish|launch(?:es)?|plunge(?:s)?|surges?|rebounds?|announces?|plans?|expected|data shows)/i

export function sanitizeEnText(raw: string | null | undefined): string {
  if (!raw) return ''
  return String(raw)
    .replace(/^(?:【[^】]{2,24}】\s*)+/g, '')
    .replace(/^\[[^\]]{2,48}\]\s*/g, '')
    .replace(/([A-Za-z0-9])\s*([’‘'])\s*(s|t|re|ve|ll|d|m)\b/gi, (_, p1: string, _q: string, suf: string) => `${p1}'${suf}`)
    .replace(/(?<=[A-Za-z0-9%])\s*[，]\s*(?=[A-Za-z0-9])/g, ', ')
    .replace(/\s+([,.;:!?])/g, '$1')
    .replace(/\s{2,}/g, ' ')
    .trim()
}

export function isBrokenChinglishStitch(text: string | null | undefined): boolean {
  const s = sanitizeEnText(text)
  if (!s) return false
  const cjkCount = (s.match(/[\u4e00-\u9fff]/g) || []).length
  return cjkCount >= 2 || BROKEN_GLOSS_TOKEN_RE.test(s) && cjkCount >= 1
}

export function pickBiText(
  zhVal: string | null | undefined,
  enVal: string | null | undefined,
  fallback = '',
): string {
  const cleanZh = (zhVal && zhVal.trim()) || ''
  if (appLang.value === 'en') {
    const cleanEn = sanitizeEnText(enVal)
    if (cleanEn && !isBrokenChinglishStitch(cleanEn)) {
      return cleanEn
    }
    const strippedZh = cleanZh.replace(/^(?:【[^】]{2,18}】\s*)+/g, '').trim()
    return strippedZh || sanitizeEnText(fallback) || fallback
  }
  return cleanZh || sanitizeEnText(enVal) || fallback
}

export function stripMarkdownArtifacts(input: string | null | undefined): string {
  if (!input) return ''
  let s = String(input)
    .replace(/\[?R\d{2,4}\]?\s*[:：]?\s*/g, '')
    .replace(/[（(]\s*[、,，]?\s*(?:原始素材多?)?仅含?标题\s*[)）]/g, '')
    .replace(/[、,，]?\s*(?:原始素材多?)?仅含?标题(?:[，,。；:\s]*(?:细节待查原文|具体[^。；;]*))?[。.]?\s*/g, '')
    .replace(/注：原始素材仅含发布标题与同等简短摘要[^。]*。?/g, '')
    .replace(/已拦截\s*\d+\s*条无效引用(?:（[^）]*）)?[；;，,]?\s*/g, '')
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/^\s*\|?(?:\s*:?-{2,}:?\s*\|)+\s*$/gm, ' ')
    .replace(/\|/g, ' · ')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/__([^_]+)__/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
  s = s.replace(/(?:\s*·\s*){2,}/g, ' · ').replace(/\s+/g, ' ').trim()
  return s.replace(/^[·\s]+|[·\s]+$/g, '').trim()
}

export function truncateAtSentence(input: string | null | undefined, maxLen = 180): string {
  const s = stripMarkdownArtifacts(input).replace(/\s+/g, ' ').trim()
  if (!s) return ''
  if (s.length <= maxLen) return s
  const cut = s.slice(0, maxLen - 1)
  const minPos = Math.floor(maxLen * 0.45)
  let bestEnd = -1
  // Avoid breaking on numeric decimals such as 19.2% or $3.5B
  const endRe = /[。！？；!?]|(?<!\d)\.(?!\d)(?=\s|$|[”"）)\u4e00-\u9fa5])/g
  let m: RegExpExecArray | null
  while ((m = endRe.exec(cut)) !== null) {
    if (m.index >= minPos) {
      bestEnd = m.index
    }
  }
  if (bestEnd >= minPos) {
    return cut.slice(0, bestEnd + 1).trimEnd()
  }
  const openIdx = Math.max(cut.lastIndexOf('（'), cut.lastIndexOf('('))
  const closeIdx = Math.max(cut.lastIndexOf('）'), cut.lastIndexOf(')'))
  let trimmedCut = openIdx > closeIdx && openIdx >= Math.min(3, minPos) ? cut.slice(0, openIdx).trimEnd() : cut
  trimmedCut = trimmedCut.replace(/\.\s*$/, (m, off) => (/\d/.test(trimmedCut[off - 1] || '') ? '' : m))
  const clauseMatch = trimmedCut.match(/^(.+[，,;；：:\s])[^，,;；：:\s]{1,14}$/)
  if (clauseMatch && clauseMatch[1].length >= Math.floor(maxLen * 0.5)) {
    const cleanClause = clauseMatch[1].replace(/[，、,;；：:\s(（]+$/g, '').trimEnd()
    if (cleanClause) return `${cleanClause}…`
  }
  return trimmedCut.replace(/[，、,;；：:\s(（]+$/g, '').trimEnd() + '…'
}

export function formatWireHeadline(title: string | null | undefined): string {
  const s = stripMarkdownArtifacts(title)
  if (!s) return ''
  if (s.length >= 74 && !/[。！？!?…%”"）)元股亿万元美元]$/.test(s)) {
    return s.replace(/[，、,;:\s]+$/g, '') + '…'
  }
  return s
}

const ENTITY_EN_GLOSSARY: Record<string, string> = {
  '英伟达 (NVIDIA)': 'NVIDIA (NVDA)',
  '英伟达': 'NVIDIA (NVDA)',
  '台积电 (TSMC)': 'TSMC (TSM)',
  '台积电': 'TSMC (TSM)',
  'AMD (超威半导体)': 'AMD',
  'AMD': 'AMD',
  '英特尔 (Intel)': 'Intel (INTC)',
  '英特尔': 'Intel (INTC)',
  '中芯国际 (SMIC)': 'SMIC (00981.HK)',
  '中芯国际': 'SMIC',
  '存储芯片 (DRAM / HBM / NAND)': 'Memory Chips (DRAM / HBM / NAND)',
  '存储芯片': 'Memory Chips',
  '微软 (Microsoft)': 'Microsoft (MSFT)',
  '微软': 'Microsoft',
  '谷歌 (Google / Alphabet)': 'Google / Alphabet',
  '谷歌': 'Google',
  '亚马逊 (Amazon)': 'Amazon (AMZN)',
  '亚马逊': 'Amazon',
  '苹果 (Apple)': 'Apple (AAPL)',
  '苹果': 'Apple',
  '特斯拉 (Tesla)': 'Tesla (TSLA)',
  '特斯拉': 'Tesla',
  '腾讯 (Tencent)': 'Tencent (00700.HK)',
  '腾讯': 'Tencent',
  '阿里巴巴 (Alibaba)': 'Alibaba (09988.HK)',
  '阿里巴巴': 'Alibaba',
  '华为 (Huawei)': 'Huawei',
  '华为': 'Huawei',
  '字节跳动 (ByteDance)': 'ByteDance',
  '软银集团': 'SoftBank Group',
  '软银': 'SoftBank',
  'SK海力士': 'SK Hynix',
  '美联储 (Fed / FOMC)': 'Federal Reserve (FOMC)',
  '美联储': 'Federal Reserve (Fed)',
  '央行': 'Central Bank / PBOC',
  '欧洲央行': 'ECB',
  '日本央行': 'Bank of Japan',
  '霍尔木兹海峡': 'Strait of Hormuz',
  '黄金 (Gold / 避险金属)': 'Gold (Safe-Haven Metals)',
  '黄金': 'Gold',
  '原油 (Crude Oil / Brent / WTI)': 'Crude Oil (Brent / WTI)',
  '原油': 'Crude Oil',
}

export function translateEntityName(name: string | null | undefined): string {
  const raw = String(name || '').trim()
  if (!raw || appLang.value !== 'en') return raw
  return ENTITY_EN_GLOSSARY[raw] || raw
}

const TAG_EN_GLOSSARY: Record<string, string> = {
  '利好': 'Bullish',
  '偏多': 'Positive',
  '利空': 'Bearish',
  '利空承压': 'Bearish Pressure',
  '承压': 'Under Pressure',
  '中性': 'Neutral',
  '高分化': 'High Dispersion',
  '待核实': 'Pending Verification',
  '多空分化': 'Mixed / Divergent',
  '暂无可靠量化推演': 'Insufficient Quantitative Confidence',
  '官方证实': 'Official Confirmed',
  '多源印证': 'Multi-Source Corroborated',
  '单一信源': 'Single Source',
  '暂缺原文': 'No Direct Link',
  '核心要闻': 'Major Event',
  '常规动态': 'Standard Update',
}

export function translateTagLabel(label: string | null | undefined): string {
  const raw = String(label || '').trim()
  if (!raw || appLang.value !== 'en') return raw
  return TAG_EN_GLOSSARY[raw] || raw
}

export function translateMarketTag(market: string | null | undefined): string {
  const raw = String(market || '').trim()
  if (!raw || appLang.value !== 'en') return raw
  if (raw === 'A股') return 'A-Share'
  if (raw === '美股') return 'US'
  if (raw === '港股') return 'HK'
  return raw
}

const SOURCE_NAME_EN_PAIRS: Array<[string, string]> = [
  ['华尔街见闻 · 最热', 'WallStreetCN · Hot'],
  ['华尔街见闻 · 资讯', 'WallStreetCN · News'],
  ['华尔街见闻 · 快讯', 'WallStreetCN · Wire'],
  ['华尔街见闻 7×24 全球', 'WallStreetCN 7×24'],
  ['华尔街见闻 A股快讯', 'WallStreetCN A-Share'],
  ['华尔街见闻 科技/AI快讯', 'WallStreetCN AI Wire'],
  ['华尔街见闻', 'WallStreetCN'],
  ['财联社 · 电报', 'CLS Wire'],
  ['财联社', 'CLS'],
  ['IT之家 实时快讯', 'ITHome Wire'],
  ['IT之家', 'ITHome'],
  ['36氪', '36Kr'],
  ['证券时报', 'Securities Times'],
  ['第一财经', 'Yicai'],
  ['每日经济新闻', 'NBD'],
  ['东方财富', 'Eastmoney'],
  ['SEC EDGAR 官方披露', 'SEC EDGAR Filing'],
  ['OpenAI 官方动态', 'OpenAI Official'],
  ['NVIDIA 官方博客', 'NVIDIA Blog'],
  ['开源社区 / Hugging Face', 'Hugging Face Community'],
  ['AIHOT 前沿', 'AIHOT Frontier'],
  ['多源新闻汇总', 'Multi-Source Wire'],
  ['简报汇总', 'Briefing Digest'],
  ['直连 AI 雷达', 'Direct AI Radar'],
  ['官方披露', 'Official Filing'],
  ['实时快讯', 'Live Wire'],
  ['精选信源', 'Curated Source'],
]

function extractPublisherFromTitle(title: string | null | undefined): string {
  const s = String(title || '').trim()
  if (!s) return ''
  const m = s.match(/\s[-—|]\s([^|\-—]{2,28})$/)
  if (!m) return ''
  const cand = m[1].trim()
  if (!cand || /google\s*news/i.test(cand) || /^\d+$/.test(cand)) return ''
  return cand
}

export function translateSourceName(name: string | null | undefined, fallbackTitle?: string | null): string {
  const raw = String(name || '').trim()
  if (!raw) return ''
  if (/google\s*news/i.test(raw) || raw === '综合资讯') {
    const extracted = extractPublisherFromTitle(fallbackTitle)
    if (extracted) {
      return appLang.value === 'en' ? translateSourceName(extracted) : extracted
    }
    return appLang.value === 'en' ? 'International Media' : '国际媒体'
  }
  if (appLang.value !== 'en') return raw
  for (const [zh, en] of SOURCE_NAME_EN_PAIRS) {
    if (raw === zh) return en
  }
  let out = raw
  for (const [zh, en] of SOURCE_NAME_EN_PAIRS) {
    if (out.includes(zh)) {
      out = out.replace(zh, en)
    }
  }
  return out
}

const ENTITY_TYPE_MAP: Record<string, { zh: string; en: string }> = {
  company: { zh: '公司', en: 'Company' },
  person: { zh: '人物', en: 'Person' },
  org: { zh: '机构', en: 'Org' },
  organization: { zh: '机构', en: 'Org' },
  macro: { zh: '宏观', en: 'Macro' },
  sector: { zh: '行业', en: 'Sector' },
  commodity: { zh: '大宗商品', en: 'Commodity' },
  policy: { zh: '政策', en: 'Policy' },
}

export function translateEntityType(type: string | null | undefined): string {
  const key = String(type || '').trim().toLowerCase()
  if (!key) return ''
  const mapped = ENTITY_TYPE_MAP[key]
  if (mapped) return appLang.value === 'en' ? mapped.en : mapped.zh
  return String(type || '')
}

const EVIDENCE_STATUS_MAP: Record<string, { zh: string; en: string }> = {
  official_confirmed: { zh: '官方证实', en: 'Official' },
  multi_source: { zh: '多源交叉', en: 'Multi-Source' },
  single_source: { zh: '单一来源', en: 'Single Source' },
  needs_verification: { zh: '待核实', en: 'Unverified' },
}

export function translateEvidenceStatus(status: string | null | undefined): string {
  const key = String(status || '').trim().toLowerCase()
  if (!key) return ''
  const mapped = EVIDENCE_STATUS_MAP[key]
  if (mapped) return appLang.value === 'en' ? mapped.en : mapped.zh
  return String(status || '')
}

const PORTFOLIO_SECTOR_EN_MAP: Record<string, string> = {
  'AI 算力 / 半导体': 'AI Compute / Semis',
  '美股核心科技': 'US Mega-Cap Tech',
  '港股互联网': 'HKEX Internet',
  'CPO / 通信光模块': 'CPO / Optical Modules',
  '石油能源 / 油运': 'Oil & Tanker Shipping',
  '黄金与贵金属': 'Gold & Precious Metals',
  '银行 / 高股息红利': 'Banks / High Dividend',
  '出口链 / 消费电子': 'Exports / Consumer Tech',
  '网络安全 / 信创': 'Cybersecurity / Enterprise IT',
}

export function translatePortfolioSector(sector: string | null | undefined): string {
  const raw = String(sector || '').trim()
  if (!raw || appLang.value !== 'en') return raw
  return PORTFOLIO_SECTOR_EN_MAP[raw] || raw
}
