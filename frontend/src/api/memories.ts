import { http } from './http'

export type MemoryType =
  | 'short_term'
  | 'learning_profile'
  | 'semantic'
  | 'episodic'
  | 'project'
  | 'procedural'
  | 'task'
  | 'runtime'

export type MemoryScope = 'user' | 'project'

export interface Memory {
  memory_id: string
  project_id: string | null
  memory_type: MemoryType
  scope: MemoryScope
  content: string
  summary: string | null
  importance: string
  confidence: string
  source_type: 'manual' | 'agent_run' | 'consolidation'
  source_id: string | null
  source_detail: Record<string, unknown>
  tags: string[]
  version: number
  access_count: number
  last_accessed_at: string | null
  expires_at: string | null
  sync_status: string
  created_at: string
  updated_at: string
}

export interface MemoryWrite {
  memory_type: MemoryType
  scope: MemoryScope
  project_id: string | null
  content: string
  summary: string | null
  importance: string
  confidence: string
  tags: string[]
}

export interface MemoryListResponse {
  items: Memory[]
  next_cursor: string | null
}

export async function listMemories(): Promise<MemoryListResponse> {
  const response = await http.get<MemoryListResponse>('/v1/memories')
  return response.data
}

export async function createMemory(payload: MemoryWrite): Promise<Memory> {
  const response = await http.post<Memory>('/v1/memories', payload)
  return response.data
}

export async function updateMemory(
  memoryId: string,
  payload: Partial<MemoryWrite> & { version: number },
): Promise<Memory> {
  const response = await http.patch<Memory>(
    `/v1/memories/${memoryId}`,
    payload,
  )
  return response.data
}

export async function deleteMemory(
  memoryId: string,
  version: number,
): Promise<void> {
  await http.delete(`/v1/memories/${memoryId}`, {
    params: { version },
  })
}
