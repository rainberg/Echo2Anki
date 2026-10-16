<template>
  <div class="anki-container">
    <n-card title="推送配置" size="small">
      <template #header-extra>
        <n-button size="small" type="primary" :disabled="configs.length >= maxConfigs" @click="openAddConfig">
          添加配置 ({{ configs.length }}/{{ maxConfigs }})
        </n-button>
      </template>

      <n-empty v-if="!configs.length" description="暂无推送配置" />
      <n-list bordered v-else>
        <n-list-item v-for="cfg in configs" :key="cfg.id">
          <n-thing>
            <template #header>
              <n-tag :type="cfg.push_mode === 'self_hosted' ? 'info' : 'success'" size="small">
                {{ cfg.push_mode === 'self_hosted' ? '自建服务器' : 'AnkiWeb' }}
              </n-tag>
              <n-text style="margin-left: 8px">{{ cfg.name || cfg.deck_name }}</n-text>
            </template>
            <template #description>
              <n-text depth="3" style="font-size: 13px">
                牌组: {{ cfg.deck_name }}
                · {{ cfg.push_mode === 'self_hosted' ? cfg.sync_username : cfg.ankiweb_username }}
              </n-text>
            </template>
            <template #action>
              <n-space>
                <n-button size="tiny" @click="editConfig(cfg)">编辑</n-button>
                <n-popconfirm @positive-click="handleDeleteConfig(cfg)">
                  <template #trigger><n-button size="tiny" type="error" ghost>删除</n-button></template>
                  确定删除？
                </n-popconfirm>
              </n-space>
            </template>
          </n-thing>
        </n-list-item>
      </n-list>
    </n-card>

    <n-card title="推送操作" size="small" style="margin-top: 16px">
      <n-form :show-feedback="false" label-placement="top">
        <n-grid :cols="{ xs: 1, m: 2 }" :x-gap="12" :y-gap="8">
          <n-gi>
            <n-form-item label="收藏集">
              <n-select v-model:value="pushForm.collection_id" :options="collectionOptions" placeholder="选择收藏集" />
            </n-form-item>
          </n-gi>
          <n-gi>
            <n-form-item label="推送目标">
              <n-empty v-if="!configs.length" description="请先添加配置" size="small" />
              <n-checkbox-group v-else v-model:value="pushForm.config_ids">
                <n-space vertical>
                  <n-checkbox v-for="cfg in configs" :key="cfg.id" :value="cfg.id">
                    <n-tag :type="cfg.push_mode === 'self_hosted' ? 'info' : 'success'" size="small" style="margin-right: 4px">
                      {{ cfg.push_mode === 'self_hosted' ? '自建' : 'AnkiWeb' }}
                    </n-tag>
                    {{ cfg.name || cfg.deck_name }}
                    <n-text v-if="pushStatus" depth="3" style="font-size: 12px; margin-left: 4px">
                      {{ (() => {
                        const s = pushStatus.configs.find(c => c.config_id === cfg.id)
                        return s ? `（${s.pushed_count}/${pushStatus.total_items} 已推送）` : ''
                      })() }}
                    </n-text>
                  </n-checkbox>
                </n-space>
              </n-checkbox-group>
            </n-form-item>
          </n-gi>
          <n-gi>
            <n-form-item label=" ">
              <n-button type="primary" :loading="pushing" :disabled="!canPush" @click="handlePush" style="width: 100%">
                推送到 {{ pushForm.config_ids.length }} 个目标
              </n-button>
            </n-form-item>
          </n-gi>
        </n-grid>
      </n-form>
    </n-card>

    <n-card title="推送记录" size="small" style="margin-top: 16px">
      <n-empty v-if="!records.length" description="暂无推送记录" />
      <n-list bordered v-else>
        <n-list-item v-for="rec in records" :key="rec.id">
          <n-thing>
            <template #header>
              <n-tag :type="rec.status === 'done' ? 'success' : rec.status === 'failed' ? 'error' : 'warning'" size="small">
                {{ rec.status === 'done' ? '成功' : rec.status === 'failed' ? '失败' : '进行中' }}
              </n-tag>
              <n-text style="margin-left: 8px">{{ rec.card_count }} 张卡片</n-text>
              <n-text v-if="rec.skipped_count > 0" depth="3" style="margin-left: 8px; font-size: 12px">（跳过 {{ rec.skipped_count }}）</n-text>
            </template>
            <template #description>
              <n-text depth="3" style="font-size: 13px">
                {{ rec.push_mode === 'self_hosted' ? '自建服务器' : 'AnkiWeb' }}
                · {{ rec.deck_name }}
                · {{ formatDate(rec.created_at) }}
              </n-text>
              <n-text v-if="rec.error_message" type="error" style="font-size: 12px; display: block">{{ rec.error_message }}</n-text>
            </template>
          </n-thing>
        </n-list-item>
      </n-list>
    </n-card>

    <n-modal v-model:show="showAdd" preset="card" :title="editingId ? '编辑推送配置' : '添加推送配置'" style="max-width: 450px">
      <n-form :model="configForm">
        <n-form-item label="配置名称">
          <n-input v-model:value="configForm.name" placeholder="如：德语听力-自建服务器（不填则自动生成）" />
        </n-form-item>
        <n-form-item label="推送方式">
          <n-select v-model:value="configForm.push_mode" :options="pushModeOptions" :disabled="!!editingId" />
        </n-form-item>
        <n-form-item label="牌组名称">
          <n-input v-model:value="configForm.deck_name" placeholder="Default" />
        </n-form-item>
        <template v-if="configForm.push_mode === 'self_hosted'">
          <n-form-item label="同步用户名">
            <n-input v-model:value="configForm.sync_username" />
          </n-form-item>
          <n-form-item label="同步密码">
            <n-input v-model:value="configForm.sync_password" type="password" show-password-on="click" :placeholder="editingId ? '留空则不修改' : ''" />
          </n-form-item>
        </template>
        <template v-else>
          <n-form-item label="AnkiWeb 用户名">
            <n-input v-model:value="configForm.ankiweb_username" />
          </n-form-item>
          <n-form-item label="AnkiWeb 密码">
            <n-input v-model:value="configForm.ankiweb_password" type="password" show-password-on="click" :placeholder="editingId ? '留空则不修改' : ''" />
          </n-form-item>
        </template>
      </n-form>
      <template #action>
        <n-space justify="end">
          <n-button @click="showAdd = false">取消</n-button>
          <n-button type="primary" :loading="saving" @click="handleSaveConfig">保存</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useMessage, useDialog } from 'naive-ui'
