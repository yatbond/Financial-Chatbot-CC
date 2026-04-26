import { MOCK_PROJECTS } from '@/lib/mock-data'
import { ChatShell } from '@/components/chat/chat-shell'

interface ChatPageProps {
  params: Promise<{ projectId: string }>
}

export default async function ChatPage({ params }: ChatPageProps) {
  const { projectId } = await params
  const project = MOCK_PROJECTS.find((p) => p.id === projectId)

  return (
    <ChatShell
      projectId={projectId}
      projectCode={project?.project_code}
      projectName={project?.project_name}
      period="Feb 2026"
    />
  )
}
