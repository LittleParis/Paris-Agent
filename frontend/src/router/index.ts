import { createRouter, createWebHistory } from 'vue-router'

import WorkbenchLayout from '../layouts/WorkbenchLayout.vue'
import ChatPage from '../pages/ChatPage.vue'
import DashboardPage from '../pages/DashboardPage.vue'
import MemoryPage from '../pages/MemoryPage.vue'


const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: WorkbenchLayout,
      children: [
        {
          path: '',
          redirect: '/dashboard',
        },
        {
          path: 'dashboard',
          name: 'dashboard',
          component: DashboardPage,
          meta: {
            title: 'Dashboard',
          },
        },
        {
          path: 'chat',
          name: 'chat',
          component: ChatPage,
          meta: {
            title: 'Chat',
          },
        },
        {
          path: 'memory',
          name: 'memory',
          component: MemoryPage,
          meta: {
            title: 'Memory',
          },
        },
      ],
    },
  ],
})

router.afterEach((to) => {
  const title = typeof to.meta.title === 'string' ? to.meta.title : 'Workbench'
  document.title = `${title} | Paris Agent`
})

export default router
