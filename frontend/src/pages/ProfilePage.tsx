import { useAuth } from "../contexts/AuthContext";

const ROLE_LABEL: Record<string, string> = {
  passenger:        "Passenger",
  admin:            "Administrator",
  "airline-staff":  "Airline Staff",
  "airport-operator": "Airport Operator",
  "partner-api":    "Partner API",
};

export function ProfilePage() {
  const { user } = useAuth();

  if (!user) return null;

  const fields = [
    { label: "Full name",  value: user.full_name  },
    { label: "Username",   value: user.username   },
    { label: "Email",      value: user.email      },
    { label: "Role",       value: ROLE_LABEL[user.role] ?? user.role },
    { label: "User ID",    value: user.id         },
  ];

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-gray-900">Profile</h2>

      <div className="max-w-lg rounded-xl bg-white p-6 shadow-sm border border-gray-100">
        <div className="mb-6 flex items-center gap-4">
          <div className="flex h-14 w-14 items-center justify-center rounded-full bg-blue-600 text-xl font-bold text-white">
            {user.full_name.charAt(0).toUpperCase()}
          </div>
          <div>
            <p className="font-semibold text-gray-900">{user.full_name}</p>
            <p className="text-sm text-gray-500">{ROLE_LABEL[user.role] ?? user.role}</p>
          </div>
        </div>

        <dl className="space-y-3 divide-y divide-gray-50">
          {fields.map(({ label, value }) => (
            <div key={label} className="flex justify-between pt-3 text-sm">
              <dt className="text-gray-500">{label}</dt>
              <dd className="font-medium text-gray-900 text-right break-all max-w-xs">{value}</dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
}
