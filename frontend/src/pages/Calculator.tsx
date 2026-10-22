import { Plus, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import EstimateLines from '../components/EstimateLines'
import { Frame } from '../components/Marks'
import { EstimateTotals, ExportButtons } from '../components/Overlays'
import { Cta, Field, NumberInput, Segmented, Skeleton } from '../components/ui'
import { ApiError, calcProperty, calcRoom, explainEstimate, parseText } from '../lib/api'
import { CLASS_RU, PROPERTY_RU, ROOM_RU, TIER_RU, num, plural } from '../lib/format'
import { DEMO_CATALOG_LABEL, DEMO_PRESETS } from '../lib/fixtures'
import type { Estimate, Explanation, Opening, PropertyType, RenovationClass, RoomSpec, RoomType, Tier } from '../lib/types'
import { setStage } from '../scene/stage'
import { useApp } from '../state/AppContext'

type Scope = 'property' | 'room'

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))
const WALLS = [
  { value: '0', label: 'Длинная стена 1' },
  { value: '1', label: 'Короткая стена 1' },
  { value: '2', label: 'Длинная стена 2' },
  { value: '3', label: 'Короткая стена 2' },
]
const MISSING_RU: Record<string, string> = {
  property_type: 'тип объекта',
  renovation_class: 'класс ремонта',
  total_area_m2: 'площадь',
  room_area_m2: 'площадь помещения',
}
const ROOM_OPTIONS = (Object.keys(ROOM_RU) as RoomType[]).map((k) => ({ value: k, label: ROOM_RU[k] }))

