import { useEffect, useRef, useState } from 'react'
import { HouseScene } from './Scene'

/** Fixed 3D stage behind every page. Pointer-less, aria-hidden; the pages carry all meaning. */
export default function SceneCanvas({ hidden = false }: { hidden?: boolean }) {
  const ref = useRef<HTMLCanvasElement>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    let scene: HouseScene
    try {
      scene = new HouseScene(canvas)
    } catch {
      setFailed(true) // no WebGL: the page still works, only the model is missing
      return
    }
    if (import.meta.env.DEV) (window as unknown as { __scene?: HouseScene }).__scene = scene // dev inspection only
    let raf = 0
    const loop = (t: number) => {
      scene.frame(t)
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    const onResize = () => scene.resize()
    window.addEventListener('resize', onResize)
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', onResize)
      scene.dispose()
    }
  }, [])

  if (failed) return null
  return (
    <canvas
      ref={ref}
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 h-full w-full"
      style={{ zIndex: 'var(--z-bg)', opacity: hidden ? 0 : 1 }}
    />
  )
}
