import * as THREE from 'three'
import { LINE_FRAG, LINE_VERT, SURFACE_FRAG, SURFACE_VERT } from './shaders'

// Plan units are metres. x: west..east, z: north..south, y up. A flat-roof cutaway so the
// rooms read from above. Rooms mirror the presets the backend uses (living, bedroom, ...).

export const WALL_H = 2.7
const T = 0.14

export interface RoomDef {
  id: string
  x0: number
  x1: number
  z0: number
  z1: number
  kind: number // floor pattern: 1 planks, 2 tile, 3 mosaic, 4 decking
}

export const ROOMS: RoomDef[] = [
  { id: 'living', x0: -7, x1: -1, z0: -4.5, z1: 0, kind: 1 },
  { id: 'bedroom', x0: -1, x1: 3.5, z0: -4.5, z1: 0, kind: 1 },
  { id: 'kids', x0: 3.5, x1: 7, z0: -4.5, z1: 0, kind: 1 },
  { id: 'kitchen', x0: -7, x1: -2, z0: 0, z1: 4.5, kind: 2 },
  { id: 'hallway', x0: -2, x1: 1.5, z0: 0, z1: 4.5, kind: 2 },
  { id: 'bathroom', x0: 1.5, x1: 4, z0: 0, z1: 4.5, kind: 3 },
  { id: 'balcony', x0: 4, x1: 7, z0: 0, z1: 4.5, kind: 4 },
]

export interface Opening {
  c: number // centre along the wall
  w: number
  y0: number
  y1: number
}
const door = (c: number): Opening => ({ c, w: 0.9, y0: 0, y1: 2.05 })
const win = (c: number, w = 1.4): Opening => ({ c, w, y0: 0.9, y1: 2.1 })

interface WallDef {
  axis: 'x' | 'z'
  at: number // fixed coordinate
  from: number
  to: number
  open: Opening[]
  h?: number
}

const WALLS: WallDef[] = [
  // exterior
  { axis: 'x', at: -4.5, from: -7, to: 7, open: [win(-4), win(1.2), win(5.2)] },
  { axis: 'x', at: 4.5, from: -7, to: 4, open: [win(-4.5), { c: -0.25, w: 1.0, y0: 0, y1: 2.1 }, win(2.75, 0.6)] },
  { axis: 'z', at: -7, from: -4.5, to: 4.5, open: [win(-2), win(2.2)] },
  { axis: 'z', at: 7, from: -4.5, to: 0, open: [win(-2.2)] },
  // low balcony railing
  { axis: 'x', at: 4.5, from: 4, to: 7, open: [], h: 1.0 },
  { axis: 'z', at: 7, from: 0, to: 4.5, open: [], h: 1.0 },
  // interior
  { axis: 'x', at: 0, from: -7, to: 7, open: [door(-4), door(0.2), door(5.3)] },
  { axis: 'z', at: -1, from: -4.5, to: 0, open: [door(-2)] },
  { axis: 'z', at: 3.5, from: -4.5, to: 0, open: [door(-2)] },
  { axis: 'z', at: -2, from: 0, to: 4.5, open: [door(2)] },
  { axis: 'z', at: 1.5, from: 0, to: 4.5, open: [door(2.5)] },
  { axis: 'z', at: 4, from: 0, to: 4.5, open: [] },
]

// [width x, depth z, height y, centre x, centre z]
const FURNITURE: [number, number, number, number, number][] = [
  [2.0, 0.9, 0.8, -4.5, -3.5], // sofa
  [1.0, 0.6, 0.4, -4.5, -2.2], // coffee table
  [2.0, 1.6, 0.5, 1.2, -3.4], // bed
  [1.7, 0.9, 0.45, 5.3, -3.6], // child bed
  [3.2, 0.6, 0.9, -4.4, 4.1], // kitchen run
  [0.6, 2.2, 0.9, -6.6, 2.4], // kitchen return
  [1.4, 0.8, 0.75, -4.0, 1.8], // table
  [1.7, 0.75, 0.55, 2.8, 3.9], // bathtub
  [1.2, 0.35, 0.9, -0.4, 4.0], // hallway cabinet
]

export const LAYERS = ['slab', 'floors', 'walls', 'furniture'] as const
export type LayerName = (typeof LAYERS)[number]

