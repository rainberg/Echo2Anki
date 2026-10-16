<template>
  <div class="admin-container">
    <n-page-header @back="$router.push('/')" title="管理员面板" style="margin-bottom: 16px" />

    <n-tabs type="line" animated>
      <!-- 用户管理 -->
      <n-tab-pane name="users" tab="用户管理">
        <n-space style="margin-bottom: 12px">
          <n-input v-model:value="searchQuery" placeholder="搜索邮箱..." size="small" style="width: 300px" clearable @keyup.enter="fetchUsers" />
          <n-button size="small" type="primary" @click="fetchUsers">搜索</n-button>
        </n-space>

        <n-data-table :columns="userColumns" :data="users" :loading="usersLoading" :bordered="false" size="small"
          :pagination="{ pageSize: 20 }" />

        <n-space style="margin-top: 12px" justify="center">
          <n-pagination v-model:page="userPage" :page-count="userPageCount" size="small" @update:page="fetchUsers" />
        </n-space>
      </n-tab-pane>

      <!-- 收款码管理 -->
      <n-tab-pane name="qrcode" tab="收款码管理">
        <n-space vertical align="center" style="padding: 20px 0">
          <n-upload
            :max="1"
            accept="image/*"
            :default-upload="false"
            @change="handleQRChange"
          >
            <n-button type="primary">上传收款码</n-button>
          </n-upload>
          <div v-if="currentQRUrl" class="qr-preview">
            <div style="margin-bottom: 8px; color: var(--n-text-color-3); font-size: 13px">当前收款码</div>
            <img :src="currentQRUrl" alt="收款码" style="max-width: 300px; max-height: 300px; border-radius: 8px; border: 1px solid var(--n-border-color)" />
          </div>
          <n-empty v-else description="暂未上传收款码" />
        </n-space>
      </n-tab-pane>

      <!-- 充值审核 -->
      <n-tab-pane name="recharge" tab="充值审核">
        <n-space style="margin-bottom: 12px" align="center">
          <n-select
            v-model:value="rechargeStatusFilter"
            :options="statusFilterOptions"
            size="small"
            style="width: 140px"
            @update:value="fetchRechargeRequests"
          />
        </n-space>

        <n-data-table :columns="rechargeColumns" :data="rechargeRequests" :loading="rechargeLoading" :bordered="false" size="small"
          :pagination="{ pageSize: 20 }" />

        <n-space style="margin-top: 12px" justify="center">
          <n-pagination v-model:page="rechargePage" :page-count="rechargePageCount" size="small" @update:page="fetchRechargeRequests" />
        </n-space>
      </n-tab-pane>

      <!-- 引擎定价 -->
      <n-tab-pane name="pricing" tab="引擎定价">
        <n-data-table :columns="pricingColumns" :data="allEngines" :loading="pricingLoading" :bordered="false" size="small" />
      </n-tab-pane>
      <!-- 系统设置 -->
      <n-tab-pane name="settings" tab="系统设置">
        <n-spin :show="settingsLoading">
          <n-space vertical :size="16">
            <n-card size="small" title="OpenAI API Key">
              <n-space vertical :size="8">
                <n-input v-model:value="openaiKey" type="password" placeholder="sk-..." show-password-on="click" />
                <n-text depth="3" style="font-size: 12px">设置后，用户使用 OpenAI Whisper 引擎时无需自行输入 API Key</n-text>
                <n-button type="primary" size="small" :loading="savingKey" @click="handleSaveOpenAIKey">保存</n-button>
              </n-space>
            </n-card>
            <n-card size="small" title="豆包 API 设置">
              <n-space vertical :size="8">
                <n-input v-model:value="doubaoApiKey" type="password" placeholder="新版控制台 API Key（X-Api-Key）" show-password-on="click" />
                <n-input v-model:value="doubaoAppId" placeholder="旧版控制台 APP ID（X-Api-App-Key）" />
                <n-input v-model:value="doubaoAccessToken" type="password" placeholder="旧版控制台 Access Token（X-Api-Access-Key）" show-password-on="click" />
                <n-text depth="3" style="font-size: 12px">豆包录音识别引擎凭据，新旧控制台二选一：新版只填 API Key，旧版填 APP ID + Access Token。设置后豆包引擎即可使用</n-text>
                <n-button type="primary" size="small" :loading="savingDoubao" @click="handleSaveDoubao">保存</n-button>
              </n-space>
            </n-card>
          </n-space>
        </n-spin>
      </n-tab-pane>
      <!-- 帮助文档 -->
      <n-tab-pane name="help" tab="帮助文档">
        <n-space style="margin-bottom: 12px" align="center">
          <n-select v-model:value="helpCategoryFilter" :options="helpCategoryOptions" size="small" style="width: 160px" @update:value="fetchHelpArticles" />
          <n-button size="small" type="primary" @click="openHelpCreate">新增文章</n-button>
        </n-space>
        <n-data-table :columns="helpColumns" :data="helpArticles" :loading="helpLoading" :bordered="false" size="small" />
      </n-tab-pane>
    </n-tabs>

    <!-- 用户充值弹窗 -->
    <n-modal v-model:show="topupModalVisible" preset="dialog" title="充值" positive-text="确认" negative-text="取消"
      @positive-click="handleTopup">
      <n-form label-placement="left" label-width="80">
        <n-form-item label="用户">
          <n-text>{{ topupTarget?.email || topupTarget?.phone }}</n-text>
        </n-form-item>
        <n-form-item label="当前余额">
          <n-text>{{ topupTarget?.credits }} 积分</n-text>
        </n-form-item>
        <n-form-item label="充值金额">
          <n-input-number v-model:value="topupAmount" :min="0.01" :step="10" style="width: 200px" />
          <n-text style="margin-left: 8px">积分</n-text>
        </n-form-item>
        <n-form-item label="备注">
          <n-input v-model:value="topupDesc" placeholder="可选" size="small" />
        </n-form-item>
      </n-form>
    </n-modal>

    <!-- 用户引擎弹窗 -->
    <n-modal v-model:show="enginesModalVisible" preset="dialog" title="设置可用引擎" positive-text="确认" negative-text="取消"
      @positive-click="handleUpdateEngines">
      <n-checkbox-group v-model:value="editEngines">
        <n-space vertical>
          <n-checkbox value="local_whisper">Local Whisper</n-checkbox>
          <n-checkbox value="openai_whisper">OpenAI Whisper</n-checkbox>
          <n-checkbox value="cohere">Cohere</n-checkbox>
        </n-space>
      </n-checkbox-group>
    </n-modal>

    <!-- 配置上限弹窗 -->
    <n-modal v-model:show="configLimitModalVisible" preset="dialog" title="推送配置上限" positive-text="确认" negative-text="取消"
      @positive-click="handleSaveConfigLimit">
      <n-form label-placement="left" label-width="80">
        <n-form-item label="用户">
          <n-text>{{ configLimitTarget?.email }}</n-text>
        </n-form-item>
        <n-form-item label="配置上限">
          <n-input-number v-model:value="configLimitValue" :min="1" :max="50" style="width: 200px" />
          <n-text style="margin-left: 8px">个</n-text>
        </n-form-item>
      </n-form>
    </n-modal>

    <!-- 充值审核弹窗 -->
    <n-modal v-model:show="reviewModalVisible" preset="dialog" :title="reviewAction === 'approved' ? '通过充值' : '拒绝充值'"
      positive-text="确认" negative-text="取消" @positive-click="handleReview">
      <n-descriptions label-placement="left" :column="1" bordered size="small" style="margin-bottom: 12px">
        <n-descriptions-item label="用户">{{ reviewTarget?.user_email }}</n-descriptions-item>
        <n-descriptions-item label="金额">{{ reviewTarget?.amount }}元 → {{ reviewTarget?.credits_amount }}积分</n-descriptions-item>
        <n-descriptions-item label="提交时间">{{ formatDate(reviewTarget?.created_at) }}</n-descriptions-item>
      </n-descriptions>
      <div v-if="reviewTarget?.payment_image" style="margin-bottom: 12px; text-align: center">
        <img :src="proofUrl(reviewTarget.payment_image)" alt="付款凭证" style="max-width: 300px; max-height: 300px; border-radius: 4px; border: 1px solid var(--n-border-color)" />
      </div>
      <n-form-item label="管理员备注">
        <n-input v-model:value="reviewNote" placeholder="可选" size="small" />
      </n-form-item>
    </n-modal>

    <!-- 引擎编辑弹窗 -->
    <n-modal v-model:show="engineEditVisible" preset="dialog" title="编辑引擎" positive-text="保存" negative-text="取消"
      @positive-click="handleSaveEngine">
      <n-form label-placement="left" label-width="100">
        <n-form-item label="引擎名称">
          <n-input v-model:value="engineEdit.engine_name" size="small" />
        </n-form-item>
        <n-form-item label="单价(积分/分钟)">
          <n-input-number v-model:value="engineEdit.credits_per_minute" :min="0" :step="0.1" size="small" style="width: 200px" />
        </n-form-item>
        <n-form-item label="启用">
          <n-switch v-model:value="engineEdit.is_active" />
        </n-form-item>
        <n-form-item label="排序">
          <n-input-number v-model:value="engineEdit.sort_order" :min="0" size="small" style="width: 200px" />
        </n-form-item>
        <n-form-item label="描述">
          <n-input v-model:value="engineEdit.description" type="textarea" size="small" placeholder="可选" />
        </n-form-item>
      </n-form>
    </n-modal>

    <!-- 帮助文章编辑弹窗 -->
    <n-modal v-model:show="helpEditVisible" preset="dialog" :title="helpEditIsNew ? '新增帮助文章' : '编辑帮助文章'" positive-text="保存" negative-text="取消"
      style="width: 800px" @positive-click="handleSaveHelpArticle">
      <n-form label-placement="left" label-width="80">
        <n-form-item label="Slug">
          <n-input v-model:value="helpEdit.slug" size="small" placeholder="如 anki-push-guide" :disabled="!helpEditIsNew" />
        </n-form-item>
        <n-form-item label="标题">
          <n-input v-model:value="helpEdit.title" size="small" />
        </n-form-item>
        <n-form-item label="分类">
          <n-select v-model:value="helpEdit.category" :options="helpCategoryOptions.filter(o => o.value)" size="small" />
        </n-form-item>
        <n-form-item label="排序">
          <n-input-number v-model:value="helpEdit.sort_order" :min="0" size="small" style="width: 200px" />
        </n-form-item>
        <n-form-item label="发布">
          <n-switch v-model:value="helpEdit.is_published" />
        </n-form-item>
        <n-form-item label="内容">
          <div style="display: flex; gap: 12px; width: 100%">
            <n-input v-model:value="helpEdit.content" type="textarea" size="small" placeholder="Markdown 格式" :rows="16" style="flex: 1" />
            <div class="markdown-body" style="flex: 1; border: 1px solid var(--n-border-color); border-radius: 4px; padding: 12px; overflow-y: auto; max-height: 400px; font-size: 13px" v-html="helpEditPreview"></div>
          </div>
        </n-form-item>
      </n-form>
    </n-modal>
  </div>
