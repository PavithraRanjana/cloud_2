import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { flightClient } from "../api/client";
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

const STATUSES = ["scheduled", "boarding", "departed", "in-flight", "landed", "arrived", "cancelled", "delayed"];

const STATUS_STYLE: Record<string, string> = {
  scheduled:  "bg-blue-50   text-blue-700   border-blue-200",
  boarding:   "bg-amber-50  text-amber-700  border-amber-200",
  departed:   "bg-sky-50    text-sky-700    border-sky-200",
  "in-flight":"bg-violet-50 text-violet-700 border-violet-200",
  landed:     "bg-emerald-50 text-emerald-700 border-emerald-200",
  arrived:    "bg-emerald-50 text-emerald-700 border-emerald-200",
  cancelled:  "bg-red-50    text-red-600    border-red-200",
  delayed:    "bg-orange-50 text-orange-700 border-orange-200",
};

const INPUT  = "w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500";
const SELECT = "w-full h-9 rounded-lg border border-gray-300 px-2 text-sm bg-white focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500";

const EMPTY_CREATE = {
  flight_number: "", airline: "", origin: "", destination: "",
  departure_date: "", departure_time: "", arrival_date: "", arrival_time: "",
  aircraft_type: "",
  total_seats_economy: 150, total_seats_business: 30, total_seats_first: 10,
  price_economy: 199.99, price_business: 599.99, price_first: 1299.99,
  gate: "", terminal: "",
};

function EditPanel({ flight, onClose }: { flight: Flight; onClose: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState({
    status:         flight.status,
    gate:           flight.gate   ?? "",
    terminal:       flight.terminal ?? "",
    departure_time: flight.departure_time.slice(0, 5),
    arrival_time:   flight.arrival_time.slice(0, 5),
    price_economy:  flight.price_economy,
    price_business: flight.price_business,
    price_first:    flight.price_first,
  });

  const update = useMutation({
    mutationFn: async () => {
      const body: Record<string, unknown> = {
        status:         form.status,
        gate:           form.gate     || undefined,
        terminal:       form.terminal || undefined,
        departure_time: form.departure_time || undefined,
        arrival_time:   form.arrival_time   || undefined,
        price_economy:  form.price_economy,
        price_business: form.price_business,
        price_first:    form.price_first,
      };
      const { error } = await (flightClient as any).PUT(`/api/v1/flights/${flight.id}`, { body });
      if (error) throw new Error("Update failed");
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["staff-flights"] });
      onClose();
    },
  });

  return (
    <div className="border-t border-gray-100 bg-blue-50/30 px-5 py-4 space-y-4">
      <p className="text-sm font-bold text-gray-700">Edit Flight</p>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Status</label>
          <select value={form.status} onChange={(e) => setForm(f => ({ ...f, status: e.target.value }))} className={SELECT}>
            {STATUSES.map(s => <option key={s} value={s} className="capitalize">{s}</option>)}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Gate</label>
          <input value={form.gate} onChange={(e) => setForm(f => ({ ...f, gate: e.target.value }))} className={INPUT} placeholder="e.g. A12" />
        </div>
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Terminal</label>
          <input value={form.terminal} onChange={(e) => setForm(f => ({ ...f, terminal: e.target.value }))} className={INPUT} placeholder="e.g. T2" />
        </div>
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Dept. Time</label>
          <input type="time" value={form.departure_time} onChange={(e) => setForm(f => ({ ...f, departure_time: e.target.value }))} className={INPUT} />
        </div>
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Arr. Time</label>
          <input type="time" value={form.arrival_time} onChange={(e) => setForm(f => ({ ...f, arrival_time: e.target.value }))} className={INPUT} />
        </div>
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Economy $</label>
          <input type="number" step="0.01" value={form.price_economy} onChange={(e) => setForm(f => ({ ...f, price_economy: parseFloat(e.target.value) }))} className={INPUT} />
        </div>
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Business $</label>
          <input type="number" step="0.01" value={form.price_business} onChange={(e) => setForm(f => ({ ...f, price_business: parseFloat(e.target.value) }))} className={INPUT} />
        </div>
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">First $</label>
          <input type="number" step="0.01" value={form.price_first} onChange={(e) => setForm(f => ({ ...f, price_first: parseFloat(e.target.value) }))} className={INPUT} />
        </div>
      </div>
      {update.isError && <p className="text-xs text-red-500">{update.error instanceof Error ? update.error.message : "Update failed"}</p>}
      <div className="flex gap-2 pt-1">
        <button onClick={onClose} className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium hover:bg-gray-50 transition-colors">Cancel</button>
        <button onClick={() => update.mutate()} disabled={update.isPending}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50 transition-colors">
          {update.isPending ? "Saving…" : "Save Changes"}
        </button>
      </div>
    </div>
  );
}

