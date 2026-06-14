<script setup lang="ts">
import { computed, ref } from 'vue'

const props = defineProps<{
  disabled: boolean
}>()

const emit = defineEmits<{
  submit: [message: string]
}>()

const input = ref('')
const canSubmit = computed(
  () => !props.disabled && input.value.trim().length > 0,
)

function submit(): void {
  const message = input.value.trim()
  if (!message || props.disabled) {
    return
  }

  emit('submit', message)
  input.value = ''
}

function handleKeydown(event: KeyboardEvent): void {
  if (event.key !== 'Enter' || event.shiftKey) {
    return
  }

  event.preventDefault()
  submit()
}
</script>

<template>
  <form class="message-input" @submit.prevent="submit">
    <label for="agent-message" class="sr-only">发送给 Paris Agent</label>
    <textarea
      id="agent-message"
      v-model="input"
      :disabled="disabled"
      rows="3"
      placeholder="例如：Kafka 为什么能够保证高吞吐？"
      @keydown="handleKeydown"
    />
    <div class="message-input-footer">
      <span>Enter 发送，Shift + Enter 换行</span>
      <button type="submit" :disabled="!canSubmit">
        {{ disabled ? '运行中' : '发送' }}
      </button>
    </div>
  </form>
</template>
