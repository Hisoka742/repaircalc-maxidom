// Mirrors docs/API.md. Decimal values arrive as strings and are only formatted here, never summed.

export type RoomType = 'living' | 'bedroom' | 'kitchen' | 'bathroom' | 'kids' | 'hallway' | 'balcony'
export type PropertyType = 'apartment' | 'studio' | 'house'
export type RenovationClass = 'cosmetic' | 'major' | 'designer'
export type Tier = 'economy' | 'standard' | 'premium'

export interface BasketAlt {
  sku: string
  name: string
  price: string | null
}

export interface BasketLine {
  sku: string
  product_id?: string | null
  url?: string | null
  name: string
  qty_packs: number
  unit: string
  unit_price: string | null
  line_total: string
  reason: string
  explain: string[]
  alternatives: BasketAlt[]
}

export interface ElectricalOut {
  room: string
  sockets: number
  switches: number
  light_points: number
  junction_boxes: number
  cable_m: string
  breakers: number
  note: string
}

export interface Estimate {
  estimate_id: string
  kind: 'property' | 'room' | 'product'
  catalog_version: string
  rooms: { room_type: string; area_m2: string; height_m: string; humidity?: string | null; load?: string | null }[]
  basket: { lines: BasketLine[]; materials_total: string }
  labor: null
  warnings: string[]
  assumptions: string[]
  electrical: ElectricalOut[]
  cached: boolean
}

export interface Candidate {
  sku: string
  product_id?: string | null
  rating?: string | null
  in_stock?: boolean | null
  name: string
  price: string | null
  calc: string
  score: number
  price_tier: string | null
  reasons: string[]
}

export interface Recommendation {
  items: Candidate[]
  excluded: { sku: string; reason: string }[]
  excluded_total: number
  warnings: string[]
}

export interface Health {
  status: string
  version: string
  catalog_size: number
  catalog_version: string
  cache: string
  model_loaded: boolean
  llm?: string
}

export type Humidity = 'normal' | 'high'

export interface ParsedRoom {
  room_type: RoomType
  area_m2: string | null
  humidity: string | null
  load: string | null
}

export interface Parsed {
  property_type: PropertyType | null
  renovation_class: RenovationClass | null
  tier: Tier | null
  total_area_m2: string | null
  rooms: ParsedRoom[]
  missing: string[]
  method: 'rules' | 'llm' | 'none'
  notes: string[]
  ready: boolean
}

export interface Explanation {
  text: string
  method: 'llm' | 'template'
  facts: { id: string; text: string; source: string }[]
  note: string
}

export interface CatalogItem {
  sku: string
  product_id: string | null
  name: string
  category_path: string[]
  price: string | null
  brand: string | null
  calc: string
  work_categories: string[]
  room_types: string[]
  properties: string[]
  status: 'auto' | 'review' | 'verified'
  attributes: Record<string, string>
}

export interface Label {
  label: string
  confidence: number
  source: 'rule' | 'model'
  accepted: boolean
  reason: string
}

export interface MatchItem {
  sku: string
  status: 'auto' | 'review'
  calc_template: Label | null
  work_categories: Label[]
  room_types: Label[]
  properties: Label[]
  attributes: Record<string, string>
  reasons: string[]
}

export interface ReviewItem {
  sku: string
  name: string
  suggestion: Label | null
  confidence: number
  reasons: string[]
}

export interface Opening {
  kind: 'door' | 'window'
  width_m: string
  height_m: string
  wall: number
}

export interface RoomGeometry {
  length_m: string
  width_m: string
  height_m: string
  openings: Opening[]
}

export interface RoomSpec {
  room_type: RoomType
  area_m2: string
  humidity?: Humidity | null
  load?: Humidity | null
}

export interface PropertyRequest {
  property_type: PropertyType
  total_area_m2: string
  renovation_class: RenovationClass
  tier?: Tier | null
  rooms?: RoomSpec[] | null
}

export interface RoomRequest {
  room: RoomGeometry
  room_type: RoomType
  renovation_class: RenovationClass
  tier?: Tier | null
  include_ceiling: boolean
  humidity?: Humidity | null
}

export interface ProductCalcRequest {
  wall?: { width_m: string; height_m: string }
  floor?: { length_m: string; width_m: string }
  room_type?: RoomType
  humidity?: Humidity | null
}

export interface RecommendRequest {
  room_type: RoomType
  calc: string
  tier?: Tier | null
  top_k?: number
}
