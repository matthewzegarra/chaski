/** API response types (mirror the Pydantic schemas of the services). */

export interface Page<T> {
  items: T[]
  page: number
  page_size: number
  total: number
}

export interface Account {
  id: string
  number: string
  product: 'AHORRO_SOLES' | 'AHORRO_DOLARES'
  currency: 'PEN' | 'USD'
  balance: number
  status: string
  opened_at: string
}

export interface Movement {
  id: string
  account_id: string
  card_id: string | null
  type: string
  direction: 'CREDITO' | 'DEBITO'
  amount: number
  currency: string
  channel: string
  merchant: string | null
  city: string | null
  counterparty_account: string | null
  description: string | null
  created_at: string
}

export interface Receipt {
  transaction_id: string
  operation: 'TRANSFERENCIA' | 'PAGO_TARJETA'
  amount: number
  currency: string
  from_account_number?: string | null
  to_account_number?: string | null
  card_last4?: string | null
  merchant?: string | null
  internal?: boolean | null
  new_balance: number
  created_at: string
}

export interface CardInfo {
  id: string
  account_id: string | null
  type: 'DEBITO' | 'CREDITO'
  brand: string
  last4: string
  credit_limit: number | null
  status: 'ACTIVA' | 'BLOQUEADA'
}

export interface CustomerSelf {
  id: string
  first_name: string
  last_name: string
  document_number: string
  email: string
  phone: string | null
  segment: string
  region: string
  kyc_status: 'PENDIENTE' | 'APROBADO' | 'RECHAZADO'
}

export interface LoanQuote {
  amount: number
  term_months: number
  rate_tea: number
  monthly_payment: number
  total_payment: number
}

export interface Loan {
  id: string
  customer_id: string
  product: string
  amount: number
  term_months: number
  rate_tea: number
  status: 'SOLICITADO' | 'APROBADO' | 'RECHAZADO' | 'DESEMBOLSADO' | 'CANCELADO'
  days_past_due: number
  outstanding_balance: number
  monthly_payment: number
  ai_score: number | null
  ai_explanation: string | null
  decided_by: string | null
  decided_at: string | null
  disbursed_at: string | null
  created_at: string
}

export interface ComplaintCustomer {
  id: string
  subject: string
  body: string
  channel: string
  status: 'NUEVA' | 'EN_REVISION' | 'RESUELTA'
  category: string | null
  created_at: string
  due_at: string
}

export interface DniLookup {
  found: boolean
  available: boolean
  nombres: string | null
  apellidos: string | null
  fuente: string | null
}

export interface OnboardingResult {
  customer_id: string
  kyc_status: string
  extracted: Record<string, string> | null
  lookup: Record<string, string> | null
  confidence: number | null
  checks: Record<string, boolean | null>
  message: string
}

export interface DevPersona {
  sub?: string
  name: string
  roles: string[]
  customer_id?: string
  segment?: string
  kyc_status?: string
}

export interface DevUsers {
  staff: DevPersona[]
  customers: { customer_id: string; name: string; segment: string; kyc_status: string }[]
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface PendingAction {
  tool: 'block_card' | 'create_complaint'
  args: Record<string, string>
  summary: string
}

export interface ChatResponse {
  reply: string
  pending_action?: PendingAction | null
  data?: unknown
}
