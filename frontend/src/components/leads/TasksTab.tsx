import { useState } from "react";
import {
  Calendar,
  CheckCircle,
  CheckSquare,
  Loader2,
  Pencil,
  Plus,
  Square,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

interface Task {
  id: string;
  title: string;
  status: string;
  priority: string;
  due_date?: string;
}

interface TasksTabProps {
  tasks: Task[] | undefined;
  isCreatingTask: boolean;
  onAddTask: (title: string) => Promise<void>;
  onToggleTask: (taskId: string, currentStatus: string) => void;
  onDeleteTask: (taskId: string) => void;
  onUpdateTask: (taskId: string, title: string) => Promise<void>;
}

export function TasksTab({
  tasks,
  isCreatingTask,
  onAddTask,
  onToggleTask,
  onDeleteTask,
  onUpdateTask,
}: TasksTabProps) {
  const [newTaskTitle, setNewTaskTitle] = useState("");
  const [editingTaskId, setEditingTaskId] = useState<string | null>(null);
  const [editingTaskTitle, setEditingTaskTitle] = useState("");
  const [completingTaskId, setCompletingTaskId] = useState<string | null>(null);

  const handleAddTask = async () => {
    if (!newTaskTitle.trim()) return;
    await onAddTask(newTaskTitle.trim());
    setNewTaskTitle("");
  };

  const handleToggle = (taskId: string, currentStatus: string) => {
    const willComplete = currentStatus !== "completed";
    if (willComplete) {
      setCompletingTaskId(taskId);
      // The parent drives the actual mutation; we just animate locally
      setTimeout(() => setCompletingTaskId(null), 900);
    }
    onToggleTask(taskId, currentStatus);
  };

  const handleSaveEdit = async () => {
    if (!editingTaskId || !editingTaskTitle.trim()) return;
    await onUpdateTask(editingTaskId, editingTaskTitle.trim());
    setEditingTaskId(null);
    setEditingTaskTitle("");
  };

  const pendingTasks = tasks?.filter((t) => t.status !== "completed") ?? [];
  const completedTasks = tasks?.filter((t) => t.status === "completed") ?? [];

  return (
    <div className="space-y-3">
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
          disabled={isCreatingTask || !newTaskTitle.trim()}
          className="shrink-0"
        >
          {isCreatingTask ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Plus className="w-4 h-4" />
          )}
        </Button>
      </div>

      {/* Pending Tasks */}
      <div className="space-y-2">
        {pendingTasks.length === 0 && (
          <p className="text-center text-sm text-muted-foreground py-4">
            No hay tareas pendientes
          </p>
        )}
        {pendingTasks.map((task) => (
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
              onClick={() => handleToggle(task.id, task.status)}
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
                      if (e.key === "Enter") handleSaveEdit();
                      if (e.key === "Escape") {
                        setEditingTaskId(null);
                        setEditingTaskTitle("");
                      }
                    }}
                    autoFocus
                  />
                  <Button size="sm" variant="ghost" className="h-7 px-2" onClick={handleSaveEdit}>
                    <CheckCircle className="w-3.5 h-3.5" />
                  </Button>
                </div>
              ) : (
                <p
                  className={cn(
                    "text-sm transition-all duration-300",
                    completingTaskId === task.id && "line-through text-muted-foreground"
                  )}
                >
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
            {(task.priority === "high" || task.priority === "urgent") && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-500/20 text-red-400">
                {task.priority === "urgent" ? "Urgente" : "Alta"}
              </span>
            )}
            {editingTaskId !== task.id && completingTaskId !== task.id && (
              <div className="flex gap-1">
                <button
                  onClick={() => {
                    setEditingTaskId(task.id);
                    setEditingTaskTitle(task.title);
                  }}
                  className="p-1 text-muted-foreground hover:text-violet-500 transition-colors"
                  title="Editar"
                >
                  <Pencil className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => onDeleteTask(task.id)}
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
      {completedTasks.length > 0 && (
        <div className="space-y-2 pt-2 border-t">
          <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Completadas</p>
          {completedTasks.map((task) => (
            <div
              key={task.id}
              className="flex items-center gap-2 p-2 rounded-lg bg-muted/20 border border-muted"
            >
              <button onClick={() => handleToggle(task.id, task.status)} className="shrink-0">
                <CheckSquare className="w-4 h-4 text-emerald-500" />
              </button>
              <p className="text-sm line-through text-muted-foreground flex-1">{task.title}</p>
              <button
                onClick={() => onDeleteTask(task.id)}
                className="p-1 text-muted-foreground hover:text-red-500 transition-colors"
                title="Eliminar"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
