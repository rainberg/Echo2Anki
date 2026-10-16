import { SwipeFeedResponse, SwipeStatsResponse, SwipeRateRequest, SwipeCollectRequest } from '../types';

const BASE_URL = 'https://anki.3mudi.com/api';

let authToken: string | null = null;

export function setAuthToken(token: string | null) {
  authToken = token;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };
  if (authToken) {
    headers['Authorization'] = `Bearer ${authToken}`;
  }

  const response = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const body = await response.text().catch(() => '');
    throw new Error(`API ${response.status}: ${body || response.statusText}`);
  }

  return response.json();
}

export async function getFeed(source: string = 'public', limit: number = 10, level?: string): Promise<SwipeFeedResponse> {
  const params = new URLSearchParams({ source, limit: String(limit) });
  if (level) params.set('level', level);
  return request<SwipeFeedResponse>(`/swipe/feed?${params}`);
}

export async function rateSegment(data: SwipeRateRequest): Promise<{ rating: string; segment_id: string }> {
  return request('/swipe/rate', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function collectSegment(data: SwipeCollectRequest): Promise<{ collected: boolean; segment_id: string }> {
  return request('/swipe/collect', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function getStats(): Promise<SwipeStatsResponse> {
  return request<SwipeStatsResponse>('/swipe/stats');
}
