import type { CatalystEvent } from './types'

function formatIcsUtc(iso: string): string | null {
  const ms = Date.parse(iso)
  if (!Number.isFinite(ms)) return null
  const d = new Date(ms)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}T${pad(d.getUTCHours())}${pad(d.getUTCMinutes())}${pad(d.getUTCSeconds())}Z`
}

function escapeIcsText(raw: string): string {
  return raw
    .replace(/\\/g, '\\\\')
    .replace(/\r?\n/g, '\\n')
    .replace(/,/g, '\\,')
    .replace(/;/g, '\\;')
}

/**
 * Generate a standard RFC 5545 .ics calendar payload for confirmed-date catalyst events.
 */
export function generateCatalystIcs(events: CatalystEvent[]): string {
  const nowUtc = formatIcsUtc(new Date().toISOString()) || '20261115T000000Z'
  const lines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//Insight Pro V3//Catalyst Calendar//ZH',
    'CALSCALE:GREGORIAN',
    'METHOD:PUBLISH',
  ]

  for (const ev of events) {
    if (!ev.scheduled_at) continue
    const dtStart = formatIcsUtc(ev.scheduled_at)
    if (!dtStart) continue
    const endMs = Date.parse(ev.scheduled_at) + 60 * 60 * 1000
    const dtEnd = formatIcsUtc(new Date(endMs).toISOString()) || dtStart
    const descParts = [
      `来源：${ev.source_name}`,
      ev.watch_variable ? `关注变量：${ev.watch_variable}` : '',
      ev.pre_expectation ? `事前预期：${ev.pre_expectation}` : '',
      ev.actual_result ? `实际结果：${ev.actual_result}` : '',
      ev.source_url ? `出处链接：${ev.source_url}` : '',
    ].filter(Boolean)

    lines.push('BEGIN:VEVENT')
    lines.push(`UID:${escapeIcsText(ev.calendar_id)}@insightpro.local`)
    lines.push(`DTSTAMP:${nowUtc}`)
    lines.push(`DTSTART:${dtStart}`)
    lines.push(`DTEND:${dtEnd}`)
    lines.push(`SUMMARY:${escapeIcsText(ev.title)}`)
    lines.push(`DESCRIPTION:${escapeIcsText(descParts.join('\n'))}`)
    if (ev.source_url) {
      lines.push(`URL:${ev.source_url}`)
    }
    lines.push('END:VEVENT')
  }

  lines.push('END:VCALENDAR')
  return `${lines.join('\r\n')}\r\n`
}

export function triggerIcsDownload(filename: string, content: string): void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return
  const blob = new Blob([content], { type: 'text/calendar;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
