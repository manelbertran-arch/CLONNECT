import { TrendingUp, TrendingDown, Minus, DollarSign, Target, Users, MessageSquare, Image, SmilePlus } from 'lucide-react';
import { cn } from '@/lib/utils';

interface KPI {
  value: number;
  change: number;
  trend: 'up' | 'down' | 'stable';
}

interface SummaryKPIsProps {
  data?: {
    revenue: KPI;
    conversions: KPI;
    leads: KPI;
    dms: KPI;
    posts: KPI;
    sentiment: KPI;
  };
  isLoading: boolean;
}

export function SummaryKPIs({ data, isLoading }: SummaryKPIsProps) {
  if (isLoading || !data) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        {[...Array(6)].map((_, i) => (
          <div key={i} className="p-4 rounded-xl bg-card border border-border/50 animate-pulse h-24" />
        ))}
      </div>
    );
  }

  const kpis = [
    {
      label: 'Revenue',
      value: `€${data.revenue.value.toLocaleString()}`,
      change: data.revenue.change,
      icon: DollarSign,
      color: 'emerald'
    },
    {
      label: 'Conversiones',
      value: data.conversions.value,
      change: data.conversions.change,
      icon: Target,
      color: 'blue'
    },
    {
      label: 'Nuevos Leads',
      value: data.leads.value,
      change: data.leads.change,
      icon: Users,
      color: 'amber'
    },
    {
      label: 'DMs',
      value: data.dms.value,
      change: data.dms.change,
      icon: MessageSquare,
      color: 'purple'
    },
    {
      label: 'Posts',
      value: data.posts.value,
      change: data.posts.change,
      icon: Image,
      color: 'rose'
    },
    {
      label: 'Sentimiento',
      value: data.sentiment.value.toFixed(2),
      change: data.sentiment.change,
      icon: SmilePlus,
      color: data.sentiment.value > 0 ? 'emerald' : data.sentiment.value < 0 ? 'red' : 'gray',
      isSentiment: true
    }
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
      {kpis.map((kpi) => {
        const Icon = kpi.icon;
        const isPositive = kpi.isSentiment ? kpi.change > 0 : kpi.change > 0;
        const isNegative = kpi.isSentiment ? kpi.change < 0 : kpi.change < 0;

        return (
          <div
            key={kpi.label}
            className="p-4 rounded-xl bg-card border border-border/50 hover:border-border transition-colors"
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-muted-foreground uppercase tracking-wide">
                {kpi.label}
              </span>
              <Icon className={cn(
                "w-4 h-4",
                kpi.color === 'emerald' && "text-emerald-500",
                kpi.color === 'blue' && "text-blue-500",
                kpi.color === 'amber' && "text-amber-500",
                kpi.color === 'purple' && "text-purple-500",
                kpi.color === 'rose' && "text-rose-500",
                kpi.color === 'red' && "text-red-500",
                kpi.color === 'gray' && "text-gray-500"
              )} />
            </div>
            <p className="text-2xl font-semibold">{kpi.value}</p>
            <div className={cn(
              "flex items-center mt-1 text-sm font-medium",
              isPositive && "text-emerald-500",
              isNegative && "text-rose-500",
              !isPositive && !isNegative && "text-muted-foreground"
            )}>
              {isPositive ? (
                <TrendingUp className="w-3 h-3 mr-1" />
              ) : isNegative ? (
                <TrendingDown className="w-3 h-3 mr-1" />
              ) : (
                <Minus className="w-3 h-3 mr-1" />
              )}
              {kpi.isSentiment ? (
                <span>{kpi.change > 0 ? '+' : ''}{kpi.change.toFixed(2)}</span>
              ) : (
                <span>{kpi.change > 0 ? '+' : ''}{kpi.change}%</span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
