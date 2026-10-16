<template>
  <n-config-provider :theme="null">
    <n-message-provider>
      <n-dialog-provider>
      <n-layout v-if="showNav" style="min-height: 100vh">
        <n-layout-header bordered style="padding: 8px 16px; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; position: sticky; top: 0; z-index: 100; background: #fff">
          <router-link to="/" style="text-decoration: none; color: inherit; font-weight: 600; font-size: 16px; white-space: nowrap">🎧 德语听力</router-link>
          <n-space :size="4" :wrap="true" align="center">
            <n-button size="tiny" quaternary :type="currentRoute === '/' ? 'primary' : 'default'" @click="$router.push('/')">公共库</n-button>
            <template v-if="isLoggedIn">
              <n-button size="tiny" quaternary :type="currentRoute === '/dashboard' ? 'primary' : 'default'" @click="$router.push('/dashboard')">仪表盘</n-button>
              <n-button size="tiny" quaternary :type="currentRoute.startsWith('/tasks') ? 'primary' : 'default'" @click="$router.push('/tasks')">任务</n-button>
              <n-button size="tiny" quaternary :type="currentRoute.startsWith('/collections') ? 'primary' : 'default'" @click="$router.push('/collections')">收藏集</n-button>
              <n-button size="tiny" quaternary :type="currentRoute === '/anki' ? 'primary' : 'default'" @click="$router.push('/anki')">Anki</n-button>
              <n-button size="tiny" quaternary :type="currentRoute.startsWith('/help') ? 'primary' : 'default'" @click="$router.push('/help')">帮助</n-button>
              <n-divider vertical />
              <n-tag size="small" type="success">余额: {{ authStore.credits }} 积分</n-tag>
              <n-button size="tiny" quaternary type="success" @click="$router.push('/billing?topup=1')">充值</n-button>
              <n-divider vertical />
              <n-button size="tiny" quaternary :type="currentRoute === '/settings' ? 'primary' : 'default'" @click="$router.push('/settings')">
                {{ authStore.user?.display_name || '设置' }}
              </n-button>
              <n-button v-if="authStore.isAdmin" size="tiny" quaternary :type="currentRoute === '/admin' ? 'warning' : 'default'" @click="$router.push('/admin')">管理</n-button>
              <n-button size="tiny" quaternary type="error" @click="handleLogout">退出</n-button>
            </template>
            <template v-else>
              <n-button size="tiny" type="primary" @click="$router.push('/login')">登录</n-button>
              <n-button size="tiny" quaternary @click="$router.push('/register')">注册</n-button>
            </template>
          </n-space>
        </n-layout-header>
        <n-layout-content style="padding: 16px; max-width: 960px; margin: 0 auto; width: 100%">
          <router-view />
        </n-layout-content>
      </n-layout>
      <router-view v-else />
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const isLoggedIn = computed(() => authStore.isLoggedIn)

const showNav = computed(() => {
  // Show nav on all pages except login/register (guest pages when not logged in)
  return !route.meta.guest
})

const currentRoute = computed(() => route.path)

onMounted(() => {
  if (authStore.isLoggedIn && !authStore.user) {
    authStore.fetchUser()
  }
})

function handleLogout() {
  authStore.clearAuth()
  router.push('/')
}
</script>
