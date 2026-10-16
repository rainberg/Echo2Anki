<template>
  <div class="task-detail-container">
    <n-spin :show="loading">
      <n-page-header @back="$router.push('/tasks')" title="任务详情" style="margin-bottom: 16px">
        <template #extra>
          <n-space :size="8" align="center">
            <n-tag :type="stageTagType(task?.stage)" size="small">{{ stageLabel(task?.stage) }}</n-tag>
            <n-button v-if="task && (task.stage === 'cancelled' || task.stage === 'failed')" size="small" type="primary" :loading="retrying" @click="handleRetry">重新开始</n-button>
          </n-space>
        </template>
      </n-page-header>

      <template v-if="task">
        <n-card size="small" style="margin-bottom: 16px">
          <n-descriptions label-placement="left" :column="{ xs: 1, s: 2, m: 3 }">
            <n-descriptions-item label="文件名">{{ task.upload_name }}</n-descriptions-item>
            <n-descriptions-item label="引擎">{{ task.engine }} / {{ task.model_size }}</n-descriptions-item>
            <n-descriptions-item label="句子数">{{ task.segment_count }}</n-descriptions-item>
            <n-descriptions-item label="创建时间">{{ formatDate(task.created_at) }}</n-descriptions-item>
            <n-descriptions-item label="时长">{{ task.file_duration_sec ? (task.file_duration_sec / 60).toFixed(1) + ' 分钟' : '-' }}</n-descriptions-item>
            <n-descriptions-item label="费用">{{ task.credits_charged }} 积分</n-descriptions-item>
          </n-descriptions>
          <n-progress
            v-if="isProcessing(task.stage)"
            :percentage="Math.round(task.progress * 100)"
            type="line"
            status="info"
            style="margin-top: 12px"
          />
          <n-text v-if="task.error" type="error" style="margin-top: 8px; display: block">{{ task.error }}</n-text>
        </n-card>

        <n-card size="small" style="margin-bottom: 16px">
          <template #header>
            <n-space justify="space-between" align="center" style="width: 100%">
              <span>任务信息</span>
              <n-button v-if="!editingInfo" size="small" type="primary" ghost @click="startEditInfo">修改</n-button>
              <n-space v-else :size="8">
                <n-button size="small" @click="cancelEditInfo">取消</n-button>
                <n-button size="small" type="primary" @click="saveEditInfo">保存</n-button>
              </n-space>
            </n-space>
          </template>
          <template v-if="!editingInfo">
            <n-descriptions label-placement="left" :column="{ xs: 1, s: 3 }">
              <n-descriptions-item label="标题">{{ editTitle || task.upload_name }}</n-descriptions-item>
              <n-descriptions-item label="难度">{{ difficultyLabel(editDifficulty) || '-' }}</n-descriptions-item>
              <n-descriptions-item label="分类">{{ categoryLabel(editCategory) || '-' }}</n-descriptions-item>
            </n-descriptions>
          </template>
          <n-space v-else vertical :size="12">
            <n-input v-model:value="editTitle" size="small" placeholder="默认使用文件名">
              <template #prefix><n-text depth="3" style="white-space: nowrap">标题</n-text></template>
            </n-input>
            <n-space :size="12" :wrap="true">
              <div style="display: flex; align-items: center; gap: 8px; min-width: 180px">
                <n-text depth="3" style="white-space: nowrap">难度</n-text>
                <n-select v-model:value="editDifficulty" :options="difficultyOptions" size="small" placeholder="选择难度" clearable style="flex: 1" />
              </div>
              <div style="display: flex; align-items: center; gap: 8px; min-width: 180px">
                <n-text depth="3" style="white-space: nowrap">分类</n-text>
                <n-select v-model:value="editCategory" :options="categoryOptions" size="small" placeholder="选择分类" clearable style="flex: 1" />
              </div>
            </n-space>
          </n-space>
        </n-card>

        <n-card v-if="task.stage === 'done' && task.engine === 'cohere' && task.transcription_text" size="small">
          <template #header>
            <n-space justify="space-between" align="center" style="width: 100%">
              <span>转录文本</span>
              <n-button size="small" @click="copyTranscription">复制文本</n-button>
            </n-space>
          </template>
          <n-input type="textarea" :value="task.transcription_text" readonly :rows="12" style="font-family: monospace" />
        </n-card>

        <n-card v-else-if="task.stage === 'done' && segments.length" size="small">
          <template #header>
            <n-space justify="space-between" align="center" style="width: 100%">
              <span>字幕播放器</span>
              <n-space>
                <n-button size="small" @click="handleSelectAll">{{ isAllSelected ? '取消全选' : '全选' }}</n-button>
                <n-button size="small" type="primary" @click="openBatchCollect" :disabled="!selectedSegIds.length">
                  收藏选中 ({{ selectedSegIds.length }})
                </n-button>
                <n-button v-if="!task.is_public" size="small" type="info" @click="openShareModal">📤 分享到公共库</n-button>
                <n-popconfirm v-else @positive-click="handleUnshare">
                  <template #trigger><n-button size="small" type="warning" ghost>撤回分享</n-button></template>
                  确定撤回分享？撤回后其他用户将无法查看此内容。
                </n-popconfirm>
              </n-space>
            </n-space>
          </template>

          <SubtitlePlayer
            ref="subtitlePlayerRef"
            :cues="segments"
            :audio-src="fullAudioSrc"
            :collected-ids="collectedSegIds"
            @select-change="onSubtitleSelectChange"
          />
        </n-card>

        <n-card v-if="task.stage === 'done' && !segments.length" size="small">
          <n-empty description="暂无句子数据" />
        </n-card>
      </template>
    </n-spin>

    <n-modal v-model:show="collectModalVisible" preset="dialog" title="添加到收藏集" positive-text="确认" negative-text="取消"
      @positive-click="handleCollect">
      <n-spin :show="collectionsLoading">
        <n-radio-group v-model:value="selectedCollectionId" v-if="collections.length">
          <n-space vertical>
            <n-radio v-for="col in collections" :key="col.id" :value="col.id">
              {{ col.name }} ({{ col.item_count }}条)
            </n-radio>
          </n-space>
        </n-radio-group>
        <n-empty v-else description="暂无收藏集，请先新建" size="small" />
        <n-divider style="margin: 12px 0" />
        <n-button size="small" type="primary" ghost @click="showNewCollection = true">新建收藏集</n-button>
        <div v-if="showNewCollection" style="margin-top: 8px; display: flex; gap: 8px; align-items: center">
          <n-input
            v-model:value="newCollectionName"
            size="small"
            placeholder="收藏集名称"
            style="flex: 1"
            @keyup.enter="handleCreateCollection"
          />
          <n-button size="small" type="primary" @click="handleCreateCollection" :loading="creatingCollection">创建</n-button>
        </div>
      </n-spin>
    </n-modal>

    <n-modal v-model:show="showShareModal" preset="card" title="分享到公共库" style="max-width: 480px">
      <n-form :model="shareForm">
        <n-form-item label="标题">
          <n-input v-model:value="shareForm.title" placeholder="分享标题（默认=文件名）" />
        </n-form-item>
        <n-form-item label="描述">
          <n-input v-model:value="shareForm.description" type="textarea" placeholder="可选描述" :rows="2" />
        </n-form-item>
        <n-form-item label="难度级别">
          <n-select v-model:value="shareForm.difficulty" :options="DIFFICULTY_OPTIONS" placeholder="选择难度（可选）" clearable />
        </n-form-item>
        <n-form-item label="主题分类">
          <n-select v-model:value="shareForm.category" :options="CATEGORY_OPTIONS" placeholder="选择分类（可选）" clearable />
        </n-form-item>
      </n-form>
      <n-text depth="3" style="font-size: 12px">💡 只传标题即可快捷分享，难度和分类可后续编辑</n-text>
      <template #action>
        <n-space justify="end">
          <n-button @click="showShareModal = false">取消</n-button>
          <n-button type="primary" :loading="sharing" @click="handleShare">确认分享</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { useMessage } from 'naive-ui'
