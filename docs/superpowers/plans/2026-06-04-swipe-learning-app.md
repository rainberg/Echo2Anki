# 德语滑动学习 APP — React Native 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个抖音式全屏沉浸式德语听力学习 APP（React Native + Expo），用户通过滑动手势学习片段，基于难度标注自适应推荐。

**Architecture:** 独立 React Native + Expo 项目（`anki-swipe-app/`），复用现有后端 API（`anki.3mudi.com`）和认证服务（`auth.3mudi.com`）。APP 使用 `react-native-reanimated` 实现流畅手势动画，`expo-av` 播放音频，Zustand 管理状态，AsyncStorage 本地缓存 JWT 和离线数据。

**Tech Stack:** React Native + Expo SDK 52, TypeScript, react-native-reanimated v3, expo-av, Zustand, AsyncStorage, React Navigation, expo-secure-store

---

## File Structure

```
anki-swipe-app/
├── app/
│   ├── _layout.tsx              # Root layout with navigation
│   ├── index.tsx                # Entry → redirect to swipe
│   ├── swipe.tsx                # Main swipe feed screen
│   ├── login.tsx                # Login screen
│   ├── stats.tsx                # Learning stats screen
│   └── settings.tsx             # Settings screen
├── components/
│   ├── SwipeCard.tsx            # Single segment card (text + audio)
│   ├── SwipeDeck.tsx            # Card stack with gesture handling
│   ├── AudioProgressBar.tsx     # Audio playback progress bar
│   ├── DifficultyBadge.tsx      # A1-C2 difficulty label
│   └── RatingOverlay.tsx        # Easy/hard flash overlay
├── services/
│   ├── api.ts                   # API client (fetch wrapper)
│   ├── auth.ts                  # Auth service (login, token storage)
│   └── audioCache.ts            # Audio preload & cache
├── store/
│   └── swipeStore.ts            # Zustand store for swipe state
├── constants/
│   └── theme.ts                 # Colors, fonts, spacing
├── types/
│   └── index.ts                 # TypeScript type definitions
├── app.json                     # Expo config
├── package.json
├── tsconfig.json
└── babel.config.js
```

---

### Task 1: Initialize Expo project

**Files:**
- Create: `anki-swipe-app/` (entire project scaffold)

- [ ] **Step 1: Create Expo project**

Run:
```bash
cd d:\00_dev\anki-app
npx create-expo-app@latest anki-swipe-app --template blank-typescript
```

- [ ] **Step 2: Install core dependencies**

Run:
```bash
cd d:\00_dev\anki-app\anki-swipe-app
npx expo install expo-router expo-av expo-secure-store expo-status-bar react-native-reanimated react-native-gesture-handler react-native-safe-area-context react-native-screens zustand @react-native-async-storage/async-storage
```

- [ ] **Step 3: Configure babel for reanimated**

In `babel.config.js`, add reanimated plugin (must be first in plugins list):

```javascript
module.exports = function (api) {
  api.cache(true);
  return {
    presets: ['babel-preset-expo'],
    plugins: ['react-native-reanimated/plugin'],
  };
};
```

- [ ] **Step 4: Configure expo-router in app.json**

In `app.json`, add under `"expo"`:

```json
{
  "scheme": "ankiswipe",
  "plugins": ["expo-router"]
}
```

- [ ] **Step 5: Create directory structure**

Run:
```bash
cd d:\00_dev\anki-app\anki-swipe-app
mkdir -p components services store constants types
```

- [ ] **Step 6: Verify project starts**

Run:
```bash
cd d:\00_dev\anki-app\anki-swipe-app
npx expo start
```

Expected: Expo dev server starts, QR code shown

- [ ] **Step 7: Commit**

```bash
cd d:\00_dev\anki-app\anki-swipe-app
git init
git add -A
git commit -m "chore: initialize Expo project with core dependencies"
```

---

### Task 2: Types, constants, and API client

**Files:**
- Create: `anki-swipe-app/types/index.ts`
- Create: `anki-swipe-app/constants/theme.ts`
- Create: `anki-swipe-app/services/api.ts`

- [ ] **Step 1: Create type definitions**

Create `types/index.ts`:

```typescript
export interface SwipeFeedSegment {
  id: string;
  german_text: string;
  chinese_text: string;
  audio_url: string;
  difficulty: string | null;
  source_title: string;
  duration: number;
}

export interface SwipeFeedResponse {
  segments: SwipeFeedSegment[];
  current_level: string;
  total_rated: number;
}

export interface SwipeStatsResponse {
  current_level: string;
  total_rated: number;
  easy_count: number;
  hard_count: number;
  consecutive_easy: number;
  consecutive_hard: number;
}

export interface SwipeRateRequest {
  segment_id: string;
  rating: 'easy' | 'hard';
}

export interface SwipeCollectRequest {
  segment_id: string;
  collection_id: string;
}

export type DifficultyLevel = 'A1' | 'A2' | 'B1' | 'B2' | 'C1' | 'C2';

export const DIFFICULTY_LEVELS: DifficultyLevel[] = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2'];

export interface AuthTokens {
  access_token: string;
  refresh_token?: string;
}

export interface UserProfile {
  user_id: string;
  email?: string;
  display_name?: string;
  role: string;
}
```

- [ ] **Step 2: Create theme constants**

Create `constants/theme.ts`:

