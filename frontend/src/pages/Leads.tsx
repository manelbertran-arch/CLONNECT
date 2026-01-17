import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { Instagram, MoreHorizontal, Plus, Loader2, AlertCircle, MessageCircle, Send, Eye, Pencil, Trash2, Users, Flame, Star, CheckCircle, Ghost, Clock, ExternalLink, Settings } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import { useConversations, useUpdateLeadStatus, useCreateManualLead, useUpdateLead, useDeleteLead } from "@/hooks/useApi";
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
  const { data, isLoading, error } = useConversations();
  const [draggedLead, setDraggedLead] = useState<LeadDisplay | null>(null);
  const [localStatusOverrides, setLocalStatusOverrides] = useState<Record<string, LeadStatus>>({});
  const { toast } = useToast();
  const navigate = useNavigate();
  const updateStatusMutation = useUpdateLeadStatus();
  const createLeadMutation = useCreateManualLead();
  const updateLeadMutation = useUpdateLead();
  const deleteLeadMutation = useDeleteLead();

  // Modal states
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [isViewModalOpen, setIsViewModalOpen] = useState(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [selectedLead, setSelectedLead] = useState<LeadDisplay | null>(null);
  const [formData, setFormData] = useState(initialFormState);

  // Product price from backend
  const backendPrice = data?.product_price ?? DEFAULT_PRODUCT_PRICE;
  const [editingPrice, setEditingPrice] = useState<number | null>(null);
  const [isPricePopoverOpen, setIsPricePopoverOpen] = useState(false);

  // Initialize editingPrice when backend data arrives
  const productPrice = editingPrice ?? backendPrice;

  const leads = useMemo(() => {
    if (!data?.conversations) return [];

    return data.conversations.map((convo): LeadDisplay => {
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

      // Value = product_price × (scoring / 100)
      const value = calculateLeadValue(status, productPrice);

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
  }, [data?.conversations, localStatusOverrides, productPrice]);

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

  const totalPipelineValue = leads.reduce((sum, lead) => sum + lead.value, 0);

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
    setIsViewModalOpen(true);
  };

  const handleOpenEditModal = (lead: LeadDisplay) => {
    setSelectedLead(lead);
    setFormData({
      name: lead.name || lead.username,
      platform: lead.platform,
      email: lead.email || "",
      phone: lead.phone || "",
      notes: lead.notes || "",
    });
    setIsEditModalOpen(true);
  };

  const handleEditLead = async () => {
    if (!selectedLead) return;

    try {
      await updateLeadMutation.mutateAsync({
        leadId: selectedLead.id,
        data: {
          name: formData.name || undefined,
          email: formData.email || undefined,
          phone: formData.phone || undefined,
          notes: formData.notes || undefined,
        },
      });
      toast({
        title: "Lead actualizado",
        description: `${formData.name} guardado`,
      });
      setIsEditModalOpen(false);
      setSelectedLead(null);
    } catch (err) {
      toast({
        title: "Error",
        description: err instanceof Error ? err.message : "No se pudo actualizar",
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
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <span>{leads.length} leads · €{totalPipelineValue.toLocaleString()} potencial</span>
            <Popover open={isPricePopoverOpen} onOpenChange={setIsPricePopoverOpen}>
              <PopoverTrigger asChild>
                <button className="text-muted-foreground/50 hover:text-muted-foreground transition-colors">
                  <Settings className="w-3.5 h-3.5" />
                </button>
              </PopoverTrigger>
              <PopoverContent className="w-64" align="start">
                <div className="space-y-3">
                  <div>
                    <Label className="text-xs">Precio del producto</Label>
                    <p className="text-[10px] text-muted-foreground">Se usa para calcular el valor de cada lead</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm">€</span>
                    <Input
                      type="number"
                      value={productPrice}
                      onChange={(e) => setEditingPrice(Number(e.target.value))}
                      className="h-8"
                      min={0}
                    />
                  </div>
                  <div className="text-[10px] text-muted-foreground space-y-1">
                    <p>Fantasma: €0 (0%)</p>
                    <p>Nuevo: €{Math.round(productPrice * 0.25)} (25%)</p>
                    <p>Interesado: €{Math.round(productPrice * 0.50)} (50%)</p>
                    <p>Caliente: €{Math.round(productPrice * 0.75)} (75%)</p>
                    <p>Cliente: €{productPrice} (100%)</p>
                  </div>
                </div>
              </PopoverContent>
            </Popover>
          </div>
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
                          {/* Last contact & message count */}
                          <div className="flex items-center gap-2 mt-1 text-[10px] text-muted-foreground/70">
                            {lead.totalMessages > 0 && (
                              <span className="flex items-center gap-0.5">
                                <MessageCircle className="w-3 h-3" />
                                {lead.totalMessages}
                              </span>
                            )}
                            {lead.lastContact && (
                              <span className="flex items-center gap-0.5">
                                <Clock className="w-3 h-3" />
                                {formatTimeAgo(lead.lastContact)}
                              </span>
                            )}
                          </div>
                        </div>

                        {/* Value & Score */}
                        <div className="flex flex-col items-end shrink-0">
                          <span className={cn("text-sm font-semibold", STATUS_COLORS[lead.status])}>
                            €{lead.value}
                          </span>
                          <span className="text-[10px] text-muted-foreground">
                            {lead.score}%
                          </span>
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
                              Ver
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={(e) => { e.stopPropagation(); handleOpenEditModal(lead); }}>
                              <Pencil className="w-4 h-4 mr-2" />
                              Editar
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

      {/* View Lead Modal */}
      <Dialog open={isViewModalOpen} onOpenChange={setIsViewModalOpen}>
        <DialogContent className="sm:max-w-[400px]">
          {selectedLead && (
            <div className="space-y-4">
              {/* Profile Header with Large Photo */}
              <div className="flex flex-col items-center text-center pt-2">
                {/* Large Avatar */}
                <div className="w-24 h-24 rounded-full overflow-hidden ring-4 ring-violet-500/30 mb-3">
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
                    "w-full h-full bg-gradient-to-br from-violet-600 to-purple-600 flex items-center justify-center text-white text-2xl font-medium",
                    selectedLead.profilePicUrl && "hidden"
                  )}>
                    {selectedLead.avatar}
                  </div>
                </div>

                {/* Name & Username */}
                <h3 className="font-semibold text-lg">{selectedLead.name || selectedLead.username}</h3>
                <p className="text-sm text-muted-foreground flex items-center gap-1">
                  {platformIcons[selectedLead.platform] || platformIcons.instagram}
                  @{selectedLead.instagramUsername || selectedLead.username}
                </p>

                {/* Value Badge */}
                <div className={cn("mt-2 px-3 py-1 rounded-full text-sm font-semibold", STATUS_COLORS[selectedLead.status])}>
                  €{selectedLead.value} · {selectedLead.score}%
                </div>
              </div>

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

              {/* Contact Info */}
              {(selectedLead.email || selectedLead.phone) && (
                <div className="space-y-1.5 text-sm">
                  {selectedLead.email && (
                    <p className="text-muted-foreground">📧 {selectedLead.email}</p>
                  )}
                  {selectedLead.phone && (
                    <p className="text-muted-foreground">📱 {selectedLead.phone}</p>
                  )}
                </div>
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
                    Ver Instagram
                  </Button>
                )}
                <Button
                  className="w-full bg-violet-600 hover:bg-violet-700"
                  onClick={() => {
                    setIsViewModalOpen(false);
                    navigate(`/new/mensajes/${selectedLead.followerId}`);
                  }}
                >
                  <MessageCircle className="w-4 h-4 mr-2" />
                  Ir al Chat
                </Button>
              </div>

              {/* Secondary Actions */}
              <div className="flex justify-center gap-2 pt-1">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setIsViewModalOpen(false);
                    if (selectedLead) handleOpenEditModal(selectedLead);
                  }}
                >
                  <Pencil className="w-3.5 h-3.5 mr-1.5" />
                  Editar
                </Button>
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
                  Eliminar
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Edit Lead Modal */}
      <Dialog open={isEditModalOpen} onOpenChange={setIsEditModalOpen}>
        <DialogContent className="sm:max-w-[360px]">
          <DialogHeader>
            <DialogTitle className="text-base">Editar Lead</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3 py-3">
            <div className="grid gap-1.5">
              <Label htmlFor="edit-name" className="text-xs">Nombre</Label>
              <Input
                id="edit-name"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                className="h-9"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="grid gap-1.5">
                <Label htmlFor="edit-email" className="text-xs">Email</Label>
                <Input
                  id="edit-email"
                  type="email"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  placeholder="email@ejemplo.com"
                  className="h-9"
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="edit-phone" className="text-xs">Teléfono</Label>
                <Input
                  id="edit-phone"
                  value={formData.phone}
                  onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                  placeholder="+34 600..."
                  className="h-9"
                />
              </div>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="edit-notes" className="text-xs">Notas</Label>
              <Input
                id="edit-notes"
                value={formData.notes}
                onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                placeholder="Notas adicionales..."
                className="h-9"
              />
            </div>
          </div>
          <DialogFooter className="gap-2">
            <Button variant="ghost" size="sm" onClick={() => setIsEditModalOpen(false)}>
              Cancelar
            </Button>
            <Button
              onClick={handleEditLead}
              disabled={updateLeadMutation.isPending}
              size="sm"
            >
              {updateLeadMutation.isPending ? (
                <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
              ) : (
                <CheckCircle className="w-3.5 h-3.5 mr-1.5" />
              )}
              Guardar
            </Button>
          </DialogFooter>
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
