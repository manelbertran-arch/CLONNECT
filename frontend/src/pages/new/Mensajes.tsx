import { useState, useRef, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useParams, Link } from 'react-router-dom';
import {
  getConversations,
  getFollowerDetail,
  getPendingForLead,
  sendMessage,
  markConversationRead,
  CREATOR_ID,
  apiKeys,
} from '@/services/api';
import { Search, Send, ArrowLeft, MessageCircle } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { MessageRenderer } from '@/components/chat/MessageRenderer';
import { useEventStream } from '@/hooks/api/useEventStream';

export default function Mensajes() {
  const { conversationId } = useParams();
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [newMessage, setNewMessage] = useState('');
  const creatorId = CREATOR_ID;
  const queryClient = useQueryClient();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // SSE: real-time updates for new messages, deletions, approvals
  useEventStream(creatorId);

  const { data: conversationsData } = useQuery({
    queryKey: apiKeys.conversations(creatorId),
    queryFn: () => getConversations(creatorId),
    refetchInterval: 15000,  // SSE handles real-time; polling is fallback only
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
    staleTime: 0,
  });

  const { data: followerDetail, isLoading: isLoadingMessages } = useQuery({
    queryKey: apiKeys.follower(creatorId, conversationId || ''),
    queryFn: () => getFollowerDetail(creatorId, conversationId!),
    enabled: !!conversationId,
    refetchInterval: 3000,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
    staleTime: 0,
  });

  // Copilot suggestions for the active conversation
  const { data: copilotData } = useQuery({
    queryKey: apiKeys.copilotPendingForLead(creatorId, conversationId || ''),
    queryFn: () => getPendingForLead(creatorId, conversationId!),
    enabled: !!conversationId,
    refetchInterval: 3000,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
    staleTime: 0,
  });

  const sendMessageMutation = useMutation({
    mutationFn: (message: string) =>
      sendMessage(creatorId, conversationId!, message),
    onSuccess: () => {
      setNewMessage('');
      queryClient.invalidateQueries({ queryKey: apiKeys.follower(creatorId, conversationId || '') });
      queryClient.invalidateQueries({ queryKey: apiKeys.conversations(creatorId) });
    },
  });

  // Mark conversation as read when opened
  useEffect(() => {
    if (conversationId) {
      // Call API to mark as read
      markConversationRead(creatorId, conversationId).catch(() => {
        // Silently ignore errors - not critical
      });
      // Optimistically update local state to remove blue dot
      queryClient.setQueryData(
        ['conversations', creatorId],
        (oldData: any) => {
          if (!oldData?.conversations) return oldData;
          return {
            ...oldData,
            conversations: oldData.conversations.map((conv: any) =>
              conv.follower_id === conversationId
                ? { ...conv, is_unread: false }
                : conv
            ),
          };
        }
      );
    }
  }, [conversationId, creatorId, queryClient]);

  const conversations = conversationsData?.conversations || [];
  const unreadCount = conversations.filter((c) => c.is_unread).length;

  const selectedConversation = conversations.find(
    (c) => c.follower_id === conversationId
  );

  const filteredConversations = conversations
    .filter((c) => statusFilter === 'all' || c.status === statusFilter)
    .filter((c) =>
      (c.username || c.name || c.follower_id)
        .toLowerCase()
        .includes(search.toLowerCase())
    );

  const rawMessages = followerDetail?.last_messages || [];
  // Dedup by platform_message_id to prevent duplicate renders on refetch
  const messages = rawMessages.filter((msg, idx, arr) => {
    if (!msg.platform_message_id) return true;
    return arr.findIndex(m => m.platform_message_id === msg.platform_message_id) === idx;
  });

  // Auto-scroll to bottom when messages load or change
  useEffect(() => {
    if (messages.length > 0) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, conversationId]);

  // Format relative time - Spanish Instagram style
  const formatTimeAgo = (dateStr?: string) => {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    // < 1 hour: "hace 5 min"
    if (diffMins < 60) return `hace ${diffMins || 1} min`;

    // < 24 hours: "hace 3h"
    if (diffHours < 24) return `hace ${diffHours}h`;

    // < 7 days: "lun", "mar", etc.
    if (diffDays < 7) {
      return date.toLocaleDateString('es', { weekday: 'short' });
    }

    // > 7 days: "15 ene"
    return date.toLocaleDateString('es', { day: 'numeric', month: 'short' });
  };

  const handleSendMessage = () => {
    if (newMessage.trim() && conversationId) {
      sendMessageMutation.mutate(newMessage.trim());
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  return (
    <div className="h-[calc(100vh-8rem)] md:h-[calc(100vh-4rem)] flex flex-col md:flex-row bg-black rounded-xl overflow-hidden">
      {/* Conversation List - Instagram Style */}
      <div
        className={`
        ${conversationId ? 'hidden md:flex' : 'flex'}
        flex-col w-full md:w-96 bg-black rounded-xl overflow-hidden border-r border-[#262626]
      `}
      >
        {/* Header with username and unread count */}
        <div className="p-4 border-b border-[#262626]">
          <h1 className="text-xl font-bold text-white flex items-center">
            Mensajes
            {unreadCount > 0 && (
              <span className="bg-red-500 text-white text-xs rounded-full px-2 py-0.5 ml-2">
                {unreadCount}
              </span>
            )}
          </h1>
        </div>

        {/* Search */}
        <div className="p-3">
          <div className="relative">
            <Search
              className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500"
              size={16}
            />
            <Input
              placeholder="Buscar"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-10 bg-[#262626] border-0 rounded-lg text-white placeholder:text-gray-500 focus-visible:ring-0"
            />
          </div>
        </div>

        {/* Status Filter */}
        <div className="flex gap-2 px-3 pb-3 overflow-x-auto scrollbar-hide">
          {[
            { value: 'all', label: 'Todos' },
            { value: 'new', label: 'Nuevos' },
            { value: 'interested', label: 'Interesados' },
            { value: 'hot', label: 'Calientes' },
            { value: 'customer', label: 'Clientes' },
            { value: 'ghost', label: 'Fantasmas' },
          ].map(({ value, label }) => (
            <button
              key={value}
              onClick={() => setStatusFilter(value)}
              className={`px-3 py-1 rounded-full text-xs whitespace-nowrap transition-colors ${
                statusFilter === value
                  ? 'bg-violet-600 text-white'
                  : 'bg-[#262626] text-gray-400 hover:bg-[#363636]'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {/* List */}
        <div className="flex-1 overflow-y-auto">
          {filteredConversations.length === 0 ? (
            <div className="p-4 text-center text-gray-500">
              No hay conversaciones
            </div>
          ) : (
            filteredConversations.map((conv) => (
              <Link
                key={conv.follower_id}
                to={`/new/mensajes/${conv.follower_id}`}
                className={`
                flex items-center gap-3 px-4 py-3 hover:bg-[#121212] transition-colors
                ${conversationId === conv.follower_id ? 'bg-[#121212]' : ''}
              `}
              >
                {/* Avatar with optional hot lead ring */}
                <div className={`p-[2px] rounded-full ${(conv.purchase_intent ?? 0) > 0.5 ? 'bg-gradient-to-tr from-violet-500 via-purple-500 to-violet-600' : ''}`}>
                  <div className={`${(conv.purchase_intent ?? 0) > 0.5 ? 'p-[2px] bg-black rounded-full' : ''}`}>
                    {conv.profile_pic_url ? (
                      <img
                        src={conv.profile_pic_url}
                        alt={conv.username || conv.name || ''}
                        className="w-14 h-14 rounded-full object-cover"
                        onError={(e) => {
                          e.currentTarget.style.display = 'none';
                          e.currentTarget.nextElementSibling?.classList.remove('hidden');
                        }}
                      />
                    ) : null}
                    <div className={`w-14 h-14 rounded-full bg-gradient-to-br from-violet-600 to-purple-600 flex items-center justify-center text-white font-semibold text-lg ${conv.profile_pic_url ? 'hidden' : ''}`}>
                      {(conv.username || conv.name)?.[0]?.toUpperCase() || '?'}
                    </div>
                  </div>
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1">
                    <p className={`font-semibold text-[14px] truncate ${conv.is_unread ? 'text-white' : 'text-gray-300'}`}>
                      {conv.username || conv.name || conv.follower_id}
                    </p>
                    {/* Verified badge - Instagram style */}
                    {(conv.is_verified || conv.isVerified) && (
                      <svg className="w-4 h-4 text-[#0095F6] flex-shrink-0" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10 10-4.5 10-10S17.5 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
                      </svg>
                    )}
                  </div>
                  <div className="flex items-center gap-1">
                    <p className={`text-sm truncate flex-1 ${conv.is_unread ? 'text-white font-medium' : 'text-gray-400'}`}>
                      {conv.last_message_role === 'assistant' ? 'You: ' : ''}
                      {conv.last_message_preview || 'Sin mensajes'}
                    </p>
                    <span className="text-xs text-gray-500 shrink-0">
                      · {formatTimeAgo(conv.last_contact)}
                    </span>
                  </div>
                </div>
                {/* Unread indicator - blue dot */}
                {conv.is_unread && (
                  <div className="w-2.5 h-2.5 rounded-full bg-[#0095F6]"></div>
                )}
              </Link>
            ))
          )}
        </div>
      </div>

      {/* Conversation Detail */}
      {conversationId ? (
        <div className="flex-1 flex flex-col bg-black rounded-xl overflow-hidden">
          {/* Header - Instagram Style */}
          <div className="flex items-center gap-3 p-4 border-b border-[#262626] bg-black">
            <Link to="/new/mensajes" className="md:hidden">
              <ArrowLeft className="text-white" size={24} />
            </Link>
            {/* Violet gradient ring for avatar */}
            <div className="p-[2px] rounded-full bg-gradient-to-tr from-violet-500 via-purple-500 to-violet-600">
              <div className="w-10 h-10 rounded-full bg-black p-[2px]">
                {(selectedConversation?.profile_pic_url || followerDetail?.profile_pic_url) ? (
                  <img
                    src={selectedConversation?.profile_pic_url || followerDetail?.profile_pic_url}
                    alt={selectedConversation?.username || followerDetail?.username || ''}
                    className="w-full h-full rounded-full object-cover"
                    onError={(e) => {
                      e.currentTarget.style.display = 'none';
                      e.currentTarget.nextElementSibling?.classList.remove('hidden');
                    }}
                  />
                ) : null}
                <div className={`w-full h-full rounded-full bg-gradient-to-br from-violet-600 to-purple-600 flex items-center justify-center text-white font-semibold text-sm ${(selectedConversation?.profile_pic_url || followerDetail?.profile_pic_url) ? 'hidden' : ''}`}>
                  {(
                    selectedConversation?.username ||
                    selectedConversation?.name ||
                    followerDetail?.username
                  )?.[0]?.toUpperCase() || '?'}
                </div>
              </div>
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-1">
                <p className="font-semibold text-white text-[15px]">
                  {selectedConversation?.username ||
                    selectedConversation?.name ||
                    followerDetail?.username ||
                    conversationId}
                </p>
                {/* Verified badge - Instagram style */}
                {(selectedConversation?.is_verified || selectedConversation?.isVerified || followerDetail?.is_verified || followerDetail?.isVerified) && (
                  <svg className="w-4 h-4 text-[#0095F6] flex-shrink-0" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10 10-4.5 10-10S17.5 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
                  </svg>
                )}
              </div>
              <p className="text-xs text-gray-400">
                {(selectedConversation?.purchase_intent ?? 0) > 0.7
                  ? '🔥 Hot lead · Activo ahora'
                  : 'Activo ahora'}
              </p>
            </div>
            <button className="text-white p-2">
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
              </svg>
            </button>
            <button className="text-white p-2">
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
            </button>
          </div>

          {/* Messages - Instagram Style */}
          <div className="flex-1 overflow-y-auto p-4 space-y-1 bg-black">
            {isLoadingMessages ? (
              <div className="flex items-center justify-center h-full">
                <div className="text-gray-500">Cargando mensajes...</div>
              </div>
            ) : messages.length === 0 ? (
              <div className="flex items-center justify-center h-full">
                <div className="text-gray-500">No hay mensajes</div>
              </div>
            ) : (
              <>
                {messages.map((msg, i) => {
                  // Determine if this is the last message in a group from same sender
                  const nextMsg = messages[i + 1];
                  const isLastInGroup = !nextMsg || nextMsg.role !== msg.role;
                  const msgKey = msg.platform_message_id || `${msg.timestamp}-${msg.role}-${i}`;

                  return (
                    <MessageRenderer
                      key={msgKey}
                      message={{
                        role: msg.role === 'assistant' ? 'assistant' : 'user',
                        content: msg.content,
                        timestamp: msg.timestamp,
                        metadata: msg.metadata,
                      }}
                      isLastInGroup={isLastInGroup}
                    />
                  );
                })}
                {/* Scroll anchor */}
                <div ref={messagesEndRef} />
              </>
            )}
          </div>

          {/* Input - Instagram Style */}
          <div className="p-3 border-t border-[#262626] bg-black">
            <div className="flex items-center gap-3 bg-[#262626] rounded-full px-4 py-2">
              <Input
                placeholder="Mensaje..."
                value={newMessage}
                onChange={(e) => setNewMessage(e.target.value)}
                onKeyDown={handleKeyPress}
                className="flex-1 bg-transparent border-0 focus-visible:ring-0 focus-visible:ring-offset-0 text-white placeholder:text-gray-500"
              />
              {newMessage.trim() ? (
                <button
                  onClick={handleSendMessage}
                  disabled={sendMessageMutation.isPending}
                  className="text-[#0095F6] font-semibold text-sm hover:text-white transition-colors disabled:opacity-50"
                >
                  Enviar
                </button>
              ) : (
                <div className="flex items-center gap-3 text-gray-400">
                  <span className="text-xl">🎤</span>
                  <span className="text-xl">📷</span>
                </div>
              )}
            </div>
          </div>
        </div>
      ) : (
        <div className="hidden md:flex flex-1 items-center justify-center bg-black rounded-xl">
          <div className="text-center">
            <div className="w-24 h-24 mx-auto mb-4 rounded-full border-2 border-white flex items-center justify-center">
              <MessageCircle size={48} className="text-white" />
            </div>
            <h2 className="text-xl font-light text-white mb-2">Tus mensajes</h2>
            <p className="text-gray-400 text-sm">
              Envía mensajes privados a un amigo o grupo
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
