import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import SubtitlePlayer from '../../src/components/SubtitlePlayer.vue'

const mockCues = [
  { id: 'seg-1', start_time: 0, end_time: 5, german_text: 'Hallo Welt', chinese_text: '你好世界' },
  { id: 'seg-2', start_time: 5, end_time: 10, german_text: 'Wie geht es?', chinese_text: '你好吗？' },
  { id: 'seg-3', start_time: 10, end_time: 15, german_text: 'Auf Wiedersehen', chinese_text: null },
]

function createWrapper(props = {}) {
  return mount(SubtitlePlayer, {
    props: {
      cues: mockCues,
      audioSrc: '/test.mp3',
      collectedIds: new Set(),
      ...props,
    },
    global: {
      stubs: {
        'n-text': { template: '<span><slot /></span>' },
      },
    },
  })
}

describe('SubtitlePlayer', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('rendering', () => {
    it('renders all cues', () => {
      const wrapper = createWrapper()
      const cues = wrapper.findAll('.cue')
      expect(cues).toHaveLength(3)
    })

    it('renders cue german text', () => {
      const wrapper = createWrapper()
      const cueTexts = wrapper.findAll('.cue-text .de')
      expect(cueTexts[0].text()).toContain('Hallo Welt')
      expect(cueTexts[1].text()).toContain('Wie geht es?')
    })

    it('renders cue chinese text when available', () => {
      const wrapper = createWrapper()
      const cueTexts = wrapper.findAll('.cue-text .zh')
      expect(cueTexts[0].text()).toBe('你好世界')
    })

    it('does not render chinese text when null', () => {
      const wrapper = createWrapper()
      const cueTexts = wrapper.findAll('.cue-text .zh')
      expect(cueTexts).toHaveLength(2)
    })

    it('renders cue time', () => {
      const wrapper = createWrapper()
      const times = wrapper.findAll('.cue-time')
      expect(times[0].text()).toContain('00:00')
      expect(times[1].text()).toContain('00:05')
    })

    it('shows selected count in meta bar', () => {
      const wrapper = createWrapper()
      const metaText = wrapper.find('.meta-bar').text()
      expect(metaText).toContain('0 已选')
      expect(metaText).toContain('3 句')
    })

    it('shows collected badge for collected cues', () => {
      const wrapper = createWrapper({
        collectedIds: new Set(['seg-1']),
      })
      const badge = wrapper.find('.collected-badge')
      expect(badge.exists()).toBe(true)
    })

    it('renders audio element', () => {
      const wrapper = createWrapper()
      const audio = wrapper.find('audio')
      expect(audio.exists()).toBe(true)
      expect(audio.attributes('src')).toBe('/test.mp3')
    })
  })

  describe('fmtTime', () => {
    it('formats 0 seconds as 00:00', () => {
      const wrapper = createWrapper()
      expect(wrapper.vm.fmtTime(0)).toBe('00:00')
    })

    it('formats 65 seconds as 01:05', () => {
      const wrapper = createWrapper()
      expect(wrapper.vm.fmtTime(65)).toBe('01:05')
    })

    it('formats 3661 seconds as 61:01', () => {
      const wrapper = createWrapper()
      expect(wrapper.vm.fmtTime(3661)).toBe('61:01')
    })

    it('formats negative seconds as 00:00', () => {
      const wrapper = createWrapper()
      expect(wrapper.vm.fmtTime(-5)).toBe('00:00')
    })

    it('handles null/undefined', () => {
      const wrapper = createWrapper()
      expect(wrapper.vm.fmtTime(null)).toBe('00:00')
      expect(wrapper.vm.fmtTime(undefined)).toBe('00:00')
    })
  })

  describe('toggleSelect', () => {
    it('adds index to selected set on first click', async () => {
      const wrapper = createWrapper()
      const markButtons = wrapper.findAll('.cue-mark')
      await markButtons[0].trigger('click')

      expect(wrapper.emitted('select-change')).toBeTruthy()
      expect(wrapper.emitted('select-change')[0][0]).toEqual([0])
    })

    it('removes index from selected set on second click', async () => {
      const wrapper = createWrapper()
      const markButtons = wrapper.findAll('.cue-mark')
      await markButtons[0].trigger('click')
      await markButtons[0].trigger('click')

      const lastEmit = wrapper.emitted('select-change')
      expect(lastEmit[lastEmit.length - 1][0]).toEqual([])
    })

    it('supports multiple selections', async () => {
      const wrapper = createWrapper()
      const markButtons = wrapper.findAll('.cue-mark')
      await markButtons[0].trigger('click')
      await markButtons[2].trigger('click')

      const lastEmit = wrapper.emitted('select-change')
      expect(lastEmit[lastEmit.length - 1][0]).toEqual([0, 2])
    })

    it('sorts selected indices', async () => {
      const wrapper = createWrapper()
      const markButtons = wrapper.findAll('.cue-mark')
      await markButtons[2].trigger('click')
      await markButtons[0].trigger('click')

      const lastEmit = wrapper.emitted('select-change')
      expect(lastEmit[lastEmit.length - 1][0]).toEqual([0, 2])
    })
  })

  describe('selectAll', () => {
    it('selects all cues', () => {
      const wrapper = createWrapper()
      wrapper.vm.selectAll()
      const indices = wrapper.vm.getSelectedIndices()
      expect(indices).toEqual([0, 1, 2])
    })
  })

  describe('clearSelection', () => {
    it('clears all selections', () => {
      const wrapper = createWrapper()
      wrapper.vm.selectAll()
      wrapper.vm.clearSelection()
      const indices = wrapper.vm.getSelectedIndices()
      expect(indices).toEqual([])
    })
  })

  describe('getSelectedCues', () => {
    it('returns selected cue objects', () => {
      const wrapper = createWrapper()
      wrapper.vm.toggleSelect(0)
      wrapper.vm.toggleSelect(2)
      const cues = wrapper.vm.getSelectedCues()
      expect(cues).toHaveLength(2)
      expect(cues[0].german_text).toBe('Hallo Welt')
      expect(cues[1].german_text).toBe('Auf Wiedersehen')
    })
  })

  describe('cue click', () => {
    it('seeks audio to cue start time on click', async () => {
      const wrapper = createWrapper()
      const audioEl = wrapper.find('audio').element
      vi.spyOn(audioEl, 'play').mockResolvedValue()

      await wrapper.findAll('.cue')[1].trigger('click')

      expect(audioEl.currentTime).toBe(5)
    })
  })

  describe('watch cues prop', () => {
    it('resets selection when cues change', async () => {
      const wrapper = createWrapper()
      wrapper.vm.selectAll()

      await wrapper.setProps({
        cues: [{ id: 'new-1', start_time: 0, end_time: 3, german_text: 'Neu', chinese_text: '新' }],
      })
      await nextTick()

      expect(wrapper.vm.getSelectedIndices()).toEqual([])
    })
  })

  describe('onTimeUpdate', () => {
    it('sets activeIdx based on current audio time', () => {
      const wrapper = createWrapper()
      const audioEl = wrapper.find('audio').element
      Object.defineProperty(audioEl, 'currentTime', { value: 7, writable: true })

      wrapper.vm.onTimeUpdate()

      expect(wrapper.vm.activeIdx).toBe(1)
    })

    it('sets activeIdx to -1 when time is before first cue', () => {
      const wrapper = createWrapper()
      const audioEl = wrapper.find('audio').element
      Object.defineProperty(audioEl, 'currentTime', { value: -1, writable: true })

      wrapper.vm.onTimeUpdate()

      expect(wrapper.vm.activeIdx).toBe(-1)
    })
  })
})