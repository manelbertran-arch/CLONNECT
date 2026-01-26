import { AlertTriangle, Clock, Heart } from 'lucide-react';
import type { ChurnRisk } from '@/services/api';

interface ChurnRiskCardProps {
  lead: ChurnRisk;
  onRecover?: () => void;
}

export function ChurnRiskCard({ lead, onRecover }: ChurnRiskCardProps) {
  const getRiskLevel = (risk: number) => {
    if (risk >= 0.8) return { label: 'Critico', color: 'text-red-600', bg: 'bg-red-100' };
    if (risk >= 0.6) return { label: 'Alto', color: 'text-amber-600', bg: 'bg-amber-100' };
    return { label: 'Moderado', color: 'text-yellow-600', bg: 'bg-yellow-100' };
  };

  const riskLevel = getRiskLevel(lead.churn_risk);

  return (
    <div className="bg-white rounded-xl border border-red-200 p-4 hover:shadow-md transition-all">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-red-100 rounded-full flex items-center justify-center">
            <AlertTriangle className="w-4 h-4 text-red-600" />
          </div>
          <div>
            <p className="font-medium text-gray-900 text-sm">
              {lead.username || lead.lead_id.slice(0, 12)}...
            </p>
            <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${riskLevel.bg} ${riskLevel.color}`}>
              Riesgo {riskLevel.label}
            </span>
          </div>
        </div>

        <span className="text-2xl font-bold text-red-600">
          {(lead.churn_risk * 100).toFixed(0)}%
        </span>
      </div>

      <div className="flex gap-4 text-xs text-gray-500 mb-3">
        <span className="flex items-center gap-1">
          <Clock className="w-3 h-3" />
          {lead.days_inactive} dias inactivo
        </span>
      </div>

      <div className="p-2 bg-amber-50 rounded-lg mb-3">
        <p className="text-xs text-amber-800">
          <strong>Accion:</strong> {lead.recovery_action}
        </p>
      </div>

      {onRecover && (
        <button
          onClick={onRecover}
          className="w-full px-3 py-2 bg-amber-600 text-white text-sm font-medium rounded-lg hover:bg-amber-700 transition-colors flex items-center justify-center gap-2"
        >
          <Heart className="w-4 h-4" /> Recuperar lead
        </button>
      )}
    </div>
  );
}
