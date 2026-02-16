import { useState, useMemo, useEffect, useCallback } from "react";
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
import { useQueryClient } from "@tanstack/react-query";
import { useInfiniteConversations, useFollowerDetail, useSendMessage, useArchiveConversation, useMarkConversationSpam, useDeleteConversation, useArchivedConversations, useRestoreConversation, useEventStream } from "@/hooks/useApi";
import { getFollowerDetail, apiKeys, getCreatorId } from "@/services/api";
import { useToast } from "@/hooks/use-toast";
import type { Conversation, Message } from "@/types/api";
import { getPurchaseIntent, detectPlatform, getFriendlyName, extractNameFromMessages, getMessages } from "@/types/api";
import { RelationshipBadge, RelationshipDot } from "@/components/RelationshipBadge";

const platformIcons: Record<string, React.ReactNode> = {
  instagram: <Instagram className="w-3 h-3" />,
  telegram: <Send className="w-3 h-3" />,
  whatsapp: <MessageCircle className="w-3 h-3" />,
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
  const [showOnlyLeads, setShowOnlyLeads] = useState(false);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<"all" | "archived">("all");
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

    // Sort by last contact (most recent first)
    return filtered.sort((a, b) =>
      new Date(b.last_contact || 0).getTime() - new Date(a.last_contact || 0).getTime()
    );
  }, [data?.pages, archivedData, searchQuery, activeTab, showOnlyLeads]);

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

  // Loading state — skeleton
  if (isLoading) {
    return (
      <div className="flex h-[80vh]">
        {/* Conversation list skeleton */}
        <div className="w-80 border-r border-border/30 p-3 space-y-2">
          {Array.from({ length: 10 }).map((_, i) => (
            <div key={i} className="flex items-center gap-3 p-3 rounded-lg">
              <div className="w-10 h-10 rounded-full bg-muted/40 animate-pulse shrink-0" />
              <div className="flex-1 space-y-1.5">
                <div className="h-4 w-28 rounded bg-muted/40 animate-pulse" />
                <div className="h-3 w-40 rounded bg-muted/30 animate-pulse" />
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
        {/* Tabs */}
        <div className="flex gap-2 mb-4">
          <button
            onClick={() => setActiveTab("all")}
            className={cn(
              "flex-1 py-2 px-3 rounded-lg text-sm font-medium transition-all",
              activeTab === "all"
                ? "bg-primary text-primary-foreground"
                : "bg-secondary text-muted-foreground hover:text-foreground"
            )}
          >
            All
          </button>
          <button
            onClick={() => setActiveTab("archived")}
            className={cn(
              "flex-1 py-2 px-3 rounded-lg text-sm font-medium transition-all flex items-center justify-center gap-2",
              activeTab === "archived"
                ? "bg-primary text-primary-foreground"
                : "bg-secondary text-muted-foreground hover:text-foreground"
            )}
          >
            <Archive className="w-4 h-4" />
            Archived {archivedCount > 0 && `(${archivedCount})`}
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
        </div>

        <div className="flex-1 overflow-auto space-y-1">
          {(activeTab === "archived" ? archivedLoading : isLoading) ? (
            <div className="space-y-2 animate-pulse">
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="flex items-center gap-3 p-3 rounded-lg">
                  <div className="w-10 h-10 rounded-full bg-muted/40 shrink-0" />
                  <div className="flex-1 space-y-1.5">
                    <div className="h-4 w-28 rounded bg-muted/40" />
                    <div className="h-3 w-40 rounded bg-muted/30" />
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

              return (
                <div
                  key={convo.follower_id}
                  onMouseEnter={() => handleConversationHover(convo.follower_id)}
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
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-1.5 min-w-0">
                          <RelationshipDot type={convo.relationship_type || convo.status} />
                          <span className={`font-medium text-sm truncate ${convo.is_unread ? 'text-white' : ''}`}>{listDisplayName}</span>
                          {convo.is_verified && <span className="text-[#0095F6] text-xs shrink-0">✓</span>}
                        </div>
                        <div className="flex items-center gap-1.5 shrink-0">
                          <span className="text-xs text-muted-foreground">{formatTimeAgo(convo.last_contact)}</span>
                          {convo.is_unread && <div className="w-2 h-2 rounded-full bg-[#0095F6]"></div>}
                        </div>
                      </div>
                      <p className={`text-xs truncate mt-0.5 ${convo.is_unread ? 'text-white font-medium' : 'text-muted-foreground'}`}>
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
            <div className="flex-1 overflow-auto p-4 space-y-4">
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
                messages.map((msg, idx) => (
                  <MessageRenderer
                    key={idx}
                    message={msg}
                    isLastInGroup={idx === messages.length - 1 || messages[idx + 1]?.role !== msg.role}
                  />
                ))
              ) : (
                <div className="text-center py-8 text-muted-foreground">
                  <p>No messages in this conversation</p>
                  <p className="text-sm mt-1">Total messages: {selectedConversation.total_messages || 0}</p>
                </div>
              )}
            </div>

            {/* Input */}
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
                  className="bg-gradient-to-r from-primary to-accent hover:opacity-90 transition-opacity"
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
