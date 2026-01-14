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
          top: '20%',
          left: '10%',
          width: '500px',
          height: '500px',
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
          width: '400px',
          height: '400px',
          background: 'radial-gradient(circle, rgba(99, 102, 241, 0.15) 0%, transparent 70%)',
          borderRadius: '50%',
          filter: 'blur(80px)',
          pointerEvents: 'none'
        }}
      />

      <div className="relative z-10 text-center px-6">
        {/* Title */}
        <h1
          className="text-6xl md:text-8xl font-bold mb-6"
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
          className="text-2xl md:text-3xl mb-16"
          style={{ color: 'rgba(255, 255, 255, 0.5)' }}
        >
          Automatiza tus DMs con IA
        </p>

        {/* Buttons */}
        <div className="flex flex-col gap-4 max-w-md mx-auto">
          <button
            onClick={() => navigate('/register')}
            className="w-full px-8 py-5 text-xl font-semibold rounded-2xl transition-all hover:opacity-90 flex items-center justify-center gap-3"
            style={{
              background: 'linear-gradient(135deg, #a855f7, #6366f1)',
              boxShadow: '0 4px 30px rgba(168, 85, 247, 0.4)',
              color: 'white'
            }}
          >
            Crear cuenta
            <ArrowRight className="w-6 h-6" />
          </button>

          <button
            onClick={() => navigate('/login')}
            className="w-full px-8 py-5 text-xl font-semibold rounded-2xl transition-all hover:opacity-80"
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
