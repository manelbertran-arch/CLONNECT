import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Instagram, Globe, Loader2, Check, AlertCircle, Sparkles } from 'lucide-react';
import { API_URL, setCreatorId, getCreatorId } from '../services/api';

export default function CrearClon() {
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [websiteUrl, setWebsiteUrl] = useState('');
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
          website_url: websiteUrl || null,
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

  // =========================================================================
  // VIEW 1: BEFORE OAuth - Only "Conectar Instagram" button
  // =========================================================================
  if (!instagramConnected) {
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
          <p className="text-center mb-8" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>
            Conecta tu Instagram para empezar
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

          {/* Instagram Connect Button */}
          <button
            onClick={handleConnectInstagram}
            disabled={isLoading}
            className="w-full p-4 text-white font-semibold rounded-xl flex items-center justify-center gap-3 mb-4 transition-all hover:scale-[1.02] disabled:opacity-50 disabled:hover:scale-100"
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

          <p className="text-center text-sm" style={{ color: 'rgba(255, 255, 255, 0.4)' }}>
            Cuenta Business/Creator requerida
          </p>

          {/* Info box */}
          <div
            className="p-4 rounded-xl mt-6"
            style={{ background: 'rgba(168, 85, 247, 0.05)', border: '1px solid rgba(168, 85, 247, 0.1)' }}
          >
            <p className="text-sm" style={{ color: 'rgba(255, 255, 255, 0.6)' }}>
              <Sparkles className="w-4 h-4 inline mr-2" style={{ color: '#a855f7' }} />
              Tu clon analizará tu contenido de Instagram para aprender tu estilo y responder como tú.
            </p>
          </div>
        </div>
      </div>
    );
  }

  // =========================================================================
  // VIEW 2: AFTER OAuth - Website field + "Crear mi clon" button
  // =========================================================================
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
          ¡Instagram conectado!
        </h1>
        <p className="text-center mb-6" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>
          Añade tu web (opcional) y crea tu clon
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

        {/* Instagram Connected Badge */}
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

        {/* Website URL (optional) */}
        <div className="mb-6">
          <p className="text-sm mb-3" style={{ color: 'rgba(255, 255, 255, 0.6)' }}>
            Tu website (opcional)
          </p>
          <div className="relative">
            <Globe className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4" style={{ color: 'rgba(255, 255, 255, 0.3)' }} />
            <input
              type="url"
              placeholder="https://tuwebsite.com"
              value={websiteUrl}
              onChange={(e) => setWebsiteUrl(e.target.value)}
              className="w-full p-4 pl-11 rounded-xl text-white outline-none focus:ring-2 focus:ring-purple-500"
              style={{ background: 'rgba(255, 255, 255, 0.05)', border: '1px solid rgba(255, 255, 255, 0.08)' }}
            />
          </div>
          <p className="text-xs mt-2" style={{ color: 'rgba(255, 255, 255, 0.4)' }}>
            Tu clon también aprenderá de tus productos y servicios web
          </p>
        </div>

        {/* Create Clone Button */}
        <button
          onClick={handleCreateClon}
          disabled={isLoading}
          className="w-full p-4 text-white font-semibold rounded-xl flex items-center justify-center gap-3 transition-all hover:scale-[1.02] disabled:opacity-50 disabled:hover:scale-100"
          style={{
            background: 'linear-gradient(135deg, #a855f7, #6366f1)',
            boxShadow: '0 4px 20px rgba(168, 85, 247, 0.3)'
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
      </div>
    </div>
  );
}
