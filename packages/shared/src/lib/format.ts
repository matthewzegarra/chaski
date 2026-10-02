/** Formatters for the Peruvian market. Dates are always shown in Lima time. */

const TZ = 'America/Lima'
const number2 = new Intl.NumberFormat('en-US', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})
const number0 = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 })
const SYMBOL: Record<string, string> = { PEN: 'S/', USD: 'US$' }

/** formatMoney(1234.5) -> "S/ 1,234.50"; negatives as "-S/ 12.00". */
export function formatMoney(amount: number | string | null | undefined, currency = 'PEN'): string {
  const value = Number(amount ?? 0)
  const symbol = SYMBOL[currency] ?? currency
  const sign = value < 0 ? '-' : ''
  return `${sign}${symbol} ${number2.format(Math.abs(value))}`
}

/** Compact amounts for dashboards: S/ 1.2 M, S/ 350 K. */
export function formatCompactMoney(amount: number, currency = 'PEN'): string {
  const symbol = SYMBOL[currency] ?? currency
  const abs = Math.abs(amount)
  if (abs >= 1_000_000) return `${symbol} ${(amount / 1_000_000).toFixed(1)} M`
  if (abs >= 1_000) return `${symbol} ${(amount / 1_000).toFixed(0)} K`
  return formatMoney(amount, currency)
}

export function formatNumber(value: number): string {
  return number0.format(value)
}

export function formatPercent(value: number, digits = 1): string {
  return `${value.toFixed(digits)} %`
}

const dateFmt = new Intl.DateTimeFormat('es-PE', {
  timeZone: TZ,
  day: '2-digit',
  month: 'short',
  year: 'numeric',
})
const dateTimeFmt = new Intl.DateTimeFormat('es-PE', {
  timeZone: TZ,
  day: '2-digit',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

const calendarFmt = new Intl.DateTimeFormat('es-PE', {
  timeZone: 'UTC',
  day: '2-digit',
  month: 'short',
  year: 'numeric',
})

export function formatDate(iso: string | Date | null | undefined): string {
  if (!iso) return '—'
  // "1994-03-21" is a calendar date (birth date, due date): never shift it by time zone.
  if (typeof iso === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(iso)) {
    return calendarFmt.format(new Date(`${iso}T00:00:00Z`)).replace('.', '')
  }
  return dateFmt.format(new Date(iso)).replace('.', '')
}

export function formatDateTime(iso: string | Date | null | undefined): string {
  if (!iso) return '—'
  return dateTimeFmt.format(new Date(iso)).replace('.', '')
}

/** "hace 5 min", "hace 2 h", or the date when older than a day. */
export function formatRelative(iso: string | Date, now: Date = new Date()): string {
  const diff = Math.round((now.getTime() - new Date(iso).getTime()) / 1000)
  if (diff < 60) return 'hace un momento'
  if (diff < 3600) return `hace ${Math.floor(diff / 60)} min`
  if (diff < 86400) return `hace ${Math.floor(diff / 3600)} h`
  return formatDate(iso)
}

/** Monthly payment of a French-amortisation loan (mirrors core-api loan_math). */
export function monthlyPayment(amount: number, tea: number, months: number): number {
  const i = Math.pow(1 + tea, 1 / 12) - 1
  return Math.round(((amount * i) / (1 - Math.pow(1 + i, -months))) * 100) / 100
}

export const TX_LABELS: Record<string, string> = {
  DEPOSITO: 'Depósito',
  RETIRO: 'Retiro',
  TRANSFERENCIA_IN: 'Transferencia recibida',
  TRANSFERENCIA_OUT: 'Transferencia enviada',
  PAGO_TARJETA: 'Pago con tarjeta',
  PAGO_SERVICIO: 'Pago de servicio',
  COMISION: 'Comisión',
  INTERES: 'Intereses',
}

export const PRODUCT_LABELS: Record<string, string> = {
  AHORRO_SOLES: 'Cuenta de ahorros soles',
  AHORRO_DOLARES: 'Cuenta de ahorros dólares',
  CONSUMO: 'Préstamo de consumo',
}

export const CATEGORY_LABELS: Record<string, string> = {
  FRAUDE: 'Fraude',
  COBRO_INDEBIDO: 'Cobro indebido',
  TARJETA: 'Tarjeta',
  PRESTAMO: 'Préstamo',
  CANAL_DIGITAL: 'Canal digital',
  OTRO: 'Otro',
}
