import api from './client'

export function listCollections() {
  return api.get('/collections')
}

export function getCollection(id) {
  return api.get(`/collections/${id}`)
}

export function createCollection(data) {
  return api.post('/collections', data)
}

export function updateCollection(id, data) {
  return api.patch(`/collections/${id}`, data)
}

export function deleteCollection(id) {
  return api.delete(`/collections/${id}`)
}

export function batchDeleteCollections(collectionIds) {
  return api.post('/collections/batch-delete', { collection_ids: collectionIds })
}

export function addCollectionItems(collectionId, segmentIds) {
  return api.post(`/collections/${collectionId}/items`, { segment_ids: segmentIds })
}

export function removeCollectionItem(collectionId, itemId) {
  return api.delete(`/collections/${collectionId}/items/${itemId}`)
}

export function batchRemoveCollectionItems(collectionId, itemIds) {
  return api.post(`/collections/${collectionId}/items/batch-delete`, { item_ids: itemIds })
}

export function toggleCollectionItem(collectionId, itemId, pushEnabled) {
  return api.patch(`/collections/${collectionId}/items/${itemId}`, { push_enabled: pushEnabled })
}
