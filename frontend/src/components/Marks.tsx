import type { CSSProperties, ReactNode } from 'react'

type Corner = 'tl' | 'tr' | 'bl' | 'br'

const PATHS: Record<Corner, string> = {
  tl: 'M0 11.5V0.5H11.5',
  tr: 'M0.5 0.5H11.5V11.5',
  bl: 'M0 0.5V11.5H11.5',
  br: 'M0.5 11.5H11.5V0.5',
}

/** One of the four L-shaped corner brackets (the brief's paths, viewBox 0 0 12 12). */
export function CornerBracket({ corner, className = '', style }: { corner: Corner; className?: string; style?: CSSProperties }) {
  return (
    <svg
      viewBox="0 0 12 12"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      aria-hidden="true"
      className={`shrink-0 ${className}`}
      style={{ width: 'var(--corner)', height: 'var(--corner)', ...style }}
    >
      <path d={PATHS[corner]} />
    </svg>
  )
}

/** A framed region: four brackets at the corners and no fill, so the 3D stage reads through it.
 *  `solid` paints it white for dense data (tables) where lines behind would hurt legibility. */
export function Frame({
  children,
  className = '',
  solid = false,
  pad = true,
}: {
  children: ReactNode
  className?: string
  solid?: boolean
  pad?: boolean
}) {
  return (
    <div className={`relative ${solid ? 'bg-white' : ''} ${className}`} style={pad ? { padding: 'var(--feature-pad)' } : undefined}>
      <CornerBracket corner="tl" className="absolute left-0 top-0" />
      <CornerBracket corner="tr" className="absolute right-0 top-0" />
      <CornerBracket corner="bl" className="absolute bottom-0 left-0" />
      <CornerBracket corner="br" className="absolute bottom-0 right-0" />
      {children}
    </div>
  )
}

/** Checkerboard grid: 4 rows of 3.8 squares, even rows shifted by 2.25 (viewBox 0 0 36 18). */
export function Checker({ className = '' }: { className?: string }) {
  const rects: ReactNode[] = []
  let k = 0
  for (let row = 0; row < 4; row++) {
    const shift = row % 2 === 1 ? 2.25 : 0
    for (let col = 0; col < 7; col++) {
      rects.push(
        <rect key={`${row}-${col}`} x={col * 4.7 + shift} y={row * 4.7} width={3.8} height={3.8} fill="currentColor" style={{ ['--k' as string]: k++ }} />,
      )
    }
  }
  return (
    <svg
      viewBox="0 0 36 18"
      aria-hidden="true"
      className={`checker inline-block ${className}`}
      style={{ width: 'var(--checker-w)', height: 'var(--checker-h)', transform: 'translateY(2px)' }}
    >
      {rects}
    </svg>
  )
}

/** Wireframe globe, viewBox 0 0 64 64, stroke 1.2. */
export function Globe() {
  return (
    <svg
      viewBox="0 0 64 64"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.2}
      aria-hidden="true"
      className="shrink-0"
      style={{ width: 'var(--globe)', height: 'var(--globe)' }}
    >
      <circle cx="32" cy="32" r="28" />
      <path d="M4 32H60" />
      <ellipse cx="32" cy="32" rx="28" ry="11" />
      <ellipse cx="32" cy="32" rx="28" ry="21" />
      <path d="M32 4V60" />
      <ellipse cx="32" cy="32" rx="11" ry="28" />
      <ellipse cx="32" cy="32" rx="21" ry="28" />
    </svg>
  )
}
