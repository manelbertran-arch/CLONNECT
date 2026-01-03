import { useState } from "react";
import {
  ShoppingBag,
  Plus,
  DollarSign,
  Package,
  TrendingUp,
  ShoppingCart,
  BookOpen,
  GraduationCap,
  Users,
  FileText,
  Wrench,
  Box,
  Copy,
  Pencil,
  Trash2,
  ExternalLink,
  Loader2,
  Check
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { useProducts, useAddProduct, useUpdateProduct, useDeleteProduct, usePurchases } from "@/hooks/useApi";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import type { Product } from "@/types/api";

const PRODUCT_TYPES = [
  { value: "ebook", label: "Ebook / Guide", icon: BookOpen },
  { value: "course", label: "Course", icon: GraduationCap },
  { value: "membership", label: "Membership", icon: Users },
  { value: "template", label: "Template", icon: FileText },
  { value: "service", label: "Service", icon: Wrench },
  { value: "other", label: "Other", icon: Box },
];

function getTypeIcon(type: string) {
  const typeConfig = PRODUCT_TYPES.find(t => t.value === type);
  return typeConfig?.icon || Package;
}

function getTypeEmoji(type: string) {
  const emojis: Record<string, string> = {
    ebook: "📘",
    course: "🎓",
    membership: "👥",
    template: "📄",
    service: "🛠️",
    other: "📦",
  };
  return emojis[type] || "📦";
}

function formatPrice(price: number, currency: string = "EUR") {
  if (price === 0) return "Free";
  const symbols: Record<string, string> = { EUR: "€", USD: "$", MXN: "$" };
  return `${symbols[currency] || "€"}${price}`;
}

export default function Products() {
  const { toast } = useToast();
  const { data: productsData, isLoading, refetch } = useProducts();
  const { data: purchasesData, isLoading: purchasesLoading } = usePurchases();
  const addProductMutation = useAddProduct();
  const updateProductMutation = useUpdateProduct();
  const deleteProductMutation = useDeleteProduct();

  const [showAddModal, setShowAddModal] = useState(false);
  const [editingProduct, setEditingProduct] = useState<Product | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [formData, setFormData] = useState({
    name: "",
    description: "",
    type: "ebook",
    price: "",
    currency: "EUR",
    purchase_url: "",
    bot_enabled: true,
  });

  const products = productsData?.products || [];
  const purchases = purchasesData?.purchases || [];
  const recentSales = purchases.slice(0, 5); // Show last 5 sales

  // Calculate stats
  const totalRevenue = products.reduce((sum, p) => sum + (p.revenue || 0), 0);
  const totalSales = products.reduce((sum, p) => sum + (p.sales_count || 0), 0);
  const avgOrderValue = totalSales > 0 ? totalRevenue / totalSales : 0;

  const resetForm = () => {
    setFormData({
      name: "",
      description: "",
      type: "ebook",
      price: "",
      currency: "EUR",
      purchase_url: "",
      bot_enabled: true,
    });
    setEditingProduct(null);
  };

  const handleOpenAdd = () => {
    resetForm();
    setShowAddModal(true);
  };

  const handleOpenEdit = (product: Product) => {
    // Map backend field names to frontend form fields
    setFormData({
      name: product.name || "",
      description: product.description || "",
      type: product.type || "ebook",
      price: product.price != null ? String(product.price) : "",
      currency: product.currency || "EUR",
      purchase_url: product.purchase_url || product.payment_link || "",  // Backend uses payment_link
      bot_enabled: product.bot_enabled ?? product.is_active ?? true,     // Backend uses is_active
    });
    setEditingProduct(product);
    setShowAddModal(true);
  };

  const handleSubmit = async () => {
    if (!formData.name.trim()) {
      toast({ title: "Error", description: "Product name is required", variant: "destructive" });
      return;
    }

    // Validate price - accept any valid number >= 0
    const priceValue = parseFloat(formData.price);
    if (formData.price.trim() === "" || isNaN(priceValue) || priceValue < 0) {
      toast({ title: "Error", description: "Valid price is required", variant: "destructive" });
      return;
    }

    // Map frontend fields to backend field names
    const productData = {
      name: formData.name,
      description: formData.description,
      price: priceValue,
      currency: formData.currency,
      payment_link: formData.purchase_url,  // Backend uses payment_link
      is_active: formData.bot_enabled,       // Backend uses is_active
    };

    try {
      if (editingProduct) {
        await updateProductMutation.mutateAsync({ productId: editingProduct.id, product: productData });
        toast({ title: "Updated", description: "Product updated successfully" });
      } else {
        await addProductMutation.mutateAsync(productData);
        toast({ title: "Created", description: "Product created successfully" });
      }
      setShowAddModal(false);
      resetForm();
      refetch();
    } catch (error: any) {
      console.error("Save product error:", error);
      const message = error?.response?.data?.detail || error?.response?.data?.message || error?.message || "Failed to save product";
      toast({ title: "Error", description: String(message), variant: "destructive" });
    }
  };

  const handleDelete = async (productId: string, name: string) => {
    if (!confirm(`Delete "${name}"? This cannot be undone.`)) return;
    try {
      await deleteProductMutation.mutateAsync(productId);
      toast({ title: "Deleted", description: "Product deleted" });
      refetch();
    } catch (error: any) {
      console.error("Delete product error:", error);
      const message = error?.response?.data?.detail || error?.response?.data?.message || error?.message || "Failed to delete";
      toast({ title: "Error", description: String(message), variant: "destructive" });
    }
  };

  const handleCopyLink = async (product: Product) => {
    if (!product.purchase_url) {
      toast({ title: "No link", description: "This product has no purchase link", variant: "destructive" });
      return;
    }
    await navigator.clipboard.writeText(product.purchase_url);
    setCopiedId(product.id);
    toast({ title: "Copied!", description: "Link copied to clipboard" });
    setTimeout(() => setCopiedId(null), 2000);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight">Products</h1>
          <p className="text-muted-foreground text-sm">Manage your digital products and track sales</p>
        </div>
        <Button onClick={handleOpenAdd} className="w-full sm:w-auto">
          <Plus className="w-4 h-4 mr-2" />
          Add Product
        </Button>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="metric-card">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-lg bg-success/10 flex items-center justify-center">
              <DollarSign className="w-5 h-5 text-success" />
            </div>
          </div>
          <p className="text-3xl font-bold text-success">€{totalRevenue.toFixed(0)}</p>
          <p className="text-sm text-muted-foreground">Revenue (30d)</p>
        </div>

        <div className="metric-card">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
              <ShoppingCart className="w-5 h-5 text-primary" />
            </div>
          </div>
          <p className="text-3xl font-bold">{totalSales}</p>
          <p className="text-sm text-muted-foreground">Sales</p>
        </div>

        <div className="metric-card">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-lg bg-accent/10 flex items-center justify-center">
              <Package className="w-5 h-5 text-accent" />
            </div>
          </div>
          <p className="text-3xl font-bold">{products.length}</p>
          <p className="text-sm text-muted-foreground">Products</p>
        </div>

        <div className="metric-card">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-lg bg-purple-500/10 flex items-center justify-center">
              <TrendingUp className="w-5 h-5 text-purple-500" />
            </div>
          </div>
          <p className="text-3xl font-bold">€{avgOrderValue.toFixed(0)}</p>
          <p className="text-sm text-muted-foreground">Avg Order</p>
        </div>
      </div>

      {/* Products List */}
      <div className="metric-card">
        <h3 className="font-semibold mb-4">Your Products</h3>

        {isLoading ? (
          <div className="flex justify-center py-8">
            <Loader2 className="w-6 h-6 animate-spin text-primary" />
          </div>
        ) : products.length === 0 ? (
          <div className="text-center py-12">
            <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center mx-auto mb-4">
              <ShoppingBag className="w-8 h-8 text-primary" />
            </div>
            <h4 className="text-lg font-semibold mb-2">No products yet</h4>
            <p className="text-muted-foreground text-sm max-w-sm mx-auto mb-4">
              Add your digital products to start tracking sales and let your bot recommend them
            </p>
            <Button onClick={handleOpenAdd}>
              <Plus className="w-4 h-4 mr-2" />
              Add Your First Product
            </Button>
          </div>
        ) : (
          <div className="space-y-3">
            {products.map((product) => {
              const TypeIcon = getTypeIcon(product.type || "other");
              return (
                <div
                  key={product.id}
                  className="p-4 rounded-lg border bg-card hover:bg-accent/5 transition-colors"
                >
                  <div className="flex justify-between items-start gap-4">
                    <div className="flex gap-4 flex-1 min-w-0">
                      {/* Icon */}
                      <div className="w-12 h-12 rounded-lg bg-purple-500/20 flex items-center justify-center flex-shrink-0">
                        <TypeIcon className="w-6 h-6 text-purple-400" />
                      </div>

                      {/* Info */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <h4 className="font-semibold">{product.name}</h4>
                          <span className={cn(
                            "text-xs px-2 py-0.5 rounded-full font-medium",
                            product.is_active !== false
                              ? "bg-success/10 text-success"
                              : "bg-orange-500/10 text-orange-500"
                          )}>
                            {product.is_active !== false ? "Activo" : "Pausado"}
                          </span>
                        </div>
                        <p className="text-sm text-muted-foreground">
                          {getTypeEmoji(product.type || "other")} {product.type || "other"} • {formatPrice(product.price || 0, product.currency)}
                        </p>
                        {product.description && (
                          <p className="text-sm text-muted-foreground mt-1 line-clamp-1">
                            {product.description}
                          </p>
                        )}
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-1 flex-shrink-0">
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => handleCopyLink(product)}
                        disabled={!product.purchase_url}
                        title="Copy link"
                      >
                        {copiedId === product.id ? (
                          <Check className="w-4 h-4 text-success" />
                        ) : (
                          <Copy className="w-4 h-4" />
                        )}
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => handleOpenEdit(product)}
                        title="Edit"
                      >
                        <Pencil className="w-4 h-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="text-destructive hover:text-destructive"
                        onClick={() => handleDelete(product.id, product.name)}
                        title="Delete"
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>

                  {/* Stats */}
                  <div className="mt-4 pt-4 border-t flex gap-6 flex-wrap text-sm">
                    <div>
                      <span className="text-muted-foreground">Sales:</span>
                      <span className="ml-2 font-medium">{product.sales_count || 0}</span>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Revenue:</span>
                      <span className="ml-2 font-medium text-success">€{product.revenue || 0}</span>
                    </div>
                    {product.purchase_url && (
                      <div>
                        <a
                          href={product.purchase_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-primary hover:underline flex items-center gap-1"
                        >
                          View link <ExternalLink className="w-3 h-3" />
                        </a>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Recent Sales */}
      {recentSales.length > 0 && (
        <div className="metric-card">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold">Recent Sales</h3>
          </div>

          {purchasesLoading ? (
            <div className="flex justify-center py-4">
              <Loader2 className="w-5 h-5 animate-spin text-primary" />
            </div>
          ) : (
            <div className="space-y-3">
              {recentSales.map((sale) => (
                <div
                  key={sale.id}
                  className="flex items-center justify-between p-3 rounded-lg bg-secondary/30"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-success/10 flex items-center justify-center">
                      <DollarSign className="w-5 h-5 text-success" />
                    </div>
                    <div>
                      <p className="font-medium text-sm">{sale.product_name}</p>
                      <p className="text-xs text-muted-foreground">
                        {new Date(sale.created_at).toLocaleDateString("es-ES", {
                          day: "numeric",
                          month: "short",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                        {" "}via {sale.platform}
                      </p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="font-semibold text-success">
                      {formatPrice(sale.amount, sale.currency)}
                    </p>
                    {sale.bot_attributed && (
                      <span className="text-xs text-muted-foreground">via bot</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Add/Edit Modal */}
      <Dialog open={showAddModal} onOpenChange={setShowAddModal}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{editingProduct ? "Edit Product" : "Add Product"}</DialogTitle>
          </DialogHeader>

          <div className="space-y-4">
            {/* Name */}
            <div>
              <Label>Product name *</Label>
              <Input
                placeholder="e.g. Instagram Growth Guide"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              />
            </div>

            {/* Description */}
            <div>
              <Label>Short description</Label>
              <Input
                placeholder="What will they learn/get?"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              />
            </div>

            {/* Type */}
            <div>
              <Label>Type</Label>
              <Select value={formData.type} onValueChange={(v) => setFormData({ ...formData, type: v })}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PRODUCT_TYPES.map((type) => (
                    <SelectItem key={type.value} value={type.value}>
                      {getTypeEmoji(type.value)} {type.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Price */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Price *</Label>
                <Input
                  type="number"
                  min="0"
                  step="0.01"
                  placeholder="29.00"
                  value={formData.price}
                  onChange={(e) => setFormData({ ...formData, price: e.target.value })}
                />
              </div>
              <div>
                <Label>Currency</Label>
                <Select value={formData.currency} onValueChange={(v) => setFormData({ ...formData, currency: v })}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="EUR">€ EUR</SelectItem>
                    <SelectItem value="USD">$ USD</SelectItem>
                    <SelectItem value="MXN">$ MXN</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Purchase URL */}
            <div>
              <Label>Purchase link</Label>
              <Input
                placeholder="https://gumroad.com/l/..."
                value={formData.purchase_url}
                onChange={(e) => setFormData({ ...formData, purchase_url: e.target.value })}
              />
              <p className="text-xs text-muted-foreground mt-1">
                Where customers can buy (Gumroad, Hotmart, your website, etc.)
              </p>
            </div>

            {/* Bot option */}
            <div className="flex items-center justify-between p-3 bg-secondary rounded-lg">
              <div>
                <p className="font-medium text-sm">Mostrar en conversaciones</p>
                <p className="text-xs text-muted-foreground">Si se agotan las existencias o necesitas pausar las ventas, desactívalo temporalmente</p>
              </div>
              <Switch
                checked={formData.bot_enabled}
                onCheckedChange={(v) => setFormData({ ...formData, bot_enabled: v })}
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAddModal(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={addProductMutation.isPending || updateProductMutation.isPending}
            >
              {(addProductMutation.isPending || updateProductMutation.isPending) && (
                <Loader2 className="w-4 h-4 animate-spin mr-2" />
              )}
              {editingProduct ? "Update" : "Create"} Product
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
