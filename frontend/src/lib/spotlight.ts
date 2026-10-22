// One spotlight for the whole stage. The portrait mask and the 3D house shader both read it,
// so a single cursor gesture peels the portrait AND builds the house.
//
// Math is the brief's: the cursor is eased with factor 0.1 per frame (made frame-rate
// independent below) and the radius is round(min(420, max(160, innerWidth * 0.16))).

export const spot = {
  x: 0,
  y: 0,
  radius: 240,
  /** true once a real pointer has moved: the idle drift then stops */
  userDriven: false,
}

const target = { x: 0, y: 0 }
let lastUser = -Infinity
let started = false
let reduced = false
const subs = new Set<() => void>()

export function onSpotlight(fn: () => void): () => void {
  subs.add(fn)
  return () => subs.delete(fn)
}

export function spotlightRadius(): number {
  return Math.round(Math.min(420, Math.max(160, window.innerWidth * 0.16)))
}

export function startSpotlight(): void {
  if (started) return
  started = true
  reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  spot.x = target.x = window.innerWidth * 0.72
  spot.y = target.y = window.innerHeight * 0.42
  spot.radius = spotlightRadius()

  const move = (e: PointerEvent) => {
    // a finger only steers the spotlight while it is down; a mouse always does
    if (e.pointerType === 'touch' && e.buttons === 0 && e.type === 'pointermove') return
    target.x = e.clientX
    target.y = e.clientY
    lastUser = performance.now()
    spot.userDriven = true
  }
  window.addEventListener('pointermove', move, { passive: true })
  window.addEventListener('pointerdown', move, { passive: true })
  window.addEventListener('resize', () => {
    spot.radius = spotlightRadius()
  })

  let prev = performance.now()
  const loop = (now: number) => {
    const dt = Math.min(0.1, (now - prev) / 1000)
    prev = now
    const idle = now - lastUser > 2600
    if (idle && !reduced) {
      // slow Lissajous over the right-centre of the stage: teaches the gesture without a label
      const t = now / 1000
      target.x = window.innerWidth * (0.72 + 0.1 * Math.sin(t * 0.43))
      target.y = window.innerHeight * (0.4 + 0.14 * Math.sin(t * 0.31 + 1.1))
    }
    // 0.1 per frame at 60 fps, expressed per second so 120 Hz screens feel identical
    const k = 1 - Math.pow(1 - 0.1, dt * 60)
    spot.x += (target.x - spot.x) * k
    spot.y += (target.y - spot.y) * k
    subs.forEach((fn) => fn())
    requestAnimationFrame(loop)
  }
  requestAnimationFrame(loop)
}
