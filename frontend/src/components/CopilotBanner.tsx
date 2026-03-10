/**
 * CopilotBanner - Inline approve/edit/discard for pending bot suggestions in Inbox.
 *
 * Minimal design: user message + 3 candidates horizontal + edit/discard.
 */
import { useState, useEffect } from "react";
import { Check, X, Edit3, Loader2 } from "lucide-react";
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
  creatorIsTyping?: boolean;
}

export function CopilotBanner({ leadId, platform, creatorIsTyping }: CopilotBannerProps) {
  const { data, isLoading } = usePendingForLead(leadId);
  const approveMutation = useApproveCopilotResponse(getCreatorId());
  const discardMutation = useDiscardCopilotResponse(getCreatorId());
  const { toast } = useToast();

  const [isEditing, setIsEditing] = useState(false);
  const [editedText, setEditedText] = useState("");
  const [hiddenPendingId, setHiddenPendingId] = useState<string | null>(null);

  const pending = data?.pending;

  // Hide suggestion when creator starts typing in this conversation
  useEffect(() => {
    if (creatorIsTyping && pending?.id) {
      setHiddenPendingId(pending.id);
    }
  }, [creatorIsTyping, pending?.id]);

  // When a new pending arrives (different id), reset the hidden state
  useEffect(() => {
    if (pending?.id && pending.id !== hiddenPendingId) {
      setHiddenPendingId(null);
    }
  }, [pending?.id]);

  if (isLoading || !pending) return null;
  if (hiddenPendingId === pending.id) return null;

  const candidates = pending.candidates || [];
  const hasCandidates = candidates.length > 0;
  const sortedCandidates = hasCandidates
    ? [...candidates].sort((a, b) => a.temperature - b.temperature)
    : [];
  const bestCandidate = candidates.find(c => c.rank === 1);

  const handleApprove = async (chosenIndex?: number) => {
    try {
      await approveMutation.mutateAsync({
        messageId: pending.id,
        editedText: isEditing ? editedText : undefined,
        chosenIndex: !isEditing ? chosenIndex : undefined,
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
    setEditedText(bestCandidate?.content || pending.suggested_response);
    setIsEditing(true);
  };

  const isBusy = approveMutation.isPending || discardMutation.isPending;

  // Platform-aware colors
  const bgColor =
    platform === "whatsapp" ? "bg-[#12262e] border-[#00a884]/30" :
    platform === "telegram" ? "bg-[#1a2836] border-[#3390ec]/30" :
    "bg-violet-500/10 border-violet-500/30";

  const approveBtn =
    platform === "whatsapp" ? "bg-[#00a884] hover:bg-[#00a884]/80" :
    platform === "telegram" ? "bg-[#3390ec] hover:bg-[#3390ec]/80" :
    "bg-violet-500 hover:bg-violet-600";

  return (
    <div className={`mx-4 mb-2 rounded-xl border p-3 ${bgColor}`}>
      {/* User message — single line */}
      {pending.user_message && (
        <p className="text-xs text-foreground/70 mb-2 truncate">
          {pending.user_message}
        </p>
      )}

      {/* Candidates or single suggestion */}
      {isEditing ? (
        <Textarea
          value={editedText}
          onChange={(e) => setEditedText(e.target.value)}
          className="mb-2 text-sm bg-black/20 border-white/10 min-h-[60px] resize-none"
          autoFocus
        />
      ) : hasCandidates ? (
        <div className="grid grid-cols-3 gap-2 mb-2">
          {sortedCandidates.map((candidate, idx) => {
            const originalIdx = candidates.indexOf(candidate);
            return (
              <div
                key={idx}
                className="p-2 rounded-lg border border-border/40 bg-white/5 flex flex-col"
              >
                <p className="text-xs text-foreground/80 whitespace-pre-wrap leading-relaxed flex-1">
                  {candidate.content}
                </p>
                <Button
                  size="sm"
                  className={`h-6 text-[10px] px-2 mt-2 w-full text-white ${approveBtn}`}
                  onClick={() => handleApprove(originalIdx)}
                  disabled={isBusy}
                >
                  <Check className="w-3 h-3 mr-0.5" />
                  Elegir
                </Button>
              </div>
            );
          })}
        </div>
      ) : (
        <p className="text-sm text-foreground/90 mb-2 whitespace-pre-wrap leading-relaxed">
          {pending.suggested_response}
        </p>
      )}

      {/* Action buttons */}
      <div className="flex items-center gap-2">
        {!hasCandidates && !isEditing && (
          <Button size="sm" className={`h-7 text-xs text-white ${approveBtn}`} onClick={() => handleApprove()} disabled={isBusy}>
            {isBusy ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <Check className="w-3 h-3 mr-1" />}
            Aprobar y enviar
          </Button>
        )}
        {isEditing && (
          <Button size="sm" className={`h-7 text-xs text-white ${approveBtn}`} onClick={() => handleApprove()} disabled={isBusy}>
            {isBusy ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <Check className="w-3 h-3 mr-1" />}
            Enviar editado
          </Button>
        )}
        {!isEditing && (
          <Button size="sm" variant="ghost" className="h-7 text-xs text-muted-foreground hover:text-foreground" onClick={handleStartEdit} disabled={isBusy}>
            <Edit3 className="w-3 h-3 mr-1" /> Editar
          </Button>
        )}
        {isEditing && (
          <Button size="sm" variant="ghost" className="h-7 text-xs text-muted-foreground hover:text-foreground" onClick={() => setIsEditing(false)} disabled={isBusy}>
            Cancelar
          </Button>
        )}
        <Button size="sm" variant="ghost" className="h-7 text-xs text-red-400 hover:text-red-300 ml-auto" onClick={handleDiscard} disabled={isBusy}>
          <X className="w-3 h-3 mr-1" /> Descartar
        </Button>
      </div>
    </div>
  );
}
