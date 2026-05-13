import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { bookingClient } from "../api/client";

interface Booking {
  id: string;
  booking_reference: string;
  flight_id: string;
  passenger_name: string;
  cabin_class: string;
  num_passengers: number;
  total_price: number;
  status: string;
  seat_numbers: string | null;
  created_at: string;
}

const STATUS_COLOR: Record<string, string> = {
  confirmed: "bg-green-100 text-green-800",
  pending:   "bg-yellow-100 text-yellow-800",
  cancelled: "bg-red-100 text-red-800",
  paid:      "bg-blue-100 text-blue-800",
};

export function BookingsPage() {
  const qc = useQueryClient();

  const { data: bookings = [], isLoading, isError } = useQuery<Booking[]>({
    queryKey: ["bookings"],
    queryFn: async () => {
      const { data, error } = await bookingClient.GET("/api/v1/bookings", {});
      if (error) throw new Error("Failed to load bookings");
      return (data as Booking[]) ?? [];
    },
  });

  const cancel = useMutation({
    mutationFn: async (id: string) => {
      const { error } = await bookingClient.POST(
        "/api/v1/bookings/{booking_id}/cancel",
        { params: { path: { booking_id: id } } }
      );
      if (error) throw new Error("Cancel failed");
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["bookings"] }),
  });

  if (isLoading) return <p className="text-sm text-gray-500">Loading bookings…</p>;
  if (isError)   return <p className="text-sm text-red-600">Failed to load bookings. Please refresh.</p>;

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-gray-900">My Bookings</h2>

      {bookings.length === 0 ? (
        <div className="rounded-xl bg-white p-10 text-center shadow-sm border border-gray-100">
          <p className="text-gray-500">No bookings yet.</p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-gray-100 bg-white shadow-sm">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs font-medium text-gray-500 uppercase">
              <tr>
                {["Reference", "Passenger", "Cabin", "Passengers", "Price", "Status", "Date", "Actions"].map((h) => (
                  <th key={h} className="px-4 py-3 text-left">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {bookings.map((b) => (
                <tr key={b.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-mono font-medium text-blue-700">
                    {b.booking_reference}
                  </td>
                  <td className="px-4 py-3">{b.passenger_name}</td>
                  <td className="px-4 py-3 capitalize">{b.cabin_class}</td>
                  <td className="px-4 py-3">{b.num_passengers}</td>
                  <td className="px-4 py-3">${b.total_price.toFixed(2)}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium capitalize ${STATUS_COLOR[b.status] ?? "bg-gray-100 text-gray-700"}`}
                    >
                      {b.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {new Date(b.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3">
                    {b.status !== "cancelled" && (
                      <button
                        onClick={() => cancel.mutate(b.id)}
                        disabled={cancel.isPending}
                        className="text-xs text-red-600 hover:underline disabled:opacity-50"
                      >
                        Cancel
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
