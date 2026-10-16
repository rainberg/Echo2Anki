import api from './client'

export function getEngines() {
  return api.get('/system/engines')
}

export function getHealth() {
  return api.get('/system/health')
}

export function listEnginePricing() {
  return api.get('/system/engines')
}

// ─── Admin engine management ─────────────────────────────────────────

export function getAllEngines() {
  return api.get('/system/engines/all')
}

export function updateEngine(engineKey, modelSize, data) {
  return api.put(`/system/engines/${engineKey}/${modelSize}`, data)
}

// ─── System Settings ─────────────────────────────────────────────────

export function getSystemSettings() {
  return api.get('/system/settings')
}

export function updateSystemSetting(key, value) {
  return api.put(`/system/settings/${key}`, { value })
}

export function checkOpenAIKeyConfigured() {
  return api.get('/system/settings/openai_key_configured')
}
