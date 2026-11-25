<script setup lang="ts">
import { ref, watch } from 'vue'
import { Check, ImagePlus, RotateCcw, Sparkles, X } from 'lucide-vue-next'
import {
  AVATAR_PRESETS,
  compressAvatarFileToDataUrl,
  estimateDataUrlBytes,
} from '../core/avatars'
import { useDialogBehavior } from '../core/dialog'
import { t } from '../core/i18n'
import UserAvatar from './UserAvatar.vue'

const props = defineProps<{
  isOpen: boolean
  currentAvatar?: string | null
  username?: string | null
  role?: string | null
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'select', avatar: string): void
}>()

const dialogEl = ref<HTMLElement | null>(null)
const fileInputEl = ref<HTMLInputElement | null>(null)
const draftAvatar = ref<string>(props.currentAvatar || '')
const uploadBusy = ref(false)
const uploadError = ref('')
const compressionInfo = ref('')

watch(
  () => props.isOpen,
  (open) => {
    if (open) {
      draftAvatar.value = props.currentAvatar || ''
      uploadError.value = ''
      if (draftAvatar.value.startsWith('data:image/')) {
        const kb = (estimateDataUrlBytes(draftAvatar.value) / 1024).toFixed(1)
        compressionInfo.value = t(`已上传自定义头像 · ${kb} KB`, `Custom photo · ${kb} KB`)
      } else {
        compressionInfo.value = ''
      }
    }
  },
)

const { requestClose } = useDialogBehavior({
  isOpen: () => props.isOpen,
  containerRef: dialogEl,
  onClose: () => emit('close'),
})

function choosePreset(presetId: string) {
  draftAvatar.value = presetId
  uploadError.value = ''
  compressionInfo.value = ''
  emit('select', presetId)
  emit('close')
}

function resetDefault() {
  draftAvatar.value = ''
  uploadError.value = ''
  compressionInfo.value = ''
  emit('select', '')
  emit('close')
}

