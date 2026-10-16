<template>
  <div class="register-container">
    <n-card title="注册" class="register-card">
      <n-tabs v-model:value="tab" type="segment" animated>
        <n-tab-pane name="email" tab="邮箱注册">
          <n-form ref="emailFormRef" :model="emailForm" :rules="emailRules" @submit.prevent="handleEmailRegister">
            <n-form-item label="邮箱" path="email">
              <n-input v-model:value="emailForm.email" placeholder="请输入邮箱" />
            </n-form-item>

            <n-form-item label="邮箱验证码" path="code">
              <n-input-group>
                <div style="flex: 1" @click="onCodeFocus('email')">
                  <n-input v-model:value="emailForm.code" placeholder="请输入验证码" maxlength="6" />
                </div>
                <n-button :disabled="emailCountdown > 0 || !emailCaptchaVerified || !emailForm.email" :loading="emailCodeLoading" @click="sendEmailCodeHandler">
                  {{ emailCountdown > 0 ? `${emailCountdown}秒后重发` : '获取验证码' }}
                </n-button>
              </n-input-group>
            </n-form-item>

            <n-form-item label="密码" path="password">
              <n-input v-model:value="emailForm.password" type="password" placeholder="请输入密码（至少6位）" show-password-on="click" />
            </n-form-item>
            <n-form-item label="确认密码" path="confirmPassword">
              <n-input v-model:value="emailForm.confirmPassword" type="password" placeholder="请再次输入密码" show-password-on="click" />
            </n-form-item>
            <n-space vertical>
              <n-button type="primary" block :loading="loading" attr-type="submit">注册</n-button>
            </n-space>
          </n-form>
        </n-tab-pane>

        <n-tab-pane name="phone" tab="手机号注册">
          <n-form ref="phoneFormRef" :model="phoneForm" :rules="phoneRules" @submit.prevent="handlePhoneRegister">
            <n-form-item label="手机号" path="phone">
              <n-input v-model:value="phoneForm.phone" placeholder="请输入11位手机号" maxlength="11" />
            </n-form-item>

            <n-form-item label="短信验证码" path="code">
              <n-input-group>
                <div style="flex: 1" @click="onCodeFocus('phone')">
                  <n-input v-model:value="phoneForm.code" placeholder="请输入验证码" maxlength="6" />
                </div>
                <n-button :disabled="phoneCountdown > 0 || !phoneCaptchaVerified || !phoneForm.phone" :loading="phoneCodeLoading" @click="sendSmsHandler">
                  {{ phoneCountdown > 0 ? `${phoneCountdown}秒后重发` : '获取验证码' }}
                </n-button>
              </n-input-group>
            </n-form-item>

            <n-form-item label="密码" path="password">
              <n-input v-model:value="phoneForm.password" type="password" placeholder="请输入密码（至少6位）" show-password-on="click" />
            </n-form-item>
            <n-form-item label="确认密码" path="confirmPassword">
              <n-input v-model:value="phoneForm.confirmPassword" type="password" placeholder="请再次输入密码" show-password-on="click" />
            </n-form-item>
            <n-space vertical>
              <n-button type="primary" block :loading="loading" attr-type="submit">注册</n-button>
            </n-space>
          </n-form>
        </n-tab-pane>
      </n-tabs>

      <n-divider />
      <n-button text block @click="$router.push('/login')">已有账号？立即登录</n-button>
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
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { register, registerPhone, sendSmsCode, sendEmailCode, captcha } from '../api/auth'
import { useAuthStore } from '../stores/auth'
import CaptchaSliderDialog from '../components/CaptchaSliderDialog.vue'

const router = useRouter()
const message = useMessage()
const authStore = useAuthStore()

const tab = ref('email')
const loading = ref(false)

// Shared captcha state
const showCaptchaDialog = ref(false)
const captchaId = ref('')
const captchaBg = ref('')
const captchaSliderImg = ref('')
const captchaY = ref(0)
const puzzleWidth = ref(50)
let currentCaptchaTarget = 'email'

// Email tab
const emailFormRef = ref(null)
const emailForm = ref({ email: '', code: '', password: '', confirmPassword: '' })
const emailRules = {
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '邮箱格式不正确', trigger: 'blur' },
  ],
  code: [{ required: true, message: '请输入验证码', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少6位', trigger: 'blur' },
  ],
  confirmPassword: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    {
      validator: (rule, value) => value === emailForm.value.password,
      message: '两次密码不一致',
      trigger: 'blur',
    },
  ],
}
const emailCaptchaVerified = ref(false)
const emailCaptchaX = ref(0)
const emailCodeLoading = ref(false)
const emailCountdown = ref(0)
let emailTimer = null

