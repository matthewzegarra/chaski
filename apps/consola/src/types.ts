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

export interface ComplaintConsole {
  id: string
  customer_id: string
  customer_name: string
  subject: string
  body: string
  channel: string
  status: 'NUEVA' | 'EN_REVISION' | 'RESUELTA'
  ai_category: string | null
  ai_urgency: 'ALTA' | 'MEDIA' | 'BAJA' | null
  ai_confidence: number | null
  ai_reason: string | null
  ai_suspicious: boolean
  requires_review: boolean
  final_category: string | null
  reviewed_by: string | null
  created_at: string
  due_at: string
  business_days_left: number
}

export interface Profitability {
  dimension: string
  since: string
  by_dimension: {
    dimension: string
    ingresos_intereses: number
    comisiones: number
    costo_fondeo: number
    provisiones: number
    margen: number
  }[]
  monthly: { mes: string; ingresos: number; margen: number }[]
}

export interface Delinquency {
  fecha: string
  by_bucket: { bucket: string; prestamos: number; saldo: number }[]
  by_region: { region: string; saldo: number; saldo_vencido_30: number; mora_pct: number }[]
  trend: { fecha: string; saldo: number; saldo_vencido_30: number; mora_pct: number }[]
}

export interface AskResult {
  respuesta: string
  columnas: string[]
  filas: Record<string, string | number | null>[]
  grafico: 'bar' | 'line' | 'table'
  sql: string
}

export interface ExecutiveSummary {
  resumen: string
  kpis: {
    periodo: string
    margen_mes: number
    variacion_margen_pct: number
    mora_pct: number
    [key: string]: unknown
  }
  valido: boolean
  numeros_no_validados: number[]
  requiere_revision: boolean
  publicado: boolean
}

export interface PipelineRun {
  id: string
  flow_name: string
  status: 'EN_CURSO' | 'EXITOSO' | 'CON_ALERTAS' | 'FALLIDO'
  trigger: string
  started_at: string
  finished_at: string | null
  rows_in: number
  rows_ok: number
  rows_quarantined: number
  error: string | null
}

export interface QualityCheck {
  check_name: string
  table_name: string
  passed: boolean
  failed_count: number
}

export interface QuarantineRecord {
  id: number
  run_id: string | null
  table_name: string
  reason: string
  payload: Record<string, unknown>
  created_at: string
}

export interface AiHealthMetrics {
  ventana_dias: number
  precision_ia_vs_humano_pct: number | null
  quejas_resueltas_evaluadas: number
  tasa_revision_manual_pct: number | null
  quejas_sospechosas: number
  correcciones_humanas: number
  bloqueos_prompt_shields_7d: number
  modo: 'mock' | 'azure'
  por_caso_de_uso: {
    use_case: string
    llamadas: number
    latencia_promedio_ms: number | null
    latencia_p95_ms: number | null
    bloqueos_shields: number
    version_prompt: string
    prompt_id: string
    proveedores: string
  }[]
}

export interface AuditEntry {
  id: number
  actor_id: string
  actor_role: string | null
  action: string
  resource: string
  resource_id: string | null
  pii_accessed: boolean
  allowed: boolean
  ip: string | null
  reason: string | null
  correlation_id: string | null
  created_at: string
}

export interface SecuritySummary {
  denegados_24h: number
  accesos_pii_24h: number
  eventos_24h: number
}

export interface SecretsMetadata {
  source: 'keyvault' | 'mock'
  secrets: {
    name: string
    enabled: boolean
    version: string | null
    created_on: string | null
    updated_on: string | null
    expires_on: string | null
    days_to_expiry: number | null
    status: 'OK' | 'POR_ROTAR' | 'VENCIDO' | 'SIN_EXPIRACION'
  }[]
}

export interface Deployments {
  source: 'github' | 'mock'
  versions: Record<string, { commit: string; deployed_at: string }>
  runs: {
    id: number
    workflow: string
    branch: string
    commit: string
    status: string
    environment: string
    started_at: string
    url: string | null
    actor: string | null
    tests?: { passed: number; failed: number }
    coverage?: number
  }[]
}
