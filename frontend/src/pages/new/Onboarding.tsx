import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Instagram, Youtube, Globe, CheckCircle, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { API_URL, setCreatorId, getCreatorId } from '@/services/api';

type OnboardingStep = 'splash' | 'connect' | 'loading' | 'complete' | 'oauth_redirect';

// SetupStatus and ManualSetupStatus interfaces removed - OAuth handles setup in backend

export default function Onboarding() {
  const [step, setStep] = useState<OnboardingStep>('connect');
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  // Optional website URL for knowledge base
  const [websiteUrl, setWebsiteUrl] = useState('');

  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  // Helper to generate a temporary creator_id before OAuth
  const generateTempCreatorId = (): string => {
    // Use existing creator_id if available, otherwise generate a temporary one
    const existing = getCreatorId();
    if (existing && existing !== 'demo_creator') {
      return existing;
    }
    // Generate a temporary ID - will be replaced with real Instagram username after OAuth
    return `temp_${Date.now()}`;
  };

  // Auto-advance from splash after 4 seconds
  useEffect(() => {
    if (step === 'splash') {
      const timer = setTimeout(() => {
        setStep('connect');
      }, 4000);
      return () => clearTimeout(timer);
    }
  }, [step]);

  // Check for OAuth callback (success or error)
  useEffect(() => {
    const success = searchParams.get('success');
    const errorParam = searchParams.get('error');
    const errorMessage = searchParams.get('message');

    // Handle OAuth errors
    if (errorParam) {
      const errorMessages: Record<string, string> = {
        'instagram_scope_error': errorMessage || 'Error de permisos. Asegúrate de aprobar todos los permisos.',
        'instagram_no_code': 'No se recibió autorización de Instagram.',
        'instagram_not_configured': 'OAuth no está configurado correctamente.',
        'instagram_auth_failed': 'Error de autenticación con Instagram.',
        'instagram_failed': 'Error al conectar con Instagram. Inténtalo de nuevo.',
      };
      setError(errorMessages[errorParam] || 'Error desconocido durante OAuth.');
      return;
    }

    // Handle OAuth success
    if (success?.includes('instagram')) {
      const onboarding = searchParams.get('onboarding');

      if (onboarding === 'started') {
        // OAuth was successful and auto-onboarding started in backend
        // Go directly to complete screen (backend handles everything)
        setStep('complete');
      }
    }
  }, [searchParams]);

  const handleConnectInstagram = async () => {
    // Generate or use existing creator_id for OAuth state
    const creatorId = generateTempCreatorId();

    setIsLoading(true);
    setError(null);

    try {
      // Build OAuth start URL with optional website_url
      let oauthUrl = `${API_URL}/oauth/instagram/start?creator_id=${encodeURIComponent(creatorId)}`;
      if (websiteUrl && websiteUrl.trim()) {
        oauthUrl += `&website_url=${encodeURIComponent(websiteUrl.trim())}`;
      }

      // Call OAuth start endpoint to get the auth URL
      const response = await fetch(oauthUrl);

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Error al iniciar OAuth');
      }

      const data = await response.json();

      if (data.auth_url) {
        // Save the creator_id before redirecting (will be updated after OAuth callback)
        setCreatorId(creatorId);

        // Redirect to Instagram/Meta OAuth page
        window.location.href = data.auth_url;
      } else {
        throw new Error('No se recibió URL de autorización');
      }
    } catch (err) {
      console.error('OAuth start error:', err);
      setError(err instanceof Error ? err.message : 'Error al iniciar OAuth. Inténtalo de nuevo.');
      setIsLoading(false);
    }
  };

  // SPLASH SCREEN - Pure black, BIG logo with pulse, 4 seconds
  if (step === 'splash') {
    return (
      <div className="min-h-screen bg-black flex flex-col items-center justify-center">
        <div className="animate-fade-in">
          <img
            src="/clonnect-logo.png"
            alt="Clonnect"
            className="w-72 h-72 md:w-96 md:h-96 object-contain animate-pulse"
          />
        </div>
      </div>
    );
  }

  // CONNECT SCREEN - Instagram OAuth only
  if (step === 'connect') {
    return (
      <div className="min-h-screen bg-black flex flex-col">
        {/* Header with logo top left */}
        <div className="p-6">
          <img
            src="/clonnect-logo.png"
            alt="Clonnect"
            className="w-12 h-12 object-contain animate-pulse"
          />
        </div>

        <div className="flex-1 flex flex-col justify-center px-6 pb-12 max-w-md mx-auto w-full animate-fade-in">
          {/* Title */}
          <div className="text-center mb-8">
            <h1 className="text-2xl md:text-3xl font-bold text-white mb-2">
              Conecta tu Instagram
            </h1>
            <p className="text-gray-400">
              Tu clon aprenderá de tu contenido y responderá DMs automáticamente
            </p>
          </div>

          {/* Error message */}
          {error && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 mb-6">
              <p className="text-red-400 text-sm">{error}</p>
            </div>
          )}

          <div className="space-y-4">
            {/* Main CTA - Instagram OAuth */}
            <Button
              onClick={handleConnectInstagram}
              disabled={isLoading}
              size="lg"
              className="w-full h-14 text-lg bg-gradient-to-r from-purple-600 to-fuchsia-500 hover:from-purple-700 hover:to-fuchsia-600 transition-all disabled:opacity-50"
            >
              {isLoading ? (
                <>
                  <Loader2 className="mr-3 h-6 w-6 animate-spin" />
                  Conectando...
                </>
              ) : (
                <>
                  <Instagram className="mr-3 h-6 w-6" />
                  Conectar con Instagram
                </>
              )}
            </Button>

            <p className="text-xs text-gray-500 text-center">
              Conecta tu cuenta Business/Creator para acceso completo a posts y DMs
            </p>

            {/* Requirements info */}
            <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4 mt-6">
              <p className="text-sm text-gray-400 mb-2">Requisitos:</p>
              <ul className="text-xs text-gray-500 space-y-1">
                <li>• Cuenta de Instagram Business o Creator</li>
                <li>• Conectada a una Página de Facebook</li>
                <li>• Permisos de mensajes activados</li>
              </ul>
            </div>

            {/* Optional website input */}
            <div className="mt-6 pt-6 border-t border-gray-800">
              <p className="text-sm text-gray-500 text-center mb-3">
                Opcional: añade tu website para más contexto
              </p>
              <div className="relative">
                <Globe className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
                <Input
                  type="url"
                  placeholder="https://tuwebsite.com"
                  value={websiteUrl}
                  onChange={(e) => setWebsiteUrl(e.target.value)}
                  className="pl-10 h-12 bg-gray-900 border-gray-700 text-white placeholder:text-gray-600 focus:border-fuchsia-500"
                />
              </div>
              <p className="text-xs text-gray-600 mt-1 text-center">
                Se scrapeará e indexará automáticamente
              </p>
            </div>

            {/* Future platforms */}
            <div className="space-y-3 mt-6">
              <p className="text-sm text-gray-500 text-center mb-3">
                Próximamente
              </p>

              <Button
                variant="outline"
                className="w-full h-12 border-gray-800 bg-gray-900/50 text-gray-400 hover:bg-gray-800"
                disabled
              >
                <Youtube className="mr-3 h-5 w-5 text-red-500" />
                YouTube
                <span className="ml-auto text-xs text-gray-600">Coming soon</span>
              </Button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // LOADING SCREEN - Shows while redirecting to OAuth
  if (step === 'loading') {
    return (
      <div className="min-h-screen bg-black flex flex-col">
        {/* Header with logo top left */}
        <div className="p-6">
          <img
            src="/clonnect-logo.png"
            alt="Clonnect"
            className="w-12 h-12 object-contain animate-pulse"
          />
        </div>

        <div className="flex-1 flex flex-col justify-center px-6 pb-12 max-w-md mx-auto w-full">
          {/* Header */}
          <div className="text-center mb-8">
            <h1 className="text-2xl md:text-3xl font-bold text-white">
              Redirigiendo a Instagram...
            </h1>
            <p className="text-gray-400 mt-2">
              Autoriza el acceso para continuar
            </p>
          </div>

          {/* Indeterminate progress bar */}
          <div className="mb-8">
            <div className="w-full bg-gray-800 rounded-full h-2 overflow-hidden">
              <div className="bg-gradient-to-r from-purple-600 to-fuchsia-500 h-2 rounded-full animate-pulse w-full" />
            </div>
          </div>

          <div className="text-center">
            <Loader2 className="w-8 h-8 text-fuchsia-500 animate-spin mx-auto" />
          </div>
        </div>
      </div>
    );
  }

  // COMPLETE SCREEN - After OAuth success, backend handles onboarding in background
  if (step === 'complete') {
    return (
      <div className="min-h-screen bg-black flex flex-col">
        {/* Header with logo top left */}
        <div className="p-6">
          <img
            src="/clonnect-logo.png"
            alt="Clonnect"
            className="w-12 h-12 object-contain"
          />
        </div>

        <div className="flex-1 flex flex-col justify-center px-6 pb-12 max-w-md mx-auto w-full animate-fade-in">
          {/* Header */}
          <div className="text-center mb-8">
            <div className="text-5xl mb-4">🎉</div>
            <h1 className="text-2xl md:text-3xl font-bold text-white">
              ¡Conectado con éxito!
            </h1>
            <p className="text-gray-400 mt-2">
              Tu clon se está configurando automáticamente
            </p>
          </div>

          {/* Processing info */}
          <div className="bg-gray-900/50 rounded-xl p-4 mb-6 border border-gray-800">
            <div className="space-y-3">
              <div className="flex items-center gap-3 text-sm">
                <Loader2 className="w-4 h-4 text-fuchsia-500 animate-spin" />
                <span className="text-gray-300">Scrapeando tus posts...</span>
              </div>
              <div className="flex items-center gap-3 text-sm">
                <div className="w-4 h-4 rounded-full bg-gray-700" />
                <span className="text-gray-500">Analizando tu tono y estilo</span>
              </div>
              <div className="flex items-center gap-3 text-sm">
                <div className="w-4 h-4 rounded-full bg-gray-700" />
                <span className="text-gray-500">Indexando contenido en RAG</span>
              </div>
              <div className="flex items-center gap-3 text-sm">
                <div className="w-4 h-4 rounded-full bg-gray-700" />
                <span className="text-gray-500">Importando conversaciones</span>
              </div>
              <div className="flex items-center gap-3 text-sm">
                <div className="w-4 h-4 rounded-full bg-gray-700" />
                <span className="text-gray-500">Activando tu bot</span>
              </div>
            </div>
          </div>

          {/* Info */}
          <div className="bg-purple-500/10 border border-purple-500/30 rounded-xl p-4 mb-6">
            <p className="text-sm text-gray-300">
              💡 El proceso continúa en segundo plano. Puedes ir al dashboard mientras se completa.
            </p>
          </div>

          {/* CTA */}
          <Button
            onClick={() => navigate('/dashboard')}
            size="lg"
            className="w-full h-14 text-lg bg-gradient-to-r from-purple-600 to-fuchsia-500 hover:from-purple-700 hover:to-fuchsia-600 transition-all"
          >
            Ir al Dashboard →
          </Button>
        </div>
      </div>
    );
  }

  return null;
}

// StepItem and StatCard components removed - no longer needed for OAuth-only flow
