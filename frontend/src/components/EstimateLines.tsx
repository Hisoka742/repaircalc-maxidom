import { ChevronRight } from 'lucide-react'
import { useState } from 'react'
import { qty, rub } from '../lib/format'
import type { BasketLine } from '../lib/types'

/** Basket lines. Every line opens into its calculation trace: the product's whole point is that
 *  a number can be checked, so the trace is one click away everywhere a quantity is shown. */
export default function EstimateLines({ lines, compact = false }: { lines: BasketLine[]; compact?: boolean }) {
  const [open, setOpen] = useState<string | null>(null)
  return (
    <ul className="divide-y divide-gray-200 border-y border-gray-200">
      {lines.map((ln, i) => {
        const isOpen = open === ln.sku
        const panelId = `trace-${ln.sku}`
        return (
          <li key={ln.sku} className="rise py-4" style={{ ['--i' as string]: Math.min(i, 8) }}>
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <p className="font-semibold leading-snug" style={{ fontSize: 'var(--text)' }}>
                  {ln.name}
                </p>
                <p className="mt-0.5 text-gray-500" style={{ fontSize: 'var(--body)' }}>
                  Артикул {ln.sku}
                  {!compact && ln.reason ? `. ${ln.reason[0].toUpperCase()}${ln.reason.slice(1)}` : ''}
                </p>
              </div>
              <div className="shrink-0 text-right">
                <p className="tnum font-semibold" style={{ fontSize: 'var(--text)' }}>
                  {rub(ln.line_total)}
                </p>
                <p className="tnum text-gray-500" style={{ fontSize: 'var(--body)' }}>
                  {qty(ln.qty_packs, ln.unit)}
                  {ln.unit_price ? ` по ${rub(ln.unit_price)}` : ''}
                </p>
              </div>
            </div>
            <button
              type="button"
              aria-expanded={isOpen}
              aria-controls={panelId}
              onClick={() => setOpen(isOpen ? null : ln.sku)}
              className="press link-fade mt-2 inline-flex items-center gap-1 py-1 uppercase text-gray-600"
              style={{ fontSize: 'var(--micro)', letterSpacing: '0.18em' }}
            >
              <ChevronRight
                strokeWidth={1.5}
                style={{ width: '0.9em', height: '0.9em', transform: isOpen ? 'rotate(90deg)' : 'none', transition: 'transform 200ms var(--ease-out)' }}
              />
              Как посчитано
            </button>
            {isOpen && (
              <div id={panelId} className="rise mt-1 border-l border-gray-300 pl-4 text-gray-700" style={{ fontSize: 'var(--body)' }}>
                <ol className="space-y-1.5">
                  {ln.explain.map((line, k) => (
                    <li key={k} className="tnum leading-snug">
                      {line}
                    </li>
                  ))}
                </ol>
                {ln.alternatives.length > 0 && (
                  <p className="mt-3 text-gray-500">
                    Аналоги: {ln.alternatives.map((a) => `${a.name}${a.price ? ` (${rub(a.price)})` : ''}`).join('; ')}
                  </p>
                )}
              </div>
            )}
          </li>
        )
      })}
    </ul>
  )
}
