import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { detectBackend, type BackendMode } from '../lib/api'
import type { Estimate, Health } from '../lib/types'

export type DrawerName = 'basket' | 'menu' | 'quantity' | null
export interface QuantityTarget {
  sku: string
  name: string
  roomType: string
}
export interface ToastItem {
  id: number
  text: string
}

interface Ctx {
  mode: BackendMode
  health: Health | null
  /** the real catalog is not loaded yet: say so wherever numbers are shown */
  synthetic: boolean
  estimate: Estimate | null
  setEstimate: (e: Estimate | null) => void
  drawer: DrawerName
  openDrawer: (d: Exclude<DrawerName, null>) => void
  closeDrawer: () => void
  quantity: QuantityTarget | null
  openQuantity: (t: QuantityTarget) => void
  toasts: ToastItem[]
  toast: (text: string) => void
}

const AppCtx = createContext<Ctx | null>(null)

export function useApp(): Ctx {
  const v = useContext(AppCtx)
  if (!v) throw new Error('useApp outside AppProvider')
  return v
}

// Until the organisers' catalog is ingested, everything the API serves is synthetic. Flip with
// VITE_SYNTHETIC_CATALOG=false once real data is loaded.
const SYNTHETIC = (import.meta.env.VITE_SYNTHETIC_CATALOG as string | undefined) !== 'false'

export function AppProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<BackendMode>('checking')
  const [health, setHealth] = useState<Health | null>(null)
  const [estimate, setEstimate] = useState<Estimate | null>(null)
  const [drawer, setDrawer] = useState<DrawerName>(null)
  const [quantity, setQuantity] = useState<QuantityTarget | null>(null)
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const seq = useRef(0)

  useEffect(() => {
    let live = true
    detectBackend().then((r) => {
      if (!live) return
      setMode(r.mode)
      setHealth(r.health)
    })
    return () => {
      live = false
    }
  }, [])

  const toast = useCallback((text: string) => {
    const id = ++seq.current
    setToasts((t) => [...t, { id, text }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3200)
  }, [])

  const value = useMemo<Ctx>(
    () => ({
      mode,
      health,
      synthetic: SYNTHETIC || mode === 'demo',
      estimate,
      setEstimate,
      drawer,
      openDrawer: (d) => setDrawer(d),
      closeDrawer: () => setDrawer(null),
      quantity,
      openQuantity: (t) => {
        setQuantity(t)
        setDrawer('quantity')
      },
      toasts,
      toast,
    }),
    [mode, health, estimate, drawer, quantity, toasts, toast],
  )
  return <AppCtx.Provider value={value}>{children}</AppCtx.Provider>
}
