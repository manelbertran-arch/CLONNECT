import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Instagram, Globe, Loader2, Check, AlertCircle } from 'lucide-react';
import { API_URL, setCreatorId, getCreatorId } from '../services/api';

type OnboardingStep = 'connect' | 'redirecting' | 'processing' | 'complete' | 'error';

export default function Onboarding() {
  const [step, setStep] = useState<OnboardingStep>('connect');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [websiteUrl, setWebsiteUrl] = useState('');

  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  // Generate or get creator_id for OAuth state
  const getOrCreateCreatorId = (): string => {
    const existing = getCreatorId();
    if (existing && existing !== 'demo_creator') {
      return existing;
    }
    return `user_${Date.now()}`;
  };

  // Check for OAuth callback on mount
  useEffect(() => {
    const success = searchParams.get('success');
    const errorParam = searchParams.get('error');
    const errorMessage = searchParams.get('message');
    const onboarding = searchParams.get('onboarding');

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
      setStep('error');
      return;
    }

    // Handle OAuth success
    if (success?.includes('instagram') && onboarding === 'started') {
      console.log('[Onboarding] OAuth success, backend processing...');
      setStep('processing');

      // Auto-redirect to dashboard after a few seconds
      setTimeout(() => {
        setStep('complete');
      }, 3000);
    }
  }, [searchParams]);

  // Auto-navigate to dashboard when complete
  useEffect(() => {
    if (step === 'complete') {
      const timer = setTimeout(() => navigate('/dashboard'), 2000);
      return () => clearTimeout(timer);
    }
  }, [step, navigate]);

  const handleConnectInstagram = async () => {
    const creatorId = getOrCreateCreatorId();

    console.log('[Onboarding] Starting Instagram OAuth for:', creatorId);
    console.log('[Onboarding] API_URL:', API_URL);

    setIsLoading(true);
    setError('');

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
        setStep('redirecting');

        // Redirect to Meta OAuth
        console.log('[Onboarding] Redirecting to:', data.auth_url);
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

  // CONNECT SCREEN - Main OAuth form
  if (step === 'connect' || step === 'error') {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: '#09090b' }}>
        {/* Background glow */}
        <div
          style={{
            position: 'fixed', top: '10%', left: '10%', width: '400px', height: '400px',
            background: 'radial-gradient(circle, rgba(168, 85, 247, 0.15) 0%, transparent 70%)',
            borderRadius: '50%', filter: 'blur(60px)', pointerEvents: 'none'
          }}
        />

        <div
          className="p-8 rounded-2xl w-full max-w-md relative z-10"
          style={{ background: '#0f0f14', border: '1px solid rgba(255, 255, 255, 0.08)' }}
        >
          {/* Title */}
          <h1
            className="text-2xl font-bold text-center mb-2"
            style={{
              background: 'linear-gradient(135deg, #a855f7, #6366f1)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent'
            }}
          >
            Conecta tu Instagram
          </h1>
          <p className="text-center mb-6" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>
            Tu clon aprenderá de tu contenido y responderá DMs automáticamente
          </p>

          {/* Error message */}
          {error && (
            <div
              className="p-4 rounded-xl mb-6 flex items-start gap-3"
              style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)' }}
            >
              <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" style={{ color: '#ef4444' }} />
              <span style={{ color: '#ef4444' }}>{error}</span>
            </div>
          )}

          {/* Main OAuth Button */}
          <button
            onClick={handleConnectInstagram}
            disabled={isLoading}
            className="w-full p-4 text-white font-semibold rounded-xl flex items-center justify-center gap-3 mb-4 transition-all hover:scale-[1.02] disabled:opacity-50 disabled:hover:scale-100"
            style={{
              background: 'linear-gradient(135deg, #a855f7, #6366f1)',
              boxShadow: '0 4px 20px rgba(168, 85, 247, 0.3)'
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

          <p className="text-center text-sm mb-6" style={{ color: 'rgba(255, 255, 255, 0.4)' }}>
            Conecta tu cuenta Business/Creator para acceso completo
          </p>

          {/* Requirements */}
          <div
            className="p-4 rounded-xl mb-6"
            style={{ background: 'rgba(255, 255, 255, 0.03)', border: '1px solid rgba(255, 255, 255, 0.06)' }}
          >
            <p className="text-sm mb-2" style={{ color: 'rgba(255, 255, 255, 0.6)' }}>Requisitos:</p>
            <ul className="space-y-1 text-sm" style={{ color: 'rgba(255, 255, 255, 0.4)' }}>
              <li>• Cuenta de Instagram Business o Creator</li>
              <li>• Conectada a una Página de Facebook</li>
              <li>• Permisos de mensajes activados</li>
            </ul>
          </div>

          {/* Optional Website */}
          <div className="pt-4" style={{ borderTop: '1px solid rgba(255, 255, 255, 0.08)' }}>
            <p className="text-sm text-center mb-3" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>
              Añade tu website (opcional)
            </p>
            <div className="relative">
              <Globe className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4" style={{ color: 'rgba(255, 255, 255, 0.3)' }} />
              <input
                type="url"
                placeholder="https://tuwebsite.com"
                value={websiteUrl}
                onChange={(e) => setWebsiteUrl(e.target.value)}
                className="w-full p-4 pl-11 rounded-xl text-white outline-none"
                style={{ background: 'rgba(255, 255, 255, 0.05)', border: '1px solid rgba(255, 255, 255, 0.08)' }}
              />
            </div>
            <p className="text-xs text-center mt-2" style={{ color: 'rgba(255, 255, 255, 0.4)' }}>
              Tu clon podrá hablar de tus productos, servicios y contenido web. Cuanto más contenido, más se parecerá a ti.
            </p>
          </div>
        </div>
      </div>
    );
  }

  // REDIRECTING SCREEN
  if (step === 'redirecting') {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: '#09090b' }}>
        <div
          style={{
            position: 'fixed', top: '10%', left: '10%', width: '400px', height: '400px',
            background: 'radial-gradient(circle, rgba(168, 85, 247, 0.15) 0%, transparent 70%)',
            borderRadius: '50%', filter: 'blur(60px)', pointerEvents: 'none'
          }}
        />
        <div className="text-center relative z-10">
          <Loader2 className="w-12 h-12 animate-spin mx-auto mb-4" style={{ color: '#a855f7' }} />
          <h2 className="text-xl font-semibold text-white mb-2">Redirigiendo a Instagram...</h2>
          <p style={{ color: 'rgba(255, 255, 255, 0.5)' }}>Autoriza el acceso para continuar</p>
        </div>
      </div>
    );
  }

  // PROCESSING SCREEN - After OAuth callback, backend is working
  if (step === 'processing') {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: '#09090b' }}>
        <div
          style={{
            position: 'fixed', top: '10%', left: '10%', width: '400px', height: '400px',
            background: 'radial-gradient(circle, rgba(168, 85, 247, 0.15) 0%, transparent 70%)',
            borderRadius: '50%', filter: 'blur(60px)', pointerEvents: 'none'
          }}
        />
        <div
          className="p-8 rounded-2xl w-full max-w-md relative z-10 text-center"
          style={{ background: '#0f0f14', border: '1px solid rgba(255, 255, 255, 0.08)' }}
        >
          <div className="text-4xl mb-4">🎉</div>
          <h2 className="text-2xl font-bold text-white mb-2">¡Conectado con éxito!</h2>
          <p className="mb-6" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>
            Tu clon se está configurando automáticamente
          </p>

          {/* Processing steps */}
          <div
            className="p-4 rounded-xl mb-6 text-left"
            style={{ background: 'rgba(255, 255, 255, 0.03)', border: '1px solid rgba(255, 255, 255, 0.06)' }}
          >
            <div className="space-y-3">
              <div className="flex items-center gap-3">
                <Loader2 className="w-4 h-4 animate-spin" style={{ color: '#a855f7' }} />
                <span style={{ color: 'rgba(255, 255, 255, 0.7)' }}>Scrapeando tus posts...</span>
              </div>
              <div className="flex items-center gap-3">
                <div className="w-4 h-4 rounded-full" style={{ background: 'rgba(255, 255, 255, 0.2)' }} />
                <span style={{ color: 'rgba(255, 255, 255, 0.4)' }}>Analizando tu tono y estilo</span>
              </div>
              <div className="flex items-center gap-3">
                <div className="w-4 h-4 rounded-full" style={{ background: 'rgba(255, 255, 255, 0.2)' }} />
                <span style={{ color: 'rgba(255, 255, 255, 0.4)' }}>Importando conversaciones</span>
              </div>
              <div className="flex items-center gap-3">
                <div className="w-4 h-4 rounded-full" style={{ background: 'rgba(255, 255, 255, 0.2)' }} />
                <span style={{ color: 'rgba(255, 255, 255, 0.4)' }}>Activando tu bot</span>
              </div>
            </div>
          </div>

          <p className="text-sm" style={{ color: 'rgba(255, 255, 255, 0.4)' }}>
            El proceso continúa en segundo plano...
          </p>
        </div>
      </div>
    );
  }

  // COMPLETE SCREEN
  if (step === 'complete') {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: '#09090b' }}>
        <div
          style={{
            position: 'fixed', top: '10%', left: '10%', width: '400px', height: '400px',
            background: 'radial-gradient(circle, rgba(34, 197, 94, 0.15) 0%, transparent 70%)',
            borderRadius: '50%', filter: 'blur(60px)', pointerEvents: 'none'
          }}
        />
        <div
          className="p-10 rounded-2xl w-full max-w-md text-center relative z-10"
          style={{ background: '#0f0f14', border: '1px solid rgba(34, 197, 94, 0.2)' }}
        >
          <div className="flex justify-center mb-6">
            <div
              className="w-20 h-20 rounded-full flex items-center justify-center"
              style={{ background: 'linear-gradient(135deg, #22c55e, #16a34a)' }}
            >
              <Check className="w-10 h-10 text-white" strokeWidth={3} />
            </div>
          </div>

          <h2
            className="text-2xl font-bold mb-3"
            style={{
              background: 'linear-gradient(135deg, #22c55e, #16a34a)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent'
            }}
          >
            ¡Tu clon está listo!
          </h2>

          <p className="mb-6" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>
            Redirigiendo al dashboard...
          </p>

          <div className="flex justify-center gap-1 mb-6">
            <div className="w-2 h-2 rounded-full animate-bounce" style={{ background: '#22c55e' }} />
            <div className="w-2 h-2 rounded-full animate-bounce" style={{ background: '#22c55e', animationDelay: '150ms' }} />
            <div className="w-2 h-2 rounded-full animate-bounce" style={{ background: '#22c55e', animationDelay: '300ms' }} />
          </div>

          <button
            onClick={() => navigate('/dashboard')}
            className="w-full p-4 text-white font-semibold rounded-xl"
            style={{ background: 'linear-gradient(135deg, #22c55e, #16a34a)', boxShadow: '0 4px 20px rgba(34, 197, 94, 0.3)' }}
          >
            Ir al Dashboard
          </button>
        </div>
      </div>
    );
  }

  return null;
}
