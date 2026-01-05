import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useParams, Link } from 'react-router-dom';
import {
  getConversations,
  getFollowerDetail,
  sendMessage,
  CREATOR_ID,
} from '@/services/api';
import { Search, Send, ArrowLeft, MessageCircle } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';

export default function Mensajes() {
  const { conversationId } = useParams();
  const [search, setSearch] = useState('');
  const [newMessage, setNewMessage] = useState('');
  const creatorId = CREATOR_ID;
  const queryClient = useQueryClient();

  const { data: conversationsData } = useQuery({
    queryKey: ['conversations', creatorId],
    queryFn: () => getConversations(creatorId),
  });

  const { data: followerDetail, isLoading: isLoadingMessages } = useQuery({
    queryKey: ['follower', creatorId, conversationId],
    queryFn: () => getFollowerDetail(creatorId, conversationId!),
    enabled: !!conversationId,
  });

  const sendMessageMutation = useMutation({
    mutationFn: (message: string) =>
      sendMessage(creatorId, conversationId!, message),
    onSuccess: () => {
      setNewMessage('');
      queryClient.invalidateQueries({
        queryKey: ['follower', creatorId, conversationId],
      });
    },
  });

  const conversations = conversationsData?.conversations || [];

  const selectedConversation = conversations.find(
    (c) => c.follower_id === conversationId
  );

  const filteredConversations = conversations.filter((c) =>
    (c.username || c.name || c.follower_id)
      .toLowerCase()
      .includes(search.toLowerCase())
  );

  const messages = followerDetail?.last_messages || [];

  // Format time ago
  const formatTimeAgo = (dateStr?: string) => {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 60) return `${diffMins}m`;
    if (diffHours < 24) return `${diffHours}h`;
    return `${diffDays}d`;
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
    <div className="h-[calc(100vh-8rem)] md:h-[calc(100vh-4rem)] flex flex-col md:flex-row gap-4">
      {/* Conversation List */}
      <div
        className={`
        ${conversationId ? 'hidden md:flex' : 'flex'}
        flex-col w-full md:w-80 bg-gray-900 rounded-xl overflow-hidden
      `}
      >
        {/* Search */}
        <div className="p-3 border-b border-gray-800">
          <div className="relative">
            <Search
              className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500"
              size={18}
            />
            <Input
              placeholder="Buscar..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-10 bg-gray-800 border-gray-700"
            />
          </div>
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
                flex items-center gap-3 p-4 border-b border-gray-800 hover:bg-gray-800 transition-colors
                ${conversationId === conv.follower_id ? 'bg-gray-800' : ''}
              `}
              >
                <div className="w-12 h-12 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center text-white font-medium">
                  {(conv.username || conv.name)?.[0]?.toUpperCase() || '?'}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <p className="font-medium text-white truncate">
                      @{conv.username || conv.name || conv.follower_id}
                    </p>
                    <span className="text-xs text-gray-500">
                      {formatTimeAgo(conv.last_contact)}
                    </span>
                  </div>
                  <p className="text-sm text-gray-400 truncate">
                    {conv.last_messages?.[0]?.content || 'Sin mensajes'}
                  </p>
                </div>
                {(conv.purchase_intent ?? 0) > 0.7 && (
                  <span className="text-orange-500">🔥</span>
                )}
              </Link>
            ))
          )}
        </div>
      </div>

      {/* Conversation Detail */}
      {conversationId ? (
        <div className="flex-1 flex flex-col bg-gray-900 rounded-xl overflow-hidden">
          {/* Header */}
          <div className="flex items-center gap-3 p-4 border-b border-gray-800">
            <Link to="/new/mensajes" className="md:hidden">
              <ArrowLeft className="text-gray-400" />
            </Link>
            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center text-white font-medium">
              {(
                selectedConversation?.username ||
                selectedConversation?.name ||
                followerDetail?.username
              )?.[0]?.toUpperCase() || '?'}
            </div>
            <div>
              <p className="font-medium text-white">
                @
                {selectedConversation?.username ||
                  selectedConversation?.name ||
                  followerDetail?.username ||
                  conversationId}
              </p>
              <p className="text-xs text-gray-400">
                {selectedConversation?.platform || followerDetail?.platform || 'instagram'} ·{' '}
                {(selectedConversation?.purchase_intent ?? 0) > 0.7
                  ? '🔥 Hot lead'
                  : 'Activo'}
              </p>
            </div>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {isLoadingMessages ? (
              <div className="flex items-center justify-center h-full">
                <div className="text-gray-500">Cargando mensajes...</div>
              </div>
            ) : messages.length === 0 ? (
              <div className="flex items-center justify-center h-full">
                <div className="text-gray-500">No hay mensajes</div>
              </div>
            ) : (
              messages.map((msg, i) => (
                <div
                  key={i}
                  className={`flex ${msg.role === 'assistant' ? 'justify-start' : 'justify-end'}`}
                >
                  <div
                    className={`
                    max-w-[80%] p-3 rounded-2xl
                    ${
                      msg.role === 'assistant'
                        ? 'bg-gray-800 text-white rounded-bl-md'
                        : 'bg-purple-500 text-white rounded-br-md'
                    }
                  `}
                  >
                    {msg.role === 'assistant' && (
                      <span className="text-xs text-gray-400 block mb-1">
                        🤖 Tu clon
                      </span>
                    )}
                    <p>{msg.content}</p>
                    <span className="text-xs opacity-60 mt-1 block text-right">
                      {new Date(msg.timestamp).toLocaleTimeString('es', {
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Input */}
          <div className="p-4 border-t border-gray-800">
            <div className="flex gap-2">
              <Input
                placeholder="Escribe un mensaje..."
                value={newMessage}
                onChange={(e) => setNewMessage(e.target.value)}
                onKeyDown={handleKeyPress}
                className="flex-1 bg-gray-800 border-gray-700"
              />
              <Button
                onClick={handleSendMessage}
                disabled={!newMessage.trim() || sendMessageMutation.isPending}
                className="bg-purple-500 hover:bg-purple-600"
              >
                <Send size={18} />
              </Button>
            </div>
            <p className="text-xs text-gray-500 mt-2 text-center">
              💡 El bot está pausado mientras escribes
            </p>
          </div>
        </div>
      ) : (
        <div className="hidden md:flex flex-1 items-center justify-center bg-gray-900 rounded-xl">
          <div className="text-center text-gray-500">
            <MessageCircle size={48} className="mx-auto mb-4 opacity-50" />
            <p>Selecciona una conversación</p>
          </div>
        </div>
      )}
    </div>
  );
}
