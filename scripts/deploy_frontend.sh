#!/bin/bash
set -e

echo "=== Phase 1.6: Deploy Frontend ==="

cd /opt/anki-app/frontend

echo "[1/5] Cleaning default template files..."
rm -f src/style.css
rm -rf src/components
rm -rf src/assets

echo "[2/5] Creating directory structure..."
mkdir -p src/api src/router src/stores src/views

echo "[3/5] Writing source files..."

cat > vite.config.js << 'VITEEOF'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
  },
})
VITEEOF

cat > index.html << 'HTMLEOF'
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Anki 听力卡片生成器</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.js"></script>
  </body>
</html>
HTMLEOF

cat > src/main.js << 'EOF'
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import naive from 'naive-ui'
import App from './App.vue'
import router from './router'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(naive)
app.mount('#app')
EOF

cat > src/App.vue << 'EOF'
<template>
  <n-config-provider :theme="null">
    <n-message-provider>
      <router-view />
    </n-message-provider>
  </n-config-provider>
</template>

<script setup>
</script>
EOF

cat > src/api/client.js << 'EOF'
import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true
      const refreshToken = localStorage.getItem('refresh_token')
      if (refreshToken) {
        try {
          const { data } = await axios.post('/api/auth/refresh', {
            refresh_token: refreshToken,
          })
          localStorage.setItem('access_token', data.access_token)
          localStorage.setItem('refresh_token', data.refresh_token)
          originalRequest.headers.Authorization = `Bearer ${data.access_token}`
          return api(originalRequest)
        } catch {
          localStorage.removeItem('access_token')
          localStorage.removeItem('refresh_token')
          window.location.href = '/login'
        }
      }
    }
    return Promise.reject(error)
  }
)

export default api
EOF

cat > src/api/auth.js << 'EOF'
import api from './client'

export function register(data) {
  return api.post('/auth/register', data)
}

export function login(data) {
  return api.post('/auth/login', data)
}

export function refreshToken(refreshToken) {
  return api.post('/auth/refresh', { refresh_token: refreshToken })
}

export function getMe() {
  return api.get('/auth/me')
}

export function updateMe(data) {
  return api.put('/auth/me', data)
}

export function getBillingBalance() {
  return api.get('/auth/billing/balance')
}

export function getBillingRecords(params) {
  return api.get('/auth/billing/records', { params })
}
EOF

cat > src/api/admin.js << 'EOF'
import api from './client'

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
EOF

cat > src/api/system.js << 'EOF'
import api from './client'

export function getEngines() {
  return api.get('/system/engines')
}

export function getHealth() {
  return api.get('/system/health')
}
EOF

cat > src/router/index.js << 'EOF'
import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/LoginView.vue'),
    meta: { guest: true },
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('../views/RegisterView.vue'),
    meta: { guest: true },
  },
  {
    path: '/',
    name: 'Dashboard',
    component: () => import('../views/DashboardView.vue'),
    meta: { auth: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('access_token')
  if (to.meta.auth && !token) {
    next('/login')
  } else if (to.meta.guest && token) {
    next('/')
  } else {
    next()
  }
})

export default router
EOF

cat > src/stores/auth.js << 'EOF'
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getMe } from '../api/auth'

export const useAuthStore = defineStore('auth', () => {
  const user = ref(null)
  const accessToken = ref(localStorage.getItem('access_token') || '')
  const refreshToken = ref(localStorage.getItem('refresh_token') || '')

  const isLoggedIn = computed(() => !!accessToken.value)
  const isAdmin = computed(() => user.value?.role === 'admin')
  const credits = computed(() => user.value?.credits ?? 0)

  function setTokens(access, refresh) {
    accessToken.value = access
    refreshToken.value = refresh
    localStorage.setItem('access_token', access)
    localStorage.setItem('refresh_token', refresh)
  }

  function clearAuth() {
    user.value = null
    accessToken.value = ''
    refreshToken.value = ''
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
  }

  async function fetchUser() {
    if (!accessToken.value) return
    try {
      const { data } = await getMe()
      user.value = data
    } catch {
      clearAuth()
    }
  }

  return { user, accessToken, refreshToken, isLoggedIn, isAdmin, credits, setTokens, clearAuth, fetchUser }
})
EOF

cat > src/views/LoginView.vue << 'EOF'
<template>
  <div class="login-container">
    <n-card title="登录" class="login-card">
      <n-form ref="formRef" :model="form" :rules="rules" @submit.prevent="handleLogin">
        <n-form-item label="邮箱" path="email">
          <n-input v-model:value="form.email" placeholder="请输入邮箱" />
        </n-form-item>
        <n-form-item label="密码" path="password">
          <n-input v-model:value="form.password" type="password" placeholder="请输入密码" show-password-on="click" />
        </n-form-item>
        <n-space vertical>
          <n-button type="primary" block :loading="loading" attr-type="submit">登录</n-button>
          <n-button text @click="$router.push('/register')">没有账号？立即注册</n-button>
        </n-space>
      </n-form>
    </n-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { login } from '../api/auth'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const message = useMessage()
