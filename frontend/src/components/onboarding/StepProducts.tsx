import { useState } from 'react';
import { ArrowLeft, ArrowRight, Package, Plus, X, ShoppingBag } from 'lucide-react';
import { useOnboarding, ProductData } from './OnboardingContext';

export function StepProducts() {
  const { nextStep, prevStep, products, addProduct, removeProduct } = useOnboarding();

  const [showForm, setShowForm] = useState(false);
  const [newProduct, setNewProduct] = useState({ name: '', description: '', price: '' });
  const [errors, setErrors] = useState<{ name?: string; description?: string }>({});

  const handleAddProduct = () => {
    // Validation
    const newErrors: typeof errors = {};

    if (!newProduct.name.trim()) {
      newErrors.name = 'El nombre es obligatorio';
    }

    if (!newProduct.description.trim()) {
      newErrors.description = 'La descripción es obligatoria';
    }

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      return;
    }

    addProduct(newProduct);
    setNewProduct({ name: '', description: '', price: '' });
    setErrors({});
    setShowForm(false);
  };

  const handleSkip = () => {
    nextStep();
  };

  return (
    <div className="flex flex-col min-h-[80vh] px-6 animate-fade-in">
      {/* Back button */}
      <button
        onClick={prevStep}
        className="flex items-center gap-2 mb-6 text-white/60 hover:text-white transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Volver
      </button>

      <div className="flex-1 flex flex-col">
        {/* Header */}
        <div className="text-center mb-6">
          <div
            className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-4"
            style={{ background: 'rgba(99, 102, 241, 0.1)' }}
          >
            <ShoppingBag className="w-8 h-8" style={{ color: '#6366f1' }} />
          </div>
          <h1 className="text-2xl md:text-3xl font-bold text-white mb-2">
            ¿Qué ofreces?
          </h1>
          <p style={{ color: 'rgba(255, 255, 255, 0.6)' }}>
            Añade tus productos o servicios para que tu clon pueda hablar de ellos
          </p>
        </div>

        {/* Products List */}
        <div className="flex-1 max-w-sm mx-auto w-full space-y-4">
          {products.length > 0 && (
            <div className="space-y-3">
              {products.map((product) => (
                <div
                  key={product.id}
                  className="p-4 rounded-xl flex items-start justify-between"
                  style={{ background: 'rgba(255, 255, 255, 0.03)', border: '1px solid rgba(255, 255, 255, 0.06)' }}
                >
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <Package className="w-4 h-4" style={{ color: '#6366f1' }} />
                      <span className="font-medium text-white">{product.name}</span>
                      {product.price && (
                        <span className="text-sm px-2 py-0.5 rounded-full" style={{ background: 'rgba(34, 197, 94, 0.1)', color: '#22c55e' }}>
                          {product.price}€
                        </span>
                      )}
                    </div>
                    <p className="text-sm mt-1" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>
                      {product.description}
                    </p>
                  </div>
                  <button
                    onClick={() => removeProduct(product.id)}
                    className="p-1 rounded-lg hover:bg-white/10 transition-colors"
                  >
                    <X className="w-4 h-4" style={{ color: 'rgba(255, 255, 255, 0.4)' }} />
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* Add Product Form */}
          {showForm ? (
            <div
              className="p-4 rounded-xl space-y-4"
              style={{ background: 'rgba(99, 102, 241, 0.05)', border: '1px solid rgba(99, 102, 241, 0.2)' }}
            >
              <div>
                <label className="block text-sm font-medium text-white mb-2">Nombre</label>
                <input
                  type="text"
                  value={newProduct.name}
                  onChange={(e) => {
                    setNewProduct(prev => ({ ...prev, name: e.target.value }));
                    if (errors.name) setErrors(prev => ({ ...prev, name: undefined }));
                  }}
                  placeholder="Ej: Plan de entrenamiento mensual"
                  className={`w-full p-3 rounded-xl text-white outline-none text-sm ${
                    errors.name ? 'ring-2 ring-red-500' : 'focus:ring-2 focus:ring-indigo-500'
                  }`}
                  style={{ background: 'rgba(255, 255, 255, 0.05)', border: '1px solid rgba(255, 255, 255, 0.08)' }}
                />
                {errors.name && <p className="text-red-400 text-xs mt-1">{errors.name}</p>}
              </div>

              <div>
                <label className="block text-sm font-medium text-white mb-2">Descripción</label>
                <textarea
                  value={newProduct.description}
                  onChange={(e) => {
                    setNewProduct(prev => ({ ...prev, description: e.target.value }));
                    if (errors.description) setErrors(prev => ({ ...prev, description: undefined }));
                  }}
                  placeholder="Describe qué incluye..."
                  rows={2}
                  className={`w-full p-3 rounded-xl text-white outline-none resize-none text-sm ${
                    errors.description ? 'ring-2 ring-red-500' : 'focus:ring-2 focus:ring-indigo-500'
                  }`}
                  style={{ background: 'rgba(255, 255, 255, 0.05)', border: '1px solid rgba(255, 255, 255, 0.08)' }}
                />
                {errors.description && <p className="text-red-400 text-xs mt-1">{errors.description}</p>}
              </div>

              <div>
                <label className="block text-sm font-medium text-white mb-2">Precio (opcional)</label>
                <input
                  type="text"
                  value={newProduct.price}
                  onChange={(e) => setNewProduct(prev => ({ ...prev, price: e.target.value }))}
                  placeholder="Ej: 49"
                  className="w-full p-3 rounded-xl text-white outline-none text-sm focus:ring-2 focus:ring-indigo-500"
                  style={{ background: 'rgba(255, 255, 255, 0.05)', border: '1px solid rgba(255, 255, 255, 0.08)' }}
                />
              </div>

              <div className="flex gap-3">
                <button
                  onClick={() => {
                    setShowForm(false);
                    setNewProduct({ name: '', description: '', price: '' });
                    setErrors({});
                  }}
                  className="flex-1 p-3 rounded-xl text-white font-medium transition-all hover:bg-white/10"
                  style={{ background: 'rgba(255, 255, 255, 0.05)', border: '1px solid rgba(255, 255, 255, 0.08)' }}
                >
                  Cancelar
                </button>
                <button
                  onClick={handleAddProduct}
                  className="flex-1 p-3 rounded-xl text-white font-medium transition-all hover:opacity-90"
                  style={{ background: 'linear-gradient(135deg, #6366f1, #4f46e5)' }}
                >
                  Añadir
                </button>
              </div>
            </div>
          ) : (
            <button
              onClick={() => setShowForm(true)}
              className="w-full p-4 rounded-xl flex items-center justify-center gap-2 text-white/70 hover:text-white hover:bg-white/5 transition-all"
              style={{ border: '2px dashed rgba(255, 255, 255, 0.1)' }}
            >
              <Plus className="w-5 h-5" />
              Añadir producto o servicio
            </button>
          )}

          {/* Info */}
          <div
            className="p-4 rounded-xl"
            style={{ background: 'rgba(168, 85, 247, 0.05)', border: '1px solid rgba(168, 85, 247, 0.1)' }}
          >
            <p className="text-sm" style={{ color: 'rgba(255, 255, 255, 0.6)' }}>
              💡 Tu clon usará esta información para recomendar productos y responder preguntas sobre precios.
            </p>
          </div>
        </div>

        {/* Buttons */}
        <div className="pt-6 max-w-sm mx-auto w-full space-y-3">
          <button
            onClick={nextStep}
            className="w-full p-4 text-white font-semibold rounded-xl flex items-center justify-center gap-3 transition-all hover:scale-[1.02]"
            style={{
              background: 'linear-gradient(135deg, #a855f7, #6366f1)',
              boxShadow: '0 4px 20px rgba(168, 85, 247, 0.3)',
            }}
          >
            {products.length > 0 ? 'Siguiente' : 'Saltar por ahora'}
            <ArrowRight className="w-5 h-5" />
          </button>

          {products.length === 0 && (
            <p className="text-center text-sm" style={{ color: 'rgba(255, 255, 255, 0.4)' }}>
              Puedes añadir productos más tarde desde el dashboard
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