</template>

<script setup>
import { ref, h, onMounted, computed } from 'vue'
import { useMessage, NButton, NTag, NSpace, NImage } from 'naive-ui'
import { listUsers, topupUser, updateUserEngines, updateUserStatus, updateUserPushConfigLimit, adminListHelpArticles, adminCreateHelpArticle, adminUpdateHelpArticle, adminDeleteHelpArticle } from '../api/admin'
import { marked } from 'marked'
import { getAllEngines, updateEngine, getSystemSettings, updateSystemSetting } from '../api/system'
import { adminUploadQR, adminListRequests, adminReviewRequest, getProofUrl } from '../api/recharge'
import { getPaymentQR } from '../api/recharge'

const message = useMessage()

// ─── Users ───────────────────────────────────────────────────────────
const users = ref([])
const usersLoading = ref(false)
const userPage = ref(1)
const userTotal = ref(0)
const searchQuery = ref('')

const topupModalVisible = ref(false)
const topupTarget = ref(null)
const topupAmount = ref(10)
const topupDesc = ref('')

const enginesModalVisible = ref(false)
const enginesTarget = ref(null)
const editEngines = ref([])

const configLimitModalVisible = ref(false)
const configLimitTarget = ref(null)
const configLimitValue = ref(4)

const userPageCount = computed(() => Math.ceil(userTotal.value / 20))

