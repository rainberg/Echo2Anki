<template>
  <div class="collections-container">
    <n-card title="我的收藏集">
      <template #header-extra>
        <n-space align="center" :size="8">
          <n-button v-if="!selectMode" size="small" @click="enterSelectMode">选择</n-button>
          <template v-else>
            <n-button size="small" quaternary @click="selectAll" :disabled="!collections.length">
              {{ allSelected ? '取消全选' : '全选' }}
            </n-button>
            <n-button size="small" type="error" :disabled="!selectedIds.size" @click="handleBatchDelete">
              删除{{ selectedIds.size ? ` (${selectedIds.size})` : '' }}
            </n-button>
            <n-button size="small" @click="exitSelectMode">取消</n-button>
          </template>
          <n-button v-if="!selectMode" size="small" type="primary" @click="showCreate = true">新建</n-button>
        </n-space>
      </template>

      <n-spin :show="loading">
        <n-empty v-if="!loading && !collections.length" description="暂无收藏集，从任务详情页添加句子" />
        <n-list bordered v-else>
          <n-list-item v-for="coll in collections" :key="coll.id" style="cursor: pointer" @click="onItemClick(coll.id)">
            <n-thing>
              <template #header>
                <n-space size="small" align="center">
                  <n-checkbox v-if="selectMode" :checked="selectedIds.has(coll.id)" @update:checked="(v) => toggleSelect(coll.id, v)" @click.stop />
                  {{ coll.name }}
                </n-space>
              </template>
              <template #description>
                <n-text depth="3" style="font-size: 13px">{{ coll.item_count || 0 }} 个句子</n-text>
              </template>
            </n-thing>
          </n-list-item>
        </n-list>
      </n-spin>
    </n-card>

    <n-modal v-model:show="showCreate" preset="card" title="新建收藏集" style="max-width: 400px">
      <n-form :model="createForm">
        <n-form-item label="名称">
          <n-input v-model:value="createForm.name" placeholder="收藏集名称" @keyup.enter="handleCreate" />
        </n-form-item>
        <n-form-item label="描述">
          <n-input v-model:value="createForm.description" type="textarea" placeholder="可选" />
        </n-form-item>
      </n-form>
      <template #action>
        <n-space justify="end">
          <n-button @click="showCreate = false">取消</n-button>
          <n-button type="primary" :loading="creating" @click="handleCreate">创建</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage, useDialog } from 'naive-ui'
import { listCollections, createCollection, batchDeleteCollections } from '../api/collections'

const router = useRouter()
const message = useMessage()
const dialog = useDialog()

const collections = ref([])
const loading = ref(false)
const showCreate = ref(false)
const creating = ref(false)
const createForm = ref({ name: '', description: '' })

const selectMode = ref(false)
const selectedIds = ref(new Set())

const allSelected = computed(() => collections.value.length > 0 && collections.value.every(c => selectedIds.value.has(c.id)))

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
    selectedIds.value = new Set(collections.value.map(c => c.id))
  }
}

function onItemClick(id) {
  if (selectMode.value) {
    toggleSelect(id, !selectedIds.value.has(id))
  } else {
    router.push(`/collections/${id}`)
  }
}

async function handleBatchDelete() {
  const count = selectedIds.value.size
  dialog.warning({
    title: '批量删除收藏集',
    content: `确定删除选中的 ${count} 个收藏集？此操作不可撤销。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await batchDeleteCollections([...selectedIds.value])
        message.success(`已删除 ${count} 个收藏集`)
        exitSelectMode()
        await fetchCollections()
      } catch (e) {
        message.error('删除失败: ' + (e.response?.data?.detail || e.message))
      }
    },
  })
}

async function fetchCollections() {
  loading.value = true
  try {
    const res = await listCollections()
    const data = res.data
    collections.value = Array.isArray(data) ? data : (data?.items || [])
  } catch (e) {
    message.error('获取收藏集失败: ' + (e.message || String(e)))
  } finally {
    loading.value = false
  }
}

async function handleCreate() {
  if (!createForm.value.name.trim()) {
    message.warning('请输入收藏集名称')
    return
  }
  creating.value = true
  try {
    await createCollection({ name: createForm.value.name.trim(), description: createForm.value.description })
    message.success('收藏集已创建')
    showCreate.value = false
    createForm.value = { name: '', description: '' }
    await fetchCollections()
  } catch (e) {
    message.error('创建失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    creating.value = false
  }
}

onMounted(fetchCollections)
</script>

<style scoped>
.collections-container {
  max-width: 900px;
  margin: 0 auto;
}
</style>
