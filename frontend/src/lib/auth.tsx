import React, { createContext, useContext, useState, useEffect } from "react";
import { api } from "./api";

export interface User {
  id: number;
  email: string;
  full_name: string;
  avatar_url: string | null;
  role: "customer" | "expert" | "admin";
  tenant_id?: string;
}

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  login: (access: string, refresh: string) => Promise<User | null>;
  logout: () => Promise<void>;
  loginWithGoogle: () => Promise<void>;
  refreshUser: () => Promise<User | null>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const fetchUser = async (): Promise<User | null> => {
    try {
      const response = await api.get<User>("/auth/me");
      setUser(response.data);
      return response.data;
    } catch {
      if (typeof window !== "undefined") {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
      }
      setUser(null);
      return null;
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
    if (token) {
      fetchUser();
    } else {
      setIsLoading(false);
    }
  }, []);

  const login = async (access: string, refresh: string): Promise<User | null> => {
    if (typeof window !== "undefined") {
      localStorage.setItem("access_token", access);
      localStorage.setItem("refresh_token", refresh);
    }
    return await fetchUser();
  };

  const logout = async () => {
    const refreshToken =
      typeof window !== "undefined" ? localStorage.getItem("refresh_token") : null;
    try {
      if (refreshToken) {
        await api.post("/auth/logout", { refresh_token: refreshToken });
      }
    } catch {
      // Ignore logout API failures
    } finally {
      if (typeof window !== "undefined") {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        setUser(null);
        window.location.href = "/login";
      }
    }
  };

  const loginWithGoogle = async () => {
    try {
      const response = await api.get<{ url: string }>("/auth/google/login");
      if (response.data?.url && typeof window !== "undefined") {
        window.location.href = response.data.url;
      }
    } catch (err) {
      console.error("Failed to initiate Google OAuth:", err);
      throw err;
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        login,
        logout,
        loginWithGoogle,
        refreshUser: fetchUser,
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
