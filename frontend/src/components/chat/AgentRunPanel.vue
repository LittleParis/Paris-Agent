<script setup lang="ts">
import { computed } from 'vue'

import type { AgentRun, AgentRunCreated } from '../../api/agent'
import type { MemoryEventItem, SSEConnectionStatus } from '../../api/agentEvents'
import type { RuntimeEventItem } from '../../stores/agentRun'

const props = defineProps<{
  run: AgentRun | null
  createdRun: AgentRunCreated | null
  events: RuntimeEventItem[]
  connectionStatus: SSEConnectionStatus
  errorMessage: string | null
  skillInfo: {
    skill_id: string | null
    skill_version: string | null
    skill_selection_mode: string | null
  }
  retrievedMemories: MemoryEventItem[]
  writtenMemories: MemoryEventItem[]
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
        <div v-if="skillInfo.skill_id">
          <dt>Skill</dt>
          <dd>{{ skillInfo.skill_id }}@{{ skillInfo.skill_version ?? '?' }}</dd>
        </div>
        <div v-if="skillInfo.skill_selection_mode">
          <dt>Selection</dt>
          <dd>{{ skillInfo.skill_selection_mode }}</dd>
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

    <!-- P6 Memory Events -->
    <section v-if="retrievedMemories.length || writtenMemories.length" class="runtime-memory">
      <h3>Memories</h3>
      <p v-if="retrievedMemories.length">Retrieved: {{ retrievedMemories.length }}</p>
      <ul v-if="retrievedMemories.length">
        <li v-for="item in retrievedMemories" :key="item.memory_id">
          {{ item.memory_type }} · {{ item.summary }}
        </li>
      </ul>
      <p v-if="writtenMemories.length">Written: {{ writtenMemories.length }}</p>
      <ul v-if="writtenMemories.length">
        <li v-for="item in writtenMemories" :key="item.memory_id">
          {{ item.memory_type }} · {{ item.summary }}
        </li>
      </ul>
    </section>

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
      <span>P6 Scope</span>
      <p>Long-Term Memory V1 — 检索与写入事件实时展示。Skill 快照由 P5 提供，每个 Run 绑定不可变 Skill Version。</p>
    </div>
  </aside>
</template>
