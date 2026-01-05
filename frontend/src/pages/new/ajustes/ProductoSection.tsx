import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Plus, Trash2, Edit2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import {
  getProducts,
  addProduct,
  updateProduct,
  deleteProduct,
  CREATOR_ID,
} from '@/services/api';
import type { Product } from '@/types/api';

interface Props {
  onBack: () => void;
}

export default function ProductoSection({ onBack }: Props) {
  const creatorId = CREATOR_ID;
  const queryClient = useQueryClient();
  const [isEditing, setIsEditing] = useState(false);
  const [editingProduct, setEditingProduct] = useState<Product | null>(null);
  const [formData, setFormData] = useState({
    name: '',
    price: '',
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
      price: '',
      description: '',
      payment_link: '',
      is_active: true,
    });
  };

  const handleEdit = (product: Product) => {
    setEditingProduct(product);
    setFormData({
      name: product.name,
      price: String(product.price || ''),
      description: product.description || '',
      payment_link: product.payment_link || product.purchase_url || '',
      is_active: product.is_active ?? product.bot_enabled ?? true,
    });
    setIsEditing(true);
  };

  const handleSubmit = () => {
    const productData = {
      name: formData.name,
      price: parseFloat(formData.price) || 0,
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
    if (confirm('¿Seguro que quieres eliminar este producto?')) {
      deleteProductMutation.mutate(id);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <button onClick={onBack}>
          <ArrowLeft className="text-gray-400" />
        </button>
        <h1 className="text-xl font-bold text-white">Productos</h1>
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
              products.map((product) => (
                <div
                  key={product.id}
                  className="bg-gray-900 rounded-xl p-4 border border-gray-800"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <h3 className="font-medium text-white">{product.name}</h3>
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
                      <p className="text-lg font-bold text-purple-500 mt-1">
                        €{product.price}
                      </p>
                      {product.description && (
                        <p className="text-sm text-gray-400 mt-2">
                          {product.description}
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
              ))
            )}
          </div>

          <Button
            onClick={() => setIsEditing(true)}
            className="w-full bg-purple-500 hover:bg-purple-600"
          >
            <Plus className="mr-2" size={18} />
            Añadir producto
          </Button>
        </>
      )}

      {/* Edit/Create Form */}
      {isEditing && (
        <div className="space-y-4">
          <div>
            <label className="text-sm text-gray-400 block mb-2">Nombre</label>
            <Input
              placeholder="Ej: Curso de Trading Pro"
              value={formData.name}
              onChange={(e) =>
                setFormData({ ...formData, name: e.target.value })
              }
              className="bg-gray-900 border-gray-800"
            />
          </div>

          <div>
            <label className="text-sm text-gray-400 block mb-2">Precio (€)</label>
            <Input
              type="number"
              placeholder="297"
              value={formData.price}
              onChange={(e) =>
                setFormData({ ...formData, price: e.target.value })
              }
              className="bg-gray-900 border-gray-800"
            />
          </div>

          <div>
            <label className="text-sm text-gray-400 block mb-2">Descripción</label>
            <Textarea
              placeholder="Describe qué incluye tu producto..."
              value={formData.description}
              onChange={(e) =>
                setFormData({ ...formData, description: e.target.value })
              }
              className="bg-gray-900 border-gray-800 min-h-[100px]"
            />
          </div>

          <div>
            <label className="text-sm text-gray-400 block mb-2">
              Link de pago
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

          <div className="flex items-center justify-between p-3 bg-gray-900 rounded-lg">
            <span className="text-white">Producto activo</span>
            <Switch
              checked={formData.is_active}
              onCheckedChange={(checked) =>
                setFormData({ ...formData, is_active: checked })
              }
            />
          </div>

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
              {editingProduct ? 'Guardar cambios' : 'Crear producto'}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
