import { useState, useMemo } from "react";
import { Instagram, MoreHorizontal, Plus, Loader2, AlertCircle, MessageCircle, Send, Eye, Pencil, Trash2, Users, Flame, Star, CheckCircle, Ghost } from "lucide-react";
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
import { cn } from "@/lib/utils";
import { useConversations, useUpdateLeadStatus, useCreateManualLead, useUpdateLead, useDeleteLead } from "@/hooks/useApi";
import { useToast } from "@/hooks/use-toast";
import type { Conversation } from "@/types/api";
import { getPurchaseIntent, detectPlatform, getDisplayName } from "@/types/api";

// Sistema de Embudo Estándar
type LeadStatus = "nuevo" | "interesado" | "caliente" | "cliente" | "fantasma";

interface LeadDisplay {
  id: string;
  name: string;
  username: string;
  score: number;         // Pipeline score (20/40/60/80/100) - main display
  intentScore: number;   // AI intent score (0-100) - secondary display
  value: number;
  status: LeadStatus;
  avatar: string;
  platform: string;
  email: string;
  phone: string;
  notes: string;
}

// Configuración de columnas con diseño limpio
const columns: { status: LeadStatus; title: string; icon: React.ReactNode; color: string; gradient: string }[] = [
  { status: "nuevo", title: "Nuevos", icon: <Users className="w-4 h-4" />, color: "text-slate-400", gradient: "from-slate-500/20 to-slate-600/10" },
  { status: "interesado", title: "Interesados", icon: <Star className="w-4 h-4" />, color: "text-amber-400", gradient: "from-amber-500/20 to-amber-600/10" },
  { status: "caliente", title: "Calientes", icon: <Flame className="w-4 h-4" />, color: "text-rose-400", gradient: "from-rose-500/20 to-rose-600/10" },
  { status: "cliente", title: "Clientes", icon: <CheckCircle className="w-4 h-4" />, color: "text-emerald-400", gradient: "from-emerald-500/20 to-emerald-600/10" },
  { status: "fantasma", title: "Fantasmas", icon: <Ghost className="w-4 h-4" />, color: "text-gray-500", gradient: "from-gray-500/20 to-gray-600/10" },
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

/**
 * Clasificar lead según embudo estándar
 * - cliente: is_customer = true
 * - caliente: intent >= 0.50 (quiere comprar)
 * - interesado: intent >= 0.20 (hace preguntas)
 * - fantasma: sin respuesta +7 días (detectado en backend)
 * - nuevo: por defecto
 */
function getLeadStatus(convo: Conversation): LeadStatus {
  if (convo.is_customer) return "cliente";
  // Si el backend ya clasifica como fantasma, respetar
  if (convo.lead_status === "fantasma") return "fantasma";
  const intent = getPurchaseIntent(convo);
  if (intent >= 0.50) return "caliente";
  if (intent >= 0.20) return "interesado";
  return "nuevo";
}

function estimateValue(convo: Conversation): number {
  const baseValue = 97;
  const intent = getPurchaseIntent(convo);
  if (convo.is_customer) return 0; // Already converted
  if (intent >= 0.75) return 497;
  if (intent >= 0.50) return 297;
  if (intent >= 0.25) return 197;
  return baseValue;
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

  const leads = useMemo(() => {
    if (!data?.conversations) return [];

    return data.conversations.map((convo): LeadDisplay => {
      const platform = convo.platform || detectPlatform(convo.follower_id);
      const displayName = getDisplayName(convo);
      const intent = getPurchaseIntent(convo);
      const leadId = convo.id || convo.follower_id;

      // Status priority:
      // 1. Local override (from optimistic update during drag & drop)
      // 2. Backend lead_status (persisted pipeline status)
      // 3. Derived from purchase_intent (legacy fallback)
      const status = localStatusOverrides[leadId]
        || (convo.lead_status as LeadStatus)
        || getLeadStatus(convo);

      // Pipeline score: derive from status (nuevo embudo)
      // nuevo=10, interesado=35, caliente=70, cliente=100, fantasma=5
      const pipelineScoreMap: Record<LeadStatus, number> = {
        nuevo: 10,
        interesado: 35,
        caliente: 70,
        cliente: 100,
        fantasma: 5,
      };
      const pipelineScore = convo.pipeline_score ?? pipelineScoreMap[status] ?? 10;

      // AI Intent score: 0-100 from purchase_intent
      const intentScore = convo.purchase_intent_score
        ?? Math.round(intent * 100);

      return {
        id: leadId, // Prefer UUID id for reliable DB lookups
        name: convo.name || "",
        username: displayName,
        score: pipelineScore,      // Stage-based score (main display)
        intentScore: intentScore,  // AI intent score (secondary)
        value: estimateValue(convo),
        status,
        avatar: getInitials(convo.name, convo.username, convo.follower_id),
        platform,
        email: convo.email || "",
        phone: convo.phone || "",
        notes: convo.notes || "",
      };
    });
  }, [data?.conversations, localStatusOverrides]);

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
    <div className="space-y-4">
      {/* Page Color Accent - Rose/Red gradient for Leads/Sales */}
      <div className="h-1 w-full bg-gradient-to-r from-rose-500 via-red-500 to-orange-500 rounded-full opacity-80" />

      {/* Header - Minimal */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">Pipeline</h1>
          <p className="text-xs text-muted-foreground">
            {leads.length} leads · €{totalPipelineValue.toLocaleString()}
          </p>
        </div>
        <Button
          onClick={handleOpenAddModal}
          size="sm"
          className="h-8 px-3"
        >
          <Plus className="w-3.5 h-3.5 mr-1.5" />
          Nuevo
        </Button>
      </div>

      {/* Kanban Board */}
      <div className="overflow-x-auto pb-2 -mx-4 px-4 md:mx-0 md:px-0">
        <div className="flex md:grid md:grid-cols-5 gap-2 h-[calc(100vh-10rem)] min-w-max md:min-w-0">
        {columns.map((column) => {
          const columnLeads = getLeadsByStatus(column.status);

          return (
            <div
              key={column.status}
              className={cn(
                "flex flex-col rounded-xl overflow-hidden w-64 md:w-auto shrink-0 md:shrink",
                "bg-gradient-to-b",
                column.gradient
              )}
              onDragOver={handleDragOver}
              onDrop={() => handleDrop(column.status)}
            >
              {/* Column Header - Compact */}
              <div className="px-3 py-2.5 flex items-center gap-2">
                <span className={cn("opacity-80", column.color)}>{column.icon}</span>
                <span className="font-medium text-sm">{column.title}</span>
                <span className="text-xs text-muted-foreground/70 ml-auto">{columnLeads.length}</span>
              </div>

              {/* Cards */}
              <div className="flex-1 overflow-auto px-2 pb-2 space-y-2">
                {columnLeads.length === 0 ? (
                  <div className="text-center py-12 text-muted-foreground/50 text-xs">
                    Vacío
                  </div>
                ) : (
                  columnLeads.map((lead) => (
                    <div
                      key={lead.id}
                      draggable
                      onDragStart={() => handleDragStart(lead)}
                      className={cn(
                        "group p-3 rounded-lg bg-card/80 backdrop-blur-sm cursor-grab active:cursor-grabbing transition-all",
                        "hover:bg-card hover:shadow-md",
                        draggedLead?.id === lead.id && "opacity-50 scale-95"
                      )}
                    >
                      <div className="flex items-center gap-2.5">
                        {/* Avatar */}
                        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-primary/40 to-accent/40 flex items-center justify-center text-[10px] font-medium shrink-0">
                          {lead.avatar}
                        </div>

                        {/* Name & Platform */}
                        <div className="flex-1 min-w-0">
                          <p className="font-medium text-sm truncate">{lead.name || lead.username}</p>
                          <p className="text-[10px] text-muted-foreground/70 flex items-center gap-1">
                            {platformIcons[lead.platform] || platformIcons.instagram}
                            <span className="truncate">{lead.username}</span>
                          </p>
                        </div>

                        {/* Value Badge */}
                        {lead.value > 0 && (
                          <span className="text-[10px] font-medium text-emerald-400 shrink-0">
                            €{lead.value}
                          </span>
                        )}

                        {/* Menu - Hidden until hover */}
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
                            >
                              <MoreHorizontal className="w-3.5 h-3.5" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end" className="w-32">
                            <DropdownMenuItem onClick={() => handleViewLead(lead)} className="text-xs">
                              <Eye className="w-3.5 h-3.5 mr-2" />
                              Ver
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={() => handleOpenEditModal(lead)} className="text-xs">
                              <Pencil className="w-3.5 h-3.5 mr-2" />
                              Editar
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              onClick={() => handleOpenDeleteDialog(lead)}
                              className="text-xs text-destructive focus:text-destructive"
                            >
                              <Trash2 className="w-3.5 h-3.5 mr-2" />
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
        <DialogContent className="sm:max-w-[360px]">
          <DialogHeader>
            <DialogTitle className="text-base">Detalles</DialogTitle>
          </DialogHeader>
          {selectedLead && (
            <div className="space-y-4 py-2">
              {/* Profile Header */}
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-full bg-gradient-to-br from-primary/50 to-accent/50 flex items-center justify-center text-sm font-medium">
                  {selectedLead.avatar}
                </div>
                <div>
                  <h3 className="font-medium">{selectedLead.name || selectedLead.username}</h3>
                  <p className="text-xs text-muted-foreground flex items-center gap-1">
                    {platformIcons[selectedLead.platform] || platformIcons.instagram}
                    {selectedLead.username}
                  </p>
                </div>
                <span className="ml-auto text-sm font-medium text-emerald-400">€{selectedLead.value}</span>
              </div>

              {/* Stats Grid */}
              <div className="grid grid-cols-2 gap-2">
                <div className="p-2.5 rounded-lg bg-muted/30 text-center">
                  <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Score</p>
                  <p className="text-lg font-semibold">{selectedLead.score}%</p>
                </div>
                <div className="p-2.5 rounded-lg bg-muted/30 text-center">
                  <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Estado</p>
                  <p className="text-sm font-medium capitalize">{selectedLead.status}</p>
                </div>
              </div>

              {/* Contact Info */}
              {(selectedLead.email || selectedLead.phone) && (
                <div className="space-y-1.5">
                  {selectedLead.email && (
                    <p className="text-xs text-muted-foreground">
                      <span className="text-foreground">{selectedLead.email}</span>
                    </p>
                  )}
                  {selectedLead.phone && (
                    <p className="text-xs text-muted-foreground">
                      <span className="text-foreground">{selectedLead.phone}</span>
                    </p>
                  )}
                </div>
              )}

              {/* Notes */}
              {selectedLead.notes && (
                <p className="text-xs text-muted-foreground bg-muted/20 p-2 rounded">
                  {selectedLead.notes}
                </p>
              )}
            </div>
          )}
          <DialogFooter className="gap-2">
            <Button variant="ghost" size="sm" onClick={() => setIsViewModalOpen(false)}>
              Cerrar
            </Button>
            <Button
              size="sm"
              onClick={() => {
                setIsViewModalOpen(false);
                if (selectedLead) handleOpenEditModal(selectedLead);
              }}
            >
              <Pencil className="w-3.5 h-3.5 mr-1.5" />
              Editar
            </Button>
          </DialogFooter>
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
