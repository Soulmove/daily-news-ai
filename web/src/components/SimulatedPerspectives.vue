<script setup lang="ts">
import { Bot, ChevronDown, ChevronUp, Info } from 'lucide-vue-next'
import SmartTime from './SmartTime.vue'
import { t } from '../core/i18n'
import type { SimulatedCommentsDoc } from '../core/types'

defineProps<{
  isOpen: boolean
  loading: boolean
  doc: SimulatedCommentsDoc | null
  expectedBatchId: string
  nowMs?: number
}>()

const emit = defineEmits<{
  (e: 'toggle'): void
}>()
</script>

<template>
  <section
    class="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden"
    aria-labelledby="ai-perspectives-heading"
  >
    <button
      type="button"
      @click="emit('toggle')"
      :aria-expanded="isOpen"
      class="w-full px-4 sm:px-5 py-3.5 flex items-center justify-between gap-3 text-left hover:bg-slate-50 dark:hover:bg-slate-800/60 transition-colors"
    >
      <div class="min-w-0">
        <div class="flex flex-wrap items-center gap-2">
          <Bot class="w-4 h-4 text-slate-600 dark:text-slate-400 shrink-0" />
          <h2 id="ai-perspectives-heading" class="text-sm sm:text-base font-bold text-slate-900 dark:text-white">
            {{ t('AI 模拟观点（角色推演）', 'AI Simulated Perspectives') }}
          </h2>
          <span class="px-2 py-0.5 rounded text-[11px] font-medium bg-slate-100 text-slate-700 border border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700">
            {{ t('非真实读者评论 · 默认折叠', 'Not Real User Comments · Collapsed') }}
          </span>
        </div>
        <p class="text-xs text-slate-500 dark:text-slate-400 mt-1">
          {{ t('与当前简报同批生成，展开后按需加载多视角推演。', 'Generated alongside this briefing; expands on demand.') }}
        </p>
      </div>
      <div class="flex items-center gap-1.5 text-xs font-medium text-blue-600 dark:text-blue-400 shrink-0">
        <span>{{ isOpen ? t('收起', 'Collapse') : t('展开参考', 'Expand') }}</span>
        <ChevronUp v-if="isOpen" class="w-4 h-4" />
        <ChevronDown v-else class="w-4 h-4" />
      </div>
    </button>

    <div v-if="isOpen" class="px-4 sm:px-5 pb-4 pt-2 border-t border-slate-200 dark:border-slate-800 space-y-3">
      <div v-if="loading" class="py-6 text-center text-xs sm:text-sm text-slate-500 dark:text-slate-400">
        {{ t('正在加载 AI 模拟观点...', 'Loading AI perspectives...') }}
      </div>

      <div
        v-else-if="!doc || (doc.status !== 'ok' && doc.status !== 'v3_dialectic_grounded') || doc.comments.length === 0"
        class="rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 p-4 text-xs sm:text-sm text-slate-600 dark:text-slate-300"
      >
        <p class="font-medium text-slate-800 dark:text-slate-200">
          {{ t('当前批次未生成 AI 模拟观点。', 'No AI perspectives generated for this batch.') }}
        </p>
      </div>

      <div v-else class="space-y-2.5">
        <div class="rounded-lg bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-900 px-3 py-2 text-xs text-amber-900 dark:text-amber-200 flex items-start gap-2">
          <Info class="w-4 h-4 shrink-0 mt-0.5" />
          <p>
            {{
              doc?.disclaimer ||
                t(
                  '声明：本栏目内容完全由 AI 基于当前简报材料进行多视角角色模拟生成，不代表真实网友观点、社会公众舆论或任何被讨论人物/机构本人的正式发言。',
                  'Disclaimer: AI-simulated multi-angle perspectives generated strictly from current briefing materials; does not represent real public comments or official statements.',
                )
            }}
          </p>
        </div>
        <div class="text-[11px] text-slate-500 dark:text-slate-400 flex flex-wrap gap-x-3">
          <span v-if="doc.generated_at">{{ t('生成于 ', 'Generated ') }}<SmartTime :iso="doc.generated_at" :now-ms="nowMs ?? Date.now()" /></span>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div
            v-for="item in doc.comments"
            :key="item.id"
            class="rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-800/40 p-3 space-y-1.5"
          >
            <div class="flex items-center justify-between gap-2 text-xs">
              <span class="font-semibold text-slate-900 dark:text-white">
                {{ item.role }}
              </span>
              <span class="px-1.5 py-0.5 rounded bg-slate-200/70 text-slate-700 dark:bg-slate-700 dark:text-slate-200 text-[11px]">
                {{ item.perspective_tag || item.stance }}
              </span>
            </div>
            <p class="text-xs sm:text-sm text-slate-700 dark:text-slate-300 leading-relaxed">
              {{ item.content }}
            </p>
            <div v-if="item.pro_argument || item.con_argument || item.key_unknown || item.next_catalyst" class="pt-1.5 border-t border-slate-200/70 dark:border-slate-700/70 space-y-1 text-[11px] leading-relaxed">
              <p v-if="item.pro_argument" class="text-emerald-800 dark:text-emerald-300">
                <strong class="font-semibold">{{ t('支持路径：', 'Bull Case: ') }}</strong>{{ item.pro_argument }}
              </p>
              <p v-if="item.con_argument" class="text-rose-800 dark:text-rose-300">
                <strong class="font-semibold">{{ t('反向质疑：', 'Bear Case: ') }}</strong>{{ item.con_argument }}
              </p>
              <p v-if="item.key_unknown" class="text-amber-800 dark:text-amber-300">
                <strong class="font-semibold">{{ t('关键未知：', 'Key Unknown: ') }}</strong>{{ item.key_unknown }}
              </p>
              <p v-if="item.next_catalyst" class="text-blue-800 dark:text-blue-300">
                <strong class="font-semibold">{{ t('验证节点：', 'Next Catalyst: ') }}</strong>{{ item.next_catalyst }}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
