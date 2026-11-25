<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Database, KeyRound, Lock, ShieldCheck, Trash2 } from 'lucide-vue-next'
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
          <ShieldCheck class="w-3.5 h-3.5" />
          <span>{{ t('镜信隐私政策（2026 年 11 月）', 'MirrorBrief Privacy Policy (Nov 2026)') }}</span>
        </div>
        <h1 class="text-xl sm:text-2xl font-bold text-slate-900 dark:text-white">
          {{ t('我们如何收集、加密保护与管理您的个人数据', 'How We Collect, Encrypt & Protect Your Data') }}
        </h1>
        <p class="text-xs sm:text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
          {{ t(
            '镜信（MirrorBrief）尊重并保护每位用户的个人隐私。本政策以透明、直白的语言说明我们收集哪些信息、这些信息存放在哪里、如何加密，以及您如何随时清理或注销账号。',
            'MirrorBrief respects your privacy. This policy explains transparently what data we store, how it is encrypted, and how you can clear local state or permanently delete your account.',
          ) }}
        </p>
      </section>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <section class="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 space-y-2">
          <h2 class="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
            <Database class="w-4 h-4 text-blue-600 shrink-0" />
            <span>{{ t('一、我们收集哪些数据', '1. Data We Collect') }}</span>
          </h2>
          <ul v-if="t('zh', 'en') === 'zh'" class="text-xs sm:text-sm text-slate-600 dark:text-slate-300 space-y-1.5 leading-relaxed list-disc pl-4">
            <li><strong>账号基本信息</strong>：注册时填写的用户名、昵称（可选），以及您主动选填或绑定的手机号/电子邮箱（仅用于登录与找回密码）。</li>
            <li><strong>个人投研同步数据</strong>：仅当您登录账号后，系统才会同步您的关注词（Watchlist）、收藏夹、稍后深读、个人研报笔记、自建日历催化事件及屏蔽词设置。</li>
            <li><strong>安全风控日志</strong>：为防止自动化脚本恶意批量注册与暴力破解，后端会记录脱敏的设备标识（随机生成匿名 ID）、登录时间戳与请求 IP（用于频控与安全审计，不用于广告追踪）。</li>
          </ul>
          <ul v-else class="text-xs sm:text-sm text-slate-600 dark:text-slate-300 space-y-1.5 leading-relaxed list-disc pl-4">
            <li><strong>Account Profile</strong>: Username, optional display name, and optional email/phone for recovery.</li>
            <li><strong>Synced Research State</strong>: When signed in, your watchlist, bookmarks, read-later items, research notes, and custom catalysts sync to your encrypted cloud vault.</li>
            <li><strong>Abuse Prevention Logs</strong>: Anonymous device IDs, login timestamps, and rate-limiting IPs solely for anti-bot security—never advertising.</li>
          </ul>
        </section>

        <section class="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 space-y-2">
          <h2 class="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
            <KeyRound class="w-4 h-4 text-amber-600 shrink-0" />
            <span>{{ t('二、AI 问答与本地数据说明', '2. Zero-Key Architecture & Local Storage') }}</span>
          </h2>
          <ul v-if="t('zh', 'en') === 'zh'" class="text-xs sm:text-sm text-slate-600 dark:text-slate-300 space-y-1.5 leading-relaxed list-disc pl-4">
            <li><strong>全站免填 Key 开箱即用</strong>：全球情报检索、多源交叉核验与双语精译均由<strong>镜信云端智能引擎</strong>自动化完成，普通用户无需配置任何第三方 API 密钥。</li>
            <li><strong>可选自有密钥仅存本地</strong>：如果您在高级追问设置中自行填入了第三方大模型 API Key，该密钥<strong>仅保存在您当前浏览器的 localStorage 本地存储中</strong>，云端同步接口会自动过滤并剥离该字段，<strong>绝不会上传或保存至我们的服务器</strong>。</li>
            <li>未登录访客的所有阅读进度、收藏与偏好同样仅保存在本地浏览器，不上传任何服务器。</li>
          </ul>
          <ul v-else class="text-xs sm:text-sm text-slate-600 dark:text-slate-300 space-y-1.5 leading-relaxed list-disc pl-4">
            <li><strong>Zero Setup Required</strong>: Global ingestion, verification, and bilingual compilation run automatically via MirrorBrief Cloud Engine.</li>
            <li><strong>Optional BYOK Keys Stay Local</strong>: If you provide a custom LLM key for interactive Q&amp;A, it stays strictly in browser <code class="font-mono">localStorage</code> and is stripped before cloud sync.</li>
            <li>Guest preferences, bookmarks, and reading counts remain strictly on-device until you sign in.</li>
          </ul>
        </section>

        <section class="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 space-y-2">
          <h2 class="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
            <Lock class="w-4 h-4 text-emerald-600 shrink-0" />
            <span>{{ t('三、云同步加密与传输安全说明', '3. Transport & At-Rest Encryption') }}</span>
          </h2>
          <ul v-if="t('zh', 'en') === 'zh'" class="text-xs sm:text-sm text-slate-600 dark:text-slate-300 space-y-1.5 leading-relaxed list-disc pl-4">
            <li><strong>传输加密</strong>：全站及私有云服务均通过 HTTPS/TLS 加密通道传输。</li>
            <li><strong>静态加密存储</strong>：您的关注词、收藏夹、研究笔记等个人研究数据在写入私有云存储前，均经过服务端高强度对称加密保护，数据库文件中不留存明文研报内容。</li>
            <li><strong>口令防护</strong>：登录密码采用行业标准的加盐单向不可逆哈希算法存储与校验，支持绑定手机号或邮箱进行自助验证码重置密码。</li>
          </ul>
          <ul v-else class="text-xs sm:text-sm text-slate-600 dark:text-slate-300 space-y-1.5 leading-relaxed list-disc pl-4">
            <li><strong>In Transit</strong>: Protected via HTTPS/TLS encrypted transport.</li>
            <li><strong>At Rest</strong>: Synced personal payloads are strongly encrypted server-side before persistence—no plaintext notes are stored at rest.</li>
            <li><strong>Password Security</strong>: Credentials use industry-standard salted irreversible hashing, with self-service OTP recovery via bound email or phone.</li>
          </ul>
        </section>

        <section class="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 space-y-2">
          <h2 class="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
            <Trash2 class="w-4 h-4 text-rose-600 shrink-0" />
            <span>{{ t('四、如何管理或删除您的账号与数据', '4. Managing or Deleting Your Data') }}</span>
          </h2>
          <ul v-if="t('zh', 'en') === 'zh'" class="text-xs sm:text-sm text-slate-600 dark:text-slate-300 space-y-1.5 leading-relaxed list-disc pl-4">
            <li><strong>清除本地缓存</strong>：您可以在浏览器设置或账号面板中清除当前设备的本地阅读记录、收藏缓存与可选自定义密钥。</li>
            <li><strong>停用或彻底删除云端账号</strong>：您可通过导航栏「意见反馈」联系站内管理员申请注销账号及彻底清除对应云端加密载荷，我们将在核实身份后及时清理库内相关记录与绑定联系方式。</li>
          </ul>
          <ul v-else class="text-xs sm:text-sm text-slate-600 dark:text-slate-300 space-y-1.5 leading-relaxed list-disc pl-4">
            <li><strong>Local Reset</strong>: Clear browser site storage or account cache anytime to wipe local device state.</li>
            <li><strong>Cloud Deletion</strong>: Contact us via the <strong>Feedback</strong> center to permanently erase your account and encrypted cloud payload.</li>
          </ul>
        </section>
      </div>

      <div class="flex flex-wrap items-center gap-3 text-xs">
        <a href="./index.html" class="px-4 py-2 rounded-lg bg-slate-900 text-white dark:bg-white dark:text-slate-900 font-semibold">{{ t('返回镜信首页', 'Back to MirrorBrief') }}</a>
        <a href="./terms.html" class="px-4 py-2 rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800">{{ t('查看《用户协议》', 'Terms of Service') }}</a>
        <a href="./help.html" class="px-4 py-2 rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800">{{ t('查看使用帮助 FAQ', 'Help & FAQ') }}</a>
      </div>
    </div>
  </AppShell>
</template>
