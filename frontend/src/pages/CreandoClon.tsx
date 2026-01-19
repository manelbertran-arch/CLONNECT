import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { getCreatorId } from '../services/api';
import {
  Check,
  Instagram,
  Globe,
  Brain,
  Sparkles,
  Loader2,
  AlertCircle
} from 'lucide-react';

// Processing steps matching backend clone_progress
const processingSteps = [
  { id: 'instagram', icon: Instagram, label: 'Scrapeando Instagram', detail: 'Extrayendo posts de tu perfil...' },
  { id: 'website', icon: Globe, label: 'Escaneando website', detail: 'Analizando tu web...' },
  { id: 'training', icon: Brain, label: 'Entrenando tu clon', detail: 'Generando ToneProfile...' },
  { id: 'activating', icon: Sparkles, label: 'Activando clon', detail: 'Finalizando configuración...' },
];

// Activity messages shown while processing
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

// Progress response type from backend /progress/{creator_id}
interface ProgressResponse {
  status: 'in_progress' | 'complete' | 'error' | 'unknown';
  steps: {
    instagram: 'pending' | 'active' | 'completed';
    website: 'pending' | 'active' | 'completed';
    training: 'pending' | 'active' | 'completed';
    activating: 'pending' | 'active' | 'completed';
  };
  error?: string;
}

