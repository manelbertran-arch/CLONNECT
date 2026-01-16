import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Plus, Trash2, Edit2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  getProducts,
  addProduct,
  updateProduct,
  deleteProduct,
  CREATOR_ID,
} from '@/services/api';
import type { Product, ProductCategory, ProductType } from '@/types/api';

interface Props {
  onBack: () => void;
}

// Tipos por categoría
const TIPOS_POR_CATEGORIA: Record<ProductCategory, { value: ProductType; label: string }[]> = {
  product: [
    { value: 'ebook', label: '📖 Ebook / Guía' },
    { value: 'curso', label: '🎓 Curso' },
    { value: 'plantilla', label: '📄 Plantilla' },
    { value: 'membership', label: '👥 Membresía' },
    { value: 'otro', label: '📦 Otro' }
  ],
  service: [
    { value: 'coaching', label: '🎯 Coaching 1:1' },
    { value: 'mentoria', label: '🧭 Mentoría' },
    { value: 'consultoria', label: '💼 Consultoría' },
    { value: 'call', label: '📞 Llamada / Call' },
    { value: 'sesion', label: '🗓️ Sesión' },
    { value: 'otro', label: '🤝 Otro servicio' }
  ],
  resource: [
    { value: 'podcast', label: '🎙️ Podcast' },
    { value: 'blog', label: '✍️ Blog' },
    { value: 'youtube', label: '📺 YouTube' },
    { value: 'newsletter', label: '📧 Newsletter' },
    { value: 'free_guide', label: '📚 Guía gratuita' },
    { value: 'otro', label: '📚 Otro recurso' }
  ]
};

// Badges de categoría
const CATEGORY_BADGES: Record<ProductCategory, { icon: string; label: string; color: string }> = {
  product: { icon: '🛒', label: 'Producto', color: 'bg-green-500/20 text-green-500' },
  service: { icon: '🤝', label: 'Servicio', color: 'bg-blue-500/20 text-blue-500' },
  resource: { icon: '📚', label: 'Recurso', color: 'bg-purple-500/20 text-purple-500' }
};

// Helper para formatear precio
const formatPrice = (product: Product) => {
  if (product.category === 'resource') {
    return 'Gratuito';
  }
  if (product.is_free) {
    return 'Gratis';
  }
  if (product.price) {
    return `${product.price} ${product.currency || '€'}`;
  }
  return 'Consultar';
};

