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
    return null;
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
