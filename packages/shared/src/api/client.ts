import { config } from '../lib/config'
import { newId } from '../lib/utils'

export type Service = 'cuentas' | 'core' | 'ia'
export type TokenGetter = () => Promise<string | null>

export class ApiError extends Error {
  readonly status: number
  readonly detail: string
  readonly correlationId: string | null

  constructor(status: number, detail: string, correlationId: string | null) {
    super(detail)
    this.status = status
    this.detail = detail
    this.correlationId = correlationId
  }
}

const BASE: Record<Service, () => string> = {
  cuentas: () => config.cuentasApiUrl,
  core: () => config.coreApiUrl,
  ia: () => config.iaApiUrl,
}

export function serviceUrl(service: Service): string {
  return BASE[service]()
}

function detailFrom(body: unknown, status: number): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { msg?: string; loc?: unknown[] }
      const field = Array.isArray(first.loc) ? String(first.loc[first.loc.length - 1]) : ''
      return `Dato inválido${field ? ` en «${field}»` : ''}: ${first.msg ?? 'revisa el formulario'}`
    }
  }
  if (status === 401) return 'Tu sesión expiró. Vuelve a ingresar.'
  if (status === 403) return 'No tienes permiso para realizar esta acción'
  if (status === 429) return 'Demasiadas solicitudes, intenta en un minuto'
  if (status >= 500) return 'Ocurrió un error en el servidor. Intenta nuevamente.'
  return `Error ${status}`
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: unknown
  form?: FormData
  headers?: Record<string, string>
  query?: Record<string, string | number | boolean | null | undefined>
  auth?: boolean
  signal?: AbortSignal
}

export interface ApiClient {
  request<T>(service: Service, path: string, options?: RequestOptions): Promise<T>
  get<T>(service: Service, path: string, query?: RequestOptions['query']): Promise<T>
  post<T>(
    service: Service,
    path: string,
    body?: unknown,
    headers?: Record<string, string>,
  ): Promise<T>
}

export function createApiClient(getToken: TokenGetter): ApiClient {
  async function request<T>(
    service: Service,
    path: string,
    options: RequestOptions = {},
  ): Promise<T> {
    const url = new URL(`${serviceUrl(service)}/api/v1${path}`)
    for (const [k, v] of Object.entries(options.query ?? {})) {
      if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, String(v))
    }
    const headers: Record<string, string> = { 'X-Correlation-ID': newId(), ...options.headers }
    if (options.auth !== false) {
      const token = await getToken()
      if (token) headers.Authorization = `Bearer ${token}`
    }
    let body: BodyInit | undefined
    if (options.form) {
      body = options.form
    } else if (options.body !== undefined) {
      headers['Content-Type'] = 'application/json'
      body = JSON.stringify(options.body)
    }
    let resp: Response
    try {
      resp = await fetch(url, {
        method: options.method ?? 'GET',
        headers,
        body,
        signal: options.signal,
      })
    } catch {
      throw new ApiError(0, 'No pudimos conectarnos. Revisa tu conexión.', null)
    }
    const text = await resp.text()
    const parsed: unknown = text ? safeJson(text) : null
    if (!resp.ok) {
      throw new ApiError(
        resp.status,
        detailFrom(parsed, resp.status),
        resp.headers.get('X-Correlation-ID'),
      )
    }
    return parsed as T
  }

  return {
    request,
    get: (service, path, query) => request(service, path, { query }),
    post: (service, path, body, headers) =>
      request(service, path, { method: 'POST', body, headers }),
  }
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text)
  } catch {
    return { detail: text }
  }
}
