export function centerPillIntoView(e?: Event | null): void {
  const el = e?.currentTarget as HTMLElement | null | undefined
  if (!el || typeof el.scrollIntoView !== 'function') return
  try {
    el.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' })
  } catch {
    el.scrollIntoView()
  }
}
