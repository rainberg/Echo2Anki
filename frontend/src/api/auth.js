import api, { authApi } from './client'

// ─── Auth (direct to auth-service) ────────────────────────────────────

export function register(data) {
  return authApi.post('/auth/register/email', data)
}

export function registerPhone(data) {
  return authApi.post('/auth/register/phone', data)
}

export function login(data) {
  return authApi.post('/auth/login/password', data)
}

export function loginPhone(data) {
  return authApi.post('/auth/login/phone', data)
}

export function refreshToken(refreshToken) {
  return authApi.post('/auth/refresh', { refresh_token: refreshToken })
}

export function getMe() {
  return api.get('/auth/me')
}

export function updateMe(data) {
  return authApi.put('/auth/me', data)
}

// ─── Captcha (auth-service) ───────────────────────────────────────────

export const captcha = {
  generate() {
    return authApi.get('/auth/captcha/generate')
  },
  verify(data) {
    return authApi.post('/auth/captcha/verify', data)
  },
}

// ─── SMS (auth-service) ───────────────────────────────────────────────

export function sendSmsCode(data) {
  return authApi.post('/auth/sms/send', data)
}

// ─── Email verification (auth-service) ────────────────────────────────

export function sendEmailCode(data) {
  return authApi.post('/auth/email/send', data)
}

// ─── Password reset (auth-service) ────────────────────────────────────

export function resetPassword(data) {
  return authApi.post('/auth/reset-password', data)
}

// ─── Credits / Billing (auth-service) ─────────────────────────────────

export function getCreditsBalance() {
  return authApi.get('/credits/balance')
}

export function getCreditsLogs(params) {
  return authApi.get('/credits/logs', { params })
}

// ─── Admin (auth-service) ─────────────────────────────────────────────

export function adminListUsers(params) {
  return authApi.get('/admin/users', { params })
}

export function adminAddCredits(userId, data) {
  return authApi.post(`/admin/users/${userId}/add-credits`, data)
}

export function adminSetCredits(userId, data) {
  return authApi.put(`/admin/users/${userId}/credits`, data)
}

export function adminToggleActive(userId) {
  return authApi.put(`/admin/users/${userId}/toggle-active`)
}

export function adminUpdateRole(userId, data) {
  return authApi.put(`/admin/users/${userId}/role`, data)
}

export function adminResetPassword(userId) {
  return authApi.post(`/admin/users/${userId}/reset-password`)
}

// ─── Legacy compat (local backend) ────────────────────────────────────

export function getBillingBalance() {
  return api.get('/billing/balance')
}

export function getBillingRecords(params) {
  return api.get('/billing/records', { params })
}

export function listUsers(params) {
  return api.get('/admin/users', { params })
}

export function topupUser(userId, data) {
  return api.post(`/admin/users/${userId}/topup`, data)
}

export function updateUserEngines(userId, data) {
  return api.put(`/admin/users/${userId}/engines`, data)
}

export function updateUserStatus(userId, data) {
  return api.put(`/admin/users/${userId}/status`, data)
}
