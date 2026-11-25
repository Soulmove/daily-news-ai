<script setup lang="ts">
import { SearchX } from 'lucide-vue-next'
import { t } from '../core/i18n'

defineProps<{
  query?: string
  hasExtraFilters?: boolean
}>()

const emit = defineEmits<{
  (e: 'reset'): void
  (e: 'clear-query'): void
  (e: 'clear-filters-only'): void
}>()
</script>

<template>
  <div class="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-7 sm:p-8 text-center space-y-3 shadow-xs">
    <div class="w-10 h-10 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-400 mx-auto flex items-center justify-center">
      <SearchX class="w-5 h-5" />
    </div>
    <p class="text-sm font-semibold text-slate-800 dark:text-slate-100">
      {{
        query?.trim()
          ? t(
              `没找到「${query.trim()}」相关事件。试试：清空筛选 / 换个关键词 / 查看全部事件`,
              `No matching items for "${query.trim()}". Try clearing filters, changing keywords, or viewing all events.`,
            )
          : t('当前筛选条件下暂无匹配内容。', 'No matching items under the current filters.')
      }}
    </p>
    <div class="flex flex-wrap justify-center gap-2 pt-1">
      <button
        v-if="query?.trim()"
        type="button"
        @click="emit('clear-query')"
        class="px-3.5 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 text-xs font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800"
      >
        {{ t('换个关键词 / 清空搜索', 'Clear Search') }}
      </button>
      <button
        v-if="hasExtraFilters"
        type="button"
        @click="emit('clear-filters-only')"
        class="px-3.5 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 text-xs font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800"
      >
        {{ t('清空筛选', 'Clear Filters') }}
      </button>
      <button
        type="button"
        @click="emit('reset')"
        class="px-3.5 py-1.5 rounded-lg bg-slate-900 dark:bg-blue-600 text-white text-xs font-semibold hover:bg-slate-800 dark:hover:bg-blue-700"
      >
        {{ t('查看全部事件', 'View All Items') }}
      </button>
    </div>
  </div>
</template>
