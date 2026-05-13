/**
 * Typed API clients for each AeroLink service.
 * Types are auto-generated from OpenAPI specs — run `npm run generate-types`.
 * All calls are routed through the Vite proxy → API gateway (port 8000).
 */
import createClient, { type Middleware } from "openapi-fetch";
import type { paths as AuthPaths } from "../types/auth";
import type { paths as FlightPaths } from "../types/flight";
import type { paths as BookingPaths } from "../types/booking";
import type { paths as PaymentPaths } from "../types/payment";
import type { paths as BaggagePaths } from "../types/baggage";
import type { paths as CheckinPaths } from "../types/checkin";
import type { paths as PassengerPaths } from "../types/passenger";
import type { paths as NotificationPaths } from "../types/notification";

const BASE = "";

let isRefreshing = false;
let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = localStorage.getItem("refresh_token");
  if (!refreshToken) return null;

  try {
    const res = await fetch("/api/v1/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!res.ok) return null;
    const data = await res.json();
    const newToken: string = data.access_token;
    if (newToken) {
      localStorage.setItem("access_token", newToken);
      if (data.refresh_token) localStorage.setItem("refresh_token", data.refresh_token);
    }
    return newToken ?? null;
  } catch {
    return null;
  }
}

const authMiddleware: Middleware = {
  async onRequest({ request }) {
    const token = localStorage.getItem("access_token");
    if (token) request.headers.set("Authorization", `Bearer ${token}`);
    return request;
  },

  async onResponse({ response, request }) {
    if (response.status !== 401) return response;

    // Don't try to refresh the token if we're already on the login/refresh endpoint
    const url = request.url;
    if (url.includes("/auth/login") || url.includes("/auth/refresh")) return response;

    // Deduplicate concurrent refresh calls
    if (!isRefreshing) {
      isRefreshing = true;
      refreshPromise = refreshAccessToken().finally(() => {
        isRefreshing = false;
        refreshPromise = null;
      });
    }

    const newToken = await refreshPromise;
    if (!newToken) {
      // Refresh failed — clear storage and redirect to login
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
      window.location.href = "/login";
      return response;
    }

    // Retry original request with fresh token
    const retried = new Request(request, {});
    retried.headers.set("Authorization", `Bearer ${newToken}`);
    return fetch(retried);
  },
};

function makeClient<T extends Record<string, unknown>>() {
  const client = createClient<T>({ baseUrl: BASE });
  client.use(authMiddleware as Middleware);
  return client;
}

export const authClient        = makeClient<AuthPaths>();
export const flightClient      = makeClient<FlightPaths>();
export const bookingClient     = makeClient<BookingPaths>();
export const paymentClient     = makeClient<PaymentPaths>();
export const baggageClient     = makeClient<BaggagePaths>();
export const checkinClient     = makeClient<CheckinPaths>();
export const passengerClient   = makeClient<PassengerPaths>();
export const notificationClient = makeClient<NotificationPaths>();
