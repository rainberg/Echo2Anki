<template>
  <div class="settings-container">
    <n-card title="个人信息" size="small" style="margin-bottom: 16px">
      <n-form ref="profileForm" :model="profileForm" label-placement="left" label-width="80" style="max-width: 400px">
        <n-form-item label="邮箱">
          <n-text>{{ authStore.user?.email }}</n-text>
        </n-form-item>
        <n-form-item label="昵称">
          <n-input v-model:value="profileForm.display_name" placeholder="输入昵称" />
        </n-form-item>
        <n-form-item label="角色">
          <n-tag :type="authStore.isAdmin ? 'warning' : 'default'" size="small">{{ authStore.isAdmin ? '管理员' : '普通用户' }}</n-tag>
        </n-form-item>
        <n-form-item label="注册时间">
          <n-text depth="3">{{ formatDate(authStore.user?.created_at) }}</n-text>
        </n-form-item>
        <n-form-item>
          <n-button type="primary" size="small" :loading="saving" @click="saveProfile">保存昵称</n-button>
        </n-form-item>
      </n-form>
    </n-card>

    <n-card title="修改密码" size="small" style="margin-bottom: 16px">
      <n-form ref="pwdForm" :model="pwdForm" :rules="pwdRules" label-placement="left" label-width="80" style="max-width: 400px">
        <n-form-item label="当前密码" path="old_password">
          <n-input v-model:value="pwdForm.old_password" type="password" show-password-on="click" placeholder="输入当前密码" />
        </n-form-item>
        <n-form-item label="新密码" path="new_password">
          <n-input v-model:value="pwdForm.new_password" type="password" show-password-on="click" placeholder="输入新密码（至少6位）" />
        </n-form-item>
        <n-form-item label="确认密码" path="confirm_password">
          <n-input v-model:value="pwdForm.confirm_password" type="password" show-password-on="click" placeholder="再次输入新密码" />
        </n-form-item>
        <n-form-item>
          <n-button type="primary" size="small" :loading="changingPwd" @click="changePassword">修改密码</n-button>
        </n-form-item>
      </n-form>
    </n-card>

    <n-card title="账户余额" size="small">
      <n-space align="center" :size="16">
        <n-statistic :value="authStore.credits" label="积分" />
        <n-button type="success" size="small" @click="$router.push('/billing')">充值 & 查看明细</n-button>
      </n-space>
    </n-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { useAuthStore } from '../stores/auth'
import { updateMe } from '../api/auth'

const router = useRouter()
const authStore = useAuthStore()
const message = useMessage()

const saving = ref(false)
const changingPwd = ref(false)

const profileForm = reactive({
  display_name: '',
})

const pwdForm = reactive({
  old_password: '',
  new_password: '',
  confirm_password: '',
})

const pwdRules = {
  old_password: [{ required: true, message: '请输入当前密码', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, message: '密码至少6位', trigger: 'blur' },
  ],
  confirm_password: [
    { required: true, message: '请确认新密码', trigger: 'blur' },
    {
      validator: (rule, value) => value === pwdForm.new_password,
      message: '两次密码不一致',
      trigger: 'blur',
    },
  ],
}

function formatDate(dt) {
  return dt ? new Date(dt).toLocaleString('zh-CN') : ''
}

async function saveProfile() {
  saving.value = true
  try {
    const { data } = await updateMe({ display_name: profileForm.display_name })
    authStore.user = data
    message.success('昵称已更新')
  } catch {
    message.error('更新失败')
  } finally {
    saving.value = false
  }
}

async function changePassword() {
  if (!pwdForm.old_password || !pwdForm.new_password) {
    message.warning('请填写完整')
    return
  }
  if (pwdForm.new_password !== pwdForm.confirm_password) {
    message.error('两次密码不一致')
    return
  }
  if (pwdForm.new_password.length < 6) {
    message.error('密码至少6位')
    return
  }
  changingPwd.value = true
  try {
    await updateMe({ old_password: pwdForm.old_password, password: pwdForm.new_password })
    message.success('密码已修改，请重新登录')
    authStore.clearAuth()
    router.push('/login')
    pwdForm.old_password = ''
    pwdForm.new_password = ''
    pwdForm.confirm_password = ''
  } catch {
    message.error('修改密码失败')
  } finally {
    changingPwd.value = false
  }
}

onMounted(() => {
  if (authStore.user) {
    profileForm.display_name = authStore.user.display_name || ''
  }
})
</script>

<style scoped>
.settings-container {
  max-width: 700px;
  margin: 0 auto;
}
</style>
