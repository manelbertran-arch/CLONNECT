import { apiFetch, CREATOR_ID } from "./client";
import type { RevenueStatsResponse, PurchasesResponse } from "./client";

export interface RecordPurchaseData {
  product_name: string;
  amount: number;
  currency: string;
  platform: string;
  status?: string;
  bot_attributed?: boolean;
  follower_id?: string;
}

export async function getRevenueStats(creatorId: string = CREATOR_ID, days: number = 30): Promise<RevenueStatsResponse> {
  return apiFetch(`/payments/${creatorId}/revenue?days=${days}`);
}

export async function getPurchases(creatorId: string = CREATOR_ID, limit: number = 100, status?: string): Promise<PurchasesResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (status) params.append("status", status);
  return apiFetch(`/payments/${creatorId}/purchases?${params}`);
}

export async function recordPurchase(creatorId: string = CREATOR_ID, data: RecordPurchaseData): Promise<{ status: string; message: string }> {
  return apiFetch(`/payments/${creatorId}/purchases`, { method: "POST", body: JSON.stringify(data) });
}
