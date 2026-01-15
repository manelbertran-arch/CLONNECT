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
  Loader2,
  Check,
  Sparkles
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
  const recentSales = purchases.slice(0, 5);

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
    setFormData({
      name: product.name || "",
      description: product.description || "",
      type: product.type || "ebook",
      price: product.price != null ? String(product.price) : "",
      currency: product.currency || "EUR",
      purchase_url: product.purchase_url || product.payment_link || "",
      bot_enabled: product.bot_enabled ?? product.is_active ?? true,
    });
    setEditingProduct(product);
    setShowAddModal(true);
  };

  const handleSubmit = async () => {
    if (!formData.name.trim()) {
      toast({ title: "Error", description: "El nombre del producto es obligatorio", variant: "destructive" });
      return;
    }

    const priceValue = parseFloat(formData.price);
    if (formData.price.trim() === "" || isNaN(priceValue) || priceValue < 0) {
      toast({ title: "Error", description: "Se requiere un precio válido", variant: "destructive" });
      return;
    }

    const productData = {
      name: formData.name,
      description: formData.description,
      price: priceValue,
      currency: formData.currency,
      payment_link: formData.purchase_url,
      is_active: formData.bot_enabled,
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
      const message = error?.response?.data?.detail || error?.message || "Error al guardar producto";
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
      const message = error?.response?.data?.detail || error?.message || "Error al eliminar";
      toast({ title: "Error", description: String(message), variant: "destructive" });
    }
  };

  const handleCopyLink = async (product: Product) => {
    if (!product.purchase_url) {
      toast({ title: "Sin enlace", description: "Este producto no tiene enlace de compra", variant: "destructive" });
      return;
    }
    await navigator.clipboard.writeText(product.purchase_url);
    setCopiedId(product.id);
    toast({ title: "¡Copiado!", description: "Enlace copiado al portapapeles" });
    setTimeout(() => setCopiedId(null), 2000);
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

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Productos</h1>
          <p className="text-sm text-muted-foreground/80 mt-0.5">Tus productos digitales</p>
        </div>
        <Button onClick={handleOpenAdd} size="sm" className="h-10 px-5 gap-2 shadow-lg shadow-primary/20">
          <Plus className="w-4 h-4" />
          Nuevo
        </Button>
      </div>

      {/* Hero Revenue Card */}
      <div className="relative group">
        <div className="absolute -inset-0.5 bg-gradient-to-r from-emerald-500 via-cyan-500 to-emerald-500 rounded-3xl blur-lg opacity-25 group-hover:opacity-35 transition-opacity duration-500" />
        <div className="relative p-6 rounded-2xl bg-gradient-to-br from-emerald-500/20 via-emerald-500/10 to-cyan-500/10 border border-emerald-500/30 backdrop-blur-xl overflow-hidden">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_20%,rgba(16,185,129,0.15),transparent_50%)]" />
          <div className="relative flex items-center justify-between">
            <div>
              <div className="flex items-center gap-2 mb-2">
                <DollarSign className="w-5 h-5 text-emerald-400" />
                <span className="text-sm font-semibold text-emerald-400/90 uppercase tracking-wider">Ingresos Totales</span>
              </div>
              <span className="text-4xl font-bold text-white">€{totalRevenue.toFixed(0)}</span>
            </div>
            <div className="hidden sm:flex items-center gap-6">
              <div className="text-center">
                <p className="text-2xl font-bold">{totalSales}</p>
                <p className="text-xs text-muted-foreground uppercase tracking-wide">Ventas</p>
              </div>
              <div className="text-center">
                <p className="text-2xl font-bold">€{avgOrderValue.toFixed(0)}</p>
                <p className="text-xs text-muted-foreground uppercase tracking-wide">Ticket Medio</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-3 gap-3">
        <div className="p-4 rounded-xl bg-gradient-to-br from-violet-500/10 to-purple-500/5 border border-violet-500/20 backdrop-blur-sm">
          <div className="flex items-center gap-2 mb-1">
            <ShoppingCart className="w-4 h-4 text-violet-400" />
            <span className="text-xs font-medium text-violet-400/80 uppercase tracking-wider">Ventas</span>
          </div>
          <span className="text-2xl font-bold">{totalSales}</span>
        </div>

        <div className="p-4 rounded-xl bg-gradient-to-br from-blue-500/10 to-cyan-500/5 border border-blue-500/20 backdrop-blur-sm">
          <div className="flex items-center gap-2 mb-1">
            <Package className="w-4 h-4 text-blue-400" />
            <span className="text-xs font-medium text-blue-400/80 uppercase tracking-wider">Productos</span>
          </div>
          <span className="text-2xl font-bold">{products.length}</span>
        </div>

        <div className="p-4 rounded-xl bg-gradient-to-br from-amber-500/10 to-orange-500/5 border border-amber-500/20 backdrop-blur-sm">
          <div className="flex items-center gap-2 mb-1">
            <TrendingUp className="w-4 h-4 text-amber-400" />
            <span className="text-xs font-medium text-amber-400/80 uppercase tracking-wider">Ticket</span>
          </div>
          <span className="text-2xl font-bold">€{avgOrderValue.toFixed(0)}</span>
        </div>
      </div>

      {/* Products List */}
      <div className="p-5 sm:p-6 rounded-2xl bg-card/50 border border-white/[0.08] backdrop-blur-sm">
        <div className="flex items-center gap-2 mb-5">
          <Sparkles className="w-4 h-4 text-primary" />
          <h3 className="font-semibold">Catálogo</h3>
          <span className="text-xs text-muted-foreground bg-muted/30 px-2 py-0.5 rounded-full ml-auto">{products.length} productos</span>
        </div>

        {products.length === 0 ? (
          <div className="text-center py-12">
            <div className="w-14 h-14 rounded-2xl bg-muted/20 flex items-center justify-center mx-auto mb-4 border border-white/[0.05]">
              <ShoppingBag className="w-7 h-7 text-muted-foreground/50" />
            </div>
            <p className="text-sm text-muted-foreground mb-1">Aún no hay productos</p>
            <p className="text-xs text-muted-foreground/60 mb-4">Crea tu primer producto digital</p>
            <Button onClick={handleOpenAdd} size="sm" variant="outline" className="gap-2">
              <Plus className="w-4 h-4" />
              Añadir producto
            </Button>
          </div>
        ) : (
          <div className="space-y-2">
            {products.map((product, idx) => {
              const TypeIcon = getTypeIcon(product.type || "other");
              return (
                <div
                  key={product.id}
                  className="group p-4 rounded-xl bg-card/80 border border-white/[0.06] hover:border-white/[0.12] hover:bg-card transition-all duration-200 hover:scale-[1.01]"
                  style={{ animationDelay: `${idx * 30}ms` }}
                >
                  <div className="flex items-center gap-4">
                    {/* Icon */}
                    <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-primary/20 to-accent/20 flex items-center justify-center shrink-0 border border-white/[0.08]">
                      <TypeIcon className="w-5 h-5 text-primary" />
                    </div>

                    {/* Info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <h4 className="font-semibold text-sm">{product.name}</h4>
                        <span className={cn(
                          "text-[10px] px-2 py-0.5 rounded-full font-medium",
                          product.is_active !== false
                            ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/20"
                            : "bg-amber-500/15 text-amber-400 border border-amber-500/20"
                        )}>
                          {product.is_active !== false ? "Activo" : "Pausado"}
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground/70 mt-0.5">
                        {formatPrice(product.price || 0, product.currency)} · {product.sales_count || 0} ventas
                      </p>
                    </div>

                    {/* Revenue */}
                    <div className="text-right shrink-0">
                      <p className="text-sm font-bold text-emerald-400">€{product.revenue || 0}</p>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                      <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => handleCopyLink(product)} disabled={!product.purchase_url}>
                        {copiedId === product.id ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
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
        <div className="p-5 sm:p-6 rounded-2xl bg-card/50 border border-white/[0.08] backdrop-blur-sm">
          <div className="flex items-center gap-2 mb-5">
            <TrendingUp className="w-4 h-4 text-emerald-400" />
            <h3 className="font-semibold">Ventas Recientes</h3>
          </div>

          {purchasesLoading ? (
            <div className="flex justify-center py-4">
              <Loader2 className="w-5 h-5 animate-spin text-primary" />
            </div>
          ) : (
            <div className="space-y-2">
              {recentSales.map((sale, idx) => (
                <div
                  key={sale.id}
                  className="flex items-center justify-between p-3 rounded-xl bg-gradient-to-r from-emerald-500/5 to-cyan-500/5 border border-emerald-500/10"
                  style={{ animationDelay: `${idx * 30}ms` }}
                >
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-emerald-500/15 flex items-center justify-center border border-emerald-500/20">
                      <DollarSign className="w-4 h-4 text-emerald-400" />
                    </div>
                    <div>
                      <p className="font-medium text-sm">{sale.product_name}</p>
                      <p className="text-xs text-muted-foreground/70">
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
                    <p className="font-bold text-emerald-400">{formatPrice(sale.amount, sale.currency)}</p>
                    {sale.bot_attributed && (
                      <span className="text-[10px] text-muted-foreground bg-muted/30 px-1.5 py-0.5 rounded">via bot</span>
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
            <div>
              <Label>Nombre del producto *</Label>
              <Input
                placeholder="Ej: Guía de Crecimiento Instagram"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              />
            </div>

            <div>
              <Label>Descripción corta</Label>
              <Input
                placeholder="¿Qué aprenderán/obtendrán?"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              />
            </div>

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

            <div className="flex items-center justify-between p-3 bg-muted/20 rounded-xl border border-white/[0.05]">
              <div>
                <p className="font-medium text-sm">Mostrar en conversaciones</p>
                <p className="text-xs text-muted-foreground">Desactívalo para pausar ventas temporalmente</p>
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
