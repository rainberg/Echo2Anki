import React, { useEffect } from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { useSwipeStore } from '../store/swipeStore';
import { Colors, Spacing, Typography } from '../constants/theme';

export default function StatsScreen() {
  const router = useRouter();
  const { stats, fetchStats } = useSwipeStore();

  useEffect(() => {
    fetchStats();
  }, []);

  return (
    <SafeAreaView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()}>
          <Text style={styles.backText}>← 返回</Text>
        </TouchableOpacity>
        <Text style={styles.title}>学习统计</Text>
        <View style={{ width: 60 }} />
      </View>

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
        <View style={styles.emptyContainer}>
          <Text style={styles.emptyText}>暂无统计数据</Text>
          <Text style={styles.emptyHint}>开始滑动学习后这里会显示你的进度</Text>
        </View>
      )}
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
  statsContainer: {
    backgroundColor: Colors.cardBackground,
    borderRadius: 12,
    padding: Spacing.lg,
    marginHorizontal: Spacing.lg,
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
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  emptyText: {
    color: Colors.textPrimary,
    fontSize: Typography.subtitleSize,
    marginBottom: Spacing.sm,
  },
  emptyHint: {
    color: Colors.textSecondary,
    fontSize: Typography.captionSize,
  },
});
