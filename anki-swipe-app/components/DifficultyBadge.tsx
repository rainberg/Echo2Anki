import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Colors, Typography, Spacing } from '../constants/theme';

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
