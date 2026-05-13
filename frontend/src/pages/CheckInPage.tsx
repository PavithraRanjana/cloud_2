import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { bookingClient, checkinClient, flightClient } from "../api/client";
import { SeatMap, CONFIGS, DEFAULT_CONFIG } from "../components/SeatMap";

// ── Types ─────────────────────────────────────────────────────────────────
interface Booking {
  id: string;
  booking_reference: string;
  flight_id: string;
  passenger_name: string;
  first_name?: string;
  last_name?: string;
  cabin_class: string;
  num_passengers: number;
  total_price: number;
  status: string;
  seat_numbers?: string;
  trip_type: string;
}

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
  aircraft_type: string | null;
  gate: string | null;
  terminal: string | null;
}

interface CheckInRecord {
  id: string;
  booking_id: string;
  flight_id: string;
  passenger_name: string;
  seat_number: string;
  boarding_group: string;
  gate: string | null;
  status: string;
  boarding_pass_url: string | null;
  has_baggage: boolean;
  seat_selected_by_user: boolean;
  created_at: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────
function fmt(t: string) {
  const [hStr, mStr] = t.slice(0, 5).split(":");
  const h = parseInt(hStr, 10);
  return `${h % 12 || 12}:${mStr} ${h >= 12 ? "PM" : "AM"}`;
}
function fmtDate(d: string) {
  return new Date(d + "T00:00:00").toLocaleDateString("en-US", {
    weekday: "short", month: "short", day: "numeric", year: "numeric",
  });
}

function pickRandom(
  aircraftType: string | null,
  cabinClass: string,
  bookedSeats: string[],
): string {
  const config = (aircraftType && CONFIGS[aircraftType]) ? CONFIGS[aircraftType] : DEFAULT_CONFIG;
  const section = config.sections.find((s) => s.cabin === cabinClass);
  if (!section) return "";
  const booked = new Set(bookedSeats);
  const available: string[] = [];
  for (let row = section.rowStart; row <= section.rowEnd; row++) {
    for (const col of [...section.leftCols, ...section.rightCols]) {
      const seat = `${row}${col}`;
      if (!booked.has(seat)) available.push(seat);
    }
  }
  if (available.length === 0) return "";
  return available[Math.floor(Math.random() * available.length)];
}

const STATUS_ELIGIBLE = new Set(["confirmed", "paid"]);
const STATUS_DONE     = new Set(["checked-in", "completed", "boarded"]);

const CABIN_COLOUR: Record<string, string> = {
  economy:  "bg-emerald-50 text-emerald-700 border-emerald-200",
  business: "bg-amber-50  text-amber-700  border-amber-200",
  first:    "bg-purple-50 text-purple-700 border-purple-200",
};

const BOOKING_STATUS_STYLE: Record<string, string> = {
  pending:           "bg-yellow-50 text-yellow-700 border border-yellow-200",
  confirmed:         "bg-blue-50   text-blue-700   border border-blue-200",
  paid:              "bg-emerald-50 text-emerald-700 border border-emerald-200",
  "payment-pending": "bg-yellow-50 text-yellow-700 border border-yellow-200",
  "checked-in":      "bg-sky-50    text-sky-700    border border-sky-200",
  completed:         "bg-gray-100  text-gray-500",
  cancelled:         "bg-red-50    text-red-600    border border-red-200",
};

// ── Boarding Pass ─────────────────────────────────────────────────────────
function BoardingPass({
  booking, flight, checkin,
}: { booking: Booking; flight: Flight | undefined; checkin: CheckInRecord }) {
  const name = booking.first_name && booking.last_name
    ? `${booking.first_name} ${booking.last_name}`
    : booking.passenger_name;

  return (
    <div className="rounded-2xl overflow-hidden border border-blue-200 shadow-lg max-w-lg">
      {/* Header strip */}
      <div className="bg-gradient-to-r from-blue-700 to-blue-500 px-6 py-4 text-white">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
              <path d="M21 16v-2l-8-5V3.5a1.5 1.5 0 0 0-3 0V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z"/>
            </svg>
            <span className="font-bold tracking-widest text-sm">AEROLINK</span>
          </div>
          <span className="rounded-full bg-white/20 px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide">
            Boarding Pass
          </span>
        </div>
        <p className="text-xs text-blue-200 uppercase tracking-widest">Passenger</p>
        <p className="text-2xl font-bold uppercase tracking-wide">{name}</p>
      </div>

      {/* Route bar */}
      {flight && (
        <div className="bg-blue-50 px-6 py-3 flex items-center justify-between border-b border-blue-100">
          <div className="text-center">
            <p className="text-2xl font-bold text-blue-700 font-mono">{flight.origin}</p>
            <p className="text-xs text-gray-500 mt-0.5">{fmt(flight.departure_time)}</p>
          </div>
          <div className="flex flex-col items-center gap-1 flex-1 px-4">
            <div className="flex w-full items-center gap-1">
              <div className="flex-1 h-px bg-blue-300" />
              <svg className="w-4 h-4 text-blue-400" viewBox="0 0 24 24" fill="currentColor">
                <path d="M21 16v-2l-8-5V3.5a1.5 1.5 0 0 0-3 0V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z"/>
              </svg>
              <div className="flex-1 h-px bg-blue-300" />
            </div>
            <p className="text-[10px] text-blue-400 font-medium">{flight.flight_number}</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-blue-700 font-mono">{flight.destination}</p>
            <p className="text-xs text-gray-500 mt-0.5">{fmt(flight.arrival_time)}</p>
          </div>
        </div>
      )}

      {/* Details grid */}
      <div className="px-6 py-4 grid grid-cols-3 gap-4 text-sm">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400">Seat</p>
          <p className="text-2xl font-bold text-gray-900 font-mono mt-0.5">{checkin.seat_number || "—"}</p>
          <p className={`text-[9px] font-semibold uppercase tracking-wide mt-1 ${
            checkin.seat_selected_by_user ? "text-emerald-500" : "text-amber-500"
          }`}>
            {checkin.seat_selected_by_user ? "chosen by you" : "auto-assigned"}
          </p>
        </div>
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400">Group</p>
          <p className="text-2xl font-bold text-gray-900 font-mono mt-0.5">{checkin.boarding_group || "—"}</p>
        </div>
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400">Gate</p>
          <p className="text-2xl font-bold text-gray-900 font-mono mt-0.5">{checkin.gate || flight?.gate || "TBA"}</p>
        </div>
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400">Date</p>
          <p className="text-xs font-semibold text-gray-700 mt-0.5">{flight ? fmtDate(flight.departure_date) : "—"}</p>
        </div>
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400">Cabin</p>
          <p className="text-xs font-semibold text-gray-700 mt-0.5 capitalize">{booking.cabin_class}</p>
        </div>
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400">Ref</p>
          <p className="text-xs font-mono font-bold text-blue-600 mt-0.5">{booking.booking_reference}</p>
        </div>
      </div>

      {/* Tear line + barcode */}
      <div className="relative border-t border-dashed border-blue-200 mx-4" />
      <div className="px-6 py-3 flex items-center justify-between bg-gray-50">
        <div className="flex gap-0.5">
          {Array.from({ length: 40 }).map((_, i) => (
            <div key={i} className="bg-gray-800 rounded-sm"
              style={{ width: i % 3 === 0 ? 3 : 1, height: i % 5 === 0 ? 32 : 24 }} />
          ))}
        </div>
        <div className="text-right ml-4">
          <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400">Status</p>
          <p className="text-sm font-bold text-emerald-600 uppercase">{checkin.status.replace(/-/g, " ")}</p>
        </div>
      </div>
    </div>
  );
}

// ── Single booking row ────────────────────────────────────────────────────
function BookingRow({
  booking,
  onCheckedIn,
}: {
  booking: Booking;
  onCheckedIn: (checkin: CheckInRecord) => void;
}) {
  const qc = useQueryClient();

  const { data: flight, isLoading: loadingFlight } = useQuery<Flight>({
    queryKey: ["flight", booking.flight_id],
    queryFn: async () => {
      const { data, error } = await flightClient.GET("/api/v1/flights/{flight_id}" as any, {
        params: { path: { flight_id: booking.flight_id } },
      });
      if (error || !data) throw new Error("Flight not found");
      return data as Flight;
    },
    staleTime: 5 * 60 * 1000,
  });

  const { data: existingCheckin } = useQuery<CheckInRecord | null>({
    queryKey: ["checkin", booking.id],
    queryFn: async () => {
      const { data } = await (checkinClient as any).GET("/api/v1/checkin/{booking_id}", {
        params: { path: { booking_id: booking.id } },
      });
      return (data as CheckInRecord) ?? null;
    },
    retry: false,
  });

  // Seat picker state — only used when booking has no pre-chosen seat
  const [showSeatPicker, setShowSeatPicker] = useState(false);
  const [pickedSeat, setPickedSeat]         = useState("");
  const [isAutoAssigned, setIsAutoAssigned] = useState(false);
  const [expanded, setExpanded]             = useState(false);

  const hasSeat = !!(booking.seat_numbers?.trim());

  const { data: bookedSeats = [], isLoading: loadingSeats } = useQuery<string[]>({
    queryKey: ["seat-availability", booking.flight_id],
    queryFn: async () => {
      const { data } = await (bookingClient as any).GET("/api/v1/bookings/seat-availability", {
        params: { query: { flight_id: booking.flight_id } },
      });
      return (data as { booked_seats: string[] })?.booked_seats ?? [];
    },
    enabled: showSeatPicker,
  });

  function acceptAnySeat() {
    const seat = pickRandom(flight?.aircraft_type ?? null, booking.cabin_class, bookedSeats);
    if (seat) { setPickedSeat(seat); setIsAutoAssigned(true); }
  }

  const checkIn = useMutation({
    mutationFn: async ({ seat, selectedByUser }: { seat: string; selectedByUser: boolean }) => {
      const { data, error } = await (checkinClient as any).POST("/api/v1/checkin", {
        body: {
          booking_id:           booking.id,
          flight_id:            booking.flight_id,
          passenger_name:       booking.passenger_name,
          seat_preference:      seat || undefined,
          seat_selected_by_user: selectedByUser,
        },
      });
      if (error || !data) throw new Error((error as any)?.detail ?? "Check-in failed");
      return data as CheckInRecord;
    },
    onSuccess: (ci) => {
      qc.setQueryData(["checkin", booking.id], ci);
      qc.invalidateQueries({ queryKey: ["bookings"] });
      setShowSeatPicker(false);
      onCheckedIn(ci);
    },
  });

  const isEligible  = STATUS_ELIGIBLE.has(booking.status.toLowerCase());
  const isDone      = STATUS_DONE.has(booking.status.toLowerCase());
  const checkin     = existingCheckin ?? (checkIn.isSuccess ? checkIn.data : null);
  const cabinStyle  = CABIN_COLOUR[booking.cabin_class] ?? "bg-gray-100 text-gray-600 border-gray-200";
  const statusStyle = BOOKING_STATUS_STYLE[booking.status.toLowerCase()] ?? "bg-gray-100 text-gray-500";

  return (
    <div className="rounded-2xl bg-white border border-gray-100 shadow-sm overflow-hidden">
      {/* Main row */}
      <div className="flex items-center gap-4 px-5 py-4">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <span className="font-mono font-bold text-blue-700 text-base tracking-wider">
              {booking.booking_reference}
            </span>
            <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${statusStyle}`}>
              {booking.status.replace(/-/g, " ")}
            </span>
            <span className={`rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize ${cabinStyle}`}>
              {booking.cabin_class}
            </span>
            {booking.trip_type === "return" && (
              <span className="rounded-full bg-blue-50 border border-blue-200 text-blue-600 px-2.5 py-0.5 text-xs font-medium">
                Return
              </span>
            )}
          </div>

          {loadingFlight ? (
            <p className="text-xs text-gray-400 animate-pulse">Loading flight info…</p>
          ) : flight ? (
            <p className="text-sm text-gray-600">
              <span className="font-semibold text-gray-800">{flight.flight_number}</span>
              {" · "}
              <span className="font-mono text-blue-600">{flight.origin}</span>
              {" → "}
              <span className="font-mono text-violet-600">{flight.destination}</span>
              {" · "}
              {fmtDate(flight.departure_date)}
              {" · "}
              {fmt(flight.departure_time)}
            </p>
          ) : (
            <p className="text-xs text-gray-400">Flight details unavailable</p>
          )}

          {checkin && (
            <p className="mt-1 text-xs text-sky-600 font-medium">
              Seat {checkin.seat_number} · Group {checkin.boarding_group}
              {checkin.gate ? ` · Gate ${checkin.gate}` : ""}
            </p>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 shrink-0">
          {checkin ? (
            <button
              onClick={() => setExpanded((v) => !v)}
              className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-700 transition-colors"
            >
              {expanded ? "Hide Pass" : "Boarding Pass"}
            </button>
          ) : isEligible ? (
            hasSeat ? (
              // Seat already chosen during booking — check in directly
              <button
                onClick={() => checkIn.mutate({ seat: booking.seat_numbers!, selectedByUser: true })}
                disabled={checkIn.isPending}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
              >
                {checkIn.isPending ? "Checking in…" : "Check In"}
              </button>
            ) : (
              // No seat — open picker
              <button
                onClick={() => setShowSeatPicker(true)}
                disabled={showSeatPicker}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-60 transition-colors"
              >
                {showSeatPicker ? "Select a seat below" : "Check In"}
              </button>
            )
          ) : isDone ? (
            <span className="rounded-full bg-emerald-50 border border-emerald-200 text-emerald-600 px-3 py-1.5 text-xs font-semibold">
              ✓ Done
            </span>
          ) : (
            <span className="text-xs text-gray-400">
              {booking.status === "pending" || booking.status === "payment-pending"
                ? "Complete payment first"
                : "Not eligible"}
            </span>
          )}
        </div>
      </div>

      {/* Check-in error */}
      {checkIn.isError && (
        <div className="border-t border-red-100 bg-red-50 px-5 py-2.5">
          <p className="text-xs text-red-600">
            {checkIn.error instanceof Error ? checkIn.error.message : "Check-in failed. Please try again."}
          </p>
        </div>
      )}

      {/* Seat picker — shown when no seat was chosen at booking time */}
      {showSeatPicker && !checkin && (
        <div className="border-t border-gray-100 px-5 py-5 space-y-4 bg-gray-50/40">
          <div className="flex items-center justify-between">
            <h4 className="font-semibold text-gray-800">Choose your seat</h4>
            <button
              type="button"
              onClick={() => { setShowSeatPicker(false); setPickedSeat(""); setIsAutoAssigned(false); }}
              className="text-xs text-gray-400 hover:text-gray-600 transition-colors"
            >
              Cancel
            </button>
          </div>

          {/* Accept any available seat */}
          <button
            type="button"
            onClick={acceptAnySeat}
            disabled={loadingSeats}
            className="w-full rounded-xl border-2 border-dashed border-gray-200 bg-white hover:border-blue-300 hover:bg-blue-50 py-3 text-sm font-semibold text-gray-500 hover:text-blue-600 disabled:opacity-50 transition-colors"
          >
            Accept Any Available Seat
          </button>

          {isAutoAssigned && pickedSeat && (
            <p className="rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-700">
              Seat <span className="font-mono font-bold">{pickedSeat}</span> has been auto-selected for you.
              You can click a different seat on the map to override.
            </p>
          )}

          {/* Seat map */}
          <SeatMap
            aircraftType={flight?.aircraft_type ?? null}
            cabinClass={booking.cabin_class}
            selectedSeat={pickedSeat}
            onSeatSelect={(seat) => { setPickedSeat(seat); setIsAutoAssigned(false); }}
            bookedSeats={bookedSeats}
            isLoading={loadingSeats}
          />

          {/* Confirm */}
          <button
            type="button"
            onClick={() => checkIn.mutate({ seat: pickedSeat, selectedByUser: !isAutoAssigned })}
            disabled={!pickedSeat || checkIn.isPending}
            className="w-full rounded-xl bg-blue-600 py-3 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {checkIn.isPending ? "Confirming…" : pickedSeat ? `Confirm Check-In — Seat ${pickedSeat}` : "Select a seat to continue"}
          </button>
        </div>
      )}

      {/* Boarding pass */}
      {expanded && checkin && (
        <div className="border-t border-gray-100 px-5 py-5 bg-gray-50/50">
          <BoardingPass booking={booking} flight={flight} checkin={checkin} />
        </div>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────
export function CheckInPage() {
  const [selectedCheckin, setSelectedCheckin] = useState<CheckInRecord | null>(null);
  const [selectedBooking, setSelectedBooking] = useState<Booking | null>(null);

  const { data: bookings = [], isLoading, isError } = useQuery<Booking[]>({
    queryKey: ["bookings"],
    queryFn: async () => {
      const { data, error } = await bookingClient.GET("/api/v1/bookings", {});
      if (error || !data) throw new Error("Failed to load bookings");
      return data as Booking[];
    },
  });

  const upcoming  = bookings.filter((b) => STATUS_ELIGIBLE.has(b.status.toLowerCase()));
  const checkedIn = bookings.filter((b) => STATUS_DONE.has(b.status.toLowerCase()));
  const cancelled = bookings.filter((b) => b.status.toLowerCase() === "cancelled");

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-2xl font-bold text-gray-900">Online Check-In</h2>
        <p className="mt-1 text-sm text-gray-500">
          Check in for your upcoming flights and get your boarding pass instantly.
        </p>
      </div>

      {isLoading && (
        <p className="text-sm text-gray-400 animate-pulse">Loading your bookings…</p>
      )}
      {isError && (
        <p className="text-sm text-red-500">Failed to load bookings. Please refresh.</p>
      )}

      {!isLoading && !isError && bookings.length === 0 && (
        <div className="rounded-2xl border border-dashed border-gray-200 bg-white px-8 py-12 text-center">
          <svg className="mx-auto w-10 h-10 text-gray-300 mb-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 6v.75m0 3v.75m0 3v.75m0 3V18m-9-5.25h5.25M7.5 15h3M3.375 5.25c-.621 0-1.125.504-1.125 1.125v3.026a2.999 2.999 0 010 5.198v3.026c0 .621.504 1.125 1.125 1.125h17.25c.621 0 1.125-.504 1.125-1.125v-3.026a3 3 0 010-5.198V6.375c0-.621-.504-1.125-1.125-1.125H3.375z" />
          </svg>
          <p className="font-semibold text-gray-500">No bookings found</p>
          <p className="mt-1 text-sm text-gray-400">Book a flight first to check in here.</p>
        </div>
      )}

      {upcoming.length > 0 && (
        <section className="space-y-3">
          <h3 className="text-sm font-bold uppercase tracking-widest text-gray-400">
            Ready to Check In
          </h3>
          {upcoming.map((b) => (
            <BookingRow key={b.id} booking={b}
              onCheckedIn={(ci) => { setSelectedCheckin(ci); setSelectedBooking(b); }} />
          ))}
        </section>
      )}

      {checkedIn.length > 0 && (
        <section className="space-y-3">
          <h3 className="text-sm font-bold uppercase tracking-widest text-gray-400">
            Checked In
          </h3>
          {checkedIn.map((b) => (
            <BookingRow key={b.id} booking={b}
              onCheckedIn={(ci) => { setSelectedCheckin(ci); setSelectedBooking(b); }} />
          ))}
        </section>
      )}

      {cancelled.length > 0 && (
        <section className="space-y-3">
          <h3 className="text-sm font-bold uppercase tracking-widest text-gray-400">
            Cancelled Bookings
          </h3>
          {cancelled.map((b) => (
            <BookingRow key={b.id} booking={b}
              onCheckedIn={(ci) => { setSelectedCheckin(ci); setSelectedBooking(b); }} />
          ))}
        </section>
      )}

      {/* suppress unused-variable warnings */}
      {selectedCheckin && selectedBooking && null}
    </div>
  );
}
