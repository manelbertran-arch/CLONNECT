/**
 * API Client - Base configuration, fetch wrapper, auth helpers
 */

import type {
  DashboardOverview,
  ConversationsResponse,
  LeadsResponse,
  MetricsResponse,
  CreatorConfig,
  ToggleResponse,
  Product,
  FollowerDetailResponse,
  RevenueStatsResponse,
  PurchasesResponse,
  BookingsResponse,
  CalendarStatsResponse,
  BookingLinksResponse,
} from "@/types/api";

// Re-export types that other modules use from @/types/api
export type {
  DashboardOverview,
  ConversationsResponse,
  LeadsResponse,
  MetricsResponse,
  CreatorConfig,
  ToggleResponse,
  Product,
  FollowerDetailResponse,
  RevenueStatsResponse,
  PurchasesResponse,
  BookingsResponse,
  CalendarStatsResponse,
  BookingLinksResponse,
};

// API Base URL - empty string means same origin (for Railway deployment)
export const API_URL = import.meta.env.VITE_API_URL || "";

// Auth token storage key
const AUTH_TOKEN_KEY = "clonnect_auth_token";
const AUTH_USER_KEY = "clonnect_auth_user";

// Auth types
export interface AuthUser {
  id: string;
  email: string;
  name: string | null;
  creators: { id: string; name: string; clone_name: string; role: string }[];
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

// Get auth token from localStorage
export function getAuthToken(): string | null {
  return localStorage.getItem(AUTH_TOKEN_KEY);
}

// Set auth token in localStorage
export function setAuthToken(token: string): void {
  localStorage.setItem(AUTH_TOKEN_KEY, token);
}

// Clear auth token
export function clearAuthToken(): void {
  localStorage.removeItem(AUTH_TOKEN_KEY);
  localStorage.removeItem(AUTH_USER_KEY);
}

// Get stored user
export function getStoredUser(): AuthUser | null {
  const user = localStorage.getItem(AUTH_USER_KEY);
  return user ? JSON.parse(user) : null;
}

// Set stored user
export function setStoredUser(user: AuthUser): void {
  localStorage.setItem(AUTH_USER_KEY, JSON.stringify(user));
}

// P1 FIX: Dynamic creator ID from localStorage/auth
const DEFAULT_CREATOR_ID = import.meta.env.VITE_CREATOR_ID || "fitpack_global";
const CREATOR_ID_KEY = "clonnect_selected_creator";
const LEGACY_CREATOR_ID_KEY = "creator_id";

export function getCreatorId(): string {
  const stored = localStorage.getItem(CREATOR_ID_KEY);
  if (stored) {
    return stored;
  }
  const legacy = localStorage.getItem(LEGACY_CREATOR_ID_KEY);
  if (legacy) {
    localStorage.setItem(CREATOR_ID_KEY, legacy);
    return legacy;
  }
  return DEFAULT_CREATOR_ID;
}

export function setCreatorId(creatorId: string): void {
  localStorage.setItem(CREATOR_ID_KEY, creatorId);
  localStorage.setItem(LEGACY_CREATOR_ID_KEY, creatorId);
}

export function clearCreatorId(): void {
  localStorage.removeItem(CREATOR_ID_KEY);
  localStorage.removeItem(LEGACY_CREATOR_ID_KEY);
}

// Legacy export for components that haven't been updated yet
export const CREATOR_ID = getCreatorId();

/**
 * Generic fetch wrapper with error handling
 */
export async function apiFetch<T>(
  endpoint: string,
  options: RequestInit = {},
  skipAuth: boolean = false
): Promise<T> {
  const url = `${API_URL}${endpoint}`;

  const defaultHeaders: HeadersInit = {
    "Content-Type": "application/json",
  };

  const token = getAuthToken();
  if (token && !skipAuth) {
    (defaultHeaders as Record<string, string>)["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(url, {
    ...options,
    headers: {
      ...defaultHeaders,
      ...options.headers,
    },
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    let errorMessage = `API Error: ${response.status}`;
    if (errorData.detail) {
      if (Array.isArray(errorData.detail)) {
        errorMessage = errorData.detail.map((e: any) => `${e.loc?.join('.')}: ${e.msg}`).join(', ');
      } else {
        errorMessage = String(errorData.detail);
      }
    }
    console.error(`API Error ${response.status}:`, errorData);
    throw new Error(errorMessage);
  }

  return response.json();
}

/**
 * Simple axios-like API wrapper for cleaner syntax
 */
export const api = {
  async get<T = any>(endpoint: string): Promise<{ data: T }> {
    const data = await apiFetch<T>(endpoint);
    return { data };
  },

  async post<T = any>(endpoint: string, body?: any): Promise<{ data: T }> {
    const data = await apiFetch<T>(endpoint, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    });
    return { data };
  },

  async put<T = any>(endpoint: string, body?: any): Promise<{ data: T }> {
    const data = await apiFetch<T>(endpoint, {
      method: "PUT",
      body: body ? JSON.stringify(body) : undefined,
    });
    return { data };
  },

  async delete<T = any>(endpoint: string): Promise<{ data: T }> {
    const data = await apiFetch<T>(endpoint, {
      method: "DELETE",
    });
    return { data };
  },
};
