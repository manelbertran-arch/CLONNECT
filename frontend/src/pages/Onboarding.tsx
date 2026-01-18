import { useState, useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { api, getCreatorId } from '../services/api';
import { ArrowRight, Check, Instagram, Globe, Brain, BarChart3, Database, Sparkles, Loader2, MessageCircle, User, HelpCircle, Link2 } from 'lucide-react';

// OAuth URL for Instagram connection
const API_URL = import.meta.env.VITE_API_URL || 'https://api-clonnect.up.railway.app';

// Processing steps mapped to backend steps
const processingSteps = [
  { id: 'instagram_scraping', icon: Instagram, label: 'Scrapeando Instagram', detail: 'Extrayendo posts de tu perfil...' },
  { id: 'website_scraping', icon: Globe, label: 'Escaneando website', detail: 'Analizando páginas...' },
  { id: 'product_detection', icon: BarChart3, label: 'Detectando productos', detail: 'Identificando ofertas...' },
  { id: 'tone_profile', icon: Brain, label: 'Generando ToneProfile', detail: 'Aprendiendo tu estilo de comunicación...' },
  { id: 'dm_history', icon: MessageCircle, label: 'Cargando historial DMs', detail: 'Importando conversaciones...' },
  { id: 'bio_extracted', icon: User, label: 'Extrayendo bio', detail: 'Obteniendo información del perfil...' },
  { id: 'faqs_generated', icon: HelpCircle, label: 'Generando FAQs', detail: 'Creando preguntas frecuentes...' },
  { id: 'creator_updated', icon: Sparkles, label: 'Finalizando configuración', detail: 'Activando tu clon...' },
];

// Status response type from backend
interface SetupStatus {
  status: 'in_progress' | 'completed' | 'failed' | 'not_found';
  progress?: number;
  current_step?: string;
  steps_completed?: string[];
  errors?: string[];
  warnings?: string[];
  result?: {
    instagram?: { posts_scraped: number; sanity_passed: number };
    website?: { products_detected: number };
    tone_profile?: { generated: boolean; confidence: number };
    rag?: { chunks_created: number };
    dms?: { conversations: number; messages: number; leads_created: number };
    bio?: { loaded: boolean };
    faqs?: { generated: number };
  };
}

export default function Onboarding() {
  const [searchParams] = useSearchParams();
  const [instagram, setInstagram] = useState('');
  const [website, setWebsite] = useState('');
  const [loading, setLoading] = useState(false);
  const [step, setStep] = useState<'form' | 'loading' | 'success'>('form');
  const [error, setError] = useState('');

  // Instagram OAuth connection state
  const [instagramConnected, setInstagramConnected] = useState(false);
  const [igUsername, setIgUsername] = useState('');

  // Real-time progress from backend
  const [progress, setProgress] = useState(0);
  const [displayProgress, setDisplayProgress] = useState(0);
  const [currentStep, setCurrentStep] = useState('');
  const [completedSteps, setCompletedSteps] = useState<string[]>([]);
  const [logLines, setLogLines] = useState<string[]>([]);
  const [stats, setStats] = useState<SetupStatus['result']>({});
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [startTime, setStartTime] = useState<number | null>(null);

  const pollingRef = useRef<NodeJS.Timeout | null>(null);
  const progressAnimRef = useRef<NodeJS.Timeout | null>(null);
  const elapsedTimerRef = useRef<NodeJS.Timeout | null>(null);
  const activityLogRef = useRef<NodeJS.Timeout | null>(null);
  const completedStepsRef = useRef<string[]>([]);
  const statsRef = useRef<SetupStatus['result']>({});
  const navigate = useNavigate();
  const creatorId = getCreatorId();

  // Check URL params for OAuth callback result
  useEffect(() => {
    const igConnected = searchParams.get('instagram');
    const username = searchParams.get('ig_username');
    const oauthError = searchParams.get('error');

    if (igConnected === 'connected') {
      setInstagramConnected(true);
      if (username) {
        setIgUsername(username);
        setInstagram(username);
      }
      // Clear URL params without reload
      window.history.replaceState({}, '', '/onboarding');
    }

    if (oauthError) {
      setError(`Error conectando Instagram: ${oauthError}`);
      window.history.replaceState({}, '', '/onboarding');
    }
  }, [searchParams]);

  // Keep refs in sync with state
  useEffect(() => {
    completedStepsRef.current = completedSteps;
  }, [completedSteps]);

  useEffect(() => {
    statsRef.current = stats;
  }, [stats]);

  // Animate progress smoothly (1% at a time)
  useEffect(() => {
    if (displayProgress < progress) {
      progressAnimRef.current = setTimeout(() => {
        setDisplayProgress(prev => Math.min(prev + 1, progress));
      }, 50); // 50ms per 1% = smooth animation
    }
    return () => {
      if (progressAnimRef.current) clearTimeout(progressAnimRef.current);
    };
  }, [displayProgress, progress]);

  // Auto-navigate to dashboard when step is success
  useEffect(() => {
    if (step === 'success') {
      const timer = setTimeout(() => navigate('/dashboard'), 2000);
      return () => clearTimeout(timer);
    }
  }, [step, navigate]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
      if (progressAnimRef.current) clearTimeout(progressAnimRef.current);
      if (elapsedTimerRef.current) clearInterval(elapsedTimerRef.current);
      if (activityLogRef.current) clearInterval(activityLogRef.current);
    };
  }, []);

  // Elapsed time counter when loading
  useEffect(() => {
    if (step === 'loading' && !elapsedTimerRef.current) {
      setStartTime(Date.now());
      elapsedTimerRef.current = setInterval(() => {
        setElapsedSeconds(prev => prev + 1);
      }, 1000);
    }
    if (step !== 'loading' && elapsedTimerRef.current) {
      clearInterval(elapsedTimerRef.current);
      elapsedTimerRef.current = null;
    }
  }, [step]);

  // Activity logs - show dynamic messages while waiting
  useEffect(() => {
    if (step === 'loading' && !activityLogRef.current) {
      const activityMessages = [
        'Conectando con Instagram API...',
        'Verificando permisos de acceso...',
        'Descargando metadatos de posts...',
        'Analizando engagement de publicaciones...',
        'Extrayendo captions y hashtags...',
        'Procesando imágenes y videos...',
        'Identificando patrones de contenido...',
        'Evaluando frecuencia de publicación...',
        'Analizando interacciones con seguidores...',
        'Detectando temas principales...',
        'Extrayendo vocabulario característico...',
        'Procesando emojis y estilo visual...',
        'Analizando horarios de publicación...',
        'Evaluando rendimiento de contenido...',
        'Clasificando tipos de posts...',
        'Detectando llamadas a la acción...',
        'Analizando menciones y etiquetas...',
        'Procesando stories destacadas...',
        'Evaluando engagement rate...',
        'Analizando comentarios recibidos...',
        'Extrayendo información de productos...',
        'Detectando precios y ofertas...',
        'Analizando landing pages...',
        'Procesando testimonios...',
        'Generando perfil de comunicación...',
        'Calibrando tono de respuestas...',
        'Indexando contenido para RAG...',
        'Creando embeddings semánticos...',
        'Optimizando base de conocimiento...',
        'Sincronizando con base de datos...',
        'Validando integridad de datos...',
        'Finalizando configuración...',
      ];
      let msgIndex = 0;
      activityLogRef.current = setInterval(() => {
        if (msgIndex < activityMessages.length) {
          addLog(`... ${activityMessages[msgIndex]}`);
          msgIndex++;
        } else {
          msgIndex = 0; // Loop back
        }
      }, 3000); // New message every 3 seconds
    }
    if (step !== 'loading' && activityLogRef.current) {
      clearInterval(activityLogRef.current);
      activityLogRef.current = null;
    }
  }, [step]);

  // Format elapsed time
  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  // Estimate remaining time based on progress
  const getEstimatedRemaining = () => {
    if (displayProgress <= 5 || elapsedSeconds < 5) return '~3:00';
    const estimatedTotal = (elapsedSeconds / displayProgress) * 100;
    const remaining = Math.max(0, estimatedTotal - elapsedSeconds);
    return formatTime(Math.ceil(remaining));
  };

  // Add log line helper
  const addLog = (message: string) => {
    setLogLines(prev => [...prev.slice(-15), message]);
  };

  // Poll backend for real progress - every 1 second
  const pollStatus = async () => {
    try {
      const response = await api.get<SetupStatus>(`/onboarding/full-auto-setup/${creatorId}/status`);
      const data = response.data;

      console.log('[Onboarding] Poll:', data);

      if (data.status === 'not_found') {
        // Process hasn't started yet or wrong creator_id
        return;
      }

      // Update progress from backend
      if (data.progress !== undefined) {
        setProgress(data.progress);
      }

      // Update current step
      if (data.current_step) {
        setCurrentStep(data.current_step);
      }

      // Update completed steps and add logs (use ref to avoid stale closure)
      if (data.steps_completed && data.steps_completed.length > completedStepsRef.current.length) {
        const newSteps = data.steps_completed.filter(s => !completedStepsRef.current.includes(s));

        newSteps.forEach(stepId => {
          const stepInfo = processingSteps.find(s => s.id === stepId);
          if (stepInfo) {
            addLog(`✓ ${stepInfo.label}`);
          }
        });

        setCompletedSteps([...data.steps_completed]);
      }

      // Update stats and add detail logs (use ref to avoid stale closure)
      if (data.result) {
        const newStats = data.result;
        const currentStats = statsRef.current;

        // Instagram stats
        if (newStats.instagram?.posts_scraped && newStats.instagram.posts_scraped !== currentStats.instagram?.posts_scraped) {
          addLog(`  → ${newStats.instagram.posts_scraped} posts extraídos`);
          if (newStats.instagram.sanity_passed) {
            addLog(`  → ${newStats.instagram.sanity_passed} posts validados`);
          }
        }

        // Website stats
        if (newStats.website?.products_detected !== undefined && newStats.website.products_detected !== currentStats.website?.products_detected) {
          addLog(`  → ${newStats.website.products_detected} productos detectados`);
        }

        // ToneProfile stats
        if (newStats.tone_profile?.generated && !currentStats.tone_profile?.generated) {
          const confidence = (newStats.tone_profile.confidence * 100).toFixed(0);
          addLog(`  → ToneProfile: ${confidence}% confianza`);
        }

        // RAG stats
        if (newStats.rag?.chunks_created && newStats.rag.chunks_created !== currentStats.rag?.chunks_created) {
          addLog(`  → ${newStats.rag.chunks_created} chunks indexados`);
        }

        // DMs stats
        if (newStats.dms?.messages && newStats.dms.messages !== currentStats.dms?.messages) {
          addLog(`  → ${newStats.dms.conversations} conversaciones encontradas`);
          addLog(`  → ${newStats.dms.messages} mensajes importados`);
          if (newStats.dms.leads_created > 0) {
            addLog(`  → ${newStats.dms.leads_created} leads creados con scoring`);
          }
        }

        // Bio stats
        if (newStats.bio?.loaded && !currentStats.bio?.loaded) {
          addLog(`  → Bio del perfil cargada`);
        }

        // FAQs stats
        if (newStats.faqs?.generated && newStats.faqs.generated !== currentStats.faqs?.generated) {
          addLog(`  → ${newStats.faqs.generated} FAQs generadas automáticamente`);
        }

        setStats({...newStats});
      }

      // Check completion
      if (data.status === 'completed') {
        if (pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
        setProgress(100);
        addLog('✓ ¡Configuración completada!');
        setTimeout(() => {
          setLoading(false);
          setStep('success');
        }, 1000);
      } else if (data.status === 'failed') {
        if (pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
        setError(data.errors?.join(', ') || 'Error durante la configuración');
        setStep('form');
        setLoading(false);
      }
    } catch (err) {
      console.warn('[Onboarding] Poll error:', err);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!instagramConnected || !instagram) {
      setError('Debes conectar tu Instagram primero');
      return;
    }

    // Reset state
    setLoading(true);
    setStep('loading');
    setError('');
    setProgress(0);
    setDisplayProgress(0);
    setCurrentStep('starting');
    setCompletedSteps([]);
    setLogLines(['Iniciando configuración...']);
    setStats({});

    const igUsername = instagram.replace('@', '');

    try {
      // Step 1: Quick setup
      addLog('Creando perfil del creator...');
      const quickResponse = await api.post('/onboarding/quick-setup', {
        creator_id: creatorId,
        instagram_username: igUsername,
        website_url: website || null
      });

      if (quickResponse.data.success === false) {
        throw new Error(quickResponse.data.errors?.join(', ') || 'Error en quick-setup');
      }

      addLog('✓ Perfil creado');
      setProgress(5);

      // Step 2: Start full auto-setup in background
      addLog('Iniciando auto-configuración V2...');

      await api.post('/onboarding/full-auto-setup-background', {
        creator_id: creatorId,
        instagram_username: igUsername,
        website_url: website || null,
        max_posts: 50,
        transcribe_videos: false
      });

      addLog('Procesando contenido...');
      setProgress(10);

      // Start polling every 1 second
      pollingRef.current = setInterval(pollStatus, 1000);

      // Initial poll after 500ms
      setTimeout(pollStatus, 500);

    } catch (err: any) {
      console.error('[Onboarding] Error:', err);
      setError(err.response?.data?.detail || err.message || 'Error al crear el clon');
      setStep('form');
      setLoading(false);
    }
  };

  // Get current step info
  const getCurrentStepInfo = () => {
    const stepInfo = processingSteps.find(s => s.id === currentStep);
    return stepInfo || processingSteps[0];
  };

  const currentStepInfo = getCurrentStepInfo();
  const currentStepIndex = processingSteps.findIndex(s => s.id === currentStep);

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
            {/* Instagram OAuth Connection */}
            <label className="block mb-2" style={{ color: 'rgba(255, 255, 255, 0.7)' }}>Tu Instagram *</label>

            {instagramConnected ? (
              // Connected state - show username
              <div
                className="w-full p-4 mb-4 rounded-xl flex items-center justify-between"
                style={{ background: 'rgba(34, 197, 94, 0.1)', border: '1px solid rgba(34, 197, 94, 0.3)' }}
              >
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #f09433, #e6683c, #dc2743, #cc2366, #bc1888)' }}>
                    <Instagram className="w-5 h-5 text-white" />
                  </div>
                  <div>
                    <p className="text-white font-medium">@{igUsername || instagram}</p>
                    <p className="text-xs" style={{ color: 'rgba(34, 197, 94, 0.8)' }}>Conectado</p>
                  </div>
                </div>
                <Check className="w-6 h-6" style={{ color: '#22c55e' }} />
              </div>
            ) : (
              // Not connected - show OAuth button
              <a
                href={`${API_URL}/oauth/instagram/start?creator_id=${creatorId}`}
                className="w-full p-4 mb-4 rounded-xl flex items-center justify-center gap-3 transition-all hover:scale-[1.02]"
                style={{
                  background: 'linear-gradient(135deg, #f09433, #e6683c, #dc2743, #cc2366, #bc1888)',
                  boxShadow: '0 4px 20px rgba(220, 39, 67, 0.3)'
                }}
              >
                <Instagram className="w-5 h-5 text-white" />
                <span className="text-white font-semibold">Conectar Instagram</span>
                <Link2 className="w-4 h-4 text-white opacity-70" />
              </a>
            )}

            <label className="block mb-2" style={{ color: 'rgba(255, 255, 255, 0.7)' }}>Tu website (opcional)</label>
            <input
              type="text"
              placeholder="https://tuwebsite.com"
              value={website}
              onChange={(e) => setWebsite(e.target.value)}
              className="w-full p-4 mb-6 rounded-xl text-white outline-none"
              style={{ background: 'rgba(255, 255, 255, 0.05)', border: '1px solid rgba(255, 255, 255, 0.08)' }}
            />

            <button
              type="submit"
              disabled={loading || !instagramConnected}
              className="w-full p-4 text-white font-semibold rounded-xl flex items-center justify-center gap-2 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              style={{
                background: instagramConnected
                  ? 'linear-gradient(135deg, #a855f7, #6366f1)'
                  : 'rgba(255, 255, 255, 0.1)',
                boxShadow: instagramConnected ? '0 4px 20px rgba(168, 85, 247, 0.3)' : 'none'
              }}
            >
              {instagramConnected ? 'Crear mi clon' : 'Conecta Instagram primero'}
              <ArrowRight className="w-5 h-5" />
            </button>

            {!instagramConnected && (
              <p className="mt-3 text-center text-xs" style={{ color: 'rgba(255, 255, 255, 0.4)' }}>
                Necesitas conectar tu cuenta de Instagram Business para continuar
              </p>
            )}
          </form>
        </div>
      </div>
    );
  }

  // LOADING STATE - Real-time progress
  if (step === 'loading') {
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
          {/* Header */}
          <div className="flex items-center gap-3 mb-6">
            <div className="w-12 h-12 rounded-xl flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #a855f7, #6366f1)' }}>
              <Brain className="w-6 h-6 text-white" />
            </div>
            <div>
              <h2 className="text-xl font-semibold text-white">Creando tu clon de IA</h2>
              <p className="text-sm" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>@{instagram.replace('@', '')}</p>
            </div>
          </div>

          {/* Progress Bar with percentage and timer */}
          <div className="mb-6">
            <div className="flex justify-between text-sm mb-2">
              <span style={{ color: 'rgba(255, 255, 255, 0.7)' }}>{currentStepInfo.label}</span>
              <div className="flex items-center gap-4">
                <span className="text-xs" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>
                  {formatTime(elapsedSeconds)} transcurrido
                </span>
                <span className="text-xs px-2 py-0.5 rounded" style={{ background: 'rgba(168, 85, 247, 0.2)', color: '#a855f7' }}>
                  ~{getEstimatedRemaining()} restante
                </span>
                <span className="font-mono font-bold" style={{ color: '#a855f7' }}>{displayProgress}%</span>
              </div>
            </div>
            <div className="h-3 rounded-full overflow-hidden" style={{ background: 'rgba(255, 255, 255, 0.1)' }}>
              <div
                className="h-full rounded-full transition-all duration-100 ease-out"
                style={{
                  width: `${displayProgress}%`,
                  background: 'linear-gradient(90deg, #a855f7, #6366f1)',
                  boxShadow: '0 0 10px rgba(168, 85, 247, 0.5)'
                }}
              />
            </div>
          </div>

          {/* Steps Grid - 4 columns for 8 steps */}
          <div className="grid grid-cols-4 gap-2 mb-6">
            {processingSteps.map((s, i) => {
              const Icon = s.icon;
              const isCompleted = completedSteps.includes(s.id);
              const isActive = currentStep === s.id;
              const isPending = !isCompleted && !isActive;

              return (
                <div
                  key={s.id}
                  className="flex flex-col items-center gap-2 p-3 rounded-lg transition-all duration-300"
                  style={{
                    background: isActive ? 'rgba(168, 85, 247, 0.15)' : 'transparent',
                    border: isActive ? '1px solid rgba(168, 85, 247, 0.3)' : '1px solid transparent'
                  }}
                >
                  <div
                    className="w-10 h-10 rounded-lg flex items-center justify-center transition-all duration-300"
                    style={{
                      background: isCompleted
                        ? 'rgba(34, 197, 94, 0.2)'
                        : isActive
                          ? 'rgba(168, 85, 247, 0.3)'
                          : 'rgba(255, 255, 255, 0.05)'
                    }}
                  >
                    {isCompleted ? (
                      <Check className="w-5 h-5" style={{ color: '#22c55e' }} />
                    ) : isActive ? (
                      <Loader2 className="w-5 h-5 animate-spin" style={{ color: '#a855f7' }} />
                    ) : (
                      <Icon className="w-5 h-5" style={{ color: 'rgba(255, 255, 255, 0.3)' }} />
                    )}
                  </div>
                  <span
                    className="text-xs text-center leading-tight"
                    style={{
                      color: isCompleted
                        ? '#22c55e'
                        : isActive
                          ? '#a855f7'
                          : 'rgba(255, 255, 255, 0.3)'
                    }}
                  >
                    {s.label.split(' ').slice(0, 2).join(' ')}
                  </span>
                </div>
              );
            })}
          </div>

          {/* Real-time Stats - 6 columns grid */}
          {(stats.instagram?.posts_scraped || stats.website?.products_detected || stats.tone_profile?.generated || stats.dms?.messages || stats.faqs?.generated) && (
            <div className="grid grid-cols-6 gap-2 mb-6">
              {stats.instagram?.posts_scraped && (
                <div className="p-2 rounded-lg text-center" style={{ background: 'rgba(168, 85, 247, 0.1)' }}>
                  <div className="text-xl font-bold text-white">{stats.instagram.posts_scraped}</div>
                  <div className="text-xs" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>Posts</div>
                </div>
              )}
              {stats.website?.products_detected !== undefined && (
                <div className="p-2 rounded-lg text-center" style={{ background: 'rgba(99, 102, 241, 0.1)' }}>
                  <div className="text-xl font-bold text-white">{stats.website.products_detected}</div>
                  <div className="text-xs" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>Productos</div>
                </div>
              )}
              {stats.tone_profile?.generated && (
                <div className="p-2 rounded-lg text-center" style={{ background: 'rgba(34, 197, 94, 0.1)' }}>
                  <div className="text-xl font-bold text-white">{(stats.tone_profile.confidence * 100).toFixed(0)}%</div>
                  <div className="text-xs" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>ToneProfile</div>
                </div>
              )}
              {stats.dms?.messages && (
                <div className="p-2 rounded-lg text-center" style={{ background: 'rgba(251, 146, 60, 0.1)' }}>
                  <div className="text-xl font-bold text-white">{stats.dms.messages}</div>
                  <div className="text-xs" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>DMs</div>
                </div>
              )}
              {stats.dms?.leads_created && (
                <div className="p-2 rounded-lg text-center" style={{ background: 'rgba(236, 72, 153, 0.1)' }}>
                  <div className="text-xl font-bold text-white">{stats.dms.leads_created}</div>
                  <div className="text-xs" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>Leads</div>
                </div>
              )}
              {stats.faqs?.generated && (
                <div className="p-2 rounded-lg text-center" style={{ background: 'rgba(6, 182, 212, 0.1)' }}>
                  <div className="text-xl font-bold text-white">{stats.faqs.generated}</div>
                  <div className="text-xs" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>FAQs</div>
                </div>
              )}
            </div>
          )}

          {/* Live Logs - taller area */}
          <div
            className="rounded-xl p-4 font-mono text-sm"
            style={{ background: 'rgba(0, 0, 0, 0.4)', border: '1px solid rgba(255, 255, 255, 0.05)' }}
          >
            <div className="flex items-center justify-between gap-2 mb-3 pb-2" style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.1)' }}>
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full animate-pulse" style={{ background: '#22c55e' }} />
                <span className="text-xs" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>LIVE LOG</span>
              </div>
              <span className="text-xs font-mono" style={{ color: 'rgba(255, 255, 255, 0.3)' }}>{logLines.length} entradas</span>
            </div>
            <div className="space-y-1 h-56 overflow-hidden">
              {logLines.map((line, i) => (
                <div
                  key={i}
                  className="flex items-start gap-2 animate-fadeIn"
                  style={{
                    opacity: i === logLines.length - 1 ? 1 : 0.6,
                    animation: i === logLines.length - 1 ? 'fadeIn 0.3s ease-out' : 'none'
                  }}
                >
                  <span style={{ color: line.startsWith('✓') ? '#22c55e' : '#a855f7' }}>
                    {line.startsWith('✓') ? '✓' : line.startsWith('  →') ? '→' : '>'}
                  </span>
                  <span style={{
                    color: line.startsWith('✓')
                      ? '#22c55e'
                      : i === logLines.length - 1
                        ? 'rgba(255, 255, 255, 0.9)'
                        : 'rgba(255, 255, 255, 0.6)'
                  }}>
                    {line.replace(/^[✓→>]\s*/, '')}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Current step detail */}
          <div className="mt-4 flex items-center justify-center gap-2">
            <Loader2 className="w-4 h-4 animate-spin" style={{ color: '#a855f7' }} />
            <span className="text-sm" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>{currentStepInfo.detail}</span>
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
          background: 'radial-gradient(circle, rgba(34, 197, 94, 0.15) 0%, transparent 70%)',
          borderRadius: '50%', filter: 'blur(60px)', pointerEvents: 'none'
        }}
      />
      <div
        className="p-10 rounded-3xl w-full max-w-md text-center relative z-10"
        style={{ background: '#0f0f14', border: '1px solid rgba(34, 197, 94, 0.2)', boxShadow: '0 0 60px rgba(34, 197, 94, 0.1)' }}
      >
        <div className="flex justify-center mb-6">
          <div className="w-20 h-20 rounded-full flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #22c55e, #16a34a)' }}>
            <Check className="w-10 h-10 text-white" strokeWidth={3} />
          </div>
        </div>

        <h2 className="text-3xl font-bold mb-3" style={{ background: 'linear-gradient(135deg, #22c55e, #16a34a)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
          ¡Tu clon está listo!
        </h2>

        <p className="text-lg mb-6" style={{ color: 'rgba(255, 255, 255, 0.6)' }}>
          Configuración completada exitosamente
        </p>

        {/* Final Stats */}
        <div className="grid grid-cols-3 gap-3 mb-6">
          <div className="p-3 rounded-xl" style={{ background: 'rgba(168, 85, 247, 0.1)' }}>
            <div className="text-xl font-bold text-white">{stats.instagram?.posts_scraped || 0}</div>
            <div className="text-xs" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>Posts</div>
          </div>
          <div className="p-3 rounded-xl" style={{ background: 'rgba(99, 102, 241, 0.1)' }}>
            <div className="text-xl font-bold text-white">{stats.website?.products_detected || 0}</div>
            <div className="text-xs" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>Productos</div>
          </div>
          <div className="p-3 rounded-xl" style={{ background: 'rgba(34, 197, 94, 0.1)' }}>
            <div className="text-xl font-bold text-white">100%</div>
            <div className="text-xs" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>Listo</div>
          </div>
        </div>

        <div className="flex items-center justify-center gap-2 mb-4">
          <span className="text-sm" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>Redirigiendo al dashboard</span>
          <div className="flex gap-1">
            <div className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: '#22c55e' }} />
            <div className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: '#22c55e', animationDelay: '150ms' }} />
            <div className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: '#22c55e', animationDelay: '300ms' }} />
          </div>
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
