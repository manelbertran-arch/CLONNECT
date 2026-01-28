/**
 * SegmentCard Component
 *
 * SPRINT4-T4.3: Card for displaying audience segments with counts
 * Used in Personas page for segment overview
 */
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface SegmentCardProps {
  segment: string;
  count: number;
  potentialRevenue?: number;
  onClick: () => void;
  className?: string;
}

/**
 * Configuration for each segment type
 */
const SEGMENT_CONFIG: Record<string, { icon: string; color: string; description: string }> = {
  hot_lead: { icon: "🔥", color: "border-red-200 bg-red-50", description: "Listos para comprar" },
  warm_lead: { icon: "🌡️", color: "border-orange-200 bg-orange-50", description: "Interesados pero no urge" },
  ghost: { icon: "👻", color: "border-gray-200 bg-gray-50", description: "Sin responder 7+ días" },
  price_objector: { icon: "💸", color: "border-yellow-200 bg-yellow-50", description: "Objeción de precio" },
  time_objector: { icon: "⏰", color: "border-blue-200 bg-blue-50", description: "Objeción de tiempo" },
  customer: { icon: "💰", color: "border-green-200 bg-green-50", description: "Ya compraron" },
  new: { icon: "✨", color: "border-purple-200 bg-purple-50", description: "Menos de 3 mensajes" },
  engaged_fan: { icon: "❤️", color: "border-pink-200 bg-pink-50", description: "Fans activos sin comprar" },
  doubt_objector: { icon: "🤔", color: "border-indigo-200 bg-indigo-50", description: "Tienen dudas" },
  trust_objector: { icon: "🛡️", color: "border-cyan-200 bg-cyan-50", description: "No confían aún" },
};

/**
 * Format segment name for display
 */
function formatSegmentName(segment: string): string {
  return segment
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function SegmentCard({
  segment,
  count,
  potentialRevenue,
  onClick,
  className,
}: SegmentCardProps) {
  const config = SEGMENT_CONFIG[segment] || {
    icon: "👤",
    color: "border-gray-200 bg-gray-50",
    description: segment,
  };

  return (
    <Card
      onClick={onClick}
      className={cn(
        "cursor-pointer transition-all hover:shadow-md hover:scale-[1.02] border-2",
        config.color,
        className
      )}
    >
      <CardContent className="p-4">
        {/* Header with icon and name */}
        <div className="flex items-center gap-3 mb-3">
          <span className="text-2xl">{config.icon}</span>
          <div className="min-w-0 flex-1">
            <div className="font-semibold text-gray-900 truncate">
              {formatSegmentName(segment)}
            </div>
            <div className="text-xs text-muted-foreground truncate">
              {config.description}
            </div>
          </div>
        </div>

        {/* Count */}
        <div className="text-3xl font-bold text-gray-900 mb-1">{count}</div>

        {/* Potential Revenue */}
        {potentialRevenue !== undefined && potentialRevenue > 0 && (
          <div className="text-sm text-green-600 font-medium">
            €{potentialRevenue.toLocaleString()} potencial
          </div>
        )}

        {/* Action link */}
        <button className="mt-3 text-sm text-primary hover:underline font-medium">
          Ver personas →
        </button>
      </CardContent>
    </Card>
  );
}

export default SegmentCard;
