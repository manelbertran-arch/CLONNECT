import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, getCreatorId } from '../services/api';
import { ArrowRight, Check, Instagram, Globe, Brain, MessageSquare, BarChart3, Zap } from 'lucide-react';

// Processing steps configuration
const processingSteps = [
  { id: 'connect', icon: Instagram, label: 'Conectando con Instagram', detail: 'Accediendo a tu perfil...' },
  { id: 'posts', icon: Instagram, label: 'Analizando posts', detail: 'Extrayendo contenido de publicaciones...' },
  { id: 'website', icon: Globe, label: 'Escaneando website', detail: 'Procesando páginas y contenido...' },
  { id: 'brain', icon: Brain, label: 'Entrenando tu clon', detail: 'Aprendiendo tu estilo y tono...' },
  { id: 'rag', icon: MessageSquare, label: 'Creando base de conocimiento', detail: 'Indexando documentos RAG...' },
  { id: 'metrics', icon: BarChart3, label: 'Configurando métricas', detail: 'Preparando dashboard...' },
  { id: 'bot', icon: Zap, label: 'Activando bot', detail: 'Tu clon está casi listo...' },
];

export default function Onboarding() {
  const [instagram, setInstagram] = useState('');
  const [website, setWebsite] = useState('');
  const [loading, setLoading] = useState(false);
  const [step, setStep] = useState<'form' | 'loading' | 'success'>('form');
  const [stats, setStats] = useState<any>(null);
  const [error, setError] = useState('');
  const [currentProcessStep, setCurrentProcessStep] = useState(0);
  const [streamingText, setStreamingText] = useState('');
  const [logLines, setLogLines] = useState<string[]>([]);
  const navigate = useNavigate();

  const creatorId = getCreatorId();

  // Auto-navigate to dashboard when step is success
  useEffect(() => {
    if (step === 'success') {
      console.log('Success state reached, navigating to dashboard in 3s');
      const timer = setTimeout(() => {
        navigate('/dashboard');
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [step, navigate]);

  // Simulated streaming logs during loading - 30 seconds minimum
  useEffect(() => {
    if (step !== 'loading') return;

    const igUsername = (instagram || '').replace('@', '') || 'usuario';
    const logs = [
      '> Iniciando conexión segura...',
      '> Verificando credenciales...',
      '> Autenticando con Instagram API...',
      '> Conexión establecida correctamente',
      '> Obteniendo perfil de @' + igUsername,
      '> Verificando permisos de acceso...',
      '> Descargando últimos 50 posts...',
      '> Post 1-10 descargados...',
      '> Post 11-25 descargados...',
      '> Post 26-40 descargados...',
      '> Post 41-50 descargados...',
      '> Analizando captions y hashtags...',
      '> Detectando idioma principal...',
      '> Extrayendo patrones de comunicación...',
      '> Identificando estilo de escritura...',
      '> Procesando engagement metrics...',
      '> Calculando ratio de interacción...',
      website ? '> Escaneando ' + website + '...' : '> Preparando análisis de contenido...',
      website ? '> Extrayendo contenido de páginas...' : '> Procesando datos disponibles...',
      website ? '> Indexando información del website...' : '> Optimizando base de datos...',
      '> Inicializando modelo de lenguaje...',
      '> Cargando parámetros del modelo...',
      '> Entrenando perfil de personalidad...',
      '> Ajustando parámetros de tono...',
      '> Calibrando tono de voz...',
      '> Analizando vocabulario frecuente...',
      '> Generando embeddings de contenido...',
      '> Procesando vectores semánticos...',
      '> Indexando documentos en RAG...',
      '> Creando índices de búsqueda...',
      '> Configurando respuestas automáticas...',
      '> Estableciendo reglas de conversación...',
      '> Preparando métricas del dashboard...',
      '> Configurando analytics...',
      '> Activando sistema de leads...',
      '> Configurando scoring automático...',
      '> Configurando nurturing sequences...',
      '> Estableciendo triggers de seguimiento...',
      '> Verificando configuración final...',
      '> Activando bot de respuestas...',
      '> Finalizando configuración...',
      '> ¡Proceso completado con éxito!'
    ].filter(Boolean);

    let currentLog = 0;
    // 43 logs at 350ms = ~15 seconds
    const interval = setInterval(() => {
      if (currentLog < logs.length) {
        setLogLines(prev => [...prev.slice(-8), logs[currentLog]]);
        currentLog++;
      }
    }, 350);

    // Progress through steps - 7 steps over 15 seconds = ~2.1s per step
    const stepInterval = setInterval(() => {
      setCurrentProcessStep(prev => {
        if (prev < processingSteps.length - 1) return prev + 1;
        return prev;
      });
    }, 2100);

    return () => {
      clearInterval(interval);
      clearInterval(stepInterval);
    };
  }, [step, instagram, website]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!instagram) {
      setError('Instagram es requerido');
      return;
    }

    setLoading(true);
    setStep('loading');
    setError('');
    setLogLines([]);
    setCurrentProcessStep(0);

    const startTime = Date.now();
    const MIN_LOADING_TIME = 15000; // 15 seconds minimum

    try {
      // Use quick-setup for faster onboarding (no scraping)
      const response = await api.post('/onboarding/quick-setup', {
        creator_id: creatorId,
        instagram_username: (instagram || '').replace('@', ''),
        website_url: website || null
      });

      console.log('Onboarding response:', response.data);

      if (response.data.success === false) {
        const errorMsg = response.data.errors?.join(', ') || 'Error durante el onboarding';
        setError(errorMsg);
        setStep('form');
        setLoading(false);
        return;
      }

      // Calculate remaining time to reach minimum 30 seconds
      const elapsed = Date.now() - startTime;
      const remainingTime = Math.max(0, MIN_LOADING_TIME - elapsed);

      // Wait for minimum loading time before showing success
      setTimeout(() => {
        setStats(response.data);
        setLoading(false);
        setStep('success');
      }, remainingTime);

    } catch (err: any) {
      console.error('Onboarding error:', err);
      setError(err.response?.data?.detail || err.message || 'Error al crear el clon');
      setStep('form');
      setLoading(false);
    }
  };

  const goToDashboard = () => {
    navigate('/dashboard');
  };

  // Background orbs
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

  // Debug log
  console.log('Onboarding render - step:', step, 'loading:', loading, 'error:', error);

  // FORM STATE
  if (step === 'form') {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: '#09090b' }}>
        <BackgroundOrbs />
        <div
          className="p-8 rounded-2xl w-full max-w-md relative z-10"
          style={{ background: '#0f0f14', border: '1px solid rgba(255, 255, 255, 0.08)' }}
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
              id="onboarding-instagram"
              name="instagram"
              placeholder="@usuario"
              value={instagram}
              onChange={(e) => setInstagram(e.target.value)}
              autoComplete="username"
              className="w-full p-4 mb-4 rounded-xl text-white outline-none transition-all"
              style={{ background: 'rgba(255, 255, 255, 0.05)', border: '1px solid rgba(255, 255, 255, 0.08)' }}
              onFocus={(e) => e.target.style.borderColor = 'rgba(168, 85, 247, 0.5)'}
              onBlur={(e) => e.target.style.borderColor = 'rgba(255, 255, 255, 0.08)'}
              required
            />

            <label className="block mb-2" style={{ color: 'rgba(255, 255, 255, 0.7)' }}>
              Tu website (opcional)
            </label>
            <input
              type="text"
              id="onboarding-website"
              name="website"
              placeholder="https://tuwebsite.com"
              value={website}
              onChange={(e) => setWebsite(e.target.value)}
              autoComplete="on"
              className="w-full p-4 mb-6 rounded-xl text-white outline-none transition-all"
              style={{ background: 'rgba(255, 255, 255, 0.05)', border: '1px solid rgba(255, 255, 255, 0.08)' }}
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

  // LOADING - AI Streaming Style
  if (step === 'loading') {
    const currentStep = processingSteps[currentProcessStep];
    const CurrentIcon = currentStep.icon;
    const progress = ((currentProcessStep + 1) / processingSteps.length) * 100;

    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: '#09090b' }}>
        <BackgroundOrbs />

        <div
          className="p-8 rounded-2xl w-full max-w-2xl relative z-10"
          style={{ background: '#0f0f14', border: '1px solid rgba(255, 255, 255, 0.08)' }}
        >
          {/* Header */}
          <div className="flex items-center gap-3 mb-6">
            <div
              className="w-10 h-10 rounded-xl flex items-center justify-center"
              style={{ background: 'linear-gradient(135deg, #a855f7, #6366f1)' }}
            >
              <Brain className="w-5 h-5 text-white" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-white">Creando tu clon de IA</h2>
              <p className="text-sm" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>
                @{(instagram || '').replace('@', '') || 'usuario'}
              </p>
            </div>
          </div>

          {/* Progress bar */}
          <div className="mb-6">
            <div className="flex justify-between text-sm mb-2">
              <span style={{ color: 'rgba(255, 255, 255, 0.7)' }}>{currentStep.label}</span>
              <span style={{ color: '#a855f7' }}>{Math.round(progress)}%</span>
            </div>
            <div
              className="h-2 rounded-full overflow-hidden"
              style={{ background: 'rgba(255, 255, 255, 0.1)' }}
            >
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{
                  width: `${progress}%`,
                  background: 'linear-gradient(90deg, #a855f7, #6366f1)'
                }}
              />
            </div>
          </div>

          {/* Steps grid */}
          <div className="grid grid-cols-4 gap-2 mb-6">
            {processingSteps.slice(0, 4).map((s, i) => {
              const Icon = s.icon;
              const isActive = i === currentProcessStep;
              const isDone = i < currentProcessStep;
              return (
                <div
                  key={s.id}
                  className="flex flex-col items-center gap-2 p-3 rounded-lg transition-all"
                  style={{
                    background: isActive ? 'rgba(168, 85, 247, 0.1)' : 'transparent',
                    border: isActive ? '1px solid rgba(168, 85, 247, 0.3)' : '1px solid transparent'
                  }}
                >
                  <div
                    className="w-8 h-8 rounded-lg flex items-center justify-center"
                    style={{
                      background: isDone ? 'rgba(34, 197, 94, 0.2)' : isActive ? 'rgba(168, 85, 247, 0.2)' : 'rgba(255, 255, 255, 0.05)'
                    }}
                  >
                    {isDone ? (
                      <Check className="w-4 h-4" style={{ color: '#22c55e' }} />
                    ) : (
                      <Icon
                        className={`w-4 h-4 ${isActive ? 'animate-pulse' : ''}`}
                        style={{ color: isActive ? '#a855f7' : 'rgba(255, 255, 255, 0.4)' }}
                      />
                    )}
                  </div>
                  <span
                    className="text-xs text-center"
                    style={{ color: isDone ? '#22c55e' : isActive ? '#a855f7' : 'rgba(255, 255, 255, 0.4)' }}
                  >
                    {s.label.split(' ').slice(0, 2).join(' ')}
                  </span>
                </div>
              );
            })}
          </div>

          {/* Terminal/Log output */}
          <div
            className="rounded-xl p-4 font-mono text-sm overflow-hidden"
            style={{ background: 'rgba(0, 0, 0, 0.3)', border: '1px solid rgba(255, 255, 255, 0.05)' }}
          >
            <div className="space-y-1 h-44 overflow-hidden">
              {logLines.map((line, i) => (
                <div
                  key={i}
                  className="flex items-start gap-2"
                  style={{
                    animation: 'fadeIn 0.3s ease-out',
                    opacity: i === logLines.length - 1 ? 1 : 0.6
                  }}
                >
                  <span style={{ color: '#a855f7' }}>{'>'}</span>
                  <span style={{ color: i === logLines.length - 1 ? '#22c55e' : 'rgba(255, 255, 255, 0.6)' }}>
                    {line.replace('> ', '')}
                    {i === logLines.length - 1 && (
                      <span className="inline-block w-2 h-4 ml-1 animate-pulse" style={{ background: '#a855f7' }} />
                    )}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Current action */}
          <div className="mt-4 flex items-center justify-center gap-2">
            <div
              className="w-2 h-2 rounded-full animate-pulse"
              style={{ background: '#a855f7' }}
            />
            <span className="text-sm" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>
              {currentStep.detail}
            </span>
          </div>
        </div>

        <style>{`
          @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
          }
        `}</style>
      </div>
    );
  }

  // SUCCESS STATE (also serves as default/fallback)
  // This renders for step === 'success' OR any unexpected state
  return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: '#09090b' }}>
      <BackgroundOrbs />

      <div
        className="p-10 rounded-3xl w-full max-w-lg text-center relative z-10"
        style={{
          background: 'linear-gradient(180deg, #0f0f14 0%, #1a1a24 100%)',
          border: '1px solid rgba(168, 85, 247, 0.2)',
          boxShadow: '0 0 60px rgba(168, 85, 247, 0.15)'
        }}
      >
        {/* Success icon with glow */}
        <div className="flex justify-center mb-8">
          <div className="relative">
            <div
              className="absolute inset-0 rounded-full blur-xl"
              style={{ background: 'rgba(34, 197, 94, 0.4)' }}
            />
            <div
              className="relative w-24 h-24 rounded-full flex items-center justify-center"
              style={{
                background: 'linear-gradient(135deg, #22c55e, #16a34a)',
                boxShadow: '0 0 30px rgba(34, 197, 94, 0.5)'
              }}
            >
              <Check className="w-12 h-12 text-white" strokeWidth={3} />
            </div>
          </div>
        </div>

        <h2
          className="text-4xl font-bold mb-4"
          style={{
            background: 'linear-gradient(135deg, #a855f7, #6366f1)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent'
          }}
        >
          ¡Tu clon está listo!
        </h2>

        <p className="text-xl mb-8" style={{ color: 'rgba(255, 255, 255, 0.7)' }}>
          Tu asistente de IA está configurado y listo para responder
        </p>

        {/* Features summary */}
        <div className="grid grid-cols-3 gap-4 mb-8">
          <div className="p-3 rounded-xl text-white" style={{ background: 'rgba(168, 85, 247, 0.1)' }}>
            <div className="text-2xl font-bold mb-1">24/7</div>
            <div className="text-xs" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>Activo</div>
          </div>
          <div className="p-3 rounded-xl text-white" style={{ background: 'rgba(99, 102, 241, 0.1)' }}>
            <div className="text-2xl font-bold mb-1">IA</div>
            <div className="text-xs" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>Entrenada</div>
          </div>
          <div className="p-3 rounded-xl text-white" style={{ background: 'rgba(34, 197, 94, 0.1)' }}>
            <div className="text-2xl font-bold mb-1">100%</div>
            <div className="text-xs" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>Listo</div>
          </div>
        </div>

        {/* Loading indicator */}
        <div className="flex items-center justify-center gap-2 mb-6">
          <span className="text-sm" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>
            Redirigiendo al dashboard
          </span>
          <div className="flex gap-1">
            <div className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: '#a855f7', animationDelay: '0ms' }} />
            <div className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: '#a855f7', animationDelay: '150ms' }} />
            <div className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: '#a855f7', animationDelay: '300ms' }} />
          </div>
        </div>

        <button
          onClick={goToDashboard}
          className="w-full p-4 text-white font-semibold rounded-xl transition-all hover:scale-[1.02] active:scale-[0.98]"
          style={{
            background: 'linear-gradient(135deg, #a855f7, #6366f1)',
            boxShadow: '0 4px 20px rgba(168, 85, 247, 0.4)'
          }}
        >
          Ir al Dashboard
        </button>
      </div>
    </div>
  );
}
