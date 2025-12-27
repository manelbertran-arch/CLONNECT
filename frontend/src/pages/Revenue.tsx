import { useState } from "react";
import { TrendingUp, CreditCard, Bot, Loader2, AlertCircle, ArrowUpRight, Plus, X } from "lucide-react";
import { useRevenue, usePurchases, useRecordPurchase } from "@/hooks/useApi";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useToast } from "@/hooks/use-toast";

function formatCurrency(amount: number, currency: string = "EUR"): string {
  return new Intl.NumberFormat("es-ES", {
    style: "currency",
    currency: currency,
  }).format(amount);
}

function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString("es-ES", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function Revenue() {
  const { data: revenueData, isLoading: revenueLoading, error: revenueError } = useRevenue();
  const { data: purchasesData, isLoading: purchasesLoading } = usePurchases();
  const recordPurchase = useRecordPurchase();
  const { toast } = useToast();

  const [showRecordForm, setShowRecordForm] = useState(false);
  const [newPurchase, setNewPurchase] = useState({
    product_name: "",
    amount: 97,
    currency: "EUR",
    platform: "stripe",
    bot_attributed: true,
  });

  const handleRecordPurchase = async () => {
    if (!newPurchase.product_name) {
      toast({ title: "Error", description: "Product name is required", variant: "destructive" });
      return;
    }
    try {
      await recordPurchase.mutateAsync(newPurchase);
      toast({ title: "Success", description: "Purchase recorded successfully" });
      setShowRecordForm(false);
      setNewPurchase({ product_name: "", amount: 97, currency: "EUR", platform: "stripe", bot_attributed: true });
    } catch (error: any) {
      toast({ title: "Error", description: error.message || "Failed to record purchase", variant: "destructive" });
    }
  };

  // Loading state
  if (revenueLoading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  // Error state
  if (revenueError) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <AlertCircle className="w-12 h-12 text-destructive" />
        <p className="text-muted-foreground">Failed to load revenue data</p>
        <p className="text-sm text-destructive">{revenueError.message}</p>
      </div>
    );
  }

  const totalRevenue = revenueData?.total_revenue || 0;
  const botAttributed = revenueData?.bot_attributed_revenue || 0;
  const totalPurchases = revenueData?.total_purchases || 0;
  const avgOrderValue = revenueData?.avg_order_value || 0;
  const stripeRevenue = revenueData?.revenue_by_platform?.stripe || 0;
  const hotmartRevenue = revenueData?.revenue_by_platform?.hotmart || 0;
  const botPercentage = totalRevenue > 0 ? (botAttributed / totalRevenue) * 100 : 0;
  const purchases = purchasesData?.purchases || [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-xl sm:text-2xl font-bold tracking-tight">Revenue Analytics</h1>
        <p className="text-muted-foreground text-sm sm:text-base">Track your earnings across all platforms</p>
      </div>

      {/* Main Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {/* Total Revenue */}
        <div className="metric-card glow">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
              <TrendingUp className="w-5 h-5 text-primary" />
            </div>
          </div>
          <p className="text-3xl font-bold">{formatCurrency(totalRevenue)}</p>
          <p className="text-sm text-muted-foreground">Total Revenue (30d)</p>
        </div>

        {/* Bot Attributed */}
        <div className="metric-card">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-lg bg-success/10 flex items-center justify-center">
              <Bot className="w-5 h-5 text-success" />
            </div>
            <span className="text-xs px-2 py-1 rounded-full bg-success/10 text-success">
              {botPercentage.toFixed(0)}% from bot
            </span>
          </div>
          <p className="text-3xl font-bold text-success">{formatCurrency(botAttributed)}</p>
          <p className="text-sm text-muted-foreground">Bot-Attributed Revenue</p>
        </div>

        {/* Total Transactions */}
        <div className="metric-card">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-lg bg-accent/10 flex items-center justify-center">
              <CreditCard className="w-5 h-5 text-accent" />
            </div>
          </div>
          <p className="text-3xl font-bold">{totalPurchases}</p>
          <p className="text-sm text-muted-foreground">Total Transactions</p>
        </div>

        {/* Average Order Value */}
        <div className="metric-card">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
              <ArrowUpRight className="w-5 h-5 text-primary" />
            </div>
          </div>
          <p className="text-3xl font-bold">{formatCurrency(avgOrderValue)}</p>
          <p className="text-sm text-muted-foreground">Avg Order Value</p>
        </div>
      </div>

      {/* Platform Breakdown */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="metric-card">
          <h3 className="font-semibold mb-4">Revenue by Platform</h3>
          <div className="space-y-4">
            {/* Stripe */}
            <div>
              <div className="flex justify-between mb-1">
                <span className="text-sm flex items-center gap-2">
                  <CreditCard className="w-4 h-4" /> Stripe
                </span>
                <span className="text-sm font-medium">{formatCurrency(stripeRevenue)}</span>
              </div>
              <Progress
                value={totalRevenue > 0 ? (stripeRevenue / totalRevenue) * 100 : 0}
                className="h-2"
              />
            </div>
            {/* Hotmart */}
            <div>
              <div className="flex justify-between mb-1">
                <span className="text-sm flex items-center gap-2">
                  <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
                  </svg>
                  Hotmart
                </span>
                <span className="text-sm font-medium">{formatCurrency(hotmartRevenue)}</span>
              </div>
              <Progress
                value={totalRevenue > 0 ? (hotmartRevenue / totalRevenue) * 100 : 0}
                className="h-2"
              />
            </div>
          </div>
        </div>

        {/* Bot Attribution */}
        <div className="metric-card">
          <h3 className="font-semibold mb-4">Bot Attribution</h3>
          <div className="flex items-center justify-center h-32">
            <div className="text-center">
              <div className="text-5xl font-bold text-success">{botPercentage.toFixed(1)}%</div>
              <p className="text-sm text-muted-foreground mt-2">
                of revenue attributed to AI conversations
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Recent Transactions */}
      <div className="metric-card">
        <h3 className="font-semibold mb-4">Recent Transactions</h3>
        {purchasesLoading ? (
          <div className="flex justify-center py-8">
            <Loader2 className="w-6 h-6 animate-spin text-primary" />
          </div>
        ) : purchases.length === 0 ? (
          <div className="text-center py-8">
            <CreditCard className="w-12 h-12 mx-auto mb-3 opacity-50 text-muted-foreground" />
            <p className="text-muted-foreground">No transactions yet</p>
            <p className="text-sm text-muted-foreground mt-2 mb-4">Record your first sale to track revenue</p>

            {showRecordForm ? (
              <div className="max-w-md mx-auto p-4 rounded-lg border bg-secondary/30 text-left">
                <div className="flex items-center justify-between mb-3">
                  <h4 className="font-medium">Record Purchase</h4>
                  <Button variant="ghost" size="sm" onClick={() => setShowRecordForm(false)}>
                    <X className="w-4 h-4" />
                  </Button>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <input
                    type="text"
                    placeholder="Product name"
                    value={newPurchase.product_name}
                    onChange={(e) => setNewPurchase(prev => ({ ...prev, product_name: e.target.value }))}
                    className="px-3 py-2 rounded border bg-background text-sm sm:col-span-2"
                  />
                  <input
                    type="number"
                    placeholder="Amount"
                    value={newPurchase.amount}
                    onChange={(e) => setNewPurchase(prev => ({ ...prev, amount: parseFloat(e.target.value) || 0 }))}
                    className="px-3 py-2 rounded border bg-background text-sm"
                  />
                  <select
                    value={newPurchase.currency}
                    onChange={(e) => setNewPurchase(prev => ({ ...prev, currency: e.target.value }))}
                    className="px-3 py-2 rounded border bg-background text-sm"
                  >
                    <option value="EUR">EUR</option>
                    <option value="USD">USD</option>
                  </select>
                  <select
                    value={newPurchase.platform}
                    onChange={(e) => setNewPurchase(prev => ({ ...prev, platform: e.target.value }))}
                    className="px-3 py-2 rounded border bg-background text-sm"
                  >
                    <option value="stripe">Stripe</option>
                    <option value="hotmart">Hotmart</option>
                    <option value="manual">Manual</option>
                  </select>
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={newPurchase.bot_attributed}
                      onChange={(e) => setNewPurchase(prev => ({ ...prev, bot_attributed: e.target.checked }))}
                      className="rounded"
                    />
                    Bot attributed
                  </label>
                </div>
                <div className="flex justify-end mt-3">
                  <Button onClick={handleRecordPurchase} disabled={recordPurchase.isPending}>
                    {recordPurchase.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
                    Record Purchase
                  </Button>
                </div>
              </div>
            ) : (
              <Button variant="outline" onClick={() => setShowRecordForm(true)}>
                <Plus className="w-4 h-4 mr-2" /> Record Purchase
              </Button>
            )}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b">
                  <th className="text-left py-2 text-sm font-medium text-muted-foreground">Date</th>
                  <th className="text-left py-2 text-sm font-medium text-muted-foreground">Product</th>
                  <th className="text-left py-2 text-sm font-medium text-muted-foreground">Platform</th>
                  <th className="text-left py-2 text-sm font-medium text-muted-foreground">Status</th>
                  <th className="text-right py-2 text-sm font-medium text-muted-foreground">Amount</th>
                  <th className="text-center py-2 text-sm font-medium text-muted-foreground">Bot</th>
                </tr>
              </thead>
              <tbody>
                {purchases.slice(0, 10).map((purchase) => (
                  <tr key={purchase.id} className="border-b last:border-0">
                    <td className="py-3 text-sm">{formatDate(purchase.created_at)}</td>
                    <td className="py-3 text-sm font-medium">{purchase.product_name}</td>
                    <td className="py-3">
                      <span className={cn(
                        "text-xs px-2 py-1 rounded-full",
                        purchase.platform === "stripe"
                          ? "bg-primary/10 text-primary"
                          : "bg-accent/10 text-accent"
                      )}>
                        {purchase.platform}
                      </span>
                    </td>
                    <td className="py-3">
                      <span className={cn(
                        "text-xs px-2 py-1 rounded-full",
                        purchase.status === "completed" && "bg-success/10 text-success",
                        purchase.status === "refunded" && "bg-destructive/10 text-destructive",
                        purchase.status === "pending" && "bg-yellow-500/10 text-yellow-600"
                      )}>
                        {purchase.status}
                      </span>
                    </td>
                    <td className="py-3 text-sm text-right font-medium">
                      {formatCurrency(purchase.amount, purchase.currency)}
                    </td>
                    <td className="py-3 text-center">
                      {purchase.bot_attributed ? (
                        <Bot className="w-4 h-4 text-success mx-auto" />
                      ) : (
                        <span className="text-muted-foreground">-</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
