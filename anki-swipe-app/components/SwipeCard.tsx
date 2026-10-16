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
