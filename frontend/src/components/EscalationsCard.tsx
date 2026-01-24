import { AlertTriangle, ChevronRight, CheckCircle2 } from "lucide-react";
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

function truncateMessage(message: string, maxLength: number = 30): string {
  if (message.length <= maxLength) return message;
  return message.slice(0, maxLength).trim() + "...";
}

function getDisplayName(
  alert: { follower_name?: string; follower_username?: string; follower_id: string },
  index: number
): string {
  // Skip "amigo" as it's a fallback placeholder
  if (alert.follower_name && alert.follower_name !== "amigo") {
    return alert.follower_name;
  }
  if (alert.follower_username && alert.follower_username !== "amigo") {
    return alert.follower_username;
  }

  // Check if follower_id is mostly numeric (like "1769168425737_3673")
  const id = alert.follower_id;
  const numericPattern = /^[\d_]+$/;
  const mostlyNumeric = /^\d{6,}/.test(id.replace(/^test_/, ""));

  if (numericPattern.test(id) || mostlyNumeric) {
    return `Usuario #${index + 1}`;
  }

  // Clean up test prefixes and return readable name
  if (id.startsWith("test_")) {
    return id.replace("test_", "").replace(/_/g, " ").slice(0, 12);
  }

  return id.slice(0, 12);
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
          <div className="w-4 h-4 rounded bg-muted-foreground/20 animate-pulse" />
          <span className="text-sm text-muted-foreground">Cargando...</span>
        </div>
      </div>
    );
  }

  // Empty state - all caught up
  if (total === 0) {
    return (
      <div className={cn("p-5 rounded-2xl bg-card border border-border/50", className)}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-medium">Escalaciones</h3>
        </div>
        <div className="flex items-center gap-3 p-3 rounded-lg bg-emerald-500/5">
          <div className="w-8 h-8 rounded-full bg-emerald-500/10 flex items-center justify-center shrink-0">
            <CheckCircle2 className="w-4 h-4 text-emerald-500" />
          </div>
          <div>
            <p className="text-sm font-medium">Todo al día</p>
            <p className="text-xs text-muted-foreground">No hay conversaciones pendientes</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={cn("p-5 rounded-2xl bg-card border border-border/50", className)}>
      {/* Header - same style as Hot Leads */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-medium">Necesitan atención</h3>
          <span className="px-1.5 py-0.5 text-xs font-medium bg-amber-500/10 text-amber-600 rounded">
            {total}
          </span>
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

      {/* Alerts list - same style as Hot Leads items */}
      <div className="space-y-2">
        {displayedAlerts.map((alert, index) => (
          <Link
            key={alert.follower_id}
            to={`/inbox?id=${alert.follower_id}`}
            className="flex items-center justify-between p-3 rounded-lg bg-muted/30 hover:bg-muted/50 transition-colors cursor-pointer group"
          >
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-8 h-8 rounded-full bg-amber-500/10 flex items-center justify-center shrink-0">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
              </div>
              <div className="min-w-0">
                <span className="text-sm font-medium truncate block">
                  {getDisplayName(alert, index)}
                </span>
                <span className="text-xs text-muted-foreground truncate block">
                  "{truncateMessage(alert.last_message)}"
                </span>
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <span className="text-xs text-muted-foreground">{formatTimeAgo(alert.timestamp)}</span>
              <ChevronRight className="w-4 h-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
