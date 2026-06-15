import { http } from './http'

export type AgentRunStatus =
  | 'queued'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'cancelled'
  | 'waiting_approval'

export interface AgentRunCreateRequest {
  thread_id?: string | null
  project_id?: string | null
  skill_id?: string | null
  task_type?: string
  input: string
}

export interface AgentRunCreated {
  run_id: string
  status: AgentRunStatus
  created_at: string
  detail_url: string
  events_url: string
  skill_id?: string | null
  skill_version?: string | null
  skill_selection_mode?: string | null
}

export interface AgentRun {
  run_id: string
  thread_id: string | null
  user_id: string
  project_id: string | null
  skill_id: string | null
  skill_version?: string | null
  skill_selection_mode?: string | null
  task_type: string
  status: AgentRunStatus
  current_node: string | null
  input: string
  final_output: string | null
  error_message: string | null
  total_tokens: number
  total_cost: string
  created_at: string
  updated_at: string
}

export async function createAgentRun(
  payload: AgentRunCreateRequest,
): Promise<AgentRunCreated> {
  const response = await http.post<AgentRunCreated>('/agent/runs', payload)
  return response.data
}

export async function getAgentRun(runId: string): Promise<AgentRun> {
  const response = await http.get<AgentRun>(`/agent/runs/${runId}`)
  return response.data
}
