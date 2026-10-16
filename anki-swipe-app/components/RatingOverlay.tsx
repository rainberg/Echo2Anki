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
