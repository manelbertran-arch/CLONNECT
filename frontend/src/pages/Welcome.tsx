import { useNavigate } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';

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
          top: '15%',
          left: '5%',
          width: '500px',
          height: '500px',
          background: 'radial-gradient(circle, rgba(168, 85, 247, 0.12) 0%, transparent 70%)',
          borderRadius: '50%',
          filter: 'blur(80px)',
          pointerEvents: 'none'
        }}
      />
      <div
        style={{
          position: 'fixed',
          bottom: '15%',
          right: '5%',
          width: '400px',
          height: '400px',
          background: 'radial-gradient(circle, rgba(99, 102, 241, 0.12) 0%, transparent 70%)',
          borderRadius: '50%',
          filter: 'blur(80px)',
          pointerEvents: 'none'
        }}
      />

      <div className="relative z-10 text-center px-6">
        {/* Title */}
        <h1
          className="text-5xl md:text-6xl font-bold mb-4"
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
          className="text-xl md:text-2xl mb-12"
          style={{ color: 'rgba(255, 255, 255, 0.5)' }}
        >
          Automatiza tus DMs con IA
        </p>

        {/* Buttons */}
        <div className="flex flex-col sm:flex-row gap-4 justify-center">
          <button
            onClick={() => navigate('/register')}
            className="px-8 py-4 text-lg font-semibold rounded-xl transition-all hover:opacity-90 flex items-center justify-center gap-2"
            style={{
              background: 'linear-gradient(135deg, #a855f7, #6366f1)',
              boxShadow: '0 4px 24px rgba(168, 85, 247, 0.35)',
              color: 'white'
            }}
          >
            Crear cuenta
            <ArrowRight className="w-5 h-5" />
          </button>

          <button
            onClick={() => navigate('/login')}
            className="px-8 py-4 text-lg font-semibold rounded-xl transition-all hover:opacity-80"
            style={{
              background: 'rgba(255, 255, 255, 0.05)',
              border: '1px solid rgba(255, 255, 255, 0.15)',
              color: 'rgba(255, 255, 255, 0.85)'
            }}
          >
            Iniciar sesión
          </button>
        </div>
      </div>
    </div>
  );
}
