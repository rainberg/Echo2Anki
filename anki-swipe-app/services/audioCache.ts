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
          if (onProgress && status.durationMillis && status.durationMillis > 0) {
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
