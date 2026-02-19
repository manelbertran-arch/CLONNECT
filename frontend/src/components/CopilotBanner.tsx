/**
 * CopilotBanner - Inline approve/edit/discard for pending bot suggestions in Inbox.
 *
 * Shows between messages and the input area when a conversation has a pending
 * copilot suggestion. Allows the creator to approve, edit, or discard without
 * leaving the inbox.
 */
import { useState } from "react";
import { Bot, Check, X, Edit3, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  usePendingForLead,
  useApproveCopilotResponse,
  useDiscardCopilotResponse,
} from "@/hooks/useApi";
import { useToast } from "@/hooks/use-toast";
import { getCreatorId } from "@/services/api";

interface CopilotBannerProps {
  leadId: string | null;
  platform?: string;
}

export function CopilotBanner({ leadId, platform }: CopilotBannerProps) {
  const { data, isLoading } = usePendingForLead(leadId);
  const approveMutation = useApproveCopilotResponse(getCreatorId());
  const discardMutation = useDiscardCopilotResponse(getCreatorId());
  const { toast } = useToast();

  const [isEditing, setIsEditing] = useState(false);
  const [editedText, setEditedText] = useState("");

  const pending = data?.pending;

  if (isLoading || !pending) return null;

  const handleApprove = async () => {
    try {
      await approveMutation.mutateAsync({
        messageId: pending.id,
        editedText: isEditing ? editedText : undefined,
      });
      toast({ title: isEditing ? "Enviado (editado)" : "Enviado" });
      setIsEditing(false);
    } catch {
      toast({ title: "Error al enviar", variant: "destructive" });
    }
  };

  const handleDiscard = async () => {
    try {
      await discardMutation.mutateAsync(pending.id);
      toast({ title: "Descartado" });
      setIsEditing(false);
    } catch {
      toast({ title: "Error al descartar", variant: "destructive" });
    }
  };

  const handleStartEdit = () => {
    setEditedText(pending.suggested_response);
    setIsEditing(true);
  };

  const isBusy = approveMutation.isPending || discardMutation.isPending;

  // Platform-aware colors
  const bgColor =
    platform === "whatsapp" ? "bg-[#12262e] border-[#00a884]/30" :
    platform === "telegram" ? "bg-[#1a2836] border-[#3390ec]/30" :
    "bg-violet-500/10 border-violet-500/30";

  const accentColor =
    platform === "whatsapp" ? "text-[#00a884]" :
    platform === "telegram" ? "text-[#3390ec]" :
    "text-violet-400";

  const approveBtn =
    platform === "whatsapp" ? "bg-[#00a884] hover:bg-[#00a884]/80" :
    platform === "telegram" ? "bg-[#3390ec] hover:bg-[#3390ec]/80" :
    "bg-violet-500 hover:bg-violet-600";

  return (
    <div className={`mx-4 mb-2 rounded-xl border p-3 ${bgColor}`}>
      {/* Header */}
      <div className="flex items-center gap-2 mb-2">
        <Bot className={`w-4 h-4 ${accentColor}`} />
        <span className={`text-xs font-medium ${accentColor}`}>Respuesta sugerida</span>
        {pending.intent && (
          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-white/10 text-muted-foreground">
            {pending.intent}
          </span>
        )}
      </div>

      {/* Suggestion text or edit area */}
      {isEditing ? (
        <Textarea
          value={editedText}
          onChange={(e) => setEditedText(e.target.value)}
          className="mb-2 text-sm bg-black/20 border-white/10 min-h-[60px] resize-none"
          autoFocus
        />
      ) : (
        <p className="text-sm text-foreground/90 mb-2 whitespace-pre-wrap leading-relaxed">
          {pending.suggested_response}
        </p>
      )}

      {/* Action buttons */}
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          className={`h-7 text-xs text-white ${approveBtn}`}
          onClick={handleApprove}
          disabled={isBusy}
        >
          {isBusy ? (
            <Loader2 className="w-3 h-3 animate-spin mr-1" />
          ) : (
            <Check className="w-3 h-3 mr-1" />
          )}
          {isEditing ? "Enviar editado" : "Aprobar y enviar"}
        </Button>
        {!isEditing && (
          <Button
            size="sm"
            variant="ghost"
            className="h-7 text-xs text-muted-foreground hover:text-foreground"
            onClick={handleStartEdit}
            disabled={isBusy}
          >
            <Edit3 className="w-3 h-3 mr-1" />
            Editar
          </Button>
        )}
        {isEditing && (
          <Button
            size="sm"
            variant="ghost"
            className="h-7 text-xs text-muted-foreground hover:text-foreground"
            onClick={() => setIsEditing(false)}
            disabled={isBusy}
          >
            Cancelar
          </Button>
        )}
        <Button
          size="sm"
          variant="ghost"
          className="h-7 text-xs text-red-400 hover:text-red-300 ml-auto"
          onClick={handleDiscard}
          disabled={isBusy}
        >
          <X className="w-3 h-3 mr-1" />
          Descartar
        </Button>
      </div>
    </div>
  );
}
