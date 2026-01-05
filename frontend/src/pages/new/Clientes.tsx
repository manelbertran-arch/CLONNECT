import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getLeads, CREATOR_ID } from '@/services/api';
import { Search } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Link } from 'react-router-dom';

type FilterType = 'all' | 'hot' | 'interested' | 'customer';

export default function Clientes() {
  const [filter, setFilter] = useState<FilterType>('all');
  const [search, setSearch] = useState('');
  const creatorId = CREATOR_ID;

  const { data: leadsData, isLoading } = useQuery({
    queryKey: ['leads', creatorId],
    queryFn: () => getLeads(creatorId),
  });

  const leads = leadsData?.leads || [];

  // Filter leads based on selected filter
  const filteredByStatus = leads.filter((lead) => {
    if (filter === 'all') return true;
    if (filter === 'hot') return (lead.purchase_intent ?? 0) > 0.7;
    if (filter === 'interested')
      return (lead.purchase_intent ?? 0) > 0.3 && (lead.purchase_intent ?? 0) <= 0.7;
    if (filter === 'customer') return lead.is_customer;
    return true;
  });

  // Further filter by search
  const filteredLeads = filteredByStatus.filter((lead) =>
    (lead.username || lead.name || lead.follower_id)
      .toLowerCase()
      .includes(search.toLowerCase())
  );

  const getStatusBadge = (lead: typeof leads[0]) => {
    if (lead.is_customer) {
      return (
        <span className="px-2 py-1 bg-green-500/20 text-green-500 text-xs rounded-full">
          Compró
        </span>
      );
    }
    if ((lead.purchase_intent ?? 0) > 0.7) {
      return (
        <span className="px-2 py-1 bg-orange-500/20 text-orange-500 text-xs rounded-full">
          🔥 Hot
        </span>
      );
    }
    if ((lead.purchase_intent ?? 0) > 0.3) {
      return (
        <span className="px-2 py-1 bg-blue-500/20 text-blue-500 text-xs rounded-full">
          Interesado
        </span>
      );
    }
    return (
      <span className="px-2 py-1 bg-gray-500/20 text-gray-500 text-xs rounded-full">
        Nuevo
      </span>
    );
  };

  // Format time ago
  const formatTimeAgo = (dateStr?: string) => {
    if (!dateStr) return 'N/A';
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 60) return `hace ${diffMins}m`;
    if (diffHours < 24) return `hace ${diffHours}h`;
    return `hace ${diffDays}d`;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">Clientes</h1>
        <p className="text-gray-400">
          Personas que han interactuado con tu clon
        </p>
      </div>

      {/* Search */}
      <div className="relative">
        <Search
          className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500"
          size={18}
        />
        <Input
          placeholder="Buscar por nombre..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="pl-10 bg-gray-900 border-gray-800"
        />
      </div>

      {/* Filters */}
      <div className="flex gap-2 overflow-x-auto pb-2">
        {[
          { id: 'all' as FilterType, label: 'Todos' },
          { id: 'hot' as FilterType, label: '🔥 Hot' },
          { id: 'interested' as FilterType, label: 'Interesados' },
          { id: 'customer' as FilterType, label: '✅ Compraron' },
        ].map((f) => (
          <button
            key={f.id}
            onClick={() => setFilter(f.id)}
            className={`
              px-4 py-2 rounded-full text-sm whitespace-nowrap transition-colors
              ${
                filter === f.id
                  ? 'bg-purple-500 text-white'
                  : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
              }
            `}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* List */}
      <div className="space-y-3">
        {isLoading ? (
          <div className="text-center py-12 text-gray-500">
            <p>Cargando clientes...</p>
          </div>
        ) : filteredLeads.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            <p>No hay clientes en esta categoría</p>
          </div>
        ) : (
          filteredLeads.map((lead) => (
            <Link
              key={lead.follower_id}
              to={`/new/mensajes/${lead.follower_id}`}
              className="block bg-gray-900 rounded-xl p-4 hover:bg-gray-800 transition-colors"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center text-white font-medium">
                    {(lead.username || lead.name)?.[0]?.toUpperCase() || '?'}
                  </div>
                  <div>
                    <p className="font-medium text-white">
                      @{lead.username || lead.name || lead.follower_id}
                    </p>
                    <p className="text-sm text-gray-400">
                      {lead.platform || 'instagram'}
                    </p>
                  </div>
                </div>
                {getStatusBadge(lead)}
              </div>

              {lead.products_discussed && lead.products_discussed.length > 0 && (
                <p className="text-sm text-gray-500 mt-3 truncate">
                  Interesado en: {lead.products_discussed.join(', ')}
                </p>
              )}

              <div className="flex items-center justify-between mt-3 text-xs text-gray-500">
                <span>{lead.total_messages} mensajes</span>
                <span>Último: {formatTimeAgo(lead.last_contact)}</span>
              </div>

              {lead.is_customer && (
                <div className="mt-3 pt-3 border-t border-gray-800">
                  <p className="text-sm text-green-500">
                    ✅ Cliente confirmado
                  </p>
                </div>
              )}
            </Link>
          ))
        )}
      </div>
    </div>
  );
}
