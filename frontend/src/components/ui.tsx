import { ArrowUpRight } from 'lucide-react'
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from 'react'

/** The landing page's liquid-glass button: solid (white) or ghost (frosted), with the shine
 *  sweep on hover and the arrow nudging up and right. */
export function Cta({
  children,
  className = '',
  icon = true,
  solid = false,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { icon?: boolean; solid?: boolean }) {
  return (
    <button
      type="button"
      {...rest}
      className={`group press lp-btn ${solid ? 'lp-btn-solid' : 'lp-btn-ghost'} disabled:cursor-not-allowed disabled:opacity-40 ${className}`}
    >
      <span>{children}</span>
      {icon && (
        <ArrowUpRight
          strokeWidth={1.75}
          className="transition-transform duration-300 group-hover:-translate-y-px group-hover:translate-x-0.5"
          style={{ width: '1.1em', height: '1.1em', transitionTimingFunction: 'var(--ease-out)' }}
        />
      )}
    </button>
  )
}

export function Field({
  label,
  hint,
  children,
  htmlFor,
}: {
  label: string
  hint?: string
  children: ReactNode
  htmlFor?: string
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={htmlFor} className="text-gray-700" style={{ fontSize: 'var(--body)', fontWeight: 600 }}>
        {label}
      </label>
      {children}
      {hint && (
        <p className="text-gray-500" style={{ fontSize: 'var(--micro)' }}>
          {hint}
        </p>
      )}
    </div>
  )
}

export function NumberInput({ suffix, className = '', ...rest }: InputHTMLAttributes<HTMLInputElement> & { suffix?: string }) {
  return (
    <div className="relative">
      <input
        type="number"
        inputMode="decimal"
        {...rest}
        className={`tnum w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-black transition-colors duration-150 focus:border-black focus:outline-none ${className}`}
        style={{ paddingRight: suffix ? '2.6rem' : undefined }}
      />
      {suffix && (
        <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-gray-500" style={{ fontSize: 'var(--body)' }}>
          {suffix}
        </span>
      )}
    </div>
  )
}

/** Mutually exclusive choice as outlined buttons; the selected one is filled. */
export function Segmented<T extends string>({
  value,
  onChange,
  options,
  label,
  columns,
}: {
  value: T
  onChange: (v: T) => void
  options: { value: T; label: string }[]
  label: string
  columns?: number
}) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="grid gap-2"
      style={{ gridTemplateColumns: `repeat(${columns ?? options.length}, minmax(0, 1fr))` }}
    >
      {options.map((o) => {
        const on = o.value === value
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={on}
            onClick={() => onChange(o.value)}
            className={`press rounded-md border px-2 py-2 text-center transition-[background-color,color,border-color] duration-200 ${
              on ? 'border-black bg-black text-white' : 'border-gray-300 bg-white text-black hover-border'
            }`}
            style={{ fontSize: 'var(--body)', fontWeight: 600 }}
          >
            {o.label}
          </button>
        )
      })}
    </div>
  )
}

export function Skeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-4" role="status" aria-label="Считаем">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-start justify-between gap-6 border-b border-gray-200 pb-4">
          <div className="w-3/5 space-y-2">
            <div className="h-3.5 w-full animate-pulse rounded-sm bg-gray-200" />
            <div className="h-3 w-2/5 animate-pulse rounded-sm bg-gray-100" />
          </div>
          <div className="w-1/4 space-y-2">
            <div className="ml-auto h-3.5 w-full animate-pulse rounded-sm bg-gray-200" />
            <div className="ml-auto h-3 w-3/5 animate-pulse rounded-sm bg-gray-100" />
          </div>
        </div>
      ))}
    </div>
  )
}