// Phone tab
const phoneFormRef = ref(null)
const phoneForm = ref({ phone: '', code: '', password: '', confirmPassword: '' })
const phoneRules = {
  phone: [
    { required: true, message: '请输入手机号', trigger: 'blur' },
    { pattern: /^1[3-9]\d{9}$/, message: '手机号格式不正确', trigger: 'blur' },
  ],
  code: [{ required: true, message: '请输入验证码', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少6位', trigger: 'blur' },
  ],
  confirmPassword: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    {
      validator: (rule, value) => value === phoneForm.value.password,
      message: '两次密码不一致',
      trigger: 'blur',
    },
  ],
}
const phoneCaptchaVerified = ref(false)
const phoneCaptchaX = ref(0)
const phoneCodeLoading = ref(false)
const phoneCountdown = ref(0)
let phoneTimer = null

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
  const verified = target === 'email' ? emailCaptchaVerified.value : phoneCaptchaVerified.value
  if (!verified) {
    currentCaptchaTarget = target
    showCaptchaDialog.value = true
    refreshCaptcha()
  }
}

function onCaptchaVerified(payload) {
  if (currentCaptchaTarget === 'email') {
    emailCaptchaVerified.value = true
    emailCaptchaX.value = payload.x_position
  } else {
    phoneCaptchaVerified.value = true
    phoneCaptchaX.value = payload.x_position
  }
  showCaptchaDialog.value = false
  message.success('图形验证通过')
}

async function sendEmailCodeHandler() {
  if (!emailCaptchaVerified.value) {
    message.warning('请先完成图形验证')
    return
  }
  const email = emailForm.value.email
  if (!email) {
    message.warning('请输入邮箱')
    return
  }
  emailCodeLoading.value = true
  try {
    await sendEmailCode({
      email,
      captcha_id: captchaId.value,
      captcha_x: emailCaptchaX.value,
    })
    message.success('验证码已发送到您的邮箱')
    emailCountdown.value = 60
    emailTimer = setInterval(() => {
      emailCountdown.value--
      if (emailCountdown.value <= 0) {
        clearInterval(emailTimer)
        emailTimer = null
      }
    }, 1000)
  } catch (err) {
    message.error(err.response?.data?.detail || '发送失败')
    emailCaptchaVerified.value = false
  } finally {
    emailCodeLoading.value = false
  }
}

async function sendSmsHandler() {
  if (!phoneCaptchaVerified.value) {
    message.warning('请先完成图形验证')
    return
  }
  const phone = phoneForm.value.phone
  if (!/^1[3-9]\d{9}$/.test(phone)) {
    message.warning('请输入正确的手机号')
    return
  }
  phoneCodeLoading.value = true
  try {
    await sendSmsCode({
      phone,
      captcha_id: captchaId.value,
      captcha_x: phoneCaptchaX.value,
    })
    message.success('验证码已发送')
    phoneCountdown.value = 60
    phoneTimer = setInterval(() => {
      phoneCountdown.value--
      if (phoneCountdown.value <= 0) {
        clearInterval(phoneTimer)
        phoneTimer = null
      }
    }, 1000)
  } catch (err) {
    message.error(err.response?.data?.detail || '发送失败')
    phoneCaptchaVerified.value = false
  } finally {
    phoneCodeLoading.value = false
  }
}

async function handleEmailRegister() {
  loading.value = true
  try {
    const { data } = await register({
      email: emailForm.value.email,
      email_code: emailForm.value.code,
      password: emailForm.value.password,
      app: 'anki',
    })
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

async function handlePhoneRegister() {
  loading.value = true
  try {
    const { data } = await registerPhone({
      phone: phoneForm.value.phone,
      code: phoneForm.value.code,
      password: phoneForm.value.password,
      app: 'anki',
    })
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

onMounted(() => {
  refreshCaptcha()
})

onUnmounted(() => {
  if (emailTimer) clearInterval(emailTimer)
  if (phoneTimer) clearInterval(phoneTimer)
})
</script>

<style scoped>
.register-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  background: #f5f5f5;
  padding: 20px;
}
.register-card {
  width: 420px;
}
</style>
