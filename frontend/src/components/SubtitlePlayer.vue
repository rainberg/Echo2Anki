<template>
  <div class="subtitle-player">
    <div class="meta-bar">
      <n-text depth="3" style="font-size: 12px">{{ fmtTime(currentTime) }}</n-text>
      <n-text depth="3" style="font-size: 12px">
        {{ selectedIds.size }} 已选 / {{ cues.length }} 句
      </n-text>
    </div>

    <div class="cue-list" ref="cueListEl">
      <div
        v-for="(cue, idx) in cues"
        :key="idx"
        :class="['cue', { active: activeIdx === idx, selected: selectedIds.has(idx) }]"
        :ref="el => cueRefs[idx] = el"
        @click="seekTo(cue)"
      >
        <div class="cue-time">
          {{ fmtTime(cue.start_time) }}
          <br />#{{ idx + 1 }}
        </div>
        <div class="cue-text">
          <div class="de">{{ cue.german_text }} <span v-if="collectedIds.has(cue.id)" class="collected-badge" title="已收藏">★</span></div>
          <div class="zh" v-if="cue.chinese_text">{{ cue.chinese_text }}</div>
        </div>
        <button
          class="cue-mark"
          :class="{ checked: selectedIds.has(idx) }"
          @click.stop="toggleSelect(idx)"
          :title="selectedIds.has(idx) ? '取消选择' : '选择收藏'"
        >
          ✓
        </button>
      </div>
    </div>

    <div class="player-bar">
      <audio
        ref="audioEl"
        :src="audioSrc"
        controls
        preload="metadata"
        @timeupdate="onTimeUpdate"
        @loadedmetadata="onLoaded"
        style="width: 100%"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onUnmounted } from 'vue'

const props = defineProps({
  cues: { type: Array, default: () => [] },
  audioSrc: { type: String, default: '' },
  collectedIds: { type: Set, default: () => new Set() },
})

const emit = defineEmits(['select-change'])

const audioEl = ref(null)
const cueListEl = ref(null)
const cueRefs = ref([])

const currentTime = ref(0)
const activeIdx = ref(-1)
const selectedIds = ref(new Set())

function fmtTime(sec) {
  const s = Math.max(0, Math.floor(sec || 0))
  return String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0')
}

function onTimeUpdate() {
  if (!audioEl.value) return
  const t = audioEl.value.currentTime
  currentTime.value = t

  let next = -1
  for (let i = 0; i < props.cues.length; i++) {
    const cue = props.cues[i]
    if (t >= Number(cue.start_time) && t <= Number(cue.end_time) + 0.15) {
      next = i
      break
    }
  }

  if (next !== activeIdx.value) {
    activeIdx.value = next
    if (next >= 0 && cueRefs.value[next] && cueListEl.value) {
      const listRect = cueListEl.value.getBoundingClientRect()
      const cueRect = cueRefs.value[next].getBoundingClientRect()
      const cueTop = cueRect.top - listRect.top + cueListEl.value.scrollTop
      const targetScroll = cueTop - listRect.height / 2 + cueRect.height / 2
      cueListEl.value.scrollTo({ top: Math.max(0, targetScroll), behavior: 'smooth' })
    }
  }
}

function onLoaded() {}

function seekTo(cue) {
  if (!audioEl.value) return
  audioEl.value.currentTime = Number(cue.start_time) || 0
  audioEl.value.play().catch(() => {})
}

function toggleSelect(idx) {
  const newSet = new Set(selectedIds.value)
  if (newSet.has(idx)) {
    newSet.delete(idx)
  } else {
    newSet.add(idx)
  }
  selectedIds.value = newSet
  emit('select-change', Array.from(newSet).sort((a, b) => a - b))
}

function selectAll() {
  const newSet = new Set(props.cues.map((_, i) => i))
  selectedIds.value = newSet
  emit('select-change', Array.from(newSet))
}

function clearSelection() {
  selectedIds.value = new Set()
  emit('select-change', [])
}

function getSelectedCues() {
  return Array.from(selectedIds.value)
    .sort((a, b) => a - b)
    .map(i => props.cues[i])
}

function getSelectedIndices() {
  return Array.from(selectedIds.value).sort((a, b) => a - b)
}

watch(() => props.cues, () => {
  selectedIds.value = new Set()
  activeIdx.value = -1
  cueRefs.value = []
})

onUnmounted(() => {
  if (audioEl.value) {
    audioEl.value.pause()
  }
})

defineExpose({ selectAll, clearSelection, getSelectedCues, getSelectedIndices })
</script>

<style scoped>
.subtitle-player {
  border: 1px solid #d8dee9;
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
  display: flex;
  flex-direction: column;
}

.meta-bar {
  display: flex;
  justify-content: space-between;
  padding: 6px 12px;
  border-bottom: 1px solid #edf0f5;
}

.cue-list {
  flex: 1;
  max-height: calc(100vh - 320px);
  min-height: 200px;
  overflow-y: auto;
}

.cue {
  display: grid;
  grid-template-columns: 58px 1fr 36px;
  gap: 10px;
  align-items: start;
  min-height: 50px;
  padding: 8px 12px;
  border-bottom: 1px solid #edf0f5;
  cursor: pointer;
  transition: background 0.15s;
}

.cue:last-child {
  border-bottom: 0;
}

.cue:hover {
  background: #f7f9fc;
}

.cue.active {
  background: #fff4cc;
  box-shadow: inset 3px 0 0 #d99b00;
}

.cue.selected {
  background: #eaf7ef;
}

.cue.selected.active {
  background: #fff1b8;
  box-shadow: inset 3px 0 0 #138a45;
}

.cue-time {
  padding-top: 2px;
  color: #697386;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.cue-text .de {
  margin-bottom: 4px;
  font-size: 15px;
  line-height: 1.45;
}

.cue-text .zh {
  color: #475467;
  font-size: 13px;
  line-height: 1.45;
}

.cue-text .zh-empty {
  min-height: 20px;
}

.cue-mark {
  width: 24px;
  height: 24px;
  margin-top: 2px;
  border: 1px solid #aab4c0;
  border-radius: 4px;
  background: #fff;
  color: transparent;
  cursor: pointer;
  font-weight: 700;
  line-height: 20px;
  font-size: 14px;
  text-align: center;
  padding: 0;
  transition: all 0.15s;
}

.cue-mark:hover {
  border-color: #64748b;
}

.cue-mark.checked {
  border-color: #0b7a3b;
  background: #dff5e8;
  color: #0b7a3b;
}

.collected-badge {
  color: #d99b00;
  font-size: 13px;
  margin-left: 4px;
  vertical-align: middle;
}

.player-bar {
  padding: 4px 8px 8px;
  border-top: 1px solid #d8dee9;
  background: #fafbfc;
  position: sticky;
  bottom: 0;
  z-index: 10;
}
</style>