import { getTask, updateTask, retryTask } from '../api/tasks'
import { updateSegment } from '../api/segments'
import { listCollections, createCollection, addCollectionItems } from '../api/collections'
import { createPublicShare, deletePublicShare, listPublicShares } from '../api/public'
import { connectProgressWS, disconnectProgressWS } from '../api/ws'
import SubtitlePlayer from '../components/SubtitlePlayer.vue'

const route = useRoute()
const message = useMessage()

const task = ref(null)
const segments = ref([])
const loading = ref(false)
const retrying = ref(false)
const subtitlePlayerRef = ref(null)
const editTitle = ref('')
const editDifficulty = ref(null)
const editCategory = ref(null)
const editingInfo = ref(false)
let savedEditState = { title: '', difficulty: null, category: null }
let pollTimer = null
let wsHandle = null

const selectedSegIds = ref([])
const collectedSegIds = ref(new Set())
const collectModalVisible = ref(false)
const collections = ref([])
const collectionsLoading = ref(false)
const selectedCollectionId = ref(null)
const showNewCollection = ref(false)
const newCollectionName = ref('')
const creatingCollection = ref(false)
const pendingSegIds = ref([])

const showShareModal = ref(false)
const shareForm = ref({ title: '', description: '', difficulty: null, category: null })
const sharing = ref(false)
const shareDone = ref(false)

