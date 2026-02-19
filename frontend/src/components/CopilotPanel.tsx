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
  UserCheck,
  BarChart3,
  ArrowRight,
  GitCompare,
  TrendingUp,
  Target,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useToast } from "@/hooks/use-toast";
import {
  useCopilotPending,
  useCopilotStatus,
  useApproveCopilotResponse,
  useDiscardCopilotResponse,
  useToggleCopilotMode,
  useApproveAllCopilot,
  useCopilotStats,
  useCopilotComparisons,
} from "@/hooks/useApi";
import type { PendingResponse } from "@/services/api";

interface PendingCardProps {
  item: PendingResponse;
  onApprove: (messageId: string, editedText?: string) => void;
  onDiscard: (messageId: string) => void;
  isLoading: boolean;
  isFading: boolean;
}

function PendingCard({ item, onApprove, onDiscard, isLoading, isFading }: PendingCardProps) {
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
    <div
      className={`border border-border rounded-lg p-4 space-y-3 bg-card hover:bg-accent/5 transition-all duration-150 ${
        isFading ? 'opacity-0 -translate-x-4 scale-95' : 'opacity-100 translate-x-0 scale-100'
      }`}
    >
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

      {/* Mensaje del Usuario */}
      <div className="bg-secondary/50 rounded-lg p-3">
        <p className="text-xs text-muted-foreground mb-1 flex items-center gap-1">
          <MessageSquare className="w-3 h-3" />
          Mensaje del usuario
        </p>
        <p className="text-sm">{item.user_message}</p>
      </div>

      {/* Respuesta del Bot */}
      <div className="bg-primary/5 border border-primary/20 rounded-lg p-3">
        <p className="text-xs text-muted-foreground mb-1 flex items-center gap-1">
          <Bot className="w-3 h-3" />
          Respuesta sugerida
        </p>
        {isEditing ? (
          <Textarea
            value={editedText}
            onChange={(e) => setEditedText(e.target.value)}
            className="min-h-[100px] text-sm"
            placeholder="Edita la respuesta..."
          />
        ) : (
          <p className="text-sm whitespace-pre-wrap">{item.suggested_response}</p>
        )}
      </div>

      {/* Acciones */}
      <div className="flex items-center justify-end gap-2 pt-2">
        {isEditing ? (
          <>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleCancelEdit}
              disabled={isLoading}
            >
              Cancelar
            </Button>
            <Button
              variant="default"
              size="sm"
              onClick={handleApprove}
              disabled={isLoading}
              className="gap-1"
            >
              {isLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Send className="w-3 h-3" />}
              Enviar Editado
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
              Descartar
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={handleEdit}
              disabled={isLoading}
            >
              <Edit3 className="w-4 h-4 mr-1" />
              Editar
            </Button>
            <Button
              variant="default"
              size="sm"
              onClick={handleApprove}
              disabled={isLoading}
              className="bg-success hover:bg-success/90"
            >
              {isLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-4 h-4 mr-1" />}
              Aprobar
            </Button>
          </>
        )}
      </div>
    </div>
  );
}

/**
 * Response Mode Card Component
 * Large clickable cards with icons, titles, and benefits
 */
interface ModeCardProps {
  title: string;
  icon: React.ReactNode;
  benefits: string[];
  isActive: boolean;
  isLoading: boolean;
  onClick: () => void;
}

