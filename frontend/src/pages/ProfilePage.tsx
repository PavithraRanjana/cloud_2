import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { passengerClient } from "../api/client";
import { useAuth } from "../contexts/AuthContext";
import { NATIONALITIES } from "../data/nationalities";
import { COUNTRY_CODES } from "../data/countryCodes";

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

interface GDPRConsent {
  id: string;
  purpose: string;
  granted: boolean;
  granted_at: string | null;
  revoked_at: string | null;
}

const CONSENT_PURPOSES = [
  { key: "marketing_emails",    label: "Marketing Emails",  desc: "Receive promotional offers, deals, and travel inspiration from AeroLink." },
  { key: "analytics",           label: "Analytics",         desc: "Allow AeroLink to use your usage data to improve the service." },
  { key: "third_party_sharing", label: "Partner Offers",    desc: "Receive offers from AeroLink's airline and travel partners." },
  { key: "loyalty_program",     label: "Loyalty Programme", desc: "Participate in the AeroLink loyalty points programme." },
];

export function ProfilePage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState("");
  const [natQuery, setNatQuery] = useState("");
  const [natOpen, setNatOpen] = useState(false);
  const filteredNationalities = NATIONALITIES.filter((n) =>
    n.toLowerCase().includes(natQuery.toLowerCase())
  );

  const [ccQuery, setCcQuery] = useState("");
  const [ccOpen, setCcOpen] = useState(false);
  const filteredCountryCodes = COUNTRY_CODES.filter((cc) =>
    cc.label.toLowerCase().includes(ccQuery.toLowerCase()) ||
    cc.dial.includes(ccQuery)
  );

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
    nationality: "", passport_number: "", phone_country_code: "+1", phone_number: "",
    meal_preference: "", seat_preference: "",
  });

  useEffect(() => {
    if (profile) {
      const raw = profile.phone_number ?? "";
      const matched = COUNTRY_CODES.slice().sort((a, b) => b.dial.length - a.dial.length)
        .find((cc) => raw.startsWith(cc.dial));
      setForm({
        first_name:          profile.first_name    ?? "",
        last_name:           profile.last_name     ?? "",
        date_of_birth:       profile.date_of_birth ?? "",
        nationality:         profile.nationality   ?? "",
        passport_number:     profile.passport_number ?? "",
        phone_country_code:  matched ? matched.dial : "+1",
        phone_number:        matched ? raw.slice(matched.dial.length).trimStart() : raw,
        meal_preference:     profile.meal_preference ?? "",
        seat_preference:     profile.seat_preference ?? "",
      });
      if (matched) setCcQuery(matched.dial);
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
        phone_number:    form.phone_number
          ? `${form.phone_country_code} ${form.phone_number}`
          : undefined,
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
      setNatQuery("");
      setCcQuery("");
    },
  });

  const { data: consents = [] } = useQuery<GDPRConsent[]>({
    queryKey: ["gdpr-consents"],
    queryFn: async () => {
      const { data } = await (passengerClient as any).GET("/api/v1/passengers/consent", {});
      return (data as GDPRConsent[]) ?? [];
    },
  });

  const setConsent = useMutation({
    mutationFn: async ({ purpose, granted }: { purpose: string; granted: boolean }) => {
      await (passengerClient as any).POST("/api/v1/passengers/consent", {
        body: { purpose, granted },
      });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["gdpr-consents"] }),
  });

  const deleteAccount = useMutation({
    mutationFn: async () => {
      await (passengerClient as any).DELETE("/api/v1/passengers/profile", {});
    },
    onSuccess: () => {
      logout();
      navigate("/login");
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
                <div className="relative">
                  <input
                    type="text"
                    value={natQuery || form.nationality}
                    placeholder="Search nationality…"
                    onChange={(e) => {
                      setNatQuery(e.target.value);
                      setForm(f => ({ ...f, nationality: "" }));
                      setNatOpen(true);
                    }}
                    onFocus={() => { setNatQuery(""); setNatOpen(true); }}
                    onBlur={() => setTimeout(() => setNatOpen(false), 150)}
                    className={INPUT}
                  />
                  {natOpen && filteredNationalities.length > 0 && (
                    <ul className="absolute z-50 mt-1 max-h-48 w-full overflow-y-auto rounded-lg border border-gray-200 bg-white shadow-lg text-sm">
                      {filteredNationalities.map((n) => (
                        <li key={n}
                          onMouseDown={() => {
                            setForm(f => ({ ...f, nationality: n }));
                            setNatQuery(n);
                            setNatOpen(false);
                          }}
                          className="cursor-pointer px-3 py-2 hover:bg-blue-50 text-gray-700">{n}</li>
                      ))}
                    </ul>
                  )}
                </div>
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
                <div className="flex gap-2">
                  <div className="relative w-32 shrink-0">
                    <input
                      type="text"
                      value={ccQuery || form.phone_country_code}
                      placeholder="Code…"
                      onChange={(e) => {
                        setCcQuery(e.target.value);
                        setForm(f => ({ ...f, phone_country_code: "" }));
                        setCcOpen(true);
                      }}
                      onFocus={() => { setCcQuery(""); setCcOpen(true); }}
                      onBlur={() => setTimeout(() => setCcOpen(false), 150)}
                      className={INPUT}
                    />
                    {ccOpen && filteredCountryCodes.length > 0 && (
                      <ul className="absolute z-50 mt-1 max-h-48 w-64 overflow-y-auto rounded-lg border border-gray-200 bg-white shadow-lg text-sm">
                        {filteredCountryCodes.map((cc) => (
                          <li key={cc.dial}
                            onMouseDown={() => {
                              setForm(f => ({ ...f, phone_country_code: cc.dial }));
                              setCcQuery(cc.dial);
                              setCcOpen(false);
                            }}
                            className="cursor-pointer px-3 py-2 hover:bg-blue-50 text-gray-700">{cc.label}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                  <input
                    type="tel"
                    value={form.phone_number}
                    onChange={(e) => setForm(f => ({ ...f, phone_number: e.target.value }))}
                    className={`flex-1 ${INPUT}`}
                    placeholder="555 0000"
                  />
                </div>
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
              <button onClick={() => { setEditing(false); setNatQuery(""); setCcQuery(""); }}
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

      {/* Privacy & Consent */}
      <div className="rounded-2xl bg-white border border-gray-100 shadow-sm p-6">
        <div className="mb-5">
          <h3 className="font-bold text-gray-900">Privacy & Consent</h3>
          <p className="text-xs text-gray-400 mt-0.5">Manage how AeroLink uses your data. Changes take effect immediately.</p>
        </div>
        <div className="space-y-4">
          {CONSENT_PURPOSES.map(({ key, label, desc }) => {
            const consent = consents.find((c) => c.purpose === key);
            const isGranted = consent?.granted ?? false;
            return (
              <div key={key} className="flex items-start justify-between gap-4">
                <div className="flex-1">
                  <p className="text-sm font-semibold text-gray-800">{label}</p>
                  <p className="text-xs text-gray-400 mt-0.5">{desc}</p>
                </div>
                <button
                  onClick={() => setConsent.mutate({ purpose: key, granted: !isGranted })}
                  disabled={setConsent.isPending}
                  className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none disabled:opacity-50 ${
                    isGranted ? "bg-blue-600" : "bg-gray-200"
                  }`}
                >
                  <span className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 ${
                    isGranted ? "translate-x-5" : "translate-x-0"
                  }`} />
                </button>
              </div>
            );
          })}
        </div>
      </div>

      {/* Danger Zone */}
      <div className="rounded-2xl bg-white border border-red-100 shadow-sm p-6">
        <div className="mb-4">
          <h3 className="font-bold text-red-600">Danger Zone</h3>
          <p className="text-xs text-gray-400 mt-0.5">
            Deleting your account removes all personal data (GDPR Article 17). Bookings are anonymised. This cannot be undone.
          </p>
        </div>
        <button
          onClick={() => setShowDeleteModal(true)}
          className="rounded-lg border border-red-200 bg-white px-4 py-2 text-sm font-semibold text-red-600 hover:bg-red-50 transition-colors"
        >
          Delete My Account
        </button>
      </div>

      {/* Delete confirmation modal */}
      {showDeleteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
            <h3 className="text-lg font-bold text-gray-900">Delete your account?</h3>
            <p className="mt-2 text-sm text-gray-500">
              This will permanently delete your passenger profile and anonymise all associated bookings and notifications. You will be logged out immediately.
            </p>
            <p className="mt-4 text-sm text-gray-700 font-medium">
              Type <span className="font-mono font-bold text-red-600">DELETE</span> to confirm:
            </p>
            <input
              value={deleteConfirm}
              onChange={(e) => setDeleteConfirm(e.target.value)}
              placeholder="DELETE"
              className="mt-2 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono focus:border-red-400 focus:outline-none focus:ring-1 focus:ring-red-400"
            />
            {deleteAccount.isError && (
              <p className="mt-2 text-xs text-red-500">
                {deleteAccount.error instanceof Error ? deleteAccount.error.message : "Deletion failed"}
              </p>
            )}
            <div className="mt-4 flex gap-3">
              <button
                onClick={() => { setShowDeleteModal(false); setDeleteConfirm(""); }}
                className="flex-1 rounded-lg border border-gray-200 py-2 text-sm font-medium hover:bg-gray-50 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => deleteAccount.mutate()}
                disabled={deleteConfirm !== "DELETE" || deleteAccount.isPending}
                className="flex-1 rounded-lg bg-red-600 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50 transition-colors"
              >
                {deleteAccount.isPending ? "Deleting…" : "Delete Account"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
