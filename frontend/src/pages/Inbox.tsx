import { useState, useMemo, useEffect, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { Search, Send, MoreHorizontal, Loader2, AlertCircle, Instagram, MessageCircle, Archive, Trash2, AlertTriangle, RotateCcw, ArrowLeft, Bot } from "lucide-react";
import { MessageRenderer, type ChatPlatform } from "@/components/chat/MessageRenderer";
import { AudioRecorder } from "@/components/chat/AudioRecorder";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { cn } from "@/lib/utils";
import { useQueryClient } from "@tanstack/react-query";
import { useConversations, useFollowerDetail, useSendMessage, useArchiveConversation, useMarkConversationSpam, useDeleteConversation, useArchivedConversations, useRestoreConversation, useEventStream, useTrackManualCopilot } from "@/hooks/useApi";
import { getFollowerDetail, apiKeys, getCreatorId, transcribeAudio } from "@/services/api";
import { useToast } from "@/hooks/use-toast";
import type { Conversation, Message } from "@/types/api";
import { getPurchaseIntent, detectPlatform, getFriendlyName, extractNameFromMessages, getMessages } from "@/types/api";
import { RelationshipBadge, RelationshipDot } from "@/components/RelationshipBadge";
import { CopilotBanner } from "@/components/CopilotBanner";

// Brand colors
const BRAND_COLORS = {
  instagram: '#E1306C',
  whatsapp: '#25D366',
  telegram: '#0088cc',
};

const platformIcons: Record<string, React.ReactNode> = {
  instagram: <Instagram className="w-5 h-5" style={{ color: BRAND_COLORS.instagram }} />,
  telegram: <Send className="w-5 h-5" style={{ color: BRAND_COLORS.telegram }} />,
  whatsapp: <MessageCircle className="w-5 h-5" style={{ color: BRAND_COLORS.whatsapp }} />,
};

const avatarGradients: Record<string, string> = {
  instagram: "from-primary/60 to-accent/60",
  whatsapp: "from-emerald-500/60 to-green-600/60",
  telegram: "from-sky-400/60 to-blue-500/60",
};

// WhatsApp-style doodle background pattern (icons: phone, chat, heart, clock, camera, envelope, smiley, music, star, plane, lock, pin, laptop, calendar, globe)
const WA_DOODLE_PATTERN = (() => {
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='250' height='250'><g opacity='0.06' fill='white'><rect x='15' y='12' width='12' height='20' rx='2'/><path d='M62 15h16c2 0 3 1 3 3v10c0 2-1 3-3 3H70l-4 4v-4h-4c-2 0-3-1-3-3V18c0-2 1-3 3-3z'/><path d='M132 20c2-5 10-5 10 1s-10 12-10 12-10-6-10-12 8-6 10-1z'/><circle cx='200' cy='22' r='9'/><rect x='18' y='77' width='18' height='13' rx='2'/><circle cx='27' cy='83' r='4'/><rect x='80' y='75' width='18' height='12' rx='1'/><circle cx='150' cy='82' r='9'/><circle cx='218' cy='86' r='4'/><rect x='222' y='70' width='2' height='16'/><path d='M28 148l4 8 8 1-6 5 1 8-7-4-7 4 1-8-6-5 8-1z'/><path d='M82 140l22 8-22 8 4-8z'/><rect x='148' y='145' width='12' height='10' rx='2'/><path d='M218 140a7 7 0 00-7 7c0 8 7 14 7 14s7-6 7-14a7 7 0 00-7-7z'/><rect x='14' y='212' width='20' height='13' rx='1'/><rect x='80' y='210' width='16' height='14' rx='2'/><circle cx='152' cy='218' r='9'/><path d='M210 225h10v-10l-4-6h-6v12z'/></g></svg>`;
  return `url("data:image/svg+xml,${encodeURIComponent(svg)}")`;
})();

function getInitials(name?: string, username?: string, id?: string): string {
  if (name && name.trim()) {
    return name.split(" ").map(n => n[0]).join("").slice(0, 2).toUpperCase();
  }
  if (username && username.trim()) {
    return username.slice(0, 2).toUpperCase();
  }
  // Use platform prefix for initials if no name/username
  if (id) {
    if (id.startsWith("tg_")) return "TG";
    if (id.startsWith("ig_")) return "IG";
    if (id.startsWith("wa_")) return "WA";
    return id.slice(0, 2).toUpperCase();
  }
  return "??";
}

function formatTimeAgo(timestamp: string | undefined): string {
  if (!timestamp) return "";
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return "now";
  if (diffMins < 60) return `${diffMins}m`;
  if (diffHours < 24) return `${diffHours}h`;
  return `${diffDays}d`;
}

function formatPreview(content?: string, _name?: string): string {
  if (!content) return "";
  const lower = content.toLowerCase().trim();
  if (lower.startsWith("reaccionó ")) return content; // Already formatted by backend
  if (lower === "shared content") return "Compartió contenido";
  if (lower.includes("mentioned you in their story")) return "Te mencionó en su story";
  if (lower === "sent an attachment") return "Envió un archivo";
  if (lower.includes("shared a post")) return "Compartió una publicación";
  if (lower.includes("shared a reel")) return "Compartió un reel";
  if (lower.includes("story reply")) return "Respondió a tu historia";
  return content;
}

// Get smart display name - tries to extract from messages if not available
function getSmartDisplayName(
  convo: Conversation,
  messages: Message[]
): string {
  // First check if we have a name or username
  if (convo.name && convo.name.trim()) return convo.name;
  if (convo.username && convo.username.trim()) return convo.username;

  // Try to extract name from bot responses
  const extractedName = extractNameFromMessages(messages);
  if (extractedName) return extractedName;

  // Fall back to friendly platform name
  return getFriendlyName(convo.follower_id);
}

export default function Inbox() {
  // SSE: real-time updates from backend when new messages arrive
  useEventStream();
  const queryClient = useQueryClient();
  const creatorId = getCreatorId();

  // Prefetch follower detail on hover — loads messages before user clicks
  const handleConversationHover = useCallback((followerId: string) => {
    queryClient.prefetchQuery({
      queryKey: apiKeys.follower(creatorId, followerId),
      queryFn: () => getFollowerDetail(creatorId, followerId),
      staleTime: 300000,
    });
  }, [queryClient, creatorId]);

  // Read conversation ID from URL query param (?id=xxx)
  const [searchParams, setSearchParams] = useSearchParams();
  const urlConversationId = searchParams.get("id");

  // SEQUENTIAL LOADING: Load conversations first, then archived (prevents backend blocking)
  const {
    data,
    isLoading,
    error,
    isSuccess,
  } = useConversations(getCreatorId(), 500);
  const { data: archivedData, isLoading: archivedLoading } = useArchivedConversations(undefined, {
    enabled: isSuccess // Only load AFTER conversations finishes
  });
  const [selectedId, setSelectedId] = useState<string | null>(urlConversationId);

  const [message, setMessage] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [showOnlyLeads, setShowOnlyLeads] = useState(false);
  const [showOnlyPending, setShowOnlyPending] = useState(false);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<"all" | "archived">("all");
  const [platformFilter, setPlatformFilter] = useState<"all" | "instagram" | "whatsapp" | "telegram">("all");
  const { toast } = useToast();
  const sendMessageMutation = useSendMessage();
  const archiveMutation = useArchiveConversation();
  const spamMutation = useMarkConversationSpam();
  const deleteMutation = useDeleteConversation();
  const restoreMutation = useRestoreConversation();
  const trackManualMutation = useTrackManualCopilot();

  // Fetch messages for the selected conversation (auto-refreshes every 5s)
  const { data: followerData, isLoading: messagesLoading } = useFollowerDetail(selectedId);

  // Conversation action handlers
  const handleArchive = async () => {
    if (!selectedId) return;
    try {
      await archiveMutation.mutateAsync(selectedId);
      toast({ title: "Conversation archived" });
      setSelectedId(null);
    } catch {
      toast({ title: "Failed to archive", variant: "destructive" });
    }
  };

  const handleMarkSpam = async () => {
    if (!selectedId) return;
    try {
      await spamMutation.mutateAsync(selectedId);
      toast({ title: "Marked as spam" });
      setSelectedId(null);
    } catch {
      toast({ title: "Failed to mark as spam", variant: "destructive" });
    }
  };

  const handleDelete = async () => {
    if (!selectedId) return;
    try {
      await deleteMutation.mutateAsync(selectedId);
      toast({ title: "Conversation deleted" });
      setSelectedId(null);
      setIsDeleteDialogOpen(false);
    } catch {
      toast({ title: "Failed to delete", variant: "destructive" });
    }
  };

  const handleRestore = async (conversationId: string) => {
    try {
      await restoreMutation.mutateAsync(conversationId);
      toast({ title: "Conversation restored" });
      if (selectedId === conversationId) {
        setSelectedId(null);
      }
    } catch {
      toast({ title: "Failed to restore", variant: "destructive" });
    }
  };

  // Handle sending a manual message
  const handleSend = async () => {
    if (!selectedId || !message.trim()) {
      return;
    }

    try {
      const result = await sendMessageMutation.mutateAsync({
        followerId: selectedId,
        message: message.trim(),
      });

      if (result.sent) {
        toast({
          title: "Message sent",
          description: `Sent via ${result.platform}`,
        });
      } else {
        // Pending delivery is normal - not an error
        toast({
          title: "Enviando...",
          description: "Tu mensaje se está enviando. Esto puede tardar unos segundos.",
        });
      }

      // A2: Auto-discard pending copilot suggestion on manual send (fire-and-forget)
      if (selectedConversation?.id) {
        trackManualMutation.mutate({ leadId: selectedConversation.id, content: message.trim() });
      }

      setMessage(""); // Clear input on success
    } catch (error) {
      toast({
        title: "Error sending message",
        description: error instanceof Error ? error.message : "Failed to send",
        variant: "destructive",
      });
    }
  };

  // Handle sending audio: transcribe then send as text message
  const handleSendAudio = async (blob: Blob) => {
    if (!selectedId) return;
    try {
      const result = await transcribeAudio(blob);
      if (!result.text.trim()) {
        toast({ title: "Audio vacio", description: "No se detecto voz en la grabacion", variant: "destructive" });
        return;
      }
      const audioText = result.text.trim();
      await sendMessageMutation.mutateAsync({
        followerId: selectedId,
        message: audioText,
      });
      toast({ title: "Audio enviado", description: audioText.slice(0, 60) + (audioText.length > 60 ? "..." : "") });
      setMessage("");
    } catch (err) {
      toast({ title: "Error", description: err instanceof Error ? err.message : "No se pudo enviar el audio", variant: "destructive" });
    }
  };

  // Handle enter key to send
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Compute unread counts per platform
  const unreadCounts = useMemo(() => {
    const all = data?.conversations || [];
    const counts = { all: 0, instagram: 0, whatsapp: 0, telegram: 0 };
    for (const c of all) {
      if (c.is_unread) {
        counts.all++;
        const p = c.platform || detectPlatform(c.follower_id);
        if (p === 'instagram') counts.instagram++;
        else if (p === 'whatsapp') counts.whatsapp++;
        else if (p === 'telegram') counts.telegram++;
      }
    }
    return counts;
  }, [data?.conversations]);

  const conversations = useMemo(() => {
    const allConversations = data?.conversations || [];
    const sourceData = activeTab === "archived" ? archivedData : allConversations;
    if (!sourceData) return [];

    let filtered = Array.isArray(sourceData) ? sourceData : [];

    // Platform filter
    if (platformFilter !== "all" && activeTab !== "archived") {
      filtered = filtered.filter(c => {
        const p = c.platform || detectPlatform(c.follower_id);
        return p === platformFilter;
      });
    }

    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(c =>
        c.username?.toLowerCase().includes(query) ||
        c.name?.toLowerCase().includes(query) ||
        c.follower_id.toLowerCase().includes(query)
      );
    }

    // Filter to show only real leads (exclude amigos, fans, colaboradores)
    if (showOnlyLeads) {
      const leadTypes = ['cliente', 'lead_caliente', 'lead_tibio', 'curioso', 'nuevo'];
      filtered = filtered.filter(c => leadTypes.includes(c.relationship_type || 'nuevo'));
    }

    // A5: Filter to show only conversations with pending copilot suggestions
    if (showOnlyPending) {
      filtered = filtered.filter(c => c.has_pending_copilot);
    }

    // Sort by last contact (most recent first)
    return filtered.sort((a, b) =>
      new Date(b.last_contact || 0).getTime() - new Date(a.last_contact || 0).getTime()
    );
  }, [data?.conversations, archivedData, searchQuery, activeTab, showOnlyLeads, showOnlyPending, platformFilter]);

  const archivedCount = archivedData?.length || 0;
  const pendingCopilotCount = useMemo(() => {
    const all = data?.conversations || [];
    return all.filter(c => c.has_pending_copilot).length;
  }, [data?.conversations]);

  // Handle URL query param for direct navigation (from Pipeline)
  useEffect(() => {
    if (urlConversationId && urlConversationId !== selectedId) {
      setSelectedId(urlConversationId);
      // Clear the URL param to keep URL clean
      setSearchParams({}, { replace: true });
    }
  }, [urlConversationId, selectedId, setSearchParams]);

  // Auto-select first conversation if none selected (desktop only)
  useEffect(() => {
    // Skip if we have a URL param (will be handled by above effect)
    if (urlConversationId) return;
    // Only auto-select on desktop (md breakpoint = 768px)
    const isDesktop = window.innerWidth >= 768;
    if (isDesktop && !selectedId && conversations.length > 0) {
      setSelectedId(conversations[0].follower_id);
    }
  }, [conversations, selectedId, urlConversationId]);

  const selectedConversation = useMemo(() => {
    return conversations.find(c => c.follower_id === selectedId) || null;
  }, [selectedId, conversations]);

  // Messages from the follower detail API — separate reactions from regular messages
  const allMessages: Message[] = useMemo(() => getMessages(followerData), [followerData]);

  const { messages, reactionsByMid } = useMemo(() => {
    const reactions = new Map<string, { emoji: string; isOutgoing: boolean }[]>();
    const visible: Message[] = [];
    for (const msg of allMessages) {
      if (msg.metadata?.type === 'reaction' && msg.metadata?.reacted_to_mid) {
        const mid = msg.metadata.reacted_to_mid;
        if (!reactions.has(mid)) reactions.set(mid, []);
        reactions.get(mid)!.push({ emoji: msg.metadata.emoji || '❤️', isOutgoing: msg.role === 'assistant' });
      } else {
        visible.push(msg);
      }
    }
    return { messages: visible, reactionsByMid: reactions };
  }, [allMessages]);

  // Get smart display name for selected conversation
  const displayName = useMemo(() => {
    if (!selectedConversation) return "";
    return getSmartDisplayName(selectedConversation, messages);
  }, [selectedConversation, messages]);

  // Determine platform for chat styling
  const chatPlatform: ChatPlatform = useMemo(() => {
    if (!selectedConversation) return 'instagram';
    const p = selectedConversation.platform || detectPlatform(selectedConversation.follower_id);
    if (p === 'whatsapp' || p === 'telegram') return p;
    return 'instagram';
  }, [selectedConversation]);

  // Loading state — skeleton
  if (isLoading) {
    return (
      <div className="flex h-[80vh]">
        {/* Conversation list skeleton */}
        <div className="w-80 border-r border-border/30 p-3 space-y-1">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="flex items-center gap-3 px-4 py-3 min-h-[72px] rounded-xl">
              <div className="w-14 h-14 rounded-full bg-muted/40 animate-pulse shrink-0" />
              <div className="flex-1 space-y-2">
                <div className="h-4 w-28 rounded bg-muted/40 animate-pulse" />
                <div className="h-3.5 w-40 rounded bg-muted/30 animate-pulse" />
              </div>
            </div>
          ))}
        </div>
        {/* Chat area skeleton */}
        <div className="flex-1 flex flex-col p-6">
          <div className="h-10 w-48 rounded bg-muted/40 animate-pulse mb-6" />
          <div className="flex-1 space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className={`h-10 ${i % 2 ? "w-48 ml-auto" : "w-64"} rounded-lg bg-muted/20 animate-pulse`} />
            ))}
          </div>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <AlertCircle className="w-12 h-12 text-destructive" />
        <p className="text-muted-foreground">Failed to load conversations</p>
        <p className="text-sm text-destructive">{error.message}</p>
      </div>
    );
  }

  // On mobile, when a conversation is selected, show chat view instead of list
  const showMobileChat = selectedId !== null;

  return (
    <div className="h-[calc(100vh-6rem)] md:h-[calc(100vh-8rem)] flex gap-0 md:gap-6">
      {/* Conversation List - hidden on mobile when chat is open */}
      <div className={cn(
        "w-full md:w-80 flex flex-col",
        showMobileChat ? "hidden md:flex" : "flex"
      )}>
        {/* Platform Tabs */}
        <div className="flex items-center gap-1.5 mb-4">
          <div className="flex gap-1 flex-1 overflow-x-auto">
            <button
              onClick={() => { setPlatformFilter("all"); setActiveTab("all"); }}
              className={cn(
                "px-3 py-1.5 rounded-full text-sm font-medium transition-all whitespace-nowrap flex items-center gap-1.5",
                platformFilter === "all" && activeTab !== "archived"
                  ? "bg-white/10 text-white ring-1 ring-white/20"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              Todos
              {unreadCounts.all > 0 && (
                <span className="bg-white/20 text-[11px] px-1.5 py-0.5 rounded-full min-w-[18px] text-center">{unreadCounts.all}</span>
              )}
            </button>
            <button
              onClick={() => { setPlatformFilter("instagram"); setActiveTab("all"); }}
              className={cn(
                "px-3 py-1.5 rounded-full text-sm font-medium transition-all whitespace-nowrap flex items-center gap-1.5",
                platformFilter === "instagram" && activeTab !== "archived"
                  ? "bg-[#E1306C]/20 ring-1 ring-[#E1306C]/30"
                  : "hover:bg-secondary"
              )}
            >
              <Instagram className="w-5 h-5" style={{ color: BRAND_COLORS.instagram }} />
              {unreadCounts.instagram > 0 && (
                <span className="bg-[#E1306C]/30 text-[#E1306C] text-[11px] px-1.5 py-0.5 rounded-full min-w-[18px] text-center">{unreadCounts.instagram}</span>
              )}
            </button>
            <button
              onClick={() => { setPlatformFilter("whatsapp"); setActiveTab("all"); }}
              className={cn(
                "px-3 py-1.5 rounded-full text-sm font-medium transition-all whitespace-nowrap flex items-center gap-1.5",
                platformFilter === "whatsapp" && activeTab !== "archived"
                  ? "bg-[#25D366]/20 ring-1 ring-[#25D366]/30"
                  : "hover:bg-secondary"
              )}
            >
              <MessageCircle className="w-5 h-5" style={{ color: BRAND_COLORS.whatsapp }} />
              {unreadCounts.whatsapp > 0 && (
                <span className="bg-[#25D366]/30 text-[#25D366] text-[11px] px-1.5 py-0.5 rounded-full min-w-[18px] text-center">{unreadCounts.whatsapp}</span>
              )}
            </button>
            <button
              onClick={() => { setPlatformFilter("telegram"); setActiveTab("all"); }}
              className={cn(
                "px-3 py-1.5 rounded-full text-sm font-medium transition-all whitespace-nowrap flex items-center gap-1.5",
                platformFilter === "telegram" && activeTab !== "archived"
                  ? "bg-[#0088cc]/20 ring-1 ring-[#0088cc]/30"
                  : "hover:bg-secondary"
              )}
            >
              <Send className="w-5 h-5" style={{ color: BRAND_COLORS.telegram }} />
              {unreadCounts.telegram > 0 && (
                <span className="bg-[#0088cc]/30 text-[#0088cc] text-[11px] px-1.5 py-0.5 rounded-full min-w-[18px] text-center">{unreadCounts.telegram}</span>
              )}
            </button>
          </div>
          <button
            onClick={() => setActiveTab(activeTab === "archived" ? "all" : "archived")}
            className={cn(
              "p-2 rounded-lg transition-all shrink-0",
              activeTab === "archived"
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:text-foreground hover:bg-secondary"
            )}
            title={activeTab === "archived" ? "Volver a conversaciones" : `Archivadas (${archivedCount})`}
          >
            <Archive className="w-4 h-4" />
          </button>
        </div>

        <div className="mb-4 space-y-2">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              placeholder="Search conversations..."
              className="pl-10 bg-secondary border-0"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowOnlyLeads(!showOnlyLeads)}
              className={cn(
                "text-xs px-3 py-1 rounded-full border transition-colors",
                showOnlyLeads
                  ? "bg-violet-500/20 text-violet-400 border-violet-400/30"
                  : "bg-secondary text-muted-foreground border-border/50 hover:text-foreground"
              )}
            >
              {showOnlyLeads ? "Solo leads" : "Todos"}
            </button>
            {pendingCopilotCount > 0 && (
              <button
                onClick={() => setShowOnlyPending(!showOnlyPending)}
                className={cn(
                  "text-xs px-3 py-1 rounded-full border transition-colors flex items-center gap-1",
                  showOnlyPending
                    ? "bg-violet-500/20 text-violet-400 border-violet-400/30"
                    : "bg-secondary text-muted-foreground border-border/50 hover:text-foreground"
                )}
              >
                <Bot className="w-3 h-3" />
                Pendientes
                <span className="bg-violet-500/30 text-violet-300 text-[10px] px-1.5 py-0.5 rounded-full min-w-[18px] text-center">{pendingCopilotCount}</span>
              </button>
            )}
          </div>
        </div>

        <div className="flex-1 overflow-auto space-y-1">
          {(activeTab === "archived" ? archivedLoading : isLoading) ? (
            <div className="space-y-1 animate-pulse">
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="flex items-center gap-3 px-4 py-3 min-h-[72px] rounded-xl">
                  <div className="w-14 h-14 rounded-full bg-muted/40 shrink-0" />
                  <div className="flex-1 space-y-2">
                    <div className="h-4 w-28 rounded bg-muted/40" />
                    <div className="h-3.5 w-40 rounded bg-muted/30" />
                  </div>
                </div>
              ))}
            </div>
          ) : conversations.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <p>{activeTab === "archived" ? "No archived conversations" : "No conversations yet"}</p>
              <p className="text-sm">{activeTab === "archived" ? "Archived and spam items will appear here" : "Messages will appear here"}</p>
            </div>
          ) : (
            conversations.map((convo) => {
              const listDisplayName = convo.name || convo.username || getFriendlyName(convo.follower_id);
              const initials = getInitials(convo.name, convo.username, convo.follower_id);
              const lastMessage = convo.last_messages?.[convo.last_messages.length - 1];
              const isArchived = activeTab === "archived";
              const convoPlatform = convo.platform || detectPlatform(convo.follower_id);

              return (
                <div
                  key={convo.follower_id}
                  onMouseEnter={() => handleConversationHover(convo.follower_id)}
                  className={cn(
                    "w-full px-4 py-3 min-h-[72px] text-left transition-all hover:bg-secondary rounded-xl",
                    selectedId === convo.follower_id && "bg-secondary"
                  )}
                >
                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => setSelectedId(convo.follower_id)}
                      className="shrink-0"
                    >
                      {convo.profile_pic_url ? (
                        <img
                          src={convo.profile_pic_url}
                          alt={convo.username || ""}
                          className="w-14 h-14 rounded-full object-cover"
                          onError={(e) => {
                            e.currentTarget.style.display = "none";
                            e.currentTarget.nextElementSibling?.classList.remove("hidden");
                          }}
                        />
                      ) : null}
                      <div className={cn(
                        "w-14 h-14 rounded-full bg-gradient-to-br flex items-center justify-center text-sm font-semibold",
                        avatarGradients[convo.platform || detectPlatform(convo.follower_id)] || avatarGradients.instagram,
                        convo.profile_pic_url && "hidden"
                      )}>
                        {initials}
                      </div>
                    </button>
                    <button
                      onClick={() => setSelectedId(convo.follower_id)}
                      className="flex-1 min-w-0 text-left"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-1.5 min-w-0">
                          <RelationshipDot type={convo.relationship_type || convo.status} />
                          <span className={cn("text-[15px] font-semibold truncate", convo.is_unread ? 'text-white' : '')}>{listDisplayName}</span>
                          {convo.is_verified && <span className="text-[#0095F6] text-xs shrink-0">✓</span>}
                        </div>
                        <div className="flex items-center gap-1.5 shrink-0">
                          <span className="text-xs text-muted-foreground">{formatTimeAgo(convo.last_contact)}</span>
                          {convo.has_pending_copilot && <Bot className="w-3.5 h-3.5 text-violet-400" />}
                          {convo.is_unread && <div className="w-2.5 h-2.5 rounded-full bg-[#0095F6]"></div>}
                        </div>
                      </div>
                      <p className={cn("text-sm truncate mt-0.5", convo.is_unread ? 'text-white font-medium' : 'text-zinc-400')}>
                        {convo.last_message_role === 'assistant' ? 'Tú: ' : ''}
                        {formatPreview(convo.last_message_preview || lastMessage?.content, convo.name || convo.username)}
                      </p>
                    </button>
                    {isArchived && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="shrink-0 h-8 w-8"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleRestore(convo.follower_id);
                        }}
                        disabled={restoreMutation.isPending}
                      >
                        {restoreMutation.isPending ? (
                          <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                          <RotateCcw className="w-4 h-4" />
                        )}
                      </Button>
                    )}
                  </div>
                </div>
              );
            })
          )}

        </div>
      </div>

      {/* Chat View - hidden on mobile when no chat selected */}
      <div className={cn(
        "flex-1 flex flex-col rounded-2xl border overflow-hidden",
        showMobileChat ? "flex" : "hidden md:flex",
        chatPlatform === 'whatsapp' ? 'bg-[#0b141a] border-[#2a3942]' :
        chatPlatform === 'telegram' ? 'bg-[#0e1621] border-[#1e2c3a]' :
        'bg-card border-border/50'
      )}>
        {selectedConversation ? (
          <>
            {/* Chat Header */}
            <div className={cn(
              "p-4 border-b flex items-center justify-between",
              chatPlatform === 'whatsapp' ? 'bg-[#202c33] border-[#2a3942]' :
              chatPlatform === 'telegram' ? 'bg-[#17212b] border-[#1e2c3a]' :
              'border-border/50'
            )}>
              <div className="flex items-center gap-3">
                {/* Mobile back button */}
                <Button
                  variant="ghost"
                  size="icon"
                  className="md:hidden shrink-0"
                  onClick={() => setSelectedId(null)}
                >
                  <ArrowLeft className="w-5 h-5" />
                </Button>
                {selectedConversation.profile_pic_url ? (
                  <img
                    src={selectedConversation.profile_pic_url}
                    alt={selectedConversation.username || ""}
                    className="w-10 h-10 rounded-full object-cover"
                    onError={(e) => {
                      e.currentTarget.style.display = "none";
                      e.currentTarget.nextElementSibling?.classList.remove("hidden");
                    }}
                  />
                ) : null}
                <div className={cn(
                  "w-10 h-10 rounded-full bg-gradient-to-br flex items-center justify-center text-sm font-semibold",
                  avatarGradients[selectedConversation.platform || detectPlatform(selectedConversation.follower_id)] || avatarGradients.instagram,
                  selectedConversation.profile_pic_url && "hidden"
                )}>
                  {getInitials(displayName, undefined, selectedConversation.follower_id)}
                </div>
                <div>
                  <p className="font-semibold">
                    {displayName}
                  </p>
                  <div className="text-xs text-muted-foreground flex items-center gap-1">
                    {(selectedConversation.platform || detectPlatform(selectedConversation.follower_id)) === "instagram" ? (
                      <button
                        onClick={() => {
                          const username = (selectedConversation.username || selectedConversation.follower_id).replace(/^@/, "").replace(/^ig_/, "");
                          window.open(`https://instagram.com/${username}`, "_blank");
                        }}
                        className="flex items-center gap-1 hover:text-violet-400 transition-colors"
                        title={`Abrir @${(selectedConversation.username || "").replace(/^@/, "")}`}
                      >
                        <Instagram className="w-3 h-3" />
                        instagram
                      </button>
                    ) : (selectedConversation.platform || detectPlatform(selectedConversation.follower_id)) === "whatsapp" ? (
                      <>
                        {platformIcons.whatsapp}
                        {selectedConversation.phone || (selectedConversation.follower_id.startsWith("wa_") ? "+" + selectedConversation.follower_id.slice(3) : "whatsapp")}
                      </>
                    ) : (
                      <>
                        {platformIcons[selectedConversation.platform || detectPlatform(selectedConversation.follower_id)]}
                        {selectedConversation.platform || detectPlatform(selectedConversation.follower_id)}
                      </>
                    )}
                    <span>•</span>
                    <RelationshipBadge type={(followerData as Conversation)?.relationship_type || selectedConversation?.relationship_type} />
                    <span>• Score: {Math.round(getPurchaseIntent(followerData || selectedConversation) * 100)}%</span>
                  </div>
                </div>
              </div>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon">
                    <MoreHorizontal className="w-5 h-5" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={handleArchive}>
                    <Archive className="w-4 h-4 mr-2" />
                    Archive
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={handleMarkSpam}>
                    <AlertTriangle className="w-4 h-4 mr-2" />
                    Mark as Spam
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    onClick={() => setIsDeleteDialogOpen(true)}
                    className="text-destructive focus:text-destructive"
                  >
                    <Trash2 className="w-4 h-4 mr-2" />
                    Delete
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>

            {/* Messages */}
            <div className={cn(
              "flex-1 overflow-auto p-4",
              chatPlatform === 'whatsapp' ? 'bg-[#0b141a]' :
              chatPlatform === 'telegram' ? 'bg-[#0e1621]' : ''
            )}
            style={chatPlatform === 'whatsapp' ? {
              backgroundImage: WA_DOODLE_PATTERN,
              backgroundSize: '250px 250px',
            } : undefined}>
              {messagesLoading ? (
                <div className="flex-1 space-y-4 py-4 animate-pulse">
                  {Array.from({ length: 6 }).map((_, i) => (
                    <div key={i} className={cn("flex", i % 2 === 0 ? "" : "justify-end")}>
                      <div className={cn(
                        "rounded-2xl bg-muted/20",
                        i % 2 === 0 ? "w-2/3 h-12" : "w-1/2 h-10"
                      )} />
                    </div>
                  ))}
                </div>
              ) : messages.length > 0 ? (
                messages.map((msg, idx) => {
                  const isFirstInGroup = idx === 0 || messages[idx - 1]?.role !== msg.role;
                  return (
                    <div key={idx} style={idx === 0 ? undefined : { marginTop: isFirstInGroup ? 16 : 3 }}>
                      <MessageRenderer
                        message={msg}
                        platform={chatPlatform}
                        isFirstInGroup={isFirstInGroup}
                        isLastInGroup={idx === messages.length - 1 || messages[idx + 1]?.role !== msg.role}
                        reactions={msg.platform_message_id ? reactionsByMid.get(msg.platform_message_id) : undefined}
                      />
                    </div>
                  );
                })
              ) : (
                <div className="text-center py-8 text-muted-foreground">
                  <p>No messages in this conversation</p>
                  <p className="text-sm mt-1">Total messages: {selectedConversation.total_messages || 0}</p>
                </div>
              )}
            </div>

            {/* Copilot Banner — shows pending suggestion inline */}
            <CopilotBanner
              leadId={selectedConversation.id || null}
              platform={chatPlatform}
            />

            {/* Input */}
            <div className={cn(
              "p-4 border-t",
              chatPlatform === 'whatsapp' ? 'bg-[#202c33] border-[#2a3942]' :
              chatPlatform === 'telegram' ? 'bg-[#17212b] border-[#1e2c3a]' :
              'border-border/50'
            )}>
              <div className="flex items-center gap-2">
                <AudioRecorder
                  onTranscription={(text) => setMessage((prev) => prev ? `${prev} ${text}` : text)}
                  onSendAudio={handleSendAudio}
                  disabled={sendMessageMutation.isPending}
                />
                <Input
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={
                    chatPlatform === 'whatsapp' ? 'Escribe un mensaje...' :
                    chatPlatform === 'telegram' ? 'Escribe un mensaje...' :
                    'Type a message...'
                  }
                  className={cn(
                    "flex-1 border-0",
                    chatPlatform === 'whatsapp' ? 'bg-[#2a3942] text-[#e9edef] placeholder:text-[#8696a0]' :
                    chatPlatform === 'telegram' ? 'bg-[#17212b] text-white placeholder:text-[#6c7883]' :
                    'bg-secondary'
                  )}
                  disabled={sendMessageMutation.isPending}
                />
                <Button
                  type="button"
                  onClick={handleSend}
                  disabled={!selectedId || !message.trim() || sendMessageMutation.isPending}
                  className={cn(
                    "hover:opacity-90 transition-opacity shrink-0",
                    chatPlatform === 'whatsapp' ? 'bg-[#00a884] hover:bg-[#00a884]' :
                    chatPlatform === 'telegram' ? 'bg-[#3390ec] hover:bg-[#3390ec]' :
                    'bg-gradient-to-r from-primary to-accent'
                  )}
                >
                  {sendMessageMutation.isPending ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Send className="w-4 h-4" />
                  )}
                </Button>
              </div>
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center text-muted-foreground">
            <p>Select a conversation to view messages</p>
          </div>
        )}
      </div>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={isDeleteDialogOpen} onOpenChange={setIsDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Conversation</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete this conversation? This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleteMutation.isPending ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Trash2 className="w-4 h-4 mr-2" />
              )}
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
