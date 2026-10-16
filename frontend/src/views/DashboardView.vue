<template>
  <div>
    <n-grid :cols="{ xs: 2, s: 2, m: 4 }" :x-gap="16" :y-gap="16">
      <n-gi>
        <n-card title="任务管理" hoverable @click="$router.push('/tasks')">
          <n-button type="primary" size="small">上传音频</n-button>
        </n-card>
      </n-gi>
      <n-gi>
        <n-card title="收藏集" hoverable @click="$router.push('/collections')">
          <n-button type="info" size="small">管理收藏集</n-button>
        </n-card>
      </n-gi>
      <n-gi>
        <n-card title="公共库" hoverable @click="$router.push('/public')">
          <n-button type="success" size="small">浏览公共库</n-button>
        </n-card>
      </n-gi>
      <n-gi>
        <n-card title="Anki 推送" hoverable @click="$router.push('/anki')">
          <n-button type="warning" size="small">推送卡片</n-button>
        </n-card>
      </n-gi>
    </n-grid>
    <n-grid v-if="authStore.isAdmin" :cols="1" :x-gap="16" :y-gap="16" style="margin-top: 16px">
      <n-gi>
        <n-card title="管理员面板" hoverable @click="$router.push('/admin')" style="border: 1px solid #f0a020">
          <n-button type="warning" size="small">用户管理 / 充值 / 引擎配置</n-button>
        </n-card>
      </n-gi>
    </n-grid>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()

onMounted(() => {
  if (!authStore.user) authStore.fetchUser()
})
</script>
