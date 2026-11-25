<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { AlertTriangle, FileText, Scale, ShieldAlert } from 'lucide-vue-next'
import AppShell from '../components/AppShell.vue'
import { syncHtmlLangAttr, t } from '../core/i18n'
import { readDarkMode, writeDarkMode } from '../core/storage'

const isDark = ref(readDarkMode())

function toggleDark() {
  isDark.value = !isDark.value
  document.documentElement.classList.toggle('dark', isDark.value)
  writeDarkMode(isDark.value)
}

onMounted(() => {
  syncHtmlLangAttr()
  document.documentElement.classList.toggle('dark', isDark.value)
})
</script>

<template>
  <AppShell
    active-page="about"
    :is-dark="isDark"
    :show-history-button="false"
    :show-bookmarks-button="false"
    :show-refresh-button="false"
    @toggle-dark="toggleDark"
  >
    <div class="max-w-4xl mx-auto space-y-5">
      <section class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 sm:p-7 space-y-2">
        <div class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900 text-xs font-semibold">
          <FileText class="w-3.5 h-3.5" />
          <span>{{ t('镜信用户协议（2026 年 11 月）', 'MirrorBrief Terms of Service (Nov 2026)') }}</span>
        </div>
        <h1 class="text-xl sm:text-2xl font-bold text-slate-900 dark:text-white">
          {{ t('镜信（MirrorBrief）服务使用条款与理性边界说明', 'MirrorBrief Terms of Service & Honest Boundaries') }}
        </h1>
        <p class="text-xs sm:text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
          {{ t(
            '欢迎使用镜信平台（包括网页工作台及 Android 原生 App）。注册、登录或使用本平台服务，即视为您已阅读并同意本协议以下条款。',
            'Welcome to MirrorBrief (Web Workbench and Native Android App). By creating an account or using the service, you agree to the terms below.',
          ) }}
        </p>
      </section>

      <div class="space-y-4 text-xs sm:text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
        <section class="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 space-y-2">
          <h2 class="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
            <Scale class="w-4 h-4 text-blue-600 shrink-0" />
            <span>{{ t('一、平台服务内容与信息定位', '1. Service Scope & Provenance') }}</span>
          </h2>
          <p v-if="t('zh', 'en') === 'zh'">
            镜信是一个多源实时资讯聚合与 AI 辅助研判工具，面向用户提供全球重要时政外交、前沿科技与 AI 模型动态、以及宏观事件对股市板块的因果推演参考。平台所有条目均尽可能标注原始出处、首次披露时间及多源核实状态，供用户跨视角浏览、打破算法信息茧房。
          </p>
          <p v-else>
            MirrorBrief is a real-time multi-source news intelligence and AI analysis platform covering global politics, frontier AI/tech breakthroughs, and macro market transmission chains, with transparent provenance and source verification timestamps.
          </p>
        </section>

        <section class="rounded-xl border border-amber-200 dark:border-amber-900 bg-amber-50/40 dark:bg-amber-950/20 p-5 space-y-2">
          <h2 class="text-base font-bold text-amber-950 dark:text-amber-200 flex items-center gap-2">
            <AlertTriangle class="w-4 h-4 text-amber-600 shrink-0" />
            <span>{{ t('二、金融分析与投资免责声明', '2. Financial & Investment Disclaimer') }}</span>
          </h2>
          <p v-if="t('zh', 'en') === 'zh'">
            本平台「股市传导」模块、新闻卡片内嵌市场预测区间以及 AI 辩证观点所展示的行业影响、涨跌幅敏感区间与演化节点，均基于公开资讯与历史宏观传导逻辑自动生成，<strong>仅用于帮助用户建立事件分析框架与信息研判参考，不构成任何具体证券、基金、期货或加密资产的买卖要约或投资建议</strong>。市场存在高度不确定性，您据此作出的任何交易决策及盈亏由您自行承担。
          </p>
          <p v-else>
            All sector transmission chains, historical sensitivity ranges, and scenario simulations in the Markets module are generated from public filings and macro reasoning strictly for analytical reference. <strong>They do not constitute investment, trading, or financial advice.</strong>
          </p>
        </section>

        <section class="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 space-y-2">
          <h2 class="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
            <ShieldAlert class="w-4 h-4 text-rose-600 shrink-0" />
            <span>{{ t('三、账号注册与合理使用规范', '3. Account Registration & Fair Use') }}</span>
          </h2>
          <ul v-if="t('zh', 'en') === 'zh'" class="list-disc pl-4 space-y-1">
            <li>为防止恶意机器批量占用资源，平台对同一设备及同一网络在特定时间窗内的注册次数实施频控限制；禁止使用自动化脚本批量注册、恶意爬取接口或发起拒绝服务攻击。</li>
            <li>注册时绑定手机号或邮箱为可选项，但若未绑定将无法通过自助流程找回遗忘密码；请妥善保管账号凭据。</li>
            <li>外部新闻原报道版权归原发布机构或作者所有，镜信仅作摘要整理、双语辅助阅读与原文直链索引；如有版权或内容异议，可通过页脚「意见反馈」联系我们处理。</li>
          </ul>
          <ul v-else class="list-disc pl-4 space-y-1">
            <li>Registration rate-limits apply per device and IP window; automated bulk signups and abusive API scraping are prohibited.</li>
            <li>Linking an email or phone number is optional on signup, but recommended for self-service password recovery.</li>
            <li>Original news article copyrights belong to their respective publishers; MirrorBrief provides verified synthesis and direct source links.</li>
          </ul>
        </section>
      </div>

      <div class="flex flex-wrap items-center gap-3 text-xs">
        <a href="./index.html" class="px-4 py-2 rounded-lg bg-slate-900 text-white dark:bg-white dark:text-slate-900 font-semibold">{{ t('返回镜信首页', 'Back to MirrorBrief') }}</a>
        <a href="./privacy.html" class="px-4 py-2 rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800">{{ t('查看《隐私政策》', 'Privacy Policy') }}</a>
        <a href="./help.html" class="px-4 py-2 rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800">{{ t('查看使用帮助 FAQ', 'Help & FAQ') }}</a>
      </div>
    </div>
  </AppShell>
</template>
