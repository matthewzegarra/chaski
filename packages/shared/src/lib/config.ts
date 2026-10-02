/**
 * Runtime configuration. In containers nginx writes /env.js from CHASKI_* variables at start,
 * so the same image runs locally and in Azure (D7). Vite dev serves public/env.js.
 */

export interface ChaskiConfig {
  authMode: 'dev' | 'entra'
  env: 'DEV' | 'TEST' | 'PROD'
  cuentasApiUrl: string
  coreApiUrl: string
  iaApiUrl: string
  entraClientId: string
  entraTenantId: string
  entraApiScope: string
  powerbiEmbedUrl: string
}

declare global {
  interface Window {
    __CHASKI_CONFIG__?: Partial<ChaskiConfig>
  }
}

const DEFAULTS: ChaskiConfig = {
  authMode: 'dev',
  env: 'DEV',
  cuentasApiUrl: 'http://localhost:8001',
  coreApiUrl: 'http://localhost:8002',
  iaApiUrl: 'http://localhost:8003',
  entraClientId: '',
  entraTenantId: '',
  entraApiScope: '',
  powerbiEmbedUrl: '',
}

export function loadConfig(): ChaskiConfig {
  const raw = (typeof window !== 'undefined' && window.__CHASKI_CONFIG__) || {}
  const merged = { ...DEFAULTS }
  for (const [key, value] of Object.entries(raw)) {
    if (typeof value === 'string' && value !== '') {
      ;(merged as Record<string, string>)[key] = value.replace(/\/+$/, '')
    }
  }
  if (merged.authMode !== 'entra') merged.authMode = 'dev'
  return merged
}

export const config: ChaskiConfig = loadConfig()
