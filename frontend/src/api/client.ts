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
import { refreshCognitoToken } from '../lib/cognito';

const BASE = '';

let isRefreshing = false;
let refreshPromise: Promise<string | null> | null = null;

async function refreshIdToken(): Promise<string | null> {
  const rt = localStorage.getItem('refresh_token');
  if (!rt) return null;
  try {
    const { id_token } = await refreshCognitoToken(rt);
    localStorage.setItem('id_token', id_token);
    return id_token;
  } catch {
    return null;
  }
}

const authMiddleware: Middleware = {
  async onRequest({ request }) {
    const token = localStorage.getItem('id_token');
    if (token) request.headers.set('Authorization', `Bearer ${token}`);
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

    const retried = new Request(request);
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
