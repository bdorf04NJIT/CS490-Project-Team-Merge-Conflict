import { useEffect, useRef } from 'react'

// Call `onDismiss` when the user interacts outside the returned ref element while
// `active` is true. Used to close an open popover (Rename, Save As) on an outside click.
// Listens on pointerdown so the popover closes before a click elsewhere activates it.
export function useDismissOnOutside<T extends HTMLElement>(active: boolean, onDismiss: () => void) {
  const ref = useRef<T>(null)

  useEffect(() => {
    if (!active) return
    function handle(event: PointerEvent) {
      const root = ref.current
      if (root && event.target instanceof Node && !root.contains(event.target)) {
        onDismiss()
      }
    }
    document.addEventListener('pointerdown', handle)
    return () => document.removeEventListener('pointerdown', handle)
  }, [active, onDismiss])

  return ref
}
