import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getDashboardOverview,
  getConversations,
  getLeads,
  toggleBot,
  CREATOR_ID,
} from '@/services/api';
import {
  MessageCircle,
  AlertCircle,
  ChevronRight,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { Switch } from '@/components/ui/switch';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';

// Skeleton loaders for fast perceived performance
const DashboardSkeleton = () => (
  <Card className="bg-gradient-to-r from-gray-900 to-gray-800 border-gray-700">
    <CardContent className="p-6">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Skeleton className="w-10 h-10 rounded-full bg-gray-700" />
          <div>
            <Skeleton className="w-24 h-6 bg-gray-700 mb-1" />
            <Skeleton className="w-32 h-4 bg-gray-700" />
          </div>
        </div>
        <Skeleton className="w-12 h-6 rounded-full bg-gray-700" />
      </div>
      <div className="grid grid-cols-3 gap-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="text-center">
            <Skeleton className="w-12 h-8 mx-auto bg-gray-700 mb-1" />
            <Skeleton className="w-16 h-3 mx-auto bg-gray-700" />
          </div>
        ))}
      </div>
    </CardContent>
  </Card>
);

const ConversationsSkeleton = () => (
  <Card className="bg-gray-900 border-gray-800">
    <CardHeader className="pb-3">
      <div className="flex items-center justify-between">
        <Skeleton className="w-48 h-6 bg-gray-700" />
        <Skeleton className="w-16 h-4 bg-gray-700" />
      </div>
    </CardHeader>
    <CardContent className="space-y-2">
      {[1, 2, 3].map((i) => (
        <div key={i} className="flex items-center gap-3 p-3 bg-gray-800/50 rounded-lg">
          <Skeleton className="w-8 h-8 rounded-full bg-gray-700" />
          <div className="flex-1">
            <Skeleton className="w-24 h-4 bg-gray-700 mb-1" />
            <Skeleton className="w-40 h-3 bg-gray-700" />
          </div>
          <Skeleton className="w-8 h-4 bg-gray-700" />
        </div>
      ))}
    </CardContent>
  </Card>
);

