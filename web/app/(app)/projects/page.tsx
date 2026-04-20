import Link from 'next/link'
import { MOCK_PROJECTS } from '@/lib/mock-data'
import { ContextBar } from '@/components/context-bar'

export default function ProjectsPage() {
  return (
    <>
      <ContextBar />
      <main className="flex-1 overflow-y-auto p-6">
        <h1 className="mb-6 text-lg font-semibold text-zinc-900">Projects</h1>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {MOCK_PROJECTS.map((project) => (
            <Link
              key={project.id}
              href={`/projects/${project.id}/chat`}
              className="group rounded-lg border border-zinc-200 bg-white p-4 transition-colors hover:border-zinc-300 hover:shadow-sm"
            >
              <div className="mb-1 text-xs font-medium text-zinc-400">
                {project.project_code}
              </div>
              <div className="text-sm font-medium text-zinc-900 group-hover:text-zinc-700">
                {project.project_name}
              </div>
            </Link>
          ))}
        </div>
        <p className="mt-6 text-xs text-zinc-400">
          Showing mock data — connect Supabase in Phase 3 to load real projects.
        </p>
      </main>
    </>
  )
}
