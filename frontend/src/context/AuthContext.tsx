/**
 * Auth Context with JWT authentication
 * Supports real login with email/password
 */

import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import {
  login as apiLogin,
  logout as apiLogout,
  getCurrentUser,
  isAuthenticated as checkAuth,
  getStoredUser,
  AuthUser,
} from "@/services/api";

interface AuthContextType {
  user: AuthUser | null;
  creatorId: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  selectCreator: (creatorName: string) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const SELECTED_CREATOR_KEY = "clonnect_selected_creator";

// DEMO MODE: Default creator for backwards compatibility
const DEFAULT_CREATOR = "stefano_auto";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [creatorId, setCreatorId] = useState<string | null>(() => {
    // Initialize from localStorage
    return localStorage.getItem(SELECTED_CREATOR_KEY) || DEFAULT_CREATOR;
  });
  const [isLoading, setIsLoading] = useState(true);

  // Check authentication status on mount
  useEffect(() => {
    const checkAuthStatus = async () => {
      if (checkAuth()) {
        try {
          // Try to get user from stored data first
          const storedUser = getStoredUser();
          if (storedUser) {
            setUser(storedUser);
            // If user has creators, select the first one if none selected
            if (storedUser.creators.length > 0 && !creatorId) {
              setCreatorId(storedUser.creators[0].name);
            }
          }
          // Verify token is still valid
          const currentUser = await getCurrentUser();
          setUser(currentUser);
        } catch (error) {
          console.error("Auth check failed:", error);
          // Token invalid, clear auth
          apiLogout();
          setUser(null);
        }
      }
      setIsLoading(false);
    };

    checkAuthStatus();
  }, []);

  const login = async (email: string, password: string) => {
    const response = await apiLogin(email, password);
    setUser(response.user);
    // If user has creators, select the first one
    if (response.user.creators.length > 0) {
      const firstCreator = response.user.creators[0].name;
      setCreatorId(firstCreator);
      localStorage.setItem(SELECTED_CREATOR_KEY, firstCreator);
    }
  };

  const logout = () => {
    apiLogout();
    setUser(null);
    // Keep creatorId for backwards compatibility with demo mode
    setCreatorId(DEFAULT_CREATOR);
    localStorage.setItem(SELECTED_CREATOR_KEY, DEFAULT_CREATOR);
  };

  const selectCreator = (creatorName: string) => {
    setCreatorId(creatorName);
    localStorage.setItem(SELECTED_CREATOR_KEY, creatorName);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        creatorId,
        isAuthenticated: !!user || checkAuth(),
        isLoading,
        login,
        logout,
        selectCreator,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}

export function useCreatorId(): string {
  const { creatorId } = useAuth();
  // For backwards compatibility, always return a valid creator ID
  return creatorId || DEFAULT_CREATOR;
}