export default function Inicio() {
  const creatorId = CREATOR_ID;
  const queryClient = useQueryClient();

  const { data: dashboard, isLoading: loadingDashboard } = useQuery({
    queryKey: ['dashboard', creatorId],
    queryFn: () => getDashboardOverview(creatorId),
  });

  const { data: conversationsData, isLoading: loadingConversations } = useQuery({
    queryKey: ['conversations', creatorId],
    queryFn: () => getConversations(creatorId, 10),
  });

  const { data: leadsData, isLoading: loadingLeads } = useQuery({
    queryKey: ['leads', creatorId],
    queryFn: () => getLeads(creatorId),
  });

  const toggleBotMutation = useMutation({
    mutationFn: (active: boolean) => toggleBot(creatorId, active),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dashboard', creatorId] });
    },
  });

  const config = dashboard?.config;
  const metrics = dashboard?.metrics;
  const recentConversations = conversationsData?.conversations || [];
  const leads = leadsData?.leads || [];
  const hotLeads = leads.filter(
    (lead) => (lead.purchase_intent ?? 0) > 0.7 || lead.is_customer
  );

  const needsSetup =
    !dashboard?.products_count || dashboard.products_count === 0;

  const handleToggleBot = (checked: boolean) => {
    toggleBotMutation.mutate(checked);
  };

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

  return (
    <div className="space-y-6">
      {/* Header: Bot Status - show skeleton while loading */}
      {loadingDashboard ? (
        <DashboardSkeleton />
      ) : (
        <Card className="bg-gradient-to-r from-gray-900 to-gray-800 border-gray-700">
          <CardContent className="p-6">
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-3">
                <span className="text-3xl">🤖</span>
                <div>
                  <h1 className="text-xl font-bold text-white">Tu clon</h1>
                  <p className="text-sm text-gray-400">
                    {dashboard?.clone_active
                      ? 'Respondiendo mensajes'
                      : 'Pausado'}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span
                  className={`w-2 h-2 rounded-full ${dashboard?.clone_active ? 'bg-green-500' : 'bg-gray-500'}`}
                />
                <Switch
                  checked={dashboard?.clone_active ?? false}
                  onCheckedChange={handleToggleBot}
                  disabled={toggleBotMutation.isPending}
                />
              </div>
            </div>

            {/* Metrics */}
            <div className="grid grid-cols-3 gap-4">
              <div className="text-center">
                <div className="text-2xl font-bold text-white">
                  {metrics?.total_messages || 0}
                </div>
                <div className="text-xs text-gray-400">Mensajes</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-white">
                  {metrics?.leads || 0}
                </div>
                <div className="text-xs text-gray-400">Leads</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-white">
                  {metrics?.customers || 0}
                </div>
                <div className="text-xs text-gray-400">Clientes</div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Action Required: Setup */}
      {needsSetup && (
        <Card className="bg-amber-500/10 border-amber-500/30">
          <CardContent className="p-4">
            <div className="flex items-start gap-3">
              <AlertCircle className="text-amber-500 mt-0.5" size={20} />
              <div className="flex-1">
                <p className="text-white font-medium">
                  Completa tu configuración
                </p>
                <p className="text-sm text-gray-400 mt-1">
                  Para que tu clon pueda vender, necesitas:
                </p>
                <div className="flex flex-wrap gap-2 mt-3">
                  {!dashboard?.products_count && (
                    <Link to="/new/ajustes?section=producto">
                      <Button
                        size="sm"
                        variant="outline"
                        className="border-amber-500/50 text-amber-500 hover:bg-amber-500/10"
                      >
                        Añadir producto
                      </Button>
                    </Link>
                  )}
                  <Link to="/new/ajustes?section=pagos">
                    <Button
                      size="sm"
                      variant="outline"
                      className="border-amber-500/50 text-amber-500 hover:bg-amber-500/10"
                    >
                      Añadir método de pago
                    </Button>
                  </Link>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Hot Leads - Need Attention */}
      {hotLeads.length > 0 && (
        <Card className="bg-gray-900 border-gray-800">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-lg flex items-center gap-2">
                <span className="text-orange-500">🔥</span>
                Necesitan tu atención
                <span className="text-sm font-normal text-gray-400">
                  ({hotLeads.length})
                </span>
              </CardTitle>
              <Link
                to="/leads"
                className="text-sm text-purple-500 hover:text-purple-400"
              >
                Ver todos
              </Link>
            </div>
          </CardHeader>
          <CardContent className="space-y-2">
            {hotLeads.slice(0, 3).map((lead) => (
              <Link
                key={lead.follower_id}
                to={`/new/mensajes/${lead.follower_id}`}
                className="flex items-center justify-between p-3 bg-gray-800 rounded-lg hover:bg-gray-750 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center text-white font-medium">
                    {(lead.username || lead.name)?.[0]?.toUpperCase() || '?'}
                  </div>
                  <div>
                    <p className="font-medium text-white">
                      @{lead.username || lead.name || lead.follower_id}
                    </p>
                    <p className="text-sm text-gray-400 truncate max-w-[200px]">
                      {lead.products_discussed?.join(', ') || 'Lead activo'}
                    </p>
                  </div>
                </div>
                <ChevronRight className="text-gray-500" size={20} />
              </Link>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Recent Conversations - skeleton while loading */}
      {loadingConversations ? (
        <ConversationsSkeleton />
      ) : (
        <Card className="bg-gray-900 border-gray-800">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-lg flex items-center gap-2">
                <MessageCircle size={20} className="text-purple-500" />
                Últimas conversaciones
              </CardTitle>
              <Link
                to="/new/mensajes"
                className="text-sm text-purple-500 hover:text-purple-400"
              >
                Ver todas
              </Link>
            </div>
          </CardHeader>
          <CardContent className="space-y-2">
            {recentConversations.length === 0 ? (
              <p className="text-gray-500 text-center py-6">
                Aún no hay conversaciones
              </p>
            ) : (
              recentConversations.slice(0, 5).map((chat) => (
                <Link
                  key={chat.follower_id}
                  to={`/new/mensajes/${chat.follower_id}`}
                  className="flex items-center justify-between p-3 bg-gray-800/50 rounded-lg hover:bg-gray-800 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-gray-700 flex items-center justify-center text-white text-sm">
                      {(chat.username || chat.name)?.[0]?.toUpperCase() || '?'}
                    </div>
                    <div>
                      <p className="text-sm text-white">
                        @{chat.username || chat.name || chat.follower_id}
                      </p>
                      <p className="text-xs text-gray-500 truncate max-w-[200px]">
                        {chat.last_messages?.[0]?.content || 'Sin mensajes'}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-500">
                      {formatTimeAgo(chat.last_contact)}
                    </span>
                    <span className="text-green-500 text-xs">✓</span>
                  </div>
                </Link>
              ))
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
