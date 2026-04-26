import Link from 'next/link'
import { ContextBar } from '@/components/context-bar'
import { createServerSupabase } from '@/lib/supabase/server'

export const dynamic = 'force-dynamic'

export default async function ProjectsPage() {
  const supabase = createServerSupabase()
  const { data: projects, error } = await supabase
    .from('projects')
    .select('id, project_code, project_name')
    .order('project_code', { ascending: true })

  return (
    <>
      <ContextBar />
      <main className="flex-1 overflow-y-auto p-6">
        <h1 className="mb-6 text-lg font-semibold text-zinc-900">Projects</h1>

        {error && (
          <p className="mb-4 text-sm text-red-500">
            Failed to load projects: {error.message}
          </p>
        )}

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {(projects ?? []).map((project) => (
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

          {!error && (projects ?? []).length === 0 && (
            <p className="col-span-3 text-sm text-zinc-400">
              No projects found. Import an Excel report to get started.
            </p>
          )}
        </div>
      </main>
    </>
  )
}
