import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, getCreatorId } from '../services/api';

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

  // FORMULARIO
  if (step === 'form') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-900">
        <div className="bg-gray-800 p-8 rounded-lg w-full max-w-md">
          <h1 className="text-2xl font-bold text-white mb-2">Crear tu clon</h1>
          <p className="text-gray-400 mb-6">Introduce tus datos para analizar tu contenido</p>

          {error && <div className="bg-red-500 text-white p-2 rounded mb-4">{error}</div>}

          <form onSubmit={handleSubmit}>
            <label className="block text-gray-300 mb-2">Tu Instagram *</label>
            <input
              type="text"
              placeholder="@usuario"
              value={instagram}
              onChange={(e) => setInstagram(e.target.value)}
              className="w-full p-3 mb-4 bg-gray-700 text-white rounded"
              required
            />

            <label className="block text-gray-300 mb-2">Tu website (opcional)</label>
            <input
              type="url"
              placeholder="https://tuwebsite.com"
              value={website}
              onChange={(e) => setWebsite(e.target.value)}
              className="w-full p-3 mb-6 bg-gray-700 text-white rounded"
            />

            <button
              type="submit"
              disabled={loading}
              className="w-full p-3 bg-purple-600 text-white rounded hover:bg-purple-700 font-bold"
            >
              Crear mi clon
            </button>
          </form>
        </div>
      </div>
    );
  }

  // LOADING
  if (step === 'loading') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-900">
        <div className="bg-gray-800 p-8 rounded-lg w-full max-w-md text-center">
          <div className="animate-spin w-12 h-12 border-4 border-purple-500 border-t-transparent rounded-full mx-auto mb-4"></div>
          <h2 className="text-xl font-bold text-white mb-2">Creando tu clon...</h2>
          <p className="text-gray-400">Analizando tu contenido de Instagram</p>
          <p className="text-gray-500 text-sm mt-4">Esto puede tardar 1-2 minutos</p>
        </div>
      </div>
    );
  }

  // SUCCESS
  if (step === 'success') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-900">
        <div className="bg-gray-800 p-8 rounded-lg w-full max-w-md text-center">
          <div className="text-6xl mb-4">🎉</div>
          <h2 className="text-2xl font-bold text-white mb-2">¡Tu clon está listo!</h2>
          <p className="text-gray-400 mb-6">Hemos analizado tu contenido</p>

          {stats && (
            <div className="bg-gray-700 p-4 rounded mb-6 text-left">
              <p className="text-gray-300">✅ Posts analizados: {stats.details?.posts_count || 50}</p>
              <p className="text-gray-300">✅ Documentos RAG: {stats.details?.rag_documents || 'N/A'}</p>
              <p className="text-gray-300">✅ Perfil de tono creado</p>
            </div>
          )}

          <button
            onClick={goToDashboard}
            className="w-full p-3 bg-green-600 text-white rounded hover:bg-green-700 font-bold"
          >
            Ir al Dashboard
          </button>
        </div>
      </div>
    );
  }

  return null;
}
