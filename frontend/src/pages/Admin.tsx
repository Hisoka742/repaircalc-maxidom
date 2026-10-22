import { useCallback, useEffect, useState } from 'react'
import { Frame } from '../components/Marks'
import { Cta, Field, Segmented, Skeleton } from '../components/ui'
import { ApiError, catalogProducts, confirmReview, matchProduct, reviewQueue } from '../lib/api'
import { CALC_RU, ROOM_RU, rub } from '../lib/format'
import type { CatalogItem, Label, MatchItem, ReviewItem } from '../lib/types'
import { setStage } from '../scene/stage'
import { useApp } from '../state/AppContext'

type Tab = 'queue' | 'catalog' | 'suggest'
const CALC_OPTIONS = Object.keys(CALC_RU)
const pct = (x: number) => `${Math.round(x * 100)}%`

function Chips({ labels, name }: { labels: Label[]; name?: (l: string) => string }) {
  if (!labels.length) return <span className="text-gray-500">нет</span>
  return (
    <span className="flex flex-wrap gap-1.5">
      {labels.map((l) => (
        <span
          key={l.label}
          title={l.reason || (l.source === 'rule' ? 'правило' : 'модель')}
          className={`tnum rounded-md border px-2 py-0.5 ${l.accepted ? 'border-gray-400' : 'border-gray-300 text-gray-500'}`}
        >
          {name ? name(l.label) : l.label} · {pct(l.confidence)}
        </span>
      ))}
    </span>
  )
}

export default function Admin() {
  const { mode } = useApp()
  const demo = mode === 'demo'
  const [tab, setTab] = useState<Tab>('suggest')

  useEffect(() => {
    setStage({ mode: 'house', focusRoom: null })
  }, [])

  return (
    <div style={{ paddingInline: 'var(--pad-x)', paddingBlock: 'var(--main-py)' }}>
      <div className="rise" style={{ ['--i' as string]: 0 }}>
        <h1 className="font-orbitron font-extrabold uppercase" style={{ fontSize: 'var(--title)', lineHeight: 1.05 }}>
          Admin
        </h1>
        <p className="mt-3 max-w-[58ch] text-gray-600" style={{ fontSize: 'var(--text)', lineHeight: 1.55, textWrap: 'balance' }}>
          Привязка товаров к типам работ и помещениям. Модель предлагает метки с уверенностью, уверенные принимаются сами, сомнительные ждут человека.
        </p>
      </div>
      {demo && (
        <p role="status" className="mt-5 max-w-[30rem] border border-gray-300 bg-white p-3 text-gray-700" style={{ fontSize: 'var(--body)' }}>
          Админка работает с живым API: запустите сервис, чтобы увидеть каталог и очередь проверки.
        </p>
      )}
      <div className="mt-6 max-w-xl">
        <Segmented
          label="Раздел"
          value={tab}
          onChange={setTab}
          options={[
            { value: 'suggest', label: 'Новый товар' },
            { value: 'queue', label: 'Очередь проверки' },
            { value: 'catalog', label: 'Каталог' },
          ]}
          columns={3}
        />
      </div>
      <div className="mt-8">
        {tab === 'suggest' && <Suggest />}
        {tab === 'queue' && <Queue />}
        {tab === 'catalog' && <CatalogTab />}
      </div>
    </div>
  )
}

