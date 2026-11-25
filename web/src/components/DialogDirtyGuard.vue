<script setup lang="ts">
import { AlertCircle } from 'lucide-vue-next'
import { t } from '../core/i18n'

defineProps<{
  open: boolean
}>()

const emit = defineEmits<{
  (e: 'confirm'): void
  (e: 'cancel'): void
}>()
</script>

<template>
  <div
    v-if="open"
    class="px-4 py-2.5 bg-amber-50 dark:bg-amber-950/60 border-b border-amber-200 dark:border-amber-800 flex flex-wrap items-center justify-between gap-2 text-xs"
    role="alert"
  >
    <div class="flex items-center gap-1.5 text-amber-900 dark:text-amber-200 font-medium">
      <AlertCircle class="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0" />
      <span>{{ t('弹窗内已有输入内容，确定放弃并关闭吗？', 'You have unsaved form input. Discard and close?') }}</span>
    </div>
    <div class="flex items-center gap-1.5 shrink-0">
      <button
        type="button"
        @click="emit('cancel')"
        class="px-2.5 py-1 rounded border border-amber-300 dark:border-amber-700 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-200 font-medium"
      >
        {{ t('继续填写', 'Keep Editing') }}
      </button>
      <button
        type="button"
        @click="emit('confirm')"
        class="px-2.5 py-1 rounded bg-red-600 text-white font-semibold hover:bg-red-700"
      >
        {{ t('放弃并关闭', 'Discard & Close') }}
      </button>
    </div>
  </div>
</template>
