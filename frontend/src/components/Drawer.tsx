import { X } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'

const ENTER_MS = 380
const EXIT_MS = 240 // leaves faster than it arrives: slow where the user decides, fast where the system answers

/** Right-hand drawer over a dimmed scrim. Accessible dialog: focus moves in, Tab is trapped,
 *  Esc and a scrim click close it, focus returns to whatever opened it. Enter and exit use the
 *  same path (in from the right, out to the right) so the spatial model stays honest. */
export default function Drawer({
  open,
  onClose,
  title,
  subtitle,
  wide = false,
  children,
  footer,
  closeLabel = 'Закрыть',
}: {
  open: boolean
  onClose: () => void
  title: string
  subtitle?: string
  wide?: boolean
  children: ReactNode
  footer?: ReactNode
  closeLabel?: string
}) {
  const [mounted, setMounted] = useState(open)
  const [shown, setShown] = useState(false)
  const panel = useRef<HTMLDivElement>(null)
  const opener = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (open) {
      opener.current = document.activeElement as HTMLElement | null
      setMounted(true)
      const id = requestAnimationFrame(() => requestAnimationFrame(() => setShown(true)))
      return () => cancelAnimationFrame(id)
    }
    setShown(false)
    const t = setTimeout(() => {
      setMounted(false)
      opener.current?.focus?.()
    }, EXIT_MS)
    return () => clearTimeout(t)
  }, [open])

  useEffect(() => {
    if (!shown) return
    panel.current?.querySelector<HTMLElement>('[data-autofocus]')?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose()
        return
      }
      if (e.key !== 'Tab' || !panel.current) return
      const f = panel.current.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea, [tabindex]:not([tabindex="-1"])',
      )
      if (!f.length) return
      const first = f[0]
      const last = f[f.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [shown, onClose])

  if (!mounted) return null
  const dur = open ? ENTER_MS : EXIT_MS
  return (
    <div className="fixed inset-0" style={{ zIndex: 'var(--z-scrim)' }}>
      <div
        className="absolute inset-0 backdrop-blur-xs"
        style={{ background: 'var(--scrim)', opacity: shown ? 1 : 0, transition: `opacity ${dur}ms var(--ease-out)` }}
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="absolute right-0 top-0 flex h-[100dvh] w-full flex-col overflow-hidden border-l border-gray-200 bg-white font-jakarta"
        style={{
          maxWidth: wide ? 'var(--drawer-wide)' : 'var(--drawer-max)',
          zIndex: 'var(--z-drawer)',
          transform: shown ? 'translateX(0)' : 'translateX(100%)',
          transition: `transform ${dur}ms var(--ease-drawer)`,
          paddingTop: 'max(var(--drawer-pad), env(safe-area-inset-top))',
          paddingBottom: 'max(var(--drawer-pad), env(safe-area-inset-bottom))',
        }}
      >
        <div className="flex items-start justify-between gap-4" style={{ paddingInline: 'var(--drawer-pad)' }}>
          <div>
            <h2 className="font-orbitron font-bold uppercase tracking-[0.12em]" style={{ fontSize: 'var(--h2)' }}>
              {title}
            </h2>
            {subtitle && (
              <p className="mt-1 text-gray-500" style={{ fontSize: 'var(--body)' }}>
                {subtitle}
              </p>
            )}
          </div>
          <button
            type="button"
            data-autofocus
            onClick={onClose}
            aria-label={closeLabel}
            className="press -mr-2 -mt-1 grid h-10 w-10 place-items-center text-black link-fade"
          >
            <X strokeWidth={1.5} style={{ width: 'var(--icon)', height: 'var(--icon)' }} />
          </button>
        </div>
        <div className="mt-5 min-h-0 flex-1 overflow-y-auto" style={{ paddingInline: 'var(--drawer-pad)', overscrollBehavior: 'contain' }}>
          {children}
        </div>
        {footer && (
          <div className="border-t border-gray-200 pt-4" style={{ paddingInline: 'var(--drawer-pad)' }}>
            {footer}
          </div>
        )}
      </div>
    </div>
  )
}
