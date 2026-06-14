import { defineStore } from 'pinia'


export const useAppStore = defineStore('app', {
  state: () => ({
    applicationName: 'Paris Agent',
    phase: 'P3 ChatPage Mock',
  }),
})
