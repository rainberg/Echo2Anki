<template>
  <div class="public-container">
    <n-card>
      <template #header>
        <n-text strong style="font-size: 18px">公共库</n-text>
      </template>
      <template #header-extra>
        <n-input v-model:value="searchQuery" placeholder="搜索德文/中文..." clearable style="width: 220px" @keyup.enter="handleSearch">
          <template #prefix>🔍</template>
        </n-input>
      </template>

      <n-space vertical size="large">
        <div v-if="featuredShares.length" class="featured-section">
          <n-text strong style="font-size: 15px; margin-bottom: 8px; display: block">📌 精选推荐</n-text>
          <div class="featured-scroll">
            <div v-for="share in featuredShares" :key="share.id" class="featured-card" @click="goDetail(share.id)">
              <div class="featured-card-body">
                <n-text strong>{{ share.title }}</n-text>
                <n-text depth="3" style="font-size: 12px">{{ formatDiffCat(share) }}</n-text>
                <n-text depth="3" style="font-size: 12px">▶ {{ formatDuration(share.file_duration_sec) }} · {{ share.segment_count }}句</n-text>
                <n-text depth="3" style="font-size: 12px">❤️ {{ share.like_count }}</n-text>
              </div>
            </div>
          </div>
        </div>

        <n-divider style="margin: 0" />

        <div class="filter-section">
          <n-space vertical size="small">
            <n-space size="small" align="center">
              <n-text depth="3" style="font-size: 13px; min-width: 40px">难度</n-text>
              <n-tag v-for="d in difficulties" :key="d.key" :type="selectedDifficulty === d.key ? 'primary' : 'default'"
                size="small" style="cursor: pointer" @click="toggleDifficulty(d.key)">
                {{ d.name }} <n-text depth="3" style="font-size: 11px">({{ d.count }})</n-text>
              </n-tag>
            </n-space>
            <n-space size="small" align="center" :wrap="true">
              <n-text depth="3" style="font-size: 13px; min-width: 40px">分类</n-text>
              <n-tag v-for="c in categories" :key="c.key" :type="selectedCategory === c.key ? 'primary' : 'default'"
                size="small" style="cursor: pointer" @click="toggleCategory(c.key)">
                {{ c.name }} <n-text depth="3" style="font-size: 11px">({{ c.count }})</n-text>
              </n-tag>
            </n-space>
            <n-space size="small" align="center">
              <n-text depth="3" style="font-size: 13px; min-width: 40px">排序</n-text>
              <n-tag v-for="s in sortOptions" :key="s.value" :type="selectedSort === s.value ? 'primary' : 'default'"
                size="small" style="cursor: pointer" @click="selectedSort = s.value; fetchShares()">
                {{ s.label }}
              </n-tag>
            </n-space>
          </n-space>
        </div>

        <n-divider style="margin: 0" />

        <n-spin :show="loading">
          <n-empty v-if="!loading && !shares.length" description="暂无公共音频资源" />
          <div v-else class="shares-grid">
            <n-card v-for="share in shares" :key="share.id" size="small" hoverable class="share-card" @click="goDetail(share.id)">
              <n-space vertical size="small">
                <n-text strong style="font-size: 14px">{{ share.title }}</n-text>
                <n-space size="small">
                  <n-tag v-if="share.difficulty" size="tiny" :type="diffTagType(share.difficulty)">{{ share.difficulty }}</n-tag>
                  <n-tag v-if="share.category" size="tiny">{{ categoryName(share.category) }}</n-tag>
                  <n-tag v-if="share.duration_tier" size="tiny" type="info">{{ durationTierName(share.duration_tier) }}</n-tag>
                </n-space>
                <n-space size="small" align="center">
                  <n-text depth="3" style="font-size: 12px">▶ {{ formatDuration(share.file_duration_sec) }}</n-text>
                  <n-text depth="3" style="font-size: 12px">{{ share.segment_count }}句</n-text>
                </n-space>
                <n-space size="small" align="center" justify="space-between" style="width: 100%">
                  <n-space size="small">
                    <n-text depth="3" style="font-size: 12px">❤️ {{ share.like_count }}</n-text>
                    <n-text depth="3" style="font-size: 12px">⭐ {{ share.collect_count }}</n-text>
                    <n-text depth="3" style="font-size: 12px">▶ {{ share.play_count }}</n-text>
                  </n-space>
                  <n-space size="tiny" @click.stop>
                    <n-button size="tiny" :type="share.is_liked ? 'error' : 'default'" quaternary @click="toggleLike(share)">
                      {{ share.is_liked ? '❤️' : '🤍' }}
                    </n-button>
                    <n-button size="tiny" :type="share.is_collected ? 'warning' : 'default'" quaternary @click="toggleCollect(share)">
                      {{ share.is_collected ? '⭐' : '☆' }}
                    </n-button>
                  </n-space>
                </n-space>
              </n-space>
            </n-card>
          </div>
        </n-spin>

        <n-space justify="center" v-if="shares.length < total">
          <n-button @click="loadMore" :loading="loadingMore">加载更多</n-button>
        </n-space>
      </n-space>
    </n-card>

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
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { useAuthStore } from '../stores/auth'
import {
  listPublicShares, listPublicCategories, listPublicDifficulties,
  likePublicShare, unlikePublicShare, collectPublicShare, uncollectPublicShare,
} from '../api/public'
import { listCollections } from '../api/collections'

