import { defineStore } from 'pinia'


export const useAppStore = defineStore('app', {
  state: () => ({
    applicationName: 'Paris Agent',
    phase: 'P4 SSE 事件流',
  }),
})
