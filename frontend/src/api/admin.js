import api, { authApi } from './client'

// ─── User management (auth-service) ───────────────────────────────────

export function listUsers(params) {
  return authApi.get('/admin/users', { params })
}

export function topupUser(userId, data) {
  return authApi.post(`/admin/users/${userId}/add-credits`, data)
}

export function updateUserStatus(userId) {
  return authApi.put(`/admin/users/${userId}/toggle-active`)
}

export function updateUserRole(userId, data) {
  return authApi.put(`/admin/users/${userId}/role`, data)
}

export function resetUserPassword(userId) {
  return authApi.post(`/admin/users/${userId}/reset-password`)
}

// ─── Anki-specific (local backend) ────────────────────────────────────

export function updateUserEngines(userId, data) {
  return api.put(`/admin/users/${userId}/engines`, data)
}

export function updateUserPushConfigLimit(userId, data) {
  return api.put(`/admin/users/${userId}/push-config-limit`, data)
}

// ─── Help articles (local backend) ────────────────────────────────────

export function adminListHelpArticles(params) {
  return api.get('/admin/help/articles', { params })
}

export function adminCreateHelpArticle(data) {
  return api.post('/admin/help/articles', data)
}

export function adminUpdateHelpArticle(id, data) {
  return api.put(`/admin/help/articles/${id}`, data)
}

export function adminDeleteHelpArticle(id) {
  return api.delete(`/admin/help/articles/${id}`)
}
