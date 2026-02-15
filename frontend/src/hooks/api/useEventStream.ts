import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { apiKeys, getCreatorId, API_URL, getAuthToken } from "@/services/api";

/**
 * SSE hook for real-time updates from the backend.
 * Connects to /events/{creatorId} and invalidates React Query caches
 * when new messages arrive via Instagram webhooks.
 */
export function useEventStream(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!creatorId) return;

    function connect() {
      // Close existing connection
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }

      const token = getAuthToken();
      // EventSource doesn't support custom headers, pass token as query param
      const url = `${API_URL}/events/${creatorId}${token ? `?token=${encodeURIComponent(token)}` : ""}`;
      const es = new EventSource(url);
      eventSourceRef.current = es;

      es.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.type === "ping") return;

          if (data.type === "new_message") {
            const followerId = data.data?.follower_id;
            // Invalidate specific conversation
            if (followerId) {
              queryClient.invalidateQueries({
                queryKey: apiKeys.follower(creatorId, followerId),
              });
            }
            // Invalidate conversation list (updates preview, order, unread)
            queryClient.invalidateQueries({
              queryKey: apiKeys.conversations(creatorId),
            });
            // Also invalidate copilot pending (new user message may have pending response)
            queryClient.invalidateQueries({
              queryKey: apiKeys.copilotPending(creatorId),
            });
          }

          if (data.type === "new_conversation") {
            queryClient.invalidateQueries({
              queryKey: apiKeys.conversations(creatorId),
            });
          }

          if (data.type === "message_approved") {
            const followerId = data.data?.follower_id;
            if (followerId) {
              queryClient.invalidateQueries({
                queryKey: apiKeys.follower(creatorId, followerId),
              });
            }
            queryClient.invalidateQueries({
              queryKey: apiKeys.conversations(creatorId),
            });
            queryClient.invalidateQueries({
              queryKey: apiKeys.copilotPending(creatorId),
            });
          }
        } catch {
          // Ignore parse errors from keepalive pings
        }
      };

      es.onerror = () => {
        es.close();
        // Reconnect after 5 seconds
        reconnectTimeoutRef.current = setTimeout(connect, 5000);
      };
    }

    connect();

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
    };
  }, [creatorId, queryClient]);
}
