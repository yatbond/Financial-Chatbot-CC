'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { UserButton } from '@clerk/nextjs'

export function AppSidebar() {
  const pathname = usePathname()

  return (
    <aside className="flex w-52 shrink-0 flex-col border-r border-zinc-200 bg-white">
      <div className="border-b border-zinc-200 px-4 py-3">
        <span className="text-sm font-semibold tracking-tight text-zinc-900">FinLens</span>
      </div>

      <nav className="flex-1 px-2 py-3">
        <Link
          href="/projects"
          className={`flex items-center rounded-md px-2 py-1.5 text-sm transition-colors ${
            pathname === '/projects'
              ? 'bg-zinc-100 font-medium text-zinc-900'
              : 'text-zinc-600 hover:bg-zinc-50 hover:text-zinc-900'
          }`}
        >
          All Projects
        </Link>
      </nav>

      <div className="border-t border-zinc-200 px-4 py-3">
        <UserButton />
      </div>
    </aside>
  )
}
