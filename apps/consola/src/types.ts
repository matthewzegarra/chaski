/** Response types of the console endpoints (mirror core-api schemas). */

export interface Kpis {
  transacciones_hoy: number
  monto_transado_hoy: number
  clientes_nuevos_hoy: number
  cartera_total: number
  mora_pct: number
  alertas_abiertas: number
  quejas_abiertas: number
  quejas_por_vencer: number
  prestamos_por_revisar: number
  onboarding_pendiente: number
  generado_en: string
}

export interface HourPoint {
  hora: number
  cantidad: number
  monto: number
}

export interface CustomerMasked {
  id: string
  first_name: string
  last_name: string
  document_type: string
  document_number: string
  email: string
  phone: string | null
  segment: string
  region: string
  kyc_status: 'PENDIENTE' | 'APROBADO' | 'RECHAZADO'
  risk_level: string
  created_at: string
}

export interface CustomerDetail extends CustomerMasked {
  monthly_income: number | null
  accounts: {
    id: string
    number: string
    product: string
    currency: string
    balance: number
    status: string
  }[]
  cards: { id: string; type: string; brand: string; last4: string; status: string }[]
  loans: {
    id: string
    amount: number
    status: string
    days_past_due: number
    outstanding_balance: number
  }[]
  open_complaints: number
}

export interface RevealedPii {
  id: string
  document_number: string
  email: string
  phone: string | null
  birth_date: string | null
}

export interface PendingOnboarding {
  customer: CustomerMasked
  document_id: string | null
  extracted: Record<string, string> | null
  confidence: number | null
  checks: Record<string, boolean | null>
}

export interface LoanConsole {
  id: string
  customer_id: string
  customer_name: string
  segment: string
  region: string
  monthly_income: number | null
  amount: number
  term_months: number
  rate_tea: number
  status: string
  days_past_due: number
  outstanding_balance: number
  monthly_payment: number
  bucket: string
  ai_score: number | null
  ai_explanation: string | null
  decided_by: string | null
  created_at: string
}

export interface FraudAlert {
  id: string
  rule: string
  score: number
  source: 'RULES' | 'FABRIC'
  status: 'ABIERTA' | 'CONFIRMADA' | 'DESCARTADA'
  details: Record<string, unknown> | null
  created_at: string
  resolved_by: string | null
  resolved_at: string | null
  customer_id: string | null
  customer_name: string | null
  transaction_id: string | null
  tx_type: string | null
  tx_amount: number | null
  tx_currency: string | null
  tx_channel: string | null
  merchant: string | null
  city: string | null
  card_id: string | null
  card_last4: string | null
  card_status: string | null
}
