import { useNavigate } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';

export default function Welcome() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen flex items-center justify-center bg-black">
      <div className="text-center px-6">
        {/* Logo - más grande */}
        <img
          src="/clonnect-logo.png"
          alt="Clonnect"
          className="w-72 md:w-96 h-auto mx-auto"
        />

        {/* Subtitle - más pequeño */}
        <p className="text-lg md:text-xl text-gray-400 -mt-2 mb-10">
          Automatiza tus DMs con IA
        </p>

        {/* CTA Button - blanco con glow púrpura */}
        <button
          onClick={() => navigate('/login')}
          className="group relative px-10 py-4 text-lg font-semibold bg-white text-gray-900 rounded-xl transition-all duration-300 hover:scale-105 flex items-center gap-2 mx-auto border border-purple-500/20"
          style={{
            boxShadow: '0 4px 24px rgba(168, 85, 247, 0.3), 0 0 0 1px rgba(168, 85, 247, 0.1)'
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.boxShadow = '0 8px 40px rgba(168, 85, 247, 0.5), 0 0 0 1px rgba(168, 85, 247, 0.3)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.boxShadow = '0 4px 24px rgba(168, 85, 247, 0.3), 0 0 0 1px rgba(168, 85, 247, 0.1)';
          }}
        >
          {/* Shimmer effect */}
          <div className="absolute inset-0 rounded-xl overflow-hidden pointer-events-none">
            <div
              className="absolute inset-0 -translate-x-full group-hover:translate-x-full transition-transform duration-1000"
              style={{
                background: 'linear-gradient(90deg, transparent, rgba(168, 85, 247, 0.1), transparent)'
              }}
            />
          </div>
          <span className="relative z-10">Empezar</span>
          <ArrowRight className="w-5 h-5 relative z-10 transition-transform group-hover:translate-x-1" />
        </button>
      </div>
    </div>
  );
}
