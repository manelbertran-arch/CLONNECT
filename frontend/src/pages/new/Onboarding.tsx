import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Instagram, Youtube, Globe, CheckCircle, Loader2, Edit3 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { API_URL, setCreatorId, getCreatorId } from '@/services/api';

type OnboardingStep = 'splash' | 'connect' | 'loading' | 'complete';
type SetupMode = 'oauth' | 'manual';

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

interface ManualSetupStatus {
  success: boolean;
  creator_id: string;
  steps_completed: {
    posts_scraped: boolean;
    tone_profile_generated: boolean;
    rag_indexed: boolean;
    website_scraped: boolean;
    onboarding_completed: boolean;
    bot_activated: boolean;
  };
  details: {
    posts_count: number;
    tone_summary: {
      formality: string;
      energy: string;
      warmth: string;
      uses_emojis: boolean;
      primary_language: string;
      signature_phrases: string[];
    } | null;
    rag_documents: number;
    website_pages: number;
  };
  errors: string[];
}

export default function Onboarding() {
  const [step, setStep] = useState<OnboardingStep>('connect'); // Skip splash, go directly to form
  const [setupMode, setSetupMode] = useState<SetupMode>('manual'); // Default to manual for demo
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const [manualStatus, setManualStatus] = useState<ManualSetupStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  // Manual setup form fields
  const [instagramUsername, setInstagramUsername] = useState('');
  const [websiteUrl, setWebsiteUrl] = useState('');

  const navigate = useNavigate();
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Helper to clean instagram username and create creator_id
  const cleanUsername = (username: string): string => {
    return username.trim().replace(/^@/, '').toLowerCase().replace(/[^a-z0-9_]/g, '_');
  };

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

  // State to track creator_id for OAuth mode
  const [oauthCreatorId, setOauthCreatorId] = useState<string>(() => getCreatorId());

  const handleConnectInstagram = async () => {
    // For OAuth mode, we need the user to be authenticated first
    // Use existing creator_id from auth or prompt to create one
    const currentCreatorId = getCreatorId();
    setOauthCreatorId(currentCreatorId);

    console.log('[Onboarding] Starting OAuth setup for:', currentCreatorId);

    setStep('loading');
    setError(null);

    try {
      const response = await fetch(`${API_URL}/onboarding/full-setup/${currentCreatorId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });

      if (!response.ok) {
        throw new Error('Failed to start setup');
      }

      startPolling(currentCreatorId);
    } catch (err) {
      console.error('Setup error:', err);
      setError('Error al iniciar el setup. Inténtalo de nuevo.');
      setStep('connect');
    }
  };

  const startPolling = (creatorId: string) => {
    pollingRef.current = setInterval(async () => {
      try {
        const response = await fetch(`${API_URL}/onboarding/full-setup/${creatorId}/progress`);
        const data: SetupStatus = await response.json();

        setStatus(data);

        if (data.status === 'completed') {
          if (pollingRef.current) {
            clearInterval(pollingRef.current);
          }
          // Save creator_id on successful completion
          setCreatorId(creatorId);
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

  // Handle manual setup (public scraping, no OAuth)
  const handleManualSetup = async () => {
    if (!instagramUsername.trim()) {
      setError('Por favor ingresa tu usuario de Instagram');
      return;
    }

    // Clean username and use as creator_id
    const igUsername = instagramUsername.trim().replace(/^@/, '');
    const newCreatorId = cleanUsername(instagramUsername);

    console.log('[Onboarding] Starting manual setup:', {
      instagram_username: igUsername,
      creator_id: newCreatorId,
      api_url: API_URL
    });

    setStep('loading');
    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch(`${API_URL}/onboarding/manual-setup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          creator_id: newCreatorId,  // Use instagram username as creator_id
          instagram_username: igUsername,
          website_url: websiteUrl.trim() || null,
          max_posts: 50
        })
      });

      console.log('[Onboarding] Response status:', response.status);
      const data: ManualSetupStatus = await response.json();
      console.log('[Onboarding] Response data:', data);

      setManualStatus(data);

      if (data.success) {
        // Save the new creator_id for the rest of the app
        setCreatorId(newCreatorId);
        console.log('[Onboarding] Saved creator_id:', newCreatorId);
        setStep('complete');
      } else {
        setError(data.errors?.[0] || 'Error durante el setup manual');
        setStep('connect');
      }
    } catch (err) {
      console.error('Manual setup error:', err);
      setError('Error al conectar con el servidor. Inténtalo de nuevo.');
      setStep('connect');
    } finally {
      setIsLoading(false);
    }
  };

  // SPLASH SCREEN - Pure black, BIG logo with pulse, 4 seconds
  if (step === 'splash') {
    return (
      <div className="min-h-screen bg-black flex flex-col items-center justify-center">
        <div className="animate-fade-in">
          <img
            src="/clonnect-logo.png"
            alt="Clonnect"
            className="w-72 h-72 md:w-96 md:h-96 object-contain animate-pulse"
          />
        </div>
      </div>
    );
  }

  // CONNECT SCREEN - With mode toggle (OAuth vs Manual)
  if (step === 'connect') {
    return (
      <div className="min-h-screen bg-black flex flex-col">
        {/* Header with logo top left */}
        <div className="p-6">
          <img
            src="/clonnect-logo.png"
            alt="Clonnect"
            className="w-12 h-12 object-contain animate-pulse"
          />
        </div>

        <div className="flex-1 flex flex-col justify-center px-6 pb-12 max-w-md mx-auto w-full animate-fade-in">
          {/* Title */}
          <div className="text-center mb-6">
            <h1 className="text-2xl md:text-3xl font-bold text-white mb-2">
              Conecta y listo
            </h1>
            <p className="text-gray-400">
              Tu clon aprenderá de tu contenido automáticamente
            </p>
          </div>

          {/* Mode Toggle */}
          <div className="flex gap-2 mb-6 p-1 bg-gray-900 rounded-xl">
            <button
              onClick={() => setSetupMode('manual')}
              className={`flex-1 py-2 px-4 rounded-lg text-sm font-medium transition-all ${
                setupMode === 'manual'
                  ? 'bg-gradient-to-r from-purple-600 to-fuchsia-500 text-white'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              <Edit3 className="w-4 h-4 inline mr-2" />
              Manual
            </button>
            <button
              onClick={() => setSetupMode('oauth')}
              className={`flex-1 py-2 px-4 rounded-lg text-sm font-medium transition-all ${
                setupMode === 'oauth'
                  ? 'bg-gradient-to-r from-purple-600 to-fuchsia-500 text-white'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              <Instagram className="w-4 h-4 inline mr-2" />
              OAuth
            </button>
          </div>

          {/* Error message */}
          {error && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 mb-6">
              <p className="text-red-400 text-sm">{error}</p>
            </div>
          )}

          {/* MANUAL MODE */}
          {setupMode === 'manual' && (
            <div className="space-y-4">
              {/* Instagram Username Input */}
              <div>
                <label className="block text-sm text-gray-400 mb-2">
                  Usuario de Instagram *
                </label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500">@</span>
                  <Input
                    type="text"
                    placeholder="tu_usuario"
                    value={instagramUsername}
                    onChange={(e) => setInstagramUsername(e.target.value)}
                    className="pl-8 h-12 bg-gray-900 border-gray-700 text-white placeholder:text-gray-600 focus:border-fuchsia-500"
                  />
                </div>
                <p className="text-xs text-gray-600 mt-1">
                  Tu perfil debe ser público para el scraping
                </p>
              </div>

              {/* Website URL Input (Optional) */}
              <div>
                <label className="block text-sm text-gray-400 mb-2">
                  Website (opcional)
                </label>
                <div className="relative">
                  <Globe className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
                  <Input
                    type="url"
                    placeholder="https://tuwebsite.com"
                    value={websiteUrl}
                    onChange={(e) => setWebsiteUrl(e.target.value)}
                    className="pl-10 h-12 bg-gray-900 border-gray-700 text-white placeholder:text-gray-600 focus:border-fuchsia-500"
                  />
                </div>
                <p className="text-xs text-gray-600 mt-1">
                  Añadiremos tu web al conocimiento del clon
                </p>
              </div>

              {/* Manual Setup CTA */}
              <Button
                onClick={handleManualSetup}
                disabled={isLoading || !instagramUsername.trim()}
                size="lg"
                className="w-full h-14 text-lg bg-gradient-to-r from-purple-600 to-fuchsia-500 hover:from-purple-700 hover:to-fuchsia-600 transition-all mt-4 disabled:opacity-50"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="mr-3 h-6 w-6 animate-spin" />
                    Procesando...
                  </>
                ) : (
                  <>
                    Crear mi clon
                    <span className="ml-2">→</span>
                  </>
                )}
              </Button>

              <p className="text-xs text-gray-500 text-center mt-2">
                Scrapearemos ~50 posts públicos para entrenar tu clon
              </p>
            </div>
          )}

          {/* OAUTH MODE */}
          {setupMode === 'oauth' && (
            <div className="space-y-4">
              {/* Main CTA - Instagram OAuth */}
              <Button
                onClick={handleConnectInstagram}
                size="lg"
                className="w-full h-14 text-lg bg-gradient-to-r from-purple-600 to-fuchsia-500 hover:from-purple-700 hover:to-fuchsia-600 transition-all"
              >
                <Instagram className="mr-3 h-6 w-6" />
                Conectar con Instagram
              </Button>

              <p className="text-xs text-gray-500 text-center">
                Conecta tu cuenta para acceso completo a posts y DMs
              </p>

              {/* Optional platforms */}
              <div className="space-y-3 mt-6">
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
          )}
        </div>
      </div>
    );
  }

  // LOADING SCREEN
  if (step === 'loading') {
    // For manual mode, show indeterminate loading
    if (setupMode === 'manual') {
      return (
        <div className="min-h-screen bg-black flex flex-col">
          {/* Header with logo top left */}
          <div className="p-6">
            <img
              src="/clonnect-logo.png"
              alt="Clonnect"
              className="w-12 h-12 object-contain animate-pulse"
            />
          </div>

          <div className="flex-1 flex flex-col justify-center px-6 pb-12 max-w-md mx-auto w-full">
            {/* Header */}
            <div className="text-center mb-8">
              <h1 className="text-2xl md:text-3xl font-bold text-white">
                Creando tu clon...
              </h1>
              <p className="text-gray-400 mt-2">
                Esto puede tardar 1-2 minutos
              </p>
            </div>

            {/* Indeterminate progress bar */}
            <div className="mb-8">
              <div className="w-full bg-gray-800 rounded-full h-2 overflow-hidden">
                <div className="bg-gradient-to-r from-purple-600 to-fuchsia-500 h-2 rounded-full animate-pulse w-full" />
              </div>
            </div>

            {/* Steps being processed */}
            <div className="space-y-3">
              <StepItem
                done={false}
                loading={true}
                text={`Scrapeando posts de @${instagramUsername}...`}
              />
              <StepItem
                done={false}
                loading={false}
                text="Analizando tu tono y estilo..."
              />
              <StepItem
                done={false}
                loading={false}
                text="Indexando contenido en RAG..."
              />
              {websiteUrl && (
                <StepItem
                  done={false}
                  loading={false}
                  text="Scrapeando tu website..."
                />
              )}
              <StepItem
                done={false}
                loading={false}
                text="Activando tu clon..."
              />
            </div>
          </div>
        </div>
      );
    }

    // For OAuth mode, show polling progress
    const progress = status?.progress || 0;
    const steps = status?.steps;

    return (
      <div className="min-h-screen bg-black flex flex-col">
        {/* Header with logo top left */}
        <div className="p-6">
          <img
            src="/clonnect-logo.png"
            alt="Clonnect"
            className="w-12 h-12 object-contain animate-pulse"
          />
        </div>

        <div className="flex-1 flex flex-col justify-center px-6 pb-12 max-w-md mx-auto w-full">
          {/* Header */}
          <div className="text-center mb-8">
            <h1 className="text-2xl md:text-3xl font-bold text-white">
              Creando tu clon...
            </h1>
          </div>

          {/* Progress bar */}
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
          <div className="space-y-3">
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
          </div>
        </div>
      </div>
    );
  }

  // COMPLETE SCREEN
  if (step === 'complete') {
    // Handle both manual and OAuth completion data
    const oauthSteps = status?.steps;
    const manualDetails = manualStatus?.details;
    const manualStepsCompleted = manualStatus?.steps_completed;

    // Determine what data to show
    const postsCount = setupMode === 'manual'
      ? (manualDetails?.posts_count || 0)
      : (oauthSteps?.posts_imported || 0);

    const ragDocuments = setupMode === 'manual'
      ? (manualDetails?.rag_documents || 0)
      : (oauthSteps?.content_indexed || 0);

    const websitePages = setupMode === 'manual'
      ? (manualDetails?.website_pages || 0)
      : 0;

    const toneSummary = setupMode === 'manual'
      ? manualDetails?.tone_summary
      : oauthSteps?.tone_summary;

    // Format tone summary for display
    const formatToneSummary = () => {
      if (setupMode === 'manual' && manualDetails?.tone_summary) {
        const t = manualDetails.tone_summary;
        const parts = [];
        if (t.formality) parts.push(t.formality);
        if (t.energy) parts.push(t.energy);
        if (t.uses_emojis) parts.push('usa emojis');
        return parts.join(', ') || 'Personalidad analizada';
      }
      return oauthSteps?.tone_summary || 'Personalidad analizada';
    };

    return (
      <div className="min-h-screen bg-black flex flex-col">
        {/* Header with logo top left */}
        <div className="p-6">
          <img
            src="/clonnect-logo.png"
            alt="Clonnect"
            className="w-12 h-12 object-contain"
          />
        </div>

        <div className="flex-1 flex flex-col justify-center px-6 pb-12 max-w-md mx-auto w-full animate-fade-in">
          {/* Header */}
          <div className="text-center mb-8">
            <div className="text-5xl mb-4">🎉</div>
            <h1 className="text-2xl md:text-3xl font-bold text-white">
              ¡Tu clon está listo!
            </h1>
          </div>

          {/* Stats grid - Different for manual vs OAuth */}
          {setupMode === 'manual' ? (
            <div className="grid grid-cols-2 gap-4 mb-6">
              <StatCard value={postsCount} label="Posts" icon="📸" />
              <StatCard value={ragDocuments} label="En RAG" icon="🧠" />
              <StatCard value={websitePages} label="Páginas web" icon="🌐" />
              <StatCard
                value={manualStepsCompleted?.bot_activated ? 1 : 0}
                label="Bot activo"
                icon="🤖"
              />
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-4 mb-6">
              <StatCard value={oauthSteps?.posts_imported || 0} label="Posts" icon="📸" />
              <StatCard value={oauthSteps?.youtube_videos_imported || 0} label="Videos" icon="🎬" />
              <StatCard value={oauthSteps?.leads_created || 0} label="Leads" icon="👥" />
              <StatCard value={oauthSteps?.dms_imported || 0} label="DMs" icon="💬" />
            </div>
          )}

          {/* Tone summary */}
          {(toneSummary || setupMode === 'manual') && (
            <div className="bg-gray-900 rounded-xl p-4 mb-6 text-center border border-gray-800">
              <p className="text-sm text-gray-400 mb-1">Tu clon es</p>
              <p className="text-lg font-medium text-white">
                {formatToneSummary()}
              </p>
            </div>
          )}

          {/* Success checklist for manual mode */}
          {setupMode === 'manual' && manualStepsCompleted && (
            <div className="bg-gray-900/50 rounded-xl p-4 mb-6 border border-gray-800">
              <div className="space-y-2">
                <div className="flex items-center gap-2 text-sm">
                  <CheckCircle className={`w-4 h-4 ${manualStepsCompleted.posts_scraped ? 'text-green-500' : 'text-gray-600'}`} />
                  <span className={manualStepsCompleted.posts_scraped ? 'text-white' : 'text-gray-500'}>Posts scrapeados</span>
                </div>
                <div className="flex items-center gap-2 text-sm">
                  <CheckCircle className={`w-4 h-4 ${manualStepsCompleted.tone_profile_generated ? 'text-green-500' : 'text-gray-600'}`} />
                  <span className={manualStepsCompleted.tone_profile_generated ? 'text-white' : 'text-gray-500'}>Tono analizado</span>
                </div>
                <div className="flex items-center gap-2 text-sm">
                  <CheckCircle className={`w-4 h-4 ${manualStepsCompleted.rag_indexed ? 'text-green-500' : 'text-gray-600'}`} />
                  <span className={manualStepsCompleted.rag_indexed ? 'text-white' : 'text-gray-500'}>RAG indexado</span>
                </div>
                <div className="flex items-center gap-2 text-sm">
                  <CheckCircle className={`w-4 h-4 ${manualStepsCompleted.bot_activated ? 'text-green-500' : 'text-gray-600'}`} />
                  <span className={manualStepsCompleted.bot_activated ? 'text-white' : 'text-gray-500'}>Bot activado</span>
                </div>
              </div>
            </div>
          )}

          {/* Tip */}
          <div className="bg-purple-500/10 border border-purple-500/30 rounded-xl p-4 mb-6">
            <p className="text-sm text-gray-300">
              💡 <strong className="text-white">Para vender:</strong> Añade tu
              producto y métodos de pago en Settings
            </p>
          </div>

          {/* CTA */}
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

// Simple StepItem without icon
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
    <div className="bg-gray-900 rounded-xl p-4 text-center border border-gray-800">
      <div className="text-2xl mb-1">{icon}</div>
      <div className="text-2xl font-bold text-white">{value}</div>
      <div className="text-xs text-gray-400">{label}</div>
    </div>
  );
}