```typescript
export const Colors = {
  background: '#0A0A0A',
  cardBackground: '#1A1A1A',
  textPrimary: '#FFFFFF',
  textSecondary: '#999999',
  easy: '#4CAF50',
  hard: '#F44336',
  collect: '#FFD700',
  accent: '#6C63FF',
  difficultyA1: '#4CAF50',
  difficultyA2: '#8BC34A',
  difficultyB1: '#FFC107',
  difficultyB2: '#FF9800',
  difficultyC1: '#F44336',
  difficultyC2: '#9C27B0',
};

export const Spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
};

export const Typography = {
  titleSize: 28,
  subtitleSize: 18,
  bodySize: 16,
  captionSize: 12,
  germanTextSize: 24,
  chineseTextSize: 18,
};

export const SWIPE_THRESHOLD = 120;
export const PRELOAD_COUNT = 3;
export const FEED_BATCH_SIZE = 10;
```

- [ ] **Step 3: Create API client**

Create `services/api.ts`:

```typescript
import { SwipeFeedResponse, SwipeStatsResponse, SwipeRateRequest, SwipeCollectRequest } from '../types';

const BASE_URL = 'https://anki.3mudi.com/api';

let authToken: string | null = null;

export function setAuthToken(token: string | null) {
  authToken = token;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };
  if (authToken) {
    headers['Authorization'] = `Bearer ${authToken}`;
  }

  const response = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const body = await response.text().catch(() => '');
    throw new Error(`API ${response.status}: ${body || response.statusText}`);
  }

  return response.json();
}

export async function getFeed(source: string = 'public', limit: number = 10, level?: string): Promise<SwipeFeedResponse> {
  const params = new URLSearchParams({ source, limit: String(limit) });
  if (level) params.set('level', level);
  return request<SwipeFeedResponse>(`/swipe/feed?${params}`);
}

export async function rateSegment(data: SwipeRateRequest): Promise<{ rating: string; segment_id: string }> {
  return request('/swipe/rate', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function collectSegment(data: SwipeCollectRequest): Promise<{ collected: boolean; segment_id: string }> {
  return request('/swipe/collect', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function getStats(): Promise<SwipeStatsResponse> {
  return request<SwipeStatsResponse>('/swipe/stats');
}
```

- [ ] **Step 4: Commit**

```bash
cd d:\00_dev\anki-app\anki-swipe-app
git add types/index.ts constants/theme.ts services/api.ts
git commit -m "feat: add type definitions, theme constants, and API client"
```

---

### Task 3: Auth service and secure token storage

**Files:**
- Create: `anki-swipe-app/services/auth.ts`

- [ ] **Step 1: Create auth service**

Create `services/auth.ts`:

```typescript
import * as SecureStore from 'expo-secure-store';
import { setAuthToken } from './api';
import { UserProfile } from '../types';

const AUTH_SERVICE_URL = 'https://auth.3mudi.com';
const TOKEN_KEY = 'anki_access_token';
const REFRESH_TOKEN_KEY = 'anki_refresh_token';

export async function login(email: string, password: string): Promise<UserProfile> {
  const response = await fetch(`${AUTH_SERVICE_URL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });

  if (!response.ok) {
    const body = await response.text().catch(() => '');
    throw new Error(`Login failed: ${body || response.statusText}`);
  }

  const data = await response.json();
  const accessToken = data.access_token;
  const refreshToken = data.refresh_token;

  // Store tokens
  await SecureStore.setItemAsync(TOKEN_KEY, accessToken);
  if (refreshToken) {
    await SecureStore.setItemAsync(REFRESH_TOKEN_KEY, refreshToken);
  }

  // Set for API client
  setAuthToken(accessToken);

  // Get user profile
  return getUserProfile(accessToken);
}

export async function restoreSession(): Promise<UserProfile | null> {
  try {
    const token = await SecureStore.getItemAsync(TOKEN_KEY);
    if (!token) return null;

    // Verify token is still valid
    const response = await fetch(`${AUTH_SERVICE_URL}/api/auth/verify`, {
      headers: { Authorization: `Bearer ${token}` },
    });

    if (!response.ok) {
      // Token expired, try refresh
      const refreshed = await tryRefreshToken();
      if (!refreshed) {
        await logout();
        return null;
      }
      return getUserProfile(refreshed);
    }

    setAuthToken(token);
    return getUserProfile(token);
  } catch {
    return null;
  }
}

async function tryRefreshToken(): Promise<string | null> {
  try {
    const refreshToken = await SecureStore.getItemAsync(REFRESH_TOKEN_KEY);
    if (!refreshToken) return null;

    const response = await fetch(`${AUTH_SERVICE_URL}/api/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (!response.ok) return null;

    const data = await response.json();
    const newAccessToken = data.access_token;
    await SecureStore.setItemAsync(TOKEN_KEY, newAccessToken);
    if (data.refresh_token) {
      await SecureStore.setItemAsync(REFRESH_TOKEN_KEY, data.refresh_token);
    }
    setAuthToken(newAccessToken);
    return newAccessToken;
  } catch {
    return null;
  }
}

async function getUserProfile(token: string): Promise<UserProfile> {
  const response = await fetch(`${AUTH_SERVICE_URL}/api/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!response.ok) {
    throw new Error('Failed to get user profile');
  }

  return response.json();
}

export async function logout(): Promise<void> {
  await SecureStore.deleteItemAsync(TOKEN_KEY);
  await SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY);
  setAuthToken(null);
}

