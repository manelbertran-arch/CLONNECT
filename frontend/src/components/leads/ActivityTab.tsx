import { AlertCircle, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface Signal {
  emoji: string;
  description: string;
  weight: number;
  detail?: string;
}

interface LeadStatsData {
  probabilidad_venta: number;
  confianza_prediccion: string;
  producto_detectado?: {
    emoji: string;
    name: string;
    estimated_price: number;
  };
  valor_estimado: number;
  siguiente_paso?: {
    prioridad: string;
    emoji: string;
    texto: string;
  };
  engagement: string;
  engagement_detalle: string;
  total_senales: number;
  senales_por_categoria?: {
    compra?: Signal[];
    interes?: Signal[];
    objecion?: Signal[];
    comportamiento?: Signal[];
  };
  mensajes_lead: number;
  mensajes_bot: number;
  metricas?: {
    tiempo_respuesta_promedio?: string;
  };
}

interface ActivityTabProps {
  statsLoading: boolean;
  statsError: boolean;
  statsData: { stats?: LeadStatsData } | null | undefined;
}

export function ActivityTab({ statsLoading, statsError, statsData }: ActivityTabProps) {
  if (statsLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (statsError) {
    return (
      <div className="flex flex-col items-center justify-center py-8 gap-2">
        <AlertCircle className="w-5 h-5 text-destructive/70" />
        <p className="text-sm text-muted-foreground">No se pudo cargar la actividad</p>
      </div>
    );
  }

  if (!statsData?.stats) {
    return (
      <div className="text-center py-8 text-muted-foreground text-sm">
        No hay datos de actividad disponibles
      </div>
    );
  }

  const stats = statsData.stats;

  return (
    <div className="space-y-3">
      {/* 1. SALE PREDICTION BAR */}
      <div className="p-3 rounded-lg border bg-card">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-muted-foreground uppercase tracking-wide">
            🎯 Predicción de venta
          </span>
          <div className="flex items-center gap-2">
            <span
              className={cn(
                "text-lg font-bold",
                stats.probabilidad_venta >= 61 && "text-emerald-500",
                stats.probabilidad_venta >= 31 &&
                  stats.probabilidad_venta < 61 &&
                  "text-amber-500",
                stats.probabilidad_venta < 31 && "text-red-500"
              )}
            >
              {stats.probabilidad_venta}%
            </span>
            <span
              className={cn(
                "text-[10px] px-1.5 py-0.5 rounded",
                stats.confianza_prediccion === "Alta" && "bg-emerald-500/20 text-emerald-400",
                stats.confianza_prediccion === "Media" && "bg-amber-500/20 text-amber-400",
                stats.confianza_prediccion === "Baja" && "bg-muted text-muted-foreground"
              )}
            >
              {stats.confianza_prediccion}
            </span>
          </div>
        </div>
        <div className="w-full h-2.5 bg-muted rounded-full overflow-hidden">
          <div
            className={cn(
              "h-full rounded-full transition-all duration-500",
              stats.probabilidad_venta >= 61 && "bg-emerald-500",
              stats.probabilidad_venta >= 31 && stats.probabilidad_venta < 61 && "bg-amber-500",
              stats.probabilidad_venta < 31 && "bg-red-500"
            )}
            style={{ width: `${stats.probabilidad_venta}%` }}
          />
        </div>
      </div>

      {/* 2. DETECTED PRODUCT */}
      {stats.producto_detectado && (
        <div className="p-3 rounded-lg border bg-card">
          <span className="text-xs text-muted-foreground uppercase tracking-wide">
            📦 Producto detectado
          </span>
          <div className="flex items-center justify-between mt-1">
            <span className="text-sm font-medium">
              {stats.producto_detectado.emoji} {stats.producto_detectado.name}
            </span>
            <span className="text-sm text-muted-foreground">
              €{stats.producto_detectado.estimated_price}
            </span>
          </div>
          {stats.valor_estimado > 0 && (
            <p className="text-xs text-emerald-400 mt-1">
              Valor estimado: €{stats.valor_estimado.toFixed(0)}
            </p>
          )}
        </div>
      )}

      {/* 3. NEXT STEP */}
      <div
        className={cn(
          "p-3 rounded-lg border",
          stats.siguiente_paso?.prioridad === "urgente" && "bg-red-500/10 border-red-500/30",
          stats.siguiente_paso?.prioridad === "alta" && "bg-amber-500/10 border-amber-500/30",
          stats.siguiente_paso?.prioridad === "media" && "bg-blue-500/10 border-blue-500/30",
          stats.siguiente_paso?.prioridad === "baja" && "bg-muted/30 border-border"
        )}
      >
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground uppercase tracking-wide">
            💡 Siguiente paso
          </span>
          <span
            className={cn(
              "text-[10px] px-1.5 py-0.5 rounded uppercase",
              stats.siguiente_paso?.prioridad === "urgente" && "bg-red-500/20 text-red-400",
              stats.siguiente_paso?.prioridad === "alta" && "bg-amber-500/20 text-amber-400",
              stats.siguiente_paso?.prioridad === "media" && "bg-blue-500/20 text-blue-400",
              stats.siguiente_paso?.prioridad === "baja" && "bg-muted text-muted-foreground"
            )}
          >
            {stats.siguiente_paso?.prioridad}
          </span>
        </div>
        <p className="text-sm font-medium mt-1">
          {stats.siguiente_paso?.emoji} {stats.siguiente_paso?.texto}
        </p>
      </div>

      {/* 4. ENGAGEMENT */}
      <div className="p-3 rounded-lg border bg-card">
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground uppercase tracking-wide">
            💬 Engagement
          </span>
          <span
            className={cn(
              "px-2 py-0.5 rounded-full text-xs font-semibold",
              stats.engagement === "Alto" && "bg-emerald-500/20 text-emerald-400",
              stats.engagement === "Medio" && "bg-amber-500/20 text-amber-400",
              stats.engagement === "Bajo" && "bg-red-500/20 text-red-400"
            )}
          >
            {stats.engagement}
          </span>
        </div>
        <p className="text-sm mt-1">{stats.engagement_detalle}</p>
      </div>

      {/* 5. DETECTED SIGNALS BY CATEGORY */}
      {stats.total_senales > 0 && (
        <div className="p-3 rounded-lg border bg-card">
          <span className="text-xs text-muted-foreground uppercase tracking-wide">
            📊 Señales detectadas ({stats.total_senales})
          </span>

          {stats.senales_por_categoria?.compra && stats.senales_por_categoria.compra.length > 0 && (
            <div className="mt-2">
              <p className="text-[10px] text-emerald-400 uppercase tracking-wide mb-1">🟢 Compra</p>
              {stats.senales_por_categoria.compra.map((s, i) => (
                <div key={i} className="flex items-center gap-2 text-sm text-emerald-400">
                  <span>{s.emoji}</span>
                  <span>{s.description}</span>
                  <span className="text-[10px] text-muted-foreground">(+{s.weight}%)</span>
                </div>
              ))}
            </div>
          )}

          {stats.senales_por_categoria?.interes && stats.senales_por_categoria.interes.length > 0 && (
            <div className="mt-2">
              <p className="text-[10px] text-blue-400 uppercase tracking-wide mb-1">🔵 Interés</p>
              {stats.senales_por_categoria.interes.map((s, i) => (
                <div key={i} className="flex items-center gap-2 text-sm text-blue-400">
                  <span>{s.emoji}</span>
                  <span>{s.description}</span>
                  <span className="text-[10px] text-muted-foreground">(+{s.weight}%)</span>
                </div>
              ))}
            </div>
          )}

          {stats.senales_por_categoria?.objecion && stats.senales_por_categoria.objecion.length > 0 && (
            <div className="mt-2">
              <p className="text-[10px] text-red-400 uppercase tracking-wide mb-1">🔴 Objeciones</p>
              {stats.senales_por_categoria.objecion.map((s, i) => (
                <div key={i} className="flex items-center gap-2 text-sm text-red-400">
                  <span>{s.emoji}</span>
                  <span>{s.description}</span>
                  <span className="text-[10px] text-muted-foreground">({s.weight}%)</span>
                </div>
              ))}
            </div>
          )}

          {stats.senales_por_categoria?.comportamiento &&
            stats.senales_por_categoria.comportamiento.length > 0 && (
              <div className="mt-2">
                <p className="text-[10px] text-violet-400 uppercase tracking-wide mb-1">
                  ⚡ Comportamiento
                </p>
                {stats.senales_por_categoria.comportamiento.map((s, i) => (
                  <div key={i} className="flex items-center gap-2 text-sm text-violet-400">
                    <span>{s.emoji}</span>
                    <span>{s.description}</span>
                    {s.detail && (
                      <span className="text-[10px] text-muted-foreground">({s.detail})</span>
                    )}
                  </div>
                ))}
              </div>
            )}
        </div>
      )}

      {/* 6. QUICK STATS */}
      <div className="grid grid-cols-2 gap-2">
        <div className="p-2.5 rounded-lg bg-muted/30 text-center">
          <p className="text-lg font-semibold">{stats.mensajes_lead}</p>
          <p className="text-[10px] text-muted-foreground">Msgs del lead</p>
        </div>
        <div className="p-2.5 rounded-lg bg-muted/30 text-center">
          <p className="text-lg font-semibold">{stats.mensajes_bot}</p>
          <p className="text-[10px] text-muted-foreground">Msgs del bot</p>
        </div>
      </div>

      {/* 7. RESPONSE TIME */}
      {stats.metricas?.tiempo_respuesta_promedio && (
        <div className="p-2.5 rounded-lg bg-muted/20 text-center">
          <p className="text-xs text-muted-foreground">Tiempo de respuesta promedio</p>
          <p className="text-sm font-semibold">{stats.metricas.tiempo_respuesta_promedio}</p>
        </div>
      )}
    </div>
  );
}
