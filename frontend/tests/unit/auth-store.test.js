import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore } from '../../src/stores/auth'

vi.mock('../../src/api/auth', () => ({
  getMe: vi.fn(),
}))

import { getMe } from '../../src/api/auth'

describe('useAuthStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.clearAllMocks()
  })

  describe('initial state', () => {
    it('user is null by default', () => {
      const store = useAuthStore()
      expect(store.user).toBeNull()
    })

    it('accessToken is empty string by default', () => {
      const store = useAuthStore()
      expect(store.accessToken).toBe('')
    })

    it('refreshToken is empty string by default', () => {
      const store = useAuthStore()
      expect(store.refreshToken).toBe('')
    })

    it('isLoggedIn is false by default', () => {
      const store = useAuthStore()
      expect(store.isLoggedIn).toBe(false)
    })

    it('isAdmin is false by default', () => {
      const store = useAuthStore()
      expect(store.isAdmin).toBe(false)
    })

    it('credits is 0 by default', () => {
      const store = useAuthStore()
      expect(store.credits).toBe(0)
    })
  })

  describe('restore from localStorage', () => {
    it('restores accessToken from localStorage', () => {
      localStorage.setItem('access_token', 'test-access')
      localStorage.setItem('refresh_token', 'test-refresh')
      const store = useAuthStore()
      expect(store.accessToken).toBe('test-access')
      expect(store.refreshToken).toBe('test-refresh')
      expect(store.isLoggedIn).toBe(true)
    })
  })

  describe('setTokens', () => {
    it('sets tokens and persists to localStorage', () => {
      const store = useAuthStore()
      store.setTokens('new-access', 'new-refresh')
      expect(store.accessToken).toBe('new-access')
      expect(store.refreshToken).toBe('new-refresh')
      expect(localStorage.getItem('access_token')).toBe('new-access')
      expect(localStorage.getItem('refresh_token')).toBe('new-refresh')
    })

    it('isLoggedIn becomes true after setting tokens', () => {
      const store = useAuthStore()
      store.setTokens('token', 'refresh')
      expect(store.isLoggedIn).toBe(true)
    })
  })

  describe('clearAuth', () => {
    it('clears all auth state', () => {
      const store = useAuthStore()
      store.setTokens('token', 'refresh')
      store.user = { id: '1', email: 'test@test.com', role: 'user', credits: 100 }
      store.clearAuth()
      expect(store.user).toBeNull()
      expect(store.accessToken).toBe('')
      expect(store.refreshToken).toBe('')
      expect(store.isLoggedIn).toBe(false)
      expect(localStorage.getItem('access_token')).toBeNull()
      expect(localStorage.getItem('refresh_token')).toBeNull()
    })
  })

  describe('isAdmin', () => {
    it('returns true when user role is admin', () => {
      const store = useAuthStore()
      store.user = { id: '1', email: 'admin@test.com', role: 'admin' }
      expect(store.isAdmin).toBe(true)
    })

    it('returns false when user role is user', () => {
      const store = useAuthStore()
      store.user = { id: '1', email: 'user@test.com', role: 'user' }
      expect(store.isAdmin).toBe(false)
    })
  })

  describe('credits', () => {
    it('returns user credits', () => {
      const store = useAuthStore()
      store.user = { id: '1', credits: 150.5 }
      expect(store.credits).toBe(150.5)
    })

    it('returns 0 when user is null', () => {
      const store = useAuthStore()
      expect(store.credits).toBe(0)
    })
  })

  describe('fetchUser', () => {
    it('fetches user and updates state', async () => {
      const store = useAuthStore()
      store.setTokens('token', 'refresh')
      const mockUser = { id: '1', email: 'test@test.com', role: 'user', credits: 100 }
      getMe.mockResolvedValue({ data: mockUser })

      await store.fetchUser()

      expect(store.user).toEqual(mockUser)
      expect(getMe).toHaveBeenCalledTimes(1)
    })

    it('does nothing when no access token', async () => {
      const store = useAuthStore()
      await store.fetchUser()
      expect(getMe).not.toHaveBeenCalled()
    })

    it('clears auth on fetch failure', async () => {
      const store = useAuthStore()
      store.setTokens('token', 'refresh')
      getMe.mockRejectedValue(new Error('Network error'))

      await store.fetchUser()

      expect(store.user).toBeNull()
      expect(store.accessToken).toBe('')
      expect(store.isLoggedIn).toBe(false)
    })
  })
})