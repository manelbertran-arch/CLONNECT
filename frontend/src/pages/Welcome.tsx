import { useNavigate } from 'react-router-dom';
import { Sparkles, ArrowRight } from 'lucide-react';

export default function Welcome() {
  const navigate = useNavigate();

  // No auto-redirect - always show welcome page
  // User chooses to login or register

  return (
    <div
      className="min-h-screen flex items-center justify-center"
      style={{ background: '#09090b' }}
    >
      {/* Background gradient orbs */}
      <div
        style={{
          position: 'fixed',
          top: '5%',
          left: '5%',
          width: '500px',
          height: '500px',
          background: 'radial-gradient(circle, rgba(168, 85, 247, 0.2) 0%, transparent 70%)',
          borderRadius: '50%',
          filter: 'blur(80px)',
          pointerEvents: 'none'
        }}
      />
      <div
        style={{
          position: 'fixed',
          bottom: '5%',
          right: '5%',
          width: '400px',
          height: '400px',
          background: 'radial-gradient(circle, rgba(99, 102, 241, 0.2) 0%, transparent 70%)',
          borderRadius: '50%',
          filter: 'blur(80px)',
          pointerEvents: 'none'
        }}
      />
      <div
        style={{
          position: 'fixed',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          width: '600px',
          height: '600px',
          background: 'radial-gradient(circle, rgba(139, 92, 246, 0.1) 0%, transparent 70%)',
          borderRadius: '50%',
          filter: 'blur(100px)',
          pointerEvents: 'none'
        }}
      />

      <div className="relative z-10 text-center px-6 max-w-2xl">
        {/* Logo */}
        <div className="flex justify-center mb-8">
          <div
            className="w-20 h-20 rounded-2xl flex items-center justify-center"
            style={{
              background: 'linear-gradient(135deg, #a855f7, #6366f1)',
              boxShadow: '0 8px 40px rgba(168, 85, 247, 0.4)'
            }}
          >
            <Sparkles className="w-10 h-10 text-white" />
          </div>
        </div>

        {/* Title */}
        <h1
          className="text-5xl md:text-6xl font-bold mb-4"
          style={{
            background: 'linear-gradient(135deg, #a855f7, #6366f1, #a855f7)',
            backgroundSize: '200% 200%',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            animation: 'gradient 3s ease infinite'
          }}
        >
          Clonnect
        </h1>

        {/* Subtitle */}
        <p
          className="text-xl md:text-2xl mb-12"
          style={{ color: 'rgba(255, 255, 255, 0.6)' }}
        >
          Automatiza tus DMs con IA y convierte seguidores en clientes
        </p>

        {/* Buttons */}
        <div className="flex flex-col sm:flex-row gap-4 justify-center">
          {/* Register Button - Primary */}
          <button
            onClick={() => navigate('/register')}
            className="px-8 py-4 font-semibold rounded-xl transition-all hover:scale-105 flex items-center justify-center gap-2"
            style={{
              background: 'linear-gradient(135deg, #a855f7, #6366f1)',
              boxShadow: '0 4px 20px rgba(168, 85, 247, 0.4)',
              color: 'white',
              fontSize: '1.1rem'
            }}
          >
            Crear cuenta gratis
            <ArrowRight className="w-5 h-5" />
          </button>

          {/* Login Button - Secondary */}
          <button
            onClick={() => navigate('/login')}
            className="px-8 py-4 font-semibold rounded-xl transition-all hover:opacity-90 flex items-center justify-center gap-2"
            style={{
              background: 'rgba(255, 255, 255, 0.05)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              color: 'rgba(255, 255, 255, 0.9)',
              fontSize: '1.1rem'
            }}
          >
            Ya tengo cuenta
          </button>
        </div>

        {/* Features */}
        <div className="mt-16 grid grid-cols-1 sm:grid-cols-3 gap-6">
          {[
            { icon: '🤖', title: 'IA que vende', desc: 'Responde como tú 24/7' },
            { icon: '📈', title: 'Más ventas', desc: 'Convierte DMs en clientes' },
            { icon: '⚡', title: 'Sin esfuerzo', desc: 'Configura en 5 minutos' }
          ].map((feature, i) => (
            <div
              key={i}
              className="p-6 rounded-xl"
              style={{
                background: 'rgba(255, 255, 255, 0.03)',
                border: '1px solid rgba(255, 255, 255, 0.06)'
              }}
            >
              <div className="text-3xl mb-3">{feature.icon}</div>
              <h3 className="font-semibold text-white mb-1">{feature.title}</h3>
              <p style={{ color: 'rgba(255, 255, 255, 0.5)', fontSize: '0.9rem' }}>
                {feature.desc}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* CSS Animation */}
      <style>{`
        @keyframes gradient {
          0%, 100% { background-position: 0% 50%; }
          50% { background-position: 100% 50%; }
        }
      `}</style>
    </div>
  );
}