function CreatePanel({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState(EMPTY_CREATE);

  const create = useMutation({
    mutationFn: async () => {
      const body = {
        ...form,
        origin:      form.origin.toUpperCase(),
        destination: form.destination.toUpperCase(),
        aircraft_type:  form.aircraft_type  || undefined,
        gate:           form.gate           || undefined,
        terminal:       form.terminal       || undefined,
        total_seats_economy:  Number(form.total_seats_economy),
        total_seats_business: Number(form.total_seats_business),
        total_seats_first:    Number(form.total_seats_first),
        price_economy:  Number(form.price_economy),
        price_business: Number(form.price_business),
        price_first:    Number(form.price_first),
      };
      const { error } = await (flightClient as any).POST("/api/v1/flights", { body });
      if (error) throw new Error("Failed to create flight");
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["staff-flights"] });
      onClose();
    },
  });

  const set = (key: string, value: unknown) => setForm(f => ({ ...f, [key]: value }));

  return (
    <div className="rounded-2xl bg-white border border-blue-100 shadow-sm p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-bold text-gray-900">New Flight</h3>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">×</button>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Flight No.*</label>
          <input value={form.flight_number} onChange={e => set("flight_number", e.target.value.toUpperCase())} className={INPUT} placeholder="BA123" />
        </div>
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Airline*</label>
          <input value={form.airline} onChange={e => set("airline", e.target.value)} className={INPUT} placeholder="British Airways" />
        </div>
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Origin (IATA)*</label>
          <input value={form.origin} onChange={e => set("origin", e.target.value.toUpperCase())} className={INPUT} placeholder="LHR" maxLength={3} />
        </div>
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Destination (IATA)*</label>
          <input value={form.destination} onChange={e => set("destination", e.target.value.toUpperCase())} className={INPUT} placeholder="JFK" maxLength={3} />
        </div>
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Departure Date*</label>
          <input type="date" value={form.departure_date} onChange={e => set("departure_date", e.target.value)} className={INPUT} />
        </div>
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Departure Time*</label>
          <input type="time" value={form.departure_time} onChange={e => set("departure_time", e.target.value)} className={INPUT} />
        </div>
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Arrival Date*</label>
          <input type="date" value={form.arrival_date} onChange={e => set("arrival_date", e.target.value)} className={INPUT} />
        </div>
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Arrival Time*</label>
          <input type="time" value={form.arrival_time} onChange={e => set("arrival_time", e.target.value)} className={INPUT} />
        </div>
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Aircraft Type</label>
          <input value={form.aircraft_type} onChange={e => set("aircraft_type", e.target.value)} className={INPUT} placeholder="Boeing 737" />
        </div>
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Gate</label>
          <input value={form.gate} onChange={e => set("gate", e.target.value)} className={INPUT} placeholder="A12" />
        </div>
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Terminal</label>
          <input value={form.terminal} onChange={e => set("terminal", e.target.value)} className={INPUT} placeholder="T2" />
        </div>
      </div>

      <p className="text-xs font-bold uppercase tracking-wide text-gray-400 pt-1">Seats & Pricing</p>
      <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Economy Seats</label>
          <input type="number" min={0} value={form.total_seats_economy} onChange={e => set("total_seats_economy", e.target.value)} className={INPUT} />
        </div>
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Economy $</label>
          <input type="number" step="0.01" min={0} value={form.price_economy} onChange={e => set("price_economy", e.target.value)} className={INPUT} />
        </div>
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Business Seats</label>
          <input type="number" min={0} value={form.total_seats_business} onChange={e => set("total_seats_business", e.target.value)} className={INPUT} />
        </div>
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Business $</label>
          <input type="number" step="0.01" min={0} value={form.price_business} onChange={e => set("price_business", e.target.value)} className={INPUT} />
        </div>
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">First Seats</label>
          <input type="number" min={0} value={form.total_seats_first} onChange={e => set("total_seats_first", e.target.value)} className={INPUT} />
        </div>
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">First $</label>
          <input type="number" step="0.01" min={0} value={form.price_first} onChange={e => set("price_first", e.target.value)} className={INPUT} />
        </div>
      </div>

      {create.isError && <p className="text-xs text-red-500">{create.error instanceof Error ? create.error.message : "Creation failed"}</p>}
      <div className="flex gap-3 pt-1">
        <button onClick={onClose} className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium hover:bg-gray-50 transition-colors">Cancel</button>
        <button
          onClick={() => create.mutate()}
          disabled={create.isPending || !form.flight_number || !form.airline || !form.origin || !form.destination || !form.departure_date || !form.departure_time || !form.arrival_date || !form.arrival_time}
          className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {create.isPending ? "Creating…" : "Create Flight"}
        </button>
      </div>
    </div>
  );
}

