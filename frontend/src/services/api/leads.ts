import { apiFetch, CREATOR_ID } from "./client";

export interface LeadActivity {
  id: string;
  activity_type: string;
  description: string;
  old_value?: string;
  new_value?: string;
  metadata?: Record<string, any>;
  created_by?: string;
  created_at: string;
}

export interface LeadTask {
  id: string;
  title: string;
  description?: string;
  task_type: string;
  priority: string;
  status: string;
  due_date?: string;
  completed_at?: string;
  assigned_to?: string;
  created_at: string;
}

export interface DetectedSignal {
  signal: string;
  keyword_found?: string;
  weight: number;
  category: "compra" | "interes" | "objecion" | "comportamiento";
  emoji: string;
  description: string;
  detail?: string;
}

export interface DetectedProduct {
  id: string;
  name: string;
  keyword_found: string;
  estimated_price: number;
  emoji: string;
}

export interface NextStep {
  accion: string;
  emoji: string;
  texto: string;
  prioridad: "urgente" | "alta" | "media" | "baja";
}

export interface BehaviorMetrics {
  tiempo_respuesta_promedio: string | null;
  tiempo_respuesta_segundos: number | null;
  longitud_mensaje_promedio: number;
  cantidad_preguntas: number;
  total_mensajes_lead: number;
  total_mensajes_bot: number;
  ratio_participacion: number;
}

export interface LeadStats {
  probabilidad_venta: number;
  confianza_prediccion: "Alta" | "Media" | "Baja";
  producto_detectado: DetectedProduct | null;
  valor_estimado: number;
  senales_detectadas: DetectedSignal[];
  senales_por_categoria: {
    compra: DetectedSignal[];
    interes: DetectedSignal[];
    objecion: DetectedSignal[];
    comportamiento: DetectedSignal[];
  };
  total_senales: number;
  siguiente_paso: NextStep;
  engagement: "Alto" | "Medio" | "Bajo";
  engagement_detalle: string;
  metricas: BehaviorMetrics;
  mensajes_lead: number;
  mensajes_bot: number;
  primer_contacto: string | null;
  ultimo_contacto: string | null;
  current_stage: string;
}

export interface EscalationAlert {
  creator_id: string;
  follower_id: string;
  follower_username: string;
  follower_name: string;
  reason: string;
  last_message: string;
  conversation_summary: string;
  purchase_intent_score: number;
  total_messages: number;
  products_discussed: string[];
  timestamp: string;
  notification_type: string;
  read?: boolean;
}

export interface EscalationsResponse {
  status: string;
  creator_id: string;
  alerts: EscalationAlert[];
  total: number;
  unread: number;
}

export async function getLeadActivities(creatorId: string = CREATOR_ID, leadId: string, limit: number = 50): Promise<{ status: string; activities: LeadActivity[] }> {
  return apiFetch(`/dm/leads/${creatorId}/${leadId}/activities?limit=${limit}`);
}

export async function createLeadActivity(creatorId: string = CREATOR_ID, leadId: string, data: { activity_type: string; description: string; metadata?: Record<string, any> }): Promise<{ status: string; activity: LeadActivity }> {
  return apiFetch(`/dm/leads/${creatorId}/${leadId}/activities`, { method: "POST", body: JSON.stringify(data) });
}

export async function getLeadTasks(creatorId: string = CREATOR_ID, leadId: string, includeCompleted: boolean = false): Promise<{ status: string; tasks: LeadTask[] }> {
  return apiFetch(`/dm/leads/${creatorId}/${leadId}/tasks?include_completed=${includeCompleted}`);
}

export async function createLeadTask(creatorId: string = CREATOR_ID, leadId: string, data: { title: string; description?: string; task_type?: string; priority?: string; due_date?: string }): Promise<{ status: string; task: LeadTask }> {
  return apiFetch(`/dm/leads/${creatorId}/${leadId}/tasks`, { method: "POST", body: JSON.stringify(data) });
}

export async function updateLeadTask(creatorId: string = CREATOR_ID, leadId: string, taskId: string, data: Partial<LeadTask>): Promise<{ status: string; task: LeadTask }> {
  return apiFetch(`/dm/leads/${creatorId}/${leadId}/tasks/${taskId}`, { method: "PUT", body: JSON.stringify(data) });
}

export async function deleteLeadTask(creatorId: string = CREATOR_ID, leadId: string, taskId: string): Promise<{ status: string; message: string }> {
  return apiFetch(`/dm/leads/${creatorId}/${leadId}/tasks/${taskId}`, { method: "DELETE" });
}

export async function deleteLeadActivity(creatorId: string = CREATOR_ID, leadId: string, activityId: string): Promise<{ status: string; message: string }> {
  return apiFetch(`/dm/leads/${creatorId}/${leadId}/activities/${activityId}`, { method: "DELETE" });
}

export async function getLeadStats(creatorId: string = CREATOR_ID, leadId: string): Promise<{ status: string; stats: LeadStats }> {
  return apiFetch(`/dm/leads/${creatorId}/${leadId}/stats`);
}

export async function getEscalations(creatorId: string = CREATOR_ID, limit: number = 50, unreadOnly: boolean = false): Promise<EscalationsResponse> {
  const params = new URLSearchParams();
  params.append("limit", limit.toString());
  if (unreadOnly) params.append("unread_only", "true");
  return apiFetch(`/dm/leads/${creatorId}/escalations?${params.toString()}`);
}