export default function Calculator() {
  const { mode, setEstimate, toast, openDrawer, synthetic } = useApp()
  const demo = mode === 'demo'

  const [scope, setScope] = useState<Scope>('property')
  const [ptype, setPtype] = useState<PropertyType>('apartment')
  const [area, setArea] = useState('60')
  const [klass, setKlass] = useState<RenovationClass>('cosmetic')
  const [tier, setTier] = useState<Tier | 'any'>('any')
  const [roomType, setRoomType] = useState<RoomType>('living')
  const [len, setLen] = useState('4')
  const [wid, setWid] = useState('3')
  const [hei, setHei] = useState('2.7')
  const [ceiling, setCeiling] = useState(true)
  const [openings, setOpenings] = useState<Opening[]>([])
  const [rooms, setRooms] = useState<RoomSpec[]>([]) // own rooms; empty = the typical layout
  const [story, setStory] = useState('')
  const [parsing, setParsing] = useState(false)
  const [parseNote, setParseNote] = useState<string | null>(null)

  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<Estimate | null>(null)
  const results = useRef<HTMLDivElement>(null)

  // demo mode has no room calculator: fall back to the property scope
  useEffect(() => {
    if (demo && scope === 'room') setScope('property')
  }, [demo, scope])

  const L = clamp(parseFloat(len) || 4, 1, 14)
  const W = clamp(parseFloat(wid) || 3, 1, 14)
  const H = clamp(parseFloat(hei) || 2.7, 1.8, 6)

  // the 3D stage follows the form: whole house, or a live model of the room being typed
  useEffect(() => {
    setStage(
      scope === 'room'
        ? { mode: 'room', room: { l: L, w: W, h: H }, focusRoom: null }
        : { mode: 'house', focusRoom: null },
    )
  }, [scope, L, W, H])
  useEffect(
    () => () => {
      setStage({ mode: 'house', focusRoom: null })
    },
    [],
  )

  const summary = useMemo(() => {
    if (scope === 'room') {
      return `${ROOM_RU[roomType]}: ${num(L, 1)} × ${num(W, 1)} × ${num(H, 1)} м, ${num(L * W, 1)} м²`
    }
    return `${PROPERTY_RU[ptype]}, ${num(parseFloat(area) || 0, 0)} м², ${CLASS_RU[klass].toLowerCase()} ремонт`
  }, [scope, roomType, L, W, H, ptype, area, klass])

  const submit = async () => {
    setError(null)
    const tierValue = tier === 'any' ? null : tier
    setBusy(true)
    try {
      let est: Estimate
      if (scope === 'property') {
        const a = parseFloat(area)
        if (!Number.isFinite(a) || a <= 0) throw new ApiError('Укажите площадь больше нуля.')
        const own = rooms.filter((r) => parseFloat(r.area_m2) > 0)
        const total = own.length ? own.reduce((s, r) => s + parseFloat(r.area_m2), 0) : a
        est = await calcProperty(
          {
            property_type: ptype,
            total_area_m2: String(total),
            renovation_class: klass,
            tier: tierValue,
            rooms: own.length ? own : null,
          },
          mode,
        )
      } else {
        est = await calcRoom(
          {
            room: { length_m: String(L), width_m: String(W), height_m: String(H), openings },
            room_type: roomType,
            renovation_class: klass,
            tier: tierValue,
            include_ceiling: ceiling,
          },
          mode,
        )
      }
      setResult(est)
      setEstimate(est)
      toast(`Смета рассчитана: ${plural(est.basket.lines.length, 'позиция', 'позиции', 'позиций')}.`)
      requestAnimationFrame(() =>
        results.current?.scrollIntoView({
          behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
          block: 'start',
        }),
      )
    } catch (e) {
      setResult(null)
      setError(e instanceof ApiError ? e.message : 'Не удалось рассчитать. Проверьте значения и повторите.')
    } finally {
      setBusy(false)
    }
  }

  const understand = async () => {
    setParseNote(null)
    if (story.trim().length < 3) return
    setParsing(true)
    try {
      const p = await parseText(story, mode)
      if (p.property_type) setPtype(p.property_type)
      if (p.renovation_class) setKlass(p.renovation_class)
      if (p.tier) setTier(p.tier)
      if (p.total_area_m2) setArea(String(parseFloat(p.total_area_m2)))
      if (p.rooms.length) {
        setRooms(
          p.rooms.map((r) => ({
            room_type: r.room_type,
            area_m2: r.area_m2 ? String(parseFloat(r.area_m2)) : '',
            humidity: r.humidity === 'high' ? 'high' : null,
          })),
        )
      }
      const parts = [`понял: ${p.rooms.length ? p.rooms.map((r) => ROOM_RU[r.room_type]).join(', ') : 'помещения не названы'}`]
      if (p.missing.length) parts.push('уточните: ' + p.missing.map((m) => MISSING_RU[m] ?? m).join(', '))
      setParseNote(parts.join('. ') + (p.method === 'llm' ? ' (разобрано локальной моделью)' : '.'))
    } catch (e) {
      setParseNote(e instanceof ApiError ? e.message : 'Не удалось разобрать запрос.')
    } finally {
      setParsing(false)
    }
  }
  const patchRoom = (i: number, patch: Partial<RoomSpec>) =>
    setRooms((r) => r.map((x, k) => (k === i ? { ...x, ...patch } : x)))

  const addOpening = () =>
    setOpenings((o) => (o.length >= 6 ? o : [...o, { kind: 'door', width_m: '0.9', height_m: '2.05', wall: 0 }]))
  const patchOpening = (i: number, patch: Partial<Opening>) =>
    setOpenings((o) => o.map((x, k) => (k === i ? { ...x, ...patch } : x)))

  return (
    <div style={{ paddingInline: 'var(--pad-x)', paddingBlock: 'var(--main-py)' }}>
      <div className="rise" style={{ ['--i' as string]: 0 }}>
        <h1 className="font-orbitron font-extrabold uppercase" style={{ fontSize: 'var(--title)', letterSpacing: '0.08em', lineHeight: 1.05 }}>
          Calculator
        </h1>
        <p className="mt-3 max-w-[52ch] text-gray-600" style={{ fontSize: 'var(--text)', lineHeight: 1.55, textWrap: 'balance' }}>
          Опишите объект или комнату. Движок посчитает материалы по упаковкам, а каждую позицию можно раскрыть до расчёта.
        </p>
      </div>

      {demo && (
        <p role="status" className="rise mt-5 max-w-[27rem] border border-gray-300 bg-white p-3 text-gray-700" style={{ ['--i' as string]: 1, fontSize: 'var(--body)' }}>
          Демо-режим: API не запущен, показаны сохранённые расчёты на {DEMO_CATALOG_LABEL}. Для произвольных значений
          запустите сервис.
        </p>
      )}

      <div className="mt-8 grid gap-8 lg:grid-cols-[minmax(0,27rem)_1fr]">
        <Frame className="rise" solid>
          <form
            className="flex flex-col gap-5"
            style={{ ['--i' as string]: 2 }}
            onSubmit={(e) => {
              e.preventDefault()
              void submit()
            }}
          >
            <Segmented
              label="Что считаем"
              value={scope}
              onChange={(v) => !(demo && v === 'room') && setScope(v)}
              options={[
                { value: 'property', label: 'Весь объект' },
                { value: 'room', label: demo ? 'Комната (нужен API)' : 'Одна комната' },
              ]}
            />

            {scope === 'property' ? (
              <>
                {demo ? (
                  <Field label="Готовый пример">
                    <Segmented
                      label="Готовый пример"
                      value={`${ptype}|${area}`}
                      onChange={(v) => {
                        const [t, a] = v.split('|')
                        setPtype(t as PropertyType)
                        setArea(a)
                      }}
                      options={DEMO_PRESETS.map((p) => ({
                        value: `${p.property_type}|${p.area}`,
                        label: `${PROPERTY_RU[p.property_type]}, ${p.area} м²`,
                      }))}
                      columns={1}
                    />
                  </Field>
                ) : (
                  <>
                    <Field label="Тип объекта">
                      <Segmented
                        label="Тип объекта"
                        value={ptype}
                        onChange={setPtype}
                        options={(Object.keys(PROPERTY_RU) as PropertyType[]).map((k) => ({ value: k, label: PROPERTY_RU[k] }))}
                      />
                    </Field>
                    <Field label="Опишите своими словами" htmlFor="story" hint={parseNote ?? 'Например: квартира, капитальный ремонт, санузел 6 м², высокая влажность'}>
                      <div className="flex gap-2">
                        <input
                          id="story"
                          value={story}
                          onChange={(e) => setStory(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                              e.preventDefault()
                              void understand()
                            }
                          }}
                          placeholder="квартира, капитальный, санузел 6 м², высокая влажность"
                          className="min-w-0 flex-1 rounded-md border border-gray-300 bg-white px-3 py-2 text-black focus:border-black focus:outline-none"
                        />
                        <Cta onClick={() => void understand()} disabled={parsing} icon={false} solid>
                          {parsing ? '…' : 'Понять'}
                        </Cta>
                      </div>
                    </Field>
                    <Field label="Общая площадь" htmlFor="area" hint={rooms.length ? 'Считается по своим помещениям ниже.' : 'Комнаты подбираются по типовой раскладке.'}>
                      <NumberInput id="area" value={area} onChange={(e) => setArea(e.target.value)} suffix="м²" min="5" max="5000" step="1" />
                      <input
                        type="range"
                        aria-label="Площадь, ползунок"
                        min={15}
                        max={300}
                        step={1}
                        value={clamp(parseFloat(area) || 60, 15, 300)}
                        onChange={(e) => setArea(e.target.value)}
                        className="mt-2"
                      />
                    </Field>
                    <div className="flex flex-col gap-2">
                      <span className="text-gray-700" style={{ fontSize: 'var(--body)', fontWeight: 600 }}>
                        Свои помещения
                      </span>
                      {rooms.map((r, i) => (
                        <div key={i} className="grid grid-cols-[1.3fr_1fr_auto_auto] items-center gap-2">
                          <select
                            aria-label="Помещение"
                            value={r.room_type}
                            onChange={(e) => patchRoom(i, { room_type: e.target.value as RoomType })}
                            className="rounded-md border border-gray-300 bg-white px-2 py-2 focus:border-black focus:outline-none"
                          >
                            {ROOM_OPTIONS.map((o) => (
                              <option key={o.value} value={o.value}>
                                {o.label}
                              </option>
                            ))}
                          </select>
                          <NumberInput aria-label="Площадь помещения" value={r.area_m2} onChange={(e) => patchRoom(i, { area_m2: e.target.value })} suffix="м²" min="1" max="500" step="0.5" />
                          <label className="flex items-center gap-1.5 text-gray-700" style={{ fontSize: 'var(--body)' }}>
                            <input type="checkbox" checked={r.humidity === 'high'} onChange={(e) => patchRoom(i, { humidity: e.target.checked ? 'high' : null })} className="h-4 w-4" />
                            влажно
                          </label>
                          <button type="button" aria-label="Убрать помещение" onClick={() => setRooms((x) => x.filter((_, k) => k !== i))} className="press link-fade grid h-10 w-10 place-items-center">
                            <X strokeWidth={1.5} style={{ width: 'var(--icon)', height: 'var(--icon)' }} />
                          </button>
                        </div>
                      ))}
                      <button
                        type="button"
                        onClick={() => setRooms((r) => (r.length >= 12 ? r : [...r, { room_type: 'bathroom', area_m2: '6', humidity: 'high' }]))}
                        className="press link-fade inline-flex w-fit items-center gap-1.5 py-1 text-gray-700"
                        style={{ fontSize: 'var(--body)', fontWeight: 600 }}
                      >
                        <Plus strokeWidth={1.5} style={{ width: '1.1em', height: '1.1em' }} />
                        Добавить помещение
                      </button>
                    </div>
                  </>
                )}
              </>
            ) : (
              <>
                <Field label="Помещение">
                  <Segmented label="Помещение" value={roomType} onChange={setRoomType} options={ROOM_OPTIONS} columns={4} />
                </Field>
                <div className="grid grid-cols-3 gap-3">
                  <Field label="Длина" htmlFor="len">
                    <NumberInput id="len" value={len} onChange={(e) => setLen(e.target.value)} suffix="м" min="1" max="14" step="0.1" />
                  </Field>
                  <Field label="Ширина" htmlFor="wid">
                    <NumberInput id="wid" value={wid} onChange={(e) => setWid(e.target.value)} suffix="м" min="1" max="14" step="0.1" />
                  </Field>
                  <Field label="Высота" htmlFor="hei">
                    <NumberInput id="hei" value={hei} onChange={(e) => setHei(e.target.value)} suffix="м" min="1.8" max="6" step="0.1" />
                  </Field>
                </div>

                <div className="flex flex-col gap-2">
                  <span className="text-gray-700" style={{ fontSize: 'var(--body)', fontWeight: 600 }}>
                    Двери и окна
                  </span>
                  {openings.map((o, i) => (
                    <div key={i} className="grid grid-cols-[1fr_1fr_1fr_auto] items-end gap-2">
                      <select
                        aria-label="Тип проёма"
                        value={o.kind}
                        onChange={(e) => {
                          const kind = e.target.value as Opening['kind']
                          patchOpening(i, { kind, width_m: kind === 'door' ? '0.9' : '1.4', height_m: kind === 'door' ? '2.05' : '1.4' })
                        }}
                        className="rounded-md border border-gray-300 bg-white px-2 py-2 focus:border-black focus:outline-none"
                      >
                        <option value="door">Дверь</option>
                        <option value="window">Окно</option>
                      </select>
                      <NumberInput aria-label="Ширина проёма" value={o.width_m} onChange={(e) => patchOpening(i, { width_m: e.target.value })} suffix="м" min="0.3" step="0.1" />
                      <select
                        aria-label="Стена"
                        value={String(o.wall)}
                        onChange={(e) => patchOpening(i, { wall: Number(e.target.value) })}
                        className="rounded-md border border-gray-300 bg-white px-2 py-2 focus:border-black focus:outline-none"
                      >
                        {WALLS.map((w) => (
                          <option key={w.value} value={w.value}>
                            {w.label}
                          </option>
                        ))}
                      </select>
                      <button
                        type="button"
                        aria-label="Убрать проём"
                        onClick={() => setOpenings((x) => x.filter((_, k) => k !== i))}
                        className="press link-fade grid h-10 w-10 place-items-center"
                      >
                        <X strokeWidth={1.5} style={{ width: 'var(--icon)', height: 'var(--icon)' }} />
                      </button>
                    </div>
                  ))}
                  <button
                    type="button"
                    onClick={addOpening}
                    disabled={openings.length >= 6}
                    className="press link-fade inline-flex w-fit items-center gap-1.5 py-1 text-gray-700 disabled:opacity-40"
                    style={{ fontSize: 'var(--body)', fontWeight: 600 }}
                  >
                    <Plus strokeWidth={1.5} style={{ width: '1.1em', height: '1.1em' }} />
                    Добавить проём
                  </button>
                </div>

                <label className="flex items-center gap-2 text-gray-700" style={{ fontSize: 'var(--body)' }}>
                  <input type="checkbox" checked={ceiling} onChange={(e) => setCeiling(e.target.checked)} className="h-4 w-4" />
                  Красить и грунтовать потолок
                </label>
              </>
            )}

            <Field label="Класс ремонта">
              <Segmented
                label="Класс ремонта"
                value={klass}
                onChange={setKlass}
                options={(Object.keys(CLASS_RU) as RenovationClass[]).map((k) => ({ value: k, label: CLASS_RU[k] }))}
              />
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

            {error && (
              <p role="alert" className="border border-gray-400 p-3 text-gray-900" style={{ fontSize: 'var(--body)' }}>
                {error}
              </p>
            )}
            <div>
              <Cta type="submit" disabled={busy}>
                {busy ? 'Считаем' : 'Рассчитать'}
              </Cta>
            </div>
          </form>
        </Frame>

        {/* the right column stays open so the 3D stage shows through; it only states what is modelled */}
        <div className="rise hidden items-end justify-end lg:flex" style={{ ['--i' as string]: 3 }}>
          <p className="max-w-[28ch] text-right text-gray-600" style={{ fontSize: 'var(--body)', lineHeight: 1.6 }} aria-live="polite">
            {summary}
          </p>
        </div>
      </div>

      <div ref={results} className="scroll-mt-6">
        {busy && (
          <div className="mt-10 max-w-3xl">
            <Skeleton rows={5} />
          </div>
        )}
        {result && !busy && <Results est={result} synthetic={synthetic} onOpen={() => openDrawer('basket')} />}
      </div>
    </div>
  )
}

