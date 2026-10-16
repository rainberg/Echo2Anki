import api from './client'

export function listTags() {
  return api.get('/tags')
}

export function createTag(data) {
  return api.post('/tags', data)
}

export function deleteTag(id) {
  return api.delete(`/tags/${id}`)
}

export function getTaskTags(taskId) {
  return api.get(`/tags/tasks/${taskId}`)
}

export function setTaskTags(taskId, tagIds) {
  return api.post(`/tags/tasks/${taskId}`, { tag_ids: tagIds })
}
