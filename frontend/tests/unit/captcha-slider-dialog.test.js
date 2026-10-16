import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import CaptchaSliderDialog from '../../src/components/CaptchaSliderDialog.vue'

const mockCaptchaData = {
  captcha_id: 'test-captcha-123',
  bg_image: 'data:image/png;base64,abc',
  slider_image: 'data:image/png;base64,def',
  y_position: 50,
  puzzle_width: 48,
}

function createWrapper(props = {}) {
  return mount(CaptchaSliderDialog, {
    props: {
      show: false,
      ...props,
    },
    global: {
      stubs: {
        'n-modal': {
          template: '<div v-if="show" class="n-modal"><slot /></div>',
          props: ['show'],
        },
        'n-card': {
          template: '<div class="n-card"><slot /><slot name="action" /></div>',
          props: ['title'],
        },
        'n-button': {
          template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
          props: ['disabled', 'loading', 'text', 'size', 'type'],
          emits: ['click'],
        },
        'n-icon': {
          template: '<span><slot /></span>',
        },
        'n-tag': {
          template: '<span><slot /></span>',
          props: ['type'],
        },
      },
    },
  })
}

describe('CaptchaSliderDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('dialog visibility', () => {
    it('renders modal when show is true', () => {
      const wrapper = createWrapper({ show: true })
      expect(wrapper.find('.n-modal').exists()).toBe(true)
    })

    it('hides modal when show is false', () => {
      const wrapper = createWrapper({ show: false })
      expect(wrapper.find('.n-modal').exists()).toBe(false)
    })

    it('emits update:show when dialog should close', async () => {
      const wrapper = createWrapper({ show: true })
      await wrapper.vm.handleClose()
      expect(wrapper.emitted('update:show')).toBeTruthy()
      expect(wrapper.emitted('update:show')[0][0]).toBe(false)
    })
  })

  describe('captcha rendering', () => {
    it('renders captcha background image when loaded', async () => {
      const wrapper = createWrapper({ show: true })
      wrapper.vm.captchaBg = mockCaptchaData.bg_image
      wrapper.vm.captchaSliderImg = mockCaptchaData.slider_image
      wrapper.vm.captchaY = mockCaptchaData.y_position
      wrapper.vm.puzzleWidth = mockCaptchaData.puzzle_width
      await nextTick()

      const bg = wrapper.find('.captcha-bg')
      expect(bg.exists()).toBe(true)
    })

    it('shows slider track', async () => {
      const wrapper = createWrapper({ show: true })
      wrapper.vm.captchaBg = mockCaptchaData.bg_image
      await nextTick()

      expect(wrapper.find('.slider-track').exists()).toBe(true)
    })

    it('shows refresh button', async () => {
      const wrapper = createWrapper({ show: true })
      wrapper.vm.captchaBg = mockCaptchaData.bg_image
      await nextTick()

      const refreshBtn = wrapper.findAll('button').find(b => b.text().includes('换一张'))
      expect(refreshBtn).toBeDefined()
    })

    it('shows verified tag when captcha is verified', async () => {
      const wrapper = createWrapper({ show: true })
      wrapper.vm.captchaVerified = true
      await nextTick()

      expect(wrapper.find('.n-tag').exists()).toBe(true)
    })
  })

  describe('slider interaction', () => {
    it('initializes slider position at 0', () => {
      const wrapper = createWrapper({ show: true })
      expect(wrapper.vm.sliderLeft).toBe(0)
      expect(wrapper.vm.sliderBtnLeft).toBe(0)
    })

    it('updates slider position on drag', () => {
      const wrapper = createWrapper({ show: true })
      wrapper.vm.onDrag({ type: 'mousemove', clientX: 100, preventDefault: () => {} })
      // delta = 100 - startX(0) = 100, clamped to maxSlide
      expect(wrapper.vm.sliderLeft).toBe(100)
    })

    it('clamps slider position to maxSlide', () => {
      const wrapper = createWrapper({ show: true })
      wrapper.vm.startX = 0
      wrapper.vm.onDrag({ type: 'mousemove', clientX: 500, preventDefault: () => {} })
      expect(wrapper.vm.sliderLeft).toBe(wrapper.vm.maxSlide)
    })

    it('clamps slider position to 0 minimum', () => {
      const wrapper = createWrapper({ show: true })
      wrapper.vm.startX = 100
      wrapper.vm.onDrag({ type: 'mousemove', clientX: 50, preventDefault: () => {} })
      expect(wrapper.vm.sliderLeft).toBe(0)
    })
  })

  describe('captcha verification', () => {
    it('emits verified event on successful verification', async () => {
      const wrapper = createWrapper({ show: true })
      wrapper.vm.captchaId = 'test-id'
      wrapper.vm.sliderLeft = 120

      // Mock the API call
      const mockVerify = vi.fn().mockResolvedValue({
        data: { success: true },
      })
      wrapper.vm.verifyCaptcha = mockVerify

      await wrapper.vm.endDrag()

      expect(wrapper.emitted('verified')).toBeTruthy()
      expect(wrapper.emitted('verified')[0]).toEqual({
        captcha_id: 'test-id',
        x_position: 120,
      })
    })

    it('resets captcha on failed verification', async () => {
      const wrapper = createWrapper({ show: true })
      wrapper.vm.captchaId = 'test-id'

      const mockVerify = vi.fn().mockResolvedValue({
        data: { success: false, message: '验证失败' },
      })
      wrapper.vm.verifyCaptcha = mockVerify
      wrapper.vm.refreshCaptcha = vi.fn()

      await wrapper.vm.endDrag()

      expect(wrapper.vm.refreshCaptcha).toHaveBeenCalled()
    })
  })

  describe('refreshCaptcha', () => {
    it('emits refresh event', async () => {
      const wrapper = createWrapper({ show: true })
      await wrapper.vm.refreshCaptcha()
      expect(wrapper.emitted('refresh')).toBeTruthy()
    })

    it('resets slider position', async () => {
      const wrapper = createWrapper({ show: true })
      wrapper.vm.sliderLeft = 100
      wrapper.vm.sliderBtnLeft = 100
      await wrapper.vm.refreshCaptcha()
      expect(wrapper.vm.sliderLeft).toBe(0)
      expect(wrapper.vm.sliderBtnLeft).toBe(0)
    })
  })

  describe('dialog open behavior', () => {
    it('auto-refreshes captcha when dialog opens', async () => {
      const wrapper = createWrapper({ show: false })
      const refreshSpy = vi.spyOn(wrapper.vm, 'refreshCaptcha')

      await wrapper.setProps({ show: true })
      await nextTick()

      expect(refreshSpy).toHaveBeenCalled()
    })

    it('resets verified state when dialog opens', async () => {
      const wrapper = createWrapper({ show: true })
      wrapper.vm.captchaVerified = true

      await wrapper.setProps({ show: false })
      await wrapper.setProps({ show: true })
      await nextTick()

      expect(wrapper.vm.captchaVerified).toBe(false)
    })
  })
})