import { useState } from "react";
import {
  Activity,
  CheckCircle,
  CheckSquare,
  Eye,
  History,
  Instagram,
  ListTodo,
  Loader2,
  Mail,
  MessageCircle,
  Phone,
  StickyNote,
  Trash2,
  Users,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { ActivityTab } from "@/components/leads/ActivityTab";
import { TasksTab } from "@/components/leads/TasksTab";
import {
  LeadDisplay,
  STATUS_COLORS,
  avatarGradients,
  platformIcons,
  formatTimeAgo,
} from "@/components/leads/leadsTypes";

interface Task {
  id: string;
  title: string;
  status: string;
  priority: string;
  due_date?: string;
}

interface Activity {
  id: string;
  activity_type: string;
  description: string;
  created_at: string;
}

interface LeadDetailModalProps {
  open: boolean;
  lead: LeadDisplay | null;
  onOpenChange: (open: boolean) => void;
  // Data
  activitiesData: { activities?: Activity[] } | null | undefined;
  tasksData: { tasks?: Task[] } | null | undefined;
  statsData: { stats?: Record<string, unknown> } | null | undefined;
  statsLoading: boolean;
  statsError: boolean;
  // Mutations pending flags
  isUpdatingLead: boolean;
  // Handlers
  onAddTask: (title: string) => Promise<void>;
  onToggleTask: (taskId: string, currentStatus: string) => void;
  onDeleteTask: (taskId: string) => void;
  onUpdateTask: (taskId: string, title: string) => Promise<void>;
  onDeleteActivity: (activityId: string) => void;
  onSaveLeadInfo: (email: string, phone: string, notes: string) => Promise<void>;
  onGoToChat: () => void;
  onDeleteLead: () => void;
  isCreatingTask: boolean;
}

export function LeadDetailModal({
  open,
  lead,
  onOpenChange,
  activitiesData,
  tasksData,
  statsData,
  statsLoading,
  statsError,
  isUpdatingLead,
  onAddTask,
  onToggleTask,
  onDeleteTask,
  onUpdateTask,
  onDeleteActivity,
  onSaveLeadInfo,
  onGoToChat,
  onDeleteLead,
  isCreatingTask,
}: LeadDetailModalProps) {
  const [modalTab, setModalTab] = useState("info");
  const [editEmail, setEditEmail] = useState("");
  const [editPhone, setEditPhone] = useState("");
  const [editNotes, setEditNotes] = useState("");

  // Reset editable fields whenever the viewed lead changes
  const handleOpenChange = (nextOpen: boolean) => {
    onOpenChange(nextOpen);
    if (!nextOpen) {
      setModalTab("info");
    }
  };

  // When lead changes, sync form fields
  const syncFields = () => {
    if (lead) {
      setEditEmail(lead.email || "");
      setEditPhone(lead.phone || "");
      setEditNotes(lead.notes || "");
    }
  };

  // We rely on the parent resetting "lead" between opens, and trigger sync on open
  if (open && lead && editEmail === "" && lead.email) {
    syncFields();
  }

  const hasUnsavedChanges =
    lead !== null &&
    (editEmail !== (lead.email || "") ||
      editPhone !== (lead.phone || "") ||
      editNotes !== (lead.notes || ""));

  const pendingTaskCount =
    tasksData?.tasks?.filter((t) => t.status !== "completed").length ?? 0;

  if (!lead) return null;

  const activityTypeIcon = (type: string) => {
    if (type === "note") return <StickyNote className="w-3 h-3" />;
    if (type === "status_change") return <Users className="w-3 h-3" />;
    if (type === "task_created") return <ListTodo className="w-3 h-3" />;
    if (type === "task_completed") return <CheckSquare className="w-3 h-3" />;
    return null;
  };

  const activityTypeColor = (type: string) => {
    if (type === "note") return "bg-blue-500/20 text-blue-400";
    if (type === "status_change") return "bg-amber-500/20 text-amber-400";
    if (type === "task_created") return "bg-violet-500/20 text-violet-400";
    if (type === "task_completed") return "bg-emerald-500/20 text-emerald-400";
    return "bg-muted/20 text-muted-foreground";
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-[500px] max-h-[90vh] overflow-hidden flex flex-col">
        {/* Compact Header */}
        <div className="flex items-center gap-3 pb-3 border-b">
          <div className="w-14 h-14 rounded-full overflow-hidden ring-2 ring-violet-500/30 shrink-0">
            {lead.profilePicUrl ? (
              <img
                src={lead.profilePicUrl}
                alt={lead.username}
                className="w-full h-full object-cover"
                onError={(e) => {
                  (e.target as HTMLImageElement).style.display = "none";
                  (e.target as HTMLImageElement).nextElementSibling?.classList.remove("hidden");
                }}
              />
            ) : null}
            <div
              className={cn(
                "w-full h-full bg-gradient-to-br flex items-center justify-center text-white text-lg font-medium",
                avatarGradients[lead.platform] || avatarGradients.instagram,
                lead.profilePicUrl && "hidden"
              )}
            >
              {lead.avatar}
            </div>
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="font-semibold text-lg truncate">{lead.name || lead.username}</h3>
            <p className="text-sm text-muted-foreground flex items-center gap-1">
              {platformIcons[lead.platform] || platformIcons.instagram}
              @{lead.instagramUsername || lead.username}
            </p>
          </div>
          <div
            className={cn(
              "px-3 py-1 rounded-full text-xs font-semibold bg-current/10 capitalize",
              STATUS_COLORS[lead.status]
            )}
          >
            {lead.status}
          </div>
        </div>

        {/* Tabs */}
        <Tabs
          value={modalTab}
          onValueChange={setModalTab}
          className="flex-1 flex flex-col overflow-hidden"
        >
          <TabsList className="grid w-full grid-cols-4">
            <TabsTrigger value="info" className="text-xs">
              <Eye className="w-3.5 h-3.5 mr-1.5" />
              Info
            </TabsTrigger>
            <TabsTrigger value="activity" className="text-xs">
              <Activity className="w-3.5 h-3.5 mr-1.5" />
              Actividad
            </TabsTrigger>
            <TabsTrigger value="tasks" className="text-xs">
              <ListTodo className="w-3.5 h-3.5 mr-1.5" />
              Tareas
              {pendingTaskCount > 0 && (
                <span className="ml-1 text-[10px] bg-violet-500/20 text-violet-400 px-1.5 rounded-full">
                  {pendingTaskCount}
                </span>
              )}
            </TabsTrigger>
            <TabsTrigger value="history" className="text-xs">
              <History className="w-3.5 h-3.5 mr-1.5" />
              Historial
            </TabsTrigger>
          </TabsList>

          {/* Info Tab */}
          <TabsContent value="info" className="flex-1 overflow-auto mt-3 space-y-4">
            {/* Stats Grid */}
            <div className="grid grid-cols-3 gap-2">
              <div className="p-2.5 rounded-lg bg-muted/30 text-center">
                <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Estado</p>
                <p className="text-sm font-medium capitalize">{lead.status}</p>
              </div>
              <div className="p-2.5 rounded-lg bg-muted/30 text-center">
                <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Mensajes</p>
                <p className="text-sm font-medium">{lead.totalMessages}</p>
              </div>
              <div className="p-2.5 rounded-lg bg-muted/30 text-center">
                <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Último</p>
                <p className="text-sm font-medium">{formatTimeAgo(lead.lastContact) || "-"}</p>
              </div>
            </div>

            {/* Editable Contact Info */}
            <div className="space-y-3">
              <p className="text-xs text-muted-foreground uppercase tracking-wide">
                Datos de contacto
              </p>
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

            {/* Save Button — only shown when there are unsaved changes */}
            {hasUnsavedChanges && (
              <Button
                onClick={() => onSaveLeadInfo(editEmail, editPhone, editNotes)}
                disabled={isUpdatingLead}
                className="w-full bg-violet-600 hover:bg-violet-700"
              >
                {isUpdatingLead ? (
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                ) : (
                  <CheckCircle className="w-4 h-4 mr-2" />
                )}
                Guardar cambios
              </Button>
            )}

            {/* Action Buttons */}
            <div className="grid grid-cols-2 gap-2 pt-2">
              {lead.platform === "instagram" && (
                <Button
                  variant="outline"
                  className="w-full"
                  onClick={() =>
                    window.open(`https://instagram.com/${lead.instagramUsername}`, "_blank")
                  }
                >
                  <Instagram className="w-4 h-4 mr-2" />
                  Instagram
                </Button>
              )}
              <Button
                className="w-full bg-violet-600 hover:bg-violet-700"
                onClick={onGoToChat}
              >
                <MessageCircle className="w-4 h-4 mr-2" />
                Ir al Chat
              </Button>
            </div>
          </TabsContent>

          {/* Activity Tab */}
          <TabsContent value="activity" className="flex-1 overflow-auto mt-3 space-y-3">
            <ActivityTab
              statsLoading={statsLoading}
              statsError={statsError}
              statsData={statsData as Parameters<typeof ActivityTab>[0]["statsData"]}
            />
          </TabsContent>

          {/* Tasks Tab */}
          <TabsContent value="tasks" className="flex-1 overflow-auto mt-3 space-y-3">
            <TasksTab
              tasks={tasksData?.tasks}
              isCreatingTask={isCreatingTask}
              onAddTask={onAddTask}
              onToggleTask={onToggleTask}
              onDeleteTask={onDeleteTask}
              onUpdateTask={onUpdateTask}
            />
          </TabsContent>

          {/* History Tab */}
          <TabsContent value="history" className="flex-1 overflow-auto mt-3">
            <div className="space-y-2">
              {!activitiesData?.activities?.length && (
                <p className="text-center text-sm text-muted-foreground py-8">
                  Sin actividad registrada
                </p>
              )}
              {activitiesData?.activities?.map((activity) => (
                <div
                  key={activity.id}
                  className="group flex items-start gap-2 p-2 rounded-lg bg-muted/20 hover:bg-muted/30 transition-colors"
                >
                  <div
                    className={cn(
                      "w-6 h-6 rounded-full flex items-center justify-center shrink-0 mt-0.5",
                      activityTypeColor(activity.activity_type)
                    )}
                  >
                    {activityTypeIcon(activity.activity_type)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm">{activity.description}</p>
                    <p className="text-[10px] text-muted-foreground mt-0.5">
                      {new Date(activity.created_at).toLocaleString()}
                    </p>
                  </div>
                  <button
                    onClick={() => onDeleteActivity(activity.id)}
                    className="p-1.5 text-muted-foreground/50 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-all shrink-0"
                    title="Eliminar"
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
            onClick={onDeleteLead}
          >
            <Trash2 className="w-3.5 h-3.5 mr-1.5" />
            Eliminar lead
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