function Suggest() {
  const { mode, toast } = useApp()
  const [name, setName] = useState('Плитка керамическая настенная Kerama Marazzi 20x30 см белая глянцевая')
  const [cat, setCat] = useState('Плитка > Настенная')
  const [desc, setDesc] = useState('В упаковке 1,44 м2')
  const [res, setRes] = useState<MatchItem | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = async () => {
    setBusy(true)
    setError(null)
    try {
      setRes(
        await matchProduct(
          { sku: 'NEW-1', name, category_path: cat.split('>').map((s) => s.trim()).filter(Boolean), description: desc },
          mode,
        ),
      )
    } catch (e) {
      setRes(null)
      setError(e instanceof ApiError ? e.message : 'Не удалось получить подсказку.')
    } finally {
      setBusy(false)
    }
  }
  const input = 'w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-black focus:border-black focus:outline-none'
  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,30rem)_minmax(0,1fr)]">
      <Frame solid>
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault()
            void run()
          }}
        >
          <Field label="Название товара" htmlFor="nm">
            <input id="nm" className={input} value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="Категория на сайте" htmlFor="ct" hint="Через « > », можно пусто">
            <input id="ct" className={input} value={cat} onChange={(e) => setCat(e.target.value)} />
          </Field>
          <Field label="Описание и характеристики" htmlFor="ds">
            <textarea id="ds" rows={3} className={input} value={desc} onChange={(e) => setDesc(e.target.value)} />
          </Field>
          <div>
            <Cta type="submit" disabled={busy}>
              {busy ? 'Определяем' : 'Предложить метки'}
            </Cta>
          </div>
        </form>
      </Frame>
      <div aria-live="polite">
        {error && (
          <p role="alert" className="border border-gray-400 p-3" style={{ fontSize: 'var(--body)' }}>
            {error}
          </p>
        )}
        {busy && <Skeleton rows={3} />}
        {res && !busy && (
          <Frame solid>
            <p style={{ fontSize: 'var(--text)', fontWeight: 600 }}>
              {res.status === 'auto' ? 'Метки приняты автоматически' : 'Нужна проверка человека'}
            </p>
            <dl className="mt-4 space-y-3" style={{ fontSize: 'var(--body)' }}>
              <div>
                <dt className="text-gray-500">Тип калькулятора</dt>
                <dd className="mt-1">{res.calc_template ? <Chips labels={[res.calc_template]} name={(l) => CALC_RU[l] ?? l} /> : <span className="text-gray-500">не определён</span>}</dd>
              </div>
              <div>
                <dt className="text-gray-500">Помещения</dt>
                <dd className="mt-1"><Chips labels={res.room_types} name={(l) => ROOM_RU[l as keyof typeof ROOM_RU] ?? (l === 'any' ? 'любое' : l)} /></dd>
              </div>
              <div>
                <dt className="text-gray-500">Виды работ</dt>
                <dd className="mt-1"><Chips labels={res.work_categories} /></dd>
              </div>
              <div>
                <dt className="text-gray-500">Свойства</dt>
                <dd className="mt-1"><Chips labels={res.properties} /></dd>
              </div>
              <div>
                <dt className="text-gray-500">Извлечённые характеристики</dt>
                <dd className="tnum mt-1">
                  {Object.keys(res.attributes).length ? Object.entries(res.attributes).map(([k, v]) => `${k}: ${v}`).join('; ') : 'нет'}
                </dd>
              </div>
            </dl>
            {res.reasons.length > 0 && (
              <ul className="mt-4 space-y-1 text-gray-600" style={{ fontSize: 'var(--body)' }}>
                {res.reasons.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            )}
            <div className="mt-5">
              <Cta icon={false} onClick={() => toast('Метки сохранены как черновик привязки.')}>
                Принять метки
              </Cta>
            </div>
          </Frame>
        )}
      </div>
    </div>
  )
}

function Queue() {
  const { mode, toast } = useApp()
  const [rows, setRows] = useState<ReviewItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const load = useCallback(() => {
    reviewQueue(mode, 25)
      .then(setRows)
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Очередь недоступна.'))
  }, [mode])
  useEffect(load, [load])

  const confirm = async (r: ReviewItem, calc: string) => {
    try {
      const cur = (await catalogProducts({ q: r.sku, limit: 5 }, mode)).items.find((i) => i.sku === r.sku)
      await confirmReview(
        r.sku,
        {
          work_categories: cur?.work_categories ?? [],
          room_types: cur?.room_types.length ? cur.room_types : ['any'],
          properties: cur?.properties ?? [],
          calc_template: calc,
          reviewer: 'admin',
        },
        mode,
      )
      toast(`Подтверждено: ${r.sku}`)
      setRows((x) => (x ? x.filter((i) => i.sku !== r.sku) : x))
    } catch (e) {
      toast(e instanceof ApiError ? e.message : 'Не удалось сохранить.')
    }
  }

  if (error) return <p role="alert" className="border border-gray-400 p-3" style={{ fontSize: 'var(--body)' }}>{error}</p>
  if (!rows) return <Skeleton rows={4} />
  if (!rows.length) return <p className="text-gray-600" style={{ fontSize: 'var(--text)' }}>Очередь пуста: всё размечено уверенно.</p>
  return (
    <ul className="divide-y divide-gray-200 border-y border-gray-200">
      {rows.map((r) => (
        <QueueRow key={r.sku} r={r} onConfirm={confirm} />
      ))}
    </ul>
  )
}

