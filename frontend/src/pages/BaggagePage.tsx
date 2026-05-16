import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { bookingClient, baggageClient, flightClient } from "../api/client";

interface Booking {
  id: string;
  booking_reference: string;
  flight_id: string;
  passenger_name: string;
  passenger_email: string;
  cabin_class: string;
  status: string;
}

interface Flight {
  id: string;
  flight_number: string;
  origin: string;
  destination: string;
  departure_date: string;
}

interface BaggageItem {
  id: string;
  tag_number: string;
  booking_id: string;
  passenger_name: string;
  flight_id: string;
  weight_kg: number;
  status: string;
  last_location: string | null;
  description: string | null;
  created_at: string;
}

function fmtDate(d: string) {
  return new Date(d + "T00:00:00").toLocaleDateString("en-US", {
    month: "short", day: "numeric", year: "numeric",
  });
}

const STATUS_STYLE: Record<string, string> = {
  checked_in:  "bg-blue-50   text-blue-700   border-blue-200",
  in_transit:  "bg-amber-50  text-amber-700  border-amber-200",
  arrived:     "bg-emerald-50 text-emerald-700 border-emerald-200",
  delivered:   "bg-emerald-50 text-emerald-700 border-emerald-200",
  lost:        "bg-red-50    text-red-600    border-red-200",
};

const STATUS_ICON: Record<string, string> = {
  checked_in: "📦",
  in_transit: "🚚",
  arrived:    "✅",
  delivered:  "✅",
  lost:       "❌",
};

