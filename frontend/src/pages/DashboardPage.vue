<script setup lang="ts">
import { ElButton } from 'element-plus'
import { computed } from 'vue'

import { useAppStore } from '../stores/app'


const appStore = useAppStore()
const phaseLabel = computed(() => appStore.phase)

const services = [
  { name: 'FastAPI', detail: 'Health endpoint and configuration', state: 'Ready' },
  { name: 'PostgreSQL', detail: 'Primary relational storage', state: 'Compose' },
  { name: 'Redis', detail: 'Cache and runtime state', state: 'Compose' },
  { name: 'RabbitMQ', detail: 'Async tasks and audit events', state: 'Compose' },
]
</script>

<template>
  <section class="dashboard">
    <div class="intro-panel">
      <div>
        <span class="eyebrow">{{ phaseLabel }}</span>
        <h2>Agent engineering starts with a dependable foundation.</h2>
        <p>
          The workspace is prepared for Skills, long-term memory, Hybrid GraphRAG,
          DAG ReAct runtime, sandboxed tools, and observable agent runs.
        </p>
      </div>
      <ElButton type="primary" disabled>Start Agent Run in P1</ElButton>
    </div>

    <div class="service-grid">
      <article v-for="service in services" :key="service.name" class="service-card">
        <div class="card-heading">
          <h3>{{ service.name }}</h3>
          <span>{{ service.state }}</span>
        </div>
        <p>{{ service.detail }}</p>
      </article>
    </div>

    <div class="roadmap-panel">
      <span class="eyebrow">Next milestone</span>
      <h3>P1 Agent Run Mock</h3>
      <p>Connect the chat workspace to a traceable mock Agent Run and SSE event stream.</p>
    </div>
  </section>
</template>
