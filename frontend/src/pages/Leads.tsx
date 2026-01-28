import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { Instagram, MoreHorizontal, Plus, Loader2, AlertCircle, MessageCircle, Send, Eye, Pencil, Trash2, Users, Flame, Star, CheckCircle, Ghost, Clock, ExternalLink, ListTodo, History, StickyNote, CheckSquare, Square, Phone, Mail, Calendar, Activity, TrendingUp, Tag, ShoppingBag, Brain } from "lucide-react";
import { ProfilePanel } from "@/components/ProfilePanel";
import { getCreatorId } from "@/services/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { cn } from "@/lib/utils";
import { useInfiniteConversations, useUpdateLeadStatus, useCreateManualLead, useUpdateLead, useDeleteLead, useLeadActivities, useLeadTasks, useCreateLeadTask, useUpdateLeadTask, useDeleteLeadTask, useDeleteLeadActivity, useLeadStats } from "@/hooks/useApi";
import { useToast } from "@/hooks/use-toast";
import type { Conversation } from "@/types/api";
import { getPurchaseIntent, detectPlatform, getDisplayName } from "@/types/api";

// Sistema de Embudo Estándar
type LeadStatus = "nuevo" | "interesado" | "caliente" | "cliente" | "fantasma";

// Scoring por etapa del funnel
const STAGE_SCORING: Record<LeadStatus, number> = {
  fantasma: 0,
  nuevo: 25,
  interesado: 50,
  caliente: 75,
  cliente: 100,
};

// Default product price (will be fetched from backend)
const DEFAULT_PRODUCT_PRICE = 97;

// Colors for each status (for value display)
const STATUS_COLORS: Record<LeadStatus, string> = {
  fantasma: "text-gray-500",
  nuevo: "text-blue-400",
  interesado: "text-amber-400",
  caliente: "text-red-400",
  cliente: "text-emerald-400",
};

interface LeadDisplay {
  id: string;
  name: string;
  username: string;        // Display name (name or username)
  instagramUsername: string; // Actual Instagram username for URL
  score: number;         // Pipeline score (20/40/60/80/100) - main display
  intentScore: number;   // AI intent score (0-100) - secondary display
  value: number;
  status: LeadStatus;
  avatar: string;
  profilePicUrl: string; // Instagram profile picture
  platform: string;
  email: string;
  phone: string;
  notes: string;
  lastContact: string;   // Last contact timestamp
  totalMessages: number; // Total messages in conversation
  followerId: string;    // For navigation to inbox
}

// Configuración de columnas del Pipeline (todo en español)
const columns: { status: LeadStatus; title: string; description: string; icon: React.ReactNode; color: string; gradient: string }[] = [
  { status: "nuevo", title: "Nuevos", description: "Primer contacto", icon: <Users className="w-4 h-4" />, color: "text-blue-400", gradient: "from-blue-500/20 to-blue-600/10" },
  { status: "interesado", title: "Interesados", description: "Mostró interés", icon: <Star className="w-4 h-4" />, color: "text-amber-400", gradient: "from-amber-500/20 to-amber-600/10" },
  { status: "caliente", title: "Calientes", description: "Listo para comprar", icon: <Flame className="w-4 h-4" />, color: "text-red-400", gradient: "from-red-500/20 to-red-600/10" },
  { status: "cliente", title: "Clientes", description: "Ya compró", icon: <CheckCircle className="w-4 h-4" />, color: "text-emerald-400", gradient: "from-emerald-500/20 to-emerald-600/10" },
  { status: "fantasma", title: "Fantasmas", description: "+7 días sin respuesta", icon: <Ghost className="w-4 h-4" />, color: "text-gray-500", gradient: "from-gray-500/20 to-gray-600/10" },
];

const platformIcons: Record<string, React.ReactNode> = {
  instagram: <Instagram className="w-3 h-3" />,
  telegram: <Send className="w-3 h-3" />,
  whatsapp: <MessageCircle className="w-3 h-3" />,
};

function getInitials(name?: string, username?: string, id?: string): string {
  if (name && name.trim()) {
    return name.split(" ").map(n => n[0]).join("").slice(0, 2).toUpperCase();
  }
  if (username && username.trim()) {
    return username.slice(0, 2).toUpperCase();
  }
  // Use platform prefix for initials if no name/username
  if (id) {
    if (id.startsWith("tg_")) return "TG";
    if (id.startsWith("ig_")) return "IG";
    if (id.startsWith("wa_")) return "WA";
    return id.slice(0, 2).toUpperCase();
  }
  return "??";
}

function formatTimeAgo(dateStr?: string): string {
  if (!dateStr) return "";
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 60) return `${diffMins}m`;
  if (diffHours < 24) return `${diffHours}h`;
  if (diffDays < 7) return `${diffDays}d`;
  return `${Math.floor(diffDays / 7)}sem`;
}

function openInstagramProfile(username: string, e: React.MouseEvent) {
  e.stopPropagation(); // Prevent card click
  // Remove @ prefix if present and clean the username
  const cleanUsername = username.replace(/^@/, "").split(" ")[0];
  window.open(`https://instagram.com/${cleanUsername}`, "_blank");
}

/**
 * Clasificar lead según embudo estándar
 * Backend returns: new, active, hot, customer, ghost
 * Frontend uses: nuevo, interesado, caliente, cliente, fantasma
 */
function getLeadStatus(convo: Conversation): LeadStatus {
  // Map backend status (English) to frontend status (Spanish)
  const statusMap: Record<string, LeadStatus> = {
    "new": "nuevo",
    "active": "interesado",
    "hot": "caliente",
    "customer": "cliente",
    "ghost": "fantasma",
  };

  // Priority 1: Use backend status if available
  const backendStatus = convo.lead_status || (convo as { status?: string }).status;
  if (backendStatus && statusMap[backendStatus]) {
    return statusMap[backendStatus];
  }

  // Priority 2: Check if customer
  if (convo.is_customer) return "cliente";

  // Priority 3: Fallback to intent-based calculation
  const intent = getPurchaseIntent(convo);
  if (intent >= 0.50) return "caliente";
  if (intent >= 0.20) return "interesado";
  return "nuevo";
}

/**
 * Calculate lead value based on stage scoring
 * Value = product_price × (scoring / 100)
 */
function calculateLeadValue(status: LeadStatus, productPrice: number): number {
  const scoring = STAGE_SCORING[status];
  return Math.round(productPrice * (scoring / 100));
}

