'use client'

import Link from 'next/link'

export type AdminTab = 'mappings' | 'query-logs' | 'discrepancies'

const TABS: { label: string; value: AdminTab }[] = [
  { label: 'Mappings', value: 'mappings' },
  { label: 'Query Logs', value: 'query-logs' },
  { label: 'Discrepancies', value: 'discrepancies' },
]

interface AdminTabsProps {
  projectId: string
  activeTab: AdminTab
}

export function AdminTabs({ projectId, activeTab }: AdminTabsProps) {
  return (
    <div className="flex border-b border-zinc-200 bg-white px-4">
      {TABS.map((tab) => {
        const href = `/projects/${projectId}/admin?tab=${tab.value}`
        const isActive = activeTab === tab.value
        return (
          <Link
            key={tab.value}
            href={href}
            className={`border-b-2 px-4 py-2.5 text-sm font-medium transition-colors ${
              isActive
                ? 'border-zinc-900 text-zinc-900'
                : 'border-transparent text-zinc-500 hover:text-zinc-700'
            }`}
          >
            {tab.label}
          </Link>
        )
      })}
    </div>
  )
}
