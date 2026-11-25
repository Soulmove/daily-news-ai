<script setup lang="ts">
import { computed } from 'vue'
import { formatUnifiedTime } from '../core/time'

const props = defineProps<{
  iso?: string | null
  ingestedIso?: string | null
  nowMs: number
  prefix?: string
  suffix?: string
  fallback?: string
  compactMobile?: boolean
}>()

const formatted = computed(() => formatUnifiedTime(props.iso, props.nowMs, props.fallback, props.ingestedIso))

const compactSplit = computed(() => {
  if (!props.compactMobile) return null
  const txt = formatted.value.text
  for (const marker of [' 发布)', ' pub)']) {
    const idx = txt.indexOf(marker)
    if (idx !== -1 && idx + marker.length === txt.length) {
      return {
        before: txt.slice(0, idx),
        hidden: marker.slice(0, -1),
        after: ')',
      }
    }
  }
  return null
})
</script>

<template>
  <time :datetime="formatted.iso" :title="formatted.title" class="tabular-nums">
    <template v-if="prefix">{{ prefix }}</template><template v-if="compactSplit">{{ compactSplit.before }}<span class="hidden sm:inline">{{ compactSplit.hidden }}</span>{{ compactSplit.after }}</template><template v-else>{{ formatted.text }}</template><template v-if="suffix">{{ suffix }}</template>
  </time>
</template>
