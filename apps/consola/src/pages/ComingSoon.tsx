import { EmptyState } from '@chaski/shared'
import { Construction } from 'lucide-react'

import { PageHeader } from '../components/Layout'
import type { ConsoleModule } from '../modules'

export function ComingSoonPage({ module }: { module: ConsoleModule }) {
  return (
    <div>
      <PageHeader title={module.label} description={module.description} />
      <EmptyState
        icon={<Construction className="size-6" />}
        title="Módulo en construcción"
        description="Este módulo se habilita en la siguiente fase del proyecto."
      />
    </div>
  )
}
