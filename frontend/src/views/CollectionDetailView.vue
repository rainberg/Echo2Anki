<template>
  <div class="collection-detail-container">
    <n-spin :show="loading">
      <n-page-header @back="$router.push('/collections')" :title="collection?.name || '收藏集'" style="margin-bottom: 16px">
        <template #extra>
          <n-space :size="8">
            <n-button v-if="!selectMode" size="small" @click="enterSelectMode">选择</n-button>
            <template v-else>
              <n-button size="small" quaternary @click="selectAll" :disabled="!collection?.items?.length">
                {{ allSelected ? '取消全选' : '全选' }}
              </n-button>
              <n-button size="small" type="error" :disabled="!selectedIds.size" @click="handleBatchRemove">
                删除{{ selectedIds.size ? ` (${selectedIds.size})` : '' }}
              </n-button>
              <n-button size="small" @click="exitSelectMode">取消</n-button>
            </template>
            <n-button size="small" @click="showEdit = true">编辑</n-button>
          </n-space>
        </template>
      </n-page-header>

      <template v-if="collection">
        <n-text depth="3">{{ collection.description }}</n-text>

        <n-card title="句子列表" size="small" style="margin-top: 16px">
          <template #header-extra>
            <n-text depth="3">{{ collection.items?.length || 0 }} 个句子</n-text>
          </template>

          <n-empty v-if="!collection.items?.length" description="暂无句子，从任务详情页添加" />
          <n-list bordered v-else>
            <n-list-item v-for="item in collection.items" :key="item.id">
              <n-thing>
                <template #header>
                  <n-space size="small" align="center">
                    <n-checkbox v-if="selectMode" :checked="selectedIds.has(item.id)" @update:checked="(v) => toggleSelect(item.id, v)" @click.stop />
                    <n-text>{{ item.segment?.german_text }}</n-text>
                    <n-tag v-if="item.segment?.pushed" size="tiny" type="success">已推送</n-tag>
                  </n-space>
                </template>
                <template #description>
                  <n-text depth="3" style="font-size: 13px">{{ item.segment?.chinese_text || '未翻译' }}</n-text>
                </template>
                <template #header-extra>
                  <n-space>
                    <n-button v-if="item.segment?.clip_path" size="tiny" quaternary @click="playAudio(item.segment.clip_path)">▶</n-button>
                    <n-switch size="small" v-model:value="item.push_enabled" @update:value="(v) => togglePush(item, v)" />
                    <n-button v-if="!selectMode" size="tiny" type="error" quaternary @click="handleRemove(item)">移除</n-button>
                  </n-space>
                </template>
              </n-thing>
            </n-list-item>
          </n-list>
        </n-card>
      </template>
    </n-spin>

    <n-modal v-model:show="showEdit" preset="card" title="编辑收藏集" style="max-width: 400px">
      <n-form :model="editForm">
        <n-form-item label="名称">
          <n-input v-model:value="editForm.name" />
        </n-form-item>
        <n-form-item label="描述">
          <n-input v-model:value="editForm.description" type="textarea" />
        </n-form-item>
      </n-form>
      <template #action>
        <n-space justify="end">
          <n-button @click="showEdit = false">取消</n-button>
          <n-button type="primary" @click="handleEdit">保存</n-button>
        </n-space>
      </template>
    </n-modal>

    <audio ref="audioPlayer" style="display: none" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useMessage, useDialog } from 'naive-ui'
import { getCollection, updateCollection, removeCollectionItem, batchRemoveCollectionItems, toggleCollectionItem } from '../api/collections'

const route = useRoute()
const message = useMessage()
const dialog = useDialog()

const collection = ref(null)
const loading = ref(false)
const showEdit = ref(false)
const editForm = ref({ name: '', description: '' })
const audioPlayer = ref(null)

const selectMode = ref(false)
const selectedIds = ref(new Set())

const allSelected = computed(() => {
  const items = collection.value?.items
  return items && items.length > 0 && items.every(i => selectedIds.value.has(i.id))
})

function enterSelectMode() {
  selectMode.value = true
  selectedIds.value = new Set()
}

function exitSelectMode() {
  selectMode.value = false
  selectedIds.value = new Set()
}

function toggleSelect(id, checked) {
  const next = new Set(selectedIds.value)
  if (checked) next.add(id)
  else next.delete(id)
  selectedIds.value = next
}

function selectAll() {
  if (allSelected.value) {
    selectedIds.value = new Set()
  } else {
    selectedIds.value = new Set(collection.value.items.map(i => i.id))
  }
}

async function handleBatchRemove() {
  const count = selectedIds.value.size
  dialog.warning({
    title: '批量移除句子',
    content: `确定从收藏集中移除选中的 ${count} 个句子？`,
    positiveText: '移除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await batchRemoveCollectionItems(route.params.id, [...selectedIds.value])
        message.success(`已移除 ${count} 个句子`)
        exitSelectMode()
        await fetchCollection()
      } catch (e) {
        message.error('移除失败: ' + (e.response?.data?.detail || e.message))
      }
    },
  })
}

async function fetchCollection() {
  loading.value = true
  try {
    const { data } = await getCollection(route.params.id)
    collection.value = data
    editForm.value = { name: data.name, description: data.description }
  } catch {
    message.error('获取收藏集失败')
  } finally {
    loading.value = false
  }
}

async function handleEdit() {
  try {
    await updateCollection(route.params.id, editForm.value)
    message.success('已更新')
    showEdit.value = false
    await fetchCollection()
  } catch {
    message.error('更新失败')
  }
}

async function handleRemove(item) {
  try {
    await removeCollectionItem(route.params.id, item.id)
    message.success('已移除')
    await fetchCollection()
  } catch {
    message.error('移除失败')
  }
}

async function togglePush(item, enabled) {
  try {
    await toggleCollectionItem(route.params.id, item.id, enabled)
  } catch {
    item.push_enabled = !enabled
    message.error('更新失败')
  }
}

function playAudio(clipPath) {
  if (!audioPlayer.value) return
  audioPlayer.value.src = `/api/audio/${clipPath}`
  audioPlayer.value.play().catch(() => message.error('播放失败'))
}

onMounted(fetchCollection)
</script>

<style scoped>
.collection-detail-container {
  max-width: 900px;
  margin: 0 auto;
}
</style>
