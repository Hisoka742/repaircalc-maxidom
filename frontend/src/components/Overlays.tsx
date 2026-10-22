import { Check, Download, ShoppingBag } from 'lucide-react'
import { useEffect, useState } from 'react'
import { ApiError, exportEstimate, productQuantity } from '../lib/api'
import { ROOM_RU, num, plural, rub } from '../lib/format'
import { TLink, useGo } from '../lib/nav'
import type { Estimate, RoomType } from '../lib/types'
import { useApp } from '../state/AppContext'
import Drawer from './Drawer'
import EstimateLines from './EstimateLines'
import { Cta, Field, NumberInput, Skeleton } from './ui'

function Notes({ items, title }: { items: string[]; title: string }) {
  if (!items.length) return null
  return (
    <section className="mt-6">
      <h3 className="font-semibold" style={{ fontSize: 'var(--body)' }}>
        {title}
      </h3>
      <ul className="mt-2 space-y-1.5 text-gray-600" style={{ fontSize: 'var(--body)' }}>
        {items.map((w, i) => (
          <li key={i} className="leading-snug">
            {w}
          </li>
        ))}
      </ul>
    </section>
  )
}

export function ExportButtons({ estimate, compact = false }: { estimate: Estimate; compact?: boolean }) {
  const { mode, toast } = useApp()
  const [busy, setBusy] = useState<string | null>(null)
  const run = async (fmt: 'xlsx' | 'pdf') => {
    setBusy(fmt)
    try {
      await exportEstimate(estimate.estimate_id, fmt, mode)
      toast(`Файл ${fmt.toUpperCase()} сохранён.`)
    } catch (e) {
      toast(e instanceof ApiError ? e.message : 'Не удалось выгрузить смету.')
    } finally {
      setBusy(null)
    }
  }
  return (
    <div className="flex flex-wrap gap-2">
      {(['xlsx', 'pdf'] as const).map((fmt) => (
        <button
          key={fmt}
          type="button"
          disabled={busy !== null}
          onClick={() => run(fmt)}
          className={`press inline-flex items-center gap-2 rounded-md border border-gray-400 uppercase transition-colors duration-200 hover-fill disabled:opacity-40 ${compact ? 'px-3 py-2' : 'px-4 py-2.5'}`}
          style={{ fontSize: 'var(--micro)', letterSpacing: '0.18em', fontWeight: 600 }}
        >
          <Download strokeWidth={1.5} style={{ width: '1.1em', height: '1.1em' }} />
          {busy === fmt ? 'Готовим' : fmt}
        </button>
      ))}
    </div>
  )
}

export function EstimateTotals({ estimate }: { estimate: Estimate }) {
  const n = estimate.basket.lines.length
  return (
    <div>
      <div className="flex items-baseline justify-between gap-4">
        <span className="uppercase text-gray-600" style={{ fontSize: 'var(--micro)', letterSpacing: '0.18em' }}>
          Итого материалы, {plural(n, 'позиция', 'позиции', 'позиций')}
        </span>
        <span className="tnum font-orbitron font-bold" style={{ fontSize: 'var(--h2)' }}>
          {rub(estimate.basket.materials_total)}
        </span>
      </div>
      <p className="mt-1 text-gray-500" style={{ fontSize: 'var(--micro)' }}>
        Стоимость работ не рассчитана: ставки работ не заданы.
      </p>
    </div>
  )
}

export function BasketDrawer() {
  const { drawer, closeDrawer, estimate, synthetic } = useApp()
  const go = useGo()
  const open = drawer === 'basket'
  return (
    <Drawer
      open={open}
      onClose={closeDrawer}
      wide
      title="Basket"
      subtitle={estimate ? `Смета ${estimate.estimate_id}` : 'Смета'}
      footer={
        estimate && (
          <div className="space-y-3">
            <EstimateTotals estimate={estimate} />
            <ExportButtons estimate={estimate} compact />
            {synthetic && (
              <p className="text-gray-500" style={{ fontSize: 'var(--micro)' }}>
                Цены и товары из синтетического демо-каталога.
              </p>
            )}
          </div>
        )
      }
    >
      {!estimate ? (
        <div className="flex flex-col items-start gap-4 pt-6 text-gray-600">
          <ShoppingBag strokeWidth={1.2} style={{ width: '2.4rem', height: '2.4rem' }} />
          <p style={{ fontSize: 'var(--text)' }}>Смета пока пуста.</p>
          <p className="text-gray-500" style={{ fontSize: 'var(--body)' }}>
            Рассчитайте ремонт, и материалы с количествами появятся здесь.
          </p>
          <Cta
            onClick={() => {
              closeDrawer()
              go('/calculator')
            }}
          >
            К калькулятору
          </Cta>
        </div>
      ) : (
        <>
          <EstimateLines lines={estimate.basket.lines} compact />
          <Notes title="Предупреждения" items={estimate.warnings} />
          <Notes title="Допущения расчёта" items={estimate.assumptions} />
        </>
      )}
    </Drawer>
  )
}

