/**
 * MissionCard - Hot lead action card
 *
 * SPRINT3-T3.2: Shows a lead ready to close with context and action
 */
import { MessageCircle, ArrowRight, Clock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { HotLeadAction } from "@/services/api";

interface MissionCardProps {
  lead: HotLeadAction;
  onOpenChat: (followerId: string) => void;
  className?: string;
}

export function MissionCard({ lead, onOpenChat, className }: MissionCardProps) {
  return (
    <div
      className={cn(
        "p-4 bg-card border border-border/50 rounded-xl hover:border-violet-500/50 hover:shadow-md hover:shadow-violet-500/10 transition-all",
        className
      )}
    >
      <div className="flex justify-between items-start gap-4">
        {/* Lead info */}
        <div className="flex items-start gap-3 flex-1 min-w-0">
          {/* Avatar */}
          {lead.profile_pic_url ? (
            <img
              src={lead.profile_pic_url}
              alt={lead.name || lead.username}
              className="w-10 h-10 rounded-full object-cover shrink-0"
              onError={(e) => {
                (e.target as HTMLImageElement).style.display = "none";
              }}
            />
          ) : (
            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-violet-600 to-purple-600 flex items-center justify-center text-white text-sm font-medium shrink-0">
              {(lead.name || lead.username || "?")[0].toUpperCase()}
            </div>
          )}

          <div className="flex-1 min-w-0">
            <div className="font-medium text-foreground truncate">
              {lead.name || lead.username}
            </div>
            <div className="text-sm text-muted-foreground truncate">
              "{lead.last_message}"
            </div>
            <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
              <Clock className="w-3 h-3" />
              <span>hace {lead.hours_ago}h</span>
              {lead.product && (
                <>
                  <span>•</span>
                  <span className="text-violet-400">{lead.product}</span>
                </>
              )}
            </div>
          </div>
        </div>

        {/* Value */}
        <div className="text-right shrink-0">
          <div className="font-semibold text-emerald-500 text-lg">
            {lead.deal_value.toFixed(0)}€
          </div>
          <div className="text-xs text-muted-foreground">
            {Math.round(lead.purchase_intent_score * 100)}% intent
          </div>
        </div>
      </div>

      {/* Context */}
      {lead.context && (
        <div className="mt-3 text-sm text-muted-foreground bg-muted/30 rounded-lg p-2">
          {lead.context}
        </div>
      )}

      {/* Action */}
      <div className="mt-3 flex justify-between items-center">
        <div className="text-sm font-medium text-violet-400 flex items-center gap-1">
          <ArrowRight className="w-4 h-4" />
          {lead.action}
        </div>
        <Button
          size="sm"
          onClick={() => onOpenChat(lead.follower_id)}
          className="bg-violet-600 hover:bg-violet-700"
        >
          <MessageCircle className="w-4 h-4 mr-1.5" />
          Abrir chat
        </Button>
      </div>
    </div>
  );
}

export default MissionCard;
