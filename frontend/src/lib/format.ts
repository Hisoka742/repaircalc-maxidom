const money = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2, minimumFractionDigits: 0 })

/** "17300.00" -> "17 300 ₽". Display only; the API owns every sum. */
export function rub(value: string | null | undefined): string {
  if (value == null) return 'нет цены'
  const n = Number(value)
  return Number.isFinite(n) ? `${money.format(n)} ₽` : value
}

export function num(value: string | number, digits = 2): string {
  const n = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(n) ? new Intl.NumberFormat('ru-RU', { maximumFractionDigits: digits }).format(n) : String(value)
}

const UNIT_FORMS: Record<string, [string, string, string]> = {
  'уп': ['упаковка', 'упаковки', 'упаковок'],
  'шт': ['штука', 'штуки', 'штук'],
  'рулон': ['рулон', 'рулона', 'рулонов'],
}

/** 1 -> "1 упаковка", 3 -> "3 упаковки", 7 -> "7 упаковок" */
export function qty(n: number, unit: string): string {
  const forms = UNIT_FORMS[unit]
  if (!forms) return `${n} ${unit}`
  const mod10 = n % 10
  const mod100 = n % 100
  const form =
    mod10 === 1 && mod100 !== 11 ? forms[0] : mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14) ? forms[1] : forms[2]
  return `${n} ${form}`
}

export function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10
  const mod100 = n % 100
  const form = mod10 === 1 && mod100 !== 11 ? one : mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14) ? few : many
  return `${n} ${form}`
}

export const ROOM_RU: Record<string, string> = {
  living: 'Гостиная',
  bedroom: 'Спальня',
  kitchen: 'Кухня',
  bathroom: 'Ванная',
  kids: 'Детская',
  hallway: 'Прихожая',
  balcony: 'Балкон',
}

export const CLASS_RU: Record<string, string> = {
  cosmetic: 'Косметический',
  major: 'Капитальный',
  designer: 'Дизайнерский',
}

export const PROPERTY_RU: Record<string, string> = {
  apartment: 'Квартира',
  studio: 'Студия',
  house: 'Дом',
}

export const TIER_RU: Record<string, string> = {
  economy: 'Эконом',
  standard: 'Стандарт',
  premium: 'Премиум',
}

export const CALC_RU: Record<string, string> = {
  paint: 'Краска',
  primer: 'Грунтовка',
  putty: 'Шпатлёвка',
  wallpaper: 'Обои',
  laminate: 'Ламинат',
  underlay: 'Подложка',
  skirting: 'Плинтус',
  tile: 'Плитка',
  tile_adhesive: 'Плиточный клей',
  grout: 'Затирка',
  self_leveling: 'Наливной пол',
  waterproofing: 'Гидроизоляция',
  drywall: 'Гипсокартон',
  electrical: 'Электрика',
}