function Results({ est, synthetic, onOpen }: { est: Estimate; synthetic: boolean; onOpen: () => void }) {
  const { mode } = useApp()
  return (
    <Frame solid className="mt-10">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="font-orbitron font-bold uppercase tracking-[0.12em]" style={{ fontSize: 'var(--h2)' }}>
            Basket
          </h2>
          <p className="mt-1 text-gray-500" style={{ fontSize: 'var(--body)' }}>
            Смета {est.estimate_id}
            {mode === 'demo' ? ', сохранённый расчёт' : est.cached ? ', из кэша' : ''}. Версия каталога {est.catalog_version}.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <ExportButtons estimate={est} />
          <Cta onClick={onOpen} icon={false}>
            Открыть смету
          </Cta>
        </div>
      </div>

      {mode !== 'demo' && <Why id={est.estimate_id} />}

      {est.rooms.length > 1 && (
        <p className="mt-4 text-gray-600" style={{ fontSize: 'var(--body)' }}>
          {est.rooms.map((r) => `${ROOM_RU[r.room_type] ?? r.room_type} ${num(r.area_m2, 1)} м²`).join(', ')}.
        </p>
      )}

      <div className="mt-6">
        <EstimateLines lines={est.basket.lines} />
      </div>
      <div className="mt-5 max-w-xl">
        <EstimateTotals estimate={est} />
        {synthetic && (
          <p className="mt-2 text-gray-500" style={{ fontSize: 'var(--micro)' }}>
            Товары и цены из синтетического демо-каталога, не из реального ассортимента.
          </p>
        )}
      </div>

      <div className="mt-8 grid gap-8 md:grid-cols-2">
        <Notes title="Предупреждения" empty="Предупреждений нет." items={est.warnings} />
        <Notes title="Допущения расчёта" empty="Допущений не потребовалось." items={est.assumptions} />
      </div>
      {est.electrical.length > 0 && (
        <div className="mt-8">
          <h3 className="font-semibold" style={{ fontSize: 'var(--text)' }}>
            Электрика (оценка по типовым нормам, не проект)
          </h3>
          <ul className="mt-2 grid gap-x-8 gap-y-1.5 text-gray-600 sm:grid-cols-2" style={{ fontSize: 'var(--body)' }}>
            {est.electrical.map((e) => (
              <li key={e.room} className="tnum">
                {e.room}: розетки {e.sockets}, свет {e.light_points}, кабель {num(e.cable_m, 0)} м, автоматы {e.breakers}
              </li>
            ))}
          </ul>
        </div>
      )}
    </Frame>
  )
}

