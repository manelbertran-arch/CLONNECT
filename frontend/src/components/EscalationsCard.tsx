import { ChevronRight, CheckCircle2 } from "lucide-react";
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
  if (diffMins < 60) return `${diffMins}m`;
  if (diffHours < 24) return `${diffHours}h`;
  if (diffDays < 7) return `${diffDays}d`;
  return date.toLocaleDateString("es-ES", { day: "numeric", month: "short" });
}

function truncateMessage(message: string, maxLength: number = 40): string {
  if (message.length <= maxLength) return message;
  return message.slice(0, maxLength).trim() + "...";
}

function getDisplayName(alert: { follower_name?: string; follower_username?: string; follower_id: string }): string {
  // Skip "amigo" as it's a fallback placeholder
  if (alert.follower_name && alert.follower_name !== "amigo") {
    return alert.follower_name;
  }
  if (alert.follower_username && alert.follower_username !== "amigo") {
    return alert.follower_username;
  }
  // Use follower_id as last resort, clean up test prefixes
  const id = alert.follower_id;
  if (id.startsWith("test_")) {
    return id.replace("test_", "").slice(0, 15);
  }
  return id.slice(0, 15);
}

export default function EscalationsCard({ className, maxItems = 6 }: EscalationsCardProps) {
  const { data, isLoading } = useEscalations();

  const alerts = data?.alerts || [];
  const total = data?.total || 0;
  const displayedAlerts = alerts.slice(0, maxItems);
  const hasMore = total > maxItems;

  if (isLoading) {
    return (
      <div className={cn("p-4 rounded-xl bg-card border border-border/50", className)}>
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-muted-foreground animate-pulse" />
          <span className="text-sm text-muted-foreground">Cargando...</span>
        </div>
      </div>
    );
  }

  // Empty state - all caught up
  if (total === 0) {
    return (
      <div className={cn("p-4 rounded-xl bg-card border border-border/50", className)}>
        <div className="flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-500" />
          <span className="text-sm font-medium">Todo al día</span>
          <span className="text-xs text-muted-foreground">— No hay pendientes</span>
        </div>
      </div>
    );
  }

  return (
    <div className={cn("p-4 rounded-xl bg-card border border-rose-500/20", className)}>
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-rose-500 animate-pulse" />
          <h3 className="text-sm font-medium">Necesitan tu atención</h3>
          <span className="text-xs text-rose-500 font-medium">({total})</span>
        </div>
        {hasMore && (
          <Link
            to="/inbox?filter=escalations"
            className="text-xs text-primary hover:text-primary/80 transition-colors flex items-center gap-0.5"
          >
            Ver todas
            <ChevronRight className="w-3 h-3" />
          </Link>
        )}
      </div>

      {/* Compact alerts list */}
      <div className="space-y-1">
        {displayedAlerts.map((alert) => (
          <Link
            key={alert.follower_id}
            to={`/inbox?id=${alert.follower_id}`}
            className="flex items-center gap-2 py-1.5 px-2 -mx-2 rounded-md hover:bg-muted/50 transition-colors group"
          >
            <span className="text-sm font-medium truncate min-w-[80px] max-w-[120px]">
              {getDisplayName(alert)}
            </span>
            <span className="text-xs text-muted-foreground shrink-0">
              · {formatTimeAgo(alert.timestamp)}
            </span>
            <span className="text-xs text-muted-foreground truncate flex-1">
              "{truncateMessage(alert.last_message, 35)}"
            </span>
            <ChevronRight className="w-3 h-3 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity shrink-0" />
          </Link>
        ))}
      </div>
    </div>
  );
}
