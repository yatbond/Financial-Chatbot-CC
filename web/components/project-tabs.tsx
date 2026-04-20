'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

interface ProjectTabsProps {
  projectId: string
}

const tabs = [
  { label: 'Chat', path: 'chat' },
  { label: 'Reports', path: 'reports' },
  { label: 'Discrepancies', path: 'discrepancies' },
  { label: 'Admin', path: 'admin' },
]

export function ProjectTabs({ projectId }: ProjectTabsProps) {
  const pathname = usePathname()

  return (
    <div className="flex border-b border-zinc-200 bg-white px-4">
      {tabs.map((tab) => {
        const href = `/projects/${projectId}/${tab.path}`
        const isActive = pathname.startsWith(href)
        return (
          <Link
            key={tab.path}
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