const DIFFICULTY_OPTIONS = [
  { label: 'A1 入门', value: 'A1' }, { label: 'A2 初级', value: 'A2' },
  { label: 'B1 中级', value: 'B1' }, { label: 'B2 中高级', value: 'B2' },
  { label: 'C1 高级', value: 'C1' }, { label: 'C2 精通', value: 'C2' },
]
const CATEGORY_OPTIONS = [
  { label: '新闻', value: 'news' }, { label: '日常对话', value: 'daily' },
  { label: '教材', value: 'textbook' }, { label: '备考', value: 'exam' },
  { label: '播客', value: 'podcast' }, { label: '影视', value: 'movie' },
  { label: '商务', value: 'business' }, { label: '文化', value: 'culture' },
  { label: '其他', value: 'other' },
]

const difficultyOptions = DIFFICULTY_OPTIONS
const categoryOptions = CATEGORY_OPTIONS

const fullAudioSrc = computed(() => {
  if (!task.value) return ''
  return `/api/audio/${task.value.user_id}/${route.params.id}/normalized.mp3`
})

const isAllSelected = computed(() => {
  return segments.value.length > 0 && selectedSegIds.value.length === segments.value.length
})

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

function difficultyLabel(val) {
  if (!val) return ''
  return DIFFICULTY_OPTIONS.find(o => o.value === val)?.label || val
}

function categoryLabel(val) {
  if (!val) return ''
  return CATEGORY_OPTIONS.find(o => o.value === val)?.label || val
}

function startEditInfo() {
  savedEditState = { title: editTitle.value, difficulty: editDifficulty.value, category: editCategory.value }
  editingInfo.value = true
}

function cancelEditInfo() {
  editTitle.value = savedEditState.title
  editDifficulty.value = savedEditState.difficulty
  editCategory.value = savedEditState.category
  editingInfo.value = false
}

async function saveEditInfo() {
  if (!task.value) return
  try {
    const updates = {}
    if (editTitle.value !== savedEditState.title) updates.title = editTitle.value
    if (editDifficulty.value !== savedEditState.difficulty) updates.difficulty = editDifficulty.value || ''
    if (editCategory.value !== savedEditState.category) updates.category = editCategory.value || ''
    if (Object.keys(updates).length) {
      await updateTask(task.value.id, updates)
      if (updates.title !== undefined) task.value.title = updates.title
      if (updates.difficulty !== undefined) task.value.difficulty = updates.difficulty
      if (updates.category !== undefined) task.value.category = updates.category
      message.success('已保存')
    }
    editingInfo.value = false
  } catch (err) {
    message.error(err.response?.data?.detail || '保存失败')
  }
}

async function handleUpdateField(field, value) {
  if (!task.value) return
  try {
    await updateTask(task.value.id, { [field]: value })
    task.value[field] = value
    message.success('已更新')
  } catch (err) {
    message.error(err.response?.data?.detail || '更新失败')
  }
}

function copyTranscription() {
  if (!task.value?.transcription_text) return
  navigator.clipboard.writeText(task.value.transcription_text)
    .then(() => message.success('已复制'))
    .catch(() => message.error('复制失败'))
}

function onSubtitleSelectChange(indices) {
  selectedSegIds.value = indices.map(i => segments.value[i]?.id).filter(Boolean)
}

function handleSelectAll() {
  if (!subtitlePlayerRef.value) return
  if (isAllSelected.value) {
    subtitlePlayerRef.value.clearSelection()
  } else {
    subtitlePlayerRef.value.selectAll()
  }
}

function openBatchCollect() {
  pendingSegIds.value = [...selectedSegIds.value]
  openCollectModal()
}

async function openCollectModal() {
  collectModalVisible.value = true
  showNewCollection.value = false
  newCollectionName.value = ''
  selectedCollectionId.value = null
  collectionsLoading.value = true
  try {
    const { data } = await listCollections()
    collections.value = data.items || data
    if (collections.value.length) {
      selectedCollectionId.value = collections.value[0].id
    }
  } catch {
    message.error('获取收藏集列表失败')
  } finally {
    collectionsLoading.value = false
  }
}

