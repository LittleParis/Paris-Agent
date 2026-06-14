import axios from 'axios'
import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import {
  createAgentRun,
  getAgentRun,
  type AgentRun,
  type AgentRunCreated,
} from '../api/agent'

export interface ChatMessageItem {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  pending?: boolean
}

const POLL_INTERVAL_MS = 500
const POLL_TIMEOUT_MS = 60_000
const ACTIVE_STATUSES = new Set(['queued', 'running', 'waiting_approval'])

function createMessageId(): string {
  return crypto.randomUUID()
}

function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') {
      return detail
    }

    if (error.code === 'ECONNABORTED') {
      return '请求超时，请确认后端服务是否正常运行。'
    }

    if (!error.response) {
      return '无法连接 Paris Agent 后端，请确认 8000 端口已启动。'
    }
  }

  return '请求处理失败，请稍后重试。'
}

export const useAgentRunStore = defineStore('agent-run', () => {
  const messages = ref<ChatMessageItem[]>([])
  const currentRun = ref<AgentRun | null>(null)
  const createdRun = ref<AgentRunCreated | null>(null)
  const isSubmitting = ref(false)
  const isPolling = ref(false)
  const errorMessage = ref<string | null>(null)

  let pollTimer: ReturnType<typeof setTimeout> | null = null
  let pollStartedAt = 0
  let requestToken = 0

  const isBusy = computed(() => isSubmitting.value || isPolling.value)

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
    if (!message) {
      return
    }

    message.content = content
    message.pending = false
  }

  function stopPolling(): void {
    if (pollTimer) {
      clearTimeout(pollTimer)
      pollTimer = null
    }

    isPolling.value = false
    // 让仍在途中的旧请求失效，避免它完成后覆盖新 Run 的界面状态。
    requestToken += 1
  }

  function finishWithRun(
    run: AgentRun,
    assistantMessageId: string,
  ): boolean {
    if (run.status === 'succeeded') {
      completeAssistantMessage(
        assistantMessageId,
        run.final_output || 'Agent Run 已完成，但没有返回内容。',
      )
      isPolling.value = false
      return true
    }

    if (run.status === 'failed') {
      const message = run.error_message || 'Agent Run 执行失败。'
      errorMessage.value = message
      completeAssistantMessage(assistantMessageId, message)
      isPolling.value = false
      return true
    }

    if (run.status === 'cancelled') {
      const message = 'Agent Run 已取消。'
      errorMessage.value = message
      completeAssistantMessage(assistantMessageId, message)
      isPolling.value = false
      return true
    }

    return false
  }

  async function pollRun(
    runId: string,
    assistantMessageId: string,
    token: number,
  ): Promise<void> {
    if (token !== requestToken) {
      return
    }

    if (Date.now() - pollStartedAt >= POLL_TIMEOUT_MS) {
      const message = '运行状态查询超时，请稍后查看。'
      errorMessage.value = message
      completeAssistantMessage(assistantMessageId, message)
      isPolling.value = false
      return
    }

    try {
      const run = await getAgentRun(runId)
      if (token !== requestToken) {
        return
      }

      currentRun.value = run
      if (finishWithRun(run, assistantMessageId)) {
        return
      }

      if (!ACTIVE_STATUSES.has(run.status)) {
        const message = `Agent Run 进入未知状态：${run.status}`
        errorMessage.value = message
        completeAssistantMessage(assistantMessageId, message)
        isPolling.value = false
        return
      }

      // 递归 setTimeout 可确保当前 GET 完成后再安排下一次请求，避免请求重叠。
      pollTimer = setTimeout(() => {
        void pollRun(runId, assistantMessageId, token)
      }, POLL_INTERVAL_MS)
    } catch (error) {
      if (token !== requestToken) {
        return
      }

      const message = `状态查询失败：${getErrorMessage(error)}`
      errorMessage.value = message
      completeAssistantMessage(assistantMessageId, message)
      isPolling.value = false
    }
  }

  async function submitMessage(input: string): Promise<void> {
    const normalizedInput = input.trim()
    if (!normalizedInput || isBusy.value) {
      return
    }

    stopPolling()
    const token = requestToken
    errorMessage.value = null
    currentRun.value = null
    createdRun.value = null
    isSubmitting.value = true

    addMessage('user', normalizedInput)
    const assistantMessageId = addMessage(
      'assistant',
      'Paris Agent 正在创建运行任务…',
      true,
    )

    try {
      const created = await createAgentRun({
        input: normalizedInput,
        task_type: 'chat',
      })
      if (token !== requestToken) {
        return
      }

      createdRun.value = created
      isSubmitting.value = false
      isPolling.value = true
      pollStartedAt = Date.now()
      await pollRun(created.run_id, assistantMessageId, token)
    } catch (error) {
      if (token !== requestToken) {
        return
      }

      const message = getErrorMessage(error)
      errorMessage.value = message
      completeAssistantMessage(assistantMessageId, message)
      isSubmitting.value = false
      isPolling.value = false
    }
  }

  function reset(): void {
    stopPolling()
    messages.value = []
    currentRun.value = null
    createdRun.value = null
    isSubmitting.value = false
    errorMessage.value = null
  }

  return {
    messages,
    currentRun,
    createdRun,
    isSubmitting,
    isPolling,
    isBusy,
    errorMessage,
    submitMessage,
    stopPolling,
    reset,
  }
})
