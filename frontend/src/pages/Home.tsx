import { useEffect, useRef, useState } from 'react'
import metrics from '../data/metrics.json'
import { TLink } from '../lib/nav'
import { setStage } from '../scene/stage'

// The landing page is the Vesper-style single viewport: pure black, looping video, three stats.
// Copy is ours (the calculator), the layout, tokens and motion are the brief's. Styles are in
// landing.css; everything below only decides what is shown.

const HERO_VIDEO =
  'https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260818_072341_50851634-bbc3-4c33-9acc-7647d4db44aa.mp4'

interface Load {
  p95: number
  rps: number
}
const M = metrics as unknown as {
  eval: { golden: { cases: number; pack_exact: [number, number] } }
  load: Load[]
}
const load = M.load[M.load.length - 1]

const NAV = [
  { to: '/calculator', label: 'Калькулятор', cls: 'scale', d: '0.16s' },
  { to: '/catalog', label: 'Каталог', cls: 'soft', d: '0.28s' },
  { to: '/product', label: 'Карточка', cls: 'scale', d: '0.40s' },
  { to: '/admin', label: 'Админка', cls: 'soft', d: '0.52s' },
  { to: '/method', label: 'Метод', cls: 'scale', d: '0.64s' },
]

function Mark() {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <g transform="rotate(-30 12 12)">
        <circle cx="7.3" cy="3.2" r="1.45" />
        <rect x="5.5" y="4.7" width="3.6" height="14.6" rx="1.8" />
        <rect x="14.9" y="4.7" width="3.6" height="14.6" rx="1.8" />
        <circle cx="16.7" cy="20.8" r="1.45" />
      </g>
    </svg>
  )
}

