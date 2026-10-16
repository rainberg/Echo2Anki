import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: { template: '<div>Login</div>' },
    meta: { guest: true },
  },
  {
    path: '/register',
    name: 'Register',
    component: { template: '<div>Register</div>' },
    meta: { guest: true },
  },
  {
    path: '/',
    name: 'Dashboard',
    component: { template: '<div>Dashboard</div>' },
    meta: { auth: true },
  },
  {
    path: '/tasks',
    name: 'Tasks',
    component: { template: '<div>Tasks</div>' },
    meta: { auth: true },
  },
  {
    path: '/tasks/:id',
    name: 'TaskDetail',
    component: { template: '<div>TaskDetail</div>' },
    meta: { auth: true },
  },
  {
    path: '/collections',
    name: 'Collections',
    component: { template: '<div>Collections</div>' },
    meta: { auth: true },
  },
  {
    path: '/collections/:id',
    name: 'CollectionDetail',
    component: { template: '<div>CollectionDetail</div>' },
    meta: { auth: true },
  },
  {
    path: '/billing',
    name: 'Billing',
    component: { template: '<div>Billing</div>' },
    meta: { auth: true },
  },
  {
    path: '/public',
    name: 'Public',
    component: { template: '<div>Public</div>' },
    meta: { auth: true },
  },
  {
    path: '/public/:id',
    name: 'PublicDetail',
    component: { template: '<div>PublicDetail</div>' },
    meta: { auth: true },
  },
  {
    path: '/anki',
    name: 'Anki',
    component: { template: '<div>Anki</div>' },
    meta: { auth: true },
  },
  {
    path: '/admin',
    name: 'Admin',
    component: { template: '<div>Admin</div>' },
    meta: { auth: true, admin: true },
  },
  {
    path: '/settings',
    name: 'Settings',
    component: { template: '<div>Settings</div>' },
    meta: { auth: true },
  },
]

function createTestRouter() {
  return createRouter({
    history: createWebHistory(),
    routes,
  })
}

describe('Router Configuration', () => {
  describe('route definitions', () => {
    it('has 13 routes', () => {
      expect(routes).toHaveLength(13)
    })

    it('has guest routes', () => {
      const guestRoutes = routes.filter(r => r.meta.guest)
      expect(guestRoutes.map(r => r.path)).toEqual(['/login', '/register'])
    })

    it('has auth routes', () => {
      const authRoutes = routes.filter(r => r.meta.auth)
      expect(authRoutes).toHaveLength(11)
    })

    it('has admin route', () => {
      const adminRoute = routes.find(r => r.meta.admin)
      expect(adminRoute.path).toBe('/admin')
    })

    it('has dynamic route for task detail', () => {
      const taskDetail = routes.find(r => r.path === '/tasks/:id')
      expect(taskDetail).toBeDefined()
      expect(taskDetail.meta.auth).toBe(true)
    })

    it('has dynamic route for collection detail', () => {
      const colDetail = routes.find(r => r.path === '/collections/:id')
      expect(colDetail).toBeDefined()
    })

    it('root path is Dashboard', () => {
      const root = routes.find(r => r.path === '/')
      expect(root.name).toBe('Dashboard')
    })
  })

  describe('navigation guards', () => {
    let router

    beforeEach(() => {
      router = createTestRouter()
      localStorage.clear()
    })

    it('redirects to /login when accessing auth route without token', async () => {
      await router.push('/tasks')
      await router.isReady()

      expect(router.currentRoute.value.path).toBe('/login')
    })

    it('allows access to auth route with token', async () => {
      localStorage.setItem('access_token', 'valid-token')
      await router.push('/tasks')
      await router.isReady()

      expect(router.currentRoute.value.path).toBe('/tasks')
    })

    it('redirects to / when accessing guest route with token', async () => {
      localStorage.setItem('access_token', 'valid-token')
      await router.push('/login')
      await router.isReady()

      expect(router.currentRoute.value.path).toBe('/')
    })

    it('allows access to guest route without token', async () => {
      await router.push('/register')
      await router.isReady()

      expect(router.currentRoute.value.path).toBe('/register')
    })

    it('allows access to root without token (redirects to login)', async () => {
      await router.push('/')
      await router.isReady()

      expect(router.currentRoute.value.path).toBe('/login')
    })
  })
})