import { NavLink, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../contexts/AuthContext";
import { notificationClient } from "../api/client";

const PASSENGER_LINKS = [
  { to: "/",              label: "Dashboard"      },
  { to: "/flights",       label: "Flights"        },
  { to: "/bookings",      label: "Bookings"       },
  { to: "/checkin",       label: "Check-in"       },
  { to: "/baggage",       label: "Baggage"        },
  { to: "/notifications", label: "Notifications"  },
];

const ADMIN_LINKS = [
  { to: "/",              label: "Dashboard"      },
  { to: "/flights",       label: "Flights"        },
  { to: "/notifications", label: "Notifications"  },
];

export function Navbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const isAdmin = user?.role === "admin";
  const links = isAdmin ? ADMIN_LINKS : PASSENGER_LINKS;

  const { data: notifications = [] } = useQuery<{ is_read: boolean }[]>({
    queryKey: ["notifications"],
    queryFn: async () => {
      const { data } = await notificationClient.GET("/api/v1/notifications", {});
      return (data as { is_read: boolean }[]) ?? [];
    },
    refetchInterval: 60_000,
    staleTime: 30_000,
    retry: 0,
  });

  const unreadCount = notifications.filter((n) => !n.is_read).length;

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <header className="bg-blue-700 text-white shadow">
      <div className="mx-auto flex max-w-7xl items-center gap-6 px-6 py-3">
        <span className="text-xl font-bold tracking-tight">✈ AeroLink</span>

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
          {["admin", "airline-staff"].includes(user?.role ?? "") && (
            <NavLink
              to="/staff/flights"
              className={({ isActive }) =>
                `rounded px-3 py-1.5 text-sm font-medium transition-colors border border-white/30 ${
                  isActive ? "bg-white/20" : "hover:bg-white/10"
                }`
              }
            >
              Staff ✦
            </NavLink>
          )}
        </nav>

        <div className="flex items-center gap-3 text-sm">
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
        </div>
      </div>
    </header>
  );
}
