import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getBookings, getCalendarStats, getBookingLinks, getCalendlySyncStatus,
  createBookingLink, deleteBookingLink, cancelBooking, clearBookingHistory,
  deleteHistoryItem, getAvailability, setAvailability,
  apiKeys, getCreatorId,
} from "@/services/api";
import type { CreateBookingLinkData } from "@/services/api";

export function useBookings(creatorId: string = getCreatorId(), upcoming: boolean = false) {
  return useQuery({ queryKey: apiKeys.bookings(creatorId, upcoming), queryFn: () => getBookings(creatorId, upcoming), staleTime: 30000, refetchInterval: 30000, refetchIntervalInBackground: false });
}

export function useCalendarStats(creatorId: string = getCreatorId()) {
  return useQuery({ queryKey: apiKeys.calendarStats(creatorId), queryFn: () => getCalendarStats(creatorId), staleTime: 60000 });
}

export function useBookingLinks(creatorId: string = getCreatorId()) {
  return useQuery({ queryKey: apiKeys.bookingLinks(creatorId), queryFn: () => getBookingLinks(creatorId), staleTime: 300000 });
}

export function useCalendlySyncStatus(creatorId: string = getCreatorId()) {
  return useQuery({ queryKey: ["calendly-sync-status", creatorId], queryFn: () => getCalendlySyncStatus(creatorId), staleTime: 60000 });
}

export function useCreateBookingLink(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateBookingLinkData) => createBookingLink(creatorId, data),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: apiKeys.bookingLinks(creatorId) }); queryClient.invalidateQueries({ queryKey: apiKeys.calendarStats(creatorId) }); },
  });
}

export function useDeleteBookingLink(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (linkId: string) => deleteBookingLink(creatorId, linkId),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: apiKeys.bookingLinks(creatorId) }); },
  });
}

export function useCancelBooking(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (bookingId: string) => cancelBooking(creatorId, bookingId),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: apiKeys.bookings(creatorId, true) }); queryClient.invalidateQueries({ queryKey: apiKeys.calendarStats(creatorId) }); },
  });
}

export function useClearBookingHistory(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => clearBookingHistory(creatorId),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: apiKeys.bookings(creatorId, true) }); queryClient.invalidateQueries({ queryKey: apiKeys.calendarStats(creatorId) }); },
  });
}

export function useDeleteHistoryItem(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (bookingId: string) => deleteHistoryItem(creatorId, bookingId),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: apiKeys.bookings(creatorId, true) }); queryClient.invalidateQueries({ queryKey: apiKeys.calendarStats(creatorId) }); },
  });
}

export function useAvailability(creatorId: string = getCreatorId()) {
  return useQuery({ queryKey: ["availability", creatorId] as const, queryFn: () => getAvailability(creatorId), staleTime: 60000 });
}

export function useSetAvailability(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (days: Array<{ day_of_week: number; start_time: string; end_time: string; is_active: boolean }>) => setAvailability(creatorId, days),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["availability", creatorId] }); },
  });
}