export async function isLoggedIn(): Promise<boolean> {
  const token = await SecureStore.getItemAsync(TOKEN_KEY);
  return token !== null;
}
```

- [ ] **Step 2: Commit**

```bash
cd d:\00_dev\anki-app\anki-swipe-app
git add services/auth.ts
git commit -m "feat: add auth service with secure token storage"
```

---

### Task 4: Zustand store for swipe state

**Files:**
- Create: `anki-swipe-app/store/swipeStore.ts`

- [ ] **Step 1: Create swipe store**

Create `store/swipeStore.ts`:

```typescript
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

  // Actions
  fetchFeed: (source?: string, level?: string) => Promise<void>;
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

  fetchFeed: async (source = 'public', level?: string) => {
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
```

- [ ] **Step 2: Commit**

```bash
cd d:\00_dev\anki-app\anki-swipe-app
git add store/swipeStore.ts
git commit -m "feat: add Zustand store for swipe feed state management"
```

---

### Task 5: SwipeCard component

**Files:**
- Create: `anki-swipe-app/components/SwipeCard.tsx`
- Create: `anki-swipe-app/components/DifficultyBadge.tsx`
- Create: `anki-swipe-app/components/AudioProgressBar.tsx`

- [ ] **Step 1: Create DifficultyBadge component**

Create `components/DifficultyBadge.tsx`:

```typescript
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Colors, Typography, Spacing } from '../constants/theme';
import { DifficultyLevel } from '../types';

const DIFFICULTY_COLORS: Record<string, string> = {
  A1: Colors.difficultyA1,
  A2: Colors.difficultyA2,
  B1: Colors.difficultyB1,
  B2: Colors.difficultyB2,
  C1: Colors.difficultyC1,
  C2: Colors.difficultyC2,
};

interface Props {
  level: string | null;
}

export function DifficultyBadge({ level }: Props) {
  if (!level) return null;

  const color = DIFFICULTY_COLORS[level] || Colors.accent;

  return (
    <View style={[styles.badge, { backgroundColor: color }]}>
      <Text style={styles.text}>{level}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    paddingHorizontal: Spacing.sm + 2,
    paddingVertical: Spacing.xs,
    borderRadius: 12,
  },
  text: {
    color: '#FFFFFF',
    fontSize: Typography.captionSize,
    fontWeight: '700',
  },
});
```

- [ ] **Step 2: Create AudioProgressBar component**

Create `components/AudioProgressBar.tsx`:

```typescript
import React from 'react';
import { View, StyleSheet } from 'react-native';
import { Colors, Spacing } from '../constants/theme';

interface Props {
  progress: number; // 0.0 to 1.0
  duration: number;
}

export function AudioProgressBar({ progress }: Props) {
  return (
    <View style={styles.container}>
      <View style={styles.track}>
        <View style={[styles.fill, { width: `${Math.min(progress * 100, 100)}%` }]} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    width: '100%',
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.sm,
  },
  track: {
    height: 3,
    backgroundColor: 'rgba(255,255,255,0.2)',
    borderRadius: 2,
    overflow: 'hidden',
  },
  fill: {
    height: '100%',
    backgroundColor: Colors.accent,
    borderRadius: 2,
  },
});
```

- [ ] **Step 3: Create SwipeCard component**

Create `components/SwipeCard.tsx`:

```typescript
import React from 'react';
import { View, Text, StyleSheet, Dimensions } from 'react-native';
import { SwipeFeedSegment } from '../types';
import { Colors, Typography, Spacing } from '../constants/theme';
import { DifficultyBadge } from './DifficultyBadge';

const { height: SCREEN_HEIGHT } = Dimensions.get('window');

interface Props {
  segment: SwipeFeedSegment;
  showTranslation: boolean;
}

export function SwipeCard({ segment, showTranslation }: Props) {
  return (
    <View style={styles.container}>
      {/* Difficulty badge - top right */}
      <View style={styles.topBar}>
        {segment.source_title ? (
          <Text style={styles.sourceTitle} numberOfLines={1}>{segment.source_title}</Text>
        ) : null}
        <DifficultyBadge level={segment.difficulty} />
      </View>

      {/* German text - center */}
      <View style={styles.textContainer}>
        <Text style={styles.germanText}>{segment.german_text}</Text>

        {/* Chinese translation - slides in from below */}
        {showTranslation && segment.chinese_text ? (
          <Text style={styles.chineseText}>{segment.chinese_text}</Text>
        ) : (
          <Text style={styles.hintText}>下滑查看翻译</Text>
        )}
      </View>

      {/* Duration indicator */}
      {segment.duration > 0 && (
        <Text style={styles.duration}>
          {Math.round(segment.duration)}s
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
    paddingHorizontal: Spacing.lg,
    paddingTop: Spacing.xxl,
  },
  topBar: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: Spacing.lg,
  },
  sourceTitle: {
    color: Colors.textSecondary,
    fontSize: Typography.captionSize,
    flex: 1,
    marginRight: Spacing.sm,
  },
  textContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  germanText: {
    color: Colors.textPrimary,
    fontSize: Typography.germanTextSize,
    fontWeight: '600',
    textAlign: 'center',
    lineHeight: Typography.germanTextSize * 1.4,
    marginBottom: Spacing.md,
  },
  chineseText: {
    color: Colors.textSecondary,
    fontSize: Typography.chineseTextSize,
    textAlign: 'center',
    lineHeight: Typography.chineseTextSize * 1.4,
  },
  hintText: {
    color: 'rgba(255,255,255,0.3)',
    fontSize: Typography.captionSize,
    textAlign: 'center',
    marginTop: Spacing.sm,
  },
  duration: {
    color: Colors.textSecondary,
    fontSize: Typography.captionSize,
    textAlign: 'center',
    paddingBottom: Spacing.lg,
  },
});
```

- [ ] **Step 4: Commit**

```bash
cd d:\00_dev\anki-app\anki-swipe-app
git add components/SwipeCard.tsx components/DifficultyBadge.tsx components/AudioProgressBar.tsx
git commit -m "feat: add SwipeCard, DifficultyBadge, and AudioProgressBar components"
```

---

### Task 6: SwipeDeck with gesture handling

**Files:**
- Create: `anki-swipe-app/components/SwipeDeck.tsx`
- Create: `anki-swipe-app/components/RatingOverlay.tsx`

- [ ] **Step 1: Create RatingOverlay component**

Create `components/RatingOverlay.tsx`:

```typescript
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import Animated, { FadeIn, FadeOut } from 'react-native-reanimated';
import { Colors, Typography, Spacing } from '../constants/theme';

