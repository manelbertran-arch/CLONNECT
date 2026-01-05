import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Plus, Trash2, Check, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  getBookingLinks,
  createBookingLink,
  deleteBookingLink,
  getConnections,
  startOAuth,
  CREATOR_ID,
} from '@/services/api';

interface Props {
  onBack: () => void;
}

export default function CalendarioSection({ onBack }: Props) {
  const creatorId = CREATOR_ID;
  const queryClient = useQueryClient();
  const [isCreating, setIsCreating] = useState(false);
  const [formData, setFormData] = useState({
    meeting_type: '',
    title: '',
    url: '',
    duration_minutes: '30',
    description: '',
  });

  const { data: linksData, isLoading } = useQuery({
    queryKey: ['bookingLinks', creatorId],
    queryFn: () => getBookingLinks(creatorId),
  });

  const { data: connections } = useQuery({
    queryKey: ['connections', creatorId],
    queryFn: () => getConnections(creatorId),
  });

  const createLinkMutation = useMutation({
    mutationFn: (data: {
      meeting_type: string;
      title: string;
      url?: string;
      platform: string;
      duration_minutes: number;
      description?: string;
    }) => createBookingLink(creatorId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bookingLinks', creatorId] });
      resetForm();
    },
  });

  const deleteLinkMutation = useMutation({
    mutationFn: (id: string) => deleteBookingLink(creatorId, id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bookingLinks', creatorId] });
    },
  });

  const links = linksData?.links || [];
  const calendlyConnected = connections?.calendly?.connected;

  const resetForm = () => {
    setIsCreating(false);
    setFormData({
      meeting_type: '',
      title: '',
      url: '',
      duration_minutes: '30',
      description: '',
    });
  };

  const handleConnectCalendly = async () => {
    try {
      const { auth_url } = await startOAuth('calendly', creatorId);
      window.open(auth_url, '_blank');
    } catch (error) {
      console.error('OAuth error:', error);
    }
  };

  const handleCreate = () => {
    createLinkMutation.mutate({
      meeting_type: formData.meeting_type || formData.title.toLowerCase().replace(/\s+/g, '_'),
      title: formData.title,
      url: formData.url || undefined,
      platform: calendlyConnected ? 'calendly' : 'manual',
      duration_minutes: parseInt(formData.duration_minutes) || 30,
      description: formData.description || undefined,
    });
  };

  const handleDelete = (id: string) => {
    if (confirm('¿Seguro que quieres eliminar este tipo de llamada?')) {
      deleteLinkMutation.mutate(id);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <button onClick={onBack}>
          <ArrowLeft className="text-gray-400" />
        </button>
        <h1 className="text-xl font-bold text-white">Calendario</h1>
      </div>

      {/* Calendly Connection */}
      <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-2xl">📅</span>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-medium text-white">Calendly</h3>
                {calendlyConnected && (
                  <Check className="text-green-500" size={16} />
                )}
              </div>
              <p className="text-sm text-gray-400">
                {calendlyConnected
                  ? 'Conectado - sincroniza automáticamente'
                  : 'Conecta para sincronizar citas'}
              </p>
            </div>
          </div>
          {!calendlyConnected && (
            <Button
              size="sm"
              onClick={handleConnectCalendly}
              className="bg-purple-500 hover:bg-purple-600"
            >
              Conectar
            </Button>
          )}
        </div>
      </div>

      <div className="border-t border-gray-800 pt-4">
        <h2 className="font-medium text-white mb-4">Tipos de llamada</h2>

        {isLoading ? (
          <p className="text-gray-500 text-center py-4">Cargando...</p>
        ) : !isCreating ? (
          <>
            <div className="space-y-3">
              {links.length === 0 ? (
                <p className="text-gray-500 text-center py-4">
                  No hay tipos de llamada configurados
                </p>
              ) : (
                links.map((link) => (
                  <div
                    key={link.id || link.meeting_type}
                    className="bg-gray-800 rounded-lg p-4"
                  >
                    <div className="flex items-start justify-between">
                      <div>
                        <h3 className="font-medium text-white">{link.title}</h3>
                        <p className="text-sm text-gray-400">
                          {link.duration_minutes} min · {link.platform}
                        </p>
                        {link.description && (
                          <p className="text-sm text-gray-500 mt-1">
                            {link.description}
                          </p>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        {link.url && (
                          <a
                            href={link.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="p-2 text-gray-400 hover:text-white transition-colors"
                          >
                            <ExternalLink size={18} />
                          </a>
                        )}
                        <button
                          onClick={() => handleDelete(link.id || '')}
                          className="p-2 text-gray-400 hover:text-red-500 transition-colors"
                        >
                          <Trash2 size={18} />
                        </button>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>

            <Button
              onClick={() => setIsCreating(true)}
              className="w-full mt-4 bg-purple-500 hover:bg-purple-600"
            >
              <Plus className="mr-2" size={18} />
              Añadir tipo de llamada
            </Button>
          </>
        ) : (
          <div className="space-y-4">
            <div>
              <label className="text-sm text-gray-400 block mb-2">Título</label>
              <Input
                placeholder="Ej: Llamada de descubrimiento"
                value={formData.title}
                onChange={(e) =>
                  setFormData({ ...formData, title: e.target.value })
                }
                className="bg-gray-800 border-gray-700"
              />
            </div>

            <div>
              <label className="text-sm text-gray-400 block mb-2">
                Duración (minutos)
              </label>
              <Input
                type="number"
                placeholder="30"
                value={formData.duration_minutes}
                onChange={(e) =>
                  setFormData({ ...formData, duration_minutes: e.target.value })
                }
                className="bg-gray-800 border-gray-700"
              />
            </div>

            {!calendlyConnected && (
              <div>
                <label className="text-sm text-gray-400 block mb-2">
                  URL de reserva (opcional)
                </label>
                <Input
                  placeholder="https://calendly.com/..."
                  value={formData.url}
                  onChange={(e) =>
                    setFormData({ ...formData, url: e.target.value })
                  }
                  className="bg-gray-800 border-gray-700"
                />
              </div>
            )}

            <div>
              <label className="text-sm text-gray-400 block mb-2">
                Descripción (opcional)
              </label>
              <Input
                placeholder="Descripción breve..."
                value={formData.description}
                onChange={(e) =>
                  setFormData({ ...formData, description: e.target.value })
                }
                className="bg-gray-800 border-gray-700"
              />
            </div>

            <div className="flex gap-3">
              <Button
                variant="outline"
                onClick={resetForm}
                className="flex-1 border-gray-700"
              >
                Cancelar
              </Button>
              <Button
                onClick={handleCreate}
                disabled={!formData.title || createLinkMutation.isPending}
                className="flex-1 bg-purple-500 hover:bg-purple-600"
              >
                Crear
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
