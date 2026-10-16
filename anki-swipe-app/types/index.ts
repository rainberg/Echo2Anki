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