export default function CreandoClon() {
  const navigate = useNavigate();
  const creatorId = getCreatorId();

  // Progress state
  const [steps, setSteps] = useState<Record<string, string>>({
    instagram: 'pending',
    website: 'pending',
    training: 'pending',
    activating: 'pending',
  });
  const [logLines, setLogLines] = useState<string[]>(['Iniciando creación del clon...']);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [error, setError] = useState('');
  const [isComplete, setIsComplete] = useState(false);

  // Refs for intervals
  const pollingRef = useRef<NodeJS.Timeout | null>(null);
  const elapsedTimerRef = useRef<NodeJS.Timeout | null>(null);
  const activityLogRef = useRef<NodeJS.Timeout | null>(null);
  const previousStepsRef = useRef<Record<string, string>>({});

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
      if (elapsedTimerRef.current) clearInterval(elapsedTimerRef.current);
      if (activityLogRef.current) clearInterval(activityLogRef.current);
    };
  }, []);

  // Elapsed time counter
  useEffect(() => {
    elapsedTimerRef.current = setInterval(() => {
      setElapsedSeconds(prev => prev + 1);
    }, 1000);

    return () => {
      if (elapsedTimerRef.current) clearInterval(elapsedTimerRef.current);
    };
  }, []);

  // Activity logs - show dynamic messages while waiting
  useEffect(() => {
    let msgIndex = 0;
    activityLogRef.current = setInterval(() => {
      if (!isComplete) {
        addLog(`... ${activityMessages[msgIndex % activityMessages.length]}`);
        msgIndex++;
      }
    }, 3000);

    return () => {
      if (activityLogRef.current) clearInterval(activityLogRef.current);
    };
  }, [isComplete]);

  // Format elapsed time
  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  // Add log line helper
  const addLog = (message: string) => {
    setLogLines(prev => [...prev.slice(-15), message]);
  };

  // Calculate progress percentage based on completed steps
  const getProgressPercent = () => {
    const stepOrder = ['instagram', 'website', 'training', 'activating'];
    let completed = 0;
    let active = 0;

    for (const stepId of stepOrder) {
      if (steps[stepId] === 'completed') completed++;
      else if (steps[stepId] === 'active') active = 1;
    }

    // Each step is 25%, active step counts as half
    return Math.min(100, (completed * 25) + (active * 12));
  };

  // Get current active step
  const getCurrentStep = () => {
    const stepOrder = ['instagram', 'website', 'training', 'activating'];
    for (const stepId of stepOrder) {
      if (steps[stepId] === 'active') {
        return processingSteps.find(s => s.id === stepId);
      }
    }
    // If no active step, find first pending
    for (const stepId of stepOrder) {
      if (steps[stepId] === 'pending') {
        return processingSteps.find(s => s.id === stepId);
      }
    }
    return processingSteps[processingSteps.length - 1];
  };

  // Poll backend for progress - CORRECT ENDPOINT
  const pollStatus = async () => {
    if (!creatorId) return;

    try {
      const response = await fetch(
        `${import.meta.env.VITE_API_URL || 'https://web-production-9f69.up.railway.app'}/onboarding/progress/${encodeURIComponent(creatorId)}`
      );

      if (!response.ok) {
        if (response.status === 404) {
          // Creator not found, keep waiting
          return;
        }
        throw new Error('Error fetching status');
      }

      const data: ProgressResponse = await response.json();
      console.log('[CreandoClon] Poll:', data);

      // Update steps and log changes
      if (data.steps) {
        const prevSteps = previousStepsRef.current;

        for (const [stepId, status] of Object.entries(data.steps)) {
          if (prevSteps[stepId] !== status) {
            const stepInfo = processingSteps.find(s => s.id === stepId);
            if (stepInfo) {
              if (status === 'active') {
                addLog(`▶ ${stepInfo.label}...`);
              } else if (status === 'completed' && prevSteps[stepId] !== 'completed') {
                addLog(`✓ ${stepInfo.label}`);
              }
            }
          }
        }

        previousStepsRef.current = { ...data.steps };
        setSteps(data.steps);
      }

      // Check completion
      if (data.status === 'complete') {
        if (pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
        if (activityLogRef.current) {
          clearInterval(activityLogRef.current);
          activityLogRef.current = null;
        }
        setIsComplete(true);
        addLog('✓ ¡Tu clon está listo!');

        setTimeout(() => {
          // Use replace to avoid /creando-clon in browser history
          // This prevents back button from going back to progress screen
          navigate('/felicidades', { replace: true });
        }, 1500);
      } else if (data.status === 'error') {
        if (pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
        setError(data.error || 'Error durante la creación del clon');
      }
    } catch (err) {
      console.warn('[CreandoClon] Poll error:', err);
    }
  };

  // Start polling on mount
  useEffect(() => {
    if (!creatorId) {
      setError('No se encontró el ID del creador. Vuelve a conectar Instagram.');
      return;
    }

    addLog(`Creador: ${creatorId}`);
    addLog('Conectando con el servidor...');

    // Start polling every 2 seconds
    pollingRef.current = setInterval(pollStatus, 2000);

    // Initial poll immediately
    pollStatus();

    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [creatorId]);

  const currentStepInfo = getCurrentStep();
  const progressPercent = getProgressPercent();

  // Error state
  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: '#09090b' }}>
        <div
          className="p-8 rounded-2xl w-full max-w-md text-center"
          style={{ background: '#0f0f14', border: '1px solid rgba(239, 68, 68, 0.3)' }}
        >
          <AlertCircle className="w-16 h-16 mx-auto mb-4" style={{ color: '#ef4444' }} />
          <h2 className="text-xl font-semibold text-white mb-2">Error</h2>
          <p className="mb-6" style={{ color: 'rgba(255, 255, 255, 0.6)' }}>{error}</p>
          <button
            onClick={() => navigate('/crear-clon')}
            className="px-6 py-3 rounded-xl text-white font-medium"
            style={{ background: 'linear-gradient(135deg, #a855f7, #6366f1)' }}
          >
            Volver a intentar
          </button>
        </div>
      </div>
    );
  }

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
        className="p-8 rounded-2xl w-full max-w-xl relative z-10"
        style={{ background: '#0f0f14', border: '1px solid rgba(255, 255, 255, 0.08)' }}
      >
        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <div className="w-12 h-12 rounded-xl flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #a855f7, #6366f1)' }}>
            <Brain className="w-6 h-6 text-white" />
          </div>
          <div>
            <h2 className="text-xl font-semibold text-white">Creando tu clon de IA</h2>
            <p className="text-sm" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>
              {creatorId ? `@${creatorId}` : 'Procesando...'}
            </p>
          </div>
        </div>

        {/* Progress Bar with percentage and timer */}
        <div className="mb-6">
          <div className="flex justify-between text-sm mb-2">
            <span style={{ color: 'rgba(255, 255, 255, 0.7)' }}>{currentStepInfo?.label || 'Procesando...'}</span>
            <div className="flex items-center gap-4">
              <span className="text-xs" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>
                {formatTime(elapsedSeconds)} transcurrido
              </span>
              <span className="font-mono font-bold" style={{ color: '#a855f7' }}>{progressPercent}%</span>
            </div>
          </div>
          <div className="h-3 rounded-full overflow-hidden" style={{ background: 'rgba(255, 255, 255, 0.1)' }}>
            <div
              className="h-full rounded-full transition-all duration-500 ease-out"
              style={{
                width: `${progressPercent}%`,
                background: 'linear-gradient(90deg, #a855f7, #6366f1)',
                boxShadow: '0 0 10px rgba(168, 85, 247, 0.5)'
              }}
            />
          </div>
        </div>

        {/* Steps - 4 columns */}
        <div className="grid grid-cols-4 gap-3 mb-6">
          {processingSteps.map((s) => {
            const Icon = s.icon;
            const status = steps[s.id] || 'pending';
            const isCompleted = status === 'completed';
            const isActive = status === 'active';

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
                  className="w-12 h-12 rounded-lg flex items-center justify-center transition-all duration-300"
                  style={{
                    background: isCompleted
                      ? 'rgba(34, 197, 94, 0.2)'
                      : isActive
                        ? 'rgba(168, 85, 247, 0.3)'
                        : 'rgba(255, 255, 255, 0.05)'
                  }}
                >
                  {isCompleted ? (
                    <Check className="w-6 h-6" style={{ color: '#22c55e' }} />
                  ) : isActive ? (
                    <Loader2 className="w-6 h-6 animate-spin" style={{ color: '#a855f7' }} />
                  ) : (
                    <Icon className="w-6 h-6" style={{ color: 'rgba(255, 255, 255, 0.3)' }} />
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

        {/* Live Logs */}
        <div
          className="rounded-xl p-4 font-mono text-sm"
          style={{ background: 'rgba(0, 0, 0, 0.4)', border: '1px solid rgba(255, 255, 255, 0.05)' }}
        >
          <div className="flex items-center justify-between gap-2 mb-3 pb-2" style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.1)' }}>
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full animate-pulse" style={{ background: isComplete ? '#22c55e' : '#a855f7' }} />
              <span className="text-xs" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>LIVE LOG</span>
            </div>
            <span className="text-xs font-mono" style={{ color: 'rgba(255, 255, 255, 0.3)' }}>{logLines.length} entradas</span>
          </div>
          <div className="space-y-1 h-48 overflow-hidden">
            {logLines.map((line, i) => (
              <div
                key={i}
                className="flex items-start gap-2"
                style={{
                  opacity: i === logLines.length - 1 ? 1 : 0.6,
                }}
              >
                <span style={{ color: line.startsWith('✓') ? '#22c55e' : line.startsWith('▶') ? '#60a5fa' : '#a855f7' }}>
                  {line.startsWith('✓') ? '✓' : line.startsWith('▶') ? '▶' : '>'}
                </span>
                <span style={{
                  color: line.startsWith('✓')
                    ? '#22c55e'
                    : i === logLines.length - 1
                      ? 'rgba(255, 255, 255, 0.9)'
                      : 'rgba(255, 255, 255, 0.6)'
                }}>
                  {line.replace(/^[✓▶>]\s*/, '')}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Current step detail */}
        <div className="mt-4 flex items-center justify-center gap-2">
          <Loader2 className="w-4 h-4 animate-spin" style={{ color: '#a855f7' }} />
          <span className="text-sm" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>{currentStepInfo?.detail || 'Procesando...'}</span>
        </div>

        {/* Footer warning */}
        <div className="mt-4 text-center">
          <p className="text-xs" style={{ color: 'rgba(255, 255, 255, 0.3)' }}>
            No cierres esta página mientras se crea tu clon
          </p>
        </div>
      </div>
    </div>
  );
}
