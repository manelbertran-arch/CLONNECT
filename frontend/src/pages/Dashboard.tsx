import { TrendingUp, MessageCircle, Users, AlertCircle, Loader2, UserCheck, DollarSign, Zap, ChevronRight, Activity, Flame } from "lucide-react";
import { Area, AreaChart, ResponsiveContainer, XAxis, YAxis, Tooltip } from "recharts";
import { Button } from "@/components/ui/button";
import { useDashboard, useToggleBot, useRevenue } from "@/hooks/useApi";
import { useToast } from "@/hooks/use-toast";
import { getPurchaseIntent } from "@/types/api";
import { cn } from "@/lib/utils";

export default function Dashboard() {
  const { data, isLoading, error } = useDashboard();
  const { data: revenueData } = useRevenue();
  const toggleBot = useToggleBot();
  const { toast } = useToast();

  const currentHour = new Date().getHours();
  const greeting = currentHour < 12 ? "Buenos días" : currentHour < 18 ? "Buenas tardes" : "Buenas noches";

  const handleToggleBot = () => {
    if (!data) return;
    const newStatus = !data.clone_active;
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

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="relative">
          <div className="absolute inset-0 rounded-full bg-primary/20 blur-xl animate-pulse" />
          <Loader2 className="w-8 h-8 animate-spin text-primary relative" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-3">
        <AlertCircle className="w-8 h-8 text-destructive/60" />
        <p className="text-sm text-muted-foreground">Error al cargar datos</p>
      </div>
    );
  }

  const metrics = data?.metrics || {
    total_messages: 0,
    total_followers: 0,
    leads: 0,
    customers: 0,
    high_intent_followers: 0,
    conversion_rate: 0,
  };

  const config = data?.config;
  const creatorName = data?.creator_name || config?.name || config?.clone_name || "Creator";
  const isActive = data?.clone_active ?? false;

  const totalRevenue = revenueData?.total_revenue || 0;
  const botAttributedRevenue = revenueData?.bot_attributed_revenue || 0;

  // Engagement data
  const getEngagementData = () => {
    const dayNames = ["D", "L", "M", "X", "J", "V", "S"];
    const now = new Date();
    const recentConversations = data?.recent_conversations || [];
    const messagesByDate: Record<string, number> = {};
    const dateToDay: Record<string, string> = {};

    for (let i = 6; i >= 0; i--) {
      const d = new Date(now);
      d.setDate(d.getDate() - i);
      const dateKey = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
      messagesByDate[dateKey] = 0;
      dateToDay[dateKey] = dayNames[d.getDay()];
    }

    recentConversations.forEach((conv: any) => {
      if (conv.last_contact) {
        const contactDate = new Date(conv.last_contact);
        const dateKey = `${contactDate.getFullYear()}-${String(contactDate.getMonth() + 1).padStart(2, '0')}-${String(contactDate.getDate()).padStart(2, '0')}`;
        if (dateKey in messagesByDate) {
          messagesByDate[dateKey] += 1;
        }
      }
    });

    const result = [];
    for (let i = 6; i >= 0; i--) {
      const d = new Date(now);
      d.setDate(d.getDate() - i);
      const dateKey = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
      result.push({ day: dateToDay[dateKey], value: messagesByDate[dateKey] || 0 });
    }
    return result;
  };

  const engagementData = getEngagementData();

  // Hot leads
  const hotLeads = data?.leads?.filter(l => getPurchaseIntent(l) >= 0.50) || [];
  const actionItems = hotLeads.slice(0, 5).map((lead, i) => {
    const displayName = lead.name || lead.username || lead.follower_id;
    const intent = (getPurchaseIntent(lead) * 100).toFixed(0);
    return {
      id: `lead-${i}`,
      name: displayName,
      intent,
    };
  });

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      {/* Header with glassmorphism */}
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-muted-foreground/80 mb-0.5">{greeting}</p>
          <h1 className="text-3xl font-bold tracking-tight bg-gradient-to-r from-foreground to-foreground/70 bg-clip-text">{creatorName}</h1>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={handleToggleBot}
          disabled={toggleBot.isPending}
          className={cn(
            "gap-2 h-10 px-5 font-medium transition-all duration-300 backdrop-blur-sm",
            isActive
              ? "border-emerald-500/40 text-emerald-400 hover:bg-emerald-500/10 hover:border-emerald-500/60 shadow-[0_0_20px_rgba(16,185,129,0.15)]"
              : "border-muted-foreground/20 text-muted-foreground hover:border-muted-foreground/40"
          )}
        >
          {toggleBot.isPending ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <div className={cn(
              "w-2.5 h-2.5 rounded-full transition-all duration-300",
              isActive ? "bg-emerald-400 shadow-[0_0_8px_rgba(16,185,129,0.8)] animate-pulse" : "bg-muted-foreground"
            )} />
          )}
          {isActive ? "Activo" : "Pausado"}
        </Button>
      </div>

      {/* Hero Revenue Card - Ultra Modern */}
      <div className="relative group">
        <div className="absolute -inset-0.5 bg-gradient-to-r from-emerald-500 via-cyan-500 to-emerald-500 rounded-3xl blur-lg opacity-30 group-hover:opacity-40 transition-opacity duration-500" />
        <div className="relative p-6 sm:p-8 rounded-2xl bg-gradient-to-br from-emerald-500/20 via-emerald-500/10 to-cyan-500/10 border border-emerald-500/30 backdrop-blur-xl overflow-hidden">
          {/* Animated background pattern */}
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_20%,rgba(16,185,129,0.15),transparent_50%)]" />
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_70%_80%,rgba(6,182,212,0.1),transparent_50%)]" />

          <div className="relative">
            <div className="flex items-center gap-2 mb-4">
              <div className="p-2 rounded-xl bg-emerald-500/20 backdrop-blur-sm">
                <DollarSign className="w-5 h-5 text-emerald-400" />
              </div>
              <span className="text-sm font-semibold text-emerald-400/90 uppercase tracking-wider">Ingresos 30d</span>
            </div>
            <div className="flex items-baseline gap-4">
              <span className="text-5xl sm:text-6xl font-bold tracking-tight text-white">€{totalRevenue.toLocaleString()}</span>
              {botAttributedRevenue > 0 && (
                <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-emerald-500/20 backdrop-blur-sm border border-emerald-500/30">
                  <Activity className="w-3.5 h-3.5 text-emerald-400" />
                  <span className="text-sm font-medium text-emerald-300">€{botAttributedRevenue.toLocaleString()} vía bot</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Stats Grid - Glassmorphism style */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: "Mensajes", value: metrics.total_messages || 0, icon: MessageCircle, color: "text-violet-400", bg: "from-violet-500/10 to-purple-500/5" },
          { label: "Contactos", value: metrics.total_followers || 0, icon: Users, color: "text-blue-400", bg: "from-blue-500/10 to-cyan-500/5" },
          { label: "Leads", value: metrics.leads || 0, icon: Zap, color: "text-amber-400", bg: "from-amber-500/10 to-orange-500/5" },
          { label: "Clientes", value: metrics.customers || 0, icon: UserCheck, color: "text-emerald-400", bg: "from-emerald-500/10 to-green-500/5" },
        ].map((stat) => (
          <div
            key={stat.label}
            className={cn(
              "group relative p-4 sm:p-5 rounded-2xl border border-white/[0.08] backdrop-blur-sm",
              "bg-gradient-to-br",
              stat.bg,
              "hover:border-white/[0.15] transition-all duration-300 hover:scale-[1.02]"
            )}
          >
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-medium text-muted-foreground/80 uppercase tracking-wide">{stat.label}</span>
              <stat.icon className={cn("w-4 h-4", stat.color)} />
            </div>
            <span className="text-2xl sm:text-3xl font-bold">{stat.value.toLocaleString()}</span>
          </div>
        ))}
      </div>

      {/* Conversion Rate - Special card */}
      <div className="p-4 sm:p-5 rounded-2xl bg-gradient-to-r from-primary/10 via-accent/5 to-primary/10 border border-primary/20 backdrop-blur-sm">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-primary/20">
              <TrendingUp className="w-4 h-4 text-primary" />
            </div>
            <div>
              <p className="text-xs text-muted-foreground uppercase tracking-wide">Tasa de conversión</p>
              <p className="text-2xl font-bold">{((metrics.conversion_rate || 0) * 100).toFixed(1)}%</p>
            </div>
          </div>
          <div className="hidden sm:flex items-center gap-2 text-xs text-muted-foreground">
            <span>Leads → Clientes</span>
          </div>
        </div>
      </div>

      {/* Two columns layout */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4 sm:gap-6">
        {/* Activity Chart */}
        <div className="lg:col-span-3 p-5 sm:p-6 rounded-2xl bg-card/50 border border-white/[0.08] backdrop-blur-sm">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-2">
              <Activity className="w-4 h-4 text-primary" />
              <h3 className="font-semibold">Actividad semanal</h3>
            </div>
            <span className="text-xs text-muted-foreground px-2 py-1 rounded-full bg-muted/30">Últimos 7 días</span>
          </div>
          <div className="h-[180px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={engagementData}>
                <defs>
                  <linearGradient id="chartGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity={0.3} />
                    <stop offset="50%" stopColor="hsl(var(--primary))" stopOpacity={0.1} />
                    <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis
                  dataKey="day"
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }}
                  dy={10}
                />
                <YAxis hide />
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'hsl(var(--card))',
                    border: '1px solid hsl(var(--border))',
                    borderRadius: '12px',
                    fontSize: '12px',
                    boxShadow: '0 4px 20px rgba(0,0,0,0.3)',
                  }}
                  formatter={(value: number) => [`${value} conversaciones`, '']}
                  labelStyle={{ color: 'hsl(var(--muted-foreground))' }}
                />
                <Area
                  type="monotone"
                  dataKey="value"
                  stroke="hsl(var(--primary))"
                  strokeWidth={2.5}
                  fill="url(#chartGradient)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Hot Leads */}
        <div className="lg:col-span-2 p-5 sm:p-6 rounded-2xl bg-card/50 border border-white/[0.08] backdrop-blur-sm">
          <div className="flex items-center justify-between mb-5">
            <div className="flex items-center gap-2">
              <Flame className="w-4 h-4 text-rose-400" />
              <h3 className="font-semibold">Leads calientes</h3>
            </div>
            {hotLeads.length > 5 && (
              <span className="text-xs text-muted-foreground bg-muted/30 px-2 py-1 rounded-full">+{hotLeads.length - 5}</span>
            )}
          </div>
          <div className="space-y-2">
            {actionItems.length > 0 ? (
              actionItems.map((item, idx) => (
                <div
                  key={item.id}
                  className="group flex items-center justify-between p-3 rounded-xl bg-gradient-to-r from-rose-500/5 to-orange-500/5 border border-rose-500/10 hover:border-rose-500/30 transition-all duration-300 cursor-pointer hover:scale-[1.02]"
                  style={{ animationDelay: `${idx * 50}ms` }}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-9 h-9 rounded-full bg-gradient-to-br from-rose-500/20 to-orange-500/20 flex items-center justify-center shrink-0 border border-rose-500/20">
                      <Zap className="w-4 h-4 text-rose-400" />
                    </div>
                    <span className="text-sm font-medium truncate">{item.name}</span>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-xs font-bold text-rose-400 bg-rose-500/10 px-2 py-0.5 rounded-full">{item.intent}%</span>
                    <ChevronRight className="w-4 h-4 text-muted-foreground opacity-0 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all" />
                  </div>
                </div>
              ))
            ) : (
              <div className="text-center py-10 text-muted-foreground">
                <div className="w-12 h-12 rounded-full bg-muted/20 flex items-center justify-center mx-auto mb-3">
                  <Zap className="w-5 h-5" />
                </div>
                <p className="text-sm font-medium">Sin leads calientes</p>
                <p className="text-xs mt-1 opacity-70">El bot está trabajando para ti</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
