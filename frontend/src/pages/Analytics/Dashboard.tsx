import { useState } from 'react';
import {
  MessageSquare, Users, Target, DollarSign,
  TrendingUp, Zap, ArrowRight,
  Sparkles, AlertTriangle, RefreshCw
} from 'lucide-react';

import { KPICard } from './components/KPICard';
import { RecommendationCard } from './components/RecommendationCard';
import { HotLeadCard } from './components/HotLeadCard';
import { ChurnRiskCard } from './components/ChurnRiskCard';
import { useIntelligenceDashboard, useGenerateWeeklyReport } from '@/hooks/useIntelligence';
import { getCreatorId } from '@/services/api';
import { useNavigate } from 'react-router-dom';

export default function AnalyticsDashboard() {
  const creatorId = getCreatorId();
  const navigate = useNavigate();
  const [days, setDays] = useState(30);

  const { data, isLoading, isError, error, refetch } = useIntelligenceDashboard(creatorId, days);
  const generateReport = useGenerateWeeklyReport(creatorId);

  if (isLoading) return <DashboardSkeleton />;
  if (isError) return <DashboardError error={error as Error} onRetry={refetch} />;
  if (!data) return null;

  const { patterns, predictions, recommendations, kpis } = data;

  // Extract metrics from patterns
  const metrics = {
    conversations: patterns?.conversation?.avg_messages_per_user || 0,
    new_leads: predictions?.total_hot_leads || 0,
    conversions: 0, // Would come from metrics_summary
    revenue: 0, // Would come from revenue data
    vs_previous: {
      conversations: 0,
      leads: 0,
      conversions: 0,
      revenue: 0
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-indigo-50">
      {/* Header */}
      <header className="bg-white/80 backdrop-blur-sm border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-6 py-5">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
                <Sparkles className="w-6 h-6 text-indigo-600" />
                Intelligence Dashboard
              </h1>
              <p className="text-gray-500 mt-1">
                Analisis predictivo de tu negocio en tiempo real
              </p>
            </div>

            <div className="flex items-center gap-3">
              <select
                value={days}
                onChange={(e) => setDays(Number(e.target.value))}
                className="text-sm border border-gray-200 rounded-lg px-3 py-2"
              >
                <option value={7}>Ultimos 7 dias</option>
                <option value={30}>Ultimos 30 dias</option>
                <option value={90}>Ultimos 90 dias</option>
              </select>
              <button
                onClick={() => refetch()}
                className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                title="Actualizar datos"
              >
                <RefreshCw className="w-5 h-5 text-gray-500" />
              </button>
              <button
                onClick={() => generateReport.mutate()}
                disabled={generateReport.isPending}
                className="px-4 py-2 bg-indigo-600 text-white rounded-xl hover:bg-indigo-700 transition-colors font-medium disabled:opacity-50"
              >
                {generateReport.isPending ? 'Generando...' : 'Generar informe'}
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8">
        {/* KPIs Grid */}
        <section className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5 mb-8">
          <KPICard
            title="Avg Mensajes/Usuario"
            value={patterns?.conversation?.avg_messages_per_user?.toFixed(1) || '0'}
            icon={<MessageSquare className="w-5 h-5" />}
          />
          <KPICard
            title="Leads Calientes"
            value={predictions?.total_hot_leads || 0}
            icon={<Users className="w-5 h-5" />}
            variant={predictions?.total_hot_leads > 0 ? 'success' : 'default'}
          />
          <KPICard
            title="En Riesgo"
            value={predictions?.total_at_risk || 0}
            icon={<Target className="w-5 h-5" />}
            variant={predictions?.total_at_risk > 3 ? 'danger' : 'warning'}
          />
          <KPICard
            title="Forecast Semanal"
            value={predictions?.revenue_forecast?.current_weekly_avg ?
              `$${predictions.revenue_forecast.current_weekly_avg.toLocaleString()}` : '$0'}
            change={predictions?.revenue_forecast?.growth_trend}
            icon={<DollarSign className="w-5 h-5" />}
            variant="success"
          />
        </section>

        {/* Main Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Left Column - Main Content */}
          <div className="lg:col-span-2 space-y-8">
            {/* Hot Leads Section */}
            <section className="bg-white rounded-2xl border border-gray-200 p-6 shadow-sm">
              <div className="flex items-center justify-between mb-6">
                <div>
                  <h2 className="text-lg font-bold text-gray-900 flex items-center gap-2">
                    Leads Calientes
                  </h2>
                  <p className="text-sm text-gray-500 mt-1">
                    Alta probabilidad de conversion
                  </p>
                </div>
                <span className="px-3 py-1.5 bg-emerald-100 text-emerald-700 text-sm font-semibold rounded-full">
                  {predictions?.total_hot_leads || 0} identificados
                </span>
              </div>

              {predictions?.hot_leads && predictions.hot_leads.length > 0 ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {predictions.hot_leads.slice(0, 4).map((lead, i) => (
                    <HotLeadCard
                      key={i}
                      lead={lead}
                      onViewProfile={() => navigate(`/leads?search=${lead.lead_id}`)}
                    />
                  ))}
                </div>
              ) : (
                <div className="text-center py-8 text-gray-500">
                  <Users className="w-12 h-12 mx-auto mb-3 text-gray-300" />
                  <p>No hay leads calientes identificados</p>
                  <p className="text-sm mt-1">Los leads apareceran cuando tengan alta probabilidad de conversion</p>
                </div>
              )}

              {predictions?.hot_leads && predictions.hot_leads.length > 4 && (
                <button
                  onClick={() => navigate('/leads?filter=hot')}
                  className="mt-5 w-full py-3 text-indigo-600 font-semibold hover:bg-indigo-50 rounded-xl transition-colors flex items-center justify-center gap-2"
                >
                  Ver todos los {predictions.total_hot_leads} leads <ArrowRight className="w-4 h-4" />
                </button>
              )}
            </section>

            {/* Recommendations Section */}
            <section className="bg-white rounded-2xl border border-gray-200 p-6 shadow-sm">
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-lg font-bold text-gray-900 flex items-center gap-2">
                  <Zap className="w-5 h-5 text-amber-500" />
                  Recomendaciones
                </h2>
              </div>

              {recommendations && recommendations.length > 0 ? (
                <div className="space-y-4">
                  {recommendations.slice(0, 3).map((rec, i) => (
                    <RecommendationCard key={i} recommendation={rec} />
                  ))}
                </div>
              ) : (
                <div className="text-center py-8 text-gray-500">
                  <Lightbulb className="w-12 h-12 mx-auto mb-3 text-gray-300" />
                  <p>No hay recomendaciones disponibles</p>
                  <p className="text-sm mt-1">Las recomendaciones se generan con mas datos</p>
                </div>
              )}
            </section>
          </div>

          {/* Right Column - Sidebar */}
          <div className="space-y-6">
            {/* Insights Card */}
            <section className="bg-gradient-to-br from-indigo-600 via-indigo-700 to-purple-700 rounded-2xl p-6 text-white shadow-xl">
              <h3 className="font-bold text-lg mb-4 flex items-center gap-2">
                <Sparkles className="w-5 h-5" /> Insights Clave
              </h3>

              <div className="space-y-4">
                {patterns?.temporal?.best_hours?.[0] && (
                  <div className="bg-white/10 backdrop-blur rounded-xl p-4">
                    <p className="text-sm opacity-80">Mejor hora para publicar</p>
                    <p className="font-bold text-2xl">
                      {patterns.temporal.best_hours[0].hour}:00
                    </p>
                    <p className="text-xs opacity-70 mt-1">
                      {patterns.temporal.best_hours[0].users} usuarios activos
                    </p>
                  </div>
                )}

                {patterns?.temporal?.peak_activity_day && (
                  <div className="bg-white/10 backdrop-blur rounded-xl p-4">
                    <p className="text-sm opacity-80">Mejor dia de la semana</p>
                    <p className="font-bold text-2xl">
                      {patterns.temporal.peak_activity_day}
                    </p>
                  </div>
                )}

                {patterns?.conversation?.avg_messages_per_user && (
                  <div className="bg-white/10 backdrop-blur rounded-xl p-4">
                    <p className="text-sm opacity-80">Mensajes promedio por usuario</p>
                    <p className="font-bold text-2xl">
                      ~{Math.round(patterns.conversation.avg_messages_per_user)} msgs
                    </p>
                  </div>
                )}
              </div>
            </section>

            {/* Churn Risks Alert */}
            {predictions?.churn_risks && predictions.churn_risks.length > 0 && (
              <section className="bg-gradient-to-br from-amber-50 to-orange-50 border border-amber-200 rounded-2xl p-6">
                <h3 className="font-bold text-amber-800 mb-4 flex items-center gap-2">
                  <AlertTriangle className="w-5 h-5" />
                  {predictions.total_at_risk} Leads en Riesgo
                </h3>

                <div className="space-y-3">
                  {predictions.churn_risks.slice(0, 2).map((lead, i) => (
                    <ChurnRiskCard
                      key={i}
                      lead={lead}
                      onRecover={() => navigate(`/leads?search=${lead.lead_id}`)}
                    />
                  ))}
                </div>

                <button
                  onClick={() => navigate('/leads?filter=at-risk')}
                  className="mt-4 w-full py-2.5 bg-amber-600 text-white font-semibold rounded-xl hover:bg-amber-700 transition-colors"
                >
                  Ver todos y recuperar
                </button>
              </section>
            )}

            {/* Revenue Forecast */}
            {predictions?.revenue_forecast?.forecasts && predictions.revenue_forecast.forecasts.length > 0 && (
              <section className="bg-white rounded-2xl border border-gray-200 p-6 shadow-sm">
                <h3 className="font-bold text-gray-900 mb-4 flex items-center gap-2">
                  <TrendingUp className="w-5 h-5 text-emerald-600" />
                  Forecast Revenue
                </h3>

                <div className="space-y-3">
                  {predictions.revenue_forecast.forecasts.slice(0, 4).map((forecast, i) => (
                    <div key={i} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                      <span className="text-sm text-gray-600">Semana {forecast.week}</span>
                      <div className="text-right">
                        <span className="font-bold text-gray-900">
                          ${forecast.projected_revenue.toLocaleString()}
                        </span>
                        <span className="text-xs text-gray-400 ml-2">
                          ({(forecast.confidence * 100).toFixed(0)}%)
                        </span>
                      </div>
                    </div>
                  ))}
                </div>

                {predictions.revenue_forecast.growth_trend !== undefined && (
                  <div className="mt-4 p-3 bg-emerald-50 rounded-xl">
                    <p className="text-sm text-emerald-700">
                      <strong>Tendencia:</strong>{' '}
                      {predictions.revenue_forecast.growth_trend >= 0 ? '+' : ''}
                      {predictions.revenue_forecast.growth_trend?.toFixed(1)}% mensual
                    </p>
                  </div>
                )}
              </section>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

// Need to import Lightbulb for the empty state
import { Lightbulb } from 'lucide-react';

function DashboardSkeleton() {
  return (
    <div className="min-h-screen bg-gray-50 animate-pulse">
      <div className="h-20 bg-white border-b" />
      <div className="max-w-7xl mx-auto px-6 py-8">
        <div className="grid grid-cols-4 gap-5 mb-8">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-32 bg-white rounded-2xl" />
          ))}
        </div>
        <div className="grid grid-cols-3 gap-8">
          <div className="col-span-2 space-y-8">
            <div className="h-80 bg-white rounded-2xl" />
            <div className="h-96 bg-white rounded-2xl" />
          </div>
          <div className="space-y-6">
            <div className="h-64 bg-indigo-200 rounded-2xl" />
            <div className="h-48 bg-white rounded-2xl" />
          </div>
        </div>
      </div>
    </div>
  );
}

function DashboardError({ error, onRetry }: { error: Error; onRetry: () => void }) {
  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <div className="text-center p-8">
        <AlertTriangle className="w-16 h-16 text-red-500 mx-auto mb-4" />
        <h2 className="text-xl font-bold text-gray-900">Error al cargar datos</h2>
        <p className="text-gray-500 mt-2">{error.message}</p>
        <button
          onClick={onRetry}
          className="mt-6 px-6 py-3 bg-indigo-600 text-white rounded-xl hover:bg-indigo-700"
        >
          Reintentar
        </button>
      </div>
    </div>
  );
}