function QueueRow({ r, onConfirm }: { r: ReviewItem; onConfirm: (r: ReviewItem, calc: string) => void }) {
  const [calc, setCalc] = useState(r.suggestion?.label ?? 'none')
  return (
    <li className="grid gap-3 py-4 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
      <div className="min-w-0">
        <p className="font-semibold leading-snug" style={{ fontSize: 'var(--text)' }}>{r.name}</p>
        <p className="tnum mt-0.5 text-gray-500" style={{ fontSize: 'var(--body)' }}>
          {r.sku} · предложение: {r.suggestion ? `${CALC_RU[r.suggestion.label] ?? r.suggestion.label}, ${pct(r.confidence)}` : 'нет'}
        </p>
        {r.reasons.length > 0 && <p className="mt-1 text-gray-600" style={{ fontSize: 'var(--body)' }}>{r.reasons.join('; ')}</p>}
      </div>
      <div className="flex items-center gap-2">
        <select
          aria-label="Тип калькулятора"
          value={calc}
          onChange={(e) => setCalc(e.target.value)}
          className="rounded-md border border-gray-300 bg-white px-2 py-2 focus:border-black focus:outline-none"
        >
          {[...CALC_OPTIONS, 'none'].map((c) => (
            <option key={c} value={c}>
              {CALC_RU[c] ?? 'не калькулируется'}
            </option>
          ))}
        </select>
        <Cta icon={false} onClick={() => onConfirm(r, calc)}>
          Подтвердить
        </Cta>
      </div>
    </li>
  )
}

function CatalogTab() {
  const { mode } = useApp()
  const [q, setQ] = useState('')
  const [status, setStatus] = useState<'all' | 'auto' | 'review' | 'verified'>('all')
  const [data, setData] = useState<{ total: number; items: CatalogItem[] } | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let live = true
    const t = setTimeout(() => {
      catalogProducts({ q, status: status === 'all' ? '' : status, limit: 25 }, mode)
        .then((r) => live && (setData(r), setError(null)))
        .catch((e) => live && setError(e instanceof ApiError ? e.message : 'Каталог недоступен.'))
    }, 200)
    return () => {
      live = false
      clearTimeout(t)
    }
  }, [q, status, mode])
  return (
    <div>
      <div className="grid max-w-3xl gap-4 md:grid-cols-[1fr_auto]">
        <input
          aria-label="Поиск по названию, артикулу или id"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Поиск по названию, артикулу или id"
          className="rounded-md border border-gray-300 bg-white px-3 py-2 text-black focus:border-black focus:outline-none"
        />
        <Segmented
          label="Статус"
          value={status}
          onChange={setStatus}
          options={[
            { value: 'all', label: 'Все' },
            { value: 'auto', label: 'Авто' },
            { value: 'review', label: 'Проверка' },
          ]}
          columns={3}
        />
      </div>
      {error && <p role="alert" className="mt-4 border border-gray-400 p-3">{error}</p>}
      {data && (
        <>
          <p className="tnum mt-4 text-gray-500" style={{ fontSize: 'var(--body)' }}>Найдено: {data.total}</p>
          <ul className="mt-2 divide-y divide-gray-200 border-y border-gray-200">
            {data.items.map((i) => (
              <li key={i.sku} className="py-3">
                <p className="font-semibold leading-snug" style={{ fontSize: 'var(--text)' }}>{i.name}</p>
                <p className="tnum mt-0.5 text-gray-600" style={{ fontSize: 'var(--body)' }}>
                  {i.sku}
                  {i.price ? ` · ${rub(i.price)}` : ''} · {CALC_RU[i.calc] ?? 'не калькулируется'} ·{' '}
                  {i.room_types.map((r) => ROOM_RU[r as keyof typeof ROOM_RU] ?? 'любое').join(', ')} ·{' '}
                  {i.status === 'auto' ? 'авто' : i.status === 'review' ? 'на проверке' : 'подтверждено'}
                </p>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
