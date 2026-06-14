<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'

import ChatMessage from './ChatMessage.vue'
import type { ChatMessageItem } from '../../stores/agentRun'

const props = defineProps<{
  messages: ChatMessageItem[]
}>()

const messageList = ref<HTMLElement | null>(null)

watch(
  () =>
    props.messages.map(
      (message) => `${message.id}:${message.content}:${message.pending}`,
    ),
  async () => {
    await nextTick()
    messageList.value?.scrollTo({
      top: messageList.value.scrollHeight,
      behavior: 'smooth',
    })
  },
)
</script>

<template>
  <section ref="messageList" class="message-list" aria-live="polite">
    <div v-if="messages.length === 0" class="chat-empty-state">
      <span class="eyebrow">P3 / Agent Run Mock</span>
      <h2>向 Paris Agent 发起一次运行</h2>
      <p>
        输入一条技术问题。前端会创建 Agent Run，并通过 REST
        轮询展示当前状态和模拟回复。
      </p>
    </div>

    <ChatMessage
      v-for="message in messages"
      :key="message.id"
      :message="message"
    />
  </section>
</template>