/** "Why these materials": the RAG explanation. Says whether the local model or a template wrote it. */
function Why({ id }: { id: string }) {
  const { mode } = useApp()
  const [data, setData] = useState<Explanation | null>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    let live = true
    setData(null)
    setFailed(false)
    explainEstimate(id, mode)
      .then((x) => live && setData(x))
      .catch(() => live && setFailed(true))
    return () => {
      live = false
    }
  }, [id, mode])
  if (failed) return null
  if (!data) return <Skeleton rows={2} />
  return (
    <div className="mt-6 border-l border-gray-300 pl-4">
      <h3 className="font-semibold" style={{ fontSize: 'var(--text)' }}>
        Почему эти материалы
      </h3>
      <p className="mt-2 max-w-[70ch] text-gray-700" style={{ fontSize: 'var(--body)', lineHeight: 1.6 }}>
        {data.text}
      </p>
      <p className="mt-2 text-gray-500" style={{ fontSize: 'var(--micro)' }}>
        {data.method === 'llm' ? 'Составлено локальной моделью по базе знаний.' : 'Составлено по шаблону из базы знаний.'}
        {data.facts.length ? ` Опора: ${data.facts.map((f) => f.source).filter((v, i, a) => a.indexOf(v) === i).join('; ')}.` : ''}
      </p>
    </div>
  )
}

function Notes({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return (
    <div>
      <h3 className="font-semibold" style={{ fontSize: 'var(--text)' }}>
        {title}
      </h3>
      {items.length ? (
        <ul className="mt-2 space-y-1.5 text-gray-600" style={{ fontSize: 'var(--body)' }}>
          {items.map((w, i) => (
            <li key={i} className="leading-snug">
              {w}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-gray-500" style={{ fontSize: 'var(--body)' }}>
          {empty}
        </p>
      )}
    </div>
  )
}