export interface Shared {
  uMouse: { value: THREE.Vector2 }
  uRadius: { value: number }
  uBase: { value: number }
  uFade: { value: number }
  uLo: { value: number }
  uHi: { value: number }
  uDark: { value: number }
}

export interface House {
  root: THREE.Group
  layers: Record<LayerName, THREE.Group>
  lineMats: Record<LayerName, THREE.ShaderMaterial>
  outlines: Map<string, { mat: THREE.ShaderMaterial; hot: number }>
  /** every part grows from its base during the intro: [mesh, delay seconds] */
  grow: { mesh: THREE.Mesh; delay: number }[]
}

export function makeShared(): Shared {
  return {
    uMouse: { value: new THREE.Vector2(-9999, -9999) },
    uRadius: { value: 240 },
    uBase: { value: 0 },
    uFade: { value: 1 },
    uLo: { value: 0.28 },
    uHi: { value: 0.85 },
    uDark: { value: 0 },
  }
}

// cached per scene (keyed by its uniforms), never module-wide: React StrictMode builds the scene
// twice in dev, and a shared cache would leave the second scene wired to the first one's uniforms
const surfaceMats = new WeakMap<Shared, Map<number, THREE.ShaderMaterial>>()

export function surfaceMat(shared: Shared, kind: number): THREE.ShaderMaterial {
  let byKind = surfaceMats.get(shared)
  if (!byKind) {
    byKind = new Map()
    surfaceMats.set(shared, byKind)
  }
  let m = byKind.get(kind)
  if (!m) {
    m = new THREE.ShaderMaterial({
      vertexShader: SURFACE_VERT,
      fragmentShader: SURFACE_FRAG,
      uniforms: {
        uMouse: shared.uMouse,
        uRadius: shared.uRadius,
        uBase: shared.uBase,
        uFade: shared.uFade,
        uDark: shared.uDark,
        uKind: { value: kind },
      },
      polygonOffset: true, // push surfaces back so the hairlines always win the depth test
      polygonOffsetFactor: 1,
      polygonOffsetUnits: 1,
    })
    byKind.set(kind, m)
  }
  return m
}

export function lineMat(shared: Shared): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    vertexShader: LINE_VERT,
    fragmentShader: LINE_FRAG,
    transparent: true,
    depthWrite: false,
    uniforms: {
      uMouse: shared.uMouse,
      uRadius: shared.uRadius,
      uLo: shared.uLo,
      uHi: shared.uHi,
      uFade: shared.uFade,
      uDark: shared.uDark,
      uHot: { value: 0 },
    },
  })
}

/** A box whose origin is its base centre, so scale.y grows it up from the floor. */
export function box(
  parent: THREE.Object3D,
  w: number,
  h: number,
  d: number,
  x: number,
  y: number,
  z: number,
  surf: THREE.Material,
  lines: THREE.Material,
): THREE.Mesh {
  const geo = new THREE.BoxGeometry(w, h, d)
  geo.translate(0, h / 2, 0)
  const mesh = new THREE.Mesh(geo, surf)
  mesh.position.set(x, y, z)
  const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geo, 25), lines)
  mesh.add(edges)
  parent.add(mesh)
  return mesh
}

function wallParts(def: WallDef): { from: number; to: number; y0: number; y1: number }[] {
  const h = def.h ?? WALL_H
  const parts: { from: number; to: number; y0: number; y1: number }[] = []
  const ops = [...def.open].sort((a, b) => a.c - b.c)
  let cursor = def.from
  for (const o of ops) {
    const a = o.c - o.w / 2
    const b = o.c + o.w / 2
    if (a > cursor) parts.push({ from: cursor, to: a, y0: 0, y1: h })
    if (o.y0 > 0) parts.push({ from: a, to: b, y0: 0, y1: o.y0 }) // sill
    if (o.y1 < h) parts.push({ from: a, to: b, y0: o.y1, y1: h }) // header
    cursor = b
  }
  if (cursor < def.to) parts.push({ from: cursor, to: def.to, y0: 0, y1: h })
  return parts
}

