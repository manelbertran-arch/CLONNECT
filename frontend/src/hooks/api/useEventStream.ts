import { useEffect, useRef, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { apiKeys, getCreatorId, API_URL, getAuthToken } from "@/services/api";

/**
 * SSE hook for real-time updates from the backend.
 * Connects to /events/{creatorId} and invalidates React Query caches
 * when new messages arrive via Instagram webhooks.
 *
 * Includes a polling fallback that activates when SSE is unhealthy
 * (disconnected or no events received within the health threshold).
 */

const POLL_INTERVAL_MS = 10_000; // 10s polling when SSE is unhealthy
const SSE_HEALTH_THRESHOLD_MS = 45_000; // SSE unhealthy if no event (incl. pings) in 45s
const SSE_RECONNECT_MS = 5_000; // Reconnect delay after SSE error

export function useEventStream(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lastEventTimeRef = useRef<number>(0);
  const sseConnectedRef = useRef<boolean>(false);

  const invalidateAll = useCallback(
    (followerId?: string) => {
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
    },
    [creatorId, queryClient],
  );

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

      es.onopen = () => {
        sseConnectedRef.current = true;
        lastEventTimeRef.current = Date.now();
      };

      es.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          // Update health timer on ANY event (including pings)
          lastEventTimeRef.current = Date.now();

          if (data.type === "ping") return;

          if (data.type === "new_message") {
            invalidateAll(data.data?.follower_id);
          }

          if (data.type === "new_conversation") {
            queryClient.invalidateQueries({
              queryKey: apiKeys.conversations(creatorId),
            });
          }

          if (data.type === "message_approved") {
            invalidateAll(data.data?.follower_id);
          }
        } catch {
          // Ignore parse errors from keepalive pings
        }
      };

      es.onerror = () => {
        sseConnectedRef.current = false;
        es.close();
        // Reconnect after delay
        reconnectTimeoutRef.current = setTimeout(connect, SSE_RECONNECT_MS);
      };
    }

    // Start SSE connection
    connect();

    // Start polling fallback — only invalidates when SSE is unhealthy
    pollingRef.current = setInterval(() => {
      const sseHealthy =
        sseConnectedRef.current &&
        Date.now() - lastEventTimeRef.current < SSE_HEALTH_THRESHOLD_MS;

      if (!sseHealthy) {
        queryClient.invalidateQueries({ queryKey: ['conversations'] });
      }
    }, POLL_INTERVAL_MS);

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
      sseConnectedRef.current = false;
    };
  }, [creatorId, queryClient, invalidateAll]);
}
