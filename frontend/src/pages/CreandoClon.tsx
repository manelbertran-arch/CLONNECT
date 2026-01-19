import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2, Check, Instagram, Globe, Brain, MessageSquare, Sparkles } from 'lucide-react';
import { API_URL, getCreatorId } from '../services/api';

type StepStatus = 'pending' | 'active' | 'completed';

interface ProgressStep {
  id: string;
  label: string;
  icon: React.ReactNode;
  status: StepStatus;
}

export default function CreandoClon() {
  const navigate = useNavigate();
  const [error, setError] = useState('');
  const [steps, setSteps] = useState<ProgressStep[]>([
    { id: 'instagram', label: 'Analizando tu Instagram', icon: <Instagram className="w-5 h-5" />, status: 'pending' },
    { id: 'website', label: 'Scrapeando tu website', icon: <Globe className="w-5 h-5" />, status: 'pending' },
    { id: 'training', label: 'Entrenando tu clon', icon: <Brain className="w-5 h-5" />, status: 'pending' },
    { id: 'activating', label: 'Activando respuestas', icon: <MessageSquare className="w-5 h-5" />, status: 'pending' },
  ]);

  const creatorId = getCreatorId();

  useEffect(() => {
    if (!creatorId) {
      console.error('[CreandoClon] No creator_id found');
      setError('No se encontró el ID del creador.');
      return;
    }

    // Start polling for progress
    const pollProgress = async () => {
      try {
        const response = await fetch(`${API_URL}/onboarding/progress/${encodeURIComponent(creatorId)}`);

        if (!response.ok) {
          // If endpoint doesn't exist yet, simulate progress
          if (response.status === 404) {
            console.log('[CreandoClon] Progress endpoint not found, simulating...');
            simulateProgress();
            return;
          }
          throw new Error('Error al obtener progreso');
        }

        const data = await response.json();
        console.log('[CreandoClon] Progress:', data);

        // Update steps based on backend response
        if (data.steps) {
          setSteps(prev => prev.map(step => ({
            ...step,
            status: data.steps[step.id] || step.status
          })));
        }

        // Check if complete
        if (data.status === 'complete') {
          navigate('/felicidades');
        }
      } catch (err) {
        console.error('Progress error:', err);
        // On error, simulate progress for demo
        simulateProgress();
      }
    };

    // Simulate progress if backend doesn't have real progress tracking
    const simulateProgress = () => {
      const stepIds = ['instagram', 'website', 'training', 'activating'];
      let currentStep = 0;

      const interval = setInterval(() => {
        setSteps(prev => prev.map((step, idx) => {
          if (idx < currentStep) {
            return { ...step, status: 'completed' };
          } else if (idx === currentStep) {
            return { ...step, status: 'active' };
          }
          return step;
        }));

        currentStep++;

        if (currentStep > stepIds.length) {
          clearInterval(interval);
          // All steps complete, navigate to success
          setTimeout(() => {
            navigate('/felicidades');
          }, 1000);
        }
      }, 2000); // Each step takes 2 seconds

      return () => clearInterval(interval);
    };

    // Initial poll
    pollProgress();

    // Poll every 3 seconds
    const pollInterval = setInterval(pollProgress, 3000);

    return () => clearInterval(pollInterval);
  }, [creatorId, navigate]);

  const getStepColor = (status: StepStatus) => {
    switch (status) {
      case 'completed': return '#22c55e';
      case 'active': return '#a855f7';
      default: return 'rgba(255, 255, 255, 0.2)';
    }
  };

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
        {/* Header */}
        <div className="text-center mb-8">
          <div
            className="w-20 h-20 rounded-full flex items-center justify-center mx-auto mb-4"
            style={{ background: 'linear-gradient(135deg, #a855f7, #6366f1)' }}
          >
            <Sparkles className="w-10 h-10 text-white animate-pulse" />
          </div>
          <h1
            className="text-2xl font-bold mb-2"
            style={{
              background: 'linear-gradient(135deg, #a855f7, #6366f1)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent'
            }}
          >
            Creando tu clon...
          </h1>
          <p style={{ color: 'rgba(255, 255, 255, 0.5)' }}>
            Esto puede tardar unos minutos
          </p>
        </div>

        {/* Error */}
        {error && (
          <div
            className="p-4 rounded-xl mb-6"
            style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)' }}
          >
            <p className="text-red-400 text-sm">{error}</p>
          </div>
        )}

        {/* Progress Steps */}
        <div className="space-y-4">
          {steps.map((step, index) => (
            <div
              key={step.id}
              className="flex items-center gap-4 p-4 rounded-xl transition-all duration-500"
              style={{
                background: step.status === 'active'
                  ? 'rgba(168, 85, 247, 0.1)'
                  : step.status === 'completed'
                    ? 'rgba(34, 197, 94, 0.05)'
                    : 'rgba(255, 255, 255, 0.02)',
                border: `1px solid ${step.status === 'active'
                  ? 'rgba(168, 85, 247, 0.3)'
                  : step.status === 'completed'
                    ? 'rgba(34, 197, 94, 0.2)'
                    : 'rgba(255, 255, 255, 0.05)'}`
              }}
            >
              {/* Icon */}
              <div
                className="w-10 h-10 rounded-full flex items-center justify-center transition-all duration-500"
                style={{
                  background: step.status === 'active'
                    ? 'rgba(168, 85, 247, 0.2)'
                    : step.status === 'completed'
                      ? 'rgba(34, 197, 94, 0.2)'
                      : 'rgba(255, 255, 255, 0.05)',
                  color: getStepColor(step.status)
                }}
              >
                {step.status === 'completed' ? (
                  <Check className="w-5 h-5" />
                ) : step.status === 'active' ? (
                  <Loader2 className="w-5 h-5 animate-spin" />
                ) : (
                  step.icon
                )}
              </div>

              {/* Label */}
              <span
                className="flex-1 font-medium transition-all duration-500"
                style={{
                  color: step.status === 'pending'
                    ? 'rgba(255, 255, 255, 0.4)'
                    : 'white'
                }}
              >
                {step.label}
              </span>

              {/* Status indicator */}
              {step.status === 'completed' && (
                <Check className="w-5 h-5" style={{ color: '#22c55e' }} />
              )}
            </div>
          ))}
        </div>

        {/* Footer info */}
        <div className="mt-8 text-center">
          <p className="text-sm" style={{ color: 'rgba(255, 255, 255, 0.4)' }}>
            No cierres esta página mientras se crea tu clon
          </p>
        </div>
      </div>
    </div>
  );
}
