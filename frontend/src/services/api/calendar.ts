import { apiFetch, CREATOR_ID } from "./client";
import type { BookingsResponse, CalendarStatsResponse, BookingLinksResponse } from "./client";

export interface CalendlySyncStatus {
  status: string;
  calendly_connected: boolean;
  has_refresh_token: boolean;
  token_expires_at: string | null;
  bookings_synced: number;
  auto_refresh_enabled: boolean;
}

export interface CreateBookingLinkData {
  meeting_type: string;
  title: string;
  url?: string;
  platform: string;
  duration_minutes: number;
  description?: string;
}

export interface DayAvailability {
  day_of_week: number;
  day_name?: string;
  start_time: string;
  end_time: string;
  is_active: boolean;
}

export interface AvailabilityResponse {
  status: string;
  creator_id: string;
  availability: DayAvailability[];
}

export async function getBookings(creatorId: string = CREATOR_ID, upcoming: boolean = false): Promise<BookingsResponse> {
  return apiFetch(`/calendar/${creatorId}/bookings?upcoming=${upcoming}`);
}

export async function getCalendarStats(creatorId: string = CREATOR_ID, days: number = 30): Promise<CalendarStatsResponse> {
  return apiFetch(`/calendar/${creatorId}/stats?days=${days}`);
}

export async function getBookingLinks(creatorId: string = CREATOR_ID): Promise<BookingLinksResponse> {
  return apiFetch(`/calendar/${creatorId}/links`);
}

export async function getCalendlySyncStatus(creatorId: string = CREATOR_ID): Promise<CalendlySyncStatus> {
  return apiFetch(`/calendar/${creatorId}/sync/status`);
}

export async function createBookingLink(creatorId: string = CREATOR_ID, data: CreateBookingLinkData): Promise<{ status: string; link: any }> {
  return apiFetch(`/calendar/${creatorId}/links`, { method: "POST", body: JSON.stringify(data) });
}

export async function deleteBookingLink(creatorId: string = CREATOR_ID, linkId: string): Promise<{ status: string }> {
  return apiFetch(`/calendar/${creatorId}/links/${linkId}`, { method: "DELETE" });
}

export async function cancelBooking(creatorId: string = CREATOR_ID, bookingId: string): Promise<{ status: string; message: string }> {
  return apiFetch(`/calendar/${creatorId}/bookings/${bookingId}`, { method: "DELETE" });
}

export async function clearBookingHistory(creatorId: string = CREATOR_ID): Promise<{ status: string; message: string; deleted_count: number }> {
  return apiFetch(`/calendar/${creatorId}/history`, { method: "DELETE" });
}

export async function deleteHistoryItem(creatorId: string = CREATOR_ID, bookingId: string): Promise<{ status: string; message: string }> {
  return apiFetch(`/calendar/${creatorId}/history/${bookingId}`, { method: "DELETE" });
}

export async function getAvailability(creatorId: string = CREATOR_ID): Promise<AvailabilityResponse> {
  return apiFetch(`/booking/availability/${creatorId}`);
}

export async function setAvailability(creatorId: string = CREATOR_ID, days: DayAvailability[]): Promise<{ status: string; message: string; days_set: number }> {
  return apiFetch(`/booking/availability/${creatorId}`, { method: "POST", body: JSON.stringify(days) });
}
