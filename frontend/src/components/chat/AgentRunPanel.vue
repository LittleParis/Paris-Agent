<script setup lang="ts">
import { computed } from 'vue'

import type { AgentRun, AgentRunCreated } from '../../api/agent'

const props = defineProps<{
  run: AgentRun | null
  createdRun: AgentRunCreated | null
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
  if (!value) {
    return '—'
  }

  return new Intl.DateTimeFormat('zh-CN', {
    dateStyle: 'medium',
    timeStyle: 'medium',
  }).format(new Date(value))
}
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

    <div class="run-panel-note">
      <span>P3 Scope</span>
      <p>当前通过 REST 短轮询更新状态；SSE 事件流将在 P4 接入。</p>
    </div>
  </aside>
</template>
