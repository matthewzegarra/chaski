import { Skeleton, useTheme } from '@chaski/shared'
import { type ComponentType, lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router'

import { AppLayout, RequireCustomer } from './components/Layout'
import { HomePage } from './pages/Home'
import { WelcomePage } from './pages/Welcome'

// Secondary screens are split into their own chunks to keep the first load small.
const page = <K extends string>(load: () => Promise<Record<K, ComponentType>>, name: K) =>
  lazy(() => load().then((m) => ({ default: m[name] })))
const OnboardingPage = page(() => import('./pages/Onboarding'), 'OnboardingPage')
const MovementsPage = page(() => import('./pages/Movements'), 'MovementsPage')
const TransferPage = page(() => import('./pages/Transfer'), 'TransferPage')
const PayPage = page(() => import('./pages/Pay'), 'PayPage')
const CardsPage = page(() => import('./pages/Cards'), 'CardsPage')
const LoansPage = page(() => import('./pages/Loans'), 'LoansPage')
const ComplaintsPage = page(() => import('./pages/Complaints'), 'ComplaintsPage')
const MorePage = page(() => import('./pages/More'), 'MorePage')

export function App() {
  useTheme() // applies the saved light/dark preference
  return (
    <Suspense fallback={<Skeleton className="m-4 h-64" />}>
      <Routes>
        <Route path="/bienvenida" element={<WelcomePage />} />
        <Route path="/registro" element={<OnboardingPage />} />
        <Route
          element={
            <RequireCustomer>
              <AppLayout />
            </RequireCustomer>
          }
        >
          <Route index element={<HomePage />} />
          <Route path="movimientos" element={<MovementsPage />} />
          <Route path="transferir" element={<TransferPage />} />
          <Route path="pagar" element={<PayPage />} />
          <Route path="tarjetas" element={<CardsPage />} />
          <Route path="prestamos" element={<LoansPage />} />
          <Route path="reclamos" element={<ComplaintsPage />} />
          <Route path="mas" element={<MorePage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  )
}