interface Props {
  type: 'easy' | 'hard' | 'collect' | null;
}

const CONFIG = {
  easy: { color: Colors.easy, label: '简单' },
  hard: { color: Colors.hard, label: '困难' },
  collect: { color: Colors.collect, label: '已收藏' },
};

export function RatingOverlay({ type }: Props) {
  if (!type) return null;

  const config = CONFIG[type];

  return (
    <Animated.View
      entering={FadeIn.duration(150)}
      exiting={FadeOut.duration(300)}
      style={[styles.container, { borderColor: config.color }]}
    >
      <Text style={[styles.label, { color: config.color }]}>{config.label}</Text>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: {
    position: 'absolute',
    top: '40%',
    alignSelf: 'center',
    borderWidth: 3,
    borderRadius: 16,
    paddingHorizontal: Spacing.xl,
    paddingVertical: Spacing.md,
    backgroundColor: 'rgba(0,0,0,0.7)',
  },
  label: {
    fontSize: Typography.titleSize,
    fontWeight: '800',
    textAlign: 'center',
  },
});
```

- [ ] **Step 2: Create SwipeDeck component with gesture handling**

Create `components/SwipeDeck.tsx`:

```typescript
import React, { useCallback, useState } from 'react';
import { View, StyleSheet, Dimensions } from 'react-native';
import {
  Gesture,
  GestureDetector,
  GestureHandlerRootView,
} from 'react-native-gesture-handler';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  withTiming,
  runOnJS,
} from 'react-native-reanimated';
import { SwipeFeedSegment } from '../types';
import { SWIPE_THRESHOLD } from '../constants/theme';
import { SwipeCard } from './SwipeCard';
import { RatingOverlay } from './RatingOverlay';

const { width: SCREEN_WIDTH, height: SCREEN_HEIGHT } = Dimensions.get('window');

interface Props {
  segments: SwipeFeedSegment[];
  currentIndex: number;
  showTranslation: boolean;
  onSwipeLeft: () => void;  // easy
  onSwipeRight: () => void; // hard
  onSwipeUp: () => void;    // replay
  onSwipeDown: () => void;  // show translation
  onLongPress: () => void;  // collect
}

