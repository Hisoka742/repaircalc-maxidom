import * as THREE from 'three'
import { spot } from '../lib/spotlight'
import {
  LAYERS,
  ROOMS,
  buildHouse,
  buildParamRoom,
  makeShared,
  updateParamRoom,
  type House,
  type ParamRoom,
  type Shared,
} from './house'
import { stage, type Route } from './stage'

interface Rig {
  dir: THREE.Vector3 // camera direction from the look-at point
  dist: number
  look: THREE.Vector3
  shiftX: number // fraction of the viewport the model is pushed right
  shiftY: number
  base: number // stipple level: how much of the house is "built" outside the spotlight
  lo: number // blueprint line opacity
  orbit: number // auto-orbit amplitude (rad)
}

const ease = (t: number) => 1 - Math.pow(1 - Math.min(1, Math.max(0, t)), 4) // easeOutQuart
const damp = (k: number, dt: number) => 1 - Math.exp(-k * dt)

export class HouseScene {
  private renderer: THREE.WebGLRenderer
  private scene = new THREE.Scene()
  private camera = new THREE.PerspectiveCamera(26, 1, 0.5, 400)
  private shared: Shared = makeShared()
  private house: House
  private param: ParamRoom
  private w = 1
  private h = 1
  private dpr = 1
  private reduced: boolean
  private t0 = performance.now()
  private last = performance.now()
  private slow = 0

  // damped state
  private pos = new THREE.Vector3(24, 22, 30)
  private look = new THREE.Vector3(0, 1, 0)
  private dist = 36
  private shiftX = 0.2
  private shiftY = 0
  private base = 0
  private lo = 0.28
  private blend = 0 // 0 house, 1 parametric room
  private explode = 0
  private pulse = 1
  private lastRoute: Route = stage.route
  private dark = 0
  private growStart = -1 // seconds; the house builds itself when the user leaves the landing page
  private roomDims = { l: 4, w: 3, h: 2.7 }

