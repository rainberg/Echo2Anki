<template>
  <div class="tasks-container">
    <n-card title="我的任务">
      <template #header-extra>
        <n-button type="primary" @click="showUpload = true">上传音频</n-button>
      </template>

      <n-spin :show="loading">
        <n-empty v-if="!tasks.length" description="暂无任务，点击右上角上传音频" />
        <n-list v-else bordered>
          <n-list-item v-for="task in tasks" :key="task.id">
            <n-thing>
              <template #header>
                <router-link :to="`/tasks/${task.id}`" style="text-decoration: none; color: inherit;">
                  {{ task.title || task.upload_name }}
                </router-link>
              </template>
              <template #header-extra>
                <n-tag :type="stageTagType(task.stage)" size="small">{{ stageLabel(task.stage) }}</n-tag>
              </template>
              <template #description>
                <n-space size="small">
                  <n-text depth="3">{{ task.engine }} / {{ task.model_size }}</n-text>
                  <n-text depth="3">{{ task.engine === 'cohere' ? '转录文本' : task.segment_count + ' 句' }}</n-text>
                  <n-text depth="3">{{ formatDate(task.created_at) }}</n-text>
                </n-space>
              </template>
              <template #footer>
                <n-progress
                  v-if="isProcessing(task.stage)"
                  :percentage="Math.round(task.progress * 100)"
                  :show-indicator="true"
                  type="line"
                  status="info"
                  style="max-width: 300px"
                />
                <n-text v-if="task.error" type="error" style="font-size: 12px">{{ task.error }}</n-text>
              </template>
              <template #action>
                <n-space>
                  <n-button size="tiny" @click="$router.push(`/tasks/${task.id}`)">查看</n-button>
                  <n-button v-if="task.stage === 'failed'" size="tiny" type="warning" @click="handleRetry(task)">重试</n-button>
                  <n-button v-if="isProcessing(task.stage)" size="tiny" type="error" @click="handleCancel(task)">取消</n-button>
                  <n-popconfirm v-if="['done','failed','cancelled'].includes(task.stage)" @positive-click="handleDelete(task)">
                    <template #trigger>
                      <n-button size="tiny" type="error" ghost>删除</n-button>
                    </template>
                    确定删除此任务？
                  </n-popconfirm>
                </n-space>
              </template>
            </n-thing>
          </n-list-item>
        </n-list>
      </n-spin>

      <n-flex v-if="total > perPage" justify="center" style="margin-top: 16px">
        <n-pagination v-model:page="page" :page-count="Math.ceil(total / perPage)" @update:page="fetchTasks" />
      </n-flex>
    </n-card>

    <n-modal v-model:show="showUpload" preset="card" title="上传音频" style="max-width: 500px">
      <n-form ref="uploadFormRef" :model="uploadForm">
        <n-form-item label="音频文件" path="file">
          <n-upload
            :max="1"
            accept="audio/*,.mp3,.wav,.m4a,.ogg,.flac"
            :default-upload="false"
            @change="handleFileChange"
          >
            <n-button>选择文件</n-button>
          </n-upload>
          <n-text v-if="uploadForm.file" style="margin-left: 8px">{{ uploadForm.file.name }}</n-text>
        </n-form-item>
        <n-form-item label="引擎" path="engine">
          <n-select v-model:value="uploadForm.engine" :options="engineOptions" @update:value="onEngineChange" />
        </n-form-item>
        <n-form-item v-if="uploadForm.engine === 'local_whisper'" label="模型大小" path="model_size">
          <n-select v-model:value="uploadForm.model_size" :options="modelSizeOptions" />
        </n-form-item>
        <n-form-item label="跳过标准化">
          <n-checkbox v-model:checked="uploadForm.skip_normalize">音频已标准化，跳过此步骤</n-checkbox>
        </n-form-item>
        <n-form-item label="标题">
          <n-input v-model:value="uploadForm.title" placeholder="可选，默认使用文件名" />
        </n-form-item>
        <n-form-item label="难度">
          <n-select v-model:value="uploadForm.difficulty" :options="difficultyOptions" placeholder="选择难度（可选）" clearable />
        </n-form-item>
        <n-form-item label="分类">
          <n-select v-model:value="uploadForm.category" :options="categoryOptions" placeholder="选择分类（可选）" clearable />
        </n-form-item>
      </n-form>
      <template #action>
        <n-space justify="end">
          <n-button @click="showUpload = false">取消</n-button>
          <n-button type="primary" :loading="uploading" @click="handleUpload">上传并处理</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useMessage, useDialog } from 'naive-ui'
