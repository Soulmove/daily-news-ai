<script setup lang="ts">
import { ref, toRef } from 'vue'
import { Calendar, CheckCircle2, Compass, Sparkles, TrendingUp, X } from 'lucide-vue-next'
import { useDialogBehavior } from '../../core/dialog'
import { appLang, t } from '../../core/i18n'
import { WATCHLIST_PRESETS, type WatchlistPresetTemplate } from '../../core/thumbnails'

const props = defineProps<{
  isOpen: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'apply-preset', preset: WatchlistPresetTemplate): void
  (e: 'jump-tab', tab: 'finance' | 'calendar'): void
}>()

const dialogEl = ref<HTMLElement | null>(null)
const selectedPresetId = ref<WatchlistPresetTemplate['id']>('stock')

useDialogBehavior({
  isOpen: toRef(props, 'isOpen'),
  containerRef: dialogEl,
  onClose: () => emit('close'),
})

function handleApplyAndClose() {
  const chosen = WATCHLIST_PRESETS.find((p) => p.id === selectedPresetId.value)
  if (chosen) emit('apply-preset', chosen)
  emit('close')
}
</script>

<template>
  <div
    v-if="isOpen"
    class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/60 backdrop-blur-xs"
    role="dialog"
    aria-modal="true"
    aria-labelledby="onboarding-modal-title"
    @click.self="emit('close')"
  >
    <div
      ref="dialogEl"
      tabindex="-1"
      class="w-full max-w-2xl rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-2xl overflow-hidden outline-none"
    >
      <div class="px-5 py-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between gap-3">
        <div class="flex items-center gap-2.5">
          <img
            :src="'./icon.svg'"
            alt="镜信 MirrorBrief"
            class="w-8 h-8 rounded-lg border border-slate-200 dark:border-slate-700 bg-[#FAFAFA] shrink-0"
          />
          <div>
            <h2 id="onboarding-modal-title" class="text-base font-bold text-slate-900 dark:text-white">
              {{ t('3 步上手镜信（每天 3 分钟高效看透大事）', 'Quick Start: 3 Steps to Master MirrorBrief') }}
            </h2>
            <p class="text-xs text-slate-500 dark:text-slate-400">
              {{ t('随时可跳过，也可在账号/帮助菜单中再次打开本引导', 'Skip anytime or reopen from your Account / Help menu') }}
            </p>
          </div>
        </div>
        <button
          type="button"
          @click="emit('close')"
          class="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800"
          :aria-label="t('关闭引导', 'Close guide')"
        >
          <X class="w-4 h-4" />
        </button>
      </div>

      <div class="p-5 space-y-4 max-h-[78vh] overflow-y-auto">
        <!-- 3-Step Core Workflow Overview -->
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
          <button
            type="button"
            @click="emit('jump-tab', 'finance'); emit('close')"
            class="text-left rounded-xl border border-slate-200/90 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-800/40 hover:border-blue-300 dark:hover:border-blue-700 p-3 space-y-1.5 transition-colors"
          >
            <div class="inline-flex items-center gap-1.5 font-bold text-blue-700 dark:text-blue-300">
              <TrendingUp class="w-4 h-4" />
              <span>{{ t('1. 点假设看影响', '1. Trace Scenarios') }}</span>
            </div>
            <p class="text-slate-600 dark:text-slate-300 leading-relaxed">
              {{ t('点开卡片里的「股市传导 / 观点对照」，一眼看懂利好承压行业与条件情景。', 'Open Market Impact or 3-Perspective Compare to gauge sector effects.') }}
            </p>
          </button>

          <div class="rounded-xl border border-indigo-200/90 dark:border-indigo-800/80 bg-indigo-50/50 dark:bg-indigo-950/20 p-3 space-y-1.5">
            <div class="inline-flex items-center gap-1.5 font-bold text-indigo-700 dark:text-indigo-300">
              <Sparkles class="w-4 h-4" />
              <span>{{ t('2. 套用关注词模板', '2. Pick a Focus Pack') }}</span>
            </div>
            <p class="text-slate-600 dark:text-slate-300 leading-relaxed">
              {{ t('下面任选一套身份预设，系统自动置顶关联事件并标注「为什么推荐给你」。', 'Select a role template below to personalize Top Picks and reasons.') }}
            </p>
          </div>

          <button
            type="button"
            @click="emit('jump-tab', 'calendar'); emit('close')"
            class="text-left rounded-xl border border-slate-200/90 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-800/40 hover:border-emerald-300 dark:hover:border-emerald-700 p-3 space-y-1.5 transition-colors"
          >
            <div class="inline-flex items-center gap-1.5 font-bold text-emerald-700 dark:text-emerald-300">
              <Calendar class="w-4 h-4" />
              <span>{{ t('3. 订阅催化日历', '3. Subscribe Catalysts') }}</span>
            </div>
            <p class="text-slate-600 dark:text-slate-300 leading-relaxed">
              {{ t('在「催化日历」追踪未来 48h 重点催化日程，并在账号里绑定邮箱接收早报摘要。', 'Track upcoming 48h catalysts in the Calendar tab or bind email for daily digests.') }}
            </p>
          </button>
        </div>

        <!-- Watchlist Preset Selector -->
        <div class="space-y-2">
          <div class="flex items-center justify-between">
            <h3 class="text-xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">
              {{ t('选择你的关注词起始模板（一键注入，可随时增删）', 'Choose a Watchlist Starter Pack') }}
            </h3>
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
            <button
              v-for="preset in WATCHLIST_PRESETS"
              :key="preset.id"
              type="button"
              @click="selectedPresetId = preset.id"
              class="text-left rounded-xl border p-3 space-y-1.5 transition-all"
              :class="
                selectedPresetId === preset.id
                  ? 'border-blue-600 bg-blue-50/70 dark:border-blue-500 dark:bg-blue-950/35 ring-2 ring-blue-500/20'
                  : 'border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700'
              "
            >
              <div class="flex items-center justify-between gap-1">
                <span class="text-xs font-bold text-slate-900 dark:text-white">
                  {{ appLang === 'en' ? preset.labelEn : preset.label }}
                </span>
                <CheckCircle2
                  v-if="selectedPresetId === preset.id"
                  class="w-4 h-4 text-blue-600 dark:text-blue-400 shrink-0"
                />
              </div>
              <p class="text-[11px] text-slate-600 dark:text-slate-400 leading-snug">
                {{ appLang === 'en' ? preset.descEn : preset.desc }}
              </p>
              <div class="flex flex-wrap gap-1 pt-0.5">
                <span
                  v-for="it in preset.items.slice(0, 3)"
                  :key="it.id"
                  class="px-1.5 py-0.2 rounded bg-white/80 dark:bg-slate-800 text-[10px] text-slate-600 dark:text-slate-300 border border-slate-200/70 dark:border-slate-700"
                >
                  {{ it.label }}
                </span>
              </div>
            </button>
          </div>
        </div>
      </div>

      <div class="px-5 py-3.5 border-t border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950/50 flex flex-wrap items-center justify-between gap-2">
        <button
          type="button"
          @click="emit('close')"
          class="px-3 py-1.5 rounded-lg text-xs font-medium text-slate-600 dark:text-slate-300 hover:bg-slate-200/70 dark:hover:bg-slate-800"
        >
          {{ t('先自己逛逛', 'Skip for Now') }}
        </button>
        <button
          type="button"
          @click="handleApplyAndClose"
          class="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold bg-slate-900 text-white dark:bg-white dark:text-slate-900 hover:opacity-90"
        >
          <Compass class="w-3.5 h-3.5" />
          <span>{{ t('应用模板并开始今日简报', 'Apply Pack & Start Reading') }}</span>
        </button>
      </div>
    </div>
  </div>
</template>
