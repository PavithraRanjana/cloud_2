import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { flightClient } from "../api/client";
import { AirportCombobox, AIRPORTS } from "../components/AirportCombobox";

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

function formatTime(t: string) {
  const [hStr, mStr] = t.slice(0, 5).split(":");
  const h = parseInt(hStr, 10);
  const period = h >= 12 ? "PM" : "AM";
  const h12 = h % 12 || 12;
  return `${h12}:${mStr} ${period}`;
}
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
          <span className="text-base text-blue-500">✈</span>
          <span className="font-bold text-blue-700 tracking-wide">{flight.flight_number}</span>
          <span className="text-sm font-medium text-indigo-400">{flight.airline}</span>
          {flight.aircraft_type && (
            <span className="hidden sm:inline rounded-full border border-sky-200 bg-sky-50 px-2.5 py-0.5 text-xs font-medium text-sky-600">
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
            <p className="text-3xl font-bold text-gray-900 tabular-nums">{formatTime(flight.departure_time)}</p>
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
        <div className="flex items-center gap-3 border-t border-gray-100 px-5 py-2.5 bg-gray-50/40">
          {cabinRows.map((c) => {
            const cabinStyle =
              c.label === "Economy"  ? "bg-emerald-50 text-emerald-700 border-emerald-200" :
              c.label === "Business" ? "bg-amber-50  text-amber-700  border-amber-200"    :
                                       "bg-purple-50 text-purple-700 border-purple-200";
            const seatStyle = c.seats < 15 && c.seats > 0 ? "text-red-500 font-semibold" : "text-gray-400";
            return (
              <div key={c.label} className={`flex items-center gap-1.5 rounded-full border px-3 py-0.5 text-xs font-medium ${cabinStyle}`}>
                <span>{c.label}</span>
                <span className="font-bold">${c.price.toFixed(0)}</span>
                <span className={seatStyle}>· {c.seats} left</span>
              </div>
            );
          })}
        </div>
      )}

      {/* Card footer */}
      <div className="flex items-center justify-between gap-4 border-t border-gray-100 bg-gray-50/60 px-5 py-3">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          {flight.gate && (
            <span className="rounded-full border border-slate-200 bg-slate-100 px-2.5 py-0.5 font-medium text-slate-600">
              Gate {flight.gate}
            </span>
          )}
          {flight.terminal && (
            <span className="rounded-full border border-slate-200 bg-slate-100 px-2.5 py-0.5 font-medium text-slate-600">
              Terminal {flight.terminal}
            </span>
          )}
          {!unavailable && (
            <span className="rounded-full border border-slate-200 bg-slate-100 px-2.5 py-0.5 font-medium text-slate-600">
              {isAny ? `${seats} seats` : `${seats} seat${seats !== 1 ? "s" : ""} left`}
            </span>
          )}
        </div>

        <div className="flex items-center gap-4 shrink-0">
          {!unavailable && price > 0 && (
            <div className="text-right">
              <p className="text-xl font-bold text-blue-700">${price.toFixed(2)}</p>
              <p className="text-[11px] capitalize font-medium text-blue-400">{priceLabel}</p>
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
  const navigate = useNavigate();

  const [filters, setFilters] = useState({
    origin: "",
    destination: "",
    departure_date: "",
    cabin_class: "",
  });
  const [tripType,    setTripType]    = useState<"one_way" | "return">("one_way");
  const [returnDate,  setReturnDate]  = useState("");

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

  function handleBook(flight: Flight) {
    navigate("/book", { state: { flight, cabinClass: filters.cabin_class, tripType, returnDate } });
  }

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-gray-900">Search Flights</h2>

      {/* Search form */}
      <div className="rounded-2xl bg-white p-5 shadow-sm border border-gray-100 space-y-4">

        {/* Trip type toggle */}
        <div className="flex gap-2">
          {(["one_way", "return"] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => { setTripType(t); if (t === "one_way") setReturnDate(""); }}
              className={`rounded-lg px-4 py-1.5 text-sm font-semibold transition-colors ${
                tripType === t
                  ? "bg-blue-600 text-white"
                  : "bg-gray-100 text-gray-500 hover:bg-gray-200"
              }`}
            >
              {t === "one_way" ? "One Way" : "Return"}
            </button>
          ))}
        </div>

        <div className={`grid grid-cols-2 gap-4 ${tripType === "return" ? "sm:grid-cols-5" : "sm:grid-cols-4"}`}>
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

          {tripType === "return" && (
            <div>
              <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-gray-500">
                Return Date
              </label>
              <input
                type="date"
                value={returnDate}
                min={filters.departure_date || undefined}
                onChange={(e) => setReturnDate(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
          )}

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
            onBook={() => handleBook(flight)}
            isBooking={false}
          />
        ))}
      </div>
    </div>
  );
}

