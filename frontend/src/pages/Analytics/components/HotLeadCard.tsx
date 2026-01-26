import { TrendingUp, MessageSquare, AlertCircle, Phone } from 'lucide-react';
import type { LeadPrediction } from '@/services/api';

interface HotLeadCardProps {
  lead: LeadPrediction;
  onContact?: () => void;
  onViewProfile?: () => void;
}

export function HotLeadCard({ lead, onContact, onViewProfile }: HotLeadCardProps) {
  const getProbabilityStyle = (prob: number) => {
    if (prob >= 0.8) return { bg: 'bg-emerald-500', text: 'text-white', label: 'Muy alta' };
    if (prob >= 0.6) return { bg: 'bg-emerald-400', text: 'text-white', label: 'Alta' };
    if (prob >= 0.4) return { bg: 'bg-amber-400', text: 'text-gray-900', label: 'Media' };
    return { bg: 'bg-gray-300', text: 'text-gray-700', label: 'Baja' };
  };

  const probStyle = getProbabilityStyle(lead.conversion_probability);

  return (
    <div className="bg-white rounded-2xl border border-gray-200 p-5 hover:shadow-xl transition-all duration-200 group">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-full flex items-center justify-center text-white font-bold text-lg shadow-lg">
            {(lead.username || lead.lead_id).slice(0, 2).toUpperCase()}
          </div>
          <div>
            <p className="font-semibold text-gray-900">
              {lead.username || (lead.lead_id.length > 15 ? `${lead.lead_id.slice(0, 15)}...` : lead.lead_id)}
            </p>
            {lead.status && (
              <span className="text-xs text-gray-500 capitalize">
                {lead.status}
              </span>
            )}
          </div>
        </div>

        {/* Probability Badge */}
        <div className={`px-3 py-1.5 rounded-full font-bold text-lg ${probStyle.bg} ${probStyle.text}`}>
          {(lead.conversion_probability * 100).toFixed(0)}%
        </div>
      </div>

      {/* Metrics Grid */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        <div className="text-center p-3 bg-gray-50 rounded-xl">
          <TrendingUp className="w-4 h-4 mx-auto text-emerald-500 mb-1" />
          <p className="text-xs text-gray-500">Score</p>
          <p className="font-bold text-gray-900">
            {(lead.factors.current_score * 100).toFixed(0)}%
          </p>
        </div>
        <div className="text-center p-3 bg-gray-50 rounded-xl">
          <MessageSquare className="w-4 h-4 mx-auto text-blue-500 mb-1" />
          <p className="text-xs text-gray-500">Mensajes</p>
          <p className="font-bold text-gray-900">
            {lead.factors.engagement_level}
          </p>
        </div>
        <div className="text-center p-3 bg-gray-50 rounded-xl">
          <AlertCircle className={`w-4 h-4 mx-auto mb-1 ${lead.factors.days_since_last_activity > 7 ? 'text-amber-500' : 'text-emerald-500'}`} />
          <p className="text-xs text-gray-500">Dias</p>
          <p className={`font-bold ${lead.factors.days_since_last_activity > 7 ? 'text-amber-600' : 'text-emerald-600'}`}>
            {lead.factors.days_since_last_activity}
          </p>
        </div>
      </div>

      {/* Recommended Action */}
      <div className="p-3 bg-indigo-50 rounded-xl mb-4">
        <p className="text-xs text-indigo-600 font-medium mb-1">Accion recomendada</p>
        <p className="text-sm text-indigo-900">{lead.recommended_action}</p>
      </div>

      {/* Actions */}
      <div className="flex gap-2">
        {onViewProfile && (
          <button
            onClick={onViewProfile}
            className="flex-1 px-4 py-2.5 border border-gray-300 text-gray-700 text-sm font-medium rounded-xl hover:bg-gray-50 transition-colors"
          >
            Ver perfil
          </button>
        )}
        {onContact && (
          <button
            onClick={onContact}
            className="flex-1 px-4 py-2.5 bg-indigo-600 text-white text-sm font-medium rounded-xl hover:bg-indigo-700 transition-colors flex items-center justify-center gap-2"
          >
            <Phone className="w-4 h-4" /> Contactar
          </button>
        )}
      </div>
    </div>
  );
}
