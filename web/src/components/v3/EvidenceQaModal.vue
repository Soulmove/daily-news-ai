<script setup lang="ts">
import { computed, ref, toRef, watch } from 'vue'
import { BookmarkPlus, ChevronDown, ExternalLink, FileText, KeyRound, RefreshCw, Sparkles, X } from 'lucide-vue-next'
import DialogDirtyGuard from '../DialogDirtyGuard.vue'
import SmartTime from '../SmartTime.vue'
import { useDialogBehavior } from '../../core/dialog'
import { t } from '../../core/i18n'
import { normalizeExternalUrl } from '../../core/legacyAdapter'
import { answerQuestionBounded, askEvidenceQa, type EvidenceQaResponse } from '../../core/qa'
import { loadAiClientConfig, saveAiClientConfig } from '../../core/storage'
import type {
  AiClientConfig,
  CatalystEvent,
  EntityProfile,
  MajorTopicSpotlight,
  ResearchNote,
  SmartEvent,
  StorylineDossier,
} from '../../core/types'

const props = defineProps<{
  isOpen: boolean
  contextEvent?: SmartEvent | null
  contextStoryline?: StorylineDossier | null
  contextEntity?: EntityProfile | null
  contextTopic?: MajorTopicSpotlight | null
  allEvents: SmartEvent[]
  topics?: MajorTopicSpotlight[]
  calendarEvents?: CatalystEvent[]
  dataCutoffAt?: string | null
  savedNotes: ResearchNote[]
  isLoggedIn?: boolean
  nowMs?: number
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'save-note', note: ResearchNote): void
  (e: 'delete-note', noteId: string): void
}>()

const dialogEl = ref<HTMLElement | null>(null)
const defaultQuestion = computed(() =>
  props.contextTopic
    ? t(`请梳理「${props.contextTopic.title}」的最新时间线、核心行程与潜在影响`, `Summarize timeline, itinerary & impact of "${props.contextTopic.title}"`)
    : t('近7天有哪些核心变化与未决分歧？', 'What are the key changes and unresolved conflicts in the past 7 days?'),
)
const question = ref(defaultQuestion.value)
const userEditedQuestion = ref(false)
const response = ref<EvidenceQaResponse | null>(null)
const savedBanner = ref(false)
const askingLive = ref(false)
const liveError = ref<string | null>(null)
const qaHistory = ref<{ role: string; content: string }[]>([])
const showKeySettings = ref(false)
const aiConfig = ref<AiClientConfig>(loadAiClientConfig())
const hasLiveKey = computed(() => Boolean(aiConfig.value.apiKey.trim()))
const effectiveNowMs = computed(() => props.nowMs ?? Date.now())

const hasDirtyForm = computed(() =>
  Boolean(showKeySettings.value || (userEditedQuestion.value && question.value.trim() && question.value.trim() !== defaultQuestion.value)),
)

const { dirtyConfirmOpen, onBackdropClick, onCloseButton, confirmDirtyDiscard, cancelDirtyClose } =
  useDialogBehavior({
    isOpen: toRef(props, 'isOpen'),
    containerRef: dialogEl,
    onClose: () => emit('close'),
    isDirty: () => hasDirtyForm.value,
  })

const scopeLabel = computed(() => {
  if (props.contextTopic) return `${t('超级专题：', 'Topic: ')}${props.contextTopic.title}`
  if (props.contextStoryline) return `${t('事件档案：', 'Dossier: ')}${props.contextStoryline.title}`
  if (props.contextEntity) return `${t('实体档案：', 'Entity: ')}${props.contextEntity.canonical_name}`
  if (props.contextEvent) return `${t('单条事件：', 'Event: ')}${props.contextEvent.title}`
  return t(
    `全站素材 (${props.allEvents.length} 条简报 · ${props.topics?.length || 0} 专题 · ${props.calendarEvents?.length || 0} 日程)`,
    `All Materials (${props.allEvents.length} briefs · ${props.topics?.length || 0} topics · ${props.calendarEvents?.length || 0} catalysts)`,
  )
})

function persistAiConfig() {
  saveAiClientConfig(aiConfig.value)
  showKeySettings.value = false
  liveError.value = null
}

