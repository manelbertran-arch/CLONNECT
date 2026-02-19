import { useMemo } from "react";
import type { Conversation } from "@/types/api";
import { getPurchaseIntent, detectPlatform, getDisplayName } from "@/types/api";
import {
  LeadDisplay,
  LeadStatus,
  STAGE_SCORING,
  getInitials,
} from "@/components/leads/leadsTypes";

/**
 * Maps a backend conversation to the V3 6-category lead status.
 * Handles all legacy English and Spanish status values.
 */
function getLeadStatus(convo: Conversation): LeadStatus {
  const statusMap: Record<string, LeadStatus> = {
    cliente: "cliente",
    caliente: "caliente",
    colaborador: "colaborador",
    amigo: "amigo",
    nuevo: "nuevo",
    "frío": "frío",
    interesado: "caliente",
    fantasma: "frío",
    new: "nuevo",
    active: "caliente",
    hot: "caliente",
    customer: "cliente",
    ghost: "frío",
  };

  const backendStatus = convo.lead_status || (convo as { status?: string }).status;
  if (backendStatus && statusMap[backendStatus]) return statusMap[backendStatus];
  if (convo.is_customer) return "cliente";

  const intent = getPurchaseIntent(convo);
  if (intent >= 0.5) return "caliente";
  if (intent >= 0.2) return "amigo";
  return "nuevo";
}

/**
 * Converts raw API conversations + optimistic leads into the LeadDisplay array,
 * applying local status overrides for optimistic drag-and-drop.
 */
export function useLeadsData(
  conversations: Conversation[] | undefined,
  optimisticLeads: LeadDisplay[],
  localStatusOverrides: Record<string, LeadStatus>,
  hiddenIds: Set<string>,
  activeFilter: LeadStatus | null
): { leads: LeadDisplay[]; filteredLeads: LeadDisplay[] } {
  const leads = useMemo(() => {
    const allConversations = conversations || [];
    if (!allConversations.length && !optimisticLeads.length) return [];

    const realLeads = allConversations.map((convo): LeadDisplay => {
      const platform = convo.platform || detectPlatform(convo.follower_id);
      const displayName = getDisplayName(convo);
      const intent = getPurchaseIntent(convo);
      const leadId = convo.id || convo.follower_id;
      const status = localStatusOverrides[leadId] || getLeadStatus(convo);
      const score = STAGE_SCORING[status];
      const intentScore = convo.purchase_intent_score ?? Math.round(intent * 100);
      const rawUsername = convo.username || convo.follower_id;
      const instagramUsername = rawUsername.replace(/^ig_/, "").replace(/^@/, "");

      return {
        id: leadId,
        name: convo.name || "",
        username: displayName,
        instagramUsername,
        score,
        intentScore,
        value: 0,
        status,
        avatar: getInitials(convo.name, convo.username, convo.follower_id),
        profilePicUrl: convo.profile_pic_url || "",
        platform,
        email: convo.email || "",
        phone: convo.phone || "",
        notes: convo.notes || "",
        lastContact: convo.last_contact || "",
        totalMessages: convo.total_messages || 0,
        followerId: convo.follower_id,
        lastMessage: convo.last_message_preview || "",
        relationshipType: convo.relationship_type || "nuevo",
      };
    });

    const realIds = new Set(realLeads.map((l) => l.name.toLowerCase()));
    const uniqueOptimistic = optimisticLeads.filter(
      (ol) => !realIds.has(ol.name.toLowerCase())
    );
    return [...uniqueOptimistic, ...realLeads];
  }, [conversations, localStatusOverrides, optimisticLeads]);

  const filteredLeads = useMemo(() => {
    const visible = leads.filter((l) => !hiddenIds.has(l.id));
    if (!activeFilter) return visible;
    return visible.filter((l) => l.status === activeFilter);
  }, [leads, activeFilter, hiddenIds]);

  return { leads, filteredLeads };
}
