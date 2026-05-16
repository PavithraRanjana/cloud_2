import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { notificationClient } from "../api/client";

interface Notification {
  id: string;
  recipient_email: string;
  recipient_name: string;
  notification_type: string;
  subject: string;
  body: string;
  event_type: string;
  status: string;
  is_read: boolean;
  created_at: string;
}

const EVENT_STYLE: Record<string, { icon: string; colour: string }> = {
  BookingCreated:    { icon: "🎫", colour: "bg-blue-50    border-blue-200    text-blue-700"    },
  PaymentCompleted:  { icon: "💳", colour: "bg-emerald-50 border-emerald-200 text-emerald-700" },
  CheckInCompleted:  { icon: "✅", colour: "bg-sky-50     border-sky-200     text-sky-700"     },
  BaggageRegistered: { icon: "🧳", colour: "bg-amber-50   border-amber-200   text-amber-700"   },
  BaggageStatusChanged: { icon: "🧳", colour: "bg-amber-50 border-amber-200 text-amber-700"   },
  BookingCancelled:  { icon: "❌", colour: "bg-red-50     border-red-200     text-red-700"     },
  PaymentRefunded:   { icon: "↩️", colour: "bg-orange-50  border-orange-200  text-orange-700"  },
  FlightUpdated:     { icon: "✈",  colour: "bg-violet-50  border-violet-200  text-violet-700"  },
};

function timeAgo(iso: string) {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60)   return "Just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function NotificationsPage() {
  const qc = useQueryClient();

  const { data: notifications = [], isLoading, isError } = useQuery<Notification[]>({
    queryKey: ["notifications"],
    queryFn: async () => {
      const { data, error } = await notificationClient.GET("/api/v1/notifications", {});
      if (error) throw new Error("Failed to load notifications");
      return (data as Notification[]) ?? [];
    },
    refetchInterval: 30_000,
  });

  const markRead = useMutation({
    mutationFn: async (id: string) => {
      await (notificationClient as any).PATCH(`/api/v1/notifications/${id}/read`, {});
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });

  const markAllRead = useMutation({
    mutationFn: async () => {
      const unread = notifications.filter((n) => !n.is_read);
      await Promise.all(
        unread.map((n) =>
          (notificationClient as any).PATCH(`/api/v1/notifications/${n.id}/read`, {})
        )
      );
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });

  const unreadCount = notifications.filter((n) => !n.is_read).length;

  return (
    <div className="space-y-6 max-w-2xl">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Notifications</h2>
          {unreadCount > 0 && (
            <p className="mt-1 text-sm text-gray-500">{unreadCount} unread</p>
          )}
        </div>
        {unreadCount > 0 && (
          <button
            onClick={() => markAllRead.mutate()}
            disabled={markAllRead.isPending}
            className="rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50 transition-colors"
          >
            Mark all as read
          </button>
        )}
      </div>

      {isLoading && <p className="text-sm text-gray-400 animate-pulse">Loading notifications…</p>}
      {isError   && <p className="text-sm text-red-500">Failed to load notifications. Please refresh.</p>}

      {!isLoading && !isError && notifications.length === 0 && (
        <div className="rounded-2xl border border-dashed border-gray-200 bg-white px-8 py-14 text-center">
          <div className="text-4xl mb-3">🔔</div>
          <p className="font-semibold text-gray-500">No notifications yet</p>
          <p className="mt-1 text-sm text-gray-400">Updates about your bookings and flights will appear here.</p>
        </div>
      )}

      <div className="space-y-2">
        {notifications.map((n) => {
          const { icon, colour } = EVENT_STYLE[n.event_type] ?? { icon: "🔔", colour: "bg-gray-50 border-gray-200 text-gray-600" };
          return (
            <div
              key={n.id}
              onClick={() => { if (!n.is_read) markRead.mutate(n.id); }}
              className={`rounded-2xl border p-4 transition-all cursor-pointer ${
                n.is_read
                  ? "bg-white border-gray-100 hover:border-gray-200"
                  : "bg-white border-blue-100 shadow-sm hover:border-blue-200"
              }`}
            >
              <div className="flex items-start gap-3">
                {/* Event type badge */}
                <span className={`inline-flex items-center justify-center w-9 h-9 rounded-full border text-base shrink-0 ${colour}`}>
                  {icon}
                </span>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <p className={`text-sm font-semibold ${n.is_read ? "text-gray-700" : "text-gray-900"}`}>
                      {n.subject}
                    </p>
                    <div className="flex items-center gap-2 shrink-0">
                      {!n.is_read && (
                        <span className="w-2 h-2 rounded-full bg-blue-500 shrink-0" />
                      )}
                      <span className="text-xs text-gray-400">{timeAgo(n.created_at)}</span>
                    </div>
                  </div>
                  <p className="mt-1 text-xs text-gray-500 whitespace-pre-line line-clamp-3">{n.body}</p>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
