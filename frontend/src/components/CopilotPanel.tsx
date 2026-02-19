/**
 * CopilotPanel - UI for reviewing and approving bot responses
 *
 * Tabs:
 * - Respuestas: Pending approval queue
 * - Métricas: Approval/edit/discard rates and stats
 * - Comparaciones: Side-by-side bot vs creator split view
 */
import { useState, useRef, useEffect, useCallback } from "react";
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
  GitCompareArrows,
  ArrowRight,
  TrendingUp,
  Timer,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
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
import type { PendingResponse, CopilotComparison } from "@/services/api";

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
  const timeAgo = new Date(item.created_at).toLocaleString("es-ES", {
    timeZone: "Europe/Madrid",
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });

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

/**
 * Metrics Dashboard Tab
 */
function MetricsTab() {
  const { data: stats, isLoading } = useCopilotStats();

  if (isLoading) {
    return (
      <div className="space-y-4 animate-pulse">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="h-24 rounded-lg bg-muted/20 border border-border/20" />
          ))}
        </div>
        <div className="h-40 rounded-lg bg-muted/20 border border-border/20" />
      </div>
    );
  }

  // Extract copilot and legacy metrics from response
  const copilot = (stats as any)?.copilot_metrics;
  const legacy = (stats as any)?.legacy_metrics;

  if (!stats || (stats.total_actions === 0 && (!legacy || legacy.total === 0))) {
    return (
      <div className="text-center py-12 bg-secondary/20 rounded-lg">
        <BarChart3 className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
        <h3 className="font-medium text-lg">Sin datos todavía</h3>
        <p className="text-muted-foreground text-sm mt-1">
          Las métricas aparecerán cuando empieces a aprobar o editar respuestas
        </p>
      </div>
    );
  }

  const formatMs = (ms: number | null) => {
    if (!ms) return "—";
    if (ms < 60000) return `${Math.round(ms / 1000)}s`;
    return `${Math.round(ms / 60000)}min`;
  };

  return (
    <div className="space-y-6">
      {/* Summary Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-4 pb-3 px-4">
            <p className="text-xs text-muted-foreground">Total acciones</p>
            <p className="text-2xl font-bold">{stats.total_actions}</p>
            <p className="text-xs text-muted-foreground">últimos {stats.period_days} días</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 pb-3 px-4">
            <p className="text-xs text-muted-foreground flex items-center gap-1">
              <Check className="w-3 h-3 text-green-500" /> Aprobadas
            </p>
            <p className="text-2xl font-bold text-green-600">{Math.round(stats.approval_rate * 100)}%</p>
            <p className="text-xs text-muted-foreground">{stats.approved} respuestas</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 pb-3 px-4">
            <p className="text-xs text-muted-foreground flex items-center gap-1">
              <Edit3 className="w-3 h-3 text-blue-500" /> Editadas
            </p>
            <p className="text-2xl font-bold text-blue-600">{Math.round(stats.edit_rate * 100)}%</p>
            <p className="text-xs text-muted-foreground">{stats.edited} respuestas</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 pb-3 px-4">
            <p className="text-xs text-muted-foreground flex items-center gap-1">
              <X className="w-3 h-3 text-red-500" /> Descartadas
            </p>
            <p className="text-2xl font-bold text-red-600">{Math.round(stats.discard_rate * 100)}%</p>
            <p className="text-xs text-muted-foreground">{stats.discarded} respuestas</p>
          </CardContent>
        </Card>
      </div>

      {/* Action Distribution Bar */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium">Distribución de acciones</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <span className="text-xs text-muted-foreground w-20">Aprobadas</span>
              <Progress value={stats.approval_rate * 100} className="flex-1 [&>div]:bg-green-500" />
              <span className="text-xs font-medium w-10 text-right">{stats.approved}</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-xs text-muted-foreground w-20">Editadas</span>
              <Progress value={stats.edit_rate * 100} className="flex-1 [&>div]:bg-blue-500" />
              <span className="text-xs font-medium w-10 text-right">{stats.edited}</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-xs text-muted-foreground w-20">Descartadas</span>
              <Progress value={stats.discard_rate * 100} className="flex-1 [&>div]:bg-red-500" />
              <span className="text-xs font-medium w-10 text-right">{stats.discarded}</span>
            </div>
            {stats.manual_override > 0 && (
              <div className="flex items-center gap-3">
                <span className="text-xs text-muted-foreground w-20">Manuales</span>
                <Progress value={stats.manual_rate * 100} className="flex-1 [&>div]:bg-orange-500" />
                <span className="text-xs font-medium w-10 text-right">{stats.manual_override}</span>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Additional Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card>
          <CardContent className="pt-4 pb-3 px-4">
            <p className="text-xs text-muted-foreground flex items-center gap-1">
              <Timer className="w-3 h-3" /> Tiempo respuesta promedio
            </p>
            <p className="text-xl font-bold">{formatMs(stats.avg_response_time_ms)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 pb-3 px-4">
            <p className="text-xs text-muted-foreground flex items-center gap-1">
              <TrendingUp className="w-3 h-3" /> Confianza promedio
            </p>
            <p className="text-xl font-bold">
              {stats.avg_confidence ? `${Math.round(stats.avg_confidence * 100)}%` : "—"}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 pb-3 px-4">
            <p className="text-xs text-muted-foreground">Edits manuales</p>
            <p className="text-xl font-bold">{stats.manual_override}</p>
            <p className="text-xs text-muted-foreground">respuestas desde cero</p>
          </CardContent>
        </Card>
      </div>

      {/* Edit Categories */}
      {Object.keys(stats.edit_categories).length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium">Tipos de edición más comunes</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {Object.entries(stats.edit_categories)
                .sort(([, a], [, b]) => b - a)
                .map(([category, count]) => (
                  <Badge key={category} variant="secondary" className="text-xs">
                    {category.replace(/_/g, " ")} ({count})
                  </Badge>
                ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Legacy Metrics (pre-copilot automatic mode) */}
      {legacy && legacy.total > 0 && (
        <Card className="opacity-70">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Historial automático (pre-copilot)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
              <div>
                <p className="text-xs text-muted-foreground">Auto-enviadas</p>
                <p className="text-lg font-semibold text-muted-foreground">{legacy.auto_sent}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Manual (creador)</p>
                <p className="text-lg font-semibold text-muted-foreground">{legacy.creator_manual}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Descartadas</p>
                <p className="text-lg font-semibold text-muted-foreground">{legacy.discarded}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Expiradas</p>
                <p className="text-lg font-semibold text-muted-foreground">{legacy.expired}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Pending count */}
      {copilot && copilot.pending > 0 && (
        <Card className="border-amber-200 bg-amber-50/50">
          <CardContent className="pt-4 pb-3 px-4 flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">Pendientes de revisión</p>
              <p className="text-xs text-muted-foreground">Sugerencias esperando tu aprobación</p>
            </div>
            <Badge variant="destructive" className="text-lg px-3 py-1">{copilot.pending}</Badge>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

/**
 * Comparisons Split View Tab
 */
function ComparisonsTab() {
  const { data, isLoading } = useCopilotComparisons();

  if (isLoading) {
    return (
      <div className="space-y-4 animate-pulse">
        {[1, 2, 3].map(i => (
          <div key={i} className="h-48 rounded-lg bg-muted/20 border border-border/20" />
        ))}
      </div>
    );
  }

  const comparisons = data?.comparisons || [];

  if (comparisons.length === 0) {
    return (
      <div className="text-center py-12 bg-secondary/20 rounded-lg">
        <GitCompareArrows className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
        <h3 className="font-medium text-lg">Sin comparaciones todavía</h3>
        <p className="text-muted-foreground text-sm mt-1">
          Cuando edites respuestas del bot, las comparaciones aparecerán aquí
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Comparación lado a lado: lo que sugirió el bot vs lo que enviaste
      </p>
      {comparisons.map((c: CopilotComparison) => (
        <ComparisonCard key={c.message_id} comparison={c} />
      ))}
    </div>
  );
}

function ComparisonCard({ comparison: c }: { comparison: CopilotComparison }) {
  const categories = c.edit_diff?.categories || [];
  const isIdentical = c.is_identical ?? (c.bot_original === c.creator_final);
  const formattedDate = c.created_at
    ? new Date(c.created_at).toLocaleString("es-ES", {
        timeZone: "Europe/Madrid",
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "";

  return (
    <div className="border border-border rounded-lg overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 bg-muted/30 border-b">
        <div className="flex items-center gap-2 text-sm">
          <span className="font-medium">{c.username || "usuario"}</span>
          <Badge variant="outline" className="text-[10px]">{c.platform}</Badge>
          {isIdentical ? (
            <Badge className="text-[10px] bg-green-500/20 text-green-700 border-green-300">
              Match
            </Badge>
          ) : (
            <Badge className="text-[10px] bg-amber-500/20 text-amber-700 border-amber-300">
              Diferente
            </Badge>
          )}
        </div>
        <span className="text-xs text-muted-foreground">{formattedDate}</span>
      </div>

      {/* Split View */}
      <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto_1fr] gap-0">
        {/* Bot Original */}
        <div className="p-4 bg-red-500/5">
          <p className="text-xs text-muted-foreground mb-2 flex items-center gap-1">
            <Bot className="w-3 h-3" /> Bot sugirió
          </p>
          <p className="text-sm whitespace-pre-wrap">{c.bot_original}</p>
        </div>

        {/* Arrow divider */}
        <div className="hidden sm:flex items-center justify-center px-2 bg-muted/20">
          <ArrowRight className="w-4 h-4 text-muted-foreground" />
        </div>

        {/* Creator Final */}
        <div className="p-4 bg-green-500/5 border-t sm:border-t-0">
          <p className="text-xs text-muted-foreground mb-2 flex items-center gap-1">
            <User className="w-3 h-3" /> Creador envió
          </p>
          <p className="text-sm whitespace-pre-wrap">{c.creator_final}</p>
        </div>
      </div>

      {/* Footer with categories */}
      {categories.length > 0 && (
        <div className="px-4 py-2 bg-muted/20 border-t flex items-center gap-2 flex-wrap">
          {categories.map(cat => (
            <Badge key={cat} variant="outline" className="text-[10px]">
              {cat.replace(/_/g, " ")}
            </Badge>
          ))}
          {c.edit_diff && (
            <span className="text-[10px] text-muted-foreground ml-auto">
              {c.edit_diff.length_delta > 0 ? "+" : ""}{c.edit_diff.length_delta} chars
            </span>
          )}
        </div>
      )}
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

  // Local state for instant UI feedback
  const [hiddenIds, setHiddenIds] = useState<Set<string>>(new Set());
  const [fadingIds, setFadingIds] = useState<Set<string>>(new Set()); // For exit animation

  // Track animation timers for cleanup on unmount
  const animationTimersRef = useRef<Set<ReturnType<typeof setTimeout>>>(new Set());
  useEffect(() => {
    return () => {
      animationTimersRef.current.forEach(timer => clearTimeout(timer));
    };
  }, []);

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
    const timer = setTimeout(() => {
      animationTimersRef.current.delete(timer);
      setHiddenIds(prev => new Set([...prev, messageId]));
      setFadingIds(prev => {
        const next = new Set(prev);
        next.delete(messageId);
        return next;
      });
    }, 150);
    animationTimersRef.current.add(timer);

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
    const timer = setTimeout(() => {
      animationTimersRef.current.delete(timer);
      setHiddenIds(prev => new Set([...prev, messageId]));
      setFadingIds(prev => {
        const next = new Set(prev);
        next.delete(messageId);
        return next;
      });
    }, 150);
    animationTimersRef.current.add(timer);

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

  // Show skeleton while fetching initial status
  if (isStatusLoading) {
    return (
      <div className="space-y-6 animate-pulse">
        {/* Header skeleton */}
        <div>
          <div className="h-7 w-64 bg-muted/40 rounded mb-2" />
          <div className="h-4 w-80 bg-muted/30 rounded" />
        </div>
        {/* Mode cards skeleton */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="h-52 rounded-xl bg-muted/20 border border-border/30" />
          <div className="h-52 rounded-xl bg-muted/20 border border-border/30" />
        </div>
        {/* Pending section skeleton */}
        <div className="border-t pt-6">
          <div className="h-5 w-48 bg-muted/30 rounded mb-4" />
          <div className="space-y-4">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-40 rounded-lg bg-muted/15 border border-border/20" />
            ))}
          </div>
        </div>
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

      {/* Mode Toggle */}
      <ResponseModeToggle
        isManualMode={isManualMode}
        isLoading={toggleMutation.isPending}
        onToggle={handleModeToggle}
      />

      {/* Info: pending responses now in inbox */}
      {pendingCount > 0 && (
        <div className="flex items-center gap-3 p-3 rounded-lg bg-violet-500/10 border border-violet-500/20">
          <MessageSquare className="w-5 h-5 text-violet-400 shrink-0" />
          <p className="text-sm text-violet-300">
            {pendingCount} respuesta{pendingCount > 1 ? "s" : ""} pendiente{pendingCount > 1 ? "s" : ""} para
            revisar en la <a href="/inbox" className="underline font-medium hover:text-violet-200">Bandeja</a>
          </p>
        </div>
      )}

      {/* Tabbed Content: Métricas | Comparaciones */}
      <Tabs defaultValue="metrics" className="w-full">
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="metrics" className="gap-1.5">
            <BarChart3 className="w-4 h-4" />
            Métricas
          </TabsTrigger>
          <TabsTrigger value="comparisons" className="gap-1.5">
            <GitCompareArrows className="w-4 h-4" />
            Comparaciones
          </TabsTrigger>
        </TabsList>

        {/* Tab: Métricas */}
        <TabsContent value="metrics" className="mt-4">
          <MetricsTab />
        </TabsContent>

        {/* Tab: Comparaciones */}
        <TabsContent value="comparisons" className="mt-4">
          <ComparisonsTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
