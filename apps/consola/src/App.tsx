import { Skeleton, useTheme } from '@chaski/shared'
import { type ComponentType, lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router'

import { ConsoleLayout, RequireStaff } from './components/Layout'
import { RoleRoute } from './components/RoleRoute'
import { MODULES } from './modules'
import { ComingSoonPage } from './pages/ComingSoon'
import { LoginPage } from './pages/Login'

const page = <K extends string>(load: () => Promise<Record<K, ComponentType>>, name: K) =>
  lazy(() => load().then((m) => ({ default: m[name] })))

// One page per module in modules.ts (a missing entry renders "En construcción").
const PAGES: Record<string, ComponentType> = {
  operaciones: page(() => import('./pages/Operations'), 'OperationsPage'),
  clientes: page(() => import('./pages/Customers'), 'CustomersPage'),
  prestamos: page(() => import('./pages/Loans'), 'LoansPage'),
  fraude: page(() => import('./pages/Fraud'), 'FraudPage'),
  quejas: page(() => import('./pages/Complaints'), 'ComplaintsPage'),
  insights: page(() => import('./pages/Insights'), 'InsightsPage'),
  pipelines: page(() => import('./pages/Pipelines'), 'PipelinesPage'),
  'salud-ia': page(() => import('./pages/AiHealth'), 'AiHealthPage'),
  seguridad: page(() => import('./pages/Security'), 'SecurityPage'),
  devops: page(() => import('./pages/DevOps'), 'DevOpsPage'),
  demo: page(() => import('./pages/Demo'), 'DemoPage'),
}

export function App() {
  useTheme()
  return (
    <Suspense fallback={<Skeleton className="m-6 h-64" />}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          element={
            <RequireStaff>
              <ConsoleLayout />
            </RequireStaff>
          }
        >
          <Route index element={<Navigate to="/operaciones" replace />} />
          {MODULES.map((m) => {
            const Page = PAGES[m.id]
            return (
              <Route
                key={m.id}
                path={m.path.slice(1)}
                element={
                  <RoleRoute moduleId={m.id}>
                    {Page ? <Page /> : <ComingSoonPage module={m} />}
                  </RoleRoute>
                }
              />
            )
          })}
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  )
}
