import { MOCK_PROJECTS } from '@/lib/mock-data'
import { ContextBar } from '@/components/context-bar'
import { ProjectTabs } from '@/components/project-tabs'

interface ProjectLayoutProps {
  children: React.ReactNode
  params: Promise<{ projectId: string }>
}

export default async function ProjectLayout({ children, params }: ProjectLayoutProps) {
  const { projectId } = await params
  const project = MOCK_PROJECTS.find((p) => p.id === projectId)

  return (
    <>
      <ContextBar
        projectCode={project?.project_code}
        projectName={project?.project_name}
        period="Feb 2026"
      />
      <ProjectTabs projectId={projectId} />
      <main className="flex-1 overflow-y-auto">{children}</main>
    </>
  )
}
