import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from 'react';
import {
  IS_HOSTED_UI,
  buildLogoutUrl,
  refreshToken,
  decodeJwt,
  redirectToLogin,
} from '../lib/cognito';

interface User {
  id: string;
  email: string;
  username: string;
  full_name: string;
  role: string;
  groups: string[];
}

interface AuthState {
  user: User | null;
  token: string | null;
  isLoading: boolean;
}

interface AuthActions {
  loginWithCognito: () => void;
  logout: () => void;
  setTokens: (idToken: string, refreshToken: string) => void;
}

const AuthContext = createContext<(AuthState & AuthActions) | null>(null);

function claimsToUser(claims: Record<string, unknown>): User {
  const groups = (claims['cognito:groups'] as string[] | undefined) ?? [];
  const role = groups[0] ?? (claims['role'] as string) ?? 'passenger';
  const fullName =
    (claims['name'] as string) ||
    [claims['given_name'], claims['family_name']].filter(Boolean).join(' ') ||
    (claims['cognito:username'] as string) ||
    (claims['username'] as string) ||
    '';
  return {
    id: (claims['sub'] as string) ?? '',
    email: (claims['email'] as string) ?? '',
    username:
      (claims['cognito:username'] as string) ??
      (claims['username'] as string) ??
      (claims['sub'] as string) ?? '',
    full_name: fullName,
    role,
    groups,
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const clearAuth = useCallback(() => {
    localStorage.removeItem('id_token');
    localStorage.removeItem('refresh_token');
    setToken(null);
    setUser(null);
  }, []);

  const logout = useCallback(() => {
    clearAuth();
    if (IS_HOSTED_UI) {
      window.location.href = buildLogoutUrl();
    }
  }, [clearAuth]);

  // Redirect to login when the API client detects an unrecoverable 401
  useEffect(() => {
    function handleSessionExpired() {
      clearAuth();
      window.location.href = '/login';
    }
    window.addEventListener('auth:session-expired', handleSessionExpired);
    return () => window.removeEventListener('auth:session-expired', handleSessionExpired);
  }, [clearAuth]);

  // Hydrate from localStorage on mount, refresh if expired
  useEffect(() => {
    const stored = localStorage.getItem('id_token');
    if (!stored) { setIsLoading(false); return; }

    try {
      const claims = decodeJwt(stored);
      const expMs = ((claims['exp'] as number) ?? 0) * 1000;

      if (Date.now() < expMs) {
        setToken(stored);
        setUser(claimsToUser(claims));
        setIsLoading(false);
        return;
      }

      // Expired — attempt silent refresh
      const rt = localStorage.getItem('refresh_token');
      if (!rt) { clearAuth(); setIsLoading(false); return; }

      refreshToken(rt)
        .then(({ id_token }) => {
          localStorage.setItem('id_token', id_token);
          setToken(id_token);
          setUser(claimsToUser(decodeJwt(id_token)));
        })
        .catch(clearAuth)
        .finally(() => setIsLoading(false));
    } catch {
      clearAuth();
      setIsLoading(false);
    }
  }, [clearAuth]);

  /** In hosted UI mode: redirect to Cognito. In local dev: LoginPage handles form directly. */
  const loginWithCognito = useCallback(() => {
    redirectToLogin();
  }, []);

  /** Called by CallbackPage (hosted UI) or LoginPage (local dev) after obtaining tokens. */
  const setTokens = useCallback((idToken: string, refreshToken: string) => {
    localStorage.setItem('id_token', idToken);
    localStorage.setItem('refresh_token', refreshToken);
    setToken(idToken);
    try { setUser(claimsToUser(decodeJwt(idToken))); } catch { /* malformed */ }

    // Ensure a DB user record exists for this Cognito identity.
    // Fire-and-forget: login proceeds even if this fails.
    fetch('/api/v1/auth/cognito-sync', {
      method: 'POST',
      headers: { Authorization: `Bearer ${idToken}` },
    }).catch(() => { /* non-blocking */ });
  }, []);

  return (
    <AuthContext.Provider value={{ user, token, isLoading, loginWithCognito, logout, setTokens }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}
