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

const BASE = "/api";

const authMiddleware: Middleware = {
  async onRequest({ request }) {
    const token = localStorage.getItem("access_token");
    if (token) request.headers.set("Authorization", `Bearer ${token}`);
    return request;
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
