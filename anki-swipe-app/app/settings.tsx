import React, { useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { logout, isLoggedIn as checkLoggedIn } from '../services/auth';
import { useSwipeStore } from '../store/swipeStore';
import { Colors, Spacing, Typography } from '../constants/theme';
import { DIFFICULTY_LEVELS } from '../types';

export default function SettingsScreen() {
  const router = useRouter();
  const { currentLevel, fetchFeed, reset } = useSwipeStore();
  const [loggedIn, setLoggedIn] = useState(false);

  useEffect(() => {
    checkLoggedIn().then(setLoggedIn);
  }, []);

  const handleLogout = async () => {
    await logout();
    reset();
    setLoggedIn(false);
    router.replace('/');
  };

  const handleLevelChange = (level: string) => {
    fetchFeed('public', level);
  };

  return (
    <SafeAreaView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()}>
          <Text style={styles.backText}>← 返回</Text>
        </TouchableOpacity>
        <Text style={styles.title}>设置</Text>
        <View style={{ width: 60 }} />
      </View>

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
        {loggedIn ? (
          <>
            <View style={styles.statusRow}>
              <Text style={styles.statusText}>已登录</Text>
              <View style={styles.statusDot} />
            </View>
            <TouchableOpacity style={styles.menuItem} onPress={handleLogout}>
              <Text style={[styles.menuText, { color: Colors.hard }]}>退出登录</Text>
            </TouchableOpacity>
          </>
        ) : (
          <TouchableOpacity style={styles.menuItem} onPress={() => router.push('/login')}>
            <Text style={[styles.menuText, { color: Colors.accent }]}>登录账户</Text>
          </TouchableOpacity>
        )}
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>手势说明</Text>
        <View style={styles.guideContainer}>
          <View style={styles.guideRow}>
            <Text style={styles.gestureText}>← 左滑</Text>
            <Text style={styles.guideDesc}>标记简单，下一条</Text>
          </View>
          <View style={styles.guideRow}>
            <Text style={styles.gestureText}>→ 右滑</Text>
            <Text style={styles.guideDesc}>标记困难，下一条</Text>
          </View>
          <View style={styles.guideRow}>
            <Text style={styles.gestureText}>↑ 上滑</Text>
            <Text style={styles.guideDesc}>重播当前音频</Text>
          </View>
          <View style={styles.guideRow}>
            <Text style={styles.gestureText}>↓ 下滑</Text>
            <Text style={styles.guideDesc}>显示/隐藏翻译</Text>
          </View>
          <View style={styles.guideRow}>
            <Text style={styles.gestureText}>长按</Text>
            <Text style={styles.guideDesc}>收藏当前片段</Text>
          </View>
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.md,
  },
  backText: {
    color: Colors.accent,
    fontSize: Typography.bodySize,
    width: 60,
  },
  title: {
    color: Colors.textPrimary,
    fontSize: Typography.subtitleSize,
    fontWeight: '700',
  },
  section: {
    marginBottom: Spacing.xl,
    paddingHorizontal: Spacing.lg,
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
  statusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    paddingVertical: Spacing.md,
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: Colors.easy,
  },
  statusText: {
    color: Colors.easy,
    fontSize: Typography.bodySize,
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
  guideContainer: {
    backgroundColor: Colors.cardBackground,
    borderRadius: 12,
    padding: Spacing.lg,
  },
  guideRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: Spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255,255,255,0.05)',
  },
  gestureText: {
    color: Colors.accent,
    fontSize: Typography.bodySize,
    fontWeight: '600',
    fontFamily: 'monospace',
  },
  guideDesc: {
    color: Colors.textSecondary,
    fontSize: Typography.bodySize,
  },
});