const userColumns = [
  { title: '邮箱', key: 'email', width: 220 },
  { title: '昵称', key: 'display_name', width: 120 },
  { title: '余额', key: 'credits', width: 90, render: (row) => `${row.credits ?? '-'} 积分` },
  { title: '角色', key: 'role', width: 80, render: (row) => h(NTag, { type: row.role === 'admin' ? 'warning' : 'default', size: 'small' }, () => row.role) },
  { title: '状态', key: 'is_active', width: 80, render: (row) => h(NTag, { type: row.is_active ? 'success' : 'error', size: 'small' }, () => row.is_active ? '正常' : '禁用') },
  { title: '可用引擎', key: 'allowed_engines', width: 200, render: (row) => h(NSpace, { size: 4 }, () => (row.allowed_engines || []).map(e => h(NTag, { size: 'small', type: 'info' }, () => e))) },
  { title: '配置上限', key: 'max_push_configs', width: 80, render: (row) => `${row.max_push_configs ?? 4}` },
  { title: '注册时间', key: 'created_at', width: 160, render: (row) => new Date(row.created_at).toLocaleString('zh-CN') },
  {
    title: '操作', key: 'actions', width: 320,
    render: (row) => h(NSpace, { size: 4 }, () => [
      h(NButton, { size: 'tiny', type: 'primary', onClick: () => openTopup(row) }, () => '充值'),
      h(NButton, { size: 'tiny', type: 'info', onClick: () => openEngines(row) }, () => '引擎'),
      h(NButton, { size: 'tiny', onClick: () => openConfigLimit(row) }, () => '配置上限'),
      h(NButton, {
        size: 'tiny',
        type: row.is_active ? 'warning' : 'success',
        onClick: () => handleToggleStatus(row),
      }, () => row.is_active ? '禁用' : '启用'),
    ]),
  },
]