// Mapeo de status UI a status backend (nuevo embudo)
const statusToBackend: Record<LeadStatus, string> = {
  nuevo: "nuevo",
  interesado: "interesado",
  caliente: "caliente",
  cliente: "cliente",
  fantasma: "fantasma",
};

// Initial form state for adding/editing leads
const initialFormState = {
  name: "",
  platform: "instagram" as string,
  email: "",
  phone: "",
  notes: "",
};

export default function Leads() {
  // Use conversations endpoint to get ALL followers (not just leads with is_lead=true)
  const { data, isLoading, error, fetchNextPage, hasNextPage, isFetchingNextPage } = useInfiniteConversations();
  const [draggedLead, setDraggedLead] = useState<LeadDisplay | null>(null);
  const [localStatusOverrides, setLocalStatusOverrides] = useState<Record<string, LeadStatus>>({});
  const { toast } = useToast();
  const navigate = useNavigate();
  const updateStatusMutation = useUpdateLeadStatus();
  const createLeadMutation = useCreateManualLead();
  const updateLeadMutation = useUpdateLead();
  const deleteLeadMutation = useDeleteLead();
  const createTaskMutation = useCreateLeadTask();
  const updateTaskMutation = useUpdateLeadTask();
  const deleteTaskMutation = useDeleteLeadTask();
  const deleteActivityMutation = useDeleteLeadActivity();

  // Modal states
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [isViewModalOpen, setIsViewModalOpen] = useState(false);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [selectedLead, setSelectedLead] = useState<LeadDisplay | null>(null);
  const [formData, setFormData] = useState(initialFormState);

  // CRM modal state - editable fields
  const [newTaskTitle, setNewTaskTitle] = useState("");
  const [modalTab, setModalTab] = useState("info");
  const [editEmail, setEditEmail] = useState("");
  const [editPhone, setEditPhone] = useState("");
  const [editNotes, setEditNotes] = useState("");
  const [editingTaskId, setEditingTaskId] = useState<string | null>(null);
  const [editingTaskTitle, setEditingTaskTitle] = useState("");
  const [completingTaskId, setCompletingTaskId] = useState<string | null>(null);

  // Fetch activities, tasks, and stats for selected lead
  const { data: activitiesData } = useLeadActivities(selectedLead?.followerId || null);
  const { data: tasksData } = useLeadTasks(selectedLead?.followerId || null);
  const { data: statsData, isLoading: statsLoading } = useLeadStats(selectedLead?.followerId || null);


  const leads = useMemo(() => {
    // Flatten all pages from infinite query
    const allConversations = data?.pages?.flatMap(page => page.conversations) || [];
    if (!allConversations.length) return [];

    return allConversations.map((convo): LeadDisplay => {
      const platform = convo.platform || detectPlatform(convo.follower_id);
      const displayName = getDisplayName(convo);
      const intent = getPurchaseIntent(convo);
      const leadId = convo.id || convo.follower_id;

      // Status priority:
      // 1. Local override (from optimistic update during drag & drop)
      // 2. Mapped from backend status (getLeadStatus handles English→Spanish mapping)
      const status = localStatusOverrides[leadId] || getLeadStatus(convo);

      // Stage-based scoring (0-100%)
      const score = STAGE_SCORING[status];

      // AI Intent score: 0-100 from purchase_intent
      const intentScore = convo.purchase_intent_score ?? Math.round(intent * 100);

      // Value no longer displayed, kept for internal use
      const value = 0;

      // Get Instagram username (without ig_ prefix if present)
      const rawUsername = convo.username || convo.follower_id;
      const instagramUsername = rawUsername.replace(/^ig_/, "").replace(/^@/, "");

      return {
        id: leadId, // Prefer UUID id for reliable DB lookups
        name: convo.name || "",
        username: displayName,
        instagramUsername,  // Actual username for Instagram URL
        score,              // Stage-based scoring (0-100%)
        intentScore,        // AI intent score (secondary)
        value,              // Calculated value in €
        status,
        avatar: getInitials(convo.name, convo.username, convo.follower_id),
        profilePicUrl: convo.profile_pic_url || "",
        platform,
        email: convo.email || "",
        phone: convo.phone || "",
        notes: convo.notes || "",
        lastContact: convo.last_contact || "",
        totalMessages: convo.total_messages || 0,
        followerId: convo.follower_id,
      };
    });
  }, [data?.pages, localStatusOverrides]);

  const handleDragStart = (lead: LeadDisplay) => {
    setDraggedLead(lead);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const handleDrop = async (status: LeadStatus) => {
    if (!draggedLead || draggedLead.status === status) {
      setDraggedLead(null);
      return;
    }

    const leadId = draggedLead.id;
    const oldStatus = draggedLead.status;

    // Optimistic update - update local state immediately
    setLocalStatusOverrides(prev => ({
      ...prev,
      [leadId]: status
    }));
    setDraggedLead(null);

    // Call API to persist the change
    try {
      await updateStatusMutation.mutateAsync({
        followerId: leadId,
        status: statusToBackend[status],
      });

      toast({
        title: "Estado actualizado",
        description: `Lead movido a ${status}`,
      });
    } catch (error) {
      // Revert on error
      setLocalStatusOverrides(prev => ({
        ...prev,
        [leadId]: oldStatus
      }));

      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "No se pudo actualizar",
        variant: "destructive",
      });
    }
  };

  const getLeadsByStatus = (status: LeadStatus) => leads.filter(lead => lead.status === status);

  // Handlers for Add Lead modal
  const handleOpenAddModal = () => {
    setFormData(initialFormState);
    setIsAddModalOpen(true);
  };

  const handleAddLead = async () => {
    if (!formData.name.trim()) {
      toast({
        title: "Nombre requerido",
        description: "Ingresa un nombre para el lead",
        variant: "destructive",
      });
      return;
    }

    try {
      await createLeadMutation.mutateAsync({
        name: formData.name,
        platform: formData.platform,
        email: formData.email || undefined,
        phone: formData.phone || undefined,
        notes: formData.notes || undefined,
      });
      toast({
        title: "Lead creado",
        description: `${formData.name} agregado al pipeline`,
      });
      setIsAddModalOpen(false);
      setFormData(initialFormState);
    } catch (err) {
      toast({
        title: "Error",
        description: err instanceof Error ? err.message : "No se pudo crear el lead",
        variant: "destructive",
      });
    }
  };

  // Handlers for View/Edit/Delete
  const handleViewLead = (lead: LeadDisplay) => {
    setSelectedLead(lead);
    setModalTab("info"); // Reset to info tab
    setNewTaskTitle("");
    // Initialize editable fields with current values
    setEditEmail(lead.email || "");
    setEditPhone(lead.phone || "");
    setEditNotes(lead.notes || "");
    setEditingTaskId(null);
    setEditingTaskTitle("");
    setIsViewModalOpen(true);
  };

  // Handler for adding a task
  const handleAddTask = async () => {
    if (!selectedLead || !newTaskTitle.trim()) return;

    try {
      await createTaskMutation.mutateAsync({
        leadId: selectedLead.followerId,
        data: {
          title: newTaskTitle.trim(),
          task_type: "follow_up",
          priority: "medium",
        },
      });
      setNewTaskTitle("");
      toast({
        title: "Tarea creada",
        description: "Se ha añadido la tarea",
      });
    } catch {
      toast({
        title: "Error",
        description: "No se pudo crear la tarea",
        variant: "destructive",
      });
    }
  };

  // Handler for completing a task
  const handleToggleTask = async (taskId: string, currentStatus: string) => {
    if (!selectedLead) return;

    const newStatus = currentStatus === "completed" ? "pending" : "completed";

    // If completing (not uncompleting), show animation first
    if (newStatus === "completed") {
      setCompletingTaskId(taskId);
      // Wait for animation before actually completing
      setTimeout(async () => {
        try {
          await updateTaskMutation.mutateAsync({
            leadId: selectedLead.followerId,
            taskId,
            data: { status: newStatus },
          });
          toast({ title: "Tarea completada" });
        } catch {
          toast({ title: "Error", description: "No se pudo completar la tarea", variant: "destructive" });
        } finally {
          setCompletingTaskId(null);
        }
      }, 800);
    } else {
      // Uncompleting - do immediately
      try {
        await updateTaskMutation.mutateAsync({
          leadId: selectedLead.followerId,
          taskId,
          data: { status: newStatus },
        });
        toast({ title: "Tarea reabierta" });
      } catch {
        toast({ title: "Error", description: "No se pudo actualizar la tarea", variant: "destructive" });
      }
    }
  };

  const handleDeleteActivity = async (activityId: string) => {
    if (!selectedLead) return;
    try {
      await deleteActivityMutation.mutateAsync({
        leadId: selectedLead.followerId,
        activityId,
      });
      toast({ title: "Entrada eliminada" });
    } catch {
      toast({ title: "Error", description: "No se pudo eliminar", variant: "destructive" });
    }
  };

  // Handler for saving lead info (email, phone, notes)
  const handleSaveLeadInfo = async () => {
    if (!selectedLead) return;

    try {
      await updateLeadMutation.mutateAsync({
        leadId: selectedLead.followerId,
        data: {
          email: editEmail,
          phone: editPhone,
          notes: editNotes,
        },
      });
      // Update local state
      setSelectedLead({
        ...selectedLead,
        email: editEmail,
        phone: editPhone,
        notes: editNotes,
      });
      toast({
        title: "Guardado",
        description: "Datos del lead actualizados",
      });
    } catch {
      toast({
        title: "Error",
        description: "No se pudo guardar los cambios",
        variant: "destructive",
      });
    }
  };

  // Handler for deleting a task
  const handleDeleteTask = async (taskId: string) => {
    if (!selectedLead) return;

    try {
      await deleteTaskMutation.mutateAsync({
        leadId: selectedLead.followerId,
        taskId,
      });
      toast({
        title: "Tarea eliminada",
      });
    } catch {
      toast({
        title: "Error",
        description: "No se pudo eliminar la tarea",
        variant: "destructive",
      });
    }
  };

  // Handler for saving task edit
  const handleSaveTaskEdit = async () => {
    if (!selectedLead || !editingTaskId || !editingTaskTitle.trim()) return;

    try {
      await updateTaskMutation.mutateAsync({
        leadId: selectedLead.followerId,
        taskId: editingTaskId,
        data: { title: editingTaskTitle.trim() },
      });
      setEditingTaskId(null);
      setEditingTaskTitle("");
      toast({
        title: "Tarea actualizada",
      });
    } catch {
      toast({
        title: "Error",
        description: "No se pudo actualizar la tarea",
        variant: "destructive",
      });
    }
  };

  const handleOpenDeleteDialog = (lead: LeadDisplay) => {
    setSelectedLead(lead);
    setIsDeleteDialogOpen(true);
  };

  const handleDeleteLead = async () => {
    if (!selectedLead) return;

    try {
      await deleteLeadMutation.mutateAsync(selectedLead.id);
      toast({
        title: "Lead eliminado",
        description: `${selectedLead.name || selectedLead.username} eliminado`,
      });
      setIsDeleteDialogOpen(false);
      setSelectedLead(null);
    } catch (err) {
      toast({
        title: "Error",
        description: err instanceof Error ? err.message : "No se pudo eliminar",
        variant: "destructive",
      });
    }
  };

  // Loading state
  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <Loader2 className="w-6 h-6 animate-spin text-primary" />
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-3">
        <AlertCircle className="w-8 h-8 text-destructive/70" />
        <p className="text-sm text-muted-foreground">No se pudieron cargar los leads</p>
        <p className="text-xs text-destructive/70">{error.message}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Pipeline</h1>
          <p className="text-sm text-muted-foreground">{leads.length} leads en el pipeline</p>
        </div>
        <Button onClick={handleOpenAddModal} size="sm" className="h-9 px-4">
          <Plus className="w-4 h-4 mr-2" />
          Nuevo Lead
        </Button>
      </div>

      {/* Kanban Board */}
      <div className="overflow-x-auto pb-4 -mx-4 px-4 md:mx-0 md:px-0">
        <div className="flex md:grid md:grid-cols-5 gap-3 h-[calc(100vh-12rem)] min-w-max md:min-w-0">
        {columns.map((column) => {
          const columnLeads = getLeadsByStatus(column.status);

          return (
            <div
              key={column.status}
              className="flex flex-col rounded-2xl overflow-hidden w-64 md:w-auto shrink-0 md:shrink bg-card/50 border border-border/50"
              onDragOver={handleDragOver}
              onDrop={() => handleDrop(column.status)}
            >
              {/* Column Header */}
              <div className="px-4 py-3 border-b border-border/30">
                <div className="flex items-center gap-2">
                  <span className={cn("opacity-80", column.color)}>{column.icon}</span>
                  <span className={cn("font-semibold text-sm", column.color)}>{column.title}</span>
                  <span className={cn("text-xs font-semibold px-2 py-0.5 rounded-full ml-auto", column.color, "bg-current/10")}>
                    {columnLeads.length}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mt-1">{column.description}</p>
              </div>

              {/* Cards */}
              <div className="flex-1 overflow-auto p-2 space-y-2">
                {columnLeads.length === 0 ? (
                  <div className="text-center py-16 text-muted-foreground/40 text-xs">
                    Sin leads
                  </div>
                ) : (
                  columnLeads.map((lead) => (
                    <div
                      key={lead.id}
                      draggable
                      onDragStart={() => handleDragStart(lead)}
                      onClick={() => handleViewLead(lead)}
                      className={cn(
                        "group p-3 rounded-xl bg-card border border-border/30 cursor-pointer transition-all",
                        "hover:border-violet-500/50 hover:shadow-md hover:shadow-violet-500/10 hover:bg-card/80",
                        draggedLead?.id === lead.id && "opacity-50 scale-95"
                      )}
                    >
                      <div className="flex items-start gap-3">
                        {/* Avatar - Clickable for Instagram */}
                        <button
                          onClick={(e) => {
                            e.stopPropagation(); // Always stop propagation
                            if (lead.platform === "instagram" && lead.instagramUsername) {
                              window.open(`https://instagram.com/${lead.instagramUsername}`, "_blank");
                            }
                          }}
                          className={cn(
                            "w-10 h-10 rounded-full shrink-0 overflow-hidden",
                            lead.platform === "instagram" && "hover:ring-2 hover:ring-violet-500 cursor-pointer",
                            lead.platform !== "instagram" && "cursor-default"
                          )}
                          title={lead.platform === "instagram" ? `Abrir @${lead.instagramUsername}` : undefined}
                        >
                          {lead.profilePicUrl ? (
                            <img
                              src={lead.profilePicUrl}
                              alt={lead.username}
                              className="w-full h-full object-cover"
                              onError={(e) => {
                                // Fallback to initials on error
                                (e.target as HTMLImageElement).style.display = "none";
                                (e.target as HTMLImageElement).nextElementSibling?.classList.remove("hidden");
                              }}
                            />
                          ) : null}
                          <div className={cn(
                            "w-full h-full bg-gradient-to-br from-violet-600 to-purple-600 flex items-center justify-center text-white text-xs font-medium",
                            lead.profilePicUrl && "hidden"
                          )}>
                            {lead.avatar}
                          </div>
                        </button>

                        {/* Name, Username & Time */}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <p className="font-medium text-sm truncate">{lead.name || lead.username}</p>
                            {lead.platform === "instagram" && (
                              <ExternalLink className="w-3 h-3 text-muted-foreground/50 opacity-0 group-hover:opacity-100" />
                            )}
                          </div>
                          <p className="text-xs text-muted-foreground flex items-center gap-1">
                            {platformIcons[lead.platform] || platformIcons.instagram}
                            <span className="truncate">@{lead.username.replace(/^@/, "")}</span>
                          </p>
                        </div>

                        {/* Messages & Time (instead of € values) */}
                        <div className="flex flex-col items-end shrink-0 text-muted-foreground">
                          {lead.totalMessages > 0 && (
                            <span className="flex items-center gap-1 text-xs">
                              <MessageCircle className="w-3 h-3" />
                              {lead.totalMessages}
                            </span>
                          )}
                          {lead.lastContact && (
                            <span className="text-[10px]">
                              {formatTimeAgo(lead.lastContact)}
                            </span>
                          )}
                        </div>

                        {/* Menu */}
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
                            <DropdownMenuItem onClick={(e) => { e.stopPropagation(); handleViewLead(lead); }}>
                              <Eye className="w-4 h-4 mr-2" />
                              Ver detalles
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={(e) => { e.stopPropagation(); navigate(`/inbox?id=${lead.followerId}`); }}>
                              <MessageCircle className="w-4 h-4 mr-2" />
                              Ir al chat
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              onClick={(e) => { e.stopPropagation(); handleOpenDeleteDialog(lead); }}
                              className="text-destructive focus:text-destructive"
                            >
                              <Trash2 className="w-4 h-4 mr-2" />
                              Eliminar
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          );
        })}
        </div>
      </div>

      {/* Load More Button */}
      {hasNextPage && (
        <div className="flex justify-center py-4">
          <Button
            variant="outline"
            onClick={() => fetchNextPage()}
            disabled={isFetchingNextPage}
            className="w-full max-w-xs"
          >
            {isFetchingNextPage ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Cargando...
              </>
            ) : (
              "Cargar más leads"
            )}
          </Button>
        </div>
      )}

      {/* Add Lead Modal */}
      <Dialog open={isAddModalOpen} onOpenChange={setIsAddModalOpen}>
        <DialogContent className="sm:max-w-[380px]">
          <DialogHeader>
            <DialogTitle className="text-base">Nuevo Lead</DialogTitle>
            <DialogDescription className="text-xs">
              Agrega un lead manualmente
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-3 py-3">
            <div className="grid gap-1.5">
              <Label htmlFor="name" className="text-xs">Nombre *</Label>
              <Input
                id="name"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="Nombre del contacto"
                className="h-9"
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="platform" className="text-xs">Plataforma</Label>
              <Select
                value={formData.platform}
                onValueChange={(value) => setFormData({ ...formData, platform: value })}
              >
                <SelectTrigger className="h-9">
                  <SelectValue placeholder="Seleccionar" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="instagram">Instagram</SelectItem>
                  <SelectItem value="telegram">Telegram</SelectItem>
                  <SelectItem value="whatsapp">WhatsApp</SelectItem>
                  <SelectItem value="manual">Otro</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="grid gap-1.5">
                <Label htmlFor="email" className="text-xs">Email</Label>
                <Input
                  id="email"
                  type="email"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  placeholder="email@ejemplo.com"
                  className="h-9"
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="phone" className="text-xs">Teléfono</Label>
                <Input
                  id="phone"
                  value={formData.phone}
                  onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                  placeholder="+34 600..."
                  className="h-9"
                />
              </div>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="notes" className="text-xs">Notas</Label>
              <Input
                id="notes"
                value={formData.notes}
                onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                placeholder="Notas adicionales..."
                className="h-9"
              />
            </div>
          </div>
          <DialogFooter className="gap-2">
            <Button variant="ghost" size="sm" onClick={() => setIsAddModalOpen(false)}>
              Cancelar
            </Button>
            <Button
              onClick={handleAddLead}
              disabled={createLeadMutation.isPending}
              size="sm"
            >
              {createLeadMutation.isPending ? (
                <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
              ) : (
                <Plus className="w-3.5 h-3.5 mr-1.5" />
              )}
              Agregar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* View Lead Modal - CRM Enhanced */}
      <Dialog open={isViewModalOpen} onOpenChange={setIsViewModalOpen}>
        <DialogContent className="sm:max-w-[500px] max-h-[90vh] overflow-hidden flex flex-col">
          {selectedLead && (
            <>
              {/* Compact Header */}
              <div className="flex items-center gap-3 pb-3 border-b">
                <div className="w-14 h-14 rounded-full overflow-hidden ring-2 ring-violet-500/30 shrink-0">
                  {selectedLead.profilePicUrl ? (
                    <img
                      src={selectedLead.profilePicUrl}
                      alt={selectedLead.username}
                      className="w-full h-full object-cover"
                      onError={(e) => {
                        (e.target as HTMLImageElement).style.display = "none";
                        (e.target as HTMLImageElement).nextElementSibling?.classList.remove("hidden");
                      }}
                    />
                  ) : null}
                  <div className={cn(
                    "w-full h-full bg-gradient-to-br from-violet-600 to-purple-600 flex items-center justify-center text-white text-lg font-medium",
                    selectedLead.profilePicUrl && "hidden"
                  )}>
                    {selectedLead.avatar}
                  </div>
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="font-semibold text-lg truncate">{selectedLead.name || selectedLead.username}</h3>
                  <p className="text-sm text-muted-foreground flex items-center gap-1">
                    {platformIcons[selectedLead.platform] || platformIcons.instagram}
                    @{selectedLead.instagramUsername || selectedLead.username}
                  </p>
                </div>
                <div className={cn("px-3 py-1 rounded-full text-xs font-semibold bg-current/10 capitalize", STATUS_COLORS[selectedLead.status])}>
                  {selectedLead.status}
                </div>
              </div>

              {/* Tabs */}
              <Tabs value={modalTab} onValueChange={setModalTab} className="flex-1 flex flex-col overflow-hidden">
                <TabsList className="grid w-full grid-cols-5">
                  <TabsTrigger value="info" className="text-xs">
                    <Eye className="w-3.5 h-3.5 mr-1.5" />
                    Info
                  </TabsTrigger>
                  <TabsTrigger value="intelligence" className="text-xs">
                    <Brain className="w-3.5 h-3.5 mr-1.5" />
                    AI
                  </TabsTrigger>
                  <TabsTrigger value="activity" className="text-xs">
                    <Activity className="w-3.5 h-3.5 mr-1.5" />
                    Actividad
                  </TabsTrigger>
                  <TabsTrigger value="tasks" className="text-xs">
                    <ListTodo className="w-3.5 h-3.5 mr-1.5" />
                    Tareas
                    {tasksData?.tasks?.filter((t: { status: string }) => t.status !== "completed")?.length ? (
                      <span className="ml-1 text-[10px] bg-violet-500/20 text-violet-400 px-1.5 rounded-full">
                        {tasksData.tasks.filter((t: { status: string }) => t.status !== "completed").length}
                      </span>
                    ) : null}
                  </TabsTrigger>
                  <TabsTrigger value="history" className="text-xs">
                    <History className="w-3.5 h-3.5 mr-1.5" />
                    Historial
                  </TabsTrigger>
                </TabsList>

                {/* Info Tab - Editable */}
                <TabsContent value="info" className="flex-1 overflow-auto mt-3 space-y-4">
                  {/* Stats Grid */}
                  <div className="grid grid-cols-3 gap-2">
                    <div className="p-2.5 rounded-lg bg-muted/30 text-center">
                      <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Estado</p>
                      <p className="text-sm font-medium capitalize">{selectedLead.status}</p>
                    </div>
                    <div className="p-2.5 rounded-lg bg-muted/30 text-center">
                      <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Mensajes</p>
                      <p className="text-sm font-medium">{selectedLead.totalMessages}</p>
                    </div>
                    <div className="p-2.5 rounded-lg bg-muted/30 text-center">
                      <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Último</p>
                      <p className="text-sm font-medium">{formatTimeAgo(selectedLead.lastContact) || "-"}</p>
                    </div>
                  </div>

                  {/* Editable Contact Info */}
                  <div className="space-y-3">
                    <p className="text-xs text-muted-foreground uppercase tracking-wide">Datos de contacto</p>
                    <div className="space-y-2">
                      <div className="flex items-center gap-2">
                        <Mail className="w-4 h-4 text-muted-foreground shrink-0" />
                        <Input
                          placeholder="email@ejemplo.com"
                          value={editEmail}
                          onChange={(e) => setEditEmail(e.target.value)}
                          className="h-8 text-sm"
                        />
                      </div>
                      <div className="flex items-center gap-2">
                        <Phone className="w-4 h-4 text-muted-foreground shrink-0" />
                        <Input
                          placeholder="+34 600 000 000"
                          value={editPhone}
                          onChange={(e) => setEditPhone(e.target.value)}
                          className="h-8 text-sm"
                        />
                      </div>
                    </div>
                  </div>

                  {/* Editable Notes */}
                  <div className="space-y-2">
                    <p className="text-xs text-muted-foreground uppercase tracking-wide">Notas</p>
                    <Textarea
                      placeholder="Notas sobre este lead..."
                      value={editNotes}
                      onChange={(e) => setEditNotes(e.target.value)}
                      className="h-24 text-sm resize-none"
                    />
                  </div>

                  {/* Save Button */}
                  {(editEmail !== (selectedLead.email || "") ||
                    editPhone !== (selectedLead.phone || "") ||
                    editNotes !== (selectedLead.notes || "")) && (
                    <Button
                      onClick={handleSaveLeadInfo}
                      disabled={updateLeadMutation.isPending}
                      className="w-full bg-violet-600 hover:bg-violet-700"
                    >
                      {updateLeadMutation.isPending ? (
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      ) : (
                        <CheckCircle className="w-4 h-4 mr-2" />
                      )}
                      Guardar cambios
                    </Button>
                  )}

                  {/* Action Buttons */}
                  <div className="grid grid-cols-2 gap-2 pt-2">
                    {selectedLead.platform === "instagram" && (
                      <Button
                        variant="outline"
                        className="w-full"
                        onClick={() => window.open(`https://instagram.com/${selectedLead.instagramUsername}`, "_blank")}
                      >
                        <Instagram className="w-4 h-4 mr-2" />
                        Instagram
                      </Button>
                    )}
                    <Button
                      className="w-full bg-violet-600 hover:bg-violet-700"
                      onClick={() => {
                        setIsViewModalOpen(false);
                        navigate(`/inbox?id=${selectedLead.followerId}`);
                      }}
                    >
                      <MessageCircle className="w-4 h-4 mr-2" />
                      Ir al Chat
                    </Button>
                  </div>
                </TabsContent>

                {/* Intelligence Tab - Audience Profile */}
                <TabsContent value="intelligence" className="flex-1 overflow-auto mt-3">
                  <ProfilePanel
                    creatorId={getCreatorId()}
                    followerId={selectedLead.followerId}
                    showCloseButton={false}
                    className="border-0 shadow-none"
                  />
                </TabsContent>

                {/* Activity Tab - INTELLIGENT Prediction */}
                <TabsContent value="activity" className="flex-1 overflow-auto mt-3 space-y-3">
                  {statsLoading ? (
                    <div className="flex items-center justify-center py-8">
                      <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
                    </div>
                  ) : statsData?.stats ? (
                    <>
                      {/* 1. SALE PREDICTION BAR */}
                      <div className="p-3 rounded-lg border bg-card">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-xs text-muted-foreground uppercase tracking-wide">
                            🎯 Predicción de venta
                          </span>
                          <div className="flex items-center gap-2">
                            <span className={cn(
                              "text-lg font-bold",
                              statsData.stats.probabilidad_venta >= 61 && "text-emerald-500",
                              statsData.stats.probabilidad_venta >= 31 && statsData.stats.probabilidad_venta < 61 && "text-amber-500",
                              statsData.stats.probabilidad_venta < 31 && "text-red-500"
                            )}>
                              {statsData.stats.probabilidad_venta}%
                            </span>
                            <span className={cn(
                              "text-[10px] px-1.5 py-0.5 rounded",
                              statsData.stats.confianza_prediccion === "Alta" && "bg-emerald-500/20 text-emerald-400",
                              statsData.stats.confianza_prediccion === "Media" && "bg-amber-500/20 text-amber-400",
                              statsData.stats.confianza_prediccion === "Baja" && "bg-muted text-muted-foreground"
                            )}>
                              {statsData.stats.confianza_prediccion}
                            </span>
                          </div>
                        </div>
                        <div className="w-full h-2.5 bg-muted rounded-full overflow-hidden">
                          <div
                            className={cn(
                              "h-full rounded-full transition-all duration-500",
                              statsData.stats.probabilidad_venta >= 61 && "bg-emerald-500",
                              statsData.stats.probabilidad_venta >= 31 && statsData.stats.probabilidad_venta < 61 && "bg-amber-500",
                              statsData.stats.probabilidad_venta < 31 && "bg-red-500"
                            )}
                            style={{ width: `${statsData.stats.probabilidad_venta}%` }}
                          />
                        </div>
                      </div>

                      {/* 2. DETECTED PRODUCT */}
                      {statsData.stats.producto_detectado && (
                        <div className="p-3 rounded-lg border bg-card">
                          <span className="text-xs text-muted-foreground uppercase tracking-wide">
                            📦 Producto detectado
                          </span>
                          <div className="flex items-center justify-between mt-1">
                            <span className="text-sm font-medium">
                              {statsData.stats.producto_detectado.emoji} {statsData.stats.producto_detectado.name}
                            </span>
                            <span className="text-sm text-muted-foreground">
                              €{statsData.stats.producto_detectado.estimated_price}
                            </span>
                          </div>
                          {statsData.stats.valor_estimado > 0 && (
                            <p className="text-xs text-emerald-400 mt-1">
                              Valor estimado: €{statsData.stats.valor_estimado.toFixed(0)}
                            </p>
                          )}
                        </div>
                      )}

                      {/* 3. NEXT STEP */}
                      <div className={cn(
                        "p-3 rounded-lg border",
                        statsData.stats.siguiente_paso?.prioridad === "urgente" && "bg-red-500/10 border-red-500/30",
                        statsData.stats.siguiente_paso?.prioridad === "alta" && "bg-amber-500/10 border-amber-500/30",
                        statsData.stats.siguiente_paso?.prioridad === "media" && "bg-blue-500/10 border-blue-500/30",
                        statsData.stats.siguiente_paso?.prioridad === "baja" && "bg-muted/30 border-border"
                      )}>
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-muted-foreground uppercase tracking-wide">
                            💡 Siguiente paso
                          </span>
                          <span className={cn(
                            "text-[10px] px-1.5 py-0.5 rounded uppercase",
                            statsData.stats.siguiente_paso?.prioridad === "urgente" && "bg-red-500/20 text-red-400",
                            statsData.stats.siguiente_paso?.prioridad === "alta" && "bg-amber-500/20 text-amber-400",
                            statsData.stats.siguiente_paso?.prioridad === "media" && "bg-blue-500/20 text-blue-400",
                            statsData.stats.siguiente_paso?.prioridad === "baja" && "bg-muted text-muted-foreground"
                          )}>
                            {statsData.stats.siguiente_paso?.prioridad}
                          </span>
                        </div>
                        <p className="text-sm font-medium mt-1">
                          {statsData.stats.siguiente_paso?.emoji} {statsData.stats.siguiente_paso?.texto}
                        </p>
                      </div>

                      {/* 4. ENGAGEMENT */}
                      <div className="p-3 rounded-lg border bg-card">
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-muted-foreground uppercase tracking-wide">
                            💬 Engagement
                          </span>
                          <span className={cn(
                            "px-2 py-0.5 rounded-full text-xs font-semibold",
                            statsData.stats.engagement === "Alto" && "bg-emerald-500/20 text-emerald-400",
                            statsData.stats.engagement === "Medio" && "bg-amber-500/20 text-amber-400",
                            statsData.stats.engagement === "Bajo" && "bg-red-500/20 text-red-400"
                          )}>
                            {statsData.stats.engagement}
                          </span>
                        </div>
                        <p className="text-sm mt-1">
                          {statsData.stats.engagement_detalle}
                        </p>
                      </div>

                      {/* 5. DETECTED SIGNALS BY CATEGORY */}
                      {statsData.stats.total_senales > 0 && (
                        <div className="p-3 rounded-lg border bg-card">
                          <span className="text-xs text-muted-foreground uppercase tracking-wide">
                            📊 Señales detectadas ({statsData.stats.total_senales})
                          </span>

                          {/* Purchase signals */}
                          {statsData.stats.senales_por_categoria?.compra?.length > 0 && (
                            <div className="mt-2">
                              <p className="text-[10px] text-emerald-400 uppercase tracking-wide mb-1">🟢 Compra</p>
                              {statsData.stats.senales_por_categoria.compra.map((s: { emoji: string; description: string; weight: number }, i: number) => (
                                <div key={i} className="flex items-center gap-2 text-sm text-emerald-400">
                                  <span>{s.emoji}</span>
                                  <span>{s.description}</span>
                                  <span className="text-[10px] text-muted-foreground">(+{s.weight}%)</span>
                                </div>
                              ))}
                            </div>
                          )}

                          {/* Interest signals */}
                          {statsData.stats.senales_por_categoria?.interes?.length > 0 && (
                            <div className="mt-2">
                              <p className="text-[10px] text-blue-400 uppercase tracking-wide mb-1">🔵 Interés</p>
                              {statsData.stats.senales_por_categoria.interes.map((s: { emoji: string; description: string; weight: number }, i: number) => (
                                <div key={i} className="flex items-center gap-2 text-sm text-blue-400">
                                  <span>{s.emoji}</span>
                                  <span>{s.description}</span>
                                  <span className="text-[10px] text-muted-foreground">(+{s.weight}%)</span>
                                </div>
                              ))}
                            </div>
                          )}

                          {/* Objection signals */}
                          {statsData.stats.senales_por_categoria?.objecion?.length > 0 && (
                            <div className="mt-2">
                              <p className="text-[10px] text-red-400 uppercase tracking-wide mb-1">🔴 Objeciones</p>
                              {statsData.stats.senales_por_categoria.objecion.map((s: { emoji: string; description: string; weight: number }, i: number) => (
                                <div key={i} className="flex items-center gap-2 text-sm text-red-400">
                                  <span>{s.emoji}</span>
                                  <span>{s.description}</span>
                                  <span className="text-[10px] text-muted-foreground">({s.weight}%)</span>
                                </div>
                              ))}
                            </div>
                          )}

                          {/* Behavior signals */}
                          {statsData.stats.senales_por_categoria?.comportamiento?.length > 0 && (
                            <div className="mt-2">
                              <p className="text-[10px] text-violet-400 uppercase tracking-wide mb-1">⚡ Comportamiento</p>
                              {statsData.stats.senales_por_categoria.comportamiento.map((s: { emoji: string; description: string; weight: number; detail?: string }, i: number) => (
                                <div key={i} className="flex items-center gap-2 text-sm text-violet-400">
                                  <span>{s.emoji}</span>
                                  <span>{s.description}</span>
                                  {s.detail && <span className="text-[10px] text-muted-foreground">({s.detail})</span>}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}

                      {/* 6. QUICK STATS */}
                      <div className="grid grid-cols-2 gap-2">
                        <div className="p-2.5 rounded-lg bg-muted/30 text-center">
                          <p className="text-lg font-semibold">{statsData.stats.mensajes_lead}</p>
                          <p className="text-[10px] text-muted-foreground">Msgs del lead</p>
                        </div>
                        <div className="p-2.5 rounded-lg bg-muted/30 text-center">
                          <p className="text-lg font-semibold">{statsData.stats.mensajes_bot}</p>
                          <p className="text-[10px] text-muted-foreground">Msgs del bot</p>
                        </div>
                      </div>

                      {/* 7. RESPONSE TIME */}
                      {statsData.stats.metricas?.tiempo_respuesta_promedio && (
                        <div className="p-2.5 rounded-lg bg-muted/20 text-center">
                          <p className="text-xs text-muted-foreground">Tiempo de respuesta promedio</p>
                          <p className="text-sm font-semibold">{statsData.stats.metricas.tiempo_respuesta_promedio}</p>
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="text-center py-8 text-muted-foreground text-sm">
                      No hay datos de actividad disponibles
                    </div>
                  )}
                </TabsContent>

                {/* Tasks Tab */}
                <TabsContent value="tasks" className="flex-1 overflow-auto mt-3 space-y-3">
                  {/* Add Task */}
                  <div className="flex gap-2">
                    <Input
                      placeholder="Nueva tarea..."
                      value={newTaskTitle}
                      onChange={(e) => setNewTaskTitle(e.target.value)}
                      className="h-9 text-sm"
                      onKeyDown={(e) => e.key === "Enter" && handleAddTask()}
                    />
                    <Button
                      size="sm"
                      onClick={handleAddTask}
                      disabled={createTaskMutation.isPending || !newTaskTitle.trim()}
                      className="shrink-0"
                    >
                      {createTaskMutation.isPending ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Plus className="w-4 h-4" />
                      )}
                    </Button>
                  </div>

                  {/* Pending Tasks */}
                  <div className="space-y-2">
                    {tasksData?.tasks?.filter((t: { status: string }) => t.status !== "completed").length === 0 && (
                      <p className="text-center text-sm text-muted-foreground py-4">
                        No hay tareas pendientes
                      </p>
                    )}
                    {tasksData?.tasks?.filter((t: { status: string }) => t.status !== "completed").map((task: { id: string; title: string; status: string; priority: string; due_date?: string }) => (
                      <div
                        key={task.id}
                        className={cn(
                          "flex items-start gap-2 p-2 rounded-lg border bg-card transition-all duration-300",
                          completingTaskId === task.id
                            ? "border-emerald-500/50 bg-emerald-500/10 opacity-60"
                            : "border-border hover:border-violet-500/30"
                        )}
                      >
                        <button
                          onClick={() => handleToggleTask(task.id, task.status)}
                          className="mt-0.5"
                          disabled={completingTaskId === task.id}
                        >
                          {completingTaskId === task.id ? (
                            <CheckSquare className="w-4 h-4 text-emerald-500 animate-pulse" />
                          ) : (
                            <Square className="w-4 h-4 text-muted-foreground hover:text-violet-500" />
                          )}
                        </button>
                        <div className="flex-1 min-w-0">
                          {editingTaskId === task.id ? (
                            <div className="flex gap-1">
                              <Input
                                value={editingTaskTitle}
                                onChange={(e) => setEditingTaskTitle(e.target.value)}
                                className="h-7 text-sm"
                                onKeyDown={(e) => {
                                  if (e.key === "Enter") handleSaveTaskEdit();
                                  if (e.key === "Escape") { setEditingTaskId(null); setEditingTaskTitle(""); }
                                }}
                                autoFocus
                              />
                              <Button size="sm" variant="ghost" className="h-7 px-2" onClick={handleSaveTaskEdit}>
                                <CheckCircle className="w-3.5 h-3.5" />
                              </Button>
                            </div>
                          ) : (
                            <p className={cn(
                              "text-sm transition-all duration-300",
                              completingTaskId === task.id && "line-through text-muted-foreground"
                            )}>
                              {task.title}
                            </p>
                          )}
                          {task.due_date && (
                            <p className="text-[10px] text-muted-foreground flex items-center gap-1 mt-0.5">
                              <Calendar className="w-3 h-3" />
                              {new Date(task.due_date).toLocaleDateString()}
                            </p>
                          )}
                        </div>
                        {task.priority === "high" || task.priority === "urgent" ? (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-500/20 text-red-400">
                            {task.priority === "urgent" ? "Urgente" : "Alta"}
                          </span>
                        ) : null}
                        {editingTaskId !== task.id && completingTaskId !== task.id && (
                          <div className="flex gap-1">
                            <button
                              onClick={() => { setEditingTaskId(task.id); setEditingTaskTitle(task.title); }}
                              className="p-1 text-muted-foreground hover:text-violet-500 transition-colors"
                              title="Editar"
                            >
                              <Pencil className="w-3.5 h-3.5" />
                            </button>
                            <button
                              onClick={() => handleDeleteTask(task.id)}
                              className="p-1 text-muted-foreground hover:text-red-500 transition-colors"
                              title="Eliminar"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>

                  {/* Completed Tasks */}
                  {tasksData?.tasks?.filter((t: { status: string }) => t.status === "completed").length > 0 && (
                    <div className="space-y-2 pt-2 border-t">
                      <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Completadas</p>
                      {tasksData?.tasks?.filter((t: { status: string }) => t.status === "completed").map((task: { id: string; title: string; status: string }) => (
                        <div
                          key={task.id}
                          className="flex items-center gap-2 p-2 rounded-lg bg-muted/20 border border-muted"
                        >
                          <button
                            onClick={() => handleToggleTask(task.id, task.status)}
                            className="shrink-0"
                          >
                            <CheckSquare className="w-4 h-4 text-emerald-500" />
                          </button>
                          <p className="text-sm line-through text-muted-foreground flex-1">{task.title}</p>
                          <button
                            onClick={() => handleDeleteTask(task.id)}
                            className="p-1 text-muted-foreground hover:text-red-500 transition-colors"
                            title="Eliminar"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </TabsContent>

                {/* History Tab */}
                <TabsContent value="history" className="flex-1 overflow-auto mt-3">
                  <div className="space-y-2">
                    {activitiesData?.activities?.length === 0 && (
                      <p className="text-center text-sm text-muted-foreground py-8">
                        Sin actividad registrada
                      </p>
                    )}
                    {activitiesData?.activities?.map((activity: { id: string; activity_type: string; description: string; created_at: string }) => (
                      <div
                        key={activity.id}
                        className="group flex items-start gap-2 p-2 rounded-lg bg-muted/20 hover:bg-muted/30 transition-colors"
                      >
                        <div className={cn(
                          "w-6 h-6 rounded-full flex items-center justify-center shrink-0 mt-0.5",
                          activity.activity_type === "note" && "bg-blue-500/20 text-blue-400",
                          activity.activity_type === "status_change" && "bg-amber-500/20 text-amber-400",
                          activity.activity_type === "task_created" && "bg-violet-500/20 text-violet-400",
                          activity.activity_type === "task_completed" && "bg-emerald-500/20 text-emerald-400"
                        )}>
                          {activity.activity_type === "note" && <StickyNote className="w-3 h-3" />}
                          {activity.activity_type === "status_change" && <Users className="w-3 h-3" />}
                          {activity.activity_type === "task_created" && <ListTodo className="w-3 h-3" />}
                          {activity.activity_type === "task_completed" && <CheckCircle className="w-3 h-3" />}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm">{activity.description}</p>
                          <p className="text-[10px] text-muted-foreground mt-0.5">
                            {new Date(activity.created_at).toLocaleString()}
                          </p>
                        </div>
                        <button
                          onClick={() => handleDeleteActivity(activity.id)}
                          className="p-1.5 text-muted-foreground/50 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-all shrink-0"
                          title="Eliminar"
                          disabled={deleteActivityMutation.isPending}
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    ))}
                  </div>
                </TabsContent>
              </Tabs>

              {/* Footer Actions */}
              <div className="flex justify-end pt-3 border-t mt-3">
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-destructive hover:text-destructive"
                  onClick={() => {
                    setIsViewModalOpen(false);
                    if (selectedLead) handleOpenDeleteDialog(selectedLead);
                  }}
                >
                  <Trash2 className="w-3.5 h-3.5 mr-1.5" />
                  Eliminar lead
                </Button>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>


      {/* Delete Confirmation Dialog */}
      <AlertDialog open={isDeleteDialogOpen} onOpenChange={setIsDeleteDialogOpen}>
        <AlertDialogContent className="sm:max-w-[340px]">
          <AlertDialogHeader>
            <AlertDialogTitle className="text-base">Eliminar Lead</AlertDialogTitle>
            <AlertDialogDescription className="text-sm">
              ¿Eliminar a <span className="font-medium text-foreground">{selectedLead?.name || selectedLead?.username}</span>?
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter className="gap-2">
            <AlertDialogCancel className="h-8 text-xs">Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteLead}
              className="h-8 text-xs bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleteLeadMutation.isPending ? (
                <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
              ) : (
                <Trash2 className="w-3.5 h-3.5 mr-1.5" />
              )}
              Eliminar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
