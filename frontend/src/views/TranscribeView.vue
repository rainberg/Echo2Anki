<template>
  <div class="transcribe-container">
    <!-- Upload Area -->
    <n-card title="语音转文字" size="small">
      <n-upload
        :max="1"
        :default-upload="false"
        accept=".flac,.mp3,.mpeg,.mpga,.ogg,.wav"
        @change="handleFileChange"
      >
        <n-upload-dragger>
          <n-text style="font-size: 16px">点击或拖拽音频文件到此处</n-text>
          <n-text depth="3" style="font-size: 13px; display: block; margin-top: 4px">
            支持 FLAC / MP3 / OGG / WAV，最大 25MB
          </n-text>
        </n-upload-dragger>
      </n-upload>

      <n-space vertical style="margin-top: 12px">
        <n-space align="center">
          <n-text>语言：</n-text>
          <n-select v-model:value="language" :options="languageOptions" style="width: 180px" />
        </n-space>
        <n-button type="primary" :loading="uploading" :disabled="!selectedFile" @click="handleUpload" block>
          {{ uploading ? '上传中...' : '开始转录' }}
        </n-button>
      </n-space>
    </n-card>

    <!-- Current Job Status -->
    <n-card v-if="currentJob" size="small" style="margin-top: 16px">
      <template #header>
        <n-space align="center">
          <n-spin v-if="currentJob.status === 'pending' || currentJob.status === 'processing'" :size="16" />
          <n-tag :type="statusType(currentJob.status)" size="small">{{ statusLabel(currentJob.status) }}</n-tag>
          <n-text>{{ currentJob.filename }}</n-text>
        </n-space>
      </template>
      <n-text v-if="currentJob.status === 'pending'" depth="3">排队中，前方 {{ currentJob.queue_size || 0 }} 个任务</n-text>
      <n-text v-else-if="currentJob.status === 'processing'" depth="3">正在转录，请稍候...</n-text>
      <template v-else-if="currentJob.status === 'done'">
        <n-input type="textarea" :value="currentJob.text" readonly :rows="8" style="font-family: monospace" />
        <n-button size="small" style="margin-top: 8px" @click="copyText(currentJob.text)">复制文本</n-button>
      </template>
      <n-text v-else-if="currentJob.status === 'failed'" type="error">{{ currentJob.error_message }}</n-text>
    </n-card>

    <!-- History -->
    <n-card title="转录历史" size="small" style="margin-top: 16px">
      <n-empty v-if="!records.length" description="暂无转录记录" />
      <n-list bordered v-else>
        <n-list-item v-for="rec in records" :key="rec.id">
          <n-thing>
            <template #header>
              <n-tag :type="statusType(rec.status)" size="small">{{ statusLabel(rec.status) }}</n-tag>
              <n-text style="margin-left: 8px">{{ rec.filename }}</n-text>
            </template>
            <template #description>
              <n-text depth="3" style="font-size: 13px">
                {{ languageName(rec.language) }} · {{ formatSize(rec.file_size) }} · {{ formatDate(rec.created_at) }}
              </n-text>
            </template>
            <template #action>
              <n-space>
                <n-button v-if="rec.status === 'done'" size="tiny" @click="viewDetail(rec)">查看</n-button>
                <n-popconfirm @positive-click="handleDelete(rec)">
                  <template #trigger><n-button size="tiny" type="error" ghost>删除</n-button></template>
                  确定删除？
                </n-popconfirm>
              </n-space>
            </template>
          </n-thing>
        </n-list-item>
      </n-list>
    </n-card>

    <!-- Detail Modal -->
    <n-modal v-model:show="showDetail" preset="card" title="转录结果" style="max-width: 700px">
      <template v-if="detailRecord">
        <n-text depth="3" style="font-size: 13px; display: block; margin-bottom: 8px">
          {{ detailRecord.filename }} · {{ languageName(detailRecord.language) }} · {{ formatDate(detailRecord.created_at) }}
        </n-text>
        <n-input type="textarea" :value="detailRecord.text" readonly :rows="12" style="font-family: monospace" />
        <n-button size="small" style="margin-top: 8px" @click="copyText(detailRecord.text)">复制文本</n-button>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useMessage } from 'naive-ui'
