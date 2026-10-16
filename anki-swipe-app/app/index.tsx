import React, { useEffect, useCallback, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ActivityIndicator, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { useSwipeStore } from '../store/swipeStore';
import { SwipeDeck } from '../components/SwipeDeck';
import { AudioProgressBar } from '../components/AudioProgressBar';
import { playSegmentAudio, stopAudio, replayAudio } from '../services/audioCache';
import { isLoggedIn } from '../services/auth';
import { Colors, Spacing, Typography } from '../constants/theme';

export default function SwipeScreen() {
  const router = useRouter();
  const {
    segments,
    currentIndex,
    currentLevel,
    totalRated,
    isLoading,
    showTranslation,
    source,
    fetchFeed,
    setSource,
    rateCurrent,
    collectCurrent,
    nextSegment,
    toggleTranslation,
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
      {/* Top bar with source toggle */}
      <View style={styles.topBar}>
        <View style={styles.sourceToggle}>
          <TouchableOpacity
            style={[styles.sourceButton, source === 'public' && styles.sourceButtonActive]}
            onPress={() => setSource('public')}
          >
            <Text style={[styles.sourceText, source === 'public' && styles.sourceTextActive]}>公共库</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.sourceButton, source === 'mine' && styles.sourceButtonActive]}
            onPress={async () => {
              if (source !== 'mine') {
                const loggedIn = await isLoggedIn();
                if (!loggedIn) {
                  Alert.alert('需要登录', '查看个人片段需要登录账户', [
                    { text: '取消', style: 'cancel' },
                    { text: '去登录', onPress: () => router.push('/login') },
                  ]);
                  return;
                }
                setSource('mine');
              }
            }}
          >
            <Text style={[styles.sourceText, source === 'mine' && styles.sourceTextActive]}>我的片段</Text>
          </TouchableOpacity>
        </View>
        <View style={styles.statsRow}>
          <Text style={styles.levelText}>{currentLevel}</Text>
          <Text style={styles.ratedText}>已学 {totalRated}</Text>
        </View>
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
        <TouchableOpacity style={styles.navItem} onPress={() => router.push('/stats')}>
          <Text style={styles.navIcon}>📊</Text>
          <Text style={styles.navLabel}>统计</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.navItem} onPress={() => router.push('/settings')}>
          <Text style={styles.navIcon}>⚙️</Text>
          <Text style={styles.navLabel}>设置</Text>
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
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.sm,
  },
  sourceToggle: {
    flexDirection: 'row',
    backgroundColor: Colors.cardBackground,
    borderRadius: 8,
    padding: 2,
    marginBottom: Spacing.sm,
  },
  sourceButton: {
    flex: 1,
    paddingVertical: Spacing.sm,
    alignItems: 'center',
    borderRadius: 6,
  },
  sourceButtonActive: {
    backgroundColor: Colors.accent,
  },
  sourceText: {
    color: Colors.textSecondary,
    fontSize: Typography.captionSize,
    fontWeight: '600',
  },
  sourceTextActive: {
    color: '#FFFFFF',
  },
  statsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
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
    paddingVertical: Spacing.sm,
    paddingBottom: Spacing.md,
  },
  navItem: {
    alignItems: 'center',
    paddingVertical: Spacing.xs,
    paddingHorizontal: Spacing.lg,
  },
  navIcon: {
    fontSize: 20,
    marginBottom: 2,
  },
  navLabel: {
    color: Colors.textSecondary,
    fontSize: Typography.captionSize,
  },
});
