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
  { value: "ebook", label: "Ebook / Guía", icon: BookOpen },
  { value: "course", label: "Curso", icon: GraduationCap },
  { value: "membership", label: "Membresía", icon: Users },
  { value: "template", label: "Plantilla", icon: FileText },
  { value: "service", label: "Servicio", icon: Wrench },
  { value: "other", label: "Otro", icon: Box },
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
  if (price === 0) return "Gratis";
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
      toast({ title: "Error", description: "El nombre del producto es obligatorio", variant: "destructive" });
      return;
    }

    // Validate price - accept any valid number >= 0
    const priceValue = parseFloat(formData.price);
    if (formData.price.trim() === "" || isNaN(priceValue) || priceValue < 0) {
      toast({ title: "Error", description: "Se requiere un precio válido", variant: "destructive" });
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
        toast({ title: "Actualizado", description: "Producto actualizado correctamente" });
      } else {
        await addProductMutation.mutateAsync(productData);
        toast({ title: "Creado", description: "Producto creado correctamente" });
      }
      setShowAddModal(false);
      resetForm();
      refetch();
    } catch (error: any) {
      console.error("Save product error:", error);
      const message = error?.response?.data?.detail || error?.response?.data?.message || error?.message || "Error al guardar producto";
      toast({ title: "Error", description: String(message), variant: "destructive" });
    }
  };

  const handleDelete = async (productId: string, name: string) => {
    if (!confirm(`¿Eliminar "${name}"? Esta acción no se puede deshacer.`)) return;
    try {
      await deleteProductMutation.mutateAsync(productId);
      toast({ title: "Eliminado", description: "Producto eliminado" });
      refetch();
    } catch (error: any) {
      console.error("Delete product error:", error);
      const message = error?.response?.data?.detail || error?.response?.data?.message || error?.message || "Error al eliminar";
      toast({ title: "Error", description: String(message), variant: "destructive" });
    }
  };

  const handleCopyLink = async (product: Product) => {
    if (!product.purchase_url) {
      toast({ title: "Sin enlace", description: "Este producto no tiene enlace de compra", variant: "destructive" });
      return;
    }
    try {
      await navigator.clipboard.writeText(product.purchase_url);
      setCopiedId(product.id);
      toast({ title: "Copiado", description: "Enlace copiado al portapapeles" });
      setTimeout(() => setCopiedId(null), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
      toast({ title: "Error", description: "No se pudo copiar al portapapeles", variant: "destructive" });
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Productos</h1>
          <p className="text-sm text-muted-foreground">Tus productos digitales</p>
        </div>
        <Button onClick={handleOpenAdd} size="sm" className="h-9 px-4">
          <Plus className="w-4 h-4 mr-2" />
          Nuevo
        </Button>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-5 rounded-2xl bg-gradient-to-br from-emerald-500/10 via-emerald-500/5 to-transparent border border-emerald-500/20">
          <div className="flex items-center gap-2 mb-2">
            <DollarSign className="w-4 h-4 text-emerald-500" />
            <span className="text-xs font-medium text-emerald-500/80 uppercase tracking-wide">Ingresos</span>
          </div>
          <p className="text-2xl font-semibold">€{totalRevenue.toFixed(0)}</p>
        </div>

        <div className="p-5 rounded-2xl bg-card border border-border/50">
          <div className="flex items-center gap-2 mb-2">
            <ShoppingCart className="w-4 h-4 text-muted-foreground" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Ventas</span>
          </div>
          <p className="text-2xl font-semibold">{totalSales}</p>
        </div>

        <div className="p-5 rounded-2xl bg-card border border-border/50">
          <div className="flex items-center gap-2 mb-2">
            <Package className="w-4 h-4 text-muted-foreground" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Productos</span>
          </div>
          <p className="text-2xl font-semibold">{products.length}</p>
        </div>

        <div className="p-5 rounded-2xl bg-card border border-border/50">
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp className="w-4 h-4 text-muted-foreground" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Ticket Medio</span>
          </div>
          <p className="text-2xl font-semibold">€{avgOrderValue.toFixed(0)}</p>
        </div>
      </div>

      {/* Products List */}
      <div className="p-5 rounded-2xl bg-card border border-border/50">
        <h3 className="text-sm font-medium mb-4">Catálogo</h3>

        {isLoading ? (
          <div className="space-y-2 animate-pulse">
            {[1, 2, 3].map(i => (
              <div key={i} className="flex items-center gap-4 p-4 rounded-xl border border-border/30">
                <div className="w-10 h-10 rounded-lg bg-muted/40" />
                <div className="flex-1">
                  <div className="h-4 w-40 bg-muted/40 rounded mb-2" />
                  <div className="h-3 w-24 bg-muted/30 rounded" />
                </div>
                <div className="h-4 w-12 bg-muted/30 rounded" />
              </div>
            ))}
          </div>
        ) : products.length === 0 ? (
          <div className="text-center py-12">
            <div className="w-12 h-12 rounded-full bg-muted/50 flex items-center justify-center mx-auto mb-4">
              <ShoppingBag className="w-6 h-6 text-muted-foreground" />
            </div>
            <p className="text-sm text-muted-foreground mb-4">
              Aún no hay productos
            </p>
            <Button onClick={handleOpenAdd} size="sm" variant="outline">
              <Plus className="w-4 h-4 mr-2" />
              Añadir producto
            </Button>
          </div>
        ) : (
          <div className="space-y-2">
            {products.map((product) => {
              const TypeIcon = getTypeIcon(product.type || "other");
              return (
                <div
                  key={product.id}
                  className="group p-4 rounded-xl border border-border/30 bg-card hover:border-border transition-colors"
                >
                  <div className="flex items-center gap-4">
                    {/* Icon */}
                    <div className="w-10 h-10 rounded-lg bg-muted/50 flex items-center justify-center shrink-0">
                      <TypeIcon className="w-5 h-5 text-muted-foreground" />
                    </div>

                    {/* Info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <h4 className="font-medium text-sm">{product.name}</h4>
                        <span className={cn(
                          "text-[10px] px-1.5 py-0.5 rounded font-medium",
                          product.is_active !== false
                            ? "bg-emerald-500/10 text-emerald-500"
                            : "bg-amber-500/10 text-amber-500"
                        )}>
                          {product.is_active !== false ? "Activo" : "Pausado"}
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {formatPrice(product.price || 0, product.currency)} · {product.sales_count || 0} ventas
                      </p>
                    </div>

                    {/* Revenue */}
                    <div className="text-right shrink-0">
                      <p className="text-sm font-medium text-emerald-500">€{product.revenue || 0}</p>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                      <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => handleCopyLink(product)} disabled={!product.purchase_url}>
                        {copiedId === product.id ? <Check className="w-4 h-4 text-emerald-500" /> : <Copy className="w-4 h-4" />}
                      </Button>
                      <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => handleOpenEdit(product)}>
                        <Pencil className="w-4 h-4" />
                      </Button>
                      <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive hover:text-destructive" onClick={() => handleDelete(product.id, product.name)}>
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
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
            <h3 className="font-semibold">Ventas Recientes</h3>
          </div>

          {purchasesLoading ? (
            <div className="space-y-3 animate-pulse">
              {[1, 2, 3].map(i => (
                <div key={i} className="flex items-center justify-between p-3 rounded-lg bg-muted/20">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-muted/40" />
                    <div>
                      <div className="h-4 w-28 bg-muted/40 rounded mb-1" />
                      <div className="h-3 w-20 bg-muted/30 rounded" />
                    </div>
                  </div>
                  <div className="h-4 w-12 bg-muted/30 rounded" />
                </div>
              ))}
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
            <DialogTitle>{editingProduct ? "Editar Producto" : "Añadir Producto"}</DialogTitle>
          </DialogHeader>

          <div className="space-y-4">
            {/* Name */}
            <div>
              <Label>Nombre del producto *</Label>
              <Input
                placeholder="Ej: Guía de Crecimiento Instagram"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              />
            </div>

            {/* Description */}
            <div>
              <Label>Descripción corta</Label>
              <Input
                placeholder="¿Qué aprenderán/obtendrán?"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              />
            </div>

            {/* Type */}
            <div>
              <Label>Tipo</Label>
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
                <Label>Precio *</Label>
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
                <Label>Moneda</Label>
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
              <Label>Enlace de compra</Label>
              <Input
                placeholder="https://gumroad.com/l/..."
                value={formData.purchase_url}
                onChange={(e) => setFormData({ ...formData, purchase_url: e.target.value })}
              />
              <p className="text-xs text-muted-foreground mt-1">
                Donde pueden comprar (Gumroad, Hotmart, tu web, etc.)
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
              Cancelar
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={addProductMutation.isPending || updateProductMutation.isPending}
            >
              {(addProductMutation.isPending || updateProductMutation.isPending) && (
                <Loader2 className="w-4 h-4 animate-spin mr-2" />
              )}
              {editingProduct ? "Actualizar" : "Crear"} Producto
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
