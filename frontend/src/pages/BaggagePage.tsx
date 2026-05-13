import { useState, type FormEvent } from "react";
import { baggageClient } from "../api/client";

interface BaggageItem {
  id: string;
  tag_number: string;
  booking_id: string;
  weight_kg: number;
  status: string;
  location: string | null;
  created_at: string;
}

const STATUS_COLOR: Record<string, string> = {
  checked_in:  "bg-blue-100 text-blue-800",
  in_transit:  "bg-yellow-100 text-yellow-800",
  arrived:     "bg-green-100 text-green-800",
  lost:        "bg-red-100 text-red-800",
  delivered:   "bg-green-100 text-green-800",
};

export function BaggagePage() {
  const [tagNumber, setTagNumber] = useState("");
  const [baggage, setBaggage] = useState<BaggageItem | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSearch(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBaggage(null);
    setLoading(true);
    try {
      const { data, error: err } = await baggageClient.GET(
        "/api/v1/baggage/{tag_number}",
        { params: { path: { tag_number: tagNumber } } }
      );
      if (err || !data) throw new Error("Not found");
      setBaggage(data as BaggageItem);
    } catch {
      setError("Baggage tag not found. Please check the number and try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-gray-900">Track Baggage</h2>

      <div className="rounded-xl bg-white p-6 shadow-sm border border-gray-100 max-w-lg">
        <form onSubmit={handleSearch} className="flex gap-3">
          <input
            type="text"
            required
            value={tagNumber}
            onChange={(e) => setTagNumber(e.target.value)}
            placeholder="Enter baggage tag number"
            className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
          <button
            type="submit"
            disabled={loading}
            className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-60 transition-colors"
          >
            {loading ? "Searching…" : "Track"}
          </button>
        </form>
        {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
      </div>

      {baggage && (
        <div className="max-w-lg rounded-xl bg-white p-6 shadow-sm border border-gray-100 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-gray-400 uppercase">Tag Number</p>
              <p className="font-mono font-bold text-gray-900">{baggage.tag_number}</p>
            </div>
            <span
              className={`rounded-full px-3 py-1 text-xs font-medium capitalize ${STATUS_COLOR[baggage.status] ?? "bg-gray-100 text-gray-700"}`}
            >
              {baggage.status.replace("_", " ")}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-4 border-t pt-4 text-sm">
            <div>
              <p className="text-xs text-gray-400">Booking ID</p>
              <p className="font-medium font-mono text-xs">{baggage.booking_id}</p>
            </div>
            <div>
              <p className="text-xs text-gray-400">Weight</p>
              <p className="font-medium">{baggage.weight_kg} kg</p>
            </div>
            {baggage.location && (
              <div className="col-span-2">
                <p className="text-xs text-gray-400">Current Location</p>
                <p className="font-medium">{baggage.location}</p>
              </div>
            )}
            <div>
              <p className="text-xs text-gray-400">Checked in</p>
              <p className="font-medium">{new Date(baggage.created_at).toLocaleString()}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