function ModeCard({ title, icon, benefits, isActive, isLoading, onClick }: ModeCardProps) {
  return (
    <button
      onClick={onClick}
      disabled={isLoading}
      className={`
        relative flex-1 flex flex-col items-center p-6 rounded-xl
        transition-all duration-200 text-left
        ${isActive
          ? 'bg-card border-2 border-success shadow-lg'
          : 'bg-secondary/30 border-2 border-transparent hover:bg-secondary/50 hover:border-border'
        }
        ${isLoading ? 'opacity-70 cursor-not-allowed' : 'cursor-pointer'}
      `}
    >
      {/* Active Badge */}
      {isActive && (
        <div className="absolute -top-2 -right-2 bg-success text-white text-xs font-bold px-2 py-0.5 rounded-full">
          Activo
        </div>
      )}

      {/* Icon */}
      <div className={`
        w-16 h-16 rounded-full flex items-center justify-center mb-4
        ${isActive ? 'bg-success/20' : 'bg-secondary'}
      `}>
        {isLoading ? (
          <Loader2 className="w-8 h-8 animate-spin text-primary" />
        ) : (
          <div className={`${isActive ? 'text-success' : 'text-muted-foreground'}`}>
            {icon}
          </div>
        )}
      </div>

      {/* Title */}
      <h3 className={`
        text-lg font-bold mb-3 text-center
        ${isActive ? 'text-foreground' : 'text-muted-foreground'}
      `}>
        {title}
      </h3>

      {/* Benefits */}
      <ul className="space-y-2 w-full">
        {benefits.map((benefit, index) => (
          <li
            key={index}
            className={`
              flex items-center gap-2 text-sm
              ${isActive ? 'text-foreground' : 'text-muted-foreground'}
            `}
          >
            <Check className={`w-4 h-4 flex-shrink-0 ${isActive ? 'text-success' : 'text-muted-foreground/50'}`} />
            {benefit}
          </li>
        ))}
      </ul>
    </button>
  );
}

/**
 * Response Mode Toggle Component
 * Card-based UX with two distinct options
 */
interface ResponseModeToggleProps {
  isManualMode: boolean; // true = copilot_enabled (human reviews)
  isLoading: boolean;
  onToggle: (manualMode: boolean) => void;
}

function ResponseModeToggle({ isManualMode, isLoading, onToggle }: ResponseModeToggleProps) {
  return (
    <div className="space-y-4">
      <p className="text-sm font-medium text-muted-foreground">
        Elige cómo quieres gestionar las respuestas:
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {/* Modo Automático Card */}
        <ModeCard
          title="MODO AUTOMÁTICO"
          icon={<Bot className="w-8 h-8" />}
          benefits={[
            "Respuestas 24/7",
            "Sin intervención necesaria",
            "Ideal para alto volumen"
          ]}
          isActive={!isManualMode}
          isLoading={isLoading && !isManualMode}
          onClick={() => !isLoading && onToggle(false)}
        />

        {/* Modo Copilot Card */}
        <ModeCard
          title="MODO COPILOT"
          icon={<UserCheck className="w-8 h-8" />}
          benefits={[
            "Control total",
            "Puedes editar respuestas",
            "Apruebas antes de enviar"
          ]}
          isActive={isManualMode}
          isLoading={isLoading && isManualMode}
          onClick={() => !isLoading && onToggle(true)}
        />
      </div>
    </div>
  );
}

