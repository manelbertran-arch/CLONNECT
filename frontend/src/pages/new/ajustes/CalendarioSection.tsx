import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Plus, Trash2, Check, ExternalLink, Clock, Save } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import {
  getBookingLinks,
  createBookingLink,
  deleteBookingLink,
  getConnections,
  startOAuth,
  getAvailability,
  setAvailability,
  CREATOR_ID,
  DayAvailability,
} from '@/services/api';
import { toast } from 'sonner';

interface Props {
  onBack: () => void;
}

const DAY_NAMES_ES = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'];

// Generate time options from 00:00 to 23:30 in 30min intervals
const TIME_OPTIONS = Array.from({ length: 48 }, (_, i) => {
  const hours = Math.floor(i / 2);
  const minutes = (i % 2) * 30;
  return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}`;
});

// Default availability: Mon-Fri 9:00-18:00
const DEFAULT_AVAILABILITY: DayAvailability[] = [
  { day_of_week: 0, start_time: '09:00', end_time: '18:00', is_active: true },
  { day_of_week: 1, start_time: '09:00', end_time: '18:00', is_active: true },
  { day_of_week: 2, start_time: '09:00', end_time: '18:00', is_active: true },
  { day_of_week: 3, start_time: '09:00', end_time: '18:00', is_active: true },
  { day_of_week: 4, start_time: '09:00', end_time: '18:00', is_active: true },
  { day_of_week: 5, start_time: '09:00', end_time: '18:00', is_active: false },
  { day_of_week: 6, start_time: '09:00', end_time: '18:00', is_active: false },
];

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

  // Availability state
  const [availability, setLocalAvailability] = useState<DayAvailability[]>(DEFAULT_AVAILABILITY);
  const [availabilityChanged, setAvailabilityChanged] = useState(false);
  const [savingAvailability, setSavingAvailability] = useState(false);

  // Fetch availability
  const { data: availabilityData, isLoading: loadingAvailability } = useQuery({
    queryKey: ['availability', creatorId],
    queryFn: () => getAvailability(creatorId),
  });

  // Update local state when data loads
  useEffect(() => {
    if (availabilityData?.availability) {
      // Merge with defaults to ensure all 7 days exist
      const merged = DEFAULT_AVAILABILITY.map((defaultDay) => {
        const savedDay = availabilityData.availability.find(
          (d) => d.day_of_week === defaultDay.day_of_week
        );
        return savedDay || defaultDay;
      });
      setLocalAvailability(merged);
    }
  }, [availabilityData]);

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

  // Availability handlers
  const handleDayToggle = (dayIndex: number) => {
    setLocalAvailability((prev) =>
      prev.map((day) =>
        day.day_of_week === dayIndex ? { ...day, is_active: !day.is_active } : day
      )
    );
    setAvailabilityChanged(true);
  };

  const handleTimeChange = (dayIndex: number, field: 'start_time' | 'end_time', value: string) => {
    setLocalAvailability((prev) =>
      prev.map((day) =>
        day.day_of_week === dayIndex ? { ...day, [field]: value } : day
      )
    );
    setAvailabilityChanged(true);
  };

  const handleSaveAvailability = async () => {
    setSavingAvailability(true);
    try {
      await setAvailability(creatorId, availability);
      toast.success('Horarios guardados correctamente');
      setAvailabilityChanged(false);
      queryClient.invalidateQueries({ queryKey: ['availability', creatorId] });
    } catch (error) {
      console.error('Error saving availability:', error);
      toast.error('Error al guardar los horarios');
    } finally {
      setSavingAvailability(false);
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

      {/* ========== AVAILABILITY SECTION ========== */}
      <div className="border-t border-gray-800 pt-4">
        <div className="flex items-center gap-2 mb-4">
          <Clock className="text-purple-400" size={20} />
          <h2 className="font-medium text-white">Horarios de disponibilidad</h2>
        </div>
        <p className="text-sm text-gray-400 mb-4">
          Define cuándo estás disponible para llamadas. Por defecto: L-V 9:00-18:00
        </p>

        {loadingAvailability ? (
          <p className="text-gray-500 text-center py-4">Cargando...</p>
        ) : (
          <div className="space-y-3">
            {availability.map((day) => (
              <div
                key={day.day_of_week}
                className={`flex items-center gap-4 p-3 rounded-lg transition-colors ${
                  day.is_active ? 'bg-gray-800' : 'bg-gray-900/50'
                }`}
              >
                {/* Day toggle */}
                <div className="flex items-center gap-3 w-28">
                  <Switch
                    checked={day.is_active}
                    onCheckedChange={() => handleDayToggle(day.day_of_week)}
                  />
                  <span className={`text-sm font-medium ${day.is_active ? 'text-white' : 'text-gray-500'}`}>
                    {DAY_NAMES_ES[day.day_of_week]}
                  </span>
                </div>

                {/* Time selectors */}
                <div className={`flex items-center gap-2 flex-1 ${!day.is_active && 'opacity-40'}`}>
                  <select
                    value={day.start_time}
                    onChange={(e) => handleTimeChange(day.day_of_week, 'start_time', e.target.value)}
                    disabled={!day.is_active}
                    className="bg-gray-700 border border-gray-600 rounded-md px-2 py-1 text-sm text-white"
                  >
                    {TIME_OPTIONS.map((time) => (
                      <option key={time} value={time}>{time}</option>
                    ))}
                  </select>
                  <span className="text-gray-400 text-sm">hasta</span>
                  <select
                    value={day.end_time}
                    onChange={(e) => handleTimeChange(day.day_of_week, 'end_time', e.target.value)}
                    disabled={!day.is_active}
                    className="bg-gray-700 border border-gray-600 rounded-md px-2 py-1 text-sm text-white"
                  >
                    {TIME_OPTIONS.map((time) => (
                      <option key={time} value={time}>{time}</option>
                    ))}
                  </select>
                </div>
              </div>
            ))}

            {/* Save button */}
            <Button
              onClick={handleSaveAvailability}
              disabled={!availabilityChanged || savingAvailability}
              className={`w-full mt-4 ${
                availabilityChanged
                  ? 'bg-purple-500 hover:bg-purple-600'
                  : 'bg-gray-700 text-gray-400'
              }`}
            >
              <Save className="mr-2" size={18} />
              {savingAvailability ? 'Guardando...' : 'Guardar horarios'}
            </Button>
          </div>
        )}
      </div>

      {/* ========== BOOKING LINKS SECTION ========== */}
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
