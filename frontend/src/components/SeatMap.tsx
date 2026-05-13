export interface Section {
  cabin: string;
  rowStart: number;
  rowEnd: number;
  leftCols: string[];
  rightCols: string[];
}

interface AircraftConfig {
  sections: Section[];
}

export const CONFIGS: Record<string, AircraftConfig> = {
  "Airbus A320": {
    sections: [
      { cabin: "business", rowStart: 1, rowEnd: 5,  leftCols: ["A","B"],       rightCols: ["D","E"]       },
      { cabin: "economy",  rowStart: 6, rowEnd: 30, leftCols: ["A","B","C"],   rightCols: ["D","E","F"]   },
    ],
  },
  "Boeing 737": {
    sections: [
      { cabin: "first",    rowStart: 1, rowEnd: 2,  leftCols: ["A","B"],       rightCols: ["D","E","F"]   },
      { cabin: "business", rowStart: 3, rowEnd: 7,  leftCols: ["A","B","C"],   rightCols: ["D","E","F"]   },
      { cabin: "economy",  rowStart: 8, rowEnd: 32, leftCols: ["A","B","C"],   rightCols: ["D","E","F"]   },
    ],
  },
  "Boeing 787": {
    sections: [
      { cabin: "first",    rowStart: 1,  rowEnd: 3,  leftCols: ["A","B"],     rightCols: ["D","E"]       },
      { cabin: "business", rowStart: 4,  rowEnd: 11, leftCols: ["A","B","C"], rightCols: ["D","E","F"]   },
      { cabin: "economy",  rowStart: 12, rowEnd: 51, leftCols: ["A","B","C"], rightCols: ["D","E","F"]   },
    ],
  },
  "Airbus A380": {
    sections: [
      { cabin: "first",    rowStart: 1,  rowEnd: 2,  leftCols: ["A","B","C"], rightCols: ["E","F","G"]   },
      { cabin: "business", rowStart: 3,  rowEnd: 16, leftCols: ["A","B","C"], rightCols: ["D","E","F"]   },
      { cabin: "economy",  rowStart: 17, rowEnd: 83, leftCols: ["A","B","C"], rightCols: ["D","E","F"]   },
    ],
  },
};

export const DEFAULT_CONFIG: AircraftConfig = {
  sections: [
    { cabin: "business", rowStart: 1, rowEnd: 5,  leftCols: ["A","B"],     rightCols: ["D","E"]     },
    { cabin: "economy",  rowStart: 6, rowEnd: 35, leftCols: ["A","B","C"], rightCols: ["D","E","F"] },
  ],
};

const CABIN_COLOURS: Record<string, string> = {
  economy:  "bg-sky-50  text-sky-700  border-sky-200",
  business: "bg-amber-50 text-amber-700 border-amber-200",
  first:    "bg-purple-50 text-purple-700 border-purple-200",
};

interface SeatMapProps {
  aircraftType: string | null;
  cabinClass: string;
  selectedSeat: string;
  onSeatSelect: (seat: string) => void;
  bookedSeats: string[];
  isLoading?: boolean;
}

