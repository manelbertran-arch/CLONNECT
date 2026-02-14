import { apiFetch, setAuthToken, setStoredUser, clearAuthToken, getAuthToken } from "./client";
import type { AuthUser, LoginResponse } from "./client";

export type { AuthUser, LoginResponse };

export async function login(email: string, password: string): Promise<LoginResponse> {
  const response = await apiFetch<LoginResponse>(
    "/auth/login",
    { method: "POST", body: JSON.stringify({ email, password }) },
    true
  );
  setAuthToken(response.access_token);
  setStoredUser(response.user);
  return response;
}

export async function register(email: string, password: string, name?: string): Promise<LoginResponse> {
  const response = await apiFetch<LoginResponse>(
    "/auth/register",
    { method: "POST", body: JSON.stringify({ email, password, name }) },
    true
  );
  setAuthToken(response.access_token);
  setStoredUser(response.user);
  return response;
}

export async function getCurrentUser(): Promise<AuthUser> {
  const response = await apiFetch<{
    id: string; email: string; name: string | null; is_active: boolean;
    creators: { id: string; name: string; clone_name: string; role: string }[];
  }>("/auth/me");
  const user: AuthUser = { id: response.id, email: response.email, name: response.name, creators: response.creators };
  setStoredUser(user);
  return user;
}

export function logout(): void {
  clearAuthToken();
}

export function isAuthenticated(): boolean {
  return !!getAuthToken();
}
