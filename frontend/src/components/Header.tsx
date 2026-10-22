import { ShoppingBag } from 'lucide-react'
import { useLocation } from 'react-router-dom'
import { TLink } from '../lib/nav'
import { useApp } from '../state/AppContext'

const LINKS = [
  { to: '/calculator', label: 'Калькулятор' },
  { to: '/catalog', label: 'Каталог' },
  { to: '/product', label: 'Карточка' },
  { to: '/admin', label: 'Админка' },
  { to: '/method', label: 'Метод' },
]

/** The landing page's header, carried over to the inner pages: logo, liquid-metal pills, and the
 *  estimate button in the same glass as the landing buttons. */
export default function Header() {
  const { pathname } = useLocation()
  const { estimate, openDrawer, closeDrawer } = useApp()
  const count = estimate?.basket.lines.length ?? 0

  return (
    <header className="lp-header" style={{ fontFamily: 'var(--font-jakarta)' }}>
      <TLink to="/" onNavigate={closeDrawer} className="lp-logo press" label="Maxicalc, на главную">
        <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <g transform="rotate(-30 12 12)">
            <circle cx="7.3" cy="3.2" r="1.45" />
            <rect x="5.5" y="4.7" width="3.6" height="14.6" rx="1.8" />
            <rect x="14.9" y="4.7" width="3.6" height="14.6" rx="1.8" />
            <circle cx="16.7" cy="20.8" r="1.45" />
          </g>
        </svg>
        <span>
          Maxi<span className="lp-logo-suffix">calc</span>
        </span>
      </TLink>

      <nav className="lp-nav lp-nav--inner" aria-label="Основная навигация">
        {LINKS.map((l) => (
          <TLink key={l.to} to={l.to} current={pathname === l.to} className="lp-pill">
            {l.label}
          </TLink>
        ))}
      </nav>

      <div className="lp-header-right">
        <button
          type="button"
          onClick={() => openDrawer('basket')}
          aria-label={count ? `Смета, позиций: ${count}` : 'Смета пуста'}
          className="lp-btn lp-btn-ghost press"
        >
          <ShoppingBag strokeWidth={1.5} style={{ width: '1.15em', height: '1.15em' }} />
          <span className="tnum">{count > 0 ? `Смета · ${count}` : 'Смета'}</span>
        </button>
        <button
          type="button"
          className="lp-burger press"
          aria-label="Меню"
          aria-expanded={false}
          onClick={() => openDrawer('menu')}
        >
          <span />
          <span />
          <span />
        </button>
      </div>
    </header>
  )
}
