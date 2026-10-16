import api from './client'

export function listPushConfigs() {
  return api.get('/anki/configs')
}

export function createPushConfig(data) {
  return api.post('/anki/configs', data)
}

export function updatePushConfig(id, data) {
  return api.patch(`/anki/configs/${id}`, data)
}

export function deletePushConfig(id) {
  return api.delete(`/anki/configs/${id}`)
}

export function pushToAnki(data) {
  return api.post('/anki/push', data)
}

export function getPushStatus(collectionId) {
  return api.get('/anki/push-status', { params: { collection_id: collectionId } })
}

export function listPushRecords() {
  return api.get('/anki/records')
}