export function StaffFlightsPage() {
  const { user } = useAuth();
  const [showCreate, setShowCreate] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const isStaff = ["admin", "airline-staff"].includes(user?.role ?? "");

  const { data, isLoading, isError } = useQuery<{ items: Flight[] }>({
    queryKey: ["staff-flights"],
    queryFn: async () => {
      const { data, error } = await (flightClient as any).GET("/api/v1/flights", {
        params: { query: { page_size: 100 } },
      });
      if (error) throw new Error("Failed to load flights");
      return data as { items: Flight[] };
    },
    enabled: isStaff,
  });

  if (!isStaff) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <div className="text-5xl mb-4">🔒</div>
        <h2 className="text-xl font-bold text-gray-800">Access Restricted</h2>
        <p className="text-sm text-gray-400 mt-2">This page is only available to airline staff and administrators.</p>
      </div>
    );
  }

  const flights = (data?.items ?? []).filter(f =>
    !search || [f.flight_number, f.origin, f.destination, f.airline].some(v =>
      v.toLowerCase().includes(search.toLowerCase())
    )
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Flight Management</h2>
          <p className="mt-1 text-sm text-gray-500">Create and update flights in the schedule.</p>
        </div>
        <button
          onClick={() => { setShowCreate(true); setEditingId(null); }}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 transition-colors"
        >
          + New Flight
        </button>
      </div>

      {showCreate && <CreatePanel onClose={() => setShowCreate(false)} />}

      <input
        value={search}
        onChange={e => setSearch(e.target.value)}
        placeholder="Search by flight number, origin, destination or airline…"
        className="w-full rounded-xl border border-gray-200 px-4 py-2.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
      />

      {isLoading && <p className="text-sm text-gray-400 animate-pulse">Loading flights…</p>}
      {isError   && <p className="text-sm text-red-500">Failed to load flights.</p>}

      {!isLoading && flights.length === 0 && (
        <div className="rounded-2xl border border-dashed border-gray-200 bg-white px-8 py-14 text-center">
          <p className="font-semibold text-gray-500">{search ? "No flights match your search" : "No flights in the schedule"}</p>
          <p className="mt-1 text-sm text-gray-400">{!search && "Click \"+ New Flight\" to add one."}</p>
        </div>
      )}

      <div className="space-y-3">
        {flights.map((f) => {
          const ss = STATUS_STYLE[f.status] ?? "bg-gray-100 text-gray-500 border-gray-200";
          const isEditing = editingId === f.id;
          return (
            <div key={f.id} className="rounded-2xl bg-white border border-gray-100 shadow-sm overflow-hidden">
              <div className="flex items-center gap-4 px-5 py-3 flex-wrap">
                {/* Route */}
                <div className="flex items-center gap-2 min-w-[160px]">
                  <span className="font-mono font-bold text-blue-700">{f.flight_number}</span>
                  <span className="text-gray-400">·</span>
                  <span className="font-mono font-semibold text-gray-700">{f.origin}</span>
                  <span className="text-gray-400">→</span>
                  <span className="font-mono font-semibold text-gray-700">{f.destination}</span>
                </div>

                {/* Date + times */}
                <div className="text-xs text-gray-500 min-w-[140px]">
                  <span>{f.departure_date}</span>
                  <span className="mx-1 text-gray-300">|</span>
                  <span>{f.departure_time.slice(0,5)} → {f.arrival_time.slice(0,5)}</span>
                </div>

                {/* Airline */}
                <span className="text-xs text-gray-500 flex-1">{f.airline}</span>

                {/* Gate / terminal */}
                {(f.gate || f.terminal) && (
                  <span className="text-xs text-gray-400">
                    {f.terminal && `T${f.terminal}`}{f.gate && ` · Gate ${f.gate}`}
                  </span>
                )}

                {/* Seats */}
                <div className="flex gap-2 text-[11px] text-gray-400">
                  <span title="Economy">E:{f.available_seats_economy}</span>
                  <span title="Business">B:{f.available_seats_business}</span>
                  <span title="First">F:{f.available_seats_first}</span>
                </div>

                {/* Status badge */}
                <span className={`rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize ${ss}`}>{f.status}</span>

                {/* Edit button */}
                <button
                  onClick={() => setEditingId(isEditing ? null : f.id)}
                  className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 transition-colors shrink-0"
                >
                  {isEditing ? "Close" : "Edit"}
                </button>
              </div>

              {isEditing && <EditPanel flight={f} onClose={() => setEditingId(null)} />}
            </div>
          );
        })}
      </div>
    </div>
  );
}