async function handleCreateCollection() {
  if (!newCollectionName.value.trim()) return
  creatingCollection.value = true
  try {
    const { data } = await createCollection({ name: newCollectionName.value.trim() })
    collections.value.unshift(data)
    selectedCollectionId.value = data.id
    showNewCollection.value = false
    newCollectionName.value = ''
    message.success('收藏集已创建')
  } catch {
    message.error('创建收藏集失败')
  } finally {
    creatingCollection.value = false
  }
}

function handleCollect() {
  if (!selectedCollectionId.value) {
    message.warning('请选择收藏集')
    return false
  }
  addCollectionItems(selectedCollectionId.value, pendingSegIds.value)
    .then(() => {
      message.success(`已添加 ${pendingSegIds.value.length} 条句子到收藏集`)
      pendingSegIds.value.forEach(id => collectedSegIds.value.add(id))
      collectedSegIds.value = new Set(collectedSegIds.value)
      selectedSegIds.value = []
      if (subtitlePlayerRef.value) subtitlePlayerRef.value.clearSelection()
      collectModalVisible.value = false
    })
    .catch(err => {
      message.error(err.response?.data?.detail || '添加失败')
    })
  return false
}

function openShareModal() {
  if (!task.value) return
  shareForm.value = {
    title: task.value.upload_name || '',
    description: '',
    difficulty: null,
    category: null,
  }
  shareDone.value = false
  showShareModal.value = true
}

async function handleShare() {
  if (!task.value) return
  sharing.value = true
  try {
    await createPublicShare({
      task_id: task.value.id,
      title: shareForm.value.title || undefined,
      description: shareForm.value.description || undefined,
      difficulty: shareForm.value.difficulty || undefined,
      category: shareForm.value.category || undefined,
    })
    message.success('已分享到公共库')
    task.value.is_public = true
    shareDone.value = true
    showShareModal.value = false
  } catch (err) {
    const detail = err.response?.data?.detail
    if (detail === 'Task already shared') {
      message.warning('该任务已分享过')
    } else {
      message.error(detail || '分享失败')
    }
  } finally {
    sharing.value = false
  }
}

async function handleUnshare() {
  if (!task.value) return
  try {
    const { data } = await listPublicShares({ task_id: task.value.id, per_page: 1 })
    const shares = data.items || data
    if (!shares.length) {
      message.warning('未找到分享记录')
      return
    }
    await deletePublicShare(shares[0].id)
    task.value.is_public = false
    message.success('已撤回分享')
  } catch (err) {
    message.error(err.response?.data?.detail || '撤回失败')
  }
}

async function fetchTask() {
  loading.value = true
  try {
    const { data } = await getTask(route.params.id)
    task.value = data
    editTitle.value = data.title || ''
    editDifficulty.value = data.difficulty || null
    editCategory.value = data.category || null
    if (data.segments?.length) {
      segments.value = data.segments
      collectedSegIds.value = new Set(
        data.segments.filter(s => s.collected).map(s => s.id)
      )
    }
  } catch (err) {
    message.error('获取任务详情失败')
  } finally {
    loading.value = false
  }
}

async function handleRetry() {
  retrying.value = true
  try {
    const { data } = await retryTask(route.params.id, {})
    task.value = data
    message.success('任务已重新开始')
    startPolling()
  } catch (err) {
    message.error('重新开始失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    retrying.value = false
  }
}

function startPolling() {
  const token = localStorage.getItem('access_token')
  if (token) {
    wsHandle = connectProgressWS(token, (data) => {
      if (data.type === 'task_progress' && data.task_id === route.params.id) {
        if (task.value) {
          task.value.stage = data.stage
          task.value.progress = data.progress
          task.value.stage_message = data.message
        }
        if (data.stage === 'done' || data.stage === 'failed' || data.stage === 'cancelled') {
          fetchTask()
        }
      }
    })
  }
  pollTimer = setInterval(() => {
    if (task.value && isProcessing(task.value.stage)) {
      fetchTask()
    }
  }, 15000)
}

onMounted(() => {
  fetchTask()
  startPolling()
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (wsHandle) wsHandle.close()
})
</script>

<style scoped>
.task-detail-container {
  max-width: 900px;
  margin: 0 auto;
}
</style>
