import { Clock, Eye, MessageCircle, MoreHorizontal, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { RelationshipBadge } from "@/components/RelationshipBadge";
import {
  LeadDisplay,
  STATUS_DOT,
  platformIcons,
  avatarGradients,
  formatTimeAgo,
} from "@/components/leads/leadsTypes";

interface LeadsTableProps {
  leads: LeadDisplay[];
  draggedLeadId: string | null;
  fadingIds: Set<string>;
  activeFilter: string | null;
  onDragStart: (lead: LeadDisplay) => void;
  onRowClick: (lead: LeadDisplay) => void;
  onRowMouseEnter: (lead: LeadDisplay) => void;
  onViewLead: (lead: LeadDisplay) => void;
  onGoToChat: (lead: LeadDisplay) => void;
  onDeleteLead: (lead: LeadDisplay) => void;
}

export function LeadsTable({
  leads,
  draggedLeadId,
  fadingIds,
  activeFilter,
  onDragStart,
  onRowClick,
  onRowMouseEnter,
  onViewLead,
  onGoToChat,
  onDeleteLead,
}: LeadsTableProps) {
  return (
    <div className="rounded-xl border border-border/50 bg-card/50 overflow-hidden">
      {/* Table Header */}
      <div className="grid grid-cols-[1fr_80px] md:grid-cols-[1fr_200px_100px_80px] gap-4 px-4 py-2.5 border-b border-border/30 text-xs text-muted-foreground uppercase tracking-wide">
        <span>Contacto</span>
        <span className="hidden md:block">Último mensaje</span>
        <span className="hidden md:block">Tipo</span>
        <span className="text-right">Tiempo</span>
      </div>

      {/* Table Rows */}
      {leads.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground/40 text-sm">
          {activeFilter ? "Sin leads en esta categoría" : "Sin leads"}
        </div>
      ) : (
        <div className="divide-y divide-border/20">
          {leads.map((lead) => (
            <div
              key={lead.id}
              draggable
              onDragStart={() => onDragStart(lead)}
              onClick={() => onRowClick(lead)}
              onMouseEnter={() => onRowMouseEnter(lead)}
              className={cn(
                "group grid grid-cols-[1fr_80px] md:grid-cols-[1fr_200px_100px_80px] gap-4 px-4 py-3 items-center cursor-pointer transition-all duration-150",
                "hover:bg-muted/30",
                draggedLeadId === lead.id && "opacity-50 scale-[0.99]",
                fadingIds.has(lead.id) && "opacity-0 -translate-x-4 scale-95"
              )}
            >
              {/* Contact: Avatar + Name + Username */}
              <div className="flex items-center gap-3 min-w-0">
                <div className="relative shrink-0">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      if (lead.platform === "instagram" && lead.instagramUsername) {
                        window.open(`https://instagram.com/${lead.instagramUsername}`, "_blank");
                      }
                    }}
                    className={cn(
                      "w-9 h-9 rounded-full overflow-hidden",
                      lead.platform === "instagram" && "hover:ring-2 hover:ring-violet-500 cursor-pointer",
                      lead.platform !== "instagram" && "cursor-default"
                    )}
                    title={
                      lead.platform === "instagram"
                        ? `Abrir @${lead.instagramUsername}`
                        : undefined
                    }
                  >
                    {lead.profilePicUrl ? (
                      <img
                        src={lead.profilePicUrl}
                        alt={lead.username}
                        className="w-full h-full object-cover"
                        onError={(e) => {
                          (e.target as HTMLImageElement).style.display = "none";
                          (e.target as HTMLImageElement).nextElementSibling?.classList.remove("hidden");
                        }}
                      />
                    ) : null}
                    <div
                      className={cn(
                        "w-full h-full bg-gradient-to-br flex items-center justify-center text-white text-[10px] font-medium",
                        avatarGradients[lead.platform] || avatarGradients.instagram,
                        lead.profilePicUrl && "hidden"
                      )}
                    >
                      {lead.avatar}
                    </div>
                  </button>
                  {/* Status dot */}
                  <span
                    className={cn(
                      "absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full border-2 border-card",
                      STATUS_DOT[lead.status]
                    )}
                  />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="font-medium text-sm truncate">{lead.name || lead.username}</p>
                  <p className="text-xs text-muted-foreground truncate flex items-center gap-1">
                    {platformIcons[lead.platform] || platformIcons.instagram}
                    @{lead.username.replace(/^@/, "")}
                  </p>
                </div>
                {/* 3-dot menu */}
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <MoreHorizontal className="w-4 h-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-36">
                    <DropdownMenuItem
                      onClick={(e) => {
                        e.stopPropagation();
                        onViewLead(lead);
                      }}
                    >
                      <Eye className="w-4 h-4 mr-2" />
                      Ver detalles
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      onClick={(e) => {
                        e.stopPropagation();
                        onGoToChat(lead);
                      }}
                    >
                      <MessageCircle className="w-4 h-4 mr-2" />
                      Ir al chat
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      onClick={(e) => {
                        e.stopPropagation();
                        onDeleteLead(lead);
                      }}
                      className="text-destructive focus:text-destructive"
                    >
                      <Trash2 className="w-4 h-4 mr-2" />
                      Eliminar
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>

              {/* Last Message (hidden on mobile) */}
              <span className="hidden md:block text-xs text-muted-foreground truncate">
                {lead.lastMessage || "—"}
              </span>

              {/* Relationship Badge (hidden on mobile) */}
              <span className="hidden md:block">
                <RelationshipBadge type={lead.relationshipType} />
              </span>

              {/* Time */}
              <span className="text-xs text-muted-foreground text-right flex items-center justify-end gap-1">
                <Clock className="w-3 h-3" />
                {formatTimeAgo(lead.lastContact) || "—"}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
