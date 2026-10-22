import { useEffect, useState } from 'react'
import EstimateLines from '../components/EstimateLines'
import { Frame } from '../components/Marks'
import { EstimateTotals } from '../components/Overlays'
import { Cta, Field, NumberInput, Segmented, Skeleton } from '../components/ui'
import { ApiError, catalogProducts, productCalc } from '../lib/api'
import { CALC_RU, rub } from '../lib/format'
import type { CatalogItem, Estimate, ProductCalcRequest } from '../lib/types'
import { setStage } from '../scene/stage'
import { useApp } from '../state/AppContext'

// Product types the card calculator serves, and which surface each one is measured on.
const KINDS = [
  { calc: 'paint', label: 'Краска', surface: 'wall' },
  { calc: 'wallpaper', label: 'Обои', surface: 'wall' },
  { calc: 'tile', label: 'Плитка', surface: 'floor' },
  { calc: 'laminate', label: 'Ламинат', surface: 'floor' },
] as const

export default function Product() {
  const { mode } = useApp()
  const demo = mode === 'demo'
  const [kind, setKind] = useState<(typeof KINDS)[number]['calc']>('paint')
  const [items, setItems] = useState<CatalogItem[]>([])
  const [pick, setPick] = useState<CatalogItem | null>(null)
  const [a, setA] = useState('4.2') // wall width or floor length
  const [b, setB] = useState('2.6') // wall height or floor width
  const [wet, setWet] = useState(false)
  const [est, setEst] = useState<Estimate | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const surface = KINDS.find((k) => k.calc === kind)!.surface

  useEffect(() => {
    setStage({ mode: 'house', focusRoom: null })
  }, [])

  useEffect(() => {
    if (demo) return
    let live = true
    catalogProducts({ calc: kind, limit: 6, status: 'auto' }, mode)
      .then((r) => {
        if (!live) return
        setItems(r.items)
        setPick(r.items[0] ?? null)
        setEst(null)
      })
      .catch((e) => live && setError(e instanceof ApiError ? e.message : 'Не удалось получить товары.'))
    return () => {
      live = false
    }
  }, [kind, demo, mode])

  // instant: every change of the dimensions recalculates (the brief: "мгновенный расчёт")
  useEffect(() => {
    if (!pick || demo) return
    const x = parseFloat(a)
    const y = parseFloat(b)
    if (!(x > 0 && y > 0)) return
    const body: ProductCalcRequest =
      surface === 'wall'
        ? { wall: { width_m: String(x), height_m: String(y) } }
        : { floor: { length_m: String(x), width_m: String(y) } }
    if (wet) body.humidity = 'high'
    const id = pick.product_id ?? pick.sku
    let live = true
    setBusy(true)
    setError(null)
    const t = setTimeout(() => {
      productCalc(id, body, mode)
        .then((r) => live && setEst(r))
        .catch((e) => {
          if (!live) return
          setEst(null)
          setError(e instanceof ApiError ? e.message : 'Не удалось рассчитать.')
        })
        .finally(() => live && setBusy(false))
    }, 180)
    return () => {
      live = false
      clearTimeout(t)
    }
  }, [pick, a, b, wet, surface, demo, mode])

  const main = est?.basket.lines.find((l) => l.sku === pick?.sku)
  const id = pick?.product_id ?? pick?.sku ?? '{id}'
  const snippet =
    `POST /api/v1/product/${id}/calc\n` +
    JSON.stringify(surface === 'wall' ? { wall: { width_m: a, height_m: b } } : { floor: { length_m: a, width_m: b } })

  return (
    <div style={{ paddingInline: 'var(--pad-x)', paddingBlock: 'var(--main-py)' }}>
      <div className="rise" style={{ ['--i' as string]: 0 }}>
        <h1 className="font-orbitron font-extrabold uppercase" style={{ fontSize: 'var(--title)', lineHeight: 1.05 }}>
          Product card
        </h1>
        <p className="mt-3 max-w-[56ch] text-gray-600" style={{ fontSize: 'var(--text)', lineHeight: 1.55, textWrap: 'balance' }}>
          Так калькулятор выглядит внутри карточки товара: покупатель вводит размеры и сразу видит, сколько упаковок и на какую сумму.
        </p>
      </div>

      {demo && (
        <p role="status" className="mt-5 max-w-[30rem] border border-gray-300 bg-white p-3 text-gray-700" style={{ fontSize: 'var(--body)' }}>
          Карточка работает с живым API: запустите сервис, и здесь появятся товары каталога.
        </p>
      )}

      <div className="mt-8 grid gap-8 lg:grid-cols-[minmax(0,30rem)_minmax(0,1fr)]">
        <Frame solid className="rise">
          <div className="flex flex-col gap-5" style={{ ['--i' as string]: 2 }}>
            <Field label="Тип товара">
              <Segmented label="Тип товара" value={kind} onChange={setKind} options={KINDS.map((k) => ({ value: k.calc, label: k.label }))} columns={4} />
            </Field>
            {items.length > 0 && (
              <Field label="Товар">
                <select
                  aria-label="Товар"
                  value={pick?.sku ?? ''}
                  onChange={(e) => setPick(items.find((i) => i.sku === e.target.value) ?? null)}
                  className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-black focus:border-black focus:outline-none"
                >
                  {items.map((i) => (
                    <option key={i.sku} value={i.sku}>
                      {i.name}
                    </option>
                  ))}
                </select>
              </Field>
            )}
            {pick && (
              <div className="border-y border-gray-200 py-3">
                <p className="font-semibold leading-snug" style={{ fontSize: 'var(--text)' }}>
                  {pick.name}
                </p>
                <p className="tnum mt-1 text-gray-600" style={{ fontSize: 'var(--body)' }}>
                  {pick.price ? rub(pick.price) : 'цена не указана'} · артикул {pick.sku}
                  {pick.product_id ? ` · id ${pick.product_id}` : ''}
                </p>
              </div>
            )}
            <div className="grid grid-cols-2 gap-3">
              <Field label={surface === 'wall' ? 'Ширина стены' : 'Длина пола'} htmlFor="pa">
                <NumberInput id="pa" value={a} onChange={(e) => setA(e.target.value)} suffix="м" min="0.5" max="50" step="0.1" />
              </Field>
              <Field label={surface === 'wall' ? 'Высота стены' : 'Ширина пола'} htmlFor="pb">
                <NumberInput id="pb" value={b} onChange={(e) => setB(e.target.value)} suffix="м" min="0.5" max="50" step="0.1" />
              </Field>
            </div>
            <label className="flex items-center gap-2 text-gray-700" style={{ fontSize: 'var(--body)' }}>
              <input type="checkbox" checked={wet} onChange={(e) => setWet(e.target.checked)} className="h-4 w-4" />
              Влажное помещение (подбор сопутствующих по требованиям влажных зон)
            </label>
          </div>
        </Frame>

        <div className="flex flex-col gap-6" aria-live="polite">
          {error && (
            <p role="alert" className="border border-gray-400 p-3" style={{ fontSize: 'var(--body)' }}>
              {error}
            </p>
          )}
          {busy && !est && <Skeleton rows={3} />}
          {est && main && (
            <Frame solid>
              <p className="text-gray-500" style={{ fontSize: 'var(--body)' }}>
                Для ваших размеров нужно
              </p>
              <p className="tnum font-orbitron mt-1" style={{ fontSize: 'var(--title)', lineHeight: 1.05 }}>
                {main.qty_packs} {main.unit}
              </p>
              <p className="tnum mt-1 text-gray-700" style={{ fontSize: 'var(--text)' }}>
                {rub(main.line_total)}
                {main.unit_price ? ` (${rub(main.unit_price)} за упаковку)` : ''}
              </p>
              <div className="mt-5">
                <EstimateLines lines={est.basket.lines} compact />
              </div>
              <div className="mt-4 max-w-md">
                <EstimateTotals estimate={est} />
              </div>
              {est.warnings.filter((w) => !w.includes('Ставки работ')).length > 0 && (
                <ul className="mt-4 space-y-1 text-gray-600" style={{ fontSize: 'var(--body)' }}>
                  {est.warnings
                    .filter((w) => !w.includes('Ставки работ'))
                    .map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                </ul>
              )}
            </Frame>
          )}
          <div>
            <h2 className="font-orbitron font-bold uppercase" style={{ fontSize: 'var(--h2)' }}>
              Embed
            </h2>
            <p className="mt-1 text-gray-600" style={{ fontSize: 'var(--body)' }}>
              Один запрос из карточки на сайте (Bitrix, AJAX или любой фронт):
            </p>
            <pre className="tnum mt-3 overflow-x-auto border border-gray-300 p-3 text-gray-800" style={{ fontSize: 'var(--body)' }}>
              {snippet}
            </pre>
            <div className="mt-3">
              <Cta
                icon={false}
                onClick={() => void navigator.clipboard?.writeText(snippet)}
              >
                Скопировать
              </Cta>
            </div>
            <p className="mt-3 text-gray-500" style={{ fontSize: 'var(--micro)' }}>
              Товар в запросе: {CALC_RU[kind] ?? kind}; ответ содержит ход расчёта на русском и сопутствующие товары.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
