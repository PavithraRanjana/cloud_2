import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { flightClient, bookingClient, baggageClient } from "../api/client";
import { AIRPORTS } from "../components/AirportCombobox";

interface Flight {
  id: string;
  flight_number: string;
  airline: string;
  origin: string;
  destination: string;
  departure_date: string;
  departure_time: string;
  arrival_time: string;
  status: string;
  aircraft_type: string | null;
  available_seats_economy: number;
  available_seats_business: number;
  available_seats_first: number;
  price_economy: number;
  gate: string | null;
  terminal: string | null;
}

interface Booking {
  id: string;
  booking_reference: string;
  status: string;
  cabin_class: string;
  total_price: number;
  created_at: string;
}

interface BaggageItem {
  id: string;
  tag_number: string;
  booking_id: string;
  passenger_name: string;
  weight_kg: number;
  status: string;
  last_location: string | null;
  description: string | null;
}

const STATUS_STYLE: Record<string, { bg: string; text: string; border: string }> = {
  scheduled:  { bg: "bg-blue-50",    text: "text-blue-700",   border: "border-blue-200"   },
  boarding:   { bg: "bg-amber-50",   text: "text-amber-700",  border: "border-amber-200"  },
  departed:   { bg: "bg-sky-50",     text: "text-sky-700",    border: "border-sky-200"    },
  "in-flight":{ bg: "bg-violet-50",  text: "text-violet-700", border: "border-violet-200" },
  landed:     { bg: "bg-emerald-50", text: "text-emerald-700",border: "border-emerald-200"},
  arrived:    { bg: "bg-emerald-50", text: "text-emerald-700",border: "border-emerald-200"},
  delayed:    { bg: "bg-orange-50",  text: "text-orange-700", border: "border-orange-200" },
  cancelled:  { bg: "bg-red-50",     text: "text-red-600",    border: "border-red-200"    },
};

const BAGGAGE_STATUS_STYLE: Record<string, string> = {
  registered:       "bg-gray-100   text-gray-600   border-gray-200",
  checked_in:       "bg-blue-50    text-blue-700   border-blue-200",
  security_cleared: "bg-indigo-50  text-indigo-700 border-indigo-200",
  loaded:           "bg-violet-50  text-violet-700 border-violet-200",
  in_transit:       "bg-amber-50   text-amber-700  border-amber-200",
  arrived:          "bg-emerald-50 text-emerald-700 border-emerald-200",
  on_carousel:      "bg-teal-50    text-teal-700   border-teal-200",
  collected:        "bg-emerald-50 text-emerald-700 border-emerald-200",
  lost:             "bg-red-50     text-red-600    border-red-200",
  found:            "bg-orange-50  text-orange-700 border-orange-200",
};

const BOOKING_STATUS_STYLE: Record<string, string> = {
  pending_payment: "bg-yellow-50  text-yellow-700 border-yellow-200",
  confirmed:       "bg-blue-50    text-blue-700   border-blue-200",
  paid:            "bg-emerald-50 text-emerald-700 border-emerald-200",
  "checked-in":    "bg-sky-50     text-sky-700    border-sky-200",
  cancelled:       "bg-red-50     text-red-600    border-red-200",
  refunded:        "bg-gray-100   text-gray-500   border-gray-200",
};

function fmt(t: string) {
  const [h, m] = t.slice(0, 5).split(":");
  const hn = parseInt(h, 10);
  return `${hn % 12 || 12}:${m} ${hn >= 12 ? "PM" : "AM"}`;
}

