import { Suspense, lazy, useEffect, useLayoutEffect } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import Header from './components/Header'
import { BasketDrawer, MenuDrawer, QuantityDrawer, Toasts } from './components/Overlays'
import { startSpotlight } from './lib/spotlight'
import Calculator from './pages/Calculator'
import Catalog from './pages/Catalog'
import Admin from './pages/Admin'
import Home from './pages/Home'
import Product from './pages/Product'
import Method from './pages/Method'
import { setStage, type Route as StageRoute } from './scene/stage'

// three.js is the heaviest dependency: load it after first paint so the page text appears first
const SceneCanvas = lazy(() => import('./scene/SceneCanvas'))

function routeOf(pathname: string): StageRoute {
  if (pathname.startsWith('/calculator')) return 'calculator'
  if (pathname.startsWith('/catalog') || pathname.startsWith('/product') || pathname.startsWith('/admin'))
    return 'catalog'
  if (pathname.startsWith('/method')) return 'method'
  return 'home'
}

export default function App() {
  const { pathname } = useLocation()
  const route = routeOf(pathname)

  useEffect(() => {
    startSpotlight()
  }, [])
  useEffect(() => {
    setStage({ route })
  }, [route])
  useEffect(() => {
    setStage({ dark: true })
  }, [])
  // white landing, dark app: set before paint so the view-transition snapshot already has the new theme
  useLayoutEffect(() => {
    document.documentElement.dataset.theme = 'dark'
    document.documentElement.dataset.page = route === 'home' ? 'home' : 'app'
    document.title = 'Maxicalc — Smart Repair Calculator'
    document.querySelector('meta[name=theme-color]')?.setAttribute('content', '#000000')
  }, [route])

  return (
    <div className="relative flex min-h-[100dvh] flex-col font-jakarta">
      <Suspense fallback={null}>
        <SceneCanvas hidden={route === 'home'} />
      </Suspense>
      {route !== 'home' && <Header />}
      <main className="page-surface relative flex flex-1 flex-col" style={{ zIndex: 'var(--z-page)' }}>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/calculator" element={<Calculator />} />
          <Route path="/catalog" element={<Catalog />} />
          <Route path="/product" element={<Product />} />
          <Route path="/admin" element={<Admin />} />
          <Route path="/method" element={<Method />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
      <BasketDrawer />
      <MenuDrawer />
      <QuantityDrawer />
      <Toasts />
    </div>
  )
}