export function SwipeDeck({
  segments,
  currentIndex,
  showTranslation,
  onSwipeLeft,
  onSwipeRight,
  onSwipeUp,
  onSwipeDown,
  onLongPress,
}: Props) {
  const translateX = useSharedValue(0);
  const translateY = useSharedValue(0);
  const [overlayType, setOverlayType] = useState<'easy' | 'hard' | null>(null);

  const segment = segments[currentIndex];

  const handleSwipeEnd = useCallback(
    (direction: 'left' | 'right' | 'up' | 'down') => {
      translateX.value = withTiming(0, { duration: 200 });
      translateY.value = withTiming(0, { duration: 200 });
      setOverlayType(null);

      switch (direction) {
        case 'left':
          onSwipeLeft();
          break;
        case 'right':
          onSwipeRight();
          break;
        case 'up':
          onSwipeUp();
          break;
        case 'down':
          onSwipeDown();
          break;
      }
    },
    [onSwipeLeft, onSwipeRight, onSwipeUp, onSwipeDown]
  );

  const panGesture = Gesture.Pan()
    .onUpdate((event) => {
      translateX.value = event.translationX;
      translateY.value = event.translationY;

      // Show overlay hint
      if (Math.abs(event.translationX) > SWIPE_THRESHOLD / 2) {
        runOnJS(setOverlayType)(event.translationX < 0 ? 'easy' : 'hard');
      } else {
        runOnJS(setOverlayType)(null);
      }
    })
    .onEnd((event) => {
      const absX = Math.abs(event.translationX);
      const absY = Math.abs(event.translationY);

      if (absX > SWIPE_THRESHOLD && absX > absY) {
        // Horizontal swipe
        if (event.translationX < 0) {
          // Swipe left → easy
          translateX.value = withTiming(-SCREEN_WIDTH, { duration: 200 }, () => {
            runOnJS(handleSwipeEnd)('left');
          });
        } else {
          // Swipe right → hard
          translateX.value = withTiming(SCREEN_WIDTH, { duration: 200 }, () => {
            runOnJS(handleSwipeEnd)('right');
          });
        }
      } else if (absY > SWIPE_THRESHOLD && absY > absX) {
        if (event.translationY < 0) {
          // Swipe up → replay
          runOnJS(handleSwipeEnd)('up');
        } else {
          // Swipe down → show translation
          runOnJS(handleSwipeEnd)('down');
        }
      } else {
        // Not enough — spring back
        translateX.value = withSpring(0);
        translateY.value = withSpring(0);
        runOnJS(setOverlayType)(null);
      }
    });

  const longPressGesture = Gesture.LongPress()
    .minDuration(500)
    .onEnd(() => {
      runOnJS(onLongPress)();
    });

  const composed = Gesture.Simultaneous(panGesture, longPressGesture);

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [
      { translateX: translateX.value },
      { translateY: translateY.value },
    ],
  }));

  if (!segment) {
    return (
      <View style={styles.emptyContainer}>
        {/* Empty state handled by parent */}
      </View>
    );
  }

  return (
    <GestureHandlerRootView style={styles.root}>
      <GestureDetector gesture={composed}>
        <Animated.View style={[styles.cardContainer, animatedStyle]}>
          <SwipeCard segment={segment} showTranslation={showTranslation} />
          <RatingOverlay type={overlayType} />
        </Animated.View>
      </GestureDetector>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
  },
  cardContainer: {
    flex: 1,
  },
  emptyContainer: {
    flex: 1,
    backgroundColor: '#0A0A0A',
  },
});
```

- [ ] **Step 3: Commit**

```bash
cd d:\00_dev\anki-app\anki-swipe-app
git add components/SwipeDeck.tsx components/RatingOverlay.tsx
git commit -m "feat: add SwipeDeck with gesture handling and RatingOverlay"
```

---

### Task 7: Audio service with expo-av

**Files:**
- Create: `anki-swipe-app/services/audioCache.ts`

- [ ] **Step 1: Create audio cache and playback service**

Create `services/audioCache.ts`:

```typescript
import { Audio } from 'expo-av';
import { SwipeFeedSegment } from '../types';

let currentSound: Audio.Sound | null = null;
let currentSegmentId: string | null = null;

export async function playSegmentAudio(
  segment: SwipeFeedSegment,
  onPlaybackComplete?: () => void,
  onProgress?: (progress: number) => void
): Promise<void> {
  if (!segment.audio_url) return;

  // Stop current playback
  await stopAudio();

  try {
    // Set audio mode for playback
    await Audio.setAudioModeAsync({
      allowsRecordingIOS: false,
      playsInSilentModeIOS: true,
      staysActiveInBackground: true,
    });

    const fullUrl = segment.audio_url.startsWith('http')
      ? segment.audio_url
      : `https://anki.3mudi.com${segment.audio_url}`;

    const { sound } = await Audio.Sound.createAsync(
      { uri: fullUrl },
      { shouldPlay: true },
      (status) => {
        if (status.isLoaded) {
          if (onProgress && status.durationMillis > 0) {
            onProgress(status.positionMillis / status.durationMillis);
          }
          if (status.didJustFinish && onPlaybackComplete) {
            onPlaybackComplete();
          }
        }
      }
    );

    currentSound = sound;
    currentSegmentId = segment.id;
  } catch (error) {
    console.error('Audio playback error:', error);
  }
}

export async function stopAudio(): Promise<void> {
  if (currentSound) {
    try {
      await currentSound.stopAsync();
      await currentSound.unloadAsync();
    } catch {
      // Sound may already be unloaded
    }
    currentSound = null;
    currentSegmentId = null;
  }
}

export async function replayAudio(): Promise<void> {
  if (currentSound) {
    try {
      await currentSound.setPositionAsync(0);
      await currentSound.playAsync();
    } catch {
      // Sound may be unloaded
    }
  }
}

export function isPlayingSegment(segmentId: string): boolean {
  return currentSegmentId === segmentId;
}
```

- [ ] **Step 2: Commit**

```bash
cd d:\00_dev\anki-app\anki-swipe-app
git add services/audioCache.ts
git commit -m "feat: add audio playback service with expo-av"
```

---

### Task 8: Navigation and screen layouts

**Files:**
- Create: `anki-swipe-app/app/_layout.tsx`
- Create: `anki-swipe-app/app/index.tsx`
- Create: `anki-swipe-app/app/swipe.tsx`
- Create: `anki-swipe-app/app/login.tsx`
- Create: `anki-swipe-app/app/stats.tsx`
- Create: `anki-swipe-app/app/settings.tsx`

- [ ] **Step 1: Create root layout**

Create `app/_layout.tsx`:

```typescript
import React, { useEffect, useState } from 'react';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { restoreSession } from '../services/auth';
import { useSwipeStore } from '../store/swipeStore';

export default function RootLayout() {
  const [isReady, setIsReady] = useState(false);
  const fetchFeed = useSwipeStore((s) => s.fetchFeed);

  useEffect(() => {
    async function init() {
      await restoreSession();
      await fetchFeed();
      setIsReady(true);
    }
    init();
  }, []);

  if (!isReady) {
    return null; // Splash screen placeholder
  }

  return (
    <>
      <StatusBar style="light" />
      <Stack
        screenOptions={{
          headerShown: false,
          contentStyle: { backgroundColor: '#0A0A0A' },
          animation: 'slide_from_right',
        }}
      />
    </>
  );
}
```

- [ ] **Step 2: Create index (entry redirect)**

Create `app/index.tsx`:

```typescript
import { Redirect } from 'expo-router';