import { useRouter } from 'vue-router'
import { listTasks, createTask, retryTask, cancelTask, deleteTask } from '../api/tasks'
import { connectProgressWS, disconnectProgressWS } from '../api/ws'

const message = useMessage()
const dialog = useDialog()
const router = useRouter()

const tasks = ref([])
const loading = ref(false)
const page = ref(1)
const total = ref(0)
const perPage = ref(20)
const showUpload = ref(false)
const uploading = ref(false)
const uploadForm = ref({ file: null, engine: 'local_whisper', model_size: 'small', api_key: '', skip_normalize: false, title: '', difficulty: null, category: null })
let pollTimer = null
let wsHandle = null

const engineOptions = [
  { label: '本地 Whisper', value: 'local_whisper' },
  { label: 'OpenAI Whisper API', value: 'openai_whisper' },
  { label: 'Cohere ASR（快速转写）', value: 'cohere' },
  { label: '豆包录音识别 2.0（云端）', value: 'doubao' },
]

const difficultyOptions = [
  { label: 'A1 入门', value: 'A1' }, { label: 'A2 初级', value: 'A2' },
  { label: 'B1 中级', value: 'B1' }, { label: 'B2 中高级', value: 'B2' },
  { label: 'C1 高级', value: 'C1' }, { label: 'C2 精通', value: 'C2' },
]

const categoryOptions = [
  { label: '新闻', value: 'news' }, { label: '日常对话', value: 'daily' },
  { label: '教材', value: 'textbook' }, { label: '备考', value: 'exam' },
  { label: '播客', value: 'podcast' }, { label: '影视', value: 'movie' },
  { label: '商务', value: 'business' }, { label: '文化', value: 'culture' },
  { label: '其他', value: 'other' },
]

const modelSizeOptions = computed(() => {
  const map = {
    local_whisper: [
      { label: 'Tiny (最快)', value: 'tiny' },
      { label: 'Base', value: 'base' },
      { label: 'Small (推荐)', value: 'small' },
      { label: 'Medium', value: 'medium' },
      { label: 'Large (最准)', value: 'large' },
    ],
    openai_whisper: [{ label: 'Whisper-1', value: 'whisper-1' }],
    cohere: [{ label: 'Default', value: 'default' }],
    doubao: [{ label: 'SeedASR 2.0', value: 'seedasr-2.0' }],
  }
  return map[uploadForm.value.engine] || []
})

const DEFAULT_MODEL_SIZE = { local_whisper: 'small', openai_whisper: 'whisper-1', cohere: 'default', doubao: 'seedasr-2.0' }

function onEngineChange(engine) {
  uploadForm.value.model_size = DEFAULT_MODEL_SIZE[engine] || 'default'
}

function stageLabel(stage) {
  const map = { pending: '等待中', normalizing: '标准化', transcribing: '转录中', translating: '翻译中', done: '完成', failed: '失败', cancelled: '已取消' }
  return map[stage] || stage
}

function stageTagType(stage) {
  const map = { pending: 'default', normalizing: 'info', transcribing: 'info', translating: 'info', done: 'success', failed: 'error', cancelled: 'warning' }
  return map[stage] || 'default'
}

function isProcessing(stage) {
  return ['pending', 'normalizing', 'transcribing', 'translating'].includes(stage)
}

function formatDate(dt) {
  if (!dt) return ''
  return new Date(dt).toLocaleString('zh-CN')
}

function handleFileChange({ file }) {
  uploadForm.value.file = file?.file || null
}

