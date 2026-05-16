import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { bookingClient, notificationClient, flightClient, passengerClient } from "../api/client";
import { AdminDashboardPage } from "./AdminDashboardPage";

interface Booking {
  id: string;
  booking_reference: string;
  flight_id: string;
  cabin_class: string;
  status: string;
  total_price: number;
  seat_numbers?: string;
  created_at: string;
}

interface Flight {
  flight_number: string;
  origin: string;
  destination: string;
  departure_date: string;
  departure_time: string;
  airline: string;
  gate: string | null;
}

interface Profile {
  loyalty_tier: string;
  loyalty_points: number;
}

interface Notification {
  id: string;
  subject: string;
  event_type: string;
  is_read: boolean;
  created_at: string;
}

function fmt(t: string) {
  const [h, m] = t.slice(0, 5).split(":");
  const hn = parseInt(h, 10);
  return `${hn % 12 || 12}:${m} ${hn >= 12 ? "PM" : "AM"}`;
}
function fmtDate(d: string) {
  return new Date(d + "T00:00:00").toLocaleDateString("en-US", {
    weekday: "short", month: "short", day: "numeric",
  });
}
function timeAgo(iso: string) {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60)    return "Just now";
  if (diff < 3600)  return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

const TIER_CONFIG: Record<string, { label: string; color: string; next: string | null; nextAt: number }> = {
  bronze:   { label: "Bronze",   color: "from-amber-700 to-amber-500",    next: "Silver",   nextAt: 1_000  },
  silver:   { label: "Silver",   color: "from-slate-500 to-slate-400",    next: "Gold",     nextAt: 5_000  },
  gold:     { label: "Gold",     color: "from-yellow-500 to-yellow-400",  next: "Platinum", nextAt: 10_000 },
  platinum: { label: "Platinum", color: "from-violet-600 to-violet-400",  next: null,       nextAt: 0      },
};

const STATUS_STYLE: Record<string, string> = {
  confirmed:    "bg-blue-50   text-blue-700   border-blue-200",
  paid:         "bg-emerald-50 text-emerald-700 border-emerald-200",
  "checked-in": "bg-sky-50    text-sky-700    border-sky-200",
  cancelled:    "bg-red-50    text-red-600    border-red-200",
  pending:      "bg-yellow-50 text-yellow-700 border-yellow-200",
};

const EVENT_ICON: Record<string, string> = {
  BookingCreated:      "🎫",
  PaymentCompleted:    "💳",
  CheckInCompleted:    "✅",
  BaggageRegistered:   "🧳",
  BaggageStatusChanged:"🧳",
  BookingCancelled:    "❌",
  PaymentRefunded:     "↩️",
  FlightUpdated:       "✈",
};

function NextFlightCard({ booking }: { booking: Booking }) {
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

  const isCheckedIn = ["checked-in", "boarded"].includes(booking.status.toLowerCase());

  return (
    <div className="rounded-2xl bg-gradient-to-br from-blue-600 to-blue-500 p-5 text-white shadow-md">
      <div className="flex items-center justify-between mb-4">
        <p className="text-xs font-bold uppercase tracking-widest text-blue-200">Next Flight</p>
        <span className="rounded-full bg-white/20 px-2.5 py-0.5 text-xs font-semibold capitalize">
          {booking.status.replace(/-/g, " ")}
        </span>
      </div>

      {flight ? (
        <div className="space-y-3">
          <div className="flex items-center gap-4">
            <div className="text-center">
              <p className="text-3xl font-bold tabular-nums">{flight.origin}</p>
              <p className="text-sm text-blue-200 mt-0.5">{fmt(flight.departure_time)}</p>
            </div>
            <div className="flex flex-col items-center flex-1">
              <div className="flex w-full items-center gap-1">
                <div className="flex-1 h-px bg-blue-300" />
                <svg className="w-5 h-5 text-blue-300" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M21 16v-2l-8-5V3.5a1.5 1.5 0 0 0-3 0V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z"/>
                </svg>
                <div className="flex-1 h-px bg-blue-300" />
              </div>
              <p className="text-[11px] text-blue-300 mt-1">{flight.flight_number} · {flight.airline}</p>
            </div>
            <div className="text-center">
              <p className="text-3xl font-bold tabular-nums">{flight.destination}</p>
              <p className="text-sm text-blue-200 mt-0.5">{fmtDate(flight.departure_date)}</p>
            </div>
          </div>
          <div className="flex items-center justify-between pt-1 border-t border-blue-400/40 text-sm">
            <div className="flex gap-3">
              {booking.seat_numbers && (
                <span className="text-blue-200">Seat <span className="font-mono font-bold text-white">{booking.seat_numbers}</span></span>
              )}
              <span className="text-blue-200 capitalize">{booking.cabin_class}</span>
              {flight.gate && <span className="text-blue-200">Gate <span className="font-bold text-white">{flight.gate}</span></span>}
            </div>
            {!isCheckedIn && (
              <Link to="/checkin"
                className="rounded-lg bg-white text-blue-700 px-3 py-1.5 text-xs font-bold hover:bg-blue-50 transition-colors">
                Check In
              </Link>
            )}
          </div>
        </div>
      ) : (
        <p className="text-blue-200 text-sm animate-pulse">Loading flight details…</p>
      )}
    </div>
  );
}

