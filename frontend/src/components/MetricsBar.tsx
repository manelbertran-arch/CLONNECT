/**
 * MetricsBar - Weekly metrics display bar
 *
 * SPRINT3-T3.2: Shows revenue, sales, response rate with deltas
 */
import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import { cn } from "@/lib/utils";
import type { WeeklyMetrics } from "@/services/api";

interface MetricsBarProps {
  metrics: WeeklyMetrics;
  className?: string;
}

interface MetricItemProps {
  label: string;
  value: string | number;
  delta?: number;
  deltaType?: "percentage" | "absolute" | "points";
  icon?: string;
}

function MetricItem({ label, value, delta, deltaType = "percentage", icon }: MetricItemProps) {
  const isPositive = delta !== undefined && delta > 0;
  const isNegative = delta !== undefined && delta < 0;
  const isNeutral = delta === undefined || delta === 0;

  const formatDelta = () => {
    if (delta === undefined) return null;
    const prefix = isPositive ? "+" : "";
    if (deltaType === "percentage") {
      return `${prefix}${delta.toFixed(1)}%`;
    } else if (deltaType === "points") {
      return `${prefix}${(delta * 100).toFixed(0)}pp`;
    }
    return `${prefix}${delta}`;
  };

  return (
    <div className="flex flex-col">
      <span className="text-xs text-muted-foreground uppercase tracking-wide">
        {label}
      </span>
      <div className="flex items-center gap-1.5 mt-0.5">
        {icon && <span className="text-sm">{icon}</span>}
        <span className="font-semibold text-foreground">{value}</span>
        {delta !== undefined && (
          <span
            className={cn(
              "text-xs flex items-center gap-0.5",
              isPositive && "text-emerald-500",
              isNegative && "text-red-500",
              isNeutral && "text-muted-foreground"
            )}
          >
            {isPositive && <TrendingUp className="w-3 h-3" />}
            {isNegative && <TrendingDown className="w-3 h-3" />}
            {isNeutral && <Minus className="w-3 h-3" />}
            {formatDelta()}
          </span>
        )}
      </div>
    </div>
  );
}

export function MetricsBar({ metrics, className }: MetricsBarProps) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-6 p-4 bg-card rounded-xl border border-border/50",
        className
      )}
    >
      <MetricItem
        label="Esta semana"
        value={`${metrics.revenue.toFixed(0)}€`}
        delta={metrics.revenue_delta}
        deltaType="percentage"
      />
      <MetricItem
        label="Ventas"
        value={metrics.sales_count}
        delta={metrics.sales_delta}
        deltaType="absolute"
      />
      <MetricItem
        label="Respuestas"
        value={`${(metrics.response_rate * 100).toFixed(0)}%`}
        delta={metrics.response_delta}
        deltaType="points"
      />
      <MetricItem
        label="Hot leads"
        value={metrics.hot_leads_count}
        icon="🔥"
      />
      <MetricItem
        label="Conversaciones"
        value={metrics.conversations_count}
      />
      <MetricItem
        label="Nuevos"
        value={metrics.new_leads_count}
        icon="✨"
      />
    </div>
  );
}

export default MetricsBar;
