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
  events,
  connectionStatus,
  isBusy,
  errorMessage,
} = storeToRefs(agentRunStore)

function handleSubmit(message: string): void {
  void agentRunStore.submitMessage(message)
}

onBeforeUnmount(() => {
  agentRunStore.closeSSE()
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
        :events="events"
        :connection-status="connectionStatus"
        :error-message="errorMessage"
      />
    </div>
  </section>
</template>
