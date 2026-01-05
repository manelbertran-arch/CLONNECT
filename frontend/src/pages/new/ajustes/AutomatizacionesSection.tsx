import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Zap, ChevronRight } from 'lucide-react';
import { Switch } from '@/components/ui/switch';
import {
  getNurturingSequences,
  toggleNurturingSequence,
  CREATOR_ID,
} from '@/services/api';

interface Props {
  onBack: () => void;
}

export default function AutomatizacionesSection({ onBack }: Props) {
  const creatorId = CREATOR_ID;
  const queryClient = useQueryClient();

  const { data: sequencesData, isLoading } = useQuery({
    queryKey: ['nurturingSequences', creatorId],
    queryFn: () => getNurturingSequences(creatorId),
  });

  const toggleMutation = useMutation({
    mutationFn: (sequenceType: string) =>
      toggleNurturingSequence(creatorId, sequenceType),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['nurturingSequences', creatorId] });
    },
  });

  const sequences = sequencesData?.sequences || [];
  const stats = sequencesData?.stats;

  const getSequenceInfo = (type: string) => {
    switch (type) {
      case 'welcome':
        return {
          title: 'Bienvenida',
          description: 'Mensaje automático al primer contacto',
          icon: '👋',
        };
      case 'follow_up':
        return {
          title: 'Follow-up',
          description: 'Recordatorio si no responden',
          icon: '🔔',
        };
      case 'abandoned_cart':
        return {
          title: 'Carrito abandonado',
          description: 'Si muestran interés pero no compran',
          icon: '🛒',
        };
      case 'post_purchase':
        return {
          title: 'Post-compra',
          description: 'Seguimiento después de comprar',
          icon: '🎉',
        };
      default:
        return {
          title: type,
          description: 'Secuencia automatizada',
          icon: '⚡',
        };
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <button onClick={onBack}>
          <ArrowLeft className="text-gray-400" />
        </button>
        <h1 className="text-xl font-bold text-white">Automatizaciones</h1>
      </div>

      <p className="text-gray-400 text-sm">
        Secuencias automáticas para nutrir leads y cerrar ventas.
      </p>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-gray-900 rounded-xl p-4 text-center">
            <div className="text-2xl font-bold text-white">{stats.total_sent || 0}</div>
            <div className="text-xs text-gray-400">Enviados</div>
          </div>
          <div className="bg-gray-900 rounded-xl p-4 text-center">
            <div className="text-2xl font-bold text-white">{stats.pending || 0}</div>
            <div className="text-xs text-gray-400">Pendientes</div>
          </div>
          <div className="bg-gray-900 rounded-xl p-4 text-center">
            <div className="text-2xl font-bold text-white">{stats.active_sequences || 0}</div>
            <div className="text-xs text-gray-400">Activas</div>
          </div>
        </div>
      )}

      {/* Sequences */}
      {isLoading ? (
        <p className="text-gray-500 text-center py-4">Cargando...</p>
      ) : sequences.length === 0 ? (
        <div className="space-y-3">
          {/* Default sequences when none exist */}
          {['welcome', 'follow_up', 'abandoned_cart', 'post_purchase'].map((type) => {
            const info = getSequenceInfo(type);
            return (
              <div
                key={type}
                className="bg-gray-900 rounded-xl p-4 border border-gray-800"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">{info.icon}</span>
                    <div>
                      <h3 className="font-medium text-white">{info.title}</h3>
                      <p className="text-sm text-gray-400">{info.description}</p>
                    </div>
                  </div>
                  <Switch
                    checked={false}
                    onCheckedChange={() => toggleMutation.mutate(type)}
                    disabled={toggleMutation.isPending}
                  />
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="space-y-3">
          {sequences.map((sequence: any) => {
            const info = getSequenceInfo(sequence.sequence_type);
            return (
              <div
                key={sequence.sequence_type}
                className="bg-gray-900 rounded-xl p-4 border border-gray-800"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">{info.icon}</span>
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="font-medium text-white">{info.title}</h3>
                        {sequence.enrolled_count > 0 && (
                          <span className="px-2 py-0.5 bg-purple-500/20 text-purple-500 text-xs rounded-full">
                            {sequence.enrolled_count} activos
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-gray-400">{info.description}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <Switch
                      checked={sequence.is_active}
                      onCheckedChange={() =>
                        toggleMutation.mutate(sequence.sequence_type)
                      }
                      disabled={toggleMutation.isPending}
                    />
                  </div>
                </div>

                {/* Steps preview */}
                {sequence.steps && sequence.steps.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-gray-800">
                    <p className="text-xs text-gray-500 mb-2">
                      {sequence.steps.length} pasos configurados
                    </p>
                    <div className="space-y-1">
                      {sequence.steps.slice(0, 2).map((step: any, i: number) => (
                        <p key={i} className="text-xs text-gray-400 truncate">
                          {i + 1}. {step.message?.slice(0, 50)}...
                        </p>
                      ))}
                      {sequence.steps.length > 2 && (
                        <p className="text-xs text-gray-500">
                          +{sequence.steps.length - 2} más
                        </p>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
        <p className="text-sm text-gray-400">
          💡 <strong className="text-white">Tip:</strong> Activa el follow-up para
          recuperar leads que no responden. Se envía automáticamente después de 24h
          sin respuesta.
        </p>
      </div>
    </div>
  );
}
