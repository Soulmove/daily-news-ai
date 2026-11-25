/**
 * Global reactive store for zero-UGC structured 1-click reactions across Events,
 * Finance Impacts, and Predictions.
 */
import { reactive } from 'vue'
import {
  apiFetchReactionsBatch,
  apiSubmitReaction,
  loadAuthSession,
  type ReactionSummary,
  type ReactionTargetType,
} from './auth'

const ALLOWED_KEYS: Record<ReactionTargetType, readonly string[]> = {
  event: ['heavy', 'track', 'noise'],
  finance: ['bullish_cat', 'bearish_hedge', 'priced_in'],
  prediction: ['agree', 'disagree', 'neutral'],
}

const reactionMap = reactive<Record<string, ReactionSummary>>({})
const loadedKeys = new Set<string>()
let inflightBatches = 0

function makeKey(targetType: ReactionTargetType, targetId: string): string {
  return `${targetType}:${targetId}`
}

function defaultSummary(targetType: ReactionTargetType, targetId: string): ReactionSummary {
  const counts: Record<string, number> = {}
  for (const k of ALLOWED_KEYS[targetType]) counts[k] = 0
  return {
    target_type: targetType,
    target_id: targetId,
    counts,
    total: 0,
    my_reaction: null,
  }
}

export function getReactionSummary(targetType: ReactionTargetType, targetId: string): ReactionSummary {
  const cleanId = (targetId || '').trim()
  const key = makeKey(targetType, cleanId)
  return reactionMap[key] ?? defaultSummary(targetType, cleanId)
}

export function invalidateReactionsCache(): void {
  loadedKeys.clear()
}

export async function loadReactionsBatch(
  targetType: ReactionTargetType,
  ids: string[],
  options: { force?: boolean; token?: string | null } = {},
): Promise<void> {
  const uniqueIds = Array.from(new Set(ids.map((s) => (s || '').trim()).filter(Boolean)))
  const pending = options.force
    ? uniqueIds
    : uniqueIds.filter((id) => !loadedKeys.has(makeKey(targetType, id)))
  if (pending.length === 0) return

  const token = options.token ?? loadAuthSession()?.token ?? null
  for (let i = 0; i < pending.length; i += 80) {
    const chunk = pending.slice(i, i + 80)
    inflightBatches += 1
    try {
      const res = await apiFetchReactionsBatch(targetType, chunk, token)
      for (const id of chunk) {
        const fullKey = makeKey(targetType, id)
        loadedKeys.add(fullKey)
        const item = res.items?.[id]
        if (item) {
          reactionMap[fullKey] = item
        } else if (!reactionMap[fullKey]) {
          reactionMap[fullKey] = defaultSummary(targetType, id)
        }
      }
    } catch {
      // Non-blocking: UI still falls back cleanly to 0 counts
    } finally {
      inflightBatches = Math.max(0, inflightBatches - 1)
    }
  }
}

export async function toggleStructuredReaction(
  targetType: ReactionTargetType,
  targetId: string,
  reactionKey: string,
  token?: string | null,
): Promise<ReactionSummary> {
  const cleanId = (targetId || '').trim()
  const fullKey = makeKey(targetType, cleanId)
  const prev = reactionMap[fullKey]
    ? {
        ...reactionMap[fullKey],
        counts: { ...reactionMap[fullKey].counts },
      }
    : defaultSummary(targetType, cleanId)

  // Optimistic update (mirrors backend idempotent switch semantics)
  if (prev.my_reaction !== reactionKey) {
    const nextCounts = { ...prev.counts }
    if (prev.my_reaction && prev.my_reaction in nextCounts) {
      nextCounts[prev.my_reaction] = Math.max(0, Number(nextCounts[prev.my_reaction] || 0) - 1)
    }
    nextCounts[reactionKey] = Number(nextCounts[reactionKey] || 0) + 1
    const nextTotal = Object.values(nextCounts).reduce((acc, n) => acc + n, 0)
    reactionMap[fullKey] = {
      target_type: targetType,
      target_id: cleanId,
      counts: nextCounts,
      total: nextTotal,
      my_reaction: reactionKey,
    }
  }

  try {
    const res = await apiSubmitReaction(
      { target_type: targetType, target_id: cleanId, reaction_key: reactionKey },
      token ?? loadAuthSession()?.token ?? null,
    )
    if (res?.item) {
      reactionMap[fullKey] = res.item
      loadedKeys.add(fullKey)
      return res.item
    }
  } catch {
    reactionMap[fullKey] = prev
  }
  return reactionMap[fullKey] ?? prev
}

export function isReactionsBusy(): boolean {
  return inflightBatches > 0
}
