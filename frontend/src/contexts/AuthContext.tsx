import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from "react";
import { authClient } from "../api/client";

interface User {
  id: string;
  email: string;
  username: string;
  full_name: string;
  role: string;
}

interface AuthState {
  user: User | null;
  token: string | null;
  isLoading: boolean;
}

interface AuthActions {
  login: (username: string, password: string) => Promise<void>;
  register: (data: RegisterData) => Promise<void>;
  logout: () => void;
}

interface RegisterData {
  email: string;
  username: string;
  password: string;
  full_name: string;
}

const AuthContext = createContext<(AuthState & AuthActions) | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(
    () => localStorage.getItem("access_token")
  );
  const [isLoading, setIsLoading] = useState(!!localStorage.getItem("access_token"));

  const logout = useCallback(() => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    setToken(null);
    setUser(null);
  }, []);

  useEffect(() => {
    if (!token) return;
    setIsLoading(true);
    authClient
      .GET("/api/v1/auth/me", {})
      .then(({ data, error }) => {
        if (error || !data) { logout(); return; }
        setUser(data as User);
      })
      .finally(() => setIsLoading(false));
  }, [token, logout]);

  const login = useCallback(async (username: string, password: string) => {
    const { data, error } = await authClient.POST("/api/v1/auth/login", {
      body: { username, password },
    });
    if (error || !data) throw new Error("Invalid credentials");
    const t = (data as { access_token: string; refresh_token: string }).access_token;
    const rt = (data as { refresh_token: string }).refresh_token;
    localStorage.setItem("access_token", t);
    localStorage.setItem("refresh_token", rt);
    setToken(t);
  }, []);

  const register = useCallback(async (form: RegisterData) => {
    const { error } = await authClient.POST("/api/v1/auth/register", {
      body: form,
    });
    if (error) throw new Error("Registration failed");
  }, []);

  return (
    <AuthContext.Provider value={{ user, token, isLoading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
