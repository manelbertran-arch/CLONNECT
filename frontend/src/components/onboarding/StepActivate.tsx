import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Check, Rocket, Instagram, User, ShoppingBag, Loader2, Sparkles } from 'lucide-react';
import { useOnboarding, clearOnboardingStorage } from './OnboardingContext';
import { API_URL } from '@/services/api';

export function StepActivate() {
  const navigate = useNavigate();
  const {
    prevStep,
    instagramUsername,
    profile,
    products,
    botActive,
    setBotActive,
    creatorId,
    setLoading,
    isLoading,
    setError,
    error,
  } = useOnboarding();

  const [isActivating, setIsActivating] = useState(false);
  const [isComplete, setIsComplete] = useState(false);

  const handleActivate = async () => {
    setIsActivating(true);
    setError(null);

    try {
      // Save profile and products to backend
      const response = await fetch(`${API_URL}/onboarding/complete`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          creator_id: creatorId,
          profile: {
            business_name: profile.businessName,
            description: profile.description,
            tone: profile.tone,
          },
          products: products.map(p => ({
            name: p.name,
            description: p.description,
            price: p.price ? parseFloat(p.price) : null,
          })),
          bot_active: botActive,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Error al completar onboarding');
      }

      // Success!
      setIsComplete(true);

      // Clear onboarding storage
      clearOnboardingStorage();

      // Redirect to dashboard after animation
      setTimeout(() => {
        navigate('/dashboard');
      }, 2500);

    } catch (err) {
      console.error('Activation error:', err);
      setError(err instanceof Error ? err.message : 'Error al activar. Inténtalo de nuevo.');
      setIsActivating(false);
    }
  };

  // Completion screen
  if (isComplete) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[80vh] px-6 animate-fade-in">
        <div
          className="w-24 h-24 rounded-full flex items-center justify-center mb-6"
          style={{ background: 'linear-gradient(135deg, #22c55e, #16a34a)' }}
        >
          <Check className="w-12 h-12 text-white" strokeWidth={3} />
        </div>

        <h1
          className="text-3xl font-bold text-center mb-4"
          style={{
            background: 'linear-gradient(135deg, #22c55e, #16a34a)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
          }}
        >
          ¡Tu clon está listo!
        </h1>

        <p className="text-center mb-8" style={{ color: 'rgba(255, 255, 255, 0.6)' }}>
          Ya puedes empezar a automatizar tus DMs
        </p>

        <div className="flex justify-center gap-1.5">
          <div className="w-2 h-2 rounded-full animate-bounce" style={{ background: '#22c55e' }} />
          <div className="w-2 h-2 rounded-full animate-bounce" style={{ background: '#22c55e', animationDelay: '150ms' }} />
          <div className="w-2 h-2 rounded-full animate-bounce" style={{ background: '#22c55e', animationDelay: '300ms' }} />
        </div>

        <p className="text-sm mt-4" style={{ color: 'rgba(255, 255, 255, 0.4)' }}>
          Redirigiendo al dashboard...
        </p>
      </div>
    );
  }

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

      <div className="flex-1 flex flex-col items-center justify-center">
        {/* Header */}
        <div className="text-center mb-8">
          <div
            className="w-20 h-20 rounded-2xl flex items-center justify-center mx-auto mb-4"
            style={{ background: 'linear-gradient(135deg, #a855f7, #6366f1)' }}
          >
            <Rocket className="w-10 h-10 text-white" />
          </div>
          <h1 className="text-2xl md:text-3xl font-bold text-white mb-2">
            ¡Todo listo!
          </h1>
          <p style={{ color: 'rgba(255, 255, 255, 0.6)' }}>
            Revisa tu configuración y activa tu clon
          </p>
        </div>

        {/* Summary */}
        <div className="w-full max-w-sm space-y-3 mb-8">
          {/* Instagram */}
          <div
            className="p-4 rounded-xl flex items-center gap-4"
            style={{ background: 'rgba(255, 255, 255, 0.03)', border: '1px solid rgba(255, 255, 255, 0.06)' }}
          >
            <div className="p-2 rounded-lg" style={{ background: 'rgba(228, 64, 95, 0.1)' }}>
              <Instagram className="w-5 h-5" style={{ color: '#E4405F' }} />
            </div>
            <div className="flex-1">
              <p className="text-white font-medium">Instagram</p>
              <p className="text-sm" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>
                @{instagramUsername}
              </p>
            </div>
            <Check className="w-5 h-5" style={{ color: '#22c55e' }} />
          </div>

          {/* Profile */}
          <div
            className="p-4 rounded-xl flex items-center gap-4"
            style={{ background: 'rgba(255, 255, 255, 0.03)', border: '1px solid rgba(255, 255, 255, 0.06)' }}
          >
            <div className="p-2 rounded-lg" style={{ background: 'rgba(168, 85, 247, 0.1)' }}>
              <User className="w-5 h-5" style={{ color: '#a855f7' }} />
            </div>
            <div className="flex-1">
              <p className="text-white font-medium">{profile.businessName || 'Perfil'}</p>
              <p className="text-sm" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>
                Tono {profile.tone}
              </p>
            </div>
            <Check className="w-5 h-5" style={{ color: '#22c55e' }} />
          </div>

          {/* Products */}
          <div
            className="p-4 rounded-xl flex items-center gap-4"
            style={{ background: 'rgba(255, 255, 255, 0.03)', border: '1px solid rgba(255, 255, 255, 0.06)' }}
          >
            <div className="p-2 rounded-lg" style={{ background: 'rgba(99, 102, 241, 0.1)' }}>
              <ShoppingBag className="w-5 h-5" style={{ color: '#6366f1' }} />
            </div>
            <div className="flex-1">
              <p className="text-white font-medium">Productos</p>
              <p className="text-sm" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>
                {products.length > 0 ? `${products.length} añadidos` : 'Ninguno añadido'}
              </p>
            </div>
            {products.length > 0 ? (
              <Check className="w-5 h-5" style={{ color: '#22c55e' }} />
            ) : (
              <span className="text-xs px-2 py-1 rounded-full" style={{ background: 'rgba(255, 255, 255, 0.1)', color: 'rgba(255, 255, 255, 0.5)' }}>
                Opcional
              </span>
            )}
          </div>
        </div>

        {/* Bot Toggle */}
        <div
          className="w-full max-w-sm p-4 rounded-xl mb-6"
          style={{ background: 'rgba(34, 197, 94, 0.05)', border: '1px solid rgba(34, 197, 94, 0.2)' }}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Sparkles className="w-5 h-5" style={{ color: '#22c55e' }} />
              <div>
                <p className="text-white font-medium">Activar clon</p>
                <p className="text-xs" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>
                  Empezará a responder DMs automáticamente
                </p>
              </div>
            </div>
            <button
              onClick={() => setBotActive(!botActive)}
              className={`
                relative w-14 h-7 rounded-full transition-all duration-300
                ${botActive ? 'bg-green-500' : 'bg-white/20'}
              `}
            >
              <div
                className={`
                  absolute top-1 w-5 h-5 rounded-full bg-white transition-all duration-300
                  ${botActive ? 'left-8' : 'left-1'}
                `}
              />
            </button>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div
            className="w-full max-w-sm p-4 rounded-xl mb-6"
            style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)' }}
          >
            <p className="text-red-400 text-sm">{error}</p>
          </div>
        )}

        {/* Activate Button */}
        <button
          onClick={handleActivate}
          disabled={isActivating}
          className="w-full max-w-sm p-4 text-white font-semibold rounded-xl flex items-center justify-center gap-3 transition-all hover:scale-[1.02] disabled:opacity-50 disabled:hover:scale-100"
          style={{
            background: 'linear-gradient(135deg, #22c55e, #16a34a)',
            boxShadow: '0 4px 20px rgba(34, 197, 94, 0.3)',
          }}
        >
          {isActivating ? (
            <>
              <Loader2 className="w-5 h-5 animate-spin" />
              Activando...
            </>
          ) : (
            <>
              <Rocket className="w-5 h-5" />
              Activar mi clon
            </>
          )}
        </button>
      </div>
    </div>
  );
}
