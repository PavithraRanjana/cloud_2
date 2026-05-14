import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { bookingClient, paymentClient, flightClient } from "../api/client";

interface Booking {
  id: string;
  booking_reference: string;
  flight_id: string;
  passenger_name: string;
  first_name?: string;
  last_name?: string;
  cabin_class: string;
  num_passengers: number;
  total_price: number;
  status: string;
  seat_numbers?: string;
  trip_type: string;
  created_at: string;
}

interface Flight {
  id: string;
  flight_number: string;
  airline: string;
  origin: string;
  destination: string;
  departure_date: string;
  departure_time: string;
  arrival_date: string;
  arrival_time: string;
  status: string;
  gate: string | null;
}

interface Payment {
  id: string;
  amount: number;
  currency: string;
  status: string;
  payment_method: string;
  card_last_four?: string;
  transaction_ref?: string;
  created_at: string;
}

function fmt(t: string) {
  const [h, m] = t.slice(0, 5).split(":");
  const hn = parseInt(h, 10);
  return `${hn % 12 || 12}:${m} ${hn >= 12 ? "PM" : "AM"}`;
}
function fmtDate(d: string) {
  return new Date(d + "T00:00:00").toLocaleDateString("en-US", {
    month: "short", day: "numeric", year: "numeric",
  });
}

const BOOKING_STATUS: Record<string, string> = {
  pending:           "bg-yellow-50 text-yellow-700 border-yellow-200",
  confirmed:         "bg-blue-50   text-blue-700   border-blue-200",
  paid:              "bg-emerald-50 text-emerald-700 border-emerald-200",
  "payment-pending": "bg-yellow-50 text-yellow-700 border-yellow-200",
  "checked-in":      "bg-sky-50    text-sky-700    border-sky-200",
  completed:         "bg-gray-100  text-gray-500   border-gray-200",
  cancelled:         "bg-red-50    text-red-600    border-red-200",
};

const PAYMENT_STATUS: Record<string, string> = {
  completed: "text-emerald-600",
  pending:   "text-yellow-600",
  failed:    "text-red-500",
  refunded:  "text-gray-500",
};

const CABIN_COLOUR: Record<string, string> = {
  economy:  "bg-emerald-50 text-emerald-700 border-emerald-200",
  business: "bg-amber-50   text-amber-700   border-amber-200",
  first:    "bg-purple-50  text-purple-700  border-purple-200",
};

