#!/bin/bash
set -e

echo "=== Phase 2: Deploy Frontend ==="

cd /opt/anki-app/frontend

mkdir -p src/api src/router src/stores src/views

cat > src/api/tasks.js << 'EOF'
import api from './client'

export function createTask(formData) {
  return api.post('/tasks', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  })
}

export function listTasks(params) {
  return api.get('/tasks', { params })
}

export function getTask(taskId) {
  return api.get(`/tasks/${taskId}`)
}

export function updateTask(taskId, data) {
  return api.patch(`/tasks/${taskId}`, data)
}

export function deleteTask(taskId) {
  return api.delete(`/tasks/${taskId}`)
}

export function retryTask(taskId, data) {
  return api.post(`/tasks/${taskId}/retry`, data)
}

export function cancelTask(taskId) {
  return api.post(`/tasks/${taskId}/cancel`)
}
EOF

cat > src/api/segments.js << 'EOF'
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
EOF

echo "Frontend API files created"
echo "Now uploading Vue components..."
