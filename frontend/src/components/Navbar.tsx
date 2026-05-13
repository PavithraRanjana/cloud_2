import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";

const links = [
  { to: "/",            label: "Dashboard" },
  { to: "/flights",     label: "Flights"   },
  { to: "/bookings",    label: "Bookings"  },
  { to: "/checkin",     label: "Check-in"  },
  { to: "/baggage",     label: "Baggage"   },
];

export function Navbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <header className="bg-blue-700 text-white shadow">
      <div className="mx-auto flex max-w-7xl items-center gap-6 px-6 py-3">
        <span className="text-xl font-bold tracking-tight">✈ AeroLink</span>

        <nav className="flex flex-1 gap-1">
          {links.map(({ to, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                `rounded px-3 py-1.5 text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-white/20"
                    : "hover:bg-white/10"
                }`
              }
            >
              {label}
            </NavLink>
          ))}
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
