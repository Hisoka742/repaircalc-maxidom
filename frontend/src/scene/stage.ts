// Mutable, non-React state the 3D stage reads every frame. Pages write to it from effects;
// nothing here triggers a React render (continuous values must never live in useState).

export type Route = 'home' | 'calculator' | 'catalog' | 'method'
export type StageMode = 'house' | 'room'

export interface Stage {
  route: Route
  /** dark theme: the model is drawn in light lines on a dark ground */
  dark: boolean
  /** house = the whole cutaway model; room = a parametric single room from the form */
  mode: StageMode
  /** room id (living, kitchen, ...) lit up in the house, or null */
  focusRoom: string | null
  /** parametric room size in metres */
  room: { l: number; w: number; h: number }
  /** exploded-view amount for the method page, 0..1 */
  explode: number
  /** layer emphasised in the exploded view: 0 slab, 1 floors, 2 walls, 3 furniture, -1 none */
  layer: number
}

export const stage: Stage = {
  route: 'home',
  dark: false,
  mode: 'house',
  focusRoom: null,
  room: { l: 4, w: 3, h: 2.7 },
  explode: 0,
  layer: -1,
}

export function setStage(patch: Partial<Stage>): void {
  Object.assign(stage, patch)
}
