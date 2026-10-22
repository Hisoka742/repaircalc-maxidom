// Demo mode: real engine responses recorded by scripts/dump_frontend_fixtures.py from the
// SYNTHETIC demo catalog. Used only when the API does not answer /health.
import raw from '../data/fixtures.json'
import type { Estimate, PropertyRequest, RecommendRequest, Recommendation } from './types'

interface Fixtures {
  generated: string
  catalog: string
  catalog_version: string
  presets: { property_type: string; area: number }[]
  property: Record<string, Estimate>
  recommend: Record<string, Recommendation>
}

const data = raw as unknown as Fixtures

export const DEMO_PRESETS = data.presets
export const DEMO_CATALOG_LABEL = data.catalog

export function fixtureProperty(req: PropertyRequest): Estimate | undefined {
  if (req.tier) return undefined
  const key = `${req.property_type}|${Number(req.total_area_m2)}|${req.renovation_class}`
  const hit = data.property[key]
  return hit ? { ...hit, cached: true } : undefined
}

export function fixtureRecommend(req: RecommendRequest): Recommendation | undefined {
  if (req.tier) return undefined
  return data.recommend[`${req.room_type}|${req.calc}`]
}
