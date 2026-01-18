import { useNavigate } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';

export default function Welcome() {
  const navigate = useNavigate();

  return (
    <div
      className="min-h-screen flex items-center justify-center overflow-hidden"
      style={{ background: '#000000' }}
    >
      {/* Animated background gradient orbs */}
      <div
        style={{
          position: 'fixed',
          top: '10%',
          left: '0%',
          width: '600px',
          height: '600px',
          background: 'radial-gradient(circle, rgba(168, 85, 247, 0.12) 0%, transparent 70%)',
          borderRadius: '50%',
          filter: 'blur(100px)',
          pointerEvents: 'none',
          animation: 'pulse 4s ease-in-out infinite'
        }}
      />
      <div
        style={{
          position: 'fixed',
          bottom: '10%',
          right: '0%',
          width: '500px',
          height: '500px',
          background: 'radial-gradient(circle, rgba(45, 212, 191, 0.10) 0%, transparent 70%)',
          borderRadius: '50%',
          filter: 'blur(100px)',
          pointerEvents: 'none',
          animation: 'pulse 5s ease-in-out infinite',
          animationDelay: '1s'
        }}
      />

      <div
        className="relative z-10 text-center px-6 max-w-4xl mx-auto"
        style={{
          animation: 'fadeInUp 0.8s ease-out'
        }}
      >
        {/* Logo */}
        <div
          className="flex justify-center mb-10"
          style={{ animation: 'fadeInUp 0.6s ease-out' }}
        >
          <img
            src="/clonnect-logo.png"
            alt="Clonnect"
            className="w-64 md:w-80 h-auto"
          />
        </div>

        {/* Main subtitle */}
        <p
          className="text-xl md:text-3xl font-medium mb-4"
          style={{
            color: 'rgba(255, 255, 255, 0.85)',
            animation: 'fadeInUp 0.8s ease-out'
          }}
        >
          Automatiza tus DMs con IA
        </p>

        {/* Secondary subtitle */}
        <p
          className="text-base md:text-xl mb-12"
          style={{
            color: 'rgba(255, 255, 255, 0.5)',
            animation: 'fadeInUp 0.9s ease-out'
          }}
        >
          Convierte conversaciones en ventas mientras duermes
        </p>

        {/* CTA Button with shimmer effect */}
        <div
          className="flex justify-center mb-10"
          style={{ animation: 'fadeInUp 1s ease-out' }}
        >
          <button
            onClick={() => navigate('/login')}
            className="group relative px-12 py-5 text-xl font-semibold rounded-2xl transition-all duration-300 flex items-center justify-center gap-3 hover:scale-105"
            style={{
              background: 'linear-gradient(135deg, #a855f7, #2dd4bf)',
              boxShadow: '0 8px 32px rgba(168, 85, 247, 0.4), 0 0 0 1px rgba(255, 255, 255, 0.1) inset',
              color: 'white'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.boxShadow = '0 12px 48px rgba(168, 85, 247, 0.5), 0 0 0 1px rgba(255, 255, 255, 0.2) inset';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.boxShadow = '0 8px 32px rgba(168, 85, 247, 0.4), 0 0 0 1px rgba(255, 255, 255, 0.1) inset';
            }}
          >
            {/* Shimmer effect overlay */}
            <div
              className="absolute inset-0 rounded-2xl overflow-hidden"
              style={{ pointerEvents: 'none' }}
            >
              <div
                style={{
                  position: 'absolute',
                  top: 0,
                  left: '-100%',
                  width: '100%',
                  height: '100%',
                  background: 'linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.2), transparent)',
                  animation: 'shimmer 3s infinite'
                }}
              />
            </div>
            <span className="relative z-10">Empezar</span>
            <ArrowRight className="w-6 h-6 relative z-10 transition-transform group-hover:translate-x-1" />
          </button>
        </div>

        {/* Social proof badge */}
        <div
          className="flex justify-center"
          style={{ animation: 'fadeInUp 1.1s ease-out' }}
        >
          <div
            className="flex items-center gap-3 px-5 py-3 rounded-full"
            style={{
              background: 'rgba(255, 255, 255, 0.03)',
              border: '1px solid rgba(255, 255, 255, 0.08)'
            }}
          >
            {/* Avatar stack */}
            <div className="flex -space-x-2">
              {['#a855f7', '#c026d3', '#2dd4bf'].map((color, i) => (
                <div
                  key={i}
                  className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-medium"
                  style={{
                    background: color,
                    border: '2px solid #000000',
                    color: 'white'
                  }}
                >
                  {['M', 'A', 'L'][i]}
                </div>
              ))}
            </div>
            <span style={{ color: 'rgba(255, 255, 255, 0.6)', fontSize: '14px' }}>
              <span style={{ color: 'rgba(255, 255, 255, 0.9)', fontWeight: 500 }}>500+</span> creators ya automatizan sus DMs
            </span>
          </div>
        </div>
      </div>

      {/* CSS Animations */}
      <style>{`
        @keyframes fadeInUp {
          from {
            opacity: 0;
            transform: translateY(30px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }

        @keyframes shimmer {
          0% {
            left: -100%;
          }
          100% {
            left: 100%;
          }
        }

        @keyframes pulse {
          0%, 100% {
            opacity: 1;
          }
          50% {
            opacity: 0.6;
          }
        }
      `}</style>
    </div>
  );
}