function clearAiKey() {
  aiConfig.value = { ...aiConfig.value, apiKey: '' }
  saveAiClientConfig(aiConfig.value)
  liveError.value = null
}

async function askNow(customQ?: string, forceLocal = false) {
  if (customQ) {
    question.value = customQ
    userEditedQuestion.value = false
  }
  liveError.value = null
  savedBanner.value = false
  const ctx = {
    event: props.contextEvent,
    storyline: props.contextStoryline,
    entity: props.contextEntity,
    topic: props.contextTopic,
    allEvents: props.allEvents,
    topics: props.topics,
    calendarEvents: props.calendarEvents,
    dataCutoffAt: props.dataCutoffAt,
  }
  if (forceLocal) {
    response.value = answerQuestionBounded(question.value, ctx)
  }
  askingLive.value = true
  try {
    const qText = question.value.trim()
    const res = await askEvidenceQa(qText, aiConfig.value, ctx, {
      forceLocal: false,
      history: qaHistory.value.slice(-6),
    })
    response.value = res
    if (!forceLocal && qText) {
      qaHistory.value = [
        ...qaHistory.value.slice(-4),
        { role: 'user', content: qText },
        { role: 'assistant', content: res.answerMarkdown.slice(0, 600) },
      ]
    }
    return
  } catch (err) {
    liveError.value = t(
      `${err instanceof Error ? err.message : '问答请求失败'}，已自动回退至本地多源证据研判。`,
      `${err instanceof Error ? err.message : 'Q&A request failed'} — fell back to local evidence synthesis.`,
    )
    response.value = answerQuestionBounded(question.value, ctx)
  } finally {
    askingLive.value = false
  }
}

function parseInlineSegments(text: string): { text: string; kind: 'text' | 'bold' | 'italic' | 'code' }[] {
  const parts: { text: string; kind: 'text' | 'bold' | 'italic' | 'code' }[] = []
  const re = /(\*\*(.+?)\*\*|`([^`]+)`|\*([^*\n]+?)\*)/g
  let lastIdx = 0
  let match: RegExpExecArray | null
  const cleanOrphan = (s: string) => s.replace(/[*`]/g, '')
  while ((match = re.exec(text)) !== null) {
    if (match.index > lastIdx) {
      const seg = cleanOrphan(text.slice(lastIdx, match.index))
      if (seg) parts.push({ text: seg, kind: 'text' })
    }
    if (match[2] !== undefined) {
      parts.push({ text: match[2].replace(/[`*]/g, ''), kind: 'bold' })
    } else if (match[3] !== undefined) {
      parts.push({ text: match[3], kind: 'code' })
    } else if (match[4] !== undefined) {
      parts.push({ text: match[4].replace(/[`*]/g, ''), kind: 'italic' })
    }
    lastIdx = re.lastIndex
  }
  if (lastIdx < text.length) {
    const tail = cleanOrphan(text.slice(lastIdx))
    if (tail) parts.push({ text: tail, kind: 'text' })
  }
  return parts.length > 0 ? parts : [{ text: cleanOrphan(text), kind: 'text' }]
}

function parseAnswerBlocks(md: string): { kind: 'h3' | 'bullet' | 'p'; text: string }[] {
  return md
    .split(/\r?\n/)
    .map((ln) => ln.trim())
    .filter(Boolean)
    .map((ln) => {
      if (ln.startsWith('### ')) return { kind: 'h3' as const, text: ln.slice(4).trim() }
      if (ln.startsWith('- ')) return { kind: 'bullet' as const, text: ln.slice(2).trim() }
      return { kind: 'p' as const, text: ln }
    })
}

watch(
  () => [props.isOpen, props.contextEvent?.event_id, props.contextStoryline?.storyline_id, props.contextEntity?.entity_id, props.contextTopic?.topic_id],
  ([open]) => {
    if (open) {
      userEditedQuestion.value = false
      question.value = defaultQuestion.value
      void askNow(undefined, true)
    }
  },
)

