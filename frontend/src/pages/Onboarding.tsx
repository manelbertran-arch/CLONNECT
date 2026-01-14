import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, getCreatorId } from '../services/api';
import { ArrowRight, Check } from 'lucide-react';

export default function Onboarding() {
  const [instagram, setInstagram] = useState('');
  const [website, setWebsite] = useState('');
  const [loading, setLoading] = useState(false);
  const [step, setStep] = useState<'form' | 'loading' | 'success'>('form');
  const [stats, setStats] = useState<any>(null);
  const [error, setError] = useState('');
  const navigate = useNavigate();

  // P1 FIX: Use getCreatorId helper (handles fallback and migration)
  const creatorId = getCreatorId();
  console.log('[Onboarding] Using creator_id:', creatorId);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!instagram) {
      setError('Instagram es requerido');
      return;
    }

    setLoading(true);
    setStep('loading');
    setError('');

    try {
      const response = await api.post('/onboarding/manual-setup', {
        creator_id: creatorId,
        instagram_username: instagram.replace('@', ''),
        website_url: website || null
      });

      // Check if backend returned success: false
      if (response.data.success === false) {
        const errorMsg = response.data.errors?.join(', ') || 'Error durante el onboarding';
        setError(errorMsg);
        setStep('form');
        return;
      }

      setStats(response.data);
      setStep('success');
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Error al crear el clon');
      setStep('form');
    } finally {
      setLoading(false);
    }
  };

  const goToDashboard = () => {
    navigate('/dashboard');
  };

  // Background orbs component
  const BackgroundOrbs = () => (
    <>
      <div
        style={{
          position: 'fixed',
          top: '10%',
          left: '10%',
          width: '400px',
          height: '400px',
          background: 'radial-gradient(circle, rgba(168, 85, 247, 0.15) 0%, transparent 70%)',
          borderRadius: '50%',
          filter: 'blur(60px)',
          pointerEvents: 'none'
        }}
      />
      <div
        style={{
          position: 'fixed',
          bottom: '10%',
          right: '10%',
          width: '300px',
          height: '300px',
          background: 'radial-gradient(circle, rgba(99, 102, 241, 0.15) 0%, transparent 70%)',
          borderRadius: '50%',
          filter: 'blur(60px)',
          pointerEvents: 'none'
        }}
      />
    </>
  );

  // FORMULARIO
  if (step === 'form') {
    return (
      <div
        className="min-h-screen flex items-center justify-center"
        style={{ background: '#09090b' }}
      >
        <BackgroundOrbs />

        <div
          className="p-8 rounded-2xl w-full max-w-md relative z-10"
          style={{
            background: '#0f0f14',
            border: '1px solid rgba(255, 255, 255, 0.08)'
          }}
        >
          <h1
            className="text-2xl font-bold text-center mb-2"
            style={{
              background: 'linear-gradient(135deg, #a855f7, #6366f1)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent'
            }}
          >
            Crear tu clon
          </h1>
          <p className="text-center mb-6" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>
            Introduce tus datos para analizar tu contenido
          </p>

          {error && (
            <div
              className="p-3 rounded-lg mb-4 text-center"
              style={{
                background: 'rgba(239, 68, 68, 0.1)',
                border: '1px solid rgba(239, 68, 68, 0.3)',
                color: '#ef4444'
              }}
            >
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit}>
            <label className="block mb-2" style={{ color: 'rgba(255, 255, 255, 0.7)' }}>
              Tu Instagram *
            </label>
            <input
              type="text"
              placeholder="@usuario"
              value={instagram}
              onChange={(e) => setInstagram(e.target.value)}
              className="w-full p-4 mb-4 rounded-xl text-white outline-none transition-all"
              style={{
                background: 'rgba(255, 255, 255, 0.05)',
                border: '1px solid rgba(255, 255, 255, 0.08)'
              }}
              onFocus={(e) => e.target.style.borderColor = 'rgba(168, 85, 247, 0.5)'}
              onBlur={(e) => e.target.style.borderColor = 'rgba(255, 255, 255, 0.08)'}
              required
            />

            <label className="block mb-2" style={{ color: 'rgba(255, 255, 255, 0.7)' }}>
              Tu website (opcional)
            </label>
            <input
              type="url"
              placeholder="https://tuwebsite.com"
              value={website}
              onChange={(e) => setWebsite(e.target.value)}
              className="w-full p-4 mb-6 rounded-xl text-white outline-none transition-all"
              style={{
                background: 'rgba(255, 255, 255, 0.05)',
                border: '1px solid rgba(255, 255, 255, 0.08)'
              }}
              onFocus={(e) => e.target.style.borderColor = 'rgba(168, 85, 247, 0.5)'}
              onBlur={(e) => e.target.style.borderColor = 'rgba(255, 255, 255, 0.08)'}
            />

            <button
              type="submit"
              disabled={loading}
              className="w-full p-4 text-white font-semibold rounded-xl transition-all hover:opacity-90 disabled:opacity-50 flex items-center justify-center gap-2"
              style={{
                background: 'linear-gradient(135deg, #a855f7, #6366f1)',
                boxShadow: '0 4px 20px rgba(168, 85, 247, 0.3)'
              }}
            >
              Crear mi clon
              <ArrowRight className="w-5 h-5" />
            </button>
          </form>
        </div>
      </div>
    );
  }

  // LOADING
  if (step === 'loading') {
    return (
      <div
        className="min-h-screen flex items-center justify-center"
        style={{ background: '#09090b' }}
      >
        <BackgroundOrbs />

        <div
          className="p-8 rounded-2xl w-full max-w-md text-center relative z-10"
          style={{
            background: '#0f0f14',
            border: '1px solid rgba(255, 255, 255, 0.08)'
          }}
        >
          <div
            className="w-12 h-12 border-4 rounded-full mx-auto mb-4 animate-spin"
            style={{
              borderColor: 'rgba(168, 85, 247, 0.2)',
              borderTopColor: '#a855f7'
            }}
          />
          <h2
            className="text-xl font-bold mb-2"
            style={{
              background: 'linear-gradient(135deg, #a855f7, #6366f1)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent'
            }}
          >
            Creando tu clon...
          </h2>
          <p style={{ color: 'rgba(255, 255, 255, 0.5)' }}>
            Analizando tu contenido de Instagram
          </p>
          <p className="text-sm mt-4" style={{ color: 'rgba(255, 255, 255, 0.3)' }}>
            Esto puede tardar 1-2 minutos
          </p>
        </div>
      </div>
    );
  }

  // SUCCESS
  if (step === 'success') {
    return (
      <div
        className="min-h-screen flex items-center justify-center"
        style={{ background: '#09090b' }}
      >
        <BackgroundOrbs />

        <div
          className="p-8 rounded-2xl w-full max-w-md text-center relative z-10"
          style={{
            background: '#0f0f14',
            border: '1px solid rgba(255, 255, 255, 0.08)'
          }}
        >
          {/* Success Icon */}
          <div className="flex justify-center mb-6">
            <div
              className="w-16 h-16 rounded-2xl flex items-center justify-center"
              style={{ background: 'linear-gradient(135deg, #22c55e, #16a34a)' }}
            >
              <Check className="w-8 h-8 text-white" />
            </div>
          </div>

          <h2
            className="text-2xl font-bold mb-2"
            style={{
              background: 'linear-gradient(135deg, #a855f7, #6366f1)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent'
            }}
          >
            ¡Tu clon está listo!
          </h2>
          <p className="mb-6" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>
            Hemos analizado tu contenido
          </p>

          {stats && (
            <div
              className="p-4 rounded-xl mb-6 text-left"
              style={{
                background: 'rgba(255, 255, 255, 0.03)',
                border: '1px solid rgba(255, 255, 255, 0.06)'
              }}
            >
              <p className="flex items-center gap-2 mb-2" style={{ color: 'rgba(255, 255, 255, 0.7)' }}>
                <span style={{ color: '#22c55e' }}>✓</span> Posts analizados: {stats.details?.posts_count || 50}
              </p>
              <p className="flex items-center gap-2 mb-2" style={{ color: 'rgba(255, 255, 255, 0.7)' }}>
                <span style={{ color: '#22c55e' }}>✓</span> Documentos RAG: {stats.details?.rag_documents || 'N/A'}
              </p>
              <p className="flex items-center gap-2" style={{ color: 'rgba(255, 255, 255, 0.7)' }}>
                <span style={{ color: '#22c55e' }}>✓</span> Perfil de tono creado
              </p>
            </div>
          )}

          <button
            onClick={goToDashboard}
            className="w-full p-4 text-white font-semibold rounded-xl transition-all hover:opacity-90 flex items-center justify-center gap-2"
            style={{
              background: 'linear-gradient(135deg, #a855f7, #6366f1)',
              boxShadow: '0 4px 20px rgba(168, 85, 247, 0.3)'
            }}
          >
            Ir al Dashboard
            <ArrowRight className="w-5 h-5" />
          </button>
        </div>
      </div>
    );
  }

  return null;
}
