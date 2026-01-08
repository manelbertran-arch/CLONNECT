/**
 * Simple Auth Context for multi-creator support
 * Stores creator_id in localStorage for persistence
 */

import { createContext, useContext, useState, useEffect, ReactNode } from "react";

interface AuthContextType {
  creatorId: string | null;
  isAuthenticated: boolean;
  login: (creatorId: string) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const STORAGE_KEY = "clonnect_creator_id";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [creatorId, setCreatorId] = useState<string | null>(() => {
    // Initialize from localStorage
    return localStorage.getItem(STORAGE_KEY);
  });

  const login = (id: string) => {
    localStorage.setItem(STORAGE_KEY, id);
    setCreatorId(id);
  };

  const logout = () => {
    localStorage.removeItem(STORAGE_KEY);
    setCreatorId(null);
  };

  return (
    <AuthContext.Provider
      value={{
        creatorId,
        isAuthenticated: !!creatorId,
        login,
        logout,
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
  if (!creatorId) {
    throw new Error("No creator logged in");
  }
  return creatorId;
}