async function fetchTasks() {
  loading.value = true
  try {
    const { data } = await listTasks({ page: page.value, per_page: perPage.value })
    tasks.value = data.items
    total.value = data.total
  } catch (err) {
    message.error('获取任务列表失败')
  } finally {
    loading.value = false
  }
}

async function handleUpload() {
  if (!uploadForm.value.file) {
    message.warning('请选择音频文件')
    return
  }
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', uploadForm.value.file)
    fd.append('engine', uploadForm.value.engine)
    fd.append('model_size', uploadForm.value.model_size)
    if (uploadForm.value.api_key) fd.append('api_key', uploadForm.value.api_key)
    if (uploadForm.value.skip_normalize) fd.append('skip_normalize', '1')
    if (uploadForm.value.title) fd.append('title', uploadForm.value.title)
    if (uploadForm.value.difficulty) fd.append('difficulty', uploadForm.value.difficulty)
    if (uploadForm.value.category) fd.append('category', uploadForm.value.category)
    await createTask(fd)
    message.success('任务已提交')
    showUpload.value = false
    uploadForm.value = { file: null, engine: 'local_whisper', model_size: 'small', api_key: '', skip_normalize: false, title: '', difficulty: null, category: null }
    await fetchTasks()
  } catch (err) {
    const detail = err.response?.data?.detail || '上传失败'
    const status = err.response?.status
    if (status === 402 || detail.includes('余额不足')) {
      dialog.warning({
        title: '余额不足',
        content: '您的账户余额不足以处理此音频，请先充值后再提交任务。',
        positiveText: '去充值',
        negativeText: '取消',
        onPositiveClick: () => { router.push('/billing') },
      })
    } else {
      message.error(detail)
    }
  } finally {
    uploading.value = false
  }
}

async function handleRetry(task) {
  const retryData = {}
  if (task.engine === 'openai_whisper') {
    const { value: apiKey } = await dialog.create({
      title: '输入 OpenAI API Key',
      content: '请输入您的 OpenAI API Key',
      positiveText: '重试',
      negativeText: '取消',
      inputPlaceholder: 'sk-...',
    })
    if (!apiKey) return
    retryData.api_key = apiKey
  }
  try {
    await retryTask(task.id, retryData)
    message.success('已重新提交')
    await fetchTasks()
  } catch (err) {
    const detail = err.response?.data?.detail || '重试失败'
    const status = err.response?.status
    if (status === 402 || detail.includes('余额不足')) {
      dialog.warning({
        title: '余额不足',
        content: '您的账户余额不足以处理此音频，请先充值后再重试。',
        positiveText: '去充值',
        negativeText: '取消',
        onPositiveClick: () => { router.push('/billing') },
      })
    } else {
      message.error(detail)
    }
  }
}

async function handleCancel(task) {
  try {
    await cancelTask(task.id)
    message.success('已取消')
    await fetchTasks()
  } catch (err) {
    message.error(err.response?.data?.detail || '取消失败')
  }
}

async function handleDelete(task) {
  try {
    await deleteTask(task.id)
    message.success('已删除')
    await fetchTasks()
  } catch (err) {
    message.error(err.response?.data?.detail || '删除失败')
  }
}

function startPolling() {
  const token = localStorage.getItem('access_token')
  if (token) {
    wsHandle = connectProgressWS(token, (data) => {
      if (data.type === 'task_progress') {
        const idx = tasks.value.findIndex(t => t.id === data.task_id)
        if (idx >= 0) {
          tasks.value[idx].stage = data.stage
          tasks.value[idx].progress = data.progress
          tasks.value[idx].stage_message = data.message
        }
        if (data.stage === 'done' || data.stage === 'failed' || data.stage === 'cancelled') {
          fetchTasks()
        }
      }
    })
  }
  pollTimer = setInterval(() => {
    const hasProcessing = tasks.value.some(t => isProcessing(t.stage))
    if (hasProcessing) fetchTasks()
  }, 15000)
}

onMounted(() => {
  fetchTasks()
  startPolling()
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (wsHandle) wsHandle.close()
})
</script>

<style scoped>
.tasks-container {
  max-width: 900px;
  margin: 0 auto;
}
</style>
