export interface EditorialOverrideItem {
  key: string
  target_type: 'event' | 'wire'
  event_id?: string
  title?: string
  title_fingerprint?: string
  severity_override?: 'S' | 'A' | 'B' | null
  heavy_reason_tag?: string | null
  pinned?: boolean
  hidden?: boolean
  updated_by?: string
  updated_at?: string
}

export interface EditorialOverridesDoc {
  updated_at: string | null
  items: Record<string, EditorialOverrideItem>
}

export function titleFingerprint(title: string | null | undefined): string {
  return String(title || '')
    .toLowerCase()
    .replace(/[\s\-_·:：,，.。!！?？()（）\[\]【】'"]+/g, '')
    .slice(0, 40)
}

function findMatchingOverride(
  item: { event_id?: string; id?: string; title?: string; title_zh?: string },
  overridesList: EditorialOverrideItem[],
): EditorialOverrideItem | null {
  const id = String(item.event_id || item.id || '').trim()
  const fp = titleFingerprint(item.title_zh || item.title)
  for (const ov of overridesList) {
    if (id && ov.event_id && ov.event_id === id) return ov
    if (fp && ov.title_fingerprint && ov.title_fingerprint === fp) return ov
    if (id && ov.key && ov.key === id) return ov
  }
  return null
}

export function applyEditorialOverridesToEvents<
  T extends {
    event_id?: string
    title?: string
    title_zh?: string
    severity_tier?: string
    severity_label?: string
    heavy_reason_tag?: string | null
    importance?: string
  },
>(events: T[], doc?: EditorialOverridesDoc | null): T[] {
  const map = doc?.items
  if (!map || typeof map !== 'object') return events
  const list = Object.values(map).filter((ov) => ov && ov.target_type !== 'wire')
  if (list.length === 0) return events

  const pinnedItems: T[] = []
  const normalItems: T[] = []
  for (const ev of events) {
    const ov = findMatchingOverride(ev, list)
    if (!ov) {
      normalItems.push(ev)
      continue
    }
    if (ov.hidden) continue
    const patched: T = { ...ev }
    if (ov.severity_override === 'S' || ov.severity_override === 'A') {
      patched.severity_tier = ov.severity_override
      patched.severity_label = ov.severity_override === 'S' ? 'S级重磅' : 'A级要闻'
      patched.importance = 'high'
      if (ov.heavy_reason_tag) patched.heavy_reason_tag = ov.heavy_reason_tag
    } else if (ov.severity_override === 'B') {
      patched.severity_tier = 'B'
      patched.severity_label = 'B级常规'
      patched.importance = 'normal'
      patched.heavy_reason_tag = null
    }
    if (ov.pinned) pinnedItems.push(patched)
    else normalItems.push(patched)
  }
  return pinnedItems.length > 0 ? [...pinnedItems, ...normalItems] : normalItems
}

export function applyEditorialOverridesToWire<
  T extends {
    id?: string
    title?: string
    severity_tier?: string
    heavy_reason_tag?: string | null
    importance?: string
  },
>(items: T[], doc?: EditorialOverridesDoc | null): T[] {
  const map = doc?.items
  if (!map || typeof map !== 'object') return items
  const list = Object.values(map).filter((ov) => ov && ov.target_type === 'wire')
  if (list.length === 0) return items

  const pinnedItems: T[] = []
  const normalItems: T[] = []
  for (const it of items) {
    const ov = findMatchingOverride(it, list)
    if (!ov) {
      normalItems.push(it)
      continue
    }
    if (ov.hidden) continue
    const patched: T = { ...it }
    if (ov.severity_override === 'S' || ov.severity_override === 'A') {
      patched.severity_tier = ov.severity_override
      patched.importance = 'high'
      if (ov.heavy_reason_tag) patched.heavy_reason_tag = ov.heavy_reason_tag
    } else if (ov.severity_override === 'B') {
      patched.severity_tier = 'B'
      patched.importance = 'normal'
      patched.heavy_reason_tag = null
    }
    if (ov.pinned) pinnedItems.push(patched)
    else normalItems.push(patched)
  }
  return pinnedItems.length > 0 ? [...pinnedItems, ...normalItems] : normalItems
}
