import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Instagram, Loader2, CheckCircle, AlertCircle, ArrowLeft } from 'lucide-react';
import { useOnboarding } from './OnboardingContext';
import { API_URL, setCreatorId } from '@/services/api';

export function StepConnectIG() {
  const {
    nextStep,
    prevStep,
    instagramConnected,
    instagramUsername,
    setInstagramConnected,
    getOrCreateCreatorId,
    setError,
    error,
  } = useOnboarding();

  const [isLoading, setIsLoading] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();

  // Check for OAuth callback on mount
  useEffect(() => {
    const success = searchParams.get('success');
    const errorParam = searchParams.get('error');
    const errorMessage = searchParams.get('message');
    const onboarding = searchParams.get('onboarding');
    const igUsername = searchParams.get('ig_username');

    // Handle OAuth errors
    if (errorParam) {
      console.log('[Onboarding] OAuth error:', errorParam, errorMessage);
      const errorMessages: Record<string, string> = {
        'instagram_scope_error': errorMessage || 'Error de permisos. Asegúrate de aprobar todos los permisos.',
        'instagram_no_code': 'No se recibió autorización de Instagram.',
        'instagram_not_configured': 'OAuth no está configurado correctamente.',
        'instagram_auth_failed': 'Error de autenticación con Instagram.',
        'instagram_failed': 'Error al conectar con Instagram. Inténtalo de nuevo.',
      };
      setError(errorMessages[errorParam] || 'Error desconocido durante OAuth.');
      // Clear URL params
      setSearchParams({});
      return;
    }

    // Handle OAuth success
    if (success?.includes('instagram') && onboarding === 'started') {
      console.log('[Onboarding] OAuth success!', { igUsername });
      setInstagramConnected(true, igUsername || 'conectado');
      setError(null);
      // Clear URL params
      setSearchParams({});
    }
  }, [searchParams, setSearchParams, setInstagramConnected, setError]);

  const handleConnectInstagram = async () => {
    const creatorId = getOrCreateCreatorId();

    console.log('[Onboarding] Starting Instagram OAuth for:', creatorId);
    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch(`${API_URL}/oauth/instagram/start?creator_id=${encodeURIComponent(creatorId)}`);

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Error al iniciar OAuth');
      }

      const data = await response.json();
      console.log('[Onboarding] OAuth response:', data);

      if (data.auth_url) {
        // Save creator_id before redirecting
        setCreatorId(creatorId);
        // Redirect to Instagram OAuth
        window.location.href = data.auth_url;
      } else {
        throw new Error('No se recibió URL de autorización');
      }
    } catch (err) {
      console.error('OAuth error:', err);
      setError(err instanceof Error ? err.message : 'Error al conectar. Inténtalo de nuevo.');
      setIsLoading(false);
    }
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

      <div className="flex-1 flex flex-col items-center justify-center">
        {/* Icon */}
        <div
          className="w-20 h-20 rounded-2xl flex items-center justify-center mb-6"
          style={{
            background: instagramConnected
              ? 'linear-gradient(135deg, #22c55e, #16a34a)'
              : 'linear-gradient(135deg, #E4405F, #833AB4)',
          }}
        >
          {instagramConnected ? (
            <CheckCircle className="w-10 h-10 text-white" />
          ) : (
            <Instagram className="w-10 h-10 text-white" />
          )}
        </div>

        {/* Title */}
        <h1 className="text-2xl md:text-3xl font-bold text-center text-white mb-3">
          {instagramConnected ? '¡Instagram conectado!' : 'Conecta tu Instagram'}
        </h1>

        <p className="text-center mb-8 max-w-sm" style={{ color: 'rgba(255, 255, 255, 0.6)' }}>
          {instagramConnected
            ? `Conectado como @${instagramUsername}`
            : 'Tu clon aprenderá de tu contenido y responderá DMs automáticamente'}
        </p>

        {/* Error message */}
        {error && (
          <div
            className="w-full max-w-sm p-4 rounded-xl mb-6 flex items-start gap-3"
            style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)' }}
          >
            <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" style={{ color: '#ef4444' }} />
            <span style={{ color: '#ef4444' }}>{error}</span>
          </div>
        )}

        {/* Connect Button or Continue */}
        {instagramConnected ? (
          <button
            onClick={nextStep}
            className="w-full max-w-sm p-4 text-white font-semibold rounded-xl flex items-center justify-center gap-3 transition-all hover:scale-[1.02]"
            style={{
              background: 'linear-gradient(135deg, #22c55e, #16a34a)',
              boxShadow: '0 4px 20px rgba(34, 197, 94, 0.3)',
            }}
          >
            Continuar
          </button>
        ) : (
          <>
            <button
              onClick={handleConnectInstagram}
              disabled={isLoading}
              className="w-full max-w-sm p-4 text-white font-semibold rounded-xl flex items-center justify-center gap-3 transition-all hover:scale-[1.02] disabled:opacity-50 disabled:hover:scale-100"
              style={{
                background: 'linear-gradient(135deg, #E4405F, #833AB4)',
                boxShadow: '0 4px 20px rgba(228, 64, 95, 0.3)',
              }}
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  Conectando...
                </>
              ) : (
                <>
                  <Instagram className="w-5 h-5" />
                  Conectar con Instagram
                </>
              )}
            </button>

            {/* Requirements */}
            <div
              className="w-full max-w-sm p-4 rounded-xl mt-6"
              style={{ background: 'rgba(255, 255, 255, 0.03)', border: '1px solid rgba(255, 255, 255, 0.06)' }}
            >
              <p className="text-sm mb-2" style={{ color: 'rgba(255, 255, 255, 0.6)' }}>Requisitos:</p>
              <ul className="space-y-1 text-sm" style={{ color: 'rgba(255, 255, 255, 0.4)' }}>
                <li>• Cuenta de Instagram Business o Creator</li>
                <li>• Conectada a una Página de Facebook</li>
                <li>• Permisos de mensajes activados</li>
              </ul>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
