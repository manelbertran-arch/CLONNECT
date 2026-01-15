/**
 * CopilotPanel - UI for reviewing and approving bot responses
 *
 * Modes:
 * - Automático (copilot_enabled: false): Bot responds automatically
 * - Manual (copilot_enabled: true): Human reviews and approves responses
 */
import { useState } from "react";
import {
  Bot,
  Check,
  X,
  Edit3,
  Send,
  Loader2,
  MessageSquare,
  User,
  Clock,
  CheckCheck,
  Zap,
  UserCheck
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import {
  useCopilotPending,
  useCopilotStatus,
  useApproveCopilotResponse,
  useDiscardCopilotResponse,
  useToggleCopilotMode,
  useApproveAllCopilot,
} from "@/hooks/useApi";
import type { PendingResponse } from "@/services/api";

interface PendingCardProps {
  item: PendingResponse;
  onApprove: (messageId: string, editedText?: string) => void;
  onDiscard: (messageId: string) => void;
  isLoading: boolean;
}

function PendingCard({ item, onApprove, onDiscard, isLoading }: PendingCardProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editedText, setEditedText] = useState(item.suggested_response);

  const handleApprove = () => {
    if (isEditing && editedText !== item.suggested_response) {
      onApprove(item.id, editedText);
    } else {
      onApprove(item.id);
    }
    setIsEditing(false);
  };

  const handleEdit = () => {
    setIsEditing(true);
    setEditedText(item.suggested_response);
  };

  const handleCancelEdit = () => {
    setIsEditing(false);
    setEditedText(item.suggested_response);
  };

  const displayName = item.full_name || item.username || item.follower_id;
  const timeAgo = new Date(item.created_at).toLocaleTimeString();

  return (
    <div className="border border-border rounded-lg p-4 space-y-3 bg-card hover:bg-accent/5 transition-colors">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
            <User className="w-4 h-4 text-primary" />
          </div>
          <div>
            <p className="font-medium text-sm">{displayName}</p>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                {item.platform}
              </Badge>
              <span className="flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {timeAgo}
              </span>
            </div>
          </div>
        </div>
        {item.intent && (
          <Badge
            variant={item.intent.includes("interest") ? "default" : "secondary"}
            className="text-[10px]"
          >
            {item.intent}
          </Badge>
        )}
      </div>

      {/* User Message */}
      <div className="bg-secondary/50 rounded-lg p-3">
        <p className="text-xs text-muted-foreground mb-1 flex items-center gap-1">
          <MessageSquare className="w-3 h-3" />
          User message
        </p>
        <p className="text-sm">{item.user_message}</p>
      </div>

      {/* Bot Response */}
      <div className="bg-primary/5 border border-primary/20 rounded-lg p-3">
        <p className="text-xs text-muted-foreground mb-1 flex items-center gap-1">
          <Bot className="w-3 h-3" />
          Suggested response
        </p>
        {isEditing ? (
          <Textarea
            value={editedText}
            onChange={(e) => setEditedText(e.target.value)}
            className="min-h-[100px] text-sm"
            placeholder="Edit the response..."
          />
        ) : (
          <p className="text-sm whitespace-pre-wrap">{item.suggested_response}</p>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center justify-end gap-2 pt-2">
        {isEditing ? (
          <>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleCancelEdit}
              disabled={isLoading}
            >
              Cancel
            </Button>
            <Button
              variant="default"
              size="sm"
              onClick={handleApprove}
              disabled={isLoading}
              className="gap-1"
            >
              {isLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Send className="w-3 h-3" />}
              Send Edited
            </Button>
          </>
        ) : (
          <>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onDiscard(item.id)}
              disabled={isLoading}
              className="text-destructive hover:text-destructive hover:bg-destructive/10"
            >
              <X className="w-4 h-4 mr-1" />
              Discard
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={handleEdit}
              disabled={isLoading}
            >
              <Edit3 className="w-4 h-4 mr-1" />
              Edit
            </Button>
            <Button
              variant="default"
              size="sm"
              onClick={handleApprove}
              disabled={isLoading}
              className="bg-success hover:bg-success/90"
            >
              {isLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-4 h-4 mr-1" />}
              Approve
            </Button>
          </>
        )}
      </div>
    </div>
  );
}

/**
 * Response Mode Toggle Component
 * Clear UX with two distinct options: Automático vs Manual
 */
interface ResponseModeToggleProps {
  isManualMode: boolean; // true = copilot_enabled (human reviews)
  isLoading: boolean;
  onToggle: (manualMode: boolean) => void;
}

function ResponseModeToggle({ isManualMode, isLoading, onToggle }: ResponseModeToggleProps) {
  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-3">
      <p className="text-sm font-medium text-muted-foreground">
        ¿Cómo quieres responder a los mensajes?
      </p>

      <div className="flex gap-2">
        {/* Automático Button */}
        <button
          onClick={() => !isLoading && onToggle(false)}
          disabled={isLoading}
          className={`
            flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-lg
            font-medium text-sm transition-all duration-200
            ${!isManualMode
              ? 'bg-success text-white shadow-md'
              : 'bg-secondary/50 text-muted-foreground hover:bg-secondary'
            }
            ${isLoading ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
          `}
        >
          {isLoading && !isManualMode ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Zap className="w-4 h-4" />
          )}
          Automático
        </button>

        {/* Manual Button */}
        <button
          onClick={() => !isLoading && onToggle(true)}
          disabled={isLoading}
          className={`
            flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-lg
            font-medium text-sm transition-all duration-200
            ${isManualMode
              ? 'bg-primary text-white shadow-md'
              : 'bg-secondary/50 text-muted-foreground hover:bg-secondary'
            }
            ${isLoading ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
          `}
        >
          {isLoading && isManualMode ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <UserCheck className="w-4 h-4" />
          )}
          Manual
        </button>
      </div>

      {/* Description */}
      <p className="text-xs text-muted-foreground">
        {isManualMode ? (
          <span className="flex items-center gap-1">
            <UserCheck className="w-3 h-3" />
            Tú revisas y apruebas cada respuesta antes de enviarla
          </span>
        ) : (
          <span className="flex items-center gap-1">
            <Zap className="w-3 h-3" />
            El bot responde automáticamente sin tu intervención
          </span>
        )}
      </p>
    </div>
  );
}

