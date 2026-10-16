<template>
  <div class="login-container">
    <n-card title="登录" class="login-card">
      <n-tabs v-model:value="tab" type="segment" animated>
        <n-tab-pane name="password" tab="密码登录">
          <n-form ref="pwdFormRef" :model="pwdForm" :rules="pwdRules" @submit.prevent="handlePasswordLogin">
            <n-form-item label="邮箱/手机号" path="account">
              <n-input v-model:value="pwdForm.account" placeholder="请输入邮箱或手机号" />
            </n-form-item>
            <n-form-item label="密码" path="password">
              <n-input v-model:value="pwdForm.password" type="password" placeholder="请输入密码" show-password-on="click" />
            </n-form-item>
            <n-space vertical>
              <n-button type="primary" block :loading="loading" attr-type="submit">登录</n-button>
            </n-space>
            <n-space justify="end" style="margin-top: 8px">
              <n-button text size="small" @click="showResetPassword = true">忘记密码？</n-button>
            </n-space>
          </n-form>
        </n-tab-pane>

        <n-tab-pane name="sms" tab="验证码登录">
          <n-form ref="smsFormRef" :model="smsForm" :rules="smsRules" @submit.prevent="handleSmsLogin">
            <n-form-item label="手机号" path="phone">
              <n-input v-model:value="smsForm.phone" placeholder="请输入11位手机号" maxlength="11" />
            </n-form-item>

            <n-form-item label="短信验证码" path="code">
              <n-input-group>
                <div style="flex: 1" @click="onCodeFocus('sms')">
                  <n-input v-model:value="smsForm.code" placeholder="请输入验证码" maxlength="6" />
                </div>
                <n-button :disabled="smsCountdown > 0 || !smsCaptchaVerified || !smsForm.phone" :loading="smsLoading" @click="sendSms">
                  {{ smsCountdown > 0 ? `${smsCountdown}秒后重发` : '获取验证码' }}
                </n-button>
              </n-input-group>
            </n-form-item>

            <n-space vertical>
              <n-button type="primary" block :loading="loading" attr-type="submit">登录</n-button>
            </n-space>
          </n-form>
        </n-tab-pane>
      </n-tabs>

      <n-divider />
      <n-button text block @click="$router.push('/register')">没有账号？立即注册</n-button>
    </n-card>

    <!-- 验证码滑块弹窗 -->
    <CaptchaSliderDialog
      v-model:show="showCaptchaDialog"
      :captcha-bg="captchaBg"
      :captcha-slider-img="captchaSliderImg"
      :captcha-y="captchaY"
      :puzzle-width="puzzleWidth"
      :captcha-id="captchaId"
      @verified="onCaptchaVerified"
      @refresh="refreshCaptcha"
    />

    <!-- 密码找回弹窗 -->
    <n-modal v-model:show="showResetPassword">
      <n-card title="找回密码" style="width: 420px" :bordered="false">
        <n-form ref="resetFormRef" :model="resetForm" :rules="resetRules" @submit.prevent="handleResetPassword">
          <n-form-item label="邮箱" path="email">
            <n-input v-model:value="resetForm.email" placeholder="请输入注册时使用的邮箱" />
          </n-form-item>

          <n-form-item label="邮箱验证码" path="code">
            <n-input-group>
              <div style="flex: 1" @click="onCodeFocus('reset')">
                <n-input v-model:value="resetForm.code" placeholder="请输入验证码" maxlength="6" />
              </div>
              <n-button :disabled="resetCountdown > 0 || !resetCaptchaVerified || !resetForm.email" :loading="resetCodeLoading" @click="sendResetCode">
                {{ resetCountdown > 0 ? `${resetCountdown}秒后重发` : '获取验证码' }}
              </n-button>
            </n-input-group>
          </n-form-item>
          <n-form-item label="新密码" path="password">
            <n-input v-model:value="resetForm.password" type="password" placeholder="请输入新密码（至少6位）" show-password-on="click" />
          </n-form-item>
          <n-space vertical>
            <n-button type="primary" block :loading="resetLoading" attr-type="submit">重置密码</n-button>
          </n-space>
        </n-form>
      </n-card>
    </n-modal>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { login, loginPhone, sendSmsCode, sendEmailCode, resetPassword, captcha } from '../api/auth'
import { useAuthStore } from '../stores/auth'
import CaptchaSliderDialog from '../components/CaptchaSliderDialog.vue'

const router = useRouter()
const message = useMessage()
const authStore = useAuthStore()

const tab = ref('password')
const loading = ref(false)

