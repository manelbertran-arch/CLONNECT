import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  LeadStatus,
  COLUMN_EMOJI,
  COLUMN_BG,
  STATUS_COLORS,
  columns,
} from "@/components/leads/leadsTypes";

interface LeadsSummaryCardsProps {
  countsByStatus: Record<string, number>;
  activeFilter: LeadStatus | null;
  onFilterChange: (status: LeadStatus | null) => void;
  onDragOver: (e: React.DragEvent) => void;
  onDrop: (status: LeadStatus) => void;
}

export function LeadsSummaryCards({
  countsByStatus,
  activeFilter,
  onFilterChange,
  onDragOver,
  onDrop,
}: LeadsSummaryCardsProps) {
  return (
    <>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {columns.map((col) => {
          const count = countsByStatus[col.status] || 0;
          const isActive = activeFilter === col.status;

          return (
            <button
              key={col.status}
              onClick={() => onFilterChange(isActive ? null : col.status)}
              onDragOver={onDragOver}
              onDrop={() => onDrop(col.status)}
              className={cn(
                "flex flex-col items-center gap-1 p-3 rounded-xl border transition-all duration-150 cursor-pointer",
                "hover:shadow-md",
                isActive
                  ? COLUMN_BG[col.status]
                  : "border-border/50 bg-card/50 hover:border-border"
              )}
            >
              <span className="text-xl">{COLUMN_EMOJI[col.status]}</span>
              <span className={cn("text-2xl font-bold tabular-nums", col.color)}>{count}</span>
              <span className="text-xs text-muted-foreground">{col.title}</span>
            </button>
          );
        })}
      </div>

      {activeFilter && (
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">
            Filtrando por:{" "}
            <span className={cn("font-semibold capitalize", STATUS_COLORS[activeFilter])}>
              {activeFilter}
            </span>
          </span>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-2 text-xs"
            onClick={() => onFilterChange(null)}
          >
            Limpiar
          </Button>
        </div>
      )}
    </>
  );
}
