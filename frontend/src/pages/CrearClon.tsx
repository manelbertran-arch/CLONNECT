import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Instagram, Loader2, Check, AlertCircle, Sparkles } from 'lucide-react';
import { API_URL, setCreatorId, getCreatorId } from '../services/api';

type PageState = 'form' | 'redirecting' | 'connected';

export default function CrearClon() {
  const [state, setState] = useState<PageState>('form');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [instagramConnected, setInstagramConnected] = useState(false);

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
    const instagramParam = searchParams.get('instagram');

    // Handle OAuth errors
    if (errorParam) {
      console.log('[CrearClon] OAuth error:', errorParam, errorMessage);
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

    // Handle OAuth success (redirected back from Instagram)
    if (success?.includes('instagram') || instagramParam === 'connected') {
      console.log('[CrearClon] Instagram connected successfully!');
      setInstagramConnected(true);
      setState('connected');
    }
  }, [searchParams]);

  const handleConnectInstagram = async () => {
    const creatorId = getOrCreateCreatorId();

    console.log('[CrearClon] Starting Instagram OAuth for:', creatorId);
    console.log('[CrearClon] API_URL:', API_URL);

    setIsLoading(true);
    setError('');

    try {
      const response = await fetch(`${API_URL}/oauth/instagram/start?creator_id=${encodeURIComponent(creatorId)}`);

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Error al iniciar OAuth');
      }

      const data = await response.json();
      console.log('[CrearClon] OAuth response:', data);

      if (data.auth_url) {
        // Save creator_id before redirecting
        setCreatorId(creatorId);
        setState('redirecting');

        // Redirect to Meta OAuth
        console.log('[CrearClon] Redirecting to:', data.auth_url);
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

  const handleCreateClon = async () => {
    const creatorId = getCreatorId();

    if (!creatorId) {
      setError('No se encontró el ID del creador. Conecta Instagram primero.');
      return;
    }

    console.log('[CrearClon] Creating clone for:', creatorId);
    setIsLoading(true);
    setError('');

    try {
      // Start the clone creation process
      const response = await fetch(`${API_URL}/onboarding/start-clone`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          creator_id: creatorId,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Error al iniciar la creación del clon');
      }

      // Navigate to progress page
      navigate('/creando-clon');
    } catch (err) {
      console.error('Create clone error:', err);
      setError(err instanceof Error ? err.message : 'Error al crear el clon. Inténtalo de nuevo.');
      setIsLoading(false);
    }
  };

  // REDIRECTING SCREEN
  if (state === 'redirecting') {
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

  // MAIN FORM (with or without Instagram connected)
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
          Crea tu clon
        </h1>
        <p className="text-center mb-6" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>
          Conecta tu Instagram para entrenar tu clon de IA
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

        {/* Instagram Connection */}
        {instagramConnected ? (
          <div
            className="p-4 rounded-xl mb-6 flex items-center gap-3"
            style={{ background: 'rgba(34, 197, 94, 0.1)', border: '1px solid rgba(34, 197, 94, 0.3)' }}
          >
            <div className="p-2 rounded-lg" style={{ background: 'rgba(34, 197, 94, 0.2)' }}>
              <Check className="w-5 h-5" style={{ color: '#22c55e' }} />
            </div>
            <div className="flex-1">
              <p className="text-white font-medium">Instagram conectado</p>
              <p className="text-sm" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>
                Tu cuenta está lista
              </p>
            </div>
            <Instagram className="w-5 h-5" style={{ color: '#E4405F' }} />
          </div>
        ) : (
          <>
            <button
              onClick={handleConnectInstagram}
              disabled={isLoading}
              className="w-full p-4 text-white font-semibold rounded-xl flex items-center justify-center gap-3 mb-2 transition-all hover:scale-[1.02] disabled:opacity-50 disabled:hover:scale-100"
              style={{
                background: 'linear-gradient(135deg, #E4405F, #833AB4)',
                boxShadow: '0 4px 20px rgba(228, 64, 95, 0.3)'
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
              Cuenta Business/Creator requerida
            </p>
          </>
        )}

        {/* Info box */}
        <div
          className="p-4 rounded-xl mb-6"
          style={{ background: 'rgba(168, 85, 247, 0.05)', border: '1px solid rgba(168, 85, 247, 0.1)' }}
        >
          <p className="text-sm" style={{ color: 'rgba(255, 255, 255, 0.6)' }}>
            <Sparkles className="w-4 h-4 inline mr-2" style={{ color: '#a855f7' }} />
            Tu clon analizará tu contenido de Instagram para aprender tu estilo y responder como tú.
          </p>
        </div>

        {/* Create Clone Button */}
        <button
          onClick={handleCreateClon}
          disabled={!instagramConnected || isLoading}
          className="w-full p-4 text-white font-semibold rounded-xl flex items-center justify-center gap-3 transition-all hover:scale-[1.02] disabled:opacity-50 disabled:hover:scale-100 disabled:cursor-not-allowed"
          style={{
            background: instagramConnected
              ? 'linear-gradient(135deg, #a855f7, #6366f1)'
              : 'rgba(255, 255, 255, 0.1)',
            boxShadow: instagramConnected ? '0 4px 20px rgba(168, 85, 247, 0.3)' : 'none'
          }}
        >
          {isLoading ? (
            <>
              <Loader2 className="w-5 h-5 animate-spin" />
              Iniciando...
            </>
          ) : (
            <>
              <Sparkles className="w-5 h-5" />
              Crear mi clon
            </>
          )}
        </button>

        {!instagramConnected && (
          <p className="text-center text-sm mt-4" style={{ color: 'rgba(255, 255, 255, 0.4)' }}>
            Conecta Instagram para continuar
          </p>
        )}
      </div>
    </div>
  );
}
