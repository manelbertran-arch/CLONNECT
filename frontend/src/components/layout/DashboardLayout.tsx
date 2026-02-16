import { useEffect, useRef } from "react";
import { Outlet } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Sidebar } from "./Sidebar";
import { MobileNav } from "./MobileNav";
import {
  apiKeys,
  getCreatorId,
  getDashboardOverview,
  getConversations,
  getProducts,
  getCalendarStats,
  getBookings,
  getCreatorConfig,
  getCopilotStatus,
} from "@/services/api";

export function DashboardLayout() {
  const queryClient = useQueryClient();
  const prefetched = useRef(false);

  // Prefetch ALL page data on mount — eliminates loading spinners on navigation
  useEffect(() => {
    if (prefetched.current) return;
    prefetched.current = true;

    const cid = getCreatorId();
    if (!cid) return;

    const staleTime = 300000; // 5 min

    // Dashboard
    queryClient.prefetchQuery({
      queryKey: apiKeys.dashboard(cid),
      queryFn: () => getDashboardOverview(cid),
      staleTime,
    });

    // Inbox + Leads (shared data)
    queryClient.prefetchInfiniteQuery({
      queryKey: [...apiKeys.conversations(cid), "infinite"],
      queryFn: () => getConversations(cid, 50, 0),
      initialPageParam: 0,
      staleTime,
    });

    // Products
    queryClient.prefetchQuery({
      queryKey: apiKeys.products(cid),
      queryFn: () => getProducts(cid),
      staleTime,
    });

    // Bookings
    queryClient.prefetchQuery({
      queryKey: apiKeys.calendarStats(cid),
      queryFn: () => getCalendarStats(cid),
      staleTime,
    });
    queryClient.prefetchQuery({
      queryKey: apiKeys.bookings(cid, true),
      queryFn: () => getBookings(cid, undefined, true),
      staleTime,
    });

    // Settings
    queryClient.prefetchQuery({
      queryKey: apiKeys.config(cid),
      queryFn: () => getCreatorConfig(cid),
      staleTime,
    });

    // Copilot
    queryClient.prefetchQuery({
      queryKey: apiKeys.copilotStatus(cid),
      queryFn: () => getCopilotStatus(cid),
      staleTime,
    });
  }, [queryClient]);

  return (
    <div className="min-h-screen bg-background">

      {/* Desktop Sidebar - hidden on mobile */}
      <div className="hidden md:block">
        <Sidebar />
      </div>

      {/* Mobile Navigation - visible on mobile only */}
      <MobileNav />

      {/* Main Content - no padding-left on mobile, pl-64 on desktop */}
      <main className="pl-0 md:pl-64 min-h-screen pt-16 md:pt-0">
        <div className="p-4 md:p-8 animate-fade-in">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