export function MenuDrawer() {
  const { drawer, closeDrawer } = useApp()
  return (
    <Drawer open={drawer === 'menu'} onClose={closeDrawer} title="Menu" subtitle="Разделы">
      <nav aria-label="Разделы" className="flex flex-col divide-y divide-gray-200 border-y border-gray-200">
        {[
          ['/calculator', 'Калькулятор', 'Расчёт материалов для объекта или комнаты'],
          ['/catalog', 'Каталог', 'Подбор товаров под помещение, с причинами'],
          ['/method', 'Метод', 'Как считаем и что пока не доказано'],
        ].map(([to, name, text], i) => (
          <TLink key={to} to={to} onNavigate={closeDrawer} className="rise py-4" style={{ ['--i' as string]: i }}>
            <span className="font-orbitron text-lg font-bold uppercase tracking-[0.12em]">{name}</span>
            <span className="mt-1 block text-gray-500" style={{ fontSize: 'var(--body)' }}>
              {text}
            </span>
          </TLink>
        ))}
      </nav>
    </Drawer>
  )
}

export function QuantityDrawer() {
  const { drawer, closeDrawer, quantity, mode, setEstimate, toast, openDrawer } = useApp()
  const [l, setL] = useState('4')
  const [w, setW] = useState('3')
  const [h, setH] = useState('2.7')
  const [ceiling, setCeiling] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<Estimate | null>(null)

  useEffect(() => {
    setResult(null)
    setError(null)
  }, [quantity?.sku])

  if (!quantity) return null
  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      const est = await productQuantity(
        quantity.sku,
        { length_m: l, width_m: w, height_m: h, openings: [] },
        quantity.roomType as RoomType,
        ceiling,
        mode,
      )
      setResult(est)
    } catch (e) {
      setResult(null)
      setError(e instanceof ApiError ? e.message : 'Не удалось рассчитать количество.')
    } finally {
      setBusy(false)
    }
  }
  return (
    <Drawer open={drawer === 'quantity'} onClose={closeDrawer} wide title="Quantity" subtitle={quantity.name}>
      <p className="text-gray-600" style={{ fontSize: 'var(--body)' }}>
        Сколько упаковок нужно для помещения «{ROOM_RU[quantity.roomType] ?? quantity.roomType}», с сопутствующими товарами.
      </p>
      <div className="mt-5 grid grid-cols-3 gap-3">
        <Field label="Длина" htmlFor="q-l">
          <NumberInput id="q-l" value={l} onChange={(e) => setL(e.target.value)} suffix="м" min="0.5" step="0.1" />
        </Field>
        <Field label="Ширина" htmlFor="q-w">
          <NumberInput id="q-w" value={w} onChange={(e) => setW(e.target.value)} suffix="м" min="0.5" step="0.1" />
        </Field>
        <Field label="Высота" htmlFor="q-h">
          <NumberInput id="q-h" value={h} onChange={(e) => setH(e.target.value)} suffix="м" min="1.8" step="0.1" />
        </Field>
      </div>
      <label className="mt-4 flex items-center gap-2 text-gray-700" style={{ fontSize: 'var(--body)' }}>
        <input type="checkbox" checked={ceiling} onChange={(e) => setCeiling(e.target.checked)} className="h-4 w-4" />
        Учитывать потолок для краски и грунтовки
      </label>
      <div className="mt-5">
        <Cta onClick={submit} disabled={busy}>
          {busy ? 'Считаем' : 'Рассчитать'}
        </Cta>
      </div>
      {error && (
        <p role="alert" className="mt-4 border border-gray-300 p-3 text-gray-800" style={{ fontSize: 'var(--body)' }}>
          {error}
        </p>
      )}
      {busy && (
        <div className="mt-6">
          <Skeleton rows={2} />
        </div>
      )}
      {result && !busy && (
        <div className="mt-6">
          <EstimateLines lines={result.basket.lines} compact />
          <div className="mt-4">
            <EstimateTotals estimate={result} />
          </div>
          <Notes title="Предупреждения" items={result.warnings.filter((x) => !x.startsWith('Ставки'))} />
          <div className="mt-5">
            <Cta
              icon={false}
              onClick={() => {
                setEstimate(result)
                toast(`Смета обновлена: ${num(result.basket.lines.length, 0)} поз.`)
                openDrawer('basket')
              }}
            >
              Сделать текущей сметой
            </Cta>
          </div>
        </div>
      )}
    </Drawer>
  )
}

export function Toasts() {
  const { toasts } = useApp()
  return (
    <div
      aria-live="polite"
      className="pointer-events-none fixed right-0 top-0 flex flex-col items-end gap-2"
      style={{ zIndex: 'var(--z-toast)', padding: 'max(1rem, env(safe-area-inset-top)) var(--pad-x) 0 var(--pad-x)' }}
    >
      {toasts.map((t) => (
        <ToastRow key={t.id} text={t.text} />
      ))}
    </div>
  )
}

function ToastRow({ text }: { text: string }) {
  const [on, setOn] = useState(false)
  useEffect(() => {
    const id = requestAnimationFrame(() => setOn(true))
    return () => cancelAnimationFrame(id)
  }, [])
  return (
    <div
      className="flex max-w-[min(26rem,86vw)] items-start gap-2 rounded-md bg-black px-4 py-3 text-white"
      style={{
        fontSize: 'var(--body)',
        opacity: on ? 1 : 0,
        transform: on ? 'translateY(0)' : 'translateY(-10px)',
        transition: 'opacity 260ms var(--ease-out), transform 260ms var(--ease-out)',
      }}
    >
      <Check strokeWidth={2} className="mt-0.5 shrink-0 text-emerald-400" style={{ width: '1.1em', height: '1.1em' }} />
      <span>{text}</span>
    </div>
  )
}
