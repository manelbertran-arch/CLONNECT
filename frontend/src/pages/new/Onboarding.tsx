import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Instagram, Youtube, Globe, CheckCircle, Loader2, Zap } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { API_URL, CREATOR_ID } from '@/services/api';

type OnboardingStep = 'connect' | 'loading' | 'complete';

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
  const [step, setStep] = useState<OnboardingStep>('connect');
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const creatorId = CREATOR_ID;

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
      // Start full setup
      const response = await fetch(`${API_URL}/onboarding/full-setup/${creatorId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });

      if (!response.ok) {
        throw new Error('Failed to start setup');
      }

      // Start polling for progress
      startPolling();
    } catch (err) {
      console.error('Setup error:', err);
      setError('Error al iniciar el setup. Inténtalo de nuevo.');
      setStep('connect');
    }
  };

  const startPolling = () => {
    // Poll every 2 seconds
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

  // STEP 1: Connect platforms
  if (step === 'connect') {
    return (
      <div className="min-h-screen bg-background flex flex-col">
        <div className="flex-1 flex flex-col justify-center px-6 py-12 max-w-md mx-auto w-full">
          {/* Logo - matches Sidebar */}
          <div className="text-center mb-8">
            <div className="w-16 h-16 rounded-xl bg-gradient-to-br from-primary to-accent flex items-center justify-center mx-auto mb-4">
              <Zap className="w-8 h-8 text-white" />
            </div>
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">
              Conecta y <span className="gradient-text">listo</span>
            </h1>
            <p className="text-muted-foreground mt-2">
              Tu clon aprenderá de tu contenido automáticamente
            </p>
          </div>

          {/* Error message */}
          {error && (
            <div className="metric-card border-destructive/50 mb-6">
              <p className="text-destructive text-sm">{error}</p>
            </div>
          )}

          {/* Main CTA - Instagram */}
          <Button
            onClick={handleConnectInstagram}
            size="lg"
            className="w-full h-14 text-lg bg-gradient-to-r from-primary to-accent hover:opacity-90 transition-opacity mb-6"
          >
            <Instagram className="mr-3 h-6 w-6" />
            Conectar Instagram
          </Button>

          {/* Optional platforms */}
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground text-center mb-3">
              Opcional: más contenido = clon más inteligente
            </p>

            <Button
              variant="outline"
              className="w-full h-12 border-border text-muted-foreground hover:bg-secondary hover:text-foreground"
              disabled
            >
              <Youtube className="mr-3 h-5 w-5 text-destructive" />
              YouTube
              <span className="ml-auto text-xs text-muted-foreground">Próximamente</span>
            </Button>

            <Button
              variant="outline"
              className="w-full h-12 border-border text-muted-foreground hover:bg-secondary hover:text-foreground"
              disabled
            >
              <Globe className="mr-3 h-5 w-5 text-accent" />
              Website
              <span className="ml-auto text-xs text-muted-foreground">Próximamente</span>
            </Button>
          </div>
        </div>
      </div>
    );
  }

  // STEP 2: Loading with real-time progress
  if (step === 'loading') {
    const progress = status?.progress || 0;
    const steps = status?.steps;

    return (
      <div className="min-h-screen bg-background flex flex-col">
        <div className="flex-1 flex flex-col justify-center px-6 py-12 max-w-md mx-auto w-full">
          {/* Header */}
          <div className="text-center mb-8">
            <div className="w-16 h-16 rounded-xl bg-gradient-to-br from-primary to-accent flex items-center justify-center mx-auto mb-4 animate-pulse">
              <Zap className="w-8 h-8 text-white" />
            </div>
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">
              Creando tu <span className="gradient-text">clon</span>...
            </h1>
          </div>

          {/* Progress bar - use shadcn Progress */}
          <div className="mb-8">
            <Progress value={progress} className="h-2" />
            <p className="text-sm text-muted-foreground text-center mt-2">{progress}%</p>
          </div>

          {/* Steps list */}
          <div className="metric-card space-y-4">
            <StepItem
              done={steps?.instagram_connected}
              loading={!steps?.instagram_connected && progress < 15}
              text="Conectado a Instagram"
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

  // STEP 3: Complete
  if (step === 'complete') {
    const steps = status?.steps;

    return (
      <div className="min-h-screen bg-background flex flex-col">
        <div className="flex-1 flex flex-col justify-center px-6 py-12 max-w-md mx-auto w-full">
          {/* Header */}
          <div className="text-center mb-8">
            <div className="w-16 h-16 rounded-xl bg-gradient-to-br from-success to-accent flex items-center justify-center mx-auto mb-4">
              <CheckCircle className="w-8 h-8 text-white" />
            </div>
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">
              ¡Tu clon está <span className="gradient-text">listo</span>!
            </h1>
          </div>

          {/* Stats grid - metric cards style */}
          <div className="grid grid-cols-2 gap-4 mb-6">
            <StatCard
              value={steps?.posts_imported || 0}
              label="Posts"
              icon="📸"
            />
            <StatCard
              value={steps?.youtube_videos_imported || 0}
              label="Videos"
              icon="🎬"
            />
            <StatCard
              value={steps?.leads_created || 0}
              label="Leads"
              icon="👥"
            />
            <StatCard
              value={steps?.dms_imported || 0}
              label="DMs"
              icon="💬"
            />
          </div>

          {/* Tone summary */}
          {steps?.tone_summary && (
            <div className="metric-card mb-6 text-center">
              <p className="text-sm text-muted-foreground mb-1">Tu clon es</p>
              <p className="text-lg font-medium gradient-text">
                {steps.tone_summary}
              </p>
            </div>
          )}

          {/* Tip */}
          <div className="metric-card border-primary/30 mb-6">
            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                <span>💡</span>
              </div>
              <p className="text-sm text-muted-foreground">
                <strong className="text-foreground">Para vender:</strong> Añade tu
                producto y métodos de pago en Settings
              </p>
            </div>
          </div>

          {/* CTA - Navigate to OLD dashboard */}
          <Button
            onClick={() => navigate('/dashboard')}
            size="lg"
            className="w-full h-14 text-lg bg-gradient-to-r from-primary to-accent hover:opacity-90 transition-opacity"
          >
            Ir al Dashboard →
          </Button>
        </div>
      </div>
    );
  }

  return null;
}

// Helper components - styled to match old dashboard
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
        <div className="w-6 h-6 rounded-full bg-success flex items-center justify-center flex-shrink-0">
          <CheckCircle className="w-4 h-4 text-white" />
        </div>
      ) : loading ? (
        <Loader2 className="w-6 h-6 text-primary animate-spin flex-shrink-0" />
      ) : (
        <div className="w-6 h-6 rounded-full bg-secondary flex-shrink-0" />
      )}
      <span className={`text-sm ${done ? 'text-foreground' : 'text-muted-foreground'}`}>
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
    <div className="metric-card text-center group hover:glow transition-all">
      <div className="text-2xl mb-1">{icon}</div>
      <div className="text-2xl font-bold">{value}</div>
      <div className="text-xs text-muted-foreground">{label}</div>
    </div>
  );
}