function BookingCard({ booking }: { booking: Booking }) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [showPayment, setShowPayment] = useState(false);

  const { data: flight } = useQuery<Flight>({
    queryKey: ["flight", booking.flight_id],
    queryFn: async () => {
      const { data, error } = await flightClient.GET("/api/v1/flights/{flight_id}" as any, {
        params: { path: { flight_id: booking.flight_id } },
      });
      if (error || !data) throw new Error("Flight not found");
      return data as Flight;
    },
    staleTime: 5 * 60 * 1000,
  });

  const { data: payment } = useQuery<Payment | null>({
    queryKey: ["payment", booking.id],
    queryFn: async () => {
      const { data } = await (paymentClient as any).GET("/api/v1/payments/booking/{booking_id}", {
        params: { path: { booking_id: booking.id } },
      });
      return (data as Payment) ?? null;
    },
    retry: false,
  });

  const cancel = useMutation({
    mutationFn: async () => {
      const { error } = await bookingClient.POST("/api/v1/bookings/{booking_id}/cancel" as any, {
        params: { path: { booking_id: booking.id } },
      });
      if (error) throw new Error("Cancel failed");
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["bookings"] }),
  });

  const isCancellable = !["cancelled", "checked-in", "completed", "boarded"].includes(booking.status.toLowerCase());
  const isCheckable   = ["confirmed", "paid"].includes(booking.status.toLowerCase());
  const statusStyle   = BOOKING_STATUS[booking.status.toLowerCase()] ?? "bg-gray-100 text-gray-500 border-gray-200";
  const cabinStyle    = CABIN_COLOUR[booking.cabin_class] ?? "bg-gray-100 text-gray-600 border-gray-200";

  return (
    <div className="rounded-2xl bg-white border border-gray-100 shadow-sm overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100 bg-gray-50/50">
        <div className="flex items-center gap-3 flex-wrap">
          <span className="font-mono font-bold text-blue-700 text-base tracking-wider">
            {booking.booking_reference}
          </span>
          <span className={`rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize ${statusStyle}`}>
            {booking.status.replace(/-/g, " ")}
          </span>
          <span className={`rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize ${cabinStyle}`}>
            {booking.cabin_class}
          </span>
          {booking.trip_type === "return" && (
            <span className="rounded-full bg-blue-50 border border-blue-200 text-blue-600 px-2.5 py-0.5 text-xs font-medium">
              Return
            </span>
          )}
        </div>
        <span className="text-xs text-gray-400">{fmtDate(booking.created_at)}</span>
      </div>

      {/* Flight info */}
      <div className="px-5 py-4">
        {flight ? (
          <div className="flex items-center gap-4">
            <div className="flex-1">
              <div className="flex items-center gap-3">
                <div className="text-center">
                  <p className="text-2xl font-bold text-gray-900 tabular-nums">{fmt(flight.departure_time)}</p>
                  <p className="text-sm font-semibold text-gray-700 mt-0.5">{flight.origin}</p>
                  <p className="text-xs text-gray-400">{fmtDate(flight.departure_date)}</p>
                </div>
                <div className="flex flex-col items-center gap-1 flex-1 min-w-[80px]">
                  <div className="flex w-full items-center gap-1">
                    <div className="flex-1 h-px bg-green-200" />
                    <svg className="w-4 h-4 text-green-500" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M21 16v-2l-8-5V3.5a1.5 1.5 0 0 0-3 0V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z"/>
                    </svg>
                    <div className="flex-1 h-px bg-green-200" />
                  </div>
                  <span className="text-[11px] text-green-600 font-medium">{flight.flight_number}</span>
                  <span className="text-[10px] text-gray-400">{flight.airline}</span>
                </div>
                <div className="text-center">
                  <p className="text-2xl font-bold text-gray-900 tabular-nums">{fmt(flight.arrival_time)}</p>
                  <p className="text-sm font-semibold text-gray-700 mt-0.5">{flight.destination}</p>
                  <p className="text-xs text-gray-400">{fmtDate(flight.arrival_date)}</p>
                </div>
              </div>
            </div>

            {/* Right side: seat + price */}
            <div className="text-right shrink-0 space-y-1">
              {booking.seat_numbers && (
                <div>
                  <span className="text-[10px] text-gray-400 uppercase font-semibold tracking-wide">Seat</span>
                  <p className="font-mono font-bold text-gray-900 text-lg">{booking.seat_numbers}</p>
                </div>
              )}
              <p className="text-xl font-bold text-blue-700">${booking.total_price.toFixed(2)}</p>
            </div>
          </div>
        ) : (
          <p className="text-sm text-gray-400 animate-pulse">Loading flight details…</p>
        )}
      </div>

      {/* Gate / terminal badges */}
      {flight && (flight.gate) && (
        <div className="flex gap-2 px-5 pb-3">
          {flight.gate && (
            <span className="rounded-full border border-slate-200 bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-600">
              Gate {flight.gate}
            </span>
          )}
        </div>
      )}

      {/* Payment panel */}
      {showPayment && payment && (
        <div className="border-t border-gray-100 px-5 py-3 bg-gray-50/40 text-sm space-y-1.5">
          <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400 mb-2">Payment</p>
          <div className="grid grid-cols-2 gap-x-6 gap-y-1">
            <span className="text-gray-500">Amount</span>
            <span className="font-semibold">${payment.amount.toFixed(2)} {payment.currency}</span>
            <span className="text-gray-500">Status</span>
            <span className={`font-semibold capitalize ${PAYMENT_STATUS[payment.status] ?? "text-gray-700"}`}>
              {payment.status}
            </span>
            <span className="text-gray-500">Method</span>
            <span className="font-semibold capitalize">{payment.payment_method}</span>
            {payment.card_last_four && (
              <>
                <span className="text-gray-500">Card</span>
                <span className="font-mono font-semibold">•••• {payment.card_last_four}</span>
              </>
            )}
            {payment.transaction_ref && (
              <>
                <span className="text-gray-500">Transaction</span>
                <span className="font-mono text-xs text-gray-600">{payment.transaction_ref}</span>
              </>
            )}
          </div>
        </div>
      )}

      {/* Footer actions */}
      <div className="flex items-center justify-between gap-3 border-t border-gray-100 px-5 py-3 bg-gray-50/60">
        <div className="flex gap-2">
          {payment && (
            <button
              onClick={() => setShowPayment((v) => !v)}
              className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 transition-colors"
            >
              {showPayment ? "Hide Payment" : "Payment Details"}
            </button>
          )}
          {isCheckable && (
            <button
              onClick={() => navigate("/checkin")}
              className="rounded-lg border border-sky-200 bg-sky-50 px-3 py-1.5 text-xs font-medium text-sky-700 hover:bg-sky-100 transition-colors"
            >
              Check In
            </button>
          )}
          <button
            onClick={() => navigate("/baggage")}
            className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 transition-colors"
          >
            Baggage
          </button>
        </div>

        {isCancellable && (
          <button
            onClick={() => { if (confirm("Cancel this booking?")) cancel.mutate(); }}
            disabled={cancel.isPending}
            className="rounded-lg border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-50 transition-colors"
          >
            {cancel.isPending ? "Cancelling…" : "Cancel"}
          </button>
        )}
      </div>
    </div>
  );
}

export function BookingsPage() {
  const { data: bookings = [], isLoading, isError } = useQuery<Booking[]>({
    queryKey: ["bookings"],
    queryFn: async () => {
      const { data, error } = await bookingClient.GET("/api/v1/bookings", {});
      if (error) throw new Error("Failed to load bookings");
      return (data as Booking[]) ?? [];
    },
  });

  const active    = bookings.filter((b) => !["cancelled"].includes(b.status.toLowerCase()));
  const cancelled = bookings.filter((b) => b.status.toLowerCase() === "cancelled");

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-gray-900">My Bookings</h2>

      {isLoading && <p className="text-sm text-gray-400 animate-pulse">Loading bookings…</p>}
      {isError   && <p className="text-sm text-red-500">Failed to load bookings. Please refresh.</p>}

      {!isLoading && !isError && bookings.length === 0 && (
        <div className="rounded-2xl border border-dashed border-gray-200 bg-white px-8 py-14 text-center">
          <p className="font-semibold text-gray-500">No bookings yet</p>
          <p className="mt-1 text-sm text-gray-400">Search for a flight to get started.</p>
        </div>
      )}

      {active.length > 0 && (
        <section className="space-y-4">
          {active.length < bookings.length && (
            <h3 className="text-sm font-bold uppercase tracking-widest text-gray-400">Active</h3>
          )}
          {active.map((b) => <BookingCard key={b.id} booking={b} />)}
        </section>
      )}

      {cancelled.length > 0 && (
        <section className="space-y-4">
          <h3 className="text-sm font-bold uppercase tracking-widest text-gray-400">Cancelled</h3>
          {cancelled.map((b) => <BookingCard key={b.id} booking={b} />)}
        </section>
      )}
    </div>
  );
}