export function SeatMap({
  aircraftType,
  cabinClass,
  selectedSeat,
  onSeatSelect,
  bookedSeats,
  isLoading = false,
}: SeatMapProps) {
  const config = (aircraftType && CONFIGS[aircraftType]) ? CONFIGS[aircraftType] : DEFAULT_CONFIG;
  const section = config.sections.find((s) => s.cabin === cabinClass);
  const bookedSet = new Set(bookedSeats);

  if (!section) {
    return (
      <p className="text-sm text-gray-400">
        No seat map available for {cabinClass} class on this aircraft.
      </p>
    );
  }

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-400 animate-pulse py-8">
        <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M4 12a8 8 0 018-8v8H4z" />
        </svg>
        Loading seat availability…
      </div>
    );
  }

  const rows: number[] = [];
  for (let r = section.rowStart; r <= section.rowEnd; r++) rows.push(r);

  const allCols = [...section.leftCols, ...section.rightCols];
  const cabinColour = CABIN_COLOURS[cabinClass] ?? "bg-gray-50 text-gray-700 border-gray-200";

  return (
    <div className="space-y-4">
      {/* Aircraft + cabin label */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <svg className="w-5 h-5 text-gray-400" viewBox="0 0 24 24" fill="currentColor">
            <path d="M21 16v-2l-8-5V3.5a1.5 1.5 0 0 0-3 0V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z"/>
          </svg>
          <span className="text-sm font-medium text-gray-600">{aircraftType ?? "Aircraft"}</span>
        </div>
        <span className={`rounded-full border px-3 py-0.5 text-xs font-semibold capitalize ${cabinColour}`}>
          {cabinClass} class · rows {section.rowStart}–{section.rowEnd}
        </span>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-4 text-xs text-gray-500">
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-5 h-5 rounded border border-gray-300 bg-white" />
          Available
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-5 h-5 rounded bg-gray-300" />
          Taken
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-5 h-5 rounded bg-blue-500" />
          Your seat
        </span>
      </div>

      {/* Seat grid */}
      <div className="overflow-x-auto rounded-xl border border-gray-100 bg-gray-50/50 p-3">
        {/* Column headers */}
        <div className="flex items-center gap-1 pl-8 mb-2">
          {section.leftCols.map((c) => (
            <div key={c} className="w-8 text-center text-[11px] font-bold text-gray-400">{c}</div>
          ))}
          <div className="w-5" />
          {section.rightCols.map((c) => (
            <div key={c} className="w-8 text-center text-[11px] font-bold text-gray-400">{c}</div>
          ))}
        </div>

        {/* Rows */}
        <div className="max-h-96 overflow-y-auto space-y-1">
          {rows.map((row) => (
            <div key={row} className="flex items-center gap-1">
              {/* Row number */}
              <div className="w-6 text-right text-[10px] text-gray-400 shrink-0 tabular-nums">{row}</div>
              <div className="w-2 shrink-0" />

              {/* Left seats */}
              {section.leftCols.map((col) => {
                const seat = `${row}${col}`;
                const taken    = bookedSet.has(seat);
                const selected = selectedSeat === seat;
                return (
                  <button
                    key={seat}
                    type="button"
                    title={seat}
                    disabled={taken}
                    onClick={() => onSeatSelect(selected ? "" : seat)}
                    className={`w-8 h-7 rounded text-[10px] font-semibold transition-all ${
                      taken
                        ? "bg-gray-300 text-gray-400 cursor-not-allowed"
                        : selected
                        ? "bg-blue-500 text-white shadow ring-2 ring-blue-300 ring-offset-1 scale-105"
                        : "bg-white border border-gray-200 text-gray-500 hover:border-blue-400 hover:bg-blue-50 hover:text-blue-600"
                    }`}
                  >
                    {selected ? "✓" : ""}
                  </button>
                );
              })}

              {/* Aisle */}
              <div className="w-5 shrink-0 flex items-center justify-center">
                <div className="h-full w-px bg-gray-200" />
              </div>

              {/* Right seats */}
              {section.rightCols.map((col) => {
                const seat = `${row}${col}`;
                const taken    = bookedSet.has(seat);
                const selected = selectedSeat === seat;
                return (
                  <button
                    key={seat}
                    type="button"
                    title={seat}
                    disabled={taken}
                    onClick={() => onSeatSelect(selected ? "" : seat)}
                    className={`w-8 h-7 rounded text-[10px] font-semibold transition-all ${
                      taken
                        ? "bg-gray-300 text-gray-400 cursor-not-allowed"
                        : selected
                        ? "bg-blue-500 text-white shadow ring-2 ring-blue-300 ring-offset-1 scale-105"
                        : "bg-white border border-gray-200 text-gray-500 hover:border-blue-400 hover:bg-blue-50 hover:text-blue-600"
                    }`}
                  >
                    {selected ? "✓" : ""}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      </div>

      {/* Selected seat callout */}
      {selectedSeat ? (
        <div className="flex items-center justify-between rounded-lg bg-blue-50 border border-blue-200 px-4 py-2.5">
          <p className="text-sm font-semibold text-blue-700">
            Seat <span className="font-mono text-base">{selectedSeat}</span> selected
          </p>
          <button
            type="button"
            onClick={() => onSeatSelect("")}
            className="text-xs text-blue-400 hover:text-blue-600 transition-colors"
          >
            Clear
          </button>
        </div>
      ) : (
        <p className="text-xs text-gray-400 text-center">Click a seat to select it</p>
      )}
    </div>
  );
}