export function buildHouse(shared: Shared): House {
  const root = new THREE.Group()
  const layers = {} as Record<LayerName, THREE.Group>
  const lineMats = {} as Record<LayerName, THREE.ShaderMaterial>
  for (const name of LAYERS) {
    layers[name] = new THREE.Group()
    lineMats[name] = lineMat(shared)
    root.add(layers[name])
  }
  const grow: House['grow'] = []
  const reg = (mesh: THREE.Mesh, base: number) => {
    const dist = Math.hypot(mesh.position.x, mesh.position.z)
    grow.push({ mesh, delay: base + dist * 0.045 })
  }

  // slab
  const slab = box(layers.slab, 14.8, 0.25, 9.8, 0, -0.25, 0, surfaceMat(shared, 0), lineMats.slab)
  reg(slab, 0)

  // floors
  const outlines = new Map<string, { mat: THREE.ShaderMaterial; hot: number }>()
  for (const r of ROOMS) {
    const f = box(
      layers.floors, r.x1 - r.x0 - T, 0.03, r.z1 - r.z0 - T,
      (r.x0 + r.x1) / 2, 0, (r.z0 + r.z1) / 2,
      surfaceMat(shared, r.kind), lineMats.floors,
    )
    reg(f, 0.25)
    // room outline used for the "focused room" highlight
    const pts = [
      new THREE.Vector3(r.x0 + T / 2, 0.045, r.z0 + T / 2),
      new THREE.Vector3(r.x1 - T / 2, 0.045, r.z0 + T / 2),
      new THREE.Vector3(r.x1 - T / 2, 0.045, r.z1 - T / 2),
      new THREE.Vector3(r.x0 + T / 2, 0.045, r.z1 - T / 2),
    ]
    const mat = lineMat(shared)
    // own uniforms (not the shared ones): an outline is invisible until it is focused
    mat.uniforms.uLo = { value: 0 }
    mat.uniforms.uHi = { value: 0 }
    layers.floors.add(new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(pts), mat))
    outlines.set(r.id, { mat, hot: 0 })
  }

  // walls
  const wallSurf = surfaceMat(shared, 0)
  for (const def of WALLS) {
    for (const p of wallParts(def)) {
      const len = p.to - p.from
      const h = p.y1 - p.y0
      const mid = (p.from + p.to) / 2
      const m =
        def.axis === 'x'
          ? box(layers.walls, len, h, T, mid, p.y0, def.at, wallSurf, lineMats.walls)
          : box(layers.walls, T, h, len, def.at, p.y0, mid, wallSurf, lineMats.walls)
      reg(m, 0.5)
    }
  }

  // furniture
  for (const [w, d, h, x, z] of FURNITURE) {
    reg(box(layers.furniture, w, h, d, x, 0.03, z, surfaceMat(shared, 0), lineMats.furniture), 1.1)
  }
  return { root, layers, lineMats, outlines, grow }
}

/** Parametric room for the calculator's "one room" mode: unit boxes scaled to the form values. */
export interface ParamRoom {
  root: THREE.Group
  floor: THREE.Mesh
  walls: THREE.Mesh[] // N, S, E, W
  lines: THREE.ShaderMaterial
}

export function buildParamRoom(shared: Shared): ParamRoom {
  const root = new THREE.Group()
  const lines = lineMat(shared)
  const surf = surfaceMat(shared, 1)
  const wallSurf = surfaceMat(shared, 0)
  const floor = box(root, 1, 1, 1, 0, 0, 0, surf, lines)
  const walls = [0, 1, 2, 3].map(() => box(root, 1, 1, 1, 0, 0, 0, wallSurf, lines))
  return { root, floor, walls, lines }
}

export function updateParamRoom(p: ParamRoom, l: number, w: number, h: number): void {
  const t = 0.12
  p.floor.scale.set(l, 0.06, w)
  p.floor.position.set(0, -0.06, 0)
  const [n, s, e, wst] = p.walls
  n.scale.set(l + t, h, t)
  n.position.set(0, 0, -w / 2)
  s.scale.set(l + t, h, t)
  s.position.set(0, 0, w / 2)
  e.scale.set(t, h, w)
  e.position.set(l / 2, 0, 0)
  wst.scale.set(t, h, w)
  wst.position.set(-l / 2, 0, 0)
}
