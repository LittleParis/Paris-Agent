<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElButton, ElDialog, ElMessage, ElMessageBox } from 'element-plus'

import {
  createMemory,
  deleteMemory,
  listMemories,
  updateMemory,
  type Memory,
  type MemoryWrite,
} from '../api/memories'
import MemoryEditor from '../components/memory/MemoryEditor.vue'
import MemoryList from '../components/memory/MemoryList.vue'

const items = ref<Memory[]>([])
const loading = ref(false)
const editorOpen = ref(false)
const editing = ref<Memory | null>(null)

async function load(): Promise<void> {
  loading.value = true
  try {
    items.value = (await listMemories()).items
  } finally {
    loading.value = false
  }
}

function openCreate(): void {
  editing.value = null
  editorOpen.value = true
}

function openEdit(memory: Memory): void {
  editing.value = memory
  editorOpen.value = true
}

async function save(payload: MemoryWrite): Promise<void> {
  if (editing.value) {
    await updateMemory(editing.value.memory_id, {
      ...payload,
      version: editing.value.version,
    })
  } else {
    await createMemory(payload)
  }
  editorOpen.value = false
  ElMessage.success('Memory saved')
  await load()
}

async function remove(memory: Memory): Promise<void> {
  await ElMessageBox.confirm('Soft-delete this memory?', 'Confirm')
  await deleteMemory(memory.memory_id, memory.version)
  ElMessage.success('Memory deleted')
  await load()
}

onMounted(load)
</script>

<template>
  <section class="memory-page">
    <header class="memory-page-header">
      <div>
        <span class="eyebrow">Long-Term Memory V1</span>
        <h2>Canonical memories</h2>
        <p>PostgreSQL records with deterministic retrieval and Milvus projection status.</p>
      </div>
      <ElButton type="primary" @click="openCreate">New memory</ElButton>
    </header>
    <MemoryList
      :items="items"
      :loading="loading"
      @edit="openEdit"
      @remove="remove"
    />
    <ElDialog v-model="editorOpen" :title="editing ? 'Edit memory' : 'New memory'" width="640">
      <MemoryEditor
        :memory="editing"
        @save="save"
        @cancel="editorOpen = false"
      />
    </ElDialog>
  </section>
</template>
