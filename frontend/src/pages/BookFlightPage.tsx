import { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { bookingClient, paymentClient } from "../api/client";
import { useAuth } from "../contexts/AuthContext";
import { PaymentForm, PaymentFormData } from "../components/PaymentForm";
import { AIRPORTS } from "../components/AirportCombobox";

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
  aircraft_type: string | null;
  available_seats_economy: number;
  available_seats_business: number;
  available_seats_first: number;
  price_economy: number;
  price_business: number;
  price_first: number;
  gate: string | null;
  terminal: string | null;
}

const STATUS_STYLE: Record<string, string> = {
  scheduled: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200",
  boarding:  "bg-blue-50   text-blue-700   ring-1 ring-blue-200",
  departed:  "bg-gray-100  text-gray-500",
  in_flight: "bg-sky-50    text-sky-700    ring-1 ring-sky-200",
  landed:    "bg-gray-100  text-gray-500",
  arrived:   "bg-gray-100  text-gray-500",
  cancelled: "bg-red-50    text-red-700    ring-1 ring-red-200",
  delayed:   "bg-amber-50  text-amber-700  ring-1 ring-amber-200",
};

function cityLabel(code: string) { return AIRPORTS[code]?.city ?? code; }
function fmt(t: string) { return t.slice(0, 5); }
function fmtDate(d: string) {
  return new Date(d).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}
function duration(depDate: string, depTime: string, arrDate: string, arrTime: string) {
  const mins = Math.round(
    (new Date(`${arrDate}T${arrTime}`).getTime() - new Date(`${depDate}T${depTime}`).getTime()) / 60000,
  );
  const h = Math.floor(mins / 60), m = mins % 60;
  return `${h}h${m > 0 ? ` ${m}m` : ""}`;
}

interface BookResult {
  success: boolean;
  bookingRef: string;
  transactionRef?: string;
  failureReason?: string;
}

