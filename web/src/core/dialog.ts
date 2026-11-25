/**
 * B5 Unified Dialog & Drawer Accessibility Manager:
 * - Stack-ordered Escape dismissal (closes topmost dialog only)
 * - Focus moves into dialog on open and returns to trigger element on close
 * - Focus trapping with Tab / Shift+Tab inside active dialog
 * - Optional dirty-form guard before closing on backdrop click
 */

import { nextTick, onBeforeUnmount, onMounted, ref, watch, type ComputedRef, type Ref } from 'vue'

interface DialogStackItem {
  id: symbol
  getElement: () => HTMLElement | null
  requestClose: (reason: 'escape' | 'backdrop' | 'button') => void
}

const openStack: DialogStackItem[] = []
let globalKeyBound = false

function getFocusableElements(container: HTMLElement): HTMLElement[] {
  const selector = [
    'a[href]',
    'button:not([disabled])',
    'input:not([disabled]):not([type="hidden"])',
    'select:not([disabled])',
    'textarea:not([disabled])',
    '[tabindex]:not([tabindex="-1"])',
  ].join(',')
  return Array.from(container.querySelectorAll<HTMLElement>(selector)).filter(
    (el) => el.offsetParent !== null || el.getClientRects().length > 0,
  )
}

function syncBodyScrollLock(): void {
  if (typeof document === 'undefined') return
  const locked = openStack.length > 0
  document.documentElement.style.overflow = locked ? 'hidden' : ''
  document.body.style.overflow = locked ? 'hidden' : ''
}

function handleGlobalDialogKeydown(e: KeyboardEvent): void {
  if (openStack.length === 0) return
  const top = openStack[openStack.length - 1]
  if (!top) return

  if (e.key === 'Escape') {
    e.preventDefault()
    e.stopPropagation()
    top.requestClose('escape')
    return
  }

  if (e.key === 'Tab') {
    const container = top.getElement()
    if (!container) return
    const focusables = getFocusableElements(container)
    if (focusables.length === 0) {
      e.preventDefault()
      container.focus()
      return
    }
    const first = focusables[0]
    const last = focusables[focusables.length - 1]
    const active = document.activeElement as HTMLElement | null
    if (e.shiftKey) {
      if (!active || active === first || !container.contains(active)) {
        e.preventDefault()
        last.focus()
      }
    } else if (!active || active === last || !container.contains(active)) {
      e.preventDefault()
      first.focus()
    }
  }
}

function ensureGlobalKeyListener(): void {
  if (globalKeyBound || typeof window === 'undefined') return
  window.addEventListener('keydown', handleGlobalDialogKeydown, true)
  globalKeyBound = true
}

export interface UseDialogOptions {
  isOpen: Ref<boolean> | ComputedRef<boolean>
  containerRef: Ref<HTMLElement | null>
  onClose: () => void
  isDirty?: () => boolean
}

export function useDialogBehavior(opts: UseDialogOptions) {
  const dialogId = Symbol('dialog')
  const dirtyConfirmOpen = ref(false)
  let previousFocused: HTMLElement | null = null

  function forceClose(): void {
    dirtyConfirmOpen.value = false
    opts.onClose()
  }

  function requestClose(reason: 'escape' | 'backdrop' | 'button'): void {
    if (reason === 'backdrop' && opts.isDirty && opts.isDirty()) {
      dirtyConfirmOpen.value = true
      return
    }
    forceClose()
  }

  function cancelDirtyClose(): void {
    dirtyConfirmOpen.value = false
  }

  function pushToStack(): void {
    if (openStack.some((item) => item.id === dialogId)) return
    previousFocused = (typeof document !== 'undefined' ? document.activeElement : null) as HTMLElement | null
    ensureGlobalKeyListener()
    openStack.push({
      id: dialogId,
      getElement: () => opts.containerRef.value,
      requestClose,
    })
    syncBodyScrollLock()

    void nextTick(() => {
      const container = opts.containerRef.value
      if (!container) return
      const autoEl = container.querySelector<HTMLElement>('[autofocus]')
      const focusables = getFocusableElements(container)
      const target = autoEl || focusables[0] || container
      if (target === container && !container.hasAttribute('tabindex')) {
        container.setAttribute('tabindex', '-1')
      }
      try {
        target.focus({ preventScroll: true })
      } catch {
        // ignore focus errors on detached elements
      }
    })
  }

  function popFromStack(): void {
    const idx = openStack.findIndex((item) => item.id === dialogId)
    if (idx !== -1) {
      openStack.splice(idx, 1)
    }
    dirtyConfirmOpen.value = false
    syncBodyScrollLock()
    const opener = previousFocused
    previousFocused = null
    if (opener && typeof opener.focus === 'function') {
      void nextTick(() => {
        try {
          opener.focus({ preventScroll: true })
        } catch {
          // opener may have unmounted
        }
      })
    }
  }

  watch(
    opts.isOpen,
    (open) => {
      if (open) {
        pushToStack()
      } else {
        popFromStack()
      }
    },
    { flush: 'post' },
  )

  onMounted(() => {
    if (opts.isOpen.value) {
      pushToStack()
    }
  })

  onBeforeUnmount(() => {
    popFromStack()
  })

  return {
    dirtyConfirmOpen,
    requestClose,
    onBackdropClick: () => requestClose('backdrop'),
    onCloseButton: () => requestClose('button'),
    confirmDirtyDiscard: forceClose,
    cancelDirtyClose,
  }
}
