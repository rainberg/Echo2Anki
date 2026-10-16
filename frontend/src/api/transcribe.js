import api from './client'

export function uploadTranscription(file, language = 'de') {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('language', language)
  return api.post('/transcribe/', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000,
  })
}

export function listTranscriptions() {
  return api.get('/transcribe/')
}

export function getTranscription(id) {
  return api.get(`/transcribe/${id}`)
}

export function deleteTranscription(id) {
  return api.delete(`/transcribe/${id}`)
}