export default function CopilotPanel() {
  const { toast } = useToast();
  const [activeTab, setActiveTab] = useState<"pending" | "metrics" | "comparisons">("pending");
  const { data: pendingData, isLoading: isPendingLoading } = useCopilotPending();
  const { data: statusData, isLoading: isStatusLoading } = useCopilotStatus();
  const { data: statsData, isLoading: isStatsLoading } = useCopilotStats();
  const { data: comparisonsData, isLoading: isComparisonsLoading } = useCopilotComparisons();
  const approveMutation = useApproveCopilotResponse();
  const discardMutation = useDiscardCopilotResponse();
  const toggleMutation = useToggleCopilotMode();
  const approveAllMutation = useApproveAllCopilot();

  // Local state for instant UI feedback
  const [hiddenIds, setHiddenIds] = useState<Set<string>>(new Set());
  const [fadingIds, setFadingIds] = useState<Set<string>>(new Set()); // For exit animation

  // Filter out hidden items - this makes discard INSTANT
  const allResponses = pendingData?.pending_responses || [];
  const pendingResponses = allResponses.filter(item => !hiddenIds.has(item.id));
  const pendingCount = pendingResponses.length;

  // copilot_enabled: true = Manual mode (human reviews)
  // copilot_enabled: false = Automatic mode (bot responds alone)
  const isManualMode = statusData?.copilot_enabled ?? true;

  const handleApprove = (messageId: string, editedText?: string) => {
    // Prevent double-click
    if (fadingIds.has(messageId) || hiddenIds.has(messageId)) return;

    // Start fade animation
    setFadingIds(prev => new Set([...prev, messageId]));

    // Hide after animation (150ms)
    setTimeout(() => {
      setHiddenIds(prev => new Set([...prev, messageId]));
      setFadingIds(prev => {
        const next = new Set(prev);
        next.delete(messageId);
        return next;
      });
    }, 150);

    approveMutation.mutate(
      { messageId, editedText },
      {
        onSuccess: () => {
          toast({
            title: "Respuesta enviada",
            description: editedText ? "Respuesta editada enviada correctamente" : "Respuesta aprobada y enviada",
          });
        },
        onError: (error) => {
          // Show again on error
          setHiddenIds(prev => {
            const next = new Set(prev);
            next.delete(messageId);
            return next;
          });
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
    // Prevent double-click
    if (fadingIds.has(messageId) || hiddenIds.has(messageId)) return;

    // Start fade animation
    setFadingIds(prev => new Set([...prev, messageId]));

    // Hide after animation (150ms)
    setTimeout(() => {
      setHiddenIds(prev => new Set([...prev, messageId]));
      setFadingIds(prev => {
        const next = new Set(prev);
        next.delete(messageId);
        return next;
      });
    }, 150);

    discardMutation.mutate(messageId, {
      onSuccess: () => {
        toast({
          title: "Respuesta descartada",
          description: "La respuesta sugerida fue descartada",
        });
      },
      onError: (error) => {
        // Show again on error
        setHiddenIds(prev => {
          const next = new Set(prev);
          next.delete(messageId);
          return next;
        });
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
          title: "Aprobación masiva completada",
          description: `${results.approved} respuestas enviadas, ${results.failed} fallidas`,
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
                {pendingCount} pendientes
              </Badge>
            )}
          </h2>
          <p className="text-muted-foreground text-sm mt-1">
            Controla cómo el bot responde a tus seguidores
          </p>
        </div>

        {/* Aprobar Todas Button */}
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
            Aprobar Todas ({pendingCount})
          </Button>
        )}
      </div>

      {/* Mode Toggle - New Design */}
      <ResponseModeToggle
        isManualMode={isManualMode}
        isLoading={toggleMutation.isPending}
        onToggle={handleModeToggle}
      />

      {/* Tabs for Pending, Metrics, Comparisons */}
      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as typeof activeTab)} className="border-t pt-6">
        <TabsList className="grid w-full grid-cols-3 mb-6">
          <TabsTrigger value="pending" className="gap-2">
            <MessageSquare className="w-4 h-4" />
            Pendientes
            {pendingCount > 0 && <Badge variant="destructive" className="ml-1 h-5 px-1.5">{pendingCount}</Badge>}
          </TabsTrigger>
          <TabsTrigger value="metrics" className="gap-2">
            <BarChart3 className="w-4 h-4" />
            Métricas
          </TabsTrigger>
          <TabsTrigger value="comparisons" className="gap-2">
            <GitCompare className="w-4 h-4" />
            Comparaciones
          </TabsTrigger>
        </TabsList>

        {/* Pending Responses Tab */}
        <TabsContent value="pending" className="mt-0">
          {isManualMode ? (
            isPendingLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-8 h-8 animate-spin text-primary" />
              </div>
            ) : pendingResponses.length === 0 ? (
              <div className="text-center py-12 bg-secondary/20 rounded-lg">
                <Bot className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
                <h3 className="font-medium text-lg">No hay respuestas pendientes</h3>
                <p className="text-muted-foreground text-sm mt-1">
                  Las nuevas respuestas del bot aparecerán aquí para tu aprobación
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
                    isFading={fadingIds.has(item.id)}
                  />
                ))}
              </div>
            )
          ) : (
            <div className="text-center py-8 bg-secondary/20 rounded-lg">
              <Bot className="w-12 h-12 mx-auto text-success mb-4" />
              <h3 className="font-medium text-lg">Bot en piloto automático</h3>
              <p className="text-muted-foreground text-sm mt-1 max-w-md mx-auto">
                El bot está respondiendo automáticamente a todos los mensajes.
                Cambia a Modo Copilot si quieres revisar las respuestas antes de enviarlas.
              </p>
            </div>
          )}
        </TabsContent>

        {/* Metrics Tab */}
        <TabsContent value="metrics" className="mt-0">
          {isStatsLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-8 h-8 animate-spin text-primary" />
            </div>
          ) : statsData ? (
            <div className="space-y-6">
              {/* Learning Progress */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-lg flex items-center gap-2">
                    <TrendingUp className="w-5 h-5 text-primary" />
                    Progreso de Aprendizaje
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-3 gap-4">
                    <div className="text-center p-4 bg-secondary/30 rounded-lg">
                      <p className="text-2xl font-bold text-primary">{statsData.learning_progress.days_active}</p>
                      <p className="text-xs text-muted-foreground">Días activo</p>
                    </div>
                    <div className="text-center p-4 bg-secondary/30 rounded-lg">
                      <p className="text-2xl font-bold text-primary">{statsData.learning_progress.total_interactions}</p>
                      <p className="text-xs text-muted-foreground">Interacciones</p>
                    </div>
                    <div className="text-center p-4 bg-secondary/30 rounded-lg">
                      <p className="text-2xl font-bold text-primary">{statsData.learning_progress.patterns_detected}</p>
                      <p className="text-xs text-muted-foreground">Patrones</p>
                    </div>
                  </div>
                  <div className="mt-4">
                    <Badge variant={statsData.learning_progress.learning_stage === "optimizing" ? "default" : "secondary"}>
                      {statsData.learning_progress.learning_stage === "exploring" && "Explorando"}
                      {statsData.learning_progress.learning_stage === "learning" && "Aprendiendo"}
                      {statsData.learning_progress.learning_stage === "optimizing" && "Optimizando"}
                    </Badge>
                  </div>
                </CardContent>
              </Card>

              {/* Copilot Metrics */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-lg flex items-center gap-2">
                    <Target className="w-5 h-5 text-emerald-500" />
                    Métricas Copilot (últimos {statsData.period_days} días)
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                    <div className="text-center p-4 bg-emerald-500/10 rounded-lg">
                      <p className="text-2xl font-bold text-emerald-500">{statsData.copilot_metrics.approved}</p>
                      <p className="text-xs text-muted-foreground">Aprobadas</p>
                    </div>
                    <div className="text-center p-4 bg-amber-500/10 rounded-lg">
                      <p className="text-2xl font-bold text-amber-500">{statsData.copilot_metrics.edited}</p>
                      <p className="text-xs text-muted-foreground">Editadas</p>
                    </div>
                    <div className="text-center p-4 bg-red-500/10 rounded-lg">
                      <p className="text-2xl font-bold text-red-500">{statsData.copilot_metrics.discarded}</p>
                      <p className="text-xs text-muted-foreground">Descartadas</p>
                    </div>
                    <div className="text-center p-4 bg-blue-500/10 rounded-lg">
                      <p className="text-2xl font-bold text-blue-500">{statsData.copilot_metrics.pending}</p>
                      <p className="text-xs text-muted-foreground">Pendientes</p>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Legacy Auto-sent */}
              {statsData.legacy_metrics.auto_sent > 0 && (
                <Card className="bg-secondary/20">
                  <CardContent className="py-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Zap className="w-4 h-4 text-muted-foreground" />
                        <span className="text-sm text-muted-foreground">Auto-enviadas (antes de copilot)</span>
                      </div>
                      <span className="font-medium">{statsData.legacy_metrics.auto_sent}</span>
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          ) : (
            <div className="text-center py-12 bg-secondary/20 rounded-lg">
              <BarChart3 className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
              <h3 className="font-medium text-lg">No hay datos disponibles</h3>
            </div>
          )}
        </TabsContent>

        {/* Comparisons Tab */}
        <TabsContent value="comparisons" className="mt-0">
          {isComparisonsLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-8 h-8 animate-spin text-primary" />
            </div>
          ) : comparisonsData && comparisonsData.comparisons.length > 0 ? (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground mb-4">
                Mostrando {comparisonsData.total_comparisons} comparaciones de los últimos {comparisonsData.period_days} días
              </p>
              {comparisonsData.comparisons.map((comparison) => (
                <Card key={comparison.id} className="overflow-hidden">
                  <CardHeader className="pb-2 bg-secondary/30">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <User className="w-4 h-4" />
                        <span className="font-medium">{comparison.username}</span>
                        <Badge variant="outline" className="text-[10px]">{comparison.platform}</Badge>
                      </div>
                      <span className="text-xs text-muted-foreground">
                        {new Date(comparison.created_at).toLocaleDateString()}
                      </span>
                    </div>
                  </CardHeader>
                  <CardContent className="pt-4 space-y-4">
                    {/* Conversation Context */}
                    {comparison.conversation_context.length > 0 && (
                      <div className="space-y-2 p-3 bg-secondary/20 rounded-lg">
                        <p className="text-xs font-medium text-muted-foreground mb-2">Contexto:</p>
                        {comparison.conversation_context.slice(-3).map((ctx, idx) => (
                          <div key={idx} className={`text-sm ${ctx.role === "user" ? "text-blue-400" : "text-emerald-400"}`}>
                            <span className="font-medium">{ctx.role === "user" ? "Usuario" : "Bot"}:</span>{" "}
                            <span className="text-foreground/80">{ctx.content.slice(0, 100)}{ctx.content.length > 100 ? "..." : ""}</span>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Bot Suggestion vs Creator Response */}
                    <div className="grid gap-3">
                      <div className="p-3 border border-muted rounded-lg">
                        <div className="flex items-center gap-2 mb-2">
                          <Bot className="w-4 h-4 text-muted-foreground" />
                          <span className="text-xs font-medium text-muted-foreground">Sugerencia del Bot</span>
                        </div>
                        <p className="text-sm">{comparison.bot_suggestion || "Sin sugerencia"}</p>
                      </div>

                      <ArrowRight className="w-4 h-4 mx-auto text-muted-foreground" />

                      <div className="p-3 border border-emerald-500/30 bg-emerald-500/5 rounded-lg">
                        <div className="flex items-center gap-2 mb-2">
                          <UserCheck className="w-4 h-4 text-emerald-500" />
                          <span className="text-xs font-medium text-emerald-500">Respuesta del Creator</span>
                          {comparison.is_identical && (
                            <Badge variant="outline" className="text-[10px] text-emerald-500 border-emerald-500/30">Idéntica</Badge>
                          )}
                        </div>
                        {comparison.creator_responses.map((resp, idx) => (
                          <p key={idx} className="text-sm">{resp.content}</p>
                        ))}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : (
            <div className="text-center py-12 bg-secondary/20 rounded-lg">
              <GitCompare className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
              <h3 className="font-medium text-lg">No hay comparaciones disponibles</h3>
              <p className="text-muted-foreground text-sm mt-1">
                Las comparaciones aparecerán cuando edites respuestas del bot
              </p>
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
