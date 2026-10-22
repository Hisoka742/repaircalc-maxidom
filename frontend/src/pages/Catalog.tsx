import { ChevronRight } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Frame } from '../components/Marks'
import { Field, Segmented, Skeleton } from '../components/ui'
import { ApiError, recommend } from '../lib/api'
import { CALC_RU, ROOM_RU, TIER_RU, plural, rub } from '../lib/format'
import type { Recommendation, RoomType, Tier } from '../lib/types'
import { setStage } from '../scene/stage'
import { useApp } from '../state/AppContext'

const ROOMS = (Object.keys(ROOM_RU) as RoomType[]).map((k) => ({ value: k, label: ROOM_RU[k] }))
const NEEDS = Object.keys(CALC_RU).map((k) => ({ value: k, label: CALC_RU[k] }))

export default function Catalog() {
  const { mode, openQuantity, synthetic } = useApp()
  const demo = mode === 'demo'
  const [room, setRoom] = useState<RoomType>('bathroom')
  const [need, setNeed] = useState('drywall')
  const [tier, setTier] = useState<Tier | 'any'>('any')
  const [data, setData] = useState<Recommendation | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showWhy, setShowWhy] = useState(false)
  const seq = useRef(0)

  // the camera flies into the chosen room of the 3D house
  useEffect(() => {
    setStage({ mode: 'house', focusRoom: room })
    return () => setStage({ focusRoom: null })
  }, [room])

  useEffect(() => {
    if (mode === 'checking') return
    const id = ++seq.current
    setBusy(true)
    setError(null)
    recommend({ room_type: room, calc: need, tier: tier === 'any' ? null : tier }, mode)
      .then((r) => {
        if (id === seq.current) setData(r)
      })
      .catch((e) => {
        if (id !== seq.current) return
        setData(null)
        setError(e instanceof ApiError ? e.message : 'Не удалось получить подбор.')
      })
      .finally(() => {
        if (id === seq.current) setBusy(false)
      })
  }, [room, need, tier, mode])

  const reasons = useMemo(() => {
    const m = new Map<string, number>()
    data?.excluded.forEach((x) => m.set(x.reason, (m.get(x.reason) ?? 0) + 1))
    return [...m.entries()].sort((a, b) => b[1] - a[1])
  }, [data])

  return (
    <div style={{ paddingInline: 'var(--pad-x)', paddingBlock: 'var(--main-py)' }}>
      <div className="rise" style={{ ['--i' as string]: 0 }}>
        <h1 className="font-orbitron font-extrabold uppercase" style={{ fontSize: 'var(--title)', letterSpacing: '0.08em', lineHeight: 1.05 }}>
          Catalog
        </h1>
        <p className="mt-3 max-w-[52ch] text-gray-600" style={{ fontSize: 'var(--text)', lineHeight: 1.55, textWrap: 'balance' }}>
          Выберите помещение и что нужно купить. Правила комнат отсеивают небезопасное, а причины видны.
        </p>
      </div>

      <div className="mt-8 grid gap-8 lg:grid-cols-[minmax(0,44rem)_1fr]">
        <div className="flex flex-col gap-8">
          <Frame solid className="rise">
            <div className="flex flex-col gap-5" style={{ ['--i' as string]: 2 }}>
              <Field label="Помещение">
                <Segmented label="Помещение" value={room} onChange={setRoom} options={ROOMS} columns={4} />
              </Field>
              <Field label="Что нужно">
                <Segmented label="Что нужно" value={need} onChange={setNeed} options={NEEDS} columns={4} />
              </Field>
              <Field label="Уровень цен" hint={demo ? 'В демо-режиме доступен только вариант без предпочтений.' : undefined}>
                <Segmented
                  label="Уровень цен"
                  value={tier}
                  onChange={(v) => !demo && setTier(v)}
                  options={[{ value: 'any', label: 'Любой' }, ...(Object.keys(TIER_RU) as Tier[]).map((k) => ({ value: k, label: TIER_RU[k] }))]}
                  columns={4}
                />
              </Field>
            </div>
          </Frame>

          <div aria-live="polite">
            {busy && <Skeleton rows={3} />}
            {error && (
              <p role="alert" className="border border-gray-400 p-3 text-gray-900" style={{ fontSize: 'var(--body)' }}>
                {error}
              </p>
            )}
            {data && !busy && (
              <Frame solid>
                <h2 className="font-orbitron font-bold uppercase tracking-[0.12em]" style={{ fontSize: 'var(--h2)' }}>
                  {CALC_RU[need]} для: {ROOM_RU[room].toLowerCase()}
                </h2>
                {synthetic && (
                  <p className="mt-1 text-gray-500" style={{ fontSize: 'var(--micro)' }}>
                    Товары и цены из синтетического демо-каталога.
                  </p>
                )}

                {data.items.length === 0 ? (
                  <div className="mt-5 text-gray-700" style={{ fontSize: 'var(--text)' }}>
                    {data.warnings.map((w, i) => (
                      <p key={i}>{w}</p>
                    ))}
                    <p className="mt-2 text-gray-500" style={{ fontSize: 'var(--body)' }}>
                      Правила помещения не ослабляются: небезопасный товар не покажется, даже если больше предложить нечего.
                    </p>
                  </div>
                ) : (
                  <ul className="mt-5 divide-y divide-gray-200 border-y border-gray-200">
                    {data.items.map((c, i) => (
                      <li key={c.sku} className="rise py-4" style={{ ['--i' as string]: Math.min(i, 8) }}>
                        <div className="flex items-start justify-between gap-4">
                          <div className="min-w-0">
                            <p className="font-semibold leading-snug" style={{ fontSize: 'var(--text)' }}>
                              {c.name}
                            </p>
                            <p className="mt-0.5 text-gray-500" style={{ fontSize: 'var(--body)' }}>
                              Артикул {c.sku}
                              {c.price_tier ? `, ${TIER_RU[c.price_tier]?.toLowerCase() ?? c.price_tier}` : ''}
                            </p>
                          </div>
                          <p className="tnum shrink-0 font-semibold" style={{ fontSize: 'var(--text)' }}>
                            {rub(c.price)}
                          </p>
                        </div>
                        <ul className="mt-2 space-y-1 text-gray-600" style={{ fontSize: 'var(--body)' }}>
                          {c.reasons.map((r, k) => (
                            <li key={k}>{r[0].toUpperCase() + r.slice(1)}.</li>
                          ))}
                        </ul>
                        <button
                          type="button"
                          disabled={demo}
                          onClick={() => openQuantity({ sku: c.sku, name: c.name, roomType: room })}
                          className="press link-fade mt-3 inline-flex items-center gap-1 py-1 uppercase text-gray-900 disabled:opacity-40"
                          style={{ fontSize: 'var(--micro)', letterSpacing: '0.18em', fontWeight: 600 }}
                        >
                          {demo ? 'Количество: нужен API' : 'Сколько нужно'}
                          {!demo && <ChevronRight strokeWidth={1.5} style={{ width: '1em', height: '1em' }} />}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}

                {data.excluded_total > 0 && (
                  <div className="mt-5">
                    <button
                      type="button"
                      aria-expanded={showWhy}
                      aria-controls="why-not"
                      onClick={() => setShowWhy((v) => !v)}
                      className="press link-fade inline-flex items-center gap-1 py-1 text-gray-800"
                      style={{ fontSize: 'var(--body)', fontWeight: 600 }}
                    >
                      <ChevronRight
                        strokeWidth={1.5}
                        style={{ width: '1em', height: '1em', transform: showWhy ? 'rotate(90deg)' : 'none', transition: 'transform 200ms var(--ease-out)' }}
                      />
                      Почему не показаны другие: {plural(data.excluded_total, 'товар', 'товара', 'товаров')}
                    </button>
                    {showWhy && (
                      <ul id="why-not" className="rise mt-2 space-y-1.5 border-l border-gray-300 pl-4 text-gray-600" style={{ fontSize: 'var(--body)' }}>
                        {reasons.map(([why, n]) => (
                          <li key={why}>
                            {why} <span className="tnum text-gray-400">({n} в выборке)</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </Frame>
            )}
          </div>
        </div>
        <div className="hidden lg:block" aria-hidden="true" />
      </div>
    </div>
  )
}
