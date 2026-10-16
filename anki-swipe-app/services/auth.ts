import * as SecureStore from 'expo-secure-store';
import { setAuthToken } from './api';
import { UserProfile } from '../types';

const AUTH_SERVICE_URL = 'https://auth.3mudi.com';
const TOKEN_KEY = 'anki_access_token';
const REFRESH_TOKEN_KEY = 'anki_refresh_token';

export async function login(email: string, password: string): Promise<UserProfile> {
  const response = await fetch(`${AUTH_SERVICE_URL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });

  if (!response.ok) {
    const body = await response.text().catch(() => '');
    throw new Error(`Login failed: ${body || response.statusText}`);
  }

  const data = await response.json();
  const accessToken = data.access_token;
  const refreshToken = data.refresh_token;

  // Store tokens
  await SecureStore.setItemAsync(TOKEN_KEY, accessToken);
  if (refreshToken) {
    await SecureStore.setItemAsync(REFRESH_TOKEN_KEY, refreshToken);
  }

  // Set for API client
  setAuthToken(accessToken);

  // Get user profile
  return getUserProfile(accessToken);
}

export async function restoreSession(): Promise<UserProfile | null> {
  try {
    const token = await SecureStore.getItemAsync(TOKEN_KEY);
    if (!token) return null;

    // Verify token is still valid
    const response = await fetch(`${AUTH_SERVICE_URL}/api/auth/verify`, {
      headers: { Authorization: `Bearer ${token}` },
    });

    if (!response.ok) {
      // Token expired, try refresh
      const refreshed = await tryRefreshToken();
      if (!refreshed) {
        await logout();
        return null;
      }
      return getUserProfile(refreshed);
    }

    setAuthToken(token);
    return getUserProfile(token);
  } catch {
    return null;
  }
}

async function tryRefreshToken(): Promise<string | null> {
  try {
    const refreshToken = await SecureStore.getItemAsync(REFRESH_TOKEN_KEY);
    if (!refreshToken) return null;

    const response = await fetch(`${AUTH_SERVICE_URL}/api/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (!response.ok) return null;

    const data = await response.json();
    const newAccessToken = data.access_token;
    await SecureStore.setItemAsync(TOKEN_KEY, newAccessToken);
    if (data.refresh_token) {
      await SecureStore.setItemAsync(REFRESH_TOKEN_KEY, data.refresh_token);
    }
    setAuthToken(newAccessToken);
    return newAccessToken;
  } catch {
    return null;
  }
}

async function getUserProfile(token: string): Promise<UserProfile> {
  const response = await fetch(`${AUTH_SERVICE_URL}/api/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!response.ok) {
    throw new Error('Failed to get user profile');
  }

  return response.json();
}

export async function logout(): Promise<void> {
  await SecureStore.deleteItemAsync(TOKEN_KEY);
  await SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY);
  setAuthToken(null);
}

export async function isLoggedIn(): Promise<boolean> {
  const token = await SecureStore.getItemAsync(TOKEN_KEY);
  return token !== null;
}
