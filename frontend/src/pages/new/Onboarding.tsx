import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Instagram, Youtube, Globe, CheckCircle, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { API_URL, CREATOR_ID } from '@/services/api';

type OnboardingStep = 'splash' | 'connect' | 'loading' | 'complete';

interface SetupStatus {
  status: string;
  progress: number;
  current_step?: string;
  steps: {
    instagram_connected: boolean;
    posts_imported: number;
    tone_profile_generated: boolean;
    tone_summary: string | null;
    content_indexed: number;
    dms_imported: number;
    leads_created: number;
    youtube_detected: boolean;
    youtube_videos_imported: number;
    website_detected: boolean;
    website_url: string | null;
  };
  errors: string[];
}

export default function Onboarding() {
  const [step, setStep] = useState<OnboardingStep>('splash');
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const creatorId = CREATOR_ID;

  // Auto-advance from splash after 4 seconds
  useEffect(() => {
    if (step === 'splash') {
      const timer = setTimeout(() => {
        setStep('connect');
      }, 4000);
      return () => clearTimeout(timer);
    }
  }, [step]);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
      }
    };
  }, []);

  const handleConnectInstagram = async () => {
    setStep('loading');
    setError(null);

    try {
      const response = await fetch(`${API_URL}/onboarding/full-setup/${creatorId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });

      if (!response.ok) {
        throw new Error('Failed to start setup');
      }

      startPolling();
    } catch (err) {
      console.error('Setup error:', err);
      setError('Error al iniciar el setup. Inténtalo de nuevo.');
      setStep('connect');
    }
  };

  const startPolling = () => {
    pollingRef.current = setInterval(async () => {
      try {
        const response = await fetch(`${API_URL}/onboarding/full-setup/${creatorId}/progress`);
        const data: SetupStatus = await response.json();

        setStatus(data);

        if (data.status === 'completed') {
          if (pollingRef.current) {
            clearInterval(pollingRef.current);
          }
          setStep('complete');
        } else if (data.status === 'error') {
          if (pollingRef.current) {
            clearInterval(pollingRef.current);
          }
          setError(data.errors?.[0] || 'Error durante el setup');
        }
      } catch (err) {
        console.error('Polling error:', err);
      }
    }, 2000);
  };

  // SPLASH SCREEN
  if (step === 'splash') {
    return (
      <div className="min-h-screen bg-black flex flex-col items-center justify-center">
        {/* Logo with glow effect */}
        <div className="relative animate-fade-in">
          <img
            src="/clonnect-logo.png"
            alt="Clonnect"
            className="w-48 h-48 md:w-64 md:h-64 object-contain"
          />
          {/* Glow effect behind logo */}
          <div className="absolute inset-0 bg-purple-500/30 blur-3xl rounded-full -z-10 scale-150" />
        </div>

        {/* Tagline */}
        <p className="text-fuchsia-400 text-sm md:text-base mt-6 tracking-[0.2em] animate-fade-in">
          FROM FOLLOW TO HELLO
        </p>
      </div>
    );
  }

  // CONNECT SCREEN
  if (step === 'connect') {
    return (
      <div className="min-h-screen bg-black flex flex-col">
        <div className="flex-1 flex flex-col justify-center px-6 py-12 max-w-md mx-auto w-full animate-fade-in">
          {/* Small logo */}
          <div className="flex justify-center mb-8">
            <img
              src="/clonnect-logo.png"
              alt="Clonnect"
              className="w-20 h-20 object-contain"
            />
          </div>

          {/* Title */}
          <div className="text-center mb-8">
            <h1 className="text-2xl md:text-3xl font-bold text-white mb-2">
              Clonnecta y listo
            </h1>
            <p className="text-gray-400">
              Tu clon aprenderá de tu contenido automáticamente
            </p>
          </div>

          {/* Error message */}
          {error && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 mb-6">
              <p className="text-red-400 text-sm">{error}</p>
            </div>
          )}

          {/* Main CTA - Instagram */}
          <Button
            onClick={handleConnectInstagram}
            size="lg"
            className="w-full h-14 text-lg bg-gradient-to-r from-purple-600 to-fuchsia-500 hover:from-purple-700 hover:to-fuchsia-600 transition-all mb-6"
          >
            <Instagram className="mr-3 h-6 w-6" />
            Clonnectar Instagram
          </Button>

          {/* Optional platforms */}
          <div className="space-y-3">
            <p className="text-sm text-gray-500 text-center mb-3">
              Opcional: más contenido = clon más inteligente
            </p>

            <Button
              variant="outline"
              className="w-full h-12 border-gray-800 bg-gray-900/50 text-gray-400 hover:bg-gray-800"
              disabled
            >
              <Youtube className="mr-3 h-5 w-5 text-red-500" />
              YouTube
              <span className="ml-auto text-xs text-gray-600">Próximamente</span>
            </Button>

            <Button
              variant="outline"
              className="w-full h-12 border-gray-800 bg-gray-900/50 text-gray-400 hover:bg-gray-800"
              disabled
            >
              <Globe className="mr-3 h-5 w-5 text-blue-400" />
              Website
              <span className="ml-auto text-xs text-gray-600">Próximamente</span>
            </Button>
          </div>
        </div>
      </div>
    );
  }

  // LOADING SCREEN
  if (step === 'loading') {
    const progress = status?.progress || 0;
    const steps = status?.steps;

    return (
      <div className="min-h-screen bg-black flex flex-col">
        <div className="flex-1 flex flex-col justify-center px-6 py-12 max-w-md mx-auto w-full">
          {/* Header */}
          <div className="text-center mb-8">
            <img
              src="/clonnect-logo.png"
              alt="Clonnect"
              className="w-16 h-16 object-contain mx-auto mb-4 animate-pulse"
            />
            <h1 className="text-2xl md:text-3xl font-bold text-white">
              Creando tu clon...
            </h1>
          </div>

          {/* Progress bar - purple/fuchsia gradient */}
          <div className="mb-8">
            <div className="w-full bg-gray-800 rounded-full h-2">
              <div
                className="bg-gradient-to-r from-purple-600 to-fuchsia-500 h-2 rounded-full transition-all duration-500"
                style={{ width: `${progress}%` }}
              />
            </div>
            <p className="text-sm text-gray-500 text-center mt-2">{progress}%</p>
          </div>

          {/* Steps list */}
          <div className="bg-gray-900/50 rounded-xl p-5 border border-gray-800 space-y-4">
            <StepItem
              done={steps?.instagram_connected}
              loading={!steps?.instagram_connected && progress < 15}
              text="Clonnectado a Instagram"
            />
            <StepItem
              done={(steps?.posts_imported || 0) > 0}
              loading={steps?.instagram_connected && !(steps?.posts_imported)}
              text={
                steps?.posts_imported
                  ? `${steps.posts_imported} posts importados`
                  : 'Importando posts...'
              }
            />
            <StepItem
              done={steps?.tone_profile_generated}
              loading={(steps?.posts_imported || 0) > 0 && !steps?.tone_profile_generated}
              text={steps?.tone_summary || 'Analizando tu tono...'}
            />
            <StepItem
              done={(steps?.content_indexed || 0) > 0}
              loading={steps?.tone_profile_generated && !(steps?.content_indexed)}
              text={
                steps?.content_indexed
                  ? `${steps.content_indexed} contenidos indexados`
                  : 'Indexando contenido...'
              }
            />
            <StepItem
              done={(steps?.dms_imported || 0) > 0}
              loading={(steps?.content_indexed || 0) > 0 && !(steps?.dms_imported)}
              text={
                steps?.dms_imported
                  ? `${steps.dms_imported} conversaciones importadas`
                  : 'Importando conversaciones...'
              }
            />
            <StepItem
              done={(steps?.leads_created || 0) > 0}
              loading={(steps?.dms_imported || 0) > 0 && !(steps?.leads_created)}
              text={
                steps?.leads_created
                  ? `${steps.leads_created} leads creados`
                  : 'Creando leads...'
              }
            />
            {steps?.youtube_detected && (
              <StepItem
                done={(steps?.youtube_videos_imported || 0) > 0}
                loading={steps?.youtube_detected && !steps?.youtube_videos_imported}
                text={
                  steps?.youtube_videos_imported
                    ? `${steps.youtube_videos_imported} videos importados`
                    : 'Importando videos de YouTube...'
                }
              />
            )}
          </div>
        </div>
      </div>
    );
  }

  // COMPLETE SCREEN
  if (step === 'complete') {
    const steps = status?.steps;

    return (
      <div className="min-h-screen bg-black flex flex-col">
        <div className="flex-1 flex flex-col justify-center px-6 py-12 max-w-md mx-auto w-full animate-fade-in">
          {/* Header */}
          <div className="text-center mb-8">
            <div className="w-16 h-16 rounded-xl bg-gradient-to-br from-green-500 to-emerald-400 flex items-center justify-center mx-auto mb-4">
              <CheckCircle className="w-8 h-8 text-white" />
            </div>
            <h1 className="text-2xl md:text-3xl font-bold text-white">
              ¡Tu clon está listo!
            </h1>
          </div>

          {/* Stats grid */}
          <div className="grid grid-cols-2 gap-4 mb-6">
            <StatCard value={steps?.posts_imported || 0} label="Posts" icon="📸" />
            <StatCard value={steps?.youtube_videos_imported || 0} label="Videos" icon="🎬" />
            <StatCard value={steps?.leads_created || 0} label="Leads" icon="👥" />
            <StatCard value={steps?.dms_imported || 0} label="DMs" icon="💬" />
          </div>

          {/* Tone summary */}
          {steps?.tone_summary && (
            <div className="bg-gray-900/50 rounded-xl p-4 mb-6 text-center border border-gray-800">
              <p className="text-sm text-gray-400 mb-1">Tu clon es</p>
              <p className="text-lg font-medium bg-gradient-to-r from-purple-400 to-fuchsia-400 bg-clip-text text-transparent">
                {steps.tone_summary}
              </p>
            </div>
          )}

          {/* Tip */}
          <div className="bg-purple-500/10 border border-purple-500/30 rounded-xl p-4 mb-6">
            <div className="flex items-start gap-3">
              <span className="text-lg">💡</span>
              <p className="text-sm text-gray-300">
                <strong className="text-white">Para vender:</strong> Añade tu
                producto y métodos de pago en Settings
              </p>
            </div>
          </div>

          {/* CTA - Navigate to dashboard */}
          <Button
            onClick={() => navigate('/dashboard')}
            size="lg"
            className="w-full h-14 text-lg bg-gradient-to-r from-purple-600 to-fuchsia-500 hover:from-purple-700 hover:to-fuchsia-600 transition-all"
          >
            Ir al Dashboard →
          </Button>
        </div>
      </div>
    );
  }

  return null;
}

// Helper components
function StepItem({
  done,
  loading,
  text,
}: {
  done?: boolean;
  loading?: boolean;
  text: string;
}) {
  return (
    <div className="flex items-center gap-3">
      {done ? (
        <div className="w-6 h-6 rounded-full bg-green-500 flex items-center justify-center flex-shrink-0">
          <CheckCircle className="w-4 h-4 text-white" />
        </div>
      ) : loading ? (
        <Loader2 className="w-6 h-6 text-fuchsia-500 animate-spin flex-shrink-0" />
      ) : (
        <div className="w-6 h-6 rounded-full bg-gray-700 flex-shrink-0" />
      )}
      <span className={`text-sm ${done ? 'text-white' : 'text-gray-500'}`}>
        {text}
      </span>
    </div>
  );
}

function StatCard({
  value,
  label,
  icon,
}: {
  value: number;
  label: string;
  icon: string;
}) {
  return (
    <div className="bg-gray-900/50 rounded-xl p-4 text-center border border-gray-800 hover:border-purple-500/50 transition-all">
      <div className="text-2xl mb-1">{icon}</div>
      <div className="text-2xl font-bold text-white">{value}</div>
      <div className="text-xs text-gray-400">{label}</div>
    </div>
  );
}