// ─── Recharge ────────────────────────────────────────────────────────
const rechargeRequests = ref([])
const rechargeLoading = ref(false)
const rechargePage = ref(1)
const rechargeTotal = ref(0)
const rechargeStatusFilter = ref('pending')

const reviewModalVisible = ref(false)
const reviewTarget = ref(null)
const reviewAction = ref('approved')
const reviewNote = ref('')

const currentQRUrl = ref(null)

const statusFilterOptions = [
  { label: '待审核', value: 'pending' },
  { label: '已通过', value: 'approved' },
  { label: '已拒绝', value: 'rejected' },
  { label: '全部', value: '' },
]

const rechargePageCount = computed(() => Math.ceil(rechargeTotal.value / 20))

function proofUrl(filename) {
  return getProofUrl(filename)
}

function formatDate(dt) {
  return dt ? new Date(dt).toLocaleString('zh-CN') : ''
}

function statusTagType(status) {
  const map = { pending: 'warning', approved: 'success', rejected: 'error' }
  return map[status] || 'default'
}

function statusLabel(status) {
  const map = { pending: '待审核', approved: '已通过', rejected: '已拒绝' }
  return map[status] || status
}

const rechargeColumns = [
  { title: '用户', key: 'user_email', width: 180 },
  { title: '金额', key: 'amount', width: 80, render: (row) => `${row.amount}元` },
  { title: '积分', key: 'credits_amount', width: 80, render: (row) => `${row.credits_amount}` },
  {
    title: '付款截图', key: 'payment_image', width: 100,
    render: (row) => h(NImage, {
      src: proofUrl(row.payment_image),
      width: 60,
      style: { borderRadius: '4px' },
      objectFit: 'contain',
      fallbackSrc: 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg"/>',
    }),
  },
  { title: '状态', key: 'status', width: 80, render: (row) => h(NTag, { type: statusTagType(row.status), size: 'small' }, () => statusLabel(row.status)) },
  { title: '提交时间', key: 'created_at', width: 150, render: (row) => formatDate(row.created_at) },
  { title: '管理员备注', key: 'admin_note', width: 150, ellipsis: { tooltip: true } },
  {
    title: '操作', key: 'actions', width: 160,
    render: (row) => row.status === 'pending'
      ? h(NSpace, { size: 4 }, () => [
          h(NButton, { size: 'tiny', type: 'success', onClick: () => openReview(row, 'approved') }, () => '通过'),
          h(NButton, { size: 'tiny', type: 'error', onClick: () => openReview(row, 'rejected') }, () => '拒绝'),
        ])
      : h(NText, { depth: 3, style: 'font-size: 12px' }, () => '已处理'),
  },
]

