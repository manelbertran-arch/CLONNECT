import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Instagram, CheckCircle, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';

type OnboardingStep = 'connect' | 'analyzing' | 'ready';

export default function Onboarding() {
  const [step, setStep] = useState<OnboardingStep>('connect');
  const [progress, setProgress] = useState(0);
  const navigate = useNavigate();

  const handleConnect = async () => {
    // TODO: Implement real Instagram OAuth
    setStep('analyzing');

    // Simulate analysis progress
    const steps = [
      { progress: 20, delay: 500 },
      { progress: 40, delay: 1000 },
      { progress: 60, delay: 1500 },
      { progress: 80, delay: 2000 },
      { progress: 100, delay: 2500 },
    ];

    for (let i = 0; i < steps.length; i++) {
      const s = steps[i];
      const prevDelay = i > 0 ? steps[i - 1].delay : 0;
      await new Promise((r) => setTimeout(r, s.delay - prevDelay));
      setProgress(s.progress);
    }

    setStep('ready');
  };

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
      <div className="max-w-md w-full text-center">
        {/* Step: Connect */}
        {step === 'connect' && (
          <div className="space-y-8">
            <div className="text-6xl">🤖</div>
            <div>
              <h1 className="text-2xl font-bold text-white mb-2">
                Conecta y listo
              </h1>
              <p className="text-gray-400">
                Tu clon aprenderá de tu contenido automáticamente
              </p>
            </div>

            <Button
              onClick={handleConnect}
              size="lg"
              className="w-full bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600"
            >
              <Instagram className="mr-2" />
              Conectar Instagram
            </Button>

            <div className="flex justify-center gap-4 text-gray-500 text-sm">
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-gray-600" />
                Telegram
              </span>
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-gray-600" />
                WhatsApp
              </span>
            </div>
          </div>
        )}

        {/* Step: Analyzing */}
        {step === 'analyzing' && (
          <div className="space-y-8">
            <div className="text-6xl">✨</div>
            <div>
              <h1 className="text-2xl font-bold text-white mb-2">
                Preparando tu clon...
              </h1>
            </div>

            {/* Progress bar */}
            <div className="w-full bg-gray-800 rounded-full h-2">
              <div
                className="bg-gradient-to-r from-purple-500 to-pink-500 h-2 rounded-full transition-all duration-500"
                style={{ width: `${progress}%` }}
              />
            </div>

            {/* Status items */}
            <div className="text-left space-y-3">
              <div
                className={`flex items-center gap-3 ${progress >= 20 ? 'text-white' : 'text-gray-600'}`}
              >
                {progress >= 20 ? (
                  <CheckCircle className="text-green-500" size={20} />
                ) : (
                  <Loader2 className="animate-spin" size={20} />
                )}
                Conectado a Instagram
              </div>
              <div
                className={`flex items-center gap-3 ${progress >= 40 ? 'text-white' : 'text-gray-600'}`}
              >
                {progress >= 40 ? (
                  <CheckCircle className="text-green-500" size={20} />
                ) : (
                  <Loader2 className="animate-spin" size={20} />
                )}
                Analizando tu contenido
              </div>
              <div
                className={`flex items-center gap-3 ${progress >= 70 ? 'text-white' : 'text-gray-600'}`}
              >
                {progress >= 70 ? (
                  <CheckCircle className="text-green-500" size={20} />
                ) : (
                  <Loader2 className="animate-spin" size={20} />
                )}
                Aprendiendo tu tono
              </div>
              <div
                className={`flex items-center gap-3 ${progress >= 100 ? 'text-white' : 'text-gray-600'}`}
              >
                {progress >= 100 ? (
                  <CheckCircle className="text-green-500" size={20} />
                ) : (
                  <Loader2 className="animate-spin" size={20} />
                )}
                Listo para responder
              </div>
            </div>
          </div>
        )}

        {/* Step: Ready */}
        {step === 'ready' && (
          <div className="space-y-8">
            <div className="text-6xl">✅</div>
            <div>
              <h1 className="text-2xl font-bold text-white mb-2">
                Tu clon está activo
              </h1>
              <p className="text-gray-400">
                Ya puede responder mensajes en Instagram
              </p>
            </div>

            <Button
              onClick={() => navigate('/new/inicio')}
              size="lg"
              className="w-full bg-gradient-to-r from-purple-500 to-pink-500"
            >
              Ir al Dashboard →
            </Button>

            <div className="bg-gray-900 rounded-xl p-4 text-left">
              <p className="text-gray-400 text-sm">
                💡{' '}
                <strong className="text-white">Tip:</strong> Añade tu producto y
                métodos de pago para que pueda cerrar ventas.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
