<template>
  <div class="public-detail-container">
    <n-spin :show="loading">
      <n-page-header @back="$router.push('/')" :title="share?.title || '公共库详情'" style="margin-bottom: 16px" />

      <template v-if="share">
        <n-card size="small" style="margin-bottom: 16px">
          <n-descriptions label-placement="left" :column="{ xs: 1, s: 2, m: 3 }">
            <n-descriptions-item label="标题">{{ share.title }}</n-descriptions-item>
            <n-descriptions-item label="分享者">{{ share.sharer_name || '匿名' }}</n-descriptions-item>
            <n-descriptions-item label="难度/分类">
              <n-space size="small">
                <n-tag v-if="share.difficulty" size="small" :type="diffTagType(share.difficulty)">{{ share.difficulty }}</n-tag>
                <n-tag v-if="share.category" size="small">{{ categoryName(share.category) }}</n-tag>
                <n-tag v-if="share.duration_tier" size="small" type="info">{{ durationTierName(share.duration_tier) }}</n-tag>
              </n-space>
            </n-descriptions-item>
            <n-descriptions-item label="时长">{{ formatDuration(share.file_duration_sec) }}</n-descriptions-item>
            <n-descriptions-item label="句子数">{{ share.segment_count }}</n-descriptions-item>
            <n-descriptions-item label="播放次数">{{ share.play_count }}</n-descriptions-item>
          </n-descriptions>
          <n-text v-if="share.description" depth="3" style="margin-top: 8px; display: block">{{ share.description }}</n-text>
          <n-space size="small" style="margin-top: 8px" v-if="share.tags?.length">
            <n-tag v-for="tag in share.tags" :key="tag.id" size="tiny">{{ tag.name }}</n-tag>
          </n-space>

          <n-divider style="margin: 12px 0" />

          <n-space>
            <n-button :type="share.is_liked ? 'error' : 'default'" @click="toggleLike">
              {{ share.is_liked ? '❤️ 已点赞' : '🤍 点赞' }} ({{ share.like_count }})
            </n-button>
            <n-button :type="share.is_collected ? 'warning' : 'default'" @click="toggleCollect">
              {{ share.is_collected ? '⭐ 已收藏' : '☆ 收藏到我的收藏集' }} ({{ share.collect_count }})
            </n-button>
          </n-space>
        </n-card>

        <n-card title="字幕播放器" size="small">
          <n-empty v-if="!share.segments?.length" description="暂无句子" />
          <SubtitlePlayer
            v-else
            :cues="share.segments"
            :audio-src="publicAudioSrc"
          />
        </n-card>
      </template>
    </n-spin>

    <n-modal v-model:show="showCollectModal" preset="dialog" title="收藏到我的收藏集" positive-text="确认" negative-text="取消" @positive-click="handleCollectToCollection">
      <n-spin :show="collectLoading">
        <n-radio-group v-model:value="selectedCollectionId" v-if="collections.length">
          <n-space vertical>
            <n-radio v-for="col in collections" :key="col.id" :value="col.id">
              {{ col.name }} ({{ col.item_count }}条)
            </n-radio>
          </n-space>
        </n-radio-group>
        <n-empty v-else description="暂无收藏集" size="small" />
      </n-spin>
    </n-modal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { useAuthStore } from '../stores/auth'
import {
  getPublicShare, likePublicShare, unlikePublicShare,
  collectPublicShare, uncollectPublicShare, recordPublicPlay,
} from '../api/public'
import { listCollections } from '../api/collections'
import SubtitlePlayer from '../components/SubtitlePlayer.vue'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const authStore = useAuthStore()

const isLoggedIn = computed(() => authStore.isLoggedIn)

const share = ref(null)
const loading = ref(false)

const publicAudioSrc = computed(() => {
  if (!share.value) return ''
  return `/api/audio/${share.value.user_id}/${share.value.task_id}/normalized.mp3`
})

const showCollectModal = ref(false)
const collectLoading = ref(false)
const collections = ref([])
const selectedCollectionId = ref(null)

function formatDuration(sec) {
  if (!sec) return '-'
  const s = parseFloat(sec)
  if (s < 60) return `${Math.round(s)}s`
  return `${(s / 60).toFixed(1)}min`
}

function categoryName(key) {
  const map = { news: '新闻', daily: '日常对话', textbook: '教材', exam: '备考', podcast: '播客', movie: '影视', business: '商务', culture: '文化', other: '其他' }
  return map[key] || key
}

function durationTierName(tier) {
  const map = { short: '短句', medium: '中篇', long: '长篇' }
  return map[tier] || tier
}

function diffTagType(diff) {
  const map = { A1: 'success', A2: 'success', B1: 'info', B2: 'info', C1: 'warning', C2: 'error' }
  return map[diff] || 'default'
}

async function fetchShare() {
  loading.value = true
  try {
    const { data } = await getPublicShare(route.params.id)
    share.value = data
    recordPublicPlay(route.params.id).catch(() => {})
  } catch {
    message.error('获取详情失败')
  } finally {
    loading.value = false
  }
}

async function toggleLike() {
  if (!share.value) return
  if (!isLoggedIn.value) {
    message.warning('请先登录')
    router.push('/login')
    return
  }
  try {
    if (share.value.is_liked) {
      const { data } = await unlikePublicShare(share.value.id)
      share.value.is_liked = false
      share.value.like_count = data.like_count
    } else {
      const { data } = await likePublicShare(share.value.id)
      share.value.is_liked = true
      share.value.like_count = data.like_count
    }
  } catch {
    message.error('操作失败')
  }
}

function toggleCollect() {
  if (!share.value) return
  if (!isLoggedIn.value) {
    message.warning('请先登录')
    router.push('/login')
    return
  }
  if (share.value.is_collected) {
    uncollectPublicShare(share.value.id).then(({ data }) => {
      share.value.is_collected = false
      share.value.collect_count = data.collect_count
    }).catch(() => message.error('操作失败'))
  } else {
    openCollectModal()
  }
}

async function openCollectModal() {
  showCollectModal.value = true
  collectLoading.value = true
  selectedCollectionId.value = null
  try {
    const { data } = await listCollections()
    collections.value = Array.isArray(data) ? data : (data?.items || [])
    if (collections.value.length) {
      selectedCollectionId.value = collections.value[0].id
    }
  } catch {
    message.error('获取收藏集失败')
  } finally {
    collectLoading.value = false
  }
}

function handleCollectToCollection() {
  if (!share.value) return false
  const collectionId = selectedCollectionId.value
  collectPublicShare(share.value.id, collectionId).then(({ data }) => {
    share.value.is_collected = true
    share.value.collect_count = data.collect_count
    message.success('已收藏')
  }).catch(() => message.error('收藏失败'))
  return true
}

onMounted(fetchShare)
</script>

<style scoped>
.public-detail-container {
  max-width: 900px;
  margin: 0 auto;
}
</style>
