import { useState, useRef, useEffect } from "react";

export const AIRPORTS: Record<string, { city: string; country: string }> = {
  JFK: { city: "New York",       country: "United States"       },
  LAX: { city: "Los Angeles",    country: "United States"       },
  ORD: { city: "Chicago",        country: "United States"       },
  MIA: { city: "Miami",          country: "United States"       },
  SFO: { city: "San Francisco",  country: "United States"       },
  BOS: { city: "Boston",         country: "United States"       },
  ATL: { city: "Atlanta",        country: "United States"       },
  DFW: { city: "Dallas",         country: "United States"       },
  LHR: { city: "London",         country: "United Kingdom"      },
  LGW: { city: "London Gatwick", country: "United Kingdom"      },
  MAN: { city: "Manchester",     country: "United Kingdom"      },
  DUB: { city: "Dublin",         country: "Ireland"             },
  CMB: { city: "Colombo",        country: "Sri Lanka"           },
  SIN: { city: "Singapore",      country: "Singapore"           },
  SYD: { city: "Sydney",         country: "Australia"           },
  MEL: { city: "Melbourne",      country: "Australia"           },
  CDG: { city: "Paris",          country: "France"              },
  AMS: { city: "Amsterdam",      country: "Netherlands"         },
  FRA: { city: "Frankfurt",      country: "Germany"             },
  MUC: { city: "Munich",         country: "Germany"             },
  MAD: { city: "Madrid",         country: "Spain"               },
  BCN: { city: "Barcelona",      country: "Spain"               },
  FCO: { city: "Rome",           country: "Italy"               },
  ZRH: { city: "Zurich",         country: "Switzerland"         },
  BKK: { city: "Bangkok",        country: "Thailand"            },
  HKG: { city: "Hong Kong",      country: "Hong Kong"           },
  NRT: { city: "Tokyo",          country: "Japan"               },
  ICN: { city: "Seoul",          country: "South Korea"         },
  DXB: { city: "Dubai",          country: "United Arab Emirates"},
  DOH: { city: "Doha",           country: "Qatar"               },
  DEL: { city: "New Delhi",      country: "India"               },
  BOM: { city: "Mumbai",         country: "India"               },
};

interface Props {
  value: string;
  onChange: (code: string) => void;
  placeholder: string;
  exclude?: string;
}

export function AirportCombobox({ value, onChange, placeholder, exclude }: Props) {
  const [query, setQuery]   = useState("");
  const [open, setOpen]     = useState(false);
  const containerRef        = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onOutsideClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onOutsideClick);
    return () => document.removeEventListener("mousedown", onOutsideClick);
  }, []);

  const selectedLabel =
    value && AIRPORTS[value] ? `${AIRPORTS[value].city} (${value})` : "";

  const options = Object.entries(AIRPORTS).filter(([code, { city, country }]) => {
    if (code === exclude) return false;
    const q = query.toLowerCase();
    return (
      !q ||
      code.toLowerCase().includes(q) ||
      city.toLowerCase().includes(q) ||
      country.toLowerCase().includes(q)
    );
  });

  function select(code: string) {
    onChange(code);
    setQuery("");
    setOpen(false);
  }

  function handleClear(e: React.MouseEvent) {
    e.stopPropagation();
    onChange("");
    setQuery("");
  }

  return (
    <div ref={containerRef} className="relative">
      <div className="relative">
        <input
          type="text"
          placeholder={placeholder}
          value={open ? query : selectedLabel}
          onFocus={() => { setQuery(""); setOpen(true); }}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
          className="w-full rounded-lg border border-gray-300 px-3 py-2 pr-8 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
        {value && !open && (
          <button
            type="button"
            onClick={handleClear}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 text-lg leading-none"
          >
            ×
          </button>
        )}
      </div>

      {open && (
        <ul className="absolute z-50 mt-1 max-h-60 w-full overflow-auto rounded-lg border border-gray-200 bg-white shadow-lg text-sm">
          {options.length === 0 ? (
            <li className="px-3 py-2 text-gray-400">No airports found</li>
          ) : (
            options.map(([code, { city, country }]) => (
              <li
                key={code}
                onMouseDown={() => select(code)}
                className={`flex cursor-pointer items-center justify-between px-3 py-2.5 hover:bg-blue-50 ${
                  code === value ? "bg-blue-50" : ""
                }`}
              >
                <div>
                  <span className="font-medium text-gray-900">{city}</span>
                  <span className="ml-2 text-xs text-gray-400">{country}</span>
                </div>
                <span className="font-mono text-xs font-bold text-blue-600">{code}</span>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}
