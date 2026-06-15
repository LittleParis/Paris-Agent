import { http } from './http'

export interface SkillListItem {
  skill_id: string
  name: string
  description: string
  enabled: boolean
  version: string
  is_default: boolean
}

export interface SkillDetail {
  skill_id: string
  name: string
  description: string
  enabled: boolean
  version: string
  is_default: boolean
  input_schema: Record<string, unknown>
  output_schema: Record<string, unknown>
  tools: unknown[]
  workflow: Record<string, unknown>
  memory_policy: Record<string, unknown>
  safety_policy: Record<string, unknown>
  runtime_config: Record<string, unknown>
}

export async function listSkills(includeDisabled = false): Promise<SkillListItem[]> {
  const response = await http.get<SkillListItem[]>('/skills', {
    params: { include_disabled: includeDisabled },
  })
  return response.data
}

export async function getSkill(skillId: string): Promise<SkillDetail> {
  const response = await http.get<SkillDetail>(`/skills/${skillId}`)
  return response.data
}
