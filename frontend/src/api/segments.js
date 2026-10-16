import api from './client'

export function listSegments(taskId) {
  return api.get(`/segments/${taskId}`)
}

export function updateSegment(segmentId, data) {
  return api.patch(`/segments/${segmentId}`, data)
}

export function translateSegment(segmentId) {
  return api.post(`/segments/${segmentId}/translate`)
}
