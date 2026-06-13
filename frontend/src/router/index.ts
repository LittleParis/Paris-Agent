import { createRouter, createWebHistory } from 'vue-router'

import WorkbenchLayout from '../layouts/WorkbenchLayout.vue'
import DashboardPage from '../pages/DashboardPage.vue'


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
      ],
    },
  ],
})

router.afterEach((to) => {
  const title = typeof to.meta.title === 'string' ? to.meta.title : 'Workbench'
  document.title = `${title} | AGI Assistant`
})

export default router