const authStore = useAuthStore()

const form = ref({ email: '', password: '' })
const loading = ref(false)
const formRef = ref(null)

const rules = {
  email: [{ required: true, message: '请输入邮箱', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function handleLogin() {
  loading.value = true
  try {
    const { data } = await login(form.value)
    authStore.setTokens(data.access_token, data.refresh_token)
    authStore.user = data.user
    message.success('登录成功')
    router.push('/')
  } catch (err) {
    message.error(err.response?.data?.detail || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  background: #f5f5f5;
}
.login-card {
  width: 400px;
}
</style>
EOF

cat > src/views/RegisterView.vue << 'EOF'
<template>
  <div class="register-container">
    <n-card title="注册" class="register-card">
      <n-form ref="formRef" :model="form" :rules="rules" @submit.prevent="handleRegister">
        <n-form-item label="邮箱" path="email">
          <n-input v-model:value="form.email" placeholder="请输入邮箱" />
        </n-form-item>
        <n-form-item label="密码" path="password">
          <n-input v-model:value="form.password" type="password" placeholder="请输入密码（至少6位）" show-password-on="click" />
        </n-form-item>
        <n-form-item label="显示名称" path="display_name">
          <n-input v-model:value="form.display_name" placeholder="可选" />
        </n-form-item>
        <n-space vertical>
          <n-button type="primary" block :loading="loading" attr-type="submit">注册</n-button>
          <n-button text @click="$router.push('/login')">已有账号？立即登录</n-button>
        </n-space>
      </n-form>
    </n-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { register } from '../api/auth'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const message = useMessage()
const authStore = useAuthStore()

const form = ref({ email: '', password: '', display_name: '' })
const loading = ref(false)

const rules = {
  email: [{ required: true, message: '请输入邮箱', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少6位', trigger: 'blur' },
  ],
}

async function handleRegister() {
  loading.value = true
  try {
    const { data } = await register(form.value)
    authStore.setTokens(data.access_token, data.refresh_token)
    authStore.user = data.user
    message.success('注册成功')
    router.push('/')
  } catch (err) {
    message.error(err.response?.data?.detail || '注册失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.register-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  background: #f5f5f5;
}
.register-card {
  width: 400px;
}
</style>
EOF

cat > src/views/DashboardView.vue << 'EOF'
<template>
  <n-layout style="min-height: 100vh">
    <n-layout-header bordered style="padding: 12px 24px; display: flex; align-items: center; justify-content: space-between">
      <n-h3 style="margin: 0">🎧 德语听力卡片生成器</n-h3>
      <n-space align="center">
        <n-tag type="success">余额: {{ authStore.credits }} 分钟</n-tag>
        <n-tag v-if="authStore.isAdmin" type="warning">管理员</n-tag>
        <span>{{ authStore.user?.display_name || authStore.user?.email }}</span>
        <n-button size="small" @click="handleLogout">退出</n-button>
      </n-space>
    </n-layout-header>
    <n-layout-content style="padding: 24px">
      <n-grid :cols="3" :x-gap="16" :y-gap="16">
        <n-gi>
          <n-card title="余额" size="small">
            <n-statistic :value="authStore.credits" label="分钟" />
          </n-card>
        </n-gi>
        <n-gi>
          <n-card title="任务" size="small">
            <n-statistic :value="balance?.total_tasks ?? '-'" label="总任务数" />
          </n-card>
        </n-gi>
        <n-gi>
          <n-card title="使用量" size="small">
            <n-statistic :value="balance?.total_used ?? '-'" label="已使用分钟" />
          </n-card>
        </n-gi>
      </n-grid>
      <n-card title="功能开发中" style="margin-top: 16px">
        <n-empty description="更多功能正在开发中，敬请期待..." />
      </n-card>
    </n-layout-content>
  </n-layout>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { getBillingBalance } from '../api/auth'

const router = useRouter()
const authStore = useAuthStore()
const balance = ref(null)

onMounted(async () => {
  await authStore.fetchUser()
  try {
    const { data } = await getBillingBalance()
    balance.value = data
  } catch {}
})

function handleLogout() {
  authStore.clearAuth()
  router.push('/login')
}
</script>
EOF

echo "[4/5] Building frontend..."
npm run build 2>&1

echo "[5/5] Verifying build..."
ls -la dist/
echo "Frontend build complete!"
