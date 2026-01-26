import { usePredictions } from '@/hooks/useAnalytics';
import { Loader2, Zap, AlertTriangle, TrendingUp, Lightbulb, ChevronRight, Users } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Link } from 'react-router-dom';

interface PredictionsTabProps {
  creatorId: string;
}

export function PredictionsTab({ creatorId }: PredictionsTabProps) {
  const { data, isLoading, isError } = usePredictions(creatorId);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <Zap className="w-12 h-12 mx-auto mb-3 opacity-50" />
        <p>Error al cargar predicciones</p>
      </div>
    );
  }

  const { hot_leads, churn_risks, revenue_forecast, recommendations } = data;

  return (
    <div className="space-y-6">
      {/* Revenue Forecast */}
      {revenue_forecast?.forecasts?.length > 0 && (
        <div className="p-5 rounded-xl bg-card border border-border/50">
          <h3 className="text-sm font-medium mb-4 flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-emerald-500" />
            Forecast de Revenue (4 semanas)
          </h3>
          <div className="grid grid-cols-4 gap-3">
            {revenue_forecast.forecasts.map((forecast: any, i: number) => (
              <div key={i} className="p-4 rounded-xl bg-muted/30 text-center">
                <p className="text-xs text-muted-foreground mb-1">Semana {forecast.week}</p>
                <p className="text-xl font-semibold">${forecast.projected_revenue?.toLocaleString() || 0}</p>
                <p className="text-xs text-muted-foreground mt-1">
                  {((forecast.confidence || 0) * 100).toFixed(0)}% confianza
                </p>
              </div>
            ))}
          </div>
          {revenue_forecast.growth_trend !== undefined && (
            <div className={cn(
              "mt-4 p-3 rounded-lg",
              revenue_forecast.growth_trend >= 0 ? "bg-emerald-500/10" : "bg-rose-500/10"
            )}>
              <p className={cn(
                "text-sm",
                revenue_forecast.growth_trend >= 0 ? "text-emerald-600" : "text-rose-600"
              )}>
                Tendencia: {revenue_forecast.growth_trend >= 0 ? '+' : ''}{revenue_forecast.growth_trend?.toFixed(1)}% mensual
              </p>
            </div>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Hot Leads */}
        <div className="p-5 rounded-xl bg-card border border-border/50">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-medium flex items-center gap-2">
              <Zap className="w-4 h-4 text-emerald-500" />
              Leads Calientes
            </h3>
            <span className="text-xs text-emerald-500 font-medium">
              {data.total_hot_leads || 0} total
            </span>
          </div>

          {hot_leads?.length > 0 ? (
            <div className="space-y-2">
              {hot_leads.slice(0, 5).map((lead: any, i: number) => (
                <Link
                  key={i}
                  to={`/inbox?id=${lead.lead_id}`}
                  className="flex items-center justify-between p-3 rounded-lg bg-emerald-500/5 hover:bg-emerald-500/10 transition-colors group"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-8 h-8 rounded-full bg-emerald-500/20 flex items-center justify-center">
                      <Zap className="w-4 h-4 text-emerald-500" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate">{lead.username || lead.lead_id}</p>
                      <p className="text-xs text-muted-foreground">{lead.recommended_action}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-emerald-500">
                      {((lead.conversion_probability || 0) * 100).toFixed(0)}%
                    </span>
                    <ChevronRight className="w-4 h-4 text-muted-foreground opacity-0 group-hover:opacity-100" />
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <Users className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p className="text-sm">Sin leads calientes</p>
            </div>
          )}
        </div>

        {/* Churn Risks */}
        <div className="p-5 rounded-xl bg-card border border-border/50">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-medium flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-500" />
              Leads en Riesgo
            </h3>
            <span className="text-xs text-amber-500 font-medium">
              {data.total_at_risk || 0} en riesgo
            </span>
          </div>

          {churn_risks?.length > 0 ? (
            <div className="space-y-2">
              {churn_risks.slice(0, 5).map((lead: any, i: number) => (
                <Link
                  key={i}
                  to={`/inbox?id=${lead.lead_id}`}
                  className="flex items-center justify-between p-3 rounded-lg bg-amber-500/5 hover:bg-amber-500/10 transition-colors group"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-8 h-8 rounded-full bg-amber-500/20 flex items-center justify-center">
                      <AlertTriangle className="w-4 h-4 text-amber-500" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate">{lead.username || lead.lead_id}</p>
                      <p className="text-xs text-muted-foreground">{lead.days_inactive}d inactivo</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-amber-500">
                      {((lead.churn_risk || 0) * 100).toFixed(0)}% riesgo
                    </span>
                    <ChevronRight className="w-4 h-4 text-muted-foreground opacity-0 group-hover:opacity-100" />
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <Users className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p className="text-sm">Sin leads en riesgo</p>
            </div>
          )}
        </div>
      </div>

      {/* Recommendations */}
      {(recommendations?.content?.length > 0 || recommendations?.actions?.length > 0) && (
        <div className="p-5 rounded-xl bg-card border border-border/50">
          <h3 className="text-sm font-medium mb-4 flex items-center gap-2">
            <Lightbulb className="w-4 h-4 text-primary" />
            Recomendaciones
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {[...(recommendations?.content || []), ...(recommendations?.actions || [])].slice(0, 6).map((rec: any, i: number) => (
              <div
                key={i}
                className={cn(
                  "p-4 rounded-xl border-l-4",
                  rec.priority === 'high'
                    ? "bg-rose-500/5 border-l-rose-500"
                    : rec.priority === 'medium'
                    ? "bg-amber-500/5 border-l-amber-500"
                    : "bg-blue-500/5 border-l-blue-500"
                )}
              >
                <div className="flex items-center gap-2 mb-2">
                  <span className={cn(
                    "px-2 py-0.5 rounded-full text-xs font-medium",
                    rec.priority === 'high'
                      ? "bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300"
                      : rec.priority === 'medium'
                      ? "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300"
                      : "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300"
                  )}>
                    {rec.priority === 'high' ? 'Alta' : rec.priority === 'medium' ? 'Media' : 'Baja'}
                  </span>
                  <span className="text-xs text-muted-foreground uppercase">{rec.category}</span>
                </div>
                <h4 className="font-medium text-sm mb-1">{rec.title}</h4>
                <p className="text-xs text-muted-foreground line-clamp-2">{rec.description}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Empty State */}
      {!hot_leads?.length && !churn_risks?.length && !revenue_forecast?.forecasts?.length && (
        <div className="text-center py-12 text-muted-foreground">
          <Zap className="w-12 h-12 mx-auto mb-3 opacity-50" />
          <p>No hay predicciones disponibles</p>
          <p className="text-sm mt-1">Las predicciones se generan con mas datos de conversaciones</p>
        </div>
      )}
    </div>
  );
}