const router = useRouter()
const message = useMessage()
const authStore = useAuthStore()

const shares = ref([])
const featuredShares = ref([])
const categories = ref([])
const difficulties = ref([])
const loading = ref(false)
const loadingMore = ref(false)
const searchQuery = ref('')
const selectedDifficulty = ref(null)
const selectedCategory = ref(null)
const selectedSort = ref('newest')
const total = ref(0)
const page = ref(1)
const perPage = 20

const showCollectModal = ref(false)
const collectLoading = ref(false)
const collections = ref([])
const selectedCollectionId = ref(null)
const pendingShareId = ref(null)

const isLoggedIn = computed(() => authStore.isLoggedIn)

const sortOptions = [
  { label: '最新', value: 'newest' },
  { label: '最热', value: 'popular' },
  { label: '最多收藏', value: 'most_collected' },
]

function toggleDifficulty(key) {
  selectedDifficulty.value = selectedDifficulty.value === key ? null : key
  page.value = 1
  fetchShares()
}

function toggleCategory(key) {
  selectedCategory.value = selectedCategory.value === key ? null : key
  page.value = 1
  fetchShares()
}

function goDetail(id) {
  router.push(`/public/${id}`)
}

function formatDuration(sec) {
  if (!sec) return '-'
  const s = parseFloat(sec)
  if (s < 60) return `${Math.round(s)}s`
  return `${(s / 60).toFixed(1)}min`
}

function formatDiffCat(share) {
  const parts = []
  if (share.difficulty) parts.push(share.difficulty)
  if (share.category) parts.push(categoryName(share.category))
  return parts.join(' · ') || '-'
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

async function fetchShares() {
  loading.value = true
  try {
    const params = {
      page: page.value,
      per_page: perPage,
      sort: selectedSort.value,
    }
    if (selectedDifficulty.value) params.difficulty = selectedDifficulty.value
    if (selectedCategory.value) params.category = selectedCategory.value
    if (searchQuery.value) params.q = searchQuery.value

    const { data } = await listPublicShares(params)
    shares.value = data.items || []
    total.value = data.total || 0
  } catch {
    message.error('获取公共库失败')
  } finally {
    loading.value = false
  }
}

async function fetchFeatured() {
  try {
    const { data } = await listPublicShares({ per_page: 6, sort: 'popular' })
    featuredShares.value = (data.items || []).filter(s => s.is_featured || s.like_count > 0)
  } catch {}
}

async function fetchCategories() {
  try {
    const { data } = await listPublicCategories()
    categories.value = data
  } catch {}
}

async function fetchDifficulties() {
  try {
    const { data } = await listPublicDifficulties()
    difficulties.value = data
  } catch {}
}

async function loadMore() {
  loadingMore.value = true
  try {
    page.value += 1
    const params = {
      page: page.value,
      per_page: perPage,
      sort: selectedSort.value,
    }
    if (selectedDifficulty.value) params.difficulty = selectedDifficulty.value
    if (selectedCategory.value) params.category = selectedCategory.value
    const { data } = await listPublicShares(params)
    shares.value = [...shares.value, ...(data.items || [])]
    total.value = data.total || 0
  } catch {
    message.error('加载失败')
  } finally {
    loadingMore.value = false
  }
}

function handleSearch() {
  page.value = 1
  fetchShares()
}

async function toggleLike(share) {
  if (!isLoggedIn.value) {
    message.warning('请先登录')
    return
  }
  try {
    if (share.is_liked) {
      const { data } = await unlikePublicShare(share.id)
      share.is_liked = false
      share.like_count = data.like_count
    } else {
      const { data } = await likePublicShare(share.id)
      share.is_liked = true
      share.like_count = data.like_count
    }
  } catch {
    message.error('操作失败')
  }
}

function toggleCollect(share) {
  if (!isLoggedIn.value) {
    message.warning('请先登录')
    return
  }
  if (share.is_collected) {
    uncollectPublicShare(share.id).then(({ data }) => {
      share.is_collected = false
      share.collect_count = data.collect_count
    }).catch(() => message.error('操作失败'))
  } else {
    pendingShareId.value = share.id
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
  if (!pendingShareId.value) return false
  const shareId = pendingShareId.value
  const collectionId = selectedCollectionId.value
  collectPublicShare(shareId, collectionId).then(({ data }) => {
    const share = shares.value.find(s => s.id === shareId)
    if (share) {
      share.is_collected = true
      share.collect_count = data.collect_count
    }
    message.success('已收藏')
  }).catch(() => message.error('收藏失败'))
  pendingShareId.value = null
  return true
}

onMounted(() => {
  fetchShares()
  fetchFeatured()
  fetchCategories()
  fetchDifficulties()
})
</script>

<style scoped>
.public-container {
  max-width: 960px;
  margin: 0 auto;
}

.featured-section {
  padding: 4px 0;
}

.featured-scroll {
  display: flex;
  gap: 12px;
  overflow-x: auto;
  padding-bottom: 4px;
}

.featured-card {
  min-width: 180px;
  max-width: 200px;
  padding: 12px;
  border: 1px solid var(--n-border-color);
  border-radius: 8px;
  cursor: pointer;
  transition: box-shadow 0.2s;
}

.featured-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.featured-card-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.shares-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
}

.share-card {
  cursor: pointer;
  transition: box-shadow 0.2s;
}

.share-card:hover {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
}
</style>
