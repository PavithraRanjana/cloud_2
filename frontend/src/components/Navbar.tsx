import { NavLink, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../contexts/AuthContext";
import { notificationClient } from "../api/client";

const PASSENGER_LINKS = [
  { to: "/flights",       label: "Flights"        },
  { to: "/bookings",      label: "Bookings"       },
  { to: "/checkin",       label: "Check-in"       },
  { to: "/baggage",       label: "Baggage"        },
  { to: "/notifications", label: "Notifications"  },
];

const ADMIN_LINKS = [
  { to: "/flights",       label: "Flights"        },
  { to: "/notifications", label: "Notifications"  },
];

const PUBLIC_LINKS = [
  { to: "/flights",   label: "Flights"         },
  { to: "/bookings",  label: "Bookings"        },
  { to: "/checkin",   label: "Check-in"        },
  { to: "/baggage",   label: "Baggage"         },
  { to: "/track",     label: "Track Baggage"   },
];

export function Navbar() {
  const { user, token, logout } = useAuth();
  const navigate = useNavigate();
  const isAdmin = user?.role === "admin";

  const links = !token ? PUBLIC_LINKS : isAdmin ? ADMIN_LINKS : PASSENGER_LINKS;

  const { data: notifications = [] } = useQuery<{ is_read: boolean }[]>({
    queryKey: ["notifications"],
    queryFn: async () => {
      const { data } = await notificationClient.GET("/api/v1/notifications", {});
      return (data as { is_read: boolean }[]) ?? [];
    },
    enabled: !!token,
    refetchInterval: 60_000,
    staleTime: 30_000,
    retry: 0,
  });

  const unreadCount = notifications.filter((n) => !n.is_read).length;

  function handleLogout() {
    logout();
    navigate("/");
  }

  return (
    <header className="bg-blue-700 text-white shadow">
      <div className="mx-auto flex max-w-7xl items-center gap-6 px-6 py-3">
        <NavLink to="/" className="text-xl font-bold tracking-tight hover:opacity-90 transition-opacity">
          ✈ AeroLink
        </NavLink>

        <nav className="flex flex-1 gap-1 flex-wrap">
          {links.map(({ to, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                `relative rounded px-3 py-1.5 text-sm font-medium transition-colors ${
                  isActive ? "bg-white/20" : "hover:bg-white/10"
                }`
              }
            >
              {label}
              {to === "/notifications" && unreadCount > 0 && (
                <span className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[10px] font-bold text-white">
                  {unreadCount > 9 ? "9+" : unreadCount}
                </span>
              )}
            </NavLink>
          ))}
          {isAdmin && (
            <NavLink
              to="/staff/flights"
              className={({ isActive }) =>
                `rounded px-3 py-1.5 text-sm font-medium transition-colors border border-white/30 ${
                  isActive ? "bg-white/20" : "hover:bg-white/10"
                }`
              }
            >
              Flights ✦
            </NavLink>
          )}
        </nav>

        <div className="flex items-center gap-3 text-sm">
          {token ? (
            <>
              <NavLink
                to="/profile"
                className="rounded px-3 py-1.5 hover:bg-white/10 transition-colors"
              >
                {user?.full_name ?? user?.username}
              </NavLink>
              <button
                onClick={handleLogout}
                className="rounded border border-white/40 px-3 py-1.5 hover:bg-white/10 transition-colors"
              >
                Logout
              </button>
            </>
          ) : (
            <>
              <NavLink
                to="/login"
                className="rounded px-3 py-1.5 hover:bg-white/10 transition-colors"
              >
                Sign in
              </NavLink>
              <NavLink
                to="/register"
                className="rounded border border-white/40 px-3 py-1.5 hover:bg-white/10 transition-colors"
              >
                Sign up
              </NavLink>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