async function onFileSelected(ev: Event) {
  const input = ev.target as HTMLInputElement | null
  const file = input?.files?.[0]
  if (!file) return
  uploadBusy.value = true
  uploadError.value = ''
  try {
    const res = await compressAvatarFileToDataUrl(file, 15 * 1024)
    draftAvatar.value = res.dataUrl
    const kb = (res.byteSize / 1024).toFixed(1)
    compressionInfo.value = `${res.width}×${res.height} ${res.format.toUpperCase()} · ${kb} KB`
    emit('select', res.dataUrl)
    emit('close')
  } catch (err) {
    uploadError.value =
      err instanceof Error ? err.message : t('图片压缩或裁剪失败，请换一张重试', 'Failed to crop or compress image')
  } finally {
    uploadBusy.value = false
    if (input) input.value = ''
  }
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="isOpen"
      class="fixed inset-0 z-[70] flex items-end sm:items-center justify-center sm:p-4 bg-slate-950/60 backdrop-blur-xs ios-fade-in"
      role="dialog"
      aria-modal="true"
      aria-labelledby="avatar-picker-title"
      @click.self="requestClose('backdrop')"
      data-testid="avatar-picker-modal"
    >
      <div
        ref="dialogEl"
        tabindex="-1"
        class="w-full sm:max-w-lg rounded-t-2xl sm:rounded-2xl bg-white dark:bg-[#1C1C1E] border border-black/[0.08] dark:border-white/[0.1] shadow-2xl overflow-hidden focus:outline-none max-h-[88vh] flex flex-col"
      >
        <header class="px-5 py-3.5 border-b border-black/[0.06] dark:border-white/[0.08] flex items-center justify-between gap-2 shrink-0">
          <div class="flex items-center gap-2 font-bold text-zinc-950 dark:text-white text-[15px]">
            <Sparkles class="w-4 h-4 text-[#007AFF]" :stroke-width="1.75" />
            <h2 id="avatar-picker-title">{{ t('自定义头像 · 高定矢量馆', 'Customize Avatar') }}</h2>
          </div>
          <button
            type="button"
            @click="requestClose('button')"
            class="w-8 h-8 rounded-lg inline-flex items-center justify-center text-zinc-500 hover:bg-black/[0.05] dark:hover:bg-white/[0.08]"
            :aria-label="t('关闭头像选择弹窗', 'Close avatar picker')"
          >
            <X class="w-4 h-4" />
          </button>
        </header>

        <div class="p-5 space-y-4 overflow-y-auto text-xs">
          <!-- Preview + Upload Banner -->
          <div class="rounded-2xl bg-[#F5F5F7] dark:bg-zinc-900/90 border border-black/[0.05] dark:border-white/[0.08] p-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div class="flex items-center gap-3 min-w-0">
              <UserAvatar
                :avatar="draftAvatar"
                :username="username"
                :role="role"
                size="xl"
              />
              <div class="min-w-0 space-y-1">
                <div class="text-[13px] font-bold text-zinc-950 dark:text-white truncate">
                  {{ username ? `@${username}` : t('当前预览效果', 'Current Preview') }}
                </div>
                <p class="text-[11px] text-zinc-500 dark:text-zinc-400">
                  {{
                    compressionInfo ||
                    t('本地自动居中裁剪为 160×160（<15KB），云端多端实时同步', 'Auto-cropped 160×160 (<15KB) · Cloud Synced')
                  }}
                </p>
              </div>
            </div>

            <div class="flex items-center gap-2 shrink-0">
              <input
                ref="fileInputEl"
                type="file"
                accept="image/png,image/jpeg,image/webp"
                class="hidden"
                data-testid="avatar-file-input"
                @change="onFileSelected"
              />
              <button
                type="button"
                @click="fileInputEl?.click()"
                :disabled="uploadBusy"
                class="ios-tap inline-flex items-center gap-1.5 min-h-[36px] px-3 rounded-xl bg-[#007AFF] hover:bg-[#0066D6] text-white font-semibold shadow-xs disabled:opacity-50 whitespace-nowrap"
                data-testid="avatar-upload-btn"
              >
                <ImagePlus class="w-3.5 h-3.5" :stroke-width="1.8" />
                <span>{{ uploadBusy ? t('裁剪压缩中...', 'Processing...') : t('上传照片 (<15KB)', 'Upload Photo') }}</span>
              </button>
              <button
                type="button"
                @click="resetDefault"
                class="ios-tap inline-flex items-center gap-1 min-h-[36px] px-2.5 rounded-xl bg-white dark:bg-zinc-800 border border-black/[0.08] dark:border-white/[0.1] text-zinc-700 dark:text-zinc-200 font-medium whitespace-nowrap"
                :title="t('恢复系统默认高定矢量头像', 'Reset to default vector avatar')"
              >
                <RotateCcw class="w-3.5 h-3.5" :stroke-width="1.6" />
                <span>{{ t('默认', 'Reset') }}</span>
              </button>
            </div>
          </div>

          <p
            v-if="uploadError"
            class="rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 px-3 py-2 text-rose-700 dark:text-rose-300 font-medium"
          >
            {{ uploadError }}
          </p>

          <!-- 12 Curated Built-in Vector Presets -->
          <div class="space-y-2">
            <div class="flex items-center justify-between text-[11px] font-semibold text-zinc-500 dark:text-zinc-400">
              <span>{{ t('方式 A · 镜信 12 款高定矢量主题头像（点击即刻切换）', '12 Bespoke Geometric SVG Presets') }}</span>
              <span class="tabular-nums">{{ AVATAR_PRESETS.length }} {{ t('款', 'Styles') }}</span>
            </div>

            <div class="grid grid-cols-3 sm:grid-cols-4 gap-2.5">
              <button
                v-for="preset in AVATAR_PRESETS"
                :key="preset.id"
                type="button"
                @click="choosePreset(preset.id)"
                class="ios-tap group relative flex flex-col items-center gap-1.5 p-2.5 rounded-2xl border text-center transition-all"
                :class="
                  draftAvatar === preset.id
                    ? 'border-[#007AFF] bg-[#007AFF]/[0.06] dark:bg-[#0A84FF]/15 shadow-xs'
                    : 'border-black/[0.07] dark:border-white/[0.08] bg-white dark:bg-zinc-900/60 hover:border-[#007AFF]/50 hover:-translate-y-0.5'
                "
                :data-testid="`avatar-preset-${preset.id}`"
              >
                <span
                  v-if="draftAvatar === preset.id"
                  class="absolute top-1.5 right-1.5 w-4 h-4 rounded-full bg-[#007AFF] text-white inline-flex items-center justify-center"
                >
                  <Check class="w-2.5 h-2.5" :stroke-width="2.5" />
                </span>
                <UserAvatar :avatar="preset.id" size="lg" />
                <span class="text-[11px] font-semibold text-zinc-800 dark:text-zinc-200 truncate max-w-full">
                  {{ t(preset.nameZh, preset.nameEn) }}
                </span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>
