<script setup lang="ts">
import { ElTag } from 'element-plus'
import { computed } from 'vue'
import { useRoute } from 'vue-router'


const route = useRoute()
const pageTitle = computed(() =>
  typeof route.meta.title === 'string' ? route.meta.title : 'Workbench',
)

const routeTag = computed(() => {
  switch (route.name) {
    case 'chat':
      return { label: 'P3 Integration', type: 'primary' as const }
    case 'memory':
      return { label: 'P6 Memory', type: 'warning' as const }
    default:
      return { label: 'Foundation', type: 'success' as const }
  }
})
</script>

<template>
  <div class="workbench-shell">
    <aside class="sidebar">
      <div class="brand">
        <span class="brand-mark">PA</span>
        <div>
          <strong>Paris Agent</strong>
          <small>Agent Workbench</small>
        </div>
      </div>

      <nav aria-label="Primary navigation">
        <RouterLink to="/dashboard">Dashboard</RouterLink>
        <RouterLink to="/chat">Chat</RouterLink>
        <RouterLink to="/memory">Memory</RouterLink>
      </nav>

      <p class="phase-label">P6 / Long-Term Memory V1</p>
    </aside>

    <main class="workspace">
      <header class="topbar">
        <div>
          <span class="eyebrow">Skill-based Agent Workbench</span>
          <h1>{{ pageTitle }}</h1>
        </div>
        <ElTag :type="routeTag.type" effect="plain">
          {{ routeTag.label }}
        </ElTag>
      </header>

      <RouterView />
    </main>
  </div>
</template>