import { uploadTranscription, listTranscriptions, getTranscription, deleteTranscription } from '../api/transcribe'

const message = useMessage()

const language = ref('de')
const selectedFile = ref(null)
const uploading = ref(false)
const currentJob = ref(null)
const records = ref([])
const showDetail = ref(false)
const detailRecord = ref(null)
let pollTimer = null

const languageOptions = [
  { label: '🇩🇪 德语', value: 'de' },
  { label: '🇬🇧 英语', value: 'en' },
  { label: '🇫🇷 法语', value: 'fr' },
  { label: '🇮🇹 意大利语', value: 'it' },
  { label: '🇪🇸 西班牙语', value: 'es' },
  { label: '🇵🇹 葡萄牙语', value: 'pt' },
  { label: '🇬🇷 希腊语', value: 'el' },
  { label: '🇳🇱 荷兰语', value: 'nl' },
  { label: '🇵🇱 波兰语', value: 'pl' },
  { label: '🇻🇳 越南语', value: 'vi' },
  { label: '🇨🇳 中文', value: 'zh' },
  { label: '🇸🇦 阿拉伯语', value: 'ar' },
  { label: '🇯🇵 日语', value: 'ja' },
  { label: '🇰🇷 韩语', value: 'ko' },
]

const LANG_NAMES = {
  de: '德语', en: '英语', fr: '法语', it: '意大利语', es: '西班牙语',
  pt: '葡萄牙语', el: '希腊语', nl: '荷兰语', pl: '波兰语', vi: '越南语',
  zh: '中文', ar: '阿拉伯语', ja: '日语', ko: '韩语',
}

function languageName(code) { return LANG_NAMES[code] || code }

function statusType(s) {
  if (s === 'done') return 'success'
  if (s === 'failed') return 'error'
  if (s === 'processing') return 'warning'
  return 'default'
}

function statusLabel(s) {
  if (s === 'pending') return '排队中'
  if (s === 'processing') return '转录中'
  if (s === 'done') return '完成'
  if (s === 'failed') return '失败'
  return s
}

function formatSize(bytes) {
  if (!bytes) return ''
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}

function formatDate(dt) {
  return dt ? new Date(dt).toLocaleString('zh-CN') : ''
}

function handleFileChange({ file }) {
  selectedFile.value = file?.file || null
}

async function handleUpload() {
  if (!selectedFile.value) return
  uploading.value = true
  try {
    const { data } = await uploadTranscription(selectedFile.value, language.value)
    currentJob.value = data
    message.success('已提交转录任务')
    startPolling(data.id)
    await fetchRecords()
  } catch (err) {
    message.error(err.response?.data?.detail || '上传失败')
  } finally {
    uploading.value = false
  }
}

function startPolling(id) {
  stopPolling()
  pollTimer = setInterval(async () => {
    try {
      const { data } = await getTranscription(id)
      currentJob.value = data
      if (data.status === 'done' || data.status === 'failed') {
        stopPolling()
        await fetchRecords()
      }
    } catch {
      stopPolling()
    }
  }, 3000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function fetchRecords() {
  try {
    const { data } = await listTranscriptions()
    records.value = data
  } catch {}
}

function viewDetail(rec) {
  detailRecord.value = rec
  showDetail.value = true
}

async function handleDelete(rec) {
  try {
    await deleteTranscription(rec.id)
    message.success('已删除')
    await fetchRecords()
  } catch {
    message.error('删除失败')
  }
}

function copyText(text) {
  navigator.clipboard.writeText(text).then(() => message.success('已复制')).catch(() => message.error('复制失败'))
}

onMounted(() => {
  fetchRecords()
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style scoped>
.transcribe-container {
  max-width: 900px;
  margin: 0 auto;
}
</style>
