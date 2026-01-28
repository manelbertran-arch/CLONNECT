/**
 * InsightCard - Weekly insight display card
 *
 * SPRINT3-T3.2: Shows content, trend, product, or competition insight
 */
import { ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";

interface InsightCardProps {
  icon: string;
  title: string;
  highlight: string;
  detail: string;
  suggestion: string;
  onAction?: () => void;
  className?: string;
}

export function InsightCard({
  icon,
  title,
  highlight,
  detail,
  suggestion,
  onAction,
  className,
}: InsightCardProps) {
  return (
    <div
      className={cn(
        "p-4 bg-card border border-border/50 rounded-xl hover:border-violet-500/30 transition-all",
        className
      )}
    >
      {/* Header */}
      <div className="flex items-center gap-2 mb-3">
        <span className="text-xl">{icon}</span>
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          {title}
        </span>
      </div>

      {/* Content */}
      <div className="font-semibold text-foreground">{highlight}</div>
      <div className="text-sm text-muted-foreground mt-1">{detail}</div>

      {/* Suggestion */}
      <div className="mt-3 text-sm text-violet-400 flex items-center gap-1">
        <ArrowRight className="w-3.5 h-3.5" />
        {suggestion}
      </div>

      {/* Action button */}
      {onAction && (
        <button
          onClick={onAction}
          className="mt-2 text-xs text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1"
        >
          Ver más
          <ArrowRight className="w-3 h-3" />
        </button>
      )}
    </div>
  );
}

export default InsightCard;