function StatCard({ label, value, sub, color = "blue" }: {
  label: string; value: string | number; sub?: string; color?: string;
}) {
  const colors: Record<string, string> = {
    blue:   "text-blue-700",
    green:  "text-emerald-600",
    amber:  "text-amber-600",
    red:    "text-red-600",
    violet: "text-violet-600",
  };
  return (
    <div className="rounded-2xl bg-white border border-gray-100 shadow-sm p-5">
      <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">{label}</p>
      <p className={`mt-2 text-3xl font-bold tabular-nums ${colors[color] ?? colors.blue}`}>{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
    </div>
  );
}

export function AdminDashboardPage() {
  const { user } = useAuth();
  const today = new Date().toISOString().slice(0, 10);
  const weekEnd = new Date(Date.now() + 7 * 86400_000).toISOString().slice(0, 10);

  const { data: flightData } = useQuery<{ items: Flight[] }>({
    queryKey: ["admin-flights"],
    queryFn: async () => {
      const { data, error } = await (flightClient as any).GET("/api/v1/flights", {
        params: { query: { page_size: 500 } }, // cap raised to 500 in flight-service
      });
      if (error) throw new Error();
      return data as { items: Flight[] };
    },
  });

  const { data: bookingData = [] } = useQuery<Booking[]>({
    queryKey: ["admin-bookings"],
    queryFn: async () => {
      const { data } = await bookingClient.GET("/api/v1/bookings", {});
      return (data as Booking[]) ?? [];
    },
  });

  const { data: baggageData = [] } = useQuery<BaggageItem[]>({
    queryKey: ["admin-baggage"],
    queryFn: async () => {
      const { data } = await (baggageClient as any).GET("/api/v1/baggage", {});
      return (data as BaggageItem[]) ?? [];
    },
  });

  const flights  = flightData?.items ?? [];
  const bookings = bookingData;
  const baggage  = baggageData;

  // Flight metrics
  const totalFlights    = flights.length;
  const todayFlights    = flights.filter(f => f.departure_date === today);
  const weekFlights     = flights.filter(f => f.departure_date >= today && f.departure_date <= weekEnd);
  const delayedFlights  = flights.filter(f => f.status === "delayed");
  const cancelledFlights= flights.filter(f => f.status === "cancelled");

  const statusGroups = Object.entries(
    flights.reduce<Record<string, number>>((acc, f) => {
      acc[f.status] = (acc[f.status] ?? 0) + 1;
      return acc;
    }, {})
  ).sort(([a], [b]) => a.localeCompare(b));

  // Booking metrics
  const totalBookings    = bookings.length;
  const confirmedBookings= bookings.filter(b => ["confirmed", "paid", "checked-in"].includes(b.status));
  const revenue          = bookings
    .filter(b => ["paid", "confirmed", "checked-in"].includes(b.status))
    .reduce((s, b) => s + b.total_price, 0);

  const bookingGroups = Object.entries(
    bookings.reduce<Record<string, number>>((acc, b) => {
      acc[b.status] = (acc[b.status] ?? 0) + 1;
      return acc;
    }, {})
  );

  // Baggage metrics
  const totalBaggage   = baggage.length;
  const lostBaggage    = baggage.filter(b => b.status === "lost").length;
  const inTransit      = baggage.filter(b => ["in_transit", "loaded", "checked_in", "security_cleared"].includes(b.status)).length;
  const totalWeight    = baggage.reduce((s, b) => s + b.weight_kg, 0);
  const baggageGroups  = Object.entries(
    baggage.reduce<Record<string, number>>((acc, b) => {
      acc[b.status] = (acc[b.status] ?? 0) + 1;
      return acc;
    }, {})
  );

  // Upcoming flights today
  const upcomingToday = todayFlights
    .filter(f => ["scheduled", "boarding", "delayed"].includes(f.status))
    .slice(0, 8);

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">
            Welcome, {user?.full_name ?? user?.username}
          </h2>
          <p className="text-sm text-gray-500 mt-1">AeroLink operations overview · {new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric" })}</p>
        </div>
      </div>

      {/* Key stats */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard label="Total Flights"    value={totalFlights}             sub={`${weekFlights.length} this week`}       color="blue"   />
        <StatCard label="Today's Flights"  value={todayFlights.length}      sub={`${upcomingToday.length} active`}         color="violet" />
        <StatCard label="Delayed"          value={delayedFlights.length}    sub="require attention"                        color="amber"  />
        <StatCard label="Cancelled"        value={cancelledFlights.length}  sub="all time"                                 color="red"    />
      </div>

      {/* Flight status breakdown */}
      <div className="rounded-2xl bg-white border border-gray-100 shadow-sm p-6">
        <h3 className="text-sm font-bold uppercase tracking-widest text-gray-400 mb-4">Fleet Status</h3>
        {statusGroups.length === 0 ? (
          <p className="text-sm text-gray-400">No flights loaded.</p>
        ) : (
          <div className="flex flex-wrap gap-3">
            {statusGroups.map(([status, count]) => {
              const s = STATUS_STYLE[status] ?? { bg: "bg-gray-100", text: "text-gray-600", border: "border-gray-200" };
              const pct = totalFlights > 0 ? Math.round((count / totalFlights) * 100) : 0;
              return (
                <div key={status} className={`flex-1 min-w-[120px] rounded-xl border px-4 py-3 ${s.bg} ${s.border}`}>
                  <p className={`text-xs font-bold uppercase tracking-wide ${s.text}`}>{status}</p>
                  <p className={`text-2xl font-bold tabular-nums mt-1 ${s.text}`}>{count}</p>
                  <p className={`text-xs mt-0.5 opacity-70 ${s.text}`}>{pct}% of total</p>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Today's flights table */}
      <div className="rounded-2xl bg-white border border-gray-100 shadow-sm overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-50">
          <h3 className="text-sm font-bold uppercase tracking-widest text-gray-400">Today's Schedule</h3>
          <Link to="/flights" className="text-sm text-blue-600 hover:underline">View all →</Link>
        </div>
        {upcomingToday.length === 0 ? (
          <p className="px-6 py-8 text-sm text-gray-400 text-center">No active flights scheduled for today.</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs font-semibold text-gray-400 uppercase">
              <tr>
                {["Flight", "Route", "Departure", "Aircraft", "Gate", "Seats (E/B/F)", "Status"].map(h => (
                  <th key={h} className="px-4 py-3 text-left whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {upcomingToday.map(f => {
                const s = STATUS_STYLE[f.status] ?? { bg: "", text: "text-gray-600", border: "" };
                const origin = AIRPORTS[f.origin];
                const dest   = AIRPORTS[f.destination];
                return (
                  <tr key={f.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-3 font-mono font-bold text-blue-700">{f.flight_number}</td>
                    <td className="px-4 py-3 text-gray-700">
                      <span className="font-semibold">{f.origin}</span>
                      <span className="text-gray-400 mx-1">→</span>
                      <span className="font-semibold">{f.destination}</span>
                      <p className="text-xs text-gray-400">{origin?.city} → {dest?.city}</p>
                    </td>
                    <td className="px-4 py-3 text-gray-700 tabular-nums">{fmt(f.departure_time)}</td>
                    <td className="px-4 py-3 text-gray-500">{f.aircraft_type ?? "—"}</td>
                    <td className="px-4 py-3 font-mono text-gray-600">{f.terminal ? `T${f.terminal}` : ""}{f.gate ? ` · ${f.gate}` : "—"}</td>
                    <td className="px-4 py-3 tabular-nums text-gray-600 text-xs">
                      <span className="text-emerald-600 font-medium">{f.available_seats_economy}</span>
                      <span className="text-gray-300 mx-1">/</span>
                      <span className="text-amber-600 font-medium">{f.available_seats_business}</span>
                      <span className="text-gray-300 mx-1">/</span>
                      <span className="text-violet-600 font-medium">{f.available_seats_first}</span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize ${s.bg} ${s.text} ${s.border}`}>
                        {f.status}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Bookings & Revenue */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard label="Total Bookings"    value={totalBookings}                sub={`${confirmedBookings.length} active`}  color="blue"  />
        <StatCard label="Total Revenue"     value={`$${revenue.toLocaleString("en-US", { minimumFractionDigits: 0 })}`} sub="from paid bookings" color="green" />
        <StatCard label="Cancellation Rate" value={totalBookings > 0 ? `${Math.round((bookings.filter(b => b.status === "cancelled").length / totalBookings) * 100)}%` : "0%"} sub="of all bookings" color="amber" />
      </div>

      {/* Booking status breakdown */}
      {bookingGroups.length > 0 && (
        <div className="rounded-2xl bg-white border border-gray-100 shadow-sm p-6">
          <h3 className="text-sm font-bold uppercase tracking-widest text-gray-400 mb-4">Booking Breakdown</h3>
          <div className="flex flex-wrap gap-3">
            {bookingGroups.map(([status, count]) => {
              const style = BOOKING_STATUS_STYLE[status] ?? "bg-gray-100 text-gray-500 border-gray-200";
              return (
                <div key={status} className={`rounded-xl border px-4 py-3 min-w-[120px] ${style}`}>
                  <p className="text-xs font-bold uppercase tracking-wide opacity-80">{status.replace(/_/g, " ")}</p>
                  <p className="text-2xl font-bold tabular-nums mt-1">{count}</p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Baggage metrics */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard label="Total Bags"     value={totalBaggage}                                                                          sub="all registered bags"   color="blue"   />
        <StatCard label="In Transit"     value={inTransit}                                                                             sub="checked in or loading" color="violet" />
        <StatCard label="Total Weight"   value={`${totalWeight.toLocaleString("en-US", { maximumFractionDigits: 0 })} kg`}            sub="across all bags"       color="green"  />
        <StatCard label="Lost Bags"      value={lostBaggage}                                                                           sub="require attention"     color="red"    />
      </div>

      {baggageGroups.length > 0 && (
        <div className="rounded-2xl bg-white border border-gray-100 shadow-sm p-6">
          <h3 className="text-sm font-bold uppercase tracking-widest text-gray-400 mb-4">Baggage Status Breakdown</h3>
          <div className="flex flex-wrap gap-3">
            {baggageGroups.map(([status, count]) => {
              const style = BAGGAGE_STATUS_STYLE[status] ?? "bg-gray-100 text-gray-500 border-gray-200";
              return (
                <div key={status} className={`rounded-xl border px-4 py-3 min-w-[120px] ${style}`}>
                  <p className="text-xs font-bold uppercase tracking-wide opacity-80">{status.replace(/_/g, " ")}</p>
                  <p className="text-2xl font-bold tabular-nums mt-1">{count}</p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Quick actions */}
      <div>
        <h3 className="mb-3 text-sm font-bold uppercase tracking-widest text-gray-400">Quick Actions</h3>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            { to: "/flights",       label: "Flight Schedule",   icon: "📅", desc: "View public flight board" },
            { to: "/notifications", label: "Notifications",     icon: "🔔", desc: "System notifications" },
            { to: "/profile",       label: "Account Settings",  icon: "⚙", desc: "Manage your admin account" },
          ].map(({ to, label, icon, desc }) => (
            <Link key={to} to={to}
              className="flex flex-col gap-1.5 rounded-2xl bg-white border border-gray-100 shadow-sm p-4 hover:border-blue-300 hover:shadow-md transition-all">
              <span className="text-2xl">{icon}</span>
              <p className="text-sm font-semibold text-gray-800">{label}</p>
              <p className="text-xs text-gray-400">{desc}</p>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
