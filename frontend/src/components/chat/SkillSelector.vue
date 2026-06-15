<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { listSkills, type SkillListItem } from '../../api/skills'

const props = defineProps<{
  modelValue: string | null
}>()

const emit = defineEmits<{
  'update:modelValue': [skillId: string | null]
}>()

const skills = ref<SkillListItem[]>([])
const loading = ref(true)
const error = ref<string | null>(null)

async function loadSkills(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    skills.value = await listSkills()
  } catch (e) {
    error.value = '技能列表加载失败'
  } finally {
    loading.value = false
  }
}

function handleChange(event: Event): void {
  const target = event.target as HTMLSelectElement
  const value = target.value
  if (value === '__default__') {
    emit('update:modelValue', null)
  } else {
    emit('update:modelValue', value)
  }
}

const selectedValue = (): string => {
  if (props.modelValue === null) { return '__default__' }
  return props.modelValue
}

const currentLabel = (): string => {
  if (props.modelValue === null) {
    const defaultSkill = skills.value.find((s) => s.is_default)
    return defaultSkill ? `Default · ${defaultSkill.skill_id}` : 'Default'
  }
  const skill = skills.value.find((s) => s.skill_id === props.modelValue)
  return skill ? `${skill.name} (${skill.skill_id})` : props.modelValue
}

onMounted(() => {
  void loadSkills()
})

defineExpose({ reload: loadSkills })
</script>

<template>
  <div class="skill-selector">
    <label for="skill-select" class="skill-selector-label">Skill</label>
    <select
      id="skill-select"
      :value="selectedValue()"
      :disabled="loading || !!error"
      @change="handleChange"
    >
      <option value="__default__">
        {{ loading ? '加载中...' : error ? '加载失败' : currentLabel() }}
      </option>
      <option v-if="!loading && !error" disabled>──────────</option>
      <option
        v-for="skill in skills"
        :key="skill.skill_id"
        :value="skill.skill_id"
      >
        {{ skill.name }} ({{ skill.skill_id }}) · {{ skill.version }}
      </option>
    </select>
    <button
      v-if="error"
      type="button"
      class="skill-reload-btn"
      @click="loadSkills"
    >
      重试
    </button>
  </div>
</template>
