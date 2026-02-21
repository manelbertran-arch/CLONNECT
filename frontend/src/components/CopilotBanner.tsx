/**
 * CopilotBanner - Inline approve/edit/discard for pending bot suggestions in Inbox.
 *
 * Minimal design: user message + 3 candidates horizontal + edit/discard.
 */
import { useState } from "react";
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
}

// Temperature → style mapping
const CANDIDATE_STYLES: Record<string, { label: string; emoji: string; color: string; border: string }> = {
  "0.2": { label: "Corta", emoji: "\u{1F6E1}\u{FE0F}", color: "text-blue-400", border: "border-blue-500/30" },
  "0.7": { label: "Balanceada", emoji: "\u{2696}\u{FE0F}", color: "text-green-400", border: "border-green-500/30" },
  "1.4": { label: "Expresiva", emoji: "\u{2728}", color: "text-orange-400", border: "border-orange-500/30" },
};

export function CopilotBanner({ leadId, platform }: CopilotBannerProps) {
  const { data, isLoading } = usePendingForLead(leadId);
  const approveMutation = useApproveCopilotResponse(getCreatorId());
  const discardMutation = useDiscardCopilotResponse(getCreatorId());
  const { toast } = useToast();

  const [isEditing, setIsEditing] = useState(false);
  const [editedText, setEditedText] = useState("");

  const pending = data?.pending;

  if (isLoading || !pending) return null;

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
            const key = candidate.temperature.toFixed(1);
            const style = CANDIDATE_STYLES[key] || { label: `T=${key}`, emoji: "\u{1F916}", color: "text-gray-400", border: "border-gray-500/30" };
            const originalIdx = candidates.indexOf(candidate);
            return (
              <div
                key={idx}
                className={`p-2 rounded-lg border-l-2 ${style.border} bg-white/5`}
              >
                <span className={`text-[10px] font-medium ${style.color} block mb-1`}>
                  {style.emoji} {style.label}
                </span>
                <p className="text-xs text-foreground/80 whitespace-pre-wrap leading-relaxed min-h-[40px]">
                  {candidate.content}
                </p>
                <Button
                  size="sm"
                  className={`h-6 text-[10px] px-2 mt-1 w-full text-white ${approveBtn}`}
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
