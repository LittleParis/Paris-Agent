import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import {
  createAgentRun,
  getAgentRun,
  type AgentRun,
  type AgentRunCreated,
} from '../api/agent'
import {
  AgentEventSource,
  type MemoryEventItem,
  type RuntimeEventEnvelope,
  type SSEConnectionStatus,
} from '../api/agentEvents'
import { getErrorMessage } from '../utils/error'

export interface ChatMessageItem {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  pending?: boolean
}

export interface RuntimeEventItem {
  sequence: number
  event_type: string
  status: string
  timestamp: string
  payload: Record<string, unknown>
}

function createMessageId(): string {
  return crypto.randomUUID()
}

export const useAgentRunStore = defineStore('agent-run', () => {
  // ===== 核心状态 =====
  const messages = ref<ChatMessageItem[]>([])
  const currentRun = ref<AgentRun | null>(null)
  const createdRun = ref<AgentRunCreated | null>(null)
  const isSubmitting = ref(false)
  const errorMessage = ref<string | null>(null)

  // ===== P4 SSE 状态 =====
  const events = ref<RuntimeEventItem[]>([])
  const connectionStatus = ref<SSEConnectionStatus>('idle')
  const lastSequence = ref(0)
  const seenEventIds = ref<Set<string>>(new Set())

  // ===== P5 Skill 状态 =====
  const selectedSkillId = ref<string | null>(null)
  const skillInfo = ref<{
    skill_id: string | null
    skill_version: string | null
    skill_selection_mode: string | null
  }>({ skill_id: null, skill_version: null, skill_selection_mode: null })

  // ===== P6 Memory 状态 =====
  const retrievedMemories = ref<MemoryEventItem[]>([])
  const writtenMemories = ref<MemoryEventItem[]>([])

  // ===== 内部状态 =====
  const agentEventSource = new AgentEventSource()
  let requestToken = 0
  let pendingAssistantMessageId: string | null = null
  let accumulatedDelta = ''

  const isBusy = computed(() => isSubmitting.value || connectionStatus.value === 'connecting' || connectionStatus.value === 'open' || connectionStatus.value === 'reconnecting')

  // ===== 消息管理 =====

  function addMessage(
    role: ChatMessageItem['role'],
    content: string,
    pending = false,
  ): string {
    const id = createMessageId()
    messages.value.push({ id, role, content, pending })
    return id
  }

  function completeAssistantMessage(
    messageId: string,
    content: string,
  ): void {
    const message = messages.value.find((item) => item.id === messageId)
    if (!message) { return }
    message.content = content
    message.pending = false
  }

  // ===== SSE 事件处理 =====

  function handleEvent(envelope: RuntimeEventEnvelope): void {
    // 去重：已见过的 event_id 直接忽略
    if (seenEventIds.value.has(envelope.event_id)) { return }
    // 去重：sequence <= lastSequence 直接忽略
    if (envelope.sequence <= lastSequence.value) { return }

    // 接受事件：记录 event_id 并推进 lastSequence
    seenEventIds.value.add(envelope.event_id)
    lastSequence.value = envelope.sequence

    // 记录到事件时间线
    events.value.push({
      sequence: envelope.sequence,
      event_type: envelope.event_type,
      status: envelope.status,
      timestamp: envelope.timestamp,
      payload: envelope.payload as Record<string, unknown>,
    })

    // 按事件类型分发处理
    switch (envelope.event_type) {
      case 'skill.matched':
        if (envelope.payload) {
          skillInfo.value = {
            skill_id: envelope.payload.skill_id ?? null,
            skill_version: envelope.payload.skill_version ?? null,
            skill_selection_mode: envelope.payload.skill_selection_mode ?? null,
          }
        }
        break

      case 'memory.retrieval.completed':
        retrievedMemories.value = envelope.payload.memories ?? []
        break
      case 'memory.write.completed':
        writtenMemories.value = envelope.payload.memories ?? []
        break

      case 'run.started':
        if (currentRun.value) {
          currentRun.value = { ...currentRun.value, status: 'running' }
        }
        break

      case 'node.started':
        if (currentRun.value && envelope.payload.node_name) {
          currentRun.value = {
            ...currentRun.value,
            current_node: envelope.payload.node_name,
          }
        }
        break

      case 'message.delta':
        if (envelope.payload.delta && pendingAssistantMessageId) {
          accumulatedDelta += envelope.payload.delta
          const msg = messages.value.find(
            (item) => item.id === pendingAssistantMessageId,
          )
          if (msg) {
            msg.content = accumulatedDelta
          }
        }
        break

      case 'node.completed':
        // 保留事件，节点完成时清理 current_node 显示
        if (currentRun.value) {
          currentRun.value = { ...currentRun.value, current_node: null }
        }
        break

      case 'run.completed': {
        const finalContent =
          envelope.payload.output ||
          accumulatedDelta ||
          'Agent Run 已完成，但没有返回内容。'
        if (pendingAssistantMessageId) {
          completeAssistantMessage(pendingAssistantMessageId, finalContent)
        }
        if (currentRun.value) {
          currentRun.value = { ...currentRun.value, status: 'succeeded' }
        }
        // 终态快照 GET
        refreshRunSnapshot()
        break
      }

      case 'run.failed': {
        const failMessage =
          envelope.payload.error_message || 'Agent Run 执行失败。'
        errorMessage.value = failMessage
        if (pendingAssistantMessageId) {
          completeAssistantMessage(pendingAssistantMessageId, failMessage)
        }
        if (currentRun.value) {
          currentRun.value = { ...currentRun.value, status: 'failed' }
        }
        break
      }

      case 'run.cancelled': {
        const cancelMessage = envelope.payload.reason || 'Agent Run 已取消。'
        errorMessage.value = cancelMessage
        if (pendingAssistantMessageId) {
          completeAssistantMessage(pendingAssistantMessageId, cancelMessage)
        }
        if (currentRun.value) {
          currentRun.value = { ...currentRun.value, status: 'cancelled' }
        }
        break
      }
    }
  }

  /**
   * 收到终止事件后调用一次 GET 刷新最终 tokens/cost/时间。
   * 该请求失败不覆盖已经由 SSE 得到的终止状态和回复。
   */
  async function refreshRunSnapshot(): Promise<void> {
    const runId = createdRun.value?.run_id ?? currentRun.value?.run_id
    if (!runId) { return }
    try {
      const run = await getAgentRun(runId)
      currentRun.value = run
    } catch {
      // 终态快照 GET 失败只提示，不覆盖 SSE 已得到的终止状态
      errorMessage.value =
        (errorMessage.value ? errorMessage.value + ' ' : '') +
        '（最终状态详情刷新失败，但回复内容不受影响。）'
    }
  }

  // ===== SSE 连接管理 =====

  function connectSSE(eventsUrl: string): void {
    agentEventSource.onStatusChange = (status) => {
      connectionStatus.value = status
    }
    agentEventSource.onEvent = handleEvent
    agentEventSource.onError = (message) => {
      errorMessage.value = message
    }
    agentEventSource.connect(eventsUrl)
  }

  function closeSSE(): void {
    agentEventSource.close()
    connectionStatus.value = 'idle'
  }

  // ===== 提交消息 =====

  async function submitMessage(input: string): Promise<void> {
    const normalizedInput = input.trim()
    if (!normalizedInput || isBusy.value) { return }

    const token = ++requestToken

    // 先捕获当前选中的 skill，再清除 UI 状态
    const skillIdForRun = selectedSkillId.value ?? undefined
    selectedSkillId.value = null

    // 关闭旧连接、清理旧 Run 的事件状态
    closeSSE()
    events.value = []
    lastSequence.value = 0
    seenEventIds.value = new Set()
    accumulatedDelta = ''
    pendingAssistantMessageId = null
    skillInfo.value = { skill_id: null, skill_version: null, skill_selection_mode: null }
    retrievedMemories.value = []
    writtenMemories.value = []

    errorMessage.value = null
    currentRun.value = null
    createdRun.value = null
    isSubmitting.value = true

    addMessage('user', normalizedInput)
    const assistantId = addMessage(
      'assistant',
      'Paris Agent 正在创建运行任务…',
      true,
    )
    pendingAssistantMessageId = assistantId

    try {
      const created = await createAgentRun({
        input: normalizedInput,
        task_type: 'chat',
        skill_id: skillIdForRun,
      })
      if (token !== requestToken) { return }

      // 保存轻量创建响应
      createdRun.value = created
      // 初始化 currentRun 为轻量状态
      currentRun.value = {
        run_id: created.run_id,
        thread_id: null,
        user_id: '',
        project_id: null,
        skill_id: null,
        task_type: 'chat',
        status: created.status,
        current_node: null,
        input: normalizedInput,
        final_output: null,
        error_message: null,
        total_tokens: 0,
        total_cost: '0.00000000',
        created_at: created.created_at,
        updated_at: created.created_at,
      }

      // If response includes skill info, update skillInfo
      if (created.skill_id || created.skill_version) {
        skillInfo.value = {
          skill_id: created.skill_id ?? null,
          skill_version: created.skill_version ?? null,
          skill_selection_mode: created.skill_selection_mode ?? null,
        }
      }

      isSubmitting.value = false
      pendingAssistantMessageId = assistantId
      accumulatedDelta = ''

      // 连接 SSE events_url
      connectSSE(created.events_url)
    } catch (error) {
      if (token !== requestToken) { return }
      const message = getErrorMessage(error)
      errorMessage.value = message
      completeAssistantMessage(assistantId, message)
      isSubmitting.value = false
    }
  }

  // ===== 重置 =====

  function reset(): void {
    closeSSE()
    requestToken += 1
    messages.value = []
    currentRun.value = null
    createdRun.value = null
    isSubmitting.value = false
    errorMessage.value = null
    events.value = []
    lastSequence.value = 0
    seenEventIds.value = new Set()
    accumulatedDelta = ''
    pendingAssistantMessageId = null
    selectedSkillId.value = null
    skillInfo.value = { skill_id: null, skill_version: null, skill_selection_mode: null }
    retrievedMemories.value = []
    writtenMemories.value = []
  }

  return {
    // 核心状态
    messages,
    currentRun,
    createdRun,
    isSubmitting,
    isBusy,
    errorMessage,
    // P4 SSE 状态
    events,
    connectionStatus,
    lastSequence,
    // P5 Skill 状态
    selectedSkillId,
    skillInfo,
    // P6 Memory 状态
    retrievedMemories,
    writtenMemories,
    // 操作
    submitMessage,
    closeSSE,
    reset,
  }
})
