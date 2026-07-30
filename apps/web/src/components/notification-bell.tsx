"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

/**
 * Extracted from the dashboard so it can live in the global top nav instead
 * of being local to one page -- this also removes the need for the copilot's
 * OPEN_PANEL action to navigate home before it can open the panel.
 */
export function NotificationBell() {
  const queryClient = useQueryClient();
  const [showNotifications, setShowNotifications] = useState(false);
  const notifications = useQuery({ queryKey: ["notifications"], queryFn: api.listNotifications });
  const markRead = useMutation({
    mutationFn: api.markNotificationRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });
  const unread = (notifications.data ?? []).filter((item) => !item.read_at).length;

  useEffect(() => {
    const openPanel = (event: Event) => {
      const panel = (event as CustomEvent<{ panel?: string }>).detail?.panel;
      if (panel === "notifications") setShowNotifications(true);
    };
    window.addEventListener("neurox:open-panel", openPanel);
    return () => window.removeEventListener("neurox:open-panel", openPanel);
  }, []);

  return (
    <div className="relative" data-panel-id="notifications">
      <Button
        type="button"
        variant="icon"
        onClick={() => setShowNotifications((value) => !value)}
        aria-label={`${unread} unread notifications`}
        aria-expanded={showNotifications}
      >
        <Bell className="h-5 w-5" />
        {unread > 0 && (
          <span className="absolute right-1.5 top-1.5 min-w-4 rounded-full bg-rose-600 px-1 text-[10px] font-bold text-white">
            {unread}
          </span>
        )}
      </Button>
      {showNotifications && (
        <Card padding="sm" className="absolute right-0 z-30 mt-3 w-80">
          <h2 className="mb-3 font-bold">Notifications</h2>
          <div className="max-h-80 space-y-2 overflow-y-auto">
            {(notifications.data ?? []).length === 0 && (
              <p className="text-sm text-[var(--color-muted)]">No notifications.</p>
            )}
            {(notifications.data ?? []).map((item) => (
              <button
                key={item.notification_id}
                type="button"
                onClick={() => !item.read_at && markRead.mutate(item.notification_id)}
                className="w-full rounded-xl bg-[var(--color-surface-muted)] p-3 text-left"
              >
                <span className="block text-sm font-bold">{item.title}</span>
                <span className="mt-1 block text-xs text-[var(--color-muted)]">{item.body}</span>
              </button>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
