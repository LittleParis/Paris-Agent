<script setup lang="ts">
import { computed, ref, watch, nextTick } from 'vue'

const props = defineProps<{
  disabled: boolean
  selectedSkillLabel?: string
}>()

const emit = defineEmits<{
  submit: [message: string]
  slashCommand: [query: string]
  slashClose: []
  keydown: [event: KeyboardEvent]
  removeSkill: []
}>()

const input = ref('')
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const canSubmit = computed(
  () => !props.disabled && input.value.trim().length > 0,
)

// Detect slash prefix
const slashQuery = computed(() => {
  const trimmed = input.value.trimStart()
  if (trimmed.startsWith('/') && !trimmed.includes(' ', 1)) {
    return trimmed.slice(1)
  }
  return null
})

watch(slashQuery, (q) => {
  if (q !== null) {
    emit('slashCommand', q)
  } else {
    emit('slashClose')
  }
})

function submit(): void {
  const message = input.value.trim()
  if (!message || props.disabled) {
    return
  }

  emit('submit', message)
  input.value = ''
}

function clearInput(): void {
  input.value = ''
}

function handleKeydown(event: KeyboardEvent): void {
  // 转发 keydown 事件给父组件（用于斜杠菜单键盘导航）
  emit('keydown', event)

  // Backspace on empty input → remove skill chip
  if (event.key === 'Backspace' && input.value === '' && props.selectedSkillLabel) {
    event.preventDefault()
    emit('removeSkill')
    return
  }

  if (event.key !== 'Enter' || event.shiftKey) {
    return
  }

  event.preventDefault()
  submit()
}

// When skill chip appears, focus textarea
watch(() => props.selectedSkillLabel, (val) => {
  if (val) {
    nextTick(() => {
      textareaRef.value?.focus()
    })
  }
})

defineExpose({ clearInput })
</script>

<template>
  <form class="message-input" @submit.prevent="submit">
    <label for="agent-message" class="sr-only">发送给 Paris Agent</label>
    <div class="textarea-container" :class="{ 'has-chip': !!selectedSkillLabel }">
      <span v-if="selectedSkillLabel" class="inline-skill-chip">
        <span class="chip-icon">S</span>
        <span class="chip-label">{{ selectedSkillLabel }}</span>
        <button type="button" class="chip-remove" @click="emit('removeSkill')" title="移除 Skill">&times;</button>
      </span>
      <textarea
        ref="textareaRef"
        id="agent-message"
        v-model="input"
        :disabled="disabled"
        rows="3"
        :placeholder="selectedSkillLabel ? '输入你的问题…' : '例如：Kafka 为什么能够保证高吞吐？输入 / 选择 Skill'"
        @keydown="handleKeydown"
      />
    </div>
    <div class="message-input-footer">
      <span>Enter 发送，Shift + Enter 换行，输入 / 选择 Skill</span>
      <button type="submit" :disabled="!canSubmit">
        {{ disabled ? '运行中' : '发送' }}
      </button>
    </div>
  </form>
</template>
