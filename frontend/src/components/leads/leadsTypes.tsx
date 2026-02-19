import { Instagram, Send, MessageCircle } from "lucide-react";

// V3 — 6 Category System
export type LeadStatus = "cliente" | "caliente" | "colaborador" | "amigo" | "nuevo" | "frío";

// Scoring per pipeline stage
export const STAGE_SCORING: Record<LeadStatus, number> = {
  "frío": 0,
  nuevo: 20,
  amigo: 40,
  colaborador: 60,
  caliente: 80,
  cliente: 100,
};

// Colors for each status
export const STATUS_COLORS: Record<LeadStatus, string> = {
  "frío": "text-cyan-500",
  nuevo: "text-gray-400",
  amigo: "text-blue-500",
  colaborador: "text-amber-500",
  caliente: "text-red-500",
  cliente: "text-green-500",
};

export const COLUMN_EMOJI: Record<LeadStatus, string> = {
  nuevo: "\u{1F195}",
  amigo: "\u{1F499}",
  colaborador: "\u{1F91D}",
  caliente: "\u{1F525}",
  cliente: "\u2705",
  "frío": "\u2744\uFE0F",
};

export const COLUMN_BG: Record<LeadStatus, string> = {
  nuevo: "border-gray-400/50 bg-gray-400/10",
  amigo: "border-blue-500/50 bg-blue-500/10",
  colaborador: "border-amber-500/50 bg-amber-500/10",
  caliente: "border-red-500/50 bg-red-500/10",
  cliente: "border-green-500/50 bg-green-500/10",
  "frío": "border-cyan-500/50 bg-cyan-500/10",
};

export const STATUS_DOT: Record<LeadStatus, string> = {
  nuevo: "bg-gray-400",
  amigo: "bg-blue-500",
  colaborador: "bg-amber-500",
  caliente: "bg-red-500",
  cliente: "bg-green-500",
  "frío": "bg-cyan-500",
};

// Simplified column config for summary cards (icon displayed via COLUMN_EMOJI)
export const columns: { status: LeadStatus; title: string; color: string }[] = [
  { status: "nuevo", title: "Nuevos", color: "text-gray-400" },
  { status: "amigo", title: "Amigos", color: "text-blue-500" },
  { status: "colaborador", title: "Colaboradores", color: "text-amber-500" },
  { status: "caliente", title: "Calientes", color: "text-red-500" },
  { status: "cliente", title: "Clientes", color: "text-green-500" },
  { status: "frío", title: "Fríos", color: "text-cyan-500" },
];

export const platformIcons: Record<string, React.ReactNode> = {
  instagram: <Instagram className="w-3 h-3" />,
  telegram: <Send className="w-3 h-3" />,
  whatsapp: <MessageCircle className="w-3 h-3" />,
};

export const avatarGradients: Record<string, string> = {
  instagram: "from-violet-600 to-purple-600",
  whatsapp: "from-emerald-500 to-green-600",
  telegram: "from-sky-400 to-blue-500",
};

export interface LeadDisplay {
  id: string;
  name: string;
  username: string;
  instagramUsername: string;
  score: number;
  intentScore: number;
  value: number;
  status: LeadStatus;
  avatar: string;
  profilePicUrl: string;
  platform: string;
  email: string;
  phone: string;
  notes: string;
  lastContact: string;
  totalMessages: number;
  followerId: string;
  lastMessage: string;
  relationshipType: string;
}

// Mapeo de status UI a status backend (V3)
export const statusToBackend: Record<LeadStatus, string> = {
  cliente: "cliente",
  caliente: "caliente",
  colaborador: "colaborador",
  amigo: "amigo",
  nuevo: "nuevo",
  "frío": "frío",
};

export function getInitials(name?: string, username?: string, id?: string): string {
  if (name && name.trim()) {
    return name.split(" ").map((n) => n[0]).join("").slice(0, 2).toUpperCase();
  }
  if (username && username.trim()) {
    return username.slice(0, 2).toUpperCase();
  }
  if (id) {
    if (id.startsWith("tg_")) return "TG";
    if (id.startsWith("ig_")) return "IG";
    if (id.startsWith("wa_")) return "WA";
    return id.slice(0, 2).toUpperCase();
  }
  return "??";
}

export function formatTimeAgo(dateStr?: string): string {
  if (!dateStr) return "";
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 60) return `${diffMins}m`;
  if (diffHours < 24) return `${diffHours}h`;
  if (diffDays < 7) return `${diffDays}d`;
  return `${Math.floor(diffDays / 7)}sem`;
}