function BookingBaggageRow({ booking }: { booking: Booking }) {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [weight, setWeight]     = useState("23");
  const [desc,   setDesc]       = useState("");

  const { data: flight } = useQuery<Flight>({
    queryKey: ["flight", booking.flight_id],
    queryFn: async () => {
      const { data } = await flightClient.GET("/api/v1/flights/{flight_id}" as any, {
        params: { path: { flight_id: booking.flight_id } },
      });
      return data as Flight;
    },
    staleTime: 5 * 60 * 1000,
  });

  const { data: bags = [], isLoading: loadingBags } = useQuery<BaggageItem[]>({
    queryKey: ["baggage", booking.id],
    queryFn: async () => {
      const { data } = await (baggageClient as any).GET("/api/v1/baggage/booking/{booking_id}", {
        params: { path: { booking_id: booking.id } },
      });
      return (data as BaggageItem[]) ?? [];
    },
    retry: false,
  });

  const addBag = useMutation({
    mutationFn: async () => {
      const { data, error } = await baggageClient.POST("/api/v1/baggage", {
        body: {
          booking_id:      booking.id,
          flight_id:       booking.flight_id,
          passenger_name:  booking.passenger_name,
          passenger_email: booking.passenger_email,
          weight_kg:       parseFloat(weight),
          description:     desc || undefined,
        },
      });
      if (error || !data) throw new Error("Failed to register baggage");
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["baggage", booking.id] });
      setShowForm(false);
      setWeight("23");
      setDesc("");
    },
  });

  const canAdd = ["confirmed", "paid", "checked-in"].includes(booking.status.toLowerCase());

  return (
    <div className="rounded-2xl bg-white border border-gray-100 shadow-sm overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100 bg-gray-50/50">
        <div className="flex items-center gap-3">
          <span className="font-mono font-bold text-blue-700 tracking-wider">{booking.booking_reference}</span>
          {flight && (
            <span className="text-sm text-gray-600">
              <span className="font-mono text-blue-600">{flight.origin}</span>
              {" → "}
              <span className="font-mono text-violet-600">{flight.destination}</span>
              {" · "}
              <span className="text-gray-400">{fmtDate(flight.departure_date)}</span>
              {" · "}
              <span className="text-gray-500 font-medium">{flight.flight_number}</span>
            </span>
          )}
        </div>
        {canAdd && (
          <button
            onClick={() => setShowForm((v) => !v)}
            className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-700 transition-colors"
          >
            + Add Bag
          </button>
        )}
      </div>

      {/* Add baggage form */}
      {showForm && (
        <div className="border-b border-gray-100 px-5 py-4 bg-blue-50/30 space-y-3">
          <p className="text-sm font-semibold text-gray-700">Register new bag</p>
          <div className="flex gap-3 items-end">
            <div>
              <label className="text-xs font-semibold uppercase tracking-wide text-gray-500 block mb-1">Weight (kg)</label>
              <input
                type="number" min="1" max="50" step="0.5"
                value={weight} onChange={(e) => setWeight(e.target.value)}
                className="w-24 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
            <div className="flex-1">
              <label className="text-xs font-semibold uppercase tracking-wide text-gray-500 block mb-1">Description (optional)</label>
              <input
                type="text" placeholder="e.g. Black suitcase"
                value={desc} onChange={(e) => setDesc(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
            <button
              onClick={() => addBag.mutate()}
              disabled={addBag.isPending || !weight}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {addBag.isPending ? "Registering…" : "Register"}
            </button>
            <button onClick={() => setShowForm(false)}
              className="rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-500 hover:bg-gray-50 transition-colors">
              Cancel
            </button>
          </div>
          {addBag.isError && (
            <p className="text-xs text-red-500">{addBag.error instanceof Error ? addBag.error.message : "Failed"}</p>
          )}
        </div>
      )}

      {/* Bags list */}
      {loadingBags ? (
        <p className="px-5 py-4 text-sm text-gray-400 animate-pulse">Loading baggage…</p>
      ) : bags.length === 0 ? (
        <p className="px-5 py-4 text-sm text-gray-400">No baggage registered for this booking.</p>
      ) : (
        <div className="divide-y divide-gray-50">
          {bags.map((bag) => {
            const style = STATUS_STYLE[bag.status] ?? "bg-gray-100 text-gray-500 border-gray-200";
            const icon  = STATUS_ICON[bag.status] ?? "📦";
            return (
              <div key={bag.id} className="flex items-center gap-4 px-5 py-3">
                <span className="text-xl">{icon}</span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-mono font-bold text-gray-900 text-sm">{bag.tag_number}</span>
                    <span className={`rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize ${style}`}>
                      {bag.status.replace(/_/g, " ")}
                    </span>
                  </div>
                  <div className="flex gap-4 mt-0.5 text-xs text-gray-500">
                    <span>{bag.weight_kg} kg</span>
                    {bag.description && <span>{bag.description}</span>}
                    {bag.last_location && (
                      <span className="text-blue-600 font-medium">📍 {bag.last_location}</span>
                    )}
                  </div>
                </div>
                <span className="text-xs text-gray-400 shrink-0">
                  {new Date(bag.created_at).toLocaleDateString()}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function BaggagePage() {
  const { data: bookings = [], isLoading, isError } = useQuery<Booking[]>({
    queryKey: ["bookings"],
    queryFn: async () => {
      const { data, error } = await bookingClient.GET("/api/v1/bookings", {});
      if (error) throw new Error("Failed");
      return (data as Booking[]) ?? [];
    },
  });

  const eligible = bookings.filter(
    (b) => !["cancelled"].includes(b.status.toLowerCase())
  );

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Baggage</h2>
          <p className="mt-1 text-sm text-gray-500">Register and track your baggage for each booking.</p>
        </div>
        <Link
          to="/track"
          className="flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 transition-colors shrink-0"
        >
          <span>🔍</span> Track by Tag
        </Link>
      </div>

      {isLoading && <p className="text-sm text-gray-400 animate-pulse">Loading bookings…</p>}
      {isError   && <p className="text-sm text-red-500">Failed to load bookings. Please refresh.</p>}

      {!isLoading && !isError && eligible.length === 0 && (
        <div className="rounded-2xl border border-dashed border-gray-200 bg-white px-8 py-14 text-center">
          <p className="font-semibold text-gray-500">No active bookings</p>
          <p className="mt-1 text-sm text-gray-400">Book a flight first to manage baggage.</p>
        </div>
      )}

      <div className="space-y-4">
        {eligible.map((b) => <BookingBaggageRow key={b.id} booking={b} />)}
      </div>
    </div>
  );
}
