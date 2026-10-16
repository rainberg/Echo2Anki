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
