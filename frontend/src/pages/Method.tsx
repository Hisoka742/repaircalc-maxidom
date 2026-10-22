import { useEffect, useRef } from 'react'
import { Frame } from '../components/Marks'
import { Cta } from '../components/ui'
import metrics from '../data/metrics.json'
import { num } from '../lib/format'
import { useGo } from '../lib/nav'
import { setStage } from '../scene/stage'

interface LoadRow {
  label: string
  rps: number
  seconds: number
  requests: number
  ok: number
  errors_5xx: number
  p50: number
  p95: number
  p99: number
}
interface Metrics {
  eval: {
    generated: string
    golden: { cases: number; verified: number; pack_exact: [number, number]; mape_pct: number; mae_packs: number }
  }
  load: LoadRow[]
  rematch: { products: number; seconds: number } | null
}
const M = metrics as unknown as Metrics

// Each step owns one layer of the exploded 3D house: 0 slab, 1 floors, 2 walls, 3 furniture.
const STEPS = [
  {
    layer: 0,
    title: 'Catalog',
    text: 'Файл любого формата (CSV, XLSX, JSON, YML) становится единым каталогом. Заголовки колонок распознаются, неизвестные остаются как характеристики товара.',
  },
  {
    layer: 1,
    title: 'Labels',
    text: 'Правила по названию и категории, затем модель. У каждой метки есть уверенность: сомнительное уходит в очередь ручной проверки, а не в выдачу.',
  },
  {
    layer: 2,
    title: 'Engine',
    text: 'Числа считает детерминированный движок в точной десятичной арифметике. До упаковок округляется один раз, в самом конце, после суммирования по всем комнатам.',
  },
  {
    layer: 3,
    title: 'Basket',
    text: 'Корзина с количеством упаковок, расчётом по каждой позиции и допущениями. Выгрузка сметы в XLSX и PDF для подрядчиков.',
  },
]

const PRINCIPLES = [
  ['Показывай арифметику', 'Каждая позиция раскрывается до расчёта на русском языке.'],
  ['Говори, чего не хватает', 'Если в карточке нет расхода, позиция не считается, а причина выводится предупреждением.'],
  ['Округляй один раз', 'Упаковки округляются вверх только после суммирования по всем помещениям.'],
  ['Безопасность по правилу', 'Правила помещений не ослабляются: во влажной комнате не появится обычный гипсокартон.'],
  ['Три клика до корзины', 'Кратчайший честный путь от параметров комнаты до списка покупок.'],
]

const REQS = [
  ['Общий калькулятор', 'Тип объекта, класс ремонта, площади и помещения дают смету по полу, стенам, обоям и электрике.', '/v1/calc/property'],
  ['Специфика комнаты', 'Влажность и нагрузка задаются на помещение; правила отсеивают небезопасное, например обычный гипсокартон во влажной зоне.', '/v1/calc/property, /v1/recommend'],
  ['Расчёт на карточке товара', 'Покупатель вводит размеры стены, пола или комнаты и сразу получает количество упаковок и сумму.', '/api/v1/product/{id}/calc'],
  ['ML-матчинг каталога', 'Правила и обученная модель привязывают товары к типам работ и помещениям, сомнительное идёт на проверку.', '/v1/catalog/match'],
  ['Рекомендации', 'Жёсткие требования помещения, затем ранжирование по цене и рейтингу товара (recsys_rating).', '/v1/recommend'],
  ['RAG-объяснение', 'Факты из базы знаний и числа сметы; локальная модель только формулирует, числа проверяются.', '/v1/estimate/{id}/explain'],
  ['Запрос своими словами', 'Правила разбирают текст, локальная модель подстраховывает; чего не хватило, спрашиваем.', '/v1/parse'],
  ['Админка привязки', 'Подсказки модели с уверенностью, очередь проверки и подтверждение.', '/v1/catalog/review-queue'],
  ['Закрытый контур', 'Ollama на сервере с RTX 3090, интернет не нужен; без модели работают шаблоны.', 'LLM_BASE_URL'],
]

const NOT_PROVEN = [
  'Качество разметки и извлечения на реальном каталоге Максидом пока не измерено, все ML-цифры получены на синтетических данных.',
  'Ставки работ не заданы, поэтому стоимость работ не считается.',
  'Готовность реальных карточек к расчёту (расход, фасовка) неизвестна до загрузки данных организаторов.',
  'Формулы ещё не сверены с эталонными значениями организаторов.',
  'Нагрузка измерена без Docker и Redis; авторизации нет.',
]

