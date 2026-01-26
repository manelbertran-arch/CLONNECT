import { useAudienceAnalytics } from '@/hooks/useAnalytics';
import { Loader2, Users, MessageSquare, AlertTriangle, HelpCircle, SmilePlus, TrendingDown } from 'lucide-react';
import { cn } from '@/lib/utils';

interface AudienceTabProps {
  creatorId: string;
  period: string;
}

export function AudienceTab({ creatorId, period }: AudienceTabProps) {
  const { data, isLoading, isError } = useAudienceAnalytics(creatorId, period);

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
        <Users className="w-12 h-12 mx-auto mb-3 opacity-50" />
        <p>Error al cargar datos de audiencia</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <StatCard label="Total Mensajes" value={data.total_messages} icon={MessageSquare} />
        <StatCard label="Usuarios Unicos" value={data.unique_users} icon={Users} />
        <StatCard label="Msgs/Usuario" value={data.avg_messages_per_user?.toFixed(1) || '0'} />
        <StatCard
          label="Sentimiento"
          value={data.sentiment?.average?.toFixed(2) || '0'}
          sentiment={data.sentiment?.average}
        />
        <StatCard label="Preguntas" value={data.questions?.total || 0} icon={HelpCircle} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Intent Distribution */}
        <div className="p-5 rounded-xl bg-card border border-border/50">
          <h3 className="text-sm font-medium mb-4 flex items-center gap-2">
            🎯 Distribucion de Intenciones
          </h3>
          {data.intent_distribution?.length > 0 ? (
            <div className="space-y-3">
              {data.intent_distribution.slice(0, 8).map((intent: any, i: number) => (
                <div key={i} className="flex items-center gap-3">
                  <span className="w-28 text-sm text-muted-foreground capitalize truncate">
                    {intent.intent.replace(/_/g, ' ')}
                  </span>
                  <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                    <div
                      className="h-full bg-primary rounded-full"
                      style={{ width: `${intent.percentage}%` }}
                    />
                  </div>
                  <span className="text-sm font-medium w-16 text-right">
                    {intent.percentage}%
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground text-center py-4">
              No hay datos de intenciones
            </p>
          )}
        </div>

        {/* Objections */}
        <div className="p-5 rounded-xl bg-card border border-border/50">
          <h3 className="text-sm font-medium mb-4 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-500" />
            Top Objeciones
          </h3>
          {data.objections?.length > 0 ? (
            <div className="space-y-4">
              {data.objections.slice(0, 5).map((obj: any, i: number) => (
                <div key={i} className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium capitalize">{obj.type.replace(/_/g, ' ')}</span>
                    <span className="text-xs text-muted-foreground">({obj.count})</span>
                  </div>
                  <div className="h-2 bg-muted rounded-full overflow-hidden">
                    <div
                      className="h-full bg-amber-500 rounded-full"
                      style={{ width: `${obj.percentage}%` }}
                    />
                  </div>
                  {obj.examples?.[0] && (
                    <p className="text-xs text-muted-foreground italic truncate">
                      "{obj.examples[0]}"
                    </p>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground text-center py-4">
              Sin objeciones detectadas
            </p>
          )}
        </div>
      </div>

      {/* Funnel */}
      <div className="p-5 rounded-xl bg-card border border-border/50">
        <h3 className="text-sm font-medium mb-4">📊 Funnel de Conversacion</h3>
        <div className="space-y-3">
          {data.funnel?.map((stage: any, i: number) => (
            <div key={i} className="flex items-center gap-4">
              <span className="w-40 text-sm text-muted-foreground">{stage.stage}</span>
              <div className="flex-1 h-6 bg-muted rounded-lg overflow-hidden relative">
                <div
                  className={cn(
                    "h-full rounded-lg transition-all",
                    i === 0 ? "bg-primary" :
                    i === data.funnel.length - 1 ? "bg-emerald-500" :
                    "bg-primary/70"
                  )}
                  style={{ width: `${stage.percentage}%` }}
                />
                <span className="absolute inset-0 flex items-center justify-center text-xs font-medium">
                  {stage.count} ({stage.percentage}%)
                </span>
              </div>
            </div>
          ))}
        </div>

        {/* Insight */}
        {data.funnel && data.funnel.length >= 3 && (
          <div className="mt-4 p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg">
            <p className="text-sm text-amber-700 dark:text-amber-300">
              💡 <strong>Punto de fuga:</strong> De "{data.funnel[1]?.stage}" a "{data.funnel[2]?.stage}".
              Considera mejorar el engagement en los primeros mensajes.
            </p>
          </div>
        )}
      </div>

      {/* Questions */}
      {data.questions?.samples?.length > 0 && (
        <div className="p-5 rounded-xl bg-card border border-border/50">
          <h3 className="text-sm font-medium mb-4 flex items-center gap-2">
            <HelpCircle className="w-4 h-4 text-blue-500" />
            Preguntas Frecuentes ({data.questions.total})
          </h3>
          <div className="space-y-2">
            {data.questions.samples.slice(0, 8).map((q: any, i: number) => (
              <div key={i} className="p-3 rounded-lg bg-muted/30">
                <p className="text-sm">{q.content}</p>
              </div>
            ))}
          </div>
          <p className="text-xs text-muted-foreground mt-3">
            💡 Crear una FAQ con estas preguntas podria reducir la carga del bot
          </p>
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value, icon: Icon, sentiment }: { label: string; value: string | number; icon?: any; sentiment?: number }) {
  return (
    <div className="p-4 rounded-xl bg-card border border-border/50">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-muted-foreground uppercase tracking-wide">{label}</span>
        {Icon && <Icon className="w-4 h-4 text-muted-foreground" />}
        {sentiment !== undefined && (
          <SmilePlus className={cn(
            "w-4 h-4",
            sentiment > 0.3 ? "text-emerald-500" : sentiment < -0.3 ? "text-red-500" : "text-muted-foreground"
          )} />
        )}
      </div>
      <p className={cn(
        "text-2xl font-semibold",
        sentiment !== undefined && sentiment > 0.3 && "text-emerald-500",
        sentiment !== undefined && sentiment < -0.3 && "text-red-500"
      )}>
        {value}
      </p>
    </div>
  );
}