export default function Home() {
  const root = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    setStage({ mode: 'house', focusRoom: null, explode: 0, layer: -1 })
    const html = document.documentElement
    html.classList.add('lp-on')
    return () => {
      html.classList.remove('lp-on')
      document.body.classList.remove('menu-open')
    }
  }, [])

  // entrance: each element removes its own animation when done, and if the browser never starts
  // one (reduced motion, throttled tab) everything is simply put in its final state
  useEffect(() => {
    const els = Array.from(root.current?.querySelectorAll<HTMLElement>('.lp-appear') ?? [])
    const photo = document.querySelector<HTMLElement>('.lp-photo')
    const done = (el: HTMLElement) => () => el.classList.add('is-in')
    const offs = [...els, ...(photo ? [photo] : [])].map((el) => {
      const f = done(el)
      el.addEventListener('animationend', f, { once: true })
      return () => el.removeEventListener('animationend', f)
    })
    let raf = 0
    raf = requestAnimationFrame(() => {
      raf = requestAnimationFrame(() => {
        const target = els[0]
        const running = target?.getAnimations().some((a) => a.playState === 'running' || a.playState === 'finished')
        if (!running) for (const el of [...els, ...(photo ? [photo] : [])]) el.classList.add('is-in')
      })
    })
    return () => {
      cancelAnimationFrame(raf)
      offs.forEach((f) => f())
    }
  }, [])

  // phone menu
  useEffect(() => {
    document.body.classList.toggle('menu-open', open)
  }, [open])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    const mq = window.matchMedia('(min-width: 901px)')
    const onMq = () => mq.matches && setOpen(false)
    window.addEventListener('keydown', onKey)
    mq.addEventListener('change', onMq)
    return () => {
      window.removeEventListener('keydown', onKey)
      mq.removeEventListener('change', onMq)
    }
  }, [])

  const ap = (kind: string, d: string, extra = '') => ({ className: `lp-appear lp-appear--${kind} ${extra}`.trim(), style: { ['--d' as string]: d } })

  return (
    <div ref={root} className="lp">
      <video className="lp-photo" src={HERO_VIDEO} autoPlay muted loop playsInline preload="auto" aria-hidden="true" />
      <div className="lp-grain" aria-hidden="true" />

      <div className="lp-menu-backdrop" onClick={() => setOpen(false)} />
      <header className="lp-header">
        <TLink to="/" className="lp-logo lp-appear lp-appear--scale" style={{ ['--d' as string]: '0.08s' }} label="Maxicalc">
          <Mark />
          <span>
            Maxi<span className="lp-logo-suffix">calc</span>
          </span>
        </TLink>

        <nav id="site-nav" className="lp-nav" aria-label="Основная навигация">
          {NAV.map((n) => (
            <TLink key={n.label} to={n.to} onNavigate={() => setOpen(false)} className={`lp-pill lp-appear lp-appear--${n.cls}`} style={{ ['--d' as string]: n.d }}>
              {n.label}
            </TLink>
          ))}
        </nav>

        <TLink to="/calculator" className="lp-btn lp-btn-solid lp-header-cta lp-appear lp-appear--scale" style={{ ['--d' as string]: '0.34s' }}>
          Рассчитать
        </TLink>
        <button
          type="button"
          className="lp-burger lp-appear lp-appear--scale"
          style={{ ['--d' as string]: '0.34s' }}
          aria-controls="site-nav"
          aria-expanded={open}
          aria-label={open ? 'Закрыть меню' : 'Открыть меню'}
          onClick={() => setOpen((v) => !v)}
        >
          <span />
          <span />
          <span />
        </button>
      </header>

      <main className="lp-hero" id="top">
        <div className="lp-copy">
          <div className="lp-badge lp-appear lp-appear--pop" style={{ ['--d' as string]: '0.22s' }}>
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M12 2.6C12.55 2.6 12.88 3.15 13.08 4.7c.62 4.7 1.52 5.6 6.22 6.22 1.55.2 2.1.53 2.1 1.08s-.55.88-2.1 1.08c-4.7.62-5.6 1.52-6.22 6.22-.2 1.55-.53 2.1-1.08 2.1s-.88-.55-1.08-2.1c-.62-4.7-1.52-5.6-6.22-6.22C3.15 12.88 2.6 12.55 2.6 12s.55-.88 2.1-1.08c4.7-.62 5.6-1.52 6.22-6.22C11.12 3.15 11.45 2.6 12 2.6Z" />
            </svg>
            Smart Repair Calculator
          </div>

          <h1 className="lp-h1">
            <span className="lp-line lp-appear lp-appear--mask" style={{ ['--d' as string]: '0.42s' }}>
              Plan <em>every repair</em> down to
            </span>
            <span className="lp-line lp-appear lp-appear--mask" style={{ ['--d' as string]: '0.62s' }}>
              the last pack in minutes.
            </span>
          </h1>

          <p className="lp-lede lp-appear lp-appear--soft" style={{ ['--d' as string]: '0.82s', animationDuration: '1.25s' }}>
            Движок считает материалы по упаковкам, а каждую позицию можно раскрыть до расчёта. Нейросеть понимает текст, числа считает только формула.
          </p>

          <div className="lp-hero-actions">
            <TLink to="/calculator" className="lp-btn lp-btn-solid lp-appear lp-appear--btn" style={{ ['--d' as string]: '0.96s' }}>
              Рассчитать ремонт
            </TLink>
            <TLink to="/method" className="lp-btn lp-btn-ghost lp-appear lp-appear--side" style={{ ['--d' as string]: '1.10s' }}>
              Как это работает
            </TLink>
          </div>
        </div>
      </main>

      <footer className="lp-stats">
        <div className="lp-stat lp-appear lp-appear--stat" style={ap('stat', '1.12s').style}>
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <defs>
              <linearGradient id="lpg1" x1="3" y1="2" x2="14" y2="22" gradientUnits="userSpaceOnUse">
                <stop offset="0.38" stopColor="#fff" />
                <stop offset="0.62" stopColor="#3a3a3a" />
              </linearGradient>
              <linearGradient id="lpg2" x1="3" y1="2" x2="14" y2="22" gradientUnits="userSpaceOnUse">
                <stop offset="0.38" stopColor="#3a3a3a" />
                <stop offset="0.62" stopColor="#fff" />
              </linearGradient>
            </defs>
            <rect x="3.4" y="2.6" width="7.2" height="18.8" rx="3.6" fill="url(#lpg1)" />
            <rect x="13.4" y="2.6" width="7.2" height="18.8" rx="3.6" fill="url(#lpg2)" />
            <rect x="9.2" y="10.9" width="5.6" height="2.2" rx="1.1" fill="#4a4a4a" />
          </svg>
          {M.eval.golden.cases} эталонных случаев расчёта
        </div>

        <div className="lp-stat lp-appear lp-appear--stat" style={ap('stat', '1.28s').style}>
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <rect x="2.4" y="2.4" width="19.2" height="19.2" rx="6.2" fill="#fff" />
            <path d="M12 7.1v7.4M8.15 12.35L12 16.2l3.85-3.85" fill="none" stroke="#111" strokeWidth="1.85" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          {M.eval.golden.pack_exact[0]} из {M.eval.golden.pack_exact[1]} упаковок посчитаны точно
        </div>

        <div className="lp-stat lp-appear lp-appear--stat" style={ap('stat', '1.44s').style}>
          <svg className="lp-icon-wide" viewBox="0 0 40 22" aria-hidden="true">
            <path d="M4.6 5.6L6.9 2.4L9.2 5.4Z M11.2 5.4L13.5 2.4L15.8 5.6Z" fill="#2b2b2b" />
            <circle cx="10.2" cy="11" r="9.2" fill="#2b2b2b" />
            <ellipse cx="10.2" cy="12.1" rx="4.15" ry="3.7" fill="#f4f4f4" />
            <circle cx="8.6" cy="11.4" r="0.7" fill="#1a1a1a" />
            <circle cx="11.8" cy="11.4" r="0.7" fill="#1a1a1a" />
            <circle cx="20.2" cy="11" r="9.2" fill="#fff" />
            <circle cx="17.6" cy="9.8" r="1.7" fill="#111" />
            <circle cx="22.8" cy="9.8" r="1.7" fill="#111" />
            <ellipse cx="20.2" cy="12.8" rx="1" ry="0.7" fill="#111" />
            <path d="M16.9 14.9Q20.2 17.4 23.5 14.9" fill="none" stroke="#111" strokeWidth="1.2" strokeLinecap="round" />
            <circle cx="30.2" cy="11" r="9.2" fill="#f26b1d" />
            <text x="30.2" y="15.1" fontSize="12.5" fontWeight="700" textAnchor="middle" fill="#fff" fontFamily="Inter, sans-serif">
              e
            </text>
          </svg>
          p95 {load.p95} мс при {load.rps} запросах в секунду
        </div>
      </footer>
    </div>
  )
}
