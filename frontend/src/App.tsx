import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "./contexts/AuthContext";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { Layout } from "./components/Layout";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { LoginPage } from "./pages/LoginPage";
import { RegisterPage } from "./pages/RegisterPage";
import { CallbackPage } from "./pages/CallbackPage";
import { DashboardPage } from "./pages/DashboardPage";
import { FlightsPage } from "./pages/FlightsPage";
import { BookingsPage } from "./pages/BookingsPage";
import { CheckInPage } from "./pages/CheckInPage";
import { BaggagePage } from "./pages/BaggagePage";
import { ProfilePage } from "./pages/ProfilePage";
import { BookFlightPage } from "./pages/BookFlightPage";
import { NotificationsPage } from "./pages/NotificationsPage";
import { BaggageTrackingPage } from "./pages/BaggageTrackingPage";
import { StaffFlightsPage } from "./pages/StaffFlightsPage";

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
            <Route path="/callback" element={<CallbackPage />} />
            <Route element={<ProtectedRoute />}>
              <Route element={<Layout />}>
                <Route index         element={<ErrorBoundary><DashboardPage /></ErrorBoundary>} />
                <Route path="flights"  element={<ErrorBoundary><FlightsPage /></ErrorBoundary>} />
                <Route path="book"     element={<ErrorBoundary><BookFlightPage /></ErrorBoundary>} />
                <Route path="bookings" element={<ErrorBoundary><BookingsPage /></ErrorBoundary>} />
                <Route path="checkin"  element={<ErrorBoundary><CheckInPage /></ErrorBoundary>} />
                <Route path="baggage"  element={<ErrorBoundary><BaggagePage /></ErrorBoundary>} />
                <Route path="profile"       element={<ErrorBoundary><ProfilePage /></ErrorBoundary>} />
                <Route path="notifications" element={<ErrorBoundary><NotificationsPage /></ErrorBoundary>} />
                <Route path="track"         element={<ErrorBoundary><BaggageTrackingPage /></ErrorBoundary>} />
                <Route path="staff/flights" element={<ErrorBoundary><StaffFlightsPage /></ErrorBoundary>} />
              </Route>
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}