export default function Method() {
  const go = useGo()
  const stepRefs = useRef<(HTMLElement | null)[]>([])
  const revealRefs = useRef<(HTMLElement | null)[]>([])

  useEffect(() => {
    setStage({ mode: 'house', focusRoom: null, explode: 0, layer: -1 })
    // The step in the middle band of the screen decides the exploded layer. IntersectionObserver
    // instead of a scroll listener: no per-frame work on the main thread.
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) setStage({ explode: 1, layer: Number((e.target as HTMLElement).dataset.layer) })
        }
      },
      { rootMargin: '-42% 0px -42% 0px' },
    )
    stepRefs.current.forEach((el) => el && io.observe(el))
    const head = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) setStage({ explode: 0, layer: -1 })
      },
      { rootMargin: '0px 0px -55% 0px' },
    )
    const top = document.getElementById('method-top')
    if (top) head.observe(top)
    const rv = new IntersectionObserver(
      (entries) => {
        for (const e of entries) if (e.isIntersecting) (e.target as HTMLElement).dataset.in = 'true'
      },
      { rootMargin: '0px 0px -8% 0px' },
    )
    revealRefs.current.forEach((el) => el && rv.observe(el))
    return () => {
      io.disconnect()
      head.disconnect()
      rv.disconnect()
      setStage({ explode: 0, layer: -1 })
    }
  }, [])

  const r = (i: number) => (el: HTMLElement | null) => {
    revealRefs.current[i] = el
  }

  return (
    <div style={{ paddingInline: 'var(--pad-x)', paddingBlock: 'var(--main-py)' }}>
      <div className="max-w-[40rem]">
        <div id="method-top" className="rise" style={{ ['--i' as string]: 0 }}>
          <h1 className="font-orbitron font-extrabold uppercase" style={{ fontSize: 'var(--title)', letterSpacing: '0.08em', lineHeight: 1.05 }}>
            Method
          </h1>
          <p className="mt-3 text-gray-600" style={{ fontSize: 'var(--text)', lineHeight: 1.55, textWrap: 'balance' }}>
            Как устроен расчёт, что в нём измерено и что пока не доказано. Справа дом разбирается на слои, по одному на каждый шаг.
          </p>
        </div>

        <ol className="mt-16 space-y-[26vh]" aria-label="Шаги расчёта">
          {STEPS.map((s, i) => (
            <li
              key={s.title}
              ref={(el) => {
                stepRefs.current[i] = el
              }}
              data-layer={s.layer}
              className="reveal"
              data-in="true"
            >
              <h2 className="font-orbitron font-bold uppercase tracking-[0.12em]" style={{ fontSize: 'var(--h2)' }}>
                {s.title}
              </h2>
              <p className="mt-3 max-w-[46ch] text-gray-700" style={{ fontSize: 'var(--text)', lineHeight: 1.6 }}>
                {s.text}
              </p>
            </li>
          ))}
        </ol>

        <section className="mt-[22vh]">
          <h2 className="font-orbitron font-bold uppercase tracking-[0.12em]" style={{ fontSize: 'var(--h2)' }}>
            Principles
          </h2>
          <dl className="mt-6 divide-y divide-gray-200 border-y border-gray-200 bg-white">
            {PRINCIPLES.map(([t, d], i) => (
              <div key={t} ref={r(i)} className="reveal py-4" style={{ ['--i' as string]: 0 }}>
                <dt className="font-semibold" style={{ fontSize: 'var(--text)' }}>
                  {t}
                </dt>
                <dd className="mt-1 max-w-[52ch] text-gray-600" style={{ fontSize: 'var(--body)', lineHeight: 1.55 }}>
                  {d}
                </dd>
              </div>
            ))}
          </dl>
        </section>

        <section className="mt-20">
          <h2 className="font-orbitron font-bold uppercase tracking-[0.12em]" style={{ fontSize: 'var(--h2)' }}>
            Requirements
          </h2>
          <p className="mt-2 text-gray-600" style={{ fontSize: 'var(--body)' }}>
            Что требовал кейс и где это реализовано.
          </p>
          <dl className="mt-6 divide-y divide-gray-200 border-y border-gray-200 bg-white">
            {REQS.map(([t, d, ep]) => (
              <div key={t} className="grid gap-1 py-4 md:grid-cols-[14rem_1fr]">
                <dt className="font-semibold" style={{ fontSize: 'var(--text)' }}>
                  {t}
                </dt>
                <dd className="text-gray-600" style={{ fontSize: 'var(--body)', lineHeight: 1.55 }}>
                  {d} <span className="tnum text-gray-500">{ep}</span>
                </dd>
              </div>
            ))}
          </dl>
        </section>

        <section className="mt-20">
          <h2 className="font-orbitron font-bold uppercase tracking-[0.12em]" style={{ fontSize: 'var(--h2)' }}>
            Measured
          </h2>
          <Frame solid className="mt-6">
            <div ref={r(10)} className="reveal">
              <p className="font-semibold" style={{ fontSize: 'var(--text)' }}>
                Точность расчётов
              </p>
              <p className="mt-2 text-gray-700" style={{ fontSize: 'var(--body)', lineHeight: 1.6 }}>
                Эталонных случаев: {M.eval.golden.cases}, из них сверено с документацией производителей (Ceresit): {M.eval.golden.verified}.
                Точное совпадение по упаковкам: {M.eval.golden.pack_exact[0]} из {M.eval.golden.pack_exact[1]}, средняя абсолютная ошибка (MAE) {num(M.eval.golden.mae_packs, 2)} упаковки. Расхождение по
                непрерывным величинам {num(M.eval.golden.mape_pct, 2)}%, это округление в таблицах производителя. Остальные случаи
                посчитаны вручную по тем же формулам и защищают от регрессий, но не проверяют сами формулы.
              </p>
            </div>

            <div ref={r(11)} className="reveal mt-8">
              <p className="font-semibold" style={{ fontSize: 'var(--text)' }}>
                Скорость, синтетический каталог 10 000 товаров
              </p>
              <p className="mt-1 text-gray-500" style={{ fontSize: 'var(--micro)' }}>
                Один процесс, ноутбук, генератор нагрузки на той же машине.
              </p>
              <div className="mt-3 overflow-x-auto">
                <table className="tnum w-full min-w-[34rem] text-left" style={{ fontSize: 'var(--body)' }}>
                  <caption className="sr-only">Результаты нагрузочных тестов</caption>
                  <thead>
                    <tr className="border-b border-gray-300 text-gray-500">
                      <th className="py-2 pr-4 font-semibold">Сценарий</th>
                      <th className="py-2 pr-4 font-semibold">Нагрузка</th>
                      <th className="py-2 pr-4 text-right font-semibold">Запросов</th>
                      <th className="py-2 pr-4 text-right font-semibold">Ошибок 5xx</th>
                      <th className="py-2 pr-4 text-right font-semibold">p50, мс</th>
                      <th className="py-2 pr-4 text-right font-semibold">p95, мс</th>
                      <th className="py-2 text-right font-semibold">p99, мс</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200">
                    {M.load.map((row) => (
                      <tr key={row.label}>
                        <td className="py-2 pr-4">{row.label}</td>
                        <td className="py-2 pr-4">
                          {row.rps} rps, {row.seconds} с
                        </td>
                        <td className="py-2 pr-4 text-right">{num(row.requests, 0)}</td>
                        <td className="py-2 pr-4 text-right">{row.errors_5xx}</td>
                        <td className="py-2 pr-4 text-right">{row.p50}</td>
                        <td className="py-2 pr-4 text-right">{row.p95}</td>
                        <td className="py-2 text-right">{row.p99}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {M.rematch && (
                <p className="mt-3 text-gray-700" style={{ fontSize: 'var(--body)' }}>
                  Полная перемаркировка {num(M.rematch.products, 0)} товаров (загрузка, извлечение, правила, модель): {M.rematch.seconds} с.
                </p>
              )}
            </div>
          </Frame>
        </section>

        <section className="mt-20">
          <h2 className="font-orbitron font-bold uppercase tracking-[0.12em]" style={{ fontSize: 'var(--h2)' }}>
            Not proven
          </h2>
          <ul ref={r(20)} className="reveal mt-6 space-y-3 bg-white text-gray-700" style={{ fontSize: 'var(--body)', lineHeight: 1.6 }}>
            {NOT_PROVEN.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
          <div className="mt-10">
            <Cta onClick={() => go('/calculator')}>Рассчитать ремонт</Cta>
          </div>
        </section>
      </div>
    </div>
  )
}
