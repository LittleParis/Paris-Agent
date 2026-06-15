<script setup lang="ts">
import { reactive, watch } from 'vue'
import { ElButton, ElForm, ElFormItem, ElInput, ElOption, ElSelect } from 'element-plus'

import type { Memory, MemoryScope, MemoryType, MemoryWrite } from '../../api/memories'

const props = defineProps<{ memory: Memory | null }>()
const emit = defineEmits<{
  save: [payload: MemoryWrite]
  cancel: []
}>()

const form = reactive<MemoryWrite>({
  memory_type: 'semantic',
  scope: 'user',
  project_id: null,
  content: '',
  summary: null,
  importance: '0.5000',
  confidence: '0.8000',
  tags: [],
})

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
            importance: memory.importance,
            confidence: memory.confidence,
            tags: [...memory.tags],
          }
        : {
            memory_type: 'semantic',
            scope: 'user',
            project_id: null,
            content: '',
            summary: null,
            importance: '0.5000',
            confidence: '0.8000',
            tags: [],
          },
    )
  },
  { immediate: true },
)

function submit(): void {
  emit('save', {
    ...form,
    project_id: form.scope === 'project' ? form.project_id : null,
    tags: [...form.tags],
  })
}
</script>

<template>
  <ElForm label-position="top" @submit.prevent="submit">
    <div class="memory-editor-grid">
      <ElFormItem label="Type">
        <ElSelect v-model="form.memory_type">
          <ElOption
            v-for="item in ['learning_profile', 'semantic', 'episodic', 'project', 'procedural', 'task', 'runtime']"
            :key="item"
            :label="item"
            :value="item as MemoryType"
          />
        </ElSelect>
      </ElFormItem>
      <ElFormItem label="Scope">
        <ElSelect v-model="form.scope">
          <ElOption label="user" :value="'user' as MemoryScope" />
          <ElOption label="project" :value="'project' as MemoryScope" />
        </ElSelect>
      </ElFormItem>
    </div>
    <ElFormItem v-if="form.scope === 'project'" label="Project UUID">
      <ElInput v-model="form.project_id" />
    </ElFormItem>
    <ElFormItem label="Content">
      <ElInput v-model="form.content" type="textarea" :rows="5" />
    </ElFormItem>
    <ElFormItem label="Summary">
      <ElInput v-model="form.summary" />
    </ElFormItem>
    <div class="memory-editor-grid">
      <ElFormItem label="Importance">
        <ElInput v-model="form.importance" />
      </ElFormItem>
      <ElFormItem label="Confidence">
        <ElInput v-model="form.confidence" />
      </ElFormItem>
    </div>
    <ElFormItem label="Tags">
      <ElSelect v-model="form.tags" multiple allow-create filterable />
    </ElFormItem>
    <div class="memory-editor-actions">
      <ElButton @click="emit('cancel')">Cancel</ElButton>
      <ElButton type="primary" native-type="submit">Save memory</ElButton>
    </div>
  </ElForm>
</template>
