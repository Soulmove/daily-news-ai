/**
 * Resolves static data & historical archive URLs.
 * Uses `VITE_DATA_BASE_URL` (e.g. https://data.mirrorinfo.xyz) when configured at build time,
 * cleanly falling back to relative `./` resolution on local dev or legacy single-host setups.
 */
export function getDataBaseUrl(): string {
  const raw = (import.meta as unknown as { env?: Record<string, string> }).env?.VITE_DATA_BASE_URL
  if (raw && raw.trim()) {
    return raw.trim().replace(/\/+$/, '')
  }
  return ''
}

export function resolveDataUrl(relPath: string, cacheBust = false): string {
  const clean = relPath.replace(/^\/+/, '').replace(/^\.\//, '')
  const configuredBase = getDataBaseUrl()
  const base = configuredBase
    ? `${configuredBase}/${clean}`
    : typeof window !== 'undefined' && window.location
      ? new URL(clean, window.location.href).toString()
      : `./${clean}`
  if (!cacheBust) return base
  const sep = base.includes('?') ? '&' : '?'
  return `${base}${sep}_v=${Date.now()}`
}