function saveAsNote() {
  if (!response.value) return
  emit('save-note', {
    note_id: `note_${Date.now().toString(36)}`,
    target_type: props.contextStoryline
      ? 'storyline'
      : props.contextEntity
        ? 'entity'
        : props.contextEvent
          ? 'event'
          : 'qa',
    target_id:
      props.contextStoryline?.storyline_id ||
      props.contextEntity?.entity_id ||
      props.contextEvent?.event_id ||
      'global',
    title: scopeLabel.value,
    question: question.value,
    answer_markdown: response.value.answerMarkdown,
    evidence_urls: response.value.evidenceUrls.map((u) => u.url),
    data_cutoff_at: props.dataCutoffAt,
    created_at: new Date().toISOString(),
  })
  savedBanner.value = true
}
</script>

<template>
  <div
    v-if="isOpen"
    class="mac-drawer-backdrop"
    role="dialog"
    aria-modal="true"
    aria-labelledby="qa-modal-title"
    :aria-label="t('AI 证据问答', 'Evidence Q&A')"
    @click.self="onBackdropClick"
  >
    <div
      ref="dialogEl"
      tabindex="-1"
      class="mac-drawer-panel overflow-y-auto focus:outline-none"
    >
      <header class="sticky top-0 z-10 bg-white/95 dark:bg-[#1C1C1E]/95 backdrop-blur-md px-4 pt-2.5 pb-3 border-b border-black/[0.06] dark:border-white/[0.08]">
        <div class="w-9 h-1 rounded-full bg-zinc-300 dark:bg-zinc-600 mx-auto mb-2 sm:hidden" />
        <div class="flex items-center justify-between gap-2">
          <div class="flex items-center gap-2 min-w-0">
            <Sparkles class="w-4 h-4 text-[#007AFF] shrink-0" :stroke-width="1.5" />
            <h2 id="qa-modal-title" class="text-[16px] font-semibold text-zinc-950 dark:text-white truncate">
              {{ hasLiveKey ? t(`AI 问答 (${aiConfig.model})`, `AI Q&A (${aiConfig.model})`) : t('AI 证据问答', 'Evidence Q&A') }}
            </h2>
            <button
              type="button"
              @click="showKeySettings = !showKeySettings"
              class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-[#F2F2F7] dark:bg-[#2C2C2E] text-zinc-600 dark:text-zinc-300 shrink-0"
              :title="t('配置自定义模型', 'Custom LLM API')"
            >
              <KeyRound class="w-3 h-3" :stroke-width="1.5" />
              <span>{{ hasLiveKey ? t('自定义', 'BYOK') : t('模型', 'Model') }}</span>
            </button>
          </div>

          <button
            type="button"
            @click="onCloseButton"
            class="w-11 h-11 -mr-2 rounded-xl inline-flex items-center justify-center text-zinc-400 hover:text-zinc-900 dark:hover:text-white shrink-0"
            :aria-label="t('关闭', 'Close')"
          >
            <X class="w-5 h-5" :stroke-width="1.5" />
          </button>
        </div>
      </header>

      <DialogDirtyGuard
        :open="dirtyConfirmOpen"
        @confirm="confirmDirtyDiscard"
        @cancel="cancelDirtyClose"
      />

      <div class="p-4 sm:p-5 space-y-4 text-xs sm:text-sm">
        <div
          v-if="showKeySettings"
          class="rounded-xl border border-blue-200 dark:border-blue-800 bg-slate-50 dark:bg-slate-800/70 p-3.5 space-y-2.5 text-xs"
        >
          <div class="rounded-lg bg-white dark:bg-slate-900 border border-emerald-200/80 dark:border-emerald-800/70 px-3 py-2 flex items-center justify-between gap-2">
            <div>
              <div class="font-bold text-slate-900 dark:text-white">
                {{ t('镜信云端投研大模型（默认免配置）', 'MirrorBrief Cloud Research Engine (Default · Zero Setup)') }}
              </div>
              <div class="text-[11px] text-slate-500 dark:text-slate-400">
                {{ t('已默认启用云端多源证据检索与智能核验引擎，开箱即用。', 'Zero-setup cloud grounding and evidence verification is active by default.') }}
              </div>
            </div>
            <span v-if="!hasLiveKey" class="px-2 py-0.5 rounded-full bg-emerald-500/12 text-emerald-700 dark:text-emerald-300 text-[10px] font-semibold shrink-0">
              {{ t('当前使用中', 'Active') }}
            </span>
          </div>

          <details class="pt-0.5">
            <summary class="cursor-pointer select-none font-semibold text-slate-700 dark:text-slate-200">
              {{ t('高级自定义接口（可选，密钥仅保存于当前设备浏览器）', 'Advanced Custom API (Optional · Local Browser Only)') }}
            </summary>
            <div class="mt-2.5 space-y-2.5">
              <div class="grid grid-cols-1 sm:grid-cols-3 gap-2">
                <div class="relative inline-flex items-center w-full h-9 pl-2.5 pr-7 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white focus-within:ring-2 focus-within:ring-[#007AFF]/40">
                  <span class="pointer-events-none truncate">
                    {{
                      aiConfig.provider === 'gemini'
                        ? t('云端标准直连协议', 'Standard Native Protocol')
                        : t('OpenAI 兼容接口 (DeepSeek 等)', 'OpenAI-Compatible (DeepSeek / etc.)')
                    }}
                  </span>
                  <ChevronDown class="w-3.5 h-3.5 text-zinc-400 pointer-events-none absolute right-2" />
                  <select
                    v-model="aiConfig.provider"
                    :aria-label="t('API 协议类型', 'API Provider')"
                    class="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                  >
                    <option value="gemini">{{ t('云端标准直连协议', 'Standard Native Protocol') }}</option>
                    <option value="openai_compat">{{ t('OpenAI 兼容接口 (DeepSeek 等)', 'OpenAI-Compatible (DeepSeek / etc.)') }}</option>
                  </select>
                </div>
                <input
                  v-model="aiConfig.model"
                  type="text"
                  :placeholder="t('自定义模型名，如 deepseek-chat', 'Custom model, e.g. deepseek-chat')"
                  class="h-9 px-2.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white"
                />
                <input
                  v-model="aiConfig.apiKey"
                  type="password"
                  :placeholder="t('填入您的个人 API Key...', 'Paste personal API Key...')"
                  class="h-9 px-2.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white"
                />
              </div>
              <input
                v-if="aiConfig.provider === 'openai_compat'"
                v-model="aiConfig.baseUrl"
                type="url"
                :placeholder="t('Base URL，如 https://api.deepseek.com/v1', 'Base URL, e.g. https://api.deepseek.com/v1')"
                class="w-full h-9 px-2.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white"
              />
              <div class="flex items-center gap-2">
                <button type="button" @click="persistAiConfig" class="px-3 py-1.5 rounded-lg bg-blue-600 text-white font-semibold hover:bg-blue-700">
                  {{ t('保存自定义配置', 'Save Custom Config') }}
                </button>
                <button v-if="hasLiveKey" type="button" @click="clearAiKey" class="px-3 py-1.5 rounded-lg border border-red-200 text-red-600 hover:bg-red-50">
                  {{ t('恢复默认云端引擎', 'Use Default Engine') }}
                </button>
              </div>
            </div>
          </details>
        </div>

        <div class="flex flex-wrap gap-1.5 text-xs">
          <button type="button" @click="askNow(t('特朗普访华与深圳APEC最新行程进展是什么？', 'What is the latest on Trump visit & APEC Shenzhen?'))" class="px-2.5 py-1 rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800">
            {{ t('特朗普访华 / APEC 行程？', 'Trump Visit / APEC?') }}
          </button>
          <button type="button" @click="askNow(t('近7天有哪些核心变化？', 'What changed over the past 7 days?'))" class="px-2.5 py-1 rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800">
            {{ t('近7天有哪些核心变化？', '7-Day Core Changes?') }}
          </button>
          <button type="button" @click="askNow(t('主要正反依据和分歧在哪里？', 'What are the bull/bear arguments and conflicts?'))" class="px-2.5 py-1 rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800">
            {{ t('正反依据与分歧在哪里？', 'Evidence & Conflicts?') }}
          </button>
          <button type="button" @click="askNow(t('证伪条件与下个验证节点是什么？', 'What are the invalidation triggers & next catalysts?'))" class="px-2.5 py-1 rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800">
            {{ t('证伪条件与验证节点？', 'Invalidation & Catalysts?') }}
          </button>
        </div>

        <form @submit.prevent="askNow()" class="flex items-stretch gap-2">
          <input
            v-model="question"
            @input="userEditedQuestion = true"
            type="text"
            :placeholder="t('输入想核查的问题或关键词（如 特朗普行程 / 英伟达 / 美联储 / Qwen）...', 'Ask a question or keyword (e.g. APEC / NVDA / FOMC / Qwen)...')"
            :aria-label="t('证据问答输入', 'Evidence Q&A question')"
            class="min-w-0 flex-1 h-10 px-3 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-xs sm:text-sm text-slate-900 dark:text-white"
          />
          <button
            type="submit"
            :disabled="askingLive || !question.trim()"
            class="inline-flex items-center justify-center gap-1.5 px-3.5 sm:px-4 h-10 rounded-lg bg-blue-600 text-white text-xs sm:text-sm font-semibold hover:bg-blue-700 disabled:opacity-60 shrink-0 whitespace-nowrap"
          >
            <RefreshCw v-if="askingLive" class="w-3.5 h-3.5 animate-spin" />
            <span>{{ askingLive ? t('推理中...', 'Thinking...') : t('提交提问', 'Ask AI') }}</span>
          </button>
        </form>

        <div v-if="liveError" class="rounded-lg bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 px-3 py-2 text-xs text-red-700 dark:text-red-300">
          {{ liveError }}
        </div>

        <div v-if="response" class="rounded-xl border border-blue-200 dark:border-blue-900 bg-blue-50/40 dark:bg-blue-950/20 p-4 space-y-3">
          <div class="space-y-2 text-xs sm:text-sm text-slate-800 dark:text-slate-100 leading-relaxed">
            <template v-for="(block, bi) in parseAnswerBlocks(response.answerMarkdown)" :key="bi">
              <h4 v-if="block.kind === 'h3'" class="text-sm font-bold text-slate-900 dark:text-white pt-1 first:pt-0">
                {{ block.text.replace(/[*`]/g, '') }}
              </h4>
              <div v-else-if="block.kind === 'bullet'" class="flex items-start gap-2 pl-1">
                <span class="mt-1.5 w-1.5 h-1.5 rounded-full bg-blue-600 dark:bg-blue-400 shrink-0" />
                <span>
                  <template v-for="(seg, si) in parseInlineSegments(block.text)" :key="si">
                    <strong v-if="seg.kind === 'bold'" class="font-semibold text-slate-900 dark:text-white">{{ seg.text }}</strong>
                    <code v-else-if="seg.kind === 'code'" class="px-1 py-0.5 rounded bg-slate-200/70 dark:bg-slate-800 font-mono text-[11px]">{{ seg.text }}</code>
                    <em v-else-if="seg.kind === 'italic'" class="italic text-slate-700 dark:text-slate-200">{{ seg.text }}</em>
                    <span v-else>{{ seg.text }}</span>
                  </template>
                </span>
              </div>
              <p v-else>
                <template v-for="(seg, si) in parseInlineSegments(block.text)" :key="si">
                  <strong v-if="seg.kind === 'bold'" class="font-semibold text-slate-900 dark:text-white">{{ seg.text }}</strong>
                  <code v-else-if="seg.kind === 'code'" class="px-1 py-0.5 rounded bg-slate-200/70 dark:bg-slate-800 font-mono text-[11px]">{{ seg.text }}</code>
                  <em v-else-if="seg.kind === 'italic'" class="italic text-slate-700 dark:text-slate-200">{{ seg.text }}</em>
                  <span v-else>{{ seg.text }}</span>
                </template>
              </p>
            </template>
          </div>

          <div v-if="response.evidenceUrls.length > 0" class="space-y-1 pt-2 border-t border-blue-200/70 dark:border-blue-900">
            <div class="text-xs font-bold text-slate-700 dark:text-slate-300">
              {{ t(`支持原文索引 (${response.evidenceUrls.length})：`, `Supporting Sources (${response.evidenceUrls.length}):`) }}
            </div>
            <div class="flex flex-wrap gap-2">
              <template v-for="u in response.evidenceUrls" :key="u.url">
                <a
                  v-if="normalizeExternalUrl(u.url)"
                  :href="normalizeExternalUrl(u.url)!"
                  target="_blank"
                  rel="noopener noreferrer"
                  @click.stop
                  class="inline-flex items-center gap-1 px-2 py-1 rounded border border-blue-200 dark:border-blue-800 bg-white dark:bg-slate-900 text-xs text-blue-700 dark:text-blue-300 hover:underline"
                >
                  <span>{{ u.label }}</span>
                  <ExternalLink class="w-3 h-3" />
                </a>
                <span v-else class="inline-flex items-center gap-1 px-2 py-1 rounded border border-slate-200 dark:border-slate-700 text-xs text-slate-400">
                  {{ u.label }}（{{ t('暂无直链', 'No Link') }}）
                </span>
              </template>
            </div>
          </div>

          <div class="rounded-lg bg-amber-50/80 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900 p-2.5 text-xs text-amber-900 dark:text-amber-200 space-y-1">
            <div class="font-semibold">
              {{ t(`证据边界与缺失说明（截止 ${response.dataCutoffAt}）：`, `Evidence Boundaries (Cutoff ${response.dataCutoffAt}):`) }}
            </div>
            <ul class="list-disc list-inside space-y-0.5">
              <li v-for="(m, idx) in response.missingDisclosures" :key="idx">{{ m }}</li>
            </ul>
          </div>

          <div class="flex items-center justify-between pt-1">
            <span v-if="savedBanner" class="text-xs font-semibold text-emerald-700 dark:text-emerald-300">
              {{ isLoggedIn ? t('已保存至云端研究笔记！', 'Saved & synced to cloud notes!') : t('已保存至本机研究笔记！', 'Saved to browser notes!') }}
            </span>
            <span v-else class="text-[11px] text-slate-500">
              {{
                isLoggedIn
                  ? t('研究笔记已关联云端账号自动同步。', 'Notes sync automatically to your cloud account.')
                  : t('仅保存在本机浏览器，登录后可跨设备同步。', 'Saved locally in browser; sign in to sync across devices.')
              }}
            </span>
            <button
              type="button"
              @click="saveAsNote"
              class="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-emerald-600 text-white text-xs font-semibold hover:bg-emerald-700"
            >
              <BookmarkPlus class="w-3.5 h-3.5" />
              <span>{{ t('保存为研究笔记', 'Save as Note') }}</span>
            </button>
          </div>
        </div>

        <div class="pt-3 border-t border-slate-200 dark:border-slate-800 space-y-2.5">
          <div class="flex items-center justify-between">
            <h3 class="text-xs sm:text-sm font-bold text-slate-900 dark:text-white flex items-center gap-1.5">
              <FileText class="w-4 h-4 text-slate-600" />
              <span>
                {{
                  isLoggedIn
                    ? t(`我的研究笔记 (${savedNotes.length}) · 云端同步`, `My Research Notes (${savedNotes.length}) · Synced`)
                    : t(`我的研究笔记 (${savedNotes.length})`, `My Research Notes (${savedNotes.length})`)
                }}
              </span>
            </h3>
          </div>

          <p v-if="savedNotes.length === 0" class="text-xs text-slate-500">
            {{ t('暂无保存的研究笔记。', 'No saved research notes yet.') }}
          </p>
          <div v-else class="space-y-2">
            <div
              v-for="n in savedNotes"
              :key="n.note_id"
              class="rounded-xl border border-slate-200 dark:border-slate-800 p-3 space-y-1 text-xs"
            >
              <div class="flex items-center justify-between gap-2">
                <span class="font-bold text-slate-900 dark:text-white">{{ n.title }}</span>
                <div class="flex items-center gap-2">
                  <span class="text-slate-400 tabular-nums"><SmartTime :iso="n.created_at" :now-ms="effectiveNowMs" /></span>
                  <button type="button" @click="emit('delete-note', n.note_id)" class="text-red-600 hover:underline">{{ t('删除', 'Delete') }}</button>
                </div>
              </div>
              <p v-if="n.question" class="text-blue-700 dark:text-blue-300 font-medium">{{ t('问：', 'Q: ') }}{{ n.question }}</p>
              <p class="whitespace-pre-line text-slate-600 dark:text-slate-300 line-clamp-4">{{ n.answer_markdown.replace(/\*\*|\*|`/g, '') }}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
