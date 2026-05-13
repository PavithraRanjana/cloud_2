import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { bookingClient } from "../api/client";

interface Booking {
  id: string;
  booking_reference: string;
  flight_id: string;
  cabin_class: string;
  status: string;
  total_price: number;
  created_at: string;
}

const STATUS_COLOR: Record<string, string> = {
  confirmed: "bg-green-100 text-green-800",
  pending:   "bg-yellow-100 text-yellow-800",
  cancelled: "bg-red-100 text-red-800",
  paid:      "bg-blue-100 text-blue-800",
};

export function DashboardPage() {
  const { user } = useAuth();

  const { data: bookings = [] } = useQuery<Booking[]>({
    queryKey: ["bookings"],
    queryFn: async () => {
      const { data } = await bookingClient.GET("/api/v1/bookings", {});
      return (data as Booking[]) ?? [];
    },
  });

  const upcoming = bookings.filter((b) => b.status !== "cancelled");
  const totalSpent = bookings
    .filter((b) => b.status === "confirmed" || b.status === "paid")
    .reduce((sum, b) => sum + b.total_price, 0);

  const quickActions = [
    { to: "/flights",  label: "Search Flights", icon: "✈" },
    { to: "/bookings", label: "My Bookings",     icon: "📋" },
    { to: "/checkin",  label: "Check-in",        icon: "🎫" },
    { to: "/baggage",  label: "Track Baggage",   icon: "🧳" },
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
        {[
          { label: "Total Bookings",    value: bookings.length },
          { label: "Active Bookings",   value: upcoming.length },
          { label: "Total Spent",       value: `$${totalSpent.toFixed(2)}` },
        ].map(({ label, value }) => (
          <div key={label} className="rounded-xl bg-white p-6 shadow-sm border border-gray-100">
            <p className="text-sm text-gray-500">{label}</p>
            <p className="mt-1 text-3xl font-bold text-blue-700">{value}</p>
          </div>
        ))}
      </div>

      {/* Quick actions */}
      <div>
        <h3 className="mb-3 font-semibold text-gray-700">Quick actions</h3>
        <div className="grid grid-cols-4 gap-3">
          {quickActions.map(({ to, label, icon }) => (
            <Link
              key={to}
              to={to}
              className="flex flex-col items-center gap-2 rounded-xl bg-white p-5 shadow-sm border border-gray-100 hover:border-blue-300 hover:shadow-md transition-all"
            >
              <span className="text-3xl">{icon}</span>
              <span className="text-sm font-medium text-gray-700">{label}</span>
            </Link>
          ))}
        </div>
      </div>

      {/* Recent bookings */}
      {bookings.length > 0 && (
        <div>
          <div className="mb-3 flex items-center justify-between">
            <h3 className="font-semibold text-gray-700">Recent bookings</h3>
            <Link to="/bookings" className="text-sm text-blue-600 hover:underline">
              View all
            </Link>
          </div>
          <div className="overflow-hidden rounded-xl border border-gray-100 bg-white shadow-sm">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-xs font-medium text-gray-500 uppercase">
                <tr>
                  {["Reference", "Cabin", "Status", "Price", "Date"].map((h) => (
                    <th key={h} className="px-4 py-3 text-left">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {bookings.slice(0, 5).map((b) => (
                  <tr key={b.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-mono font-medium">{b.booking_reference}</td>
                    <td className="px-4 py-3 capitalize">{b.cabin_class}</td>
                    <td className="px-4 py-3">
                      <span className={`rounded-full px-2 py-0.5 text-xs font-medium capitalize ${STATUS_COLOR[b.status] ?? "bg-gray-100 text-gray-700"}`}>
                        {b.status}
                      </span>
                    </td>
                    <td className="px-4 py-3">${b.total_price.toFixed(2)}</td>
                    <td className="px-4 py-3 text-gray-500">
                      {new Date(b.created_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
