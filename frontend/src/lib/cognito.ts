/**
 * Cognito Hosted UI utilities.
 *
 * Two modes, controlled by env vars:
 *   - Hosted UI (production): VITE_COGNITO_DOMAIN is set
 *       → OAuth PKCE redirect flow via the Cognito hosted login page
 *   - Local dev (LocalStack): VITE_COGNITO_DOMAIN is empty
 *       → Direct USER_PASSWORD_AUTH against LocalStack at VITE_LOCALSTACK_URL
 */

const DOMAIN = import.meta.env.VITE_COGNITO_DOMAIN ?? '';
const CLIENT_ID = import.meta.env.VITE_COGNITO_CLIENT_ID ?? '';
const LOCALSTACK_URL = import.meta.env.VITE_LOCALSTACK_URL ?? 'http://localhost:4566';

export const IS_HOSTED_UI = Boolean(DOMAIN && CLIENT_ID);

function getRedirectUri(): string {
  return import.meta.env.VITE_COGNITO_REDIRECT_URI ?? `${window.location.origin}/callback`;
}

// ── PKCE helpers ──────────────────────────────────────────────────────────────

function randomBase64url(byteLen: number): string {
  return btoa(String.fromCharCode(...crypto.getRandomValues(new Uint8Array(byteLen))))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}

async function sha256Base64url(plain: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(plain));
  return btoa(String.fromCharCode(...new Uint8Array(buf)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}

// ── Hosted UI redirect helpers ────────────────────────────────────────────────

/** Redirect the browser to the Cognito Hosted UI login page (PKCE). */
export async function redirectToLogin(): Promise<void> {
  const verifier = randomBase64url(32);
  const challenge = await sha256Base64url(verifier);
  const state = randomBase64url(16);

  sessionStorage.setItem('pkce_verifier', verifier);
  sessionStorage.setItem('pkce_state', state);

  const params = new URLSearchParams({
    response_type: 'code',
    client_id: CLIENT_ID,
    redirect_uri: getRedirectUri(),
    scope: 'openid email profile',
    state,
    code_challenge: challenge,
    code_challenge_method: 'S256',
  });

  window.location.href = `https://${DOMAIN}/login?${params}`;
}

/** Redirect to the Cognito Hosted UI sign-up page. */
export function redirectToSignUp(): void {
  const params = new URLSearchParams({
    response_type: 'code',
    client_id: CLIENT_ID,
    redirect_uri: getRedirectUri(),
    scope: 'openid email profile',
  });
  window.location.href = `https://${DOMAIN}/signup?${params}`;
}

/** Build the Cognito logout URL (clears the Cognito session, redirects home). */
export function buildLogoutUrl(): string {
  const params = new URLSearchParams({
    client_id: CLIENT_ID,
    logout_uri: window.location.origin,
  });
  return `https://${DOMAIN}/logout?${params}`;
}

// ── Token operations ──────────────────────────────────────────────────────────

export interface TokenResult {
  id_token: string;
  access_token: string;
  refresh_token: string;
}

/** Exchange the OAuth authorization code for tokens after the Hosted UI redirect. */
export async function exchangeCodeForTokens(code: string, state: string): Promise<TokenResult> {
  const verifier = sessionStorage.getItem('pkce_verifier') ?? '';
  const savedState = sessionStorage.getItem('pkce_state') ?? '';
  sessionStorage.removeItem('pkce_verifier');
  sessionStorage.removeItem('pkce_state');

  if (state !== savedState) throw new Error('OAuth state mismatch — possible CSRF');

  const body = new URLSearchParams({
    grant_type: 'authorization_code',
    client_id: CLIENT_ID,
    code,
    redirect_uri: getRedirectUri(),
    code_verifier: verifier,
  });

  const resp = await fetch(`https://${DOMAIN}/oauth2/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });
  if (!resp.ok) throw new Error(`Token exchange failed: ${resp.status}`);
  return resp.json();
}

/** Refresh the Cognito ID token using a refresh token. */
export async function refreshCognitoToken(
  refreshToken: string,
): Promise<{ id_token: string; access_token: string }> {
  const tokenUrl = IS_HOSTED_UI
    ? `https://${DOMAIN}/oauth2/token`
    : `${LOCALSTACK_URL}/oauth2/token`;

  const body = new URLSearchParams({
    grant_type: 'refresh_token',
    client_id: CLIENT_ID,
    refresh_token: refreshToken,
  });

  const resp = await fetch(tokenUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });
  if (!resp.ok) throw new Error('Token refresh failed');
  return resp.json();
}

// ── Local dev (LocalStack) ────────────────────────────────────────────────────

/** Authenticate directly against LocalStack Cognito (local dev only). */
export async function localDevLogin(username: string, password: string): Promise<TokenResult> {
  const resp = await fetch(LOCALSTACK_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-amz-json-1.1',
      'X-Amz-Target': 'AWSCognitoIdentityProviderService.InitiateAuth',
    },
    body: JSON.stringify({
      AuthFlow: 'USER_PASSWORD_AUTH',
      ClientId: CLIENT_ID,
      AuthParameters: { USERNAME: username, PASSWORD: password },
    }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error((err as { message?: string }).message ?? 'Login failed');
  }
  const data = await resp.json() as { AuthenticationResult: { IdToken: string; AccessToken: string; RefreshToken: string } };
  return {
    id_token: data.AuthenticationResult.IdToken,
    access_token: data.AuthenticationResult.AccessToken,
    refresh_token: data.AuthenticationResult.RefreshToken,
  };
}

// ── JWT decoding (client-side, no verification) ───────────────────────────────

/** Decode a JWT payload — used client-side to extract Cognito claims. */
export function decodeJwt(token: string): Record<string, unknown> {
  const [, payload] = token.split('.');
  return JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')));
}
