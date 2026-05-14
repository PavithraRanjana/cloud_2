import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { baggageClient } from "../api/client";

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

const STATUS_STYLE: Record<string, { colour: string; icon: string; label: string }> = {
  checked_in:  { colour: "bg-blue-50   border-blue-200   text-blue-700",    icon: "📦", label: "Checked In"  },
  in_transit:  { colour: "bg-amber-50  border-amber-200  text-amber-700",   icon: "🚚", label: "In Transit"  },
  arrived:     { colour: "bg-emerald-50 border-emerald-200 text-emerald-700", icon: "✅", label: "Arrived"    },
  delivered:   { colour: "bg-emerald-50 border-emerald-200 text-emerald-700", icon: "✅", label: "Delivered"  },
  lost:        { colour: "bg-red-50    border-red-200    text-red-600",     icon: "❌", label: "Lost"        },
};

const STEPS = ["checked_in", "in_transit", "arrived", "delivered"];

function StatusTimeline({ current }: { current: string }) {
  if (current === "lost") return null;
  const idx = STEPS.indexOf(current);
  return (
    <div className="flex items-center gap-0 mt-6">
      {STEPS.map((step, i) => {
        const done    = i <= idx;
        const active  = i === idx;
        const label   = STATUS_STYLE[step]?.label ?? step;
        return (
          <div key={step} className="flex-1 flex flex-col items-center">
            <div className="flex items-center w-full">
              {i > 0 && <div className={`flex-1 h-1 ${done ? "bg-blue-500" : "bg-gray-200"}`} />}
              <div className={`w-8 h-8 rounded-full border-2 flex items-center justify-center text-sm shrink-0
                ${active  ? "border-blue-600 bg-blue-600 text-white shadow-md shadow-blue-200" :
                  done    ? "border-blue-500 bg-blue-500 text-white" :
                            "border-gray-200 bg-white text-gray-300"}`}>
                {done ? "✓" : i + 1}
              </div>
              {i < STEPS.length - 1 && <div className={`flex-1 h-1 ${i < idx ? "bg-blue-500" : "bg-gray-200"}`} />}
            </div>
            <p className={`mt-1.5 text-[11px] font-medium text-center ${active ? "text-blue-600" : done ? "text-gray-600" : "text-gray-300"}`}>
              {label}
            </p>
          </div>
        );
      })}
    </div>
  );
}

export function BaggageTrackingPage() {
  const [input, setInput] = useState("");
  const [searchTag, setSearchTag] = useState("");

  const { data: bag, isLoading, isError, error } = useQuery<BaggageItem>({
    queryKey: ["baggage-track", searchTag],
    queryFn: async () => {
      const { data, error: err } = await (baggageClient as any).GET(`/api/v1/baggage/${searchTag}`, {});
      if (err) throw new Error((err as any)?.detail ?? "Baggage not found");
      if (!data) throw new Error("Baggage not found");
      return data as BaggageItem;
    },
    enabled: !!searchTag,
    retry: false,
  });

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = input.trim().toUpperCase();
    if (trimmed) setSearchTag(trimmed);
  }

  const statusMeta = bag ? (STATUS_STYLE[bag.status] ?? { colour: "bg-gray-50 border-gray-200 text-gray-600", icon: "📦", label: bag.status }) : null;

  return (
    <div className="space-y-6 max-w-xl">
      <div>
        <h2 className="text-2xl font-bold text-gray-900">Track Baggage</h2>
        <p className="mt-1 text-sm text-gray-500">Enter your baggage tag number to see real-time status.</p>
      </div>

      {/* Search form */}
      <form onSubmit={handleSearch} className="flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value.toUpperCase())}
          placeholder="e.g. BAG-A1B2C3"
          className="flex-1 rounded-xl border border-gray-300 px-4 py-2.5 font-mono text-sm uppercase tracking-wider focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
        <button
          type="submit"
          disabled={!input.trim() || isLoading}
          className="rounded-xl bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {isLoading ? "Searching…" : "Track"}
        </button>
      </form>

      {/* Not found */}
      {isError && searchTag && (
        <div className="rounded-2xl border border-red-100 bg-red-50 px-5 py-4 text-sm text-red-600">
          {error instanceof Error ? error.message : "Baggage not found. Check the tag number and try again."}
        </div>
      )}

      {/* Result */}
      {bag && statusMeta && (
        <div className="rounded-2xl bg-white border border-gray-100 shadow-sm overflow-hidden">
          {/* Status header */}
          <div className={`px-5 py-4 border-b ${statusMeta.colour} flex items-center justify-between`}>
            <div className="flex items-center gap-3">
              <span className="text-3xl">{statusMeta.icon}</span>
              <div>
                <p className="font-bold text-lg">{statusMeta.label}</p>
                {bag.last_location && (
                  <p className="text-sm mt-0.5 opacity-80">📍 {bag.last_location}</p>
                )}
              </div>
            </div>
            <span className="font-mono font-bold text-sm opacity-70">{bag.tag_number}</span>
          </div>

          {/* Timeline */}
          <div className="px-5 py-4 border-b border-gray-100">
            <StatusTimeline current={bag.status} />
          </div>

          {/* Details */}
          <dl className="grid grid-cols-2 gap-x-6 gap-y-3 px-5 py-4 text-sm">
            <div>
              <dt className="text-xs font-semibold uppercase tracking-wide text-gray-400">Passenger</dt>
              <dd className="mt-0.5 font-medium text-gray-900">{bag.passenger_name}</dd>
            </div>
            <div>
              <dt className="text-xs font-semibold uppercase tracking-wide text-gray-400">Weight</dt>
              <dd className="mt-0.5 font-medium text-gray-900">{bag.weight_kg} kg</dd>
            </div>
            {bag.description && (
              <div className="col-span-2">
                <dt className="text-xs font-semibold uppercase tracking-wide text-gray-400">Description</dt>
                <dd className="mt-0.5 font-medium text-gray-900">{bag.description}</dd>
              </div>
            )}
            <div className="col-span-2">
              <dt className="text-xs font-semibold uppercase tracking-wide text-gray-400">Registered</dt>
              <dd className="mt-0.5 font-medium text-gray-900">
                {new Date(bag.created_at).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}
              </dd>
            </div>
          </dl>
        </div>
      )}

      {/* Empty initial state */}
      {!searchTag && (
        <div className="rounded-2xl border border-dashed border-gray-200 bg-white px-8 py-14 text-center">
          <div className="text-4xl mb-3">🧳</div>
          <p className="font-semibold text-gray-500">Enter a tag number above</p>
          <p className="mt-1 text-sm text-gray-400">Your baggage tag is printed on the label attached to your bag at check-in.</p>
        </div>
      )}
    </div>
  );
}
