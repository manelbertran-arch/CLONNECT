import { useState } from 'react';
import {
  MessageSquare, Users, Target, DollarSign,
  TrendingUp, Zap, ArrowRight, ChevronRight,
  Sparkles, AlertTriangle, RefreshCw, Loader2, AlertCircle, Lightbulb
} from 'lucide-react';

import { useIntelligenceDashboard, useGenerateWeeklyReport } from '@/hooks/useIntelligence';
import { getCreatorId } from '@/services/api';
import { useNavigate, Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export default function AnalyticsDashboard() {
  const creatorId = getCreatorId();
  const navigate = useNavigate();
  const [days, setDays] = useState(30);

  const { data, isLoading, isError, error, refetch } = useIntelligenceDashboard(creatorId, days);
  const generateReport = useGenerateWeeklyReport(creatorId);

  if (isLoading) return <DashboardSkeleton />;
  if (isError) return <DashboardError error={error as Error} onRetry={refetch} />;
  if (!data) return null;

  const { patterns, predictions, recommendations } = data;

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-muted-foreground mb-1">Business Intelligence</p>
          <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-primary" />
            Analytics
          </h1>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="text-sm border border-border/50 rounded-lg px-3 py-2 bg-card"
          >
            <option value={7}>7 dias</option>
            <option value={30}>30 dias</option>
            <option value={90}>90 dias</option>
          </select>
          <Button
            variant="outline"
            size="sm"
            onClick={() => refetch()}
            className="h-9 px-3"
          >
            <RefreshCw className="w-4 h-4" />
          </Button>
          <Button
            size="sm"
            onClick={() => generateReport.mutate()}
            disabled={generateReport.isPending}
            className="h-9"
          >
            {generateReport.isPending ? 'Generando...' : 'Generar informe'}
          </Button>
        </div>
      </div>

      {/* Main KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Avg Messages */}
        <div className="p-5 rounded-2xl bg-card border border-border/50">
          <div className="flex items-center gap-2 mb-3">
            <MessageSquare className="w-4 h-4 text-muted-foreground" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Avg Msgs/Usuario</span>
          </div>
          <span className="text-2xl font-semibold">
            {patterns?.conversation?.avg_messages_per_user?.toFixed(1) || '0'}
          </span>
        </div>

        {/* Hot Leads */}
        <div className={cn(
          "p-5 rounded-2xl border",
          predictions?.total_hot_leads > 0
            ? "bg-gradient-to-br from-emerald-500/10 via-emerald-500/5 to-transparent border-emerald-500/20"
            : "bg-card border-border/50"
        )}>
          <div className="flex items-center gap-2 mb-3">
            <Zap className={cn("w-4 h-4", predictions?.total_hot_leads > 0 ? "text-emerald-500" : "text-muted-foreground")} />
            <span className={cn(
              "text-xs font-medium uppercase tracking-wide",
              predictions?.total_hot_leads > 0 ? "text-emerald-500/80" : "text-muted-foreground"
            )}>Leads Calientes</span>
          </div>
          <span className="text-2xl font-semibold">{predictions?.total_hot_leads || 0}</span>
        </div>

        {/* At Risk */}
        <div className={cn(
          "p-5 rounded-2xl border",
          predictions?.total_at_risk > 3
            ? "bg-gradient-to-br from-rose-500/10 via-rose-500/5 to-transparent border-rose-500/20"
            : predictions?.total_at_risk > 0
            ? "bg-gradient-to-br from-amber-500/10 via-amber-500/5 to-transparent border-amber-500/20"
            : "bg-card border-border/50"
        )}>
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle className={cn(
              "w-4 h-4",
              predictions?.total_at_risk > 3 ? "text-rose-500" : predictions?.total_at_risk > 0 ? "text-amber-500" : "text-muted-foreground"
            )} />
            <span className={cn(
              "text-xs font-medium uppercase tracking-wide",
              predictions?.total_at_risk > 3 ? "text-rose-500/80" : predictions?.total_at_risk > 0 ? "text-amber-500/80" : "text-muted-foreground"
            )}>En Riesgo</span>
          </div>
          <span className="text-2xl font-semibold">{predictions?.total_at_risk || 0}</span>
        </div>

        {/* Weekly Forecast */}
        <div className="p-5 rounded-2xl bg-card border border-border/50">
          <div className="flex items-center gap-2 mb-3">
            <DollarSign className="w-4 h-4 text-muted-foreground" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Forecast</span>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-semibold">
              ${predictions?.revenue_forecast?.current_weekly_avg?.toLocaleString() || '0'}
            </span>
            {predictions?.revenue_forecast?.growth_trend !== undefined && predictions.revenue_forecast.growth_trend !== 0 && (
              <span className={cn(
                "text-sm font-medium",
                predictions.revenue_forecast.growth_trend > 0 ? "text-emerald-500" : "text-rose-500"
              )}>
                {predictions.revenue_forecast.growth_trend > 0 ? '+' : ''}{predictions.revenue_forecast.growth_trend.toFixed(1)}%
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Secondary metrics */}
      <div className="grid grid-cols-3 gap-4">
        <div className="p-4 rounded-xl bg-card/50 border border-border/30">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-muted-foreground">Mejor hora</span>
            <Sparkles className="w-3.5 h-3.5 text-primary" />
          </div>
          <span className="text-xl font-semibold">
            {patterns?.temporal?.best_hours?.[0]?.hour !== undefined
              ? `${patterns.temporal.best_hours[0].hour}:00`
              : patterns?.temporal?.peak_activity_hour !== undefined
              ? `${patterns.temporal.peak_activity_hour}:00`
              : '--'}
          </span>
        </div>

        <div className="p-4 rounded-xl bg-card/50 border border-border/30">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-muted-foreground">Mejor dia</span>
            <Target className="w-3.5 h-3.5 text-blue-500" />
          </div>
          <span className="text-xl font-semibold">{patterns?.temporal?.peak_activity_day || '--'}</span>
        </div>

        <div className="p-4 rounded-xl bg-card/50 border border-border/30">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-muted-foreground">Max msgs</span>
            <TrendingUp className="w-3.5 h-3.5 text-emerald-500" />
          </div>
          <span className="text-xl font-semibold">
            {patterns?.conversation?.max_messages_per_user || 0}
          </span>
        </div>
      </div>

      {/* Two columns */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Hot Leads */}
        <div className="lg:col-span-3 p-5 rounded-2xl bg-card border border-border/50">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-medium">Leads calientes</h3>
            <Link
              to="/leads?filter=hot"
              className="text-xs text-primary hover:text-primary/80 transition-colors flex items-center gap-1"
            >
              Ver todos
              {predictions?.total_hot_leads > 4 && (
                <span className="text-muted-foreground">(+{predictions.total_hot_leads - 4})</span>
              )}
              <ChevronRight className="w-3 h-3" />
            </Link>
          </div>
          <div className="space-y-2">
            {predictions?.hot_leads && predictions.hot_leads.length > 0 ? (
              predictions.hot_leads.slice(0, 5).map((lead, i) => (
                <Link
                  key={i}
                  to={`/inbox?id=${lead.lead_id}`}
                  className="flex items-center justify-between p-3 rounded-lg bg-muted/30 hover:bg-muted/50 transition-colors cursor-pointer group"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-8 h-8 rounded-full bg-emerald-500/10 flex items-center justify-center shrink-0">
                      <Zap className="w-3.5 h-3.5 text-emerald-500" />
                    </div>
                    <div className="min-w-0">
                      <span className="text-sm font-medium truncate block">{lead.username || lead.lead_id}</span>
                      <span className="text-xs text-muted-foreground">{lead.recommended_action}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-xs text-emerald-500 font-medium">
                      {(lead.conversion_probability * 100).toFixed(0)}%
                    </span>
                    <ChevronRight className="w-4 h-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                  </div>
                </Link>
              ))
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                <p className="text-sm">Sin leads calientes</p>
                <p className="text-xs mt-1">El bot esta trabajando</p>
              </div>
            )}
          </div>
        </div>

        {/* Churn Risks */}
        <div className="lg:col-span-2 p-5 rounded-2xl bg-card border border-border/50">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-medium flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-500" />
              En riesgo
            </h3>
            {predictions?.total_at_risk > 0 && (
              <span className="text-xs text-amber-500 font-medium">
                {predictions.total_at_risk} leads
              </span>
            )}
          </div>
          <div className="space-y-2">
            {predictions?.churn_risks && predictions.churn_risks.length > 0 ? (
              predictions.churn_risks.slice(0, 4).map((lead, i) => (
                <Link
                  key={i}
                  to={`/inbox?id=${lead.lead_id}`}
                  className="flex items-center justify-between p-3 rounded-lg bg-amber-500/5 hover:bg-amber-500/10 transition-colors cursor-pointer group"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-8 h-8 rounded-full bg-amber-500/10 flex items-center justify-center shrink-0">
                      <Users className="w-3.5 h-3.5 text-amber-500" />
                    </div>
                    <div className="min-w-0">
                      <span className="text-sm font-medium truncate block">{lead.username || lead.lead_id}</span>
                      <span className="text-xs text-muted-foreground">{lead.days_inactive}d inactivo</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-xs text-amber-500 font-medium">
                      {(lead.churn_risk * 100).toFixed(0)}% riesgo
                    </span>
                    <ChevronRight className="w-4 h-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                  </div>
                </Link>
              ))
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                <p className="text-sm">Sin leads en riesgo</p>
                <p className="text-xs mt-1">Tus leads estan activos</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Recommendations */}
      {recommendations && recommendations.length > 0 && (
        <div className="p-5 rounded-2xl bg-card border border-border/50">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-medium flex items-center gap-2">
              <Lightbulb className="w-4 h-4 text-primary" />
              Recomendaciones
            </h3>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {recommendations.slice(0, 3).map((rec, i) => (
              <div
                key={i}
                className={cn(
                  "p-4 rounded-xl border-l-4 transition-all",
                  rec.priority === 'high'
                    ? "bg-rose-500/5 border-l-rose-500"
                    : rec.priority === 'medium'
                    ? "bg-amber-500/5 border-l-amber-500"
                    : "bg-blue-500/5 border-l-blue-500"
                )}
              >
                <div className="flex items-center gap-2 mb-2">
                  <span className={cn(
                    "px-2 py-0.5 rounded-full text-xs font-semibold",
                    rec.priority === 'high'
                      ? "bg-rose-100 text-rose-700"
                      : rec.priority === 'medium'
                      ? "bg-amber-100 text-amber-700"
                      : "bg-blue-100 text-blue-700"
                  )}>
                    {rec.priority === 'high' ? 'Alta' : rec.priority === 'medium' ? 'Media' : 'Baja'}
                  </span>
                  <span className="text-xs text-muted-foreground uppercase">{rec.category}</span>
                </div>
                <h4 className="font-semibold text-sm mb-1">{rec.title}</h4>
                <p className="text-xs text-muted-foreground line-clamp-2">{rec.description}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Revenue Forecast */}
      {predictions?.revenue_forecast?.forecasts && predictions.revenue_forecast.forecasts.length > 0 && (
        <div className="p-5 rounded-2xl bg-card border border-border/50">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-medium flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-emerald-500" />
              Forecast Revenue
            </h3>
            {predictions.revenue_forecast.growth_trend !== undefined && (
              <span className={cn(
                "text-xs font-medium",
                predictions.revenue_forecast.growth_trend >= 0 ? "text-emerald-500" : "text-rose-500"
              )}>
                Tendencia: {predictions.revenue_forecast.growth_trend >= 0 ? '+' : ''}
                {predictions.revenue_forecast.growth_trend.toFixed(1)}%
              </span>
            )}
          </div>
          <div className="grid grid-cols-4 gap-3">
            {predictions.revenue_forecast.forecasts.slice(0, 4).map((forecast, i) => (
              <div key={i} className="p-3 rounded-xl bg-muted/30">
                <p className="text-xs text-muted-foreground mb-1">Semana {forecast.week}</p>
                <p className="font-semibold">${forecast.projected_revenue.toLocaleString()}</p>
                <p className="text-xs text-muted-foreground">
                  {(forecast.confidence * 100).toFixed(0)}% conf.
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function DashboardSkeleton() {
  return (
    <div className="space-y-8 animate-pulse">
      <div className="flex items-center justify-between">
        <div className="space-y-2">
          <div className="h-4 w-32 bg-muted rounded" />
          <div className="h-8 w-48 bg-muted rounded" />
        </div>
        <div className="flex gap-3">
          <div className="h-9 w-24 bg-muted rounded-lg" />
          <div className="h-9 w-9 bg-muted rounded-lg" />
          <div className="h-9 w-32 bg-muted rounded-lg" />
        </div>
      </div>
      <div className="grid grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-28 bg-card rounded-2xl border border-border/50" />
        ))}
      </div>
      <div className="grid grid-cols-3 gap-4">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="h-20 bg-card/50 rounded-xl border border-border/30" />
        ))}
      </div>
      <div className="grid grid-cols-5 gap-6">
        <div className="col-span-3 h-64 bg-card rounded-2xl border border-border/50" />
        <div className="col-span-2 h-64 bg-card rounded-2xl border border-border/50" />
      </div>
    </div>
  );
}

function DashboardError({ error, onRetry }: { error: Error; onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center h-[60vh] gap-3">
      <AlertCircle className="w-8 h-8 text-destructive/60" />
      <p className="text-sm text-muted-foreground">Error al cargar datos</p>
      <p className="text-xs text-muted-foreground">{error.message}</p>
      <Button variant="outline" size="sm" onClick={onRetry} className="mt-2">
        Reintentar
      </Button>
    </div>
  );
}
