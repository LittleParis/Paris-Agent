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
import { getErrorMessage } from '../utils/error'

const items = ref<Memory[]>([])
const loading = ref(false)
const loadingMore = ref(false)
const editorOpen = ref(false)
const editing = ref<Memory | null>(null)
const nextCursor = ref<string | null>(null)

async function load(): Promise<void> {
  loading.value = true
  try {
    const response = await listMemories()
    items.value = response.items
    nextCursor.value = response.next_cursor
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    loading.value = false
  }
}

async function loadMore(): Promise<void> {
  if (!nextCursor.value || loadingMore.value) { return }
  loadingMore.value = true
  try {
    const response = await listMemories(nextCursor.value)
    items.value = [...items.value, ...response.items]
    nextCursor.value = response.next_cursor
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    loadingMore.value = false
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
  try {
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
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  }
}

async function remove(memory: Memory): Promise<void> {
  try {
    await ElMessageBox.confirm('Soft-delete this memory?', 'Confirm')
  } catch {
    // User cancelled the dialog — nothing to do
    return
  }
  try {
    await deleteMemory(memory.memory_id, memory.version)
    ElMessage.success('Memory deleted')
    await load()
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  }
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
    <div v-if="nextCursor" class="memory-load-more">
      <ElButton :loading="loadingMore" @click="loadMore">Load more</ElButton>
    </div>
    <ElDialog v-model="editorOpen" :title="editing ? 'Edit memory' : 'New memory'" width="640">
      <MemoryEditor
        :memory="editing"
        @save="save"
        @cancel="editorOpen = false"
      />
    </ElDialog>
  </section>
</template>
