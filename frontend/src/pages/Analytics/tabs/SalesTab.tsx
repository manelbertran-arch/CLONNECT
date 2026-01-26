import { useSalesAnalytics, useTrends } from '@/hooks/useAnalytics';
import { Loader2, DollarSign, TrendingUp, TrendingDown, Package, ShoppingCart } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Area, AreaChart, ResponsiveContainer, XAxis, YAxis, Tooltip } from 'recharts';

interface SalesTabProps {
  creatorId: string;
  period: string;
}

export function SalesTab({ creatorId, period }: SalesTabProps) {
  const { data, isLoading, isError } = useSalesAnalytics(creatorId, period);
  const { data: trendData } = useTrends(creatorId, 'revenue', period);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <DollarSign className="w-12 h-12 mx-auto mb-3 opacity-50" />
        <p>Error al cargar datos de ventas</p>
      </div>
    );
  }

  const { summary, by_product, revenue_trend } = data;
  const chartData = trendData?.data || revenue_trend || [];

  return (
    <div className="space-y-6">
      {/* Main KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className={cn(
          "col-span-2 p-5 rounded-xl border",
          summary.total_revenue > 0
            ? "bg-gradient-to-br from-emerald-500/10 via-emerald-500/5 to-transparent border-emerald-500/20"
            : "bg-card border-border/50"
        )}>
          <div className="flex items-center gap-2 mb-3">
            <DollarSign className={cn("w-4 h-4", summary.total_revenue > 0 ? "text-emerald-500" : "text-muted-foreground")} />
            <span className={cn(
              "text-xs font-medium uppercase tracking-wide",
              summary.total_revenue > 0 ? "text-emerald-500/80" : "text-muted-foreground"
            )}>Revenue Total</span>
          </div>
          <div className="flex items-baseline gap-3">
            <span className="text-3xl font-semibold">€{summary.total_revenue.toLocaleString()}</span>
            {summary.revenue_change !== 0 && (
              <span className={cn(
                "text-sm font-medium flex items-center",
                summary.revenue_change > 0 ? "text-emerald-500" : "text-rose-500"
              )}>
                {summary.revenue_change > 0 ? <TrendingUp className="w-3 h-3 mr-1" /> : <TrendingDown className="w-3 h-3 mr-1" />}
                {summary.revenue_change > 0 ? '+' : ''}{summary.revenue_change}%
              </span>
            )}
          </div>
          <p className="text-xs text-muted-foreground mt-2">
            Anterior: €{summary.previous_revenue?.toLocaleString() || 0}
          </p>
        </div>

        <div className="p-4 rounded-xl bg-card border border-border/50">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-muted-foreground">Ventas</span>
            <ShoppingCart className="w-4 h-4 text-blue-500" />
          </div>
          <p className="text-2xl font-semibold">{summary.total_sales}</p>
          {summary.sales_change !== 0 && (
            <p className={cn(
              "text-xs font-medium mt-1",
              summary.sales_change > 0 ? "text-emerald-500" : "text-rose-500"
            )}>
              {summary.sales_change > 0 ? '+' : ''}{summary.sales_change}%
            </p>
          )}
        </div>

        <div className="p-4 rounded-xl bg-card border border-border/50">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-muted-foreground">Ticket Promedio</span>
            <DollarSign className="w-4 h-4 text-amber-500" />
          </div>
          <p className="text-2xl font-semibold">€{summary.avg_ticket?.toLocaleString() || 0}</p>
        </div>
      </div>

      {/* Revenue Chart */}
      {chartData.length > 0 && (
        <div className="p-5 rounded-xl bg-card border border-border/50">
          <h3 className="text-sm font-medium mb-4">Tendencia de Revenue</h3>
          <div className="h-[200px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="revenueGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity={0.3} />
                    <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis
                  dataKey="date"
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }}
                  tickFormatter={(value) => {
                    const date = new Date(value);
                    return `${date.getDate()}/${date.getMonth() + 1}`;
                  }}
                />
                <YAxis
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }}
                  tickFormatter={(value) => `€${value}`}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'hsl(var(--card))',
                    border: '1px solid hsl(var(--border))',
                    borderRadius: '8px',
                    fontSize: '12px',
                  }}
                  formatter={(value: number) => [`€${value.toLocaleString()}`, 'Revenue']}
                  labelFormatter={(label) => new Date(label).toLocaleDateString()}
                />
                <Area
                  type="monotone"
                  dataKey="value"
                  stroke="hsl(var(--primary))"
                  strokeWidth={2}
                  fill="url(#revenueGradient)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Products Performance */}
      {by_product?.length > 0 && (
        <div className="p-5 rounded-xl bg-card border border-border/50">
          <h3 className="text-sm font-medium mb-4 flex items-center gap-2">
            <Package className="w-4 h-4 text-primary" />
            Performance por Producto
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="text-left text-xs text-muted-foreground uppercase tracking-wide border-b border-border/50">
                  <th className="pb-3 font-medium">Producto</th>
                  <th className="pb-3 font-medium text-right">Precio</th>
                  <th className="pb-3 font-medium text-right">Menciones</th>
                  <th className="pb-3 font-medium text-right">Categoria</th>
                  <th className="pb-3 font-medium text-right">Estado</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/30">
                {by_product.map((product: any) => (
                  <tr key={product.id} className="hover:bg-muted/30 transition-colors">
                    <td className="py-3">
                      <span className="font-medium">{product.name}</span>
                    </td>
                    <td className="py-3 text-right">€{product.price?.toLocaleString() || 0}</td>
                    <td className="py-3 text-right">
                      <span className={cn(
                        "font-medium",
                        product.mentions > 10 ? "text-emerald-500" : ""
                      )}>
                        {product.mentions}
                      </span>
                    </td>
                    <td className="py-3 text-right">
                      <span className="text-xs px-2 py-1 bg-muted rounded-full">
                        {product.category || 'N/A'}
                      </span>
                    </td>
                    <td className="py-3 text-right">
                      <span className={cn(
                        "text-xs px-2 py-1 rounded-full",
                        product.is_active ? "bg-emerald-500/10 text-emerald-500" : "bg-muted text-muted-foreground"
                      )}>
                        {product.is_active ? 'Activo' : 'Inactivo'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Empty State */}
      {summary.total_sales === 0 && by_product?.length === 0 && (
        <div className="text-center py-12 text-muted-foreground">
          <ShoppingCart className="w-12 h-12 mx-auto mb-3 opacity-50" />
          <p>No hay ventas en este periodo</p>
          <p className="text-sm mt-1">Las ventas apareceran cuando los leads se conviertan en clientes</p>
        </div>
      )}
    </div>
  );
}
