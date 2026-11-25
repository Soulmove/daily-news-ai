<script setup lang="ts">
import { computed } from 'vue'
import { BookmarkCheck, ShieldCheck, Sparkles, Target, X } from 'lucide-vue-next'
import { t } from '../core/i18n'

export type SoftAuthScenario = 'portfolio_saved' | 'prediction_vote' | 'qa_quota' | 'second_note'

const props = defineProps<{
  isOpen: boolean
  scenario: SoftAuthScenario
  remainingQuota?: number | null
}>()

const emit = defineEmits<{
  close: []
  'open-auth': [mode: 'register' | 'login']
}>()

const copy = computed(() => {
  switch (props.scenario) {
    case 'portfolio_saved':
      return {
        badge: t('持仓雷达云备份', 'Portfolio Radar'),
        title: t('你的持仓传导雷达已就绪，别让配置随手丢失', 'Your portfolio radar is ready — keep it synced'),
        desc: t(
          '免费注册只需 10 秒（仅需用户名 + 密码），即可多端加密同步自选股与持仓板块配置，每日接收专属传导追踪。',
          'Take 10 seconds to create a free account and sync your watchlist & portfolio sectors across devices.',
        ),
        cta: t('10 秒保存我的持仓雷达', 'Save My Portfolio Radar (10s)'),
        icon: ShieldCheck,
      }
    case 'prediction_vote':
      return {
        badge: t('前瞻预判已暂存', 'Forecast Staged'),
        title: t('你的预判已暂存，登录即可锁定胜率战绩', 'Your probability is staged — sign in to lock your record'),
        desc: t(
          '当前预判已保存在本机。登录后将正式计入全站群众共识池，并在到期结算后为你累积个人 Brier 校准战绩。',
          'Sign in to commit this vote into the live crowd pool and track your personal Brier calibration score.',
        ),
        cta: t('锁定我的预测并查看共识', 'Lock Prediction & View Consensus'),
        icon: Target,
      }
    case 'second_note':
      return {
        badge: t('研报笔记云端同步', 'Cloud Research Notes'),
        title: t('免费多源 AI 研报额度已用完，登录立即扩容', 'Unlock higher AI research limits & cloud sync'),
        desc: t(
          '你已在本机沉淀多条研报笔记。免费登录即可云端加密保存全部笔记与收藏，同时每日 AI 证据问答额度大幅扩容。',
          'You have saved multiple research notes locally. Sign in free for encrypted cloud backup and expanded daily AI Q&A quota.',
        ),
        cta: t('免费解锁更高额度 + 云端备份', 'Unlock Higher Quota + Cloud Backup'),
        icon: BookmarkCheck,
      }
    case 'qa_quota':
    default:
      return {
        badge: t('AI 证据问答额度已满', 'Daily Free Quota Used'),
        title: t('免费多源 AI 研报额度已用完，登录立即扩容', 'Free daily AI Q&A limit reached — unlock more for free'),
        desc: t(
          '游客每日体验额度已用尽。10 秒免费注册或登录账号，立即解锁每日 30 次多源证据问答与云端研究同步。',
          'Guest daily Q&A quota is used up. Sign in or create a free account in 10 seconds for 30 daily Q&As + cloud sync.',
        ),
        cta: t('免费解锁更高额度 + 云端备份', 'Unlock Higher Quota + Cloud Backup'),
        icon: Sparkles,
      }
  }
})
</script>

<template>
  <Teleport to="body">
    <div
      v-if="isOpen"
      class="fixed inset-0 z-[58] flex items-end sm:items-center justify-center p-0 sm:p-4 bg-black/45 backdrop-blur-xs"
      @click.self="emit('close')"
      @keydown.esc.prevent="emit('close')"
    >
      <div
        role="dialog"
        aria-modal="true"
        class="w-full sm:max-w-md rounded-t-3xl sm:rounded-3xl bg-white dark:bg-[#1C1C1E] border border-black/[0.08] dark:border-white/[0.12] shadow-2xl p-5 space-y-4 ios-fade-in"
      >
        <div class="flex items-start justify-between gap-3">
          <div class="flex items-center gap-2">
            <span class="inline-flex items-center justify-center w-8 h-8 rounded-xl bg-[#007AFF]/10 text-[#007AFF] dark:text-[#0A84FF] shrink-0">
              <component :is="copy.icon" class="w-4 h-4" :stroke-width="1.75" />
            </span>
            <span class="text-[11px] font-semibold uppercase tracking-wider text-[#007AFF] dark:text-[#0A84FF]">
              {{ copy.badge }}
            </span>
          </div>
          <button
            type="button"
            @click="emit('close')"
            class="w-8 h-8 inline-flex items-center justify-center rounded-full text-zinc-400 hover:bg-black/[0.05] dark:hover:bg-white/[0.08]"
            :aria-label="t('暂存本机，继续体验', 'Keep local and continue')"
          >
            <X class="w-4 h-4" :stroke-width="1.5" />
          </button>
        </div>

        <div class="space-y-2">
          <h3 class="text-[17px] font-bold leading-snug text-zinc-950 dark:text-white">
            {{ copy.title }}
          </h3>
          <p class="text-[13px] text-zinc-600 dark:text-zinc-300 leading-relaxed">
            {{ copy.desc }}
          </p>
        </div>

        <div class="flex flex-col gap-2 pt-1">
          <button
            type="button"
            @click="emit('open-auth', 'register')"
            class="ios-tap w-full min-h-[42px] px-4 py-2.5 rounded-2xl bg-[#007AFF] hover:bg-[#0066D6] text-white text-[13px] font-semibold transition-colors"
          >
            {{ copy.cta }}
          </button>
          <div class="flex items-center justify-between gap-2">
            <button
              type="button"
              @click="emit('close')"
              class="ios-tap flex-1 min-h-[38px] px-3 py-2 rounded-xl bg-[#F2F2F7] dark:bg-[#2C2C2E] text-zinc-700 dark:text-zinc-200 text-xs font-medium"
            >
              {{ t('暂存本机，继续体验', 'Keep Local & Continue') }}
            </button>
            <button
              type="button"
              @click="emit('open-auth', 'login')"
              class="ios-tap min-h-[38px] px-3 py-2 rounded-xl text-xs font-semibold text-[#007AFF] dark:text-[#0A84FF] hover:bg-[#007AFF]/10"
            >
              {{ t('已有账号登录', 'Sign In') }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>
