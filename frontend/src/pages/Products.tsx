import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Plus,
  BookOpen,
  GraduationCap,
  Users,
  Key,
  FileText,
  Package,
  Pencil,
  Trash2,
  Copy,
  ExternalLink,
  MoreVertical,
  Check,
  Loader2,
  Bot,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/hooks/use-toast";
import { Product } from "@/types/api";

const API_URL = import.meta.env.VITE_API_URL || "https://web-production-9f69.up.railway.app";
const CREATOR_ID = import.meta.env.VITE_CREATOR_ID || "manel";

// Product types with emojis
const PRODUCT_TYPES = {
  ebook: { label: "Ebook/Guia", emoji: "📘", icon: BookOpen },
  course: { label: "Curso", emoji: "🎓", icon: GraduationCap },
  mentorship: { label: "Mentoria", emoji: "👥", icon: Users },
  membership: { label: "Membresia", emoji: "🔑", icon: Key },
  template: { label: "Plantilla", emoji: "📄", icon: FileText },
  other: { label: "Otro", emoji: "📦", icon: Package },
};

type ProductType = keyof typeof PRODUCT_TYPES;

// API functions
async function getProducts(): Promise<{ products: Product[]; count: number }> {
  const res = await fetch(`${API_URL}/products/${CREATOR_ID}`);
  if (!res.ok) throw new Error("Failed to fetch products");
  return res.json();
}