// ─── Engine Pricing ──────────────────────────────────────────────────
const allEngines = ref([])
const pricingLoading = ref(false)

const engineEditVisible = ref(false)
const engineEdit = ref({ engine_key: '', model_size: '', engine_name: '', credits_per_minute: 0, is_active: true, sort_order: 0, description: '' })

const pricingColumns = [
  { title: '引擎', key: 'engine_key', width: 140 },
  { title: '模型', key: 'model_size', width: 120 },
  { title: '名称', key: 'engine_name', width: 150 },
  { title: '单价(积分/分钟)', key: 'credits_per_minute', width: 140 },
  {
    title: '状态', key: 'is_active', width: 80,
    render: (row) => h(NTag, { type: row.is_active ? 'success' : 'error', size: 'small' }, () => row.is_active ? '启用' : '禁用'),
  },
  { title: '排序', key: 'sort_order', width: 70 },
  {
    title: '操作', key: 'actions', width: 80,
    render: (row) => h(NButton, { size: 'tiny', type: 'info', onClick: () => openEngineEdit(row) }, () => '编辑'),
  },
]

// ─── Fetch functions ─────────────────────────────────────────────────

async function fetchUsers() {
  usersLoading.value = true
  try {
    const params = { page: userPage.value, per_page: 20 }
    if (searchQuery.value) params.search = searchQuery.value
    const { data } = await listUsers(params)
    users.value = data.items ?? data.users ?? []
    userTotal.value = data.total ?? 0
  } catch {
    message.error('获取用户列表失败')
  } finally {
    usersLoading.value = false
  }
}

async function fetchRechargeRequests() {
  rechargeLoading.value = true
  try {
    const params = { page: rechargePage.value, per_page: 20 }
    if (rechargeStatusFilter.value) params.status_filter = rechargeStatusFilter.value
    const { data } = await adminListRequests(params)
    rechargeRequests.value = data.items ?? []
    rechargeTotal.value = data.total ?? 0
  } catch {
    message.error('获取充值申请失败')
  } finally {
    rechargeLoading.value = false
  }
}

async function fetchAllEngines() {
  pricingLoading.value = true
  try {
    const { data } = await getAllEngines()
    allEngines.value = data
  } catch {
    message.error('获取引擎列表失败')
  } finally {
    pricingLoading.value = false
  }
}

// ─── User actions ────────────────────────────────────────────────────

function openTopup(user) {
  topupTarget.value = user
  topupAmount.value = 10
  topupDesc.value = ''
  topupModalVisible.value = true
}

async function handleTopup() {
  try {
    await topupUser(topupTarget.value.id, { amount: topupAmount.value, description: topupDesc.value || undefined })
    message.success('充值成功')
    fetchUsers()
  } catch {
    message.error('充值失败')
  }
}

function openEngines(user) {
  enginesTarget.value = user
  editEngines.value = [...(user.allowed_engines || [])]
  enginesModalVisible.value = true
}

async function handleUpdateEngines() {
  try {
    await updateUserEngines(enginesTarget.value.id, { allowed_engines: editEngines.value })
    message.success('引擎更新成功')
    fetchUsers()
  } catch {
    message.error('更新引擎失败')
  }
}

async function handleToggleStatus(user) {
  try {
    await updateUserStatus(user.id)
    message.success(user.is_active ? '已禁用' : '已启用')
    fetchUsers()
  } catch {
    message.error('操作失败')
  }
}

function openConfigLimit(user) {
  configLimitTarget.value = user
  configLimitValue.value = user.max_push_configs ?? 4
  configLimitModalVisible.value = true
}

async function handleSaveConfigLimit() {
  try {
    await updateUserPushConfigLimit(configLimitTarget.value.id, { max_push_configs: configLimitValue.value })
    message.success('配置上限已更新')
    fetchUsers()
  } catch {
    message.error('更新配置上限失败')
  }
}

// ─── Recharge actions ────────────────────────────────────────────────

