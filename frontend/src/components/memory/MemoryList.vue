<script setup lang="ts">
import { ElButton, ElEmpty, ElTable, ElTableColumn, ElTag } from 'element-plus'

import type { Memory } from '../../api/memories'

defineProps<{ items: Memory[]; loading: boolean }>()
const emit = defineEmits<{
  edit: [memory: Memory]
  remove: [memory: Memory]
}>()
</script>

<template>
  <ElTable v-if="items.length" :data="items" v-loading="loading">
    <ElTableColumn prop="memory_type" label="Type" width="150">
      <template #default="{ row }">
        <ElTag effect="plain">{{ row.memory_type }}</ElTag>
      </template>
    </ElTableColumn>
    <ElTableColumn label="Memory" min-width="360">
      <template #default="{ row }">
        <strong>{{ row.summary || row.content.slice(0, 80) }}</strong>
        <p>{{ row.content }}</p>
      </template>
    </ElTableColumn>
    <ElTableColumn label="Tags" width="220">
      <template #default="{ row }">{{ row.tags.join(', ') || 'None' }}</template>
    </ElTableColumn>
    <ElTableColumn prop="access_count" label="Access" width="90" />
    <ElTableColumn label="Actions" width="160">
      <template #default="{ row }">
        <ElButton link type="primary" @click="emit('edit', row as Memory)">Edit</ElButton>
        <ElButton link type="danger" @click="emit('remove', row as Memory)">Delete</ElButton>
      </template>
    </ElTableColumn>
  </ElTable>
  <ElEmpty v-else description="No long-term memories yet." />
</template>
