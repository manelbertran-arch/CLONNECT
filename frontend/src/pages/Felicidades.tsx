import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Check, Sparkles, ArrowRight, Instagram, MessageSquare, Zap } from 'lucide-react';

export default function Felicidades() {
  const navigate = useNavigate();
  const [showConfetti, setShowConfetti] = useState(true);

  useEffect(() => {
    // Hide confetti after animation
    const timer = setTimeout(() => setShowConfetti(false), 3000);
    return () => clearTimeout(timer);
  }, []);

  return (
    <div className="min-h-screen flex items-center justify-center overflow-hidden" style={{ background: '#09090b' }}>
      {/* Success background glow */}
      <div
        style={{
          position: 'fixed', top: '10%', left: '10%', width: '400px', height: '400px',
          background: 'radial-gradient(circle, rgba(34, 197, 94, 0.15) 0%, transparent 70%)',
          borderRadius: '50%', filter: 'blur(60px)', pointerEvents: 'none'
        }}
      />
      <div
        style={{
          position: 'fixed', bottom: '10%', right: '10%', width: '300px', height: '300px',
          background: 'radial-gradient(circle, rgba(168, 85, 247, 0.1) 0%, transparent 70%)',
          borderRadius: '50%', filter: 'blur(60px)', pointerEvents: 'none'
        }}
      />

      {/* Confetti animation (simple CSS version) */}
      {showConfetti && (
        <div className="fixed inset-0 pointer-events-none overflow-hidden">
          {[...Array(20)].map((_, i) => (
            <div
              key={i}
              className="absolute animate-bounce"
              style={{
                left: `${Math.random() * 100}%`,
                top: `-20px`,
                animationDelay: `${Math.random() * 2}s`,
                animationDuration: `${2 + Math.random() * 2}s`,
              }}
            >
              <Sparkles
                className="w-4 h-4"
                style={{
                  color: ['#22c55e', '#a855f7', '#6366f1', '#f59e0b'][Math.floor(Math.random() * 4)]
                }}
              />
            </div>
          ))}
        </div>
      )}

      <div
        className="p-8 rounded-2xl w-full max-w-md relative z-10 text-center"
        style={{ background: '#0f0f14', border: '1px solid rgba(34, 197, 94, 0.2)' }}
      >
        {/* Success Icon */}
        <div className="flex justify-center mb-6">
          <div
            className="w-24 h-24 rounded-full flex items-center justify-center animate-pulse"
            style={{ background: 'linear-gradient(135deg, #22c55e, #16a34a)' }}
          >
            <Check className="w-12 h-12 text-white" strokeWidth={3} />
          </div>
        </div>

        {/* Title */}
        <h1
          className="text-3xl font-bold mb-3"
          style={{
            background: 'linear-gradient(135deg, #22c55e, #16a34a)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent'
          }}
        >
          ¡Felicidades!
        </h1>

        <p className="text-xl text-white mb-2">Tu clon está listo</p>
        <p className="mb-8" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>
          Ya puedes empezar a automatizar tus DMs de Instagram
        </p>

        {/* Features */}
        <div className="space-y-3 mb-8">
          <div
            className="p-4 rounded-xl flex items-center gap-4"
            style={{ background: 'rgba(255, 255, 255, 0.03)', border: '1px solid rgba(255, 255, 255, 0.06)' }}
          >
            <div className="p-2 rounded-lg" style={{ background: 'rgba(228, 64, 95, 0.1)' }}>
              <Instagram className="w-5 h-5" style={{ color: '#E4405F' }} />
            </div>
            <div className="text-left flex-1">
              <p className="text-white font-medium">Instagram conectado</p>
              <p className="text-sm" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>
                Listo para recibir DMs
              </p>
            </div>
            <Check className="w-5 h-5" style={{ color: '#22c55e' }} />
          </div>

          <div
            className="p-4 rounded-xl flex items-center gap-4"
            style={{ background: 'rgba(255, 255, 255, 0.03)', border: '1px solid rgba(255, 255, 255, 0.06)' }}
          >
            <div className="p-2 rounded-lg" style={{ background: 'rgba(168, 85, 247, 0.1)' }}>
              <MessageSquare className="w-5 h-5" style={{ color: '#a855f7' }} />
            </div>
            <div className="text-left flex-1">
              <p className="text-white font-medium">Clon entrenado</p>
              <p className="text-sm" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>
                Aprendió tu estilo
              </p>
            </div>
            <Check className="w-5 h-5" style={{ color: '#22c55e' }} />
          </div>

          <div
            className="p-4 rounded-xl flex items-center gap-4"
            style={{ background: 'rgba(255, 255, 255, 0.03)', border: '1px solid rgba(255, 255, 255, 0.06)' }}
          >
            <div className="p-2 rounded-lg" style={{ background: 'rgba(34, 197, 94, 0.1)' }}>
              <Zap className="w-5 h-5" style={{ color: '#22c55e' }} />
            </div>
            <div className="text-left flex-1">
              <p className="text-white font-medium">Bot activado</p>
              <p className="text-sm" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>
                Respondiendo automáticamente
              </p>
            </div>
            <Check className="w-5 h-5" style={{ color: '#22c55e' }} />
          </div>
        </div>

        {/* CTA Button */}
        <button
          onClick={() => navigate('/dashboard')}
          className="w-full p-4 text-white font-semibold rounded-xl flex items-center justify-center gap-3 transition-all hover:scale-[1.02]"
          style={{
            background: 'linear-gradient(135deg, #22c55e, #16a34a)',
            boxShadow: '0 4px 20px rgba(34, 197, 94, 0.3)'
          }}
        >
          Ir al Dashboard
          <ArrowRight className="w-5 h-5" />
        </button>

        <p className="text-sm mt-4" style={{ color: 'rgba(255, 255, 255, 0.4)' }}>
          Configura más opciones desde el panel de control
        </p>
      </div>
    </div>
  );
}