async function handleQRChange({ file }) {
  if (!file?.file) return
  try {
    const formData = new FormData()
    formData.append('qr_image', file.file)
    await adminUploadQR(formData)
    message.success('收款码已上传')
    fetchQR()
  } catch {
    message.error('上传收款码失败')
  }
}

async function fetchQR() {
  try {
    const { data } = await getPaymentQR()
    currentQRUrl.value = URL.createObjectURL(data)
  } catch {
    currentQRUrl.value = null
  }
}

function openReview(request, action) {
  reviewTarget.value = request
  reviewAction.value = action
  reviewNote.value = ''
  reviewModalVisible.value = true
}

async function handleReview() {
  try {
    await adminReviewRequest(reviewTarget.value.id, {
      action: reviewAction.value,
      admin_note: reviewNote.value,
    })
    message.success(reviewAction.value === 'approved' ? '已通过' : '已拒绝')
    fetchRechargeRequests()
  } catch (e) {
    const detail = e.response?.data?.detail || '操作失败'
    message.error(detail)
  }
}

// ─── Engine pricing actions ──────────────────────────────────────────

function openEngineEdit(engine) {
  engineEdit.value = {
    engine_key: engine.engine_key,
    model_size: engine.model_size,
    engine_name: engine.engine_name || '',
    credits_per_minute: engine.credits_per_minute ?? 0,
    is_active: engine.is_active ?? true,
    sort_order: engine.sort_order ?? 0,
    description: engine.description || '',
  }
  engineEditVisible.value = true
}

async function handleSaveEngine() {
  try {
    await updateEngine(engineEdit.value.engine_key, engineEdit.value.model_size, {
      engine_name: engineEdit.value.engine_name,
      credits_per_minute: engineEdit.value.credits_per_minute,
      is_active: engineEdit.value.is_active,
      sort_order: engineEdit.value.sort_order,
      description: engineEdit.value.description,
    })
    message.success('引擎更新成功')
    fetchAllEngines()
  } catch {
    message.error('更新引擎失败')
  }
}

// ─── Help Articles ───────────────────────────────────────────────────

const helpArticles = ref([])
const helpLoading = ref(false)
const helpCategoryFilter = ref(null)
const helpEditVisible = ref(false)
const helpEditIsNew = ref(true)
const helpEdit = ref({ id: null, slug: '', title: '', content: '', category: 'tasks', sort_order: 0, is_published: false })

const helpCategoryOptions = [
  { label: '全部', value: null },
  { label: '任务与音频处理', value: 'tasks' },
  { label: '收藏与公共库', value: 'collections' },
  { label: 'Anki 推送', value: 'anki' },
]

const helpEditPreview = computed(() => {
  if (!helpEdit.value.content) return ''
  return marked(helpEdit.value.content)
})

const helpColumns = [
  { title: '标题', key: 'title', width: 200 },
  { title: 'Slug', key: 'slug', width: 160 },
  { title: '分类', key: 'category', width: 130, render: (row) => {
    const map = { tasks: '任务与音频处理', collections: '收藏与公共库', anki: 'Anki 推送' }
    return map[row.category] || row.category
  }},
  { title: '排序', key: 'sort_order', width: 70 },
  { title: '状态', key: 'is_published', width: 80, render: (row) => h(NTag, { type: row.is_published ? 'success' : 'warning', size: 'small' }, () => row.is_published ? '已发布' : '草稿') },
  { title: '更新时间', key: 'updated_at', width: 160, render: (row) => formatDate(row.updated_at) },
  {
    title: '操作', key: 'actions', width: 160,
    render: (row) => h(NSpace, { size: 4 }, () => [
      h(NButton, { size: 'tiny', type: 'info', onClick: () => openHelpEdit(row) }, () => '编辑'),
      h(NButton, { size: 'tiny', type: 'error', onClick: () => handleDeleteHelpArticle(row) }, () => '删除'),
    ]),
  },
]

async function fetchHelpArticles() {
  helpLoading.value = true
  try {
    const params = {}
    if (helpCategoryFilter.value) params.category = helpCategoryFilter.value
    const { data } = await adminListHelpArticles(params)
    helpArticles.value = data
  } catch {
    message.error('获取帮助文章失败')
  } finally {
    helpLoading.value = false
  }
}

