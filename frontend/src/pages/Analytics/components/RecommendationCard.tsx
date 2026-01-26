import { Lightbulb, Zap, Package, Target, Clock, ArrowRight, Sparkles } from 'lucide-react';
import type { Recommendation } from '@/services/api';

interface RecommendationCardProps {
  recommendation: Recommendation;
  onAction?: () => void;
  compact?: boolean;
}

const categoryConfig: Record<string, { icon: typeof Lightbulb; color: string; bg: string }> = {
  content: { icon: Lightbulb, color: 'text-purple-600', bg: 'bg-purple-100' },
  action: { icon: Zap, color: 'text-amber-600', bg: 'bg-amber-100' },
  product: { icon: Package, color: 'text-blue-600', bg: 'bg-blue-100' },
  pricing: { icon: Target, color: 'text-green-600', bg: 'bg-green-100' },
  timing: { icon: Clock, color: 'text-indigo-600', bg: 'bg-indigo-100' }
};

const priorityConfig: Record<string, { border: string; bg: string; badge: string; label: string }> = {
  high: {
    border: 'border-l-red-500',
    bg: 'bg-red-50',
    badge: 'bg-red-100 text-red-700',
    label: 'Alta prioridad'
  },
  medium: {
    border: 'border-l-amber-500',
    bg: 'bg-amber-50',
    badge: 'bg-amber-100 text-amber-700',
    label: 'Media'
  },
  low: {
    border: 'border-l-blue-500',
    bg: 'bg-blue-50',
    badge: 'bg-blue-100 text-blue-700',
    label: 'Sugerencia'
  }
};

export function RecommendationCard({ recommendation, onAction, compact = false }: RecommendationCardProps) {
  const { icon: Icon, color, bg } = categoryConfig[recommendation.category] || categoryConfig.content;
  const priority = priorityConfig[recommendation.priority] || priorityConfig.medium;

  if (compact) {
    return (
      <div className={`rounded-xl p-4 border-l-4 transition-all hover:shadow-md ${priority.border} ${priority.bg}`}>
        <div className="flex items-start gap-3">
          <div className={`p-1.5 rounded-lg ${bg}`}>
            <Icon className={`w-4 h-4 ${color}`} />
          </div>
          <div className="flex-1 min-w-0">
            <h4 className="font-semibold text-gray-900 text-sm truncate">
              {recommendation.title}
            </h4>
            <p className="text-xs text-gray-600 mt-0.5 line-clamp-2">
              {recommendation.description}
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`rounded-xl p-5 border-l-4 transition-all hover:shadow-lg ${priority.border} ${priority.bg}`}>
      <div className="flex items-start gap-4">
        <div className={`p-2.5 rounded-xl shadow-sm ${bg}`}>
          <Icon className={`w-5 h-5 ${color}`} />
        </div>

        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${priority.badge}`}>
              {priority.label}
            </span>
            <span className="text-xs text-gray-400 uppercase tracking-wide">
              {recommendation.category}
            </span>
          </div>

          <h3 className="font-bold text-gray-900 text-lg mb-1">
            {recommendation.title}
          </h3>

          <p className="text-gray-600 mb-3">
            {recommendation.description}
          </p>

          {recommendation.reasoning && (
            <div className="flex items-start gap-2 p-3 bg-white/50 rounded-lg mb-3">
              <Sparkles className="w-4 h-4 text-purple-500 mt-0.5 flex-shrink-0" />
              <p className="text-sm text-gray-600 italic">
                {recommendation.reasoning}
              </p>
            </div>
          )}

          {recommendation.expected_impact && Object.keys(recommendation.expected_impact).length > 0 && (
            <div className="flex flex-wrap gap-2 mb-4">
              {Object.entries(recommendation.expected_impact).map(([key, value]) => (
                <span
                  key={key}
                  className="px-3 py-1.5 bg-white rounded-lg text-sm text-gray-700 shadow-sm"
                >
                  <span className="text-gray-500">
                    {key.replace(/_/g, ' ')}:
                  </span>{' '}
                  <strong className="text-gray-900">{value}</strong>
                </span>
              ))}
            </div>
          )}

          {recommendation.action_data && (
            <div className="p-3 bg-white rounded-lg border border-gray-200 mb-4">
              <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">
                Sugerencia
              </p>
              {recommendation.action_data.suggested_format && (
                <p className="text-sm text-gray-700">
                  <strong>Formato:</strong> {recommendation.action_data.suggested_format}
                </p>
              )}
              {recommendation.action_data.suggested_hook && (
                <p className="text-sm text-gray-700 mt-1">
                  <strong>Hook:</strong> "{recommendation.action_data.suggested_hook}"
                </p>
              )}
            </div>
          )}

          {onAction && (
            <button
              onClick={onAction}
              className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-sm font-semibold rounded-lg hover:bg-indigo-700 transition-colors"
            >
              Tomar accion <ArrowRight className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
