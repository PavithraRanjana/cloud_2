import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { flightClient, bookingClient, paymentClient } from "../api/client";
import { useAuth } from "../contexts/AuthContext";
import { AirportCombobox, AIRPORTS } from "../components/AirportCombobox";
import { PaymentForm, PaymentFormData } from "../components/PaymentForm";

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

function flightDuration(depDate: string, depTime: string, arrDate: string, arrTime: string) {
  const dep = new Date(`${depDate}T${depTime}`);
  const arr = new Date(`${arrDate}T${arrTime}`);
  const totalMins = Math.round((arr.getTime() - dep.getTime()) / 60000);
  const h = Math.floor(totalMins / 60);
  const m = totalMins % 60;
  return `${h}h${m > 0 ? ` ${m}m` : ""}`;
}

function formatTime(t: string) { return t.slice(0, 5); }
function formatDate(d: string) {
  return new Date(d).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}
function cityLabel(code: string) { return AIRPORTS[code]?.city ?? code; }

interface FlightCardProps {
  flight: Flight;
  cabinClass: string;
  onBook: () => void;
  isBooking: boolean;
}

function FlightCard({ flight, cabinClass, onBook, isBooking }: FlightCardProps) {
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

  const isAny = cabinClass === "";

  // For "any": show the cheapest available cabin price as "from $X"
  const lowestPrice = Math.min(
    ...(["economy", "business", "first"] as const)
      .map((c) => priceMap[c])
      .filter((p) => p > 0),
  );
  const totalSeats =
    flight.available_seats_economy +
    flight.available_seats_business +
    flight.available_seats_first;

  const price      = isAny ? lowestPrice : (priceMap[cabinClass] ?? 0);
  const seats      = isAny ? totalSeats  : (seatsMap[cabinClass] ?? 0);
  const priceLabel = isAny ? "from"      : cabinClass;

  const duration = flightDuration(
    flight.departure_date, flight.departure_time,
    flight.arrival_date,   flight.arrival_time,
  );
  const statusKey = flight.status.toLowerCase();
  const noFirstClass = flight.price_first === 0 && flight.available_seats_first === 0;
  const unavailable = isAny
    ? totalSeats === 0
    : seats === 0 || (cabinClass === "first" && noFirstClass);

  // Cabin breakdown shown when "any" is selected
  const cabinRows = [
    { label: "Economy",    price: flight.price_economy,  seats: flight.available_seats_economy  },
    { label: "Business",   price: flight.price_business, seats: flight.available_seats_business },
    { label: "First",      price: flight.price_first,    seats: flight.available_seats_first    },
  ].filter((c) => c.price > 0);

  return (
    <div className="rounded-2xl bg-white border border-gray-100 shadow-sm hover:shadow-md transition-shadow overflow-hidden">

      {/* Card header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100">
        <div className="flex items-center gap-3">
          <span className="text-base">✈</span>
          <span className="font-bold text-gray-900 tracking-wide">{flight.flight_number}</span>
          <span className="text-sm text-gray-400">{flight.airline}</span>
          {flight.aircraft_type && (
            <span className="hidden sm:inline rounded border border-gray-200 px-2 py-0.5 text-xs text-gray-400">
              {flight.aircraft_type}
            </span>
          )}
        </div>
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${STATUS_STYLE[statusKey] ?? "bg-gray-100 text-gray-500"}`}>
          {statusKey}
        </span>
      </div>

      {/* Route section */}
      <div className="px-5 py-5">
        <div className="flex items-center gap-3">

          {/* Origin */}
          <div className="flex-1 text-center">
            <p className="text-3xl font-bold text-blue-700 tabular-nums">{formatTime(flight.departure_time)}</p>
            <p className="mt-0.5 font-semibold text-gray-800">{cityLabel(flight.origin)}</p>
            <p className="text-xs font-mono text-blue-500">{flight.origin}</p>
            <p className="mt-1 text-xs text-gray-400">{formatDate(flight.departure_date)}</p>
          </div>

          {/* Duration */}
          <div className="flex flex-col items-center gap-1.5 min-w-[90px]">
            <span className="text-xs text-green-600 font-medium">{duration}</span>
            <div className="flex w-full items-center gap-1">
              <div className="flex-1 h-px bg-green-200" />
              <svg className="w-4 h-4 text-green-500" viewBox="0 0 24 24" fill="currentColor">
                <path d="M21 16v-2l-8-5V3.5a1.5 1.5 0 0 0-3 0V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z"/>
              </svg>
              <div className="flex-1 h-px bg-green-200" />
            </div>
            <span className="text-xs text-green-600">Direct</span>
          </div>

          {/* Destination */}
          <div className="flex-1 text-center">
            <p className="text-3xl font-bold text-gray-900 tabular-nums">{formatTime(flight.arrival_time)}</p>
            <p className="mt-0.5 font-semibold text-gray-800">{cityLabel(flight.destination)}</p>
            <p className="text-xs font-mono text-blue-500">{flight.destination}</p>
            <p className="mt-1 text-xs text-gray-400">{formatDate(flight.arrival_date)}</p>
          </div>
        </div>
      </div>

      {/* Cabin breakdown — only shown when "Any cabin" is selected */}
      {isAny && cabinRows.length > 0 && (
        <div className="flex items-center gap-6 border-t border-gray-100 px-5 py-2.5 bg-gray-50/40">
          {cabinRows.map((c) => (
            <div key={c.label} className="flex items-center gap-1.5 text-xs">
              <span className="text-gray-400">{c.label}</span>
              <span className="font-semibold text-gray-700">${c.price.toFixed(0)}</span>
              <span className={`text-gray-400 ${c.seats < 15 && c.seats > 0 ? "text-amber-500 font-medium" : ""}`}>
                · {c.seats} left
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Card footer */}
      <div className="flex items-center justify-between gap-4 border-t border-gray-100 bg-gray-50/60 px-5 py-3">
        <div className="flex flex-wrap items-center gap-3 text-xs text-gray-400">
          {flight.gate     && <span className="rounded bg-gray-100 px-2 py-0.5">Gate {flight.gate}</span>}
          {flight.terminal && <span className="rounded bg-gray-100 px-2 py-0.5">Terminal {flight.terminal}</span>}
          {!unavailable && (
            <span className={seats > 0 && seats < 15 ? "font-medium text-amber-600" : ""}>
              {isAny ? `${seats} seats across all cabins` : `${seats} seat${seats !== 1 ? "s" : ""} left`}
            </span>
          )}
        </div>

        <div className="flex items-center gap-4 shrink-0">
          {!unavailable && price > 0 && (
            <div className="text-right">
              <p className="text-xl font-bold text-blue-700">${price.toFixed(2)}</p>
              <p className="text-xs capitalize text-gray-400">{priceLabel}</p>
            </div>
          )}
          <button
            onClick={onBook}
            disabled={isBooking || unavailable}
            className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {unavailable ? "Unavailable" : "Book"}
          </button>
        </div>
      </div>
    </div>
  );
}

export function FlightsPage() {
  const { user } = useAuth();
  const qc = useQueryClient();

  const [filters, setFilters] = useState({
    origin: "",
    destination: "",
    departure_date: "",
    cabin_class: "",
  });
  const [bookingFlight,  setBookingFlight]  = useState<Flight | null>(null);
  const [modalCabin,     setModalCabin]     = useState("economy");
  const [modalStep,      setModalStep]      = useState<1 | 2>(1);
  const [idempotencyKey, setIdempotencyKey] = useState("");

  interface PaymentResult {
    success: boolean;
    bookingRef: string;
    transactionRef?: string;
    failureReason?: string;
  }
  const [paymentResult, setPaymentResult] = useState<PaymentResult | null>(null);

  // Load all flights on mount; refetch when filters change
  const { data: flights = [], isFetching, isError } = useQuery<Flight[]>({
    queryKey: ["flights", filters],
    queryFn: async () => {
      const { data, error } = await flightClient.GET("/api/v1/flights", {
        params: {
          query: {
            origin:         filters.origin         || undefined,
            destination:    filters.destination     || undefined,
            departure_date: filters.departure_date  || undefined,
            cabin_class:    filters.cabin_class     || undefined,
          },
        },
      });
      if (error) throw new Error("Failed to load flights");
      const envelope = data as { items?: Flight[] } | null;
      return envelope?.items ?? [];
    },
  });

  // Effective cabin for booking: use filter value unless "any", then use modal selection
  const effectiveCabin = filters.cabin_class || modalCabin;

  const bookAndPay = useMutation({
    mutationFn: async ({ flight, paymentData: pd }: { flight: Flight; paymentData: PaymentFormData }) => {
      // Step 1: create the booking
      const { data: bookingData, error: bookingErr } = await bookingClient.POST("/api/v1/bookings", {
        body: {
          flight_id:       flight.id,
          passenger_name:  user!.full_name,
          passenger_email: user!.email,
          cabin_class:     effectiveCabin,
        },
      });
      if (bookingErr || !bookingData) throw new Error("Failed to create booking");
      const booking = bookingData as { id: string; booking_reference: string; total_price: number };

      // Step 2: process payment
      const { data: paymentResp, error: paymentErr } = await paymentClient.POST("/api/v1/payments", {
        body: {
          booking_id:      booking.id,
          amount:          booking.total_price,
          currency:        "USD",
          idempotency_key: idempotencyKey,
          ...pd,
        },
      });
      if (paymentErr) throw new Error("Payment request failed");
      const payment = paymentResp as { status: string; transaction_ref?: string; failure_reason?: string };
      return { booking, payment };
    },
    onSuccess: ({ booking, payment }) => {
      qc.invalidateQueries({ queryKey: ["bookings"] });
      setPaymentResult({
        success:        payment.status === "completed",
        bookingRef:     booking.booking_reference,
        transactionRef: payment.transaction_ref ?? undefined,
        failureReason:  payment.failure_reason  ?? undefined,
      });
    },
    onError: () => {
      setPaymentResult({ success: false, bookingRef: "", failureReason: "An unexpected error occurred." });
    },
  });

  const priceKey = `price_${effectiveCabin}` as keyof Flight;

  function openBookingModal(flight: Flight) {
    if (!filters.cabin_class) {
      if (flight.available_seats_economy  > 0) setModalCabin("economy");
      else if (flight.available_seats_business > 0) setModalCabin("business");
      else setModalCabin("first");
    }
    setModalStep(1);
    setPaymentMethod("credit-card");
    setCardNumber("");
    setIdempotencyKey(crypto.randomUUID());
    setPaymentResult(null);
    setBookingFlight(flight);
  }

  function closeModal() {
    setBookingFlight(null);
    setPaymentResult(null);
    setModalStep(1);
  }

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-gray-900">Search Flights</h2>

      {/* Search form */}
      <div className="rounded-2xl bg-white p-5 shadow-sm border border-gray-100">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div>
            <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-gray-500">
              From
            </label>
            <AirportCombobox
              value={filters.origin}
              onChange={(code) => setFilters((f) => ({ ...f, origin: code }))}
              placeholder="City or airport"
              exclude={filters.destination}
            />
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-gray-500">
              To
            </label>
            <AirportCombobox
              value={filters.destination}
              onChange={(code) => setFilters((f) => ({ ...f, destination: code }))}
              placeholder="City or airport"
              exclude={filters.origin}
            />
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-gray-500">
              Departure
            </label>
            <input
              type="date"
              value={filters.departure_date}
              onChange={(e) => setFilters((f) => ({ ...f, departure_date: e.target.value }))}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-gray-500">
              Cabin
            </label>
            <select
              value={filters.cabin_class}
              onChange={(e) => setFilters((f) => ({ ...f, cabin_class: e.target.value }))}
              className="w-full h-9 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              <option value="">Any cabin</option>
              <option value="economy">Economy</option>
              <option value="business">Business</option>
              <option value="first">First Class</option>
            </select>
          </div>
        </div>
      </div>

      {/* Status line */}
      {isFetching && (
        <p className="text-sm text-gray-400 animate-pulse">Loading flights…</p>
      )}
      {isError && (
        <p className="text-sm text-red-500">Failed to load flights. Please try again.</p>
      )}
      {!isFetching && !isError && (
        <p className="text-sm text-gray-400">
          {flights.length === 0
            ? "No flights found for these filters."
            : `${flights.length} flight${flights.length !== 1 ? "s" : ""} available`}
        </p>
      )}

      {/* Flight cards */}
      <div className="space-y-4">
        {flights.map((flight) => (
          <FlightCard
            key={flight.id}
            flight={flight}
            cabinClass={filters.cabin_class}
            onBook={() => openBookingModal(flight)}
            isBooking={bookAndPay.isPending}
          />
        ))}
      </div>

      {/* Booking + Payment modal */}
      {bookingFlight && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-sm rounded-2xl bg-white shadow-2xl overflow-hidden">

            {/* Step indicator */}
            {!paymentResult && (
              <div className="flex border-b border-gray-100">
                {(["Review", "Payment"] as const).map((label, i) => (
                  <div key={label} className={`flex-1 py-3 text-center text-xs font-semibold ${modalStep === i + 1 ? "bg-blue-600 text-white" : "text-gray-400"}`}>
                    {i + 1}. {label}
                  </div>
                ))}
              </div>
            )}

            <div className="p-6">

              {/* ── Result state ── */}
              {paymentResult ? (
                paymentResult.success ? (
                  <div className="text-center space-y-3">
                    <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-green-100 text-2xl">✓</div>
                    <h3 className="text-lg font-bold text-gray-900">Payment Successful</h3>
                    <div className="rounded-xl bg-gray-50 p-4 text-left space-y-2 text-sm">
                      <div className="flex justify-between">
                        <span className="text-gray-500">Booking Ref</span>
                        <span className="font-mono font-bold text-blue-700">{paymentResult.bookingRef}</span>
                      </div>
                      {paymentResult.transactionRef && (
                        <div className="flex justify-between">
                          <span className="text-gray-500">Transaction</span>
                          <span className="font-mono text-xs text-gray-600">{paymentResult.transactionRef}</span>
                        </div>
                      )}
                    </div>
                    <button onClick={closeModal} className="w-full rounded-lg bg-blue-600 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 transition-colors">
                      Done
                    </button>
                  </div>
                ) : (
                  <div className="text-center space-y-3">
                    <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-red-100 text-2xl">✗</div>
                    <h3 className="text-lg font-bold text-gray-900">Payment Failed</h3>
                    <p className="text-sm text-gray-500">{paymentResult.failureReason}</p>
                    {paymentResult.bookingRef && (
                      <p className="text-xs text-gray-400">
                        Booking <span className="font-mono font-medium text-gray-600">{paymentResult.bookingRef}</span> is on hold — retry to complete it.
                      </p>
                    )}
                    <div className="flex gap-3 pt-1">
                      <button onClick={closeModal} className="flex-1 rounded-lg border border-gray-300 py-2 text-sm font-medium hover:bg-gray-50 transition-colors">
                        Cancel
                      </button>
                      <button
                        onClick={() => {
                          setPaymentResult(null);
                          setModalStep(2);
                          setIdempotencyKey(crypto.randomUUID());
                        }}
                        className="flex-1 rounded-lg bg-blue-600 py-2 text-sm font-semibold text-white hover:bg-blue-700 transition-colors"
                      >
                        Retry Payment
                      </button>
                    </div>
                  </div>
                )
              ) : modalStep === 1 ? (
                /* ── Step 1: Review ── */
                <>
                  <h3 className="mb-4 text-base font-bold text-gray-900">Review your booking</h3>
                  <div className="mb-4 rounded-xl bg-gray-50 p-4 space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-gray-500">Flight</span>
                      <span className="font-semibold">{bookingFlight.flight_number}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">Route</span>
                      <span className="font-semibold">{cityLabel(bookingFlight.origin)} → {cityLabel(bookingFlight.destination)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">Date</span>
                      <span className="font-semibold">{formatDate(bookingFlight.departure_date)}</span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-gray-500">Cabin</span>
                      {filters.cabin_class ? (
                        <span className="font-semibold capitalize">{filters.cabin_class}</span>
                      ) : (
                        <select
                          value={modalCabin}
                          onChange={(e) => setModalCabin(e.target.value)}
                          className="rounded-lg border border-gray-300 px-2 py-1 text-sm font-semibold focus:border-blue-500 focus:outline-none"
                        >
                          {bookingFlight.available_seats_economy  > 0 && <option value="economy">Economy — ${bookingFlight.price_economy.toFixed(2)}</option>}
                          {bookingFlight.available_seats_business > 0 && <option value="business">Business — ${bookingFlight.price_business.toFixed(2)}</option>}
                          {bookingFlight.available_seats_first    > 0 && bookingFlight.price_first > 0 && <option value="first">First — ${bookingFlight.price_first.toFixed(2)}</option>}
                        </select>
                      )}
                    </div>
                    <div className="flex justify-between border-t pt-2 mt-1">
                      <span className="text-gray-500">Total</span>
                      <span className="text-xl font-bold text-blue-700">${(bookingFlight[priceKey] as number)?.toFixed(2)}</span>
                    </div>
                  </div>
                  <div className="flex gap-3">
                    <button onClick={closeModal} className="flex-1 rounded-lg border border-gray-300 py-2 text-sm font-medium hover:bg-gray-50 transition-colors">
                      Cancel
                    </button>
                    <button onClick={() => setModalStep(2)} className="flex-1 rounded-lg bg-blue-600 py-2 text-sm font-semibold text-white hover:bg-blue-700 transition-colors">
                      Continue to Payment
                    </button>
                  </div>
                </>
              ) : (
                /* ── Step 2: Payment ── */
                <>
                  <h3 className="mb-4 text-base font-bold text-gray-900">Payment details</h3>
                  <PaymentForm
                    amount={(bookingFlight[priceKey] as number) ?? 0}
                    currency="USD"
                    isPending={bookAndPay.isPending}
                    onBack={() => setModalStep(1)}
                    onSubmit={(pd) => bookAndPay.mutate({ flight: bookingFlight, paymentData: pd })}
                  />
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
