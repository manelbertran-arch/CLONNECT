import { TrendingUp, Flame, MessageCircle, Users, AlertCircle, Loader2, Power, PowerOff, UserCheck } from "lucide-react";
import { Area, AreaChart, ResponsiveContainer, XAxis, YAxis, Tooltip } from "recharts";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import { useDashboard, useToggleBot } from "@/hooks/useApi";
import { useToast } from "@/hooks/use-toast";
import { getPurchaseIntent } from "@/types/api";
import { OnboardingChecklist } from "@/components/OnboardingChecklist";

export default function Dashboard() {
  const { data, isLoading, error } = useDashboard();
  const toggleBot = useToggleBot();
  const { toast } = useToast();

  const currentHour = new Date().getHours();
  const greeting = currentHour < 12 ? "Good morning" : currentHour < 18 ? "Good afternoon" : "Good evening";

  // Handle bot toggle
  const handleToggleBot = () => {
    if (!data) return;

    const newStatus = !data.clone_active;
    toggleBot.mutate(
      { active: newStatus },
      {
        onSuccess: () => {
          toast({
            title: newStatus ? "Bot Activated" : "Bot Paused",
            description: newStatus
              ? "Your AI clone is now responding to messages"
              : "Your AI clone is paused",
          });
        },
        onError: (error) => {
          toast({
            title: "Error",
            description: error.message,
            variant: "destructive",
          });
        },
      }
    );
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
        <p className="text-muted-foreground">Failed to load dashboard data</p>
        <p className="text-sm text-destructive">{error.message}</p>
      </div>
    );
  }

  // Extract data with safe defaults
  const metrics = data?.metrics || {
    total_messages: 0,
    total_followers: 0,
    leads: 0,
    customers: 0,
    high_intent_followers: 0,
    conversion_rate: 0,
    lead_rate: 0,
  };

  const config = data?.config;
  const creatorName = data?.creator_name || config?.name || config?.clone_name || "Creator";
  const isActive = data?.clone_active ?? false;

  // Calculate progress based on leads goal
  const leadsGoal = 50;
  const progressPercent = Math.min(100, ((metrics.leads || 0) / leadsGoal) * 100);

  // Generate engagement trend data from recent conversations
  // Shows MESSAGE COUNT per day from conversations
  const getEngagementData = () => {
    const dayNames = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    const now = new Date();

    // Get recent conversations
    const recentConversations = data?.recent_conversations || [];

    // Build date keys for last 7 days using LOCAL date (not UTC)
    const messagesByDate: Record<string, number> = {};
    const dateToDay: Record<string, string> = {};

    for (let i = 6; i >= 0; i--) {
      const d = new Date(now);
      d.setDate(d.getDate() - i);
      // Use local date format YYYY-MM-DD
      const dateKey = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
      messagesByDate[dateKey] = 0;
      dateToDay[dateKey] = dayNames[d.getDay()];
    }

    // Count MESSAGES (not conversations) per day
    // Each conversation adds its total_messages to its last_contact date
    recentConversations.forEach((conv: any) => {
      if (conv.last_contact) {
        const contactDate = new Date(conv.last_contact);
        // Use local date format
        const dateKey = `${contactDate.getFullYear()}-${String(contactDate.getMonth() + 1).padStart(2, '0')}-${String(contactDate.getDate()).padStart(2, '0')}`;

        // Only count if this date is in our 7-day window
        if (dateKey in messagesByDate) {
          // Add total_messages for this conversation to this day
          messagesByDate[dateKey] += (conv.total_messages || 1);
        }
      }
    });

    // Build data array for last 7 days in order (oldest first)
    const result = [];
    for (let i = 6; i >= 0; i--) {
      const d = new Date(now);
      d.setDate(d.getDate() - i);
      const dateKey = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
      result.push({
        day: dateToDay[dateKey],
        value: messagesByDate[dateKey] || 0
      });
    }

    return result;
  };

  const engagementData = getEngagementData();

  // Build action items from hot leads - use NAME not username
  // Hot = 50%+ with new ranges (0-25% new | 25-50% warm | 50%+ hot)
  const hotLeads = data?.leads?.filter(l => getPurchaseIntent(l) >= 0.50) || [];
  const actionItems = hotLeads.slice(0, 3).map((lead, i) => {
    // Use extracted name, fallback to username, then follower_id
    const displayName = lead.name || lead.username || lead.follower_id;
    const isUsername = !lead.name && lead.username;
    return {
      id: `lead-${i}`,
      title: `${isUsername ? '@' : ''}${displayName} is a hot lead`,
      subtitle: `Intent Score: ${(getPurchaseIntent(lead) * 100).toFixed(0)}%`,
      priority: "high" as const,
      time: "Recently active",
    };
  });

  // Add notification for high intent followers
  if ((metrics.high_intent_followers || 0) > 0 && actionItems.length === 0) {
    actionItems.push({
      id: "high-intent",
      title: `${metrics.high_intent_followers} high intent follower${metrics.high_intent_followers > 1 ? 's' : ''}`,
      subtitle: "Ready to convert",
      priority: "high" as const,
      time: "Now",
    });
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">
            {greeting}, <span className="gradient-text">{creatorName}</span>
          </h1>
          <p className="text-muted-foreground mt-1 text-sm sm:text-base">Here's what's happening with your business today.</p>
        </div>
        <Button
          variant={isActive ? "default" : "outline"}
          className={`gap-2 ${isActive ? "status-badge status-online animate-pulse-glow" : "status-badge"}`}
          onClick={handleToggleBot}
          disabled={toggleBot.isPending}
        >
          {toggleBot.isPending ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : isActive ? (
            <Power className="w-4 h-4" />
          ) : (
            <PowerOff className="w-4 h-4" />
          )}
          {isActive ? "Bot Online" : "Bot Paused"}
        </Button>
      </div>

      {/* Onboarding Checklist - shows only if incomplete */}
      <OnboardingChecklist />

      {/* Main Stats Card */}
      <div className="metric-card glow relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-primary/5 to-accent/5"></div>
        <div className="relative">
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="text-muted-foreground text-sm font-medium">Total Messages</p>
              <p className="text-4xl font-bold mt-1">{(metrics.total_messages || 0).toLocaleString()}</p>
            </div>
            <div className="flex items-center gap-2 text-success text-sm font-medium">
              <TrendingUp className="w-4 h-4" />
              {metrics.leads || 0} leads · {metrics.customers || 0} customers
            </div>
          </div>
          <div className="space-y-2">
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Progress to {leadsGoal} leads goal</span>
              <span className="font-medium">{progressPercent.toFixed(0)}%</span>
            </div>
            <Progress value={progressPercent} className="h-2" />
          </div>
        </div>
      </div>

      {/* Metrics Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="metric-card group hover:glow transition-all">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-destructive/10 flex items-center justify-center group-hover:scale-110 transition-transform">
              <Flame className="w-6 h-6 text-destructive" />
            </div>
            <div>
              <p className="text-muted-foreground text-sm">Hot Leads</p>
              <p className="text-2xl font-bold">{metrics.high_intent_followers || 0}</p>
            </div>
          </div>
        </div>

        <div className="metric-card group hover:glow-cyan transition-all">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-accent/10 flex items-center justify-center group-hover:scale-110 transition-transform">
              <Users className="w-6 h-6 text-accent" />
            </div>
            <div>
              <p className="text-muted-foreground text-sm">Total Followers</p>
              <p className="text-2xl font-bold">{metrics.total_followers || 0}</p>
            </div>
          </div>
        </div>

        <div className="metric-card group hover:glow transition-all">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center group-hover:scale-110 transition-transform">
              <UserCheck className="w-6 h-6 text-primary" />
            </div>
            <div>
              <p className="text-muted-foreground text-sm">Conversion Rate</p>
              <p className="text-2xl font-bold">{((metrics.conversion_rate || 0) * 100).toFixed(0)}%</p>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Action Required */}
        <div className="metric-card">
          <h3 className="font-semibold mb-4 flex items-center gap-2">
            <AlertCircle className="w-5 h-5 text-warning" />
            Action Required
          </h3>
          <div className="space-y-3">
            {actionItems.length > 0 ? (
              actionItems.map((item) => (
                <div
                  key={item.id}
                  className="flex items-start gap-3 p-3 rounded-lg bg-secondary/50 hover:bg-secondary transition-colors cursor-pointer"
                >
                  <div className={`w-2 h-2 rounded-full mt-2 ${item.priority === "high" ? "bg-destructive" : "bg-warning"}`}></div>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-sm">{item.title}</p>
                    <p className="text-xs text-muted-foreground">{item.subtitle}</p>
                  </div>
                  <span className="text-xs text-muted-foreground whitespace-nowrap">{item.time}</span>
                </div>
              ))
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                <p>No actions required</p>
                <p className="text-sm">Your bot is handling everything!</p>
              </div>
            )}
          </div>
        </div>

        {/* Engagement Trend */}
        <div className="metric-card">
          <h3 className="font-semibold mb-4 flex items-center gap-2">
            <MessageCircle className="w-5 h-5 text-primary" />
            Message Activity
          </h3>
          <div className="h-[180px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={engagementData}>
                <defs>
                  <linearGradient id="engagementGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="hsl(262, 83%, 58%)" stopOpacity={0.3} />
                    <stop offset="100%" stopColor="hsl(187, 92%, 55%)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="day" axisLine={false} tickLine={false} tick={{ fill: 'hsl(240, 5%, 65%)', fontSize: 12 }} />
                <YAxis hide />
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'hsl(240, 5%, 8%)',
                    border: '1px solid hsl(240, 4%, 16%)',
                    borderRadius: '8px',
                    color: 'hsl(0, 0%, 98%)',
                  }}
                  formatter={(value: number) => [`${value} message${value !== 1 ? 's' : ''}`, 'Activity']}
                />
                <Area
                  type="monotone"
                  dataKey="value"
                  stroke="url(#engagementGradient)"
                  strokeWidth={2}
                  fill="url(#engagementGradient)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
}
