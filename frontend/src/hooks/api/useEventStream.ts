import { useEffect, useRef, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { apiKeys, getCreatorId, API_URL, getAuthToken } from "@/services/api";

/**
 * SSE hook for real-time updates from the backend.
 * Connects to /events/{creatorId} and invalidates React Query caches
 * when new messages arrive via webhooks.
 *
 * Polling fallback activates when SSE is unhealthy (disconnected or no
 * events received within the health threshold).
 */

const POLL_INTERVAL_MS = 5_000;          // 5s polling when SSE is unhealthy
const SSE_HEALTH_THRESHOLD_MS = 30_000;  // SSE unhealthy if no event in 30s (ping every 20s)
const SSE_RECONNECT_MS = 3_000;          // Reconnect delay after SSE error

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
        queryClient.invalidateQueries({
          queryKey: apiKeys.copilotPendingForLead(creatorId, followerId),
        });
      }
      queryClient.invalidateQueries({ queryKey: apiKeys.conversations(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.copilotPending(creatorId) });
    },
    [creatorId, queryClient],
  );

  useEffect(() => {
    if (!creatorId) return;

    function connect() {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }

      const token = getAuthToken();
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
          lastEventTimeRef.current = Date.now();

          if (data.type === "ping") return;

          if (data.type === "new_message" || data.type === "message_approved" || data.type === "message_deleted") {
            invalidateAll(data.data?.follower_id);
          }

          if (data.type === "new_conversation") {
            queryClient.invalidateQueries({ queryKey: apiKeys.conversations(creatorId) });
          }

          if (data.type === "new_pending_response") {
            const fid = data.data?.follower_id || data.data?.lead_id;
            if (fid) {
              queryClient.invalidateQueries({ queryKey: apiKeys.copilotPendingForLead(creatorId, fid) });
            }
            queryClient.invalidateQueries({ queryKey: apiKeys.copilotPending(creatorId) });
          }
        } catch {
          // Ignore parse errors
        }
      };

      es.onerror = () => {
        sseConnectedRef.current = false;
        es.close();
        reconnectTimeoutRef.current = setTimeout(connect, SSE_RECONNECT_MS);
      };
    }

    connect();

    // Polling fallback: fires when SSE is unhealthy, invalidates ALL real-time queries
    pollingRef.current = setInterval(() => {
      const sseHealthy =
        sseConnectedRef.current &&
        Date.now() - lastEventTimeRef.current < SSE_HEALTH_THRESHOLD_MS;

      if (!sseHealthy) {
        queryClient.invalidateQueries({ queryKey: apiKeys.conversations(creatorId) });
        queryClient.invalidateQueries({ queryKey: ["follower", creatorId] });
        queryClient.invalidateQueries({ queryKey: apiKeys.copilotPending(creatorId) });
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
