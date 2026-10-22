import type { MouseEvent, ReactNode, CSSProperties } from 'react'
import { flushSync } from 'react-dom'
import { useLocation, useNavigate } from 'react-router-dom'

type VT = Document & { startViewTransition?: (cb: () => void) => { finished: Promise<void> } }

/** Navigate inside a View Transition. Between the landing page and the app the whole frame
 *  flies: the old page is carried past the camera (or recedes) while the new one arrives out of
 *  depth, and the 3D house assembles behind it. Between inner pages only the body crossfades. */
export function useGo(): (to: string) => void {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  return (to: string) => {
    if (to === pathname) return
    const run = () => {
      flushSync(() => navigate(to))
      window.scrollTo(0, 0)
    }
    const d = document as VT
    if (!d.startViewTransition) return run()
    const fly = pathname === '/' || to === '/'
    const root = document.documentElement
    if (fly) {
      root.dataset.fly = pathname === '/' ? 'in' : 'out'
      root.classList.add('vt-fly')
    }
    const t = d.startViewTransition(run)
    if (fly)
      void t.finished.finally(() => {
        root.classList.remove('vt-fly')
        delete root.dataset.fly
      })
  }
}

/** A real anchor (right-click, middle-click and copy-link work) with a transitioned click. */
export function TLink({
  to,
  children,
  className,
  style,
  onNavigate,
  current,
  label,
}: {
  to: string
  children: ReactNode
  className?: string
  style?: CSSProperties
  onNavigate?: () => void
  current?: boolean
  label?: string
}) {
  const go = useGo()
  const onClick = (e: MouseEvent<HTMLAnchorElement>) => {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
    e.preventDefault()
    onNavigate?.()
    go(to)
  }
  return (
    <a href={to} onClick={onClick} className={className} style={style} aria-current={current ? 'page' : undefined} aria-label={label}>
      {children}
    </a>
  )
}
