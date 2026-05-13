import { useState, type FormEvent } from "react";
import { checkinClient } from "../api/client";

interface CheckIn {
  id: string;
  booking_id: string;
  seat_number: string | null;
  checked_in_at: string;
  status: string;
}

interface BoardingPass {
  booking_id: string;
  passenger_name: string;
  flight_number: string;
  origin: string;
  destination: string;
  departure_time: string;
  seat_number: string;
  cabin_class: string;
  gate: string | null;
  boarding_pass_number: string;
}

export function CheckInPage() {
  const [bookingId, setBookingId] = useState("");
  const [checkin, setCheckin] = useState<CheckIn | null>(null);
  const [boardingPass, setBoardingPass] = useState<BoardingPass | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleCheckin(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const { data, error: err } = await checkinClient.POST("/api/v1/checkin", {
        body: { booking_id: bookingId },
      });
      if (err || !data) throw new Error("Check-in failed");
      setCheckin(data as CheckIn);
    } catch {
      setError("Check-in failed. Please verify your booking ID.");
    } finally {
      setLoading(false);
    }
  }

  async function fetchBoardingPass() {
    if (!bookingId) return;
    const { data } = await checkinClient.GET(
      "/api/v1/checkin/{booking_id}/boarding-pass",
      { params: { path: { booking_id: bookingId } } }
    );
    if (data) setBoardingPass(data as BoardingPass);
  }

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-gray-900">Online Check-in</h2>

      <div className="rounded-xl bg-white p-6 shadow-sm border border-gray-100 max-w-lg">
        <form onSubmit={handleCheckin} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Booking ID
            </label>
            <input
              type="text"
              required
              value={bookingId}
              onChange={(e) => setBookingId(e.target.value)}
              placeholder="Enter your booking ID"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>
          {error && (
            <p className="text-sm text-red-600">{error}</p>
          )}
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-blue-600 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-60 transition-colors"
          >
            {loading ? "Checking in…" : "Check in"}
          </button>
        </form>
      </div>

      {checkin && (
        <div className="max-w-lg space-y-4">
          <div className="rounded-xl bg-green-50 border border-green-200 p-5">
            <p className="font-semibold text-green-800">✓ Check-in successful</p>
            <p className="text-sm text-green-700 mt-1">
              Status: <span className="font-medium capitalize">{checkin.status}</span>
              {checkin.seat_number && ` · Seat ${checkin.seat_number}`}
            </p>
          </div>

          <button
            onClick={fetchBoardingPass}
            className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-semibold text-white hover:bg-blue-700 transition-colors"
          >
            Get Boarding Pass
          </button>
        </div>
      )}

      {boardingPass && (
        <div className="max-w-md rounded-2xl border-2 border-blue-200 bg-white shadow-lg overflow-hidden">
          <div className="bg-blue-700 px-6 py-4 text-white">
            <p className="text-xs uppercase tracking-widest opacity-75">Boarding Pass</p>
            <p className="text-xl font-bold mt-1">{boardingPass.passenger_name}</p>
          </div>
          <div className="p-6 grid grid-cols-2 gap-4 text-sm">
            <div>
              <p className="text-xs text-gray-400 uppercase">Flight</p>
              <p className="font-bold">{boardingPass.flight_number}</p>
            </div>
            <div>
              <p className="text-xs text-gray-400 uppercase">Cabin</p>
              <p className="font-bold capitalize">{boardingPass.cabin_class}</p>
            </div>
            <div>
              <p className="text-xs text-gray-400 uppercase">From</p>
              <p className="font-bold">{boardingPass.origin}</p>
            </div>
            <div>
              <p className="text-xs text-gray-400 uppercase">To</p>
              <p className="font-bold">{boardingPass.destination}</p>
            </div>
            <div>
              <p className="text-xs text-gray-400 uppercase">Departure</p>
              <p className="font-bold">{boardingPass.departure_time}</p>
            </div>
            <div>
              <p className="text-xs text-gray-400 uppercase">Seat</p>
              <p className="font-bold">{boardingPass.seat_number}</p>
            </div>
            {boardingPass.gate && (
              <div>
                <p className="text-xs text-gray-400 uppercase">Gate</p>
                <p className="font-bold">{boardingPass.gate}</p>
              </div>
            )}
            <div className="col-span-2 border-t pt-3">
              <p className="text-xs text-gray-400 uppercase">Boarding Pass #</p>
              <p className="font-mono text-xs text-gray-600">{boardingPass.boarding_pass_number}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
