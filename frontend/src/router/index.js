import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/LoginView.vue'),
    meta: { guest: true },
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('../views/RegisterView.vue'),
    meta: { guest: true },
  },
  {
    path: '/',
    name: 'Public',
    component: () => import('../views/PublicView.vue'),
  },
  {
    path: '/help',
    name: 'Help',
    component: () => import('../views/HelpView.vue'),
  },
  {
    path: '/help/:slug',
    name: 'HelpArticle',
    component: () => import('../views/HelpView.vue'),
  },
  {
    path: '/public/:id',
    name: 'PublicDetail',
    component: () => import('../views/PublicDetailView.vue'),
  },
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: () => import('../views/DashboardView.vue'),
    meta: { auth: true },
  },
  {
    path: '/tasks',
    name: 'Tasks',
    component: () => import('../views/TasksView.vue'),
    meta: { auth: true },
  },
  {
    path: '/tasks/:id',
    name: 'TaskDetail',
    component: () => import('../views/TaskDetailView.vue'),
    meta: { auth: true },
  },
  {
    path: '/collections',
    name: 'Collections',
    component: () => import('../views/CollectionsView.vue'),
    meta: { auth: true },
  },
  {
    path: '/collections/:id',
    name: 'CollectionDetail',
    component: () => import('../views/CollectionDetailView.vue'),
    meta: { auth: true },
  },
  {
    path: '/billing',
    name: 'Billing',
    component: () => import('../views/BillingView.vue'),
    meta: { auth: true },
  },
  {
    path: '/transcribe',
    name: 'Transcribe',
    component: () => import('../views/TranscribeView.vue'),
    meta: { auth: true },
  },
  {
    path: '/anki',
    name: 'Anki',
    component: () => import('../views/AnkiView.vue'),
    meta: { auth: true },
  },
  {
    path: '/admin',
    name: 'Admin',
    component: () => import('../views/AdminView.vue'),
    meta: { auth: true, admin: true },
  },
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('../views/SettingsView.vue'),
    meta: { auth: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('access_token')
  if (to.meta.auth && !token) {
    next('/login')
  } else if (to.meta.guest && token) {
    next('/')
  } else {
    next()
  }
})

export default router
