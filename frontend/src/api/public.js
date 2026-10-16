import api from './client'

export function listPublicShares(params) {
  return api.get('/public/shares', { params })
}

export function getPublicShare(shareId) {
  return api.get(`/public/shares/${shareId}`)
}

export function createPublicShare(data) {
  return api.post('/public/shares', data)
}

export function updatePublicShare(shareId, data) {
  return api.patch(`/public/shares/${shareId}`, data)
}

export function deletePublicShare(shareId) {
  return api.delete(`/public/shares/${shareId}`)
}

export function likePublicShare(shareId) {
  return api.post(`/public/shares/${shareId}/like`)
}

export function unlikePublicShare(shareId) {
  return api.delete(`/public/shares/${shareId}/like`)
}

export function collectPublicShare(shareId, collectionId) {
  const params = {}
  if (collectionId) params.collection_id = collectionId
  return api.post(`/public/shares/${shareId}/collect`, null, { params })
}

export function uncollectPublicShare(shareId, collectionId) {
  const params = {}
  if (collectionId) params.collection_id = collectionId
  return api.delete(`/public/shares/${shareId}/collect`, { params })
}

export function recordPublicPlay(shareId) {
  return api.post(`/public/shares/${shareId}/play`)
}

export function listPublicCategories() {
  return api.get('/public/categories')
}

export function listPublicDifficulties() {
  return api.get('/public/difficulties')
}

export function listPublicTasks(params) {
  return api.get('/public/tasks', { params })
}

export function getPublicSegments(taskId) {
  return api.get(`/public/tasks/${taskId}/segments`)
}

export function listPublicTags() {
  return api.get('/public/tags')
}

export function searchSegments(params) {
  return api.get('/public/search', { params })
}
