import { create } from 'zustand';
import { SwipeFeedSegment, SwipeStatsResponse } from '../types';
import * as api from '../services/api';
import { FEED_BATCH_SIZE } from '../constants/theme';

interface SwipeState {
  segments: SwipeFeedSegment[];
  currentIndex: number;
  currentLevel: string;
  totalRated: number;
  stats: SwipeStatsResponse | null;
  isLoading: boolean;
  isPlaying: boolean;
  showTranslation: boolean;
  error: string | null;
  source: 'public' | 'mine';

  // Actions
  fetchFeed: (source?: string, level?: string) => Promise<void>;
  setSource: (source: 'public' | 'mine') => void;
  fetchStats: () => Promise<void>;
  rateCurrent: (rating: 'easy' | 'hard') => Promise<void>;
  collectCurrent: (collectionId: string) => Promise<void>;
  nextSegment: () => void;
  setPlaying: (playing: boolean) => void;
  toggleTranslation: () => void;
  reset: () => void;
}

export const useSwipeStore = create<SwipeState>((set, get) => ({
  segments: [],
  currentIndex: 0,
  currentLevel: 'A1',
  totalRated: 0,
  stats: null,
  isLoading: false,
  isPlaying: false,
  showTranslation: false,
  error: null,
  source: 'public' as const,

  setSource: (source: 'public' | 'mine') => {
    set({ source });
    get().fetchFeed(source);
  },

  fetchFeed: async (sourceOverride?: string, level?: string) => {
    const source = sourceOverride || get().source;
    set({ isLoading: true, error: null });
    try {
      const response = await api.getFeed(source, FEED_BATCH_SIZE, level);
      set({
        segments: response.segments,
        currentLevel: response.current_level,
        totalRated: response.total_rated,
        currentIndex: 0,
        isLoading: false,
      });
    } catch (err: any) {
      set({ error: err.message, isLoading: false });
    }
  },

  fetchStats: async () => {
    try {
      const stats = await api.getStats();
      set({ stats });
    } catch {
      // Stats are non-critical, silently fail
    }
  },

  rateCurrent: async (rating: 'easy' | 'hard') => {
    const { segments, currentIndex } = get();
    const segment = segments[currentIndex];
    if (!segment) return;

    try {
      await api.rateSegment({ segment_id: segment.id, rating });
      set({ totalRated: get().totalRated + 1 });
    } catch {
      // Rating is non-critical for UX, continue
    }
  },

  collectCurrent: async (collectionId: string) => {
    const { segments, currentIndex } = get();
    const segment = segments[currentIndex];
    if (!segment) return;

    try {
      await api.collectSegment({ segment_id: segment.id, collection_id: collectionId });
    } catch {
      // Collect is non-critical for UX
    }
  },

  nextSegment: () => {
    const { segments, currentIndex, fetchFeed } = get();
    const nextIndex = currentIndex + 1;

    // Prefetch more when running low
    if (nextIndex >= segments.length - 3) {
      fetchFeed();
    }

    if (nextIndex < segments.length) {
      set({ currentIndex: nextIndex, showTranslation: false, isPlaying: false });
    } else {
      // No more segments, fetch new batch
      set({ currentIndex: 0, showTranslation: false, isPlaying: false });
      fetchFeed();
    }
  },

  setPlaying: (playing: boolean) => set({ isPlaying: playing }),
  toggleTranslation: () => set((s) => ({ showTranslation: !s.showTranslation })),
  reset: () => set({
    segments: [],
    currentIndex: 0,
    currentLevel: 'A1',
    totalRated: 0,
    stats: null,
    isLoading: false,
    isPlaying: false,
    showTranslation: false,
    error: null,
  }),
}));
