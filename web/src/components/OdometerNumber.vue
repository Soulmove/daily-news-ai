<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    value: number | string
    prefix?: string
    suffix?: string
    decimals?: number
  }>(),
  {
    prefix: '',
    suffix: '',
  },
)

const displayText = computed(() => {
  if (typeof props.decimals === 'number' && typeof props.value === 'number' && Number.isFinite(props.value)) {
    return props.value.toFixed(props.decimals)
  }
  return props.value
})

const rollDir = ref<'up' | 'down' | null>(null)
const rollKey = ref(0)

watch(
  () => props.value,
  (nextVal, prevVal) => {
    if (nextVal === prevVal) return
    const nNext = typeof nextVal === 'number' ? nextVal : Number.parseFloat(String(nextVal).replace(/[^0-9.-]/g, ''))
    const nPrev = typeof prevVal === 'number' ? prevVal : Number.parseFloat(String(prevVal ?? '').replace(/[^0-9.-]/g, ''))
    if (Number.isFinite(nNext) && Number.isFinite(nPrev)) {
      rollDir.value = nNext >= nPrev ? 'up' : 'down'
    } else {
      rollDir.value = 'up'
    }
    rollKey.value += 1
  },
)
</script>

<template>
  <span class="inline-flex items-baseline overflow-hidden tabular-nums align-baseline">
    <span
      :key="rollKey"
      class="inline-block"
      :class="rollDir === 'up' ? 'jx-odo-up' : rollDir === 'down' ? 'jx-odo-down' : ''"
    >{{ prefix }}{{ displayText }}{{ suffix }}</span>
  </span>
</template>
