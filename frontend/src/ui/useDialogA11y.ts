import { useEffect, useRef } from 'react'

const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

const dialogStack: HTMLElement[] = []

interface DialogA11yOptions {
  active?: boolean
  inertAppRoot?: boolean
}

export function useDialogA11y<T extends HTMLElement>(onClose: () => void, options: DialogA11yOptions = {}) {
  const containerRef = useRef<T>(null)
  const onCloseRef = useRef(onClose)
  const active = options.active ?? true
  const inertAppRoot = options.inertAppRoot ?? true
  onCloseRef.current = onClose

  useEffect(() => {
    if (!active) return
    const container = containerRef.current
    const trigger = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const appRoot = inertAppRoot ? document.getElementById('root') : null
    const coveredDialogs = dialogStack.map((dialog) => ({
      dialog,
      ariaHidden: dialog.getAttribute('aria-hidden'),
      inert: dialog.inert,
    }))
    const coveredToastButtons = Array.from(document.querySelectorAll<HTMLButtonElement>('.toast-stack button')).map((button) => ({
      button,
      tabIndex: button.getAttribute('tabindex'),
    }))
    const previousOverflow = document.body.style.overflow
    const previousAriaHidden = appRoot?.getAttribute('aria-hidden')
    const previousInert = appRoot?.inert ?? false

    document.body.style.overflow = 'hidden'
    if (appRoot) {
      appRoot.inert = true
      appRoot.setAttribute('aria-hidden', 'true')
    }
    for (const covered of coveredDialogs) {
      covered.dialog.inert = true
      covered.dialog.setAttribute('aria-hidden', 'true')
    }
    for (const covered of coveredToastButtons) covered.button.tabIndex = -1
    if (container) dialogStack.push(container)
    document.body.classList.add('dialog-open')

    const focusable = () => Array.from(container?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [])
      .filter((element) => !element.hidden && element.getAttribute('aria-hidden') !== 'true')

    const focusFrame = window.requestAnimationFrame(() => {
      const preferred = container?.querySelector<HTMLElement>('[data-autofocus]')
      ;(preferred ?? focusable()[0] ?? container)?.focus()
    })

    const onKeyDown = (event: KeyboardEvent) => {
      if (dialogStack.at(-1) !== container) return
      if (event.key === 'Escape') {
        event.preventDefault()
        onCloseRef.current()
        return
      }
      if (event.key !== 'Tab') return
      const items = focusable()
      if (items.length === 0) {
        event.preventDefault()
        container?.focus()
        return
      }
      const first = items[0]
      const last = items[items.length - 1]
      if (!first || !last) return
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    const onFocusIn = (event: FocusEvent) => {
      if (dialogStack.at(-1) !== container || !container) return
      if (event.target instanceof Node && container.contains(event.target)) return
      ;(focusable()[0] ?? container).focus()
    }

    document.addEventListener('keydown', onKeyDown)
    document.addEventListener('focusin', onFocusIn)
    return () => {
      window.cancelAnimationFrame(focusFrame)
      document.removeEventListener('keydown', onKeyDown)
      document.removeEventListener('focusin', onFocusIn)
      if (container) {
        const stackIndex = dialogStack.lastIndexOf(container)
        if (stackIndex >= 0) dialogStack.splice(stackIndex, 1)
      }
      const stackEmpty = dialogStack.length === 0
      if (stackEmpty) document.body.classList.remove('dialog-open')
      for (const covered of coveredDialogs) {
        covered.dialog.inert = covered.inert
        if (covered.ariaHidden == null) covered.dialog.removeAttribute('aria-hidden')
        else covered.dialog.setAttribute('aria-hidden', covered.ariaHidden)
      }
      for (const covered of coveredToastButtons) {
        if (covered.tabIndex == null) covered.button.removeAttribute('tabindex')
        else covered.button.setAttribute('tabindex', covered.tabIndex)
      }
      if (stackEmpty) {
        for (const button of document.querySelectorAll<HTMLButtonElement>('.toast-stack button')) button.tabIndex = 0
      }
      document.body.style.overflow = previousOverflow
      if (appRoot) {
        appRoot.inert = previousInert
        if (previousAriaHidden == null) appRoot.removeAttribute('aria-hidden')
        else appRoot.setAttribute('aria-hidden', previousAriaHidden)
      }
      trigger?.focus()
    }
  }, [active, inertAppRoot])

  return containerRef
}