export default function CopilotPanel() {
  const { toast } = useToast();
  const { data: pendingData, isLoading: isPendingLoading } = useCopilotPending();
  const { data: statusData, isLoading: isStatusLoading } = useCopilotStatus();
  const approveMutation = useApproveCopilotResponse();
  const discardMutation = useDiscardCopilotResponse();
  const toggleMutation = useToggleCopilotMode();
  const approveAllMutation = useApproveAllCopilot();

  const pendingResponses = pendingData?.pending_responses || [];
  const pendingCount = pendingData?.pending_count || 0;

  // copilot_enabled: true = Manual mode (human reviews)
  // copilot_enabled: false = Automatic mode (bot responds alone)
  const isManualMode = statusData?.copilot_enabled ?? true;

  const handleApprove = (messageId: string, editedText?: string) => {
    approveMutation.mutate(
      { messageId, editedText },
      {
        onSuccess: () => {
          toast({
            title: "Response sent",
            description: editedText ? "Edited response sent successfully" : "Response approved and sent",
          });
        },
        onError: (error) => {
          toast({
            title: "Error",
            description: error.message,
            variant: "destructive",
          });
        },
      }
    );
  };

  const handleDiscard = (messageId: string) => {
    discardMutation.mutate(messageId, {
      onSuccess: () => {
        toast({
          title: "Response discarded",
          description: "The suggested response was discarded",
        });
      },
      onError: (error) => {
        toast({
          title: "Error",
          description: error.message,
          variant: "destructive",
        });
      },
    });
  };

  const handleModeToggle = (manualMode: boolean) => {
    // Prevent action if already loading or same mode
    if (toggleMutation.isPending || manualMode === isManualMode) return;

    toggleMutation.mutate(manualMode, {
      onSuccess: () => {
        toast({
          title: manualMode ? "Modo Manual activado" : "Modo Automático activado",
          description: manualMode
            ? "Ahora revisarás las respuestas antes de enviarlas"
            : "El bot responderá automáticamente",
        });
      },
      onError: (error) => {
        toast({
          title: "Error al cambiar modo",
          description: error.message || "No se pudo cambiar el modo. Intenta de nuevo.",
          variant: "destructive",
        });
      },
    });
  };

  const handleApproveAll = () => {
    approveAllMutation.mutate(undefined, {
      onSuccess: (data) => {
        const results = data.results;
        toast({
          title: "Bulk approval complete",
          description: `${results.approved} responses sent, ${results.failed} failed`,
        });
      },
    });
  };

  const isAnyLoading = approveMutation.isPending || discardMutation.isPending;

  // Show loading state while fetching initial status
  if (isStatusLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Bot className="w-6 h-6 text-primary" />
            Gestión de Respuestas
            {pendingCount > 0 && (
              <Badge variant="destructive" className="ml-2">
                {pendingCount} pending
              </Badge>
            )}
          </h2>
          <p className="text-muted-foreground text-sm mt-1">
            Controla cómo el bot responde a tus seguidores
          </p>
        </div>

        {/* Approve All Button */}
        {pendingCount > 1 && (
          <Button
            variant="outline"
            onClick={handleApproveAll}
            disabled={approveAllMutation.isPending}
            className="gap-2"
          >
            {approveAllMutation.isPending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <CheckCheck className="w-4 h-4" />
            )}
            Approve All ({pendingCount})
          </Button>
        )}
      </div>

      {/* Mode Toggle - New Design */}
      <ResponseModeToggle
        isManualMode={isManualMode}
        isLoading={toggleMutation.isPending}
        onToggle={handleModeToggle}
      />

      {/* Mode Status Banner */}
      {!isManualMode && (
        <div className="bg-success/10 border border-success/20 rounded-lg p-4 flex items-start gap-3">
          <Zap className="w-5 h-5 text-success mt-0.5" />
          <div>
            <p className="font-medium text-success">Modo Automático Activo</p>
            <p className="text-sm text-muted-foreground">
              El bot está respondiendo automáticamente. Cambia a Manual para revisar las respuestas primero.
            </p>
          </div>
        </div>
      )}

      {/* Pending Responses Section */}
      {isManualMode && (
        <>
          <div className="border-t pt-6">
            <h3 className="font-semibold mb-4 flex items-center gap-2">
              <MessageSquare className="w-5 h-5" />
              Respuestas Pendientes
            </h3>

            {isPendingLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-8 h-8 animate-spin text-primary" />
              </div>
            ) : pendingResponses.length === 0 ? (
              <div className="text-center py-12 bg-secondary/20 rounded-lg">
                <Bot className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
                <h3 className="font-medium text-lg">No hay respuestas pendientes</h3>
                <p className="text-muted-foreground text-sm mt-1">
                  Las nuevas respuestas aparecerán aquí para tu aprobación
                </p>
              </div>
            ) : (
              <div className="space-y-4">
                {pendingResponses.map((item) => (
                  <PendingCard
                    key={item.id}
                    item={item}
                    onApprove={handleApprove}
                    onDiscard={handleDiscard}
                    isLoading={isAnyLoading}
                  />
                ))}
              </div>
            )}
          </div>
        </>
      )}

      {/* Info when in automatic mode */}
      {!isManualMode && (
        <div className="text-center py-8 bg-secondary/20 rounded-lg">
          <Zap className="w-12 h-12 mx-auto text-success mb-4" />
          <h3 className="font-medium text-lg">Bot en piloto automático</h3>
          <p className="text-muted-foreground text-sm mt-1 max-w-md mx-auto">
            El bot está respondiendo automáticamente a todos los mensajes.
            Cambia a modo Manual si quieres revisar las respuestas antes de enviarlas.
          </p>
        </div>
      )}
    </div>
  );
}