const pwdFormRef = ref(null)
const pwdForm = ref({ account: '', password: '' })
const pwdRules = {
  account: [{ required: true, message: '请输入邮箱或手机号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

const smsFormRef = ref(null)
const smsForm = ref({ phone: '', code: '' })
const smsRules = {
  phone: [
    { required: true, message: '请输入手机号', trigger: 'blur' },
    { pattern: /^1[3-9]\d{9}$/, message: '手机号格式不正确', trigger: 'blur' },
  ],
  code: [{ required: true, message: '请输入验证码', trigger: 'blur' }],
}

// Shared captcha state
const showCaptchaDialog = ref(false)
const captchaId = ref('')
const captchaBg = ref('')
const captchaSliderImg = ref('')
const captchaY = ref(0)
const puzzleWidth = ref(50)
let currentCaptchaTarget = 'sms'

const smsCaptchaVerified = ref(false)
const smsCaptchaX = ref(0)
const smsLoading = ref(false)
const smsCountdown = ref(0)
let smsTimer = null

// Reset password state
const showResetPassword = ref(false)
const resetFormRef = ref(null)
const resetForm = ref({ email: '', code: '', password: '' })
const resetRules = {
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '邮箱格式不正确', trigger: 'blur' },
  ],
  code: [{ required: true, message: '请输入验证码', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, message: '密码至少6位', trigger: 'blur' },
  ],
}
const resetLoading = ref(false)
const resetCodeLoading = ref(false)
const resetCountdown = ref(0)
const resetCaptchaVerified = ref(false)
const resetCaptchaX = ref(0)
let resetTimer = null

async function refreshCaptcha() {
  try {
    const { data } = await captcha.generate()
    captchaId.value = data.captcha_id
    captchaBg.value = data.bg_image
    captchaSliderImg.value = data.slider_image
    captchaY.value = data.y_position
    puzzleWidth.value = data.puzzle_width
  } catch {
    message.error('获取验证码失败')
  }
}

function onCodeFocus(target) {
  const verified = target === 'sms' ? smsCaptchaVerified.value : resetCaptchaVerified.value
  if (!verified) {
    currentCaptchaTarget = target
    showCaptchaDialog.value = true
    refreshCaptcha()
  }
}

function onCaptchaVerified(payload) {
  if (currentCaptchaTarget === 'sms') {
    smsCaptchaVerified.value = true
    smsCaptchaX.value = payload.x_position
  } else {
    resetCaptchaVerified.value = true
    resetCaptchaX.value = payload.x_position
  }
  showCaptchaDialog.value = false
  message.success('图形验证通过')
}

async function sendSms() {
  if (!smsCaptchaVerified.value) {
    message.warning('请先完成图形验证')
    return
  }
  const phone = smsForm.value.phone
  if (!/^1[3-9]\d{9}$/.test(phone)) {
    message.warning('请输入正确的手机号')
    return
  }
  smsLoading.value = true
  try {
    await sendSmsCode({
      phone,
      captcha_id: captchaId.value,
      captcha_x: smsCaptchaX.value,
    })
    message.success('验证码已发送')
    smsCountdown.value = 60
    smsTimer = setInterval(() => {
      smsCountdown.value--
      if (smsCountdown.value <= 0) {
        clearInterval(smsTimer)
        smsTimer = null
      }
    }, 1000)
  } catch (err) {
    message.error(err.response?.data?.detail || '发送失败')
    smsCaptchaVerified.value = false
  } finally {
    smsLoading.value = false
  }
}

async function handlePasswordLogin() {
  loading.value = true
  try {
    const { data } = await login({ account: pwdForm.value.account, password: pwdForm.value.password, app: 'anki' })
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

async function handleSmsLogin() {
  loading.value = true
  try {
    const { data } = await loginPhone({ phone: smsForm.value.phone, code: smsForm.value.code, app: 'anki' })
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

async function sendResetCode() {
  if (!resetCaptchaVerified.value) {
    message.warning('请先完成图形验证')
    return
  }
  const email = resetForm.value.email
  if (!email) {
    message.warning('请输入邮箱')
    return
  }
  resetCodeLoading.value = true
  try {
    await sendEmailCode({
      email,
      captcha_id: captchaId.value,
      captcha_x: resetCaptchaX.value,
    })
    message.success('验证码已发送到您的邮箱')
    resetCountdown.value = 60
    resetTimer = setInterval(() => {
      resetCountdown.value--
      if (resetCountdown.value <= 0) {
        clearInterval(resetTimer)
        resetTimer = null
      }
    }, 1000)
  } catch (err) {
    message.error(err.response?.data?.detail || '发送失败')
    resetCaptchaVerified.value = false
  } finally {
    resetCodeLoading.value = false
  }
}

async function handleResetPassword() {
  resetLoading.value = true
  try {
    await resetPassword({
      email: resetForm.value.email,
      email_code: resetForm.value.code,
      new_password: resetForm.value.password,
    })
    message.success('密码重置成功，请使用新密码登录')
    showResetPassword.value = false
    resetForm.value = { email: '', code: '', password: '' }
    resetCaptchaVerified.value = false
  } catch (err) {
    message.error(err.response?.data?.detail || '重置失败')
  } finally {
    resetLoading.value = false
  }
}

onMounted(() => {
  refreshCaptcha()
})

onUnmounted(() => {
  if (smsTimer) clearInterval(smsTimer)
  if (resetTimer) clearInterval(resetTimer)
})
</script>

<style scoped>
.login-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  background: #f5f5f5;
  padding: 20px;
}
.login-card {
  width: 420px;
}
</style>
