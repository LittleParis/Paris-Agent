<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { ElButton, ElForm, ElFormItem, ElInput, ElInputNumber, ElMessage, ElOption, ElSelect } from 'element-plus'

import type { Memory, MemoryScope, MemoryType, MemoryWrite } from '../../api/memories'

const props = defineProps<{ memory: Memory | null }>()
const emit = defineEmits<{
  save: [payload: MemoryWrite]
  cancel: []
}>()

/** Internal form uses `number` for importance/confidence for ElInputNumber. */
const form = reactive({
  memory_type: 'semantic' as MemoryType,
  scope: 'user' as MemoryScope,
  project_id: null as string | null,
  content: '',
  summary: null as string | null,
  importance: 0.5,
  confidence: 0.8,
  tags: [] as string[],
})

const formRef = ref<InstanceType<typeof ElForm> | null>(null)

/** All memory types defined in the API, including system-managed short_term. */
const memoryTypeOptions: MemoryType[] = [
  'short_term',
  'learning_profile',
  'semantic',
  'episodic',
  'project',
  'procedural',
  'task',
  'runtime',
]

watch(
  () => props.memory,
  (memory) => {
    Object.assign(
      form,
      memory
        ? {
            memory_type: memory.memory_type,
            scope: memory.scope,
            project_id: memory.project_id,
            content: memory.content,
            summary: memory.summary,
            importance: parseFloat(memory.importance) || 0.5,
            confidence: parseFloat(memory.confidence) || 0.8,
            tags: [...memory.tags],
          }
        : {
            memory_type: 'semantic' as MemoryType,
            scope: 'user' as MemoryScope,
            project_id: null,
            content: '',
            summary: null,
            importance: 0.5,
            confidence: 0.8,
            tags: [] as string[],
          },
    )
  },
  { immediate: true },
)

function validate(): boolean {
  if (!form.content.trim()) {
    ElMessage.warning('Content is required.')
    return false
  }
  if (form.importance < 0 || form.importance > 1) {
    ElMessage.warning('Importance must be between 0 and 1.')
    return false
  }
  if (form.confidence < 0 || form.confidence > 1) {
    ElMessage.warning('Confidence must be between 0 and 1.')
    return false
  }
  if (form.scope === 'project' && !form.project_id?.trim()) {
    ElMessage.warning('Project UUID is required when scope is "project".')
    return false
  }
  return true
}

function submit(): void {
  if (!validate()) { return }
  const payload: MemoryWrite = {
    memory_type: form.memory_type,
    scope: form.scope,
    project_id: form.scope === 'project' ? form.project_id : null,
    content: form.content,
    summary: form.summary,
    importance: form.importance.toFixed(4),
    confidence: form.confidence.toFixed(4),
    tags: [...form.tags],
  }
  emit('save', payload)
}
</script>

<template>
  <ElForm ref="formRef" label-position="top" @submit.prevent="submit">
    <div class="memory-editor-grid">
      <ElFormItem label="Type">
        <ElSelect v-model="form.memory_type">
          <ElOption
            v-for="item in memoryTypeOptions"
            :key="item"
            :label="item"
            :value="item"
          />
        </ElSelect>
      </ElFormItem>
      <ElFormItem label="Scope">
        <ElSelect v-model="form.scope">
          <ElOption label="user" value="user" />
          <ElOption label="project" value="project" />
        </ElSelect>
      </ElFormItem>
    </div>
    <ElFormItem v-if="form.scope === 'project'" label="Project UUID">
      <ElInput v-model="form.project_id" placeholder="Enter project UUID" />
    </ElFormItem>
    <ElFormItem label="Content">
      <ElInput v-model="form.content" type="textarea" :rows="5" placeholder="Memory content" />
    </ElFormItem>
    <ElFormItem label="Summary">
      <ElInput v-model="form.summary" placeholder="Optional short summary" />
    </ElFormItem>
    <div class="memory-editor-grid">
      <ElFormItem label="Importance">
        <ElInputNumber
          v-model="form.importance"
          :min="0"
          :max="1"
          :step="0.1"
          :precision="4"
          controls-position="right"
          style="width: 100%"
        />
      </ElFormItem>
      <ElFormItem label="Confidence">
        <ElInputNumber
          v-model="form.confidence"
          :min="0"
          :max="1"
          :step="0.1"
          :precision="4"
          controls-position="right"
          style="width: 100%"
        />
      </ElFormItem>
    </div>
    <ElFormItem label="Tags">
      <ElSelect v-model="form.tags" multiple allow-create filterable placeholder="Add tags" />
    </ElFormItem>
    <div class="memory-editor-actions">
      <ElButton @click="emit('cancel')">Cancel</ElButton>
      <ElButton type="primary" native-type="submit">Save memory</ElButton>
    </div>
  </ElForm>
</template>
