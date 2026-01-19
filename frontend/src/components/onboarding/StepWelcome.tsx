import { ArrowRight, Sparkles, MessageCircle, Zap } from 'lucide-react';
import { useOnboarding } from './OnboardingContext';

export function StepWelcome() {
  const { nextStep } = useOnboarding();

  return (
    <div className="flex flex-col items-center justify-center min-h-[80vh] px-6 animate-fade-in">
      {/* Logo */}
      <div className="mb-8">
        <img
          src="/clonnect-logo.png"
          alt="Clonnect"
          className="w-24 h-24 object-contain"
          onError={(e) => {
            e.currentTarget.style.display = 'none';
          }}
        />
      </div>

      {/* Title */}
      <h1
        className="text-3xl md:text-4xl font-bold text-center mb-4"
        style={{
          background: 'linear-gradient(135deg, #a855f7, #6366f1)',
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
        }}
      >
        Bienvenido a Clonnect
      </h1>

      <p className="text-center text-lg mb-10 max-w-md" style={{ color: 'rgba(255, 255, 255, 0.6)' }}>
        Automatiza tus DMs con tu clon de IA personalizado
      </p>

      {/* Features */}
      <div className="grid gap-4 mb-10 w-full max-w-sm">
        <div className="flex items-center gap-4 p-4 rounded-xl" style={{ background: 'rgba(255, 255, 255, 0.03)', border: '1px solid rgba(255, 255, 255, 0.06)' }}>
          <div className="p-2 rounded-lg" style={{ background: 'rgba(168, 85, 247, 0.1)' }}>
            <MessageCircle className="w-5 h-5" style={{ color: '#a855f7' }} />
          </div>
          <div>
            <p className="font-medium text-white">Responde DMs 24/7</p>
            <p className="text-sm" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>Tu clon responde como tú</p>
          </div>
        </div>

        <div className="flex items-center gap-4 p-4 rounded-xl" style={{ background: 'rgba(255, 255, 255, 0.03)', border: '1px solid rgba(255, 255, 255, 0.06)' }}>
          <div className="p-2 rounded-lg" style={{ background: 'rgba(99, 102, 241, 0.1)' }}>
            <Sparkles className="w-5 h-5" style={{ color: '#6366f1' }} />
          </div>
          <div>
            <p className="font-medium text-white">Aprende tu estilo</p>
            <p className="text-sm" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>Analiza tu contenido</p>
          </div>
        </div>

        <div className="flex items-center gap-4 p-4 rounded-xl" style={{ background: 'rgba(255, 255, 255, 0.03)', border: '1px solid rgba(255, 255, 255, 0.06)' }}>
          <div className="p-2 rounded-lg" style={{ background: 'rgba(34, 197, 94, 0.1)' }}>
            <Zap className="w-5 h-5" style={{ color: '#22c55e' }} />
          </div>
          <div>
            <p className="font-medium text-white">Convierte seguidores</p>
            <p className="text-sm" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>En clientes automáticamente</p>
          </div>
        </div>
      </div>

      {/* CTA Button */}
      <button
        onClick={nextStep}
        className="w-full max-w-sm p-4 text-white font-semibold rounded-xl flex items-center justify-center gap-3 transition-all hover:scale-[1.02]"
        style={{
          background: 'linear-gradient(135deg, #a855f7, #6366f1)',
          boxShadow: '0 4px 20px rgba(168, 85, 247, 0.3)',
        }}
      >
        Empezar
        <ArrowRight className="w-5 h-5" />
      </button>

      <p className="text-center text-sm mt-4" style={{ color: 'rgba(255, 255, 255, 0.4)' }}>
        Configuración en menos de 3 minutos
      </p>
    </div>
  );
}
