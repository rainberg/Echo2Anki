import api from './client'

export function createTask(formData) {
  return api.post('/tasks', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  })
}

export function listTasks(params) {
  return api.get('/tasks', { params })
}

export function getTask(taskId) {
  return api.get(`/tasks/${taskId}`)
}

export function updateTask(taskId, data) {
  return api.patch(`/tasks/${taskId}`, data)
}

export function deleteTask(taskId) {
  return api.delete(`/tasks/${taskId}`)
}

export function retryTask(taskId, data) {
  return api.post(`/tasks/${taskId}/retry`, data)
}

export function cancelTask(taskId) {
  return api.post(`/tasks/${taskId}/cancel`)
}
