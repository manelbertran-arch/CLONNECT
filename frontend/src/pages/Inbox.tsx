import { useState, useMemo, useEffect } from "react";
import { Search, Send, MoreHorizontal, Bot, User, Loader2, AlertCircle, Instagram, MessageCircle, Archive, Trash2, AlertTriangle } from "lucide-react";
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
import { useConversations, useFollowerDetail, useSendMessage, useArchiveConversation, useMarkConversationSpam, useDeleteConversation } from "@/hooks/useApi";
import { useToast } from "@/hooks/use-toast";
import type { Conversation, Message } from "@/types/api";
import { getPurchaseIntent, detectPlatform, getFriendlyName, extractNameFromMessages, getMessages } from "@/types/api";

const statusColors: Record<string, string> = {
  hot: "bg-destructive/10 text-destructive border-destructive/20",
  active: "bg-accent/10 text-accent border-accent/20",
  replied: "bg-success/10 text-success border-success/20",
  nurturing: "bg-primary/10 text-primary border-primary/20",
  customer: "bg-success/10 text-success border-success/20",
  new: "bg-muted/10 text-muted-foreground border-muted/20",
};

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

function getStatus(convo: Conversation): string {
  if (convo.is_customer) return "customer";
  const score = getPurchaseIntent(convo);
  // Ranges: 0-25% (new) | 25-50% (active) | 50%+ (hot)
  if (score >= 0.50) return "hot";
  if (score >= 0.25) return "active";
  if (convo.is_lead) return "nurturing";
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
  const { data, isLoading, error } = useConversations();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const { toast } = useToast();
  const sendMessageMutation = useSendMessage();
  const archiveMutation = useArchiveConversation();
  const spamMutation = useMarkConversationSpam();
  const deleteMutation = useDeleteConversation();

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

  // Handle sending a manual message
  const handleSend = async () => {
    console.log("handleSend called", { selectedId, message: message.trim() });

    if (!selectedId || !message.trim()) {
      console.log("handleSend early return - missing data");
      return;
    }

    console.log("Calling sendMessageMutation...");
    try {
      const result = await sendMessageMutation.mutateAsync({
        followerId: selectedId,
        message: message.trim(),
      });
      console.log("sendMessageMutation result:", result);

      if (result.sent) {
        toast({
          title: "Message sent",
          description: `Sent via ${result.platform}`,
        });
      } else {
        toast({
          title: "Message saved",
          description: "Message saved but delivery pending (platform not connected)",
          variant: "destructive",
        });
      }
      setMessage(""); // Clear input on success
    } catch (error) {
      console.error("sendMessageMutation error:", error);
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
    if (!data?.conversations) return [];

    let filtered = data.conversations;

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
  }, [data?.conversations, searchQuery]);

  // Auto-select first conversation if none selected
  useEffect(() => {
    if (!selectedId && conversations.length > 0) {
      setSelectedId(conversations[0].follower_id);
    }
  }, [conversations, selectedId]);

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

  return (
    <div className="h-[calc(100vh-8rem)] flex gap-6">
      {/* Conversation List */}
      <div className="w-80 flex flex-col">
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
          {conversations.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <p>No conversations yet</p>
              <p className="text-sm">Messages will appear here</p>
            </div>
          ) : (
            conversations.map((convo) => {
              const status = getStatus(convo);
              const platform = convo.platform || detectPlatform(convo.follower_id);
              const listDisplayName = convo.name || convo.username || getFriendlyName(convo.follower_id);
              const initials = getInitials(convo.name, convo.username, convo.follower_id);
              const lastMessage = convo.last_messages?.[convo.last_messages.length - 1];

              return (
                <button
                  key={convo.follower_id}
                  onClick={() => setSelectedId(convo.follower_id)}
                  className={cn(
                    "w-full p-3 rounded-xl text-left transition-all hover:bg-secondary",
                    selectedId === convo.follower_id && "bg-secondary"
                  )}
                >
                  <div className="flex items-start gap-3">
                    <div className="w-10 h-10 rounded-full bg-gradient-to-br from-primary/60 to-accent/60 flex items-center justify-center text-xs font-semibold shrink-0">
                      {initials}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between">
                        <span className="font-medium text-sm truncate">{listDisplayName}</span>
                        <span className="text-xs text-muted-foreground">{formatTimeAgo(convo.last_contact)}</span>
                      </div>
                      <p className="text-xs text-muted-foreground truncate mt-0.5">
                        {lastMessage?.content || `${convo.total_messages || 0} messages`}
                      </p>
                      <div className="mt-2 flex items-center gap-2">
                        <span className={cn("status-badge text-[10px] border", statusColors[status])}>
                          {status}
                        </span>
                        <span className="text-[10px] text-muted-foreground flex items-center gap-1">
                          {platformIcons[platform]}
                          {platform}
                        </span>
                      </div>
                    </div>
                  </div>
                </button>
              );
            })
          )}
        </div>
      </div>

      {/* Chat View */}
      <div className="flex-1 flex flex-col bg-card rounded-2xl border border-border/50 overflow-hidden">
        {selectedConversation ? (
          <>
            {/* Chat Header */}
            <div className="p-4 border-b border-border/50 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-gradient-to-br from-primary/60 to-accent/60 flex items-center justify-center text-sm font-semibold">
                  {getInitials(displayName, undefined, selectedConversation.follower_id)}
                </div>
                <div>
                  <p className="font-semibold">
                    {displayName}
                  </p>
                  <p className="text-xs text-muted-foreground flex items-center gap-1">
                    {platformIcons[selectedConversation.platform || detectPlatform(selectedConversation.follower_id)]}
                    {selectedConversation.platform || detectPlatform(selectedConversation.follower_id)} • Score: {Math.round(getPurchaseIntent(followerData || selectedConversation) * 100)}%
                  </p>
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
                <div className="flex items-center justify-center h-full">
                  <Loader2 className="w-6 h-6 animate-spin text-primary" />
                </div>
              ) : messages.length > 0 ? (
                messages.map((msg, idx) => (
                  <div
                    key={idx}
                    className={cn(
                      "flex gap-3",
                      msg.role === "assistant" ? "justify-start" : "justify-end"
                    )}
                  >
                    {msg.role === "assistant" && (
                      <div className="w-8 h-8 rounded-full bg-gradient-to-br from-primary to-accent flex items-center justify-center shrink-0">
                        <Bot className="w-4 h-4 text-white" />
                      </div>
                    )}
                    <div
                      className={cn(
                        "max-w-[70%] p-3 rounded-2xl text-sm",
                        msg.role === "assistant"
                          ? "bg-secondary rounded-tl-md"
                          : "bg-gradient-to-br from-primary to-accent text-white rounded-tr-md"
                      )}
                    >
                      <p className="whitespace-pre-wrap">{msg.content}</p>
                      <p className={cn(
                        "text-[10px] mt-1",
                        msg.role === "assistant" ? "text-muted-foreground" : "text-white/70"
                      )}>
                        {msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}
                      </p>
                    </div>
                    {msg.role === "user" && (
                      <div className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center shrink-0">
                        <User className="w-4 h-4" />
                      </div>
                    )}
                  </div>
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
                  onClick={() => {
                    console.log("Send button clicked!", { selectedId, message, isPending: sendMessageMutation.isPending });
                    handleSend();
                  }}
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