function openHelpCreate() {
  helpEditIsNew.value = true
  helpEdit.value = { id: null, slug: '', title: '', content: '', category: 'tasks', sort_order: 0, is_published: false }
  helpEditVisible.value = true
}

function openHelpEdit(article) {
  helpEditIsNew.value = false
  helpEdit.value = { ...article }
  helpEditVisible.value = true
}

async function handleSaveHelpArticle() {
  try {
    if (helpEditIsNew.value) {
      await adminCreateHelpArticle({
        slug: helpEdit.value.slug,
        title: helpEdit.value.title,
        content: helpEdit.value.content,
        category: helpEdit.value.category,
        sort_order: helpEdit.value.sort_order,
        is_published: helpEdit.value.is_published,
      })
      message.success('文章已创建')
    } else {
      await adminUpdateHelpArticle(helpEdit.value.id, {
        title: helpEdit.value.title,
        content: helpEdit.value.content,
        category: helpEdit.value.category,
        sort_order: helpEdit.value.sort_order,
        is_published: helpEdit.value.is_published,
      })
      message.success('文章已更新')
    }
    fetchHelpArticles()
  } catch (e) {
    const detail = e.response?.data?.detail || '操作失败'
    message.error(detail)
  }
}

async function handleDeleteHelpArticle(article) {
  if (!confirm(`确定删除「${article.title}」？`)) return
  try {
    await adminDeleteHelpArticle(article.id)
    message.success('已删除')
    fetchHelpArticles()
  } catch {
    message.error('删除失败')
  }
}

// ─── System Settings ─────────────────────────────────────────────────

const settingsLoading = ref(false)
const openaiKey = ref('')
const savingKey = ref(false)
const doubaoApiKey = ref('')
const doubaoAppId = ref('')
const doubaoAccessToken = ref('')
const savingDoubao = ref(false)

async function fetchSettings() {
  settingsLoading.value = true
  try {
    const { data } = await getSystemSettings()
    openaiKey.value = data.openai_api_key || ''
    doubaoApiKey.value = data.doubao_api_key || ''
    doubaoAppId.value = data.doubao_app_id || ''
    doubaoAccessToken.value = data.doubao_access_token || ''
  } catch {
    message.error('获取系统设置失败')
  } finally {
    settingsLoading.value = false
  }
}

async function handleSaveOpenAIKey() {
  savingKey.value = true
  try {
    await updateSystemSetting('openai_api_key', openaiKey.value)
    message.success('OpenAI API Key 已保存')
  } catch {
    message.error('保存失败')
  } finally {
    savingKey.value = false
  }
}

async function handleSaveDoubao() {
  savingDoubao.value = true
  try {
    await updateSystemSetting('doubao_api_key', doubaoApiKey.value)
    await updateSystemSetting('doubao_app_id', doubaoAppId.value)
    await updateSystemSetting('doubao_access_token', doubaoAccessToken.value)
    message.success('豆包 API 设置已保存')
  } catch {
    message.error('保存失败')
  } finally {
    savingDoubao.value = false
  }
}

// ─── Init ────────────────────────────────────────────────────────────

onMounted(() => {
  fetchUsers()
  fetchRechargeRequests()
  fetchAllEngines()
  fetchQR()
  fetchHelpArticles()
  fetchSettings()
})
</script>

<style scoped>
.admin-container {
  max-width: 1100px;
  margin: 0 auto;
}

.markdown-body {
  font-size: 13px;
  line-height: 1.6;
}
.markdown-body :deep(h1) { font-size: 1.4em; margin: 0.8em 0 0.4em; }
.markdown-body :deep(h2) { font-size: 1.2em; margin: 0.6em 0 0.3em; }
.markdown-body :deep(h3) { font-size: 1.05em; margin: 0.5em 0 0.2em; }
.markdown-body :deep(p) { margin: 0.4em 0; }
.markdown-body :deep(ul), .markdown-body :deep(ol) { padding-left: 1.5em; }
.markdown-body :deep(code) { background: var(--n-color-modal); padding: 1px 4px; border-radius: 3px; font-size: 0.9em; }
.markdown-body :deep(pre) { background: var(--n-color-modal); padding: 10px; border-radius: 4px; overflow-x: auto; }
.markdown-body :deep(pre code) { background: none; padding: 0; }
</style>
