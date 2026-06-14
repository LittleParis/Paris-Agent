<script setup lang="ts">
import { computed } from 'vue'

import type { AgentRun, AgentRunCreated } from '../../api/agent'
import type { SSEConnectionStatus } from '../../api/agentEvents'
import type { RuntimeEventItem } from '../../stores/agentRun'

const props = defineProps<{
  run: AgentRun | null
  createdRun: AgentRunCreated | null
  events: RuntimeEventItem[]
  connectionStatus: SSEConnectionStatus
  errorMessage: string | null
}>()

const runId = computed(
  () => props.run?.run_id ?? props.createdRun?.run_id ?? null,
)
const status = computed(
  () => props.run?.status ?? props.createdRun?.status ?? null,
)
const createdAt = computed(
  () => props.run?.created_at ?? props.createdRun?.created_at ?? null,
)

function formatDate(value: string | null): string {
  if (!value) { return '—' }
  return new Intl.DateTimeFormat('zh-CN', {
    dateStyle: 'medium',
    timeStyle: 'medium',
  }).format(new Date(value))
}

function formatEventTime(timestamp: string): string {
  return new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(new Date(timestamp))
}

const connectionStatusLabel = computed(() => {
  switch (props.connectionStatus) {
    case 'idle': return '未连接'
    case 'connecting': return '连接中'
    case 'open': return '已连接'
    case 'reconnecting': return '重连中'
    case 'closed': return '已关闭'
    default: return props.connectionStatus
  }
})

const connectionStatusClass = computed(() => {
  return `connection-status--${props.connectionStatus}`
})
</script>

<template>
  <aside class="run-panel">
    <div class="run-panel-heading">
      <div>
        <span class="eyebrow">Agent Runtime</span>
        <h2>Run 状态</h2>
      </div>
      <span
        v-if="status"
        class="run-status"
        :class="`run-status--${status}`"
      >
        {{ status }}
      </span>
    </div>

    <div v-if="runId" class="run-details">
      <dl>
        <div>
          <dt>Run ID</dt>
          <dd class="run-id">{{ runId }}</dd>
        </div>
        <div>
          <dt>Current Node</dt>
          <dd>{{ run?.current_node ?? '—' }}</dd>
        </div>
        <div>
          <dt>Connection</dt>
          <dd>
            <span class="connection-status" :class="connectionStatusClass">
              {{ connectionStatusLabel }}
            </span>
          </dd>
        </div>
        <div>
          <dt>Created</dt>
          <dd>{{ formatDate(createdAt) }}</dd>
        </div>
        <div>
          <dt>Updated</dt>
          <dd>{{ formatDate(run?.updated_at ?? null) }}</dd>
        </div>
        <div>
          <dt>Tokens</dt>
          <dd>{{ run?.total_tokens ?? 0 }}</dd>
        </div>
        <div>
          <dt>Cost</dt>
          <dd>{{ run?.total_cost ?? '0.00000000' }}</dd>
        </div>
      </dl>
    </div>

    <p v-else class="run-panel-empty">
      发送消息后，这里会展示本次 Agent Run 的标识和状态。
    </p>

    <div v-if="errorMessage" class="run-error" role="alert">
      <strong>运行提示</strong>
      <p>{{ errorMessage }}</p>
    </div>

    <!-- 事件时间线 -->
    <div v-if="events.length > 0" class="event-timeline">
      <h3>事件时间线</h3>
      <ol class="event-list">
        <li
          v-for="event in events"
          :key="event.sequence"
          class="event-item"
          :class="`event-item--${event.event_type.replace('.', '-')}`"
        >
          <div class="event-header">
            <span class="event-sequence">#{{ event.sequence }}</span>
            <span class="event-type">{{ event.event_type }}</span>
            <span class="event-time">{{ formatEventTime(event.timestamp) }}</span>
          </div>
          <span class="event-status" :class="`run-status--${event.status}`">
            {{ event.status }}
          </span>
        </li>
      </ol>
    </div>

    <div class="run-panel-note">
      <span>P4 Scope</span>
      <p>事件先持久化到数据库，再通过 SSE 推送到浏览器。支持断线恢复和事件回放。</p>
    </div>
  </aside>
</template>
