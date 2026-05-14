import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { passengerClient } from "../api/client";
import { useAuth } from "../contexts/AuthContext";

interface PassengerProfile {
  id: string;
  user_id: string;
  first_name: string;
  last_name: string;
  date_of_birth: string | null;
  nationality: string | null;
  passport_number: string | null;
  phone_number: string | null;
  loyalty_tier: string;
  loyalty_points: number;
  meal_preference: string | null;
  seat_preference: string | null;
  created_at: string;
}

const ROLE_LABEL: Record<string, string> = {
  passenger:          "Passenger",
  admin:              "Administrator",
  "airline-staff":    "Airline Staff",
  "airport-operator": "Airport Operator",
  "partner-api":      "Partner API",
};

const TIER_STYLE: Record<string, string> = {
  bronze:   "bg-amber-100   text-amber-800",
  silver:   "bg-gray-100    text-gray-700",
  gold:     "bg-yellow-100  text-yellow-800",
  platinum: "bg-blue-100    text-blue-800",
};

const INPUT = "w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500";
const SELECT = "w-full h-9 rounded-lg border border-gray-300 px-2 text-sm bg-white focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500";

export function ProfilePage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);

  const { data: profile, isLoading, isError, error } = useQuery<PassengerProfile | null>({
    queryKey: ["passenger-profile"],
    queryFn: async () => {
      const { data, error: err } = await passengerClient.GET("/api/v1/passengers/profile", {});
      if (err) return null;
      return (data as PassengerProfile) ?? null;
    },
    retry: false,
  });

  const hasProfile = !!profile?.id;

  const [form, setForm] = useState({
    first_name: "", last_name: "", date_of_birth: "",
    nationality: "", passport_number: "", phone_number: "",
    meal_preference: "", seat_preference: "",
  });

  useEffect(() => {
    if (profile) {
      setForm({
        first_name:      profile.first_name    ?? "",
        last_name:       profile.last_name     ?? "",
        date_of_birth:   profile.date_of_birth ?? "",
        nationality:     profile.nationality   ?? "",
        passport_number: profile.passport_number ?? "",
        phone_number:    profile.phone_number  ?? "",
        meal_preference: profile.meal_preference ?? "",
        seat_preference: profile.seat_preference ?? "",
      });
    }
  }, [profile]);

  const save = useMutation({
    mutationFn: async () => {
      const body = {
        first_name:      form.first_name,
        last_name:       form.last_name,
        date_of_birth:   form.date_of_birth   || undefined,
        nationality:     form.nationality     || undefined,
        passport_number: form.passport_number || undefined,
        phone_number:    form.phone_number    || undefined,
        meal_preference: form.meal_preference || undefined,
        seat_preference: form.seat_preference || undefined,
      };
      if (hasProfile) {
        const { error } = await passengerClient.PUT("/api/v1/passengers/profile", { body });
        if (error) throw new Error("Failed to update profile");
      } else {
        const { error } = await passengerClient.POST("/api/v1/passengers/profile", { body: body as any });
        if (error) throw new Error("Failed to create profile");
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["passenger-profile"] });
      setEditing(false);
    },
  });

  if (isLoading) return <p className="text-sm text-gray-400 animate-pulse">Loading profile…</p>;

  const initials = user?.full_name?.charAt(0).toUpperCase() ?? "?";

  return (
    <div className="space-y-6 max-w-2xl">
      <h2 className="text-2xl font-bold text-gray-900">Profile</h2>

      {/* Account info card */}
      <div className="rounded-2xl bg-white border border-gray-100 shadow-sm p-6">
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-4">
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-blue-600 text-xl font-bold text-white">
              {initials}
            </div>
            <div>
              <p className="font-bold text-gray-900 text-lg">{user?.full_name ?? user?.username}</p>
              <p className="text-sm text-gray-500">{ROLE_LABEL[user?.role ?? ""] ?? user?.role}</p>
            </div>
          </div>
          {profile && (
            <div className="text-right">
              <span className={`rounded-full px-3 py-1 text-xs font-bold uppercase tracking-wide ${TIER_STYLE[profile.loyalty_tier] ?? "bg-gray-100 text-gray-500"}`}>
                {profile.loyalty_tier}
              </span>
              <p className="text-xs text-gray-400 mt-1">{profile.loyalty_points.toLocaleString()} pts</p>
            </div>
          )}
        </div>

        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm border-t pt-4">
          <div>
            <dt className="text-gray-400 text-xs uppercase font-semibold tracking-wide">Email</dt>
            <dd className="font-medium text-gray-900 mt-0.5">{user?.email}</dd>
          </div>
          <div>
            <dt className="text-gray-400 text-xs uppercase font-semibold tracking-wide">Username</dt>
            <dd className="font-medium text-gray-900 mt-0.5">{user?.username}</dd>
          </div>
        </dl>
      </div>

      {/* Passenger profile card */}
      <div className="rounded-2xl bg-white border border-gray-100 shadow-sm p-6">
        <div className="flex items-center justify-between mb-5">
          <div>
            <h3 className="font-bold text-gray-900">Passenger Details</h3>
            <p className="text-xs text-gray-400 mt-0.5">
              {hasProfile ? "Used for check-in and passport verification." : "Add your details for faster booking."}
            </p>
          </div>
          {!editing && (
            <button
              onClick={() => setEditing(true)}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 transition-colors"
            >
              {hasProfile ? "Edit" : "Add Details"}
            </button>
          )}
        </div>

        {!hasProfile && !editing && (
          <div className="rounded-xl border border-dashed border-gray-200 px-6 py-8 text-center">
            <p className="text-gray-400 text-sm">No passenger profile yet.</p>
            <p className="text-gray-400 text-xs mt-1">Click "Add Details" to get started.</p>
          </div>
        )}

        {hasProfile && !editing && (
          <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
            {[
              { label: "First Name",      value: profile.first_name },
              { label: "Last Name",       value: profile.last_name },
              { label: "Date of Birth",   value: profile.date_of_birth ?? "—" },
              { label: "Nationality",     value: profile.nationality ?? "—" },
              { label: "Passport",        value: profile.passport_number ?? "—" },
              { label: "Phone",           value: profile.phone_number ?? "—" },
              { label: "Meal Preference", value: profile.meal_preference ?? "—" },
              { label: "Seat Preference", value: profile.seat_preference ?? "—" },
            ].map(({ label, value }) => (
              <div key={label}>
                <dt className="text-gray-400 text-xs uppercase font-semibold tracking-wide">{label}</dt>
                <dd className="font-medium text-gray-900 mt-0.5 capitalize">{value}</dd>
              </div>
            ))}
          </dl>
        )}

        {editing && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">First Name*</label>
                <input value={form.first_name} onChange={(e) => setForm(f => ({ ...f, first_name: e.target.value }))}
                  className={INPUT} placeholder="First name" />
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Last Name*</label>
                <input value={form.last_name} onChange={(e) => setForm(f => ({ ...f, last_name: e.target.value }))}
                  className={INPUT} placeholder="Last name" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Date of Birth</label>
                <input type="date" value={form.date_of_birth}
                  onChange={(e) => setForm(f => ({ ...f, date_of_birth: e.target.value }))}
                  className={INPUT} />
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Nationality</label>
                <input value={form.nationality} onChange={(e) => setForm(f => ({ ...f, nationality: e.target.value }))}
                  className={INPUT} placeholder="e.g. British" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Passport Number</label>
                <input value={form.passport_number} onChange={(e) => setForm(f => ({ ...f, passport_number: e.target.value.toUpperCase() }))}
                  className={INPUT} placeholder="e.g. A1234567" />
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Phone Number</label>
                <input value={form.phone_number} onChange={(e) => setForm(f => ({ ...f, phone_number: e.target.value }))}
                  className={INPUT} placeholder="+1 555 0000" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Meal Preference</label>
                <select value={form.meal_preference} onChange={(e) => setForm(f => ({ ...f, meal_preference: e.target.value }))}
                  className={SELECT}>
                  <option value="">No preference</option>
                  <option value="standard">Standard</option>
                  <option value="vegetarian">Vegetarian</option>
                  <option value="vegan">Vegan</option>
                  <option value="halal">Halal</option>
                  <option value="kosher">Kosher</option>
                  <option value="gluten_free">Gluten Free</option>
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Seat Preference</label>
                <select value={form.seat_preference} onChange={(e) => setForm(f => ({ ...f, seat_preference: e.target.value }))}
                  className={SELECT}>
                  <option value="">No preference</option>
                  <option value="window">Window</option>
                  <option value="aisle">Aisle</option>
                  <option value="middle">Middle</option>
                  <option value="front">Front</option>
                  <option value="rear">Rear</option>
                  <option value="extra_legroom">Extra Legroom</option>
                </select>
              </div>
            </div>

            {save.isError && (
              <p className="text-xs text-red-500">{save.error instanceof Error ? save.error.message : "Save failed"}</p>
            )}

            <div className="flex gap-3 pt-2">
              <button onClick={() => { setEditing(false); }}
                className="flex-1 rounded-lg border border-gray-300 py-2.5 text-sm font-medium hover:bg-gray-50 transition-colors">
                Cancel
              </button>
              <button
                onClick={() => save.mutate()}
                disabled={save.isPending || !form.first_name || !form.last_name}
                className="flex-1 rounded-lg bg-blue-600 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50 transition-colors">
                {save.isPending ? "Saving…" : "Save Changes"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
