import { useState, useMemo, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { AlertCircle, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useQueryClient } from "@tanstack/react-query";
import {
  useConversations,
  useUpdateLeadStatus,
  useCreateManualLead,
  useUpdateLead,
  useDeleteLead,
  useLeadActivities,
  useLeadTasks,
  useCreateLeadTask,
  useUpdateLeadTask,
  useDeleteLeadTask,
  useDeleteLeadActivity,
  useLeadStats,
} from "@/hooks/useApi";
import { useToast } from "@/hooks/use-toast";
import { getFollowerDetail, apiKeys, getCreatorId } from "@/services/api";

import {
  LeadDisplay,
  LeadStatus,
  statusToBackend,
  getInitials,
} from "@/components/leads/leadsTypes";
import { useLeadsData } from "@/components/leads/useLeadsData";
import { LeadsSummaryCards } from "@/components/leads/LeadsSummaryCards";
import { LeadsTable } from "@/components/leads/LeadsTable";
import { AddLeadModal, AddLeadFormData } from "@/components/leads/AddLeadModal";
import { LeadDetailModal } from "@/components/leads/LeadDetailModal";
import { LeadsSkeleton } from "@/components/leads/LeadsSkeleton";
import { DeleteLeadDialog } from "@/components/leads/DeleteLeadDialog";

export default function Leads() {
  const { data, isLoading, error } = useConversations(getCreatorId(), 500);
  const queryClient = useQueryClient();
  const creatorId = getCreatorId();
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

  // Filter + drag state
  const [activeFilter, setActiveFilter] = useState<LeadStatus | null>(null);
  const [draggedLead, setDraggedLead] = useState<LeadDisplay | null>(null);
  const [localStatusOverrides, setLocalStatusOverrides] = useState<Record<string, LeadStatus>>({});

  // Optimistic UI state
  const [fadingIds, setFadingIds] = useState<Set<string>>(new Set());
  const [hiddenIds, setHiddenIds] = useState<Set<string>>(new Set());
  const [optimisticLeads, setOptimisticLeads] = useState<LeadDisplay[]>([]);

  // Cleanup animation timers on unmount
  const animationTimersRef = useRef<Set<ReturnType<typeof setTimeout>>>(new Set());
  useEffect(() => {
    return () => { animationTimersRef.current.forEach(clearTimeout); };
  }, []);

  // Modal state
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [isViewModalOpen, setIsViewModalOpen] = useState(false);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [selectedLead, setSelectedLead] = useState<LeadDisplay | null>(null);

  // Fetch per-lead detail only when the CRM modal is open
  const modalLeadId = isViewModalOpen && selectedLead ? selectedLead.followerId : null;
  const { data: activitiesData } = useLeadActivities(modalLeadId);
  const { data: tasksData } = useLeadTasks(modalLeadId);
  const { data: statsData, isLoading: statsLoading, isError: statsError } = useLeadStats(modalLeadId);

  const countsByStatus = useMemo(() => data?.counts_by_status || {}, [data?.counts_by_status]);

  const { leads, filteredLeads } = useLeadsData(
    data?.conversations,
    optimisticLeads,
    localStatusOverrides,
    hiddenIds,
    activeFilter
  );

  // --- Drag & Drop ---
  const handleDragStart = (lead: LeadDisplay) => setDraggedLead(lead);
  const handleDragOver = (e: React.DragEvent) => e.preventDefault();

  const handleDrop = async (status: LeadStatus) => {
    if (!draggedLead || draggedLead.status === status) { setDraggedLead(null); return; }
    const leadId = draggedLead.id;
    const oldStatus = draggedLead.status;
    setLocalStatusOverrides((prev) => ({ ...prev, [leadId]: status }));
    setDraggedLead(null);
    try {
      await updateStatusMutation.mutateAsync({ followerId: leadId, status: statusToBackend[status] });
      toast({ title: "Estado actualizado", description: `Lead movido a ${status}` });
    } catch (err) {
      setLocalStatusOverrides((prev) => ({ ...prev, [leadId]: oldStatus }));
      toast({ title: "Error", description: err instanceof Error ? err.message : "No se pudo actualizar", variant: "destructive" });
    }
  };

  // --- Add Lead ---
  const handleAddLead = (formData: AddLeadFormData) => {
    if (!formData.name.trim()) {
      toast({ title: "Nombre requerido", description: "Ingresa un nombre para el lead", variant: "destructive" });
      return;
    }
    const { name: leadName, platform, email, phone, notes } = formData;
    setIsAddModalOpen(false);
    const tempId = `temp-${Date.now()}`;
    const optimisticLead: LeadDisplay = {
      id: tempId, name: leadName, username: leadName,
      instagramUsername: leadName.toLowerCase().replace(/\s+/g, "_"),
      score: 20, intentScore: 0, value: 0, status: "nuevo",
      avatar: getInitials(leadName), profilePicUrl: "", platform,
      email: email || "", phone: phone || "", notes: notes || "",
      lastContact: new Date().toISOString(), totalMessages: 0,
      followerId: tempId, lastMessage: "", relationshipType: "nuevo",
    };
    setOptimisticLeads((prev) => [optimisticLead, ...prev]);
    toast({ title: "Lead creado", description: `${leadName} agregado al pipeline` });
    createLeadMutation.mutate(
      { name: leadName, platform, email: email || undefined, phone: phone || undefined, notes: notes || undefined },
      { onError: (err) => {
        setOptimisticLeads((prev) => prev.filter((l) => l.id !== tempId));
        toast({ title: "Error al crear lead", description: err instanceof Error ? err.message : "No se pudo crear el lead", variant: "destructive" });
      }}
    );
  };

  // --- View Lead ---
  const handleViewLead = (lead: LeadDisplay) => { setSelectedLead(lead); setIsViewModalOpen(true); };

  // --- Tasks ---
  const handleAddTask = async (title: string) => {
    if (!selectedLead) return;
    try {
      await createTaskMutation.mutateAsync({ leadId: selectedLead.followerId, data: { title, task_type: "follow_up", priority: "medium" } });
      toast({ title: "Tarea creada", description: "Se ha añadido la tarea" });
    } catch { toast({ title: "Error", description: "No se pudo crear la tarea", variant: "destructive" }); }
  };

  const handleToggleTask = async (taskId: string, currentStatus: string) => {
    if (!selectedLead) return;
    const newStatus = currentStatus === "completed" ? "pending" : "completed";
    if (newStatus === "completed") {
      const timer = setTimeout(async () => {
        animationTimersRef.current.delete(timer);
        try {
          await updateTaskMutation.mutateAsync({ leadId: selectedLead.followerId, taskId, data: { status: newStatus } });
          toast({ title: "Tarea completada" });
        } catch { toast({ title: "Error", description: "No se pudo completar la tarea", variant: "destructive" }); }
      }, 800);
      animationTimersRef.current.add(timer);
    } else {
      try {
        await updateTaskMutation.mutateAsync({ leadId: selectedLead.followerId, taskId, data: { status: newStatus } });
        toast({ title: "Tarea reabierta" });
      } catch { toast({ title: "Error", description: "No se pudo actualizar la tarea", variant: "destructive" }); }
    }
  };

  const handleDeleteTask = async (taskId: string) => {
    if (!selectedLead) return;
    try {
      await deleteTaskMutation.mutateAsync({ leadId: selectedLead.followerId, taskId });
      toast({ title: "Tarea eliminada" });
    } catch { toast({ title: "Error", description: "No se pudo eliminar la tarea", variant: "destructive" }); }
  };

  const handleUpdateTask = async (taskId: string, title: string) => {
    if (!selectedLead) return;
    try {
      await updateTaskMutation.mutateAsync({ leadId: selectedLead.followerId, taskId, data: { title } });
      toast({ title: "Tarea actualizada" });
    } catch { toast({ title: "Error", description: "No se pudo actualizar la tarea", variant: "destructive" }); }
  };

  // --- Activity ---
  const handleDeleteActivity = async (activityId: string) => {
    if (!selectedLead) return;
    try {
      await deleteActivityMutation.mutateAsync({ leadId: selectedLead.followerId, activityId });
      toast({ title: "Entrada eliminada" });
    } catch { toast({ title: "Error", description: "No se pudo eliminar", variant: "destructive" }); }
  };

  // --- Save lead info ---
  const handleSaveLeadInfo = async (email: string, phone: string, notes: string) => {
    if (!selectedLead) return;
    try {
      await updateLeadMutation.mutateAsync({ leadId: selectedLead.followerId, data: { email, phone, notes } });
      setSelectedLead({ ...selectedLead, email, phone, notes });
      toast({ title: "Guardado", description: "Datos del lead actualizados" });
    } catch { toast({ title: "Error", description: "No se pudo guardar los cambios", variant: "destructive" }); }
  };

  // --- Delete Lead ---
  const handleOpenDeleteDialog = (lead: LeadDisplay) => { setSelectedLead(lead); setIsDeleteDialogOpen(true); };

  const handleDeleteLead = () => {
    if (!selectedLead) return;
    const leadId = selectedLead.id;
    const leadName = selectedLead.name || selectedLead.username;
    setIsDeleteDialogOpen(false);
    setIsViewModalOpen(false);
    setFadingIds((prev) => new Set([...prev, leadId]));
    const timer = setTimeout(() => {
      animationTimersRef.current.delete(timer);
      setHiddenIds((prev) => new Set([...prev, leadId]));
      setFadingIds((prev) => { const next = new Set(prev); next.delete(leadId); return next; });
    }, 150);
    animationTimersRef.current.add(timer);
    deleteLeadMutation.mutate(leadId, {
      onSuccess: () => { toast({ title: "Lead eliminado", description: `${leadName} eliminado` }); setSelectedLead(null); },
      onError: (err) => {
        setHiddenIds((prev) => { const next = new Set(prev); next.delete(leadId); return next; });
        toast({ title: "Error al eliminar", description: err instanceof Error ? err.message : "No se pudo eliminar", variant: "destructive" });
      },
    });
  };

  // --- Loading / Error ---
  if (isLoading) return <LeadsSkeleton />;
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
        <Button onClick={() => setIsAddModalOpen(true)} size="sm" className="h-9 px-4">
          <Plus className="w-4 h-4 mr-2" />
          Nuevo Lead
        </Button>
      </div>

      <LeadsSummaryCards
        countsByStatus={countsByStatus}
        activeFilter={activeFilter}
        onFilterChange={setActiveFilter}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
      />

      <LeadsTable
        leads={filteredLeads}
        draggedLeadId={draggedLead?.id ?? null}
        fadingIds={fadingIds}
        activeFilter={activeFilter}
        onDragStart={handleDragStart}
        onRowClick={handleViewLead}
        onRowMouseEnter={(lead) => {
          queryClient.prefetchQuery({
            queryKey: apiKeys.follower(creatorId, lead.followerId),
            queryFn: () => getFollowerDetail(creatorId, lead.followerId),
            staleTime: 60000,
          });
        }}
        onViewLead={handleViewLead}
        onGoToChat={(lead) => navigate(`/inbox?id=${lead.followerId}`)}
        onDeleteLead={handleOpenDeleteDialog}
      />

      <AddLeadModal
        open={isAddModalOpen}
        onOpenChange={setIsAddModalOpen}
        isPending={createLeadMutation.isPending}
        onSubmit={handleAddLead}
      />

      <LeadDetailModal
        open={isViewModalOpen}
        lead={selectedLead}
        onOpenChange={(open) => { setIsViewModalOpen(open); if (!open) setSelectedLead(null); }}
        activitiesData={activitiesData}
        tasksData={tasksData}
        statsData={statsData}
        statsLoading={statsLoading}
        statsError={statsError}
        isUpdatingLead={updateLeadMutation.isPending}
        isCreatingTask={createTaskMutation.isPending}
        onAddTask={handleAddTask}
        onToggleTask={handleToggleTask}
        onDeleteTask={handleDeleteTask}
        onUpdateTask={handleUpdateTask}
        onDeleteActivity={handleDeleteActivity}
        onSaveLeadInfo={handleSaveLeadInfo}
        onGoToChat={() => { setIsViewModalOpen(false); if (selectedLead) navigate(`/inbox?id=${selectedLead.followerId}`); }}
        onDeleteLead={() => { setIsViewModalOpen(false); if (selectedLead) handleOpenDeleteDialog(selectedLead); }}
      />

      <DeleteLeadDialog
        open={isDeleteDialogOpen}
        onOpenChange={setIsDeleteDialogOpen}
        leadName={selectedLead?.name || selectedLead?.username}
        onConfirm={handleDeleteLead}
      />
    </div>
  );
}