import { listPushConfigs, createPushConfig, updatePushConfig, deletePushConfig, pushToAnki, getPushStatus, listPushRecords } from '../api/anki'
import { listCollections } from '../api/collections'

const message = useMessage()
const dialog = useDialog()

const pushStatus = ref(null)

const configs = ref([])
const records = ref([])
const collections = ref([])
const showAdd = ref(false)
const saving = ref(false)
const pushing = ref(false)
const editingId = ref(null)
const maxConfigs = ref(4)

const configForm = ref({
  name: '',
  push_mode: 'self_hosted',
  deck_name: 'Default',
  sync_username: '',
  sync_password: '',
  ankiweb_username: '',
  ankiweb_password: '',
})

const pushForm = ref({
  collection_id: null,
  config_ids: [],
})

const pushModeOptions = [
  { label: '自建 Anki 服务器', value: 'self_hosted' },
  { label: 'AnkiWeb', value: 'ankiweb' },
]

const collectionOptions = computed(() =>
  collections.value.map(c => ({ label: c.name, value: c.id }))
)

const canPush = computed(() => pushForm.value.collection_id && pushForm.value.config_ids.length > 0)

// 已推送情况文本（针对当前选中的 config）
const pushedInfo = computed(() => {
  if (!pushStatus.value || !pushForm.value.config_ids.length) return null
  const selected = pushStatus.value.configs.filter(c => pushForm.value.config_ids.includes(c.config_id))
  const total = pushStatus.value.total_items
  const allPushed = selected.every(c => c.unpushed_count === 0)
  const hasPartial = selected.some(c => c.pushed_count > 0 && c.unpushed_count > 0)
  return { total, allPushed, hasPartial, selected }
})

watch(() => pushForm.value.collection_id, async (cid) => {
  pushStatus.value = null
  if (!cid) return
  try {
    const { data } = await getPushStatus(cid)
    pushStatus.value = data
  } catch {}
})

function formatDate(dt) {
  return dt ? new Date(dt).toLocaleString('zh-CN') : ''
}

function openAddConfig() {
  editingId.value = null
  configForm.value = {
    name: '',
    push_mode: 'self_hosted',
    deck_name: 'Default',
    sync_username: '',
    sync_password: '',
    ankiweb_username: '',
    ankiweb_password: '',
  }
  showAdd.value = true
}

async function fetchConfigs() {
  try {
    const { data } = await listPushConfigs()
    configs.value = data
  } catch {}
}

