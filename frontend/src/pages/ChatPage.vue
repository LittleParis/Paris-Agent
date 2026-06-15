<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { storeToRefs } from 'pinia'

import AgentChat from '../components/chat/AgentChat.vue'
import AgentRunPanel from '../components/chat/AgentRunPanel.vue'
import MessageInput from '../components/chat/MessageInput.vue'
import SkillSelector from '../components/chat/SkillSelector.vue'
import SlashCommandMenu from '../components/chat/SlashCommandMenu.vue'
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
  selectedSkillId,
  skillInfo,
  retrievedMemories,
  writtenMemories,
} = storeToRefs(agentRunStore)

const messageInputRef = ref<InstanceType<typeof MessageInput> | null>(null)
const slashMenuRef = ref<InstanceType<typeof SlashCommandMenu> | null>(null)
const slashVisible = ref(false)
const slashQuery = ref('')

// 将 skill_id 格式化为可读标签
const selectedSkillLabel = computed(() => {
  if (!selectedSkillId.value) return ''
  return selectedSkillId.value.replace(/_/g, ' ')
})

function handleSubmit(message: string): void {
  void agentRunStore.submitMessage(message)
}

function handleSkillSelect(skillId: string | null): void {
  agentRunStore.selectedSkillId = skillId
}

function handleSlashCommand(query: string): void {
  slashQuery.value = query
  slashVisible.value = true
}

function handleSlashSelect(skillId: string): void {
  agentRunStore.selectedSkillId = skillId
  slashVisible.value = false
  // 清除输入框中的 / 前缀，chip 会自动显示
  if (messageInputRef.value) {
    messageInputRef.value.clearInput()
  }
}

function handleSlashClose(): void {
  slashVisible.value = false
}

function handleInputKeydown(event: KeyboardEvent): void {
  if (slashVisible.value && slashMenuRef.value) {
    slashMenuRef.value.handleKeydown(event)
  }
}

function handleRemoveSkill(): void {
  agentRunStore.selectedSkillId = null
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
        <div class="chat-composer-area">
          <SkillSelector
            :model-value="selectedSkillId"
            @update:model-value="handleSkillSelect"
          />
          <div style="position: relative">
            <SlashCommandMenu
              ref="slashMenuRef"
              :query="slashQuery"
              :visible="slashVisible"
              @select="handleSlashSelect"
              @close="handleSlashClose"
            />
            <MessageInput
              ref="messageInputRef"
              :disabled="isBusy"
              :selected-skill-label="selectedSkillLabel"
              @submit="handleSubmit"
              @slash-command="handleSlashCommand"
              @slash-close="handleSlashClose"
              @keydown="handleInputKeydown"
              @remove-skill="handleRemoveSkill"
            />
          </div>
        </div>
      </div>

      <AgentRunPanel
        :run="currentRun"
        :created-run="createdRun"
        :events="events"
        :connection-status="connectionStatus"
        :error-message="errorMessage"
        :skill-info="skillInfo"
        :retrieved-memories="retrievedMemories"
        :written-memories="writtenMemories"
      />
    </div>
  </section>
</template>