async function createProduct(data: Partial<Product>): Promise<{ product: Product }> {
  const res = await fetch(`${API_URL}/products/${CREATOR_ID}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to create product");
  return res.json();
}

async function updateProduct(productId: string, data: Partial<Product>): Promise<void> {
  const res = await fetch(`${API_URL}/products/${CREATOR_ID}/${productId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to update product");
}

async function deleteProduct(productId: string): Promise<void> {
  const res = await fetch(`${API_URL}/products/${CREATOR_ID}/${productId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Failed to delete product");
}

export default function Products() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingProduct, setEditingProduct] = useState<Product | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Fetch products
  const { data, isLoading } = useQuery({
    queryKey: ["products", CREATOR_ID],
    queryFn: getProducts,
  });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: deleteProduct,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["products"] });
      toast({ title: "Producto eliminado" });
    },
    onError: () => {
      toast({ title: "Error al eliminar", variant: "destructive" });
    },
  });

  const products = data?.products || [];

  // Calculate stats
  const totalRevenue = products.reduce((sum, p) => sum + (p.revenue || 0), 0);
  const totalSales = products.reduce((sum, p) => sum + (p.sales_count || 0), 0);
  const activeProducts = products.filter((p) => p.is_active !== false).length;

  const copyLink = (product: Product) => {
    if (product.purchase_url) {
      navigator.clipboard.writeText(product.purchase_url);
      setCopiedId(product.id);
      setTimeout(() => setCopiedId(null), 2000);
      toast({ title: "Link copiado" });
    }
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold">Products</h1>
          <p className="text-gray-400">Tu bot puede recomendar estos productos</p>
        </div>
        <Button onClick={() => setShowAddModal(true)}>
          <Plus className="w-4 h-4 mr-2" />
          Anadir Producto
        </Button>
      </div>

      {/* Quick stats */}
      <div className="grid grid-cols-4 gap-4">
        <div className="bg-gray-800 rounded-lg p-4">
          <p className="text-gray-400 text-sm">Productos</p>
          <p className="text-2xl font-bold">{products.length}</p>
        </div>
        <div className="bg-gray-800 rounded-lg p-4">
          <p className="text-gray-400 text-sm">Activos</p>
          <p className="text-2xl font-bold text-green-400">{activeProducts}</p>
        </div>
        <div className="bg-gray-800 rounded-lg p-4">
          <p className="text-gray-400 text-sm">Ventas totales</p>
          <p className="text-2xl font-bold">{totalSales}</p>
        </div>
        <div className="bg-gray-800 rounded-lg p-4">
          <p className="text-gray-400 text-sm">Revenue</p>
          <p className="text-2xl font-bold text-green-400">
            €{totalRevenue.toLocaleString()}
          </p>
        </div>
      </div>

      {/* Products list */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
        </div>
      ) : products.length === 0 ? (
        <EmptyState onAdd={() => setShowAddModal(true)} />
      ) : (
        <div className="space-y-3">
          {products.map((product) => (
            <ProductCard
              key={product.id}
              product={product}
              onEdit={() => setEditingProduct(product)}
              onDelete={() => deleteMutation.mutate(product.id)}
              onCopy={() => copyLink(product)}
              copied={copiedId === product.id}
            />
          ))}
        </div>
      )}

      {/* Add/Edit Modal */}
      <ProductModal
        open={showAddModal || !!editingProduct}
        onClose={() => {
          setShowAddModal(false);
          setEditingProduct(null);
        }}
        product={editingProduct}
      />
    </div>
  );
}

// Product card
function ProductCard({
  product,
  onEdit,
  onDelete,
  onCopy,
  copied,
}: {
  product: Product;
  onEdit: () => void;
  onDelete: () => void;
  onCopy: () => void;
  copied: boolean;
}) {
  const typeConfig = PRODUCT_TYPES[(product.type as ProductType) || "other"] || PRODUCT_TYPES.other;

  return (
    <div className="bg-gray-800 rounded-lg border border-gray-700 p-4 hover:border-gray-600 transition-colors">
      <div className="flex gap-4">
        {/* Image or icon */}
        <div className="w-16 h-16 rounded-lg bg-purple-500/20 flex items-center justify-center flex-shrink-0">
          {product.image_url ? (
            <img
              src={product.image_url}
              alt=""
              className="w-full h-full object-cover rounded-lg"
            />
          ) : (
            <span className="text-2xl">{typeConfig.emoji}</span>
          )}
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <div>
              <h3 className="font-semibold text-white truncate">{product.name}</h3>
              <p className="text-sm text-gray-400">{typeConfig.label}</p>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <span className="font-bold text-lg">
                {product.price === 0 ? "Gratis" : `€${product.price}`}
              </span>
              <Badge variant={product.is_active !== false ? "default" : "secondary"}>
                {product.is_active !== false ? "Activo" : "Inactivo"}
              </Badge>
            </div>
          </div>

          {product.tagline && (
            <p className="text-sm text-gray-500 mt-1 truncate">{product.tagline}</p>
          )}

          {/* Stats and actions */}
          <div className="flex items-center justify-between mt-3">
            <div className="flex items-center gap-4 text-sm">
              <span className="text-gray-400">
                📊 {product.sales_count || 0} ventas
              </span>
              <span className="text-green-400">
                €{(product.revenue || 0).toLocaleString()}
              </span>
              {product.bot_enabled !== false && (
                <span className="text-purple-400 flex items-center gap-1">
                  <Bot className="w-3 h-3" /> Bot activo
                </span>
              )}
            </div>

            <div className="flex items-center gap-1">
              {product.purchase_url && (
                <>
                  <Button variant="ghost" size="sm" onClick={onCopy}>
                    {copied ? (
                      <Check className="w-4 h-4 text-green-400" />
                    ) : (
                      <Copy className="w-4 h-4" />
                    )}
                  </Button>
                  <Button variant="ghost" size="sm" asChild>
                    <a href={product.purchase_url} target="_blank" rel="noopener noreferrer">
                      <ExternalLink className="w-4 h-4" />
                    </a>
                  </Button>
                </>
              )}

              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="sm">
                    <MoreVertical className="w-4 h-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={onEdit}>
                    <Pencil className="w-4 h-4 mr-2" /> Editar
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={onDelete} className="text-red-400">
                    <Trash2 className="w-4 h-4 mr-2" /> Eliminar
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// Empty state
function EmptyState({ onAdd }: { onAdd: () => void }) {
  return (
    <div className="text-center py-12 bg-gray-800/50 rounded-lg border border-dashed border-gray-700">
      <Package className="w-12 h-12 mx-auto text-gray-500 mb-4" />
      <h3 className="text-lg font-medium mb-2">No tienes productos</h3>
      <p className="text-gray-400 mb-4">
        Anade tu primer producto para que el bot pueda recomendarlo
      </p>
      <Button onClick={onAdd}>
        <Plus className="w-4 h-4 mr-2" />
        Anadir Producto
      </Button>
    </div>
  );
}

// Create/Edit product modal
function ProductModal({
  open,
  onClose,
  product,
}: {
  open: boolean;
  onClose: () => void;
  product: Product | null;
}) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const isEditing = !!product;

  const [formData, setFormData] = useState({
    name: "",
    price: "",
    type: "ebook" as ProductType,
    tagline: "",
    purchase_url: "",
    bot_enabled: true,
  });

  // Load data when editing
  useEffect(() => {
    if (product) {
      setFormData({
        name: product.name || "",
        price: product.price?.toString() || "",
        type: (product.type as ProductType) || "ebook",
        tagline: product.tagline || "",
        purchase_url: product.purchase_url || "",
        bot_enabled: product.bot_enabled !== false,
      });
    } else {
      setFormData({
        name: "",
        price: "",
        type: "ebook",
        tagline: "",
        purchase_url: "",
        bot_enabled: true,
      });
    }
  }, [product, open]);

  const createMutation = useMutation({
    mutationFn: createProduct,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["products"] });
      toast({ title: "Producto creado" });
      onClose();
    },
    onError: () => {
      toast({ title: "Error al crear producto", variant: "destructive" });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<Product> }) =>
      updateProduct(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["products"] });
      toast({ title: "Producto actualizado" });
      onClose();
    },
    onError: () => {
      toast({ title: "Error al actualizar producto", variant: "destructive" });
    },
  });

  const handleSubmit = () => {
    const data = {
      name: formData.name,
      price: parseFloat(formData.price) || 0,
      type: formData.type,
      tagline: formData.tagline,
      purchase_url: formData.purchase_url,
      bot_enabled: formData.bot_enabled,
    };

    if (isEditing && product) {
      updateMutation.mutate({ id: product.id, data });
    } else {
      createMutation.mutate(data);
    }
  };

  const isLoading = createMutation.isPending || updateMutation.isPending;

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>
            {isEditing ? "Editar Producto" : "Nuevo Producto"}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {/* Product type */}
          <div>
            <Label className="mb-2 block">Tipo de producto</Label>
            <div className="grid grid-cols-3 gap-2">
              {Object.entries(PRODUCT_TYPES).map(([key, config]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setFormData({ ...formData, type: key as ProductType })}
                  className={`p-3 rounded-lg border text-center transition-colors ${
                    formData.type === key
                      ? "border-purple-500 bg-purple-500/20"
                      : "border-gray-700 hover:border-gray-600"
                  }`}
                >
                  <span className="text-xl block mb-1">{config.emoji}</span>
                  <span className="text-xs">{config.label}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Name */}
          <div>
            <Label>Nombre *</Label>
            <Input
              placeholder="Guia Instagram 2024"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
            />
          </div>

          {/* Price */}
          <div>
            <Label>Precio (€)</Label>
            <Input
              type="number"
              placeholder="29"
              value={formData.price}
              onChange={(e) => setFormData({ ...formData, price: e.target.value })}
            />
            <p className="text-xs text-gray-500 mt-1">Deja en 0 para gratis</p>
          </div>

          {/* Tagline */}
          <div>
            <Label>Descripcion corta (para el bot)</Label>
            <Input
              placeholder="Aprende a crecer de 0 a 10k seguidores"
              value={formData.tagline}
              onChange={(e) => setFormData({ ...formData, tagline: e.target.value })}
            />
            <p className="text-xs text-gray-500 mt-1">
              El bot usara esta frase para describir tu producto
            </p>
          </div>

          {/* Purchase URL */}
          <div>
            <Label>Link de compra</Label>
            <Input
              placeholder="https://gumroad.com/l/tu-producto"
              value={formData.purchase_url}
              onChange={(e) =>
                setFormData({ ...formData, purchase_url: e.target.value })
              }
            />
            <p className="text-xs text-gray-500 mt-1">
              Gumroad, Hotmart, Stripe, tu web...
            </p>
          </div>

          {/* Bot enabled */}
          <div className="flex items-center justify-between p-3 bg-gray-800 rounded-lg">
            <div>
              <p className="font-medium">El bot puede recomendar</p>
              <p className="text-sm text-gray-400">
                Mostrar cuando pregunten por productos
              </p>
            </div>
            <Switch
              checked={formData.bot_enabled}
              onCheckedChange={(v) => setFormData({ ...formData, bot_enabled: v })}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button onClick={handleSubmit} disabled={!formData.name || isLoading}>
            {isLoading ? (
              <Loader2 className="w-4 h-4 animate-spin mr-2" />
            ) : null}
            {isEditing ? "Guardar" : "Crear"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
