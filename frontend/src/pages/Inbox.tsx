import { useState, useMemo, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { Search, Send, MoreHorizontal, Loader2, AlertCircle, Instagram, MessageCircle, Archive, Trash2, AlertTriangle, RotateCcw, ArrowLeft } from "lucide-react";
import { MessageRenderer } from "@/components/chat/MessageRenderer";
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
import { useInfiniteConversations, useFollowerDetail, useSendMessage, useArchiveConversation, useMarkConversationSpam, useDeleteConversation, useArchivedConversations, useRestoreConversation } from "@/hooks/useApi";
import { useToast } from "@/hooks/use-toast";
import type { Conversation, Message } from "@/types/api";
import { getPurchaseIntent, detectPlatform, getFriendlyName, extractNameFromMessages, getMessages } from "@/types/api";

// Status colors matching Pipeline (solid colors for visibility)
const statusColors: Record<string, string> = {
  new: "bg-blue-500/20 text-blue-400 border-blue-400/30",
  active: "bg-amber-500/20 text-amber-400 border-amber-400/30",
  hot: "bg-red-500/20 text-red-400 border-red-400/30",
  customer: "bg-emerald-500/20 text-emerald-400 border-emerald-400/30",
  ghost: "bg-gray-500/20 text-gray-400 border-gray-400/30",
  archived: "bg-gray-500/20 text-gray-400 border-gray-400/30",
  spam: "bg-red-500/20 text-red-400 border-red-400/30",
};

// Status names in Spanish (matching Pipeline)
const statusNames: Record<string, string> = {
  new: "Nuevo",
  active: "Interesado",
  hot: "Caliente",
  customer: "Cliente",
  ghost: "Fantasma",
  archived: "Archivado",
  spam: "Spam",
};

// Platform brand colors
const platformColors = {
  instagram: {
    gradient: "linear-gradient(45deg, #f09433, #e6683c, #dc2743, #cc2366, #bc1888)",
    primary: "#E1306C",
    bg: "bg-gradient-to-r from-[#f09433] via-[#dc2743] to-[#bc1888]",
    bgLight: "bg-[#E1306C]/10",
    text: "text-[#E1306C]",
    border: "border-[#E1306C]",
  },
  whatsapp: {
    gradient: "linear-gradient(45deg, #25D366, #128C7E)",
    primary: "#25D366",
    bg: "bg-[#25D366]",
    bgLight: "bg-[#25D366]/10",
    text: "text-[#25D366]",
    border: "border-[#25D366]",
  },
  telegram: {
    gradient: "linear-gradient(45deg, #0088cc, #229ED9)",
    primary: "#0088cc",
    bg: "bg-[#0088cc]",
    bgLight: "bg-[#0088cc]/10",
    text: "text-[#0088cc]",
    border: "border-[#0088cc]",
  },
};

// Platform icons with brand colors (always colored)
const PlatformIcon = ({ platform, size = "sm" }: { platform: string; size?: "sm" | "md" | "lg" }) => {
  const sizeClasses = {
    sm: "w-4 h-4",
    md: "w-6 h-6",
    lg: "w-8 h-8",
  };
  const iconSize = sizeClasses[size];

  switch (platform) {
    case "instagram":
      return (
        <div className="relative" style={{ width: size === "lg" ? 32 : size === "md" ? 24 : 16, height: size === "lg" ? 32 : size === "md" ? 24 : 16 }}>
          <Instagram className={`${iconSize}`} style={{ stroke: "url(#instagram-gradient)" }} />
          <svg width="0" height="0" className="absolute">
            <defs>
              <linearGradient id="instagram-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#f09433" />
                <stop offset="25%" stopColor="#e6683c" />
                <stop offset="50%" stopColor="#dc2743" />
                <stop offset="75%" stopColor="#cc2366" />
                <stop offset="100%" stopColor="#bc1888" />
              </linearGradient>
            </defs>
          </svg>
        </div>
      );
    case "whatsapp":
      return <MessageCircle className={`${iconSize} text-[#25D366]`} />;
    case "telegram":
      return <Send className={`${iconSize} text-[#0088cc]`} />;
    default:
      return <MessageCircle className={`${iconSize} text-muted-foreground`} />;
  }
};

// Legacy platformIcons for backwards compatibility
const platformIcons: Record<string, React.ReactNode> = {
  instagram: <Instagram className="w-4 h-4 text-[#E1306C]" />,
  telegram: <Send className="w-4 h-4 text-[#0088cc]" />,
  whatsapp: <MessageCircle className="w-4 h-4 text-[#25D366]" />,
};

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

function getStatus(convo: Conversation): string {
  // Priority 1: Use backend status if available
  // Backend categories: nuevo→new, interesado→active, caliente→hot, cliente→customer, fantasma→ghost
  const backendStatus = (convo as { status?: string }).status || convo.lead_status;
  if (backendStatus && ["hot", "active", "new", "customer", "ghost", "archived", "spam"].includes(backendStatus)) {
    return backendStatus;
  }

  // Priority 2: Check if customer
  if (convo.is_customer) return "customer";

  // Priority 3: Fallback to score-based calculation (only if no backend status)
  const score = getPurchaseIntent(convo);
  if (score >= 0.50) return "hot";
  if (score >= 0.25) return "active";
  return "new";
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
  // Read conversation ID from URL query param (?id=xxx)
  const [searchParams, setSearchParams] = useSearchParams();
  const urlConversationId = searchParams.get("id");

  // SEQUENTIAL LOADING: Load conversations first, then archived (prevents backend blocking)
  const {
    data,
    isLoading,
    error,
    isSuccess,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage
  } = useInfiniteConversations();
  const { data: archivedData, isLoading: archivedLoading } = useArchivedConversations(undefined, {
    enabled: isSuccess // Only load AFTER conversations finishes
  });
  const [selectedId, setSelectedId] = useState<string | null>(urlConversationId);

  const [message, setMessage] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<"all" | "archived">("all");
  const [platformFilter, setPlatformFilter] = useState<"all" | "instagram" | "whatsapp" | "telegram">("all");
  const { toast } = useToast();
  const sendMessageMutation = useSendMessage();
  const archiveMutation = useArchiveConversation();
  const spamMutation = useMarkConversationSpam();
  const deleteMutation = useDeleteConversation();
  const restoreMutation = useRestoreConversation();

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
      setMessage(""); // Clear input on success
    } catch (error) {
      toast({
        title: "Error sending message",
        description: error instanceof Error ? error.message : "Failed to send",
        variant: "destructive",
      });
    }
  };

  // Handle enter key to send
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const conversations = useMemo(() => {
    // Flatten all pages from infinite query
    const allConversations = data?.pages?.flatMap(page => page.conversations) || [];
    const sourceData = activeTab === "archived" ? archivedData : allConversations;
    if (!sourceData) return [];

    let filtered = Array.isArray(sourceData) ? sourceData : [];

    // Filter by platform
    if (platformFilter !== "all") {
      filtered = filtered.filter(c => {
        const platform = c.platform || detectPlatform(c.follower_id);
        return platform === platformFilter;
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

    // Sort by last contact (most recent first)
    return filtered.sort((a, b) =>
      new Date(b.last_contact || 0).getTime() - new Date(a.last_contact || 0).getTime()
    );
  }, [data?.pages, archivedData, searchQuery, activeTab, platformFilter]);

  const archivedCount = archivedData?.length || 0;

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

  // Messages from the follower detail API (uses last_messages field)
  const messages: Message[] = useMemo(() => {
    return getMessages(followerData);
  }, [followerData]);

  // Get smart display name for selected conversation
  const displayName = useMemo(() => {
    if (!selectedConversation) return "";
    return getSmartDisplayName(selectedConversation, messages);
  }, [selectedConversation, messages]);

  // Loading state
  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
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
        {/* Platform Tabs - Always show brand colors */}
        <div className="flex gap-1 mb-3 overflow-x-auto pb-1">
          <button
            onClick={() => { setPlatformFilter("all"); setActiveTab("all"); }}
            className={cn(
              "flex items-center gap-2 py-2 px-3 rounded-lg text-sm font-medium transition-all whitespace-nowrap",
              platformFilter === "all" && activeTab === "all"
                ? "bg-primary text-primary-foreground"
                : "bg-secondary/50 text-muted-foreground hover:text-foreground hover:bg-secondary"
            )}
          >
            All
          </button>
          <button
            onClick={() => { setPlatformFilter("instagram"); setActiveTab("all"); }}
            className={cn(
              "flex items-center gap-2 py-2 px-3 rounded-lg text-sm font-medium transition-all whitespace-nowrap",
              platformFilter === "instagram"
                ? "bg-[#E1306C]/20 text-white border border-[#E1306C]/50"
                : "bg-secondary/50 text-muted-foreground hover:text-foreground hover:bg-secondary"
            )}
          >
            <Instagram className="w-5 h-5" style={{ color: "#E1306C" }} />
            <span className={platformFilter === "instagram" ? "text-[#E1306C]" : ""}>Instagram</span>
          </button>
          <button
            onClick={() => { setPlatformFilter("whatsapp"); setActiveTab("all"); }}
            className={cn(
              "flex items-center gap-2 py-2 px-3 rounded-lg text-sm font-medium transition-all whitespace-nowrap",
              platformFilter === "whatsapp"
                ? "bg-[#25D366]/20 text-white border border-[#25D366]/50"
                : "bg-secondary/50 text-muted-foreground hover:text-foreground hover:bg-secondary"
            )}
          >
            <MessageCircle className="w-5 h-5 text-[#25D366]" />
            <span className={platformFilter === "whatsapp" ? "text-[#25D366]" : ""}>WhatsApp</span>
          </button>
          <button
            onClick={() => { setPlatformFilter("telegram"); setActiveTab("all"); }}
            className={cn(
              "flex items-center gap-2 py-2 px-3 rounded-lg text-sm font-medium transition-all whitespace-nowrap",
              platformFilter === "telegram"
                ? "bg-[#0088cc]/20 text-white border border-[#0088cc]/50"
                : "bg-secondary/50 text-muted-foreground hover:text-foreground hover:bg-secondary"
            )}
          >
            <Send className="w-5 h-5 text-[#0088cc]" />
            <span className={platformFilter === "telegram" ? "text-[#0088cc]" : ""}>Telegram</span>
          </button>
          <button
            onClick={() => { setActiveTab("archived"); setPlatformFilter("all"); }}
            className={cn(
              "flex items-center gap-2 py-2 px-3 rounded-lg text-sm font-medium transition-all whitespace-nowrap ml-auto",
              activeTab === "archived"
                ? "bg-muted text-foreground"
                : "bg-secondary/50 text-muted-foreground hover:text-foreground hover:bg-secondary"
            )}
          >
            <Archive className="w-4 h-4" />
            {archivedCount > 0 && <span className="text-xs">({archivedCount})</span>}
          </button>
        </div>

        <div className="mb-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              placeholder="Search conversations..."
              className="pl-10 bg-secondary border-0"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
        </div>

        <div className="flex-1 overflow-auto space-y-1">
          {(activeTab === "archived" ? archivedLoading : isLoading) ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
            </div>
          ) : conversations.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <p>{activeTab === "archived" ? "No archived conversations" : "No conversations yet"}</p>
              <p className="text-sm">{activeTab === "archived" ? "Archived and spam items will appear here" : "Messages will appear here"}</p>
            </div>
          ) : (
            conversations.map((convo) => {
              const status = activeTab === "archived" ? (convo.status || "archived") : getStatus(convo);
              const platform = convo.platform || detectPlatform(convo.follower_id);
              const listDisplayName = convo.name || convo.username || getFriendlyName(convo.follower_id);
              const initials = getInitials(convo.name, convo.username, convo.follower_id);
              const lastMessage = convo.last_messages?.[convo.last_messages.length - 1];
              const isArchived = activeTab === "archived";

              return (
                <div
                  key={convo.follower_id}
                  className={cn(
                    "w-full p-3 rounded-xl text-left transition-all hover:bg-secondary",
                    selectedId === convo.follower_id && "bg-secondary"
                  )}
                >
                  <div className="flex items-start gap-3">
                    <button
                      onClick={() => setSelectedId(convo.follower_id)}
                      className="shrink-0"
                    >
                      {convo.profile_pic_url ? (
                        <img
                          src={convo.profile_pic_url}
                          alt={convo.username || ""}
                          className="w-10 h-10 rounded-full object-cover"
                          onError={(e) => {
                            e.currentTarget.style.display = "none";
                            e.currentTarget.nextElementSibling?.classList.remove("hidden");
                          }}
                        />
                      ) : null}
                      <div className={cn(
                        "w-10 h-10 rounded-full bg-gradient-to-br from-primary/60 to-accent/60 flex items-center justify-center text-xs font-semibold",
                        convo.profile_pic_url && "hidden"
                      )}>
                        {initials}
                      </div>
                    </button>
                    <button
                      onClick={() => setSelectedId(convo.follower_id)}
                      className="flex-1 min-w-0 text-left"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-1">
                          <span className={`font-medium text-sm truncate ${convo.is_unread ? 'text-white' : ''}`}>{listDisplayName}</span>
                          {convo.is_verified && <span className="text-[#0095F6] text-xs">✓</span>}
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-muted-foreground">{formatTimeAgo(convo.last_contact)}</span>
                          {convo.is_unread && <div className="w-2 h-2 rounded-full bg-[#0095F6]"></div>}
                        </div>
                      </div>
                      <p className={`text-xs truncate mt-0.5 ${convo.is_unread ? 'text-white font-medium' : 'text-muted-foreground'}`}>
                        {convo.last_message_role === 'assistant' ? 'You: ' : ''}
                        {convo.last_message_preview || lastMessage?.content || `${convo.total_messages || 0} messages`}
                      </p>
                      <div className="mt-2 flex items-center gap-2">
                        <span className={cn(
                          "status-badge text-[10px] border",
                          isArchived
                            ? status === "spam" ? "bg-destructive/10 text-destructive border-destructive/20" : "bg-muted/10 text-muted-foreground border-muted/20"
                            : statusColors[status]
                        )}>
                          {statusNames[status] || status}
                        </span>
                        {platform === "instagram" ? (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              const username = (convo.username || convo.follower_id).replace(/^@/, "").replace(/^ig_/, "");
                              window.open(`https://instagram.com/${username}`, "_blank");
                            }}
                            className="text-[10px] flex items-center gap-1 hover:opacity-80 transition-opacity"
                            title={`Abrir @${(convo.username || "").replace(/^@/, "")}`}
                          >
                            <Instagram className="w-4 h-4" style={{ color: "#E1306C" }} />
                            <span className="text-[#E1306C]">{platform}</span>
                          </button>
                        ) : platform === "whatsapp" ? (
                          <span className="text-[10px] flex items-center gap-1">
                            <MessageCircle className="w-4 h-4 text-[#25D366]" />
                            <span className="text-[#25D366]">{platform}</span>
                          </span>
                        ) : platform === "telegram" ? (
                          <span className="text-[10px] flex items-center gap-1">
                            <Send className="w-4 h-4 text-[#0088cc]" />
                            <span className="text-[#0088cc]">{platform}</span>
                          </span>
                        ) : (
                          <span className="text-[10px] text-muted-foreground flex items-center gap-1">
                            {platformIcons[platform]}
                            {platform}
                          </span>
                        )}
                      </div>
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

          {/* Load More Button for infinite scroll */}
          {activeTab === "all" && hasNextPage && (
            <div className="py-4 flex justify-center">
              <Button
                variant="outline"
                size="sm"
                onClick={() => fetchNextPage()}
                disabled={isFetchingNextPage}
                className="w-full max-w-xs"
              >
                {isFetchingNextPage ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Loading...
                  </>
                ) : (
                  "Load more conversations"
                )}
              </Button>
            </div>
          )}
        </div>
      </div>

      {/* Chat View - hidden on mobile when no chat selected */}
      <div className={cn(
        "flex-1 flex flex-col bg-card rounded-2xl border border-border/50 overflow-hidden",
        showMobileChat ? "flex" : "hidden md:flex"
      )}>
        {selectedConversation ? (
          <>
            {/* Chat Header */}
            <div className="p-4 border-b border-border/50 flex items-center justify-between">
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
                  "w-10 h-10 rounded-full bg-gradient-to-br from-primary/60 to-accent/60 flex items-center justify-center text-sm font-semibold",
                  selectedConversation.profile_pic_url && "hidden"
                )}>
                  {getInitials(displayName, undefined, selectedConversation.follower_id)}
                </div>
                <div>
                  <p className="font-semibold">
                    {displayName}
                  </p>
                  <div className="text-xs flex items-center gap-1">
                    {(() => {
                      const platform = selectedConversation.platform || detectPlatform(selectedConversation.follower_id);
                      if (platform === "instagram") {
                        return (
                          <button
                            onClick={() => {
                              const username = (selectedConversation.username || selectedConversation.follower_id).replace(/^@/, "").replace(/^ig_/, "");
                              window.open(`https://instagram.com/${username}`, "_blank");
                            }}
                            className="flex items-center gap-1 hover:opacity-80 transition-opacity"
                            title={`Abrir @${(selectedConversation.username || "").replace(/^@/, "")}`}
                          >
                            <Instagram className="w-4 h-4" style={{ color: "#E1306C" }} />
                            <span className="text-[#E1306C] font-medium">Instagram</span>
                          </button>
                        );
                      } else if (platform === "whatsapp") {
                        return (
                          <span className="flex items-center gap-1">
                            <MessageCircle className="w-4 h-4 text-[#25D366]" />
                            <span className="text-[#25D366] font-medium">WhatsApp</span>
                          </span>
                        );
                      } else if (platform === "telegram") {
                        return (
                          <span className="flex items-center gap-1">
                            <Send className="w-4 h-4 text-[#0088cc]" />
                            <span className="text-[#0088cc] font-medium">Telegram</span>
                          </span>
                        );
                      }
                      return (
                        <span className="flex items-center gap-1 text-muted-foreground">
                          {platformIcons[platform]}
                          {platform}
                        </span>
                      );
                    })()}
                    <span className="text-muted-foreground">• Score: {Math.round(getPurchaseIntent(followerData || selectedConversation) * 100)}%</span>
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

            {/* Messages - Platform-specific background */}
            {(() => {
              const platform = selectedConversation.platform || detectPlatform(selectedConversation.follower_id);
              const chatBgClass = platform === "whatsapp"
                ? "bg-[#0B141A]"
                : platform === "telegram"
                ? "bg-[#0E1621]"
                : ""; // Instagram uses default bg-card
              return (
                <div className={cn("flex-1 overflow-auto p-4 space-y-4", chatBgClass)}>
                  {messagesLoading ? (
                    <div className="flex items-center justify-center h-full">
                      <Loader2 className="w-6 h-6 animate-spin text-primary" />
                    </div>
                  ) : messages.length > 0 ? (
                    messages.map((msg, idx) => (
                      <MessageRenderer
                        key={idx}
                        message={msg}
                        isLastInGroup={idx === messages.length - 1 || messages[idx + 1]?.role !== msg.role}
                        platform={platform as "instagram" | "whatsapp" | "telegram"}
                      />
                    ))
                  ) : (
                    <div className="text-center py-8 text-muted-foreground">
                      <p>No messages in this conversation</p>
                      <p className="text-sm mt-1">Total messages: {selectedConversation.total_messages || 0}</p>
                    </div>
                  )}
                </div>
              );
            })()}

            {/* Input - Platform-specific send button */}
            {(() => {
              const platform = selectedConversation.platform || detectPlatform(selectedConversation.follower_id);
              const sendButtonClass = platform === "whatsapp"
                ? "bg-[#25D366] hover:bg-[#20BD5A]"
                : platform === "telegram"
                ? "bg-[#0088cc] hover:bg-[#0077B5]"
                : "bg-gradient-to-r from-[#833AB4] via-[#E1306C] to-[#F77737] hover:opacity-90";
              return (
                <div className="p-4 border-t border-border/50">
                  <div className="flex gap-3">
                    <Input
                      value={message}
                      onChange={(e) => setMessage(e.target.value)}
                      onKeyDown={handleKeyDown}
                      placeholder="Type a message..."
                      className="flex-1 bg-secondary border-0"
                      disabled={sendMessageMutation.isPending}
                    />
                    <Button
                      type="button"
                      onClick={handleSend}
                      disabled={!selectedId || !message.trim() || sendMessageMutation.isPending}
                      className={cn(sendButtonClass, "transition-opacity")}
                    >
                      {sendMessageMutation.isPending ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Send className="w-4 h-4" />
                      )}
                    </Button>
                  </div>
                </div>
              );
            })()}
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
