import { describe, it, expect, beforeEach, vi } from 'vitest'
import axios from 'axios'
import MockAdapter from 'axios-mock-adapter'

vi.mock('../../src/api/client', async () => {
  const actual = await vi.importActual('../../src/api/client')
  return actual
})

describe('API Client', () => {
  let mock
  let api

  beforeEach(async () => {
    vi.resetModules()
    localStorage.clear()
    const clientModule = await import('../../src/api/client')
    api = clientModule.default
    mock = new MockAdapter(api, { delayResponse: 0 })
  })

  afterEach(() => {
    mock.restore()
  })

  describe('request interceptor', () => {
    it('adds Authorization header when token exists', async () => {
      localStorage.setItem('access_token', 'test-token')
      mock.onGet('/test').reply(200, { ok: true })

      const response = await api.get('/test')

      expect(response.data).toEqual({ ok: true })
      const requestHeaders = mock.history.get[0].headers
      expect(requestHeaders.Authorization).toBe('Bearer test-token')
    })

    it('does not add Authorization header when no token', async () => {
      mock.onGet('/test').reply(200, { ok: true })

      const response = await api.get('/test')

      expect(response.data).toEqual({ ok: true })
      const requestHeaders = mock.history.get[0].headers
      expect(requestHeaders.Authorization).toBeUndefined()
    })
  })

  describe('response interceptor', () => {
    it('returns response on success', async () => {
      mock.onGet('/test').reply(200, { data: 'ok' })
      const response = await api.get('/test')
      expect(response.status).toBe(200)
      expect(response.data).toEqual({ data: 'ok' })
    })

    it('handles 401 with refresh token', async () => {
      localStorage.setItem('access_token', 'expired')
      localStorage.setItem('refresh_token', 'valid-refresh')

      mock.onGet('/test').replyOnce(401)
      mock.onPost('/auth/refresh').replyOnce(200, {
        access_token: 'new-access',
        refresh_token: 'new-refresh',
      })
      mock.onGet('/test').replyOnce(200, { data: 'retried' })

      const response = await api.get('/test')

      expect(response.data).toEqual({ data: 'retried' })
      expect(localStorage.getItem('access_token')).toBe('new-access')
      expect(localStorage.getItem('refresh_token')).toBe('new-refresh')
    })
  })
})

describe('Auth API', () => {
  let mock

  beforeEach(() => {
    vi.resetModules()
    localStorage.clear()
  })

  afterEach(() => {
    if (mock) mock.restore()
  })

  it('login calls correct endpoint', async () => {
    const { login } = await import('../../src/api/auth')
    const { authApi } = await import('../../src/api/client')
    mock = new MockAdapter(authApi)

    mock.onPost('/auth/login/password').reply(200, { access_token: 'token' })

    const response = await login({ email: 'test@test.com', password: 'password' })
    expect(response.data.access_token).toBe('token')
  })

  it('register calls correct endpoint', async () => {
    const { register } = await import('../../src/api/auth')
    const { authApi } = await import('../../src/api/client')
    mock = new MockAdapter(authApi)

    mock.onPost('/auth/register/email').reply(201, { user_id: '1' })

    const response = await register({ email: 'test@test.com', password: 'password' })
    expect(response.status).toBe(201)
  })

  it('getMe calls correct endpoint', async () => {
    const { getMe } = await import('../../src/api/auth')
    const api = (await import('../../src/api/client')).default
    mock = new MockAdapter(api)

    mock.onGet('/auth/me').reply(200, { id: '1', email: 'test@test.com' })

    const response = await getMe()
    expect(response.data).toEqual({ id: '1', email: 'test@test.com' })
  })
})

describe('Tasks API', () => {
  let mock
  let api

  beforeEach(async () => {
    vi.resetModules()
    localStorage.clear()
    const clientModule = await import('../../src/api/client')
    api = clientModule.default
    mock = new MockAdapter(api)
  })

  afterEach(() => {
    mock.restore()
  })

  it('listTasks calls GET /tasks', async () => {
    const { listTasks } = await import('../../src/api/tasks')
    mock.onGet('/tasks').reply(200, { items: [], total: 0 })

    const response = await listTasks({ page: 1, per_page: 20 })
    expect(response.data).toEqual({ items: [], total: 0 })
  })

  it('createTask calls POST /tasks with multipart', async () => {
    const { createTask } = await import('../../src/api/tasks')
    mock.onPost('/tasks').reply(201, { task_id: '1' })

    const formData = new FormData()
    formData.append('file', new Blob(['test']))
    const response = await createTask(formData)
    expect(response.data).toEqual({ task_id: '1' })
  })

  it('getTask calls GET /tasks/:id', async () => {
    const { getTask } = await import('../../src/api/tasks')
    mock.onGet('/tasks/task-1').reply(200, { id: 'task-1' })

    const response = await getTask('task-1')
    expect(response.data).toEqual({ id: 'task-1' })
  })

  it('deleteTask calls DELETE /tasks/:id', async () => {
    const { deleteTask } = await import('../../src/api/tasks')
    mock.onDelete('/tasks/task-1').reply(204)

    const response = await deleteTask('task-1')
    expect(response.status).toBe(204)
  })

  it('retryTask calls POST /tasks/:id/retry', async () => {
    const { retryTask } = await import('../../src/api/tasks')
    mock.onPost('/tasks/task-1/retry').reply(200, { task_id: 'task-2' })

    const response = await retryTask('task-1', { engine: 'whisper' })
    expect(response.data).toEqual({ task_id: 'task-2' })
  })

  it('cancelTask calls POST /tasks/:id/cancel', async () => {
    const { cancelTask } = await import('../../src/api/tasks')
    mock.onPost('/tasks/task-1/cancel').reply(200, { status: 'cancelled' })

    const response = await cancelTask('task-1')
    expect(response.data).toEqual({ status: 'cancelled' })
  })
})

describe('Collections API', () => {
  let mock
  let api

  beforeEach(async () => {
    vi.resetModules()
    localStorage.clear()
    const clientModule = await import('../../src/api/client')
    api = clientModule.default
    mock = new MockAdapter(api)
  })

  afterEach(() => {
    mock.restore()
  })

  it('listCollections calls GET /collections', async () => {
    const { listCollections } = await import('../../src/api/collections')
    mock.onGet('/collections').reply(200, { items: [] })

    const response = await listCollections()
    expect(response.data).toEqual({ items: [] })
  })

  it('createCollection calls POST /collections', async () => {
    const { createCollection } = await import('../../src/api/collections')
    mock.onPost('/collections').reply(201, { id: 'col-1' })

    const response = await createCollection({ name: 'Test' })
    expect(response.data).toEqual({ id: 'col-1' })
  })

  it('addCollectionItems calls POST with segment_ids', async () => {
    const { addCollectionItems } = await import('../../src/api/collections')
    mock.onPost('/collections/col-1/items').reply(200, { added: 2 })

    const response = await addCollectionItems('col-1', ['seg-1', 'seg-2'])
    expect(response.data).toEqual({ added: 2 })
    const requestData = JSON.parse(mock.history.post[0].data)
    expect(requestData).toEqual({ segment_ids: ['seg-1', 'seg-2'] })
  })
})