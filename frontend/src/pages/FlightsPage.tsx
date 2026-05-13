import { useState, type FormEvent } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { flightClient, bookingClient } from "../api/client";
import { useAuth } from "../contexts/AuthContext";

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
  available_seats_economy: number;
  available_seats_business: number;
  available_seats_first: number;
  price_economy: number;
  price_business: number;
  price_first: number;
  gate: string | null;
  terminal: string | null;
}

const CABIN_PRICES: Record<string, keyof Flight> = {
  economy:  "price_economy",
  business: "price_business",
  first:    "price_first",
};

export function FlightsPage() {
  const { user } = useAuth();
  const qc = useQueryClient();

  const [search, setSearch] = useState({
    origin: "",
    destination: "",
    departure_date: "",
    cabin_class: "economy",
  });
  const [submitted, setSubmitted] = useState(false);
  const [bookingFlight, setBookingFlight] = useState<Flight | null>(null);
  const [bookingMsg, setBookingMsg] = useState("");

  const { data: flights = [], isFetching } = useQuery<Flight[]>({
    queryKey: ["flights", search],
    enabled: submitted,
    queryFn: async () => {
      const { data } = await flightClient.GET("/api/v1/flights", {
        params: {
          query: {
            origin:         search.origin      || undefined,
            destination:    search.destination  || undefined,
            departure_date: search.departure_date || undefined,
            cabin_class:    search.cabin_class  || undefined,
          },
        },
      });
      return (data as Flight[]) ?? [];
    },
  });

  const book = useMutation({
    mutationFn: async (flight: Flight) => {
      const { data, error } = await bookingClient.POST("/api/v1/bookings", {
        body: {
          flight_id:       flight.id,
          passenger_name:  user!.full_name,
          passenger_email: user!.email,
          cabin_class:     search.cabin_class,
        },
      });
      if (error) throw new Error("Booking failed");
      return data;
    },
    onSuccess: () => {
      setBookingFlight(null);
      setBookingMsg("Booking confirmed!");
      qc.invalidateQueries({ queryKey: ["bookings"] });
      setTimeout(() => setBookingMsg(""), 4000);
    },
  });

  function handleSearch(e: FormEvent) {
    e.preventDefault();
    setSubmitted(true);
  }

  const priceKey = CABIN_PRICES[search.cabin_class];

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-gray-900">Search Flights</h2>

      {bookingMsg && (
        <div className="rounded-lg bg-green-50 px-4 py-3 text-sm text-green-800">
          ✓ {bookingMsg}
        </div>
      )}

      {/* Search form */}
      <form
        onSubmit={handleSearch}
        className="rounded-xl bg-white p-6 shadow-sm border border-gray-100"
      >
        <div className="grid grid-cols-4 gap-4">
          {[
            { key: "origin",         label: "From",         type: "text",   placeholder: "e.g. CMB" },
            { key: "destination",    label: "To",           type: "text",   placeholder: "e.g. LHR" },
            { key: "departure_date", label: "Departure",    type: "date",   placeholder: ""          },
          ].map(({ key, label, type, placeholder }) => (
            <div key={key}>
              <label className="mb-1 block text-xs font-medium text-gray-500 uppercase">
                {label}
              </label>
              <input
                type={type}
                placeholder={placeholder}
                value={search[key as keyof typeof search]}
                onChange={(e) =>
                  setSearch((s) => ({ ...s, [key]: e.target.value }))
                }
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
          ))}

          <div>
            <label className="mb-1 block text-xs font-medium text-gray-500 uppercase">
              Cabin
            </label>
            <select
              value={search.cabin_class}
              onChange={(e) => setSearch((s) => ({ ...s, cabin_class: e.target.value }))}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              <option value="economy">Economy</option>
              <option value="business">Business</option>
              <option value="first">First</option>
            </select>
          </div>
        </div>

        <button
          type="submit"
          className="mt-4 rounded-lg bg-blue-600 px-6 py-2 text-sm font-semibold text-white hover:bg-blue-700 transition-colors"
        >
          Search
        </button>
      </form>

      {/* Results */}
      {isFetching && <p className="text-sm text-gray-500">Searching…</p>}

      {submitted && !isFetching && flights.length === 0 && (
        <p className="text-sm text-gray-500">No flights found for these criteria.</p>
      )}

      <div className="space-y-3">
        {flights.map((flight) => (
          <div
            key={flight.id}
            className="flex items-center justify-between rounded-xl bg-white p-5 shadow-sm border border-gray-100"
          >
            <div className="flex items-center gap-8">
              <div>
                <p className="text-xs text-gray-400">{flight.airline}</p>
                <p className="font-mono font-bold text-gray-800">{flight.flight_number}</p>
              </div>
              <div className="text-center">
                <p className="text-lg font-bold text-gray-900">{flight.origin}</p>
                <p className="text-xs text-gray-500">{flight.departure_time}</p>
              </div>
              <div className="text-gray-300">→</div>
              <div className="text-center">
                <p className="text-lg font-bold text-gray-900">{flight.destination}</p>
                <p className="text-xs text-gray-500">{flight.arrival_time}</p>
              </div>
              <div>
                <p className="text-xs text-gray-400">{flight.departure_date}</p>
                {flight.gate && (
                  <p className="text-xs text-gray-400">Gate {flight.gate}</p>
                )}
              </div>
            </div>
            <div className="flex items-center gap-6">
              <div className="text-right">
                <p className="text-2xl font-bold text-blue-700">
                  ${(flight[priceKey] as number)?.toFixed(2)}
                </p>
                <p className="text-xs text-gray-400 capitalize">{search.cabin_class}</p>
              </div>
              <button
                onClick={() => setBookingFlight(flight)}
                disabled={book.isPending}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-60 transition-colors"
              >
                Book
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Confirm booking modal */}
      {bookingFlight && (
        <div className="fixed inset-0 flex items-center justify-center bg-black/40 z-50">
          <div className="w-full max-w-sm rounded-2xl bg-white p-6 shadow-2xl">
            <h3 className="mb-4 text-lg font-bold">Confirm Booking</h3>
            <p className="text-sm text-gray-600 mb-1">
              <span className="font-medium">{bookingFlight.flight_number}</span>
              &nbsp;·&nbsp;{bookingFlight.origin} → {bookingFlight.destination}
            </p>
            <p className="text-sm text-gray-600 mb-4">
              {bookingFlight.departure_date} &nbsp;·&nbsp; {search.cabin_class} class
            </p>
            <p className="text-2xl font-bold text-blue-700 mb-6">
              ${(bookingFlight[priceKey] as number)?.toFixed(2)}
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setBookingFlight(null)}
                className="flex-1 rounded-lg border border-gray-300 py-2 text-sm font-medium hover:bg-gray-50 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => book.mutate(bookingFlight)}
                disabled={book.isPending}
                className="flex-1 rounded-lg bg-blue-600 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-60 transition-colors"
              >
                {book.isPending ? "Booking…" : "Confirm"}
              </button>
            </div>
            {book.isError && (
              <p className="mt-3 text-xs text-red-600">Booking failed. Please try again.</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
