/**
 * Dashboard / "Hoy" Page
 *
 * SPRINT3-T3.2: Reimagined dashboard with daily mission and insights
 */
import { Loader2, AlertCircle, Power, Calendar, MessageCircle, Ghost, ChevronRight } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { useDashboard, useToggleBot } from "@/hooks/useApi";
import { useTodayMission, useWeeklyInsights, useWeeklyMetrics } from "@/hooks/useInsights";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import { getCreatorId } from "@/services/api";
import { MetricsBar } from "@/components/MetricsBar";
import { MissionCard } from "@/components/MissionCard";
import { InsightCard } from "@/components/InsightCard";

export default function Dashboard() {
  const creatorId = getCreatorId();
  const navigate = useNavigate();
  const { toast } = useToast();

  // Existing dashboard data (for bot status and creator name)
  const { data: dashboardData, isLoading: dashboardLoading, error: dashboardError } = useDashboard();
  const toggleBot = useToggleBot();

  // New insights data
  const { data: mission, isLoading: missionLoading } = useTodayMission(creatorId);
  const { data: insights, isLoading: insightsLoading } = useWeeklyInsights(creatorId);
  const { data: metrics, isLoading: metricsLoading } = useWeeklyMetrics(creatorId);

  // Greeting based on time
  const currentHour = new Date().getHours();
  const greeting = currentHour < 12 ? "Buenos días" : currentHour < 18 ? "Buenas tardes" : "Buenas noches";

  // Bot toggle handler
  const handleToggleBot = () => {
    if (!dashboardData) return;
    const newStatus = !dashboardData.clone_active;
    toggleBot.mutate(
      { active: newStatus },
      {
        onSuccess: () => {
          toast({
            title: newStatus ? "Bot Activado" : "Bot Pausado",
            description: newStatus ? "Respondiendo mensajes automáticamente" : "Pausado temporalmente",
          });
        },
        onError: (error) => {
          toast({ title: "Error", description: error.message, variant: "destructive" });
        },
      }
    );
  };

  // Open chat handler
  const handleOpenChat = (followerId: string) => {
    navigate(`/inbox?id=${followerId}`);
  };

  // Loading state
  if (dashboardLoading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  // Error state
  if (dashboardError) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-3">
        <AlertCircle className="w-8 h-8 text-destructive/60" />
        <p className="text-sm text-muted-foreground">Error al cargar datos</p>
      </div>
    );
  }

  const config = dashboardData?.config;
  const creatorName = dashboardData?.creator_name || config?.name || config?.clone_name || "Creator";
  const isActive = dashboardData?.clone_active ?? false;

  return (
    <div className="space-y-8 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-muted-foreground mb-1">{greeting}</p>
          <h1 className="text-2xl font-semibold tracking-tight">{creatorName}</h1>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={handleToggleBot}
          disabled={toggleBot.isPending}
          className={cn(
            "gap-2 h-9 px-4 font-medium transition-all",
            isActive
              ? "border-emerald-500/50 text-emerald-500 hover:bg-emerald-500/10"
              : "border-muted-foreground/30 text-muted-foreground"
          )}
        >
          {toggleBot.isPending ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <div className={cn("w-2 h-2 rounded-full", isActive ? "bg-emerald-500" : "bg-muted-foreground")} />
          )}
          {isActive ? "Activo" : "Pausado"}
        </Button>
      </div>

      {/* Metrics Bar */}
      {metricsLoading ? (
        <div className="h-20 bg-card rounded-xl border border-border/50 animate-pulse" />
      ) : metrics ? (
        <MetricsBar metrics={metrics} />
      ) : null}

      {/* Section: Ventas de Hoy */}
      <section>
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <span>💰</span>
          Ventas de Hoy
        </h2>

        {missionLoading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-32 bg-card rounded-xl border border-border/50 animate-pulse" />
            ))}
          </div>
        ) : mission && mission.hot_leads.length > 0 ? (
          <>
            {mission.potential_revenue > 0 && (
              <p className="text-muted-foreground mb-4">
                Si haces estas <span className="text-foreground font-medium">{mission.hot_leads.length} cosas</span>, cierras{" "}
                <span className="text-emerald-500 font-semibold">{mission.potential_revenue.toFixed(0)}€</span> hoy
              </p>
            )}

            <div className="space-y-3">
              {mission.hot_leads.map((lead) => (
                <MissionCard
                  key={lead.follower_id}
                  lead={lead}
                  onOpenChat={handleOpenChat}
                />
              ))}
            </div>

            {mission.pending_responses > 0 && (
              <div className="mt-4 flex items-center gap-2 text-muted-foreground">
                <MessageCircle className="w-4 h-4" />
                <span>+ {mission.pending_responses} personas más esperan respuesta</span>
                <Link to="/inbox" className="text-violet-400 hover:text-violet-300 ml-1 flex items-center gap-1">
                  Ver en Bandeja
                  <ChevronRight className="w-4 h-4" />
                </Link>
              </div>
            )}
          </>
        ) : (
          <div className="p-8 bg-card rounded-xl border border-border/50 text-center">
            <p className="text-muted-foreground">No hay leads calientes hoy</p>
            <p className="text-sm text-muted-foreground/70 mt-1">El bot está trabajando para ti</p>
          </div>
        )}
      </section>

      {/* Section: Agenda de Hoy */}
      {mission && mission.today_bookings && mission.today_bookings.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Calendar className="w-5 h-5" />
            Agenda de Hoy
          </h2>

          <div className="space-y-2">
            {mission.today_bookings.map((booking) => (
              <div
                key={booking.id}
                className="p-4 bg-card rounded-xl border border-border/50 flex items-center justify-between"
              >
                <div className="flex items-center gap-4">
                  <span className="font-semibold text-lg text-violet-400">{booking.time}</span>
                  <div>
                    <span className="font-medium">{booking.attendee_name}</span>
                    <span className="text-muted-foreground ml-2">• {booking.title}</span>
                  </div>
                </div>
                <span className="text-xs text-muted-foreground capitalize">{booking.platform}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Section: Ghosts to Reactivate */}
      {mission && mission.ghost_reactivation_count > 0 && (
        <section className="p-4 bg-muted/30 rounded-xl border border-border/30">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Ghost className="w-5 h-5 text-muted-foreground" />
              <div>
                <span className="font-medium">{mission.ghost_reactivation_count} fantasmas</span>
                <span className="text-muted-foreground ml-2">llevan +7 días sin respuesta</span>
              </div>
            </div>
            <Link
              to="/leads"
              className="text-sm text-violet-400 hover:text-violet-300 flex items-center gap-1"
            >
              Reactivar
              <ChevronRight className="w-4 h-4" />
            </Link>
          </div>
        </section>
      )}

      {/* Section: Tu Audiencia Esta Semana */}
      <section>
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <span>💡</span>
          Tu Audiencia Esta Semana
        </h2>

        {insightsLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-36 bg-card rounded-xl border border-border/50 animate-pulse" />
            ))}
          </div>
        ) : insights && (insights.content || insights.trend || insights.product || insights.competition) ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {insights.content && (
              <InsightCard
                icon="📝"
                title="CONTENIDO"
                highlight={`${insights.content.count} personas preguntaron sobre ${insights.content.topic}`}
                detail={`${insights.content.percentage.toFixed(0)}% de tu audiencia`}
                suggestion={insights.content.suggestion}
              />
            )}

            {insights.trend && (
              <InsightCard
                icon="🔥"
                title="TENDENCIA"
                highlight={`"${insights.trend.term}" apareció ${insights.trend.count} veces`}
                detail={insights.trend.growth}
                suggestion={insights.trend.suggestion}
              />
            )}

            {insights.product && (
              <InsightCard
                icon="🎁"
                title="PRODUCTO"
                highlight={`${insights.product.count} personas pidieron ${insights.product.product_name}`}
                detail={`Potencial: ${insights.product.potential_revenue.toFixed(0)}€`}
                suggestion={insights.product.suggestion}
              />
            )}

            {insights.competition && (
              <InsightCard
                icon="🆚"
                title="COMPETENCIA"
                highlight={`${insights.competition.count} mencionaron a ${insights.competition.competitor}`}
                detail={insights.competition.sentiment}
                suggestion={insights.competition.suggestion}
              />
            )}
          </div>
        ) : (
          <div className="p-8 bg-card rounded-xl border border-border/50 text-center">
            <p className="text-muted-foreground">No hay suficientes datos esta semana</p>
            <p className="text-sm text-muted-foreground/70 mt-1">Los insights aparecerán cuando tengas más conversaciones</p>
          </div>
        )}

        {/* Link to full audience page (future) */}
        {/* <Link
          to="/tu-audiencia"
          className="block mt-4 text-sm text-violet-400 hover:text-violet-300 flex items-center gap-1"
        >
          Ver todo en Tu Audiencia
          <ChevronRight className="w-4 h-4" />
        </Link> */}
      </section>
    </div>
  );
}