export default function Index() {
  return <Redirect href="/swipe" />;
}
```

- [ ] **Step 3: Create main swipe screen**

Create `app/swipe.tsx`:

```typescript
import React, { useEffect, useCallback, useState, useRef } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useSwipeStore } from '../store/swipeStore';
import { SwipeDeck } from '../components/SwipeDeck';
import { AudioProgressBar } from '../components/AudioProgressBar';
import { playSegmentAudio, stopAudio, replayAudio } from '../services/audioCache';
import { Colors, Spacing, Typography } from '../constants/theme';

export default function SwipeScreen() {
  const {
    segments,
    currentIndex,
    currentLevel,
    totalRated,
    isLoading,
    showTranslation,
    fetchFeed,
    rateCurrent,
    collectCurrent,
    nextSegment,
    toggleTranslation,
    fetchStats,
  } = useSwipeStore();

  const [audioProgress, setAudioProgress] = useState(0);
  const currentSegment = segments[currentIndex];

  // Auto-play audio when segment changes
  useEffect(() => {
    if (currentSegment) {
      setAudioProgress(0);
      playSegmentAudio(currentSegment, () => {
        setAudioProgress(1);
      }, (progress) => {
        setAudioProgress(progress);
      });
    }

    return () => {
      stopAudio();
    };
  }, [currentSegment?.id]);

  const handleSwipeLeft = useCallback(async () => {
    await rateCurrent('easy');
    nextSegment();
  }, [rateCurrent, nextSegment]);

  const handleSwipeRight = useCallback(async () => {
    await rateCurrent('hard');
    nextSegment();
  }, [rateCurrent, nextSegment]);

  const handleSwipeUp = useCallback(() => {
    replayAudio();
  }, []);

  const handleSwipeDown = useCallback(() => {
    toggleTranslation();
  }, [toggleTranslation]);

  const handleLongPress = useCallback(async () => {
    // For now, use a default collection ID
    // In production, show a collection picker
    await collectCurrent('00000000-0000-0000-0000-000000000001');
  }, [collectCurrent]);

  if (isLoading && segments.length === 0) {
    return (
      <SafeAreaView style={styles.centerContainer}>
        <ActivityIndicator size="large" color={Colors.accent} />
        <Text style={styles.loadingText}>加载中...</Text>
      </SafeAreaView>
    );
  }

  if (segments.length === 0) {
    return (
      <SafeAreaView style={styles.centerContainer}>
        <Text style={styles.emptyText}>暂无学习片段</Text>
        <TouchableOpacity style={styles.retryButton} onPress={() => fetchFeed()}>
          <Text style={styles.retryText}>重新加载</Text>
        </TouchableOpacity>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      {/* Top bar */}
      <View style={styles.topBar}>
        <Text style={styles.levelText}>当前级别: {currentLevel}</Text>
        <Text style={styles.ratedText}>已学: {totalRated}</Text>
      </View>

      {/* Swipe deck */}
      <View style={styles.deckContainer}>
        <SwipeDeck
          segments={segments}
          currentIndex={currentIndex}
          showTranslation={showTranslation}
          onSwipeLeft={handleSwipeLeft}
          onSwipeRight={handleSwipeRight}
          onSwipeUp={handleSwipeUp}
          onSwipeDown={handleSwipeDown}
          onLongPress={handleLongPress}
        />
      </View>

      {/* Audio progress */}
      {currentSegment && (
        <AudioProgressBar
          progress={audioProgress}
          duration={currentSegment.duration}
        />
      )}

      {/* Bottom navigation */}
      <View style={styles.bottomNav}>
        <TouchableOpacity onPress={() => fetchStats()}>
          <Text style={styles.navText}>统计</Text>
        </TouchableOpacity>
        <TouchableOpacity onPress={() => {}}>
          <Text style={styles.navText}>收藏</Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  centerContainer: {
    flex: 1,
    backgroundColor: Colors.background,
    justifyContent: 'center',
    alignItems: 'center',
  },
  topBar: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.sm,
  },
  levelText: {
    color: Colors.accent,
    fontSize: Typography.captionSize,
    fontWeight: '600',
  },
  ratedText: {
    color: Colors.textSecondary,
    fontSize: Typography.captionSize,
  },
  deckContainer: {
    flex: 1,
  },
  loadingText: {
    color: Colors.textSecondary,
    marginTop: Spacing.md,
    fontSize: Typography.bodySize,
  },
  emptyText: {
    color: Colors.textPrimary,
    fontSize: Typography.subtitleSize,
    marginBottom: Spacing.lg,
  },
  retryButton: {
    backgroundColor: Colors.accent,
    paddingHorizontal: Spacing.xl,
    paddingVertical: Spacing.md,
    borderRadius: 8,
  },
  retryText: {
    color: '#FFFFFF',
    fontSize: Typography.bodySize,
    fontWeight: '600',
  },
  bottomNav: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    paddingVertical: Spacing.md,
    paddingBottom: Spacing.lg,
  },
  navText: {
    color: Colors.textSecondary,
    fontSize: Typography.bodySize,
  },
});
```

- [ ] **Step 4: Create login screen**

Create `app/login.tsx`:

```typescript
import React, { useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { login } from '../services/auth';
import { useSwipeStore } from '../store/swipeStore';
import { Colors, Spacing, Typography } from '../constants/theme';

export default function LoginScreen() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const router = useRouter();
  const fetchFeed = useSwipeStore((s) => s.fetchFeed);

  const handleLogin = async () => {
    if (!email || !password) {
      Alert.alert('提示', '请输入邮箱和密码');
      return;
    }

    setIsLoading(true);
    try {
      await login(email, password);
      await fetchFeed();
      router.replace('/swipe');
    } catch (err: any) {
      Alert.alert('登录失败', err.message || '请检查邮箱和密码');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.content}>
        <Text style={styles.title}>德语滑动学习</Text>
        <Text style={styles.subtitle}>登录以同步学习进度</Text>

        <TextInput
          style={styles.input}
          placeholder="邮箱"
          placeholderTextColor={Colors.textSecondary}
          value={email}
          onChangeText={setEmail}
          keyboardType="email-address"
          autoCapitalize="none"
        />

        <TextInput
          style={styles.input}
          placeholder="密码"
          placeholderTextColor={Colors.textSecondary}
          value={password}
          onChangeText={setPassword}
          secureTextEntry
        />

        <TouchableOpacity
          style={[styles.button, isLoading && styles.buttonDisabled]}
          onPress={handleLogin}
          disabled={isLoading}
        >
          <Text style={styles.buttonText}>
            {isLoading ? '登录中...' : '登录'}
          </Text>
        </TouchableOpacity>

        <TouchableOpacity onPress={() => router.back()}>
          <Text style={styles.skipText}>跳过，匿名使用</Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  content: {
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: Spacing.xl,
  },
  title: {
    color: Colors.textPrimary,
    fontSize: 32,
    fontWeight: '700',
    textAlign: 'center',
    marginBottom: Spacing.sm,
  },
  subtitle: {
    color: Colors.textSecondary,
    fontSize: Typography.bodySize,
    textAlign: 'center',
    marginBottom: Spacing.xxl,
  },
  input: {
    backgroundColor: Colors.cardBackground,
    color: Colors.textPrimary,
    fontSize: Typography.bodySize,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.md,
    borderRadius: 8,
    marginBottom: Spacing.md,
  },
  button: {
    backgroundColor: Colors.accent,
    paddingVertical: Spacing.md,
    borderRadius: 8,
    alignItems: 'center',
    marginTop: Spacing.sm,
  },
  buttonDisabled: {
    opacity: 0.6,
  },
  buttonText: {
    color: '#FFFFFF',
    fontSize: Typography.bodySize,
    fontWeight: '600',
  },
  skipText: {
    color: Colors.textSecondary,
    fontSize: Typography.captionSize,
    textAlign: 'center',
    marginTop: Spacing.lg,
  },
});
```

- [ ] **Step 5: Create stats screen**

Create `app/stats.tsx`:

```typescript
import React, { useEffect } from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useSwipeStore } from '../store/swipeStore';
import { Colors, Spacing, Typography } from '../constants/theme';

