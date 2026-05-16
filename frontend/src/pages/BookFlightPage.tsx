import React, { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { flightClient, bookingClient, paymentClient } from "../api/client";
import { useAuth } from "../contexts/AuthContext";
import { PaymentForm, PaymentFormData } from "../components/PaymentForm";
import { SeatMap } from "../components/SeatMap";
import { AIRPORTS } from "../components/AirportCombobox";
import { NATIONALITIES } from "../data/nationalities";

// ── Types ─────────────────────────────────────────────────────────────────
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

// ── Helpers ───────────────────────────────────────────────────────────────
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
  return `${h % 12 || 12}:${mStr} ${h >= 12 ? "PM" : "AM"}`;
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
function pricesOf(f: Flight): Record<string, number> {
  return { economy: f.price_economy, business: f.price_business, first: f.price_first };
}
function seatsOf(f: Flight): Record<string, number> {
  return { economy: f.available_seats_economy, business: f.available_seats_business, first: f.available_seats_first };
}

// ── Sub-components ────────────────────────────────────────────────────────
function FlightSummaryCard({ flight, cabin, label }: { flight: Flight; cabin: string; label?: string }) {
  const dur = calcDuration(flight.departure_date, flight.departure_time, flight.arrival_date, flight.arrival_time);
  const statusKey = flight.status.toLowerCase();
  return (
    <div className="space-y-3">
      {label && <p className="text-[10px] font-bold uppercase tracking-widest text-blue-500">{label}</p>}
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
      <p className="text-xs text-gray-400 capitalize">{cabin} class</p>
    </div>
  );
}

interface ReturnOptionProps {
  flight: Flight; selected: boolean; selectedCabin: string;
  onSelect: () => void; onCabin: (c: string) => void;
}
function ReturnFlightOption({ flight, selected, selectedCabin, onSelect, onCabin }: ReturnOptionProps) {
  const prices = pricesOf(flight);
  const seats  = seatsOf(flight);
  const dur    = calcDuration(flight.departure_date, flight.departure_time, flight.arrival_date, flight.arrival_time);
  const statusKey = flight.status.toLowerCase();
  return (
    <div onClick={onSelect}
      className={`cursor-pointer rounded-xl border p-4 transition-all ${selected ? "border-blue-500 bg-blue-50/40 shadow-sm" : "border-gray-200 hover:border-blue-300 bg-white"}`}>
      <div className="flex items-center justify-between gap-4">
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
            <span className="hidden sm:inline text-xs text-gray-400 border border-gray-200 rounded px-1.5 py-0.5">{flight.aircraft_type}</span>
          )}
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium capitalize ${STATUS_STYLE[statusKey] ?? "bg-gray-100 text-gray-500"}`}>{statusKey}</span>
          <span className="text-sm font-bold text-blue-700">from ${Math.min(...Object.values(prices).filter(p => p > 0)).toFixed(0)}</span>
          {selected && <span className="rounded-full bg-blue-600 px-2.5 py-0.5 text-[10px] font-semibold text-white">Selected</span>}
        </div>
      </div>
      {selected && (
        <div className="mt-4 grid grid-cols-3 gap-2" onClick={(e) => e.stopPropagation()}>
          {(["economy", "business", "first"] as const).map((c) => {
            const price = prices[c]; const avail = seats[c]; const unavail = avail === 0 || price === 0;
            return (
              <button key={c} type="button" disabled={unavail} onClick={() => onCabin(c)}
                className={`rounded-lg border p-2.5 text-left transition-colors ${unavail ? "border-gray-100 bg-gray-50 opacity-40 cursor-not-allowed" : selectedCabin === c ? "border-blue-500 bg-blue-50" : "border-gray-200 hover:border-blue-300"}`}>
                <p className={`text-[10px] font-bold uppercase tracking-widest ${selectedCabin === c && !unavail ? "text-blue-500" : "text-gray-400"}`}>
                  {c === "first" ? "First" : c === "business" ? "Business" : "Economy"}
                </p>
                <p className={`text-base font-bold mt-0.5 ${selectedCabin === c && !unavail ? "text-blue-700" : "text-gray-800"}`}>${price.toFixed(0)}</p>
                <p className={`text-[10px] mt-0.5 ${avail < 10 && !unavail ? "text-amber-500 font-medium" : "text-gray-400"}`}>{unavail ? "N/A" : `${avail} left`}</p>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Country phone codes ───────────────────────────────────────────────────
const COUNTRY_CODES = [
  { dial: "+1",   label: "+1  (USA / Canada)"       },
  { dial: "+44",  label: "+44  (United Kingdom)"    },
  { dial: "+61",  label: "+61  (Australia)"         },
  { dial: "+64",  label: "+64  (New Zealand)"       },
  { dial: "+353", label: "+353 (Ireland)"           },
  { dial: "+65",  label: "+65  (Singapore)"         },
  { dial: "+94",  label: "+94  (Sri Lanka)"         },
  { dial: "+91",  label: "+91  (India)"             },
  { dial: "+86",  label: "+86  (China)"             },
  { dial: "+81",  label: "+81  (Japan)"             },
  { dial: "+82",  label: "+82  (South Korea)"       },
  { dial: "+49",  label: "+49  (Germany)"           },
  { dial: "+33",  label: "+33  (France)"            },
  { dial: "+39",  label: "+39  (Italy)"             },
  { dial: "+34",  label: "+34  (Spain)"             },
  { dial: "+31",  label: "+31  (Netherlands)"       },
  { dial: "+32",  label: "+32  (Belgium)"           },
  { dial: "+41",  label: "+41  (Switzerland)"       },
  { dial: "+46",  label: "+46  (Sweden)"            },
  { dial: "+47",  label: "+47  (Norway)"            },
  { dial: "+45",  label: "+45  (Denmark)"           },
  { dial: "+358", label: "+358 (Finland)"           },
  { dial: "+48",  label: "+48  (Poland)"            },
  { dial: "+7",   label: "+7   (Russia)"            },
  { dial: "+55",  label: "+55  (Brazil)"            },
  { dial: "+52",  label: "+52  (Mexico)"            },
  { dial: "+54",  label: "+54  (Argentina)"         },
  { dial: "+27",  label: "+27  (South Africa)"      },
  { dial: "+20",  label: "+20  (Egypt)"             },
  { dial: "+971", label: "+971 (UAE)"               },
  { dial: "+966", label: "+966 (Saudi Arabia)"      },
  { dial: "+974", label: "+974 (Qatar)"             },
  { dial: "+90",  label: "+90  (Turkey)"            },
  { dial: "+92",  label: "+92  (Pakistan)"          },
  { dial: "+880", label: "+880 (Bangladesh)"        },
  { dial: "+66",  label: "+66  (Thailand)"          },
  { dial: "+84",  label: "+84  (Vietnam)"           },
  { dial: "+62",  label: "+62  (Indonesia)"         },
  { dial: "+63",  label: "+63  (Philippines)"       },
  { dial: "+60",  label: "+60  (Malaysia)"          },
  { dial: "+234", label: "+234 (Nigeria)"           },
  { dial: "+254", label: "+254 (Kenya)"             },
  { dial: "+251", label: "+251 (Ethiopia)"          },
];

// ── Form field component ──────────────────────────────────────────────────
function Field({
  label, error, required = false, children,
}: { label: string; error?: string; required?: boolean; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-gray-500">
        {label}{required && <span className="ml-0.5 text-red-400">*</span>}
      </label>
      {children}
      {error && <p className="mt-1 text-xs text-red-500">{error}</p>}
    </div>
  );
}

const INPUT = "w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500";
const INPUT_ERR = "w-full rounded-lg border border-red-400 px-3 py-2 text-sm focus:border-red-500 focus:outline-none focus:ring-1 focus:ring-red-400";
const SELECT = "w-full h-9 rounded-lg border border-gray-300 px-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 bg-white";
const SELECT_ERR = "w-full h-9 rounded-lg border border-red-400 px-2 text-sm focus:border-red-500 focus:outline-none focus:ring-1 focus:ring-red-400 bg-white";

// ── Main page ─────────────────────────────────────────────────────────────
export function BookFlightPage() {
  const navigate  = useNavigate();
  const location  = useLocation();
  const { user }  = useAuth();
  const qc        = useQueryClient();

  const state = location.state as BookState | null;
  if (!state?.flight) { navigate("/flights", { replace: true }); return null; }

  const { flight, cabinClass: initialCabin, tripType = "one_way", returnDate = "" } = state;
  const isReturn = tripType === "return";

  // Step constants
  const STEP_OUTBOUND   = 1;
  const STEP_RETURN_SEL = 2; // return trips only
  const STEP_PASSENGER  = isReturn ? 3 : 1;
  const STEP_CONTACT    = isReturn ? 4 : 2;
  const STEP_SEAT       = isReturn ? 5 : 3;
  const STEP_SUMMARY    = isReturn ? 6 : 4;
  const STEP_PAYMENT    = isReturn ? 7 : 5;

  const STEPS = isReturn
    ? ["Outbound", "Return", "Passenger", "Contact", "Seat", "Summary", "Payment"]
    : ["Passenger", "Contact", "Seat", "Summary", "Payment"];

  // ── State ────────────────────────────────────────────────────────────────
  const [step, setStep] = useState<number>(isReturn ? STEP_OUTBOUND : STEP_PASSENGER);

  // Outbound cabin
  const [cabin, setCabin] = useState(() => {
    if (initialCabin) return initialCabin;
    if (flight.available_seats_economy  > 0) return "economy";
    if (flight.available_seats_business > 0) return "business";
    return "first";
  });

  // Return flight
  const [returnFlight, setReturnFlight] = useState<Flight | null>(null);
  const [returnCabin,  setReturnCabin]  = useState("economy");

  // Passenger details
  const [passenger, setPassenger] = useState({
    title: "", gender: "",
    first_name: "", middle_name: "", last_name: "",
    dob_day: "", dob_month: "", dob_year: "",
    nationality: "",
    passport_number: "",
    passport_exp_day: "", passport_exp_month: "", passport_exp_year: "",
  });
  const [natQuery,  setNatQuery]  = useState("");
  const [natOpen,   setNatOpen]   = useState(false);
  const [ccQuery,   setCcQuery]   = useState("");
  const [ccOpen,    setCcOpen]    = useState(false);

  // Contact details
  const [contact, setContact] = useState({
    email: user?.email ?? "",
    country_code: "+1",
    phone_number: "",
  });

  // Seat selection
  const [selectedSeat,       setSelectedSeat]       = useState("");
  const [selectedReturnSeat, setSelectedReturnSeat] = useState("");
  const [seatTab,            setSeatTab]            = useState<"outbound" | "return">("outbound");

  // Payment idempotency key
  const [ikey] = useState(() => crypto.randomUUID());
  const [result, setResult] = useState<BookResult | null>(null);

  // Validation errors
  const [errors, setErrors] = useState<Record<string, string>>({});

  // ── Derived values ───────────────────────────────────────────────────────
  const prices    = pricesOf(flight);
  const seats     = seatsOf(flight);
  const retPrices = returnFlight ? pricesOf(returnFlight) : {} as Record<string, number>;
  const outboundPrice = prices[cabin]          ?? 0;
  const returnPrice   = retPrices[returnCabin] ?? 0;
  const totalAmount   = outboundPrice + (isReturn ? returnPrice : 0);

  // ── Data fetching ────────────────────────────────────────────────────────
  const { data: returnFlights = [], isFetching: fetchingReturn, isError: returnError } = useQuery<Flight[]>({
    queryKey: ["return-flights", flight.destination, flight.origin, returnDate],
    queryFn: async () => {
      const { data, error } = await flightClient.GET("/api/v1/flights", {
        params: { query: { origin: flight.destination, destination: flight.origin, departure_date: returnDate || undefined } },
      });
      if (error) throw new Error("Failed to load return flights");
      const envelope = data as { items?: Flight[] } | null;
      return envelope?.items ?? [];
    },
    enabled: isReturn,
  });

  const { data: bookedSeats = [], isFetching: loadingSeats } = useQuery<string[]>({
    queryKey: ["seat-availability", flight.id],
    queryFn: async () => {
      const res = await (bookingClient as any).GET("/api/v1/bookings/seat-availability", {
        params: { query: { flight_id: flight.id } },
      });
      return (res.data?.booked_seats as string[]) ?? [];
    },
    enabled: step === STEP_SEAT,
  });

  const { data: returnBookedSeats = [], isFetching: loadingReturnSeats } = useQuery<string[]>({
    queryKey: ["seat-availability", returnFlight?.id],
    queryFn: async () => {
      if (!returnFlight) return [];
      const res = await (bookingClient as any).GET("/api/v1/bookings/seat-availability", {
        params: { query: { flight_id: returnFlight.id } },
      });
      return (res.data?.booked_seats as string[]) ?? [];
    },
    enabled: step === STEP_SEAT && isReturn && !!returnFlight,
  });

  const filteredNationalities = NATIONALITIES.filter((n) =>
    n.toLowerCase().includes(natQuery.toLowerCase())
  ).slice(0, 20);

  const filteredCountryCodes = COUNTRY_CODES.filter((cc) =>
    cc.label.toLowerCase().includes(ccQuery.toLowerCase()) ||
    cc.dial.includes(ccQuery)
  );

  // ── Validation ───────────────────────────────────────────────────────────
  function validatePassenger(): boolean {
    const e: Record<string, string> = {};
    if (!passenger.title)                e.title = "Please select a title";
    if (!passenger.gender)               e.gender = "Please select gender";
    if (!passenger.first_name.trim())    e.first_name = "First name is required";
    if (!passenger.last_name.trim())     e.last_name = "Last name is required";
    if (!passenger.dob_day || !passenger.dob_month || !passenger.dob_year)
      e.dob = "Full date of birth is required";
    if (!passenger.nationality)          e.nationality = "Nationality is required";
    if (!passenger.passport_number.trim()) e.passport_number = "Passport number is required";
    if (!passenger.passport_exp_day || !passenger.passport_exp_month || !passenger.passport_exp_year)
      e.passport_expiry = "Passport expiry date is required";
    setErrors(e);
    return Object.keys(e).length === 0;
  }

  function validateContact(): boolean {
    const e: Record<string, string> = {};
    if (!contact.email.trim() || !contact.email.includes("@")) e.email = "Valid email is required";
    if (!contact.phone_number.trim()) e.phone_number = "Phone number is required";
    setErrors(e);
    return Object.keys(e).length === 0;
  }

  function validateSeat(): boolean {
    const e: Record<string, string> = {};
    if (!selectedSeat) e.seat = "Please select a seat for the outbound flight";
    if (isReturn && returnFlight && !selectedReturnSeat) e.return_seat = "Please select a seat for the return flight";
    setErrors(e);
    return Object.keys(e).length === 0;
  }

  // ── Navigation ───────────────────────────────────────────────────────────
  function handleNext() {
    setErrors({});
    if (step === STEP_PASSENGER && !validatePassenger()) return;
    if (step === STEP_CONTACT   && !validateContact())   return;
    if (step === STEP_SEAT      && !validateSeat())      return;
    setStep((s) => s + 1);
  }

  function handleBack() {
    setErrors({});
    if (step === (isReturn ? STEP_OUTBOUND : STEP_PASSENGER)) navigate("/flights");
    else setStep((s) => s - 1);
  }

  // ── Booking mutation ──────────────────────────────────────────────────────
  const bookAndPay = useMutation({
    mutationFn: async (pd: PaymentFormData) => {
      const dobStr = passenger.dob_year && passenger.dob_month && passenger.dob_day
        ? `${passenger.dob_year}-${passenger.dob_month.padStart(2, "0")}-${passenger.dob_day.padStart(2, "0")}`
        : undefined;
      const passportExpiryStr = passenger.passport_exp_year && passenger.passport_exp_month && passenger.passport_exp_day
        ? `${passenger.passport_exp_year}-${passenger.passport_exp_month.padStart(2, "0")}-${passenger.passport_exp_day.padStart(2, "0")}`
        : undefined;
      const passengerName = `${passenger.first_name}${passenger.middle_name ? " " + passenger.middle_name : ""} ${passenger.last_name}`.trim();

      const commonPassengerFields = {
        passenger_name:   passengerName,
        passenger_email:  contact.email,
        title:            passenger.title || undefined,
        gender:           passenger.gender || undefined,
        first_name:       passenger.first_name,
        middle_name:      passenger.middle_name || undefined,
        last_name:        passenger.last_name,
        date_of_birth:    dobStr,
        nationality:      passenger.nationality,
        passport_number:  passenger.passport_number,
        passport_expiry:  passportExpiryStr,
        country_code:     contact.country_code,
        phone_number:     contact.phone_number,
      };

      const groupId = isReturn ? crypto.randomUUID() : undefined;

      // Outbound booking
      const { data: b1, error: e1 } = await bookingClient.POST("/api/v1/bookings", {
        body: {
          flight_id:        flight.id,
          cabin_class:      cabin,
          trip_type:        isReturn ? "return" : "one_way",
          group_booking_id: groupId,
          seat_number:      selectedSeat,
          ...commonPassengerFields,
        } as any,
      });
      if (e1 || !b1) throw new Error("Failed to create outbound booking");
      const outbound = b1 as { id: string; booking_reference: string; total_price: number };

      let returnRef: string | undefined;
      let total = outbound.total_price;

      // Return booking
      if (isReturn && returnFlight) {
        const { data: b2, error: e2 } = await bookingClient.POST("/api/v1/bookings", {
          body: {
            flight_id:        returnFlight.id,
            cabin_class:      returnCabin,
            trip_type:        "return",
            group_booking_id: groupId,
            seat_number:      selectedReturnSeat,
            ...commonPassengerFields,
          } as any,
        });
        if (e2 || !b2) {
          await bookingClient.POST(`/api/v1/bookings/${outbound.id}/cancel` as any, {});
          throw new Error("Failed to create return booking");
        }
        const ret = b2 as { id: string; booking_reference: string; total_price: number };
        returnRef = ret.booking_reference;
        total    += ret.total_price;
      }

      // Payment
      const { data: pData, error: pErr } = await paymentClient.POST("/api/v1/payments", {
        body: { booking_id: outbound.id, amount: total, currency: "USD", idempotency_key: ikey, ...pd },
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
    onError: (err: unknown) => setResult({
      success: false, outboundRef: "", totalAmount: 0,
      failureReason: err instanceof Error ? err.message : "An unexpected error occurred.",
    }),
  });

  // ── Result screen ─────────────────────────────────────────────────────────
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
                <h2 className="text-xl font-bold text-gray-900">{isReturn ? "Return Trip Confirmed" : "Booking Confirmed"}</h2>
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
                <div className="flex justify-between border-t pt-3">
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
                  className="flex-1 rounded-lg border border-gray-300 py-2.5 text-sm font-medium hover:bg-gray-50 transition-colors">Cancel</button>
                <button onClick={() => { setResult(null); setStep(STEP_PAYMENT); }}
                  className="flex-1 rounded-lg bg-blue-600 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 transition-colors">Retry Payment</button>
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  // ── Stepper ───────────────────────────────────────────────────────────────
  // For one-way: step 1 = STEP_PASSENGER. For return: step 1 = STEP_OUTBOUND.
  // Map step to label index for display.
  const stepLabelIndex = isReturn ? step - 1 : step - 1;

  // ── Layout ────────────────────────────────────────────────────────────────
  return (
    <div className="max-w-5xl mx-auto space-y-5">
      <button onClick={handleBack}
        className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800 transition-colors">
        <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
        {step === (isReturn ? STEP_OUTBOUND : STEP_PASSENGER) ? "Back to Flights" : "Back"}
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

            {/* Price breakdown */}
            <div className="border-t pt-4 space-y-1.5">
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-500">Outbound</span>
                <span className="font-semibold text-gray-800">${outboundPrice.toFixed(2)}</span>
              </div>
              {isReturn && returnFlight && (
                <div className="flex items-center justify-between text-sm">
                  <span className="text-gray-500">Return</span>
                  <span className="font-semibold text-gray-800">${returnPrice.toFixed(2)}</span>
                </div>
              )}
              <div className="flex items-center justify-between pt-1 border-t mt-1">
                <span className="text-sm font-semibold text-gray-600">Total</span>
                <span className="text-lg font-bold text-blue-700">${totalAmount.toFixed(2)}</span>
              </div>
            </div>
          </div>
        </div>

        {/* ── Form area ── */}
        <div className="lg:col-span-2 space-y-5">

          {/* Stepper */}
          <div className="flex flex-wrap items-center gap-2">
            {STEPS.map((label, i) => {
              const active = stepLabelIndex === i;
              const done   = stepLabelIndex > i;
              return (
                <div key={label} className="flex items-center gap-2">
                  {i > 0 && <div className={`h-px w-6 ${done || active ? "bg-blue-400" : "bg-gray-200"}`} />}
                  <div className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold transition-colors ${active ? "bg-blue-600 text-white" : done ? "bg-blue-100 text-blue-600" : "bg-gray-100 text-gray-400"}`}>
                    {done ? (
                      <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={3}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                    ) : i + 1}
                  </div>
                  <span className={`text-xs font-medium ${active ? "text-gray-900" : "text-gray-400"}`}>{label}</span>
                </div>
              );
            })}
          </div>

          <div className="rounded-2xl bg-white border border-gray-100 shadow-sm p-6">

            {/* ═══════════════════════════════════════════════════════════
                Step: Outbound cabin selection (return trips only)
            ═══════════════════════════════════════════════════════════ */}
            {isReturn && step === STEP_OUTBOUND && (
              <div className="space-y-6">
                <h2 className="text-lg font-bold text-gray-900">Select Outbound Cabin</h2>
                <div className="grid grid-cols-3 gap-3">
                  {(["economy", "business", "first"] as const).map((c) => {
                    const price = prices[c]; const avail = seats[c]; const unavail = avail === 0 || price === 0;
                    return (
                      <button key={c} type="button" disabled={unavail} onClick={() => setCabin(c)}
                        className={`rounded-xl border p-3.5 text-left transition-colors ${unavail ? "border-gray-100 bg-gray-50 opacity-40 cursor-not-allowed" : cabin === c ? "border-blue-500 bg-blue-50 shadow-sm" : "border-gray-200 hover:border-blue-300"}`}>
                        <p className={`text-[10px] font-bold uppercase tracking-widest ${cabin === c && !unavail ? "text-blue-500" : "text-gray-400"}`}>
                          {c === "first" ? "First" : c === "business" ? "Business" : "Economy"}
                        </p>
                        <p className={`mt-1 text-xl font-bold tabular-nums ${cabin === c && !unavail ? "text-blue-700" : "text-gray-800"}`}>${price.toFixed(0)}</p>
                        <p className={`mt-0.5 text-xs ${avail < 10 && !unavail ? "font-medium text-amber-500" : "text-gray-400"}`}>
                          {unavail ? "Unavailable" : `${avail} seat${avail !== 1 ? "s" : ""} left`}
                        </p>
                      </button>
                    );
                  })}
                </div>
                <div className="flex gap-3">
                  <button onClick={handleBack} className="flex-1 rounded-lg border border-gray-300 py-2.5 text-sm font-medium hover:bg-gray-50 transition-colors">Cancel</button>
                  <button onClick={handleNext} className="flex-1 rounded-lg bg-blue-600 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 transition-colors">Choose Return Flight →</button>
                </div>
              </div>
            )}

            {/* ═══════════════════════════════════════════════════════════
                Step: Return flight selection
            ═══════════════════════════════════════════════════════════ */}
            {isReturn && step === STEP_RETURN_SEL && (
              <div className="space-y-5">
                <div>
                  <h2 className="text-lg font-bold text-gray-900">Select Return Flight</h2>
                  <p className="mt-1 text-sm text-gray-400">
                    {cityLabel(flight.destination)} → {cityLabel(flight.origin)}
                    {returnDate ? ` · ${fmtDate(returnDate)}` : ""}
                  </p>
                </div>
                {fetchingReturn && <p className="text-sm text-gray-400 animate-pulse">Loading return flights…</p>}
                {returnError    && <p className="text-sm text-red-500">Failed to load return flights.</p>}
                {!fetchingReturn && !returnError && returnFlights.length === 0 && (
                  <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-700">
                    No return flights found for this date. Try a different return date.
                  </div>
                )}
                <div className="space-y-3">
                  {returnFlights.map((rf) => (
                    <ReturnFlightOption key={rf.id} flight={rf}
                      selected={returnFlight?.id === rf.id} selectedCabin={returnCabin}
                      onSelect={() => {
                        setReturnFlight(rf);
                        const rfs = seatsOf(rf); const rfp = pricesOf(rf);
                        if (rfs[cabin] > 0 && rfp[cabin] > 0) setReturnCabin(cabin);
                        else if (rfs.economy > 0) setReturnCabin("economy");
                        else if (rfs.business > 0) setReturnCabin("business");
                        else setReturnCabin("first");
                      }}
                      onCabin={setReturnCabin}
                    />
                  ))}
                </div>
                {returnFlight && (
                  <div className="flex items-center justify-between rounded-xl bg-blue-50 px-5 py-3 text-sm">
                    <span className="font-medium text-gray-600">Both legs</span>
                    <span className="text-2xl font-bold text-blue-700">${totalAmount.toFixed(2)}</span>
                  </div>
                )}
                <div className="flex gap-3">
                  <button onClick={handleBack} className="flex-1 rounded-lg border border-gray-300 py-2.5 text-sm font-medium hover:bg-gray-50 transition-colors">Back</button>
                  <button onClick={handleNext} disabled={!returnFlight}
                    className="flex-1 rounded-lg bg-blue-600 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
                    Continue →
                  </button>
                </div>
              </div>
            )}

            {/* ═══════════════════════════════════════════════════════════
                Step: Passenger Details
            ═══════════════════════════════════════════════════════════ */}
            {step === STEP_PASSENGER && (
              <div className="space-y-5">
                <div>
                  <h2 className="text-lg font-bold text-gray-900">Passenger Details</h2>
                  <p className="mt-1 text-sm text-gray-400">Please enter details exactly as shown on your passport.</p>
                </div>

                {/* Title + Gender */}
                <div className="grid grid-cols-2 gap-4">
                  <Field label="Title" required error={errors.title}>
                    <select value={passenger.title} onChange={(e) => setPassenger(p => ({ ...p, title: e.target.value }))}
                      className={errors.title ? SELECT_ERR : SELECT}>
                      <option value="">Select…</option>
                      {["Mr", "Mrs", "Ms", "Miss", "Dr", "General", "Prof"].map((t) => (
                        <option key={t} value={t.toLowerCase()}>{t}</option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Gender" required error={errors.gender}>
                    <div className="flex gap-2 mt-0.5">
                      {["Male", "Female"].map((g) => (
                        <button key={g} type="button"
                          onClick={() => setPassenger(p => ({ ...p, gender: g.toLowerCase() }))}
                          className={`flex-1 rounded-lg border py-2 text-sm font-medium transition-colors ${passenger.gender === g.toLowerCase() ? "border-blue-500 bg-blue-50 text-blue-700" : "border-gray-300 text-gray-500 hover:border-blue-300"} ${errors.gender ? "border-red-400" : ""}`}>
                          {g}
                        </button>
                      ))}
                    </div>
                  </Field>
                </div>

                {/* Names */}
                <div className="grid grid-cols-2 gap-4">
                  <Field label="First Name (as on passport)" required error={errors.first_name}>
                    <input value={passenger.first_name}
                      onChange={(e) => setPassenger(p => ({ ...p, first_name: e.target.value }))}
                      className={errors.first_name ? INPUT_ERR : INPUT} placeholder="e.g. John" />
                  </Field>
                  <Field label="Middle Name (optional)">
                    <input value={passenger.middle_name}
                      onChange={(e) => setPassenger(p => ({ ...p, middle_name: e.target.value }))}
                      className={INPUT} placeholder="Middle name(s)" />
                  </Field>
                </div>
                <Field label="Last Name (as on passport)" required error={errors.last_name}>
                  <input value={passenger.last_name}
                    onChange={(e) => setPassenger(p => ({ ...p, last_name: e.target.value }))}
                    className={errors.last_name ? INPUT_ERR : INPUT} placeholder="e.g. Smith" />
                </Field>

                {/* Date of birth */}
                <Field label="Date of Birth" required error={errors.dob}>
                  <div className="grid grid-cols-3 gap-2">
                    <select value={passenger.dob_day} onChange={(e) => setPassenger(p => ({ ...p, dob_day: e.target.value }))}
                      className={errors.dob ? SELECT_ERR : SELECT}>
                      <option value="">Day</option>
                      {Array.from({ length: 31 }, (_, i) => i + 1).map((d) => (
                        <option key={d} value={String(d)}>{d}</option>
                      ))}
                    </select>
                    <select value={passenger.dob_month} onChange={(e) => setPassenger(p => ({ ...p, dob_month: e.target.value }))}
                      className={errors.dob ? SELECT_ERR : SELECT}>
                      <option value="">Month</option>
                      {["January","February","March","April","May","June","July","August","September","October","November","December"].map((m, i) => (
                        <option key={m} value={String(i + 1)}>{m}</option>
                      ))}
                    </select>
                    <select value={passenger.dob_year} onChange={(e) => setPassenger(p => ({ ...p, dob_year: e.target.value }))}
                      className={errors.dob ? SELECT_ERR : SELECT}>
                      <option value="">Year</option>
                      {Array.from({ length: 110 }, (_, i) => 2010 - i).map((y) => (
                        <option key={y} value={String(y)}>{y}</option>
                      ))}
                    </select>
                  </div>
                </Field>

                {/* Nationality */}
                <Field label="Nationality" required error={errors.nationality}>
                  <div className="relative">
                    <input
                      type="text"
                      value={natQuery || passenger.nationality}
                      placeholder="Search nationality…"
                      onChange={(e) => {
                        setNatQuery(e.target.value);
                        setPassenger(p => ({ ...p, nationality: "" }));
                        setNatOpen(true);
                      }}
                      onFocus={() => { setNatQuery(""); setNatOpen(true); }}
                      onBlur={() => setTimeout(() => setNatOpen(false), 150)}
                      className={errors.nationality ? INPUT_ERR : INPUT}
                    />
                    {natOpen && filteredNationalities.length > 0 && (
                      <ul className="absolute z-50 mt-1 max-h-48 w-full overflow-y-auto rounded-lg border border-gray-200 bg-white shadow-lg text-sm">
                        {filteredNationalities.map((n) => (
                          <li key={n}
                            onMouseDown={() => {
                              setPassenger(p => ({ ...p, nationality: n }));
                              setNatQuery(n);
                              setNatOpen(false);
                            }}
                            className="cursor-pointer px-3 py-2 hover:bg-blue-50 text-gray-700">{n}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                </Field>

                {/* Passport */}
                <div className="grid grid-cols-2 gap-4">
                  <Field label="Passport Number" required error={errors.passport_number}>
                    <input value={passenger.passport_number}
                      onChange={(e) => setPassenger(p => ({ ...p, passport_number: e.target.value.toUpperCase() }))}
                      className={errors.passport_number ? INPUT_ERR : INPUT} placeholder="e.g. A1234567" />
                  </Field>
                  <Field label="Passport Expiry Date" required error={errors.passport_expiry}>
                    <div className="grid grid-cols-3 gap-1">
                      <select value={passenger.passport_exp_day} onChange={(e) => setPassenger(p => ({ ...p, passport_exp_day: e.target.value }))}
                        className={errors.passport_expiry ? SELECT_ERR : SELECT}>
                        <option value="">Day</option>
                        {Array.from({ length: 31 }, (_, i) => i + 1).map((d) => <option key={d} value={String(d)}>{d}</option>)}
                      </select>
                      <select value={passenger.passport_exp_month} onChange={(e) => setPassenger(p => ({ ...p, passport_exp_month: e.target.value }))}
                        className={errors.passport_expiry ? SELECT_ERR : SELECT}>
                        <option value="">Mon</option>
                        {["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"].map((m, i) => (
                          <option key={m} value={String(i + 1)}>{m}</option>
                        ))}
                      </select>
                      <select value={passenger.passport_exp_year} onChange={(e) => setPassenger(p => ({ ...p, passport_exp_year: e.target.value }))}
                        className={errors.passport_expiry ? SELECT_ERR : SELECT}>
                        <option value="">Year</option>
                        {Array.from({ length: 15 }, (_, i) => 2025 + i).map((y) => <option key={y} value={String(y)}>{y}</option>)}
                      </select>
                    </div>
                  </Field>
                </div>

                <div className="flex gap-3 pt-2">
                  <button onClick={handleBack} className="flex-1 rounded-lg border border-gray-300 py-2.5 text-sm font-medium hover:bg-gray-50 transition-colors">
                    {isReturn ? "Back" : "Cancel"}
                  </button>
                  <button onClick={handleNext} className="flex-1 rounded-lg bg-blue-600 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 transition-colors">
                    Continue →
                  </button>
                </div>
              </div>
            )}

            {/* ═══════════════════════════════════════════════════════════
                Step: Contact Details
            ═══════════════════════════════════════════════════════════ */}
            {step === STEP_CONTACT && (
              <div className="space-y-5">
                <div>
                  <h2 className="text-lg font-bold text-gray-900">Contact Details</h2>
                  <p className="mt-1 text-sm text-gray-400">Tell us where to send your booking confirmation.</p>
                </div>

                <Field label="Email Address" required error={errors.email}>
                  <input type="email" value={contact.email}
                    onChange={(e) => setContact(c => ({ ...c, email: e.target.value }))}
                    className={errors.email ? INPUT_ERR : INPUT} placeholder="your@email.com" />
                </Field>

                <Field label="Mobile Number" required error={errors.phone_number}>
                  <div className="flex gap-2">
                    <div className="relative w-48 shrink-0">
                      <input
                        type="text"
                        value={ccQuery || contact.country_code}
                        placeholder="Search code…"
                        onChange={(e) => {
                          setCcQuery(e.target.value);
                          setContact(c => ({ ...c, country_code: "" }));
                          setCcOpen(true);
                        }}
                        onFocus={() => { setCcQuery(""); setCcOpen(true); }}
                        onBlur={() => setTimeout(() => setCcOpen(false), 150)}
                        className="w-full h-9 rounded-lg border border-gray-300 px-2 text-sm bg-white focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                      />
                      {ccOpen && filteredCountryCodes.length > 0 && (
                        <ul className="absolute z-50 mt-1 max-h-48 w-64 overflow-y-auto rounded-lg border border-gray-200 bg-white shadow-lg text-sm">
                          {filteredCountryCodes.map((cc) => (
                            <li key={cc.dial}
                              onMouseDown={() => {
                                setContact(c => ({ ...c, country_code: cc.dial }));
                                setCcQuery(cc.dial);
                                setCcOpen(false);
                              }}
                              className="cursor-pointer px-3 py-2 hover:bg-blue-50 text-gray-700">{cc.label}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                    <input type="tel" value={contact.phone_number}
                      onChange={(e) => setContact(c => ({ ...c, phone_number: e.target.value }))}
                      className={`flex-1 ${errors.phone_number ? INPUT_ERR : INPUT}`}
                      placeholder="Phone number" />
                  </div>
                </Field>

                <div className="flex gap-3 pt-2">
                  <button onClick={handleBack} className="flex-1 rounded-lg border border-gray-300 py-2.5 text-sm font-medium hover:bg-gray-50 transition-colors">Back</button>
                  <button onClick={handleNext} className="flex-1 rounded-lg bg-blue-600 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 transition-colors">Continue →</button>
                </div>
              </div>
            )}

            {/* ═══════════════════════════════════════════════════════════
                Step: Seat Selection
            ═══════════════════════════════════════════════════════════ */}
            {step === STEP_SEAT && (
              <div className="space-y-5">
                <div>
                  <h2 className="text-lg font-bold text-gray-900">Choose Your Seat</h2>
                  <p className="mt-1 text-sm text-gray-400">Gray seats are already taken. Click to select yours.</p>
                </div>

                {/* Tab switcher for return trips */}
                {isReturn && returnFlight && (
                  <div className="flex gap-2">
                    {(["outbound", "return"] as const).map((tab) => (
                      <button key={tab} type="button" onClick={() => setSeatTab(tab)}
                        className={`rounded-lg px-4 py-1.5 text-sm font-semibold transition-colors capitalize ${seatTab === tab ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-500 hover:bg-gray-200"}`}>
                        {tab === "outbound" ? `Outbound${selectedSeat ? ` · ${selectedSeat}` : ""}` : `Return${selectedReturnSeat ? ` · ${selectedReturnSeat}` : ""}`}
                      </button>
                    ))}
                  </div>
                )}

                {(seatTab === "outbound" || !isReturn) && (
                  <SeatMap
                    aircraftType={flight.aircraft_type}
                    cabinClass={cabin}
                    selectedSeat={selectedSeat}
                    onSeatSelect={setSelectedSeat}
                    bookedSeats={bookedSeats}
                    isLoading={loadingSeats}
                  />
                )}
                {isReturn && seatTab === "return" && returnFlight && (
                  <SeatMap
                    aircraftType={returnFlight.aircraft_type}
                    cabinClass={returnCabin}
                    selectedSeat={selectedReturnSeat}
                    onSeatSelect={setSelectedReturnSeat}
                    bookedSeats={returnBookedSeats}
                    isLoading={loadingReturnSeats}
                  />
                )}

                {errors.seat && <p className="text-xs text-red-500">{errors.seat}</p>}
                {errors.return_seat && <p className="text-xs text-red-500">{errors.return_seat}</p>}

                <div className="flex gap-3 pt-2">
                  <button onClick={handleBack} className="flex-1 rounded-lg border border-gray-300 py-2.5 text-sm font-medium hover:bg-gray-50 transition-colors">Back</button>
                  <button onClick={handleNext}
                    disabled={!selectedSeat || (isReturn && !!returnFlight && !selectedReturnSeat)}
                    className="flex-1 rounded-lg bg-blue-600 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
                    Continue →
                  </button>
                </div>
              </div>
            )}

            {/* ═══════════════════════════════════════════════════════════
                Step: Summary
            ═══════════════════════════════════════════════════════════ */}
            {step === STEP_SUMMARY && (
              <div className="space-y-5">
                <h2 className="text-lg font-bold text-gray-900">Review Your Booking</h2>

                {/* Passenger info */}
                <div className="rounded-xl border border-gray-100 bg-gray-50/50 p-4 space-y-2">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-blue-500 mb-3">Passenger</p>
                  <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
                    <div><span className="text-gray-400">Name</span><p className="font-semibold text-gray-800 capitalize">{passenger.title} {passenger.first_name}{passenger.middle_name ? " " + passenger.middle_name : ""} {passenger.last_name}</p></div>
                    <div><span className="text-gray-400">Gender</span><p className="font-semibold text-gray-800 capitalize">{passenger.gender}</p></div>
                    <div><span className="text-gray-400">Date of Birth</span><p className="font-semibold text-gray-800">{passenger.dob_day}/{passenger.dob_month}/{passenger.dob_year}</p></div>
                    <div><span className="text-gray-400">Nationality</span><p className="font-semibold text-gray-800">{passenger.nationality}</p></div>
                    <div><span className="text-gray-400">Passport</span><p className="font-semibold text-gray-800 font-mono">{passenger.passport_number}</p></div>
                    <div><span className="text-gray-400">Passport Expiry</span><p className="font-semibold text-gray-800">{passenger.passport_exp_day}/{passenger.passport_exp_month}/{passenger.passport_exp_year}</p></div>
                  </div>
                </div>

                {/* Contact info */}
                <div className="rounded-xl border border-gray-100 bg-gray-50/50 p-4 space-y-2">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-blue-500 mb-3">Contact</p>
                  <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
                    <div><span className="text-gray-400">Email</span><p className="font-semibold text-gray-800">{contact.email}</p></div>
                    <div><span className="text-gray-400">Phone</span><p className="font-semibold text-gray-800">{contact.country_code} {contact.phone_number}</p></div>
                  </div>
                </div>

                {/* Outbound flight */}
                <div className="rounded-xl border border-gray-100 bg-gray-50/50 p-4">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-blue-500 mb-3">{isReturn ? "Outbound Flight" : "Flight"}</p>
                  <div className="flex items-center justify-between text-sm">
                    <div>
                      <p className="font-bold text-gray-900">{flight.flight_number} · {cityLabel(flight.origin)} → {cityLabel(flight.destination)}</p>
                      <p className="text-gray-400">{fmtDate(flight.departure_date)} · {fmt(flight.departure_time)} · <span className="capitalize">{cabin}</span></p>
                    </div>
                    <div className="text-right">
                      {selectedSeat && <span className="rounded bg-blue-100 text-blue-700 px-2 py-0.5 text-xs font-mono font-semibold">Seat {selectedSeat}</span>}
                      <p className="mt-1 font-bold text-gray-800">${outboundPrice.toFixed(2)}</p>
                    </div>
                  </div>
                </div>

                {/* Return flight */}
                {isReturn && returnFlight && (
                  <div className="rounded-xl border border-gray-100 bg-gray-50/50 p-4">
                    <p className="text-[10px] font-bold uppercase tracking-widest text-blue-500 mb-3">Return Flight</p>
                    <div className="flex items-center justify-between text-sm">
                      <div>
                        <p className="font-bold text-gray-900">{returnFlight.flight_number} · {cityLabel(returnFlight.origin)} → {cityLabel(returnFlight.destination)}</p>
                        <p className="text-gray-400">{fmtDate(returnFlight.departure_date)} · {fmt(returnFlight.departure_time)} · <span className="capitalize">{returnCabin}</span></p>
                      </div>
                      <div className="text-right">
                        {selectedReturnSeat && <span className="rounded bg-blue-100 text-blue-700 px-2 py-0.5 text-xs font-mono font-semibold">Seat {selectedReturnSeat}</span>}
                        <p className="mt-1 font-bold text-gray-800">${returnPrice.toFixed(2)}</p>
                      </div>
                    </div>
                  </div>
                )}

                {/* Total */}
                <div className="flex items-center justify-between rounded-xl bg-blue-50 border border-blue-100 px-5 py-4">
                  <div>
                    <p className="text-sm font-semibold text-gray-700">Total to pay</p>
                    <p className="text-xs text-gray-400 mt-0.5">Includes all taxes and fees</p>
                  </div>
                  <p className="text-2xl font-bold text-blue-700">${totalAmount.toFixed(2)} <span className="text-sm font-normal text-gray-400">USD</span></p>
                </div>

                <div className="flex gap-3 pt-2">
                  <button onClick={handleBack} className="flex-1 rounded-lg border border-gray-300 py-2.5 text-sm font-medium hover:bg-gray-50 transition-colors">Back</button>
                  <button onClick={handleNext} className="flex-1 rounded-lg bg-blue-600 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 transition-colors">
                    Confirm & Pay →
                  </button>
                </div>
              </div>
            )}

            {/* ═══════════════════════════════════════════════════════════
                Step: Payment
            ═══════════════════════════════════════════════════════════ */}
            {step === STEP_PAYMENT && (
              <div>
                <h2 className="mb-5 text-lg font-bold text-gray-900">Payment Details</h2>
                <PaymentForm
                  amount={totalAmount}
                  currency="USD"
                  isPending={bookAndPay.isPending}
                  onBack={handleBack}
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