async function fetchRecords() {
  try { const { data } = await listPushRecords(); records.value = data } catch {}
}

async function fetchCollections() {
  try { const { data } = await listCollections(); collections.value = data } catch {}
}

function editConfig(cfg) {
  editingId.value = cfg.id
  configForm.value = {
    name: cfg.name || '',
    push_mode: cfg.push_mode,
    deck_name: cfg.deck_name,
    sync_username: cfg.sync_username || '',
    sync_password: '',
    ankiweb_username: cfg.ankiweb_username || '',
    ankiweb_password: '',
  }
  showAdd.value = true
}

async function handleSaveConfig() {
  saving.value = true
  try {
    if (editingId.value) {
      const update = { name: configForm.value.name, deck_name: configForm.value.deck_name }
      if (configForm.value.push_mode === 'self_hosted') {
        update.sync_username = configForm.value.sync_username
        if (configForm.value.sync_password) update.sync_password = configForm.value.sync_password
      } else {
        update.ankiweb_username = configForm.value.ankiweb_username
        if (configForm.value.ankiweb_password) update.ankiweb_password = configForm.value.ankiweb_password
      }
      await updatePushConfig(editingId.value, update)
    } else {
      await createPushConfig(configForm.value)
    }
    message.success('保存成功')
    showAdd.value = false
    editingId.value = null
    await fetchConfigs()
  } catch (err) {
    message.error(err.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function handleDeleteConfig(cfg) {
  try {
    await deletePushConfig(cfg.id)
    message.success('已删除')
    await fetchConfigs()
    // Remove from push selection if selected
    pushForm.value.config_ids = pushForm.value.config_ids.filter(id => id !== cfg.id)
  } catch {
    message.error('删除失败')
  }
}

async function handlePush() {
  if (!canPush.value) return

  // 检查是否有已推送的句子
  const info = pushedInfo.value
  if (info && (info.allPushed || info.hasPartial)) {
    const pushedTotal = info.selected.reduce((s, c) => s + c.pushed_count, 0)
    const unpushedTotal = info.selected.reduce((s, c) => s + c.unpushed_count, 0)

    if (info.allPushed) {
      // 全部已推送，必须确认是否强制重推
      dialog.warning({
        title: '句子已推送过',
        content: `选中的目标已推送过全部 ${info.total} 个句子。重复推送会在 Anki 中产生重复卡片，请先在 Anki 中清理后再推送。\n\n如确需强制重新推送，请点击下方按钮。`,
        positiveText: '强制重新推送',
        negativeText: '取消',
        onPositiveClick: async () => { await doPush(true) },
      })
      return
    } else {
      // 部分已推送
      dialog.info({
        title: '部分句子已推送过',
        content: `选中的目标中，${unpushedTotal} 个句子未推送，${pushedTotal} 个句子已推送过。\n\n默认只推送未推送的句子，已推送的会被跳过。`,
        positiveText: '仅推送新增',
        negativeText: '全部重新推送',
        onPositiveClick: async () => { await doPush(false) },
        onNegativeClick: async () => { await doPush(true) },
      })
      return
    }
  }

  await doPush(false)
}

async function doPush(force) {
  pushing.value = true
  try {
    const { data } = await pushToAnki({ ...pushForm.value, force })
    const results = Array.isArray(data) ? data : [data]
    const succeeded = results.filter(r => r.status === 'done')
    const failed = results.filter(r => r.status === 'failed')

    if (succeeded.length) {
      const totalCards = succeeded.reduce((s, r) => s + r.card_count, 0)
      const totalSkipped = succeeded.reduce((s, r) => s + (r.skipped_count || 0), 0)
      let msg = `${succeeded.length} 个目标推送成功，共 ${totalCards} 张卡片`
      if (totalSkipped > 0) msg += `（跳过 ${totalSkipped} 个已推送句子）`
      message.success(msg)
    }
    if (failed.length) {
      message.error(`${failed.length} 个目标推送失败`)
    }
    // 刷新推送状态
    if (pushForm.value.collection_id) {
      try {
        const { data } = await getPushStatus(pushForm.value.collection_id)
        pushStatus.value = data
      } catch {}
    }
    await fetchRecords()
  } catch (err) {
    message.error(err.response?.data?.detail || '推送失败')
  } finally {
    pushing.value = false
  }
}

onMounted(() => {
  fetchConfigs()
  fetchRecords()
  fetchCollections()
})
</script>

<style scoped>
.anki-container {
  max-width: 900px;
  margin: 0 auto;
}
</style>