export default function ProductoSection({ onBack }: Props) {
  const creatorId = CREATOR_ID;
  const queryClient = useQueryClient();
  const [isEditing, setIsEditing] = useState(false);
  const [editingProduct, setEditingProduct] = useState<Product | null>(null);
  const [formData, setFormData] = useState({
    name: '',
    category: 'product' as ProductCategory,
    product_type: 'otro' as ProductType,
    price: '',
    currency: 'EUR',
    is_free: false,
    description: '',
    payment_link: '',
    is_active: true,
  });

  const { data: productsData, isLoading } = useQuery({
    queryKey: ['products', creatorId],
    queryFn: () => getProducts(creatorId),
  });

  const addProductMutation = useMutation({
    mutationFn: (product: Omit<Product, 'id'>) => addProduct(creatorId, product),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products', creatorId] });
      resetForm();
    },
  });

  const updateProductMutation = useMutation({
    mutationFn: ({ id, product }: { id: string; product: Partial<Product> }) =>
      updateProduct(creatorId, id, product),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products', creatorId] });
      resetForm();
    },
  });

  const deleteProductMutation = useMutation({
    mutationFn: (id: string) => deleteProduct(creatorId, id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products', creatorId] });
    },
  });

  const products = productsData?.products || [];

  const resetForm = () => {
    setIsEditing(false);
    setEditingProduct(null);
    setFormData({
      name: '',
      category: 'product',
      product_type: 'otro',
      price: '',
      currency: 'EUR',
      is_free: false,
      description: '',
      payment_link: '',
      is_active: true,
    });
  };

  const handleEdit = (product: Product) => {
    setEditingProduct(product);
    setFormData({
      name: product.name,
      category: product.category || 'product',
      product_type: product.product_type || 'otro',
      price: String(product.price || ''),
      currency: product.currency || 'EUR',
      is_free: product.is_free || false,
      description: product.description || '',
      payment_link: product.payment_link || product.purchase_url || '',
      is_active: product.is_active ?? product.bot_enabled ?? true,
    });
    setIsEditing(true);
  };

  const handleCategoryChange = (newCategory: ProductCategory) => {
    setFormData({
      ...formData,
      category: newCategory,
      product_type: TIPOS_POR_CATEGORIA[newCategory][0].value,
      // Reset is_free si cambia de service a otra categoría
      is_free: newCategory === 'resource' ? true : (newCategory === 'service' ? formData.is_free : false),
      // Reset precio si es resource
      price: newCategory === 'resource' ? '0' : formData.price,
    });
  };

  const handleSubmit = () => {
    const productData: Omit<Product, 'id'> = {
      name: formData.name,
      category: formData.category,
      product_type: formData.product_type,
      price: formData.category === 'resource' ? 0 : (parseFloat(formData.price) || 0),
      currency: formData.currency,
      is_free: formData.category === 'resource' || formData.is_free,
      description: formData.description,
      payment_link: formData.payment_link,
      is_active: formData.is_active,
    };

    if (editingProduct) {
      updateProductMutation.mutate({ id: editingProduct.id, product: productData });
    } else {
      addProductMutation.mutate(productData);
    }
  };

  const handleDelete = (id: string) => {
    if (confirm('¿Seguro que quieres eliminar este elemento?')) {
      deleteProductMutation.mutate(id);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <button onClick={onBack}>
          <ArrowLeft className="text-gray-400" />
        </button>
        <h1 className="text-xl font-bold text-white">Catálogo</h1>
      </div>

      {/* Product List */}
      {!isEditing && (
        <>
          <div className="space-y-3">
            {isLoading ? (
              <p className="text-gray-500 text-center py-4">Cargando...</p>
            ) : products.length === 0 ? (
              <p className="text-gray-500 text-center py-4">
                No hay productos configurados
              </p>
            ) : (
              products.map((product) => {
                const category = (product.category || 'product') as ProductCategory;
                const badge = CATEGORY_BADGES[category];
                return (
                  <div
                    key={product.id}
                    className="bg-gray-900 rounded-xl p-4 border border-gray-800"
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          {/* Category badge */}
                          <span className={`px-2 py-0.5 text-xs rounded-full ${badge.color}`}>
                            {badge.icon} {badge.label}
                          </span>
                          {/* Type */}
                          <span className="text-xs text-gray-500">
                            {product.product_type || product.type || 'otro'}
                          </span>
                          {/* Active status */}
                          {product.is_active ? (
                            <span className="px-2 py-0.5 bg-green-500/20 text-green-500 text-xs rounded-full">
                              Activo
                            </span>
                          ) : (
                            <span className="px-2 py-0.5 bg-gray-500/20 text-gray-500 text-xs rounded-full">
                              Pausado
                            </span>
                          )}
                        </div>
                        <h3 className="font-medium text-white mt-2">{product.name}</h3>
                        <p className="text-lg font-bold text-purple-500 mt-1">
                          {formatPrice(product)}
                        </p>
                        {product.description && (
                          <p className="text-sm text-gray-400 mt-2 line-clamp-2">
                            {product.short_description || product.description}
                          </p>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => handleEdit(product)}
                          className="p-2 text-gray-400 hover:text-white transition-colors"
                        >
                          <Edit2 size={18} />
                        </button>
                        <button
                          onClick={() => handleDelete(product.id)}
                          className="p-2 text-gray-400 hover:text-red-500 transition-colors"
                        >
                          <Trash2 size={18} />
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>

          <Button
            onClick={() => setIsEditing(true)}
            className="w-full bg-purple-500 hover:bg-purple-600"
          >
            <Plus className="mr-2" size={18} />
            Añadir elemento
          </Button>
        </>
      )}

      {/* Edit/Create Form */}
      {isEditing && (
        <div className="space-y-4">
          {/* Categoría */}
          <div>
            <label className="text-sm text-gray-400 block mb-2">Categoría *</label>
            <Select
              value={formData.category}
              onValueChange={(value) => handleCategoryChange(value as ProductCategory)}
            >
              <SelectTrigger className="bg-gray-900 border-gray-800">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="product">🛒 Producto (algo que vendes)</SelectItem>
                <SelectItem value="service">🤝 Servicio (sesiones, coaching)</SelectItem>
                <SelectItem value="resource">📚 Recurso (podcast, blog gratuito)</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Tipo (dinámico según categoría) */}
          <div>
            <label className="text-sm text-gray-400 block mb-2">Tipo</label>
            <Select
              value={formData.product_type}
              onValueChange={(value) => setFormData({ ...formData, product_type: value as ProductType })}
            >
              <SelectTrigger className="bg-gray-900 border-gray-800">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TIPOS_POR_CATEGORIA[formData.category].map((tipo) => (
                  <SelectItem key={tipo.value} value={tipo.value}>
                    {tipo.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Nombre */}
          <div>
            <label className="text-sm text-gray-400 block mb-2">Nombre *</label>
            <Input
              placeholder={
                formData.category === 'product' ? 'Ej: Curso de Trading Pro' :
                formData.category === 'service' ? 'Ej: Sesión de Coaching 1:1' :
                'Ej: Podcast Sabios y Salvajes'
              }
              value={formData.name}
              onChange={(e) =>
                setFormData({ ...formData, name: e.target.value })
              }
              className="bg-gray-900 border-gray-800"
            />
          </div>

          {/* Precio - solo para product y service */}
          {formData.category !== 'resource' && (
            <>
              <div className="flex gap-4">
                <div className="flex-1">
                  <label className="text-sm text-gray-400 block mb-2">
                    Precio {formData.category === 'product' ? '*' : '(opcional)'}
                  </label>
                  <Input
                    type="number"
                    placeholder="297"
                    value={formData.price}
                    disabled={formData.is_free}
                    onChange={(e) =>
                      setFormData({ ...formData, price: e.target.value })
                    }
                    className="bg-gray-900 border-gray-800"
                  />
                </div>
                <div className="w-24">
                  <label className="text-sm text-gray-400 block mb-2">Moneda</label>
                  <Select
                    value={formData.currency}
                    onValueChange={(value) => setFormData({ ...formData, currency: value })}
                  >
                    <SelectTrigger className="bg-gray-900 border-gray-800">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="EUR">€ EUR</SelectItem>
                      <SelectItem value="USD">$ USD</SelectItem>
                      <SelectItem value="MXN">$ MXN</SelectItem>
                      <SelectItem value="GBP">£ GBP</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              {/* Checkbox "Es gratuito" para servicios */}
              {formData.category === 'service' && (
                <div className="flex items-center space-x-2">
                  <Checkbox
                    id="is_free"
                    checked={formData.is_free}
                    onCheckedChange={(checked) =>
                      setFormData({ ...formData, is_free: checked as boolean, price: checked ? '0' : formData.price })
                    }
                  />
                  <label
                    htmlFor="is_free"
                    className="text-sm text-gray-300 cursor-pointer"
                  >
                    Es gratuito (ej: discovery call)
                  </label>
                </div>
              )}
            </>
          )}

          {/* Descripción */}
          <div>
            <label className="text-sm text-gray-400 block mb-2">Descripción</label>
            <Textarea
              placeholder={
                formData.category === 'product' ? 'Describe qué incluye tu producto...' :
                formData.category === 'service' ? 'Describe qué incluye tu servicio...' :
                'Describe de qué trata tu recurso...'
              }
              value={formData.description}
              onChange={(e) =>
                setFormData({ ...formData, description: e.target.value })
              }
              className="bg-gray-900 border-gray-800 min-h-[100px]"
            />
          </div>

          {/* Link de pago/reserva/recurso */}
          <div>
            <label className="text-sm text-gray-400 block mb-2">
              {formData.category === 'product' ? 'Link de pago' :
               formData.category === 'service' ? 'Link de reserva (Calendly, etc.)' :
               'Link al recurso'}
            </label>
            <Input
              placeholder="https://..."
              value={formData.payment_link}
              onChange={(e) =>
                setFormData({ ...formData, payment_link: e.target.value })
              }
              className="bg-gray-900 border-gray-800"
            />
          </div>

          {/* Toggle activo */}
          <div className="flex items-center justify-between p-3 bg-gray-900 rounded-lg">
            <span className="text-white">
              {formData.category === 'product' ? 'Producto activo' :
               formData.category === 'service' ? 'Servicio activo' :
               'Recurso activo'}
            </span>
            <Switch
              checked={formData.is_active}
              onCheckedChange={(checked) =>
                setFormData({ ...formData, is_active: checked })
              }
            />
          </div>

          {/* Botones */}
          <div className="flex gap-3">
            <Button
              variant="outline"
              onClick={resetForm}
              className="flex-1 border-gray-700"
            >
              Cancelar
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={
                !formData.name ||
                addProductMutation.isPending ||
                updateProductMutation.isPending
              }
              className="flex-1 bg-purple-500 hover:bg-purple-600"
            >
              {editingProduct ? 'Guardar cambios' : 'Crear'}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