export function DashboardPage() {
  const { user } = useAuth();
  if (user?.role === "admin") return <AdminDashboardPage />;

  const { data: bookings = [] } = useQuery<Booking[]>({
    queryKey: ["bookings"],
    queryFn: async () => {
      const { data } = await bookingClient.GET("/api/v1/bookings", {});
      return (data as Booking[]) ?? [];
    },
  });

  const { data: notifications = [] } = useQuery<Notification[]>({
    queryKey: ["notifications"],
    queryFn: async () => {
      const { data } = await notificationClient.GET("/api/v1/notifications", {});
      return (data as Notification[]) ?? [];
    },
  });

  const { data: profile } = useQuery<Profile>({
    queryKey: ["passenger-profile"],
    queryFn: async () => {
      const { data } = await passengerClient.GET("/api/v1/passengers/profile", {});
      return data as Profile;
    },
    retry: false,
  });

  const activeBookings = bookings.filter((b) => !["cancelled"].includes(b.status.toLowerCase()));
  const nextFlight     = activeBookings.find((b) => ["confirmed","paid","checked-in"].includes(b.status.toLowerCase()));
  const totalSpent     = bookings
    .filter((b) => ["confirmed","paid","checked-in","completed"].includes(b.status.toLowerCase()))
    .reduce((s, b) => s + b.total_price, 0);
  const unreadCount    = notifications.filter((n) => !n.is_read).length;
  const recentNotifs   = notifications.slice(0, 4);

  const stats = [
    { label: "Total Bookings",  value: bookings.length,             sub: `${activeBookings.length} active` },
    { label: "Total Spent",     value: `$${totalSpent.toFixed(0)}`, sub: "USD" },
    { label: "Notifications",   value: unreadCount,                 sub: "unread", link: "/notifications" },
  ];

  const tier       = profile ? (TIER_CONFIG[profile.loyalty_tier] ?? TIER_CONFIG.bronze) : null;
  const pts        = profile?.loyalty_points ?? 0;
  const ptsToNext  = tier?.next ? Math.max(0, tier.nextAt - pts) : 0;
  const progress   = tier?.next
    ? Math.min(100, Math.round((pts / tier.nextAt) * 100))
    : 100;

  const quickActions = [
    { to: "/flights",       label: "Search Flights", icon: (
      <svg className="w-7 h-7" viewBox="0 0 24 24" fill="currentColor">
        <path d="M21 16v-2l-8-5V3.5a1.5 1.5 0 0 0-3 0V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z"/>
      </svg>
    )},
    { to: "/bookings",      label: "My Bookings", icon: (
      <svg className="w-7 h-7" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
      </svg>
    )},
    { to: "/checkin",       label: "Check-In", icon: (
      <svg className="w-7 h-7" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 6v.75m0 3v.75m0 3v.75m0 3V18m-9-5.25h5.25M7.5 15h3M3.375 5.25c-.621 0-1.125.504-1.125 1.125v3.026a2.999 2.999 0 010 5.198v3.026c0 .621.504 1.125 1.125 1.125h17.25c.621 0 1.125-.504 1.125-1.125v-3.026a3 3 0 010-5.198V6.375c0-.621-.504-1.125-1.125-1.125H3.375z" />
      </svg>
    )},
    { to: "/baggage",       label: "Baggage", icon: (
      <svg className="w-7 h-7" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M20 7H4a2 2 0 00-2 2v10a2 2 0 002 2h16a2 2 0 002-2V9a2 2 0 00-2-2zM16 7V5a2 2 0 00-2-2h-4a2 2 0 00-2 2v2M12 12v4M10 14h4" />
      </svg>
    )},
    { to: "/notifications", label: "Notifications", icon: (
      <svg className="w-7 h-7" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" />
      </svg>
    )},
    { to: "/profile",       label: "Profile", icon: (
      <svg className="w-7 h-7" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" />
      </svg>
    )},
  ];

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-2xl font-bold text-gray-900">
          Welcome back, {user?.full_name ?? user?.username}
        </h2>
        <p className="text-sm text-gray-500 mt-1">Here's your travel overview.</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        {stats.map(({ label, value, sub, link }) => (
          <div key={label} className="rounded-2xl bg-white p-5 shadow-sm border border-gray-100">
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">{label}</p>
            <p className="mt-2 text-3xl font-bold text-blue-700">{value}</p>
            {sub && link ? (
              <Link to={link} className="text-xs text-blue-500 hover:underline mt-0.5 inline-block">{sub}</Link>
            ) : (
              <p className="text-xs text-gray-400 mt-0.5">{sub}</p>
            )}
          </div>
        ))}
      </div>

      {/* Loyalty card */}
      {profile && tier && (
        <div className={`rounded-2xl bg-gradient-to-r ${tier.color} p-5 text-white shadow-md`}>
          <div className="flex items-center justify-between mb-3">
            <div>
              <p className="text-xs font-bold uppercase tracking-widest opacity-80">AeroLink Loyalty</p>
              <p className="text-2xl font-bold mt-0.5">{tier.label} Member</p>
            </div>
            <div className="text-right">
              <p className="text-3xl font-bold tabular-nums">{pts.toLocaleString()}</p>
              <p className="text-xs opacity-80 mt-0.5">points</p>
            </div>
          </div>
          {tier.next ? (
            <>
              <div className="w-full bg-white/20 rounded-full h-2 mb-1.5">
                <div className="bg-white h-2 rounded-full transition-all" style={{ width: `${progress}%` }} />
              </div>
              <p className="text-xs opacity-80">
                {ptsToNext.toLocaleString()} pts to {tier.next} · Earn 10 pts per $1 spent
              </p>
            </>
          ) : (
            <p className="text-xs opacity-80">You're at the highest tier · Earn 10 pts per $1 spent</p>
          )}
        </div>
      )}

      {/* Next flight */}
      {nextFlight && <NextFlightCard booking={nextFlight} />}

      {/* Quick actions */}
      <div>
        <h3 className="mb-3 text-sm font-bold uppercase tracking-widest text-gray-400">Quick Actions</h3>
        <div className="grid grid-cols-3 sm:grid-cols-6 gap-3">
          {quickActions.map(({ to, label, icon }) => (
            <Link key={to} to={to}
              className="relative flex flex-col items-center gap-2 rounded-2xl bg-white p-4 shadow-sm border border-gray-100 hover:border-blue-300 hover:shadow-md transition-all text-gray-600 hover:text-blue-600">
              {icon}
              <span className="text-xs font-medium text-center">{label}</span>
              {to === "/notifications" && unreadCount > 0 && (
                <span className="absolute -top-1 -right-1 flex h-5 w-5 items-center justify-center rounded-full bg-red-500 text-[10px] font-bold text-white">
                  {unreadCount > 9 ? "9+" : unreadCount}
                </span>
              )}
            </Link>
          ))}
        </div>
      </div>

      {/* Recent notifications */}
      {recentNotifs.length > 0 && (
        <div>
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-bold uppercase tracking-widest text-gray-400">Recent Notifications</h3>
            <Link to="/notifications" className="text-sm text-blue-600 hover:underline">View all</Link>
          </div>
          <div className="space-y-2">
            {recentNotifs.map((n) => (
              <div key={n.id}
                className={`flex items-start gap-3 rounded-xl px-4 py-3 border ${n.is_read ? "bg-white border-gray-100" : "bg-blue-50 border-blue-100"}`}>
                <span className="text-lg mt-0.5">{EVENT_ICON[n.event_type] ?? "🔔"}</span>
                <div className="flex-1 min-w-0">
                  <p className={`text-sm font-medium ${n.is_read ? "text-gray-700" : "text-gray-900"}`}>{n.subject}</p>
                </div>
                <span className="text-xs text-gray-400 shrink-0">{timeAgo(n.created_at)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recent bookings */}
      {activeBookings.length > 0 && (
        <div>
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-bold uppercase tracking-widest text-gray-400">Recent Bookings</h3>
            <Link to="/bookings" className="text-sm text-blue-600 hover:underline">View all</Link>
          </div>
          <div className="rounded-2xl overflow-hidden border border-gray-100 bg-white shadow-sm">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-xs font-semibold text-gray-400 uppercase">
                <tr>
                  {["Reference", "Cabin", "Seat", "Status", "Price"].map((h) => (
                    <th key={h} className="px-4 py-3 text-left">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {activeBookings.slice(0, 5).map((b) => {
                  const ss = STATUS_STYLE[b.status.toLowerCase()] ?? "bg-gray-100 text-gray-500 border-gray-200";
                  return (
                    <tr key={b.id} className="hover:bg-gray-50 transition-colors">
                      <td className="px-4 py-3 font-mono font-bold text-blue-700">{b.booking_reference}</td>
                      <td className="px-4 py-3 capitalize text-gray-700">{b.cabin_class}</td>
                      <td className="px-4 py-3 font-mono text-gray-700">{b.seat_numbers ?? "—"}</td>
                      <td className="px-4 py-3">
                        <span className={`rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize ${ss}`}>
                          {b.status.replace(/-/g, " ")}
                        </span>
                      </td>
                      <td className="px-4 py-3 font-semibold text-gray-900">${b.total_price.toFixed(2)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
