import { useState } from "react";
import { useConversations, useFollowerDetail, useSendMessage } from "@/hooks/useApi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Send, MessageSquare } from "lucide-react";

export default function Inbox() {
  const { data, isLoading, error } = useConversations();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [message, setMessage] = useState("");

  const { data: followerData } = useFollowerDetail(selectedId);
  const sendMutation = useSendMessage();

  // Simple loading state
  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    );
  }

  if (error) {
    return <div className="text-red-500">Error loading conversations</div>;
  }

  const conversations = data?.conversations || [];

  const handleSend = async () => {
    if (!selectedId || !message.trim()) return;
    try {
      await sendMutation.mutateAsync({ recipientId: selectedId, message });
      setMessage("");
    } catch (e) {
      console.error("Send failed:", e);
    }
  };

  return (
    <div className="flex h-[calc(100vh-8rem)] gap-4">
      {/* Conversation list */}
      <Card className="w-80 flex-shrink-0">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <MessageSquare className="h-5 w-5" />
            Inbox ({conversations.length})
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0 overflow-y-auto max-h-[calc(100vh-12rem)]">
          {conversations.map((conv: any) => (
            <div
              key={conv.follower_id}
              onClick={() => setSelectedId(conv.follower_id)}
              className={`p-3 border-b cursor-pointer hover:bg-muted/50 ${
                selectedId === conv.follower_id ? "bg-muted" : ""
              }`}
            >
              <div className="font-medium">{conv.username || conv.name || conv.follower_id}</div>
              <div className="text-sm text-muted-foreground truncate">
                {conv.last_messages?.[0]?.content || "No messages"}
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Messages */}
      <Card className="flex-1 flex flex-col">
        <CardHeader>
          <CardTitle>
            {selectedId ? (followerData?.username || selectedId) : "Select a conversation"}
          </CardTitle>
        </CardHeader>
        <CardContent className="flex-1 overflow-y-auto">
          {followerData?.messages?.map((msg: any, i: number) => (
            <div
              key={i}
              className={`mb-2 p-2 rounded max-w-[80%] ${
                msg.role === "user" ? "bg-blue-100 ml-auto" : "bg-gray-100"
              }`}
            >
              {msg.content}
            </div>
          ))}
        </CardContent>
        {selectedId && (
          <div className="p-4 border-t flex gap-2">
            <Input
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Type a message..."
              onKeyPress={(e) => e.key === "Enter" && handleSend()}
            />
            <Button onClick={handleSend} disabled={sendMutation.isPending}>
              <Send className="h-4 w-4" />
            </Button>
          </div>
        )}
      </Card>
    </div>
  );
}
