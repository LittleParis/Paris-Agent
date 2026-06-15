<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'

import { listSkills, type SkillListItem } from '../../api/skills'

const props = defineProps<{
  query: string
  visible: boolean
}>()

const emit = defineEmits<{
  select: [skillId: string]
  close: []
}>()

const skills = ref<SkillListItem[]>([])
const activeIndex = ref(0)

const filteredSkills = computed(() => {
  const q = props.query.toLowerCase()
  return skills.value.filter(
    (s) => s.skill_id.includes(q) || s.name.toLowerCase().includes(q),
  )
})

watch(() => props.visible, (val) => {
  if (val) { activeIndex.value = 0 }
})

watch(() => props.query, () => {
  activeIndex.value = 0
})

function selectSkill(skill: SkillListItem): void {
  emit('select', skill.skill_id)
}

function handleKeydown(event: KeyboardEvent): void {
  if (!props.visible) { return }

  if (event.key === 'ArrowDown') {
    event.preventDefault()
    activeIndex.value = Math.min(activeIndex.value + 1, filteredSkills.value.length - 1)
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    activeIndex.value = Math.max(activeIndex.value - 1, 0)
  } else if (event.key === 'Enter') {
    event.preventDefault()
    const skill = filteredSkills.value[activeIndex.value]
    if (skill) { selectSkill(skill) }
  } else if (event.key === 'Escape') {
    event.preventDefault()
    emit('close')
  }
}

onMounted(async () => {
  try {
    skills.value = await listSkills()
  } catch {
    // Silently fail — menu will be empty
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleKeydown)
})

defineExpose({ handleKeydown })
</script>

<template>
  <div v-if="visible && filteredSkills.length > 0" class="slash-command-menu">
    <div class="slash-menu-header">选择 Skill</div>
    <ul class="slash-menu-list">
      <li
        v-for="(skill, index) in filteredSkills"
        :key="skill.skill_id"
        class="slash-menu-item"
        :class="{ 'slash-menu-item--active': index === activeIndex }"
        @click="selectSkill(skill)"
        @mouseenter="activeIndex = index"
      >
        <span class="slash-command">/{{ skill.skill_id }}</span>
        <span class="slash-name">{{ skill.name }}</span>
      </li>
    </ul>
  </div>
</template>
