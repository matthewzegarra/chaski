/** Data hooks for the customer app. customer_id always comes from the token on the server. */
import {
  type Account,
  type CardInfo,
  type ComplaintCustomer,
  type CustomerSelf,
  type Loan,
  type LoanQuote,
  type Movement,
  type Page,
  type Receipt,
  useApi,
} from '@chaski/shared'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

export function useProfile() {
  const api = useApi()
  return useQuery({
    queryKey: ['me'],
    queryFn: () => api.get<CustomerSelf>('core', '/customers/me'),
  })
}

export function useAccounts(enabled = true) {
  const api = useApi()
  return useQuery({
    queryKey: ['accounts'],
    queryFn: () => api.get<Account[]>('cuentas', '/accounts/me'),
    enabled,
  })
}

export function useCards() {
  const api = useApi()
  return useQuery({ queryKey: ['cards'], queryFn: () => api.get<CardInfo[]>('core', '/cards/me') })
}

export interface MovementFilters {
  type?: string
  from?: string
  to?: string
  page?: number
  pageSize?: number
}

export function useMovements(accountId: string | undefined, f: MovementFilters = {}) {
  const api = useApi()
  return useQuery({
    queryKey: ['movements', accountId, f],
    queryFn: () =>
      api.get<Page<Movement>>('cuentas', `/accounts/${accountId}/movements`, {
        type: f.type,
        from: f.from,
        to: f.to,
        page: f.page ?? 1,
        page_size: f.pageSize ?? 20,
      }),
    enabled: Boolean(accountId),
    placeholderData: keepPreviousData,
  })
}

function useInvalidateMoney() {
  const qc = useQueryClient()
  return () => {
    void qc.invalidateQueries({ queryKey: ['accounts'] })
    void qc.invalidateQueries({ queryKey: ['movements'] })
  }
}

export interface TransferInput {
  from_account_id: string
  to_account_number: string
  amount: string
  description?: string
  idempotencyKey: string
}

export function useTransfer() {
  const api = useApi()
  const invalidate = useInvalidateMoney()
  return useMutation({
    mutationFn: ({ idempotencyKey, ...body }: TransferInput) =>
      api.post<Receipt>('cuentas', '/transfers', body, { 'Idempotency-Key': idempotencyKey }),
    onSuccess: invalidate,
  })
}

export interface CardPaymentInput {
  card_id: string
  amount: string
  merchant: string
  city?: string
  channel: 'POS' | 'WEB'
  idempotencyKey: string
}

export function useCardPayment() {
  const api = useApi()
  const invalidate = useInvalidateMoney()
  return useMutation({
    mutationFn: ({ idempotencyKey, ...body }: CardPaymentInput) =>
      api.post<Receipt>('cuentas', '/card-payments', body, { 'Idempotency-Key': idempotencyKey }),
    onSuccess: invalidate,
  })
}

export function useCardStatus() {
  const api = useApi()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, block }: { id: string; block: boolean }) =>
      api.post<CardInfo>('core', `/cards/${id}/${block ? 'block' : 'unblock'}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['cards'] }),
  })
}

export function useLoanQuote(amount: number, term: number) {
  const api = useApi()
  return useQuery({
    queryKey: ['quote', amount, term],
    queryFn: () => api.get<LoanQuote>('core', '/loans/quote', { amount, term_months: term }),
    enabled: amount >= 500 && amount <= 100_000,
    placeholderData: keepPreviousData,
  })
}

export function useLoans() {
  const api = useApi()
  return useQuery({ queryKey: ['loans'], queryFn: () => api.get<Loan[]>('core', '/loans/me') })
}

export function useRequestLoan() {
  const api = useApi()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { amount: number; term_months: number }) =>
      api.post<Loan>('core', '/loans', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['loans'] }),
  })
}

export function useComplaints() {
  const api = useApi()
  return useQuery({
    queryKey: ['complaints'],
    queryFn: () => api.get<ComplaintCustomer[]>('core', '/complaints/me'),
  })
}

export function useCreateComplaint() {
  const api = useApi()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { subject: string; body: string; channel?: string }) =>
      api.post<ComplaintCustomer>('core', '/complaints', { channel: 'APP', ...body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['complaints'] }),
  })
}
