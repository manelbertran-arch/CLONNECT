import { useState } from "react";
import {
  Play, Loader2, AlertCircle, Clock,
  ShoppingCart, Snowflake, RefreshCw, Gift,
  ChevronDown, ChevronUp, X, Save, Trash2, Edit3,
  Zap, Send, Users, Lightbulb, RotateCcw
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import {
  useNurturingSequences,
  useNurturingStats,
  useToggleNurturingSequence,
  useUpdateNurturingSequence,
  useCancelNurturing,
  useRunNurturing
} from "@/hooks/useApi";
import { getNurturingEnrolled } from "@/services/api";
import { cn } from "@/lib/utils";
import { useToast } from "@/hooks/use-toast";

// =============================================================================
// CORE SEQUENCES - Only these 4 are shown in the UI
// =============================================================================
const CORE_SEQUENCES = [
  {
    id: 'abandoned',
    backendType: 'abandoned',
    name: 'Carrito Abandonado',
    icon: ShoppingCart,
    colorClass: 'text-red-500 bg-red-500/10 border-red-500/20',
    description: 'Recupera leads que vieron el precio pero no compraron',
    howItWorks: 'Se activa automáticamente cuando un lead pide el precio o link de pago y no completa la compra en 1 hora.',
    defaultTiming: [
      { delay: '1h', label: 'Recordatorio amigable' },
      { delay: '24h', label: 'Última oportunidad' }
    ]
  },
  {
    id: 'cold_interest',
    backendType: 'interest_cold',
    name: 'Interés Frío',
    icon: Snowflake,
    colorClass: 'text-blue-500 bg-blue-500/10 border-blue-500/20',
    description: 'Followup a leads que mostraron interés pero no avanzaron',
    howItWorks: 'Se activa cuando un lead hace preguntas sobre el producto pero no muestra intención de compra.',
    defaultTiming: [
      { delay: '24h', label: 'Seguimiento inicial' },
      { delay: '72h', label: 'Oferta de ayuda' }
    ]
  },
  {
    id: 'reengagement',
    backendType: 're_engagement',
    name: 'Reactivación',
    icon: RefreshCw,
    colorClass: 'text-green-500 bg-green-500/10 border-green-500/20',
    description: 'Reactiva leads que llevan tiempo sin interactuar',
    howItWorks: 'Se activa automáticamente cuando un lead no responde en 7 días.',
    defaultTiming: [
      { delay: '7d', label: 'Te echamos de menos' }
    ]
  },
  {
    id: 'post_purchase',
    backendType: 'post_purchase',
    name: 'Post Compra',
    icon: Gift,
    colorClass: 'text-purple-500 bg-purple-500/10 border-purple-500/20',
    description: 'Onboarding y seguimiento después de una compra',
    howItWorks: 'Se activa automáticamente cuando se confirma un pago.',
    defaultTiming: [
      { delay: '24h', label: 'Bienvenida y acceso' },
      { delay: '72h', label: 'Check-in y soporte' }
    ]
  }
];

// =============================================================================
// DEFAULT MESSAGES - Auto-generated for each sequence type
// =============================================================================
const DEFAULT_MESSAGES: Record<string, Array<{ delay_hours: number; message: string }>> = {
  abandoned: [
    { delay_hours: 1, message: "Ey! Vi que estabas interesado en {producto}. ¿Te surgió alguna duda? Estoy aquí para ayudarte 😊" },
    { delay_hours: 24, message: "Hola de nuevo! Solo quería asegurarme de que viste toda la info de {producto}. Si tienes preguntas, escríbeme 👋" }
  ],
  interest_cold: [
    { delay_hours: 24, message: "Hey {nombre}! Vi que te interesó {producto}. ¿Quieres que te cuente más?" },
    { delay_hours: 72, message: "¿Qué tal? Solo quería recordarte que {producto} sigue disponible. ¿Te echo una mano?" }
  ],
  re_engagement: [
    { delay_hours: 168, message: "¡Hola! Hace tiempo que no hablamos. ¿Cómo va todo? Si necesitas algo, aquí estoy 👋" }
  ],
  post_purchase: [
    { delay_hours: 24, message: "¡Gracias por confiar en mí! ¿Ya pudiste empezar con {producto}? Si necesitas ayuda, escríbeme 🙌" },
    { delay_hours: 72, message: "¿Qué tal va todo con {producto}? ¿Necesitas ayuda con algo?" }
  ]
};

interface EnrolledUser {
  follower_id: string;
  next_scheduled: string;
  pending_steps: Array<{ step: number; scheduled_at: string; message_preview: string }>;
}

// Format delay hours to human readable
function formatDelay(hours: number): string {
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  const remainingHours = hours % 24;
  if (remainingHours === 0) return `${days}d`;
  return `${days}d ${remainingHours}h`;
}

export default function Nurturing() {
  const { data: sequencesData, isLoading: sequencesLoading, error: sequencesError, refetch: refetchSequences } = useNurturingSequences();
  const { data: statsData, isLoading: statsLoading, refetch: refetchStats } = useNurturingStats();
  const toggleSequence = useToggleNurturingSequence();
  const updateSequence = useUpdateNurturingSequence();
  const cancelNurturing = useCancelNurturing();
  const runNurturing = useRunNurturing();
  const { toast } = useToast();

  const [expandedSequence, setExpandedSequence] = useState<string | null>(null);
  const [enrolledUsers, setEnrolledUsers] = useState<Record<string, EnrolledUser[]>>({});
  const [loadingEnrolled, setLoadingEnrolled] = useState<string | null>(null);
  const [editingSequence, setEditingSequence] = useState<string | null>(null);
  const [editingSequenceName, setEditingSequenceName] = useState<string>('');
  const [editSteps, setEditSteps] = useState<Array<{ delay_hours: number; message: string }>>([]);

  // Loading state
  if (sequencesLoading || statsLoading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  // Error state
  if (sequencesError) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <AlertCircle className="w-12 h-12 text-destructive" />
        <p className="text-muted-foreground">Error al cargar datos de nurturing</p>
        <p className="text-sm text-destructive">{sequencesError.message}</p>
      </div>
    );
  }

  const allSequences = sequencesData?.sequences || [];
  const stats = statsData || { total: 0, pending: 0, sent: 0, cancelled: 0 };

  // Map backend sequences to our core sequences
  const getBackendSequence = (backendType: string) => {
    return allSequences.find(s => s.type === backendType);
  };

  // Calculate stats from core sequences only
  const coreSequenceStats = CORE_SEQUENCES.reduce((acc, core) => {
    const backend = getBackendSequence(core.backendType);
    if (backend) {
      if (backend.is_active !== false) acc.active++;
      acc.pending += backend.enrolled_count || 0;
      acc.sent += backend.sent_count || 0;
    }
    return acc;
  }, { active: 0, pending: 0, sent: 0 });

  const handleToggle = async (backendType: string) => {
    try {
      await toggleSequence.mutateAsync(backendType);
      toast({
        title: "Secuencia actualizada",
        description: "El estado se ha cambiado correctamente",
      });
    } catch (error) {
      toast({
        title: "Error",
        description: "No se pudo cambiar el estado",
        variant: "destructive",
      });
    }
  };

  const handleExpand = async (backendType: string) => {
    if (expandedSequence === backendType) {
      setExpandedSequence(null);
      return;
    }

    setExpandedSequence(backendType);

    if (!enrolledUsers[backendType]) {
      setLoadingEnrolled(backendType);
      try {
        const data = await getNurturingEnrolled(undefined, backendType);
        setEnrolledUsers(prev => ({ ...prev, [backendType]: data.enrolled || [] }));
      } catch (error) {
        console.error("Failed to load enrolled users", error);
      }
      setLoadingEnrolled(null);
    }
  };

  const handleEditStart = (coreSeq: typeof CORE_SEQUENCES[0], backendSeq: any) => {
    setEditingSequence(coreSeq.backendType);
    setEditingSequenceName(coreSeq.name);

    // Use backend steps if they exist, otherwise use defaults
    const defaultSteps = DEFAULT_MESSAGES[coreSeq.backendType] || [];
    const existingSteps = backendSeq?.steps?.filter((s: any) => s.message?.trim()) || [];

    if (existingSteps.length > 0) {
      setEditSteps(existingSteps.map((s: any) => ({ ...s })));
    } else {
      // Use default messages
      setEditSteps(defaultSteps.map(s => ({ ...s })));
    }
  };

  const handleRestoreDefaults = () => {
    if (!editingSequence) return;
    const defaultSteps = DEFAULT_MESSAGES[editingSequence] || [];
    setEditSteps(defaultSteps.map(s => ({ ...s })));
    toast({
      title: "Restaurado",
      description: "Se han restaurado los mensajes por defecto",
    });
  };

  const handleEditSave = async () => {
    if (!editingSequence) return;

    try {
      await updateSequence.mutateAsync({
        sequenceType: editingSequence,
        steps: editSteps,
      });
      toast({
        title: "Mensajes guardados",
        description: "Los cambios se han guardado correctamente",
      });
      setEditingSequence(null);
    } catch (error) {
      console.error("Save error:", error);
      toast({
        title: "Error",
        description: "No se pudieron guardar los cambios",
        variant: "destructive",
      });
    }
  };

  const handleCancelFollowup = async (followerId: string, sequenceType: string) => {
    try {
      await cancelNurturing.mutateAsync({ followerId, sequenceType });
      setEnrolledUsers(prev => ({
        ...prev,
        [sequenceType]: prev[sequenceType]?.filter(u => u.follower_id !== followerId) || []
      }));
      toast({
        title: "Cancelado",
        description: "Se ha cancelado el followup para este usuario",
      });
    } catch (error) {
      toast({
        title: "Error",
        description: "No se pudo cancelar el followup",
        variant: "destructive",
      });
    }
  };

  const handleRunNurturing = async () => {
    try {
      const result = await runNurturing.mutateAsync({
        dryRun: false,
        forceDue: true,
        limit: 50
      });

      toast({
        title: "Ejecutado",
        description: `Procesados: ${result.processed || 0}, Enviados: ${result.sent || 0}`,
      });
      refetchSequences();
      refetchStats();
    } catch (error: any) {
      toast({
        title: "Error",
        description: error.message || "No se pudo ejecutar",
        variant: "destructive",
      });
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="metric-card">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
          <div>
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight">Nurturing Automático</h1>
            <p className="text-muted-foreground text-sm">Followups inteligentes que se envían solos</p>
          </div>
          <div className="flex gap-2">
            <Button
              onClick={handleRunNurturing}
              disabled={runNurturing.isPending}
              className="bg-gradient-to-r from-primary to-accent"
            >
              {runNurturing.isPending ? (
                <Loader2 className="w-4 h-4 animate-spin mr-2" />
              ) : (
                <Play className="w-4 h-4 mr-2" />
              )}
              Ejecutar pendientes
            </Button>
          </div>
        </div>

        {/* Stats Row */}
        <div className="grid grid-cols-3 gap-4">
          <div className="text-center p-4 rounded-lg bg-secondary/50">
            <div className="flex items-center justify-center gap-2 mb-1">
              <Zap className="w-4 h-4 text-primary" />
              <span className="text-2xl font-bold">{coreSequenceStats.active}</span>
            </div>
            <p className="text-xs text-muted-foreground">Activas</p>
          </div>
          <div className="text-center p-4 rounded-lg bg-secondary/50">
            <div className="flex items-center justify-center gap-2 mb-1">
              <Users className="w-4 h-4 text-accent" />
              <span className="text-2xl font-bold">{coreSequenceStats.pending}</span>
            </div>
            <p className="text-xs text-muted-foreground">Pendientes</p>
          </div>
          <div className="text-center p-4 rounded-lg bg-secondary/50">
            <div className="flex items-center justify-center gap-2 mb-1">
              <Send className="w-4 h-4 text-success" />
              <span className="text-2xl font-bold">{coreSequenceStats.sent}</span>
            </div>
            <p className="text-xs text-muted-foreground">Enviados</p>
          </div>
        </div>
      </div>

      {/* Sequences List */}
      <div className="space-y-4">
        {CORE_SEQUENCES.map((coreSeq) => {
          const backendSeq = getBackendSequence(coreSeq.backendType);
          const isActive = backendSeq?.is_active !== false;
          const Icon = coreSeq.icon;
          const steps = backendSeq?.steps || [];

          return (
            <div
              key={coreSeq.id}
              className={cn(
                "metric-card border transition-all",
                isActive ? "border-border" : "border-border/50 opacity-75"
              )}
            >
              {/* Header Row */}
              <div className="flex items-start justify-between gap-4 mb-4">
                <div className="flex items-center gap-3">
                  <div className={cn(
                    "w-10 h-10 rounded-lg flex items-center justify-center border",
                    coreSeq.colorClass
                  )}>
                    <Icon className="w-5 h-5" />
                  </div>
                  <h3 className="font-semibold text-lg">{coreSeq.name}</h3>
                </div>
                <Switch
                  checked={isActive}
                  onCheckedChange={() => handleToggle(coreSeq.backendType)}
                  disabled={toggleSequence.isPending}
                />
              </div>

              {/* Description */}
              <p className="text-muted-foreground text-sm mb-4">
                {coreSeq.description}
              </p>

              {/* How it works */}
              <div className="mb-4 p-3 rounded-lg bg-secondary/30">
                <div className="flex items-start gap-2">
                  <Lightbulb className="w-4 h-4 text-yellow-500 mt-0.5 shrink-0" />
                  <div>
                    <p className="text-xs font-medium text-muted-foreground mb-1">¿Cómo funciona?</p>
                    <p className="text-sm">{coreSeq.howItWorks}</p>
                  </div>
                </div>
              </div>

              {/* Timeline */}
              <div className="mb-4">
                <div className="flex items-center gap-2 mb-2">
                  <Clock className="w-4 h-4 text-muted-foreground" />
                  <span className="text-xs font-medium text-muted-foreground">Secuencia:</span>
                </div>
                <div className="pl-2 border-l-2 border-muted space-y-2">
                  {(steps.length > 0 ? steps : coreSeq.defaultTiming.map((t, i) => ({
                    delay_hours: t.delay.includes('d')
                      ? parseInt(t.delay) * 24
                      : parseInt(t.delay),
                    message: t.label
                  }))).map((step: any, idx: number) => (
                    <div key={idx} className="flex items-center gap-2 text-sm">
                      <div className="w-2 h-2 rounded-full bg-muted-foreground -ml-[5px]" />
                      <span className="font-medium text-muted-foreground min-w-[60px]">
                        {formatDelay(step.delay_hours)}
                      </span>
                      <span className="text-foreground">→</span>
                      <span className="truncate">
                        {step.message?.slice(0, 50) || coreSeq.defaultTiming[idx]?.label || `Paso ${idx + 1}`}
                        {step.message?.length > 50 && '...'}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Stats Row */}
              <div className="flex items-center justify-between pt-4 border-t">
                <div className="flex items-center gap-4 text-sm">
                  <span className="text-muted-foreground">
                    <span className="font-semibold text-foreground">{backendSeq?.enrolled_count || 0}</span> Pendientes
                  </span>
                  <span className="text-muted-foreground">
                    <span className="font-semibold text-success">{backendSeq?.sent_count || 0}</span> Enviados
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleEditStart(coreSeq, backendSeq)}
                  >
                    <Edit3 className="w-4 h-4 mr-1" />
                    Personalizar mensajes
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => handleExpand(coreSeq.backendType)}
                  >
                    {expandedSequence === coreSeq.backendType ? (
                      <ChevronUp className="w-4 h-4" />
                    ) : (
                      <ChevronDown className="w-4 h-4" />
                    )}
                  </Button>
                </div>
              </div>

              {/* Expanded section - Enrolled users */}
              {expandedSequence === coreSeq.backendType && (
                <div className="mt-4 pt-4 border-t">
                  <h4 className="text-sm font-medium mb-3">Usuarios en cola</h4>
                  {loadingEnrolled === coreSeq.backendType ? (
                    <div className="flex justify-center py-4">
                      <Loader2 className="w-5 h-5 animate-spin" />
                    </div>
                  ) : (enrolledUsers[coreSeq.backendType]?.length || 0) === 0 ? (
                    <p className="text-sm text-muted-foreground text-center py-4">
                      No hay usuarios en esta secuencia
                    </p>
                  ) : (
                    <div className="space-y-2">
                      {enrolledUsers[coreSeq.backendType]?.map((user) => (
                        <div
                          key={user.follower_id}
                          className="flex items-center justify-between p-3 rounded-lg bg-secondary/50"
                        >
                          <div>
                            <p className="font-medium text-sm">{user.follower_id}</p>
                            <p className="text-xs text-muted-foreground">
                              Próximo: {new Date(user.next_scheduled).toLocaleString('es-ES')}
                            </p>
                          </div>
                          <Button
                            size="sm"
                            variant="ghost"
                            className="text-destructive hover:text-destructive"
                            onClick={() => handleCancelFollowup(user.follower_id, coreSeq.backendType)}
                            disabled={cancelNurturing.isPending}
                          >
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Edit Modal */}
      {editingSequence && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-background rounded-xl border shadow-lg max-w-2xl w-full max-h-[85vh] overflow-hidden flex flex-col">
            {/* Modal Header */}
            <div className="flex items-center justify-between p-4 border-b">
              <div className="flex items-center gap-2">
                <Edit3 className="w-5 h-5 text-primary" />
                <h2 className="text-lg font-semibold">Personalizar: {editingSequenceName}</h2>
              </div>
              <Button variant="ghost" size="sm" onClick={() => setEditingSequence(null)}>
                <X className="w-4 h-4" />
              </Button>
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {/* Info banner */}
              <div className="flex items-start gap-2 p-3 rounded-lg bg-blue-500/10 border border-blue-500/20">
                <Lightbulb className="w-4 h-4 text-blue-500 mt-0.5 shrink-0" />
                <p className="text-sm text-muted-foreground">
                  Los mensajes se personalizan automáticamente con el nombre de tu producto.
                  Puedes editarlos si quieres.
                </p>
              </div>

              {editSteps.map((step, idx) => (
                <div key={idx} className="p-4 rounded-lg border bg-secondary/20">
                  <div className="flex items-center justify-between mb-3">
                    <span className="font-medium">
                      Paso {idx + 1} ({formatDelay(step.delay_hours)} después)
                    </span>
                    <div className="flex items-center gap-2">
                      <label className="text-sm text-muted-foreground">Horas:</label>
                      <input
                        type="number"
                        min="1"
                        value={step.delay_hours}
                        onChange={(e) => {
                          setEditSteps(prev => prev.map((s, i) =>
                            i === idx ? { ...s, delay_hours: parseInt(e.target.value) || 1 } : s
                          ));
                        }}
                        className="w-16 px-2 py-1 rounded border bg-background text-sm"
                      />
                    </div>
                  </div>
                  <textarea
                    value={step.message}
                    onChange={(e) => {
                      setEditSteps(prev => prev.map((s, i) =>
                        i === idx ? { ...s, message: e.target.value } : s
                      ));
                    }}
                    className="w-full h-24 px-3 py-2 rounded-lg border bg-background resize-none text-sm"
                    placeholder="Escribe tu mensaje aquí..."
                  />
                  <p className="text-xs text-muted-foreground mt-2">
                    Variables: <code className="bg-secondary px-1 rounded">{'{nombre}'}</code> <code className="bg-secondary px-1 rounded">{'{producto}'}</code> <code className="bg-secondary px-1 rounded">{'{precio}'}</code>
                  </p>
                </div>
              ))}

              {/* Tip */}
              <div className="flex items-start gap-2 p-3 rounded-lg bg-primary/5 border border-primary/20">
                <Lightbulb className="w-4 h-4 text-primary mt-0.5 shrink-0" />
                <p className="text-sm text-muted-foreground">
                  <strong className="text-foreground">Tip:</strong> Mantén los mensajes cortos y personales.
                  Los followups que parecen humanos tienen mejor conversión.
                </p>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="flex items-center justify-between p-4 border-t bg-secondary/20">
              <Button
                variant="ghost"
                size="sm"
                onClick={handleRestoreDefaults}
                className="text-muted-foreground"
              >
                <RotateCcw className="w-4 h-4 mr-1" />
                Restaurar por defecto
              </Button>
              <div className="flex gap-2">
                <Button variant="outline" onClick={() => setEditingSequence(null)}>
                  Cancelar
                </Button>
                <Button onClick={handleEditSave} disabled={updateSequence.isPending}>
                  {updateSequence.isPending ? (
                    <Loader2 className="w-4 h-4 animate-spin mr-2" />
                  ) : (
                    <Save className="w-4 h-4 mr-2" />
                  )}
                  Guardar
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
