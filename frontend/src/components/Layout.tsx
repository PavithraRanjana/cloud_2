import { useEffect } from "react";
import { Outlet, useNavigate } from "react-router-dom";
import { Navbar } from "./Navbar";

export function Layout() {
  const navigate = useNavigate();

  useEffect(() => {
    const handler = () => navigate("/login", { replace: true });
    window.addEventListener("auth:session-expired", handler);
    return () => window.removeEventListener("auth:session-expired", handler);
  }, [navigate]);

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />
      <main className="mx-auto max-w-7xl px-6 py-8">
        <Outlet />
      </main>
    </div>
  );
}
