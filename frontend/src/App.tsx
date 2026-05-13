import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "./contexts/AuthContext";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { Layout } from "./components/Layout";
import { LoginPage } from "./pages/LoginPage";
import { RegisterPage } from "./pages/RegisterPage";
import { DashboardPage } from "./pages/DashboardPage";
import { FlightsPage } from "./pages/FlightsPage";
import { BookingsPage } from "./pages/BookingsPage";
import { CheckInPage } from "./pages/CheckInPage";
import { BaggagePage } from "./pages/BaggagePage";
import { ProfilePage } from "./pages/ProfilePage";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login"    element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route element={<ProtectedRoute />}>
              <Route element={<Layout />}>
                <Route index         element={<DashboardPage />} />
                <Route path="flights"  element={<FlightsPage />} />
                <Route path="bookings" element={<BookingsPage />} />
                <Route path="checkin"  element={<CheckInPage />} />
                <Route path="baggage"  element={<BaggagePage />} />
                <Route path="profile"  element={<ProfilePage />} />
              </Route>
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}
