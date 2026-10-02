import {
  formatCompactMoney,
  formatDate,
  formatMoney,
  formatRelative,
  monthlyPayment,
} from './format'

describe('formatMoney', () => {
  it('formats soles with thousands separator and 2 decimals', () => {
    expect(formatMoney(1234.56)).toBe('S/ 1,234.56')
    expect(formatMoney('1500')).toBe('S/ 1,500.00')
    expect(formatMoney(0)).toBe('S/ 0.00')
  })
  it('formats dollars and negatives', () => {
    expect(formatMoney(99.9, 'USD')).toBe('US$ 99.90')
    expect(formatMoney(-12, 'PEN')).toBe('-S/ 12.00')
  })
  it('handles null', () => {
    expect(formatMoney(null)).toBe('S/ 0.00')
  })
})

describe('formatCompactMoney', () => {
  it('uses K and M', () => {
    expect(formatCompactMoney(3_917_014)).toBe('S/ 3.9 M')
    expect(formatCompactMoney(128_316)).toBe('S/ 128 K')
    expect(formatCompactMoney(999)).toBe('S/ 999.00')
  })
})

describe('dates', () => {
  it('shows dates in Lima time', () => {
    // 2026-10-02 03:00 UTC is still Oct 1 in Lima (UTC-5).
    expect(formatDate('2026-10-02T03:00:00Z')).toMatch(/^01 oct/)
  })
  it('relative times', () => {
    const now = new Date('2026-10-01T12:00:00Z')
    expect(formatRelative('2026-10-01T11:55:00Z', now)).toBe('hace 5 min')
    expect(formatRelative('2026-10-01T09:00:00Z', now)).toBe('hace 3 h')
  })
  it('returns a dash for empty values', () => {
    expect(formatDate(null)).toBe('—')
  })
})

describe('monthlyPayment', () => {
  it('matches the backend French amortisation', () => {
    // core-api test: 10,000 at 18% TEA over 12 months is between 910 and 920.
    const p = monthlyPayment(10_000, 0.18, 12)
    expect(p).toBeGreaterThan(910)
    expect(p).toBeLessThan(920)
  })
})
