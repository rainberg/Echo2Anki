import api from './client'

// ─── User endpoints ──────────────────────────────────────────────────

export function getRechargeInfo() {
  return api.get('/recharge/info')
}

export function getPaymentQR() {
  return api.get('/recharge/payment-qr', { responseType: 'blob' })
}

export function submitRecharge(formData) {
  return api.post('/recharge/submit', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function getMyRequests(params) {
  return api.get('/recharge/my-requests', { params })
}

export function getProofUrl(filename) {
  const token = localStorage.getItem('access_token')
  return `/api/recharge/proof/${filename}${token ? '?token=' + token : ''}`
}

// ─── Admin endpoints ─────────────────────────────────────────────────

export function adminUploadQR(formData) {
  return api.post('/recharge/admin/upload-qr', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function adminListRequests(params) {
  return api.get('/recharge/admin/requests', { params })
}

export function adminReviewRequest(requestId, data) {
  const formData = new FormData()
  formData.append('action', data.action)
  if (data.admin_note) formData.append('admin_note', data.admin_note)
  return api.post(`/recharge/admin/review/${requestId}`, formData)
}
