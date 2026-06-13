import { defineStore } from 'pinia'


export const useAppStore = defineStore('app', {
  state: () => ({
    applicationName: 'AGI Assistant',
    phase: 'P0 Project Skeleton',
  }),
})
