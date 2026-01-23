import { AlertCircle, ChevronRight, Clock, MessageSquare, CheckCircle2 } from "lucide-react";
import { Link } from "react-router-dom";
import { useEscalations } from "@/hooks/useApi";
import { cn } from "@/lib/utils";

interface EscalationsCardProps {
  className?: string;
  maxItems?: number;
}

function formatTimeAgo(timestamp: string): string {
  const now = new Date();
  const date = new Date(timestamp);
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return "ahora";
  if (diffMins < 60) return `hace ${diffMins}m`;
  if (diffHours < 24) return `hace ${diffHours}h`;
  if (diffDays < 7) return `hace ${diffDays}d`;
  return date.toLocaleDateString("es-ES", { day: "numeric", month: "short" });
}

function truncateMessage(message: string, maxLength: number = 50): string {
  if (message.length <= maxLength) return message;
  return message.slice(0, maxLength).trim() + "...";
}

export default function EscalationsCard({ className, maxItems = 5 }: EscalationsCardProps) {
  const { data, isLoading } = useEscalations();

  const alerts = data?.alerts || [];
  const total = data?.total || 0;
  const displayedAlerts = alerts.slice(0, maxItems);
  const hasMore = total > maxItems;

  if (isLoading) {
    return (
      <div className={cn("p-5 rounded-2xl bg-card border border-border/50", className)}>
        <div className="flex items-center gap-2 mb-4">
          <div className="w-2 h-2 rounded-full bg-muted-foreground animate-pulse" />
          <span className="text-sm font-medium text-muted-foreground">Cargando...</span>
        </div>
      </div>
    );
  }

  // Empty state - all caught up
  if (total === 0) {
    return (
      <div className={cn("p-5 rounded-2xl bg-card border border-border/50", className)}>
        <div className="flex items-center gap-2 mb-3">
          <CheckCircle2 className="w-4 h-4 text-emerald-500" />
          <span className="text-sm font-medium">Todo al dia</span>
        </div>
        <p className="text-sm text-muted-foreground">
          No hay conversaciones pendientes de atencion
        </p>
      </div>
    );
  }

  return (
    <div className={cn("p-5 rounded-2xl bg-card border border-rose-500/20", className)}>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-rose-500 animate-pulse" />
          <h3 className="text-sm font-medium">Necesitan tu atencion</h3>
          <span className="text-xs text-rose-500 font-medium">({total})</span>
        </div>
        {hasMore && (
          <Link
            to="/inbox?filter=escalations"
            className="text-xs text-primary hover:text-primary/80 transition-colors flex items-center gap-1"
          >
            Ver todas
            <ChevronRight className="w-3 h-3" />
          </Link>
        )}
      </div>

      {/* Alerts list */}
      <div className="space-y-2">
        {displayedAlerts.map((alert) => (
          <Link
            key={alert.follower_id}
            to={`/inbox/${alert.follower_id}`}
            className="flex items-start gap-3 p-3 rounded-lg bg-muted/30 hover:bg-muted/50 transition-colors group"
          >
            {/* Avatar placeholder */}
            <div className="w-9 h-9 rounded-full bg-rose-500/10 flex items-center justify-center shrink-0">
              <AlertCircle className="w-4 h-4 text-rose-500" />
            </div>

            {/* Content */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-sm font-medium truncate">
                  {alert.follower_name || alert.follower_username || "Usuario"}
                </span>
                <span className="text-xs text-muted-foreground flex items-center gap-1 shrink-0">
                  <Clock className="w-3 h-3" />
                  {formatTimeAgo(alert.timestamp)}
                </span>
              </div>
              <p className="text-xs text-muted-foreground truncate">
                "{truncateMessage(alert.last_message, 45)}"
              </p>
            </div>

            {/* Action indicator */}
            <div className="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
              <MessageSquare className="w-4 h-4 text-primary" />
            </div>
          </Link>
        ))}
      </div>

      {/* Footer hint */}
      {total > 0 && (
        <p className="text-xs text-muted-foreground mt-3 text-center">
          Haz click para ver la conversacion
        </p>
      )}
    </div>
  );
}
