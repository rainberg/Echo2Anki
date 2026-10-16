<template>
  <div class="billing-container">
    <n-grid :cols="{ xs: 1, s: 2, m: 3 }" :xgap="16" :ygap="16">
      <n-gi>
        <n-card title="当前余额" size="small">
          <n-statistic :value="balance ?? '-'" label="积分" />
        </n-card>
      </n-gi>
      <n-gi>
        <n-card title="累计使用" size="small">
          <n-statistic :value="totalUsed" label="积分" />
        </n-card>
      </n-gi>
      <n-gi>
        <n-card title="充值系数" size="small">
          <n-statistic :value="coefficient" label="元 → 积分" />
        </n-card>
      </n-gi>
    </n-grid>

    <n-card title="充值" size="small" style="margin-top: 16px">
      <n-grid :cols="{ xs: 1, m: 2 }" :xgap="24">
        <n-gi>
          <div class="qr-section">
            <div class="qr-title">扫描收款码付款</div>
            <div v-if="qrLoading" style="text-align: center; padding: 40px 0">
              <n-spin size="large" />
            </div>
            <div v-else-if="qrUrl" class="qr-image-wrap">
              <img :src="qrUrl" alt="收款码" class="qr-image" />
            </div>
            <n-empty v-else description="管理员暂未上传收款码" style="padding: 40px 0" />
          </div>
        </n-gi>
        <n-gi>
          <n-form label-placement="left" label-width="80" style="margin-top: 8px">
            <n-form-item label="充值金额">
              <n-input-number v-model:value="rechargeAmount" :min="1" :step="10" style="width: 100%">
                <template #suffix>元</template>
              </n-input-number>
            </n-form-item>
            <n-form-item label="可得积分">
              <n-text type="success" style="font-size: 18px; font-weight: bold">
                {{ rechargeAmount * coefficient }} 积分
              </n-text>
            </n-form-item>
            <n-form-item label="付款截图">
              <n-upload
                :max="1"
                accept="image/*"
                :default-upload="false"
                @change="handleProofChange"
              >
                <n-button>选择图片</n-button>
              </n-upload>
              <div v-if="proofPreview" style="margin-top: 8px">
                <img :src="proofPreview" alt="预览" style="max-width: 200px; max-height: 150px; border-radius: 4px" />
              </div>
            </n-form-item>
            <n-form-item>
              <n-button type="primary" :loading="submitting" :disabled="!canSubmit" @click="handleSubmit">
                提交充值申请
              </n-button>
            </n-form-item>
          </n-form>
          <n-alert v-if="pendingRequest" type="warning" style="margin-top: 8px">
            您有一笔待审核的充值申请（{{ pendingRequest.amount }}元 → {{ pendingRequest.credits_amount }}积分），请等待管理员处理。
          </n-alert>
        </n-gi>
      </n-grid>
    </n-card>

    <n-card title="引擎定价" size="small" style="margin-top: 16px">
      <n-table :bordered="false" :single-line="false" size="small">
        <thead>
          <tr><th>引擎</th><th>模型</th><th>单价（积分/分钟）</th></tr>
        </thead>
        <tbody>
          <tr v-for="e in engines" :key="e.engine_key + e.model_sizes?.join()">
            <td>{{ e.engine_name }}</td>
            <td>{{ e.model_sizes?.join(', ') || '-' }}</td>
            <td>{{ e.credits_per_minute }}</td>
          </tr>
        </tbody>
      </n-table>
    </n-card>

    <n-card title="充值记录" size="small" style="margin-top: 16px">
      <n-spin :show="requestsLoading">
        <n-list bordered v-if="rechargeRequests.length">
          <n-list-item v-for="r in rechargeRequests" :key="r.id">
            <n-thing>
              <template #header>
                <n-tag :type="statusTagType(r.status)" size="small">{{ statusLabel(r.status) }}</n-tag>
                <n-text style="margin-left: 8px">{{ r.amount }}元 → {{ r.credits_amount }}积分</n-text>
              </template>
              <template #description>
                <n-text v-if="r.admin_note" depth="3" style="font-size: 13px">管理员备注: {{ r.admin_note }}</n-text>
              </template>
              <template #header-extra>
                <n-text depth="3" style="font-size: 12px">{{ formatDate(r.created_at) }}</n-text>
              </template>
            </n-thing>
          </n-list-item>
        </n-list>
        <n-empty v-else description="暂无充值记录" />
      </n-spin>
      <n-flex v-if="requestsTotal > requestsPerPage" justify="center" style="margin-top: 12px">
        <n-pagination v-model:page="requestsPage" :page-count="Math.ceil(requestsTotal / requestsPerPage)" @update:page="fetchRequests" />
      </n-flex>
    </n-card>

    <n-card title="交易记录" size="small" style="margin-top: 16px">
      <n-spin :show="loading">
        <n-list bordered v-if="logs.length">
          <n-list-item v-for="log in logs" :key="log.id">
            <n-thing>
              <template #header>
                <n-tag :type="actionTagType(log.action)" size="small">{{ actionLabel(log.action) }}</n-tag>
                <n-text style="margin-left: 8px">{{ log.amount > 0 ? '+' : '' }}{{ log.amount }} 积分</n-text>
              </template>
              <template #description>
                <n-text depth="3" style="font-size: 13px">{{ log.description }}</n-text>
              </template>
              <template #header-extra>
                <n-text depth="3" style="font-size: 12px">{{ formatDate(log.created_at) }}</n-text>
              </template>
            </n-thing>
          </n-list-item>
        </n-list>
        <n-empty v-else description="暂无交易记录" />
      </n-spin>
      <n-flex v-if="logTotal > logPerPage" justify="center" style="margin-top: 12px">
        <n-pagination v-model:page="logPage" :page-count="Math.ceil(logTotal / logPerPage)" @update:page="fetchLogs" />
      </n-flex>
    </n-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useMessage } from 'naive-ui'
