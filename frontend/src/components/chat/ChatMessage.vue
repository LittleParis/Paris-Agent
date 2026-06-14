<script setup lang="ts">
import { computed } from 'vue'

import type { ChatMessageItem } from '../../stores/agentRun'

const props = defineProps<{
  message: ChatMessageItem
}>()

const roleLabel = computed(() => {
  if (props.message.role === 'user') {
    return '你'
  }

  if (props.message.role === 'assistant') {
    return 'Paris Agent'
  }

  return '系统'
})
</script>

<template>
  <article class="message-row" :class="`message-row--${message.role}`">
    <header class="message-meta">
      <span>{{ roleLabel }}</span>
      <span v-if="message.pending" class="message-pending">处理中</span>
    </header>
    <p>{{ message.content }}</p>
  </article>
</template>
