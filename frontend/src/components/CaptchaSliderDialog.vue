<template>
  <n-modal :show="show" @update:show="$emit('update:show', $event)">
    <n-card title="图形验证" style="width: 380px" :bordered="false">
      <div v-if="!captchaVerified" class="captcha-box">
        <div
          class="captcha-bg"
          :style="{
            backgroundImage: `url(${captchaBg})`,
            width: captchaWidth + 'px',
            height: captchaHeight + 'px',
          }"
        >
          <div
            v-if="captchaSliderImg"
            class="captcha-slider"
            :style="{
              backgroundImage: `url(${captchaSliderImg})`,
              left: sliderLeft + 'px',
              top: captchaY + 'px',
              width: puzzleWidth + 'px',
              height: puzzleWidth + 'px',
            }"
          />
        </div>
        <div class="slider-track">
          <div class="slider-tip">拖动滑块完成拼图</div>
          <div
            class="slider-btn"
            :class="{ dragging: isDragging }"
            :style="{ left: sliderBtnLeft + 'px' }"
            @mousedown="startDrag"
            @touchstart="startDrag"
          >
            <n-icon><span>&#10095;</span></n-icon>
          </div>
        </div>
        <n-button text size="small" @click="handleRefresh">换一张</n-button>
      </div>
      <n-tag v-else type="success">图形验证已通过</n-tag>

      <template #action>
        <n-button @click="handleClose">关闭</n-button>
      </template>
    </n-card>
  </n-modal>
</template>

<script setup>
import { ref, watch } from 'vue'
import { captcha } from '../api/auth'

const props = defineProps({
  show: { type: Boolean, default: false },
  captchaBg: { type: String, default: '' },
  captchaSliderImg: { type: String, default: '' },
  captchaY: { type: Number, default: 0 },
  puzzleWidth: { type: Number, default: 50 },
  captchaId: { type: String, default: '' },
})

const emit = defineEmits(['update:show', 'verified', 'refresh'])

const captchaWidth = ref(320)
const captchaHeight = ref(160)
const captchaVerified = ref(false)

const sliderLeft = ref(0)
const sliderBtnLeft = ref(0)
const isDragging = ref(false)
const startX = ref(0)
const startBtnX = ref(0)
const maxSlide = ref(270)

function handleClose() {
  emit('update:show', false)
}

function handleRefresh() {
  sliderLeft.value = 0
  sliderBtnLeft.value = 0
  captchaVerified.value = false
  emit('refresh')
}

function startDrag(e) {
  if (captchaVerified.value) return
  isDragging.value = true
  startX.value = e.type.includes('touch') ? e.touches[0].clientX : e.clientX
  startBtnX.value = sliderBtnLeft.value
  document.addEventListener('mousemove', onDrag)
  document.addEventListener('mouseup', endDrag)
  document.addEventListener('touchmove', onDrag, { passive: false })
  document.addEventListener('touchend', endDrag)
}

function onDrag(e) {
  if (!isDragging.value) return
  e.preventDefault()
  const clientX = e.type.includes('touch') ? e.touches[0].clientX : e.clientX
  let delta = clientX - startX.value
  delta = Math.max(0, Math.min(delta, maxSlide.value))
  sliderLeft.value = delta
  sliderBtnLeft.value = delta
}

async function endDrag() {
  if (!isDragging.value) return
  isDragging.value = false
  document.removeEventListener('mousemove', onDrag)
  document.removeEventListener('mouseup', endDrag)
  document.removeEventListener('touchmove', onDrag)
  document.removeEventListener('touchend', endDrag)

  try {
    const { data } = await captcha.verify({
      captcha_id: props.captchaId,
      x_position: sliderLeft.value,
    })
    if (data.success) {
      captchaVerified.value = true
      emit('verified', {
        captcha_id: props.captchaId,
        x_position: sliderLeft.value,
      })
    } else {
      handleRefresh()
    }
  } catch {
    handleRefresh()
  }
}

watch(() => props.show, (val) => {
  if (val) {
    captchaVerified.value = false
    sliderLeft.value = 0
    sliderBtnLeft.value = 0
  }
})
</script>

<style scoped>
.captcha-box {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: flex-start;
}
.captcha-bg {
  position: relative;
  background-size: cover;
  border-radius: 4px;
  overflow: hidden;
  border: 1px solid #d9d9d9;
}
.captcha-slider {
  position: absolute;
  background-size: cover;
  cursor: default;
}
.slider-track {
  position: relative;
  width: 320px;
  height: 40px;
  background: #f0f0f0;
  border-radius: 20px;
  border: 1px solid #d9d9d9;
  display: flex;
  align-items: center;
  justify-content: center;
}
.slider-tip {
  color: #999;
  font-size: 14px;
  user-select: none;
}
.slider-btn {
  position: absolute;
  top: 2px;
  left: 0;
  width: 36px;
  height: 36px;
  background: #fff;
  border-radius: 50%;
  box-shadow: 0 2px 6px rgba(0,0,0,0.15);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  user-select: none;
  transition: background 0.2s;
}
.slider-btn:hover {
  background: #f5f5f5;
}
.slider-btn.dragging {
  background: #e6f7ff;
}
</style>
