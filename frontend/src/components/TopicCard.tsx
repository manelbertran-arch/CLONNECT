/**
 * TopicCard Component
 *
 * SPRINT4-T4.2: Reusable card for displaying aggregated audience data
 * Used in Tu Audiencia page for topics, frustrations, trends, etc.
 */
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface TopicCardProps {
  title: string;
  count: number;
  percentage?: number;
  quotes?: string[];
  users?: string[];
  suggestion?: string;
  sentiment?: "positivo" | "neutral" | "negativo";
  growth?: number;
  emoji?: string;
  className?: string;
}

/**
 * Get sentiment color based on value
 */
function getSentimentColor(sentiment: "positivo" | "neutral" | "negativo"): string {
  switch (sentiment) {
    case "positivo":
      return "bg-green-500/10 text-green-500 border-green-500/20";
    case "negativo":
      return "bg-red-500/10 text-red-500 border-red-500/20";
    default:
      return "bg-gray-500/10 text-gray-500 border-gray-500/20";
  }
}

/**
 * Get growth indicator
 */
function GrowthIndicator({ growth }: { growth: number }) {
  if (growth === 0) return null;

  const isPositive = growth > 0;
  return (
    <span
      className={cn(
        "text-xs font-medium",
        isPositive ? "text-green-500" : "text-red-500"
      )}
    >
      {isPositive ? "+" : ""}
      {growth.toFixed(0)}%
    </span>
  );
}

export function TopicCard({
  title,
  count,
  percentage,
  quotes = [],
  users = [],
  suggestion,
  sentiment,
  growth,
  emoji,
  className,
}: TopicCardProps) {
  return (
    <Card className={cn("hover:shadow-md transition-shadow", className)}>
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            {emoji && <span>{emoji}</span>}
            <span className="line-clamp-1">{title}</span>
          </CardTitle>
          <div className="flex items-center gap-2 shrink-0">
            {sentiment && (
              <Badge
                variant="outline"
                className={cn("text-[10px]", getSentimentColor(sentiment))}
              >
                {sentiment}
              </Badge>
            )}
            {growth !== undefined && <GrowthIndicator growth={growth} />}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Stats row */}
        <div className="flex items-center gap-4 text-sm">
          <div className="flex items-center gap-1">
            <span className="text-lg font-bold">{count}</span>
            <span className="text-muted-foreground">menciones</span>
          </div>
          {percentage !== undefined && percentage > 0 && (
            <div className="text-muted-foreground">
              ({percentage.toFixed(1)}%)
            </div>
          )}
        </div>

        {/* Quotes */}
        {quotes.length > 0 && (
          <div className="space-y-1.5">
            {quotes.slice(0, 2).map((quote, i) => (
              <p
                key={i}
                className="text-xs text-muted-foreground italic line-clamp-2 pl-2 border-l-2 border-muted"
              >
                "{quote}"
              </p>
            ))}
          </div>
        )}

        {/* Users who mentioned */}
        {users.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {users.slice(0, 3).map((user, i) => (
              <Badge key={i} variant="secondary" className="text-[10px]">
                @{user}
              </Badge>
            ))}
            {users.length > 3 && (
              <Badge variant="outline" className="text-[10px]">
                +{users.length - 3} más
              </Badge>
            )}
          </div>
        )}

        {/* Suggestion */}
        {suggestion && (
          <div className="pt-2 border-t">
            <p className="text-xs text-primary font-medium">
              💡 {suggestion}
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default TopicCard;
