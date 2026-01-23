import { TrendingUp, TrendingDown, MessageCircle, Users, AlertCircle, Loader2, Power, PowerOff, UserCheck, Bot, DollarSign, Zap, ArrowUpRight, ChevronRight } from "lucide-react";
import { Area, AreaChart, ResponsiveContainer, XAxis, YAxis, Tooltip } from "recharts";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { useDashboard, useToggleBot, useRevenue } from "@/hooks/useApi";
import { useToast } from "@/hooks/use-toast";
import { getPurchaseIntent } from "@/types/api";
import { cn } from "@/lib/utils";
import EscalationsCard from "@/components/EscalationsCard";

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
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
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
      follower_id: lead.follower_id,
      name: displayName,
      intent,
    };
  });

  return (
    <div className="space-y-8">
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

      {/* Main KPIs - Clean cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Revenue */}
        <div className="col-span-2 p-5 rounded-2xl bg-gradient-to-br from-emerald-500/10 via-emerald-500/5 to-transparent border border-emerald-500/20">
          <div className="flex items-center gap-2 mb-3">
            <DollarSign className="w-4 h-4 text-emerald-500" />
            <span className="text-xs font-medium text-emerald-500/80 uppercase tracking-wide">Ingresos 30d</span>
          </div>
          <div className="flex items-baseline gap-3">
            <span className="text-3xl font-semibold">€{totalRevenue.toLocaleString()}</span>
            {botAttributedRevenue > 0 && (
              <span className="text-sm text-emerald-500">
                €{botAttributedRevenue.toLocaleString()} via bot
              </span>
            )}
          </div>
        </div>

        {/* Messages */}
        <div className="p-5 rounded-2xl bg-card border border-border/50">
          <div className="flex items-center gap-2 mb-3">
            <MessageCircle className="w-4 h-4 text-muted-foreground" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Mensajes</span>
          </div>
          <span className="text-2xl font-semibold">{(metrics.total_messages || 0).toLocaleString()}</span>
        </div>

        {/* Followers */}
        <div className="p-5 rounded-2xl bg-card border border-border/50">
          <div className="flex items-center gap-2 mb-3">
            <Users className="w-4 h-4 text-muted-foreground" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Contactos</span>
          </div>
          <span className="text-2xl font-semibold">{metrics.total_followers || 0}</span>
        </div>
      </div>

      {/* Secondary metrics */}
      <div className="grid grid-cols-3 gap-4">
        <div className="p-4 rounded-xl bg-card/50 border border-border/30">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-muted-foreground">Leads</span>
            <Zap className="w-3.5 h-3.5 text-amber-500" />
          </div>
          <span className="text-xl font-semibold">{metrics.leads || 0}</span>
        </div>

        <div className="p-4 rounded-xl bg-card/50 border border-border/30">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-muted-foreground">Clientes</span>
            <UserCheck className="w-3.5 h-3.5 text-emerald-500" />
          </div>
          <span className="text-xl font-semibold">{metrics.customers || 0}</span>
        </div>

        <div className="p-4 rounded-xl bg-card/50 border border-border/30">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-muted-foreground">Conversión</span>
            <TrendingUp className="w-3.5 h-3.5 text-blue-500" />
          </div>
          <span className="text-xl font-semibold">{((metrics.conversion_rate || 0) * 100).toFixed(0)}%</span>
        </div>
      </div>

      {/* Escalations - needs attention */}
      <EscalationsCard maxItems={5} />

      {/* Two columns */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Activity Chart */}
        <div className="lg:col-span-3 p-5 rounded-2xl bg-card border border-border/50">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-medium">Actividad semanal</h3>
            <span className="text-xs text-muted-foreground">Conversaciones activas</span>
          </div>
          <div className="h-[160px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={engagementData}>
                <defs>
                  <linearGradient id="chartGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity={0.2} />
                    <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis
                  dataKey="day"
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }}
                />
                <YAxis hide />
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'hsl(var(--card))',
                    border: '1px solid hsl(var(--border))',
                    borderRadius: '8px',
                    fontSize: '12px',
                  }}
                  formatter={(value: number) => [`${value}`, 'Activas']}
                />
                <Area
                  type="monotone"
                  dataKey="value"
                  stroke="hsl(var(--primary))"
                  strokeWidth={2}
                  fill="url(#chartGradient)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Hot Leads */}
        <div className="lg:col-span-2 p-5 rounded-2xl bg-card border border-border/50">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-medium">Leads calientes</h3>
            <Link
              to="/leads"
              className="text-xs text-primary hover:text-primary/80 transition-colors flex items-center gap-1"
            >
              Ver todos
              {hotLeads.length > 5 && <span className="text-muted-foreground">(+{hotLeads.length - 5})</span>}
              <ChevronRight className="w-3 h-3" />
            </Link>
          </div>
          <div className="space-y-2">
            {actionItems.length > 0 ? (
              actionItems.map((item) => (
                <Link
                  key={item.id}
                  to={`/inbox?id=${item.follower_id}`}
                  className="flex items-center justify-between p-3 rounded-lg bg-muted/30 hover:bg-muted/50 transition-colors cursor-pointer group"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-8 h-8 rounded-full bg-rose-500/10 flex items-center justify-center shrink-0">
                      <Zap className="w-3.5 h-3.5 text-rose-500" />
                    </div>
                    <span className="text-sm font-medium truncate">{item.name}</span>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-xs text-rose-500 font-medium">{item.intent}%</span>
                    <ChevronRight className="w-4 h-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                  </div>
                </Link>
              ))
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                <p className="text-sm">Sin leads calientes</p>
                <p className="text-xs mt-1">El bot está trabajando</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
