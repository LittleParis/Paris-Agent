import { defineStore } from 'pinia'


export const useAppStore = defineStore('app', {
  state: () => ({
    applicationName: 'Paris Agent',
    phase: 'P6 Long-Term Memory V1',
  }),
})
