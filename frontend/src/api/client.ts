/**
 * Typed API clients for each AeroLink service.
 * Types are auto-generated from OpenAPI specs — run `npm run generate-types`.
 * All calls are routed through the Vite proxy → API gateway (port 8000).
 *
 * Bearer token: Cognito ID token stored in localStorage as 'id_token'.
 * On 401: refresh via Cognito token endpoint, retry once, then redirect to /login.
 */
import createClient, { type Middleware } from 'openapi-fetch';
import type { paths as AuthPaths } from '../types/auth';
import type { paths as FlightPaths } from '../types/flight';
import type { paths as BookingPaths } from '../types/booking';
import type { paths as PaymentPaths } from '../types/payment';
import type { paths as BaggagePaths } from '../types/baggage';
import type { paths as CheckinPaths } from '../types/checkin';
import type { paths as PassengerPaths } from '../types/passenger';
import type { paths as NotificationPaths } from '../types/notification';
import { refreshToken } from '../lib/cognito';

const BASE = '';

let isRefreshing = false;
let refreshPromise: Promise<string | null> | null = null;

async function refreshIdToken(): Promise<string | null> {
  const rt = localStorage.getItem('refresh_token');
  if (!rt) return null;
  try {
    const { id_token } = await refreshToken(rt);
    localStorage.setItem('id_token', id_token);
    return id_token;
  } catch {
    return null;
  }
}

// Clone body bytes before the request is sent so we can retry after a 401.
const _bodyCache = new WeakMap<Request, ArrayBuffer>();

const authMiddleware: Middleware = {
  async onRequest({ request }) {
    const token = localStorage.getItem('id_token');
    if (!token) {
      // No token at all — fire session-expired immediately instead of
      // letting the request fail with 401 and then discovering no refresh token either.
      window.dispatchEvent(new CustomEvent('auth:session-expired'));
      return request;
    }
    request.headers.set('Authorization', `Bearer ${token}`);

    // Cache body bytes for POST/PUT/PATCH so onResponse can retry.
    if (request.body && !_bodyCache.has(request)) {
      try {
        const cloned = request.clone();
        const bytes = await cloned.arrayBuffer();
        _bodyCache.set(request, bytes);
      } catch { /* non-critical */ }
    }

    return request;
  },

  async onResponse({ response, request }) {
    if (response.status !== 401) return response;

    // Avoid refresh loops on auth endpoints
    if (request.url.includes('/auth/login') || request.url.includes('/auth/refresh')) {
      return response;
    }

    // Deduplicate concurrent refresh calls
    if (!isRefreshing) {
      isRefreshing = true;
      refreshPromise = refreshIdToken().finally(() => {
        isRefreshing = false;
        refreshPromise = null;
      });
    }

    const newToken = await refreshPromise;
    if (!newToken) {
      localStorage.removeItem('id_token');
      localStorage.removeItem('refresh_token');
      // Soft navigation via event — avoids a hard page reload that looks like a crash
      window.dispatchEvent(new CustomEvent('auth:session-expired'));
      return response;
    }

    // Rebuild the request with the refreshed token, restoring the body if needed.
    const cachedBody = _bodyCache.get(request);
    const retried = new Request(request.url, {
      method: request.method,
      headers: new Headers(request.headers),
      body: cachedBody ?? null,
      credentials: request.credentials,
      mode: request.mode,
    });
    retried.headers.set('Authorization', `Bearer ${newToken}`);
    return fetch(retried);
  },
};

function makeClient<T extends Record<string, unknown>>() {
  const client = createClient<T>({ baseUrl: BASE });
  client.use(authMiddleware as Middleware);
  return client;
}

export const authClient         = makeClient<AuthPaths>();
export const flightClient       = makeClient<FlightPaths>();
export const bookingClient      = makeClient<BookingPaths>();
export const paymentClient      = makeClient<PaymentPaths>();
export const baggageClient      = makeClient<BaggagePaths>();
export const checkinClient      = makeClient<CheckinPaths>();
export const passengerClient    = makeClient<PassengerPaths>();
export const notificationClient = makeClient<NotificationPaths>();