  constructor(canvas: HTMLCanvasElement) {
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'high-performance' })
    this.renderer.setClearColor(0xffffff, 0)
    this.reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    this.house = buildHouse(this.shared)
    this.param = buildParamRoom(this.shared)
    this.param.root.visible = false
    this.scene.add(this.house.root, this.param.root)
    this.resize()
  }

  resize(): void {
    this.w = Math.max(1, window.innerWidth)
    this.h = Math.max(1, window.innerHeight)
    this.dpr = Math.min(window.devicePixelRatio || 1, 1.75)
    this.renderer.setPixelRatio(this.dpr)
    this.renderer.setSize(this.w, this.h, false)
    this.camera.aspect = this.w / this.h
    this.camera.updateProjectionMatrix()
  }

  private rig(): Rig {
    const mobile = this.w < 1024
    const portrait = this.w / this.h < 0.9
    const r = stage.route
    const focus = stage.focusRoom ? ROOMS.find((x) => x.id === stage.focusRoom) : undefined
    const a = Math.min(1, this.w / this.h / 1.78)
    const D = (v: number) => (portrait ? v * 1.55 : v * (1 + (1 - a) * 0.45))
    const X = (v: number) => (mobile ? 0 : v + (1 - a) * 0.1)

    if (stage.mode === 'room') {
      const span = Math.max(stage.room.l, stage.room.w, stage.room.h * 1.2)
      return {
        dir: new THREE.Vector3(0.62, 0.55, 0.78).normalize(),
        dist: D(span * 3.1 + 5),
        look: new THREE.Vector3(0, stage.room.h * 0.35, 0),
        shiftX: X(0.27),
        shiftY: mobile ? -0.2 : 0,
        base: 0.1,
        lo: 0.4,
        orbit: 0.22,
      }
    }
    switch (r) {
      case 'calculator':
        return {
          dir: new THREE.Vector3(0.55, 0.78, 0.72).normalize(),
          dist: D(46),
          look: focus ? new THREE.Vector3((focus.x0 + focus.x1) / 2, 0, (focus.z0 + focus.z1) / 2).multiplyScalar(0.6) : new THREE.Vector3(0, 0, 0),
          shiftX: X(0.31),
          shiftY: mobile ? -0.25 : -0.02,
          base: 0.12,
          lo: 0.3,
          orbit: 0.2,
        }
      case 'catalog': {
        const c = focus ? new THREE.Vector3((focus.x0 + focus.x1) / 2, 0.4, (focus.z0 + focus.z1) / 2) : new THREE.Vector3(0, 0, 0)
        return {
          dir: new THREE.Vector3(0.42, 0.66, 0.62).normalize(),
          dist: D(focus ? 30 : 42),
          look: c,
          shiftX: X(0.3),
          shiftY: mobile ? -0.25 : 0,
          base: 0.1,
          lo: 0.34,
          orbit: 0.14,
        }
      }
      case 'method':
        return {
          dir: new THREE.Vector3(0.7 - this.explode * 0.35, 0.5 + this.explode * 0.12, 0.7).normalize(),
          dist: D(42 + this.explode * 10),
          look: new THREE.Vector3(0, 0.8 + this.explode * 2.4, 0),
          shiftX: X(0.3),
          shiftY: mobile ? -0.22 : 0,
          base: 0.1,
          lo: 0.3,
          orbit: 0.12,
        }
      default: {
        // Home: the portrait owns the centre, so the house sits to its right. The narrower the
        // viewport, the further right and the smaller, so it never covers her face.
        return {
          dir: new THREE.Vector3(0.56, 0.62, 0.78).normalize(),
          dist: D(47),
          look: new THREE.Vector3(0, 0.6, 0),
          shiftX: X(0.3),
          shiftY: mobile ? -0.27 : -0.05,
          base: 0,
          lo: mobile ? 0.2 : 0.3,
          orbit: 0.14,
        }
      }
    }
  }

  frame(nowMs: number): void {
    const dt = Math.min(0.08, (nowMs - this.last) / 1000)
    this.last = nowMs
    const t = (nowMs - this.t0) / 1000
    const instant = this.reduced
    const kCam = instant ? 1 : damp(2.4, dt)

    // the landing page is pure white and has no model: nothing to draw, nothing to pay for
    if (stage.route === 'home') {
      this.growStart = -1
      return
    }
    this.dark += ((stage.dark ? 1 : 0) - this.dark) * (instant ? 1 : damp(9, dt))
    this.shared.uDark.value = this.dark
    if (this.growStart < 0) {
      this.growStart = t + (instant ? 0 : 0.3) // starts under the wipe, once the circle has opened
      this.pulse = 1
    }

    // adaptive quality: a slow device drops to 1x pixel ratio instead of stuttering
    this.slow = this.slow * 0.95 + dt * 0.05
    if (this.slow > 0.028 && this.dpr > 1) {
      this.dpr = 1
      this.renderer.setPixelRatio(1)
      this.renderer.setSize(this.w, this.h, false)
    }

    if (stage.route !== this.lastRoute) {
      this.lastRoute = stage.route
      this.pulse = 1 // re-materialise: a stipple flash and a small dolly on every page change
    }
    this.pulse *= instant ? 0 : Math.exp(-dt * 2.6)

    // ---- camera rig
    const rig = this.rig()
    const mx = (spot.x / this.w - 0.5) * 2
    const my = (spot.y / this.h - 0.5) * 2
    const az = (instant ? 0 : Math.sin(t * 0.12) * rig.orbit) + mx * 0.07
    const dir = rig.dir.clone().applyAxisAngle(new THREE.Vector3(0, 1, 0), az)
    dir.y += -my * 0.03
    const wantDist = rig.dist * (1 + this.pulse * 0.07)
    this.dist += (wantDist - this.dist) * kCam
    this.look.lerp(rig.look, kCam)
    this.shiftX += (rig.shiftX - this.shiftX) * kCam
    this.shiftY += (rig.shiftY - this.shiftY) * kCam
    this.base += (rig.base - this.base) * kCam
    this.lo += (rig.lo - this.lo) * kCam
    this.pos.copy(this.look).addScaledVector(dir.normalize(), this.dist)
    this.camera.position.copy(this.pos)
    this.camera.lookAt(this.look)
    this.camera.setViewOffset(
      this.w, this.h, -this.shiftX * this.w, -this.shiftY * this.h, this.w, this.h,
    )

    // ---- uniforms shared by every surface and line
    this.shared.uMouse.value.set(spot.x * this.dpr, (this.h - spot.y) * this.dpr)
    this.shared.uRadius.value = spot.radius * this.dpr
    this.shared.uBase.value = Math.min(1, this.base + this.pulse * 0.55)
    this.shared.uLo.value = this.lo

    // ---- house <-> parametric room
    const wantBlend = stage.mode === 'room' ? 1 : 0
    this.blend += (wantBlend - this.blend) * (instant ? 1 : damp(3.2, dt))
    const hb = Math.max(0.0001, 1 - ease(this.blend))
    this.house.root.visible = this.blend < 0.995
    this.house.root.scale.y = hb
    this.param.root.visible = this.blend > 0.005
    this.param.root.scale.y = Math.max(0.0001, ease(this.blend))
    if (this.param.root.visible) {
      const k = instant ? 1 : damp(6, dt)
      this.roomDims.l += (stage.room.l - this.roomDims.l) * k
      this.roomDims.w += (stage.room.w - this.roomDims.w) * k
      this.roomDims.h += (stage.room.h - this.roomDims.h) * k
      updateParamRoom(this.param, this.roomDims.l, this.roomDims.w, this.roomDims.h)
    }

    // ---- intro: every part grows from its base, walls last
    if (!instant) {
      for (const g of this.house.grow) g.mesh.scale.y = Math.max(0.0001, ease((t - this.growStart - g.delay) / 0.9))
    }

    // ---- exploded view (method page)
    this.explode += (stage.explode - this.explode) * (instant ? 1 : damp(3, dt))
    const offs = [-1.3, 0.55, 2.6, 5.0]
    LAYERS.forEach((name, i) => {
      this.house.layers[name].position.y = offs[i] * this.explode * 1.6
      const hot = stage.layer === i ? 1 : 0
      const m = this.house.lineMats[name]
      const cur = m.uniforms.uHot.value as number
      m.uniforms.uHot.value = cur + (hot * 0.5 - cur) * (instant ? 1 : damp(6, dt))
    })

    // ---- focused room outline
    for (const [id, o] of this.house.outlines) {
      const want = stage.focusRoom === id ? 1 : 0
      o.hot += (want - o.hot) * (instant ? 1 : damp(7, dt))
      o.mat.uniforms.uHot.value = o.hot
    }

    this.renderer.render(this.scene, this.camera)
  }

  dispose(): void {
    this.scene.traverse((o) => {
      const m = o as THREE.Mesh
      if (m.geometry) m.geometry.dispose()
    })
    this.renderer.dispose()
  }
}