export default function StatsScreen() {
  const { stats, fetchStats } = useSwipeStore();

  useEffect(() => {
    fetchStats();
  }, []);

  return (
    <SafeAreaView style={styles.container}>
      <Text style={styles.title}>学习统计</Text>

      {stats ? (
        <View style={styles.statsContainer}>
          <View style={styles.statRow}>
            <Text style={styles.statLabel}>当前级别</Text>
            <Text style={[styles.statValue, { color: Colors.accent }]}>{stats.current_level}</Text>
          </View>
          <View style={styles.statRow}>
            <Text style={styles.statLabel}>已学片段</Text>
            <Text style={styles.statValue}>{stats.total_rated}</Text>
          </View>
          <View style={styles.statRow}>
            <Text style={styles.statLabel}>标记简单</Text>
            <Text style={[styles.statValue, { color: Colors.easy }]}>{stats.easy_count}</Text>
          </View>
          <View style={styles.statRow}>
            <Text style={styles.statLabel}>标记困难</Text>
            <Text style={[styles.statValue, { color: Colors.hard }]}>{stats.hard_count}</Text>
          </View>
          <View style={styles.statRow}>
            <Text style={styles.statLabel}>连续简单</Text>
            <Text style={styles.statValue}>{stats.consecutive_easy}</Text>
          </View>
          <View style={styles.statRow}>
            <Text style={styles.statLabel}>连续困难</Text>
            <Text style={styles.statValue}>{stats.consecutive_hard}</Text>
          </View>
        </View>
      ) : (
        <Text style={styles.emptyText}>暂无统计数据</Text>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
    paddingHorizontal: Spacing.lg,
  },
  title: {
    color: Colors.textPrimary,
    fontSize: Typography.titleSize,
    fontWeight: '700',
    marginTop: Spacing.lg,
    marginBottom: Spacing.xl,
  },
  statsContainer: {
    backgroundColor: Colors.cardBackground,
    borderRadius: 12,
    padding: Spacing.lg,
  },
  statRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: Spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255,255,255,0.1)',
  },
  statLabel: {
    color: Colors.textSecondary,
    fontSize: Typography.bodySize,
  },
  statValue: {
    color: Colors.textPrimary,
    fontSize: Typography.subtitleSize,
    fontWeight: '600',
  },
  emptyText: {
    color: Colors.textSecondary,
    fontSize: Typography.bodySize,
    textAlign: 'center',
    marginTop: Spacing.xxl,
  },
});
```

- [ ] **Step 6: Create settings screen**

Create `app/settings.tsx`:

```typescript
import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { logout, isLoggedIn } from '../services/auth';
import { useSwipeStore } from '../store/swipeStore';
import { Colors, Spacing, Typography } from '../constants/theme';
import { DIFFICULTY_LEVELS } from '../types';

