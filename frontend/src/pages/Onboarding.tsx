import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, getCreatorId } from '../services/api';
import { ArrowRight, Check, Instagram, Globe, Brain, MessageSquare, BarChart3, Zap, Rocket } from 'lucide-react';

// Processing steps configuration
const processingSteps = [
  { id: 'connect', icon: Instagram, label: 'Conectando con Instagram', detail: 'Accediendo a tu perfil...' },
  { id: 'posts', icon: Instagram, label: 'Analizando posts', detail: 'Extrayendo contenido...' },
  { id: 'website', icon: Globe, label: 'Escaneando website', detail: 'Procesando páginas...' },
  { id: 'brain', icon: Brain, label: 'Entrenando tu clon', detail: 'Aprendiendo tu estilo...' },
  { id: 'rag', icon: MessageSquare, label: 'Base de conocimiento', detail: 'Indexando documentos...' },
  { id: 'metrics', icon: BarChart3, label: 'Configurando métricas', detail: 'Preparando dashboard...' },
  { id: 'bot', icon: Zap, label: 'Activando bot', detail: 'Tu clon está casi listo...' },
];

export default function Onboarding() {
  const [instagram, setInstagram] = useState('');
  const [website, setWebsite] = useState('');
  const [loading, setLoading] = useState(false);
  const [step, setStep] = useState<'form' | 'loading' | 'success'>('form');
  const [error, setError] = useState('');
  const [currentProcessStep, setCurrentProcessStep] = useState(0);
  const [logLines, setLogLines] = useState<string[]>([]);
  const navigate = useNavigate();

  const creatorId = getCreatorId();

  // Auto-navigate to dashboard when step is success
  useEffect(() => {
    if (step === 'success') {
      const timer = setTimeout(() => {
        navigate('/dashboard');
      }, 5000);
      return () => clearTimeout(timer);
    }
  }, [step, navigate]);

  // Simulated streaming logs during loading - 10 seconds
  useEffect(() => {
    if (step !== 'loading') return;

    const igUsername = (instagram || '').replace('@', '') || 'usuario';
    const logs = [
      'Iniciando conexión segura...',
      'Autenticando con Instagram API...',
      'Obteniendo perfil de @' + igUsername,
      'Descargando posts...',
      'Analizando contenido...',
      'Extrayendo patrones de comunicación...',
      'Procesando engagement metrics...',
      website ? 'Escaneando ' + website + '...' : 'Preparando análisis...',
      'Inicializando modelo de lenguaje...',
      'Entrenando perfil de personalidad...',
      'Calibrando tono de voz...',
      'Generando embeddings...',
      'Indexando documentos en RAG...',
      'Configurando respuestas automáticas...',
      'Preparando métricas del dashboard...',
      'Activando sistema de leads...',
      'Configurando nurturing...',
      'Verificando configuración...',
      'Activando bot...',
      '¡Proceso completado!'
    ];

    let currentLog = 0;
    // 20 logs at 500ms = 10 seconds
    const interval = setInterval(() => {
      if (currentLog < logs.length) {
        setLogLines(prev => [...prev.slice(-6), logs[currentLog]]);
        currentLog++;
      }
    }, 500);

    // Progress through steps - 7 steps over 10 seconds = ~1.4s per step
    const stepInterval = setInterval(() => {
      setCurrentProcessStep(prev => {
        if (prev < processingSteps.length - 1) return prev + 1;
        return prev;
      });
    }, 1400);

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
    const MIN_LOADING_TIME = 10000; // 10 seconds minimum

    try {
      const response = await api.post('/onboarding/quick-setup', {
        creator_id: creatorId,
        instagram_username: (instagram || '').replace('@', ''),
        website_url: website || null
      });

      if (response.data.success === false) {
        const errorMsg = response.data.errors?.join(', ') || 'Error durante el onboarding';
        setError(errorMsg);
        setStep('form');
        setLoading(false);
        return;
      }

      // Wait for minimum loading time
      const elapsed = Date.now() - startTime;
      const remainingTime = Math.max(0, MIN_LOADING_TIME - elapsed);

      setTimeout(() => {
        setLoading(false);
        setStep('success');
      }, remainingTime);

    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Error al crear el clon');
      setStep('form');
      setLoading(false);
    }
  };

  // FORM STATE
  if (step === 'form') {
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
              style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)', color: '#ef4444' }}
            >
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit}>
            <label className="block mb-2" style={{ color: 'rgba(255, 255, 255, 0.7)' }}>Tu Instagram *</label>
            <input
              type="text"
              id="onboarding-instagram"
              name="instagram"
              placeholder="@usuario"
              value={instagram}
              onChange={(e) => setInstagram(e.target.value)}
              autoComplete="username"
              className="w-full p-4 mb-4 rounded-xl text-white outline-none"
              style={{ background: 'rgba(255, 255, 255, 0.05)', border: '1px solid rgba(255, 255, 255, 0.08)' }}
              required
            />

            <label className="block mb-2" style={{ color: 'rgba(255, 255, 255, 0.7)' }}>Tu website (opcional)</label>
            <input
              type="text"
              id="onboarding-website"
              name="website"
              placeholder="https://tuwebsite.com"
              value={website}
              onChange={(e) => setWebsite(e.target.value)}
              autoComplete="on"
              className="w-full p-4 mb-6 rounded-xl text-white outline-none"
              style={{ background: 'rgba(255, 255, 255, 0.05)', border: '1px solid rgba(255, 255, 255, 0.08)' }}
            />

            <button
              type="submit"
              disabled={loading}
              className="w-full p-4 text-white font-semibold rounded-xl flex items-center justify-center gap-2"
              style={{ background: 'linear-gradient(135deg, #a855f7, #6366f1)', boxShadow: '0 4px 20px rgba(168, 85, 247, 0.3)' }}
            >
              Crear mi clon
              <ArrowRight className="w-5 h-5" />
            </button>
          </form>
        </div>
      </div>
    );
  }

  // LOADING STATE
  if (step === 'loading') {
    const currentStepData = processingSteps[currentProcessStep] || processingSteps[0];
    const progress = ((currentProcessStep + 1) / processingSteps.length) * 100;

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
          className="p-8 rounded-2xl w-full max-w-2xl relative z-10"
          style={{ background: '#0f0f14', border: '1px solid rgba(255, 255, 255, 0.08)' }}
        >
          <div className="flex items-center gap-3 mb-6">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #a855f7, #6366f1)' }}>
              <Brain className="w-5 h-5 text-white" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-white">Creando tu clon de IA</h2>
              <p className="text-sm" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>@{(instagram || '').replace('@', '') || 'usuario'}</p>
            </div>
          </div>

          <div className="mb-6">
            <div className="flex justify-between text-sm mb-2">
              <span style={{ color: 'rgba(255, 255, 255, 0.7)' }}>{currentStepData.label}</span>
              <span style={{ color: '#a855f7' }}>{Math.round(progress)}%</span>
            </div>
            <div className="h-2 rounded-full overflow-hidden" style={{ background: 'rgba(255, 255, 255, 0.1)' }}>
              <div className="h-full rounded-full transition-all duration-500" style={{ width: `${progress}%`, background: 'linear-gradient(90deg, #a855f7, #6366f1)' }} />
            </div>
          </div>

          <div className="grid grid-cols-4 gap-2 mb-6">
            {processingSteps.slice(0, 4).map((s, i) => {
              const Icon = s.icon;
              const isActive = i === currentProcessStep;
              const isDone = i < currentProcessStep;
              return (
                <div key={s.id} className="flex flex-col items-center gap-2 p-3 rounded-lg" style={{ background: isActive ? 'rgba(168, 85, 247, 0.1)' : 'transparent' }}>
                  <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: isDone ? 'rgba(34, 197, 94, 0.2)' : isActive ? 'rgba(168, 85, 247, 0.2)' : 'rgba(255, 255, 255, 0.05)' }}>
                    {isDone ? <Check className="w-4 h-4" style={{ color: '#22c55e' }} /> : <Icon className="w-4 h-4" style={{ color: isActive ? '#a855f7' : 'rgba(255, 255, 255, 0.4)' }} />}
                  </div>
                  <span className="text-xs text-center" style={{ color: isDone ? '#22c55e' : isActive ? '#a855f7' : 'rgba(255, 255, 255, 0.4)' }}>{s.label.split(' ').slice(0, 2).join(' ')}</span>
                </div>
              );
            })}
          </div>

          <div className="rounded-xl p-4 font-mono text-sm" style={{ background: 'rgba(0, 0, 0, 0.3)', border: '1px solid rgba(255, 255, 255, 0.05)' }}>
            <div className="space-y-1 h-36 overflow-hidden">
              {logLines.map((line, i) => (
                <div key={i} className="flex items-start gap-2" style={{ opacity: i === logLines.length - 1 ? 1 : 0.6 }}>
                  <span style={{ color: '#a855f7' }}>{'>'}</span>
                  <span style={{ color: i === logLines.length - 1 ? '#22c55e' : 'rgba(255, 255, 255, 0.6)' }}>{line}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="mt-4 flex items-center justify-center gap-2">
            <div className="w-2 h-2 rounded-full animate-pulse" style={{ background: '#a855f7' }} />
            <span className="text-sm" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>{currentStepData.detail}</span>
          </div>
        </div>
      </div>
    );
  }

  // SUCCESS STATE
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
        className="p-10 rounded-3xl w-full max-w-md text-center relative z-10"
        style={{ background: '#0f0f14', border: '1px solid rgba(168, 85, 247, 0.2)', boxShadow: '0 0 60px rgba(168, 85, 247, 0.1)' }}
      >
        <div className="flex justify-center mb-6">
          <div className="w-20 h-20 rounded-full flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #22c55e, #16a34a)' }}>
            <Check className="w-10 h-10 text-white" strokeWidth={3} />
          </div>
        </div>

        <h2 className="text-3xl font-bold mb-3" style={{ background: 'linear-gradient(135deg, #a855f7, #6366f1)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
          ¡Tu clon está listo!
        </h2>

        <p className="text-lg mb-6" style={{ color: 'rgba(255, 255, 255, 0.6)' }}>
          Tu asistente de IA está configurado y listo para responder
        </p>

        <div className="grid grid-cols-3 gap-3 mb-6">
          <div className="p-3 rounded-xl text-white" style={{ background: 'rgba(168, 85, 247, 0.1)' }}>
            <div className="text-xl font-bold">24/7</div>
            <div className="text-xs" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>Activo</div>
          </div>
          <div className="p-3 rounded-xl text-white" style={{ background: 'rgba(99, 102, 241, 0.1)' }}>
            <div className="text-xl font-bold">IA</div>
            <div className="text-xs" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>Entrenada</div>
          </div>
          <div className="p-3 rounded-xl text-white" style={{ background: 'rgba(34, 197, 94, 0.1)' }}>
            <div className="text-xl font-bold">100%</div>
            <div className="text-xs" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>Listo</div>
          </div>
        </div>

        <div className="flex items-center justify-center gap-2 mb-4">
          <span className="text-sm" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>Redirigiendo al dashboard</span>
          <div className="flex gap-1">
            <div className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: '#a855f7' }} />
            <div className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: '#a855f7', animationDelay: '150ms' }} />
            <div className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: '#a855f7', animationDelay: '300ms' }} />
          </div>
        </div>

        <button
          onClick={() => navigate('/dashboard')}
          className="w-full p-4 text-white font-semibold rounded-xl"
          style={{ background: 'linear-gradient(135deg, #a855f7, #6366f1)', boxShadow: '0 4px 20px rgba(168, 85, 247, 0.3)' }}
        >
          Ir al Dashboard
        </button>
      </div>
    </div>
  );
}