import { getCreditsBalance, getCreditsLogs } from '../api/auth'
import { getEngines } from '../api/system'
import { getRechargeInfo, getPaymentQR, submitRecharge, getMyRequests } from '../api/recharge'

const route = useRoute()
const message = useMessage()

const balance = ref(null)
const totalUsed = ref(0)
const coefficient = ref(10)
const logs = ref([])
const engines = ref([])
const loading = ref(false)
const logPage = ref(1)
const logTotal = ref(0)
const logPerPage = ref(20)

// Recharge state
const qrUrl = ref(null)
const qrLoading = ref(false)
const rechargeAmount = ref(10)
const proofFile = ref(null)
const proofPreview = ref(null)
const submitting = ref(false)
const pendingRequest = ref(null)

const rechargeRequests = ref([])
const requestsLoading = ref(false)
const requestsPage = ref(1)
const requestsTotal = ref(0)
const requestsPerPage = ref(20)

const canSubmit = computed(() => rechargeAmount.value > 0 && proofFile.value && !pendingRequest.value)

function actionLabel(action) {
  const map = { topup: '充值', reserve: '预扣', settle: '结算', refund: '退还', charge: '扣费' }
  return map[action] || action
}

function actionTagType(action) {
  const map = { topup: 'success', reserve: 'warning', settle: 'error', refund: 'info', charge: 'error' }
  return map[action] || 'default'
}

function statusLabel(status) {
  const map = { pending: '待审核', approved: '已通过', rejected: '已拒绝' }
  return map[status] || status
}

function statusTagType(status) {
  const map = { pending: 'warning', approved: 'success', rejected: 'error' }
  return map[status] || 'default'
}

function formatDate(dt) {
  return dt ? new Date(dt).toLocaleString('zh-CN') : ''
}

function handleProofChange({ file }) {
  if (file?.file) {
    proofFile.value = file.file
    const reader = new FileReader()
    reader.onload = (e) => { proofPreview.value = e.target.result }
    reader.readAsDataURL(file.file)
  } else {
    proofFile.value = null
    proofPreview.value = null
  }
}

async function fetchBalance() {
  try {
    const { data } = await getCreditsBalance()
    balance.value = data.credits ?? data.balance
    totalUsed.value = data.total_used ?? 0
  } catch {}
}

async function fetchLogs() {
  loading.value = true
  try {
    const { data } = await getCreditsLogs({ page: logPage.value, per_page: logPerPage.value })
    logs.value = data.items ?? data.logs ?? []
    logTotal.value = data.total ?? 0
  } catch {
    message.error('获取记录失败')
  } finally {
    loading.value = false
  }
}

async function fetchEngines() {
  try {
    const { data } = await getEngines()
    engines.value = data
  } catch {}
}

async function fetchQR() {
  qrLoading.value = true
  try {
    const { data } = await getPaymentQR()
    qrUrl.value = URL.createObjectURL(data)
  } catch {
    qrUrl.value = null
  } finally {
    qrLoading.value = false
  }
}

async function fetchRechargeInfo() {
  try {
    const { data } = await getRechargeInfo()
    coefficient.value = data.coefficient ?? 10
  } catch {}
}

async function fetchRequests() {
  requestsLoading.value = true
  try {
    const { data } = await getMyRequests({ page: requestsPage.value, per_page: requestsPerPage.value })
    rechargeRequests.value = data.items ?? []
    requestsTotal.value = data.total ?? 0
    // Check for pending request
    pendingRequest.value = rechargeRequests.value.find(r => r.status === 'pending') || null
  } catch {
    message.error('获取充值记录失败')
  } finally {
    requestsLoading.value = false
  }
}

async function handleSubmit() {
  if (!canSubmit.value) return
  submitting.value = true
  try {
    const formData = new FormData()
    formData.append('amount', rechargeAmount.value)
    formData.append('payment_image', proofFile.value)
    await submitRecharge(formData)
    message.success('充值申请已提交，请等待管理员审核')
    proofFile.value = null
    proofPreview.value = null
    fetchRequests()
    fetchBalance()
  } catch (e) {
    const detail = e.response?.data?.detail || '提交失败'
    message.error(detail)
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  fetchBalance()
  fetchLogs()
  fetchEngines()
  fetchQR()
  fetchRechargeInfo()
  fetchRequests()
})
</script>

<style scoped>
.billing-container {
  max-width: 900px;
  margin: 0 auto;
}
.qr-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 16px 0;
}
.qr-title {
  font-size: 15px;
  font-weight: 500;
  margin-bottom: 12px;
  color: var(--n-text-color);
}
.qr-image-wrap {
  border: 1px solid var(--n-border-color);
  border-radius: 8px;
  padding: 8px;
  background: #fff;
}
.qr-image {
  max-width: 240px;
  max-height: 240px;
  display: block;
}
</style>