export function BookFlightPage() {
  const navigate  = useNavigate();
  const location  = useLocation();
  const { user }  = useAuth();
  const qc        = useQueryClient();

  const state = location.state as { flight: Flight; cabinClass: string } | null;

  if (!state?.flight) {
    navigate("/flights", { replace: true });
    return null;
  }

  const { flight, cabinClass: initialCabin } = state;

  const [step,       setStep]       = useState<1 | 2>(1);
  const [cabin,      setCabin]      = useState(() => {
    if (initialCabin) return initialCabin;
    if (flight.available_seats_economy  > 0) return "economy";
    if (flight.available_seats_business > 0) return "business";
    return "first";
  });
  const [ikey,       setIkey]       = useState(crypto.randomUUID);
  const [result,     setResult]     = useState<BookResult | null>(null);

  const priceMap: Record<string, number> = {
    economy:  flight.price_economy,
    business: flight.price_business,
    first:    flight.price_first,
  };
  const seatsMap: Record<string, number> = {
    economy:  flight.available_seats_economy,
    business: flight.available_seats_business,
    first:    flight.available_seats_first,
  };

  const bookAndPay = useMutation({
    mutationFn: async (pd: PaymentFormData) => {
      const { data: bData, error: bErr } = await bookingClient.POST("/api/v1/bookings", {
        body: {
          flight_id:       flight.id,
          passenger_name:  user!.full_name,
          passenger_email: user!.email,
          cabin_class:     cabin,
        },
      });
      if (bErr || !bData) throw new Error("Failed to create booking");
      const booking = bData as { id: string; booking_reference: string; total_price: number };

      const { data: pData, error: pErr } = await paymentClient.POST("/api/v1/payments", {
        body: { booking_id: booking.id, amount: booking.total_price, currency: "USD", idempotency_key: ikey, ...pd },
      });
      if (pErr) throw new Error("Payment request failed");
      const payment = pData as { status: string; transaction_ref?: string; failure_reason?: string };
      return { booking, payment };
    },
    onSuccess: ({ booking, payment }) => {
      qc.invalidateQueries({ queryKey: ["bookings"] });
      setResult({
        success:        payment.status === "completed",
        bookingRef:     booking.booking_reference,
        transactionRef: payment.transaction_ref ?? undefined,
        failureReason:  payment.failure_reason  ?? undefined,
      });
    },
    onError: () => setResult({ success: false, bookingRef: "", failureReason: "An unexpected error occurred." }),
  });

  const dur       = duration(flight.departure_date, flight.departure_time, flight.arrival_date, flight.arrival_time);
  const statusKey = flight.status.toLowerCase();

  // ── Result screen ──────────────────────────────────────────────────────────
  if (result) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center p-4">
        <div className="w-full max-w-md">
          {result.success ? (
            <div className="rounded-2xl bg-white border border-gray-100 shadow-sm p-8 text-center space-y-5">
              <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-green-100">
                <svg className="w-8 h-8 text-green-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <div>
                <h2 className="text-xl font-bold text-gray-900">Booking Confirmed</h2>
                <p className="mt-1 text-sm text-gray-400">Your seat is reserved and payment was successful.</p>
              </div>
              <div className="rounded-xl bg-gray-50 p-4 text-left space-y-3 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-500">Flight</span>
                  <span className="font-semibold">{flight.flight_number}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Route</span>
                  <span className="font-semibold">{cityLabel(flight.origin)} → {cityLabel(flight.destination)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Date</span>
                  <span className="font-semibold">{fmtDate(flight.departure_date)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Cabin</span>
                  <span className="font-semibold capitalize">{cabin}</span>
                </div>
                <div className="flex justify-between border-t pt-3 mt-1">
                  <span className="text-gray-500">Booking Reference</span>
                  <span className="font-mono font-bold text-blue-700 text-base tracking-wider">{result.bookingRef}</span>
                </div>
                {result.transactionRef && (
                  <div className="flex justify-between">
                    <span className="text-gray-500">Transaction ID</span>
                    <span className="font-mono text-xs text-gray-500">{result.transactionRef}</span>
                  </div>
                )}
              </div>
              <div className="flex gap-3">
                <button
                  onClick={() => navigate("/bookings")}
                  className="flex-1 rounded-lg bg-blue-600 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 transition-colors"
                >
                  View My Bookings
                </button>
                <button
                  onClick={() => navigate("/flights")}
                  className="flex-1 rounded-lg border border-gray-300 py-2.5 text-sm font-medium hover:bg-gray-50 transition-colors"
                >
                  Back to Flights
                </button>
              </div>
            </div>
          ) : (
            <div className="rounded-2xl bg-white border border-gray-100 shadow-sm p-8 text-center space-y-5">
              <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-red-100">
                <svg className="w-8 h-8 text-red-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </div>
              <div>
                <h2 className="text-xl font-bold text-gray-900">Payment Failed</h2>
                <p className="mt-1 text-sm text-gray-500">{result.failureReason}</p>
              </div>
              {result.bookingRef && (
                <p className="text-xs text-gray-400">
                  Booking <span className="font-mono font-medium text-gray-600">{result.bookingRef}</span> is on hold — retry to complete it.
                </p>
              )}
              <div className="flex gap-3">
                <button
                  onClick={() => navigate("/flights")}
                  className="flex-1 rounded-lg border border-gray-300 py-2.5 text-sm font-medium hover:bg-gray-50 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={() => { setResult(null); setStep(2); setIkey(crypto.randomUUID()); }}
                  className="flex-1 rounded-lg bg-blue-600 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 transition-colors"
                >
                  Retry Payment
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  // ── Main booking flow ──────────────────────────────────────────────────────
  return (
    <div className="max-w-5xl mx-auto space-y-5">

      {/* Back link */}
      <button
        onClick={() => navigate("/flights")}
        className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800 transition-colors"
      >
        <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
        Back to Flights
      </button>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">

        {/* ── Flight summary sidebar ── */}
        <div className="lg:col-span-1">
          <div className="rounded-2xl bg-white border border-gray-100 shadow-sm p-5 lg:sticky lg:top-6 space-y-4">

            <div className="flex items-center justify-between">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-widest text-gray-400">{flight.airline}</p>
                <p className="text-xl font-bold text-gray-900">{flight.flight_number}</p>
              </div>
              <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${STATUS_STYLE[statusKey] ?? "bg-gray-100 text-gray-500"}`}>
                {statusKey}
              </span>
            </div>

            {/* Route timeline */}
            <div className="space-y-2">
              <div className="flex items-start gap-3">
                <div className="mt-2 h-2.5 w-2.5 shrink-0 rounded-full bg-blue-500" />
                <div>
                  <p className="text-2xl font-bold text-blue-700 tabular-nums leading-none">{fmt(flight.departure_time)}</p>
                  <p className="mt-0.5 text-sm font-semibold text-gray-800">{cityLabel(flight.origin)}</p>
                  <p className="text-xs text-gray-400">{fmtDate(flight.departure_date)} · {flight.origin}</p>
                </div>
              </div>
              <div className="flex items-center gap-3 pl-[5px]">
                <div className="w-px h-7 bg-green-200 mx-0.5" />
                <span className="text-xs text-green-600 font-medium">{dur} · Direct</span>
              </div>
              <div className="flex items-start gap-3">
                <div className="mt-2 h-2.5 w-2.5 shrink-0 rounded-full bg-gray-400" />
                <div>
                  <p className="text-2xl font-bold text-gray-800 tabular-nums leading-none">{fmt(flight.arrival_time)}</p>
                  <p className="mt-0.5 text-sm font-semibold text-gray-800">{cityLabel(flight.destination)}</p>
                  <p className="text-xs text-gray-400">{fmtDate(flight.arrival_date)} · {flight.destination}</p>
                </div>
              </div>
            </div>

            {/* Tags */}
            {(flight.aircraft_type || flight.gate || flight.terminal) && (
              <div className="border-t pt-3 flex flex-wrap gap-2">
                {flight.aircraft_type && (
                  <span className="rounded border border-gray-200 px-2 py-0.5 text-xs text-gray-500">{flight.aircraft_type}</span>
                )}
                {flight.gate     && <span className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-500">Gate {flight.gate}</span>}
                {flight.terminal && <span className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-500">Terminal {flight.terminal}</span>}
              </div>
            )}
          </div>
        </div>

        {/* ── Form area ── */}
        <div className="lg:col-span-2 space-y-5">

          {/* Stepper */}
          <div className="flex items-center gap-2">
            {(["Review", "Payment"] as const).map((label, i) => {
              const num    = i + 1;
              const active = step === num;
              const done   = step > num;
              return (
                <div key={label} className="flex items-center gap-2">
                  {i > 0 && <div className={`h-px w-10 ${done || active ? "bg-blue-400" : "bg-gray-200"}`} />}
                  <div className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold transition-colors ${
                    active ? "bg-blue-600 text-white" :
                    done   ? "bg-blue-100 text-blue-600" :
                             "bg-gray-100 text-gray-400"
                  }`}>
                    {done ? (
                      <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={3}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                    ) : num}
                  </div>
                  <span className={`text-sm font-medium ${active ? "text-gray-900" : "text-gray-400"}`}>{label}</span>
                </div>
              );
            })}
          </div>

          <div className="rounded-2xl bg-white border border-gray-100 shadow-sm p-6">

            {step === 1 ? (
              /* ── Step 1: Review ── */
              <div className="space-y-6">
                <h2 className="text-lg font-bold text-gray-900">Review Your Booking</h2>

                {/* Passenger */}
                <div>
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">Passenger Details</p>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <p className="mb-1 text-xs text-gray-400">Full Name</p>
                      <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-700">
                        {user?.full_name}
                      </div>
                    </div>
                    <div>
                      <p className="mb-1 text-xs text-gray-400">Email</p>
                      <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-700 truncate">
                        {user?.email}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Cabin selector */}
                <div>
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">Select Cabin Class</p>
                  <div className="grid grid-cols-3 gap-3">
                    {(["economy", "business", "first"] as const).map((c) => {
                      const price = priceMap[c];
                      const seats = seatsMap[c];
                      const unavailable = seats === 0 || price === 0;
                      return (
                        <button
                          key={c}
                          type="button"
                          disabled={unavailable}
                          onClick={() => setCabin(c)}
                          className={`rounded-xl border p-3.5 text-left transition-colors ${
                            unavailable
                              ? "border-gray-100 bg-gray-50 opacity-40 cursor-not-allowed"
                              : cabin === c
                              ? "border-blue-500 bg-blue-50 shadow-sm"
                              : "border-gray-200 hover:border-blue-300"
                          }`}
                        >
                          <p className={`text-[11px] font-bold uppercase tracking-widest ${cabin === c && !unavailable ? "text-blue-500" : "text-gray-400"}`}>
                            {c === "first" ? "First" : c === "business" ? "Business" : "Economy"}
                          </p>
                          <p className={`mt-1 text-xl font-bold tabular-nums ${cabin === c && !unavailable ? "text-blue-700" : "text-gray-800"}`}>
                            ${price.toFixed(0)}
                          </p>
                          <p className={`mt-0.5 text-xs ${seats < 10 && !unavailable ? "font-medium text-amber-500" : "text-gray-400"}`}>
                            {unavailable ? "Unavailable" : `${seats} seat${seats !== 1 ? "s" : ""} left`}
                          </p>
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Total */}
                <div className="flex items-center justify-between rounded-xl bg-blue-50 px-5 py-4">
                  <div>
                    <p className="text-sm text-gray-600 font-medium">Total to pay</p>
                    <p className="text-xs text-gray-400 mt-0.5 capitalize">{cabin} class · 1 passenger</p>
                  </div>
                  <p className="text-2xl font-bold text-blue-700">${priceMap[cabin]?.toFixed(2)}</p>
                </div>

                <div className="flex gap-3">
                  <button
                    onClick={() => navigate("/flights")}
                    className="flex-1 rounded-lg border border-gray-300 py-2.5 text-sm font-medium hover:bg-gray-50 transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={() => setStep(2)}
                    className="flex-1 rounded-lg bg-blue-600 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 transition-colors"
                  >
                    Continue to Payment →
                  </button>
                </div>
              </div>

            ) : (
              /* ── Step 2: Payment ── */
              <div>
                <h2 className="mb-5 text-lg font-bold text-gray-900">Payment Details</h2>
                <PaymentForm
                  amount={priceMap[cabin] ?? 0}
                  currency="USD"
                  isPending={bookAndPay.isPending}
                  onBack={() => setStep(1)}
                  onSubmit={(pd) => bookAndPay.mutate(pd)}
                />
              </div>
            )}

          </div>
        </div>
      </div>
    </div>
  );
}
