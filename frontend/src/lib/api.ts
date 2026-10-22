import { fixtureProperty, fixtureRecommend } from './fixtures'
import type {
  CatalogItem,
  Estimate,
  Explanation,
  Health,
  MatchItem,
  Parsed,
  ProductCalcRequest,
  ReviewItem,
  PropertyRequest,
  RecommendRequest,
  Recommendation,
  RoomGeometry,
  RoomRequest,
  RoomType,
} from './types'

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? ''

export class ApiError extends Error {
  details: { field: string; message: string }[]
  constructor(message: string, details: { field: string; message: string }[] = []) {
    super(message)
    this.name = 'ApiError'
    this.details = details
  }
}

/** The backend answers every failure with {error:{message,details}} in Russian. */
async function parseError(res: Response): Promise<ApiError> {
  try {
    const body = (await res.json()) as { error?: { message?: string; details?: { field: string; message: string }[] } }
    const e = body.error
    if (e?.message) {
      const detail = e.details?.map((d) => `${d.field}: ${d.message}`).join('; ')
      return new ApiError(detail ? `${e.message}. ${detail}` : e.message, e.details ?? [])
    }
  } catch {
    /* fall through */
  }
  return new ApiError(`Сервис вернул ошибку ${res.status}`)
}

async function post<T>(path: string, body: unknown): Promise<T> {
  let res: Response
  try {
    res = await fetch(BASE + path, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch {
    throw new ApiError('Нет связи с сервисом расчёта')
  }
  if (!res.ok) throw await parseError(res)
  return (await res.json()) as T
}

export type BackendMode = 'checking' | 'live' | 'demo'

/** Live API if /health answers quickly; otherwise saved demo responses (offline rehearsal). */
export async function detectBackend(): Promise<{ mode: BackendMode; health: Health | null }> {
  try {
    const ctl = new AbortController()
    const t = setTimeout(() => ctl.abort(), 1800)
    const res = await fetch(BASE + '/health', { signal: ctl.signal })
    clearTimeout(t)
    if (res.ok) return { mode: 'live', health: (await res.json()) as Health }
  } catch {
    /* demo */
  }
  return { mode: 'demo', health: null }
}

const DEMO_HINT = 'Демо-режим: доступны только готовые расчёты. Запустите API для произвольных значений.'

export async function calcProperty(req: PropertyRequest, mode: BackendMode): Promise<Estimate> {
  if (mode === 'demo') {
    const hit = fixtureProperty(req)
    if (!hit) throw new ApiError(DEMO_HINT)
    return hit
  }
  return post<Estimate>('/v1/calc/property', { ...req, tier: req.tier ?? null })
}

export async function calcRoom(req: RoomRequest, mode: BackendMode): Promise<Estimate> {
  if (mode === 'demo') throw new ApiError(DEMO_HINT)
  return post<Estimate>('/v1/calc/room', { ...req, tier: req.tier ?? null })
}

export async function recommend(req: RecommendRequest, mode: BackendMode): Promise<Recommendation> {
  if (mode === 'demo') {
    const hit = fixtureRecommend(req)
    if (!hit) throw new ApiError(DEMO_HINT)
    return hit
  }
  return post<Recommendation>('/v1/recommend', { top_k: 5, ...req, tier: req.tier ?? null })
}

export async function productQuantity(
  sku: string,
  room: RoomGeometry,
  roomType: RoomType,
  includeCeiling: boolean,
  mode: BackendMode,
): Promise<Estimate> {
  if (mode === 'demo') throw new ApiError(DEMO_HINT)
  return post<Estimate>(`/v1/products/${encodeURIComponent(sku)}/quantity`, {
    room,
    room_type: roomType,
    include_ceiling: includeCeiling,
  })
}

const LIVE_ONLY = 'Эта функция работает при запущенном API.'

async function get<T>(path: string): Promise<T> {
  let res: Response
  try {
    res = await fetch(BASE + path)
  } catch {
    throw new ApiError('Нет связи с сервисом расчёта')
  }
  if (!res.ok) throw await parseError(res)
  return (await res.json()) as T
}

/** Free text ("санузел 6 м², высокая влажность") -> calculator input. */
export async function parseText(text: string, mode: BackendMode): Promise<Parsed> {
  if (mode === 'demo') throw new ApiError(LIVE_ONLY)
  return post<Parsed>('/v1/parse', { text })
}

/** "Why these materials": RAG over the knowledge base, local LLM or a template. */
export async function explainEstimate(id: string, mode: BackendMode): Promise<Explanation> {
  if (mode === 'demo') throw new ApiError(LIVE_ONLY)
  return post<Explanation>(`/v1/estimate/${id}/explain`, {})
}

/** The product-card calculator the case brief names: /api/v1/product/{id}/calc. */
export async function productCalc(id: string, req: ProductCalcRequest, mode: BackendMode): Promise<Estimate> {
  if (mode === 'demo') throw new ApiError(LIVE_ONLY)
  return post<Estimate>(`/api/v1/product/${encodeURIComponent(id)}/calc`, req)
}

export async function catalogProducts(
  params: { q?: string; status?: string; calc?: string; limit?: number; offset?: number },
  mode: BackendMode,
): Promise<{ total: number; items: CatalogItem[] }> {
  if (mode === 'demo') throw new ApiError(LIVE_ONLY)
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== '') qs.set(k, String(v))
  return get(`/v1/catalog/products?${qs}`)
}

export async function reviewQueue(mode: BackendMode, limit = 30): Promise<ReviewItem[]> {
  if (mode === 'demo') throw new ApiError(LIVE_ONLY)
  return get(`/v1/catalog/review-queue?limit=${limit}`)
}

export async function matchProduct(
  p: { sku: string; name: string; category_path: string[]; description: string; price?: string | null },
  mode: BackendMode,
): Promise<MatchItem> {
  if (mode === 'demo') throw new ApiError(LIVE_ONLY)
  const r = await post<{ results: MatchItem[] }>('/v1/catalog/match', { products: [p] })
  return r.results[0]
}

export async function confirmReview(
  sku: string,
  body: { work_categories: string[]; room_types: string[]; properties: string[]; calc_template: string; reviewer: string },
  mode: BackendMode,
): Promise<void> {
  if (mode === 'demo') throw new ApiError(LIVE_ONLY)
  await post(`/v1/catalog/review/${encodeURIComponent(sku)}`, body)
}

export async function exportEstimate(id: string, format: 'xlsx' | 'pdf', mode: BackendMode): Promise<void> {
  if (mode === 'demo') throw new ApiError('Экспорт доступен при запущенном API.')
  let res: Response
  try {
    res = await fetch(`${BASE}/v1/estimate/${id}/export?format=${format}`, { method: 'POST' })
  } catch {
    throw new ApiError('Нет связи с сервисом расчёта')
  }
  if (!res.ok) throw await parseError(res)
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `smeta-${id}.${format}`
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 2000)
}
