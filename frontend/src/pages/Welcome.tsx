import { useNavigate } from 'react-router-dom';
import { Sparkles, ArrowRight } from 'lucide-react';

export default function Welcome() {
  const navigate = useNavigate();

  return (
    <div
      className="min-h-screen flex items-center justify-center"
      style={{ background: '#09090b' }}
    >
      {/* Background gradient orbs */}
      <div
        style={{
          position: 'fixed',
          top: '20%',
          left: '10%',
          width: '400px',
          height: '400px',
          background: 'radial-gradient(circle, rgba(168, 85, 247, 0.15) 0%, transparent 70%)',
          borderRadius: '50%',
          filter: 'blur(80px)',
          pointerEvents: 'none'
        }}
      />
      <div
        style={{
          position: 'fixed',
          bottom: '20%',
          right: '10%',
          width: '300px',
          height: '300px',
          background: 'radial-gradient(circle, rgba(99, 102, 241, 0.15) 0%, transparent 70%)',
          borderRadius: '50%',
          filter: 'blur(80px)',
          pointerEvents: 'none'
        }}
      />

      <div className="relative z-10 text-center px-6">
        {/* Logo */}
        <div className="flex justify-center mb-6">
          <div
            className="w-16 h-16 rounded-2xl flex items-center justify-center"
            style={{
              background: 'linear-gradient(135deg, #a855f7, #6366f1)',
              boxShadow: '0 8px 32px rgba(168, 85, 247, 0.3)'
            }}
          >
            <Sparkles className="w-8 h-8 text-white" />
          </div>
        </div>

        {/* Title */}
        <h1
          className="text-4xl md:text-5xl font-bold mb-3"
          style={{
            background: 'linear-gradient(135deg, #a855f7, #6366f1)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent'
          }}
        >
          Clonnect
        </h1>

        {/* Subtitle */}
        <p
          className="text-lg mb-10"
          style={{ color: 'rgba(255, 255, 255, 0.5)' }}
        >
          Automatiza tus DMs con IA
        </p>

        {/* Buttons */}
        <div className="flex flex-col gap-3 max-w-xs mx-auto">
          <button
            onClick={() => navigate('/register')}
            className="w-full px-6 py-4 font-semibold rounded-xl transition-all hover:opacity-90 flex items-center justify-center gap-2"
            style={{
              background: 'linear-gradient(135deg, #a855f7, #6366f1)',
              boxShadow: '0 4px 20px rgba(168, 85, 247, 0.3)',
              color: 'white'
            }}
          >
            Crear cuenta
            <ArrowRight className="w-5 h-5" />
          </button>

          <button
            onClick={() => navigate('/login')}
            className="w-full px-6 py-4 font-semibold rounded-xl transition-all hover:opacity-80"
            style={{
              background: 'rgba(255, 255, 255, 0.05)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              color: 'rgba(255, 255, 255, 0.8)'
            }}
          >
            Iniciar sesión
          </button>
        </div>
      </div>
    </div>
  );
}
