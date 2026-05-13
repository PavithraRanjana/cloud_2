import { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { flightClient, bookingClient, paymentClient } from "../api/client";
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

interface BookState {
  flight: Flight;
  cabinClass: string;
  tripType: "one_way" | "return";
  returnDate: string;
}

interface BookResult {
  success: boolean;
  outboundRef: string;
  returnRef?: string;
  transactionRef?: string;
  totalAmount: number;
  failureReason?: string;
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
function fmt(t: string) {
  const [hStr, mStr] = t.slice(0, 5).split(":");
  const h = parseInt(hStr, 10);
  const period = h >= 12 ? "PM" : "AM";
  const h12 = h % 12 || 12;
  return `${h12}:${mStr} ${period}`;
}
function fmtDate(d: string) {
  return new Date(d + "T00:00:00").toLocaleDateString("en-US", {
    month: "short", day: "numeric", year: "numeric",
  });
}
function calcDuration(depDate: string, depTime: string, arrDate: string, arrTime: string) {
  const mins = Math.round(
    (new Date(`${arrDate}T${arrTime}`).getTime() - new Date(`${depDate}T${depTime}`).getTime()) / 60000,
  );
  const h = Math.floor(mins / 60), m = mins % 60;
  return `${h}h${m > 0 ? ` ${m}m` : ""}`;
}

function pricesOf(f: Flight) {
  return { economy: f.price_economy, business: f.price_business, first: f.price_first };
}
function seatsOf(f: Flight) {
  return {
    economy:  f.available_seats_economy,
    business: f.available_seats_business,
    first:    f.available_seats_first,
  };
}

// ── Compact selectable return flight card ──────────────────────────────────
interface ReturnOptionProps {
  flight: Flight;
  selected: boolean;
  selectedCabin: string;
  onSelect: () => void;
  onCabin: (c: string) => void;
}
function ReturnFlightOption({ flight, selected, selectedCabin, onSelect, onCabin }: ReturnOptionProps) {
  const prices = pricesOf(flight);
  const seats  = seatsOf(flight);
  const dur    = calcDuration(flight.departure_date, flight.departure_time, flight.arrival_date, flight.arrival_time);
  const statusKey = flight.status.toLowerCase();

  return (
    <div
      onClick={onSelect}
      className={`cursor-pointer rounded-xl border p-4 transition-all ${
        selected ? "border-blue-500 bg-blue-50/40 shadow-sm" : "border-gray-200 hover:border-blue-300 bg-white"
      }`}
    >
      <div className="flex items-center justify-between gap-4">
        {/* Left: flight info */}
        <div className="flex items-center gap-4 min-w-0">
          <div>
            <p className="font-bold text-gray-900 text-sm">{flight.flight_number}</p>
            <p className="text-xs text-gray-400">{flight.airline}</p>
          </div>
          <div className="flex items-center gap-2 text-sm tabular-nums">
            <span className="font-bold text-blue-700">{fmt(flight.departure_time)}</span>
            <div className="flex flex-col items-center gap-0.5">
              <span className="text-[10px] text-green-600 font-medium">{dur}</span>
              <div className="h-px w-8 bg-green-300" />
            </div>
            <span className="font-bold text-gray-800">{fmt(flight.arrival_time)}</span>
          </div>
          {flight.aircraft_type && (
            <span className="hidden sm:inline text-xs text-gray-400 border border-gray-200 rounded px-1.5 py-0.5">
              {flight.aircraft_type}
            </span>
          )}
        </div>

        {/* Right: status + price hint */}
        <div className="flex items-center gap-3 shrink-0">
          <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium capitalize ${STATUS_STYLE[statusKey] ?? "bg-gray-100 text-gray-500"}`}>
            {statusKey}
          </span>
          <span className="text-sm font-bold text-blue-700">
            from ${Math.min(...Object.values(prices).filter(p => p > 0)).toFixed(0)}
          </span>
          {selected && (
            <span className="rounded-full bg-blue-600 px-2.5 py-0.5 text-[10px] font-semibold text-white">Selected</span>
          )}
        </div>
      </div>

      {/* Cabin selector — shown when selected */}
      {selected && (
        <div className="mt-4 grid grid-cols-3 gap-2" onClick={(e) => e.stopPropagation()}>
          {(["economy", "business", "first"] as const).map((c) => {
            const price = prices[c];
            const avail = seats[c];
            const unavail = avail === 0 || price === 0;
            return (
              <button
                key={c}
                type="button"
                disabled={unavail}
                onClick={() => onCabin(c)}
                className={`rounded-lg border p-2.5 text-left transition-colors ${
                  unavail
                    ? "border-gray-100 bg-gray-50 opacity-40 cursor-not-allowed"
                    : selectedCabin === c
                    ? "border-blue-500 bg-blue-50"
                    : "border-gray-200 hover:border-blue-300"
                }`}
              >
                <p className={`text-[10px] font-bold uppercase tracking-widest ${selectedCabin === c && !unavail ? "text-blue-500" : "text-gray-400"}`}>
                  {c === "first" ? "First" : c === "business" ? "Business" : "Economy"}
                </p>
                <p className={`text-base font-bold mt-0.5 ${selectedCabin === c && !unavail ? "text-blue-700" : "text-gray-800"}`}>
                  ${price.toFixed(0)}
                </p>
                <p className={`text-[10px] mt-0.5 ${avail < 10 && !unavail ? "text-amber-500 font-medium" : "text-gray-400"}`}>
                  {unavail ? "N/A" : `${avail} left`}
                </p>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Compact flight summary used in sidebar ─────────────────────────────────
function FlightSummaryCard({
  flight, cabin, label,
}: { flight: Flight; cabin: string; label?: string }) {
  const dur = calcDuration(
    flight.departure_date, flight.departure_time,
    flight.arrival_date, flight.arrival_time,
  );
  const statusKey = flight.status.toLowerCase();
  return (
    <div className="space-y-3">
      {label && (
        <p className="text-[10px] font-bold uppercase tracking-widest text-blue-500">{label}</p>
      )}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-widest text-gray-400">{flight.airline}</p>
          <p className="text-lg font-bold text-gray-900">{flight.flight_number}</p>
        </div>
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${STATUS_STYLE[statusKey] ?? "bg-gray-100 text-gray-500"}`}>
          {statusKey}
        </span>
      </div>
      <div className="space-y-1.5">
        <div className="flex items-start gap-2.5">
          <div className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-blue-500" />
          <div>
            <p className="text-xl font-bold text-blue-700 tabular-nums leading-none">{fmt(flight.departure_time)}</p>
            <p className="mt-0.5 text-sm font-semibold text-gray-800">{cityLabel(flight.origin)}</p>
            <p className="text-[11px] text-gray-400">{fmtDate(flight.departure_date)} · {flight.origin}</p>
          </div>
        </div>
        <div className="flex items-center gap-2.5 pl-[5px]">
          <div className="w-px h-6 bg-green-200 ml-0.5" />
          <span className="text-[11px] text-green-600 font-medium">{dur} · Direct</span>
        </div>
        <div className="flex items-start gap-2.5">
          <div className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-gray-400" />
          <div>
            <p className="text-xl font-bold text-gray-800 tabular-nums leading-none">{fmt(flight.arrival_time)}</p>
            <p className="mt-0.5 text-sm font-semibold text-gray-800">{cityLabel(flight.destination)}</p>
            <p className="text-[11px] text-gray-400">{fmtDate(flight.arrival_date)} · {flight.destination}</p>
          </div>
        </div>
      </div>
      {(flight.aircraft_type || flight.gate || flight.terminal) && (
        <div className="flex flex-wrap gap-1.5 pt-1">
          {flight.aircraft_type && (
            <span className="rounded border border-gray-200 px-1.5 py-0.5 text-[10px] text-gray-500">{flight.aircraft_type}</span>
          )}
          {flight.gate     && <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] text-gray-500">Gate {flight.gate}</span>}
          {flight.terminal && <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] text-gray-500">Terminal {flight.terminal}</span>}
        </div>
      )}
      <p className="text-xs text-gray-400 capitalize">{cabin} class</p>
    </div>
  );
}


// ── Main page ──────────────────────────────────────────────────────────────
export function BookFlightPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user }  = useAuth();
  const qc        = useQueryClient();

  const state = location.state as BookState | null;
  if (!state?.flight) { navigate("/flights", { replace: true }); return null; }

  const { flight, cabinClass: initialCabin, tripType = "one_way", returnDate = "" } = state;
  const isReturn = tripType === "return";

  const [step,         setStep]         = useState<1 | 2 | 3>(1);
  const [cabin,        setCabin]        = useState(() => {
    if (initialCabin) return initialCabin;
    if (flight.available_seats_economy  > 0) return "economy";
    if (flight.available_seats_business > 0) return "business";
    return "first";
  });
  const [returnFlight, setReturnFlight] = useState<Flight | null>(null);
  const [returnCabin,  setReturnCabin]  = useState("economy");
  const [ikey,         setIkey]         = useState(() => crypto.randomUUID());
  const [result,       setResult]       = useState<BookResult | null>(null);

  const prices    = pricesOf(flight);
  const seats     = seatsOf(flight);
  const retPrices = returnFlight ? pricesOf(returnFlight) : {} as Record<string, number>;
  const retSeats  = returnFlight ? seatsOf(returnFlight)  : {} as Record<string, number>;

  const STEPS        = isReturn ? ["Outbound", "Return Flight", "Payment"] : ["Review", "Payment"];
  const PAYMENT_STEP = STEPS.length as 2 | 3;

  const outboundPrice = prices[cabin]          ?? 0;
  const returnPrice   = retPrices[returnCabin] ?? 0;
  const totalAmount   = outboundPrice + (isReturn ? returnPrice : 0);

  // Fetch return flights (pre-fetched immediately so step 2 loads fast)
  const { data: returnFlights = [], isFetching: fetchingReturn, isError: returnError } = useQuery<Flight[]>({
    queryKey: ["return-flights", flight.destination, flight.origin, returnDate],
    queryFn: async () => {
      const { data, error } = await flightClient.GET("/api/v1/flights", {
        params: {
          query: {
            origin:         flight.destination,
            destination:    flight.origin,
            departure_date: returnDate || undefined,
          },
        },
      });
      if (error) throw new Error("Failed to load return flights");
      const envelope = data as { items?: Flight[] } | null;
      return envelope?.items ?? [];
    },
    enabled: isReturn,
  });

  const bookAndPay = useMutation({
    mutationFn: async (pd: PaymentFormData) => {
      const groupId = isReturn ? crypto.randomUUID() : undefined;

      // Outbound booking
      const { data: b1, error: e1 } = await bookingClient.POST("/api/v1/bookings", {
        body: {
          flight_id:        flight.id,
          passenger_name:   user!.full_name,
          passenger_email:  user!.email,
          cabin_class:      cabin,
          trip_type:        isReturn ? "return" : "one_way",
          group_booking_id: groupId,
        } as any,
      });
      if (e1 || !b1) throw new Error("Failed to create outbound booking");
      const outbound = b1 as { id: string; booking_reference: string; total_price: number };

      let returnRef: string | undefined;
      let total = outbound.total_price;

      // Return booking (if return trip)
      if (isReturn && returnFlight) {
        const { data: b2, error: e2 } = await bookingClient.POST("/api/v1/bookings", {
          body: {
            flight_id:        returnFlight.id,
            passenger_name:   user!.full_name,
            passenger_email:  user!.email,
            cabin_class:      returnCabin,
            trip_type:        "return",
            group_booking_id: groupId,
          } as any,
        });
        if (e2 || !b2) {
          // Compensating transaction: cancel outbound booking
          await bookingClient.POST(`/api/v1/bookings/${outbound.id}/cancel` as any, {});
          throw new Error("Failed to create return booking");
        }
        const ret = b2 as { id: string; booking_reference: string; total_price: number };
        returnRef = ret.booking_reference;
        total     += ret.total_price;
      }

      // Payment for combined total
      const { data: pData, error: pErr } = await paymentClient.POST("/api/v1/payments", {
        body: {
          booking_id:      outbound.id,
          amount:          total,
          currency:        "USD",
          idempotency_key: ikey,
          ...pd,
        },
      });
      if (pErr) throw new Error("Payment request failed");
      const payment = pData as { status: string; transaction_ref?: string; failure_reason?: string };
      return { outboundRef: outbound.booking_reference, returnRef, payment, totalAmount: total };
    },
    onSuccess: ({ outboundRef, returnRef, payment, totalAmount: paid }) => {
      qc.invalidateQueries({ queryKey: ["bookings"] });
      setResult({
        success:        payment.status === "completed",
        outboundRef,
        returnRef,
        transactionRef: payment.transaction_ref ?? undefined,
        failureReason:  payment.failure_reason  ?? undefined,
        totalAmount:    paid,
      });
    },
    onError: () => setResult({
      success: false, outboundRef: "", totalAmount: 0,
      failureReason: "An unexpected error occurred.",
    }),
  });

  // ── Result screen ────────────────────────────────────────────────────────
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
                <h2 className="text-xl font-bold text-gray-900">
                  {isReturn ? "Return Trip Confirmed" : "Booking Confirmed"}
                </h2>
                <p className="mt-1 text-sm text-gray-400">Your seat{isReturn ? "s are" : " is"} reserved and payment was successful.</p>
              </div>
              <div className="rounded-xl bg-gray-50 p-4 text-left space-y-3 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-500">Outbound</span>
                  <div className="text-right">
                    <span className="font-mono font-bold text-blue-700 text-base tracking-wider">{result.outboundRef}</span>
                    <p className="text-[10px] text-gray-400">{cityLabel(flight.origin)} → {cityLabel(flight.destination)}</p>
                  </div>
                </div>
                {result.returnRef && returnFlight && (
                  <div className="flex justify-between">
                    <span className="text-gray-500">Return</span>
                    <div className="text-right">
                      <span className="font-mono font-bold text-blue-700 text-base tracking-wider">{result.returnRef}</span>
                      <p className="text-[10px] text-gray-400">{cityLabel(returnFlight.origin)} → {cityLabel(returnFlight.destination)}</p>
                    </div>
                  </div>
                )}
                <div className="flex justify-between border-t pt-3 mt-1">
                  <span className="text-gray-500">Total Paid</span>
                  <span className="font-bold text-gray-900">${result.totalAmount.toFixed(2)} USD</span>
                </div>
                {result.transactionRef && (
                  <div className="flex justify-between">
                    <span className="text-gray-500">Transaction ID</span>
                    <span className="font-mono text-xs text-gray-500">{result.transactionRef}</span>
                  </div>
                )}
              </div>
              <div className="flex gap-3">
                <button onClick={() => navigate("/bookings")}
                  className="flex-1 rounded-lg bg-blue-600 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 transition-colors">
                  View My Bookings
                </button>
                <button onClick={() => navigate("/flights")}
                  className="flex-1 rounded-lg border border-gray-300 py-2.5 text-sm font-medium hover:bg-gray-50 transition-colors">
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
              <div className="flex gap-3">
                <button onClick={() => navigate("/flights")}
                  className="flex-1 rounded-lg border border-gray-300 py-2.5 text-sm font-medium hover:bg-gray-50 transition-colors">
                  Cancel
                </button>
                <button onClick={() => { setResult(null); setStep(PAYMENT_STEP); setIkey(crypto.randomUUID()); }}
                  className="flex-1 rounded-lg bg-blue-600 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 transition-colors">
                  Retry Payment
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  // ── Main booking flow ────────────────────────────────────────────────────
  return (
    <div className="max-w-5xl mx-auto space-y-5">
      <button onClick={() => navigate("/flights")}
        className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800 transition-colors">
        <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
        Back to Flights
      </button>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">

        {/* ── Sidebar ── */}
        <div className="lg:col-span-1">
          <div className="rounded-2xl bg-white border border-gray-100 shadow-sm p-5 lg:sticky lg:top-6 space-y-5">
            <FlightSummaryCard flight={flight} cabin={cabin} label={isReturn ? "Outbound" : undefined} />

            {isReturn && returnFlight && (
              <>
                <div className="border-t" />
                <FlightSummaryCard flight={returnFlight} cabin={returnCabin} label="Return" />
              </>
            )}

            {isReturn && step < PAYMENT_STEP && (
              <div className="border-t pt-4">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-gray-500">Outbound</span>
                  <span className="font-semibold text-gray-800">${outboundPrice.toFixed(2)}</span>
                </div>
                {returnFlight && (
                  <div className="flex items-center justify-between text-sm mt-1">
                    <span className="text-gray-500">Return</span>
                    <span className="font-semibold text-gray-800">${returnPrice.toFixed(2)}</span>
                  </div>
                )}
                <div className="flex items-center justify-between mt-2 pt-2 border-t">
                  <span className="text-sm font-semibold text-gray-600">Total</span>
                  <span className="text-lg font-bold text-blue-700">${totalAmount.toFixed(2)}</span>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* ── Form area ── */}
        <div className="lg:col-span-2 space-y-5">

          {/* Stepper */}
          <div className="flex items-center gap-2">
            {STEPS.map((label, i) => {
              const num    = i + 1;
              const active = step === num;
              const done   = step > num;
              return (
                <div key={label} className="flex items-center gap-2">
                  {i > 0 && <div className={`h-px w-8 ${done || active ? "bg-blue-400" : "bg-gray-200"}`} />}
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

            {/* ── Step 1: Outbound / Review ── */}
            {step === 1 && (
              <div className="space-y-6">
                <h2 className="text-lg font-bold text-gray-900">
                  {isReturn ? "Review Outbound Flight" : "Review Your Booking"}
                </h2>

                <div>
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">Passenger Details</p>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <p className="mb-1 text-xs text-gray-400">Full Name</p>
                      <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-700">{user?.full_name}</div>
                    </div>
                    <div>
                      <p className="mb-1 text-xs text-gray-400">Email</p>
                      <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-700 truncate">{user?.email}</div>
                    </div>
                  </div>
                </div>

                <div>
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
                    {isReturn ? "Outbound Cabin Class" : "Select Cabin Class"}
                  </p>
                  <div className="grid grid-cols-3 gap-3">
                    {(["economy", "business", "first"] as const).map((c) => {
                      const price  = prices[c];
                      const avail  = seats[c];
                      const unavail = avail === 0 || price === 0;
                      return (
                        <button key={c} type="button" disabled={unavail} onClick={() => setCabin(c)}
                          className={`rounded-xl border p-3.5 text-left transition-colors ${
                            unavail ? "border-gray-100 bg-gray-50 opacity-40 cursor-not-allowed"
                            : cabin === c ? "border-blue-500 bg-blue-50 shadow-sm"
                            : "border-gray-200 hover:border-blue-300"
                          }`}>
                          <p className={`text-[10px] font-bold uppercase tracking-widest ${cabin === c && !unavail ? "text-blue-500" : "text-gray-400"}`}>
                            {c === "first" ? "First" : c === "business" ? "Business" : "Economy"}
                          </p>
                          <p className={`mt-1 text-xl font-bold tabular-nums ${cabin === c && !unavail ? "text-blue-700" : "text-gray-800"}`}>
                            ${price.toFixed(0)}
                          </p>
                          <p className={`mt-0.5 text-xs ${avail < 10 && !unavail ? "font-medium text-amber-500" : "text-gray-400"}`}>
                            {unavail ? "Unavailable" : `${avail} seat${avail !== 1 ? "s" : ""} left`}
                          </p>
                        </button>
                      );
                    })}
                  </div>
                </div>

                {!isReturn && (
                  <div className="flex items-center justify-between rounded-xl bg-blue-50 px-5 py-4">
                    <div>
                      <p className="text-sm text-gray-600 font-medium">Total to pay</p>
                      <p className="text-xs text-gray-400 mt-0.5 capitalize">{cabin} class · 1 passenger</p>
                    </div>
                    <p className="text-2xl font-bold text-blue-700">${outboundPrice.toFixed(2)}</p>
                  </div>
                )}

                <div className="flex gap-3">
                  <button onClick={() => navigate("/flights")}
                    className="flex-1 rounded-lg border border-gray-300 py-2.5 text-sm font-medium hover:bg-gray-50 transition-colors">
                    Cancel
                  </button>
                  <button onClick={() => setStep(isReturn ? 2 : (PAYMENT_STEP as 2 | 3))}
                    className="flex-1 rounded-lg bg-blue-600 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 transition-colors">
                    {isReturn ? "Choose Return Flight →" : "Continue to Payment →"}
                  </button>
                </div>
              </div>
            )}

            {/* ── Step 2: Return flight selector (return trips only) ── */}
            {step === 2 && isReturn && (
              <div className="space-y-5">
                <div>
                  <h2 className="text-lg font-bold text-gray-900">Select Your Return Flight</h2>
                  <p className="mt-1 text-sm text-gray-400">
                    {cityLabel(flight.destination)} → {cityLabel(flight.origin)}
                    {returnDate ? ` · ${fmtDate(returnDate)}` : ""}
                  </p>
                </div>

                {fetchingReturn && (
                  <p className="text-sm text-gray-400 animate-pulse">Loading return flights…</p>
                )}
                {returnError && (
                  <p className="text-sm text-red-500">Failed to load return flights. Please go back and try again.</p>
                )}
                {!fetchingReturn && !returnError && returnFlights.length === 0 && (
                  <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-700">
                    No return flights found for this date. Try a different return date.
                  </div>
                )}

                <div className="space-y-3">
                  {returnFlights.map((rf) => (
                    <ReturnFlightOption
                      key={rf.id}
                      flight={rf}
                      selected={returnFlight?.id === rf.id}
                      selectedCabin={returnCabin}
                      onSelect={() => {
                        setReturnFlight(rf);
                        // Default to same cabin as outbound if available
                        const rfSeats = seatsOf(rf);
                        const rfPrices = pricesOf(rf);
                        if (rfSeats[cabin] > 0 && rfPrices[cabin] > 0) {
                          setReturnCabin(cabin);
                        } else if (rfSeats.economy > 0) {
                          setReturnCabin("economy");
                        } else if (rfSeats.business > 0) {
                          setReturnCabin("business");
                        } else {
                          setReturnCabin("first");
                        }
                      }}
                      onCabin={setReturnCabin}
                    />
                  ))}
                </div>

                {returnFlight && (
                  <div className="flex items-center justify-between rounded-xl bg-blue-50 px-5 py-4 text-sm">
                    <div>
                      <p className="font-medium text-gray-600">Total for both legs</p>
                      <p className="text-xs text-gray-400 mt-0.5">
                        Outbound {cabin} ${outboundPrice.toFixed(2)} + Return {returnCabin} ${returnPrice.toFixed(2)}
                      </p>
                    </div>
                    <p className="text-2xl font-bold text-blue-700">${totalAmount.toFixed(2)}</p>
                  </div>
                )}

                <div className="flex gap-3">
                  <button onClick={() => setStep(1)}
                    className="flex-1 rounded-lg border border-gray-300 py-2.5 text-sm font-medium hover:bg-gray-50 transition-colors">
                    Back
                  </button>
                  <button
                    onClick={() => setStep(3)}
                    disabled={!returnFlight}
                    className="flex-1 rounded-lg bg-blue-600 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
                    Continue to Payment →
                  </button>
                </div>
              </div>
            )}

            {/* ── Step 3 / Step 2 (one-way): Payment ── */}
            {step === PAYMENT_STEP && (
              <div>
                <h2 className="mb-5 text-lg font-bold text-gray-900">Payment Details</h2>
                <PaymentForm
                  amount={totalAmount}
                  currency="USD"
                  isPending={bookAndPay.isPending}
                  onBack={() => setStep((isReturn ? 2 : 1) as 1 | 2)}
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