export default function SettingsScreen() {
  const router = useRouter();
  const { currentLevel, fetchFeed, reset } = useSwipeStore();

  const handleLogout = async () => {
    await logout();
    reset();
    router.replace('/swipe');
  };

  const handleLevelChange = (level: string) => {
    fetchFeed('public', level);
  };

  return (
    <SafeAreaView style={styles.container}>
      <Text style={styles.title}>设置</Text>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>难度级别</Text>
        <View style={styles.levelGrid}>
          {DIFFICULTY_LEVELS.map((level) => (
            <TouchableOpacity
              key={level}
              style={[
                styles.levelButton,
                currentLevel === level && styles.levelButtonActive,
              ]}
              onPress={() => handleLevelChange(level)}
            >
              <Text
                style={[
                  styles.levelText,
                  currentLevel === level && styles.levelTextActive,
                ]}
              >
                {level}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>账户</Text>
        <TouchableOpacity style={styles.menuItem} onPress={() => router.push('/login')}>
          <Text style={styles.menuText}>登录</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.menuItem} onPress={handleLogout}>
          <Text style={[styles.menuText, { color: Colors.hard }]}>退出登录</Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
    paddingHorizontal: Spacing.lg,
  },
  title: {
    color: Colors.textPrimary,
    fontSize: Typography.titleSize,
    fontWeight: '700',
    marginTop: Spacing.lg,
    marginBottom: Spacing.xl,
  },
  section: {
    marginBottom: Spacing.xl,
  },
  sectionTitle: {
    color: Colors.textSecondary,
    fontSize: Typography.captionSize,
    fontWeight: '600',
    textTransform: 'uppercase',
    marginBottom: Spacing.md,
  },
  levelGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.sm,
  },
  levelButton: {
    backgroundColor: Colors.cardBackground,
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.md,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: 'transparent',
  },
  levelButtonActive: {
    borderColor: Colors.accent,
    backgroundColor: 'rgba(108,99,255,0.2)',
  },
  levelText: {
    color: Colors.textPrimary,
    fontSize: Typography.bodySize,
    fontWeight: '600',
  },
  levelTextActive: {
    color: Colors.accent,
  },
  menuItem: {
    paddingVertical: Spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255,255,255,0.1)',
  },
  menuText: {
    color: Colors.textPrimary,
    fontSize: Typography.bodySize,
  },
});
```

- [ ] **Step 7: Commit**

```bash
cd d:\00_dev\anki-app\anki-swipe-app
git add app/_layout.tsx app/index.tsx app/swipe.tsx app/login.tsx app/stats.tsx app/settings.tsx
git commit -m "feat: add all screen layouts with navigation"
```

---

### Task 9: Polish and verify

**Files:**
- Modify: `anki-swipe-app/app.json`
- Modify: `anki-swipe-app/app/_layout.tsx`

- [ ] **Step 1: Update app.json with proper config**

In `app.json`, update the expo config:

```json
{
  "expo": {
    "name": "德语滑动学习",
    "slug": "anki-swipe",
    "version": "1.0.0",
    "orientation": "portrait",
    "icon": "./assets/icon.png",
    "userInterfaceStyle": "dark",
    "scheme": "ankiswipe",
    "splash": {
      "backgroundColor": "#0A0A0A"
    },
    "ios": {
      "supportsTablet": false,
      "bundleIdentifier": "com.3mudi.ankiswipe"
    },
    "android": {
      "adaptiveIcon": {
        "backgroundColor": "#0A0A0A"
      },
      "package": "com.3mudi.ankiswipe"
    },
    "plugins": [
      "expo-router",
      [
        "expo-av",
        {
          "microphonePermission": false
        }
      ]
    ]
  }
}
```

- [ ] **Step 2: Verify TypeScript compilation**

Run:
```bash
cd d:\00_dev\anki-app\anki-swipe-app
npx tsc --noEmit
```

Expected: No errors (or only minor type warnings)

- [ ] **Step 3: Verify Expo can start**

Run:
```bash
cd d:\00_dev\anki-app\anki-swipe-app
npx expo start
```

Expected: Dev server starts without errors

- [ ] **Step 4: Commit**

```bash
cd d:\00_dev\anki-app\anki-swipe-app
git add app.json
git commit -m "chore: update app.json with proper config and permissions"
```

---

## Summary

| Task | Description | Key Files |
|------|-------------|-----------|
| 1 | Initialize Expo project | `anki-swipe-app/` scaffold |
| 2 | Types, constants, API client | `types/`, `constants/`, `services/api.ts` |
| 3 | Auth service | `services/auth.ts` |
| 4 | Zustand store | `store/swipeStore.ts` |
| 5 | UI components | `SwipeCard`, `DifficultyBadge`, `AudioProgressBar` |
| 6 | Gesture handling | `SwipeDeck`, `RatingOverlay` |
| 7 | Audio service | `services/audioCache.ts` |
| 8 | Navigation & screens | `app/` directory |
| 9 | Polish & verify | `app.json`, TypeScript check |
