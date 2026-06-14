<script setup lang="ts">
import { onBeforeUnmount } from 'vue'
import { storeToRefs } from 'pinia'

import AgentChat from '../components/chat/AgentChat.vue'
import AgentRunPanel from '../components/chat/AgentRunPanel.vue'
import MessageInput from '../components/chat/MessageInput.vue'
import { useAgentRunStore } from '../stores/agentRun'

const agentRunStore = useAgentRunStore()
const {
  messages,
  currentRun,
  createdRun,
  isBusy,
  errorMessage,
} = storeToRefs(agentRunStore)

function handleSubmit(message: string): void {
  void agentRunStore.submitMessage(message)
}

onBeforeUnmount(() => {
  agentRunStore.stopPolling()
})
</script>

<template>
  <section class="chat-page">
    <div class="chat-workspace">
      <div class="chat-column">
        <AgentChat :messages="messages" />
        <MessageInput :disabled="isBusy" @submit="handleSubmit" />
      </div>

      <AgentRunPanel
        :run="currentRun"
        :created-run="createdRun"
        :error-message="errorMessage"
      />
    </div>
  </section>
</template>
