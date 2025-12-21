import { useState, useMemo } from "react";
import { Instagram, MoreHorizontal, Plus, TrendingUp, Loader2, AlertCircle, MessageCircle, Send, Eye, Pencil, Trash2, X } from "lucide-react";
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

type LeadStatus = "new" | "active" | "hot" | "customer";

interface LeadDisplay {
  id: string;
  name: string;
  username: string;
  score: number;
  value: number;
  status: LeadStatus;
  avatar: string;
  platform: string;
}

const columns: { status: LeadStatus; title: string; color: string }[] = [
  { status: "new", title: "New Leads", color: "bg-muted-foreground" },
  { status: "active", title: "Active", color: "bg-accent" },
  { status: "hot", title: "Hot 🔥", color: "bg-destructive" },
  { status: "customer", title: "Customers ✅", color: "bg-success" },
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
 * Classify lead status based on purchase_intent
 * Ranges: 0-25% (new) | 25-50% (active) | 50%+ (hot) | customer
 * - is_customer = true → customer
 * - purchase_intent >= 0.50 → hot
 * - purchase_intent >= 0.25 → active
 * - purchase_intent < 0.25 → new
 */
function getLeadStatus(convo: Conversation): LeadStatus {
  if (convo.is_customer) return "customer";
  const intent = getPurchaseIntent(convo);
  if (intent >= 0.50) return "hot";
  if (intent >= 0.25) return "active";
  return "new";
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

// Map UI status to backend status
const statusToBackend: Record<LeadStatus, "cold" | "warm" | "hot" | "customer"> = {
  new: "cold",
  active: "warm",
  hot: "hot",
  customer: "customer",
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

      return {
        id: convo.follower_id,
        name: convo.name || "",
        username: displayName,
        score: Math.round(intent * 100),
        value: estimateValue(convo),
        status: localStatusOverrides[convo.follower_id] || getLeadStatus(convo),
        avatar: getInitials(convo.name, convo.username, convo.follower_id),
        platform,
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
        title: "Status updated",
        description: `Lead moved to ${status.toUpperCase()}`,
      });
    } catch (error) {
      // Revert on error
      setLocalStatusOverrides(prev => ({
        ...prev,
        [leadId]: oldStatus
      }));

      toast({
        title: "Error updating status",
        description: error instanceof Error ? error.message : "Failed to update",
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
        title: "Name required",
        description: "Please enter a name for the lead",
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
        title: "Lead created",
        description: `${formData.name} has been added to your pipeline`,
      });
      setIsAddModalOpen(false);
      setFormData(initialFormState);
    } catch (err) {
      toast({
        title: "Error creating lead",
        description: err instanceof Error ? err.message : "Failed to create lead",
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
      email: "",
      phone: "",
      notes: "",
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
        title: "Lead updated",
        description: `${formData.name} has been updated`,
      });
      setIsEditModalOpen(false);
      setSelectedLead(null);
    } catch (err) {
      toast({
        title: "Error updating lead",
        description: err instanceof Error ? err.message : "Failed to update lead",
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
        title: "Lead deleted",
        description: `${selectedLead.name || selectedLead.username} has been removed`,
      });
      setIsDeleteDialogOpen(false);
      setSelectedLead(null);
    } catch (err) {
      toast({
        title: "Error deleting lead",
        description: err instanceof Error ? err.message : "Failed to delete lead",
        variant: "destructive",
      });
    }
  };

  // Loading state
  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <AlertCircle className="w-12 h-12 text-destructive" />
        <p className="text-muted-foreground">Failed to load leads</p>
        <p className="text-sm text-destructive">{error.message}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Lead Pipeline</h1>
          <p className="text-muted-foreground">
            {leads.length} total leads • Drag and drop to update status
          </p>
        </div>
        <Button
          onClick={handleOpenAddModal}
          className="bg-gradient-to-r from-primary to-accent hover:opacity-90 transition-opacity"
        >
          <Plus className="w-4 h-4 mr-2" />
          Add Lead
        </Button>
      </div>

      {/* Kanban Board */}
      <div className="grid grid-cols-4 gap-4 h-[calc(100vh-16rem)]">
        {columns.map((column) => {
          const columnLeads = getLeadsByStatus(column.status);
          const columnValue = columnLeads.reduce((sum, lead) => sum + lead.value, 0);

          return (
            <div
              key={column.status}
              className="flex flex-col bg-card/50 rounded-2xl border border-border/50 overflow-hidden"
              onDragOver={handleDragOver}
              onDrop={() => handleDrop(column.status)}
            >
              {/* Column Header */}
              <div className="p-4 border-b border-border/50">
                <div className="flex items-center gap-2">
                  <div className={cn("w-2 h-2 rounded-full", column.color)}></div>
                  <h3 className="font-semibold text-sm">{column.title}</h3>
                  <span className="text-xs text-muted-foreground ml-auto">{columnLeads.length}</span>
                </div>
                <p className="text-xs text-muted-foreground mt-1">€{columnValue.toLocaleString()}</p>
              </div>

              {/* Cards */}
              <div className="flex-1 overflow-auto p-3 space-y-3">
                {columnLeads.length === 0 ? (
                  <div className="text-center py-8 text-muted-foreground text-xs">
                    No leads
                  </div>
                ) : (
                  columnLeads.map((lead) => (
                    <div
                      key={lead.id}
                      draggable
                      onDragStart={() => handleDragStart(lead)}
                      className={cn(
                        "p-4 rounded-xl bg-card border border-border/50 cursor-grab active:cursor-grabbing transition-all hover:border-primary/50 hover:shadow-lg",
                        draggedLead?.id === lead.id && "opacity-50"
                      )}
                    >
                      <div className="flex items-start justify-between mb-3">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-full bg-gradient-to-br from-primary/60 to-accent/60 flex items-center justify-center text-xs font-semibold">
                            {lead.avatar}
                          </div>
                          <div>
                            <p className="font-medium text-sm">{lead.name || lead.username}</p>
                            <p className="text-xs text-muted-foreground flex items-center gap-1">
                              {platformIcons[lead.platform] || platformIcons.instagram}
                              {lead.id}
                            </p>
                          </div>
                        </div>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-6 w-6">
                              <MoreHorizontal className="w-3 h-3" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem onClick={() => handleViewLead(lead)}>
                              <Eye className="w-4 h-4 mr-2" />
                              View
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={() => handleOpenEditModal(lead)}>
                              <Pencil className="w-4 h-4 mr-2" />
                              Edit
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              onClick={() => handleOpenDeleteDialog(lead)}
                              className="text-destructive focus:text-destructive"
                            >
                              <Trash2 className="w-4 h-4 mr-2" />
                              Delete
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-1.5">
                          <TrendingUp className="w-3 h-3 text-primary" />
                          <span className="text-xs font-medium">{lead.score}%</span>
                        </div>
                        {lead.value > 0 && (
                          <span className="text-xs font-semibold text-accent">€{lead.value}</span>
                        )}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Footer */}
      <div className="metric-card flex items-center justify-between">
        <span className="text-muted-foreground">Total Pipeline Value</span>
        <span className="text-2xl font-bold gradient-text">€{totalPipelineValue.toLocaleString()}</span>
      </div>

      {/* Add Lead Modal */}
      <Dialog open={isAddModalOpen} onOpenChange={setIsAddModalOpen}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>Add New Lead</DialogTitle>
            <DialogDescription>
              Create a manual lead entry. Fill in the details below.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="name">Name *</Label>
              <Input
                id="name"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="John Doe"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="platform">Platform</Label>
              <Select
                value={formData.platform}
                onValueChange={(value) => setFormData({ ...formData, platform: value })}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select platform" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="instagram">Instagram</SelectItem>
                  <SelectItem value="telegram">Telegram</SelectItem>
                  <SelectItem value="whatsapp">WhatsApp</SelectItem>
                  <SelectItem value="manual">Manual / Other</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                placeholder="john@example.com"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="phone">Phone</Label>
              <Input
                id="phone"
                value={formData.phone}
                onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                placeholder="+34 600 000 000"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="notes">Notes</Label>
              <Input
                id="notes"
                value={formData.notes}
                onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                placeholder="Any additional notes..."
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsAddModalOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleAddLead}
              disabled={createLeadMutation.isPending}
              className="bg-gradient-to-r from-primary to-accent"
            >
              {createLeadMutation.isPending ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Plus className="w-4 h-4 mr-2" />
              )}
              Add Lead
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* View Lead Modal */}
      <Dialog open={isViewModalOpen} onOpenChange={setIsViewModalOpen}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>Lead Details</DialogTitle>
          </DialogHeader>
          {selectedLead && (
            <div className="grid gap-4 py-4">
              <div className="flex items-center gap-4">
                <div className="w-16 h-16 rounded-full bg-gradient-to-br from-primary/60 to-accent/60 flex items-center justify-center text-lg font-semibold">
                  {selectedLead.avatar}
                </div>
                <div>
                  <h3 className="font-semibold text-lg">{selectedLead.name || selectedLead.username}</h3>
                  <p className="text-sm text-muted-foreground flex items-center gap-1">
                    {platformIcons[selectedLead.platform] || platformIcons.instagram}
                    {selectedLead.platform}
                  </p>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="p-3 rounded-lg bg-muted/50">
                  <p className="text-xs text-muted-foreground">Lead Score</p>
                  <p className="text-lg font-semibold">{selectedLead.score}%</p>
                </div>
                <div className="p-3 rounded-lg bg-muted/50">
                  <p className="text-xs text-muted-foreground">Est. Value</p>
                  <p className="text-lg font-semibold">€{selectedLead.value}</p>
                </div>
              </div>
              <div className="p-3 rounded-lg bg-muted/50">
                <p className="text-xs text-muted-foreground">Status</p>
                <p className="text-sm font-medium capitalize">{selectedLead.status}</p>
              </div>
              <div className="p-3 rounded-lg bg-muted/50">
                <p className="text-xs text-muted-foreground">ID</p>
                <p className="text-sm font-mono">{selectedLead.id}</p>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsViewModalOpen(false)}>
              Close
            </Button>
            <Button
              onClick={() => {
                setIsViewModalOpen(false);
                if (selectedLead) handleOpenEditModal(selectedLead);
              }}
            >
              <Pencil className="w-4 h-4 mr-2" />
              Edit
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Lead Modal */}
      <Dialog open={isEditModalOpen} onOpenChange={setIsEditModalOpen}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>Edit Lead</DialogTitle>
            <DialogDescription>
              Update the lead information below.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="edit-name">Name</Label>
              <Input
                id="edit-name"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="edit-email">Email</Label>
              <Input
                id="edit-email"
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                placeholder="john@example.com"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="edit-phone">Phone</Label>
              <Input
                id="edit-phone"
                value={formData.phone}
                onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                placeholder="+34 600 000 000"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="edit-notes">Notes</Label>
              <Input
                id="edit-notes"
                value={formData.notes}
                onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                placeholder="Any additional notes..."
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsEditModalOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleEditLead}
              disabled={updateLeadMutation.isPending}
            >
              {updateLeadMutation.isPending ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Pencil className="w-4 h-4 mr-2" />
              )}
              Save Changes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={isDeleteDialogOpen} onOpenChange={setIsDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Lead</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete{" "}
              <span className="font-semibold">{selectedLead?.name || selectedLead?.username}</span>?
              This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteLead}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleteLeadMutation.isPending ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Trash2 className="w-4 h-4 mr-2" />
              )}
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
