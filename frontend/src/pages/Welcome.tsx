import { useNavigate } from 'react-router-dom';
import { ArrowRight, MessageSquare, Sparkles } from 'lucide-react';

export default function Welcome() {
  const navigate = useNavigate();

  return (
    <div
      className="min-h-screen flex items-center justify-center overflow-hidden"
      style={{ background: '#09090b' }}
    >
      {/* Animated background gradient orbs */}
      <div
        className="animate-pulse"
        style={{
          position: 'fixed',
          top: '10%',
          left: '0%',
          width: '600px',
          height: '600px',
          background: 'radial-gradient(circle, rgba(168, 85, 247, 0.15) 0%, transparent 70%)',
          borderRadius: '50%',
          filter: 'blur(100px)',
          pointerEvents: 'none',
          animation: 'pulse 4s ease-in-out infinite'
        }}
      />
      <div
        className="animate-pulse"
        style={{
          position: 'fixed',
          bottom: '10%',
          right: '0%',
          width: '500px',
          height: '500px',
          background: 'radial-gradient(circle, rgba(236, 72, 153, 0.12) 0%, transparent 70%)',
          borderRadius: '50%',
          filter: 'blur(100px)',
          pointerEvents: 'none',
          animation: 'pulse 5s ease-in-out infinite',
          animationDelay: '1s'
        }}
      />
      <div
        style={{
          position: 'fixed',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          width: '800px',
          height: '800px',
          background: 'radial-gradient(circle, rgba(99, 102, 241, 0.08) 0%, transparent 60%)',
          borderRadius: '50%',
          filter: 'blur(120px)',
          pointerEvents: 'none'
        }}
      />

      {/* Grid pattern overlay */}
      <div
        style={{
          position: 'fixed',
          inset: 0,
          backgroundImage: `radial-gradient(rgba(255, 255, 255, 0.03) 1px, transparent 1px)`,
          backgroundSize: '50px 50px',
          pointerEvents: 'none'
        }}
      />

      <div
        className="relative z-10 text-center px-6 max-w-4xl mx-auto"
        style={{
          animation: 'fadeInUp 0.8s ease-out'
        }}
      >
        {/* Icon */}
        <div
          className="flex justify-center mb-8"
          style={{ animation: 'fadeInUp 0.6s ease-out' }}
        >
          <div
            className="relative"
            style={{
              padding: '20px',
              borderRadius: '24px',
              background: 'linear-gradient(135deg, rgba(168, 85, 247, 0.1), rgba(236, 72, 153, 0.1))',
              border: '1px solid rgba(168, 85, 247, 0.2)'
            }}
          >
            <MessageSquare
              className="w-12 h-12"
              style={{ color: '#a855f7' }}
            />
            <Sparkles
              className="w-5 h-5 absolute -top-1 -right-1"
              style={{ color: '#ec4899' }}
            />
          </div>
        </div>

        {/* Title with glow effect */}
        <h1
          className="text-6xl md:text-8xl font-bold mb-6 tracking-tight"
          style={{
            background: 'linear-gradient(135deg, #a855f7 0%, #ec4899 50%, #6366f1 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            filter: 'drop-shadow(0 0 30px rgba(168, 85, 247, 0.3))',
            animation: 'fadeInUp 0.7s ease-out'
          }}
        >
          Clonnect
        </h1>

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
              background: 'linear-gradient(135deg, #a855f7, #ec4899)',
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
              {['#a855f7', '#ec4899', '#6366f1'].map((color, i) => (
                <div
                  key={i}
                  className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-medium"
                  style={{
                    background: color,
                    border: '2px solid #09090b',
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
