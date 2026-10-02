/**
 * Single source of truth for "who sees what" in the Control Center (prompt section 10).
 * The sidebar, the route guard and the tests all read this table. The APIs enforce the
 * same rules on their side: hiding a module is UX, never the security boundary.
 */
import {
  Activity,
  BrainCircuit,
  ChartPie,
  FlaskConical,
  GitBranch,
  HandCoins,
  type LucideIcon,
  MessageSquareWarning,
  ShieldAlert,
  ShieldCheck,
  Users,
  Workflow,
} from 'lucide-react'

export type StaffRole =
  'Admin' | 'Operaciones' | 'Atencion' | 'Riesgos' | 'Fraude' | 'Direccion' | 'Marketing' | 'TI'

export const STAFF_ROLES: StaffRole[] = [
  'Admin',
  'Operaciones',
  'Atencion',
  'Riesgos',
  'Fraude',
  'Direccion',
  'Marketing',
  'TI',
]

export const ROLE_LABELS: Record<StaffRole, string> = {
  Admin: 'Administrador',
  Operaciones: 'Operaciones',
  Atencion: 'Atención al cliente',
  Riesgos: 'Riesgos',
  Fraude: 'Fraude',
  Direccion: 'Dirección',
  Marketing: 'Marketing',
  TI: 'TI',
}

export interface ConsoleModule {
  id: string
  path: string
  label: string
  description: string
  icon: LucideIcon
  roles: StaffRole[] | 'all'
}

export const MODULES: ConsoleModule[] = [
  {
    id: 'operaciones',
    path: '/operaciones',
    label: 'Centro de Operaciones',
    description: 'KPIs en vivo y salud de las APIs',
    icon: Activity,
    roles: 'all',
  },
  {
    id: 'clientes',
    path: '/clientes',
    label: 'Clientes y KYC',
    description: 'Clientes, onboarding y revelado de PII',
    icon: Users,
    roles: ['Atencion', 'Admin'],
  },
  {
    id: 'prestamos',
    path: '/prestamos',
    label: 'Préstamos',
    description: 'Solicitudes, score IA y cartera',
    icon: HandCoins,
    roles: ['Riesgos'],
  },
  {
    id: 'quejas',
    path: '/quejas',
    label: 'Centro de Quejas IA',
    description: 'Clasificación IA y cola de revisión',
    icon: MessageSquareWarning,
    roles: ['Atencion'],
  },
  {
    id: 'fraude',
    path: '/fraude',
    label: 'Chaski Guard',
    description: 'Alertas de fraude en vivo',
    icon: ShieldAlert,
    roles: ['Fraude'],
  },
  {
    id: 'insights',
    path: '/insights',
    label: 'Chaski Insights',
    description: 'Rentabilidad, morosidad y NL2SQL',
    icon: ChartPie,
    roles: ['Direccion', 'Riesgos', 'Marketing'],
  },
  {
    id: 'pipelines',
    path: '/pipelines',
    label: 'Data Pipelines',
    description: 'Corridas, calidad y cuarentena',
    icon: Workflow,
    roles: ['TI', 'Admin'],
  },
  {
    id: 'salud-ia',
    path: '/salud-ia',
    label: 'Salud de IA',
    description: 'Precisión, revisión manual y latencia',
    icon: BrainCircuit,
    roles: ['TI', 'Admin'],
  },
  {
    id: 'seguridad',
    path: '/seguridad',
    label: 'Seguridad y Auditoría',
    description: 'Auditoría, accesos denegados y secretos',
    icon: ShieldCheck,
    roles: ['Admin', 'TI'],
  },
  {
    id: 'devops',
    path: '/devops',
    label: 'DevOps',
    description: 'Despliegues y versiones',
    icon: GitBranch,
    roles: ['TI'],
  },
  {
    id: 'demo',
    path: '/demo',
    label: 'Modo Demo',
    description: 'Escenarios para la presentación',
    icon: FlaskConical,
    roles: ['Admin'],
  },
]

export function canAccess(module: ConsoleModule, role: string | null): boolean {
  if (!role || !STAFF_ROLES.includes(role as StaffRole)) return false
  return module.roles === 'all' || module.roles.includes(role as StaffRole)
}

export function modulesFor(role: string | null): ConsoleModule[] {
  return MODULES.filter((m) => canAccess(m, role))
}

export function moduleById(id: string): ConsoleModule {
  const found = MODULES.find((m) => m.id === id)
  if (!found) throw new Error(`Unknown module ${id}`)
  return found
}
