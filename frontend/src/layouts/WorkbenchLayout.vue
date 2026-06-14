<script setup lang="ts">
import { ElTag } from 'element-plus'
import { computed } from 'vue'
import { useRoute } from 'vue-router'


const route = useRoute()
const pageTitle = computed(() =>
  typeof route.meta.title === 'string' ? route.meta.title : 'Workbench',
)
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
      </nav>

      <p class="phase-label">P3 / ChatPage Mock</p>
    </aside>

    <main class="workspace">
      <header class="topbar">
        <div>
          <span class="eyebrow">Skill-based Agent Workbench</span>
          <h1>{{ pageTitle }}</h1>
        </div>
        <ElTag
          :type="route.name === 'chat' ? 'primary' : 'success'"
          effect="plain"
        >
          {{ route.name === 'chat' ? 'P3 Integration' : 'Foundation' }}
        </ElTag>
      </header>

      <RouterView />
    </main>
  </div>
</template>
